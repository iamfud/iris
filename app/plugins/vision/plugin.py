"""Vision plugin — thin wrapper delegating to VisionSensorManager."""

import logging

from .connector import VisionSensorManager

log = logging.getLogger("iris.plugins.vision")


class Plugin:
    name = "vision"
    display_name = "Vision"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._serial = serial_sender
        self.overlays = overlays
        self._manager = VisionSensorManager(cfg, serial_sender, overlays=overlays)

    def start(self):
        self._manager.start()
        log.info("vision plugin started")

    def stop(self):
        self._manager.stop()
        if self._serial and hasattr(self._serial, "clear_display_prefix"):
            self._serial.clear_display_prefix("vision.")

    def poll(self):
        return self._manager.poll()

    def snapshot(self):
        return self._manager.snapshot()
