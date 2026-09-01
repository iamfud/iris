"""Iris 3.0 — Generic Lighting Service & Profile Focus Manager.

Architecture:
- Zero plugin-specific hardcoding in core.
- Plugins declare `"lighting_provider": true` and provide:
    `get_lighting_presets() -> List[{"id": str, "name": str}]`
    `apply_lighting_preset(preset_id: str)`
- Manages:
    1. Base Default Profile lighting (day / night / baseline).
    2. Active Profile override (switched via focus watcher with anti-spam cooldown).
    3. Alert layer duration pulses (automations).
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
        
        # Focus watcher
        self._watcher_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_hwnd: Optional[int] = None
        self._last_exe: str = ""
        self._active_profile_id: str = "__default__"
        self._last_switch_ts: float = 0.0
        self._debounce_timer: Optional[threading.Timer] = None
        self._cooldown_s: float = 1.5

        # Alert pulse stack (Layer 3)
        self._active_alert: Optional[Dict[str, Any]] = None
        self._alert_timer: Optional[threading.Timer] = None

    def initialize(self, cfg: Dict[str, Any]):
        with self._lock:
            self._cfg = cfg
        if not self._running:
            self._running = True
            self._watcher_thread = threading.Thread(target=self._focus_watcher_loop, daemon=True, name="iris-lighting-focus")
            self._watcher_thread.start()
        self.evaluate_state()

    def update_config(self, cfg: Dict[str, Any]):
        with self._lock:
            self._cfg = cfg
        self.evaluate_state()

    def is_daytime(self) -> bool:
        """Evaluate if local time is between 07:30 and 19:30."""
        now = datetime.datetime.now().time()
        return datetime.time(7, 30) <= now <= datetime.time(19, 30)

    # ── Generic Plugin Discovery ─────────────────────────────────

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

    # ── Alert Stack (Layer 3) ────────────────────────────────────

    def push_alert(self, actions: Dict[str, str], duration_s: float):
        """Temporary high-priority alert override (e.g. {'openrgb': 'Red Alert', 'ha': 'script.gaming_red'})."""
        with self._lock:
            if self._alert_timer:
                self._alert_timer.cancel()
                self._alert_timer = None
            self._active_alert = actions
            if duration_s > 0:
                self._alert_timer = threading.Timer(duration_s, self.pop_alert)
                self._alert_timer.daemon = True
                self._alert_timer.start()
        log.info("[lighting] alert pushed (duration=%.1fs, actions=%s)", duration_s, actions)
        self.evaluate_state()

    def pop_alert(self):
        with self._lock:
            self._active_alert = None
            if self._alert_timer:
                self._alert_timer.cancel()
                self._alert_timer = None
        log.info("[lighting] alert expired -> reverting to active profile baseline")
        self.evaluate_state()

    # ── State Evaluation & Dispatch ──────────────────────────────

    def evaluate_state(self):
        with self._lock:
            active_alert = self._active_alert
            profile_id = self._active_profile_id
            cfg = self._cfg or {}
            is_day = self.is_daytime()

        # 1. LAYER 3: Alert Active (always passes through alerts)
        if active_alert:
            self._dispatch_actions(active_alert)
            return

        # Check global ambient lighting enabled master state
        ambient_cfg = cfg.get("ambient_lighting") or {}
        if ambient_cfg.get("enabled", True) is False:
            return

        # 2. Find Profile Settings (Layer 2) or Fallback to Default (Layer 1)
        profiles = cfg.get("panel_profiles", [])
        active_prof = None
        default_prof = None

        for p in profiles:
            if p.get("id") == "__default__":
                default_prof = p
            if p.get("id") == profile_id:
                active_prof = p

        target_prof = active_prof or default_prof or {}
        lighting_cfg = target_prof.get("lighting", {})
        default_lighting = (default_prof.get("lighting", {}) if default_prof else {})

        # Compute per-plugin actions
        actions = {}
        global_follow_day = ambient_cfg.get("follow_daylight", None)

        for prov in self.get_providers():
            pid = prov["id"]
            p_conf = lighting_cfg.get(pid) or {}
            if not p_conf or p_conf.get("preset") == "inherit":
                p_conf = default_lighting.get(pid) or {}

            preset = p_conf.get("preset", "")
            # Handle day/night split if configured
            follow_day = p_conf.get("follow_daylight", False)
            if global_follow_day is False:
                follow_day = False
            elif global_follow_day is True and ("day_preset" in p_conf or "night_preset" in p_conf):
                follow_day = True

            if follow_day:
                if is_day:
                    preset = p_conf.get("day_preset", preset)
                else:
                    preset = p_conf.get("night_preset", preset)

            if preset:
                actions[pid] = preset

        self._dispatch_actions(actions)

    def _dispatch_actions(self, actions: Dict[str, str]):
        if not actions:
            return
        try:
            import plugin_manager
            for pid, preset_id in actions.items():
                if not preset_id:
                    continue
                inst = plugin_manager.get(pid)
                if inst and hasattr(inst, "apply_lighting_preset"):
                    try:
                        inst.apply_lighting_preset(preset_id)
                    except Exception as ex:
                        log.warning("[lighting] %s apply_lighting_preset(%s) failed: %s", pid, preset_id, ex)
        except Exception as ex:
            log.warning("[lighting] dispatch error: %s", ex)

    # ── Focus Watcher Loop ───────────────────────────────────────

    def _focus_watcher_loop(self):
        import ctypes
        user32 = ctypes.windll.user32
        import psutil

        while self._running:
            try:
                hwnd = user32.GetForegroundWindow()
                if hwnd and hwnd != self._last_hwnd:
                    self._last_hwnd = hwnd
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value:
                        try:
                            proc = psutil.Process(pid.value)
                            exe = proc.name().lower()
                            if exe != self._last_exe:
                                self._last_exe = exe
                                self._on_foreground_exe_changed(exe)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            except Exception as ex:
                log.debug("[lighting] focus query error: %s", ex)
            time.sleep(0.5)

    def _on_foreground_exe_changed(self, exe: str):
        # Coalesce rapid window switching with debounce timer
        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        def _apply_switch():
            with self._lock:
                cfg = self._cfg or {}
                profiles = cfg.get("panel_profiles", [])
                target_id = "__default__"
                exe_norm = exe.strip().lower().replace(".exe", "")
                for p in profiles:
                    p_exe = (p.get("exe") or "").strip().lower().replace(".exe", "")
                    if p_exe and p_exe == exe_norm and p.get("enabled", True):
                        target_id = p.get("id")
                        break

                if target_id != self._active_profile_id:
                    log.info("[lighting] focus switch -> profile: %s (exe: %s)", target_id, exe)
                    self._active_profile_id = target_id
                    self._last_switch_ts = time.time()
            self.evaluate_state()

        # Run after a 400ms debounce
        self._debounce_timer = threading.Timer(0.4, _apply_switch)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()
