"""Minimal ED journal watcher — tails the active journal and polls Status.json."""

import glob
import json
import logging
import os
import threading
import time

log = logging.getLogger("iris.ed.watcher")

_JOURNAL_DIR = os.path.join(
    os.environ.get("USERPROFILE", ""),
    "Saved Games", "Frontier Developments", "Elite Dangerous")

_STATUS_FILE = os.path.join(_JOURNAL_DIR, "Status.json")

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
    0x00010000: "mass_locked",
    0x00040000: "in_srv",
    0x00080000: "in_fighter",
    0x00200000: "night_vision",
    0x00800000: "fsd_charging",
    0x01000000: "fsd_cooldown",
    0x04000000: "fsd_jump",
    0x08000000: "hyperdrive",
    0x10000000: "glide",
    0x20000000: "on_foot",
    0x40000000: "taxi",
    0x80000000: "multicrew",
}


def parse_status_flags(flags_int):
    return {name: bool(flags_int & bit) for bit, name in _STATUS_FLAGS.items()}


def _newest_journal():
    files = glob.glob(os.path.join(_JOURNAL_DIR, "Journal.*.log"))
    return max(files, key=os.path.getmtime) if files else None


class JournalWatcher:

    def __init__(self):
        self.on_event = None
        self.on_status = None
        self.on_game_state = None
        self._running = False
        self._thread = None
        self._status_thread = None
        self._current_journal = None
        self._offset = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ed-journal")
        self._thread.start()
        self._status_thread = threading.Thread(target=self._status_loop, daemon=True, name="ed-status")
        self._status_thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception:
                log.exception("[ed] journal tick error")
            time.sleep(1.0)

    def _tick(self):
        newest = _newest_journal()
        if newest is None:
            if self._current_journal:
                self._current_journal = None
                self._offset = 0
                if self.on_game_state:
                    self.on_game_state("stopped")
            return

        if newest != self._current_journal:
            if self._current_journal and self.on_game_state:
                self.on_game_state("stopped")
            self._current_journal = newest
            self._offset = 0
            if self.on_game_state:
                self.on_game_state("started")

        try:
            size = os.path.getsize(newest)
            if size < self._offset:
                self._offset = 0
            if size == self._offset:
                return
            with open(newest, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if self.on_event:
                        try:
                            self.on_event(event)
                        except Exception:
                            log.exception("[ed] event callback error")
                self._offset = f.tell()
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("[ed] journal read error")

    def _status_loop(self):
        while self._running:
            try:
                if not os.path.isfile(_STATUS_FILE):
                    time.sleep(0.5)
                    continue
                with open(_STATUS_FILE, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                flags = parse_status_flags(data.get("Flags", 0))
                if self.on_status:
                    self.on_status(flags)
            except Exception:
                pass
            time.sleep(0.5)

    def read_last_n_events(self, n=50):
        if not self._current_journal:
            return []
        events = []
        try:
            with open(self._current_journal, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
        return events[-n:]
