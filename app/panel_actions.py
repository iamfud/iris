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
    {"type": "CORE", "label": "Iris Core Action", "icon": "star-circle", "group": False},
]

DEFAULT_UTILITY = [
    {
        "type": "HOTKEY",
        "name": "Previous",
        "icon": "skip-previous",
        "color": "",
        "hotkey": "",
        "keys": [],
        "entity": "media.prev",
        "show_name": True,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
        "plugin": "media",
        "button_id": "prev",
        "state_key": "prev",
    },
    {
        "type": "MEDIA_PLAY",
        "name": "Play/Pause",
        "icon": "play-pause",
        "color": "",
    },
    {
        "type": "MEDIA_NEXT",
        "name": "Next",
        "icon": "skip-next",
        "color": "",
    },
    {
        "type": "HOTKEY",
        "name": "Player",
        "icon": "application",
        "color": "",
        "hotkey": "",
        "keys": [],
        "entity": "media.player",
        "show_name": True,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": True,
        "show_album_art": True,
        "show_progress_fill": True,
        "plugin": "media",
        "button_id": "player",
        "state_key": "player",
    },
]

DEFAULT_CORE = [
    {
        "type": "CORE",
        "name": "Toolbar",
        "icon": "dock-top",
        "color": "",
        "show_name": True,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
        "core_action": "toolbar",
    },
    {
        "type": "CORE",
        "name": "Snipping Tool",
        "icon": "crop",
        "color": "",
        "show_name": True,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
        "core_action": "screenshot_zone",
    },
    {
        "type": "CORE",
        "name": "Screenshot",
        "icon": "camera",
        "color": "",
        "show_name": True,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
        "core_action": "screenshot",
    },
    {
        "type": "CORE",
        "name": "Settings",
        "icon": "cog",
        "color": "",
        "core_action": "settings",
    },
]

DEFAULT_SLIDERS = [
    {"id": "app_volume", "enabled": True},
    {"id": "master_volume", "enabled": True},
    {"id": "brightness", "enabled": True},
    {"id": "app_mixer", "enabled": True},
]

DEFAULT_LAYOUT = [
    {"id": "gauges", "enabled": True, "local": True, "remote": True},
    {"id": "button_box", "enabled": True, "local": True, "remote": True},
    {"id": "sliders", "enabled": True, "local": True, "remote": True},
    {"id": "utility", "enabled": True, "local": True, "remote": True},
]

DEFAULT_GAUGES = {"source": "pc_stats", "enabled": True}

DEFAULT_BOARD = [
    {
        "type": "GROUP",
        "name": "Lights",
        "icon": "lightbulb",
        "color": "",
        "hotkey": "",
        "keys": [],
        "children": [],
        "profile_id": "prof_2",
        "show_name": True,
        "show_icon": True,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
    },
    {
        "type": "CORE",
        "name": "Iris Note",
        "icon": "note-outline",
        "color": "",
        "show_name": False,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": False,
        "core_action": "note",
    },
    {
        "type": "AUDIO OUTPUT",
        "name": "Audio",
        "icon": "speaker",
        "color": "",
        "show_name": False,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": False,
        "audio_input_device_id": "",
        "audio_input_device_name": "",
        "audio_input_device_id_alt": "",
        "audio_input_device_name_alt": "",
        "audio_primary_icon": "speaker",
        "audio_alt_icon": "headphones",
    },
    {
        "type": "TOGGLE",
        "name": "Microphone Mute",
        "icon": "microphone",
        "color": "",
        "hotkey": "",
        "keys": [],
        "entity": "system.mic_mute",
        "show_name": False,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": False,
        "plugin": "system",
        "button_id": "mic_mute",
        "state_key": "mic_mute",
        "labels": {
            "on": "MUTED",
            "off": "UNMUTED",
        },
        "colors": {
            "on": "#48B2E9",
        },
    },
    {
        "type": "CORE",
        "name": "PC STATS",
        "icon": "speedometer",
        "color": "",
        "show_name": False,
        "show_icon": True,
        "show_state": False,
        "use_app_icon": False,
        "show_album_art": False,
        "show_progress_fill": True,
        "core_action": "overlay",
    },
]

