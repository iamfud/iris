"""Home Assistant plugin — orchestrator delegating to HASSConnector."""

import logging
from plugins.ha.connector import HASSConnector

log = logging.getLogger("iris.plugins.ha")


class Plugin:
    name = "ha"
    display_name = "Home Assistant"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._connector = HASSConnector(cfg)
        self.overlays = overlays

    def start(self):
        self._connector.connect()

    def stop(self):
        self._connector.disconnect()

    def is_connected(self) -> bool:
        return bool(self._connector and self._connector.available)

    def get_lighting_presets(self) -> list:
        """Return available HA scripts and scenes as standardized lighting presets."""
        ents = self.get_entities() or []
        presets = []
        for e in ents:
            dom = e.get("domain", "")
            if dom in ("script", "scene"):
                presets.append({
                    "id": e["entity_id"],
                    "name": e.get("name") or e["entity_id"]
                })
        return presets

    def apply_lighting_preset(self, preset_id: str):
        """Execute HA script or scene."""
        if not preset_id:
            return
        clean_id = preset_id.replace("ha.", "") if preset_id.startswith("ha.") else preset_id
        dom = clean_id.split(".")[0] if "." in clean_id else "script"
        self._connector.call_service(dom, "turn_on", entity_id=clean_id)

    def get_entities(self) -> list:
        return self._connector.get_entities()

    def get_options(self, key: str) -> list:
        if key in ("ha_entities", "entities", "lights", "scenes"):
            return [e["entity_id"] for e in self._connector.get_entities()]
        return []

    def on_tap(self, control_id, value=None):
        if not control_id:
            return False
        # If control_id is an entity_id (e.g. light.kitchen_counter_lights_socket_1)
        if "." in str(control_id):
            domain = control_id.split(".")[0]
            service = "turn_on" if domain in ("scene", "script") else "toggle"
            return self._connector.call_service(domain, service, entity_id=control_id)
        return True

    def on_button(self, button_id, slot_data=None):
        slot = slot_data or {}
        ent_id = slot.get("entity_id") or button_id
        if not ent_id:
            ent = str(slot.get("entity") or "")
            if ent.startswith("ha."):
                ent_id = ent[len("ha."):]
        if ent_id and "." in ent_id:
            domain = ent_id.split(".")[0]
            service = "turn_on" if domain in ("scene", "script") else "toggle"
            return self._connector.call_service(domain, service, entity_id=ent_id)
        return False

    def on_action(self, action_id):
        if action_id == "discover":
            log.info("[ha] Running mDNS network discovery...")
            instances = self._connector.discover_instances(timeout_s=2.5)
            if instances:
                best = instances[0]
                best_url = best.get("url", "")
                if best_url:
                    ha_cfg = self._cfg.setdefault("plugins", {}).setdefault("ha", {})
                    ha_cfg["url"] = best_url
                    try:
                        from config import save_config
                        save_config(self._cfg)
                    except Exception:
                        pass
                    self._connector.connect()
                    log.info(f"[ha] Auto-selected discovered instance: {best_url}")
                    return True
        elif action_id == "reconnect":
            self._connector.disconnect()
            return self._connector.connect()
        return False

    def poll(self):
        info = self._connector.get_info()
        is_conn = info.get("connected", False)

        if not is_conn:
            ha_cfg = (self._cfg.get("plugins", {}).get("ha", {}) if isinstance(self._cfg, dict) else {})
            url = (ha_cfg.get("url") or self._cfg.get("ha_url") or "").strip()
            token = (ha_cfg.get("token") or self._cfg.get("ha_token") or "").strip()
            if url and token:
                if self._connector.connect():
                    info = self._connector.get_info()
                    is_conn = True

        ver = info.get("version", "Offline")
        loc = info.get("location_name", "—")
        url = info.get("url", "Not configured")

        return {
            "available": is_conn,
            "connected": is_conn,
            "url": url,
            "version": ver,
            "location_name": loc,
            "state": {
                "connected": is_conn,
                "url": url,
                "version": ver,
                "location_name": loc,
            },
            "status": {
                "version": ver,
                "location_name": loc,
            },
            "layout": [
                {
                    "title": "Connection",
                    "fields": [
                        {"key": "url", "label": "Server URL", "source": "state", "type": "string"},
                        {"key": "location_name", "label": "Instance", "source": "status", "type": "string"},
                        {"key": "version", "label": "HA Version", "source": "status", "type": "string"},
                        {"key": "connected", "label": "Connected", "source": "state", "type": "boolean"},
                    ]
                }
            ]
        }
