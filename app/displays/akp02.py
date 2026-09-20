"""Ajazz AKP02 USB display panel driver."""

import logging
import threading
import time
from typing import Any, Dict, Optional
from displays.base import BaseDisplayDriver

log = logging.getLogger("iris.displays.akp02")

try:
    from akp02 import AKP02
except ImportError:
    AKP02 = None


class AKP02DisplayDriver(BaseDisplayDriver):
    """Exclusive hardware driver for Ajazz AKP02 USB LCD panels."""

    def __init__(self, cfg=None):
        super().__init__(name="akp02", width_px=1920, height_px=462)
        self._cfg = cfg or {}
        self._lock = threading.RLock()
        self._panel = None
        self._brightness = int((self._cfg.get("plugins") or {}).get("akp02_stats", {}).get("brightness", 85))
        self._last_connect_attempt = 0.0
        self._connect_cooldown_s = 1.0

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._panel is not None

    @is_connected.setter
    def is_connected(self, value: bool):
        pass

    def start(self) -> bool:
        """Atomically establish connection and apply initial state.

        AKP02() and screen_on() are transactional (handle closed and discarded on failure).
        Brightness application is best-effort.
        """
        if AKP02 is None:
            return False

        with self._lock:
            if self._panel is not None:
                return True

            now = time.time()
            if now - self._last_connect_attempt < self._connect_cooldown_s:
                return False
            self._last_connect_attempt = now

            panel = None
            try:
                panel = AKP02()
                panel.screen_on()
                try:
                    panel.set_brightness(self._brightness)
                except Exception as b_ex:
                    log.debug("[displays.akp02] initial brightness set warning: %s", b_ex)
                self._panel = panel
                log.info("[displays.akp02] Connected to AKP02 panel (brightness=%d%%)", self._brightness)
                return True
            except Exception as ex:
                log.debug("[displays.akp02] Connection failed: %s", ex)
                if panel:
                    try:
                        panel.close()
                    except Exception:
                        pass
                self._panel = None
                return False

    def stop(self):
        """Safely close hardware connection."""
        with self._lock:
            if self._panel:
                try:
                    self._panel.close()
                except Exception as ex:
                    log.debug("[displays.akp02] Close error: %s", ex)
                self._panel = None
                log.info("[displays.akp02] Disconnected from AKP02 panel")

    def show(self, image) -> bool:
        """Transmit frame to physical panel with automatic reconnect."""
        with self._lock:
            if not self._panel:
                if not self.start():
                    return False

            try:
                self._panel.show(image)
                return True
            except Exception as ex:
                log.warning("[displays.akp02] Frame transmission failed: %s", ex)
                try:
                    self._panel.close()
                except Exception:
                    pass
                self._panel = None
                return False

    def render_frame(self, image) -> bool:
        """Alias for canonical show(image)."""
        return self.show(image)

    def set_brightness(self, value: int) -> bool:
        """Set desired brightness and apply to panel if connected."""
        val = max(0, min(100, int(value)))
        with self._lock:
            self._brightness = val
            if self._panel:
                try:
                    self._panel.set_brightness(val)
                    return True
                except Exception as ex:
                    log.debug("[displays.akp02] set_brightness error: %s", ex)
                    return False
            return True

    def get_brightness(self) -> int:
        """Return desired brightness level."""
        with self._lock:
            return self._brightness

    def screen_on(self) -> bool:
        with self._lock:
            if self._panel:
                try:
                    self._panel.screen_on()
                    return True
                except Exception:
                    pass
            return False

    def screen_off(self) -> bool:
        with self._lock:
            if self._panel:
                try:
                    self._panel.screen_off()
                    return True
                except Exception:
                    pass
            return False
