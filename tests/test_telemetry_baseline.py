import os
import sys
import threading
import types
import unittest
from collections import namedtuple
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import panel_entities
import panel_runtime
from plugins.pc_stats.plugin import Plugin, Snapshot
from telemetry.collector import TelemetryEngine
from telemetry.read_projection import project_pc_telemetry


class _FakePsutil:
    CpuTimes = namedtuple("CpuTimes", "user system idle")
    VM = namedtuple("VM", "percent used total")
    Swap = namedtuple("Swap", "percent")
    Disk = namedtuple("Disk", "used total percent")
    Freq = namedtuple("Freq", "current")

    def cpu_times(self):
        return self.CpuTimes(30.0, 10.0, 60.0)

    def cpu_count(self, logical=True):
        return 16 if logical else 8

    def virtual_memory(self):
        return self.VM(40.0, 8_000_000_000, 16_000_000_000)

    def swap_memory(self):
        return self.Swap(2.0)

    def disk_usage(self, _path):
        return self.Disk(10_000_000_000, 20_000_000_000, 50.0)

    def net_io_counters(self):
        return types.SimpleNamespace(bytes_sent=2000, bytes_recv=4000)

    def pids(self):
        return [1, 2]

    def cpu_freq(self):
        return self.Freq(3000.0)


class _FakeLhm:
    def __init__(self, data):
        self.data = data

    def read(self):
        return dict(self.data)


class _FakeNvml:
    def __init__(self, data):
        self.data = data

    def read(self):
        return dict(self.data)


class _FakeFps:
    def __init__(self, data):
        self.data = data

    def get_stats(self):
        return dict(self.data)


class _FakeCpuTracker:
    base_mhz = 3000

    def read(self):
        return 4.0, 3.5


def _engine_for(lhm_data, nvml_data, fps_data):
    engine = TelemetryEngine.__new__(TelemetryEngine)
    engine._lhm = _FakeLhm(lhm_data)
    engine._nvml = _FakeNvml(nvml_data)
    engine._fps_tracker = _FakeFps(fps_data)
    engine._cpu_tracker = _FakeCpuTracker()
    engine._net_prev = types.SimpleNamespace(bytes_sent=1000, bytes_recv=2000)
    engine._net_t = 999.0
    engine._boot_time = 999.0
    engine._gpu_name = "Test GPU"
    engine._is_admin = False
    engine._last_cpu_times = _FakePsutil.CpuTimes(20.0, 10.0, 50.0)
    engine._last_cpu_pct = 12.0
    return engine


