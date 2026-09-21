import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import plugin_manager


def _write_plugin(base, name, manifest, connector_body=""):
    plugin_dir = os.path.join(base, name)
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    if connector_body:
        with open(os.path.join(plugin_dir, "connector.py"), "w", encoding="utf-8") as f:
            f.write(connector_body)
    return plugin_dir


def _manifest(name):
    return {
        "name": name,
        "version": "1.0",
        "display_name": name.title(),
        "type": "service",
        "capabilities": {"status": True, "live_data": True},
        "settings": [],
    }


class PluginDiscoverySecurityTests(unittest.TestCase):
    def setUp(self):
        plugin_manager._cfg = {"plugin_trust": {}}
        plugin_manager._DISCOVERED_CACHE = None
        plugin_manager._PROVENANCE = {}

    def test_current_builtin_manifests_validate(self):
        import glob
        for path in glob.glob(os.path.join(os.path.dirname(__file__), "..", "app", "plugins", "*", "plugin.json")):
            name = os.path.basename(os.path.dirname(path))
            with open(path, encoding="utf-8") as f:
                manifest = json.load(f)
            valid, reason = plugin_manager.validate_manifest(manifest, name)
            self.assertTrue(valid, f"{name}: {reason}")

    def test_discovery_does_not_import_connector(self):
        with tempfile.TemporaryDirectory() as builtin, tempfile.TemporaryDirectory() as user:
            marker = os.path.join(user, "imported.txt")
            _write_plugin(
                user,
                "untrusted_demo",
                _manifest("untrusted_demo"),
                f"open({marker!r}, 'w').write('imported')\n",
            )
            with patch.object(plugin_manager, "builtin_plugins_dir", return_value=builtin), \
                 patch.object(plugin_manager, "user_plugins_dir", return_value=user):
                discovered = plugin_manager.discover_plugins(force=True)
            self.assertEqual([name for name, _ in discovered], ["untrusted_demo"])
            self.assertFalse(os.path.exists(marker))
            self.assertFalse(plugin_manager.is_plugin_approved("untrusted_demo"))

    def test_unapproved_plugin_cannot_load(self):
        with patch.object(plugin_manager, "is_plugin_approved", return_value=False), \
             patch.object(plugin_manager.importlib, "import_module") as importer:
            self.assertIsNone(plugin_manager.load_plugin("untrusted_demo", {}))
            importer.assert_not_called()

    def test_user_plugin_requires_matching_explicit_approval(self):
        with tempfile.TemporaryDirectory() as builtin, tempfile.TemporaryDirectory() as user:
            _write_plugin(user, "untrusted_demo", _manifest("untrusted_demo"))
            with patch.object(plugin_manager, "builtin_plugins_dir", return_value=builtin), \
                 patch.object(plugin_manager, "user_plugins_dir", return_value=user):
                plugin_manager.discover_plugins(force=True)
                self.assertFalse(plugin_manager.is_plugin_approved("untrusted_demo"))
                with patch("config.save_config"):
                    self.assertTrue(plugin_manager.set_plugin_approval("untrusted_demo", True))
                self.assertTrue(plugin_manager.is_plugin_approved("untrusted_demo"))

    def test_bundled_user_collision_keeps_bundled_candidate(self):
        with tempfile.TemporaryDirectory() as builtin, tempfile.TemporaryDirectory() as user:
            _write_plugin(builtin, "collision_demo", _manifest("collision_demo"))
            _write_plugin(user, "collision_demo", _manifest("collision_demo"))
            with patch.object(plugin_manager, "builtin_plugins_dir", return_value=builtin), \
                 patch.object(plugin_manager, "user_plugins_dir", return_value=user):
                discovered = plugin_manager.discover_plugins(force=True)
            self.assertEqual([name for name, _ in discovered], ["collision_demo"])
            provenance = plugin_manager.get_plugin_provenance("collision_demo")
            self.assertTrue(provenance["collision"])
            self.assertEqual(provenance["source"], "builtin")
            self.assertTrue(plugin_manager.is_plugin_approved("collision_demo"))
            self.assertTrue(provenance["path"].startswith(builtin))
            self.assertEqual({candidate["source"] for candidate in provenance["candidates"]}, {"builtin", "user"})

    def test_user_plugin_named_like_builtin_is_not_trusted_when_separate(self):
        with tempfile.TemporaryDirectory() as builtin, tempfile.TemporaryDirectory() as user:
            _write_plugin(user, "ha", _manifest("ha"))
            with patch.object(plugin_manager, "builtin_plugins_dir", return_value=builtin), \
                 patch.object(plugin_manager, "user_plugins_dir", return_value=user):
                plugin_manager.discover_plugins(force=True)
            self.assertEqual(plugin_manager.get_plugin_provenance("ha")["source"], "user")
            self.assertFalse(plugin_manager.is_plugin_approved("ha"))

    def test_invalid_manifest_is_not_discovered(self):
        with tempfile.TemporaryDirectory() as builtin, tempfile.TemporaryDirectory() as user:
            bad = _manifest("invalid_demo")
            bad["capabilities"] = {"status": "yes"}
            _write_plugin(user, "invalid_demo", bad)
            with patch.object(plugin_manager, "builtin_plugins_dir", return_value=builtin), \
                 patch.object(plugin_manager, "user_plugins_dir", return_value=user):
                discovered = plugin_manager.discover_plugins(force=True)
            self.assertEqual(discovered, [])
            provenance = plugin_manager.get_plugin_provenance("invalid_demo")
            self.assertFalse(provenance["valid"])


if __name__ == "__main__":
    unittest.main()
