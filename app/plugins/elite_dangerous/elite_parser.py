"""Pure parser — Frontier Development JSON journal events → Iris state.

No filesystem, no network, no Iris knowledge.  Transforms event
dicts into in-memory state/status dicts via the ``apply()`` method.
"""

import logging

log = logging.getLogger("iris.ed.parser")


# ── Helpers ──────────────────────────────────────────────────────

def _fmt_credits(val):
    if val is None:
        return ""
    try:
        v = int(val)
        if v >= 1_000_000_000:
            return f"{v / 1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return str(v)
    except (ValueError, TypeError):
        return str(val) if val else ""


def _fmt_population(val):
    try:
        v = int(val)
        if v == 0:
            return "None"
        if v >= 1_000_000_000:
            return f"{v / 1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"{v / 1_000:.0f}K"
        return str(v)
    except (ValueError, TypeError):
        return str(val) if val else ""


def _clean(val):
    if not val:
        return ""
    if val.startswith("$"):
        end = val.rfind(";")
        val = val[1:end] if end > 0 else val[1:]
        val = val.replace("_", " ").title()
    return val


# ── Event handlers ───────────────────────────────────────────────

def _set(s, e, key, state_key=None, fn=None):
    v = e.get(key)
    if v is not None:
        s[state_key or key] = fn(v) if fn else str(v)


def _handle_loadgame(s, st, e):
    s["commander"] = e.get("Commander", "")
    s["ship"] = e.get("Ship_Localised") or e.get("Ship", "")
    s["credits"] = _fmt_credits(e.get("Credits"))
    _set(s, e, "FuelLevel", "fuel_level", lambda v: f"{float(v):.1f}")
    _set(s, e, "FuelCapacity", "fuel_capacity", lambda v: f"{float(v):.1f}")


def _handle_loadout(s, st, e):
    raw = e.get("Ship", "")
    loc = e.get("Ship_Localised")
    if loc:
        s["ship"] = loc
    elif raw and not s.get("ship"):
        s["ship"] = raw
    hull = e.get("HullHealth")
    if hull is not None:
        s["hull_health"] = f"{float(hull) * 100:.0f}%"
    fc = e.get("FuelCapacity", {})
    if isinstance(fc, dict):
        v = fc.get("Main")
        if v is not None:
            s["fuel_capacity"] = f"{float(v):.1f}"


def _handle_commander(s, st, e):
    s["commander"] = e.get("Name", "")


def _pop_set(s, e):
    pop = e.get("Population")
    if pop is not None:
        s["population"] = _fmt_population(pop)


def _handle_location(s, st, e):
    s["system"] = e.get("StarSystem", "")
    s["system_addr"] = str(e.get("SystemAddress", ""))
    s["allegiance"] = _clean(e.get("SystemAllegiance", ""))
    s["economy"] = _clean(e.get("SystemEconomy_Localised") or e.get("SystemEconomy", ""))
    s["government"] = _clean(e.get("SystemGovernment_Localised") or e.get("SystemGovernment", ""))
    s["security"] = _clean(e.get("SystemSecurity_Localised") or e.get("SystemSecurity", ""))
    _pop_set(s, e)
    if e.get("Docked"):
        s["body"] = e.get("StationName", "")
    else:
        s["body"] = e.get("Body", "")
    s["body_type"] = e.get("BodyType", "")
    # Clear stale jump type
    s.pop("jump_type", None)


def _handle_fsdjump(s, st, e):
    s["system"] = e.get("StarSystem", "")
    s["system_addr"] = str(e.get("SystemAddress", ""))
    s["allegiance"] = _clean(e.get("SystemAllegiance", ""))
    s["economy"] = _clean(e.get("SystemEconomy_Localised") or e.get("SystemEconomy", ""))
    s["government"] = _clean(e.get("SystemGovernment_Localised") or e.get("SystemGovernment", ""))
    s["security"] = _clean(e.get("SystemSecurity_Localised") or e.get("SystemSecurity", ""))
    _pop_set(s, e)
    _set(s, e, "FuelLevel", "fuel_level", lambda v: f"{float(v):.1f}")
    s["body"] = ""
    s["body_type"] = ""
    s.pop("jump_type", None)


