"""Library and screenshots API handler mixin for Iris server."""

import json
import logging
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import paths

log = logging.getLogger("iris.server.library")


class LibraryHandlerMixin:
    """Provides screenshot & note library routes to RequestHandler."""

    def _broadcast_update(self, msg):
        try:
            import ws_bridge
            ws_bridge.broadcast(msg)
        except Exception:
            pass

    def _handle_screenshot_latest(self):
        """Return the most recent screenshot captured by the Tk dialog."""
        app = self._get_app_ref()
        if app is None:
            self._send_json({"available": False, "seq": 0})
            return
        data = getattr(app, "screenshot_last", None)
        if not data:
            self._send_json({"available": False, "seq": getattr(app, "screenshot_seq", 0)})
            return
        self._send_json({"available": True, **data})

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

    def _screenshots_folder(self):
        app = self._get_app_ref()
        cfg = getattr(app, "cfg", None) if app is not None else None
        return paths.get_screenshots_dir(cfg)

    def _notes_folder(self):
        app = self._get_app_ref()
        cfg = getattr(app, "cfg", None) if app is not None else None
        return paths.get_notes_dir(cfg)

    def _library_folders(self):
        folders = []
        sf = self._screenshots_folder()
        nf = self._notes_folder()
        for f in (sf, nf):
            if f and f not in folders:
                folders.append(f)
        legacy = os.path.abspath(os.path.join(os.path.expanduser("~"), "Documents", "Iris", "Screenshots"))
        if os.path.isdir(legacy) and legacy not in folders:
            folders.append(legacy)
        return folders

    def _find_library_file(self, filename):
        fname = os.path.basename(filename)
        for folder in self._library_folders():
            cand = os.path.join(folder, fname)
            if os.path.isfile(cand):
                return folder, cand
        if fname.lower().endswith(".txt"):
            return self._notes_folder(), os.path.join(self._notes_folder(), fname)
        return self._screenshots_folder(), os.path.join(self._screenshots_folder(), fname)

    def _library_folder(self):
        """Legacy helper returning screenshots folder."""
        return self._screenshots_folder()

    def _parse_library_filename(self, fname):
        """Extract app name and timestamp from an iris_* filename."""
        m = re.match(r'^iris_note_(.+)_(\d{8}_\d{6})\.txt$', fname)
        if m:
            return {"type": "note", "app": m.group(1), "ts_str": m.group(2)}
        m = re.match(r'^iris_([a-z0-9_]+)_(\d{8})_(\d{6})\.png$', fname)
        if m:
            app = m.group(1)
            ts_str = m.group(2) + "_" + m.group(3)
            return {"type": "screenshot", "app": app, "ts_str": ts_str}
        m = re.match(r'^iris_(\d{8})_(\d{6})\.png$', fname)
        if m:
            ts_str = m.group(1) + "_" + m.group(2)
            return {"type": "screenshot", "app": "unknown", "ts_str": ts_str}
        return None

    def _ts_from_str(self, ts_str):
        """Convert YYYYMMDD_HHMMSS -> unix timestamp."""
        try:
            return time.mktime(time.strptime(ts_str, "%Y%m%d_%H%M%S"))
        except Exception:
            return 0.0

    def _sidecar_path(self, folder, img_fname):
        base = os.path.splitext(img_fname)[0]
        return os.path.join(folder, base + ".json")

    def _handle_library_items(self):
        """List all screenshots and notes across the library folders."""
        items = []
        seen = set()
        try:
            for folder in self._library_folders():
                if not os.path.isdir(folder):
                    continue
                all_files = os.listdir(folder)
                for fname in all_files:
                    if fname in seen:
                        continue
                    meta = self._parse_library_filename(fname)

                    if meta is None:
                        if fname.lower().endswith(".png"):
                            fpath = os.path.join(folder, fname)
                            ts = os.path.getmtime(fpath) if os.path.isfile(fpath) else 0.0
                            sc_path = self._sidecar_path(folder, fname)
                            title = ""
                            if os.path.isfile(sc_path):
                                try:
                                    with open(sc_path, encoding="utf-8") as f:
                                        sc = json.load(f)
                                    title = sc.get("title", "")
                                except Exception:
                                    pass
                            seen.add(fname)
                            items.append({
                                "type": "screenshot",
                                "filename": fname,
                                "app": "orphan",
                                "ts": ts,
                                "title": title,
                            })
                        continue

                    seen.add(fname)
                    ts = self._ts_from_str(meta["ts_str"])

                    if meta["type"] == "screenshot":
                        sc_path = self._sidecar_path(folder, fname)
                        title = ""
                        if os.path.isfile(sc_path):
                            try:
                                with open(sc_path, encoding="utf-8") as f:
                                    sc = json.load(f)
                                title = sc.get("title", "")
                            except Exception:
                                pass
                        items.append({
                            "type": "screenshot",
                            "filename": fname,
                            "app": meta["app"],
                            "ts": ts,
                            "title": title,
                        })

                    elif meta["type"] == "note":
                        title = ""
                        preview = ""
                        fpath = os.path.join(folder, fname)
                        try:
                            with open(fpath, encoding="utf-8") as f:
                                content = f.read(500)
                            lines = content.split("\n")
                            body_lines = []
                            for idx, line in enumerate(lines):
                                if idx == 0 and line.startswith("title:"):
                                    title = line[6:].strip()
                                else:
                                    clean_line = re.sub(r"<[^>]+>", " ", line)
                                    clean_line = clean_line.replace("&nbsp;", " ").strip()
                                    if clean_line:
                                        body_lines.append(clean_line)
                            preview = body_lines[0][:80] if body_lines else ""
                        except Exception:
                            pass
                        items.append({
                            "type": "note",
                            "filename": fname,
                            "app": meta["app"],
                            "ts": ts,
                            "title": title,
                            "preview": preview,
                        })

            items.sort(key=lambda x: x["ts"], reverse=True)
            self._send_json({"items": items})
        except Exception as e:
            log.warning("library items error: %s", e)
            self._send_json({"items": []})

    def _handle_library_image(self, filename):
        """Serve a PNG from the library folder."""
        filename = unquote(filename.split("?")[0])
        filename = os.path.basename(filename)
        if not filename.lower().endswith(".png"):
            self.send_error(400)
            return
        folder, path = self._find_library_file(filename)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            log.warning("library image serve error: %s", e)
            self.send_error(500)

    def _handle_library_get_sidecar(self, filename):
        """Return sidecar JSON for a screenshot (empty object if none exists)."""
        filename = os.path.basename(filename)
        folder, _ = self._find_library_file(filename)
        sc_path = self._sidecar_path(folder, filename)
        if not os.path.isfile(sc_path):
            self._send_json({})
            return
        try:
            with open(sc_path, encoding="utf-8") as f:
                self._send_json(json.load(f))
        except Exception:
            self._send_json({})

    def _handle_library_save_sidecar(self, filename):
        """Save sidecar JSON for a screenshot."""
        filename = os.path.basename(filename)
        folder, img_path = self._find_library_file(filename)
        if not os.path.isfile(img_path):
            self.send_error(404)
            return
        try:
            body = self._read_json()
            sc_path = self._sidecar_path(folder, filename)
            existing = {}
            if os.path.isfile(sc_path):
                try:
                    with open(sc_path, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
            if "title" in body:
                existing["title"] = str(body["title"])
            if "annotations" in body and isinstance(body["annotations"], list):
                existing["annotations"] = body["annotations"]
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False)
            self._broadcast_update({"type": "library_update"})
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library sidecar save error: %s", e)
            self.send_error(500)

    def _handle_library_get_note(self, filename):
        """Return the content of a note file."""
        filename = os.path.basename(filename)
        folder, path = self._find_library_file(filename)
        if not os.path.isfile(path):
            self._send_json({"content": "", "app": "", "title": ""})
            return
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n", 2)
            title = ""
            body = content
            if lines and lines[0].startswith("title:"):
                title = lines[0][6:].strip()
                body = "\n".join(lines[1:]).lstrip("\n")
            meta = self._parse_library_filename(filename) or {}
            self._send_json({"content": body, "title": title, "app": meta.get("app", "")})
        except Exception as e:
            log.warning("library note read error: %s", e)
            self.send_error(500)

    def _handle_library_save_note(self):
        """Create or overwrite a note file."""
        try:
            body = self._read_json()
            app = body.get("app", "general") or "general"
            app = re.sub(r'[^a-z0-9]+', '_', app.lower()).strip('_') or "general"
            title = str(body.get("title", "")).strip()
            content = str(body.get("content", ""))
            raw_filename = str(body.get("filename", "")).strip()

            folder = self._notes_folder()
            os.makedirs(folder, exist_ok=True)

            if not raw_filename:
                ts = time.strftime("%Y%m%d_%H%M%S")
                filename = "iris_note_%s_%s.txt" % (app, ts)
            else:
                base = os.path.basename(raw_filename)
                if base.lower().endswith(".txt"):
                    base = base[:-4]
                base = re.sub(r'[^a-zA-Z0-9_\-\. ]+', '_', base).strip('._ ')
                if not base:
                    base = f"note_{int(time.time())}"
                filename = f"{base}.txt"

            path = os.path.join(folder, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write("title:%s\n%s" % (title, content))
            self._broadcast_update({"type": "library_update"})
            self._send_json({"ok": True, "filename": os.path.basename(path)})
        except Exception as e:
            log.warning("library note save error: %s", e)
            self.send_error(500)

    def _handle_library_delete(self, filename):
        """Delete a library item (PNG + sidecar, or note txt)."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        filename = os.path.basename(filename)
        folder, path = self._find_library_file(filename)
        try:
            if not os.path.isfile(path):
                self.send_error(404)
                return
            os.remove(path)
            if filename.lower().endswith(".png"):
                sc = self._sidecar_path(folder, filename)
                if os.path.isfile(sc):
                    os.remove(sc)
            self._broadcast_update({"type": "library_update"})
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library delete error: %s", e)
            self.send_error(500)

    def _handle_library_open_folder(self):
        """Open the screenshots library folder in Explorer, optionally selecting a specific file."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        try:
            fname = None
            if self.command == "POST":
                body = self._read_json()
                fname = body.get("filename") if isinstance(body, dict) else None
            elif "?" in self.path:
                qs = parse_qs(urlparse(self.path).query)
                files = qs.get("file") or qs.get("filename")
                if files:
                    fname = files[0]

            folder = self._screenshots_folder()
            if not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            if fname:
                _, full_path = self._find_library_file(fname)
                if full_path and os.path.isfile(full_path):
                    import subprocess
                    norm_path = os.path.normpath(full_path)
                    subprocess.Popen(["explorer.exe", f"/select,{norm_path}"], shell=False)
                    self._send_json({"ok": True, "path": norm_path})
                    return
            os.startfile(folder)
            self._send_json({"ok": True, "path": folder})
        except Exception as e:
            log.warning("library open folder error: %s", e)
            self.send_error(500, str(e))

    def _handle_library_running_apps(self):
        """Return a list of currently running process names for the note app picker."""
        try:
            from win_platform import get_running_process_names
            names = get_running_process_names(ttl=1.0)
            seen = set()
            apps = []
            for name in names:
                try:
                    key = re.sub(r'\.exe$', '', name, flags=re.IGNORECASE).lower()
                    key = re.sub(r'[^a-z0-9]+', '_', key).strip('_')
                    if key and key not in seen:
                        seen.add(key)
                        apps.append(key)
                except Exception:
                    pass
            apps.sort()
            self._send_json({"apps": apps})
        except Exception as e:
            log.warning("library running apps error: %s", e)
            self._send_json({"apps": []})
