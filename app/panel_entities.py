"""Iris — Entity Registry.

Discovers and aggregates status and data entities across Core and Plugins.
Provides standardized entity metadata (status, data, capabilities, labels, defaults)
for the Generic Button Card editor and Panel Runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("iris.panel_entities")


def get_core_entities() -> List[Dict[str, Any]]:
    """Return builtin Core system, media, and PC telemetry entities."""
    return [
        # ── System (Status Toggles & Actions) ────────────────────
        {
            "id": "system.lighting_sync",
            "domain": "System",
            "plugin": "system",
            "button_id": "lighting_sync",
            "state_key": "lighting_sync",
            "name": "Lighting Sync",
            "type": "status",
            "icon": "lightbulb",
            "icon_off": "lightbulb-outline",
            "color": "#48B2E9",
            "labels": {"on": "ACTIVE", "off": "OFF"},
            "writable": True,
            "default_action": "toggle_lighting_sync",
            "description": "Toggle automatic ambient lighting & profile sync",
        },
        {
            "id": "system.display",
            "domain": "System",
            "plugin": "system",
            "button_id": "display",
            "state_key": "display",
            "name": "Companion Display",
            "type": "status",
            "icon": "desktop-tower-monitor",
            "color": "#48B2E9",
            "labels": {"on": "ON", "off": "OFF"},
            "writable": True,
            "default_action": "toggle_display",
            "description": "Toggle physical Iris companion display",
        },
        {
            "id": "system.overlay",
            "domain": "System",
            "plugin": "system",
            "button_id": "overlay",
            "state_key": "overlay",
            "name": "PC Stats Overlay",
            "type": "status",
            "icon": "picture-in-picture-bottom-right",
            "color": "#48B2E9",
            "labels": {"on": "ACTIVE", "off": "HIDDEN"},
            "writable": True,
            "default_action": "toggle_overlay",
            "description": "Toggle desktop PC gauges/stats overlay window",
        },
        {
            "id": "system.toolbar",
            "domain": "System",
            "plugin": "system",
            "button_id": "toolbar",
            "state_key": "toolbar",
            "name": "Toolbar",
            "type": "status",
            "icon": "dock-top",
            "color": "#48B2E9",
            "labels": {"on": "OPEN", "off": "CLOSED"},
            "writable": True,
            "default_action": "toggle_toolbar",
            "description": "Toggle desktop capture & actions top toolbar",
        },
        {
            "id": "system.mic_mute",
            "domain": "System",
            "plugin": "system",
            "button_id": "mic_mute",
            "state_key": "mic_mute",
            "name": "Microphone Mute",
            "type": "status",
            "icon": "microphone",
            "icon_off": "microphone-off",
            "color": "#48B2E9",
            "labels": {"on": "MUTED", "off": "UNMUTED"},
            "writable": True,
            "default_action": "mic_mute",
            "description": "Toggle default recording microphone mute",
        },
        {
            "id": "system.settings",
            "domain": "System",
            "plugin": "system",
            "button_id": "settings",
            "state_key": "settings",
            "name": "Open Settings",
            "type": "action",
            "icon": "cog",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "open_settings",
            "description": "Open Iris web settings and portal",
        },
        {
            "id": "time.str",
            "domain": "Time",
            "plugin": "time",
            "button_id": "str",
            "state_key": "str",
            "name": "Time of Day (HH:MM)",
            "type": "data",
            "data_type": "string",
            "icon": "clock-outline",
            "color": "#48B2E9",
            "unit": "",
            "writable": False,
            "default_action": "",
            "description": "Current wall-clock time in 24-hour HH:MM format (e.g. 16:00)",
        },
        {
            "id": "time.hour",
            "domain": "Time",
            "plugin": "time",
            "button_id": "hour",
            "state_key": "hour",
            "name": "Hour (0-23)",
            "type": "data",
            "data_type": "number",
            "icon": "clock-outline",
            "color": "#48B2E9",
            "unit": "h",
            "writable": False,
            "default_action": "",
            "description": "Current hour of day, 0-23",
        },
        {
            "id": "time.minute",
            "domain": "Time",
            "plugin": "time",
            "button_id": "minute",
            "state_key": "minute",
            "name": "Minute (0-59)",
            "type": "data",
            "data_type": "number",
            "icon": "clock-outline",
            "color": "#48B2E9",
            "unit": "min",
            "writable": False,
            "default_action": "",
            "description": "Current minute of the hour, 0-59",
        },
        {
            "id": "time.now",
            "domain": "Time",
            "plugin": "time",
            "button_id": "now",
            "state_key": "now",
            "name": "Clock Time (seconds)",
            "type": "data",
            "data_type": "number",
            "icon": "clock-outline",
            "color": "#48B2E9",
            "unit": "",
            "writable": False,
            "default_action": "",
            "description": "Current epoch time in seconds",
        },
        {
            "id": "time.hourminute",
            "domain": "Time",
            "plugin": "time",
            "button_id": "hourminute",
            "state_key": "hourminute",
            "name": "Time (HHMM numeric)",
            "type": "data",
            "data_type": "number",
            "icon": "clock-outline",
            "color": "#48B2E9",
            "unit": "",
            "writable": False,
            "default_action": "",
            "description": "Current time as 4-digit number: 1400 = 2:00 PM, 900 = 9:00 AM",
        },
        {
            "id": "system.colour_picker",
            "domain": "System",
            "plugin": "system",
            "button_id": "colour_picker",
            "state_key": "colour_picker",
            "name": "Colour Picker",
            "type": "action",
            "icon": "eyedropper",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "colour_picker",
            "description": "Grab a colour from the screen with the round-grid eyedropper",
        },
        {
            "id": "system.screenshot",
            "domain": "System",
            "plugin": "system",
            "button_id": "screenshot",
            "state_key": "screenshot",
            "name": "Screenshot",
            "type": "action",
            "icon": "camera",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "screenshot",
            "description": "Capture an instant fullscreen screenshot",
        },
        {
            "id": "system.screenshot_zone",
            "domain": "System",
            "plugin": "system",
            "button_id": "screenshot_zone",
            "state_key": "screenshot_zone",
            "name": "Snipping Tool",
            "type": "action",
            "icon": "crop",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "screenshot_zone",
            "description": "Drag rectangular crosshairs to snip a screen zone",
        },
        {
            "id": "system.borderless_toggle",
            "domain": "System",
            "plugin": "system",
            "button_id": "borderless_toggle",
            "state_key": "borderless_toggle",
            "name": "Toggle Borderless",
            "type": "action",
            "icon": "window-maximize",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "borderless_toggle",
            "description": "Toggle active game/window between windowed and borderless fullscreen",
        },

        # ── Media Controls (Momentary Actions) ───────────────────
        {
            "id": "media.play_pause",
            "domain": "Media",
            "plugin": "media",
            "button_id": "play_pause",
            "state_key": "play_pause",
            "name": "Play / Pause",
            "type": "action",
            "icon": "play-pause",
            "color": "",
            "writable": True,
            "default_action": "media_play_pause",
            "description": "Toggle media playback",
        },
        {
            "id": "media.next",
            "domain": "Media",
            "plugin": "media",
            "button_id": "next",
            "state_key": "next",
            "name": "Next Track",
            "type": "action",
            "icon": "skip-next",
            "color": "",
            "writable": True,
            "default_action": "media_next",
            "description": "Skip to next media track",
        },
        {
            "id": "media.prev",
            "domain": "Media",
            "plugin": "media",
            "button_id": "prev",
            "state_key": "prev",
            "name": "Previous Track",
            "type": "action",
            "icon": "skip-previous",
            "color": "",
            "writable": True,
            "default_action": "media_prev",
            "description": "Go to previous media track",
        },
        {
            "id": "media.player",
            "domain": "Media",
            "plugin": "media",
            "button_id": "player",
            "state_key": "player",
            "name": "Media Player",
            "type": "action",
            "icon": "eject",
            "color": "",
            "writable": True,
            "default_action": "media_eject",
            "description": "Launch configured default media player",
        },

        # ── PC Telemetry & Sensors ───────────────────────────────
        {
            "id": "pc_stats.cpu_temp",
            "domain": "PC Stats",
            "name": "CPU Temperature",
            "type": "data",
            "icon": "cpu-64-bit",
            "color": "#ffb703",
            "unit": "°C",
            "writable": False,
            "description": "Live CPU package temperature",
        },
        {
            "id": "pc_stats.gpu_temp",
            "domain": "PC Stats",
            "name": "GPU Temperature",
            "type": "data",
            "icon": "expansion-card",
            "color": "#00ff88",
            "unit": "°C",
            "writable": False,
            "description": "Live GPU core temperature",
        },
        {
            "id": "pc_stats.fps",
            "domain": "PC Stats",
            "name": "Game Framerate",
            "type": "data",
            "icon": "speedometer",
            "color": "#48B2E9",
            "unit": "FPS",
            "writable": False,
            "description": "RTSS game framerate",
        },
        {
            "id": "pc_stats.cpu_usage",
            "domain": "PC Stats",
            "name": "CPU Usage",
            "type": "data",
            "icon": "chip",
            "color": "#ffb703",
            "unit": "%",
            "writable": False,
            "description": "Total CPU utilization percentage",
        },
        {
            "id": "pc_stats.ram_usage",
            "domain": "PC Stats",
            "name": "RAM Usage",
            "type": "data",
            "icon": "memory",
            "color": "#00ff88",
            "unit": "%",
            "writable": False,
            "description": "System memory utilization percentage",
        },
    ]


def get_plugin_entities() -> List[Dict[str, Any]]:
    """Discover entities exposed by installed plugins."""
    entities: List[Dict[str, Any]] = []
    try:
        import plugin_manager
        for name, manifest in plugin_manager.discover_plugins():
            domain = manifest.get("display_name") or name.replace("_", " ").title()

            # 1. Buttons / Controls defined in manifest
            for btn in manifest.get("buttons") or []:
                bid = btn.get("id")
                if not bid:
                    continue
                ent_id = f"{name}.{bid}"
                w_type = btn.get("widget_type", "status_toggle")
                ent_type = "status" if "toggle" in w_type or "status" in w_type else "data"
                entities.append({
                    "id": ent_id,
                    "plugin": name,
                    "button_id": bid,
                    "domain": domain,
                    "name": btn.get("name") or bid.replace("_", " ").title(),
                    "type": ent_type,
                    "icon": btn.get("icon") or "puzzle",
                    "icon_off": btn.get("icon_off") or "",
                    "color": (btn.get("colors") or {}).get("on") or "#00ff88",
                    "labels": btn.get("labels") or {"on": "ON", "off": "OFF"},
                    "writable": bool(btn.get("default_hotkey") or btn.get("writable", True)),
                    "default_hotkey": btn.get("default_hotkey") or "",
                    "state_key": btn.get("state_key") or bid,
                    "description": btn.get("description") or "",
                    "display_mode": btn.get("display_mode", ""),
                    "max_key": btn.get("max_key", ""),
                    "unit": btn.get("unit", ""),
                    "min": btn.get("min", 0),
                    "max": btn.get("max", None),
                })

            # 2. Momentary Actions defined in manifest
            for act in manifest.get("actions") or []:
                aid = act.get("id") if isinstance(act, dict) else str(act)
                if not aid:
                    continue
                ent_id = f"{name}.{aid}"
                if any(e["id"] == ent_id for e in entities):
                    continue
                entities.append({
                    "id": ent_id,
                    "plugin": name,
                    "action_id": aid,
                    "domain": domain,
                    "name": act.get("label") or act.get("name") or aid.replace("_", " ").title() if isinstance(act, dict) else aid.replace("_", " ").title(),
                    "type": "action",
                    "icon": act.get("icon") or "gesture-tap-button" if isinstance(act, dict) else "gesture-tap-button",
                    "color": "#48B2E9",
                    "writable": True,
                    "default_action": f"{name}_{aid}",
                    "description": act.get("description") or "" if isinstance(act, dict) else "",
                })

            # 3. Live Data / Sensors defined in manifest
            live_data = manifest.get("live_data") or {}
            raw_fields = live_data.get("fields") or {}
            field_items = []
            if isinstance(raw_fields, dict):
                field_items.extend(list(raw_fields.items()))
            elif isinstance(raw_fields, list):
                for f in raw_fields:
                    if isinstance(f, dict) and (f.get("key") or f.get("id")):
                        field_items.append((f.get("key") or f.get("id"), f))
            
            # Support nested live_data layout sections
            for section in live_data.get("layout") or []:
                if isinstance(section, dict):
                    sec_fields = section.get("fields") or []
                    for f in sec_fields:
                        if isinstance(f, dict) and (f.get("key") or f.get("id")):
                            field_items.append((f.get("key") or f.get("id"), f))

            for sid, sdef in field_items:
                if not sid:
                    continue
                ent_id = f"{name}.{sid}"
                if any(e["id"] == ent_id for e in entities):
                    continue
                raw_dtype = (sdef.get("type") or "string").lower() if isinstance(sdef, dict) else "string"
                if raw_dtype in ("percentage", "float", "integer", "number"):
                    vtype = "number"
                elif raw_dtype in ("boolean", "bool", "status", "toggle"):
                    vtype = "boolean"
                else:
                    vtype = "string"
                entities.append({
                    "id": ent_id,
                    "plugin": name,
                    "domain": domain,
                    "name": (sdef.get("label") or sdef.get("name") or sid.replace("_", " ").title()) if isinstance(sdef, dict) else sid.replace("_", " ").title(),
                    "type": "data",
                    "data_type": vtype,
                    "raw_data_type": raw_dtype,
                    "icon": (sdef.get("icon") or "gauge") if isinstance(sdef, dict) else "gauge",
                    "color": "#48B2E9",
                    "unit": (sdef.get("unit") or "") if isinstance(sdef, dict) else "",
                    "writable": False,
                    "description": (sdef.get("description") or "") if isinstance(sdef, dict) else "",
                })

            # 4. OpenRGB Profiles
            if name == "openrgb":
                profiles = []
                inst = plugin_manager.get(name)
                if inst and hasattr(inst, "get_options"):
                    try:
                        profiles = inst.get_options("openrgb_profiles") or []
                    except Exception:
                        pass
                if not profiles:
                    try:
                        from plugins.openrgb.connector import OpenRGBConnector
                        conn = OpenRGBConnector()
                        profiles = conn.get_options("openrgb_profiles")
                    except Exception:
                        pass
                for p in profiles:
                    clean_id = p.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("[", "").replace("]", "")
                    ent_id = f"openrgb.profile.{clean_id}"
                    if not any(e["id"] == ent_id for e in entities):
                        entities.append({
                            "id": ent_id,
                            "plugin": "openrgb",
                            "button_id": "profile",
                            "domain": "OpenRGB",
                            "name": p,
                            "type": "action",
                            "icon": "palette",
                            "color": "#00ff88",
                            "writable": True,
                            "openrgb_profile": p,
                            "default_action": "openrgb_profile",
                            "state_key": "active_profile",
                            "labels": {"on": "ACTIVE", "off": "IDLE"},
                            "description": f"Switch OpenRGB to '{p}' profile",
                        })
            # 5. Home Assistant Controllable Entities
            if name == "ha":
                ha_entities = []
                inst = plugin_manager.get(name)
                if inst and hasattr(inst, "get_entities"):
                    try:
                        ha_entities = inst.get_entities() or []
                    except Exception:
                        pass
                if not ha_entities:
                    try:
                        from plugins.ha.connector import HASSConnector
                        conn = HASSConnector(plugin_manager._cfg)
                        ha_entities = conn.get_entities()
                    except Exception:
                        pass
                
                DOM_ICONS = {
                    "light": "lightbulb",
                    "switch": "power",
                    "scene": "palette-swatch",
                    "script": "script-text",
                    "sun": "weather-sunny",
                    "climate": "thermostat",
                }
                for he in ha_entities:
                    eid = he.get("entity_id", "")
                    hdom = he.get("domain", "ha")
                    fname = he.get("friendly_name") or eid
                    ent_id = f"ha.{eid}"
                    if not any(e["id"] == ent_id for e in entities):
                        is_writable = hdom in ("light", "switch", "scene", "script", "climate", "input_boolean")
                        entities.append({
                            "id": ent_id,
                            "plugin": "ha",
                            "button_id": eid,
                            "domain": f"Home Assistant ({hdom.title()})",
                            "name": fname,
                            "type": "action" if is_writable else "data",
                            "data_type": "string" if not is_writable else None,
                            "icon": DOM_ICONS.get(hdom, "home-automation"),
                            "color": "#48B2E9",
                            "writable": is_writable,
                            "ha_entity_id": eid,
                            "ha_domain": hdom,
                            "default_action": "ha_toggle",
                            "state_key": eid,
                            "description": f"Home Assistant {hdom}: {fname}",
                        })
    except Exception as e:
        log.debug("Plugin entity discovery failed: %s", e)

    return entities


def get_entity_registry() -> List[Dict[str, Any]]:
    """Return full unified entity registry (Core + Plugins)."""
    registry = list(get_core_entities())
    registry.extend(get_plugin_entities())
    return registry


def get_entity(entity_id: str) -> Optional[Dict[str, Any]]:
    """Return a single entity definition by ID or None."""
    if not entity_id:
        return None
    for e in get_entity_registry():
        if e.get("id") == entity_id or e.get("state_key") == entity_id:
            return e
    return None


def get_live_entity_states(plugin_button_states=None) -> Dict[str, Dict[str, Any]]:
    """Return dictionary of {entity_id: {"active": bool, "label": str, ...}} for live UI binding."""
    states: Dict[str, Dict[str, Any]] = {}

    # Synthetic Time entities (wall-clock, Core/Time domain — no plugin dependency)
    try:
        import time as _time
        _lt = _time.localtime()
        _hhmm = f"{_lt.tm_hour:02d}:{_lt.tm_min:02d}"
        _hhmm_num = _lt.tm_hour * 100 + _lt.tm_min
        states["time.str"] = {"value": _hhmm, "label": _hhmm}
        states["time.hour"] = {"value": _lt.tm_hour, "label": f"{_lt.tm_hour}h"}
        states["time.minute"] = {"value": _lt.tm_min, "label": f"{_lt.tm_min}min"}
        states["time.hourminute"] = {"value": _hhmm_num, "label": str(_hhmm_num)}
        states["time.now"] = {"value": int(_time.time()), "label": str(int(_time.time()))}
    except Exception:
        pass

    # Hardware connected
    try:
        from main import get_serial_comm
        sc = get_serial_comm()
        states["system.display"] = {
            "active": bool(sc and sc.is_connected),
            "label": "ON" if (sc and sc.is_connected) else "OFF",
        }
    except Exception:
        pass

    # Core states
    try:
        from ws_bridge import _app
        if _app is not None:
            # Lighting Sync state
            ambient_cfg = getattr(_app, "cfg", {}).get("ambient_lighting") or {}
            is_lighting_on = ambient_cfg.get("enabled", True) is not False
            states["system.lighting_sync"] = {
                "active": is_lighting_on,
                "label": "ACTIVE" if is_lighting_on else "OFF",
                "value": is_lighting_on,
            }
            states["system.overlay"] = {
                "active": bool(getattr(_app, "_overlay_shown", False)),
                "label": "ACTIVE" if getattr(_app, "_overlay_shown", False) else "HIDDEN",
                "value": bool(getattr(_app, "_overlay_shown", False)),
            }
            # Toolbar state
            mw = getattr(_app, "_main_win", None)
            tb = getattr(mw, "_capture_toolbar", None) if mw else None
            is_tb_open = bool(tb and getattr(tb, "_visible", False))
            states["system.toolbar"] = {
                "active": is_tb_open,
                "label": "OPEN" if is_tb_open else "CLOSED",
                "value": is_tb_open,
            }
            # Microphone Mute
            from win_platform import get_mic_mute_state
            is_mic_muted = get_mic_mute_state()
            if is_mic_muted is not None:
                states["system.mic_mute"] = {
                    "active": bool(is_mic_muted),
                    "label": "MUTED" if is_mic_muted else "UNMUTED",
                    "value": bool(is_mic_muted),
                }

            # PC Stats live telemetry
            stats_prov = getattr(_app, "_stats_provider", None)
            if stats_prov is not None:
                st = getattr(stats_prov, "last_stats", {}) or {}
                if "cpu_temp" in st:
                    states["pc_stats.cpu_temp"] = {"value": st["cpu_temp"], "label": f"{st['cpu_temp']}°C"}
                if "gpu_temp" in st:
                    states["pc_stats.gpu_temp"] = {"value": st["gpu_temp"], "label": f"{st['gpu_temp']}°C"}
                if "fps" in st:
                    states["pc_stats.fps"] = {"value": st["fps"], "label": f"{st['fps']} FPS"}
                if "cpu_usage" in st:
                    states["pc_stats.cpu_usage"] = {"value": st["cpu_usage"], "label": f"{st['cpu_usage']}%"}
                if "ram_usage" in st:
                    states["pc_stats.ram_usage"] = {"value": st["ram_usage"], "label": f"{st['ram_usage']}%"}
    except Exception:
        pass

    # Media Player
    try:
        from ws_bridge import _app as _app_ref
        media_prov = getattr(_app_ref, "_media_provider", None)
        if media_prov is None and getattr(_app_ref, "_providers", None):
            for p in _app_ref._providers:
                if hasattr(p, "get_artwork"):
                    media_prov = p
                    break
        if media_prov is not None:
            m_data = media_prov.poll_data() if hasattr(media_prov, "poll_data") else {}
            if m_data:
                status = m_data.get("playback_status") or m_data.get("status")
                is_playing = (status == "playing")
                states["media.player"] = {
                    "active": is_playing,
                    "status": status,
                    "title": m_data.get("title", ""),
                    "artist": m_data.get("artist", ""),
                    "album": m_data.get("album", ""),
                    "has_art": bool(m_data.get("has_art")),
                    "art_id": m_data.get("art_id", ""),
                    "label": (m_data.get("title") or "Player")[:14],
                }
                states["media.play_pause"] = {
                    "active": is_playing,
                    "label": "PAUSE" if is_playing else "PLAY",
                }
    except Exception:
        pass

    # OpenRGB active profile states
    try:
        import plugin_manager
        inst = plugin_manager.get("openrgb")
        if inst and hasattr(inst, "poll"):
            p_poll = inst.poll()
            act_prof = p_poll.get("active_profile") or ""
            for prof in (p_poll.get("profiles") or []):
                clean_id = prof.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("[", "").replace("]", "")
                clean_prof = prof.replace(" (Device)", "").replace(" (Effect)", "").strip().lower()
                clean_act = act_prof.replace(" (Device)", "").replace(" (Effect)", "").strip().lower()
                is_active = (clean_prof == clean_act) if (clean_prof and clean_act) else False
                states[f"openrgb.profile.{clean_id}"] = {
                    "active": is_active,
                    "label": "ACTIVE" if is_active else "IDLE",
                    "value": is_active,
                }
    except Exception:
        pass

    # Plugin button states
    try:
        if plugin_button_states is None:
            import plugin_manager
            p_states = plugin_manager.get_plugin_button_states()
        else:
            p_states = plugin_button_states
        for k, v in p_states.items():
            # key is "plugin:button_id"
            ent_id = k.replace(":", ".")
            states[ent_id] = v
            states[k] = v  # legacy alias
    except Exception:
        pass

    # Plugin live data & telemetry sensors
    try:
        import plugin_manager
        for pname, inst in getattr(plugin_manager, "_instances", {}).items():
            if not hasattr(inst, "poll"):
                continue
            polled = inst.poll()
            if not isinstance(polled, dict):
                continue
            manifest = plugin_manager.get_manifest(pname) or {}
            live_data = manifest.get("live_data") or {}
            raw_fields = live_data.get("fields") or []
            
            field_map = {}
            if isinstance(raw_fields, list):
                for f in raw_fields:
                    if isinstance(f, dict) and (f.get("key") or f.get("id")):
                        field_map[f.get("key") or f.get("id")] = f
            elif isinstance(raw_fields, dict):
                field_map = raw_fields

            state_data = polled.get("state") if isinstance(polled.get("state"), dict) else polled
            for k, val in state_data.items():
                if k in ("available", "state", "status", "layout", "fields"):
                    continue
                fdef = field_map.get(k) or {}
                unit = fdef.get("unit") or ""
                val_str = f"{val} {unit}".strip() if unit else str(val)
                ent_id = f"{pname}.{k}"
                if ent_id not in states:
                    states[ent_id] = {
                        "value": val,
                        "label": val_str,
                        "unit": unit,
                        "min": fdef.get("min", 0),
                        "max": fdef.get("max", 100 if fdef.get("type") == "percentage" else None),
                        "active": bool(val),
                    }
                    states[f"{pname}:{k}"] = states[ent_id]
    except Exception:
        pass

    return states