def _handle_startjump(s, st, e):
    s["jump_type"] = e.get("JumpType", "")


def _handle_supercruiseentry(s, st, e):
    s.pop("jump_type", None)


def _handle_supercruiseexit(s, st, e):
    s.pop("jump_type", None)
    s["body"] = e.get("Body", "")
    s["body_type"] = e.get("BodyType", "")


def _handle_docked(s, st, e):
    s["body"] = e.get("StationName", "")
    s["body_type"] = e.get("StationType", "Station")


def _handle_undocked(s, st, e):
    s["body"] = ""
    s["body_type"] = ""


def _handle_scan(s, st, e):
    s["last_scan"] = e.get("BodyName", "")
    dist = e.get("DistanceFromArrivalLS")
    if dist is not None:
        s["scan_distance"] = f"{dist:.1f} LS"


def _handle_fssdiscoveryscan(s, st, e):
    prog = e.get("Progress", 0)
    s["system_scan_pct"] = f"{prog * 100:.0f}%"


def _handle_fuelscp(s, st, e):
    s["fuel_scooped"] = f"{e.get('Scooped', 0):.1f}"
    t = e.get("Total")
    if t is not None:
        s["fuel_level"] = f"{float(t):.1f}"


def _handle_reservoirreplenished(s, st, e):
    v = e.get("FuelMain")
    if v is not None:
        s["fuel_level"] = f"{float(v):.1f}"


def _handle_shieldstate(s, st, e):
    st["shields_up"] = bool(e.get("ShieldsUp"))


def _handle_hulldamage(s, st, e):
    h = e.get("Health", 0)
    s["hull_health"] = f"{h * 100:.0f}%"


def _handle_repairall(s, st, e):
    s["hull_health"] = "100%"


def _handle_repair(s, st, e):
    item = e.get("Item", "")
    cost = e.get("Cost")
    s["last_repair"] = _clean(item) if item else ""
    if cost is not None:
        s["last_repair_cost"] = _fmt_credits(cost)


def _handle_shiptargeted(s, st, e):
    if e.get("TargetLocked"):
        s["target_ship"] = e.get("Ship_Localised") or e.get("Ship", "")
    else:
        s["target_ship"] = ""


def _handle_bounty(s, st, e):
    s["bounty_reward"] = _fmt_credits(e.get("TotalReward"))


RANK_NAMES = {
    0: "Harmless", 1: "Mostly Harmless", 2: "Novice", 3: "Competent",
    4: "Expert", 5: "Master", 6: "Dangerous", 7: "Deadly", 8: "Elite",
    9: "Elite I", 10: "Elite II", 11: "Elite III", 12: "Elite IV",
    13: "Elite V",
}


def _handle_rank(s, st, e):
    for k in ("Combat", "Trade", "Explore", "Empire", "Federation"):
        v = e.get(k)
        if v is not None:
            s[f"rank_{k.lower()}"] = RANK_NAMES.get(v, str(v))


def _handle_progress(s, st, e):
    for k in ("Combat", "Trade", "Explore"):
        v = e.get(k)
        if v is not None:
            s[f"progress_{k.lower()}"] = f"{v}%"


def _handle_reputation(s, st, e):
    for k in ("Empire", "Federation"):
        v = e.get(k)
        if v is not None:
            key = f"rank_{k.lower()}"
            prev = s.get(key, "")
            s[key] = f"{prev} ({v:.0f}%)" if prev else f"{v:.0f}%"


def _handle_missionaccepted(s, st, e):
    s["mission"] = e.get("LocalisedName") or e.get("Name", "")
    r = e.get("Reward")
    s["mission_reward"] = _fmt_credits(r) if r else ""


def _handle_missioncompleted(s, st, e):
    s.pop("mission", None)
    s.pop("mission_reward", None)


def _handle_missionfailed(s, st, e):
    s.pop("mission", None)
    s.pop("mission_reward", None)


