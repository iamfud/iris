"""Iris Displays Subsystem.

Provides pluggable hardware display drivers (LED matrix, secondary LCD panels, stream decks).
"""

import logging
from displays.base import BaseDisplayDriver
from displays.matrix import MatrixDisplayDriver
from displays.akp02 import AKP02DisplayDriver
from displays.registry import (
    dispatch_notification,
    dispatch_stats,
    get_all_drivers,
    get_driver,
    register_driver,
    unregister_driver,
)

log = logging.getLogger("iris.displays")


def initialize_displays(serial_sender=None, cfg=None):
    """Instantiate and register all hardware display drivers."""
    # 1. MAX7219 Serial Matrix
    if serial_sender:
        try:
            matrix = MatrixDisplayDriver(serial_sender, cfg=cfg)
            register_driver(matrix)
            log.info("[displays] Registered MatrixDisplayDriver")
        except Exception as ex:
            log.warning("[displays] Failed to register MatrixDisplayDriver: %s", ex)

    # 2. Ajazz AKP02 USB Display
    try:
        akp = AKP02DisplayDriver(cfg=cfg)
        register_driver(akp)
        akp.start()
        log.info("[displays] Registered AKP02DisplayDriver")
    except Exception as ex:
        log.warning("[displays] Failed to register AKP02DisplayDriver: %s", ex)


def stop_displays():
    """Stop and release all registered display drivers."""
    for d in get_all_drivers():
        try:
            d.stop()
        except Exception as ex:
            log.debug("[displays] Error stopping driver %s: %s", getattr(d, "name", "unknown"), ex)


__all__ = [
    "BaseDisplayDriver",
    "MatrixDisplayDriver",
    "AKP02DisplayDriver",
    "register_driver",
    "unregister_driver",
    "get_driver",
    "get_all_drivers",
    "dispatch_stats",
    "dispatch_notification",
    "initialize_displays",
    "stop_displays",
]

