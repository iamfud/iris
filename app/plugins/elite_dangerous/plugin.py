"""Elite Dangerous plugin — lifecycle only.

Starts/stops the connector on ``start()``/``stop()``.  ``poll()``
returns current state for Iris; ``snapshot()`` adds debug/event-log
data for the journal explorer.
"""

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

log = logging.getLogger("iris.plugins.elite_dangerous")

FUEL_LOW_PCT = 30.0

LAYOUT = [
    {"title": "Navigation", "fields": [
        {"key": "system", "label": "System"},
        {"key": "body", "label": "Body"},
        {"key": "body_type", "label": "Type"},
        {"key": "allegiance", "label": "Allegiance"},
        {"key": "economy", "label": "Economy"},
        {"key": "government", "label": "Government"},
        {"key": "security", "label": "Security"},
        {"key": "population", "label": "Population"},
    ]},
    {"title": "Commander", "fields": [
        {"key": "commander", "label": "Name"},
        {"key": "credits", "label": "Credits"},
        {"key": "rank_combat", "label": "Combat Rank"},
        {"key": "progress_combat", "label": "Combat Progress"},
        {"key": "rank_trade", "label": "Trade Rank"},
        {"key": "progress_trade", "label": "Trade Progress"},
        {"key": "rank_explore", "label": "Explore Rank"},
        {"key": "progress_explore", "label": "Explore Progress"},
        {"key": "rank_empire", "label": "Empire"},
        {"key": "rank_federation", "label": "Federation"},
    ]},
    {"title": "Ship", "fields": [
        {"key": "ship", "label": "Ship"},
        {"key": "hull_health", "label": "Hull"},
        {"key": "shields_up", "label": "Shields", "source": "status", "display": "up_down"},
        {"key": "fuel_level", "label": "Fuel"},
        {"key": "fuel_capacity", "label": "Capacity"},
        {"key": "fuel_scooped", "label": "Scooped"},
        {"key": "cargo", "label": "Cargo"},
        {"key": "docked", "label": "Docked", "source": "status", "display": "yes_no"},
        {"key": "landed", "label": "Landed", "source": "status", "display": "yes_no"},
        {"key": "landing_gear", "label": "Landing Gear", "source": "status", "display": "down_up"},
        {"key": "hardpoints", "label": "Hardpoints", "source": "status", "display": "deployed_retracted"},
        {"key": "cargo_scoop", "label": "Cargo Scoop", "source": "status", "display": "deployed_retracted"},
        {"key": "flight_assist", "label": "Flight Assist", "source": "status", "display": "on_off"},
        {"key": "silent_running", "label": "Silent Running", "source": "status", "display": "on_off"},
        {"key": "lights_on", "label": "Lights", "source": "status", "display": "on_off"},
        {"key": "night_vision", "label": "Night Vision", "source": "status", "display": "on_off"},
        {"key": "in_srv", "label": "In SRV", "source": "status", "display": "yes_no"},
        {"key": "in_fighter", "label": "In Fighter", "source": "status", "display": "yes_no"},
        {"key": "on_foot", "label": "On Foot", "source": "status", "display": "yes_no"},
        {"key": "taxi", "label": "Apex Taxi", "source": "status", "display": "yes_no"},
        {"key": "multicrew", "label": "Multicrew", "source": "status", "display": "yes_no"},
        {"key": "supercruise", "label": "Supercruise", "source": "status", "display": "yes_no"},
    ]},
    {"title": "Combat", "fields": [
        {"key": "target_ship", "label": "Target"},
        {"key": "bounty_reward", "label": "Bounty Reward"},
        {"key": "mission", "label": "Mission"},
        {"key": "mission_reward", "label": "Mission Reward"},
        {"key": "mass_locked", "label": "Mass Lock", "source": "status", "display": "yes_no"},
        {"key": "wing_visible", "label": "Wing", "source": "status", "display": "yes_no"},
        {"key": "last_repair", "label": "Last Repair"},
        {"key": "last_repair_cost", "label": "Repair Cost"},
    ]},
    {"title": "Exploration", "fields": [
        {"key": "jump_type", "label": "Jump Type"},
        {"key": "fsd_charging", "label": "FSD Charging", "source": "status", "display": "yes_no"},
        {"key": "fsd_cooldown", "label": "FSD Cooldown", "source": "status", "display": "yes_no"},
        {"key": "fsd_jump", "label": "FSD Jump", "source": "status", "display": "yes_no"},
        {"key": "hyperdrive", "label": "Hyperdrive", "source": "status", "display": "yes_no"},
        {"key": "glide", "label": "Glide", "source": "status", "display": "yes_no"},
        {"key": "last_scan", "label": "Last Scan"},
        {"key": "scan_distance", "label": "Scan Distance"},
        {"key": "system_scan_pct", "label": "System Scan"},
        {"key": "scooping_fuel", "label": "Fuel Scooping", "source": "status", "display": "yes_no"},
    ]},
    {"title": "Powerplay", "fields": [
        {"key": "powerplay_power", "label": "Power"},
        {"key": "powerplay_rank", "label": "Rank"},
        {"key": "powerplay_merits", "label": "Merits"},
    ]},
    {"title": "Fleet Carrier", "fields": [
        {"key": "carrier_name", "label": "Name"},
        {"key": "carrier_callsign", "label": "Callsign"},
    ]},
]


