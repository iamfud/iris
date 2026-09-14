"""Iris 3.0 — Robust Lighting Service.

Architecture (focus-decoupled):
- No foreground-exe auto-switching. Lighting never follows window focus.
- OpenRGB (PC LEDs) applies a SINGLE startup baseline once and is otherwise
  left alone. The baseline is one of:
      "theme"   -> solid colour = highest-luminance of the active theme's
                   neon (cyan) vs accent (purple), per get_current_theme_colors.
      "profile" -> load a named OpenRGB profile (startup_profile).
      "off"     -> do nothing.
  The baseline is (re)applied when Iris starts and when the user explicitly
  applies the theme in Settings (update_config). It is NOT re-evaluated on
  focus changes.
- Per-app plugin theming (general mechanism): each entry in
  ambient_lighting.per_app = [{"exe", "profile", "plugin"}] applies that
  profile while the target exe's process is running (resident, NOT focused)
  and reverts to the startup baseline when that app exits.
- Home Assistant smart-room lights keep a global day/night schedule taken
  from the default ("__default__") profile's lighting.ha day/night presets,
  completely decoupled from focus/app activity.
- Alert layer (automations) always passes through on top.

Plugins declare `"lighting_provider": true` and implement
get_lighting_presets()/apply_lighting_preset() (see plugin docs).
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("iris.lighting")

_SERVICE: Optional["LightingService"] = None
_LOCK = threading.Lock()


def get_lighting_service() -> "LightingService":
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = LightingService()
        return _SERVICE


class LightingService:
    def __init__(self):
        self._cfg: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._running = False
        self._watcher_thread: Optional[threading.Thread] = None

        # Startup baseline
        self._startup_pending: bool = True

        # Per-app watcher state
        self._active_app: Optional[tuple] = None   # (exe, plugin, profile)

        # Alert pulse stack (always on top)
        self._active_alert: Optional[Dict[str, Any]] = None
        self._alert_critical: bool = False
        self._alert_timer: Optional[threading.Timer] = None

    # ── Lifecycle ───────────────────────────────────────────────

    def initialize(self, cfg: Dict[str, Any]):
        with self._lock:
            self._cfg = cfg
        self._startup_pending = True
        if not self._running:
            self._running = True
            self._watcher_thread = threading.Thread(
                target=self._per_app_watcher_loop, daemon=True,
                name="iris-lighting-per-app")
            self._watcher_thread.start()
        # Attempt the startup baseline now; if OpenRGB is not yet connected it
        # will be applied by the watcher once the SDK becomes available.
        self.evaluate_state(force=True)

    def update_config(self, cfg: Dict[str, Any]):
        with self._lock:
            self._cfg = cfg
        # If OpenRGB is connected, apply baseline immediately and mark startup complete;
        # otherwise preserve _startup_pending so the watcher loop applies it once connected.
        if self._openrgb_connected():
            self._startup_pending = False
            self.evaluate_state(force=True)
        else:
            self._startup_pending = True

    def stop(self):
        self._running = False
        if self._alert_timer:
            self._alert_timer.cancel()
            self._alert_timer = None

    # ── Helpers ─────────────────────────────────────────────────

    def is_daytime(self) -> bool:
        now = datetime.datetime.now().time()
        return datetime.time(7, 30) <= now <= datetime.time(19, 30)

    def _ambient(self) -> Dict[str, Any]:
        return self._cfg.get("ambient_lighting") or {}

    def _openrgb_baseline(self) -> Dict[str, Any]:
        """Return the RGB startup baseline action or None for 'off'."""
        amb = self._ambient()
        if amb.get("enabled", True) is False:
            return None
        mode = amb.get("startup_mode")
        if not mode and amb.get("sync_theme") is not False:
            mode = "theme"
        target_plugin = "rgb"
        try:
            import plugin_manager
            if not plugin_manager.get("rgb") and plugin_manager.get("openrgb"):
                target_plugin = "openrgb"
        except Exception:
            pass
        if mode == "profile":
            prof = amb.get("startup_profile") or ""
            return {target_plugin: prof} if prof else None
        if mode == "off":
            return None
        # theme (default)
        return {target_plugin: "__theme__"}

    def _ha_daylight(self) -> Dict[str, Any]:
        """Return the HA day/night action based on the global (default profile) schedule."""
        with self._lock:
            cfg = self._cfg or {}
        amb = self._ambient()
        if amb.get("enabled", True) is False:
            return {}
        profiles = cfg.get("panel_profiles") or []
        default_lighting = {}
        for p in profiles:
            if p.get("id") == "__default__":
                default_lighting = p.get("lighting") or {}
                break
        ha_cfg = default_lighting.get("ha") or {}
        follow_day = ha_cfg.get("follow_daylight", amb.get("follow_daylight", False))
        if not follow_day:
            return {}
        is_day = self.is_daytime()
        preset = ha_cfg.get("day_preset" if is_day else "night_preset") or ""
        if preset:
            return {"ha": preset}
        return {}

    def get_providers(self) -> List[Dict[str, Any]]:
        """Query plugin_manager for all active plugins declaring lighting_provider capability."""
        providers = []
        try:
            import plugin_manager
            discovered = plugin_manager.discover_plugins() or []
            for name, m in discovered:
                caps = m.get("capabilities", {})
                if caps.get("lighting_provider"):
                    inst = plugin_manager.get(name)
                    connected = False
                    presets = []
                    supports_day_off = bool(m.get("supports_day_off", False))
                    if inst:
                        if hasattr(inst, "is_connected"):
                            connected = bool(inst.is_connected())
                        elif hasattr(inst, "_connector") and hasattr(inst._connector, "available"):
                            connected = bool(inst._connector.available)
                        else:
                            connected = True
                        if hasattr(inst, "get_lighting_presets"):
                            presets = inst.get_lighting_presets() or []
                    providers.append({
                        "id": name,
                        "name": m.get("display_name", name),
                        "connected": connected,
                        "supports_day_off": supports_day_off,
                        "presets": presets,
                    })
        except Exception as ex:
            log.warning("[lighting] failed to query providers: %s", ex)
        return providers

    # ── Alert Stack (highest priority) ──────────────────────────

    def push_alert(self, actions: Dict[str, str], duration_s: float, is_critical: bool = False):
        """Push a lighting alert onto the single always-on-top alert slot.

        Critical (red) alerts take precedence: a non-critical alert is ignored
        while a critical alert is already active, so ordinary automations can
        never knock out a live red alert. A critical alert replaces any prior
        alert; a non-critical alert only replaces a non-critical one.
        """
        with self._lock:
            if self._active_alert is not None and self._alert_critical and not is_critical:
                log.info("[lighting] red alert active -> ignoring non-critical alert %s", actions)
                return
            self._alert_critical = is_critical
            if self._alert_timer:
                self._alert_timer.cancel()
                self._alert_timer = None
            self._active_alert = actions
            if duration_s > 0:
                self._alert_timer = threading.Timer(duration_s, self.pop_alert)
                self._alert_timer.daemon = True
                self._alert_timer.start()
        log.info("[lighting] alert pushed (duration=%.1fs, critical=%s, actions=%s)", duration_s, is_critical, actions)
        self.evaluate_state(force=True)

    def pop_alert(self, force: bool = False):
        with self._lock:
            had_alert = self._active_alert is not None
            if had_alert and self._alert_critical and not force:
                return
            self._active_alert = None
            self._alert_critical = False
            if self._alert_timer:
                self._alert_timer.cancel()
                self._alert_timer = None
        if had_alert:
            log.info("[lighting] alert expired -> reverting to baseline")
            self.evaluate_state(force=True)

    def is_alert_active(self) -> bool:
        """Return True if a critical alert (e.g. Shields down / red alert) is active."""
        with self._lock:
            return bool(self._active_alert is not None and self._alert_critical)

    # ── State Evaluation & Dispatch ─────────────────────────────

    def evaluate_state(self, force: bool = False):
        """Compute the single set of actions to dispatch and apply them."""
        with self._lock:
            active_alert = self._active_alert

        # 1. Alert always passes through
        if active_alert:
            self._dispatch_actions(active_alert, is_alert=True)
            return

        # 2. OpenRGB baseline (startup) unless a per-app override is active
        with self._lock:
            active_app = self._active_app

        if active_app:
            openrgb_actions = {active_app[1]: active_app[2]}
        else:
            baseline = self._openrgb_baseline() or {}
            openrgb_actions = dict(baseline)

        # 3. HA day/night (global schedule, focus-decoupled)
        ha_actions = self._ha_daylight()

        actions = {}
        actions.update(openrgb_actions)
        actions.update(ha_actions)
        self._dispatch_actions(actions, is_alert=False)

    def _dispatch_actions(self, actions: Dict[str, str], is_alert: bool = False):
        if not actions:
            return
        try:
            import plugin_manager
            import inspect
            for pid, preset_id in actions.items():
                if not preset_id:
                    continue
                inst = plugin_manager.get(pid)
                if inst is None and pid == "openrgb":
                    inst = plugin_manager.get("rgb")
                elif inst is None and pid == "rgb":
                    inst = plugin_manager.get("openrgb")
                if inst and hasattr(inst, "apply_lighting_preset"):
                    try:
                        sig = inspect.signature(inst.apply_lighting_preset)
                        if "is_alert" in sig.parameters:
                            inst.apply_lighting_preset(preset_id, is_alert=is_alert)
                        else:
                            inst.apply_lighting_preset(preset_id)
                    except Exception as ex:
                        log.warning("[lighting] %s apply_lighting_preset(%s) failed: %s", pid, preset_id, ex)
        except Exception as ex:
            log.warning("[lighting] dispatch error: %s", ex)

    # ── Per-App Watcher (process activity, NOT focus) ───────────

    def _per_app_entries(self) -> List[Dict[str, Any]]:
        return self._ambient().get("per_app") or []

    def _exe_running(self, exe: str) -> bool:
        exe_l = (exe or "").strip().lower()
        if not exe_l:
            return False
        if exe_l.endswith(".exe"):
            name = exe_l[:-4]
        else:
            name = exe_l
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                try:
                    pn = (p.info.get("name") or "").lower()
                except Exception:
                    continue
                if pn in (name, name + ".exe", exe_l):
                    return True
        except Exception:
            return False
        return False

    def _openrgb_connected(self) -> bool:
        try:
            import plugin_manager
            inst = plugin_manager.get("rgb") or plugin_manager.get("openrgb")
            if inst is None:
                providers = plugin_manager.get_by_capability("lighting_provider")
                inst = providers[0] if providers else None
            if inst is None:
                return False
            if hasattr(inst, "is_connected"):
                return bool(inst.is_connected())
            return True
        except Exception:
            return False

    def _per_app_watcher_loop(self):
        while self._running:
            try:
                # Apply the startup baseline once the OpenRGB SDK is connected
                # (the plugin is not up when LightingService.initialize runs).
                if self._startup_pending:
                    if self._openrgb_connected():
                        with self._lock:
                            self._startup_pending = False
                        log.info("[lighting] startup baseline applied")
                        self.evaluate_state(force=True)
                    else:
                        time.sleep(1.0)
                        continue

                current = None
                for entry in self._per_app_entries():
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("enabled", True) is False:
                        continue
                    if self._exe_running(entry.get("exe") or ""):
                        plugin = entry.get("plugin") or "openrgb"
                        profile = entry.get("profile") or ""
                        if profile:
                            current = (entry.get("exe") or "", plugin, profile)
                            break

                changed = False
                with self._lock:
                    if current != self._active_app:
                        self._active_app = current
                        changed = True
                if changed:
                    log.info("[lighting] per-app lighting -> %s", current or "baseline")
                    self.evaluate_state(force=True)
            except Exception as ex:
                log.debug("[lighting] per-app watcher error: %s", ex)
            time.sleep(1.0)
