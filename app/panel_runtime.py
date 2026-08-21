"""Portable panel runtime for the web portal.

Executes panel slot actions without a Tk window and builds the live
snapshot consumed by the Panel view (GET /api/panel/live). Mirrors the
action dispatch in main_window._on_button_action so the phone behaves
like the hardware/Tk panel.
"""

from __future__ import annotations

import ctypes
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


_PLUGIN_TOAST = None

def _set_plugin_toast(toast):
    global _PLUGIN_TOAST
    _PLUGIN_TOAST = toast

def _last_toast():
    """Structured last notification (from notifications_store or in-flight), or None."""
    global _PLUGIN_TOAST
    try:
        import notifications_store
        stored = notifications_store.get_last_notification()
        if stored:
            return stored
    except Exception:
        pass
    return _PLUGIN_TOAST


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


def _entity_states():
    try:
        from panel_entities import get_live_entity_states
        return get_live_entity_states()
    except Exception:
        return {}


def live_payload(cfg):
    """Snapshot for GET /api/panel/live (cheap; called every ~1s)."""
    from panel_actions import ensure_panel_defaults, resolve_panel_board
    ensure_panel_defaults(cfg)
    board, active_ids, fg = resolve_panel_board(cfg)
    return {
        "config": {
            "panel_board": board,
            "panel_utility": cfg.get("panel_utility") or [],
            "panel_sliders": cfg.get("panel_sliders") or [],
            "panel_layout": cfg.get("panel_layout") or [],
            "panel_gauges": cfg.get("panel_gauges") or {},
            "panel_profiles": cfg.get("panel_profiles") or [],
            "media_player_path": cfg.get("media_player_path") or "",
            "keep_alive": bool(cfg.get("keep_alive", True)),
            "theme": cfg.get("theme") or {"mode": "iris", "accent": "#B23AF6", "neon": "#79E8FC"},
        },
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
        "plugin_button_states": _plugin_button_states(),
        "entity_states": _entity_states(),
        "warnings": _warnings(),
    }


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
        if btype == "OPENRGB":
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
            if bid == "display" or ent == "system.display":
                if app:
                    val = not bool(app.cfg.get("pc_stats_manual", False))
                    app.cfg["pc_stats_manual"] = val
                    from config import save_config
                    save_config(app.cfg)
                    return {"ok": True}
            elif bid == "overlay" or ent == "system.overlay":
                if app and hasattr(app, "_toggle_overlay"):
                    app._toggle_overlay()
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
            elif bid == "screenshot" or ent == "system.screenshot":
                if app is not None and getattr(app, "_main_win", None):
                    slot_copy = dict(slot)
                    app._root.after(
                        0, lambda: app._main_win.start_screenshot(slot_copy))
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
    entity = (slot.get("entity_id") or "").strip()
    if not entity or app is None:
        return False
    ha_url = (app.cfg.get("ha_url") or "").strip().rstrip("/")
    if not ha_url:
        return False
    token = (app.cfg.get("ha_token") or "").strip()
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    url = f"{ha_url}/api/services/homeassistant/toggle"
    payload = {"entity_id": entity}

    def _call():
        try:
            import requests as req
            r = req.post(url, json=payload, headers=headers, timeout=5)
            log.info("[panel_runtime] REST %s -> %s", entity, r.status_code)
        except Exception as ex:
            log.warning("[panel_runtime] REST action failed: %s", ex)

    threading.Thread(target=_call, daemon=True).start()
    return True


def _openrgb_action(slot):
    profile_name = (slot.get("openrgb_profile") or "").strip()
    if not profile_name:
        return False
    try:
        from providers.openrgb import _list_profile_files, _profile_name_from_path, _apply_profile
        for fp in _list_profile_files():
            if _profile_name_from_path(fp) == profile_name:
                threading.Thread(target=_apply_profile, args=(fp, profile_name), daemon=True).start()
                return True
    except Exception as ex:
        log.warning("[panel_runtime] openrgb action failed: %s", ex)
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
        current = get_current_default_audio_output()
        device_key = alt if (alt and current and current == primary) else primary
        threading.Thread(target=set_default_audio_output, args=(device_key,), daemon=True).start()
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