def _handle_cargo(s, st, e):
    s["cargo"] = str(e.get("Count", ""))


def _handle_statistics(s, st, e):
    bank = e.get("Bank_Account", {})
    w = bank.get("Current_Wealth")
    if w is not None:
        s["credits"] = _fmt_credits(w)


def _handle_powerplay(s, st, e):
    s["powerplay_power"] = e.get("Power", "")
    s["powerplay_rank"] = str(e.get("Rank", ""))
    s["powerplay_merits"] = _fmt_credits(e.get("Merits"))


def _handle_carrierstats(s, st, e):
    s["carrier_name"] = e.get("Name", "")
    s["carrier_callsign"] = e.get("Callsign", "")


def _handle_carrierlocation(s, st, e):
    s["system"] = e.get("StarSystem", "")


def _handle_carrierjump(s, st, e):
    s["system"] = e.get("StarSystem", "")
    if e.get("Docked"):
        s["body"] = e.get("StationName", "")


# ── Handler registry ─────────────────────────────────────────────

_HANDLERS = {
    "LoadGame": _handle_loadgame,
    "Loadout": _handle_loadout,
    "Commander": _handle_commander,
    "Location": _handle_location,
    "FSDJump": _handle_fsdjump,
    "StartJump": _handle_startjump,
    "SupercruiseEntry": _handle_supercruiseentry,
    "SupercruiseExit": _handle_supercruiseexit,
    "Docked": _handle_docked,
    "Undocked": _handle_undocked,
    "Scan": _handle_scan,
    "FSSDiscoveryScan": _handle_fssdiscoveryscan,
    "FuelScoop": _handle_fuelscp,
    "ReservoirReplenished": _handle_reservoirreplenished,
    "ShieldState": _handle_shieldstate,
    "HullDamage": _handle_hulldamage,
    "RepairAll": _handle_repairall,
    "Repair": _handle_repair,
    "ShipTargeted": _handle_shiptargeted,
    "Bounty": _handle_bounty,
    "Rank": _handle_rank,
    "Progress": _handle_progress,
    "Reputation": _handle_reputation,
    "MissionAccepted": _handle_missionaccepted,
    "MissionCompleted": _handle_missioncompleted,
    "MissionFailed": _handle_missionfailed,
    "Cargo": _handle_cargo,
    "Statistics": _handle_statistics,
    "Powerplay": _handle_powerplay,
    "CarrierStats": _handle_carrierstats,
    "CarrierLocation": _handle_carrierlocation,
    "CarrierJump": _handle_carrierjump,
}


# ── Public class ─────────────────────────────────────────────────

class EliteParser:
    """Pure event-to-state parser.

    Thread-safe *if the caller serialises* — the class holds no
    internal state; all mutations happen on the caller-supplied
    *state* and *status* dicts.
    """

    @staticmethod
    def apply(event, state, status):
        """Dispatch a single journal *event* dict into *state* / *status*.

        Mutates both dicts in place.  Unknown event types are silently
        ignored (they show up in the event log but do nothing).
        """
        et = event.get("event", "")
        handler = _HANDLERS.get(et)
        if handler:
            handler(state, status, event)

    @staticmethod
    def apply_many(events, state, status):
        """Apply a sequence of events in order (newest last)."""
        for ev in events:
            EliteParser.apply(ev, state, status)

    @staticmethod
    def build_default_status():
        """Return a clean status dict with all flags = False."""
        return {k: False for k in (
            "docked", "landed", "landing_gear", "shields_up", "supercruise",
            "flight_assist", "hardpoints", "wing_visible", "lights_on",
            "cargo_scoop", "silent_running", "scooping_fuel", "mass_locked",
            "in_srv", "in_fighter", "night_vision", "fsd_charging",
            "fsd_cooldown", "fsd_jump", "hyperdrive", "glide",
            "on_foot", "taxi", "multicrew",
        )}

    @staticmethod
    def build_default_state():
        """Return a clean (empty) state dict."""
        return {}
