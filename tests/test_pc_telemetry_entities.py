import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import panel_entities
import panel_runtime


class PcTelemetryEntityTests(unittest.TestCase):
    def test_normalized_values_match_current_entity_state_values(self):
        snapshot = {
            "cpu_usage": 42.5,
            "cpu_temp": 61.0,
            "gpu_temp": 54.0,
            "fps": 143.2,
        }
        class _Engine:
            def get_entity_states(self):
                return {
                    "pc_stats.cpu_usage": {"value": snapshot["cpu_usage"]},
                    "pc_stats.cpu_temp": {"value": snapshot["cpu_temp"]},
                    "pc_stats.gpu_temp": {"value": snapshot["gpu_temp"]},
                    "pc_stats.fps": {"value": snapshot["fps"]},
                    "pc_stats.ram_usage": {"value": 40.0, "label": "40.0%"},
                }

        with patch("telemetry.get_telemetry_engine", return_value=_Engine()):
            states = panel_entities.get_live_entity_states()

        self.assertEqual(states["pc_stats.cpu_usage"]["value"], snapshot["cpu_usage"])
        self.assertEqual(states["pc_stats.cpu_temp"]["value"], snapshot["cpu_temp"])
        self.assertEqual(states["pc_stats.gpu_temp"]["value"], snapshot["gpu_temp"])
        self.assertEqual(states["pc_stats.fps"]["value"], snapshot["fps"])
        self.assertEqual(states["pc_stats.ram_usage"]["value"], 40.0)

    def test_panel_entities_calls_projection_without_polling_or_collection(self):
        snapshot = {
            "cpu_usage": 42.5,
            "cpu_temp": 61.0,
            "gpu_temp": 54.0,
            "fps": 143.2,
        }

        class _Engine:
            def __init__(self):
                self.snapshot_calls = 0

            def get_entity_states(self):
                self.snapshot_calls += 1
                return {
                    "pc_stats.cpu_usage": {"value": snapshot["cpu_usage"]},
                    "pc_stats.cpu_temp": {"value": snapshot["cpu_temp"]},
                    "pc_stats.gpu_temp": {"value": snapshot["gpu_temp"]},
                    "pc_stats.fps": {"value": snapshot["fps"]},
                }

            def collect(self):
                raise AssertionError("panel_entities must not collect telemetry")

        class _StatsProvider:
            last_stats = {
                "cpu_usage": 50.0,
                "cpu_temp": 65.0,
                "gpu_temp": 55.0,
                "fps": 120.0,
            }

            def poll(self):
                raise AssertionError("panel_entities must not poll PC Stats")

        engine = _Engine()
        app = types.SimpleNamespace(_stats_provider=_StatsProvider())
        with patch("telemetry.get_telemetry_engine", return_value=engine), \
             patch("ws_bridge._app", app), \
             patch("panel_entities.project_pc_telemetry", wraps=panel_entities.project_pc_telemetry) as projection:
            states = panel_entities.get_live_entity_states()

        projection.assert_called_once()
        self.assertEqual(states["pc_stats.cpu_usage"]["value"], 50.0)
        self.assertEqual(states["pc_stats.cpu_temp"]["value"], 65.0)
        self.assertEqual(states["pc_stats.gpu_temp"]["value"], 55.0)
        self.assertEqual(states["pc_stats.fps"]["value"], 120.0)
        self.assertEqual(engine.snapshot_calls, 1)

    def test_panel_entities_preserves_unavailable_values_and_non_pc_entities(self):
        class _Engine:
            def get_entity_states(self):
                return {}

        with patch("telemetry.get_telemetry_engine", return_value=_Engine()), \
             patch("ws_bridge._app", None):
            states = panel_entities.get_live_entity_states()

        self.assertNotIn("pc_stats.cpu_usage", states)
        self.assertNotIn("pc_stats.cpu_temp", states)
        self.assertNotIn("pc_stats.gpu_temp", states)
        self.assertNotIn("pc_stats.fps", states)
        self.assertIn("time.str", states)

    def test_normalized_values_match_current_panel_gauge_values(self):
        snapshot = {
            "cpu_usage": 42.5,
            "cpu_temp": 61.0,
            "gpu_temp": 54.0,
            "fps": 143.2,
        }
        class _Engine:
            def get_snapshot(self):
                return dict(snapshot)

        with patch("telemetry.get_telemetry_engine", return_value=_Engine()), \
             patch("plugin_manager.get", return_value=None):
            gauges = panel_runtime._gauges()

        self.assertEqual(gauges["cpu_pct"], snapshot["cpu_usage"])
        self.assertEqual(gauges["cpu_temp"], snapshot["cpu_temp"])
        self.assertEqual(gauges["gpu_temp"], snapshot["gpu_temp"])
        self.assertEqual(gauges["fps"], snapshot["fps"])


if __name__ == "__main__":
    unittest.main()
