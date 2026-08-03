"""Connector interface — all connectors implement this contract.

A connector is a pure adapter. It wraps one external source (TCP, file,
shared memory, WebSocket, serial, etc.) and exposes a uniform lifecycle
and a generic control interface.

Iris never talks to the external source — only through the connector.
The connector declares what controls it supports, handles taps against
those controls, and provides dynamic option lists for select-type
controls.  The owning plugin is a thin orchestrator that merely
delegates.
"""

import logging

log = logging.getLogger("iris.connector")


class BaseConnector:
    """Interface every connector must implement.

    Subclasses add **no** public domain-specific methods — everything
    goes through ``handle()``, ``controls()``, and ``get_options()``.
    """

    # ── Lifecycle ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Establish connection to the external source.

        Must be idempotent — safe to call when already connected
        (reconnect / no-op).  Returns ``True`` on success.
        """
        raise NotImplementedError

    def disconnect(self):
        """Tear down the connection.  Safe when already disconnected."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Whether the connector is connected and usable right now."""
        raise NotImplementedError

    # ── Control definitions ──────────────────────────────────────

    @classmethod
    def controls(cls) -> list:
        """Return the list of control definitions this connector exposes.

        Each entry is a dict:

        .. code-block:: python

            {
                "id": "profile",
                "type": "select",       # select | color | slider | toggle
                "label": "Profile",
                "options_key": "profiles",   # only for type == "select"
                "min": 0, "max": 100, "step": 5,  # only for type == "slider"
            }

        This is a classmethod so discovery can enumerate controls
        without instantiating the connector.
        """
        raise NotImplementedError

    # ── Settings definitions ─────────────────────────────────────

    @classmethod
    def get_settings(cls) -> list:
        """Return the list of settings sections this connector exposes.

        Each section is a dict:

        .. code-block:: python

            {
                "title": "Temperature Limits",
                "controls": [
                    {"type": "toggle", "key": "enabled", "label": "Enabled"},
                    {"type": "slider", "key": "cpu_temp_lim", "label": "CPU Limit",
                     "min": 50, "max": 100, "step": 5, "unit": "°C"},
                ]
            }

        These merge with (and override) the ``settings`` array in
        ``plugin.json``.  Return an empty list if the connector has
        no programmatically-defined settings.

        This is a classmethod so discovery can enumerate settings
        without instantiating the connector.
        """
        return []

    # ── Actions ──────────────────────────────────────────────────

    def handle(self, control_id: str, value=None):
        """Execute the action for *control_id* with the given *value*.

        The connector owns all processing — parsing hex, looking up
        profiles, sending commands, etc.  The plugin never interprets
        the value.
        """
        raise NotImplementedError

    # ── Dynamic options (for ``select`` controls) ────────────────

    def get_options(self, option_key: str) -> list:
        """Return the current list of choices for an option key.

        Called when populating a ``select``-type control's dropdown.
        Returns a list of strings.
        """
        raise NotImplementedError