DEFAULT_PROFILES = [
    {
        "id": "prof_elite_dangerous",
        "name": "Elite Dangerous",
        "exe": "EliteDangerous64.exe",
        "enabled": True,
        "theme": {
            "accent": "#ff5500",
            "neon": "#ffaa00",
        },
        "theme_override": True,
        "lighting_enabled": True,
        "lighting_theme_enabled": True,
        "lighting_alerts_enabled": True,
        "lighting": {},
        "board": [
            {
                "type": "TOGGLE",
                "name": "Landing Gear",
                "icon": "airplane-landing",
                "color": "#ffb703",
                "hotkey": "l",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "landing_gear",
                "widget_type": "status_toggle",
                "state_key": "landing_gear",
                "labels": {"on": "DOWN", "off": "UP"},
                "colors": {"on": "#ffaa00", "off": "#444444"},
                "icon_off": "airplane-takeoff",
            },
            {
                "type": "TOGGLE",
                "name": "Cargo Scoop",
                "icon": "bag-personal",
                "color": "#ffb703",
                "hotkey": "c",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "cargo_scoop",
                "widget_type": "status_toggle",
                "state_key": "cargo_scoop",
                "labels": {"on": "DEPLOYED", "off": "RETRACTED"},
                "colors": {"on": "#ffaa00", "off": "#444444"},
            },
            {
                "type": "TOGGLE",
                "name": "Flight Assist",
                "icon": "steering",
                "color": "#ffb703",
                "hotkey": "z",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "flight_assist",
                "widget_type": "status_toggle",
                "state_key": "flight_assist",
                "labels": {"on": "OFF", "off": "ON"},
                "colors": {"on": "#ff3355", "off": "#00ff88"},
            },
            {
                "type": "TOGGLE",
                "name": "Ship Lights",
                "icon": "flare",
                "color": "#ffb703",
                "hotkey": "insert",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "lights",
                "widget_type": "status_toggle",
                "state_key": "lights_on",
                "labels": {"on": "ON", "off": "OFF"},
                "colors": {"on": "#ffaa00", "off": "#444444"},
            },
            {
                "type": "TOGGLE",
                "name": "Hardpoints",
                "icon": "crosshairs",
                "color": "#ffb703",
                "hotkey": "u",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "hardpoints",
                "widget_type": "status_toggle",
                "state_key": "hardpoints",
                "labels": {"on": "DEPLOYED", "off": "RETRACTED"},
                "colors": {"on": "#ff3355", "off": "#444444"},
            },
            {
                "type": "TOGGLE",
                "name": "Night Vision",
                "icon": "eye",
                "color": "#ffb703",
                "hotkey": "num3",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "night_vision",
                "widget_type": "status_toggle",
                "state_key": "night_vision",
                "labels": {"on": "ON", "off": "OFF"},
                "colors": {"on": "#00ff88", "off": "#444444"},
            },
            {
                "type": "TOGGLE",
                "name": "Silent Running",
                "icon": "ghost",
                "color": "#ffb703",
                "hotkey": "Delete",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "silent_running",
                "widget_type": "status_toggle",
                "state_key": "silent_running",
                "labels": {"on": "ACTIVE", "off": "OFF"},
                "colors": {"on": "#ff3355", "off": "#444444"},
            },
            {
                "type": "TOGGLE",
                "name": "Supercruise",
                "icon": "rocket-launch",
                "color": "#ffb703",
                "hotkey": "tab",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "supercruise",
                "widget_type": "status_toggle",
                "state_key": "supercruise",
                "labels": {"on": "ACTIVE", "off": "IDLE"},
                "colors": {"on": "#48b2e9", "off": "#444444"},
            },
            {
                "type": "ACTION",
                "name": "Shields",
                "icon": "shield",
                "color": "#ffb703",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "shields",
                "widget_type": "display",
                "state_key": "shields_up",
                "labels": {"on": "ONLINE", "off": "DOWN"},
                "colors": {"on": "#00ff88", "off": "#ff3355"},
            },
            {
                "type": "ACTION",
                "name": "Mass Lock",
                "icon": "weight",
                "color": "#ffb703",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "mass_lock",
                "widget_type": "display",
                "state_key": "mass_locked",
                "labels": {"on": "LOCKED", "off": "CLEAR"},
                "colors": {"on": "#ff3355", "off": "#00ff88"},
            },
            {
                "type": "ACTION",
                "name": "FSD Charge",
                "icon": "speedometer",
                "color": "#ffb703",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "fsd_status",
                "widget_type": "display",
                "state_key": "fsd_charging",
                "labels": {"on": "CHARGING", "off": "READY"},
                "colors": {"on": "#ffaa00", "off": "#555555"},
            },
            {
                "type": "ACTION",
                "name": "Fuel Scoop",
                "icon": "gas-station",
                "color": "#ffb703",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "fuel_scoop",
                "widget_type": "display",
                "state_key": "scooping_fuel",
                "labels": {"on": "SCOOPING", "off": "IDLE"},
                "colors": {"on": "#ffee00", "off": "#555555"},
            },
            {
                "type": "ACTION",
                "name": "Jumps Remaining",
                "icon": "map-marker-path",
                "color": "#48b2e9",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "jumps_remaining",
                "widget_type": "display",
                "state_key": "jumps_remaining",
            },
            {
                "type": "ACTION",
                "name": "Route Destination",
                "icon": "flag-checkered",
                "color": "#48b2e9",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "plugin": "elite_dangerous",
                "button_id": "route_destination",
                "widget_type": "display",
                "state_key": "route_destination",
            },
        ],
    },
    {
        "id": "prof_2",
        "name": "Lights",
        "exe": "",
        "enabled": True,
        "theme": {},
        "theme_override": True,
        "lighting_enabled": True,
        "lighting_theme_enabled": True,
        "lighting_alerts_enabled": True,
        "lighting": {},
        "board": [
            {
                "type": "HOTKEY",
                "name": "Office Green",
                "icon": "script-text",
                "color": "#00ff88",
                "hotkey": "",
                "keys": [],
                "entity": "ha.script.office_green",
                "show_name": True,
                "show_icon": True,
                "show_state": False,
                "use_app_icon": False,
                "show_album_art": False,
                "show_progress_fill": True,
                "plugin": "ha",
                "button_id": "script.office_green",
                "state_key": "script.office_green",
                "colors": {
                    "on": "#48B2E9",
                },
            },
            {
                "type": "HOTKEY",
                "name": "Green (Device)",
                "icon": "palette",
                "color": "#00ff88",
                "hotkey": "",
                "keys": [],
                "entity": "openrgb.profile.green_device",
                "openrgb_profile": "Green (Device)",
                "show_name": True,
                "show_icon": True,
                "show_state": False,
                "use_app_icon": False,
                "show_album_art": False,
                "show_progress_fill": True,
                "plugin": "openrgb",
                "button_id": "profile",
                "state_key": "active_profile",
                "labels": {
                    "on": "ACTIVE",
                    "off": "IDLE",
                },
                "colors": {
                    "on": "#00ff88",
                },
            },
        ],
    },
]

