"""Iris 3.0 — Automations Engine

Central state-condition evaluation, per-action conditional execution, auto-release, and rate-limiting.

Key Design:
- Rules contain an inline action pipeline (`actions`).
- When a state matches an action (e.g. Shields == DOWN), that action/alert is activated.
- When the state is NO LONGER matching (e.g. Shields becomes ONLINE), any active continuous alert
  is automatically released/popped back to the profile baseline without needing a manual return rule.
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
        self._last_matched_states: Dict[str, Any] = {}
        self._active_alert_rules: set[str] = set()
        self._fired_days: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._disclaimer_acknowledged = False
        self._tick_thread: Optional[threading.Thread] = None
        self._tick_stop = threading.Event()
        self._tick_started = False

    def start(self):
        """Start the periodic state-sourcing tick (sensor/time rule evaluation)."""
        with self._lock:
            if self._tick_started:
                return
            self._tick_started = True
            self._tick_stop.clear()
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True, name="iris-automations-tick")
        self._tick_thread.start()

    def stop(self):
        """Stop the periodic tick thread."""
        self._tick_stop.set()
        t = self._tick_thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=3)
            self._tick_thread = None
        with self._lock:
            self._tick_started = False

    def _tick_loop(self):
        while not self._tick_stop.is_set():
            try:
                self._source_all_states()
            except Exception as ex:
                log.warning("[automations] tick sourcing error: %s", ex)
            self._tick_stop.wait(1.0)

    def _source_all_states(self):
        """Merge live entity values (including Time) into the engine state and re-evaluate."""
        merged = {}
        try:
            from panel_entities import get_live_entity_states
            live = get_live_entity_states()
            if isinstance(live, dict):
                for key, valdict in live.items():
                    if isinstance(valdict, dict) and "value" in valdict:
                        merged[key.split(":")[-1]] = valdict.get("value")
                        merged[key] = valdict.get("value")
                    elif isinstance(valdict, dict):
                        for k2, v2 in valdict.items():
                            if k2 == "value":
                                merged[key] = v2
            # Plugin raw polls for full sensor coverage
            try:
                import plugin_manager
                polled = plugin_manager.poll_all()
                if isinstance(polled, dict):
                    for pname, pdata in polled.items():
                        if not isinstance(pdata, dict):
                            continue
                        for k, v in pdata.items():
                            if k in ("available", "state", "status", "layout", "fields"):
                                continue
                            if isinstance(v, (int, float, bool, str)) and not isinstance(v, dict):
                                merged[f"{pname}.{k}"] = v
            except Exception:
                pass
        except Exception as ex:
            log.warning("[automations] tick state source failed: %s", ex)
            return

        if not merged:
            return
        self.dispatch_state("live", "all", merged)

    def load_config(self, cfg: Dict[str, Any]):
        with self._lock:
            self._rules = list(cfg.get("automations", []))
            self._disclaimer_acknowledged = bool(cfg.get("automations_disclaimer_ack", False))
            log.info("[automations] loaded %d rules (disclaimer_ack=%s)", len(self._rules), self._disclaimer_acknowledged)
        self.start()

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
        rule_id = rule.get("id", "rule")
        now = time.time()
        cooldown_s = float(rule.get("cooldown_s", 2.0))

        # Check foreground requirement
        exe = rule.get("exe", "")
        req_fg = rule.get("require_foreground", True)
        if req_fg and exe:
            try:
                from plugin_manager import is_exe_foreground
                if not is_exe_foreground(exe):
                    return
            except Exception:
                pass

        # Evaluate inline action pipeline
        actions = rule.get("actions", [])
        matched_actions = []

        for a_idx, act in enumerate(actions):
            cond = act.get("condition") or {}
            op = cond.get("operator") or act.get("operator") or rule.get("operator", "==")
            tgt = cond.get("target_value") if "target_value" in cond else (act.get("target_value") if "target_value" in act else rule.get("target_value"))

            if tgt is None:
                matched_actions.append(act)
                continue

            curr_match = self._compare(curr_val, op, tgt)
            if curr_match:
                matched_actions.append(act)

        # ── AUTOMATIC RELEASE & RESET ──────────────────────────
        # If this rule was previously actively holding an alert state, but the state has now stopped matching:
        if not matched_actions:
            with self._lock:
                had_active_alert = rule_id in self._active_alert_rules
                if had_active_alert:
                    self._active_alert_rules.remove(rule_id)
                    self._last_matched_states[rule_id] = curr_val

            if had_active_alert:
                log.info("[automations] rule '%s' condition no longer active (val=%s) -> auto-releasing to baseline", rule.get("name"), curr_val)
                try:
                    from lighting_service import get_lighting_service
                    get_lighting_service().pop_alert()
                except Exception as ex:
                    log.warning("[automations] auto pop_alert failed: %s", ex)
            return

        # ── TIME TRIGGER RISING-EDGE ────────────────────────
        # For time-based triggers (time.*): fire once when condition
        # transitions from false → true; suppress while true.
        is_time_trigger = trigger_key.startswith("time.")

        with self._lock:
            was_active = rule_id in self._active_alert_rules
            self._active_alert_rules.add(rule_id)

        if is_time_trigger and was_active:
            return

        # ── STANDARD DISPATCH GATE ──────────────────────────
        with self._lock:
            last_state = self._last_matched_states.get(rule_id)
            last_fired = self._cooldown_tracker.get(rule_id, 0.0)

        is_state_flip = (last_state != curr_val)
        if is_state_flip or (now - last_fired >= cooldown_s):
            with self._lock:
                self._last_matched_states[rule_id] = curr_val
                self._cooldown_tracker[rule_id] = now
            self._dispatch_matched_actions(rule, matched_actions, curr_val)

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

            if op == "contains":
                return tgt_s in val_s

            try:
                val_f = float(val)
                tgt_f = float(target)
                if op == "==": return abs(val_f - tgt_f) < 0.001
                if op == "!=": return abs(val_f - tgt_f) >= 0.001
                if op == "<":  return val_f < tgt_f
                if op == "<=": return val_f <= tgt_f
                if op == ">":  return val_f > tgt_f
                if op == ">=": return val_f >= tgt_f
            except (ValueError, TypeError):
                pass

            if op == "==": return val_s == tgt_s
            if op == "!=": return val_s != tgt_s
            if op == "<":  return val_s < tgt_s
            if op == "<=": return val_s <= tgt_s
            if op == ">":  return val_s > tgt_s
            if op == ">=": return val_s >= tgt_s

        except Exception:
            pass
        return False

    def _dispatch_matched_actions(self, rule: Dict[str, Any], actions: List[Dict[str, Any]], trigger_value: Any):
        rule_name = rule.get("name", "Automation")
        rule_id = rule.get("id", "rule")
        log.info("[automations] firing '%s' (%d actions, val=%s)", rule_name, len(actions), trigger_value)

        # Parse lighting actions into provider map
        lighting_actions = {}
        has_inherit = False
        max_duration = 0.0

        for act in actions:
            dur = float(act.get("duration_s", 0) or 0)
            if dur > max_duration:
                max_duration = dur

            if act.get("type") == "openrgb":
                prof = act.get("profile", "")
                if prof == "inherit":
                    has_inherit = True
                elif prof:
                    lighting_actions["openrgb"] = prof
            elif act.get("type") in ("home_assistant", "ha"):
                script = act.get("entity", "") or act.get("script", "")
                if script == "inherit":
                    has_inherit = True
                elif script:
                    lighting_actions["ha"] = script.replace("ha.", "") if script.startswith("ha.") else script
            elif act.get("type") == "slot" and act.get("slot"):
                s = act.get("slot", {})
                if s.get("plugin") == "ha" or str(s.get("entity", "")).startswith("ha."):
                    script = s.get("button_id") or s.get("entity_id") or s.get("entity", "").replace("ha.", "")
                    if script:
                        lighting_actions["ha"] = script.replace("ha.", "") if script.startswith("ha.") else script
                elif s.get("plugin") == "openrgb" or str(s.get("entity", "")).startswith("openrgb."):
                    prof = s.get("openrgb_profile") or s.get("button_id")
                    if prof:
                        lighting_actions["openrgb"] = prof

        if has_inherit and not lighting_actions:
            # Explicit reversion
            with self._lock:
                self._active_alert_rules.discard(rule_id)
            try:
                from lighting_service import get_lighting_service
                get_lighting_service().pop_alert()
            except Exception as ex:
                log.warning("[automations] pop_alert failed: %s", ex)
        elif lighting_actions:
            try:
                from lighting_service import get_lighting_service
                ls = get_lighting_service()
                if ls.is_alert_active():
                    log.info("[automations] critical alert active -> ignoring automation lighting actions %s", lighting_actions)
                else:
                    with self._lock:
                        if max_duration == 0:
                            self._active_alert_rules.add(rule_id)
                        else:
                            self._active_alert_rules.discard(rule_id)
                    ls.push_alert(lighting_actions, max_duration)
            except Exception as ex:
                log.warning("[automations] failed to push lighting actions: %s", ex)

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

    def _act_slot(self, slot: Dict[str, Any]):
        def _exec():
            try:
                from panel_runtime import execute_slot
                execute_slot(slot)
            except Exception as ex:
                log.warning("[automations] slot action execution failed: %s", ex)
        threading.Thread(target=_exec, daemon=True, name="iris-auto-slot").start()

    def _act_openrgb(self, act: Dict[str, Any]):
        try:
            from lighting_service import get_lighting_service
            if get_lighting_service().is_alert_active():
                log.info("[automations] critical alert active -> skipping OpenRGB automation action")
                return
        except Exception:
            pass
        profile = act.get("profile", "")
        if not profile or profile == "inherit":
            return
        def _set_rgb():
            try:
                from lighting_service import get_lighting_service
                if get_lighting_service().is_alert_active():
                    return
                import plugin_manager
                inst = plugin_manager.get("openrgb")
                if inst and hasattr(inst, "apply_lighting_preset"):
                    inst.apply_lighting_preset(profile)
            except Exception as ex:
                log.warning("[automations] OpenRGB profile switch failed: %s", ex)
        threading.Thread(target=_set_rgb, daemon=True, name="iris-auto-openrgb").start()

    def _act_home_assistant(self, act: Dict[str, Any]):
        try:
            from lighting_service import get_lighting_service
            if get_lighting_service().is_alert_active():
                log.info("[automations] critical alert active -> skipping HA automation action")
                return
        except Exception:
            pass
        entity_id = act.get("entity", "") or act.get("script", "")
        if not entity_id or entity_id == "inherit":
            return
        def _call_ha():
            try:
                from lighting_service import get_lighting_service
                if get_lighting_service().is_alert_active():
                    return
                import plugin_manager
                inst = plugin_manager.get("ha")
                if inst and hasattr(inst, "apply_lighting_preset"):
                    inst.apply_lighting_preset(entity_id)
            except Exception as ex:
                log.warning("[automations] HA script execution failed: %s", ex)
        threading.Thread(target=_call_ha, daemon=True, name="iris-auto-ha").start()

    def _act_hotkey(self, act: Dict[str, Any], rule_name: str):
        hotkey = act.get("hotkey", "")
        if not hotkey:
            return
        def _send():
            try:
                from keyboard_service import keyboard_service
                keyboard_service.send_hotkey(hotkey)
                log.info("[automations] '%s' dispatched hotkey '%s'", rule_name, hotkey)
            except Exception as ex:
                log.warning("[automations] failed to send hotkey '%s': %s", hotkey, ex)
        threading.Thread(target=_send, daemon=True, name="iris-auto-hotkey").start()

    def _act_sound(self, act: Dict[str, Any]):
        sound_name = act.get("sound", "")
        if not sound_name:
            return
        def _play():
            try:
                import alarm_sound
                alarm_sound.play_alarm(sound_name)
            except Exception as ex:
                log.warning("[automations] failed to play sound '%s': %s", sound_name, ex)
        threading.Thread(target=_play, daemon=True, name="iris-auto-sound").start()

    def _act_notification(self, act: Dict[str, Any], trigger_val: Any):
        msg = act.get("message", "Automation Triggered")
        msg = msg.replace("{val}", str(trigger_val))
        def _notify():
            try:
                from serial_comm import serial_sender
                serial_sender.send_notification("Iris Alert", msg)
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True, name="iris-auto-notif").start()
