"""Iris — Standalone Notepad Window.

A clean, responsive, dark desktop notes tool adhering to the central Iris visual language.
Features:
- Native Windows 10/11 dark title bar with DWM caption matching (#0B0F12).
- Zero-cost static 9-slice rounded cards (8px radius) and buttons (6px radius).
- Understated dark scrollbar and restrained subtle focus states.
- Grid-based responsive layout with auto-expanding editor area.
- Explicit Save action + background autosave to Iris Library.
- Direct Library action to open the Iris Notes/Screenshot Browser.
- Geometry persistence across sessions.
"""

import ctypes
import logging
import os
import re
import time
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes

from desktop_theme import (
    BG_WINDOW,
    BG_SURFACE_1,
    BG_SURFACE_2,
    BG_CONTROL,
    BG_CONTROL_HOVER,
    BG_CONTROL_ACTIVE,
    BORDER_NORMAL,
    BORDER_SUBTLE,
    BORDER_FOCUS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    ACCENT_BLUE,
    ACCENT_SUCCESS,
    FONT_TITLE,
    FONT_EDITOR,
    FONT_SECONDARY,
    FONT_MUTED,
    PAD_WINDOW,
    apply_dark_title_bar,
    create_iris_button,
    init_desktop_styles,
)
import paths

log = logging.getLogger("iris.quick_note")
user32 = ctypes.windll.user32


