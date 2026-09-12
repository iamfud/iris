"""Elite Dangerous plugin — lifecycle only.

Starts/stops the connector on ``start()``/``stop()``.  ``poll()``
returns current state for Iris; ``snapshot()`` adds debug/event-log
data for the journal explorer.
"""

import os
import json
import logging
import threading
import time

from display_priority import (
    PRIO_PERSIST_REMINDER,
    PRIO_PERSIST_URGENT,
    PRIO_PERSIST_NORMAL,
    PRIO_PERSIST_MINOR,
)
from .connector import EDConnector
from .binds_scanner import BindsWatcher

log = logging.getLogger("iris.plugins.elite_dangerous")

FUEL_LOW_PCT = 30.0

# Critical alert colour (red flashing background). This is the ALERT channel —
# distinct from the per-button STATUS border colour the panel derives from the
# button profile. Kept as a single constant here: once the core exposes a
# semantic (colour-less) alert API, this constant can be dropped.
ALERT_COLOR = "#FF0000"

LAYOUT = [
    {"title": "Navigation & Location", "fields": [
        {"key": "system", "label": "Star System", "type": "string", "source": "state"},
        {"key": "system_addr", "label": "System Address", "type": "string", "source": "state"},
        {"key": "body", "label": "Body / Station", "type": "string", "source": "state"},
        {"key": "body_type", "label": "Body Type", "type": "string", "source": "state"},
        {"key": "allegiance", "label": "Allegiance", "type": "string", "source": "state"},
        {"key": "economy", "label": "Economy", "type": "string", "source": "state"},
        {"key": "government", "label": "Government", "type": "string", "source": "state"},
        {"key": "security", "label": "Security Level", "type": "string", "source": "state"},
        {"key": "population", "label": "Population", "type": "string", "source": "state"},
        {"key": "jump_type", "label": "Jump Type", "type": "string", "source": "state"},
    ]},
    {"title": "Ship Telemetry & Vitals", "fields": [
        {"key": "ship", "label": "Active Ship", "type": "string", "source": "state"},
        {"key": "hull_health", "label": "Hull Integrity", "type": "percentage", "source": "state"},
        {"key": "fuel_level", "label": "Fuel Level (t)", "type": "float", "source": "state"},
        {"key": "fuel_capacity", "label": "Fuel Capacity (t)", "type": "float", "source": "state"},
        {"key": "fuel_scooped", "label": "Fuel Scooped", "type": "float", "source": "state"},
        {"key": "cargo", "label": "Cargo Count (t)", "type": "integer", "source": "state"},
        {"key": "target_ship", "label": "Targeted Ship", "type": "string", "source": "state"},
    ]},
    {"title": "Flight Controls & Systems", "fields": [
        {"key": "landing_gear", "label": "Landing Gear", "type": "boolean", "source": "status", "display": "down_up"},
        {"key": "cargo_scoop", "label": "Cargo Scoop", "type": "boolean", "source": "status", "display": "deployed_retracted"},
        {"key": "flight_assist", "label": "Flight Assist", "type": "boolean", "source": "status", "display": "on_off"},
        {"key": "hardpoints", "label": "Hardpoints", "type": "boolean", "source": "status", "display": "deployed_retracted"},
        {"key": "lights_on", "label": "Exterior Lights", "type": "boolean", "source": "status", "display": "on_off"},
        {"key": "night_vision", "label": "Night Vision", "type": "boolean", "source": "status", "display": "on_off"},
        {"key": "silent_running", "label": "Silent Running", "type": "boolean", "source": "status", "display": "on_off"},
        {"key": "shields_up", "label": "Shields", "type": "boolean", "source": "status", "display": "online_down"},
        {"key": "supercruise", "label": "Supercruise", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "mass_locked", "label": "Mass Locked", "type": "boolean", "source": "status", "display": "yes_no"},
    ]},
    {"title": "Docking & Environment", "fields": [
        {"key": "docked", "label": "Docked", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "landed", "label": "Surface Landed", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "in_srv", "label": "In SRV", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "in_fighter", "label": "In Fighter", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "on_foot", "label": "On Foot (Odyssey)", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "taxi", "label": "Apex Taxi", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "multicrew", "label": "Multicrew Active", "type": "boolean", "source": "status", "display": "yes_no"},
    ]},
    {"title": "Commander & Career Ranks", "fields": [
        {"key": "commander", "label": "Commander Name", "type": "string", "source": "state"},
        {"key": "credits", "label": "Credits / Wealth", "type": "credits", "source": "state"},
        {"key": "rank_combat", "label": "Combat Rank", "type": "string", "source": "state"},
        {"key": "progress_combat", "label": "Combat Progress", "type": "percentage", "source": "state"},
        {"key": "rank_trade", "label": "Trade Rank", "type": "string", "source": "state"},
        {"key": "progress_trade", "label": "Trade Progress", "type": "percentage", "source": "state"},
        {"key": "rank_explore", "label": "Exploration Rank", "type": "string", "source": "state"},
        {"key": "progress_explore", "label": "Exploration Progress", "type": "percentage", "source": "state"},
        {"key": "rank_empire", "label": "Empire Rank", "type": "string", "source": "state"},
        {"key": "rank_federation", "label": "Federation Rank", "type": "string", "source": "state"},
    ]},
    {"title": "Frame Shift & Exploration", "fields": [
        {"key": "fsd_charging", "label": "FSD Charging", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "fsd_cooldown", "label": "FSD Cooldown", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "fsd_jump", "label": "FSD Jump Active", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "hyperdrive", "label": "Hyperdrive Active", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "glide", "label": "Planetary Glide", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "scooping_fuel", "label": "Corona Fuel Scooping", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "last_scan", "label": "Last Scanned Body", "type": "string", "source": "state"},
        {"key": "scan_distance", "label": "Scan Distance", "type": "string", "source": "state"},
        {"key": "system_scan_pct", "label": "System Scan Progress", "type": "percentage", "source": "state"},
        {"key": "jumps_remaining", "label": "Jumps to Target", "type": "number", "source": "state"},
        {"key": "route_destination", "label": "Route Destination", "type": "string", "source": "state"},
        {"key": "next_system", "label": "Next Waypoint System", "type": "string", "source": "state"},
        {"key": "next_star_class", "label": "Next Star Class", "type": "string", "source": "state"},
    ]},
    {"title": "Operations, Powerplay & Carrier", "fields": [
        {"key": "mission", "label": "Active Mission", "type": "string", "source": "state"},
        {"key": "mission_reward", "label": "Mission Reward", "type": "credits", "source": "state"},
        {"key": "bounty_reward", "label": "Claimed Bounty", "type": "credits", "source": "state"},
        {"key": "wing_visible", "label": "Wing Visible", "type": "boolean", "source": "status", "display": "yes_no"},
        {"key": "last_repair", "label": "Last Repair", "type": "string", "source": "state"},
        {"key": "last_repair_cost", "label": "Last Repair Cost", "type": "credits", "source": "state"},
        {"key": "powerplay_power", "label": "Pledged Power", "type": "string", "source": "state"},
        {"key": "powerplay_rank", "label": "Powerplay Rank", "type": "string", "source": "state"},
        {"key": "powerplay_merits", "label": "Powerplay Merits", "type": "string", "source": "state"},
        {"key": "carrier_name", "label": "Fleet Carrier Name", "type": "string", "source": "state"},
        {"key": "carrier_callsign", "label": "Carrier Callsign", "type": "string", "source": "state"},
    ]},
]


