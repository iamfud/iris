"""PC Stats connector — reads/writes temperature limits from config.

This connector has no external service — it reads from the Iris config
and pushes values to the device via serial.  It exists so the plugin
itself stays a thin orchestrator like every other plugin.
"""

import logging

from connector_base import BaseConnector

log = logging.getLogger("iris.plugins.pc_stats.connector")


class PCStatsConnector(BaseConnector):

    def __init__(self, cfg, serial_sender=None):
        self._cfg = cfg
        self._serial = serial_sender

    # ── Lifecycle ────────────────────────────────────────────────

    def connect(self) -> bool:
        if self._serial:
            self._serial.queue_on_connect("cpu_temp_lim",
                                          str(self._cfg.get("cpu_temp_lim", 90)))
            self._serial.queue_on_connect("gpu_temp_lim",
                                          str(self._cfg.get("gpu_temp_lim", 90)))
        return True

    def disconnect(self):
        pass

    @property
    def available(self) -> bool:
        return True

    # ── Control definitions ──────────────────────────────────────

    @classmethod
    def controls(cls) -> list:
        return [
            {
                "id": "cpu_temp_lim",
                "type": "slider",
                "label": "CPU Temp Limit",
                "min": 50,
                "max": 100,
                "step": 5,
            },
            {
                "id": "gpu_temp_lim",
                "type": "slider",
                "label": "GPU Temp Limit",
                "min": 50,
                "max": 100,
                "step": 5,
            },
        ]

    # ── Actions ──────────────────────────────────────────────────

    def handle(self, control_id: str, value=None):
        if control_id in ("cpu_temp_lim", "gpu_temp_lim"):
            val = int(value)
            self._cfg[control_id] = val
            if self._serial:
                self._serial.set_live(control_id, str(val))

    # ── Dynamic options ──────────────────────────────────────────

    def get_options(self, option_key: str) -> list:
        return []
