"""Iris Displays Subsystem.

Provides pluggable hardware display drivers (LED matrix, secondary LCD panels, stream decks).
"""

from displays.base import BaseDisplayDriver
from displays.matrix import MatrixDisplayDriver
from displays.registry import (
    dispatch_notification,
    dispatch_stats,
    get_all_drivers,
    get_driver,
    register_driver,
    unregister_driver,
)

__all__ = [
    "BaseDisplayDriver",
    "MatrixDisplayDriver",
    "register_driver",
    "unregister_driver",
    "get_driver",
    "get_all_drivers",
    "dispatch_stats",
    "dispatch_notification",
]
