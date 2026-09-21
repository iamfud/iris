import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from telemetry.read_projection import project_pc_telemetry


class TelemetryReadProjectionTests(unittest.TestCase):
    def test_engine_snapshot_values_match_existing_entity_shape(self):
        result = project_pc_telemetry(
            {
                "cpu_pct": 42.5,
                "cpu_temp": 61.0,
                "gpu_temp": 54.0,
                "fps": 143.2,
            }
        )

        self.assertEqual(result["gauges"]["cpu_pct"], 42.5)
        self.assertEqual(result["gauges"]["cpu_temp"], 61.0)
        self.assertEqual(result["gauges"]["gpu_temp"], 54.0)
        self.assertEqual(result["gauges"]["fps"], 143.2)
        self.assertEqual(
            result["entities"],
            {
                "pc_stats.cpu_temp": {"value": 61.0, "label": "61.0°C"},
                "pc_stats.gpu_temp": {"value": 54.0, "label": "54.0°C"},
                "pc_stats.fps": {"value": 143.2, "label": "143.2 FPS"},
                "pc_stats.cpu_usage": {"value": 42.5, "label": "42.5%"},
            },
        )

    def test_cpu_usage_uses_existing_key_precedence_then_supplied_fallback(self):
        result = project_pc_telemetry(
            {"cpu_pct": None, "cpu_usage": None, "cpu": None},
            cpu_usage_fallback=17.5,
        )
        self.assertEqual(result["gauges"]["cpu_pct"], 17.5)
        self.assertEqual(result["entities"]["pc_stats.cpu_usage"]["value"], 17.5)

        result = project_pc_telemetry(
            {"cpu_pct": 10.0, "cpu_usage": 20.0, "cpu": 30.0},
            cpu_usage_fallback=40.0,
        )
        self.assertEqual(result["gauges"]["cpu_pct"], 10.0)

    def test_missing_values_remain_missing_and_are_not_created_by_projection(self):
        result = project_pc_telemetry(
            {"cpu_usage": None, "cpu_temp": None, "gpu_temp": None, "fps": None},
            cpu_usage_fallback=None,
        )

        self.assertIsNone(result["gauges"]["cpu_pct"])
        self.assertIsNone(result["gauges"]["cpu_temp"])
        self.assertIsNone(result["gauges"]["gpu_temp"])
        self.assertIsNone(result["gauges"]["fps"])
        self.assertEqual(result["entities"], {})

    def test_cached_pc_stats_overrides_values_and_preserves_fahrenheit_metadata(self):
        result = project_pc_telemetry(
            {
                "cpu_usage": 20.0,
                "cpu_temp": 50.0,
                "gpu_temp": 60.0,
                "fps": 90.0,
            },
            pc_stats_snapshot={
                "available": True,
                "cpu_pct": 45.0,
                "cpu_temp": 68.0,
                "gpu_temp": 86.0,
                "fps": 144.0,
                "cpu_temp_unit": "°F",
                "gpu_temp_unit": "°F",
                "cpu_temp_max": 212,
                "gpu_temp_max": 212,
            },
        )

        self.assertEqual(result["gauges"]["cpu_pct"], 45.0)
        self.assertEqual(result["gauges"]["cpu_temp"], 68.0)
        self.assertEqual(result["gauges"]["gpu_temp"], 86.0)
        self.assertEqual(result["gauges"]["fps"], 144.0)
        self.assertEqual(result["gauges"]["cpu_temp_unit"], "°F")
        self.assertEqual(result["gauges"]["gpu_temp_unit"], "°F")
        self.assertEqual(result["gauges"]["cpu_temp_max"], 212)
        self.assertEqual(result["gauges"]["gpu_temp_max"], 212)
        self.assertEqual(result["entities"]["pc_stats.cpu_temp"]["label"], "68.0°C")

    def test_unavailable_pc_stats_does_not_override_engine_values(self):
        result = project_pc_telemetry(
            {"cpu_usage": 20.0, "cpu_temp": 50.0, "gpu_temp": 60.0, "fps": 90.0},
            pc_stats_snapshot={
                "available": False,
                "cpu_pct": 45.0,
                "cpu_temp": 68.0,
                "gpu_temp": 86.0,
                "fps": 144.0,
            },
        )

        self.assertEqual(result["gauges"]["cpu_pct"], 20.0)
        self.assertEqual(result["gauges"]["cpu_temp"], 50.0)
        self.assertEqual(result["gauges"]["gpu_temp"], 60.0)
        self.assertEqual(result["gauges"]["fps"], 90.0)

    def test_projection_does_not_call_plugin_poll(self):
        class _NoPoll:
            def poll(self):
                raise AssertionError("projection must not poll a plugin")

        result = project_pc_telemetry(
            {"cpu_usage": 20.0},
            pc_stats_snapshot={"available": True, "source": _NoPoll()},
        )
        self.assertEqual(result["gauges"]["cpu_pct"], 20.0)


if __name__ == "__main__":
    unittest.main()
