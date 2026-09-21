import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from lighting_service import LightingService, ON_FOOT_COLOR
from plugins.akp02_stats.plugin import ON_FOOT_ACCENT_COLOR
from plugins.akp02_stats.plugin import Plugin as Akp02Plugin
from plugins.elite_dangerous.plugin import Plugin


class _LightingServiceStub:
    def __init__(self):
        self.values = []

    def set_on_foot(self, active):
        self.values.append(bool(active))


class EliteOnFootLightingTests(unittest.TestCase):
    def test_on_foot_lighting_transitions_are_sent_once(self):
        plugin = Plugin({}, None, None)
        lighting = _LightingServiceStub()

        with patch("lighting_service.get_lighting_service", return_value=lighting):
            plugin._set_on_foot_lighting(True)
            plugin._set_on_foot_lighting(True)
            plugin._set_on_foot_lighting(False)

        self.assertEqual(lighting.values, [True, False])

    def test_lighting_service_uses_blue_override_and_restores_baseline(self):
        service = LightingService()
        service._openrgb_baseline = lambda: {"rgb": "__theme__"}
        service._ha_daylight = lambda: {}
        service._dispatch_actions = patch.object(service, "_dispatch_actions").start()
        self.addCleanup(patch.stopall)

        service.set_on_foot(True)
        service.set_on_foot(False)

        calls = service._dispatch_actions.call_args_list
        self.assertEqual(calls[0].args[0], {"rgb": ON_FOOT_COLOR})
        self.assertEqual(calls[1].args[0], {"rgb": "__theme__"})

    def test_akp02_uses_blue_accent_while_on_foot(self):
        plugin = Akp02Plugin({})
        plugin.on_theme({"mode": "custom", "neon": "#ffaa00", "accent": "#ff5500"})

        self.assertEqual(plugin._resolve_accent_color(), "#ffaa00")
        plugin.set_on_foot(True)
        self.assertEqual(plugin._resolve_accent_color(), ON_FOOT_ACCENT_COLOR)
        plugin.set_on_foot(False)
        self.assertEqual(plugin._resolve_accent_color(), "#ffaa00")


if __name__ == "__main__":
    unittest.main()
