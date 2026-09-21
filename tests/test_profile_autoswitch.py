import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import panel_actions
from panel_actions import mobile_panel_payload, resolve_panel_board
import plugin_manager
import config


class ProfileAutoSwitchTests(unittest.TestCase):
    def setUp(self):
        panel_actions._RESOLVE_CACHE.update({
            "sig": None,
            "ts": 0.0,
            "board": None,
            "active_ids": None,
            "fg": None,
            "cfg_ver": None,
        })

    def _config(self, profiles):
        return {
            "panel_board": [{"type": "EMPTY", "name": "Default"}],
            "panel_profiles": profiles,
            "panel_layout": [],
            "panel_sliders": [],
            "panel_utility": [],
            "panel_core": [],
            "panel_gauges": {"enabled": True},
        }

    def test_running_profile_is_appended_and_reported_to_mobile_clients(self):
        profiles = [{
            "id": "prof_elite",
            "name": "Elite Dangerous",
            "exe": "EliteDangerous64.exe",
            "enabled": True,
            "auto_switch": True,
            "theme": {"accent": "#ff5500", "neon": "#ffaa00"},
            "board": [{"type": "ACTION", "name": "Elite"}],
        }]
        cfg = self._config(profiles)

        with patch("win_platform.get_running_process_names", return_value=["EliteDangerous64.exe"]), \
             patch("panel_actions.foreground_exe", return_value="iris.exe"):
            board, active_ids, _ = resolve_panel_board(cfg)
            payload = mobile_panel_payload(cfg)

        self.assertEqual(active_ids, ["prof_elite"])
        self.assertEqual(payload["active_profiles"], ["prof_elite"])
        self.assertEqual(payload["panel_profiles"], [{
            "id": "prof_elite",
            "exe": "EliteDangerous64.exe",
            "enabled": True,
            "auto_switch": True,
            "theme": {"accent": "#ff5500", "neon": "#ffaa00"},
        }])
        self.assertEqual(board[-1]["name"], "Elite")
        self.assertEqual(payload["panel_board"][-1]["name"], "Elite")

    def test_stopped_profile_is_not_active_or_sent_as_active(self):
        profile = {
            "id": "prof_elite",
            "name": "Elite Dangerous",
            "exe": "EliteDangerous64.exe",
            "enabled": True,
            "auto_switch": True,
            "theme": {"accent": "#ff5500", "neon": "#ffaa00"},
            "board": [{"type": "ACTION", "name": "Elite"}],
        }
        cfg = self._config([profile])

        with patch("win_platform.get_running_process_names", return_value=[]), \
             patch("panel_actions.foreground_exe", return_value="iris.exe"):
            _, active_ids, _ = resolve_panel_board(cfg)
            payload = mobile_panel_payload(cfg)

        self.assertEqual(active_ids, [])
        self.assertEqual(payload["active_profiles"], [])
        self.assertEqual(payload["panel_profiles"][0]["id"], "prof_elite")

    def test_multiple_running_profiles_preserve_active_order(self):
        profiles = [
            {
                "id": "prof_elite",
                "exe": "EliteDangerous64.exe",
                "enabled": True,
                "auto_switch": True,
                "theme": {"accent": "#ff5500", "neon": "#ffaa00"},
                "board": [{"type": "ACTION", "name": "Elite"}],
            },
            {
                "id": "prof_sim",
                "exe": "simulator.exe",
                "enabled": True,
                "auto_switch": True,
                "theme": {"accent": "#00ff00", "neon": "#0000ff"},
                "board": [{"type": "ACTION", "name": "Sim"}],
            },
        ]
        cfg = self._config(profiles)

        with patch(
            "win_platform.get_running_process_names",
            return_value=["EliteDangerous64.exe", "simulator.exe"],
        ), patch("panel_actions.foreground_exe", return_value="iris.exe"):
            _, active_ids, _ = resolve_panel_board(cfg)

        self.assertEqual(active_ids, ["prof_elite", "prof_sim"])

    def test_mobile_payload_includes_keep_alive_and_screensaver_settings(self):
        cfg = self._config([])
        cfg["keep_alive"] = False
        cfg["screensaver_timeout"] = 7

        payload = mobile_panel_payload(cfg)

        self.assertFalse(payload["keep_alive"])
        self.assertEqual(payload["screensaver_timeout"], 7)

    def test_profile_theme_is_restored_when_game_exits(self):
        profile = {
            "id": "prof_elite",
            "name": "Elite Dangerous",
            "exe": "EliteDangerous64.exe",
            "enabled": True,
            "theme": {"accent": "#ff5500", "neon": "#ffaa00"},
            "theme_override": True,
            "lighting_theme_enabled": False,
        }
        cfg = self._config([profile])
        cfg["theme"] = {"mode": "iris", "accent": "#b23af6", "neon": "#48b2e9"}

        old_state = {
            "_cfg": plugin_manager._cfg,
            "_manifests": plugin_manager._manifests,
            "_saved_base_theme": plugin_manager._saved_base_theme,
            "_active_themed_plugin": plugin_manager._active_themed_plugin,
            "_active_themed_exe": plugin_manager._active_themed_exe,
            "_themed_exe_has_run": plugin_manager._themed_exe_has_run,
            "_themed_exe_started_at": plugin_manager._themed_exe_started_at,
            "_themed_exe_miss_count": plugin_manager._themed_exe_miss_count,
        }
        try:
            plugin_manager._cfg = cfg
            plugin_manager._manifests = {}
            plugin_manager._saved_base_theme = None
            plugin_manager._active_themed_plugin = None
            plugin_manager._active_themed_exe = None
            plugin_manager._themed_exe_has_run = False
            plugin_manager._themed_exe_miss_count = 0

            with patch("panel_actions._running_profile_exes", return_value={"elitedangerous64"}), \
                 patch("plugin_manager._broadcast_theme") as broadcast, \
                 patch("plugin_manager._ensure_theme_watcher"):
                plugin_manager.sync_plugin_themes()

                self.assertEqual(cfg["theme"]["accent"], "#ff5500")
                self.assertEqual(plugin_manager._active_themed_plugin, "prof_elite")
                self.assertEqual(
                    plugin_manager.get_persisted_theme(cfg),
                    {
                        "mode": "iris",
                        "accent": "#b23af6",
                        "neon": "#48b2e9",
                    },
                )
                with tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, "config.json")
                    with patch("config.config_path", return_value=path):
                        config.save_config(cfg)
                    with open(path) as saved:
                        self.assertEqual(
                            json.load(saved)["theme"],
                            {
                                "mode": "iris",
                                "accent": "#b23af6",
                                "neon": "#48b2e9",
                            },
                        )

                with patch("panel_actions._running_profile_exes", return_value=set()), \
                     patch("plugin_manager._broadcast_theme") as broadcast:
                    plugin_manager.sync_plugin_themes()

                self.assertEqual(cfg["theme"], {
                    "mode": "iris",
                    "accent": "#b23af6",
                    "neon": "#48b2e9",
                })
                broadcast.assert_called_once_with(cfg["theme"])
        finally:
            for name, value in old_state.items():
                setattr(plugin_manager, name, value)


if __name__ == "__main__":
    unittest.main()
