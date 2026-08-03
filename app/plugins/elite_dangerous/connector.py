"""Iris-facing ED connector — thin interface between parser and plugin.

Data flow::

  watcher → parser → [this connector] → plugin → Iris

The connector owns the game state, provides clean accessors, and hides
the internal data model from both the plugin and the UI.
"""

import logging
import os
import threading

from .elite_parser import EliteParser
from .elite_journal_watcher import EliteJournalWatcher

log = logging.getLogger("iris.ed.connector")

# How many recent journal bytes to replay on connect.
_INIT_TAIL_BYTES = 30000
# Max raw events kept in the ring buffer.
_EVENT_LOG_MAX = 200
# Process whose presence means the game is running.
_GAME_EXE = "EliteDangerous64.exe"


class EDConnector:

    def __init__(self):
        self._watcher = EliteJournalWatcher()
        self._parser = EliteParser()

        self._lock = threading.Lock()
        self._game_active = False
        self._state = {}
        self._status = EliteParser.build_default_status()
        self._event_log = []
        self._event_types = set()

    # ── Lifecycle ────────────────────────────────────────────────

    def connect(self):
        """Initialise state from journal, then start live tailing."""
        self._init_state()
        self._watcher.start(
            on_event=self._on_event,
            on_status=self._on_status,
        )

    def disconnect(self):
        self._watcher.stop()

    # ── Iris-facing accessors ────────────────────────────────────

    @property
    def available(self):
        return self._game_active

    def game_running(self):
        """True while the Elite Dangerous process is alive.

        Status.json keeps its last contents on disk after the game exits,
        so cached flags (e.g. landing_gear) go stale.  Process presence is
        the reliable live check — focus-independent, unlike Status.json's
        write cadence (it pauses on alt-tab / station menus).
        """
        try:
            from plugin_manager import is_exe_running
            return is_exe_running(_GAME_EXE)
        except Exception:
            return False

    def live_state(self):
        """Game fields only — safe for high-frequency UI polling."""
        with self._lock:
            return dict(self._state)

    def state(self):
        """Full state including debug metadata and event log (snapshot only)."""
        with self._lock:
            s = dict(self._state)
            s["_journal_dir"] = self._watcher.journal_dir
            s["_current_file"] = self._watcher.current_file or "—"
            s["_total_events"] = len(self._event_log)
            s["_event_types"] = ", ".join(sorted(self._event_types))
            s["_latest_event_timestamp"] = (
                self._event_log[-1].get("timestamp", "—")
                if self._event_log else "—")
            s["_raw_events"] = list(self._event_log)
            return s

    def status(self):
        with self._lock:
            return dict(self._status)

    def event_log(self):
        with self._lock:
            return list(self._event_log)

    def event_types(self):
        with self._lock:
            return sorted(self._event_types)

    def journal_dir(self):
        return self._watcher.journal_dir

    def current_file(self):
        return self._watcher.current_file

    # ── Clean queries (hides internal state shape) ──────────────

    def get_current_system(self):
        with self._lock:
            return self._state.get("system", "")

    def get_ship(self):
        with self._lock:
            return self._state.get("ship", "")

    def get_location(self):
        with self._lock:
            return {
                "system": self._state.get("system", ""),
                "body": self._state.get("body", ""),
                "body_type": self._state.get("body_type", ""),
            }

    # ── Internal: state initialisation ───────────────────────────

    def _init_state(self):
        """Reconstruct current state from the latest journal tail.

        Uses a bounded read (last ~30 KB) to avoid full-file replay.
        """
        journal = EliteJournalWatcher.latest_journal()
        if not journal:
            log.info("[ed] no journal found at %s",
                     EliteJournalWatcher.journal_dir)
            return

        new_state = {}
        new_status = EliteParser.build_default_status()
        events = EliteJournalWatcher.read_tail(journal, _INIT_TAIL_BYTES)
        EliteParser.apply_many(events, new_state, new_status)

        status_now = EliteJournalWatcher.read_status()
        if status_now is not None:
            new_status.update(status_now)

        with self._lock:
            self._state = new_state
            self._status = new_status
            self._event_log = list(events)[-_EVENT_LOG_MAX:]
            self._event_types = {e.get("event", "?") for e in self._event_log}
            self._game_active = True

        log.info("[ed] init: %d events from %s → state keys=%d",
                 len(events), os.path.basename(journal), len(new_state))

    # ── Internal: live event handling ────────────────────────────

    def _on_event(self, event):
        with self._lock:
            EliteParser.apply(event, self._state, self._status)
            self._event_log.append(event)
            if len(self._event_log) > _EVENT_LOG_MAX:
                self._event_log.pop(0)
            et = event.get("event", "?")
            self._event_types.add(et)

    def _on_status(self, flags):
        with self._lock:
            self._status.update(flags)



