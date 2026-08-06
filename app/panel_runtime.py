"""Portable panel runtime for the web portal.

Executes panel slot actions without a Tk window and builds the live
snapshot consumed by the Panel view (GET /api/panel/live). Mirrors the
action dispatch in main_window._on_button_action so the phone behaves
like the hardware/Tk panel.
"""

from __future__ import annotations

import ctypes
import logging
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
                "cpu_pct": p.get("cpu_pct"),
            }
    except Exception:
        pass
    return {"available": False, "cpu_temp": None, "gpu_temp": None,
            "fps": None, "cpu_pct": None}


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


def live_payload(cfg):
    """Snapshot for GET /api/panel/live (cheap; called every ~1s)."""
    from panel_actions import ensure_panel_defaults
    ensure_panel_defaults(cfg)
    return {
        "config": {
            "panel_board": cfg.get("panel_board") or [],
            "panel_utility": cfg.get("panel_utility") or [],
            "panel_sliders": cfg.get("panel_sliders") or [],
            "panel_layout": cfg.get("panel_layout") or [],
            "panel_gauges": cfg.get("panel_gauges") or {},
            "media_player_path": cfg.get("media_player_path") or "",
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
    }


# ── Action execution ────────────────────────────────────────────

def execute_slot(slot):
    """Run a panel slot action from the web portal. Returns {"ok": bool}."""
    if not isinstance(slot, dict):
        return {"ok": False}
    btype = str(slot.get("type") or "").strip()
    app = _app()
    try:
        if btype == "GROUP":
            _open_path(slot.get("shortcut_path"))
            return {"ok": True, "nav": True}
        if btype == "SHORTCUT":
            _open_path(slot.get("shortcut_path"))
            return {"ok": True}
        if btype == "REST":
            return {"ok": _rest_action(app, slot)}
        if btype == "OPENRGB":
            return {"ok": _openrgb_action(slot)}
        if btype == "HOTKEY":
            return {"ok": _hotkey_action(slot)}
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
        if btype == "MEDIA_EJECT":
            if app is not None:
                path = (app.cfg.get("media_player_path") or "").strip()
                if path:
                    _launch_exe(path)
            return {"ok": True}
        if btype == "EMPTY":
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


def _open_path(path):
    path = (path or "").strip()
    if not path:
        return
    try:
        subprocess.Popen(["cmd", "/c", "start", "", path])
    except Exception as ex:
        log.warning("[panel_runtime] launch failed: %s", ex)


def _launch_exe(path):
    path = (path or "").strip()
    if not path:
        return
    try:
        subprocess.Popen([path], shell=False)
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
    keys = slot.get("keys") or []
    keys = [int(k) for k in keys if str(k).lstrip("-").isdigit()]
    if not keys:
        return False
    try:
        from main_window import _hardware_key
    except Exception as ex:
        log.warning("[panel_runtime] hotkey helper unavailable: %s", ex)
        return False
    user32 = ctypes.windll.user32
    scans = []
    for vk in keys:
        scan = user32.MapVirtualKeyW(vk, 0)
        if scan:
            scans.append(scan)
    if not scans:
        return False
    for scan in scans:
        _hardware_key(scan, True)
        time.sleep(0.03)
    time.sleep(0.08)
    for scan in reversed(scans):
        _hardware_key(scan, False)
        time.sleep(0.03)
    return True


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
