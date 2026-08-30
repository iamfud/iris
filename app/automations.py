"""Iris 3.0 — Automations Engine

Central condition evaluation, rate-limiting, and action dispatch pipeline.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("iris.automations")

_ENGINE: Optional["AutomationsEngine"] = None
_LOCK = threading.Lock()


def get_engine() -> "AutomationsEngine":
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = AutomationsEngine()
        return _ENGINE


class AutomationsEngine:
    """Manages active automation rules, state caches, and action execution."""

    def __init__(self):
        self._rules: List[Dict[str, Any]] = []
        self._state_cache: Dict[str, Dict[str, Any]] = {}
        self._prev_state_cache: Dict[str, Dict[str, Any]] = {}
        self._cooldown_tracker: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._disclaimer_acknowledged = False

    def load_config(self, cfg: Dict[str, Any]):
        with self._lock:
            self._rules = list(cfg.get("automations", []))
            self._disclaimer_acknowledged = bool(cfg.get("automations_disclaimer_ack", False))
            log.info("[automations] loaded %d rules (disclaimer_ack=%s)", len(self._rules), self._disclaimer_acknowledged)

    def set_disclaimer_ack(self, ack: bool = True):
        with self._lock:
            self._disclaimer_acknowledged = ack

    def is_disclaimer_acknowledged(self) -> bool:
        with self._lock:
            return self._disclaimer_acknowledged

    def get_rules(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._rules]

    def save_rules(self, rules: List[Dict[str, Any]], cfg: Dict[str, Any]):
        with self._lock:
            self._rules = list(rules)
            cfg["automations"] = list(rules)
        try:
            from config import save_config
            save_config(cfg)
        except Exception as ex:
            log.warning("[automations] failed to persist config: %s", ex)

    def dispatch_state(self, source_type: str, source_id: str, state: Dict[str, Any]):
        if not state:
            return
        cache_key = f"{source_type}:{source_id}"

        # Namespaced state map e.g. "elite_dangerous.shields_up": True
        augmented_state = dict(state)
        for k, v in state.items():
            augmented_state[f"{source_id}.{k}"] = v

        with self._lock:
            prev_state = self._state_cache.get(cache_key, {})
            self._state_cache[cache_key] = dict(augmented_state)
            active_rules = [r for r in self._rules if r.get("enabled", True)
                            and (not r.get("source_type") or r.get("source_type") == source_type)
                            and (not r.get("source_id") or r.get("source_id") == source_id)]

        for rule in active_rules:
            try:
                self._evaluate_rule(rule, augmented_state, prev_state)
            except Exception as ex:
                log.warning("[automations] error evaluating rule %s: %s", rule.get("id"), ex)

    def _evaluate_rule(self, rule: Dict[str, Any], curr_state: Dict[str, Any], prev_state: Dict[str, Any]):
        trigger_key = rule.get("trigger_key", "")
        if not trigger_key:
            return

        # Resolve entity state key dynamically from registry if available
        val_key = trigger_key
        if val_key not in curr_state:
            # Check if trigger_key is an entity ID like "elite_dangerous.shields" -> state_key "shields_up"
            try:
                import panel_entities
                ent = panel_entities.get_entity(trigger_key)
                if ent:
                    st_key = ent.get("state_key")
                    plg = ent.get("plugin")
                    if st_key and st_key in curr_state:
                        val_key = st_key
                    elif st_key and plg and f"{plg}.{st_key}" in curr_state:
                        val_key = f"{plg}.{st_key}"
            except Exception:
                pass

        if val_key not in curr_state:
            return

        curr_val = curr_state.get(val_key)
        prev_val = prev_state.get(val_key)

        op = rule.get("operator", "==")
        target_val = rule.get("target_value")

        curr_match = self._compare(curr_val, op, target_val)
        prev_match = self._compare(prev_val, op, target_val) if prev_val is not None else False

        is_edge = curr_match and not prev_match

        if curr_match:
            now = time.time()
            rule_id = rule.get("id", "rule")
            cooldown_s = float(rule.get("cooldown_s", 5.0))

            with self._lock:
                last_fired = self._cooldown_tracker.get(rule_id, 0.0)

            if is_edge or (now - last_fired >= cooldown_s):
                with self._lock:
                    self._cooldown_tracker[rule_id] = now
                self._execute_actions(rule, curr_val)

    @staticmethod
    def _compare(val: Any, op: str, target: Any) -> bool:
        if val is None or target is None:
            return False
        try:
            if isinstance(target, (int, float)) and not isinstance(target, bool):
                val_num = float(val)
                tgt_num = float(target)
                if op == "==": return abs(val_num - tgt_num) < 0.001
                if op == "!=": return abs(val_num - tgt_num) >= 0.001
                if op == "<":  return val_num < tgt_num
                if op == "<=": return val_num <= tgt_num
                if op == ">":  return val_num > tgt_num
                if op == ">=": return val_num >= tgt_num

            if isinstance(target, bool) or isinstance(val, bool):
                val_b = bool(val)
                tgt_b = bool(target)
                return (val_b == tgt_b) if op == "==" else (val_b != tgt_b)

            val_s = str(val).strip().lower()
            tgt_s = str(target).strip().lower()
            if op == "==": return val_s == tgt_s
            if op == "!=": return val_s != tgt_s
            if op == "contains": return tgt_s in val_s

        except Exception:
            pass
        return False

    def _execute_actions(self, rule: Dict[str, Any], trigger_value: Any):
        rule_name = rule.get("name", "Automation")
        exe = rule.get("exe", "")
        req_fg = rule.get("require_foreground", True)

        if req_fg and exe:
            try:
                from plugin_manager import is_exe_foreground
                if not is_exe_foreground(exe):
                    log.debug("[automations] rule '%s' suppressed: %s not in foreground", rule_name, exe)
                    return
            except Exception:
                pass

        actions = rule.get("actions", [])
        duration_s = float(rule.get("duration_s", 0) or 0)
        log.info("[automations] firing rule '%s' (actions=%d, val=%s, duration=%.1fs)", rule_name, len(actions), trigger_value, duration_s)

        # Snapshot active state before applying actions for revert
        prev_openrgb_profile = None
        has_ha_actions = any(
            act.get("type") in ("home_assistant", "ha") or
            (act.get("type") == "slot" and ((act.get("slot") or {}).get("plugin") == "ha" or str((act.get("slot") or {}).get("entity", "")).startswith("ha.")))
            for act in actions
        )
        ha_scene_id = None
        try:
            import plugin_manager
            rgb_inst = plugin_manager.get("openrgb")
            if rgb_inst and hasattr(rgb_inst, "poll"):
                prev_openrgb_profile = rgb_inst.poll().get("active_profile")
        except Exception:
            pass

        if duration_s > 0 and has_ha_actions:
            try:
                import plugin_manager
                ha_inst = plugin_manager.get("ha")
                if ha_inst and hasattr(ha_inst, "_connector"):
                    ents = ha_inst.get_entities() or []
                    light_ids = [e["entity_id"] for e in ents if e.get("domain") == "light"]
                    if light_ids:
                        ha_scene_id = f"iris_snap_{rule.get('id', 'rule').replace('-', '_')}"
                        ha_inst._connector.call_service("scene", "create", {
                            "scene_id": ha_scene_id,
                            "snapshot_entities": light_ids
                        })
                        log.info("[automations] created HA scene snapshot '%s' for %d lights", ha_scene_id, len(light_ids))
            except Exception as ex:
                log.warning("[automations] failed to create HA scene snapshot: %s", ex)

        for act in actions:
            act_type = act.get("type")
            try:
                if act_type == "hotkey":
                    self._act_hotkey(act, rule_name)
                elif act_type in ("home_assistant", "ha"):
                    self._act_home_assistant(act)
                elif act_type == "slot" or act.get("slot"):
                    self._act_slot(act.get("slot") or act)
                elif act_type == "openrgb":
                    self._act_openrgb(act)
                elif act_type == "sound":
                    self._act_sound(act)
                elif act_type == "notification":
                    self._act_notification(act, trigger_value)
            except Exception as ex:
                log.warning("[automations] failed to execute action %s: %s", act_type, ex)

        # If a revert duration is specified (> 0), schedule return to previous state
        if duration_s > 0:
            def _revert():
                time.sleep(duration_s)
                log.info("[automations] reverting rule '%s' after %.1fs", rule_name, duration_s)
                if prev_openrgb_profile:
                    try:
                        import plugin_manager
                        rgb_inst = plugin_manager.get("openrgb")
                        if rgb_inst and hasattr(rgb_inst, "_apply_profile"):
                            rgb_inst._apply_profile(prev_openrgb_profile)
                        else:
                            from plugins.openrgb.connector import OpenRGBConnector
                            conn = OpenRGBConnector()
                            conn._apply_profile(prev_openrgb_profile)
                    except Exception as ex:
                        log.warning("[automations] failed to revert OpenRGB profile: %s", ex)

                if ha_scene_id:
                    try:
                        import plugin_manager
                        ha_inst = plugin_manager.get("ha")
                        if ha_inst and hasattr(ha_inst, "_connector"):
                            ha_inst._connector.call_service("scene", "turn_on", entity_id=f"scene.{ha_scene_id}")
                            log.info("[automations] restored HA scene snapshot '%s'", ha_scene_id)
                    except Exception as ex:
                        log.warning("[automations] failed to restore HA scene snapshot: %s", ex)
            threading.Thread(target=_revert, daemon=True, name=f"iris-auto-revert-{rule.get('id', 'rule')}").start()

    def _act_slot(self, slot: Dict[str, Any]):
        def _exec():
            try:
                from panel_runtime import execute_slot
                execute_slot(slot)
            except Exception as ex:
                log.warning("[automations] slot action execution failed: %s", ex)
        threading.Thread(target=_exec, daemon=True, name="iris-auto-slot").start()

    def _act_openrgb(self, act: Dict[str, Any]):
        profile = act.get("profile", "")
        if not profile:
            return
        def _set_rgb():
            try:
                import plugin_manager
                inst = plugin_manager.get("openrgb")
                if inst and hasattr(inst, "_apply_profile"):
                    inst._apply_profile(profile)
                else:
                    from plugins.openrgb.connector import OpenRGBConnector
                    conn = OpenRGBConnector()
                    conn._apply_profile(profile)
            except Exception as ex:
                log.warning("[automations] OpenRGB profile dispatch failed: %s", ex)
        threading.Thread(target=_set_rgb, daemon=True, name="iris-auto-openrgb").start()

    def _act_hotkey(self, act: Dict[str, Any], rule_name: str):
        if not self._disclaimer_acknowledged:
            log.warning("[automations] hotkey execution blocked: disclaimer not acknowledged")
            return
        key = act.get("hotkey")
        if not key:
            return
        hold = float(act.get("hold_duration", 0.05))

        def _send():
            try:
                import keyboard_service
                keyboard_service.send_sequence(key, hold_duration=hold)
            except Exception as ex:
                log.warning("[automations] keystroke injection failed: %s", ex)

        threading.Thread(target=_send, daemon=True, name="iris-auto-hotkey").start()

    def _act_home_assistant(self, act: Dict[str, Any]):
        entity_id = act.get("entity_id", "")
        service = act.get("service", "toggle")
        domain = act.get("domain") or (entity_id.split(".")[0] if "." in entity_id else "homeassistant")
        service_data = act.get("data", {})

        def _call_ha():
            try:
                import plugin_manager
                inst = plugin_manager.get("ha")
                if inst and hasattr(inst, "_connector"):
                    inst._connector.call_service(domain, service, service_data, entity_id)
                else:
                    from plugins.ha.connector import HASSConnector
                    from config import load_config
                    conn = HASSConnector(load_config())
                    conn.call_service(domain, service, service_data, entity_id)
            except Exception as ex:
                log.warning("[automations] HA dispatch failed: %s", ex)

        threading.Thread(target=_call_ha, daemon=True, name="iris-auto-ha").start()

    def _act_sound(self, act: Dict[str, Any]):
        sound_name = act.get("sound", "remind")
        try:
            import alarm_sound
            alarm_sound.play_one_shot(sound_name)
        except Exception as ex:
            log.warning("[automations] audio alert failed: %s", ex)

    def _act_notification(self, act: Dict[str, Any], trigger_value: Any):
        title = act.get("title", "Iris Automation")
        msg = act.get("message", f"Triggered: {trigger_value}")
        try:
            import ws_bridge
            ws_bridge.broadcast({
                "type": "notification",
                "notification": {
                    "app": "Automations",
                    "title": title,
                    "body": msg,
                    "theme": "alert",
                    "timestamp": int(time.time()),
                }
            })
        except Exception:
            pass
