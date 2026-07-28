"""Minimal ED connector — reads journal events into a flat state dict."""

import logging
import threading

from .journal_watcher import JournalWatcher

log = logging.getLogger("iris.ed.connector")


class EDConnector:

    def __init__(self):
        self._watcher = JournalWatcher()
        self._lock = threading.Lock()
        self._game_active = False
        self._state = {}
        self._status = {
            "docked": False, "landed": False, "landing_gear": False,
            "shields_up": False, "supercruise": False, "flight_assist": False,
            "hardpoints": False, "wing_visible": False, "lights_on": False,
            "cargo_scoop": False, "silent_running": False, "scooping_fuel": False,
            "mass_locked": False, "in_srv": False, "in_fighter": False,
            "night_vision": False, "fsd_charging": False, "fsd_cooldown": False,
            "fsd_jump": False, "hyperdrive": False, "glide": False,
            "on_foot": False, "taxi": False, "multicrew": False,
        }
        self.on_update = None

    def connect(self):
        self._watcher.on_event = self._on_event
        self._watcher.on_status = self._on_status
        self._watcher.on_game_state = self._on_game_state
        self._watcher.start()

    def disconnect(self):
        self._watcher.stop()

    @property
    def available(self):
        return self._game_active

    def state(self):
        with self._lock:
            return dict(self._state)

    def status(self):
        with self._lock:
            return dict(self._status)

    def _on_game_state(self, gs):
        self._game_active = gs == "started"
        if gs == "started":
            self._replay_events()
        self._notify()

    def _on_event(self, event):
        et = event.get("event", "")
        with self._lock:
            handler = _HANDLERS.get(et)
            if handler:
                handler(self, event)
        self._notify()

    def _on_status(self, flags):
        with self._lock:
            self._status.update(flags)
        self._notify()

    def _notify(self):
        if self.on_update:
            try:
                self.on_update()
            except Exception:
                pass

    def _replay_events(self):
        for event in self._watcher.read_last_n_events(200):
            et = event.get("event", "")
            handler = _HANDLERS.get(et)
            if handler:
                with self._lock:
                    handler(self, event)


def _s(s, e, key, state_key=None, fn=None):
    v = e.get(key)
    if v is not None:
        s._state[state_key or key] = fn(v) if fn else str(v)


def _handle_loadgame(s, e):
    s._state["commander"] = e.get("Commander", "")
    s._state["ship"] = e.get("Ship_Localised") or e.get("Ship", "")
    s._state["credits"] = _credits(e.get("Credits"))
    _s(s, e, "FuelLevel", "fuel_level", lambda v: f"{float(v):.1f}")
    _s(s, e, "FuelCapacity", "fuel_capacity", lambda v: f"{float(v):.1f}")


def _handle_loadout(s, e):
    raw = e.get("Ship", "")
    loc = e.get("Ship_Localised")
    if loc:
        s._state["ship"] = loc
    elif raw and not s._state.get("ship"):
        s._state["ship"] = raw
    hull = e.get("HullHealth")
    if hull is not None:
        s._state["hull_health"] = f"{float(hull) * 100:.0f}%"
    fc = e.get("FuelCapacity", {})
    if isinstance(fc, dict):
        v = fc.get("Main")
        if v is not None:
            s._state["fuel_capacity"] = f"{float(v):.1f}"


def _handle_commander(s, e):
    s._state["commander"] = e.get("Name", "")


def _handle_location(s, e):
    s._state["system"] = e.get("StarSystem", "")
    s._state["system_addr"] = str(e.get("SystemAddress", ""))
    s._state["allegiance"] = _clean(e.get("SystemAllegiance", ""))
    s._state["economy"] = _clean(e.get("SystemEconomy_Localised") or e.get("SystemEconomy", ""))
    s._state["government"] = _clean(e.get("SystemGovernment_Localised") or e.get("SystemGovernment", ""))
    s._state["security"] = _clean(e.get("SystemSecurity_Localised") or e.get("SystemSecurity", ""))
    _pop_set(s, e)
    if e.get("Docked"):
        s._state["body"] = e.get("StationName", "")
    else:
        s._state["body"] = e.get("Body", "")
    s._state["body_type"] = e.get("BodyType", "")


def _handle_fsdjump(s, e):
    s._state["system"] = e.get("StarSystem", "")
    s._state["system_addr"] = str(e.get("SystemAddress", ""))
    s._state["allegiance"] = _clean(e.get("SystemAllegiance", ""))
    s._state["economy"] = _clean(e.get("SystemEconomy_Localised") or e.get("SystemEconomy", ""))
    s._state["government"] = _clean(e.get("SystemGovernment_Localised") or e.get("SystemGovernment", ""))
    s._state["security"] = _clean(e.get("SystemSecurity_Localised") or e.get("SystemSecurity", ""))
    _pop_set(s, e)
    _s(s, e, "FuelLevel", "fuel_level", lambda v: f"{float(v):.1f}")
    s._state["body"] = ""
    s._state["body_type"] = ""


def _pop_set(s, e):
    pop = e.get("Population")
    if pop is not None:
        s._state["population"] = _pop(pop)


def _handle_startjump(s, e):
    s._state["jump_type"] = e.get("JumpType", "")


def _handle_supercruiseentry(s, e):
    s._state["jump_type"] = ""


def _handle_supercruiseexit(s, e):
    s._state["jump_type"] = ""
    s._state["body"] = e.get("Body", "")
    s._state["body_type"] = e.get("BodyType", "")


