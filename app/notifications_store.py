"""Iris — Persistent Notification Store and Anti-Spam Source Rule Manager."""

import json
import logging
import os
import sys
import threading
import time
import uuid

log = logging.getLogger("iris.notifications")

_LOCK = threading.RLock()
_STORE_CACHE = None
_STORE_MTIME = 0.0


def _store_path():
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA", ""), "Iris")
        os.makedirs(base, exist_ok=True)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "notifications.json")


def _load_store():
    global _STORE_CACHE, _STORE_MTIME
    path = _store_path()
    if not os.path.isfile(path):
        _STORE_CACHE = []
        _STORE_MTIME = 0.0
        return []
    try:
        mtime = os.path.getmtime(path)
        if _STORE_CACHE is not None and mtime == _STORE_MTIME:
            return list(_STORE_CACHE)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                _STORE_CACHE = data
            elif isinstance(data, dict) and "notifications" in data:
                _STORE_CACHE = data["notifications"]
            else:
                _STORE_CACHE = []
            _STORE_MTIME = mtime
            return list(_STORE_CACHE)
    except Exception as ex:
        log.warning("[notif_store] failed to load notifications: %s", ex)
    return list(_STORE_CACHE if _STORE_CACHE is not None else [])


def _save_store(items):
    global _STORE_CACHE, _STORE_MTIME
    path = _store_path()
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        if os.path.isfile(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)
        _STORE_CACHE = list(items)
        try:
            _STORE_MTIME = os.path.getmtime(path)
        except Exception:
            _STORE_MTIME = time.time()
    except Exception as ex:
        log.warning("[notif_store] failed to save notifications: %s", ex)
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def _get_config():
    try:
        from config import load_config
        return load_config()
    except Exception:
        return {}


def _save_config(cfg):
    try:
        from config import save_config
        save_config(cfg)
    except Exception:
        pass


def get_source_rule(app_name):
    """Return rule for source: 'normal', 'demote_to_events', or 'muted'."""
    if not app_name:
        return "normal"
    cfg = _get_config()
    rules = cfg.get("notification_rules") or {}
    # Case-insensitive lookup
    norm_app = str(app_name).strip().lower()
    for k, v in rules.items():
        if str(k).strip().lower() == norm_app:
            return v
    return "normal"


def set_source_rule(app_name, rule):
    """Set rule for a source: 'normal', 'demote_to_events', or 'muted'."""
    if not app_name:
        return
    cfg = _get_config()
    if not isinstance(cfg.get("notification_rules"), dict):
        cfg["notification_rules"] = {}
    if rule not in ("normal", "demote_to_events", "muted"):
        rule = "normal"
    if rule == "normal":
        cfg["notification_rules"].pop(app_name, None)
    else:
        cfg["notification_rules"][app_name] = rule
    _save_config(cfg)


def get_source_rules():
    """Return full dict of source rules."""
    cfg = _get_config()
    return cfg.get("notification_rules") or {}


def get_max_stored():
    """Return max active notifications capacity limit."""
    cfg = _get_config()
    return max(10, min(500, int(cfg.get("max_stored_notifications", 50))))


def set_max_stored(limit):
    """Update max stored notifications limit."""
    limit = max(10, min(500, int(limit)))
    cfg = _get_config()
    cfg["max_stored_notifications"] = limit
    _save_config(cfg)
    # Trim existing store if necessary
    with _LOCK:
        items = _load_store()
        active = [n for n in items if not n.get("archived")]
        archived = [n for n in items if n.get("archived")]
        if len(active) > limit:
            active = active[:limit]
            _save_store(active + archived)


def add_notification(app, title, body, theme="purple", timestamp=None):
    """Add a persistent notification adhering to anti-spam rules and capacity limits.
    
    Returns a dict with {"ok": True, "notification": item, "demoted": bool, "muted": bool}.
    """
    app_name = str(app or "System").strip()
    rule = get_source_rule(app_name)

    if rule == "muted":
        log.debug("[notif_store] dropped notification from muted source %s", app_name)
        return {"ok": False, "muted": True}

    is_alert = (str(theme).lower() in ("alert", "red"))
    if rule == "demote_to_events" or is_alert:
        log.debug("[notif_store] demoting notification from %s to event", app_name)
        return {
            "ok": True,
            "demoted": True,
            "event": {
                "app": app_name,
                "title": str(title or "").strip(),
                "body": str(body or "").strip(),
                "status": "bad" if is_alert else "info",
                "timestamp": timestamp or time.time(),
            }
        }

    item = {
        "id": f"notif_{int(time.time())}_{uuid.uuid4().hex[:6]}",
        "app": app_name,
        "title": str(title or "").strip(),
        "body": str(body or "").strip(),
        "theme": theme or "purple",
        "archived": False,
        "timestamp": float(timestamp or time.time()),
    }

    with _LOCK:
        items = _load_store()
        # Insert newest at index 0
        active = [item] + [n for n in items if not n.get("archived")]
        archived = [n for n in items if n.get("archived")]

        max_limit = get_max_stored()
        if len(active) > max_limit:
            active = active[:max_limit]

        _save_store(active + archived)

    return {"ok": True, "demoted": False, "notification": item}


def get_notifications(include_archived=True):
    """Return all notifications partitioned into active and archived lists."""
    with _LOCK:
        items = _load_store()
        # Filter out any transient alert/red notifications from library
        items = [n for n in items if str(n.get("theme", "")).lower() not in ("alert", "red")]
        # Sort newest first
        items.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        active = [n for n in items if not n.get("archived")]
        archived = [n for n in items if n.get("archived")]
        
        # Discovered sources + configured rules + common known sources
        discovered = {n.get("app") for n in items if n.get("app")}
        rules = get_source_rules()
        discovered.update(rules.keys())
        discovered.add("Elite Dangerous")
        discovered.add("Windows Notifications")
        discovered.add("Vision")
        discovered.add("Media")
        discovered.add("System")
        sources = sorted(list({s.strip() for s in discovered if s and s.strip()}))
        
        return {
            "notifications": active,
            "archived": archived,
            "max_stored": get_max_stored(),
            "rules": rules,
            "sources": sources,
        }


def get_last_notification():
    """Return the most recent active persistent notification (or None)."""
    with _LOCK:
        items = _load_store()
        active = [n for n in items if not n.get("archived") and str(n.get("theme", "")).lower() not in ("alert", "red")]
        if active:
            active.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return active[0]
        regular = [n for n in items if str(n.get("theme", "")).lower() not in ("alert", "red")]
        if regular:
            regular.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return regular[0]
    return None


def delete_notification(notif_id):
    """Delete a single notification by id."""
    with _LOCK:
        items = _load_store()
        new_items = [n for n in items if n.get("id") != notif_id]
        if len(new_items) != len(items):
            _save_store(new_items)
            return True
    return False


def delete_all(include_archived=False):
    """Delete all active notifications (or all if include_archived is True)."""
    with _LOCK:
        if include_archived:
            _save_store([])
        else:
            items = _load_store()
            archived_only = [n for n in items if n.get("archived")]
            _save_store(archived_only)
    return True


def set_archived(notif_id, archived=True):
    """Set archived state for a notification by id."""
    with _LOCK:
        items = _load_store()
        found = False
        for n in items:
            if n.get("id") == notif_id:
                n["archived"] = bool(archived)
                found = True
                break
        if found:
            _save_store(items)
            return True
    return False


def archive_all():
    """Archive all currently active notifications."""
    with _LOCK:
        items = _load_store()
        for n in items:
            if not n.get("archived"):
                n["archived"] = True
        _save_store(items)
    return True