class Plugin:
    name = "elite_dangerous"
    display_name = "Elite Dangerous"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._connector = EDConnector()
        self._serial = serial_sender
        self._cfg = cfg
        self.overlays = overlays
        self._running = False
        self._thread = None
        self._last_system = None
        self._binds_watcher = BindsWatcher()

    def start(self):
        self._connector.connect()
        self._running = True
        self._binds_watcher.check_for_updates(self._cfg)
        self._thread = threading.Thread(
            target=self._watch_system_changes,
            daemon=True,
            name="ed-system-watch",
        )
        self._thread.start()
        self._ship_thread = threading.Thread(
            target=self._watch_ship_state,
            daemon=True,
            name="ed-ship-watch",
        )
        self._ship_thread.start()
        self._ensure_default_profile()
        log.info("elite_dangerous plugin started")

    def get_options(self, key):
        """Dynamic options provider for settings dropdowns."""
        from .binds_scanner import list_available_binds_files, list_available_backups
        if key == "available_binds_files":
            return list_available_binds_files()
        if key == "available_backups":
            return list_available_backups()
        return []

    def handle_action(self, action_id, payload=None):
        """Execute plugin actions from UI (import binds, create backup, restore)."""
        import os
        from .binds_scanner import (
            get_bindings_dir,
            get_active_binds_file,
            backup_binds_file,
            parse_binds_xml,
            sync_binds_to_config,
            restore_backup,
            list_available_backups,
        )
        import plugin_manager
        pcfg = plugin_manager.get_plugin_config(self.name)
        selected_file = pcfg.get("selected_binds_file")

        if action_id == "import_binds":
            binds_dir = get_bindings_dir()
            if not binds_dir:
                return {"ok": False, "error": "Frontier Bindings directory not found"}
            if selected_file:
                target_path = os.path.join(binds_dir, selected_file)
            else:
                target_path, _ = get_active_binds_file()
            if not target_path or not os.path.isfile(target_path):
                return {"ok": False, "error": f"Binds file not found: {target_path}"}
            backup_binds_file(target_path)
            keys = parse_binds_xml(target_path)
            self._binds_watcher._current_key_map = keys
            count = sync_binds_to_config(self._cfg, keys)
            from config import save_config
            save_config(self._cfg)
            log.info("[ed.binds] manually imported %d hotkeys from %s", count, target_path)
            return {"ok": True, "message": f"Imported and synced {len(keys)} keybindings ({count} buttons updated) from {os.path.basename(target_path)}"}

        if action_id == "backup_binds":
            target_path, preset = get_active_binds_file()
            if not target_path:
                return {"ok": False, "error": "No active binds file found to backup"}
            bk = backup_binds_file(target_path, preset)
            if bk:
                return {"ok": True, "message": f"Backup saved to Iris library: {os.path.basename(bk)}"}
            return {"ok": False, "error": "Backup creation failed"}

        if action_id == "restore_binds":
            backups = list_available_backups()
            if not backups:
                return {"ok": False, "error": "No backups available in Iris plugin data"}
            bk_file = (payload or {}).get("backup_file") or backups[0]
            ok, msg = restore_backup(bk_file, self._cfg)
            return {"ok": ok, "message": msg}

        return {"ok": False, "error": f"Unknown action: {action_id}"}

    def get_buttons_def(self):
        """Return button definitions with live hotkeys synced from active .binds."""
        import plugin_manager
        manifest = plugin_manager.get_manifest(self.name) or {}
        buttons = list(manifest.get("buttons", []))
        out = []
        for b in buttons:
            b_copy = dict(b)
            bid = b_copy.get("id") or b_copy.get("button_id")
            if bid:
                b_copy["hotkey"] = self._binds_watcher.get_key(bid, b_copy.get("default_hotkey", ""))
            out.append(b_copy)
        return out

    def _ensure_default_profile(self):
        """Install a default Elite Dangerous button-box profile if one doesn't exist.

        Checks panel_profiles for any profile whose exe or name matches Elite
        Dangerous.  If none is found, injects a fully-configured 12-slot profile
        so the user has a ready-to-use button box the moment the plugin loads.
        Does nothing if a matching profile already exists.
        """
        try:
            from config import save_config
            cfg = self._cfg
            if not isinstance(cfg, dict):
                return

            profiles = cfg.get("panel_profiles") or []
            ed_exe = "EliteDangerous64.exe"

            # Already exists? Leave it alone.
            for p in profiles:
                if not isinstance(p, dict):
                    continue
                exe = (p.get("exe") or "").lower()
                name = (p.get("name") or "").lower()
                if "elite" in exe or "elite" in name or "EliteDangerous64" in (p.get("exe") or ""):
                    return

            # Dynamically import default buttons and metadata from the plugin's own plugin.json manifest
            manifest_path = os.path.join(os.path.dirname(__file__), "plugin.json")
            manifest = {}
            if os.path.isfile(manifest_path):
                try:
                    import json
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception as ex:
                    log.warning("[ed] could not read plugin.json: %s", ex)

            default_board = []
            for btn in manifest.get("buttons", []):
                wtype = btn.get("widget_type", "status_toggle")
                slot = {
                    "type": "TOGGLE" if "toggle" in wtype else "ACTION",
                    "name": btn.get("name", ""),
                    "icon": btn.get("icon", ""),
                    "color": btn.get("color", "#ffb703"),
                    "plugin": manifest.get("name", "elite_dangerous"),
                    "button_id": btn.get("id", ""),
                    "widget_type": wtype,
                    "state_key": btn.get("state_key", btn.get("id", "")),
                    "show_name": True,
                    "show_icon": True,
                    "show_state": True,
                }
                if "icon_off" in btn:
                    slot["icon_off"] = btn["icon_off"]
                if "labels" in btn:
                    slot["labels"] = btn["labels"]
                if "colors" in btn:
                    slot["colors"] = btn["colors"]
                if "default_hotkey" in btn:
                    slot["default_hotkey"] = btn["default_hotkey"]
                    slot["hotkey"] = btn["default_hotkey"]
                default_board.append(slot)

            theme = manifest.get("theme", {})
            new_profile = {
                "id": f"prof_{manifest.get('name', 'elite_dangerous')}",
                "name": manifest.get("display_name", "Elite Dangerous"),
                "exe": manifest.get("exe_default", ed_exe),
                "enabled": True,
                "theme": {
                    "accent": theme.get("accent", "#ff5500"),
                    "neon": theme.get("neon", "#ffaa00"),
                },
                "theme_override": True,
                "lighting_enabled": True,
                "lighting_theme_enabled": True,
                "lighting_alerts_enabled": True,
                "board": default_board,
            }

            profiles.append(new_profile)
            cfg["panel_profiles"] = profiles
            save_config(cfg)
            log.info("[ed] installed default button-box profile from plugin.json")

        except Exception as e:
            log.warning("[ed] could not install default profile: %s", e)


    def stop(self):
        self._running = False
        self._clear_shields_warning()
        self._connector.disconnect()
        if self._serial:
            if hasattr(self._serial, "release_progress_prefix"):
                self._serial.release_progress_prefix("ed.")
            if hasattr(self._serial, "clear_display_prefix"):
                self._serial.clear_display_prefix("ed.")

    def poll(self):
        """Lightweight live state for UI polling."""
        return {
            "available": self._connector.available,
            "state": self._connector.live_state(),
            "status": self._connector.status(),
            "layout": LAYOUT,
        }

    def _watch_system_changes(self):
        """Background thread: show hero overlay when the system changes."""
        while self._running:
            try:
                state = self._connector.live_state()
                system = state.get("system", "")
                if system:
                    if self._last_system is None:
                        # First reading: just set the baseline, no overlay.
                        self._last_system = system
                    elif system != self._last_system:
                        self._last_system = system
                        self._show_system_hero(state)
            except Exception as e:
                log.warning("[ed] system watch error: %s", e)
            time.sleep(1.0)

    def _show_system_hero(self, state):
        """Render a hero overlay and send the system to the hardware display."""
        if not self.overlays and not self._serial:
            return
        system = state.get("system", "")
        if not system:
            return

        population = state.get("population", "Unknown")
        jumps = state.get("jumps_remaining")
        dest = state.get("route_destination")

        fields = [
            ("Economy", state.get("economy", "Unknown")),
            ("Security", state.get("security", "Unknown")),
            ("Allegiance", state.get("allegiance", "Unknown")),
        ]

        if jumps is not None and jumps > 0 and dest:
            fields.insert(0, ("Route", f"{jumps} jumps to {dest}"))
            sub = f"{jumps} jumps to {dest}"
        elif jumps == 0 and dest:
            fields.insert(0, ("Route", "Destination Reached"))
            sub = f"Destination Reached"
        else:
            sub = f"Population: {population}"

        if self.overlays:
            self.overlays.hero(
                title=system,
                subtitle=sub,
                fields=fields,
                duration=6,
            )

        if self._serial:
            self._serial.notify(
                "ed.system",
                system,
                sub,
            )

        log.info("[ed] system arrival: %s (%s)", system, sub)

    def _watch_ship_state(self):
        """Push gear/hardpoints/cargo-hatch transitions and the fuel
        progress bar to the matrix display."""
        ship_labels = {
            "landing_gear": ("GEAR", "DOWN", "UP"),
            "hardpoints": ("HARDPOINTS", "DEPLOYED", "STOWED"),
            "cargo_scoop": ("CARGO HATCH", "OPEN", "CLOSED"),
        }
        prev = {}
        shield_alert_active = False
        tick_count = 0
        while self._running:
            if not self._connector.game_running():
                if shield_alert_active:
                    shield_alert_active = False
                    self._clear_shields_warning()
                prev.clear()
                time.sleep(1.0)
                continue

            try:
                st = self._connector.status()
            except Exception as e:
                log.warning("[ed] ship state error: %s", e)
                time.sleep(1.0)
                continue

            tick_count += 1
            if tick_count % 4 == 0:  # Every 2s (4 * 0.5s)
                try:
                    self._binds_watcher.check_for_updates(self._cfg)
                except Exception as ex:
                    log.debug("[ed] periodic binds check error: %s", ex)

            try:
                for key, (label, on_msg, off_msg) in ship_labels.items():
                    cur = st.get(key)
                    if cur is None:
                        continue
                    last = prev.get(key)
                    if last is not None and cur != last and self._serial:
                        # Determine good vs bad status
                        if key == "landing_gear":
                            ev_status = "good" if cur else "bad"  # DOWN is safe (good), UP is retracted (bad)
                        elif key == "hardpoints":
                            ev_status = "bad" if cur else "good"  # DEPLOYED is combat alert (bad), STOWED is safe (good)
                        else:
                            ev_status = "good"

                        if hasattr(self._serial, "event"):
                            self._serial.event(
                                f"ed.{key}",
                                label,
                                on_msg if cur else off_msg,
                                status=ev_status,
                            )
                        else:
                            self._serial.notify(
                                f"ed.{key}",
                                label,
                                on_msg if cur else off_msg,
                            )
                    prev[key] = cur

                # Shield-down alert: STATE-driven, not edge-triggered. Fire whenever shields are down
                # regardless of whether on foot or in ship.
                shields = st.get("shields_up")
                if shields is not None:
                    if shields is False:
                        if not shield_alert_active:
                            self._alert_shields_down()
                            self._set_shields_warning()
                            shield_alert_active = True
                    else:
                        if shield_alert_active:
                            shield_alert_active = False
                            self._clear_shields_warning()

                self._update_progress_bar(st)
            except Exception as ex:
                log.warning("[ed] ship state processing error: %s", ex)

            time.sleep(0.5)

    def _alert_shields_down(self):
        """Red rapid-flash alert when the ship shield generator fails."""
        log.info("[ed] shields down alert triggered")
        if self.overlays:
            try:
                self.overlays.hero(
                    title="SHIELDS DOWN",
                    subtitle="Shield generator has failed!",
                    fields=[("Status", "CRITICAL"), ("Shields", "OFFLINE")],
                    duration=6,
                )
            except Exception as e:
                log.debug("[ed] shield overlay error: %s", e)

        if self._serial:
            try:
                if hasattr(self._serial, "send_alert"):
                    self._serial.send_alert(
                        "SHIELDS DOWN",
                        "Shield generator has failed",
                        key="ed.shields",
                    )
                else:
                    self._serial.notify(
                        "ed.shields",
                        "SHIELDS DOWN",
                        "Shield generator has failed",
                        theme="alert",
                    )
                log.info("[ed] shields down alert sent to hardware")
            except Exception as e:
                log.warning("[ed] shield alert error: %s", e)

    def _set_shields_warning(self):
        """Flag the Shields button red while the shield generator is down.

        The warning colour overrides the button's normal on/off colour; when it
        is cleared the button returns to its previous saved value.
        """
        try:
            import warning_state
            warning_state.set_warning(
                "elite_dangerous:shields",
                color=ALERT_COLOR,
                message="SHIELDS DOWN",
            )
        except Exception as e:
            log.debug("[ed] warning_state set error: %s", e)

        if self._serial and hasattr(self._serial, "set_warning"):
            try:
                self._serial.set_warning(
                    "elite_dangerous:shields",
                    color=ALERT_COLOR,
                    message="SHIELDS DOWN",
                )
            except Exception as e:
                log.warning("[ed] shield warning error: %s", e)

    def _clear_shields_warning(self):
        """Turn the warning off; the button returns to its saved colour."""
        try:
            import warning_state
            warning_state.clear_warning("elite_dangerous:shields")
        except Exception as e:
            log.debug("[ed] warning_state clear error: %s", e)

        if self._serial:
            try:
                if hasattr(self._serial, "clear_warning"):
                    self._serial.clear_warning("elite_dangerous:shields")
                if hasattr(self._serial, "clear_display"):
                    self._serial.clear_display("ed.shields")
            except Exception as e:
                log.warning("[ed] shield warning clear error: %s", e)

    def _fuel_percent(self):
        """Return fuel % (0-100) from journal fuel tons, or None if unknown."""
        try:
            state = self._connector.live_state()
            level = state.get("fuel_level")
            cap = state.get("fuel_capacity")
            if not level or not cap:
                return None
            cap_f = float(cap)
            if cap_f <= 0:
                return None
            pct = float(level) / cap_f * 100.0
            return max(0.0, min(100.0, pct))
        except Exception:
            return None

    def _update_progress_bar(self, status):
        """Drive the matrix progress bar via display claims.

        Ladder: STATION (docked, urgent) > GEAR (gear down) > LIMPETS
        (reminder, 3s every 10s while docked) > FUEL (scooping / low).
        The station claim is persistent while docked and outranks gear, so
        gear "naturally resumes" when the ship undocks.  Nothing is claimed
        when the game is not running, so the bar clears shortly after the
        game exits (no stale gear from a previous session).
        """
        if not self._serial:
            return

        if not self._connector.game_running():
            if hasattr(self._serial, "release_progress_prefix"):
                self._serial.release_progress_prefix("ed.")
            else:
                for cid in ("ed.station", "ed.limpets", "ed.gear", "ed.fuel"):
                    self._serial.release_progress(cid)
            if hasattr(self._serial, "clear_display_prefix"):
                self._serial.clear_display_prefix("ed.")
            return

        fuel_pct = self._fuel_percent()
        scooping = bool(status.get("scooping_fuel", False))

        if bool(status.get("docked", False)):
            station = self._connector.live_state().get("body", "").strip() or "STATION"
            self._serial.claim_progress(
                "ed.station", PRIO_PERSIST_URGENT, station, 100)
            self._serial.remind_progress(
                "ed.limpets", PRIO_PERSIST_REMINDER, "LIMPETS", 100,
                on_s=3.0, period_s=10.0)
        else:
            self._serial.release_progress("ed.station")
            self._serial.release_progress("ed.limpets")

        if bool(status.get("landing_gear", False)):
            self._serial.claim_progress(
                "ed.gear", PRIO_PERSIST_NORMAL, "GEAR", 100)
        else:
            self._serial.release_progress("ed.gear")

        if fuel_pct is not None and (scooping or fuel_pct < FUEL_LOW_PCT):
            name = "SCOOPING" if scooping else "LOW FUEL"
            self._serial.claim_progress(
                "ed.fuel", PRIO_PERSIST_MINOR, name, int(round(fuel_pct)))
        else:
            self._serial.release_progress("ed.fuel")

    def snapshot(self):
        """Full debug payload for journal explorer / diagnostics."""
        return {
            "available": self._connector.available,
            "state": self._connector.state(),
            "status": self._connector.status(),
            "layout": LAYOUT,
            "events_raw": self._connector.event_log()[-50:],
        }
