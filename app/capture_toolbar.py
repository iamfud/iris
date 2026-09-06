"""Iris — Transient Capture & Quick Actions Toolbar.

Provides a fast, minimal, top-centre desktop toolbar exposing direct Iris actions:
- New Screenshot (Fullscreen / Zone capture)
- New Note (Iris Notepad)
- Notes (Note Library)
- Media (Screenshot/Media Browser)
"""

import ctypes
import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes

from desktop_theme import (
    BG_WINDOW,
    BG_SURFACE_1,
    BG_CONTROL,
    BG_CONTROL_HOVER,
    BG_CONTROL_ACTIVE,
    BORDER_NORMAL,
    BORDER_SUBTLE,
    BORDER_FOCUS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    NEON_PRIMARY,
    NEON_SECONDARY,
    ACCENT_DANGER,
    FONT_SECONDARY,
    RADIUS_WINDOW,
    create_iris_button,
    init_desktop_styles,
    get_current_theme_colors,
)
import vision
import mdi_icons
from quick_note import open_quick_note
from widgets import ToolTip
import paths
from win_platform import init_dpi_awareness

log = logging.getLogger("iris.capture_toolbar")
init_dpi_awareness()
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def _set_round_rect(hwnd, w, h, r):
    try:
        hrgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r)
        user32.SetWindowRgn(hwnd, hrgn, True)
    except Exception:
        pass


WS_EX_LAYERED = 0x80000
LWA_ALPHA = 0x2
GWL_EXSTYLE = -20


def _apply_window_style(hwnd, alpha=0.9, corner_pref=3):
    """Apply native DWM dark titlebar, hardware-accelerated rounded corners, and exact 90% alpha transparency."""
    try:
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        root_parent = user32.GetAncestor(hwnd, 2)
        target_hwnds = [h for h in (root_parent, parent, hwnd) if h]
        dwm = ctypes.windll.dwmapi

        for h in target_hwnds:
            # 1. DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dwm.DwmSetWindowAttribute(
                h, 20,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 2. DWMWA_WINDOW_CORNER_PREFERENCE = 33 (3 = DWMWCP_ROUND, 4 = DWMWCP_ROUNDSMALL)
            dwm.DwmSetWindowAttribute(
                h, 33,
                ctypes.byref(ctypes.c_int(corner_pref)),
                ctypes.sizeof(ctypes.c_int),
            )

        # Apply exact layered alpha transparency matching main Tk panel
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(hwnd, 0, int(alpha * 255), LWA_ALPHA)
    except Exception:
        pass


def _copy_to_clipboard(text):
    if not text:
        return
    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        # Configure 64-bit ctypes signatures to prevent access violations on Windows x64
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.OpenClipboard.restype = wintypes.BOOL
        u32.EmptyClipboard.restype = wintypes.BOOL
        u32.SetClipboardData.restype = wintypes.HANDLE
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.CloseClipboard.restype = wintypes.BOOL

        if u32.OpenClipboard(None):
            u32.EmptyClipboard()
            encoded = text.encode("utf-16-le") + b"\x00\x00"
            h_mem = k32.GlobalAlloc(0x0042, len(encoded))  # GMEM_MOVEABLE (0x0002) | GMEM_ZEROINIT (0x0040)
            if h_mem:
                ptr = k32.GlobalLock(h_mem)
                if ptr:
                    ctypes.memmove(ptr, encoded, len(encoded))
                    k32.GlobalUnlock(h_mem)
                    u32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT = 13
            u32.CloseClipboard()
            log.info("[capture_toolbar] OCR text successfully copied to Windows clipboard (%d chars)", len(text))
    except Exception as ex:
        log.warning("[capture_toolbar] clipboard copy failed: %s", ex)


def _get_active_monitor_rect():
    """Get the exact pixel rect of the active monitor (where cursor is)."""
    try:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return vision.monitor_containing(pt.x, pt.y)
    except Exception as ex:
        try:
            return {"x": 0, "y": 0, "w": user32.GetSystemMetrics(0), "h": user32.GetSystemMetrics(1)}
        except Exception:
            return {"x": 0, "y": 0, "w": 2560, "h": 1440}


