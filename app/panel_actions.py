"""Panel action catalog and defaults.

Shared by the Tk overlay (runtime) and the HTML Panel editor (config).
No plugin business logic — only builtin types plus discovered PLUGIN: controls.
"""

from __future__ import annotations

import copy
import logging

log = logging.getLogger("iris.panel_actions")

# Standard Generic Action / Button types available in the Button Card editor.
BUILTIN_ACTIONS = [
    {"type": "TOGGLE", "label": "Toggle Button", "icon": "toggle-switch", "group": False},
    {"type": "HOTKEY", "label": "Momentary / Hotkey", "icon": "keyboard", "group": False},
    {"type": "SHORTCUT", "label": "App / Shortcut", "icon": "application", "group": False},
    {"type": "GROUP", "label": "Group (Sub-Panel)", "icon": "folder", "group": True},
    {"type": "SENSOR", "label": "Status / Sensor", "icon": "gauge", "group": False},
    {"type": "AUDIO OUTPUT", "label": "Audio Device Switcher", "icon": "volume-high", "group": False},
    {"type": "SCREENSHOT", "label": "Screenshot", "icon": "camera", "group": False},
    {"type": "NOTE", "label": "Quick Note", "icon": "note-text", "group": False},
    {"type": "EMPTY", "label": "Empty / Spacer", "icon": "border-none-variant", "group": False},
]

DEFAULT_UTILITY = [
    {"name": "Previous", "type": "MEDIA_PREV", "icon": "skip-previous", "color": ""},
    {"name": "Play/Pause", "type": "MEDIA_PLAY", "icon": "play-pause", "color": ""},
    {"name": "Next", "type": "MEDIA_NEXT", "icon": "skip-next", "color": ""},
    {"name": "Spotify", "type": "MEDIA_EJECT", "icon": "eject", "color": ""},
]

DEFAULT_SLIDERS = [
    {"id": "app_volume", "enabled": True},
    {"id": "master_volume", "enabled": True},
    {"id": "brightness", "enabled": True},
    {"id": "app_mixer", "enabled": True},
]

DEFAULT_LAYOUT = [
    {"id": "gauges", "enabled": True},
    {"id": "button_box", "enabled": True},
    {"id": "sliders", "enabled": True},
    {"id": "utility", "enabled": True},
]

DEFAULT_GAUGES = {"source": "pc_stats", "enabled": True}

_SLOT_KEYS = (
    "name", "type", "icon", "color", "shortcut_path", "shortcut_args", "app_icon_path", "hotkey", "keys", "entity", "entity_id", "children", "openrgb_profile",
    "profile_id", "profile", "value", "tap_action", "show_name", "show_icon", "show_state", "use_app_icon", "show_album_art",
    "audio_input_device_id", "audio_input_device_name",
    "audio_input_device_id_alt", "audio_input_device_name_alt",
    "audio_primary_icon", "audio_alt_icon",
    "plugin", "button_id", "widget_type", "state_key", "labels", "colors", "icon_off", "description",
    "screenshot_monitor",
)



def default_utility():
    return copy.deepcopy(DEFAULT_UTILITY)


def default_sliders():
    return copy.deepcopy(DEFAULT_SLIDERS)


def default_layout():
    return copy.deepcopy(DEFAULT_LAYOUT)


def default_gauges():
    return copy.deepcopy(DEFAULT_GAUGES)


def ensure_panel_defaults(cfg):
    """Fill missing panel keys on a live config dict (mutates)."""
    if not isinstance(cfg.get("panel_board"), list):
        cfg["panel_board"] = []
    if not isinstance(cfg.get("panel_profiles"), list):
        cfg["panel_profiles"] = []
    if not isinstance(cfg.get("panel_utility"), list) or len(cfg["panel_utility"]) != 4:
        cfg["panel_utility"] = default_utility()
    else:
        # Pad/truncate to 4
        u = list(cfg["panel_utility"])[:4]
        while len(u) < 4:
            u.append({"name": "", "type": "EMPTY", "icon": "border-none-variant", "color": ""})
        cfg["panel_utility"] = u
    if not isinstance(cfg.get("panel_sliders"), list):
        cfg["panel_sliders"] = default_sliders()
    if not isinstance(cfg.get("panel_layout"), list):
        cfg["panel_layout"] = default_layout()
    if not isinstance(cfg.get("panel_gauges"), dict):
        cfg["panel_gauges"] = default_gauges()
    return cfg


