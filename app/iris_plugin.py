"""Iris Plugin SDK — Public Base Classes & Type Annotations for Third-Party Plugins.

This module provides the official `BasePlugin` class and helper interfaces
for developing third-party plugins for Iris.

Usage Example:
    from iris_plugin import BasePlugin

    class Plugin(BasePlugin):
        name = "my_plugin"

        def start(self):
            print("Plugin started!")

        def stop(self):
            print("Plugin stopped!")

        def poll(self):
            return {
                "available": True,
                "altitude": 5280
            }
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


class BasePlugin:
    """Standard base class for third-party Iris plugins.

    Provides default implementations for lifecycle and event hooks,
    and cleanly encapsulates internal runtime parameters.
    """

    name: str = ""
    display_name: str = ""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> None:
        """Initialize the plugin instance.

        Args:
            cfg: The global Iris configuration dictionary.
            *args: Internal proxies (e.g. serial hardware, overlays) captured privately.
            **kwargs: Additional runtime keyword arguments.
        """
        self._cfg: Dict[str, Any] = cfg or {}
        self._serial_sender: Any = args[0] if len(args) > 0 else kwargs.get("serial_sender")
        self._overlays: Any = args[1] if len(args) > 1 else kwargs.get("overlays")

    @property
    def config(self) -> Dict[str, Any]:
        """Return this plugin's persisted settings dictionary from config.json.
        
        Uses `self.name` to look up `plugins.<name>` in the configuration.
        """
        pcfg = self._cfg.get("plugins") or {}
        plugin_name = getattr(self, "name", "")
        if plugin_name and isinstance(pcfg, dict):
            return pcfg.get(plugin_name, {})
        return {}

    def start(self) -> None:
        """Invoked when the plugin is enabled or its target application process starts.
        
        Use this to initialize API connections, background worker threads, or file watchers.
        """
        pass

    def stop(self) -> None:
        """Invoked when the plugin is disabled or its target application process closes.
        
        Use this to cleanly close sockets, disconnect APIs, and terminate background threads.
        """
        pass

    def poll(self) -> Dict[str, Any]:
        """Polled every 1.0 second by Iris for live telemetry and status.

        Returns:
            Dictionary containing live state values. Any field declared in
            `plugin.json` under `live_data.fields` will automatically be ingested
            into the Iris Entity Bus.

            Example:
                {
                    "available": True,
                    "altitude": 5280.0,
                    "speed": 145.2,
                    "gear_down": True
                }
        """
        return {"available": True}

    def on_button(self, button_id: str, slot_data: Dict[str, Any]) -> bool:
        """Invoked when a user taps a button on the Phone Panel or Stream Deck.

        Args:
            button_id: The identifier string matching a button declared in `plugin.json`.
            slot_data: Additional context dictionary for the button slot.

        Returns:
            True if the action was handled by the plugin, False to let Iris
            trigger the default hotkey keystroke fallback.
        """
        return True

    def on_action(self, action_id: str) -> bool:
        """Invoked when a user clicks a momentary action button in the Settings page.

        Args:
            action_id: The identifier string matching an action declared in `plugin.json`.

        Returns:
            True if the action was handled successfully.
        """
        return True

    def get_options(self, option_key: str) -> List[Any]:
        """Return dynamic choices for dropdown select controls in settings.

        Args:
            option_key: The options_key declared in plugin.json setting control.

        Returns:
            List of string options or dict items (e.g. `[{"id": "opt1", "name": "Option 1"}]`).
        """
        return []

    def on_theme(self, theme_data: Dict[str, Any]) -> None:
        """Invoked when the active global theme changes via macros, game latching, or settings.

        Args:
            theme_data: Dictionary containing `mode` ('iris', 'monochrome', 'custom'),
                        `accent` (hex), and `neon` (hex).
        """
        pass
