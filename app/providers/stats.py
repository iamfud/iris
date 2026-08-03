"""PC stats provider — thin wrapper around the pc_stats plugin."""

import logging
from collections import namedtuple

import pystray
import plugin_manager

log = logging.getLogger("iris.stats")

Snapshot = namedtuple("Snapshot", "cpu_temp gpu_temp fps exe cpu_pct")


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
                )
            except Exception:
                pass
        return Snapshot(None, None, None, "", 0.0)

    def menu_items(self):
        s = self.snapshot()
        fps_str = f"{s.fps:.0f}" if s.fps is not None else "--"
        cpu_str = f"{s.cpu_temp:.0f}" if s.cpu_temp is not None else "--"
        gpu_str = f"{s.gpu_temp:.0f}" if s.gpu_temp is not None else "--"
        label = f"CPU: {cpu_str}°C  GPU: {gpu_str}°C  FPS: {fps_str}"
        if s.exe:
            label += f"  [{s.exe}]"
        return [pystray.MenuItem(label, None, enabled=False)]
