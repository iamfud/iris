"""OpenRGB SDK connector.

Connects directly to the OpenRGB SDK server via TCP and delegates
all profile switching and color management to OpenRGB.
"""

import json
import logging
import os
import socket
import threading
import time
from typing import List, Dict, Any, Optional

from connector_base import BaseConnector

log = logging.getLogger("iris.plugins.openrgb.connector")


class OpenRGBConnector(BaseConnector):

    # ── Lifecycle ────────────────────────────────────────────────

    def __init__(self):
        self._client = None
        self._sdk_version = None
        self._device_count = 0
        self._active_profile = None
        self._has_effects_plugin = False
        self._lock = threading.Lock()
        self._running = False

    def _get_configured_port(self) -> int:
        """Read configured port from OpenRGB.json if available, default to 6742."""
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            cfg_path = os.path.join(base, "OpenRGB", "OpenRGB.json")
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        p_str = d.get("AutoStart", {}).get("port")
                        if p_str:
                            return int(p_str)
                except Exception:
                    pass
        return 6742

    def connect(self) -> bool:
        with self._lock:
            if self._client is not None:
                return True

            ports_to_try = [self._get_configured_port()]
            for fallback in (6742, 6749):
                if fallback not in ports_to_try:
                    ports_to_try.append(fallback)

            for p in ports_to_try:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.05)
                    ok = (s.connect_ex(("127.0.0.1", p)) == 0)
                    s.close()
                    if not ok:
                        continue

                    from openrgb import OpenRGBClient
                    log.info(f"[openrgb] Connecting to OpenRGB SDK server at 127.0.0.1:{p}...")
                    cli = OpenRGBClient(port=p, name="Iris")
                    cli.update()
                    try:
                        if hasattr(cli, "update_profiles"):
                            cli.update_profiles()
                    except Exception:
                        pass

                    self._client = cli
                    raw_ver = getattr(cli, "protocol_version", None)
                    self._sdk_version = f"v{raw_ver}" if raw_ver is not None else "v4"
                    self._device_count = len(cli.devices) if hasattr(cli, "devices") else 0

                    try:
                        if hasattr(cli, "update_plugins"):
                            cli.update_plugins()
                        plugins = getattr(cli, "plugins", [])
                        self._has_effects_plugin = any("effect" in getattr(pl, "name", "").lower() for pl in plugins)
                    except Exception:
                        pass

                    log.info(f"[openrgb] Connected! Version: {self._sdk_version}, Devices: {self._device_count}")
                    return True
                except Exception as e:
                    log.debug(f"[openrgb] Connect port {p} failed: {e}")

            log.info("[openrgb] OpenRGB SDK server is not listening (Start Server in OpenRGB > SDK Server tab)")
            return False

    def disconnect(self):
        with self._lock:
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._sdk_version = None
            self._device_count = 0
            self._active_profile = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def get_sdk_info(self) -> Dict[str, Any]:
        """Return SDK version and device count for status display."""
        if not self._client:
            self.connect()
        return {
            "sdk_version": self._sdk_version or "Offline",
            "device_count": self._device_count,
            "has_effects_plugin": self._has_effects_plugin or bool(self._find_effect_profiles()),
        }

    # ── Control definitions ──────────────────────────────────────

    @classmethod
    def controls(cls) -> list:
        return [
            {
                "id": "profile",
                "type": "select",
                "label": "Profile",
                "options_key": "openrgb_profiles",
            },
            {
                "id": "color",
                "type": "color",
                "label": "Set Color",
            },
        ]

    @classmethod
    def get_settings(cls) -> list:
        return [
            {
                "title": "Connection",
                "controls": [
                    {
                        "type": "button",
                        "id": "openrgb_refresh",
                        "label": "Refresh Profiles",
                        "icon": "refresh",
                        "action": "refresh_profiles",
                    },
                    {
                        "type": "button",
                        "id": "openrgb_reconnect",
                        "label": "Reconnect",
                        "icon": "link",
                        "action": "reconnect",
                    },
                ],
            }
        ]

    # ── Actions ──────────────────────────────────────────────────

    def handle(self, control_id: str, value=None):
        if control_id == "profile":
            self._apply_profile(value)
        elif control_id == "color":
            self._set_color(value)

    # ── Dynamic options ──────────────────────────────────────────

    def get_options(self, option_key: str) -> list:
        if option_key in ("profiles", "openrgb_profiles"):
            return self._list_profiles()
        return []

    # ── Internal: Profiles Discovery ─────────────────────────────

    def _find_effect_profiles(self) -> List[str]:
        """Discover effect profiles created by the OpenRGB Effects Plugin."""
        effect_names = set()
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            eff_dir = os.path.join(base, "OpenRGB", "plugins", "settings", "effect-profiles")
            if os.path.isdir(eff_dir):
                try:
                    for f in os.listdir(eff_dir):
                        fp = os.path.join(eff_dir, f)
                        if os.path.isfile(fp):
                            effect_names.add(f)
                except Exception:
                    pass
        return sorted(list(effect_names))

    def _list_profiles(self) -> List[str]:
        """Return merged list of Device Profiles and Effect Profiles."""
        device_profiles = []
        if not self._client:
            self.connect()

        if self._client and hasattr(self._client, "profiles"):
            try:
                self._client.update_profiles()
                device_profiles = [p.name for p in self._client.profiles]
            except Exception:
                pass

        if not device_profiles:
            for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
                if not base:
                    continue
                p_dir = os.path.join(base, "OpenRGB")
                if os.path.isdir(p_dir):
                    import glob
                    files = glob.glob(os.path.join(p_dir, "*.orp"))
                    device_profiles = sorted([os.path.splitext(os.path.basename(f))[0] for f in files])
                    if device_profiles:
                        break

        effect_profiles = self._find_effect_profiles()
        merged = []
        dev_set = set(device_profiles)
        eff_set = set(effect_profiles)

        for dp in device_profiles:
            if dp in eff_set:
                merged.append(f"{dp} (Device)")
            else:
                merged.append(dp)

        for ep in effect_profiles:
            if ep in dev_set:
                merged.append(f"{ep} (Effect)")
            else:
                merged.append(f"{ep} (Effect)" if any(" (Device)" in m for m in merged) else ep)

        if not merged:
            merged = device_profiles or effect_profiles or []

        return sorted(list(set(merged)))

    # ── Internal: Profile Application ────────────────────────────

    def _apply_profile(self, name: str):
        """Instruct OpenRGB to apply the profile over the SDK socket (instantaneous)."""
        if not name:
            return

        clean_name = name.replace(" (Device)", "").replace(" (Effect)", "").strip()
        log.info(f"[openrgb] Switching to profile '{clean_name}'")
        self._active_profile = name

        if not self._client:
            self.connect()

        if not self._client:
            log.warning(f"[openrgb] Cannot apply '{clean_name}': OpenRGB SDK server is not connected. Please click 'Start Server' in OpenRGB.")
            return

        try:
            try:
                from openrgb.utils import Profile
                self._client.load_profile(Profile(clean_name))
            except Exception:
                self._client.load_profile(clean_name)
            log.info(f"[openrgb] Profile '{clean_name}' successfully loaded in OpenRGB")
        except Exception as e:
            log.warning(f"[openrgb] Failed to load profile '{clean_name}': {e}")

    # ── Internal: Direct Color ───────────────────────────────────

    def _set_color(self, value):
        c = value.lstrip("#")
        if len(c) != 6:
            return
        try:
            r = int(c[0:2], 16)
            g = int(c[2:4], 16)
            b = int(c[4:6], 16)
        except ValueError:
            return

        if not self._client:
            self.connect()

        if self._client is not None:
            try:
                from openrgb.utils import RGBColor
                self._client.set_color(RGBColor(red=r, green=g, blue=b))
                log.info("colour #%02x%02x%02x applied via OpenRGB SDK", r, g, b)
            except Exception as e:
                log.warning("set_color failed: %s", e)



