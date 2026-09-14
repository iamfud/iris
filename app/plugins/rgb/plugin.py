"""RGB & LCD umbrella plugin for Iris.

Unifies OpenRGB lighting management and AIO LCD hardware integrations (NZXT Kraken,
Ajazz) under a single, decoupled plugin adapter.
"""

import logging
from typing import Any, Dict, List, Optional

from plugins.rgb.connector import RGBConnector
from plugins.rgb.detect import probe_kraken_usb

log = logging.getLogger("iris.plugins.rgb")


class Plugin:
    name = "rgb"
    display_name = "RGB & LCD Hardware"

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, serial_sender=None, overlays=None):
        self._cfg = cfg or {}
        self._connector = RGBConnector()
        self.overlays = overlays
        self.serial_sender = serial_sender
        self._last_connect_attempt = 0.0

    def start(self):
        """Start the plugin connections."""
        self._connector.connect()

    def stop(self):
        """Disconnect and release resources."""
        self._connector.disconnect()

    def is_connected(self) -> bool:
        """Return True if OpenRGB SDK or any hardware device (e.g. Kraken) is reachable."""
        if self._connector and self._connector.available:
            return True
        kraken = self.get_kraken_status()
        if kraken and kraken.get("found"):
            return True
        return False

    def get_kraken_status(self) -> Dict[str, Any]:
        """Return cached NZXT Kraken USB probe results."""
        plugins_cfg = self._cfg.get("plugins", {}) if isinstance(self._cfg, dict) else {}
        rgb_cfg = plugins_cfg.get("rgb", {}) if isinstance(plugins_cfg, dict) else {}
        if rgb_cfg.get("kraken_enabled", True) is False:
            return {"found": False}
        return probe_kraken_usb()

    # ── Lighting Provider API ──────────────────────────────────────

    def get_lighting_presets(self) -> List[Dict[str, str]]:
        """Return available OpenRGB profiles as standardized lighting presets."""
        presets = [{"id": "__theme__", "name": "Sync Active Theme (Neon 1)"}]
        profs = self._connector.get_options("profiles") or []
        presets.extend([{"id": p, "name": p} for p in profs])
        return presets

    def apply_lighting_preset(self, preset_id: str, is_alert: bool = False):
        """Apply an OpenRGB profile or color."""
        if not preset_id:
            return
        if not is_alert:
            try:
                from lighting_service import get_lighting_service
                if get_lighting_service().is_alert_active():
                    log.info("[rgb] critical alert active -> ignoring non-alert preset '%s'", preset_id)
                    return
            except Exception:
                pass

        if preset_id == "__theme__":
            cfg = self._cfg or {}
            try:
                from lighting_service import get_lighting_service
                ls_cfg = get_lighting_service()._cfg
                if ls_cfg and isinstance(ls_cfg, dict) and "theme" in ls_cfg:
                    cfg = ls_cfg
            except Exception:
                pass

            theme = cfg.get("theme") or {}
            mode = theme.get("mode", "iris") if isinstance(theme, dict) else "iris"
            if mode == "monochrome":
                neon = "#FFFFFF"
                accent = "#888888"
            elif mode == "custom":
                neon = theme.get("neon") or "#48B2E9"
                accent = theme.get("accent") or "#B23AF6"
            else:  # "iris" (default)
                neon = "#48B2E9"
                accent = "#B23AF6"

            def _lum(h):
                try:
                    h = h.lstrip("#")
                    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                except Exception:
                    return 0.0

            color = neon if _lum(neon) >= _lum(accent) else accent
            self._connector._set_color(color)
        elif preset_id.startswith("#"):
            self._connector._set_color(preset_id)
        else:
            self._connector._apply_profile(preset_id)

    # ── Action & Tap Handling ─────────────────────────────────────

    def on_action(self, action_id: str, value: Any = None) -> bool:
        """Generic action trigger for profile switching, refresh, or reconnect."""
        if action_id in ("set_profile", "profile"):
            if value:
                return self._connector._apply_profile(str(value))
            return False
        elif action_id in ("set_color", "color"):
            if value:
                self._connector._set_color(str(value))
                return True
            return False
        elif action_id == "refresh_profiles":
            self._connector._list_profiles()
            return True
        elif action_id == "reconnect":
            self._connector.disconnect()
            return self._connector.connect()
        return False

    def on_tap(self, control_id: str, value: Any = None) -> bool:
        self._connector.handle(control_id, value)
        return True

    def on_button(self, button_id: str, slot_data: Optional[Dict[str, Any]] = None) -> bool:
        slot = slot_data or {}
        prof = slot.get("openrgb_profile") or slot.get("profile") or slot.get("value")
        if not prof:
            ent = str(slot.get("entity") or "")
            if ent.startswith("openrgb.profile."):
                prof = ent[len("openrgb.profile."):]
            elif ent.startswith("rgb.profile."):
                prof = ent[len("rgb.profile."):]
        if prof:
            return self._connector._apply_profile(prof)
        return False

    def get_options(self, option_key: str) -> List[str]:
        return self._connector.get_options(option_key)

    # ── Telemetry & Polling ───────────────────────────────────────

    def poll(self) -> Dict[str, Any]:
        """Return flat telemetry and structured metadata for Iris entity bus."""
        import time
        now = time.time()
        if not self._connector.available and (now - self._last_connect_attempt > 5.0):
            self._last_connect_attempt = now
            self._connector.connect()

        sdk_info = self._connector.get_sdk_info()
        profiles = self._connector.get_options("profiles")
        kraken = self.get_kraken_status()

        raw_sdk_ver = sdk_info.get("sdk_version")
        sdk_ver = str(raw_sdk_ver) if raw_sdk_ver else "—"
        dev_count = sdk_info.get("device_count", 0)
        active_profile = self._connector._active_profile or (profiles[0] if profiles else "—")
        is_avail = self.is_connected()

        data = {
            "available": is_avail,
            "openrgb_available": self._connector.available,
            "sdk_version": sdk_ver,
            "device_count": dev_count,
            "profiles": profiles,
            "active_profile": active_profile,
            "kraken_found": kraken.get("found", False),
            "kraken_model": kraken.get("model", ""),
            "kraken_resolution": kraken.get("resolution", 0),
            "kraken_shape": kraken.get("shape", ""),
            "state": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
                "active_profile": active_profile,
                "kraken_found": kraken.get("found", False),
                "kraken_model": kraken.get("model", ""),
            },
            "status": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
                "kraken_found": kraken.get("found", False),
            },
            "layout": [
                {
                    "title": "OpenRGB SDK",
                    "fields": [
                        {"key": "sdk_version", "label": "SDK Version", "source": "status"},
                        {"key": "device_count", "label": "Devices", "source": "status", "type": "integer"},
                        {"key": "active_profile", "label": "Active Profile", "source": "state"},
                    ],
                },
                {
                    "title": "AIO LCD Display",
                    "fields": [
                        {"key": "kraken_model", "label": "Detected AIO", "source": "state"},
                        {"key": "kraken_resolution", "label": "Resolution", "source": "state"},
                    ],
                },
            ],
        }

        if self._connector.available and self._connector._client:
            try:
                devices = self._connector._client.devices
                data["device_count"] = len(devices)
                data["devices"] = []
                for d in devices:
                    mode_name = "unknown"
                    if hasattr(d, "active_mode") and d.modes:
                        try:
                            mode_name = d.modes[d.active_mode].name
                        except Exception:
                            pass
                    device_data = {
                        "name": d.name,
                        "type": str(d.type),
                        "mode": mode_name,
                        "led_count": len(d.leds),
                    }
                    data["devices"].append(device_data)
            except Exception as e:
                log.debug("[rgb] poll device enumeration failed: %s", e)

        return data

    def snapshot(self) -> Dict[str, Any]:
        """Return full snapshot for settings page."""
        return self.poll()