_SLOT_KEYS = (
    "name", "type", "icon", "color", "shortcut_path", "shortcut_args", "app_icon_path", "hotkey", "keys", "entity", "entity_id", "children", "openrgb_profile",
    "profile_id", "profile", "value", "tap_action", "show_name", "show_icon", "show_state", "use_app_icon", "show_album_art",
    "show_progress_fill", "fill_min", "fill_max",
    "audio_input_device_id", "audio_input_device_name",
    "audio_input_device_id_alt", "audio_input_device_name_alt",
    "audio_primary_icon", "audio_alt_icon",
    "plugin", "button_id", "widget_type", "state_key", "labels", "colors", "icon_off", "description",
    "screenshot_monitor", "capture_mode", "core_action",
    "macro", "actions", "delay_s",
)



def default_utility():
    return copy.deepcopy(DEFAULT_UTILITY)


def default_core():
    return copy.deepcopy(DEFAULT_CORE)


def default_sliders():
    return copy.deepcopy(DEFAULT_SLIDERS)


def default_layout():
    return copy.deepcopy(DEFAULT_LAYOUT)


def default_gauges():
    return copy.deepcopy(DEFAULT_GAUGES)


def default_board():
    return copy.deepcopy(DEFAULT_BOARD)


def default_profiles():
    return copy.deepcopy(DEFAULT_PROFILES)


def ensure_panel_defaults(cfg):
    """Fill missing panel keys on a live config dict (mutates)."""
    if "panel_board" not in cfg or cfg.get("panel_board") is None or not isinstance(cfg.get("panel_board"), list) or len(cfg.get("panel_board")) == 0:
        cfg["panel_board"] = default_board()
    if "panel_profiles" not in cfg or cfg.get("panel_profiles") is None or not isinstance(cfg.get("panel_profiles"), list) or len(cfg.get("panel_profiles")) == 0:
        cfg["panel_profiles"] = default_profiles()
    if not isinstance(cfg.get("panel_utility"), list) or len(cfg["panel_utility"]) != 4:
        cfg["panel_utility"] = default_utility()
    else:
        # Pad/truncate to 4
        u = list(cfg["panel_utility"])[:4]
        while len(u) < 4:
            u.append({"name": "", "type": "EMPTY", "icon": "border-none-variant", "color": ""})
        cfg["panel_utility"] = u
    if not isinstance(cfg.get("panel_core"), list) or len(cfg["panel_core"]) != 4:
        cfg["panel_core"] = default_core()
    else:
        u = list(cfg["panel_core"])[:4]
        while len(u) < 4:
            u.append({"name": "", "type": "EMPTY", "icon": "border-none-variant", "color": ""})
        cfg["panel_core"] = u
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
    if btype in ("EMPTY", "GROUP"):
        for ek in ("entity", "plugin", "button_id", "state_key", "labels", "colors", "show_state"):
            slot.pop(ek, None)
    elif not slot.get("entity") and not slot.get("plugin"):
        for ek in ("button_id", "state_key", "labels", "colors"):
            slot.pop(ek, None)
    if btype not in ("SHORTCUT", "GROUP", "HOTKEY", "MACRO") and not slot.get("shortcut_path"):
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


