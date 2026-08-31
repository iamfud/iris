"""Iris — PC companion overlay application."""

import logging
import os
import sys
import multiprocessing
from logging.handlers import RotatingFileHandler
import paths

_LOG_DIR = paths.get_log_dir()
_LOG_FILE = paths.get_log_file()

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if not any(isinstance(h, RotatingFileHandler) for h in _root_logger.handlers):
    _log_handler = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _log_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  [%(name)s]  %(message)s", datefmt="%H:%M:%S"))
    _root_logger.addHandler(_log_handler)


if __name__ == "__main__":
    multiprocessing.freeze_support()

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
    from tray import make_icon_image, build_tray_menu

    log = logging.getLogger("iris")


    class IrisApp:
        def __init__(self):
            self.cfg = load_config()
            try:
                import automations
                automations.get_engine().load_config(self.cfg)
            except Exception as ex:
                log.warning("[automations] init error: %s", ex)
            try:
                from lighting_service import get_lighting_service
                get_lighting_service().initialize(self.cfg)
            except Exception as ex:
                log.warning("[lighting] init error: %s", ex)
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
                    mw = self._main_win
                    if mw is not None and hasattr(mw, "_reflow_panel"):
                        try:
                            self._root.after(0, mw._reflow_panel)
                        except Exception:
                            pass
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

        def _toggle_overlay(self, enabled: bool = None):
            if enabled is None:
                enabled = (self._overlay is None)
            if enabled:
                if self._overlay is None:
                    from overlay_window import OverlayWindow
                    self._overlay = OverlayWindow(
                        self._root, self._stats_provider,
                        on_close=self._on_overlay_close, style="numline",
                    )
                    log.info("Overlay ON")
                    self._sync_overlay_tile(True)
            else:
                if self._overlay is not None:
                    ov = self._overlay
                    self._overlay = None
                    ov.close()
                    self._sync_overlay_tile(False)

        def _toggle_stopwatch(self):
            if self._stopwatch is None:
                from stopwatch import StopwatchOverlay
                self._stopwatch = StopwatchOverlay(self._root)
            self._stopwatch.toggle()

        def _toggle_countdown(self):
            if self._stopwatch is None:
                from stopwatch import StopwatchOverlay
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

        def _open_capture_toolbar(self):
            mw = self._ensure_main_win()
            if mw:
                self._root.after(0, lambda: mw.start_screenshot(direct=False))

        def _toggle_capture_toolbar(self):
            mw = self._ensure_main_win()
            if mw:
                if mw._capture_toolbar is None:
                    from capture_toolbar import CaptureToolbar
                    mw._capture_toolbar = CaptureToolbar(self._root, self)
                self._root.after(0, mw._capture_toolbar.toggle)

        def _quit(self):
            self._running = False
            for p in self._providers:
                try:
                    p.stop()
                except Exception:
                    log.exception("Provider %s failed during shutdown", p.__class__.__name__)
            stop_plugins()
            try:
                import desktop_panel
                desktop_panel.close_desktop_panel()
            except Exception:
                pass
            if self.icon:
                self.icon.stop()
                self.icon = None
            self._root.after(0, self._root.destroy)

        def _ensure_main_win(self):
            if self._main_win is None:
                from main_window import MainWindow
                self._main_win = MainWindow(self._root, self, cfg=self.cfg)
                self.sync_alarm_indicator()
            return self._main_win

        def _on_tray_click(self):
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            self._root.after(0, lambda: self._toggle_window(fg))

        def _toggle_window(self, fg=None):
            mw = self._ensure_main_win()
            if fg is not None:
                mw.set_saved_foreground(fg)
            mw.toggle()

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
            HOTKEY_ID_DESKTOP = 2

            def _parse_hk(val, def_mods, def_vk):
                if not val or not isinstance(val, str):
                    return def_mods, def_vk
                parts = [p.strip().lower() for p in val.split("+") if p.strip()]
                mod_flags = 0
                vk = 0
                for p in parts:
                    if p in ("ctrl", "control"):
                        mod_flags |= MOD_CONTROL
                    elif p in ("alt", "menu"):
                        mod_flags |= MOD_ALT
                    elif p in ("shift",):
                        mod_flags |= MOD_SHIFT
                    elif p in ("win", "cmd", "meta"):
                        mod_flags |= MOD_WIN
                    elif len(p) == 1:
                        vk = ord(p.upper())
                    elif p.startswith("f") and p[1:].isdigit():
                        fnum = int(p[1:])
                        if 1 <= fnum <= 24:
                            vk = 0x70 + (fnum - 1)
                    elif p == "space":
                        vk = 0x20
                    elif p in ("enter", "return"):
                        vk = 0x0D
                    elif p == "tab":
                        vk = 0x09
                    elif p in ("esc", "escape"):
                        vk = 0x1B
                return (mod_flags if mod_flags else def_mods), (vk if vk else def_vk)

            ov_hk_str = self.cfg.get("hotkey_overlay") or "Ctrl+Alt+I"
            tb_hk_str = self.cfg.get("hotkey_toolbar") or "Ctrl+Alt+T"

            ov_mods, ov_vk = _parse_hk(ov_hk_str, MOD_CONTROL | MOD_ALT, ord('I'))
            tb_mods, tb_vk = _parse_hk(tb_hk_str, MOD_CONTROL | MOD_ALT, ord('T'))

            def listener():
                msg = ctypes.wintypes.MSG()
                user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
                reg1 = user32.RegisterHotKey(None, HOTKEY_ID, ov_mods, ov_vk)
                reg2 = user32.RegisterHotKey(None, HOTKEY_ID_DESKTOP, tb_mods, tb_vk)
                if not reg1:
                    log.warning("Failed to register overlay global hotkey: %s", ov_hk_str)
                if not reg2:
                    log.warning("Failed to register toolbar global hotkey: %s", tb_hk_str)
                try:
                    while not self._hotkey_stop.is_set():
                        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            if msg.message == WM_HOTKEY:
                                if msg.wParam == HOTKEY_ID:
                                    fg = user32.GetForegroundWindow()
                                    self._root.after(0, lambda saved_fg=fg: self._toggle_window(saved_fg))
                                elif msg.wParam == HOTKEY_ID_DESKTOP:
                                    try:
                                        self._root.after(0, self._toggle_capture_toolbar)
                                    except Exception as ex:
                                        log.warning("[hotkey] capture toolbar toggle failed: %s", ex)
                            elif msg.message == 0x0012:
                                break
                        else:
                            ctypes.windll.kernel32.Sleep(100)
                finally:
                    user32.UnregisterHotKey(None, HOTKEY_ID)
                    user32.UnregisterHotKey(None, HOTKEY_ID_DESKTOP)

            self._hotkey_thread = threading.Thread(target=listener, daemon=True)
            self._hotkey_thread.start()
            log.info("Global hotkeys registered (Overlay: %s, Toolbar: %s)", ov_hk_str, tb_hk_str)

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
            from overlay_service import OverlayService

            self._root = tk.Tk()
            self._root.withdraw()
            self._overlays = OverlayService(self._root)

            try:
                from startup import set_startup
                set_startup(bool(self.cfg.get("run_at_startup", False)))
            except Exception as exc:
                log.warning("[startup] failed to apply run_at_startup at boot: %s", exc)

            serial_sender.set_port(self.cfg.get("serial_port", "auto"))
            serial_sender.add_line_callback(self._on_serial_line)
            saved_name = self.cfg.get("user_name", "").strip()
            if saved_name:
                serial_sender.queue_on_connect("user_name", saved_name)
            self._setup_providers(self._overlays)
            self._queue_defaults()
            ws_bridge.register_app(self)
            threading.Thread(target=ws_bridge.start, daemon=True, name="ws-bridge").start()

            self._main_win = None

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


    IrisApp().run()
