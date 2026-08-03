"""Device-agnostic display intent arbiter.

Plugins and core providers publish typed intents (notify / alert / sticky /
progress).  This module decides what wins, when it ends, and asks a thin
transport callback to emit device commands.  No plugin or game names live
here — keys are opaque strings owned by the caller.
"""

from __future__ import annotations

import logging
import time
from collections import deque

from device_profile import MATRIX
from display_priority import (
    PRIO_CORE_NOTIFY,
    PRIO_PLUGIN_ALERT,
    PRIO_PLUGIN_NOTIFY,
    NOTIFY_WINDOW_S,
)

log = logging.getLogger("iris.display")

# Text channel kinds
_KIND_NOTIFY = "notify"
_KIND_ALERT = "alert"
_KIND_STICKY = "sticky"


class DisplayManager:
    """Dual-channel arbiter: TEXT (alert/notify/sticky) + PROGRESS."""

    def __init__(self, write_fn, profile_fn=None):
        """
        write_fn(line: str) -> bool
            Must be safe to call while the caller's lock is held (or re-entrant).
        profile_fn() -> DeviceProfile
        """
        self._write = write_fn
        self._profile_fn = profile_fn or (lambda: MATRIX)

        self._claims = {}
        self._prog_sent = None

        # Foreground text intent (one at a time).
        self._text_active = None  # dict or None
        # Equal-priority notify queue: (key, title, message, priority, style)
        self._text_queue = deque(maxlen=8)

        # Registry of hold/sticky keys still "owned" after wire emit
        # (for clear / clear_prefix).  Active text is also listed here.
        self._held = {}  # key -> kind snapshot

    @property
    def _profile(self):
        return self._profile_fn()

    # ── Public intent API ──────────────────────────────────────

    def notify(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Transient scrolling/static message.

        ``style``: ``normal`` (5×7) or ``emphasis`` (device big-font path).
        Same ``key`` replaces an in-flight text intent with that key.
        """
        key = self._norm_key(key)
        title = self._clean(title, 60)
        message = self._clean(message, 120)
        display = self._display_text(title, message)
        now = time.monotonic()
        intent = {
            "kind": _KIND_NOTIFY,
            "key": key,
            "title": title,
            "message": message,
            "display": display,
            "priority": int(priority),
            "style": "emphasis" if style == "emphasis" else "normal",
            "until": now + self._notify_duration_s(display),
        }
        self._submit_text(intent, now)

    def alert(self, key, text, *, mode="blink", lifetime="hold",
              timed_s=5.0, priority=PRIO_PLUGIN_ALERT):
        """High-priority ≤4-char alert (matrix: 8×8 bold).

        lifetime: ``hold`` until clear(key), or ``timed``.
        mode: ``blink`` or ``solid``.
        """
        key = self._norm_key(key)
        letters = self._alert_text(text)
        mode = "solid" if mode == "solid" else "blink"
        lifetime = "timed" if lifetime == "timed" else "hold"
        p = self._profile
        now = time.monotonic()
        if lifetime == "timed":
            dur = max(0.5, float(timed_s))
            dur = min(dur, p.alert_max_hold_ms / 1000.0)
        else:
            dur = p.alert_max_hold_ms / 1000.0
        intent = {
            "kind": _KIND_ALERT,
            "key": key,
            "text": letters,
            "mode": mode,
            "lifetime": lifetime,
            "priority": int(priority),
            "until": now + dur,
        }
        self._submit_text(intent, now)

    def sticky(self, key, title, message, *, ttl_s=None, priority=PRIO_PLUGIN_NOTIFY):
        """Scroll once, then hold settled text until clear / ttl / preempt."""
        key = self._norm_key(key)
        title = self._clean(title, 60)
        message = self._clean(message, 120)
        display = self._display_text(title, message)
        p = self._profile
        now = time.monotonic()
        if ttl_s is None:
            dur = p.sticky_max_hold_ms / 1000.0
        else:
            dur = max(0.5, min(float(ttl_s), p.sticky_max_hold_ms / 1000.0))
        # PC-side until covers scroll phase + hold; firmware sticks until OFF.
        scroll_s = self._notify_duration_s(display)
        intent = {
            "kind": _KIND_STICKY,
            "key": key,
            "title": title,
            "message": message,
            "display": display,
            "priority": int(priority),
            "until": now + max(scroll_s, dur),
        }
        self._submit_text(intent, now)

    def clear(self, key):
        """Dismiss text intent(s) with this key (active or held)."""
        key = self._norm_key(key)
        if not key:
            return
        active = self._text_active
        if active is not None and active.get("key") == key:
            self._end_text_active(emit_off=True)
        self._held.pop(key, None)
        # Drop queued notifies with this key
        if self._text_queue:
            self._text_queue = deque(
                (i for i in self._text_queue if i[0] != key),
                maxlen=self._text_queue.maxlen,
            )
        self._promote_text()

    def clear_prefix(self, prefix):
        """Dismiss all text intents whose key starts with ``prefix``."""
        prefix = str(prefix or "")
        if not prefix:
            return
        keys = set()
        if self._text_active and str(self._text_active.get("key", "")).startswith(prefix):
            keys.add(self._text_active["key"])
        keys.update(k for k in self._held if k.startswith(prefix))
        if self._text_queue:
            keys.update(i[0] for i in self._text_queue if str(i[0]).startswith(prefix))
        for k in keys:
            self.clear(k)

    def claim_progress(self, claim_id, priority, name, pct,
                       keepalive_s=3.0, ttl_s=10.0):
        keepalive_s = max(1.0, min(float(keepalive_s),
                                   self._profile.progress_timeout_ms / 1000.0 - 1.0))
        self._claims[str(claim_id)] = {
            "mode": "persistent",
            "priority": priority,
            "name": name,
            "pct": pct,
            "keepalive_s": keepalive_s,
            "ttl_s": float(ttl_s),
            "last": time.monotonic(),
        }
        self.tick_progress()

    def remind_progress(self, claim_id, priority, name, pct,
                        on_s=3.0, period_s=10.0):
        on_s = max(0.5, float(on_s))
        period_s = max(on_s + 0.5, float(period_s))
        now = time.monotonic()
        cid = str(claim_id)
        cur = self._claims.get(cid)
        if cur is not None and cur["mode"] == "reminder":
            cur["name"] = name
            cur["pct"] = pct
            cur["last"] = now
        else:
            self._claims[cid] = {
                "mode": "reminder",
                "priority": priority,
                "name": name,
                "pct": pct,
                "on_s": on_s,
                "period_s": period_s,
                "next_on": now,
                "active_until": now + on_s,
                "need_send": True,
                "keepalive_s": 999.0,
                "ttl_s": 10.0,
                "last": now,
            }
        self.tick_progress()

    def release_progress(self, claim_id):
        self._claims.pop(str(claim_id), None)
        self.tick_progress()

    def release_progress_prefix(self, prefix):
        prefix = str(prefix or "")
        if not prefix:
            return
        for cid in [c for c in self._claims if c.startswith(prefix)]:
            del self._claims[cid]
        self.tick_progress()

    # ── Ticker (called by serial arbiter thread) ────────────────

    def tick(self):
        self.tick_progress()
        self.tick_text()

    def tick_text(self):
        now = time.monotonic()
        active = self._text_active
        if active is not None and now >= active["until"]:
            # Timed end: alerts/stickies on hold may still need OFF on wire
            # if lifetime was timed or sticky ttl elapsed.
            self._end_text_active(emit_off=True)
        self._promote_text()

    def tick_progress(self):
        now = time.monotonic()
        expired = [cid for cid, c in self._claims.items()
                   if now - c["last"] >= c["ttl_s"]]
        for cid in expired:
            del self._claims[cid]

        for c in self._claims.values():
            if c["mode"] != "reminder":
                continue
            while now >= c["active_until"]:
                c["next_on"] += c["period_s"]
                c["active_until"] = c["next_on"] + c["on_s"]
                c["need_send"] = True

        # TEXT and PROGRESS are independent channels when the device layers
        # them; never pause PROG keepalives for notifications.
        candidates = [c for c in self._claims.values()
                      if c["mode"] != "reminder"
                      or (now >= c["next_on"] and now < c["active_until"])]
        winner = None
        if candidates:
            winner = max(candidates, key=lambda c: (c["priority"], c["last"]))
        sent = self._prog_sent

        if winner is None:
            if sent is not None:
                self._write("PROG:OFF\n")
                self._prog_sent = None
            return

        force = bool(winner.get("need_send", False))
        changed = (sent is None
                   or sent["name"] != winner["name"]
                   or sent["pct"] != winner["pct"])
        stale = sent is not None and (now - sent["t"]) >= winner["keepalive_s"]
        if force or changed or stale:
            name = self._clean(winner["name"], self._profile.progress_name_max_full)
            pct = max(0, min(100, int(winner["pct"])))
            self._write(f"PROG:{name}|{pct}\n")
            self._prog_sent = {
                "name": winner["name"],
                "pct": winner["pct"],
                "t": now,
            }
            if force:
                winner["need_send"] = False

    # ── Text channel internals ──────────────────────────────────

    def _submit_text(self, intent, now):
        key = intent["key"]
        prio = intent["priority"]
        active = self._text_active

        # Same key always replaces (cancel + re-show).
        if active is not None and active.get("key") == key:
            self._end_text_active(emit_off=True)
            active = None

        if active is not None and now < active["until"]:
            ap = active["priority"]
            if prio < ap:
                return
            if prio == ap:
                # Same key already cleared above. Equal-prio notify queues;
                # alerts/sticky do not steal from an equal peer.
                if (intent["kind"] == _KIND_NOTIFY
                        and active["kind"] == _KIND_NOTIFY):
                    self._text_queue.append(
                        (key, intent["title"], intent["message"], prio,
                         intent.get("style", "normal"))
                    )
                return
            self._end_text_active(emit_off=True)
        elif prio < PRIO_CORE_NOTIFY and self._core_queued():
            return

        self._activate_text(intent)

    def _activate_text(self, intent):
        self._text_active = intent
        self._held[intent["key"]] = intent["kind"]
        self._emit_text(intent)

    def _emit_text(self, intent):
        kind = intent["kind"]
        if kind == _KIND_ALERT:
            mode = intent.get("mode", "blink")
            self._write(f"ALERT:{intent['text']}|{mode}\n")
            return
        if kind == _KIND_STICKY:
            t, m = intent["title"], intent["message"]
            self._write(f"STICKY:{t}|{m}\n")
            return
        # notify
        t, m = intent["title"], intent["message"]
        if intent.get("style") == "emphasis":
            self._write(f"VISION:{t}|{m}\n")
        else:
            self._write(f"NOTIFY:{t}|{m}\n")

    def _end_text_active(self, emit_off=False):
        active = self._text_active
        if active is None:
            return
        if emit_off:
            kind = active["kind"]
            if kind == _KIND_ALERT:
                self._write("ALERT:OFF\n")
            elif kind == _KIND_STICKY:
                self._write("STICKY:OFF\n")
            # notify/vision: firmware times out; no OFF required
        key = active.get("key")
        if key:
            self._held.pop(key, None)
        self._text_active = None

    def _promote_text(self):
        now = time.monotonic()
        if self._text_active is not None and now < self._text_active["until"]:
            return
        if self._text_active is not None:
            self._end_text_active(emit_off=True)
        if not self._text_queue:
            return
        key, title, message, prio, style = self._text_queue.popleft()
        display = self._display_text(title, message)
        intent = {
            "kind": _KIND_NOTIFY,
            "key": key,
            "title": title,
            "message": message,
            "display": display,
            "priority": prio,
            "style": style,
            "until": now + self._notify_duration_s(display),
        }
        self._activate_text(intent)

    def _core_queued(self):
        return any(item[3] >= PRIO_CORE_NOTIFY for item in self._text_queue)

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _norm_key(key):
        if key is None or key == "":
            return f"anon.{time.monotonic_ns()}"
        return str(key)[:80]

    @staticmethod
    def _clean(s, n):
        return str(s or "").replace("|", " ").replace("\n", " ")[:n]

    @staticmethod
    def _display_text(title, message):
        if title and message:
            return f"{title} - {message} "
        if title:
            return f"{title} "
        return f"{message} "

    @staticmethod
    def _alert_text(text):
        letters = "".join(c for c in str(text or "") if c.isalnum())[:4].upper()
        return letters or "!!!!"

    def _notify_duration_s(self, display):
        p = self._profile
        if not display:
            return NOTIFY_WINDOW_S
        pitch = 6
        tw = len(display) * pitch
        if tw <= p.width_px:
            return p.notify_static_ms / 1000.0
        pixels = p.width_px + tw
        needed_ms = pixels * p.text_step_ms + 2000
        return max(needed_ms, p.notify_window_ms) / 1000.0
