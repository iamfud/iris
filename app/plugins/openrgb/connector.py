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
        self._lock = threading.RLock()
        self._running = False

    def _get_configured_port(self) -> int:
        """Return the OpenRGB SDK server port, defaulting to 6742.

        OpenRGB.json stores the target under AutoStart.client as "host:port"
        (e.g. "localhost:6742"). The AutoStart.port field is a separate GUI
        auto-launch field that does NOT reliably hold the SDK server port
        (it has been seen carrying 6749 while client correctly says 6742), so
        we only trust AutoStart.client's port, and otherwise default to 6742.
        """
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

            ports_to_try = [self._get_configured_port()]
            # The OpenRGB SDK server always runs on the default port 6742. Never
            # fall back to 6749: that value appears in an unrelated OpenRGB.json
            # AutoStart field and a server on it would be a different instance.
            if 6742 not in ports_to_try:
                ports_to_try.append(6742)

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

    def is_alive(self) -> bool:
        """Verify that the underlying TCP socket is still connected to the server."""
        if self._client is None:
            return False
        try:
            sock = getattr(getattr(self._client, "comms", None), "sock", None)
            if not sock or sock.fileno() == -1:
                self.disconnect()
                return False
            import select
            r, _, _ = select.select([sock], [], [], 0)
            if r:
                # Socket is readable; peek to check if it's EOF (server closed)
                peek = sock.recv(1, socket.MSG_PEEK)
                if not peek:
                    self.disconnect()
                    return False
            return True
        except Exception:
            self.disconnect()
            return False

    @property
    def available(self) -> bool:
        if self._client is None:
            return False
        return self.is_alive()

    def get_sdk_info(self) -> Dict[str, Any]:
        """Return SDK version and device count for status display."""
        if not self.available:
            self.connect()
        if not self.available:
            return {
                "sdk_version": "Offline",
                "device_count": 0,
                "has_effects_plugin": bool(self._find_effect_profiles()),
            }
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

    def _load_local_profile_resilient(self, name: str) -> bool:
        """Load profile from local .orp file, slicing or padding colors to match live device LED counts."""
        import openrgb.utils
        found_path = None
        for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            p = os.path.join(base, "OpenRGB", f"{name}.orp")
            if os.path.isfile(p):
                found_path = p
                break
        if not found_path:
            return False

        with open(found_path, "rb") as f:
            controllers = openrgb.utils.LocalProfile.unpack(f).controllers

        pairs = []
        for device in self._client.devices:
            for nc in controllers:
                if (nc.name == device.name
                        and nc.device_type == device.type
                        and nc.metadata.description == device.metadata.description):
                    controllers.remove(nc)
                    pairs.append((nc, device))
                    break

        if not pairs:
            return False

        for nc, device in pairs:
            colors = nc.colors
            n_leds = len(device.leds)
            if len(colors) > n_leds:
                colors = colors[:n_leds]
            elif len(colors) < n_leds:
                pad = colors[-1] if colors else openrgb.utils.RGBColor(0, 0, 0)
                colors = colors + [pad] * (n_leds - len(colors))
            try:
                device.set_colors(colors, fast=True)
                if nc.active_mode != device.active_mode:
                    try:
                        device.set_mode(nc.active_mode)
                    except Exception:
                        pass
            except Exception as ex:
                log.warning(f"[openrgb] Failed to set colors on '{device.name}': {ex}")

        return True

    def _apply_profile(self, name: str):
        """Instruct OpenRGB to apply the profile over the SDK socket (instantaneous)."""
        if not name:
            return

        clean_name = name.replace(" (Device)", "").replace(" (Effect)", "").strip()
        log.info(f"[openrgb] Switching to profile '{clean_name}'")
        self._active_profile = name

        with self._lock:
            if not self._client:
                self.connect()

            if not self._client:
                log.warning(f"[openrgb] Cannot apply '{clean_name}': OpenRGB SDK server is not connected. Please click 'Start Server' in OpenRGB.")
                return

            try:
                applied = False
                try:
                    applied = self._load_local_profile_resilient(clean_name)
                except Exception as ex:
                    log.debug(f"[openrgb] Resilient local load error for '{clean_name}': {ex}")

                if not applied:
                    try:
                        self._client.load_profile(clean_name, local=True)
                        applied = True
                    except Exception:
                        try:
                            from openrgb.utils import Profile
                            self._client.load_profile(Profile(clean_name))
                            applied = True
                        except Exception:
                            self._client.load_profile(clean_name)
                            applied = True

                try:
                    self._client.show()
                except Exception as e:
                    log.warning(f"[openrgb] show() failed after loading '{clean_name}': {e}")
                if applied:
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

        with self._lock:
            if not self._client:
                self.connect()
    
            if self._client is not None:
                try:
                    from openrgb.utils import RGBColor, ModeColors
                    target_color = RGBColor(red=r, green=g, blue=b)
                    devices = getattr(self._client, "devices", []) or []
                    for device in devices:
                        try:
                            # If device mode doesn't accept color, switch to Direct or Static
                            if hasattr(device, "modes") and hasattr(device, "active_mode"):
                                active_m = device.modes[device.active_mode]
                                if getattr(active_m, "color_mode", None) not in (ModeColors.PER_LED, ModeColors.MODE_SPECIFIC):
                                    direct_mode = next((m for m in device.modes if m.name.lower() in ("direct", "static", "custom")), None)
                                    if direct_mode:
                                        device.set_mode(direct_mode)
                            device.set_color(target_color)
                        except Exception as dev_err:
                            log.debug("device %s set_color error: %s", getattr(device, "name", "?"), dev_err)
                    try:
                        self._client.show()
                    except Exception:
                        pass
                    log.info("colour #%02x%02x%02x applied via OpenRGB SDK", r, g, b)
                except Exception as e:
                    log.warning("set_color failed: %s", e)



