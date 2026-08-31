"""Filesystem-only ED journal watcher.

No Iris or UI knowledge.  Finds journal files, reads lines,
detects new entries, polls Status.json.
"""

import glob
import json
import logging
import os
import threading
import time

log = logging.getLogger("iris.ed.watcher")

JOURNALS_DIR = os.path.join(
    os.environ.get("USERPROFILE", ""),
    "Saved Games", "Frontier Developments", "Elite Dangerous")

STATUS_PATH = os.path.join(JOURNALS_DIR, "Status.json")
NAVROUTE_PATH = os.path.join(JOURNALS_DIR, "NavRoute.json")

_STATUS_FLAGS = {
    0x00000001: "docked",
    0x00000002: "landed",
    0x00000004: "landing_gear",
    0x00000008: "shields_up",
    0x00000010: "supercruise",
    0x00000020: "flight_assist",
    0x00000040: "hardpoints",
    0x00000080: "wing_visible",
    0x00000100: "lights_on",
    0x00000200: "cargo_scoop",
    0x00000400: "silent_running",
    0x00000800: "scooping_fuel",
    0x00001000: "srv_handbrake",
    0x00002000: "srv_turret",
    0x00004000: "srv_under_ship",
    0x00008000: "srv_drive_assist",
    0x00010000: "mass_locked",
    0x00020000: "fsd_charging",
    0x00040000: "fsd_cooldown",
    0x00080000: "low_fuel",
    0x00100000: "overheating",
    0x00200000: "has_lat_long",
    0x00400000: "is_in_danger",
    0x00800000: "being_interdicted",
    0x01000000: "in_mainship",
    0x02000000: "in_fighter",
    0x04000000: "in_srv",
    0x08000000: "hud_analysis_mode",
    0x10000000: "night_vision",
    0x20000000: "alt_from_avg_radius",
    0x40000000: "fsd_jump",
    0x80000000: "srv_high_beam",
}


def _parse_status_flags(data):
    if isinstance(data, int):
        flags_int = data
        data_dict = {}
    elif isinstance(data, dict):
        flags_int = data.get("Flags", 0)
        data_dict = data
    else:
        flags_int = 0
        data_dict = {}

    res = {name: bool(flags_int & bit) for bit, name in _STATUS_FLAGS.items()}

    # Extract live numeric telemetry values if present in Status.json
    if "ShieldPercent" in data_dict:
        try:
            res["shield_percent"] = round(float(data_dict["ShieldPercent"]) * 100.0, 1)
        except Exception:
            pass
    if "Fuel" in data_dict and isinstance(data_dict["Fuel"], dict):
        try:
            res["fuel_main"] = round(float(data_dict["Fuel"].get("FuelMain", 0.0)), 1)
            res["fuel_reservoir"] = round(float(data_dict["Fuel"].get("FuelReservoir", 0.0)), 2)
        except Exception:
            pass
    if "Cargo" in data_dict:
        try:
            res["cargo_count"] = int(data_dict["Cargo"])
        except Exception:
            pass
    if "LegalStatus" in data_dict:
        res["legal_status"] = str(data_dict["LegalStatus"])
    if "FireGroup" in data_dict:
        res["fire_group"] = int(data_dict["FireGroup"])
    if "GuiFocus" in data_dict:
        res["gui_focus"] = int(data_dict["GuiFocus"])
    if "Pips" in data_dict and isinstance(data_dict["Pips"], list):
        res["pips"] = data_dict["Pips"]

    return res


def _glob_journals():
    return sorted(
        glob.glob(os.path.join(JOURNALS_DIR, "Journal.*.log")),
        key=os.path.getmtime)


def _latest_journal():
    files = _glob_journals()
    return files[-1] if files else None


def _read_events(path, offset=0):
    """Read lines from *path* starting at *offset*.

    Returns ``(events, new_offset)`` where *events* is a list of
    parsed JSON dicts and *new_offset* is the byte offset to resume
    from.  Lines that fail JSON decoding are silently skipped.
    """
    events = []
    try:
        size = os.path.getsize(path)
        if offset > size:
            offset = 0
        if offset == size:
            return events, offset
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            offset = f.tell()
    except (FileNotFoundError, PermissionError):
        pass
    return events, offset


def _read_tail(path, approx_bytes=20000):
    """Read the last *approx_bytes* of *path* and parse all complete lines.

    Seeks backward from end of file so the returned events are the
    newest.  This is the bounded-history entry point — no full replay.
    """
    events = []
    try:
        size = os.path.getsize(path)
        start = max(0, size - approx_bytes)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(start)
            if start > 0:
                f.readline()
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except (FileNotFoundError, PermissionError):
        pass
    return events


