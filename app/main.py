"""Iris — PC companion overlay application."""

import logging
import os
import sys
import threading
import time as _time
import winsound
import ctypes
import ctypes.wintypes

import tkinter as tk

import pystray

import ws_bridge
import alarm_sound
from config import load_config, save_config
from constants import APP_NAME, DEFAULT_BRIGHTNESS, DEVICE_DEFAULTS, HOTKEY_SLEEP_MS, PC_DISP_STATS, TRAY_ICON_SIZE
from alarm_popup import AlarmPopup
from serial_comm import serial_sender
from providers.stats import StatsProvider
from providers.ha import HAProvider
from providers.media import MediaProvider
from providers.notification_mirror import NotificationMirrorProvider
from providers.openrgb import OpenRGBProvider
import plugin_manager
from plugin_manager import start_all as start_plugins, stop_all as stop_plugins, check_plugins
import panel_window
from main_window import MainWindow
from tray import make_icon_image, build_tray_menu
from overlay_window import OverlayWindow
from overlay_service import OverlayService
from stopwatch import StopwatchOverlay

if getattr(sys, "frozen", False):
    _LOG_DIR = os.path.join(os.environ["APPDATA"], "Iris")
    os.makedirs(_LOG_DIR, exist_ok=True)
else:
    _LOG_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE = os.path.join(_LOG_DIR, "iris.log")
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("iris")


