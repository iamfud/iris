"""MAX7219 / ESP8266 LED matrix display driver."""

import logging
from typing import Any, Dict

from displays.base import BaseDisplayDriver

log = logging.getLogger("iris.displays.matrix")


class MatrixDisplayDriver(BaseDisplayDriver):
    """Driver for 32x8 MAX7219 LED matrix displays connected via serial."""

    def __init__(self, serial_sender=None):
        super().__init__(name="max7219", width_px=32, height_px=8)
        self._serial = serial_sender
        self.is_connected = bool(serial_sender and getattr(serial_sender, "is_connected", False))

    def set_serial_sender(self, serial_sender):
        self._serial = serial_sender
        self.is_connected = bool(serial_sender and getattr(serial_sender, "is_connected", False))

    def start(self) -> bool:
        if self._serial:
            self.is_connected = getattr(self._serial, "is_connected", False)
            return self.is_connected
        return False

    def stop(self):
        self.is_connected = False

    def render_stats(self, stats: Dict[str, Any]):
        if not self._serial or not self.is_connected:
            return
        cpu = stats.get("cpu_usage", stats.get("cpu", 0))
        cpu_temp = stats.get("cpu_temp")
        gpu_temp = stats.get("gpu_temp")
        fps = stats.get("fps")
        try:
            self._serial.send_stats(cpu, cpu_temp, gpu_temp, fps)
        except Exception as ex:
            log.debug("[displays.matrix] send_stats error: %s", ex)

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