class EliteJournalWatcher:
    """Finds journal files, reads events, tails for new lines.

    Two background threads:
      - **Journal thread** — polls the latest ``Journal.*.log`` at 1 Hz
        and calls ``on_event(e)`` for each new line.
      - **Status thread** — polls ``Status.json`` at 2 Hz and calls
        ``on_status(flags)``.
    """

    def __init__(self):
        self.on_event = None
        self.on_status = None

        self._lock = threading.Lock()
        self._running = False
        self._journal_thread = None
        self._status_thread = None
        self._current_file = None
        self._current_offset = 0

    # ── Public properties ────────────────────────────────────────

    @property
    def journal_dir(self):
        return JOURNALS_DIR

    @property
    def current_file(self):
        with self._lock:
            return self._current_file

    @property
    def current_offset(self):
        with self._lock:
            return self._current_offset

    # ── Static helpers (no instance state) ───────────────────────

    @staticmethod
    def find_journals():
        return _glob_journals()

    @staticmethod
    def latest_journal():
        return _latest_journal()

    @staticmethod
    def read_navroute():
        """Read and parse NavRoute.json. Returns list of route dicts or None."""
        if not os.path.isfile(NAVROUTE_PATH):
            return None
        try:
            with open(NAVROUTE_PATH, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            return data.get("Route") if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def read_status():
        """Read and parse Status.json.  Returns flag/telemetry dict or None."""
        if not os.path.isfile(STATUS_PATH):
            return None
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _parse_status_flags(data)
        except Exception:
            return None

    @staticmethod
    def read_all_events(path, max_events=0):
        """Convenience: read *path* from the beginning.

        If *max_events* > 0 only the last *max_events* are returned.
        Returns ``(events, final_offset)``.
        """
        ev, off = _read_events(path, offset=0)
        if max_events > 0 and len(ev) > max_events:
            ev = ev[-max_events:]
        return ev, off

    @staticmethod
    def read_tail(path, approx_bytes=20000):
        """Read the newest *approx_bytes* of *path*.

        Returns parsed events (newest last).  Zero full-file replay.
        """
        return _read_tail(path, approx_bytes)

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self, on_event=None, on_status=None):
        if on_event is not None:
            self.on_event = on_event
        if on_status is not None:
            self.on_status = on_status
        if self._running:
            return
        
        # Fast-forward to end of current journal so startup does not replay historical events
        newest = _latest_journal()
        if newest and os.path.isfile(newest):
            with self._lock:
                self._current_file = newest
                try:
                    self._current_offset = os.path.getsize(newest)
                except Exception:
                    self._current_offset = 0

        self._running = True
        self._journal_thread = threading.Thread(
            target=self._journal_loop, daemon=True, name="ed-journal")
        self._journal_thread.start()
        self._status_thread = threading.Thread(
            target=self._status_loop, daemon=True, name="ed-status")
        self._status_thread.start()

    def stop(self):
        self._running = False

    # ── Internals ────────────────────────────────────────────────

    def _journal_loop(self):
        while self._running:
            try:
                self._journal_tick()
            except Exception:
                log.exception("[ed] journal tick error")
            time.sleep(1.0)

    def _status_loop(self):
        last_navroute_mtime = 0.0
        while self._running:
            try:
                if os.path.isfile(STATUS_PATH):
                    with open(STATUS_PATH, "r", encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    flags = _parse_status_flags(data)
                    if self.on_status:
                        self.on_status(flags)
            except Exception:
                pass

            try:
                if os.path.isfile(NAVROUTE_PATH):
                    mtime = os.path.getmtime(NAVROUTE_PATH)
                    if mtime != last_navroute_mtime:
                        last_navroute_mtime = mtime
                        with open(NAVROUTE_PATH, "r", encoding="utf-8", errors="replace") as f:
                            route_data = json.load(f)
                        if isinstance(route_data, dict) and self.on_event:
                            self.on_event(route_data)
            except Exception:
                pass
            time.sleep(0.5)

    def _journal_tick(self):
        newest = _latest_journal()

        if newest is None:
            with self._lock:
                if self._current_file is not None:
                    self._current_file = None
                    self._current_offset = 0
            return

        with self._lock:
            file_changed = newest != self._current_file
            if file_changed:
                self._current_file = newest
                self._current_offset = 0

            events, new_offset = _read_events(newest, self._current_offset)
            self._current_offset = new_offset

        if events and self.on_event:
            for ev in events:
                try:
                    self.on_event(ev)
                except Exception:
                    log.exception("[ed] event callback error")
