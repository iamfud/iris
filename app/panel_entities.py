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
            "id": "system.display",
            "domain": "System",
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
            "name": "HUD Overlay",
            "type": "status",
            "icon": "picture-in-picture-bottom-right",
            "color": "#48B2E9",
            "labels": {"on": "ACTIVE", "off": "HIDDEN"},
            "writable": True,
            "default_action": "toggle_overlay",
            "description": "Toggle desktop HUD overlay window",
        },
        {
            "id": "system.mic_mute",
            "domain": "System",
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
            "name": "Open Settings",
            "type": "action",
            "icon": "cog",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "open_settings",
            "description": "Open Iris web settings and portal",
        },
        {
            "id": "system.colour_picker",
            "domain": "System",
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
            "name": "Screenshot",
            "type": "action",
            "icon": "camera",
            "color": "#48B2E9",
            "writable": True,
            "default_action": "screenshot",
            "description": "Capture a screenshot of a screen region or full monitor",
        },

        # ── Media Controls (Momentary Actions) ───────────────────
        {
            "id": "media.play_pause",
            "domain": "Media",
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
            if isinstance(raw_fields, dict):
                field_items = list(raw_fields.items())
            elif isinstance(raw_fields, list):
                field_items = [(f.get("key") or f.get("id"), f) for f in raw_fields if isinstance(f, dict) and (f.get("key") or f.get("id"))]
            else:
                field_items = []

            for sid, sdef in field_items:
                if not sid:
                    continue
                ent_id = f"{name}.{sid}"
                if any(e["id"] == ent_id for e in entities):
                    continue
                entities.append({
                    "id": ent_id,
                    "plugin": name,
                    "domain": domain,
                    "name": (sdef.get("label") or sdef.get("name") or sid.replace("_", " ").title()) if isinstance(sdef, dict) else sid.replace("_", " ").title(),
                    "type": "data",
                    "icon": (sdef.get("icon") or "gauge") if isinstance(sdef, dict) else "gauge",
                    "color": "#48B2E9",
                    "unit": (sdef.get("unit") or "") if isinstance(sdef, dict) else "",
                    "writable": False,
                    "description": (sdef.get("description") or "") if isinstance(sdef, dict) else "",
                })
    except Exception as e:
        log.debug("Plugin entity discovery failed: %s", e)

    return entities


def get_entity_registry() -> List[Dict[str, Any]]:
    """Return full unified entity registry (Core + Plugins)."""
    registry = list(get_core_entities())
    registry.extend(get_plugin_entities())
    return registry


def get_live_entity_states() -> Dict[str, Dict[str, Any]]:
    """Collect live states for all registered entities."""
    states: Dict[str, Dict[str, Any]] = {}

    # Core states
    try:
        from ws_bridge import _app
        if _app is not None:
            states["system.display"] = {
                "active": bool(_app.cfg.get("pc_stats_manual", False)),
                "label": "ON" if _app.cfg.get("pc_stats_manual") else "OFF",
                "value": bool(_app.cfg.get("pc_stats_manual")),
            }
            states["system.overlay"] = {
                "active": bool(getattr(_app, "_overlay_shown", False)),
                "label": "ACTIVE" if getattr(_app, "_overlay_shown", False) else "HIDDEN",
                "value": bool(getattr(_app, "_overlay_shown", False)),
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

            # Media Provider live telemetry
            media_prov = getattr(_app, "_media_provider", None)
            if media_prov is None and getattr(_app, "_providers", None):
                for p in _app._providers:
                    if hasattr(p, "get_artwork"):
                        media_prov = p
                        break
            if media_prov is not None:
                m_data = media_prov.poll_data() if hasattr(media_prov, "poll_data") else {}
                is_playing = m_data.get("status") == "playing"
                states["media.player"] = {
                    "active": is_playing,
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

    # Plugin states
    try:
        import plugin_manager
        p_states = plugin_manager.get_plugin_button_states()
        for k, v in p_states.items():
            # key is "plugin:button_id"
            ent_id = k.replace(":", ".")
            states[ent_id] = v
            states[k] = v  # legacy alias
    except Exception:
        pass

    return states
