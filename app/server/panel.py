"""Panel and UI interaction API handler mixin for Iris server."""

import collections
import logging
import os
import sys
import threading

log = logging.getLogger("iris.server.panel")

_APP_ICON_CACHE = collections.OrderedDict()
_APP_ICON_LOCK = threading.Lock()


def _get_root_dir():
    try:
        import ws_bridge
        return getattr(ws_bridge, "_ROOT_DIR", None) or (
            sys._MEIPASS if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    except Exception:
        return (
            sys._MEIPASS if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )


def _get_html_dir():
    try:
        import ws_bridge
        return getattr(ws_bridge, "_HTML_DIR", None) or os.path.join(_get_root_dir(), "HTML")
    except Exception:
        return os.path.join(_get_root_dir(), "HTML")


class PanelHandlerMixin:
    """Provides panel, icon, MDI, and slot route handlers to RequestHandler."""

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

    def _handle_save_panel(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        try:
            from panel_actions import apply_panel_save
            from config import save_config
            apply_panel_save(app.cfg, body)
            save_config(app.cfg)
            mw = getattr(app, "_main_win", None)
            if mw is not None and hasattr(mw, "rebuild_panel"):
                try:
                    app._root.after(0, mw.rebuild_panel)
                except Exception:
                    pass
            import ws_bridge
            clients_count = len(getattr(ws_bridge, "CLIENTS", {}))
            log.info("[panel_save] broadcasting config to %d WS client(s)", clients_count)
            from server.auth import annotate_action_slots
            ws_bridge.broadcast({
                "type": "config",
                "config": {
                    "panel_board": annotate_action_slots(app.cfg.get("panel_board", [])),
                    "panel_utility": annotate_action_slots(app.cfg.get("panel_utility", [])),
                    "panel_core": annotate_action_slots(app.cfg.get("panel_core", [])),
                    "panel_sliders": app.cfg.get("panel_sliders", []),
                    "panel_layout": app.cfg.get("panel_layout", []),
                    "panel_gauges": app.cfg.get("panel_gauges", {}),
                    "panel_profiles": annotate_action_slots(app.cfg.get("panel_profiles", [])),
                    "media_player_path": app.cfg.get("media_player_path", ""),
                    "default_profile_name": app.cfg.get("default_profile_name", ""),
                }
            })
            try:
                import plugin_manager
                plugin_manager.sync_plugin_themes()
            except Exception:
                pass
            if app.cfg.get("theme"):
                ws_bridge.broadcast({"type": "theme", "theme": app.cfg["theme"]})
            from panel_actions import panel_payload
            self._send_json({"ok": True, **panel_payload(app.cfg)})
        except Exception as e:
            log.warning("[http] save panel failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_icon(self):
        """Extract + serve the app icon for a shortcut path (PNG, cached)."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            import shutil
            qs = parse_qs(urlparse(self.path).query)
            raw_p = (qs.get("path") or [""])[0]
            if not raw_p:
                self.send_error(404)
                return
            p = unquote(raw_p).strip().strip('"\'')
            is_url = p.startswith(("http://", "https://")) or (("." in p) and ("/" in p or "\\" not in p) and not os.path.isabs(p) and not p.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".vbs", ".ps1")))
            if not is_url:
                p = os.path.expandvars(os.path.expanduser(p))
                if not os.path.isfile(p):
                    which_p = shutil.which(p)
                    if which_p and os.path.isfile(which_p):
                        p = which_p
                    else:
                        base_dir = _get_root_dir()
                        cand = os.path.join(base_dir, p)
                        if os.path.isfile(cand):
                            p = cand
                        else:
                            cand_media = os.path.join(base_dir, "media", p)
                            if os.path.isfile(cand_media):
                                p = cand_media
                if not os.path.isfile(p):
                    self.send_error(404)
                    return
            norm = p.lower() if is_url else os.path.normcase(os.path.abspath(p))
            with _APP_ICON_LOCK:
                cached = _APP_ICON_CACHE.get(norm)
                if cached is not None:
                    _APP_ICON_CACHE.move_to_end(norm)

            if cached is None:
                with _APP_ICON_LOCK:
                    # Double-check after lock
                    cached = _APP_ICON_CACHE.get(norm)
                    if cached is not None:
                        _APP_ICON_CACHE.move_to_end(norm)
                    else:
                        from win_platform import _extract_via_ps, detect_icon_color
                        img = _extract_via_ps(p, size=256)
                        if img is None:
                            self.send_error(404)
                            return
                        color = detect_icon_color(img)
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        blob = buf.getvalue()
                        if len(_APP_ICON_CACHE) >= 200:
                            _APP_ICON_CACHE.popitem(last=False)
                        _APP_ICON_CACHE[norm] = (blob, color)
                        cached = (blob, color)

            blob, color = cached
            etag = f'"{abs(hash(norm + str(len(blob))))}"'
            inm = self.headers.get("If-None-Match", "").strip()
            if inm and inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("ETag", etag)
            if color:
                self.send_header("X-Detected-Color", color)
                self.send_header("Access-Control-Expose-Headers", "X-Detected-Color")
            self.end_headers()
            self.wfile.write(blob)
        except Exception as e:
            log.warning("[http] app icon extraction failed: %s", e)
            self.send_error(500)

    def _handle_panel_icon_meta(self):
        """Return detected icon color metadata for an executable or image path."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            import shutil
            qs = parse_qs(urlparse(self.path).query)
            raw_p = (qs.get("path") or [""])[0]
            if not raw_p:
                self._send_json({"ok": False, "error": "missing path"})
                return
            p = unquote(raw_p).strip().strip('"\'')
            is_url = p.startswith(("http://", "https://")) or (("." in p) and ("/" in p or "\\" not in p) and not os.path.isabs(p) and not p.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".vbs", ".ps1")))
            if not is_url:
                p = os.path.expandvars(os.path.expanduser(p))
                if not os.path.isfile(p):
                    which_p = shutil.which(p)
                    if which_p and os.path.isfile(which_p):
                        p = which_p
                    else:
                        base_dir = _get_root_dir()
                        cand = os.path.join(base_dir, p)
                        if os.path.isfile(cand):
                            p = cand
                        else:
                            cand_media = os.path.join(base_dir, "media", p)
                            if os.path.isfile(cand_media):
                                p = cand_media
                if not os.path.isfile(p):
                    self._send_json({"ok": False, "error": "file not found"})
                    return
            norm = p.lower() if is_url else os.path.normcase(os.path.abspath(p))
            with _APP_ICON_LOCK:
                cached = _APP_ICON_CACHE.get(norm)
                if cached is not None:
                    _APP_ICON_CACHE.move_to_end(norm)
            if cached is not None:
                _, color = cached
            else:
                with _APP_ICON_LOCK:
                    cached = _APP_ICON_CACHE.get(norm)
                    if cached is not None:
                        _APP_ICON_CACHE.move_to_end(norm)
                        _, color = cached
                    else:
                        from win_platform import _extract_via_ps, detect_icon_color
                        img = _extract_via_ps(p, size=256)
                        if img is None:
                            self._send_json({"ok": False, "error": "extraction failed"})
                            return
                        color = detect_icon_color(img)
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        blob = buf.getvalue()
                        if len(_APP_ICON_CACHE) >= 200:
                            _APP_ICON_CACHE.popitem(last=False)
                        _APP_ICON_CACHE[norm] = (blob, color)
            self._send_json({"ok": True, "path": p, "color": color})
        except Exception as e:
            log.warning("[http] icon meta extraction failed: %s", e)
            self._send_json({"ok": False, "error": str(e)})

    def _serve_mdi_font(self):
        """Serve the MDI webfont so the web panel renders the same icons as Tk."""
        try:
            import mdi_icons
            path = str(mdi_icons.FONT_PATH)
        except Exception:
            path = ""
        html_dir = _get_html_dir()
        if not path or not os.path.isfile(path):
            path = os.path.join(html_dir, "mdi-webfont.ttf")
        if not os.path.isfile(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mdi-webfont.ttf")
        try:
            import embedded_assets
        except Exception:
            embedded_assets = None
        if not os.path.isfile(path) and embedded_assets and embedded_assets.has_asset("mdi-webfont.ttf"):
            res = embedded_assets.get_asset_bytes("mdi-webfont.ttf", prefer_gzip=False)
            if res:
                data = res[0]
                self.send_response(200)
                self.send_header("Content-Type", "font/ttf")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(data)
                return

        if not os.path.isfile(path):
            self.send_error(404)
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "font/ttf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _handle_mdi_search(self):
        """Return search matches across all 7,440+ icons: ?q=xbox&cat=gamer&limit=120"""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0]
        cat = (qs.get("cat") or [""])[0]
        limit = int((qs.get("limit") or [120])[0])
        try:
            import mdi_icons
            results = mdi_icons.search_icons(query=q, category=cat, limit=limit)
            self._send_json({"ok": True, "icons": results})
        except Exception as ex:
            self._send_json({"ok": False, "icons": [], "error": str(ex)})

    def _handle_mdi_codepoints(self):
        """Return {"name": "<char>"} for ?names=a,b,c (missing -> null)."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        names = qs.get("names", [""])
        if not names:
            self._send_json({})
            return
        import mdi_icons
        result = {}
        for chunk in names:
            for n in chunk.split(","):
                n = n.strip()
                if n:
                    result[n] = mdi_icons.get_char(n)
        self._send_json(result)

    def _handle_panel_open_library(self):
        """Open the Iris settings app directly on the Library > Notes tab (same as toolbar Library button)."""
        try:
            import panel_window
            panel_window.open_panel(page="library", tab="notes")
            self._send_json({"ok": True})
        except Exception as ex:
            log.warning("[http] open library failed: %s", ex)
            self.send_error(500, str(ex))

    def _handle_panel_action(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        from server.auth import resolve_action_slot, resolve_mobile_action
        cfg = app.cfg if app is not None else {}
        is_remote = not self._is_loopback_peer()
        slot = (resolve_mobile_action(body.get("action_id"), cfg)
                if is_remote else resolve_action_slot(body.get("action_id"), cfg))
        if slot is None:
            log.warning("[http] rejected unauthorized action execution from peer: %s", self.client_address[0])
            self.send_error(403, "Action not authorized")
            return
        try:
            from panel_runtime import execute_slot
            self._send_json(execute_slot(slot))
        except Exception as e:
            log.warning("[http] panel action failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_brightness(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        try:
            value = int(body.get("brightness"))
        except (TypeError, ValueError):
            self.send_error(400, "brightness must be an integer")
            return
        try:
            app._set_brightness(max(0, min(4, value)))
            self._send_json({"ok": True, "brightness": app.cfg.get("brightness")})
        except Exception as e:
            log.warning("[http] set brightness failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_core(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        tile = body.get("tile")
        if tile == "display":
            cur = bool(app.cfg.get("pc_stats_manual", False))
            try:
                app._toggle_pc_stats(not cur)
            except Exception as e:
                log.warning("[http] pc stats toggle failed: %s", e)
            self._send_json({"ok": True, "state": not cur})
        elif tile == "overlay":
            cur = bool(getattr(app, "_overlay", None))
            try:
                app._root.after(0, lambda: app._toggle_overlay(not cur))
            except Exception as e:
                log.warning("[http] overlay toggle failed: %s", e)
            self._send_json({"ok": True, "state": not cur})
        elif tile in ("mic", "mic_mute"):
            try:
                from win_platform import toggle_mic_mute
                st = toggle_mic_mute()
            except Exception as e:
                log.warning("[http] mic toggle failed: %s", e)
                st = None
            self._send_json({"ok": st is not None, "state": st})
        elif tile in ("lighting_sync", "lighting"):
            try:
                st = app._toggle_lighting_sync()
            except Exception as e:
                log.warning("[http] lighting sync toggle failed: %s", e)
                st = False
            self._send_json({"ok": True, "state": st})
        elif tile == "settings":
            try:
                if hasattr(app, "_open_settings"):
                    app._open_settings()
                else:
                    import panel_window
                    panel_window.open_panel()
            except Exception as e:
                log.warning("[http] settings open failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "toolbar":
            try:
                if hasattr(app, "_toggle_capture_toolbar"):
                    app._root.after(0, app._toggle_capture_toolbar)
            except Exception as e:
                log.warning("[http] toolbar toggle failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "colour_picker":
            try:
                mw = app._ensure_main_win() if hasattr(app, "_ensure_main_win") else getattr(app, "_main_win", None)
                if mw:
                    app._root.after(0, mw.start_colour_picker)
            except Exception as e:
                log.warning("[http] colour picker failed: %s", e)
            self._send_json({"ok": True})
        elif tile in ("screenshot", "screenshot_full"):
            try:
                mw = app._ensure_main_win() if hasattr(app, "_ensure_main_win") else getattr(app, "_main_win", None)
                if mw:
                    app._root.after(0, lambda: mw.start_screenshot({}, mode="fullscreen"))
            except Exception as e:
                log.warning("[http] screenshot failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "screenshot_zone":
            try:
                mw = app._ensure_main_win() if hasattr(app, "_ensure_main_win") else getattr(app, "_main_win", None)
                if mw:
                    app._root.after(0, lambda: mw.start_screenshot({}, mode="zone"))
            except Exception as e:
                log.warning("[http] screenshot zone failed: %s", e)
            self._send_json({"ok": True})
        elif tile in ("note", "note_native", "note_webview"):
            try:
                mw = app._ensure_main_win() if hasattr(app, "_ensure_main_win") else getattr(app, "_main_win", None)
                if mw:
                    app._root.after(0, lambda: mw.start_quick_note(toggle=True))
            except Exception as e:
                log.warning("[http] quick note failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "borderless_toggle":
            try:
                from win_platform import toggle_borderless_window
                st = toggle_borderless_window()
                self._send_json({"ok": True, "borderless": st})
            except Exception as e:
                log.warning("[http] borderless toggle failed: %s", e)
                self._send_json({"ok": False, "error": str(e)})
        elif tile == "stopwatch":
            try:
                if hasattr(app, "_toggle_stopwatch"):
                    app._root.after(0, app._toggle_stopwatch)
            except Exception as e:
                log.warning("[http] stopwatch toggle failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "countdown":
            try:
                if hasattr(app, "_toggle_countdown"):
                    app._root.after(0, app._toggle_countdown)
            except Exception as e:
                log.warning("[http] countdown toggle failed: %s", e)
            self._send_json({"ok": True})
        else:
            self._send_json({"ok": False})

    def _handle_panel_export_buttons(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return

        from panel_actions import sanitize_slot, sanitize_profiles, sanitize_board, ensure_panel_defaults
        from config import save_config

        profile_id = str(body.get("profile_id") or "__default__").strip()
        plugin_name = str(body.get("plugin") or "").strip()
        buttons = body.get("buttons") or []
        replace_all = bool(body.get("replace_all", False))
        slot_idx = body.get("slot_idx")

        slots = []
        for b in buttons:
            bid = b.get("id") or b.get("button_id")
            if not bid:
                continue
            ent_id = b.get("entity") or (f"{plugin_name}.{bid}" if plugin_name else bid)
            slot = {
                "type": "TOGGLE",
                "entity": ent_id,
                "name": b.get("name") or bid.replace("_", " ").title(),
                "plugin": plugin_name or b.get("plugin", ""),
                "button_id": bid,
                "widget_type": b.get("widget_type", "status_toggle"),
                "icon": b.get("icon") or "toggle-switch",
                "icon_off": b.get("icon_off") or "",
                "state_key": b.get("state_key") or bid,
                "labels": b.get("labels") or {},
                "colors": b.get("colors") or {},
                "hotkey": b.get("hotkey") or b.get("default_hotkey") or "",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "description": b.get("description") or "",
            }
            s = sanitize_slot(slot)
            if s:
                slots.append(s)

        cfg = app.cfg
        ensure_panel_defaults(cfg)

        # Prevent plugin presets from overwriting the user's default main board
        if not profile_id or profile_id == "__default__":
            profile_id = "__new__"

        profiles = cfg.get("panel_profiles") or []
        if profile_id == "__new__":
            base_id = f"prof_{plugin_name}" if plugin_name else "prof_custom"
            existing_ids = {p.get("id") for p in profiles if isinstance(p, dict)}
            new_id = base_id
            counter = 1
            while new_id in existing_ids:
                counter += 1
                new_id = f"{base_id}_{counter}"
            profile_id = new_id

            prof = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
            if not prof:
                prof_name = body.get("profile_name") or plugin_name.replace("_", " ").title()
                prof_exe = body.get("profile_exe") or ""
                prof = {
                    "id": profile_id,
                    "name": prof_name,
                    "exe": prof_exe,
                    "enabled": True,
                    "board": []
                }
                profiles.append(prof)
            target_name = prof.get("name") or profile_id

            if replace_all:
                prof["board"] = slots
            else:
                board = list(prof.get("board") or [])
                if slot_idx is not None and int(slot_idx) >= 0:
                    while len(board) <= int(slot_idx):
                        board.append({"type": "EMPTY", "name": "", "icon": "border-none-variant", "color": ""})
                    if slots:
                        board[int(slot_idx)] = slots[0]
                else:
                    placed = False
                    for i in range(len(board)):
                        if board[i].get("type") == "EMPTY" and slots:
                            board[i] = slots[0]
                            placed = True
                            break
                    if not placed and slots:
                        board.append(slots[0])
                prof["board"] = sanitize_board(board)

            cfg["panel_profiles"] = sanitize_profiles(profiles)

        save_config(cfg)
        from panel_actions import _RESOLVE_CACHE
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None

        self._send_json({"ok": True, "target_profile": target_name, "profile_id": profile_id, "count": len(slots)})

    def _handle_panel_entities(self):
        try:
            from panel_entities import get_entity_registry, get_live_entity_states
            entities = get_entity_registry()
            live = {}
            try:
                live_raw = get_live_entity_states()
                for k, v in live_raw.items():
                    if isinstance(v, dict) and "value" in v:
                        live[k] = v.get("value")
                    else:
                        live[k] = v
            except Exception:
                pass
            self._send_json({"ok": True, "entities": entities, "live_states": live})
        except Exception as e:
            log.warning("[http] panel entities failed: %s", e)
            self._send_json({"ok": False, "entities": [], "live_states": {}})
