"""Iris — PC companion overlay application."""

import logging
import os
import sys
import threading
import time as _time
import winsound
import ctypes
import ctypes.wintypes
import ctypes

import pystray

import ws_bridge
from config import load_config, save_config
from constants import APP_NAME, DEVICE_DEFAULTS
from alarm_popup import AlarmPopup
from serial_comm import serial_sender
from providers.stats import StatsProvider
from providers.ha import HAProvider
from providers.media import MediaProvider
from providers.notification_mirror import NotificationMirrorProvider
from providers.openrgb import OpenRGBProvider
from settings_dialog import SettingsDialog
from tray import make_icon_image, build_tray_menu
from main_window import MainWindow
from overlay_window import OverlayWindow

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "iris.log")
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("iris")


class DerekD1:
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
        self._alarm_active = False

    def _setup_providers(self):
        self._media_provider = MediaProvider(self.cfg, serial_sender)
        providers = [
            StatsProvider(self.cfg, serial_sender),
            HAProvider(self.cfg),
            self._media_provider,
            NotificationMirrorProvider(self.cfg, serial_sender),
            OpenRGBProvider(self.cfg),
        ]
        self._providers = providers
        for p in self._providers:
            try:
                p.start()
            except Exception as e:
                log.warning(f"[provider] {p.__class__.__name__} failed: {e}")

    def _poll_serial(self):
        while self._running:
            port = serial_sender.connected_port()
            online = port is not None
            if online != self._online or port != self._port:
                self._online = online
                self._port = port
                self._update_icon()
            _time.sleep(3)

    def _update_icon(self):
        if self.icon:
            self.icon.icon = make_icon_image(64, online=self._online)

    def _set_brightness(self, value: int):
        prev = self.cfg.get("brightness", 3)
        self.cfg["brightness"] = value
        if value == 0 and prev != 0:
            serial_sender.set_live("display_on", "0")
        elif value != 0:
            if prev == 0:
                serial_sender.set_live("display_on", "1")
            serial_sender.set_live("brightness", str(value))

    def _toggle_pc_stats(self, enabled: bool):
        self.cfg["pc_stats_manual"] = enabled
        save_config(self.cfg)
        for p in self._providers:
            if hasattr(p, "set_manual_override"):
                p.set_manual_override(enabled)
                break
        serial_sender.set_live("pc_disp", "7" if enabled else "0")
        log.info("PC stats manual override %s", "ON" if enabled else "OFF")

    def _toggle_overlay(self, enabled: bool):
        if enabled:
            if self._overlay is None:
                provider = next((p for p in self._providers if hasattr(p, "snapshot")), None)
                if provider:
                    self._overlay = OverlayWindow(
                        self._root, provider, on_close=self._on_overlay_close,
                    )
                    log.info("Overlay ON")
        else:
            if self._overlay is not None:
                ov = self._overlay
                self._overlay = None
                ov.close()
                self._sync_overlay_tile(False)

    def _on_overlay_close(self):
        self._overlay = None
        self._sync_overlay_tile(False)

    def _sync_overlay_tile(self, on):
        if self._main_win:
            self._main_win._overlay_on = on
            ov = self._main_win._ov_tiles
            self._main_win._btn_overlay.config(image=ov[2] if on else ov[0])

    def sync_alarm_indicator(self):
        if not hasattr(self, '_main_win') or not self._main_win:
            return
        alarms = self.cfg.get("alarms", [])
        active = any(a.get("enabled", False) and a.get("days", 0) for a in alarms)
        self._main_win.set_alarm_indicator(active)

    def _open_settings(self, tab=0):
        self._root.after(0, lambda: self._run_settings(tab=tab))

    def _run_settings(self, tab=0):
        dlg = SettingsDialog(self._root, serial_sender, self.cfg, initial_tab=tab)
        self._root.wait_window(dlg._win)
        self.sync_alarm_indicator()
        if self._main_win:
            self._main_win._render_buttons()

    def _quit(self):
        self._running = False
        for p in self._providers:
            try:
                p.stop()
            except Exception:
                pass
        if self.icon:
            self.icon.stop()
        self._root.after(0, self._root.destroy)

    def _on_tray_click(self):
        user32 = ctypes.windll.user32
        self._main_win._saved_foreground_hwnd = user32.GetForegroundWindow()
        self._root.after(0, self._toggle_window)

    def _toggle_window(self):
        self._main_win.toggle()

    def _setup_hotkey(self):
        import ctypes
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        WM_HOTKEY = 0x0312
        HOTKEY_ID = 1
        user32 = ctypes.windll.user32

        def listener():
            msg = ctypes.wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
            if not user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, ord("I")
            ):
                log.warning("Failed to register global hotkey")
                return
            try:
                while True:
                    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                            fg = user32.GetForegroundWindow()
                            self._main_win._saved_foreground_hwnd = fg
                            self._root.after(0, self._toggle_window)
                        elif msg.message == 0x0012:
                            break
                    else:
                        ctypes.windll.kernel32.Sleep(50)
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)

        threading.Thread(target=listener, daemon=True).start()

    def _queue_defaults(self):
        q = serial_sender.queue_on_connect
        for key, val in DEVICE_DEFAULTS.items():
            q(key, val)

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
        self._root.after(0, self._alarm_popup.hide)
        log.info("[alarm] dismissed from panel")

    def _alarm_snooze(self):
        serial_sender.set_live("alarm_snooze", "1")
        self._alarm_active = False
        self._root.after(0, self._alarm_popup.hide)
        log.info("[alarm] snoozed from panel")

    def _on_serial_line(self, line):
        if line.startswith("ALARM:"):
            state = line[6:].strip().lower()
            active = state == "active"
            if active != self._alarm_active:
                self._alarm_active = active
                if active:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    log.info("[alarm] ALARM:active — PC beep")
                    msg = self._get_next_alarm_message()
                    self._root.after(0, lambda m=msg: self._alarm_popup.show(m))
                else:
                    log.info("[alarm] alarm cleared")
                    self._root.after(0, self._alarm_popup.hide)
        elif line.startswith("OVERHEAT:active"):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            log.info("[overheat] OVERHEAT:active — PC beep")

    def run(self):
        serial_sender.set_port(self.cfg.get("serial_port", "auto"))
        serial_sender.add_line_callback(self._on_serial_line)
        self._queue_defaults()
        threading.Thread(target=ws_bridge.start, daemon=True, name="ws-bridge").start()
        self._setup_providers()

        self._root = __import__("tkinter").Tk()
        self._root.withdraw()

        self._main_win = MainWindow(self._root, self)
        self._alarm_popup = AlarmPopup(
            self._root, self._alarm_dismiss, self._alarm_snooze)
        self.sync_alarm_indicator()

        self._setup_hotkey()

        self.icon = pystray.Icon(
            "Iris",
            make_icon_image(64, online=False),
            APP_NAME,
            menu=build_tray_menu(self),
        )
        self.icon.run_detached()

        threading.Thread(target=self._poll_serial, daemon=True, name="serial-poll").start()
        self._root.mainloop()


if __name__ == "__main__":
    DerekD1().run()
