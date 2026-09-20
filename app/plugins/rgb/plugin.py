"""RGB & LCD umbrella plugin for Iris.

Unifies OpenRGB lighting management and AIO LCD hardware integrations (NZXT Kraken,
Ajazz AKP02) under a single, decoupled plugin adapter.
"""

import logging
from typing import Any, Dict, List, Optional

from plugins.rgb.connector import RGBConnector
from plugins.rgb.detect import probe_kraken_usb, probe_ajz_usb

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
        """Return True if OpenRGB SDK or any hardware display (Kraken, Ajazz AKP02) is reachable."""
        if self._connector and self._connector.available:
            return True
        kraken = self.get_kraken_status()
        if kraken and kraken.get("found"):
            return True
        ajz = self.get_ajz_status()
        if ajz and ajz.get("found"):
            return True
        return False

    def get_kraken_status(self) -> Dict[str, Any]:
        """Return cached NZXT Kraken USB probe results."""
        plugins_cfg = self._cfg.get("plugins", {}) if isinstance(self._cfg, dict) else {}
        rgb_cfg = plugins_cfg.get("rgb", {}) if isinstance(plugins_cfg, dict) else {}
        if rgb_cfg.get("kraken_enabled", True) is False:
            return {"found": False}
        return probe_kraken_usb()

    def get_ajz_status(self) -> Dict[str, Any]:
        """Return cached Ajazz AKP02 USB probe results and connection state."""
        plugins_cfg = self._cfg.get("plugins", {}) if isinstance(self._cfg, dict) else {}
        rgb_cfg = plugins_cfg.get("rgb", {}) if isinstance(plugins_cfg, dict) else {}
        if rgb_cfg.get("ajz_enabled", True) is False:
            return {"found": False}
        res = probe_ajz_usb()
        if res.get("found"):
            res["brightness"] = self.get_ajz_brightness()
        return res

    def get_ajz_brightness(self) -> int:
        """Return currently configured or active Ajazz LCD brightness (0-100%)."""
        try:
            import plugin_manager
            inst = plugin_manager.get("akp02_stats")
            if inst and hasattr(inst, "_current_brightness") and inst._current_brightness is not None:
                return int(inst._current_brightness)
        except Exception:
            pass
        plugins_cfg = self._cfg.get("plugins", {}) if isinstance(self._cfg, dict) else {}
        rgb_cfg = plugins_cfg.get("rgb", {}) if isinstance(plugins_cfg, dict) else {}
        return int(rgb_cfg.get("ajz_brightness", 80))

    def set_ajz_brightness(self, value: int) -> bool:
        """Set Ajazz LCD hardware backlight brightness (0-100%)."""
        val = max(0, min(100, int(value)))
        plugins_cfg = self._cfg.setdefault("plugins", {}) if isinstance(self._cfg, dict) else {}
        rgb_cfg = plugins_cfg.setdefault("rgb", {})
        rgb_cfg["ajz_brightness"] = val

        applied = False
        # 1. Forward to displays driver if available (preferred single exclusive driver)
        try:
            from displays.registry import get_driver
            driver = get_driver("akp02")
            if driver:
                applied = driver.set_brightness(val)
        except Exception as ex:
            log.debug("[rgb] dispatch set_brightness to akp02 driver error: %s", ex)

        # 2. Forward to active akp02_stats plugin instance
        if not applied:
            try:
                import plugin_manager
                inst = plugin_manager.get("akp02_stats")
                if inst and hasattr(inst, "set_brightness"):
                    applied = inst.set_brightness(val)
            except Exception as ex:
                log.debug("[rgb] dispatch set_brightness to akp02_stats error: %s", ex)

        return applied

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
        elif action_id in ("set_ajz_brightness", "ajz_brightness", "brightness", "set_brightness"):
            if value is not None:
                return self.set_ajz_brightness(int(value))
            return False
        elif action_id == "refresh_profiles":
            self._connector._list_profiles()
            return True
        elif action_id == "reconnect":
            self._connector.disconnect()
            return self._connector.connect()
        return False

    def on_config(self, cfg: Dict[str, Any]):
        """Invoked when plugin configuration is updated from Web Portal."""
        if isinstance(cfg, dict):
            if "ajz_brightness" in cfg:
                self.set_ajz_brightness(int(cfg["ajz_brightness"]))

    def on_tap(self, control_id: str, value: Any = None) -> bool:
        if control_id in ("ajz_brightness", "set_ajz_brightness"):
            if value is not None:
                return self.set_ajz_brightness(int(value))
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
        ajz = self.get_ajz_status()

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
            "ajz_found": ajz.get("found", False),
            "ajz_connected": ajz.get("found", False),
            "ajz_model": ajz.get("model", ""),
            "ajz_resolution": ajz.get("resolution", ""),
            "ajz_brightness": self.get_ajz_brightness(),
            "state": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
                "active_profile": active_profile,
                "kraken_found": kraken.get("found", False),
                "kraken_model": kraken.get("model", ""),
                "ajz_found": ajz.get("found", False),
                "ajz_connected": ajz.get("found", False),
                "ajz_model": ajz.get("model", ""),
                "ajz_brightness": self.get_ajz_brightness(),
            },
            "status": {
                "sdk_version": sdk_ver,
                "device_count": dev_count,
                "kraken_found": kraken.get("found", False),
                "ajz_connected": ajz.get("found", False),
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
                {
                    "title": "Ajazz LCD Display",
                    "fields": [
                        {"key": "ajz_model", "label": "Detected Screen", "source": "state"},
                        {"key": "ajz_brightness", "label": "Brightness", "source": "state"},
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
