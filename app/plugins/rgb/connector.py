"""OpenRGB SDK connector for the unified RGB plugin.

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

log = logging.getLogger("iris.plugins.rgb.connector")


class RGBConnector(BaseConnector):

    # ── Lifecycle ────────────────────────────────────────────────

    def __init__(self):
        self._client = None
        self._sdk_version = None
        self._device_count = 0
        self._active_profile = None
        self._has_effects_plugin = False
        self._lock = threading.RLock()
        self._running = False

    def _get_configured_port(self) -> int:
        """Return the OpenRGB SDK server port, defaulting to 6742."""
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            cfg_path = os.path.join(base, "OpenRGB", "OpenRGB.json")
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    client = (d.get("AutoStart") or {}).get("client") or ""
                    if ":" in client:
                        try:
                            return int(client.rsplit(":", 1)[1])
                        except ValueError:
                            pass
                except Exception:
                    pass
        return 6742

    def connect(self) -> bool:
        with self._lock:
            if self._client is not None:
                return True
            try:
                from openrgb import OpenRGBClient
            except ImportError:
                log.warning("[rgb] openrgb-python library not installed")
                return False

            port = self._get_configured_port()
            try:
                # Fast pre-check: verify port is actually listening before instantiating OpenRGBClient
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                err = s.connect_ex(("127.0.0.1", port))
                s.close()
                if err != 0:
                    log.debug("[rgb] OpenRGB SDK server not listening on port %d", port)
                    self._client = None
                    return False
            except Exception:
                pass

            try:
                self._client = OpenRGBClient(
                    name="Iris",
                    port=port,
                    protocol_version=4,
                )
                self._sdk_version = getattr(self._client, "protocol_version", "4")
                self._device_count = len(self._client.devices)
                self._has_effects_plugin = self._detect_effects_plugin()
                self._running = True
                log.info(
                    "[rgb] connected to OpenRGB SDK on port %d (%d devices, effects=%s)",
                    port,
                    self._device_count,
                    self._has_effects_plugin,
                )
                return True
            except ConnectionRefusedError:
                log.debug("[rgb] OpenRGB SDK server not running on port %d", port)
                self._client = None
                return False
            except Exception as e:
                log.warning("[rgb] connection failed: %s", e)
                self._client = None
                return False

    def disconnect(self):
        with self._lock:
            self._running = False
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
                self._client = None
                log.info("[rgb] disconnected")

    @property
    def available(self) -> bool:
        return self._client is not None

    def _detect_effects_plugin(self) -> bool:
        try:
            from openrgb.utils import RGBColor
            client = self._client
            if client is None:
                return False
            for dev in client.devices:
                for mode in getattr(dev, "modes", []):
                    if "effect" in mode.name.lower():
                        return True
        except Exception:
            pass
        return False

    # ── Options Provider ─────────────────────────────────────────

    def get_options(self, option_key: str) -> List[str]:
        if option_key in ("openrgb_profiles", "profiles"):
            return self._list_profiles()
        return []

    def _list_profiles(self) -> List[str]:
        with self._lock:
            if self._client is None:
                return self._list_profile_files()
            try:
                server_profiles = [p.name for p in self._client.profiles]
                if server_profiles:
                    return server_profiles
            except Exception as e:
                log.debug("[rgb] client.profiles failed: %s", e)
            return self._list_profile_files()

    @staticmethod
    def _list_profile_files() -> List[str]:
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            for sub in ("OpenRGB/profiles", "OpenRGB"):
                d = os.path.join(base, sub)
                if os.path.isdir(d):
                    files = [
                        os.path.splitext(f)[0]
                        for f in os.listdir(d)
                        if f.lower().endswith(".orp")
                    ]
                    if files:
                        return sorted(files)
        return []

    # ── Action Dispatch ──────────────────────────────────────────

    def handle(self, control_id: str, value: Any = None):
        if control_id == "profile" and value:
            self._apply_profile(str(value))
        elif control_id == "color" and value:
            self._set_color(str(value))
        elif control_id == "refresh_profiles":
            self._list_profiles()

    def _apply_profile(self, profile_name: str) -> bool:
        with self._lock:
            if self._client is None:
                if not self.connect():
                    log.warning("[rgb] cannot apply profile %r — SDK not connected", profile_name)
                    return False
            clean_name = profile_name.replace(" (Device)", "").replace(" (Effect)", "").strip()
            try:
                try:
                    self._client.load_profile(clean_name, local=True)
                except Exception:
                    try:
                        from openrgb.utils import Profile
                        self._client.load_profile(Profile(clean_name))
                    except Exception:
                        self._client.load_profile(clean_name)
                self._client.show()
                self._active_profile = clean_name
                log.info("[rgb] applied profile %r", clean_name)
                return True
            except Exception as e:
                log.warning("[rgb] failed to apply profile %r: %s", profile_name, e)
                return False

    def _set_color(self, hex_color: str):
        with self._lock:
            if self._client is None:
                if not self.connect():
                    return
            try:
                from openrgb.utils import RGBColor
                h = hex_color.lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                color = RGBColor(r, g, b)
                for dev in self._client.devices:
                    try:
                        dev.set_color(color)
                    except Exception:
                        pass
                self._client.show()
                log.info("[rgb] applied static color %s", hex_color)
            except Exception as e:
                log.warning("[rgb] failed to set color %s: %s", hex_color, e)

    def get_sdk_info(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sdk_version": self._sdk_version,
                "device_count": self._device_count,
                "has_effects": self._has_effects_plugin,
            }
