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

        # Load initial NavRoute from disk if present
        route_now = EliteJournalWatcher.read_navroute()
        if route_now:
            EliteParser.apply({"event": "NavRoute", "Route": route_now}, new_state, new_status)

        status_now = EliteJournalWatcher.read_status()
        if status_now is not None:
            new_status.update(status_now)
            if "fuel_main" in status_now:
                fm = status_now["fuel_main"]
                new_state["fuel_level"] = f"{float(fm):.1f}"
                new_state["fuel_main"] = fm
                cap = float(new_state.get("fuel_capacity") or 0.0)
                if cap > 0:
                    new_state["fuel_percent"] = round(min(100.0, max(0.0, (float(fm) / cap) * 100.0)), 1)
            if "fuel_reservoir" in status_now:
                new_state["fuel_reservoir"] = status_now["fuel_reservoir"]
            if "shield_percent" in status_now:
                new_state["shield_percent"] = status_now["shield_percent"]

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
            merged = dict(self._state)
            merged.update(self._status)

        try:
            import automations
            automations.get_engine().dispatch_state("plugin", "elite_dangerous", merged)
        except Exception:
            pass

    def _on_status(self, flags):
        with self._lock:
            # Status.json Flags bit 0x08 ("shields_up") is the real-time source
            # that drives the shield-down alert. The journal ShieldState event is
            # sparse and not written on every transition during combat, so relying
            # on it left the shield red alert not firing. Keep the flag.
            self._status.update(flags)
            if "fuel_main" in flags:
                fm = flags["fuel_main"]
                self._state["fuel_level"] = f"{float(fm):.1f}"
                self._state["fuel_main"] = fm
                cap = float(self._state.get("fuel_capacity") or 0.0)
                if cap > 0:
                    self._state["fuel_percent"] = round(min(100.0, max(0.0, (float(fm) / cap) * 100.0)), 1)
            if "fuel_reservoir" in flags:
                self._state["fuel_reservoir"] = flags["fuel_reservoir"]
            if "shield_percent" in flags:
                self._state["shield_percent"] = flags["shield_percent"]
            merged = dict(self._state)
            merged.update(self._status)

        try:
            import automations
            automations.get_engine().dispatch_state("plugin", "elite_dangerous", merged)
        except Exception:
            pass

    @classmethod
    def get_settings(cls):
        """Declare settings sections and controls for Elite Dangerous plugin."""
        from .binds_scanner import list_available_binds_files
        files = list_available_binds_files()
        options = [{"value": f, "label": f} for f in files]
        return [
            {
                "title": "Binds File Selection",
                "controls": [
                    {
                        "key": "selected_binds_file",
                        "label": "Active Binds File",
                        "type": "select",
                        "options": options,
                        "options_key": "available_binds_files",
                        "description": "Select the active in-game .binds file to parse and sync into Iris buttons."
                    }
                ]
            }
        ]



