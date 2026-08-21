"""Warning-state registry (Iris core).

A warning flags a panel button with an alert colour while some condition is
true. Unlike notifications (transient/queued), warnings are a *state*: plugins
call :func:`set_warning` when a condition turns true and :func:`clear_warning`
when it clears. While a warning is active the corresponding panel button tile
renders in the warning colour (and optionally shows the message in its status
bar).

Keys are opaque to core — by convention a plugin uses the same key as its
plugin button state, i.e. ``"plugin_name:button_id"`` (the key format produced
by ``plugin_manager.get_plugin_button_states()``). The panel matches a slot to
its warning by the slot's entity id (``"plugin_name.button_id"``) or its
``"plugin_name:button_id"`` pair.

Plugins reach this via the serial sender they already hold::

    self._serial.set_warning("elite_dangerous:shields", color="#ffaa00",
                             message="Shields failing")
    self._serial.clear_warning("elite_dangerous:shields")
"""

import threading

_lock = threading.Lock()
_warnings = {}  # key -> {"color": str | None, "message": str}


def set_warning(key, color=None, message=""):
    """Mark button *key* as in warning state.

    ``color`` may be a hex string (``"#ffaa00"``) or ``None``, in which case
    the panel applies its default warning colour (neon red).
    """
    if not key:
        return
    with _lock:
        _warnings[str(key)] = {
            "color": color,
            "message": str(message or ""),
        }


def clear_warning(key):
    """Remove the warning for *key* (no-op if not set)."""
    with _lock:
        _warnings.pop(str(key), None)


def clear_all():
    """Remove every warning (e.g. when plugins are stopped)."""
    with _lock:
        _warnings.clear()


def snapshot():
    """Thread-safe copy of the current warnings for the live payload."""
    with _lock:
        return dict(_warnings)
