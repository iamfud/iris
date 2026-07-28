"""OpenRGB SDK connector.

Connects to the OpenRGB SDK server via TCP and exposes
profile/color operations through the generic ``BaseConnector``
interface.
"""

import glob
import logging
import os

from connector_base import BaseConnector

log = logging.getLogger("iris.plugins.openrgb.connector")


class OpenRGBConnector(BaseConnector):

    # ── Lifecycle ────────────────────────────────────────────────

    def __init__(self):
        self._client = None

    def connect(self) -> bool:
        try:
            from openrgb import OpenRGBClient
            self._client = OpenRGBClient()
            log.info("connected to OpenRGB SDK")
            return True
        except ImportError:
            log.warning("openrgb-python not installed")
        except ConnectionRefusedError:
            log.warning("OpenRGB SDK server not running")
        except Exception as e:
            log.warning("OpenRGB connect failed: %s", e)
        return False

    def disconnect(self):
        self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    # ── Control definitions ──────────────────────────────────────

    @classmethod
    def controls(cls) -> list:
        return [
            {
                "id": "profile",
                "type": "select",
                "label": "Profile",
                "options_key": "profiles",
            },
            {
                "id": "color",
                "type": "color",
                "label": "Set Color",
            },
        ]

    # ── Actions ──────────────────────────────────────────────────

    def handle(self, control_id: str, value=None):
        if control_id == "profile":
            self._apply_profile(value)
        elif control_id == "color":
            self._set_color(value)

    # ── Dynamic options ──────────────────────────────────────────

    def get_options(self, option_key: str) -> list:
        if option_key == "profiles":
            return self._list_profiles()
        return []

    # ── Internal: profiles ───────────────────────────────────────

    def _profiles_dir(self):
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            d = os.path.join(base, "OpenRGB", "profiles")
            if os.path.isdir(d):
                return d
            d = os.path.join(base, "OpenRGB")
            if os.path.isdir(d):
                return d
        return None

    def _list_profiles(self):
        d = self._profiles_dir()
        if not d:
            return []
        files = glob.glob(os.path.join(d, "*.orp"))
        return sorted(os.path.splitext(os.path.basename(p))[0] for p in files)

    def _apply_profile(self, name):
        d = self._profiles_dir()
        if not d:
            return
        path = os.path.join(d, name + ".orp")
        if not os.path.isfile(path):
            log.warning("profile not found: %s", path)
            return
        try:
            from openrgb.utils import LocalProfile
            with open(path, "rb") as f:
                profile = LocalProfile.unpack(f)
        except Exception as e:
            log.warning("failed to parse profile %s: %s", name, e)
            return
        if self._client is None:
            return
        profile_controllers = list(profile.controllers)
        applied = 0
        used = set()
        for device in self._client.devices:
            match = None
            for i, ctrl in enumerate(profile_controllers):
                if i in used:
                    continue
                if ctrl.name == device.name:
                    match = ctrl
                    used.add(i)
                    break
            if match is None:
                continue
            try:
                pmode = match.modes[match.active_mode].name
                live = next((m for m in device.modes if m.name == pmode), None)
                if live is not None:
                    device.set_mode(live)
                if match.colors:
                    colors = match.colors
                    lc = len(device.leds)
                    if len(colors) != lc:
                        colors = (colors * (lc // len(colors) + 1))[:lc]
                    device.set_colors(colors)
                applied += 1
            except Exception as e:
                log.warning("%s: %s", device.name, e)
        log.info("applied \"%s\" to %d/%d device(s)", name, applied, len(self._client.devices))

    # ── Internal: direct color ───────────────────────────────────

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
        if self._client is None:
            return
        try:
            from openrgb.utils import RGBColor
            self._client.set_color(RGBColor(red=r, green=g, blue=b))
            log.info("colour #%02x%02x%02x applied", r, g, b)
        except Exception as e:
            log.warning("set_color failed: %s", e)