def sanitize_slot(raw, *, allow_group=True):
    """Return a cleaned slot dict or None."""
    if not isinstance(raw, dict):
        return None
    btype = str(raw.get("type") or "").strip()
    if not btype:
        return None
    if btype == "GROUP" and not allow_group:
        btype = "EMPTY"
    slot = {"type": btype}
    for k in _SLOT_KEYS:
        if k == "type":
            continue
        if k in raw and raw[k] is not None:
            slot[k] = raw[k]
    if "name" not in slot:
        slot["name"] = ""
    if "icon" not in slot:
        slot["icon"] = "help-circle"
    if "color" not in slot:
        slot["color"] = ""
    if btype in ("SHORTCUT", "EMPTY", "GROUP"):
        for ek in ("entity", "plugin", "button_id", "state_key", "labels", "colors", "show_state"):
            slot.pop(ek, None)
    elif not slot.get("entity") and not slot.get("plugin"):
        for ek in ("button_id", "state_key", "labels", "colors"):
            slot.pop(ek, None)
    if btype not in ("SHORTCUT", "GROUP"):
        slot.pop("shortcut_path", None)
        slot.pop("shortcut_args", None)
    if btype == "GROUP":
        kids = raw.get("children") or []
        if not isinstance(kids, list):
            kids = []
        slot["children"] = [s for s in (sanitize_slot(c, allow_group=True) for c in kids) if s]
    if btype == "HOTKEY":
        keys = slot.get("keys") or []
        if not isinstance(keys, list):
            keys = []
        slot["keys"] = [int(k) for k in keys if str(k).isdigit() or isinstance(k, int)]
    return slot


