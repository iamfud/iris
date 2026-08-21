"""Home Assistant provider — REST shortcuts for lights/scenes."""

import logging
import requests
import pystray

log = logging.getLogger("iris.ha")


class HAProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self._shortcuts = cfg.get("ha_shortcuts", [])

    def start(self):
        pass

    def stop(self):
        pass

    def _call(self, entity_id):
        url = self.cfg.get("ha_url", "").rstrip("/")
        token = self.cfg.get("ha_token", "")
        if not url or not token:
            return
        domain = entity_id.split(".")[0]
        service_map = {
            "light": "toggle", "switch": "toggle",
            "script": "turn_on", "scene": "turn_on",
        }
        service = f"{domain}/{service_map.get(domain, 'toggle')}"
        try:
            requests.post(
                f"{url}/api/services/{service}",
                headers={"Authorization": f"Bearer {token}"},
                json={"entity_id": entity_id},
                timeout=5,
            )
        except Exception as e:
            log.warning(f"[ha] {entity_id} failed: {e}")

    def menu_items(self):
        if not self._shortcuts:
            return []
        sub_items = []
        for s in self._shortcuts:
            name = s.get("name") or s.get("entity_id", "?")
            entity = s.get("entity_id", "")
            icon = s.get("icon", "💡")
            label = f"{icon} {name}"
            sub_items.append(pystray.MenuItem(
                label, lambda e=entity: self._call(e)))
        return [pystray.MenuItem("💡 Lights", pystray.Menu(*sub_items))]
