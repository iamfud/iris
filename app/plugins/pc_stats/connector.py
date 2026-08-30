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

    def _pcfg(self):
        return (self._cfg.get("plugins") or {}).get("pc_stats", {})

    # ── Lifecycle ────────────────────────────────────────────────

    def connect(self) -> bool:
        if self._serial:
            self._serial.queue_on_connect("cpu_temp_lim",
                                          self._serial_limit("cpu_temp_lim", 90))
            self._serial.queue_on_connect("gpu_temp_lim",
                                          self._serial_limit("gpu_temp_lim", 90))
        return True

    def disconnect(self):
        pass

    @property
    def available(self) -> bool:
        return True

    # ── Settings definitions ─────────────────────────────────────

    @classmethod
    def get_settings(cls) -> list:
        """Temperature Limits section, unit-aware via use_fahrenheit.

        Re-reads the persisted config at discovery so the panel shows
        °F ranges/labels once the toggle has been set and the app reloads.
        """
        fahrenheit = cls._uses_fahrenheit()
        if fahrenheit:
            unit = "\u00b0F"
            lo, hi = 100, 212
        else:
            unit = "\u00b0C"
            lo, hi = 50, 100
        return [
            {
                "title": "Temperature Limits",
                "controls": [
                    {"type": "toggle", "key": "enabled", "label": "Enabled",
                     "description": "Show PC hardware stats on the display"},
                    {"type": "toggle", "key": "use_fahrenheit",
                     "label": "Use Fahrenheit (\u00b0F)",
                     "description": "Set temperature limits in degrees Fahrenheit"},
                    {"type": "slider", "key": "cpu_temp_lim",
                     "label": "CPU Temperature Limit",
                     "min": lo, "max": hi, "step": 5, "unit": unit},
                    {"type": "slider", "key": "gpu_temp_lim",
                     "label": "GPU Temperature Limit",
                     "min": lo, "max": hi, "step": 5, "unit": unit},
                ],
            }
        ]

    @classmethod
    def _uses_fahrenheit(cls) -> bool:
        try:
            import plugin_manager
            cfg = getattr(plugin_manager, "_cfg", None)
            if not cfg:
                from config import load_config
                cfg = load_config()
            pcfg = (cfg.get("plugins") or {}).get("pc_stats", {})
            return bool(pcfg.get("use_fahrenheit", False))
        except Exception:
            return False

    def _serial_limit(self, cfg_key, default) -> str:
        """Limit value for the device, in the user's configured unit.

        The plugin pushes temps in the same unit, so no conversion is
        needed here — raw configured values keep the firmware comparison
        consistent in both °C and °F.
        """
        return str(int(self._pcfg().get(cfg_key, default)))

    # ── Limit migration ──────────────────────────────────────────

    @staticmethod
    def convert_temp(value, to_fahrenheit: bool) -> int:
        """Convert a limit value between °C and °F, rounded to step 5."""
        if value is None:
            return value
        if to_fahrenheit:
            f = value * 9.0 / 5.0 + 32.0
        else:
            f = (value - 32.0) * 5.0 / 9.0
        return int(round(f / 5.0)) * 5

    @classmethod
    def migrate_limits(cls, body: dict, was_fahrenheit: bool) -> dict:
        """Convert stored limits when the °F toggle flips.

        Called by the config-save handler so the user's physical
        threshold is preserved (80 °C ↔ 175 °F) in both directions.
        """
        now_f = bool(body.get("use_fahrenheit", False))
        if now_f == bool(was_fahrenheit):
            return body
        for key in ("cpu_temp_lim", "gpu_temp_lim"):
            val = body.get(key)
            if isinstance(val, (int, float)):
                body[key] = cls.convert_temp(val, to_fahrenheit=now_f)
        return body

    def normalize_limits(self):
        """One-time startup fix for the stale °F config.

        If °F is enabled but a stored limit is still °C-valued (<100,
        outside the °F slider range), convert it so the device alarm
        compares against the intended threshold.
        """
        pcfg = self._pcfg()
        if not bool(pcfg.get("use_fahrenheit", False)):
            return
        changed = False
        for key in ("cpu_temp_lim", "gpu_temp_lim"):
            val = pcfg.get(key)
            if isinstance(val, (int, float)) and val < 100:
                pcfg[key] = self.convert_temp(val, to_fahrenheit=True)
                changed = True
        if changed:
            from config import save_config
            save_config(self._cfg)

    # ── Control definitions ──────────────────────────────────────

    @classmethod
    def controls(cls) -> list:
        lo, hi = (100, 212) if cls._uses_fahrenheit() else (50, 100)
        return [
            {
                "id": "cpu_temp_lim",
                "type": "slider",
                "label": "CPU Temp Limit",
                "min": lo,
                "max": hi,
                "step": 5,
            },
            {
                "id": "gpu_temp_lim",
                "type": "slider",
                "label": "GPU Temp Limit",
                "min": lo,
                "max": hi,
                "step": 5,
            },
        ]

    # ── Actions ──────────────────────────────────────────────────

    def handle(self, control_id: str, value=None):
        if control_id in ("cpu_temp_lim", "gpu_temp_lim"):
            val = int(value)
            pcfg = self._cfg.setdefault("plugins", {}).setdefault("pc_stats", {})
            pcfg[control_id] = val
            if self._serial:
                self._serial.set_live(control_id, self._serial_limit(control_id, val))

    # ── Dynamic options ──────────────────────────────────────────

    def get_options(self, option_key: str) -> list:
        return []
