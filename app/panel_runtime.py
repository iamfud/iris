"""Portable panel runtime for the web portal.

Executes panel slot actions without a Tk window and builds the live
snapshot consumed by the Panel view (GET /api/panel/live). Mirrors the
action dispatch in main_window._on_button_action so the phone behaves
like the hardware/Tk panel.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import subprocess
import threading
import time

log = logging.getLogger("iris.panel_runtime")


def _app():
    import ws_bridge
    return getattr(ws_bridge, "_app", None)


# ── Live snapshot ───────────────────────────────────────────────

def _hardware_connected():
    try:
        from serial_comm import serial_sender
        if serial_sender.connected_port() is not None:
            return True
    except Exception:
        pass
    try:
        import ws_bridge
        app = getattr(ws_bridge, "_app", None)
        if app is not None and getattr(app, "_online", False):
            return True
    except Exception:
        pass
    return False


def _port():
    try:
        from serial_comm import serial_sender
        return serial_sender.connected_port() or ""
    except Exception:
        return ""


def _gauges():
    try:
        import plugin_manager
        inst = plugin_manager.get("pc_stats")
        if inst is not None and hasattr(inst, "poll"):
            p = inst.poll()
            return {
                "available": bool(p.get("available")),
                "cpu_temp": p.get("cpu_temp"),
                "gpu_temp": p.get("gpu_temp"),
                "fps": p.get("fps"),
                "fps_max": p.get("fps_max") or p.get("refresh_rate") or 60,
                "refresh_rate": p.get("refresh_rate") or p.get("fps_max") or 60,
                "cpu_pct": p.get("cpu_pct"),
                "cpu_temp_unit": p.get("cpu_temp_unit"),
                "cpu_temp_max": p.get("cpu_temp_max"),
                "gpu_temp_unit": p.get("gpu_temp_unit"),
                "gpu_temp_max": p.get("gpu_temp_max"),
            }
    except Exception:
        pass
    return {"available": False, "cpu_temp": None, "gpu_temp": None,
            "fps": None, "fps_max": 60, "refresh_rate": 60, "cpu_pct": None}


def _volume():
    try:
        import win_volume
        return win_volume.get_active_app_state()
    except Exception:
        return {"app": None, "volume": None}


def _master_volume():
    try:
        import win_volume
        return win_volume.get_master_state().get("volume")
    except Exception:
        return None


def _app_volumes():
    try:
        import win_volume
        return win_volume.list_sessions()
    except Exception:
        return []


def _brightness(cfg):
    try:
        from constants import DEFAULT_BRIGHTNESS
    except Exception:
        DEFAULT_BRIGHTNESS = 2
    try:
        return int(cfg.get("brightness", DEFAULT_BRIGHTNESS))
    except (TypeError, ValueError):
        return int(DEFAULT_BRIGHTNESS)


def _overlay_state():
    app = _app()
    if app is None:
        return False
    try:
        return bool(getattr(app, "_overlay", None))
    except Exception:
        return False


def _set_plugin_toast(toast):
    pass


def _last_toast():
    """Return the structured last recorded notification from notifications_store (or None)."""
    try:
        import notifications_store
        return notifications_store.get_last_notification()
    except Exception:
        return None


def _plugin_button_states():
    try:
        import plugin_manager
        return plugin_manager.get_plugin_button_states()
    except Exception:
        return {}


def _warnings():
    try:
        import warning_state
        return warning_state.snapshot()
    except Exception:
        return {}


def _entity_states(plugin_button_states=None):
    try:
        from panel_entities import get_live_entity_states
        return get_live_entity_states(plugin_button_states)
    except Exception:
        return {}


def _default_audio_output():
    try:
        from win_platform import get_current_default_audio_output
        return get_current_default_audio_output()
    except Exception:
        return None


def live_payload(cfg, client_cv=None):
    """Snapshot for GET /api/panel/live (cheap; called every ~500ms)."""
    try:
        import plugin_manager
        plugin_manager.sync_plugin_themes()
    except Exception:
        pass
    from panel_actions import ensure_panel_defaults, resolve_panel_board
    ensure_panel_defaults(cfg)
    board, active_ids, fg = resolve_panel_board(cfg)
    p_states = _plugin_button_states()
    e_states = _entity_states(p_states)

    cfg_data = {
        "panel_board": board,
        "panel_utility": cfg.get("panel_utility") or [],
        "panel_sliders": cfg.get("panel_sliders") or [],
        "panel_layout": cfg.get("panel_layout") or [
            {"id": "gauges", "enabled": True, "local": True, "remote": True},
            {"id": "button_box", "enabled": True, "local": True, "remote": True},
            {"id": "sliders", "enabled": True, "local": True, "remote": True},
            {"id": "utility", "enabled": True, "local": True, "remote": True},
        ],
        "panel_gauges": cfg.get("panel_gauges") or {},
        "panel_profiles": cfg.get("panel_profiles") or [],
        "media_player_path": cfg.get("media_player_path") or "",
        "screensaver_timeout": int(cfg.get("screensaver_timeout", 60)),
        "keep_alive": bool(cfg.get("keep_alive", True)),
        "theme": cfg.get("theme") or {"mode": "iris", "accent": "#B23AF6", "neon": "#79E8FC"},
    }
    import hashlib
    cv = hashlib.md5(json.dumps(cfg_data, sort_keys=True).encode()).hexdigest()[:12]

    payload = {
        "config_version": cv,
        "hardware_connected": _hardware_connected(),
        "port": _port(),
        "gauges": _gauges(),
        "volume": _volume(),
        "master_volume": _master_volume(),
        "app_volumes": _app_volumes(),
        "brightness": _brightness(cfg),
        "pc_stats_manual": bool(cfg.get("pc_stats_manual", False)),
        "overlay_on": _overlay_state(),
        "notification": _last_toast(),
        "foreground_app": fg,
        "active_profiles": active_ids,
        "plugin_button_states": p_states,
        "entity_states": e_states,
        "default_audio_output": _default_audio_output(),
        "warnings": _warnings(),
    }
    if client_cv != cv:
        payload["config"] = cfg_data
    return payload


# ── Action execution ────────────────────────────────────────────

def execute_slot(slot):
    """Run a panel slot action from the web portal. Returns {"ok": bool}."""
    if not isinstance(slot, dict):
        return {"ok": False}
    btype = str(slot.get("type") or "").strip()
    ent = str(slot.get("entity") or "").strip()
    app = _app()
    try:
        if btype == "GROUP":
            _open_path(slot.get("shortcut_path"), slot.get("shortcut_args"))
            return {"ok": True, "nav": True}
        if btype == "SHORTCUT":
            _open_path(slot.get("shortcut_path"), slot.get("shortcut_args"))
            return {"ok": True}
        if btype == "REST":
            return {"ok": _rest_action(app, slot)}
        if btype == "OPENRGB" or slot.get("openrgb_profile") or ent.startswith("openrgb.profile."):
            return {"ok": _openrgb_action(slot)}
        if btype == "AUDIO OUTPUT":
            return {"ok": _audio_output_action(slot)}
        if btype == "STOPWATCH":
            if app is not None and hasattr(app, "_root"):
                try:
                    app._root.after(0, app._toggle_stopwatch)
                except Exception as ex:
                    log.warning("[panel_runtime] stopwatch schedule failed: %s", ex)
            return {"ok": True}
        if btype == "SCREENSHOT" or btype == "SCREENSHOT_FULL":
            if app is not None and getattr(app, "_main_win", None):
                slot_copy = dict(slot)
                app._root.after(0, lambda: app._main_win.start_screenshot(slot_copy, mode="fullscreen"))
            return {"ok": True}
        if btype == "SCREENSHOT_ZONE":
            if app is not None and getattr(app, "_main_win", None):
                slot_copy = dict(slot)
                app._root.after(0, lambda: app._main_win.start_screenshot(slot_copy, mode="zone"))
            return {"ok": True}
        if btype == "NOTE":
            if app is not None and getattr(app, "_main_win", None):
                app._root.after(0, app._main_win.start_quick_note)
            return {"ok": True}
        if btype == "MEDIA_PREV":
            _media_key(0xB1)
            return {"ok": True}
        if btype == "MEDIA_PLAY":
            _media_key(0xB3)
            return {"ok": True}
        if btype == "MEDIA_NEXT":
            _media_key(0xB0)
            return {"ok": True}
        if btype == "MEDIA_EJECT" or ent == "media.player" or ent == "media.eject":
            path = ""
            if app is not None and getattr(app, "cfg", None):
                path = (app.cfg.get("media_player_path") or "").strip()
            if not path:
                try:
                    from config import load_config
                    path = (load_config().get("media_player_path") or "").strip()
                except Exception:
                    pass
            from win_platform import bring_media_player_to_foreground
            if not bring_media_player_to_foreground(path):
                if path:
                    _launch_exe(path)
            return {"ok": True}
        if btype == "EMPTY" or btype == "SENSOR":
            return {"ok": True}

        # ── Bound Entity / Plugin Action Dispatch ─────────────────
        pname = slot.get("plugin")
        bid = slot.get("button_id")
        if not pname and "." in ent:
            pname, bid = ent.split(".", 1)

        if pname == "system" or ent.startswith("system."):
            if bid == "lighting_sync" or ent == "system.lighting_sync":
                if app and hasattr(app, "_toggle_lighting_sync"):
                    val = app._toggle_lighting_sync()
                    return {"ok": True, "active": val}
                elif app and getattr(app, "cfg", None):
                    ambient_cfg = app.cfg.setdefault("ambient_lighting", {})
                    cur = ambient_cfg.get("enabled", True) is not False
                    ambient_cfg["enabled"] = not cur
                    from config import save_config
                    save_config(app.cfg)
                    try:
                        from lighting_service import get_lighting_service
                        get_lighting_service().update_config(app.cfg)
                    except Exception:
                        pass
                    try:
                        from ws_bridge import broadcast
                        broadcast({"type": "config", "config": {"ambient_lighting": ambient_cfg}})
                    except Exception:
                        pass
                    return {"ok": True, "active": not cur}
            elif bid == "display" or ent == "system.display":
                if app:
                    val = not bool(app.cfg.get("pc_stats_manual", False))
                    app.cfg["pc_stats_manual"] = val
                    from config import save_config
                    save_config(app.cfg)
                    return {"ok": True}
            elif bid == "overlay" or ent == "system.overlay":
                if app and hasattr(app, "_toggle_overlay"):
                    if hasattr(app, "_root"):
                        app._root.after(0, app._toggle_overlay)
                    else:
                        app._toggle_overlay()
                    return {"ok": True}
            elif bid == "toolbar" or ent == "system.toolbar":
                if app and hasattr(app, "_toggle_capture_toolbar"):
                    if hasattr(app, "_root"):
                        app._root.after(0, app._toggle_capture_toolbar)
                    else:
                        app._toggle_capture_toolbar()
                    return {"ok": True}
            elif bid == "mic_mute" or ent == "system.mic_mute":
                from win_platform import toggle_mic_mute
                toggle_mic_mute()
                return {"ok": True}
            elif bid == "settings" or ent == "system.settings":
                if app and hasattr(app, "_open_settings"):
                    app._open_settings()
                else:
                    import webbrowser
                    webbrowser.open("http://127.0.0.1:9090")
                return {"ok": True}
            elif bid == "colour_picker" or ent == "system.colour_picker":
                if app is not None and getattr(app, "_main_win", None):
                    app._root.after(0, app._main_win.start_colour_picker)
                return {"ok": True}
            elif bid in ("screenshot", "screenshot_full") or ent in ("system.screenshot", "system.screenshot_full"):
                if app is not None and getattr(app, "_main_win", None):
                    slot_copy = dict(slot)
                    app._root.after(
                        0, lambda: app._main_win.start_screenshot(slot_copy, mode="fullscreen"))
                return {"ok": True}
            elif bid == "screenshot_zone" or ent == "system.screenshot_zone":
                if app is not None and getattr(app, "_main_win", None):
                    slot_copy = dict(slot)
                    app._root.after(
                        0, lambda: app._main_win.start_screenshot(slot_copy, mode="zone"))
                return {"ok": True}
            elif bid == "note" or ent == "system.note":
                if app is not None and getattr(app, "_main_win", None):
                    app._root.after(0, app._main_win.start_quick_note)
                return {"ok": True}
        elif pname == "media" or ent.startswith("media."):
            if bid == "play_pause" or ent == "media.play_pause":
                _media_key(0xB3)
                return {"ok": True}
            elif bid == "next" or ent == "media.next":
                _media_key(0xB0)
                return {"ok": True}
            elif bid == "prev" or ent == "media.prev":
                _media_key(0xB1)
                return {"ok": True}
            elif bid == "player" or ent == "media.player" or ent == "media.eject":
                path = ""
                if app is not None and getattr(app, "cfg", None):
                    path = (app.cfg.get("media_player_path") or "").strip()
                if not path:
                    try:
                        from config import load_config
                        path = (load_config().get("media_player_path") or "").strip()
                    except Exception:
                        pass
                from win_platform import bring_media_player_to_foreground
                if not bring_media_player_to_foreground(path):
                    if path:
                        _launch_exe(path)
                return {"ok": True}
        elif pname and bid:
            import plugin_manager
            return plugin_manager.handle_button_action(pname, bid, slot)

        if btype == "HOTKEY" or slot.get("hotkey") or slot.get("keys"):
            return {"ok": _hotkey_action(slot)}
        return {"ok": True}
        if btype.startswith("PLUGIN:"):
            parts = btype.split(":", 2)
            if len(parts) >= 3:
                pname, cid = parts[1], parts[2]
                from plugin_manager import on_tap
                val = slot.get(cid) or slot.get("value")
                on_tap(pname, cid, val)
            return {"ok": True}
    except Exception as e:
        log.warning("[panel_runtime] action %s failed: %s", btype, e)
        return {"ok": False, "error": str(e)}
    return {"ok": False}


def _open_path(path, args=None):
    if not path:
        return
    import shutil
    import shlex

    raw_path = os.path.expandvars(os.path.expanduser(str(path).strip().strip('"\'')))
    raw_args = os.path.expandvars(str(args or "").strip())

    # If raw_args is not explicitly given, check if raw_path has embedded switches (e.g. 'cmd.exe /k "..."')
    if not raw_args and not os.path.isfile(raw_path):
        try:
            parts = shlex.split(raw_path, posix=False)
            if parts:
                first_token = parts[0].strip('"\'')
                first_token = os.path.expandvars(os.path.expanduser(first_token))
                which_p = shutil.which(first_token) or (first_token if os.path.isfile(first_token) else None)
                if which_p and os.path.isfile(which_p):
                    raw_path = which_p
                    raw_args = raw_path[len(parts[0]):].strip()
        except Exception:
            pass

    # URL handling
    if raw_path.startswith(("http://", "https://")) or (("." in raw_path) and ("/" in raw_path or "\\" not in raw_path) and not os.path.isabs(raw_path) and not raw_path.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".vbs", ".ps1"))):
        url_target = raw_path if raw_path.startswith(("http://", "https://")) else ("https://" + raw_path)
        try:
            import webbrowser
            webbrowser.open(url_target)
            return
        except Exception:
            try:
                if hasattr(os, "startfile"):
                    os.startfile(url_target)
                    return
            except Exception:
                pass

    exe = shutil.which(raw_path) or raw_path
    try:
        if raw_args:
            if hasattr(os, "startfile"):
                os.startfile(exe, arguments=raw_args)
            else:
                subprocess.Popen(f'"{exe}" {raw_args}', shell=True)
        else:
            if hasattr(os, "startfile"):
                os.startfile(exe)
            else:
                subprocess.Popen([exe], shell=False)
    except Exception as ex:
        log.warning("[panel_runtime] launch failed: %s", ex)


def _launch_exe(path):
    path = (path or "").strip()
    if not path:
        return
    try:
        _open_path(path)
    except Exception as ex:
        log.warning("[panel_runtime] launch exe failed: %s", ex)


def _rest_action(app, slot):
    entity = (slot.get("entity_id") or slot.get("button_id") or "").strip()
    if not entity:
        ent = str(slot.get("entity") or "").strip()
        if ent.startswith("ha."):
            entity = ent[len("ha."):]
    if not entity:
        return False

    domain = entity.split(".")[0] if "." in entity else "homeassistant"
    service = "turn_on" if domain in ("scene", "script") else "toggle"

    def _call():
        try:
            import plugin_manager
            inst = plugin_manager.get("ha")
            if inst and hasattr(inst, "_connector"):
                inst._connector.call_service(domain, service, entity_id=entity)
            else:
                from plugins.ha.connector import HASSConnector
                from config import load_config
                conn = HASSConnector(load_config())
                conn.call_service(domain, service, entity_id=entity)
        except Exception as ex:
            log.warning("[panel_runtime] HA REST action failed: %s", ex)

    threading.Thread(target=_call, daemon=True, name="iris-btn-ha").start()
    return True


def _openrgb_action(slot):
    profile_name = (slot.get("openrgb_profile") or "").strip()
    if not profile_name:
        ent = str(slot.get("entity") or "").strip()
        if ent.startswith("openrgb.profile."):
            prof_slug = ent[len("openrgb.profile."):].lower()
            try:
                import plugin_manager
                inst = plugin_manager.get("openrgb")
                if inst and hasattr(inst, "get_options"):
                    for p in inst.get_options("openrgb_profiles"):
                        clean_id = p.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("[", "").replace("]", "")
                        if clean_id == prof_slug:
                            profile_name = p
                            break
            except Exception:
                pass
    if not profile_name:
        return False
    try:
        import plugin_manager
        plugin_manager.on_tap("openrgb", "profile", profile_name)
        return True
    except Exception as ex:
        log.warning("[panel_runtime] openrgb action via plugin_manager failed: %s", ex)
        # Fallback to direct SDK call if plugin_manager not available
        try:
            from openrgb import OpenRGBClient
            client = OpenRGBClient(name="Iris")
            clean_name = profile_name.replace(" (Device)", "").replace(" (Effect)", "").strip()
            client.load_profile(clean_name)
            return True
        except Exception as ex2:
            log.warning("[panel_runtime] openrgb fallback failed: %s", ex2)
    return False


def _hotkey_action(slot):
    # Support modern string hotkey (e.g. '1', 'space', 'f13', 'ctrl+1')
    hotkey = (slot.get("hotkey") or "").strip()
    if not hotkey:
        # Fallback to legacy keys list
        legacy_keys = slot.get("keys") or []
        if legacy_keys:
            hotkey = legacy_keys

    if not hotkey:
        return False

    try:
        from keyboard_service import keyboard_service
        return keyboard_service.send_sequence(hotkey)
    except Exception as ex:
        log.warning("[panel_runtime] hotkey action failed: %s", ex)
        return False



def _audio_output_action(slot):
    primary = (slot.get("audio_input_device_id") or "").strip()
    alt = (slot.get("audio_input_device_id_alt") or "").strip()
    if not primary:
        return False
    try:
        from win_platform import get_current_default_audio_output, set_default_audio_output
        current = get_current_default_audio_output(ttl=0)
        device_key = alt if (alt and current and current == primary) else primary

        def _switch():
            set_default_audio_output(device_key)
            app = _app()
            if app is not None and getattr(app, "_main_win", None):
                try:
                    app._root.after(0, app._main_win._render_buttons)
                except Exception:
                    pass
            try:
                import ws_bridge
                ws_bridge.broadcast({"type": "panel_update"})
            except Exception:
                pass

        threading.Thread(target=_switch, daemon=True).start()
        return True
    except Exception as ex:
        log.warning("[panel_runtime] audio output action failed: %s", ex)
        return False


def _media_key(vk):
    _EXTENDED = 0x0001
    _KEYUP = 0x0002
    try:
        ctypes.windll.user32.keybd_event(vk, 0, _EXTENDED, 0)
        ctypes.windll.user32.keybd_event(vk, 0, _EXTENDED | _KEYUP, 0)
    except Exception:
        pass