def sanitize_board(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        s = sanitize_slot(item, allow_group=True)
        if s:
            out.append(s)
    return out


def sanitize_profiles(raw):
    """Return a cleaned list of panel profiles."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip() or f"prof_{i + 1}"
        if pid in seen:
            n = 2
            while f"{pid}_{n}" in seen:
                n += 1
            pid = f"{pid}_{n}"
        seen.add(pid)
        exe = str(item.get("exe") or "").strip()
        name = str(item.get("name") or "").strip() or (exe or pid)
        out.append({
            "id": pid,
            "name": name,
            "exe": exe,
            "enabled": bool(item.get("enabled", True)),
            "lighting": item.get("lighting", {}) if isinstance(item.get("lighting"), dict) else {},
            "board": sanitize_board(item.get("board")),
        })
    return out


def foreground_exe():
    """Basename of the foreground process exe, or None."""
    try:
        from win_volume import get_foreground_pid
        pid = get_foreground_pid()
        if not pid:
            return None
        import psutil
        import os
        name = psutil.Process(pid).name()
        return os.path.basename(name) if name else None
    except Exception:
        return None


def _running_profile_exes(profiles):
    """Return set of lowercased exe basenames (no .exe) for profiles whose process is running."""
    running = set()
    try:
        from win_platform import get_running_process_names
        procs = {n.replace(".exe", "") for n in get_running_process_names(ttl=1.0)}
    except Exception:
        procs = set()
    for p in (profiles or []):
        if not isinstance(p, dict) or not p.get("enabled", True):
            continue
        pexe = str(p.get("exe") or "").lower().strip().replace(".exe", "")
        if not pexe:
            continue
        if pexe in procs:
            running.add(pexe)
    return running


import threading
_CACHE_LOCK = threading.Lock()
_RESOLVE_CACHE = {"sig": None, "ts": 0.0, "board": None, "active_ids": None, "fg": None, "cfg_ver": None}
_RESOLVE_TTL = 1.0


def resolve_panel_board(cfg):
    """Return (board, active_profile_ids, foreground_exe) for the live panel.

    Default panel_board is always included first. For every enabled profile whose
    exe process is currently running (resident in memory, regardless of focus),
    its action tiles are appended after the default board (each padded to the next
    12-button page boundary). Cached ~1s by the sorted running-exe signature.
    """
    import time as _t
    now = _t.time()

    profiles = cfg.get("panel_profiles") or []
    if not profiles:
        # Fast path: No profiles defined, skip process scans entirely
        fg = foreground_exe()
        return list(cfg.get("panel_board") or []), [], fg

    with _CACHE_LOCK:
        cache = _RESOLVE_CACHE
        if cache["board"] is not None and (now - cache["ts"]) < _RESOLVE_TTL:
            return cache["board"], cache["active_ids"], cache["fg"]

    fg = foreground_exe()
    running = _running_profile_exes(profiles)
    sig = tuple(sorted(running))

    # Compute dynamic page size based on gauges, active sliders, and utility row (6 or 7 total row budget)
    layout = {r.get("id"): r.get("enabled", True) for r in (cfg.get("panel_layout") or []) if isinstance(r, dict)}
    gauges_cfg = cfg.get("panel_gauges") or {}
    g_on = layout.get("gauges", True) and (gauges_cfg.get("enabled", True) if isinstance(gauges_cfg, dict) else True)
    util_on = layout.get("utility", True)
    util_rows = 1 if util_on else 0

    sliders = cfg.get("panel_sliders") or []
    show_sliders = cfg.get("show_sliders", True) and layout.get("sliders", True)
    active_sliders = 0
    if show_sliders:
        for s in sliders:
            if isinstance(s, dict) and s.get("enabled", True):
                active_sliders += 1
    slider_rows = 1 if active_sliders == 1 else (2 if active_sliders >= 2 else 0)
    base_budget = 6 if g_on else 7
    btn_rows = max(1, base_budget - util_rows - slider_rows)
    PAGE = btn_rows * 4

    default_board = list(cfg.get("panel_board") or [])
    combined = list(default_board)
    active_ids = []

    for p in (profiles or []):
        if not isinstance(p, dict) or not p.get("enabled", True):
            continue
        pexe = str(p.get("exe") or "").lower().strip().replace(".exe", "")
        if not pexe or pexe not in running:
            continue
        profile_board = list(p.get("board") or [])
        if not profile_board:
            continue
        # Pad to next dynamic page boundary so profile starts on a clean page
        rem = len(combined) % PAGE
        if rem != 0 or len(combined) == 0:
            pad_count = (PAGE - rem) if rem != 0 else PAGE
            for _ in range(pad_count):
                combined.append({"type": "EMPTY", "name": "", "icon": "border-none-variant", "color": ""})
        combined.extend(profile_board)
        active_ids.append(p.get("id"))

    with _CACHE_LOCK:
        cache["sig"] = sig
        cache["ts"] = now
        cache["board"] = combined
        cache["active_ids"] = active_ids
        cache["fg"] = fg
    return combined, active_ids, fg


def sanitize_utility(raw):
    base = default_utility()
    if not isinstance(raw, list):
        return base
    out = []
    for i in range(4):
        if i < len(raw) and isinstance(raw[i], dict):
            s = sanitize_slot(raw[i], allow_group=False)
            out.append(s or {"name": "", "type": "EMPTY", "icon": "border-none-variant", "color": ""})
        else:
            out.append(base[i] if i < len(base) else {
                "name": "", "type": "EMPTY", "icon": "border-none-variant", "color": ""
            })
    return out


def sanitize_sliders(raw):
    defaults = {d["id"]: d["enabled"] for d in DEFAULT_SLIDERS}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id") in defaults:
                defaults[item["id"]] = bool(item.get("enabled", True))
    return [{"id": k, "enabled": v} for k, v in defaults.items()]


def sanitize_layout(raw):
    defaults = {d["id"]: {"enabled": d["enabled"], "local": d.get("local", True), "remote": d.get("remote", True)} for d in DEFAULT_LAYOUT}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id") in defaults:
                entry = defaults[item["id"]]
                en = bool(item.get("enabled", True))
                loc = bool(item.get("local", en))
                rem = bool(item.get("remote", en))
                defaults[item["id"]] = {"enabled": loc or rem, "local": loc, "remote": rem}
    return [{"id": k, "enabled": v["enabled"], "local": v["local"], "remote": v["remote"]} for k, v in defaults.items()]


def sanitize_gauges(raw):
    g = default_gauges()
    if isinstance(raw, dict):
        if "enabled" in raw:
            g["enabled"] = bool(raw["enabled"])
        if raw.get("source"):
            g["source"] = str(raw["source"])
    return g


def layout_enabled(cfg, section_id, target="local"):
    ensure_panel_defaults(cfg)
    for item in cfg.get("panel_layout") or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            if target == "local":
                return bool(item.get("local", item.get("enabled", True)))
            elif target == "remote":
                return bool(item.get("remote", item.get("enabled", True)))
            return bool(item.get("enabled", True))
    return True


def slider_enabled(cfg, slider_id):
    ensure_panel_defaults(cfg)
    for item in cfg.get("panel_sliders") or []:
        if isinstance(item, dict) and item.get("id") == slider_id:
            return bool(item.get("enabled", True))
    return True


def action_catalog():
    """Generic action types for the Button Card editor."""
    return list(BUILTIN_ACTIONS)


def panel_payload(cfg):
    """Snapshot for GET /api/panel."""
    ensure_panel_defaults(cfg)
    hw = False
    try:
        from serial_comm import serial_sender
        hw = serial_sender.connected_port() is not None
    except Exception:
        pass
    if not hw:
        try:
            import ws_bridge
            app = getattr(ws_bridge, "_app", None)
            if app is not None:
                hw = bool(getattr(app, "_online", False))
        except Exception:
            pass
    return {
        "panel_board": cfg.get("panel_board") or [],
        "panel_profiles": cfg.get("panel_profiles") or [],
        "panel_utility": cfg.get("panel_utility") or default_utility(),
        "panel_sliders": cfg.get("panel_sliders") or default_sliders(),
        "panel_layout": cfg.get("panel_layout") or default_layout(),
        "panel_gauges": cfg.get("panel_gauges") or default_gauges(),
        "media_player_path": cfg.get("media_player_path") or "",
        "hardware_connected": hw,
        "actions": action_catalog(),
    }


def apply_panel_save(cfg, body):
    """Merge POST /api/panel body into cfg. Returns cfg."""
    if not isinstance(body, dict):
        return cfg
    if "panel_board" in body:
        cfg["panel_board"] = sanitize_board(body["panel_board"])
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None
    if "panel_profiles" in body:
        cfg["panel_profiles"] = sanitize_profiles(body["panel_profiles"])
        # Invalidate resolve cache so the next live poll picks up the edit.
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None
    if "panel_utility" in body:
        cfg["panel_utility"] = sanitize_utility(body["panel_utility"])
    if "panel_sliders" in body:
        cfg["panel_sliders"] = sanitize_sliders(body["panel_sliders"])
    if "panel_layout" in body:
        cfg["panel_layout"] = sanitize_layout(body["panel_layout"])
    if "panel_gauges" in body:
        cfg["panel_gauges"] = sanitize_gauges(body["panel_gauges"])
    if "media_player_path" in body:
        cfg["media_player_path"] = str(body.get("media_player_path") or "").strip()
    ensure_panel_defaults(cfg)
    return cfg