try:
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
except Exception:
    pass


class CaptureToolbar:
    """Minimal transient top-centre capture & quick action toolbar."""

    RADIUS = 10  # Modest 10px corner radius

    def __init__(self, root, app=None):
        self._root = root
        self.app = app
        self._visible = False
        self._current_app_tag = "desktop"
        self._current_monitor = None
        self._has_spawned_children = False
        self._watcher_active = False

        self._win = tk.Toplevel(root)
        self._win.title("Iris Quick Actions")
        self._win.overrideredirect(True)
        t_colors = get_current_theme_colors()
        self._win.configure(bg=t_colors["theme_bg_hex"])
        self._win.attributes("-topmost", True)

        init_desktop_styles(self._win)

        hwnd = int(self._win.winfo_id())
        _apply_window_style(hwnd, alpha=0.9, corner_pref=3)

        self._build_ui()
        self._win.withdraw()

        self._win.bind("<Escape>", lambda e: self.hide())

    def _build_ui(self):
        # Fetch live theme colors from central theme engine
        t_colors = get_current_theme_colors()
        bg_surface = t_colors["theme_bg_hex"]
        icon_rgb = t_colors["bright_neon_rgb"]

        # Master floating container matching the solid window surface
        self._bar_frame = tk.Frame(self._win, bg=bg_surface)
        self._bar_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # MDI Icon Renderers (Vector Glyphs rendered with the neon-luminance
        # detected colour — highest-luminance of neon vs accent, per
        # get_current_theme_colors' bright_neon_rgb)
        self._icon_shot = mdi_icons.render_tk("crop-free", 18, icon_rgb)
        self._icon_full = mdi_icons.render_tk("camera", 18, icon_rgb)
        self._icon_ocr = mdi_icons.render_tk("text-box-search-outline", 18, icon_rgb)
        self._icon_note = mdi_icons.render_tk("note-edit-outline", 18, icon_rgb)
        self._icon_lib = mdi_icons.render_tk("folder-image", 18, icon_rgb)
        self._icon_eyedrop = mdi_icons.render_tk("eyedropper-variant", 18, icon_rgb)
        self._icon_close = mdi_icons.render_tk("close", 14, icon_rgb)

        def _make_square_btn(parent, icon, command, tip_text):
            """Create an exact 32x32 pixel rounded square icon button."""
            btn = tk.Button(
                parent,
                image=icon,
                command=command,
                bg=t_colors["theme_ctrl_hex"],
                activebackground=t_colors["bright_neon_hex"],
                bd=0,
                relief="flat",
                cursor="hand2",
                highlightthickness=0,
                width=32,
                height=32,
            )
            # Hover color transitions
            ctrl_bg = t_colors["theme_ctrl_hex"]
            hover_bg = "#1B2432"
            btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
            btn.bind("<Leave>", lambda e: btn.config(bg=ctrl_bg))
            ToolTip(btn, tip_text)
            return btn

        # 1. Fullscreen Screenshot Square Button (32x32)
        self._btn_full = _make_square_btn(self._bar_frame, self._icon_full, self._on_fullscreen, "Screenshot")
        self._btn_full.pack(side="left", padx=(6, 2), pady=5)

        # 2. Snipping Tool Square Button (32x32) — rectangular zone capture
        self._btn_shot = _make_square_btn(self._bar_frame, self._icon_shot, self._on_screenshot, "Snipping Tool")
        self._btn_shot.pack(side="left", padx=2, pady=5)

        # 3. OCR Text Square Button (32x32)
        self._btn_ocr = _make_square_btn(self._bar_frame, self._icon_ocr, self._on_ocr, "OCR Text")
        self._btn_ocr.pack(side="left", padx=2, pady=5)

        # 4. New Note Square Button (32x32)
        self._btn_note = _make_square_btn(self._bar_frame, self._icon_note, self._on_note, "Quick Note")
        self._btn_note.pack(side="left", padx=2, pady=5)

        # 5. Library Square Button (32x32)
        self._btn_lib = _make_square_btn(self._bar_frame, self._icon_lib, self._on_library, "Library")
        self._btn_lib.pack(side="left", padx=2, pady=5)

        # 6. Color Picker (Eyedropper) Square Button (32x32)
        self._btn_eyedrop = _make_square_btn(self._bar_frame, self._icon_eyedrop, self._on_color_picker, "Color Picker")
        self._btn_eyedrop.pack(side="left", padx=2, pady=5)

        # 6. Dynamic Color Hex Box Container (Appears on first pick / click)
        self._color_box_frame = tk.Frame(self._bar_frame, bg=bg_surface)
        self._color_swatch = tk.Label(self._color_box_frame, text="  ", bg=bg_surface, width=2, bd=0)
        self._color_entry = tk.Entry(
            self._color_box_frame,
            width=8,
            font=("Segoe UI", 9, "bold"),
            bg="#131A24",
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            bd=0,
            highlightthickness=1,
            highlightcolor=t_colors["neon_hex"],
            highlightbackground="#1C2532",
            justify="center",
        )
        self._color_entry_visible = False

        # Subtle vertical separator
        sep = tk.Frame(self._bar_frame, width=1, bg="#161E28", height=20)
        sep.pack(side="left", fill="y", pady=7, padx=(4, 4))

        # 7. Modern Dismiss Button (32x32) - Always at the very end
        self._btn_close = tk.Button(
            self._bar_frame,
            image=self._icon_close if self._icon_close else None,
            text="" if self._icon_close else "✕",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_MUTED,
            bg=bg_surface,
            activebackground=ACCENT_DANGER,
            activeforeground="#FFFFFF",
            bd=0,
            relief="flat",
            cursor="hand2",
            highlightthickness=0,
            width=32,
            height=32,
            command=self.hide,
        )
        self._btn_close.pack(side="left", padx=(2, 6), pady=5)
        self._btn_close.bind("<Enter>", lambda e: self._btn_close.config(bg=ACCENT_DANGER))
        self._btn_close.bind("<Leave>", lambda e: self._btn_close.config(bg=bg_surface))
        ToolTip(self._btn_close, "Close Toolbar")

    def _resolve_foreground_app(self):
        """Identify the foreground application before toolbar steals focus."""
        try:
            from main_window import _get_foreground_app_name
            hwnd = user32.GetForegroundWindow()
            name = _get_foreground_app_name(hwnd)
            return name or "desktop"
        except Exception:
            return "desktop"

    def show(self, slot=None):
        """Display the toolbar at the exact top-centre of the active monitor (4px from top)."""
        self._current_app_tag = self._resolve_foreground_app()
        m = _get_active_monitor_rect()
        self._current_monitor = m

        self._win.deiconify()
        self._win.update_idletasks()

        # Measure content width dynamically
        req_w = self._bar_frame.winfo_reqwidth()
        req_h = self._bar_frame.winfo_reqheight()
        w = max(180, req_w + 2)
        h = max(38, req_h + 2)

        # Compute exact horizontal center and 4px from top
        center_x = int(m["x"] + (m["w"] - w) // 2)
        target_y = int(m["y"] + 4)

        self._win.geometry(f"{w}x{h}+{center_x}+{target_y}")
        self._win.lift()
        self._win.attributes("-topmost", True)
        self._visible = True
        self._win.update_idletasks()

        hwnd = int(self._win.winfo_id())
        root_hwnd = user32.GetAncestor(hwnd, 2) or user32.GetParent(hwnd) or hwnd

        user32.SetWindowPos(root_hwnd, wintypes.HWND(-1), center_x, target_y, w, h, 0x0040)
        _apply_window_style(hwnd, alpha=0.9, corner_pref=3)

        self._win.focus_force()

    def toggle(self, slot=None):
        """Toggle toolbar visibility (dismisses if already open)."""
        if self._visible:
            self.hide()
        else:
            self.show(slot)

    def hide(self):
        """Dismiss the toolbar."""
        self._visible = False
        self._has_spawned_children = False
        self._watcher_active = False
        try:
            self._win.withdraw()
        except Exception:
            pass

    def _start_child_watcher(self):
        """Start polling to dismiss toolbar when all child windows are closed."""
        if self._watcher_active:
            return
        self._watcher_active = True
        self._win.after(800, self._poll_child_windows)

    def _poll_child_windows(self):
        if not self._visible or not self._has_spawned_children:
            self._watcher_active = False
            return

        try:
            import notepad_window
            notepad_alive = notepad_window.is_notepad_open()
        except Exception:
            notepad_alive = False

        try:
            import panel_window
            panel_alive = panel_window.is_panel_open()
        except Exception:
            panel_alive = False

        try:
            import viewer_window
            viewer_alive = viewer_window.is_viewer_open()
        except Exception:
            viewer_alive = False

        if not notepad_alive and not panel_alive and not viewer_alive:
            # All child windows (including library, notepad, and screenshot editor) dismissed -> dismiss toolbar
            self.hide()
            return

        self._win.after(600, self._poll_child_windows)

    def _library_folder(self):
        try:
            cfg = getattr(self.app, "cfg", None) if self.app is not None else None
            return paths.get_screenshots_dir(cfg)
        except Exception:
            return paths.get_screenshots_dir()

    def _save_screenshot_and_ocr(self, img, app_tag):
        """Persist screenshot to disk and trigger background OCR + sidecar generation."""
        shot_data = None
        try:
            folder = self._library_folder()
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            fname = f"iris_{app_tag}_{ts_str}.png"
            path = os.path.join(folder, fname)
            img.save(path, format="PNG")
            log.info("Screenshot saved: %s", path)

            try:
                import io, base64
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=65, optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                shot_data = {
                    "img": b64,
                    "fmt": "jpeg",
                    "w": img.width,
                    "h": img.height,
                    "ts": time.time(),
                }
                if self.app is not None:
                    self.app.screenshot_seq = getattr(self.app, "screenshot_seq", 0) + 1
                    shot_data["seq"] = self.app.screenshot_seq
                    self.app.screenshot_last = shot_data
            except Exception:
                pass

            try:
                import ws_bridge
                ws_bridge.broadcast({"type": "library_update"})
                if shot_data:
                    ws_bridge.broadcast({"type": "screenshot_ready", **shot_data})
            except Exception:
                pass

            def _ocr_worker():
                try:
                    ocr_res = vision.ocr_extract(img)
                    sc_path = os.path.splitext(path)[0] + ".json"
                    sidecar = {
                        "title": "",
                        "app": app_tag,
                        "detected_text": ocr_res.get("text", "") if isinstance(ocr_res, dict) else "",
                        "words": ocr_res.get("words", []) if isinstance(ocr_res, dict) else [],
                        "annotations": [],
                    }
                    with open(sc_path, "w", encoding="utf-8") as f:
                        json.dump(sidecar, f, ensure_ascii=False)
                    log.info("Sidecar JSON generated for: %s", fname)
                    try:
                        import ws_bridge
                        ws_bridge.broadcast({"type": "library_update"})
                    except Exception:
                        pass
                except Exception as ex:
                    log.warning("OCR sidecar generation failed: %s", ex)

            threading.Thread(target=_ocr_worker, daemon=True, name="iris-ocr-sidecar").start()
            return fname

        except Exception as ex:
            log.warning("Screenshot save failed: %s", ex)
            return None

    def _clear_screenshot_last(self):
        """Clear the last screenshot so a polling phone never sees a stale capture
        (phone/PC clock skew would otherwise make a previous screenshot look 'newer')."""
        if self.app is not None and getattr(self.app, "screenshot_last", None) is not None:
            self.app.screenshot_last = None

    def capture_fullscreen_direct(self, app_tag=None, notify=True):
        """Silently capture active game/monitor, save PNG + OCR, with zero focus stealing and no game minimization."""
        tag = app_tag or self._resolve_foreground_app() or "game"
        self._clear_screenshot_last()

        def _capture():
            try:
                img, monitor = vision.capture_active_monitor()
                if img:
                    fname = self._save_screenshot_and_ocr(img, tag)
                    log.info("[capture_toolbar] Direct fullscreen capture completed: %s", fname)
                    if fname:
                        try:
                            import viewer_window
                            viewer_window.open_viewer(fname)
                        except Exception as ex:
                            log.warning("Failed to open screenshot annotation editor: %s", ex)
                    if notify:
                        try:
                            import winsound
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                        except Exception:
                            pass
            except Exception as ex:
                log.warning("[capture_toolbar] Direct fullscreen capture failed: %s", ex)

        threading.Thread(target=_capture, daemon=True, name="iris-direct-fullscreen-capture").start()

    def _on_fullscreen(self):
        """Silent fullscreen capture of the active monitor. Shared pipeline (save + OCR +
        app.screenshot_last + library_update) so the result appears on phone and desktop."""
        app_tag = self._current_app_tag or "desktop"
        self.capture_fullscreen_direct(app_tag=app_tag, notify=True)

    def _on_screenshot(self):
        """Invoke rectangular zone selector, hide toolbar, capture, then reopen toolbar with annotation editor."""
        self.hide()
        self._clear_screenshot_last()
        app_tag = self._current_app_tag or "desktop"

        def _capture():
            try:
                rect = vision.select_region(self._root, timeout=90)
                fname = None
                if rect:
                    x, y, w, h = rect
                    img = vision.capture((x, y, x + w, y + h))
                    fname = self._save_screenshot_and_ocr(img, app_tag)
                    if fname:
                        try:
                            import viewer_window
                            viewer_window.open_viewer(fname)
                        except Exception as ex:
                            log.warning("Failed to open screenshot annotation editor: %s", ex)

                # Reopen toolbar after capture or cancel
                self._root.after(100, lambda: self._reopen_after_screenshot(bool(rect)))
            except Exception as ex:
                log.warning("Capture failed: %s", ex)
                self._root.after(100, self.show)

        self._root.after(150, lambda: threading.Thread(target=_capture, daemon=True, name="iris-capture").start())

    def _reopen_after_screenshot(self, success):
        self.show()
        if success:
            self._has_spawned_children = True
            self._start_child_watcher()

    def _on_ocr(self):
        """Crosshair region capture -> Native OCR extraction -> Clipboard copy & Notepad population (unsaved)."""
        self.hide()
        app_tag = self._current_app_tag or "desktop"

        def _capture():
            try:
                rect = vision.select_region(self._root, timeout=90)
                if rect:
                    x, y, w, h = rect
                    img = vision.capture((x, y, x + w, y + h))
                    if img:
                        ocr_res = vision.ocr_extract(img)
                        extracted_text = (ocr_res.get("text", "") if isinstance(ocr_res, dict) else "").strip()
                        if extracted_text:
                            _copy_to_clipboard(extracted_text)

                        app_clean = app_tag.replace("_", " ").title() if app_tag else "Screen"
                        ts_str = time.strftime("%H:%M")
                        note_title = f"OCR · {app_clean} ({ts_str})"

                        def _open_note():
                            try:
                                import notepad_window
                                notepad_window.open_notepad(
                                    app_tag=app_tag,
                                    filename=None,
                                    initial_title=note_title,
                                    initial_body=extracted_text,
                                )
                                self._has_spawned_children = True
                                self._start_child_watcher()
                            except Exception as ex:
                                log.warning("Failed to open notepad with OCR: %s", ex)

                        self._root.after(50, _open_note)

                # Reopen toolbar after capture or cancel
                self._root.after(100, lambda: self._reopen_after_screenshot(bool(rect)))
            except Exception as ex:
                log.warning("OCR Capture failed: %s", ex)
                self._root.after(100, self.show)

        self._root.after(150, lambda: threading.Thread(target=_capture, daemon=True, name="iris-ocr-capture").start())

    def _on_note(self):
        """Open the dedicated HTML Notepad window (toolbar persists)."""
        app_tag = self._current_app_tag or "general"
        try:
            import notepad_window
            notepad_window.open_notepad(app_tag=app_tag)
            self._has_spawned_children = True
            self._start_child_watcher()
        except Exception as ex:
            log.warning("Failed to open notepad window: %s", ex)

    def _on_library(self):
        """Open Iris Library in Settings webview (toolbar persists)."""
        try:
            import panel_window
            panel_window.open_panel(page="library", tab="notes")
            try:
                import ws_bridge
                ws_bridge.broadcast({"type": "library_update"})
            except Exception:
                pass
            self._has_spawned_children = True
            self._start_child_watcher()
        except Exception as ex:
            log.warning("Failed to open library: %s", ex)

    def _on_color_picker(self):
        """Eyedropper tool: toolbar stays visible while user clicks any pixel on the desktop."""
        # Reveal color text box on first click if not already packed
        self._ensure_color_box_visible()

        def _pick():
            try:
                # Capture single pixel from virtual screen
                pt = self._pick_pixel_point()
                if pt:
                    x, y = pt
                    img = vision.capture((x, y, x + 1, y + 1))
                    if img:
                        r, g, b = img.getpixel((0, 0))[:3]
                        hex_code = f"#{r:02X}{g:02X}{b:02X}"
                        _copy_to_clipboard(hex_code)
                        self._root.after(0, lambda: self._set_color_result(hex_code, r, g, b))
            except Exception as ex:
                log.warning("Color pick error: %s", ex)

        threading.Thread(target=_pick, daemon=True, name="iris-color-picker").start()

    def _ensure_color_box_visible(self):
        """Pack the color hex text box before the separator and close button."""
        if not self._color_entry_visible:
            self._color_entry_visible = True
            self._color_swatch.pack(side="left", padx=(2, 3), pady=6)
            self._color_entry.pack(side="left", padx=(0, 4), pady=6)
            self._color_box_frame.pack(side="left", before=self._btn_close, padx=(2, 2))
            self._color_entry.delete(0, "end")
            self._color_entry.insert(0, "#HEX")
            ToolTip(self._color_entry, "Click to copy hex color")
            self._color_entry.bind("<Button-1>", lambda e: _copy_to_clipboard(self._color_entry.get()))
            # Recalculate toolbar geometry smoothly
            self._win.update_idletasks()
            req_w = self._bar_frame.winfo_reqwidth()
            req_h = self._bar_frame.winfo_reqheight()
            w = max(240, req_w + 4)
            h = max(38, req_h + 2)
            m = self._current_monitor or _get_active_monitor_rect()
            center_x = int(m["x"] + (m["w"] - w) // 2)
            target_y = int(m["y"] + 15)
            self._win.geometry(f"{w}x{h}+{center_x}+{target_y}")
            hwnd = int(self._win.winfo_id())
            root_hwnd = user32.GetAncestor(hwnd, 2) or user32.GetParent(hwnd) or hwnd
            user32.SetWindowPos(root_hwnd, wintypes.HWND(-1), center_x, target_y, w, h, 0x0040)
            _apply_window_style(hwnd, alpha=0.9, corner_pref=3)

    def _set_color_result(self, hex_code, r, g, b):
        """Update the inline hex box and swatch with the picked color."""
        self._ensure_color_box_visible()
        self._color_entry.delete(0, "end")
        self._color_entry.insert(0, hex_code)
        self._color_swatch.config(bg=hex_code)

    def _pick_pixel_point(self):
        """Open a transparent crosshair overlay allowing the user to click any pixel on screen."""
        done = threading.Event()
        holder = {}

        def _open():
            try:
                vx, vy, vw, vh = vision.virtual_screen_bounds()
                overlay = tk.Toplevel(self._root)
                overlay.overrideredirect(True)
                overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
                overlay.attributes("-alpha", 0.01)  # Almost invisible click catcher
                overlay.attributes("-topmost", True)
                overlay.config(cursor="crosshair")

                def _on_click(e):
                    holder["point"] = (e.x_root, e.y_root)
                    try:
                        overlay.destroy()
                    except Exception:
                        pass
                    done.set()

                def _on_esc(e):
                    try:
                        overlay.destroy()
                    except Exception:
                        pass
                    done.set()

                overlay.bind("<Button-1>", _on_click)
                overlay.bind("<Escape>", _on_esc)
                overlay.focus_force()
            except Exception as ex:
                log.warning("Failed to open pixel picker overlay: %s", ex)
                done.set()

        self._root.after(0, _open)
        done.wait(60)
        return holder.get("point")