def _handle_docked(s, e):
    s._state["body"] = e.get("StationName", "")
    s._state["body_type"] = e.get("StationType", "Station")


def _handle_undocked(s, e):
    s._state["body"] = ""
    s._state["body_type"] = ""


def _handle_scan(s, e):
    s._state["last_scan"] = e.get("BodyName", "")
    dist = e.get("DistanceFromArrivalLS")
    if dist is not None:
        s._state["scan_distance"] = f"{dist:.1f} LS"


def _handle_fssdiscoveryscan(s, e):
    prog = e.get("Progress", 0)
    s._state["system_scan_pct"] = f"{prog * 100:.0f}%"


def _handle_fuelscp(s, e):
    s._state["fuel_scooped"] = f"{e.get('Scooped', 0):.1f}"
    t = e.get("Total")
    if t is not None:
        s._state["fuel_level"] = f"{float(t):.1f}"


def _handle_reservoirreplenished(s, e):
    v = e.get("FuelMain")
    if v is not None:
        s._state["fuel_level"] = f"{float(v):.1f}"


def _handle_shieldstate(s, e):
    s._status["shields_up"] = bool(e.get("ShieldsUp"))


def _handle_hulldamage(s, e):
    h = e.get("Health", 0)
    s._state["hull_health"] = f"{h * 100:.0f}%"


def _handle_repairall(s, e):
    s._state["hull_health"] = "100%"


def _handle_repair(s, e):
    item = e.get("Item", "")
    cost = e.get("Cost")
    s._state["last_repair"] = _clean(item) if item else ""
    if cost is not None:
        s._state["last_repair_cost"] = _credits(cost)


def _handle_shiptargeted(s, e):
    if e.get("TargetLocked"):
        s._state["target_ship"] = e.get("Ship_Localised") or e.get("Ship", "")
    else:
        s._state["target_ship"] = ""


def _handle_bounty(s, e):
    s._state["bounty_reward"] = _credits(e.get("TotalReward"))


def _handle_rank(s, e):
    ranks = {0: "Harmless", 1: "Mostly Harmless", 2: "Novice", 3: "Competent",
             4: "Expert", 5: "Master", 6: "Dangerous", 7: "Deadly", 8: "Elite",
             9: "Elite I", 10: "Elite II", 11: "Elite III", 12: "Elite IV", 13: "Elite V"}
    for k in ("Combat", "Trade", "Explore", "Empire", "Federation"):
        v = e.get(k)
        if v is not None:
            s._state[f"rank_{k.lower()}"] = ranks.get(v, str(v))


def _handle_progress(s, e):
    for k in ("Combat", "Trade", "Explore"):
        v = e.get(k)
        if v is not None:
            s._state[f"progress_{k.lower()}"] = f"{v}%"


def _handle_reputation(s, e):
    for k in ("Empire", "Federation"):
        v = e.get(k)
        if v is not None:
            key = f"rank_{k.lower()}"
            prev = s._state.get(key, "")
            s._state[key] = f"{prev} ({v:.0f}%)" if prev else f"{v:.0f}%"


def _handle_missionaccepted(s, e):
    s._state["mission"] = e.get("LocalisedName") or e.get("Name", "")
    r = e.get("Reward")
    s._state["mission_reward"] = _credits(r) if r else ""


def _handle_missioncompleted(s, e):
    s._state["mission"] = ""
    s._state["mission_reward"] = ""


def _handle_missionfailed(s, e):
    s._state["mission"] = ""
    s._state["mission_reward"] = ""


def _handle_cargo(s, e):
    s._state["cargo"] = str(e.get("Count", ""))


def _handle_statistics(s, e):
    bank = e.get("Bank_Account", {})
    w = bank.get("Current_Wealth")
    if w is not None:
        s._state["credits"] = _credits(w)


def _handle_powerplay(s, e):
    s._state["powerplay_power"] = e.get("Power", "")
    s._state["powerplay_rank"] = str(e.get("Rank", ""))
    s._state["powerplay_merits"] = _credits(e.get("Merits"))


def _handle_carrierstats(s, e):
    s._state["carrier_name"] = e.get("Name", "")
    s._state["carrier_callsign"] = e.get("Callsign", "")


def _handle_carrierlocation(s, e):
    s._state["system"] = e.get("StarSystem", "")


def _handle_carrierjump(s, e):
    s._state["system"] = e.get("StarSystem", "")
    if e.get("Docked"):
        s._state["body"] = e.get("StationName", "")


def _credits(val):
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


def _pop(val):
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


def read_journal_snapshot():
    """Read last journal events directly — no running instance needed."""
    from .journal_watcher import _newest_journal
    newest = _newest_journal()
    if not newest:
        return {"available": False, "state": {}, "status": {}}
    events = []
    try:
        with open(newest, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        return {"available": False, "state": {}, "status": {}}

    class _Snap:
        def __init__(self):
            self._state = {}
            self._status = {k: False for k in (
                "docked", "landed", "landing_gear", "shields_up", "supercruise",
                "flight_assist", "hardpoints", "wing_visible", "lights_on",
                "cargo_scoop", "silent_running", "scooping_fuel", "mass_locked",
                "in_srv", "in_fighter", "night_vision", "fsd_charging",
                "fsd_cooldown", "fsd_jump", "hyperdrive", "glide", "on_foot",
                "taxi", "multicrew",
            )}

    snap = _Snap()
    for event in events[-200:]:
        et = event.get("event", "")
        handler = _HANDLERS.get(et)
        if handler:
            handler(snap, event)
    return {"available": True, "state": dict(snap._state), "status": dict(snap._status)}
