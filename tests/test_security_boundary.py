import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from server.auth import action_id_for_slot, resolve_mobile_action
from ws_bridge import _RequestHandler


class _RequestStub:
    def __init__(self, address):
        self.client_address = (address, 12345)

    _is_loopback_peer = _RequestHandler._is_loopback_peer
    _lan_api_allowed = _RequestHandler._lan_api_allowed
    _lan_asset_allowed = _RequestHandler._lan_asset_allowed


class SecurityBoundaryTests(unittest.TestCase):
    def test_lan_admin_routes_are_denied(self):
        req = _RequestStub("192.168.1.50")
        for method, path in (
            ("GET", "/api/config"),
            ("GET", "/api/settings/pages"),
            ("GET", "/api/plugins/config"),
            ("POST", "/api/plugins/elite_dangerous/action/import_binds"),
            ("POST", "/api/automations"),
            ("POST", "/api/automations/test"),
            ("POST", "/api/library/note"),
            ("POST", "/api/panel"),
            ("POST", "/api/open_url"),
        ):
            self.assertFalse(req._lan_api_allowed(method, path), (method, path))

    def test_lan_allowlist_contains_only_panel_and_safe_controls(self):
        req = _RequestStub("192.168.1.50")
        for method, path in (
            ("GET", "/api/panel"),
            ("GET", "/api/panel/live?cv=abc"),
            ("GET", "/api/status"),
            ("GET", "/api/volume"),
            ("GET", "/api/audio/devices"),
            ("POST", "/api/panel/action"),
            ("POST", "/api/volume"),
            ("POST", "/api/volume/master"),
            ("POST", "/api/volume/session"),
        ):
            self.assertTrue(req._lan_api_allowed(method, path), (method, path))

    def test_loopback_retains_admin_access(self):
        req = _RequestStub("127.0.0.1")
        self.assertTrue(req._lan_api_allowed("GET", "/api/config"))
        self.assertTrue(req._lan_api_allowed("POST", "/api/automations"))

        req6 = _RequestStub("::1")
        self.assertTrue(req6._lan_api_allowed("GET", "/api/settings/pages"))

    def test_spoofed_headers_do_not_change_peer_classification(self):
        req = _RequestStub("192.168.1.50")
        req.headers = {"X-Forwarded-For": "127.0.0.1", "Host": "localhost"}
        self.assertFalse(req._is_loopback_peer())
        self.assertFalse(req._lan_api_allowed("GET", "/api/config"))

    def test_lan_cannot_fetch_desktop_admin_assets(self):
        req = _RequestStub("192.168.1.50")
        for asset in ("index.html", "script.js", "settings_renderer.js"):
            self.assertFalse(req._lan_asset_allowed(asset), asset)
        for asset in ("deck.html", "deck.js", "style.css", "manifest.json", "theme.js"):
            self.assertTrue(req._lan_asset_allowed(asset), asset)

    def test_loopback_can_fetch_desktop_admin_assets(self):
        req = _RequestStub("127.0.0.1")
        for asset in ("index.html", "script.js", "settings_renderer.js", "deck.html"):
            self.assertTrue(req._lan_asset_allowed(asset), asset)

    def test_mobile_action_rejects_shortcut_plugin_and_hidden_profile_slots(self):
        shortcut = {"type": "SHORTCUT", "shortcut_path": "cmd.exe", "shortcut_args": "/c whoami"}
        plugin = {"type": "PLUGIN", "plugin": "elite_dangerous", "button_id": "import_binds"}
        hidden_profile = {"id": "hidden", "board": [shortcut]}
        cfg = {
            "panel_board": [],
            "panel_utility": [],
            "panel_core": [],
            "panel_profiles": [hidden_profile],
        }
        self.assertIsNone(resolve_mobile_action(action_id_for_slot(shortcut), cfg))
        self.assertIsNone(resolve_mobile_action(action_id_for_slot(plugin), cfg))

    def test_mobile_action_allows_explicit_safe_media_and_core(self):
        media = {"type": "MEDIA_PLAY"}
        core = {"type": "CORE", "core_action": "mic"}
        cfg = {"panel_board": [media], "panel_utility": [], "panel_core": [core], "panel_profiles": []}
        self.assertEqual(resolve_mobile_action(action_id_for_slot(media), cfg), media)
        self.assertEqual(resolve_mobile_action(action_id_for_slot(core), cfg), core)


if __name__ == "__main__":
    unittest.main()