class QuickNoteWindow:
    """Iris Notepad desktop tool window."""

    DEFAULT_W = 500
    DEFAULT_H = 400
    MIN_W = 300
    MIN_H = 200

    def __init__(self, root, app=None, app_tag="general"):
        self._root = root
        self.app = app
        self._app_tag = self._clean_app_tag(app_tag)
        self._filename = None
        self._save_timer = None
        self._closed = False

        self._win = tk.Toplevel(root)
        self._win.title(f"Iris Note · {self._app_tag.upper()}")
        self._win.configure(bg=BG_WINDOW)
        self._win.attributes("-topmost", True)
        self._win.minsize(self.MIN_W, self.MIN_H)

        self._position_window()

        # Initialize static 9-slice desktop styles once
        init_desktop_styles(self._win)

        # Enable Windows native dark title bar
        self._win.update_idletasks()
        try:
            hwnd = int(self._win.winfo_id())
            apply_dark_title_bar(hwnd)
        except Exception:
            pass

        self._build_ui()
        self._init_file()

        self._win.bind("<Map>", self._on_map)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._win.bind("<Escape>", lambda e: self._on_close())
        self._win.bind("<Control-s>", lambda e: self._on_explicit_save())

    def _on_map(self, event=None):
        try:
            hwnd = int(self._win.winfo_id())
            apply_dark_title_bar(hwnd)
        except Exception:
            pass

    def _clean_app_tag(self, tag):
        if not tag:
            return "general"
        cleaned = re.sub(r"[^a-z0-9]+", "_", tag.lower()).strip("_")
        return cleaned or "general"

    def _library_folder(self):
        try:
            cfg = getattr(self.app, "cfg", None) if self.app is not None else None
            return paths.get_notes_dir(cfg)
        except Exception:
            return paths.get_notes_dir()

    def _init_file(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._filename = f"iris_note_{self._app_tag}_{ts}.txt"

    def _position_window(self):
        saved = None
        if self.app is not None and getattr(self.app, "cfg", None):
            saved = self.app.cfg.get("notepad_geometry")

        if saved and isinstance(saved, dict):
            w = max(self.MIN_W, int(saved.get("w", self.DEFAULT_W)))
            h = max(self.MIN_H, int(saved.get("h", self.DEFAULT_H)))
            x = int(saved.get("x", 100))
            y = int(saved.get("y", 100))
            self._win.geometry(f"{w}x{h}+{x}+{y}")
            return

        w, h = self.DEFAULT_W, self.DEFAULT_H
        try:
            import vision
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            m = vision.monitor_containing(pt.x, pt.y)
            x = m["x"] + (m["w"] - w) // 2
            y = m["y"] + (m["h"] - h) // 3
            self._win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self._win.geometry(f"{w}x{h}+100+100")

    def _save_geometry(self):
        try:
            w = self._win.winfo_width()
            h = self._win.winfo_height()
            x = self._win.winfo_x()
            y = self._win.winfo_y()
            if w >= self.MIN_W and h >= self.MIN_H:
                if self.app is not None and getattr(self.app, "cfg", None):
                    self.app.cfg["notepad_geometry"] = {"w": w, "h": h, "x": x, "y": y}
                    try:
                        from config import save_config
                        save_config(self.app.cfg)
                    except Exception:
                        pass
        except Exception:
            pass

    def _build_ui(self):
        # Configure root responsive grid
        self._win.columnconfigure(0, weight=1)
        self._win.rowconfigure(0, weight=0)  # Header
        self._win.rowconfigure(1, weight=1)  # Editor (expandable)
        self._win.rowconfigure(2, weight=0)  # Footer

        # Main content frame with standard Iris padding
        main_frame = tk.Frame(self._win, bg=BG_WINDOW, padx=PAD_WINDOW, pady=PAD_WINDOW)
        main_frame.grid(row=0, column=0, rowspan=3, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)  # Header
        main_frame.rowconfigure(1, weight=1)  # Editor
        main_frame.rowconfigure(2, weight=0)  # Footer

        # ── 1. HEADER AREA ─────────────────────────────────────────────
        hdr_frame = tk.Frame(main_frame, bg=BG_WINDOW)
        hdr_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        hdr_frame.columnconfigure(0, weight=1)
        hdr_frame.columnconfigure(1, weight=0)

        # Title Input Box (Static 8px rounded card)
        self._frm_title_box = ttk.Frame(hdr_frame, style="Iris.Card.TFrame")
        self._frm_title_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._ent_title = tk.Entry(
            self._frm_title_box,
            font=FONT_TITLE,
            fg=TEXT_PRIMARY,
            bg=BG_SURFACE_1,
            insertbackground=ACCENT_BLUE,
            bd=0,
            relief="flat",
        )
        self._ent_title.pack(fill="both", expand=True, padx=10, pady=7)
        self._ent_title.insert(0, "")
        self._ent_title.bind("<KeyRelease>", self._schedule_save)
        self._ent_title.bind("<FocusIn>", lambda e: self._frm_title_box.configure(style="Iris.CardFocus.TFrame"))
        self._ent_title.bind("<FocusOut>", lambda e: self._frm_title_box.configure(style="Iris.Card.TFrame"))

        # Save Button (Static 6px rounded button)
        self._btn_save = create_iris_button(
            hdr_frame,
            text="💾  Save",
            command=self._on_explicit_save,
        )
        self._btn_save.grid(row=0, column=1, sticky="e")

        # ── 2. EDITOR AREA ─────────────────────────────────────────────
        # Editor Surface (Static 8px rounded card)
        self._frm_body_box = ttk.Frame(main_frame, style="Iris.Card.TFrame")
        self._frm_body_box.grid(row=1, column=0, sticky="nsew")

        # Understated dark ttk scrollbar
        scrollbar = ttk.Scrollbar(
            self._frm_body_box,
            orient="vertical",
            style="Iris.Vertical.TScrollbar",
        )
        scrollbar.pack(side="right", fill="y", padx=(0, 3), pady=3)

        self._txt_body = tk.Text(
            self._frm_body_box,
            font=FONT_EDITOR,
            fg=TEXT_PRIMARY,
            bg=BG_SURFACE_1,
            insertbackground=ACCENT_BLUE,
            selectbackground="#203E5F",
            selectforeground=TEXT_PRIMARY,
            bd=0,
            relief="flat",
            wrap="word",
            padx=10,
            pady=8,
            undo=True,
            yscrollcommand=scrollbar.set,
            highlightthickness=0,
        )
        self._txt_body.pack(fill="both", expand=True, side="left", padx=(3, 0), pady=3)
        scrollbar.config(command=self._txt_body.yview)

        self._txt_body.bind("<KeyRelease>", self._schedule_save)
        self._txt_body.bind("<FocusIn>", lambda e: self._frm_body_box.configure(style="Iris.CardFocus.TFrame"))
        self._txt_body.bind("<FocusOut>", lambda e: self._frm_body_box.configure(style="Iris.Card.TFrame"))
        self._txt_body.focus_set()

        # ── 3. FOOTER / ACTION AREA ────────────────────────────────────
        ftr_frame = tk.Frame(main_frame, bg=BG_WINDOW)
        ftr_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ftr_frame.columnconfigure(0, weight=1)
        ftr_frame.columnconfigure(1, weight=0)

        # Status indicator
        self._lbl_status = tk.Label(
            ftr_frame,
            text="Ready",
            font=FONT_MUTED,
            fg=TEXT_MUTED,
            bg=BG_WINDOW,
        )
        self._lbl_status.grid(row=0, column=0, sticky="w")

        # Open Note Library button (Static 6px rounded button)
        btn_library = create_iris_button(
            ftr_frame,
            text="📚  Note Library",
            command=self._on_open_library,
            font=FONT_MUTED,
        )
        btn_library.grid(row=0, column=1, sticky="e")

    # ── Actions & File Saving ──────────────────────────────────────

    def _on_open_library(self):
        """Open the existing Iris Note Library in the settings panel."""
        try:
            import panel_window
            panel_window.open_panel(page="library", tab="notes")
        except Exception as ex:
            log.warning("Failed to open library panel: %s", ex)

    def _on_explicit_save(self):
        """Triggered by Save button or Ctrl+S."""
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
            self._save_timer = None
        self._save_to_disk(explicit=True)

    def _schedule_save(self, event=None):
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
        self._save_timer = self._win.after(400, lambda: self._save_to_disk(explicit=False))

    def _save_to_disk(self, explicit=False):
        if self._closed or not self._filename:
            return
        try:
            title = self._ent_title.get().strip()
            content = self._txt_body.get("1.0", "end-1c").strip()

            if not title and not content:
                return

            folder = self._library_folder()
            path = os.path.join(folder, self._filename)

            with open(path, "w", encoding="utf-8") as f:
                f.write(f"title:{title}\n{content}")

            if hasattr(self, "_lbl_status") and self._lbl_status.winfo_exists():
                msg = "✓ Note saved" if explicit else "Saved to Library"
                self._lbl_status.config(text=msg, fg=ACCENT_SUCCESS if explicit else TEXT_SECONDARY)
                self._win.after(
                    2500,
                    lambda: self._lbl_status.config(text="Saved to Library", fg=TEXT_MUTED)
                    if self._lbl_status.winfo_exists()
                    else None,
                )
        except Exception as e:
            log.warning("Quick note save failed: %s", e)

    def _on_close(self):
        if self._closed:
            return
        self._closed = True
        self._save_geometry()
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
            self._save_timer = None
        self._save_to_disk(explicit=False)
        try:
            self._win.destroy()
        except Exception:
            pass


def open_quick_note(root, app=None, app_tag="general"):
    """Open a new standalone Iris Notepad window."""
    return QuickNoteWindow(root, app=app, app_tag=app_tag)
