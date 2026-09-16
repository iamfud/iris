"""Abstract base class for physical display drivers in Iris."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseDisplayDriver(ABC):
    """Abstract interface for Iris display drivers (LED matrix, LCD panels, stream decks)."""

    def __init__(self, name: str, width_px: int = 0, height_px: int = 0):
        self.name = name
        self.width_px = width_px
        self.height_px = height_px
        self.is_connected = False

    @abstractmethod
    def start(self) -> bool:
        """Start the display driver and establish hardware connection."""
        pass

    @abstractmethod
    def stop(self):
        """Stop the display driver and release resources."""
        pass

    def render_stats(self, stats: Dict[str, Any]):
        """Render PC hardware telemetry snapshot on the display."""
        pass

    def render_notification(self, title: str, message: str, theme: str = "purple"):
        """Render an incoming notification."""
        pass

    def render_progress(self, label: str, percent: float):
        """Render progress bar (0-100%)."""
        pass

    def clear(self):
        """Clear display contents or return to idle."""
        pass