class IrisApp:
    def __init__(self):
        self.cfg = load_config()
        self.icon = None
        self._online = False
        self._port = None
        self._running = True
        self._providers = []
        self._root = None
        self._main_win = None
        self._overlay = None
        self._overlays = None
        self._stopwatch = None
        self._alarm_active = False
        self._alarm_silenced = False

    def set_config(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)

    def _setup_providers(self, overlays=None):
        providers = [
            StatsProvider(self.cfg, serial_sender),
            HAProvider(self.cfg),
            MediaProvider(self.cfg, serial_sender),
            NotificationMirrorProvider(self.cfg, serial_sender),
            OpenRGBProvider(self.cfg),
        ]
        self._providers = providers
        self._stats_provider = providers[0]
        for p in self._providers:
            try:
                p.start()
            except Exception as e:
                log.warning(f"[provider] {p.__class__.__name__} failed: {e}")
        start_plugins(self.cfg, serial_sender, overlays)

    def _poll_serial(self):
        while self._running:
            port = serial_sender.connected_port()
            online = port is not None
            if online != self._online or port != self._port:
                self._online = online
                self._port = port
                self._update_icon()
            _time.sleep(3)

    def _plugin_check_loop(self):
        while self._running:
            _time.sleep(60)
            try:
                check_plugins()
            except Exception as e:
                log.warning("[plugin-check] failed: %s", e)

    def _update_icon(self):
        if self.icon:
            self.icon.icon = make_icon_image(TRAY_ICON_SIZE, online=self._online)

    def _set_brightness(self, value: int):
        prev = self.cfg.get("brightness", DEFAULT_BRIGHTNESS)
        self.set_config("brightness", value)
        if value == 0 and prev != 0:
            serial_sender.set_live("display_on", "0")
        elif value != 0:
            if prev == 0:
                serial_sender.set_live("display_on", "1")
            serial_sender.set_live("brightness", str(value))

    def _toggle_pc_stats(self, enabled: bool):
        self.set_config("pc_stats_manual", enabled)
        self._stats_provider.set_manual_override(enabled)
        serial_sender.set_live("pc_disp", PC_DISP_STATS if enabled else "0")
        log.info("PC stats pin %s", "ON" if enabled else "OFF")

    def _toggle_overlay(self, enabled: bool):
        if enabled:
            if self._overlay is None:
                self._overlay = OverlayWindow(
                    self._root, self._stats_provider,
                    on_close=self._on_overlay_close, style="numline",
                )
                log.info("Overlay ON")
        else:
            if self._overlay is not None:
                ov = self._overlay
                self._overlay = None
                ov.close()
                self._sync_overlay_tile(False)

    def _toggle_stopwatch(self):
        if self._stopwatch is None:
            self._stopwatch = StopwatchOverlay(self._root)
        self._stopwatch.toggle()

    def _toggle_countdown(self):
        if self._stopwatch is None:
            self._stopwatch = StopwatchOverlay(self._root)
        self._stopwatch.start_countdown()
        self._stopwatch.toggle()

    def _on_overlay_close(self):
        self._overlay = None
        self._sync_overlay_tile(False)

    def _sync_overlay_tile(self, on):
        if self._main_win:
            self._main_win.set_overlay_state(on)

    def sync_alarm_indicator(self):
        if not self._main_win:
            return
        alarms = self.cfg.get("alarms", [])
        active = any(a.get("enabled", False) for a in alarms)
        self._main_win.set_alarm_indicator(active)

    def _open_settings(self):
        panel_window.open_panel()

    def _quit(self):
        self._running = False
        for p in self._providers:
            try:
                p.stop()
            except Exception:
                log.exception("Provider %s failed during shutdown", p.__class__.__name__)
        stop_plugins()
        if self.icon:
            self.icon.stop()
            self.icon = None
        self._root.after(0, self._root.destroy)

    def _on_tray_click(self):
        user32 = ctypes.windll.user32
        self._main_win.set_saved_foreground(user32.GetForegroundWindow())
        self._root.after(0, self._toggle_window)

    def _toggle_window(self):
        self._main_win.toggle()

    def _setup_hotkey(self):
        self._hotkey_stop = threading.Event()
        self._hotkey_thread = None
        self._reregister_hotkey()

    def _reregister_hotkey(self):
        if self._hotkey_stop.is_set():
            self._hotkey_stop.clear()
        else:
            self._hotkey_stop.set()
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_thread.join(timeout=0.5)

        self._hotkey_stop.clear()
        user32 = ctypes.windll.user32
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_WIN = 0x0008
        WM_HOTKEY = 0x0312
        HOTKEY_ID = 1
        MODS_MAP = {
            16: MOD_SHIFT,
            17: MOD_CONTROL,
            18: MOD_ALT,
            91: MOD_WIN,
            92: MOD_WIN,
        }

        modifiers = self.cfg.get("hotkey_modifiers", [17, 18])
        key_vk = self.cfg.get("hotkey_key", 73)

        mod_flags = 0
        for vk in modifiers:
            mod_flags |= MODS_MAP.get(vk, 0)

        def listener():
            msg = ctypes.wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
            if not user32.RegisterHotKey(None, HOTKEY_ID, mod_flags, key_vk):
                log.warning("Failed to register global hotkey (mods=%s key=%s)", modifiers, key_vk)
                return
            try:
                while not self._hotkey_stop.is_set():
                    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                            fg = user32.GetForegroundWindow()
                            self._main_win.set_saved_foreground(fg)
                            self._root.after(0, self._toggle_window)
                        elif msg.message == 0x0012:
                            break
                    else:
                        ctypes.windll.kernel32.Sleep(HOTKEY_SLEEP_MS)
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)

        self._hotkey_thread = threading.Thread(target=listener, daemon=True)
        self._hotkey_thread.start()
        log.info("Global hotkey registered")

    def _queue_defaults(self):
        for key, val in DEVICE_DEFAULTS.items():
            serial_sender.queue_on_connect_default(key, val)

    def _get_next_alarm_message(self):
        alarms = [a for a in self.cfg.get("alarms", [])
                  if a.get("enabled", False) and a.get("days", 0)]
        if not alarms:
            return ""
        import datetime as _dt
        now = _dt.datetime.now()
        best_msg = ""
        best_secs = float("inf")
        for a in alarms:
            mask = a.get("days", 0)
            h, m = a["hour"], a["minute"]
            for offset in range(8):
                d = now + _dt.timedelta(days=offset)
                day_bit = (d.weekday() + 1) % 7
                if not (mask >> day_bit) & 1:
                    continue
                t = d.replace(hour=h, minute=m, second=0, microsecond=0)
                if t > now:
                    secs = (t - now).total_seconds()
                    if secs < best_secs:
                        best_secs = secs
                        best_msg = (a.get("message") or "").strip()
                    break
        return best_msg

    def _alarm_dismiss(self):
        serial_sender.set_live("alarm_dismiss", "1")
        self._alarm_active = False
        self._alarm_silenced = True
        alarm_sound.stop()
        self._root.after(0, self._alarm_popup.hide)
        log.info("[alarm] dismissed from panel")

    def _alarm_snooze(self):
        serial_sender.set_live("alarm_snooze", "1")
        self._alarm_active = False
        self._alarm_silenced = True
        alarm_sound.stop()
        self._root.after(0, self._alarm_popup.hide)
        log.info("[alarm] snoozed from panel")

    def _get_active_alarm(self):
        """Find which alarm is currently matching (by time)."""
        import datetime as _dt
        now = _dt.datetime.now()
        for a in self.cfg.get("alarms", []):
            if not a.get("enabled", False):
                continue
            mask = a.get("days", 0)
            if not mask:
                continue
            if a["hour"] == now.hour and a["minute"] == now.minute:
                return a
        return None

    def _on_serial_line(self, line):
        if line.startswith("ALARM:"):
            state = line[6:].strip().lower()
            active = state == "active"
            if active and self._alarm_silenced:
                return
            if not active:
                self._alarm_silenced = False
            if active != self._alarm_active:
                self._alarm_active = active
                if active:
                    a = self._get_active_alarm()
                    sound = (a or {}).get("sound", "remind")
                    alarm_sound.play(sound)
                    log.info("[alarm] ALARM:active — playing %s", sound)
                    msg = self._get_next_alarm_message()
                    self._root.after(0, lambda m=msg: self._alarm_popup.show(m))
                else:
                    alarm_sound.stop()
                    log.info("[alarm] alarm cleared")
                    self._root.after(0, self._alarm_popup.hide)
        elif line.startswith("OVERHEAT:active"):
            alarm_sound.play("annoy")
            log.info("[overheat] OVERHEAT:active — playing annoy")
        elif line.startswith("SAFETY:led_overload"):
            log.warning("[safety] SAFETY:led_overload — display shut down by firmware")
        elif line.startswith("TIMEOUT:display_off"):
            log.info("[safety] display timed out — no serial heartbeat")
        elif line.startswith("SAFETY:rebooting"):
            log.warning("[safety] SAFETY:rebooting — repeated corruption, ESP restarting")

    def run(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._overlays = OverlayService(self._root)

        serial_sender.set_port(self.cfg.get("serial_port", "auto"))
        serial_sender.add_line_callback(self._on_serial_line)
        saved_name = self.cfg.get("user_name", "").strip()
        if saved_name:
            serial_sender.queue_on_connect("user_name", saved_name)
        self._setup_providers(self._overlays)
        self._queue_defaults()
        ws_bridge.register_app(self)
        threading.Thread(target=ws_bridge.start, daemon=True, name="ws-bridge").start()

        self._main_win = MainWindow(self._root, self, cfg=self.cfg)

        self._alarm_popup = AlarmPopup(
            self._root, self._alarm_dismiss, self._alarm_snooze)
        self.sync_alarm_indicator()

        self._setup_hotkey()

        self.icon = pystray.Icon(
            "Iris",
            make_icon_image(TRAY_ICON_SIZE, online=False),
            APP_NAME,
            menu=build_tray_menu(self),
        )
        self.icon.run_detached()

        threading.Thread(target=self._poll_serial, daemon=True, name="serial-poll").start()
        threading.Thread(target=self._plugin_check_loop, daemon=True, name="plugin-check").start()
        self._root.mainloop()


if __name__ == "__main__":
    IrisApp().run()