class Plugin:
    name = "elite_dangerous"
    display_name = "Elite Dangerous"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._connector = EDConnector()
        self._serial = serial_sender
        self.overlays = overlays
        self._running = False
        self._thread = None
        self._last_system = None

    def start(self):
        self._connector.connect()
        self._running = True
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
        log.info("elite_dangerous plugin started")

    def stop(self):
        self._running = False
        self._connector.disconnect()
        if self._serial:
            if hasattr(self._serial, "release_progress_prefix"):
                self._serial.release_progress_prefix("ed.")
            if hasattr(self._serial, "clear_display_prefix"):
                self._serial.clear_display_prefix("ed.")

    def poll(self):
        """Lightweight live state for UI polling — no event log, no layout."""
        return {
            "available": self._connector.available,
            "state": self._connector.live_state(),
            "status": self._connector.status(),
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
        if not self.overlays:
            return
        system = state.get("system", "")
        if not system:
            return

        population = state.get("population", "Unknown")
        fields = [
            ("Economy", state.get("economy", "Unknown")),
            ("Government", state.get("government", "Unknown")),
            ("Security", state.get("security", "Unknown")),
            ("Allegiance", state.get("allegiance", "Unknown")),
        ]

        self.overlays.hero(
            title=system,
            subtitle=f"Population: {population}",
            fields=fields,
            duration=6,
        )

        if self._serial:
            self._serial.notify(
                "ed.system",
                system,
                f"Population: {population}",
            )

        log.info("[ed] system arrival: %s", system)

    def _watch_ship_state(self):
        """Push gear/hardpoints/cargo-hatch transitions and the fuel
        progress bar to the matrix display."""
        ship_labels = {
            "landing_gear": ("GEAR", "DOWN", "UP"),
            "hardpoints": ("HARDPOINTS", "DEPLOYED", "STOWED"),
            "cargo_scoop": ("CARGO HATCH", "OPEN", "CLOSED"),
        }
        prev = {}
        while self._running:
            try:
                st = self._connector.status()
            except Exception as e:
                log.warning("[ed] ship state error: %s", e)
                time.sleep(1.0)
                continue
            for key, (label, on_msg, off_msg) in ship_labels.items():
                cur = st.get(key)
                if cur is None:
                    continue
                last = prev.get(key)
                if last is not None and cur != last and self._serial:
                    # Stable key so opposite edge replaces mid-scroll.
                    self._serial.notify(
                        f"ed.{key}",
                        label,
                        on_msg if cur else off_msg,
                    )
                prev[key] = cur
            self._update_progress_bar(st)
            time.sleep(0.5)

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
