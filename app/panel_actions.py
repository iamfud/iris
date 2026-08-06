"""Panel action catalog and defaults.

Shared by the Tk overlay (runtime) and the HTML Panel editor (config).
No plugin business logic — only builtin types plus discovered PLUGIN: controls.
"""

from __future__ import annotations

import copy
import logging

log = logging.getLogger("iris.panel_actions")

# Builtin action types available in the full picker.
BUILTIN_ACTIONS = [
    {"type": "SHORTCUT", "label": "App / Shortcut", "icon": "application", "group": False},
    {"type": "GROUP", "label": "Group (sub-panel)", "icon": "folder", "group": True},
    {"type": "REST", "label": "Home Assistant toggle", "icon": "home-assistant", "group": False},
    {"type": "HOTKEY", "label": "Hotkey", "icon": "keyboard", "group": False},
    {"type": "OPENRGB", "label": "OpenRGB profile (legacy)", "icon": "palette", "group": False},
    {"type": "AUDIO OUTPUT", "label": "Audio output toggle", "icon": "speaker", "group": False},
    {"type": "STOPWATCH", "label": "Stopwatch", "icon": "timer", "group": False},
    {"type": "MEDIA_PREV", "label": "Media previous", "icon": "skip-previous", "group": False},
    {"type": "MEDIA_PLAY", "label": "Media play/pause", "icon": "play-pause", "group": False},
    {"type": "MEDIA_NEXT", "label": "Media next", "icon": "skip-next", "group": False},
    {"type": "MEDIA_EJECT", "label": "Launch media player", "icon": "eject", "group": False},
    {"type": "EMPTY", "label": "Empty / spacer", "icon": "border-none-variant", "group": False},
]

DEFAULT_UTILITY = [
    {"name": "Previous", "type": "MEDIA_PREV", "icon": "skip-previous", "color": ""},
    {"name": "Play/Pause", "type": "MEDIA_PLAY", "icon": "play-pause", "color": ""},
    {"name": "Next", "type": "MEDIA_NEXT", "icon": "skip-next", "color": ""},
    {"name": "Player", "type": "MEDIA_EJECT", "icon": "eject", "color": ""},
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
    "name", "type", "icon", "color", "app_icon_path", "shortcut_path",
    "entity_id", "keys", "children", "openrgb_profile",
    "audio_input_device_id", "audio_input_device_name",
    "audio_input_device_id_alt", "audio_input_device_name_alt",
    "audio_primary_icon", "audio_alt_icon", "profile", "value",
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
    defaults = {d["id"]: d["enabled"] for d in DEFAULT_LAYOUT}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id") in defaults:
                defaults[item["id"]] = bool(item.get("enabled", True))
    return [{"id": k, "enabled": v} for k, v in defaults.items()]


def sanitize_gauges(raw):
    g = default_gauges()
    if isinstance(raw, dict):
        if "enabled" in raw:
            g["enabled"] = bool(raw["enabled"])
        if raw.get("source"):
            g["source"] = str(raw["source"])
    return g


def layout_enabled(cfg, section_id):
    ensure_panel_defaults(cfg)
    for item in cfg.get("panel_layout") or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            return bool(item.get("enabled", True))
    return True


def slider_enabled(cfg, slider_id):
    ensure_panel_defaults(cfg)
    for item in cfg.get("panel_sliders") or []:
        if isinstance(item, dict) and item.get("id") == slider_id:
            return bool(item.get("enabled", True))
    return True


def action_catalog():
    """Builtin types + discovered plugin controls for the picker."""
    items = list(BUILTIN_ACTIONS)
    try:
        import plugin_manager
        for name, manifest in plugin_manager.discover_plugins():
            display = manifest.get("display_name") or name
            for ctrl in manifest.get("controls") or []:
                cid = ctrl.get("id")
                if not cid:
                    continue
                items.append({
                    "type": f"PLUGIN:{name}:{cid}",
                    "label": f"{display}: {ctrl.get('label') or cid}",
                    "icon": ctrl.get("icon") or "puzzle",
                    "group": False,
                    "plugin": name,
                    "control_id": cid,
                    "fields": ctrl.get("fields") or ctrl.get("settings") or [],
                })
    except Exception:
        log.debug("plugin catalog failed", exc_info=True)
    return items


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