def sanitize_automations(raw):
    """Return a cleaned list of automation rules."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        name = str(item.get("name") or "Automation").strip()
        trigger_key = str(item.get("trigger_key") or "").strip()
        if not trigger_key:
            continue
        actions = item.get("actions") or []
        clean_actions = []
        if isinstance(actions, list):
            for a in actions:
                if isinstance(a, dict) and a.get("type"):
                    clean_actions.append(dict(a))
        out.append({
            "id": rid,
            "name": name,
            "enabled": bool(item.get("enabled", True)),
            "trigger_key": trigger_key,
            "operator": str(item.get("operator") or "=="),
            "target_value": item.get("target_value"),
            "require_foreground": bool(item.get("require_foreground", True)),
            "cooldown_s": float(item.get("cooldown_s", 10.0)),
            "actions": clean_actions,
            "profile_id": str(item.get("profile_id") or ""),
            "exe": str(item.get("exe") or ""),
        })
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
        theme_dict = item.get("theme")
        if not isinstance(theme_dict, dict):
            theme_dict = {}
        out.append({
            "id": pid,
            "name": name,
            "exe": exe,
            "enabled": bool(item.get("enabled", True)),
            "theme": {
                "accent": str(theme_dict.get("accent") or "").strip(),
                "neon": str(theme_dict.get("neon") or "").strip(),
            } if theme_dict else {},
            "theme_override": bool(item.get("theme_override", True)),
            "lighting_enabled": bool(item.get("lighting_enabled", True)),
            "lighting_theme_enabled": bool(item.get("lighting_theme_enabled", True)),
            "lighting_alerts_enabled": bool(item.get("lighting_alerts_enabled", True)),
            "auto_switch": bool(item.get("auto_switch", True)),
            "latch_while_running": bool(item.get("latch_while_running", True)),
            "lighting": item.get("lighting", {}) if isinstance(item.get("lighting"), dict) else {},
            "board": sanitize_board(item.get("board")),
            "automations": sanitize_automations(item.get("automations")),
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
    import os
    running = set()
    try:
        from win_platform import get_running_process_names
        procs = {n.replace(".exe", "") for n in get_running_process_names(ttl=1.0)}
    except Exception:
        procs = set()
    for p in (profiles or []):
        if not isinstance(p, dict) or not p.get("enabled", True):
            continue
        raw_exe = str(p.get("exe") or "").strip()
        pexe = os.path.basename(raw_exe.replace("\\", "/")).lower().replace(".exe", "")
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


def sanitize_core(raw):
    base = default_core()
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
        "panel_core": cfg.get("panel_core") or default_core(),
        "panel_sliders": cfg.get("panel_sliders") or default_sliders(),
        "panel_layout": cfg.get("panel_layout") or default_layout(),
        "panel_gauges": cfg.get("panel_gauges") or default_gauges(),
        "media_player_path": cfg.get("media_player_path") or "",
        "hardware_connected": hw,
        "actions": action_catalog(),
        "default_profile_name": cfg.get("default_profile_name") or "",
        "panel_default_automations": sanitize_automations(cfg.get("panel_default_automations") or []),
    }


def apply_panel_save(cfg, body):
    """Merge POST /api/panel body into cfg. Returns cfg."""
    if not isinstance(body, dict):
        return cfg
    if "default_profile_name" in body:
        cfg["default_profile_name"] = str(body.get("default_profile_name") or "").strip()
    if "panel_board" in body:
        cfg["panel_board"] = sanitize_board(body["panel_board"])
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None
    if "panel_profiles" in body:
        cfg["panel_profiles"] = sanitize_profiles(body["panel_profiles"])
        # Invalidate resolve cache so the next live poll picks up the edit.
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None
    if "panel_default_automations" in body:
        cfg["panel_default_automations"] = sanitize_automations(body["panel_default_automations"])
    if "panel_utility" in body:
        cfg["panel_utility"] = sanitize_utility(body["panel_utility"])
    if "panel_core" in body:
        cfg["panel_core"] = sanitize_core(body["panel_core"])
    if "panel_sliders" in body:
        cfg["panel_sliders"] = sanitize_sliders(body["panel_sliders"])
    if "panel_layout" in body:
        cfg["panel_layout"] = sanitize_layout(body["panel_layout"])
    if "panel_gauges" in body:
        cfg["panel_gauges"] = sanitize_gauges(body["panel_gauges"])
    if "media_player_path" in body:
        cfg["media_player_path"] = str(body.get("media_player_path") or "").strip()
    ensure_panel_defaults(cfg)
    if "panel_profiles" in body or "panel_default_automations" in body:
        try:
            import automations
            automations.get_engine().load_config(cfg)
        except Exception:
            pass
    return cfg
