"""Display driver registry and dispatcher."""

import logging
from typing import Dict, List, Optional

from displays.base import BaseDisplayDriver

log = logging.getLogger("iris.displays.registry")

_DRIVERS: Dict[str, BaseDisplayDriver] = {}


def register_driver(driver: BaseDisplayDriver):
    """Register an active display driver."""
    _DRIVERS[driver.name] = driver
    log.info("[displays] Registered display driver: %s (%dx%d)", driver.name, driver.width_px, driver.height_px)


def unregister_driver(name: str):
    """Unregister a display driver by name."""
    if name in _DRIVERS:
        del _DRIVERS[name]


def get_driver(name: str) -> Optional[BaseDisplayDriver]:
    """Retrieve a registered display driver by name."""
    return _DRIVERS.get(name)


def get_all_drivers() -> List[BaseDisplayDriver]:
    """Return all registered display drivers."""
    return list(_DRIVERS.values())


def dispatch_stats(stats: dict):
    """Broadcast a telemetry snapshot to all registered display drivers."""
    for d in _DRIVERS.values():
        if d.is_connected:
            try:
                d.render_stats(stats)
            except Exception as ex:
                log.debug("[displays] Driver %s render_stats error: %s", d.name, ex)


def dispatch_notification(title: str, message: str, theme: str = "purple"):
    """Broadcast a notification to all registered display drivers."""
    for d in _DRIVERS.values():
        if d.is_connected:
            try:
                d.render_notification(title, message, theme)
            except Exception as ex:
                log.debug("[displays] Driver %s render_notification error: %s", d.name, ex)


def dispatch_theme(theme: dict):
    """Broadcast a theme change to all registered display drivers."""
    for d in _DRIVERS.values():
        if d.is_connected and hasattr(d, "on_theme"):
            try:
                d.on_theme(theme)
            except Exception as ex:
                log.debug("[displays] Driver %s on_theme error: %s", d.name, ex)
