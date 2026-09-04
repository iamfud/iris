"""OpenRGB plugin — thin orchestrator that delegates to the connector."""

import logging
from plugins.openrgb.connector import OpenRGBConnector

log = logging.getLogger("iris.plugins.openrgb")


class Plugin:
    name = "openrgb"
    display_name = "OpenRGB"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._connector = OpenRGBConnector()
        self.overlays = overlays

    def start(self):
        self._connector.connect()

    def stop(self):
        self._connector.disconnect()

    def is_connected(self) -> bool:
        return bool(self._connector and self._connector.available)

    def get_lighting_presets(self) -> list:
        """Return available OpenRGB profiles as standardized lighting presets."""
        presets = [{"id": "__theme__", "name": "Sync Active Theme (Neon 1)"}]
        profs = self._connector.get_options("openrgb_profiles") or []
        presets.extend([{"id": p, "name": p} for p in profs])
        return presets

    def apply_lighting_preset(self, preset_id: str):
        """Apply OpenRGB profile or color."""
        if not preset_id:
            return
        if preset_id == "__theme__":
            # Highest-luminance colour of the active theme (neon cyan vs accent
            # purple) — the "neon or neon 2 depending on luminance" choice.
            try:
                from desktop_theme import get_current_theme_colors
                color = get_current_theme_colors().get("bright_neon_hex") or "#48B2E9"
            except Exception:
                cfg = self._cfg or {}
                theme = cfg.get("theme") or {}
                color = theme.get("neon") or theme.get("accent") or "#48B2E9"
            self._connector._set_color(color)
        elif preset_id.startswith("#"):
            self._connector._set_color(preset_id)
        else:
            self._connector._apply_profile(preset_id)

    def on_tap(self, control_id, value=None):
        self._connector.handle(control_id, value)
        return True

    def on_button(self, button_id, slot_data=None):
        slot = slot_data or {}
        prof = slot.get("openrgb_profile")
        if not prof:
            ent = str(slot.get("entity") or "")
            if ent.startswith("openrgb.profile."):
                prof = ent[len("openrgb.profile."):]
        if prof:
            self._connector._apply_profile(prof)
            return True
        val = slot.get("value")
        if val:
            self._connector.handle(button_id, val)
            return True
        return False

    def get_options(self, option_key):
        return self._connector.get_options(option_key)

    def on_action(self, action_id):
        if action_id == "refresh_profiles":
            log.info("[openrgb] Profile refresh requested")
            return True
        elif action_id == "reconnect":
            self._connector.disconnect()
            return self._connector.connect()
        return False

    def poll(self):
        """Return standardized telemetry for Iris plugin system."""
        sdk_info = self._connector.get_sdk_info()
        profiles = self._connector.get_options("openrgb_profiles")
        
        raw_sdk_ver = sdk_info.get("sdk_version")
        if raw_sdk_ver:
            sdk_ver = str(raw_sdk_ver) if str(raw_sdk_ver).startswith("v") else f"v{raw_sdk_ver}"
        else:
            sdk_ver = "—"
            
        dev_count = sdk_info.get("device_count", 0)
        active_profile = self._connector._active_profile or (profiles[0] if profiles else "—")
        
        data = {
            "available": self._connector.available,
            "sdk_version": sdk_ver,
            "device_count": dev_count,
            "profiles": profiles,
            "active_profile": active_profile,
            "state": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
                "active_profile": active_profile,
            },
            "status": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
            },
            "layout": [
                {"title": "Connection", "fields": [
                    {"key": "sdk_version", "label": "SDK Version", "source": "status"},
                    {"key": "device_count", "label": "Devices", "source": "status", "type": "integer"},
                    {"key": "active_profile", "label": "Active Profile", "source": "state"},
                ]},
                {"title": "Profiles", "fields": [
                    {"key": "profiles", "label": "Available Profiles", "source": "state", "type": "list"},
                ]},
            ]
        }
        
        if self._connector.available and self._connector._client:
            try:
                devices = self._connector._client.devices
                data["device_count"] = len(devices)
                data["devices"] = []
                for d in devices:
                    mode_name = "unknown"
                    if hasattr(d, 'active_mode') and d.modes:
                        try:
                            mode_name = d.modes[d.active_mode].name
                        except Exception:
                            pass
                    
                    device_data = {
                        "name": d.name,
                        "type": str(d.type),
                        "mode": mode_name,
                        "led_count": len(d.leds),
                        "colors": [[c.red, c.green, c.blue] for c in d.colors] if hasattr(d, 'colors') and d.colors else [],
                    }
                    data["devices"].append(device_data)
            except Exception as e:
                log.debug(f"[openrgb] poll device enumeration failed: {e}")
        
        return data

    def snapshot(self):
        """Return full snapshot for settings page."""
        return self.poll()
