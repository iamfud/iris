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

import logging
import threading

log = logging.getLogger("iris.warning_state")

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
    _sync_warning_lighting()


def clear_warning(key):
    """Remove the warning for *key* (no-op if not set)."""
    with _lock:
        _warnings.pop(str(key), None)
    _sync_warning_lighting()


def clear_plugin_warnings(plugin_name):
    """Remove all warnings owned by *plugin_name*."""
    prefix = f"{plugin_name}:"
    with _lock:
        to_del = [k for k in _warnings if k.startswith(prefix)]
        for k in to_del:
            _warnings.pop(k, None)
    _sync_warning_lighting()


def clear_all():
    """Remove every warning (e.g. when plugins are stopped)."""
    with _lock:
        _warnings.clear()
    _sync_warning_lighting()


def snapshot():
    """Thread-safe copy of the current warnings for the live payload."""
    with _lock:
        res = dict(_warnings)
        for k, v in list(_warnings.items()):
            if ":" in k:
                res[k.replace(":", ".")] = v
            elif "." in k:
                res[k.replace(".", ":")] = v
        return res


def _sync_warning_lighting():
    """Forward alert state to lighting providers (e.g. OpenRGB) if lighting alerts are enabled."""
    try:
        from lighting_service import get_lighting_service
        import plugin_manager

        alerts_enabled = True
        try:
            cfg = getattr(plugin_manager, "_cfg", None)
            if not cfg:
                try:
                    from lighting_service import get_lighting_service
                    cfg = get_lighting_service()._cfg
                except Exception:
                    pass
            if not cfg:
                try:
                    import config
                    cfg = config.load_config()
                except Exception:
                    pass
            cfg = cfg or {}

            active_id = getattr(plugin_manager, "_active_themed_plugin", None)
            profiles = cfg.get("panel_profiles") or []
            # Extract plugins that currently hold warnings (e.g. 'elite_dangerous' from 'elite_dangerous:shields')
            with _lock:
                warning_plugins = {str(k).split(":", 1)[0].lower() for k in _warnings.keys()}

            for p in profiles:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or "").lower()
                pexe = str(p.get("exe") or "").lower().replace(".exe", "").strip()
                act_clean = str(active_id or "").lower().replace(".exe", "").strip()

                is_active = bool(active_id and (pid == str(active_id).lower() or pexe == act_clean or (pexe and pexe in act_clean)))
                is_warn_owner = any(wp in pid or (pexe and wp in pexe) for wp in warning_plugins)

                if is_active or is_warn_owner:
                    alerts_enabled = bool(p.get("lighting_alerts_enabled", True))
                    if not alerts_enabled:
                        break
        except Exception as ex:
            log.debug("[warning_state] error evaluating alerts_enabled: %s", ex)

        with _lock:
            has_warnings = bool(_warnings)
            warn_color = "#FF0000"
            for w in _warnings.values():
                if isinstance(w, dict) and w.get("color"):
                    warn_color = w.get("color")
                    break

        ls = get_lighting_service()
        if has_warnings and alerts_enabled:
            actions = {}
            for prov in ls.get_providers():
                pid = prov.get("id")
                if prov.get("connected") or pid == "openrgb":
                    actions[pid] = warn_color
            if not actions:
                actions = {"openrgb": warn_color}
            log.info("[warning_state] pushing critical alert to lighting: %s", actions)
            ls.push_alert(actions, duration_s=0, is_critical=True)
        else:
            if has_warnings and not alerts_enabled:
                log.info("[warning_state] warnings active but lighting alerts disabled for profile")
            ls.pop_alert(force=True)
    except Exception as ex:
        log.warning("[warning_state] _sync_warning_lighting failed: %s", ex)
