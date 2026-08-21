"""PC stats provider — thin wrapper around the pc_stats plugin."""

import logging
from collections import namedtuple

import pystray
import plugin_manager

log = logging.getLogger("iris.stats")

Snapshot = namedtuple("Snapshot", "cpu_temp gpu_temp fps exe cpu_pct refresh_rate "
                                  "cpu_temp_unit cpu_temp_max gpu_temp_unit gpu_temp_max")


class StatsProvider:
    def __init__(self, cfg, serial_sender=None):
        self.cfg = cfg
        self.serial = serial_sender

    def start(self):
        pass

    def stop(self):
        pass

    def set_manual_override(self, enabled: bool):
        self.cfg["pc_stats_manual"] = enabled

    def snapshot(self):
        plugin = plugin_manager.get("pc_stats")
        if plugin and hasattr(plugin, "poll"):
            try:
                d = plugin.poll()
                return Snapshot(
                    cpu_temp=d.get("cpu_temp"),
                    gpu_temp=d.get("gpu_temp"),
                    fps=d.get("fps"),
                    exe=d.get("exe", ""),
                    cpu_pct=d.get("cpu_pct", 0.0),
                    refresh_rate=d.get("refresh_rate") or d.get("fps_max") or 60,
                    cpu_temp_unit=d.get("cpu_temp_unit", "\u00b0C"),
                    cpu_temp_max=d.get("cpu_temp_max", 100),
                    gpu_temp_unit=d.get("gpu_temp_unit", "\u00b0C"),
                    gpu_temp_max=d.get("gpu_temp_max", 100),
                )
            except Exception:
                pass
        return Snapshot(None, None, None, "", 0.0, 60,
                        "\u00b0C", 100, "\u00b0C", 100)

    def menu_items(self):
        s = self.snapshot()
        fps_str = f"{s.fps:.0f}" if s.fps is not None else "--"
        cpu_str = f"{s.cpu_temp:.0f}" if s.cpu_temp is not None else "--"
        gpu_str = f"{s.gpu_temp:.0f}" if s.gpu_temp is not None else "--"
        label = f"CPU: {cpu_str}{s.cpu_temp_unit}  GPU: {gpu_str}{s.gpu_temp_unit}  FPS: {fps_str}"
        if s.exe:
            label += f"  [{s.exe}]"
        return [pystray.MenuItem(label, None, enabled=False)]
