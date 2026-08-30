"""Home Assistant connector.

Connects to Home Assistant REST API for configuration and state,
and provides zero-dependency stdlib mDNS network discovery.
"""

import json
import logging
import socket
import threading
import time
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

from connector_base import BaseConnector

log = logging.getLogger("iris.plugins.ha.connector")


class HASSConnector(BaseConnector):

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self._cfg = cfg or {}
        self._connected = False
        self._version = None
        self._location_name = None
        self._entities: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._url = ""
        self._token = ""

    def _load_credentials(self):
        ha_cfg = (self._cfg.get("plugins", {}).get("ha", {}) if isinstance(self._cfg, dict) else {})
        url = (ha_cfg.get("url") or self._cfg.get("ha_url") or "").strip().rstrip("/")
        token = (ha_cfg.get("token") or self._cfg.get("ha_token") or "").strip()
        self._url = url
        self._token = token

    @property
    def available(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        with self._lock:
            self._load_credentials()
            if not self._url:
                log.debug("[ha] No server URL configured")
                self._connected = False
                return False

            api_url = f"{self._url}/api/config"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            } if self._token else {"Content-Type": "application/json"}

            req = urllib.request.Request(api_url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        self._connected = True
                        self._version = data.get("version", "Connected")
                        self._location_name = data.get("location_name", "Home")
                        log.info(f"[ha] Connected to Home Assistant ({self._location_name}, v{self._version})")
                        return True
            except Exception as e:
                log.debug(f"[ha] Connection test to {api_url} failed: {e}")
                self._connected = False
                self._version = None
                self._location_name = None

            return False

    def disconnect(self):
        with self._lock:
            self._connected = False
            self._version = None
            self._location_name = None

    def get_info(self) -> Dict[str, Any]:
        self._load_credentials()
        return {
            "connected": self._connected,
            "url": self._url or "Not configured",
            "version": self._version or ("Connected" if self._connected else "Offline"),
            "location_name": self._location_name or "—",
        }

    def discover_instances(self, timeout_s: float = 2.5) -> List[Dict[str, Any]]:
        results = []
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(0.5)

            query = bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            for part in ["_homeassistant", "_tcp", "local"]:
                b = part.encode("utf-8")
                query.append(len(b))
                query.extend(b)
            query.append(0x00)
            query.extend([0x00, 0x0C, 0x00, 0x01])

            multicast_addr = ("224.0.0.251", 5353)
            sock.sendto(query, multicast_addr)

            start = time.time()
            seen_ips = set()
            while (time.time() - start) < timeout_s:
                try:
                    data, addr = sock.recvfrom(4096)
                    ip = addr[0]
                    if ip not in seen_ips:
                        seen_ips.add(ip)
                        results.append({
                            "ip": ip,
                            "port": 8123,
                            "url": f"http://{ip}:8123",
                            "name": f"Home Assistant ({ip})",
                        })
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as ex:
            log.warning(f"[ha] mDNS discovery query failed: {ex}")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

        if not results:
            results.append({
                "ip": "homeassistant.local",
                "port": 8123,
                "url": "http://homeassistant.local:8123",
                "name": "Home Assistant (Default Hostname)",
            })

        return results

    def get_entities(self, cache_ttl: float = 60.0) -> List[Dict[str, Any]]:
        """Return user-relevant controllable entities (lights, switches, scenes, scripts, sun) with TTL caching."""
        with self._lock:
            now = time.time()
            if self._entities and (now - getattr(self, "_entities_ts", 0)) < cache_ttl:
                return list(self._entities)

            self._load_credentials()
            if not self._url:
                return []

            api_url = f"{self._url}/api/states"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            } if self._token else {"Content-Type": "application/json"}

            req = urllib.request.Request(api_url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        raw_states = json.loads(resp.read().decode("utf-8"))
                        allowed_domains = {"light", "switch", "scene", "script", "sun", "input_boolean", "climate"}
                        filtered = []
                        for s in raw_states:
                            eid = s.get("entity_id", "")
                            domain = eid.split(".")[0] if "." in eid else ""
                            # Keep OpenRGB separate: ignore any OpenRGB entities bridged into HA
                            attrs = s.get("attributes", {})
                            integration = attrs.get("integration") or ""
                            if "openrgb" in eid.lower() or "openrgb" in str(integration).lower():
                                continue
                            if domain in allowed_domains:
                                friendly_name = attrs.get("friendly_name") or eid
                                filtered.append({
                                    "entity_id": eid,
                                    "domain": domain,
                                    "friendly_name": friendly_name,
                                    "state": s.get("state"),
                                    "attributes": attrs,
                                })
                        self._entities = filtered
                        self._entities_ts = now
                        return list(filtered)
            except Exception as e:
                log.debug(f"[ha] Failed to fetch states: {e}")

            return list(self._entities)

    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the live state of a single entity."""
        self._load_credentials()
        if not self._url or not entity_id:
            return None
        api_url = f"{self._url}/api/states/{entity_id}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        } if self._token else {"Content-Type": "application/json"}
        req = urllib.request.Request(api_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            log.debug(f"[ha] Failed to fetch state for {entity_id}: {e}")
        return None

    def call_service(self, domain: str, service: str, data: Optional[Dict[str, Any]] = None, entity_id: str = "") -> bool:
        self._load_credentials()
        if not self._url:
            return False
        url = f"{self._url}/api/services/{domain}/{service}"
        payload = dict(data or {})
        if entity_id:
            payload["entity_id"] = entity_id

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            log.warning(f"[ha] Service call {domain}.{service} failed: {e}")
            return False
