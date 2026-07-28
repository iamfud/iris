"""Elite Dangerous plugin — thin orchestrator."""

from .connector import EDConnector, read_journal_snapshot

LAYOUT = [
    {"title": "Commander", "fields": [
        {"key": "commander", "label": "Name"},
        {"key": "ship", "label": "Ship"},
        {"key": "credits", "label": "Credits"},
        {"key": "cargo", "label": "Cargo"},
    ]},
    {"title": "Location", "fields": [
        {"key": "system", "label": "System"},
        {"key": "system_addr", "label": "Address"},
        {"key": "body", "label": "Body"},
        {"key": "body_type", "label": "Body Type"},
        {"key": "allegiance", "label": "Allegiance"},
        {"key": "economy", "label": "Economy"},
        {"key": "government", "label": "Government"},
        {"key": "security", "label": "Security"},
        {"key": "population", "label": "Population"},
    ]},
    {"title": "Fuel", "fields": [
        {"key": "fuel_level", "label": "Level"},
        {"key": "fuel_capacity", "label": "Capacity"},
        {"key": "fuel_scooped", "label": "Scooped"},
    ]},
    {"title": "Ship Status", "fields": [
        {"key": "hull_health", "label": "Hull"},
        {"key": "shields_up", "label": "Shields", "source": "status", "display": "up_down"},
        {"key": "docked", "label": "Docked", "source": "status", "display": "yes_no"},
        {"key": "landed", "label": "Landed", "source": "status", "display": "yes_no"},
        {"key": "supercruise", "label": "Supercruise", "source": "status", "display": "yes_no"},
        {"key": "landing_gear", "label": "Landing Gear", "source": "status", "display": "down_up"},
        {"key": "hardpoints", "label": "Hardpoints", "source": "status", "display": "deployed_retracted"},
        {"key": "lights_on", "label": "Lights", "source": "status", "display": "on_off"},
        {"key": "cargo_scoop", "label": "Cargo Scoop", "source": "status", "display": "deployed_retracted"},
        {"key": "silent_running", "label": "Silent Running", "source": "status", "display": "on_off"},
        {"key": "mass_locked", "label": "Mass Lock", "source": "status", "display": "yes_no"},
        {"key": "night_vision", "label": "Night Vision", "source": "status", "display": "on_off"},
    ]},
    {"title": "FSD", "fields": [
        {"key": "fsd_charging", "label": "Charging", "source": "status", "display": "yes_no"},
        {"key": "fsd_cooldown", "label": "Cooldown", "source": "status", "display": "yes_no"},
        {"key": "fsd_jump", "label": "Jump", "source": "status", "display": "yes_no"},
        {"key": "jump_type", "label": "Jump Type"},
    ]},
    {"title": "Combat", "fields": [
        {"key": "target_ship", "label": "Target"},
        {"key": "bounty_reward", "label": "Bounty"},
        {"key": "mission", "label": "Mission"},
        {"key": "mission_reward", "label": "Mission Reward"},
        {"key": "last_repair", "label": "Last Repair"},
        {"key": "last_repair_cost", "label": "Repair Cost"},
    ]},
    {"title": "Ranks", "fields": [
        {"key": "rank_combat", "label": "Combat"},
        {"key": "rank_trade", "label": "Trade"},
        {"key": "rank_explore", "label": "Explore"},
        {"key": "rank_empire", "label": "Empire"},
        {"key": "rank_federation", "label": "Federation"},
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
    {"title": "Scanning", "fields": [
        {"key": "last_scan", "label": "Last Scan"},
        {"key": "scan_distance", "label": "Distance"},
        {"key": "system_scan_pct", "label": "System Scan"},
    ]},
]


class Plugin:
    name = "elite_dangerous"
    display_name = "Elite Dangerous"

    def __init__(self, cfg, serial_sender=None):
        self._connector = EDConnector()

    def start(self):
        self._connector.connect()

    def stop(self):
        self._connector.disconnect()

    def poll(self):
        return {
            "available": self._connector.available,
            "state": self._connector.state(),
            "status": self._connector.status(),
            "layout": LAYOUT,
        }

    def snapshot(self):
        data = read_journal_snapshot()
        data["layout"] = LAYOUT
        return data