class TelemetryBaselineTests(unittest.TestCase):
    def test_engine_entity_states_use_projection_and_preserve_additional_entities(self):
        engine = TelemetryEngine.__new__(TelemetryEngine)
        snapshot = {
            "cpu_usage": 42.5,
            "cpu_temp": 61.0,
            "gpu_temp": 54.0,
            "fps": 143.2,
            "ram_usage": 40.0,
            "cpu_boost_peak": "4.00 GHz",
            "vram_pct": 25.0,
            "game_name": "game.exe",
        }
        with patch.object(engine, "get_snapshot", return_value=snapshot) as get_snapshot, \
             patch.object(engine, "collect", side_effect=AssertionError("must not collect")), \
             patch("telemetry.collector.project_pc_telemetry", wraps=project_pc_telemetry) as projection:
            states = engine.get_entity_states()

        get_snapshot.assert_called_once_with()
        projection.assert_called_once_with(snapshot)
        self.assertEqual(states["pc_stats.cpu_usage"], {"value": 42.5, "label": "42.5%"})
        self.assertEqual(states["pc_stats.cpu_temp"], {"value": 61.0, "label": "61.0°C"})
        self.assertEqual(states["pc_stats.gpu_temp"], {"value": 54.0, "label": "54.0°C"})
        self.assertEqual(states["pc_stats.fps"], {"value": 143.2, "label": "143.2 FPS"})
        self.assertEqual(states["pc_stats.ram_usage"], {"value": 40.0, "label": "40.0%"})
        self.assertEqual(states["pc_stats.cpu_freq"], {"value": "4.00 GHz", "label": "4.00 GHz"})
        self.assertEqual(states["pc_stats.vram_pct"], {"value": 25.0, "label": "25.0%"})
        self.assertEqual(states["pc_stats.game_name"], {"value": "game.exe", "label": "game.exe"})

    def test_engine_prefers_lhm_gpu_temperature_and_fps_tracker(self):
        engine = _engine_for(
            {
                "cpu_temp": 61.0,
                "gpu_temps": {"GPU Core": 54.0},
                "gpu_clocks": {},
                "gpu_loads": {},
            },
            {"gpu_temp": 70.0},
            {"fps": 143.2, "game_name": "game.exe"},
        )
        with patch("telemetry.collector.psutil", _FakePsutil()):
            snapshot = engine.collect()

        self.assertEqual(snapshot["cpu_temp"], 61.0)
        self.assertEqual(snapshot["gpu_temp"], 54.0)
        self.assertEqual(snapshot["fps"], 143.2)

    def test_engine_uses_nvml_when_lhm_gpu_temperature_is_missing(self):
        engine = _engine_for(
            {
                "cpu_temp": 61.0,
                "gpu_temps": {},
                "gpu_clocks": {},
                "gpu_loads": {},
            },
            {"gpu_temp": 70.0},
            {"fps": None, "game_name": None},
        )
        with patch("telemetry.collector.psutil", _FakePsutil()):
            snapshot = engine.collect()

        self.assertEqual(snapshot["gpu_temp"], 70.0)
        self.assertIsNone(snapshot["fps"])

    def test_engine_uses_lhm_cpu_load_only_when_cpu_delta_is_zero(self):
        engine = _engine_for(
            {
                "cpu_temp": None,
                "cpu_load": 33.0,
                "gpu_temps": {},
                "gpu_clocks": {},
                "gpu_loads": {},
            },
            {},
            {"fps": None, "game_name": None},
        )
        engine._last_cpu_times = _FakePsutil.CpuTimes(30.0, 10.0, 60.0)
        engine._last_cpu_pct = 0.0
        with patch("telemetry.collector.psutil", _FakePsutil()):
            snapshot = engine.collect()

        self.assertEqual(snapshot["cpu_usage"], 33.0)
        self.assertIsNone(snapshot["cpu_temp"])

    def test_pc_stats_poll_applies_fahrenheit_without_changing_usage_or_fps(self):
        plugin = Plugin.__new__(Plugin)
        plugin._lock = threading.Lock()
        plugin._snapshot = Snapshot(20.0, 30.0, 60.0, "game.exe", 45.0, 144)
        plugin._cfg = {"plugins": {"pc_stats": {"use_fahrenheit": True}}}

        result = plugin.poll()

        self.assertEqual(result["cpu_temp"], 68.0)
        self.assertEqual(result["gpu_temp"], 86.0)
        self.assertEqual(result["cpu_temp_unit"], "°F")
        self.assertEqual(result["gpu_temp_unit"], "°F")
        self.assertEqual(result["cpu_temp_max"], 212)
        self.assertEqual(result["gpu_temp_max"], 212)
        self.assertEqual(result["cpu_pct"], 45.0)
        self.assertEqual(result["fps"], 60.0)

    def test_panel_gauges_use_pc_stats_cached_values_as_overrides(self):
        class _Engine:
            def get_snapshot(self):
                return {
                    "cpu_usage": 20.0,
                    "cpu_temp": 50.0,
                    "gpu_temp": 60.0,
                    "fps": 90.0,
                    "ram_pct": 40.0,
                }

        class _PcStats:
            poll_count = 0

            def poll(self):
                self.poll_count += 1
                return {
                    "available": True,
                    "cpu_pct": 45.0,
                    "cpu_temp": 68.0,
                    "gpu_temp": 86.0,
                    "fps": 144.0,
                    "cpu_temp_unit": "°F",
                    "gpu_temp_unit": "°F",
                    "cpu_temp_max": 212,
                    "gpu_temp_max": 212,
                }

        pc_stats = _PcStats()
        with patch("telemetry.get_telemetry_engine", return_value=_Engine()), \
             patch("plugin_manager.get", return_value=pc_stats):
            gauges = panel_runtime._gauges()

        self.assertEqual(gauges["cpu_pct"], 45.0)
        self.assertEqual(gauges["cpu_temp"], 68.0)
        self.assertEqual(gauges["gpu_temp"], 86.0)
        self.assertEqual(gauges["fps"], 144.0)
        self.assertEqual(gauges["cpu_temp_unit"], "°F")
        self.assertEqual(gauges["cpu_temp_max"], 212)
        self.assertEqual(pc_stats.poll_count, 1)

    def test_panel_entities_fill_missing_values_from_engine(self):
        class _Engine:
            def get_entity_states(self):
                return {
                    "pc_stats.cpu_usage": {"value": 20.0, "label": "20.0%"},
                    "pc_stats.cpu_temp": {"value": 50.0, "label": "50.0°C"},
                    "pc_stats.gpu_temp": {"value": 60.0, "label": "60.0°C"},
                    "pc_stats.fps": {"value": 90.0, "label": "90.0 FPS"},
                }

        with patch("telemetry.get_telemetry_engine", return_value=_Engine()), \
             patch("ws_bridge._app", None):
            states = panel_entities.get_live_entity_states()

        self.assertEqual(states["pc_stats.cpu_usage"]["value"], 20.0)
        self.assertEqual(states["pc_stats.cpu_temp"]["value"], 50.0)
        self.assertEqual(states["pc_stats.gpu_temp"]["value"], 60.0)
        self.assertEqual(states["pc_stats.fps"]["value"], 90.0)


if __name__ == "__main__":
    unittest.main()
