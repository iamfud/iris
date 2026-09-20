"""MAX7219 / ESP8266 LED matrix display driver."""

import logging
from typing import Any, Dict

from displays.base import BaseDisplayDriver

log = logging.getLogger("iris.displays.matrix")


class MatrixDisplayDriver(BaseDisplayDriver):
    """Driver for 32x8 MAX7219 LED matrix displays connected via serial."""

    def __init__(self, serial_sender=None, cfg=None):
        super().__init__(name="max7219", width_px=32, height_px=8)
        self._serial = serial_sender
        self._cfg = cfg or {}
        self._overlay_active = False

    @property
    def is_connected(self) -> bool:
        if not self._serial:
            return False
        if hasattr(self._serial, "is_connected"):
            return bool(self._serial.is_connected)
        if hasattr(self._serial, "connected_port"):
            return self._serial.connected_port() is not None
        return False

    @is_connected.setter
    def is_connected(self, value: bool):
        pass


    def set_serial_sender(self, serial_sender):
        self._serial = serial_sender

    def start(self) -> bool:
        return self.is_connected

    def stop(self):
        self.clear()

    def render_stats(self, stats: Dict[str, Any]):
        if not self._serial or not self.is_connected:
            return

        # If pc_stats plugin is already active (e.g. RTSS running), yield to avoid duplicate serial packets
        try:
            import plugin_manager
            pc_stats = plugin_manager.get("pc_stats")
            if pc_stats and getattr(pc_stats, "_running", False):
                return
        except Exception:
            pass

        cpu = stats.get("cpu_usage", stats.get("cpu", 0))
        cpu_temp = stats.get("cpu_temp")
        gpu_temp = stats.get("gpu_temp")
        fps = stats.get("fps")

        manual_override = self._cfg.get("pc_stats_manual", False) if self._cfg else False
        stats_enabled = self._cfg.get("pc_stats_enabled", True) if self._cfg else True
        game_active = bool(fps is not None and fps > 0)
        should_show = manual_override or (stats_enabled and game_active)

        if should_show:
            if not self._overlay_active:
                pc_flags = self._cfg.get("pc_disp", 7) if self._cfg else 7
                try:
                    self._serial.set_live("pc_disp", str(pc_flags))
                except Exception:
                    pass
                self._overlay_active = True
            try:
                self._serial.send_stats(cpu, cpu_temp, gpu_temp, fps)
            except Exception as ex:
                log.debug("[displays.matrix] send_stats error: %s", ex)
        elif self._overlay_active:
            self._overlay_active = False
            try:
                self._serial.set_live("pc_disp", "0")
            except Exception as ex:
                log.debug("[displays.matrix] clear error: %s", ex)


    def render_notification(self, title: str, message: str, theme: str = "purple"):
        if not self._serial or not self.is_connected:
            return
        try:
            text = f"{title}: {message}" if title else message
            self._serial.send_notify("NOTIFY", text)
        except Exception as ex:
            log.debug("[displays.matrix] render_notification error: %s", ex)

    def render_progress(self, label: str, percent: float):
        if not self._serial or not self.is_connected:
            return
        try:
            self._serial.send_progress(label, int(percent))
        except Exception as ex:
            log.debug("[displays.matrix] render_progress error: %s", ex)

    def clear(self):
        if not self._serial or not self.is_connected:
            return
        try:
            self._serial.set_live("pc_disp", "0")
        except Exception as ex:
            log.debug("[displays.matrix] clear error: %s", ex)
