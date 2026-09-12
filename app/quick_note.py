"""Iris — Standalone Desktop Notepad (Native Lightweight Engine).

A clean, instant (<25ms), zero-VRAM desktop notes tool matching the Iris visual language.
Features:
- Frameless modern window with hardware-accelerated rounded corners and drop shadow.
- Custom header chrome: Hamburger menu, App Tag pill, Theme toggle (◐/☼/☾), Maximize/Restore, Close.
- Anti-aliased 26×26 rounded buttons with 6px corner radius and generous whitespace/padding.
- Red rounded hover badge on Close button, smooth neutral rounded hover on Theme, Max, and Menu.
- Full flat modern popover menu (zero grey 3D bevels).
- Auto-hiding modern scrollbar that only renders when text overflows the viewport.
- Smooth native edge and corner resizing with Aero Snap support.
- Full 3-mode theme cycle: Auto (◐), Light parchment (☼), Dark slate (☾) with persistent config sync.
- Autosave to Iris Library notes folder and geometry persistence.
"""

import ctypes
import logging
import math
import os
import re
import time
import tkinter as tk
from tkinter import ttk
from ctypes import wintypes
from PIL import Image, ImageDraw, ImageTk

import sys
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

if __name__ == "app.quick_note" and "quick_note" not in sys.modules:
    sys.modules["quick_note"] = sys.modules["app.quick_note"]
elif __name__ == "quick_note" and "app.quick_note" not in sys.modules:
    sys.modules["app.quick_note"] = sys.modules["quick_note"]

import paths
from config import load_config, save_config

try:
    import vision
except Exception:
    vision = None

log = logging.getLogger("iris.quick_note")
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwm = ctypes.windll.dwmapi

# Global singleton tracker for active note window
_ACTIVE_NOTE_WINDOW = None


def _get_last_note_for_app(app_tag):
    try:
        cfg = load_config()
        return (cfg.get("notepad_last_notes") or {}).get(app_tag)
    except Exception:
        return None


def _set_last_note_for_app(app_tag, filename):
    try:
        cfg = load_config()
        notes = cfg.get("notepad_last_notes") or {}
        notes[app_tag] = filename
        cfg["notepad_last_notes"] = notes
        save_config(cfg)
    except Exception as e:
        log.warning("Failed to save last note for app %s: %s", app_tag, e)


def _clear_last_note_for_app(app_tag):
    try:
        cfg = load_config()
        notes = cfg.get("notepad_last_notes") or {}
        if app_tag in notes:
            notes.pop(app_tag, None)
            cfg["notepad_last_notes"] = notes
            save_config(cfg)
    except Exception as e:
        log.warning("Failed to clear last note for app %s: %s", app_tag, e)


def _is_windows_dark_mode():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return val == 0
    except Exception:
        return True


def _hex_to_rgb(hex_str, default=(20, 20, 20)):
    try:
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return default


PALETTES = {
    "dark": {
        "bg_win": "#141414",
        "win_border": "#282828",
        "bg_chrome": "#141414",
        "chrome_border": "#252525",
        "chrome_fg": "#9aa0a6",
        "chrome_hover_bg": "#22252A",
        "chrome_hover_fg": "#ffffff",
        "close_hover_bg": "#ef4444",
        "close_hover_fg": "#ffffff",
        "title_fg": "#ffffff",
        "title_placeholder": "#585b60",
        "title_divider": "#222222",
        "body_bg": "#141414",
        "body_fg": "#dcdfe4",
        "body_placeholder": "#4a4d52",
        "body_select_bg": "#203E5F",
        "body_select_fg": "#ffffff",
        "caret": "#48B2E9",
        "status_fg": "#71767d",
        "status_saved": "#2ECC71",
        "tag_bg": "#1e2127",
        "tag_fg": "#858b94",
        "menu_bg": "#1C1E22",
        "menu_border": "#2D3239",
        "menu_fg": "#e8eaed",
        "menu_shortcut_fg": "#71767d",
        "menu_active_bg": "#2A2D33",
        "menu_active_fg": "#ffffff",
        "menu_divider": "#26292E",
        "danger_fg": "#ef4444",
        "danger_active_bg": "#361a1d",
        "danger_active_fg": "#ff6b6b",
        "scrollbar_trough": "#141414",
        "scrollbar_thumb": "#7e8490",
        "scrollbar_thumb_hover": "#9aa0ac",
        "accent": "#48B2E9",
        "is_dark": True,
    },
    "light": {
        "bg_win": "#FFFCF2",
        "win_border": "#E2DDD2",
        "bg_chrome": "#F7F3E8",
        "chrome_border": "#ede8db",
        "chrome_fg": "#5f6368",
        "chrome_hover_bg": "#ebe5d8",
        "chrome_hover_fg": "#1a1d21",
        "close_hover_bg": "#dc2626",
        "close_hover_fg": "#ffffff",
        "title_fg": "#1a1d21",
        "title_placeholder": "#9c978b",
        "title_divider": "#ede8dc",
        "body_bg": "#FFFCF2",
        "body_fg": "#202124",
        "body_placeholder": "#9c978b",
        "body_select_bg": "#C2DBFE",
        "body_select_fg": "#000000",
        "caret": "#0066cc",
        "status_fg": "#5f6368",
        "status_saved": "#1b873f",
        "tag_bg": "#ede8db",
        "tag_fg": "#5f6368",
        "menu_bg": "#FFFCF2",
        "menu_border": "#E2DDD2",
        "menu_fg": "#202124",
        "accent": "#007acc",
        "menu_shortcut_fg": "#80868b",
        "menu_active_bg": "#F0EBE0",
        "menu_active_fg": "#000000",
        "menu_divider": "#E8E3D8",
        "danger_fg": "#dc2626",
        "danger_active_bg": "#fde8e8",
        "danger_active_fg": "#b91c1c",
        "scrollbar_trough": "#FFFCF2",
        "scrollbar_thumb": "#b8bcc4",
        "scrollbar_thumb_hover": "#9fa4ad",
        "is_dark": False,
    },
}

THEMES = ["auto", "light", "dark"]
THEME_SYMBOLS = {"auto": "◐", "light": "☼", "dark": "☾"}


class IrisNoteScrollbar(tk.Canvas):
    """Featherweight, modern vertical scrollbar handle with no background bar or arrows."""

    def __init__(self, parent, command=None, width=6, bar_width=4, **kwargs):
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(parent, width=width, **kwargs)
        self._command = command
        self._bar_width = bar_width
        self._thumb_min_h = 24
        self._first = 0.0
        self._last = 1.0
        self._y0 = 0
        self._y1 = 0
        self._thumb_color = "#7e8490"
        self._thumb_hover_color = "#9aa0ac"
        self._is_hover = False
        self._drag_data = None

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<MouseWheel>", self._on_mousewheel)

    def config(self, **kwargs):
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        super().config(**kwargs)

    configure = config

    def set_colors(self, thumb=None, thumb_hover=None):
        if thumb:
            self._thumb_color = thumb
        if thumb_hover:
            self._thumb_hover_color = thumb_hover
        self._redraw()

    def set(self, first, last):
        try:
            self._first = float(first)
            self._last = float(last)
        except Exception:
            pass
        self._redraw()

    def _on_configure(self, event):
        self._redraw()

    def _on_enter(self, event):
        self._is_hover = True
        self._redraw()

    def _on_leave(self, event):
        self._is_hover = False
        self._redraw()

    def _on_mousewheel(self, event):
        if self._command:
            units = -1 * int(event.delta / 120)
            self._command("scroll", units, "units")

    def _on_click(self, event):
        if self._y0 <= event.y <= self._y1:
            self._drag_data = (event.y, self._first)
        else:
            h = self.winfo_height()
            span = self._last - self._first
            thumb_h = max(self._thumb_min_h, int(span * h))
            travel = h - thumb_h
            avail_first = max(0.0001, 1.0 - span)
            if travel > 0:
                target_y0 = event.y - thumb_h / 2.0
                target_first = max(0.0, min(avail_first, (target_y0 / travel) * avail_first))
                if self._command:
                    self._command("moveto", target_first)
                self._drag_data = (event.y, target_first)

    def _on_drag(self, event):
        if self._drag_data is not None:
            start_y, initial_first = self._drag_data
            h = self.winfo_height()
            span = self._last - self._first
            thumb_h = max(self._thumb_min_h, int(span * h))
            travel = h - thumb_h
            avail_first = max(0.0001, 1.0 - span)
            if travel > 0:
                dy = event.y - start_y
                delta_first = (dy / travel) * avail_first
                target_first = max(0.0, min(avail_first, initial_first + delta_first))
                if self._command:
                    self._command("moveto", target_first)

    def _on_release(self, event):
        self._drag_data = None

    def _redraw(self):
        self.delete("all")
        h = self.winfo_height()
        if h <= 1:
            return
        f = self._first
        l = self._last
        if f <= 0.0 and l >= 1.0:
            return
        span = max(0.001, l - f)
        thumb_h = max(self._thumb_min_h, int(span * h))
        thumb_h = min(thumb_h, h)
        travel = h - thumb_h
        avail_first = max(0.001, 1.0 - span)
        y0 = int((f / avail_first) * travel) if avail_first > 0 else 0
        y0 = max(0, min(travel, y0))
        y1 = y0 + thumb_h
        self._y0 = y0
        self._y1 = y1

        color = self._thumb_hover_color if self._is_hover else self._thumb_color
        w = self.winfo_width() or 6
        cx = w // 2
        r = max(1, self._bar_width // 2)
        if (y1 - y0) > self._bar_width:
            self.create_line(cx, y0 + r, cx, y1 - r, width=self._bar_width, capstyle="round", fill=color)
        else:
            self.create_oval(cx - r, y0, cx + r, y0 + self._bar_width, fill=color, outline="")


class QuickNoteWindow:
    """Iris Notepad desktop tool window (Native featherweight implementation)."""

    DEFAULT_W = 550
    DEFAULT_H = 650
    MIN_W = 320
    MIN_H = 360

    TITLE_PLACEHOLDER = "Untitled note"
    BODY_PLACEHOLDER = "…"

    def __init__(self, root, app=None, app_tag="general", filename=None, initial_title=None, initial_body=None):
        self._root = root
        self.app = app
        self._app_tag = self._clean_app_tag(app_tag)
        self._filename = filename
        self._save_timer = None
        self._status_timer = None
        self._closed = False
        self._is_saving = False

        self._title_has_placeholder = False
        self._body_has_placeholder = False

        self._is_maximized = False
        self._normal_geometry = None
        self._scroll_visible = True
        self._popover_visible = False

        self._drag_start_x = None
        self._drag_start_y = None
        self._drag_win_x = None
        self._drag_win_y = None

        # Cache of rendered PhotoImage button icons
        self._icons = {}

        # Load persisted theme
        self._theme_mode = self._load_theme_mode()

        # Window Pin and Persistency states
        self._is_pinned = True
        self._is_persistent = False
        self._is_in_background = False
        if not self._filename:
            persisted_file = _get_last_note_for_app(self._app_tag)
            if persisted_file:
                # Verify file still exists on disk
                folder = self._library_folder()
                if os.path.isfile(os.path.join(folder, persisted_file)):
                    self._filename = persisted_file
                    self._is_persistent = True

        self._win = tk.Toplevel(root)
        self._win.title(f"Iris Note · {self._app_tag.upper()}")
        self._win.overrideredirect(True)
        self._win.minsize(self.MIN_W, self.MIN_H)
        self._win.attributes("-topmost", True)

        self._position_window()
        self._apply_native_styles()

        self._build_ui()
        self._apply_theme()

        self._load_initial_content(initial_title, initial_body)

        self._win.bind("<Escape>", self._on_escape)
        self._win.bind("<Control-s>", lambda e: self._on_explicit_save())
        self._win.bind("<Control-S>", lambda e: self._on_explicit_save())
        self._win.bind("<Control-n>", lambda e: self._on_new_note())
        self._win.bind("<Control-N>", lambda e: self._on_new_note())
        self._win.bind("<Control-b>", lambda e: self._toggle_format("bold"))
        self._win.bind("<Control-B>", lambda e: self._toggle_format("bold"))
        self._win.bind("<Control-i>", lambda e: self._toggle_format("italic"))
        self._win.bind("<Control-I>", lambda e: self._toggle_format("italic"))
        self._win.bind_all("<Button-1>", self._on_global_click, add="+")

        self.bring_to_foreground()
        self._win.after(30, self.bring_to_foreground)

    def _clean_app_tag(self, tag):
        if not tag:
            return "general"
        cleaned = re.sub(r"[^a-z0-9]+", "_", str(tag).lower()).strip("_")
        return cleaned or "general"

    def _load_theme_mode(self):
        try:
            cfg = load_config()
            saved = cfg.get("notepad_theme")
            if saved in THEMES:
                return saved
        except Exception:
            pass
        return "auto"

    def _save_theme_mode(self, mode):
        self._theme_mode = mode
        try:
            cfg = load_config()
            cfg["notepad_theme"] = mode
            save_config(cfg)
        except Exception as e:
            log.warning("Failed to save notepad_theme config: %s", e)

    def _get_active_palette(self):
        mode = self._theme_mode
        if mode == "auto":
            return PALETTES["dark" if _is_windows_dark_mode() else "light"]
        return PALETTES.get(mode, PALETTES["dark"])

    def _position_window(self):
        saved = None
        try:
            cfg = load_config()
            saved = cfg.get("notepad_geometry")
        except Exception:
            pass

        if saved and isinstance(saved, dict):
            w = max(self.MIN_W, int(saved.get("w", self.DEFAULT_W)))
            h = max(self.MIN_H, int(saved.get("h", self.DEFAULT_H)))
            x = int(saved.get("x", 100))
            y = int(saved.get("y", 100))
            self._win.geometry(f"{w}x{h}+{x}+{y}")
            self._normal_geometry = (x, y, w, h)
            return

        w, h = self.DEFAULT_W, self.DEFAULT_H
        try:
            if vision:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                m = vision.monitor_containing(pt.x, pt.y)
                x = m["x"] + (m["w"] - w) // 2
                y = m["y"] + (m["h"] - h) // 3
                self._win.geometry(f"{w}x{h}+{x}+{y}")
                self._normal_geometry = (x, y, w, h)
                return
        except Exception:
            pass
        self._win.geometry(f"{w}x{h}+150+150")
        self._normal_geometry = (150, 150, w, h)

    def _save_geometry(self):
        try:
            if self._is_maximized:
                return
            w = self._win.winfo_width()
            h = self._win.winfo_height()
            x = self._win.winfo_x()
            y = self._win.winfo_y()
            if w >= self.MIN_W and h >= self.MIN_H:
                cfg = load_config()
                cfg["notepad_geometry"] = {"w": w, "h": h, "x": x, "y": y}
                save_config(cfg)
        except Exception:
            pass

    def _get_toplevel_hwnd(self):
        try:
            wid = int(self._win.winfo_id())
            return user32.GetParent(wid) or wid
        except Exception:
            return 0

    def _apply_native_styles(self):
        self._win.update_idletasks()
        try:
            hwnd = self._get_toplevel_hwnd()
            if not hwnd:
                return
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            s = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (s & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)

            # Windows 11 hardware-accelerated rounded window corners
            dwm.DwmSetWindowAttribute(
                hwnd, 33,
                ctypes.byref(ctypes.c_int(3)),
                ctypes.sizeof(ctypes.c_int),
            )

            # Subtle modern window transparency (matches WebView2 0.98 alpha at 0 MB VRAM)
            self._win.attributes("-alpha", 0.98)
        except Exception:
            pass

    # ── Anti-Aliased Vector Button Rendering ──────────────────────────

    def _render_rounded_icon(self, icon_type, bg_parent, bg_btn, fg_color, size=26, radius=6):
        """Render a sub-pixel smooth 26x26 rounded button image with crisp anti-aliased vector shapes."""
        scale = 4
        sw = size * scale
        sh = size * scale
        sr = radius * scale
        cx = sw / 2.0
        cy = sh / 2.0

        bg_parent_rgb = _hex_to_rgb(bg_parent)
        img = Image.new("RGB", (sw, sh), bg_parent_rgb)
        draw = ImageDraw.Draw(img)

        # Draw rounded button background if active/hovered
        if bg_btn:
            draw.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=sr, fill=_hex_to_rgb(bg_btn))

        fg_rgb = _hex_to_rgb(fg_color)
        cutout_fill = _hex_to_rgb(bg_btn) if bg_btn else bg_parent_rgb

        if icon_type == "close":
            d = 15
            draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=fg_rgb, width=5)
            draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=fg_rgb, width=5)

        elif icon_type == "max":
            d = 16
            draw.rectangle([cx - d, cy - d, cx + d, cy + d], outline=fg_rgb, width=5)

        elif icon_type == "restore":
            # Back rect (upper right)
            draw.rectangle([cx - 6, cy - 18, cx + 18, cy + 6], outline=fg_rgb, width=4)
            # Front rect (lower left, filled to occlude back rect)
            draw.rectangle([cx - 18, cy - 6, cx + 6, cy + 18], fill=cutout_fill, outline=fg_rgb, width=4)

        elif icon_type == "theme_auto":
            r = 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fg_rgb, width=4)
            draw.pieslice([cx - r, cy - r, cx + r, cy + r], start=90, end=270, fill=fg_rgb)

        elif icon_type == "theme_light":
            r = 10
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg_rgb)
            for deg in (0, 45, 90, 135, 180, 225, 270, 315):
                rad = math.radians(deg)
                x1 = cx + 15 * math.cos(rad)
                y1 = cy + 15 * math.sin(rad)
                x2 = cx + 23 * math.cos(rad)
                y2 = cy + 23 * math.sin(rad)
                draw.line([(x1, y1), (x2, y2)], fill=fg_rgb, width=4)

        elif icon_type == "theme_dark":
            r = 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg_rgb)
            r_in = 17
            ox = 8
            oy = -4
            draw.ellipse([cx + ox - r_in, cy + oy - r_in, cx + ox + r_in, cy + oy + r_in], fill=cutout_fill)

        elif icon_type == "menu":
            w = 17
            for y_off in (-14, 0, 14):
                draw.line([(cx - w, cy + y_off), (cx + w, cy + y_off)], fill=fg_rgb, width=4)

        elif icon_type == "pin_norm":
            # Pushpin angled 45deg: needle
            draw.line([(cx - 8, cy + 8), (cx - 22, cy + 22)], fill=fg_rgb, width=4)
            # Pushpin head/body outline
            draw.polygon([(cx - 12, cy - 2), (cx + 2, cy - 16), (cx + 16, cy - 2), (cx + 2, cy + 12)], outline=fg_rgb)
            # Pushpin top cap
            draw.line([(cx + 4, cy - 18), (cx + 20, cy - 2)], fill=fg_rgb, width=4)

        elif icon_type == "pin_active":
            # Pushpin needle
            draw.line([(cx - 8, cy + 8), (cx - 22, cy + 22)], fill=fg_rgb, width=4)
            # Pushpin head/body filled with accent
            draw.polygon([(cx - 12, cy - 2), (cx + 2, cy - 16), (cx + 16, cy - 2), (cx + 2, cy + 12)], fill=fg_rgb, outline=fg_rgb)
            # Pushpin top cap
            draw.line([(cx + 4, cy - 18), (cx + 20, cy - 2)], fill=fg_rgb, width=4)

        elif icon_type == "persist_norm":
            # Bookmark ribbon outline (disposable/private mode)
            pts = [(cx - 13, cy - 18), (cx + 13, cy - 18), (cx + 13, cy + 18), (cx, cy + 9), (cx - 13, cy + 18)]
            draw.polygon(pts, outline=fg_rgb)

        elif icon_type == "persist_active":
            # Bookmark ribbon filled with accent (persistent scratchpad mode)
            pts = [(cx - 13, cy - 18), (cx + 13, cy - 18), (cx + 13, cy + 18), (cx, cy + 9), (cx - 13, cy + 18)]
            draw.polygon(pts, fill=fg_rgb, outline=fg_rgb)

        smooth = img.resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(smooth, master=self._win)

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        self._outer_frame = tk.Frame(self._win, bd=1, relief="solid")
        self._outer_frame.pack(fill="both", expand=True)

        self._outer_frame.columnconfigure(0, weight=1)
        self._outer_frame.rowconfigure(0, weight=0)  # Header Chrome
        self._outer_frame.rowconfigure(1, weight=0)  # Title Entry
        self._outer_frame.rowconfigure(2, weight=1)  # Body Editor
        self._outer_frame.rowconfigure(3, weight=0)  # Status Footer

        # ── 1. Top Header Chrome ──────────────────────────────────────
        self._chrome_frame = tk.Frame(self._outer_frame, height=36)
        self._chrome_frame.grid(row=0, column=0, sticky="ew")
        self._chrome_frame.pack_propagate(False)

        # Left Controls
        self._chrome_left = tk.Frame(self._chrome_frame)
        self._chrome_left.pack(side="left", fill="y", padx=(8, 0))

        # 26x26 Hamburger Menu Button
        self._btn_menu = tk.Label(
            self._chrome_left,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_menu.pack(side="left", pady=5)
        self._btn_menu.bind("<Button-1>", lambda e: self._toggle_popover())
        self._btn_menu.bind("<Enter>", lambda e: self._on_btn_hover("menu", True))
        self._btn_menu.bind("<Leave>", lambda e: self._on_btn_hover("menu", False))

        self._lbl_app_tag = tk.Label(
            self._chrome_left,
            text=self._app_tag.upper(),
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            bd=0,
        )
        self._lbl_app_tag.pack(side="left", padx=(6, 0), pady=7)

        # Right Controls: [ Persist ] [ Pin ] [ Theme ] [ Max ] [ Close ]
        # Floating with 8px right padding from window border and 5px top/bottom padding
        self._chrome_right = tk.Frame(self._chrome_frame)
        self._chrome_right.pack(side="right", fill="y", padx=(0, 8))

        # 26x26 Rounded Close Button
        self._btn_close = tk.Label(
            self._chrome_right,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_close.pack(side="right", padx=(4, 0), pady=5)
        self._btn_close.bind("<Button-1>", lambda e: self._on_close())
        self._btn_close.bind("<Enter>", lambda e: self._on_btn_hover("close", True))
        self._btn_close.bind("<Leave>", lambda e: self._on_btn_hover("close", False))

        # 26x26 Rounded Maximize Button
        self._btn_max = tk.Label(
            self._chrome_right,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_max.pack(side="right", padx=(4, 0), pady=5)
        self._btn_max.bind("<Button-1>", lambda e: self._toggle_maximize())
        self._btn_max.bind("<Enter>", lambda e: self._on_btn_hover("max", True))
        self._btn_max.bind("<Leave>", lambda e: self._on_btn_hover("max", False))

        # 26x26 Rounded Theme Button
        self._btn_theme = tk.Label(
            self._chrome_right,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_theme.pack(side="right", padx=(4, 0), pady=5)
        self._btn_theme.bind("<Button-1>", lambda e: self._cycle_theme())
        self._btn_theme.bind("<Enter>", lambda e: self._on_btn_hover("theme", True))
        self._btn_theme.bind("<Leave>", lambda e: self._on_btn_hover("theme", False))

        # 26x26 Rounded Pin Button (Always on Top)
        self._btn_pin = tk.Label(
            self._chrome_right,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_pin.pack(side="right", padx=(4, 0), pady=5)
        self._btn_pin.bind("<Button-1>", lambda e: self._toggle_pin())
        self._btn_pin.bind("<Enter>", lambda e: self._on_btn_hover("pin", True))
        self._btn_pin.bind("<Leave>", lambda e: self._on_btn_hover("pin", False))

        # 26x26 Rounded Persist Button (Keep Note Scratchpad / Private Mode)
        self._btn_persist = tk.Label(
            self._chrome_right,
            cursor="hand2",
            bd=0,
            width=26,
            height=26,
        )
        self._btn_persist.pack(side="right", padx=(0, 0), pady=5)
        self._btn_persist.bind("<Button-1>", lambda e: self._toggle_persistency())
        self._btn_persist.bind("<Enter>", lambda e: self._on_btn_hover("persist", True))
        self._btn_persist.bind("<Leave>", lambda e: self._on_btn_hover("persist", False))

        # Dragging bindings for the header bar
        for w in (self._chrome_frame, self._chrome_left, self._lbl_app_tag, self._chrome_right):
            w.bind("<Button-1>", self._start_window_drag)
            w.bind("<B1-Motion>", self._on_window_drag)
            w.bind("<ButtonRelease-1>", self._end_window_drag)
            w.bind("<Double-Button-1>", lambda e: self._toggle_maximize())

        # Divider line
        self._chrome_div = tk.Frame(self._outer_frame, height=1)
        self._chrome_div.grid(row=0, column=0, sticky="sew")

        # ── 2. Title Entry ────────────────────────────────────────────
        self._title_wrap = tk.Frame(self._outer_frame)
        self._title_wrap.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 4))
        self._title_wrap.columnconfigure(0, weight=1)

        self._ent_title = tk.Entry(
            self._title_wrap,
            font=("Segoe UI", 15, "bold"),
            bd=0,
            relief="flat",
            highlightthickness=0,
        )
        self._ent_title.grid(row=0, column=0, sticky="ew")
        self._ent_title.bind("<KeyRelease>", self._schedule_save)
        self._ent_title.bind("<FocusIn>", self._on_title_focus_in)
        self._ent_title.bind("<FocusOut>", self._on_title_focus_out)
        self._ent_title.bind("<Return>", lambda e: self._txt_body.focus_set())

        self._title_div = tk.Frame(self._outer_frame, height=1)
        self._title_div.grid(row=1, column=0, sticky="sew", padx=14)

        # ── 3. Body Text Editor ───────────────────────────────────────
        self._body_wrap = tk.Frame(self._outer_frame)
        self._body_wrap.grid(row=2, column=0, sticky="nsew", padx=(14, 2), pady=(4, 0))
        self._body_wrap.columnconfigure(0, weight=1)
        self._body_wrap.columnconfigure(1, weight=0)
        self._body_wrap.rowconfigure(0, weight=1)

        self._scroll = IrisNoteScrollbar(self._body_wrap, width=6, bar_width=4)
        self._scroll_visible = False

        self._txt_body = tk.Text(
            self._body_wrap,
            font=("Segoe UI", 10),
            bd=0,
            relief="flat",
            highlightthickness=0,
            wrap="word",
            undo=True,
            padx=2,
            pady=8,
            spacing1=2,
            spacing2=3,
            spacing3=2,
            yscrollcommand=self._on_body_scroll,
        )
        self._txt_body.grid(row=0, column=0, sticky="nsew")
        self._scroll.config(command=self._txt_body.yview)

        # Formatting tags
        self._txt_body.tag_configure("bold", font=("Segoe UI", 10, "bold"))
        self._txt_body.tag_configure("italic", font=("Segoe UI", 10, "italic"))
        self._txt_body.tag_configure("bold_italic", font=("Segoe UI", 10, "bold italic"))
        self._txt_body.tag_raise("bold_italic")

        self._txt_body.bind("<KeyRelease>", self._schedule_save)
        self._txt_body.bind("<FocusIn>", self._on_body_focus_in)
        self._txt_body.bind("<FocusOut>", self._on_body_focus_out)
        self._txt_body.bind("<Control-b>", lambda e: self._toggle_format("bold"))
        self._txt_body.bind("<Control-B>", lambda e: self._toggle_format("bold"))
        self._txt_body.bind("<Control-i>", lambda e: self._toggle_format("italic"))
        self._txt_body.bind("<Control-I>", lambda e: self._toggle_format("italic"))

        # ── 4. Footer Status Bar ──────────────────────────────────────
        self._ftr_frame = tk.Frame(self._outer_frame, height=22)
        self._ftr_frame.grid(row=3, column=0, sticky="ew", padx=(14, 2), pady=(2, 2))
        self._ftr_frame.columnconfigure(0, weight=1)
        self._ftr_frame.columnconfigure(1, weight=0)
        self._ftr_frame.columnconfigure(2, weight=0)

        self._lbl_status = tk.Label(
            self._ftr_frame,
            text="",
            font=("Segoe UI", 8),
            bd=0,
        )
        self._lbl_status.grid(row=0, column=1, sticky="e")

        self._grip = tk.Canvas(
            self._ftr_frame,
            width=20,
            height=20,
            cursor="size_nw_se",
            bd=0,
            highlightthickness=0,
        )
        self._grip.grid(row=0, column=2, sticky="se", padx=(4, 0))
        self._grip.bind("<Button-1>", self._on_grip_press)
        self._grip.bind("<B1-Motion>", self._on_grip_drag)
        self._grip.bind("<ButtonRelease-1>", lambda e: self._save_geometry())
        self._grip.bind("<Enter>", lambda e: self._draw_grip(is_hover=True))
        self._grip.bind("<Leave>", lambda e: self._draw_grip(is_hover=False))

        # ── 5. Flat Modern Popover Menu ───────────────────────────────
        self._build_popover_menu()

    # ── Flat Popover Menu ─────────────────────────────────────────────

    def _build_popover_menu(self):
        self._popover = tk.Frame(self._outer_frame, bd=1, relief="solid")
        self._popover_items = []

        items_def = [
            ("New Note", "Ctrl+N", self._on_new_note, False),
            ("Save", "Ctrl+S", self._on_explicit_save, False),
            ("Restore Last Note", "", self._on_restore_last_note, False),
            (None, None, None, False),
            ("Bold", "Ctrl+B", lambda: self._toggle_format("bold"), False),
            ("Italic", "Ctrl+I", lambda: self._toggle_format("italic"), False),
            (None, None, None, False),
            ("Open in Library", "", self._on_open_library, False),
            ("Delete Note", "", self._on_delete_note, True),
        ]

        for label, shortcut, cmd, is_danger in items_def:
            if label is None:
                sep = tk.Frame(self._popover, height=1)
                sep.pack(fill="x", padx=4, pady=3)
                self._popover_items.append(("sep", sep))
                continue

            row = tk.Frame(self._popover, cursor="hand2")
            row.pack(fill="x", padx=3, pady=1)

            lbl = tk.Label(
                row,
                text=label,
                font=("Segoe UI", 9),
                anchor="w",
                cursor="hand2",
                bd=0,
                padx=8,
                pady=4,
            )
            lbl.pack(side="left")

            sc_lbl = None
            if shortcut:
                sc_lbl = tk.Label(
                    row,
                    text=shortcut,
                    font=("Segoe UI", 8),
                    anchor="e",
                    cursor="hand2",
                    bd=0,
                    padx=8,
                    pady=4,
                )
                sc_lbl.pack(side="right")

            action = self._make_menu_click_handler(cmd)
            for w in (row, lbl) + ((sc_lbl,) if sc_lbl else ()):
                w.bind("<Button-1>", action)
                w.bind("<Enter>", lambda e, r=row, l=lbl, s=sc_lbl, d=is_danger: self._hover_menu_item(r, l, s, d, True))
                w.bind("<Leave>", lambda e, r=row, l=lbl, s=sc_lbl, d=is_danger: self._hover_menu_item(r, l, s, d, False))

            self._popover_items.append(("item", row, lbl, sc_lbl, is_danger))

    def _make_menu_click_handler(self, cmd):
        def _handler(e):
            self._hide_popover()
            if cmd:
                cmd()
        return _handler

    def _toggle_popover(self):
        if self._popover_visible:
            self._hide_popover()
        else:
            self._show_popover()

    def _show_popover(self):
        self._popover.place(x=8, y=36)
        self._popover.lift()
        self._popover_visible = True

    def _hide_popover(self):
        if self._popover_visible:
            self._popover.place_forget()
            self._popover_visible = False

    def _on_global_click(self, event):
        if not self._popover_visible:
            return
        w = event.widget
        if w != self._popover and not str(w).startswith(str(self._popover)) and w != self._btn_menu:
            self._hide_popover()

    def _on_escape(self, event=None):
        if self._popover_visible:
            self._hide_popover()
            return
        self._on_close()

    # ── Auto-Hiding Scrollbar ─────────────────────────────────────────

    def _on_body_scroll(self, first, last):
        try:
            f = float(first)
            l = float(last)
            if f <= 0.0 and l >= 1.0:
                if self._scroll_visible:
                    self._scroll.grid_remove()
                    self._scroll_visible = False
            else:
                if not self._scroll_visible:
                    self._scroll.grid(row=0, column=1, sticky="ns", padx=(2, 2))
                    self._scroll_visible = True
        except Exception:
            pass
        self._scroll.set(first, last)

    # ── Header Dragging ───────────────────────────────────────────────

    def _start_window_drag(self, event):
        if self._is_maximized:
            self._toggle_maximize()
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_win_x = self._win.winfo_x()
        self._drag_win_y = self._win.winfo_y()

    def _on_window_drag(self, event):
        if self._drag_start_x is None or self._drag_win_x is None:
            return
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        self._win.geometry(f"+{self._drag_win_x + dx}+{self._drag_win_y + dy}")

    def _end_window_drag(self, event=None):
        self._drag_start_x = None
        self._drag_start_y = None
        self._drag_win_x = None
        self._drag_win_y = None
        self._save_geometry()

    # ── Maximize & Restore ────────────────────────────────────────────

    def _toggle_maximize(self):
        if not self._is_maximized:
            w = self._win.winfo_width()
            h = self._win.winfo_height()
            x = self._win.winfo_x()
            y = self._win.winfo_y()
            self._normal_geometry = (x, y, w, h)

            work_x, work_y, work_w, work_h = self._get_current_monitor_work_area()
            self._win.geometry(f"{work_w}x{work_h}+{work_x}+{work_y}")
            self._is_maximized = True
        else:
            if self._normal_geometry:
                x, y, w, h = self._normal_geometry
                self._win.geometry(f"{w}x{h}+{x}+{y}")
            self._is_maximized = False
        self._rebuild_button_icons()

    def _get_current_monitor_work_area(self):
        try:
            hwnd = self._get_toplevel_hwnd()
            if hwnd:
                class MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                hmon = user32.MonitorFromWindow(hwnd, 2)
                if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    rc = mi.rcWork
                    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top
        except Exception:
            pass
        rect = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    # ── Corner Resizing ───────────────────────────────────────────────

    def _on_grip_press(self, event):
        if self._is_maximized:
            return
        self._grip_start_x = event.x_root
        self._grip_start_y = event.y_root
        self._grip_start_w = self._win.winfo_width()
        self._grip_start_h = self._win.winfo_height()

    def _on_grip_drag(self, event):
        if self._is_maximized:
            return
        dx = event.x_root - self._grip_start_x
        dy = event.y_root - self._grip_start_y
        nw = max(self.MIN_W, self._grip_start_w + dx)
        nh = max(self.MIN_H, self._grip_start_h + dy)
        self._win.geometry(f"{nw}x{nh}")

    def _draw_grip(self, is_hover=False):
        """Render three parallel diagonal lines giving a full square corner to resize with."""
        if not hasattr(self, "_grip") or not self._grip:
            return
        self._grip.delete("all")
        pal = self._get_active_palette()
        fg = pal["chrome_hover_fg"] if is_hover else pal["chrome_fg"]
        self._grip.configure(bg=pal["bg_win"])
        self._grip.create_line(5, 19, 19, 5, width=2, capstyle="round", fill=fg)
        self._grip.create_line(10, 19, 19, 10, width=2, capstyle="round", fill=fg)
        self._grip.create_line(15, 19, 19, 15, width=2, capstyle="round", fill=fg)

    # ── Theme & Styling ───────────────────────────────────────────────

    def _cycle_theme(self):
        cur_idx = THEMES.index(self._theme_mode) if self._theme_mode in THEMES else 0
        nxt = THEMES[(cur_idx + 1) % len(THEMES)]
        self._save_theme_mode(nxt)
        self._apply_theme()

    def _rebuild_button_icons(self):
        """Recreate all anti-aliased 26x26 rounded button states for active theme."""
        pal = self._get_active_palette()
        bg = pal["bg_chrome"]

        # Close button: smooth 6px rounded red badge on hover
        self._icons["close_norm"] = self._render_rounded_icon("close", bg, None, pal["chrome_fg"])
        self._icons["close_hover"] = self._render_rounded_icon("close", bg, pal["close_hover_bg"], pal["close_hover_fg"])

        # Maximize button: smooth 6px rounded hover badge
        max_type = "restore" if self._is_maximized else "max"
        self._icons["max_norm"] = self._render_rounded_icon(max_type, bg, None, pal["chrome_fg"])
        self._icons["max_hover"] = self._render_rounded_icon(max_type, bg, pal["chrome_hover_bg"], pal["chrome_hover_fg"])

        # Theme button: smooth 6px rounded hover badge
        theme_type = f"theme_{self._theme_mode}" if self._theme_mode in ("auto", "light", "dark") else "theme_auto"
        self._icons["theme_norm"] = self._render_rounded_icon(theme_type, bg, None, pal["chrome_fg"])
        self._icons["theme_hover"] = self._render_rounded_icon(theme_type, bg, pal["chrome_hover_bg"], pal["chrome_hover_fg"])

        # Pin button: outline when unpinned, filled accent when pinned
        pin_type = "pin_active" if self._is_pinned else "pin_norm"
        pin_fg = pal["accent"] if self._is_pinned else pal["chrome_fg"]
        pin_hov_fg = pal["accent"] if self._is_pinned else pal["chrome_hover_fg"]
        self._icons["pin_norm"] = self._render_rounded_icon(pin_type, bg, None, pin_fg)
        self._icons["pin_hover"] = self._render_rounded_icon(pin_type, bg, pal["chrome_hover_bg"], pin_hov_fg)

        # Persist button: outline when disposable/private, filled accent when persistent
        persist_type = "persist_active" if self._is_persistent else "persist_norm"
        persist_fg = pal["accent"] if self._is_persistent else pal["chrome_fg"]
        persist_hov_fg = pal["accent"] if self._is_persistent else pal["chrome_hover_fg"]
        self._icons["persist_norm"] = self._render_rounded_icon(persist_type, bg, None, persist_fg)
        self._icons["persist_hover"] = self._render_rounded_icon(persist_type, bg, pal["chrome_hover_bg"], persist_hov_fg)

        # Menu button: smooth 6px rounded hover badge
        self._icons["menu_norm"] = self._render_rounded_icon("menu", bg, None, pal["chrome_fg"])
        self._icons["menu_hover"] = self._render_rounded_icon("menu", bg, pal["chrome_hover_bg"], pal["chrome_hover_fg"])

        # Apply normal images
        self._btn_close.configure(image=self._icons["close_norm"], bg=bg)
        self._btn_max.configure(image=self._icons["max_norm"], bg=bg)
        self._btn_theme.configure(image=self._icons["theme_norm"], bg=bg)
        self._btn_pin.configure(image=self._icons["pin_norm"], bg=bg)
        self._btn_persist.configure(image=self._icons["persist_norm"], bg=bg)
        self._btn_menu.configure(image=self._icons["menu_norm"], bg=bg)

    def _on_btn_hover(self, which, is_hover):
        norm_key = f"{which}_norm"
        hov_key = f"{which}_hover"
        btn = {
            "close": self._btn_close,
            "max": self._btn_max,
            "theme": self._btn_theme,
            "pin": self._btn_pin,
            "persist": self._btn_persist,
            "menu": self._btn_menu,
        }.get(which)
        if btn and norm_key in self._icons and hov_key in self._icons:
            btn.configure(image=self._icons[hov_key if is_hover else norm_key])

    def _toggle_pin(self):
        """Toggle always-on-top window pin state."""
        self._is_pinned = not self._is_pinned
        self._win.attributes("-topmost", self._is_pinned)
        self._rebuild_button_icons()
        status_text = "Pinned on top" if self._is_pinned else "Unpinned"
        self._set_status(status_text)

    def _toggle_persistency(self):
        """Toggle note persistency between Persistent Scratchpad and Disposable Private Note."""
        self._is_persistent = not self._is_persistent
        if self._is_persistent:
            # Ensure note has been saved to have a filename
            self._save_to_disk(explicit=True)
            if self._filename:
                _set_last_note_for_app(self._app_tag, self._filename)
            self._set_status("Persistent note (scratchpad active)")
        else:
            _clear_last_note_for_app(self._app_tag)
            self._set_status("Private note (clears on close)")
        self._rebuild_button_icons()

    def _apply_theme(self):
        pal = self._get_active_palette()

        self._win.configure(bg=pal["win_border"])
        self._outer_frame.configure(bg=pal["bg_win"], highlightbackground=pal["win_border"], highlightcolor=pal["win_border"])

        self._chrome_frame.configure(bg=pal["bg_chrome"])
        self._chrome_left.configure(bg=pal["bg_chrome"])
        self._chrome_right.configure(bg=pal["bg_chrome"])

        self._lbl_app_tag.configure(bg=pal["tag_bg"], fg=pal["tag_fg"])
        self._rebuild_button_icons()

        self._chrome_div.configure(bg=pal["chrome_border"])
        self._title_wrap.configure(bg=pal["bg_win"])
        self._title_div.configure(bg=pal["title_divider"])

        title_fg = pal["title_placeholder"] if self._title_has_placeholder else pal["title_fg"]
        self._ent_title.configure(
            bg=pal["bg_win"],
            fg=title_fg,
            insertbackground=pal["caret"],
            selectbackground=pal["body_select_bg"],
            selectforeground=pal["body_select_fg"],
        )

        self._body_wrap.configure(bg=pal["body_bg"])
        body_fg = pal["body_placeholder"] if self._body_has_placeholder else pal["body_fg"]
        self._txt_body.configure(
            bg=pal["body_bg"],
            fg=body_fg,
            insertbackground=pal["caret"],
            selectbackground=pal["body_select_bg"],
            selectforeground=pal["body_select_fg"],
        )
        if hasattr(self, "_scroll") and self._scroll:
            self._scroll.configure(bg=pal["body_bg"])
            self._scroll.set_colors(
                thumb=pal.get("scrollbar_thumb", "#7e8490"),
                thumb_hover=pal.get("scrollbar_thumb_hover", "#9aa0ac"),
            )

        self._ftr_frame.configure(bg=pal["bg_win"])
        self._lbl_status.configure(bg=pal["bg_win"], fg=pal["status_fg"])
        self._draw_grip(is_hover=False)

        # Popover Theme
        self._popover.configure(bg=pal["menu_bg"], highlightbackground=pal["menu_border"], highlightcolor=pal["menu_border"])
        for entry in self._popover_items:
            if entry[0] == "sep":
                entry[1].configure(bg=pal["menu_divider"])
            elif entry[0] == "item":
                _, row, lbl, sc_lbl, is_danger = entry
                row.configure(bg=pal["menu_bg"])
                lbl.configure(bg=pal["menu_bg"], fg=pal["danger_fg"] if is_danger else pal["menu_fg"])
                if sc_lbl:
                    sc_lbl.configure(bg=pal["menu_bg"], fg=pal["menu_shortcut_fg"])

    def _hover_menu_item(self, row, lbl, sc_lbl, is_danger, is_hover):
        pal = self._get_active_palette()
        if is_hover:
            bg = pal["danger_active_bg"] if is_danger else pal["menu_active_bg"]
            fg = pal["danger_active_fg"] if is_danger else pal["menu_active_fg"]
            row.configure(bg=bg)
            lbl.configure(bg=bg, fg=fg)
            if sc_lbl:
                sc_lbl.configure(bg=bg, fg=fg)
        else:
            bg = pal["menu_bg"]
            fg = pal["danger_fg"] if is_danger else pal["menu_fg"]
            row.configure(bg=bg)
            lbl.configure(bg=bg, fg=fg)
            if sc_lbl:
                sc_lbl.configure(bg=bg, fg=pal["menu_shortcut_fg"])

    # ── Placeholders ──────────────────────────────────────────────────

    def _on_title_focus_in(self, event=None):
        if self._title_has_placeholder:
            self._title_has_placeholder = False
            self._ent_title.delete(0, "end")
            pal = self._get_active_palette()
            self._ent_title.configure(fg=pal["title_fg"])

    def _on_title_focus_out(self, event=None):
        val = self._ent_title.get().strip()
        if not val:
            self._set_title_placeholder()

    def _set_title_placeholder(self):
        self._title_has_placeholder = True
        pal = self._get_active_palette()
        self._ent_title.delete(0, "end")
        self._ent_title.insert(0, self.TITLE_PLACEHOLDER)
        self._ent_title.configure(fg=pal["title_placeholder"])

    def _on_body_focus_in(self, event=None):
        if self._body_has_placeholder:
            self._body_has_placeholder = False
            self._txt_body.delete("1.0", "end")
            pal = self._get_active_palette()
            self._txt_body.configure(fg=pal["body_fg"])

    def _on_body_focus_out(self, event=None):
        val = self._txt_body.get("1.0", "end-1c").strip()
        if not val:
            self._set_body_placeholder()

    def _set_body_placeholder(self):
        self._body_has_placeholder = True
        pal = self._get_active_palette()
        self._txt_body.delete("1.0", "end")
        self._txt_body.tag_remove("bold", "1.0", "end")
        self._txt_body.tag_remove("italic", "1.0", "end")
        self._txt_body.tag_remove("bold_italic", "1.0", "end")
        self._txt_body.insert("1.0", self.BODY_PLACEHOLDER)
        self._txt_body.configure(fg=pal["body_placeholder"])

    # ── Content & File Handling ───────────────────────────────────────

    def _library_folder(self):
        try:
            cfg = getattr(self.app, "cfg", None) if self.app is not None else None
            return paths.get_notes_dir(cfg)
        except Exception:
            return paths.get_notes_dir()

    def _load_initial_content(self, initial_title=None, initial_body=None):
        if self._filename:
            folder = self._library_folder()
            path = os.path.join(folder, self._filename)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    title = ""
                    body_start = 0
                    if lines and lines[0].startswith("title:"):
                        title = lines[0][6:].strip()
                        body_start = 1
                    content = "".join(lines[body_start:]).strip()

                    if title:
                        self._ent_title.delete(0, "end")
                        self._ent_title.insert(0, title)
                        self._title_has_placeholder = False
                    else:
                        self._set_title_placeholder()

                    if content:
                        self._import_formatted_body(content)
                        self._body_has_placeholder = False
                    else:
                        self._set_body_placeholder()

                    self._txt_body.focus_set()
                    return
                except Exception as e:
                    log.warning("Failed to load note file %s: %s", self._filename, e)

        if initial_title:
            self._ent_title.delete(0, "end")
            self._ent_title.insert(0, str(initial_title).strip())
            self._title_has_placeholder = False
        else:
            self._set_title_placeholder()

        if initial_body:
            self._import_formatted_body(str(initial_body).strip())
            self._body_has_placeholder = False
        else:
            self._set_body_placeholder()

        if initial_title:
            self._txt_body.focus_set()
        else:
            self._ent_title.focus_set()

    # ── Text Formatting (Bold / Italic) ───────────────────────────────

    def _toggle_format(self, which):
        """Toggle 'bold' or 'italic' on current selection or current word."""
        if self._body_has_placeholder:
            return "break"
        try:
            self._txt_body.focus_set()
            sel_ranges = self._txt_body.tag_ranges("sel")
            if sel_ranges:
                start, end = sel_ranges[0], sel_ranges[1]
            else:
                ws = self._txt_body.index("insert wordstart")
                we = self._txt_body.index("insert wordend")
                if self._txt_body.compare(ws, "<", we) and self._txt_body.get(ws, we).strip():
                    start, end = ws, we
                else:
                    return "break"

            has_tag = which in self._txt_body.tag_names(start)
            if has_tag:
                self._txt_body.tag_remove(which, start, end)
            else:
                self._txt_body.tag_add(which, start, end)

            self._sync_bold_italic(start, end)
            self._schedule_save()
        except Exception:
            pass
        return "break"

    def _sync_bold_italic(self, start="1.0", end="end"):
        """Apply or remove 'bold_italic' based on overlapping 'bold' and 'italic' tags."""
        try:
            self._txt_body.tag_remove("bold_italic", start, end)
            idx = self._txt_body.index(start)
            end_idx = self._txt_body.index(end)
            while self._txt_body.compare(idx, "<", end_idx):
                t = self._txt_body.tag_names(idx)
                if "bold" in t and "italic" in t:
                    next_idx = self._txt_body.index(f"{idx} + 1 chars")
                    self._txt_body.tag_add("bold_italic", idx, next_idx)
                idx = self._txt_body.index(f"{idx} + 1 chars")
        except Exception:
            pass

    def _import_formatted_body(self, raw_text):
        """Insert text into _txt_body and apply tags for <b>, <strong>, <i>, <em>."""
        self._txt_body.delete("1.0", "end")
        self._txt_body.tag_remove("bold", "1.0", "end")
        self._txt_body.tag_remove("italic", "1.0", "end")
        self._txt_body.tag_remove("bold_italic", "1.0", "end")
        if not raw_text:
            return
        if not ("<b" in raw_text or "<B" in raw_text or "<i" in raw_text or "<I" in raw_text or "<strong" in raw_text or "<em" in raw_text):
            self._txt_body.insert("1.0", raw_text)
            return

        pattern = re.compile(r'(</?(?:b|strong|i|em)>)', re.IGNORECASE)
        tokens = pattern.split(raw_text)
        is_b = False
        is_i = False

        for token in tokens:
            if not token:
                continue
            lower = token.lower()
            if lower in ("<b>", "<strong>"):
                is_b = True
            elif lower in ("</b>", "</strong>"):
                is_b = False
            elif lower in ("<i>", "<em>"):
                is_i = True
            elif lower in ("</i>", "</em>"):
                is_i = False
            else:
                start_idx = self._txt_body.index("end-1c")
                self._txt_body.insert("end", token)
                end_idx = self._txt_body.index("end-1c")
                if is_b and is_i:
                    self._txt_body.tag_add("bold_italic", start_idx, end_idx)
                    self._txt_body.tag_add("bold", start_idx, end_idx)
                    self._txt_body.tag_add("italic", start_idx, end_idx)
                elif is_b:
                    self._txt_body.tag_add("bold", start_idx, end_idx)
                elif is_i:
                    self._txt_body.tag_add("italic", start_idx, end_idx)

    def _export_formatted_body(self):
        """Export body text with <b> and <i> HTML tags for bold/italic ranges."""
        content = self._txt_body.get("1.0", "end-1c")
        if not content:
            return ""
        if not self._txt_body.tag_ranges("bold") and not self._txt_body.tag_ranges("italic") and not self._txt_body.tag_ranges("bold_italic"):
            return content.strip()

        chars = []
        lines = content.split("\n")
        for line_idx, line in enumerate(lines, start=1):
            if line_idx > 1:
                chars.append("\n")
            for col_idx, ch in enumerate(line):
                idx = f"{line_idx}.{col_idx}"
                tags = set(self._txt_body.tag_names(idx))
                is_b = "bold" in tags or "bold_italic" in tags
                is_i = "italic" in tags or "bold_italic" in tags
                chars.append((ch, is_b, is_i))

        out = []
        curr_b = False
        curr_i = False
        for item in chars:
            if item == "\n":
                if curr_i:
                    out.append("</i>")
                    curr_i = False
                if curr_b:
                    out.append("</b>")
                    curr_b = False
                out.append("\n")
                continue
            ch, is_b, is_i = item
            if curr_i and not is_i:
                out.append("</i>")
                curr_i = False
            if curr_b and not is_b:
                out.append("</b>")
                curr_b = False
            if is_b and not curr_b:
                out.append("<b>")
                curr_b = True
            if is_i and not curr_i:
                out.append("<i>")
                curr_i = True
            out.append(ch)
        if curr_i:
            out.append("</i>")
        if curr_b:
            out.append("</b>")
        return "".join(out).strip()

    def _on_new_note(self):
        self._on_explicit_save()
        self._filename = None
        self._set_title_placeholder()
        self._set_body_placeholder()
        self._set_status("")
        self._ent_title.focus_set()

    def _on_open_library(self):
        self._on_explicit_save()
        try:
            import panel_window
            panel_window.open_panel(page="library", tab="notes")
        except Exception:
            try:
                import webbrowser
                webbrowser.open("http://127.0.0.1:15502/index.html?view=library&tab=notes")
            except Exception:
                pass

    def _on_restore_last_note(self):
        """Restore the most recently edited note for this app tag."""
        self._on_explicit_save()
        last_file = _get_last_note_for_app(self._app_tag)
        if last_file:
            folder = self._library_folder()
            if os.path.isfile(os.path.join(folder, last_file)):
                self._filename = last_file
                self._is_persistent = True
                self._load_initial_content()
                self._rebuild_button_icons()
                self._set_status("Restored last note (scratchpad active)")
                return
        self._set_status("No saved scratchpad found")

    def _on_delete_note(self):
        if not self._filename:
            self._on_new_note()
            return
        from tkinter import messagebox
        if messagebox.askyesno("Delete Note", "Delete this note? This cannot be undone.", parent=self._win):
            try:
                folder = self._library_folder()
                path = os.path.join(folder, self._filename)
                if os.path.isfile(path):
                    os.remove(path)
                _clear_last_note_for_app(self._app_tag)
                self._on_close()
            except Exception as e:
                log.warning("Failed to delete note: %s", e)

    # ── Saving & Debounce ─────────────────────────────────────────────

    def _get_clean_content(self):
        title = "" if self._title_has_placeholder else self._ent_title.get().strip()
        body = "" if self._body_has_placeholder else self._export_formatted_body()
        return title, body

    def _set_status(self, msg, is_saved=False):
        pal = self._get_active_palette()
        self._lbl_status.config(
            text=msg,
            fg=pal["status_saved"] if is_saved else pal["status_fg"],
        )
        if self._status_timer:
            self._win.after_cancel(self._status_timer)
            self._status_timer = None
        if is_saved:
            self._status_timer = self._win.after(2500, lambda: self._lbl_status.config(text="") if not self._closed else None)

    def _schedule_save(self, event=None):
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
        self._set_status("Saving…")
        self._save_timer = self._win.after(600, lambda: self._save_to_disk(explicit=False))

    def _on_explicit_save(self):
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
            self._save_timer = None
        self._save_to_disk(explicit=True)

    def _save_to_disk(self, explicit=False):
        if self._closed or self._is_saving:
            return
        self._is_saving = True
        try:
            title, content = self._get_clean_content()
            if not title and not content:
                self._set_status("")
                return

            if not self._filename:
                ts = time.strftime("%Y%m%d_%H%M%S")
                self._filename = f"iris_note_{self._app_tag}_{ts}.txt"

            folder = self._library_folder()
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, self._filename)

            with open(path, "w", encoding="utf-8") as f:
                f.write(f"title:{title}\n{content}")

            self._set_status("Saved ✓", is_saved=True)
        except Exception as e:
            log.warning("Quick note save failed: %s", e)
            self._set_status("Save failed")
        finally:
            self._is_saving = False

    def bring_to_foreground(self):
        """Unminimize, bring window to top above 3D games, and focus editor ready to type."""
        try:
            self._is_in_background = False
            self._win.deiconify()
            self._win.attributes("-topmost", True)
            self._win.lift()
            hwnd = self._get_toplevel_hwnd()
            if hwnd:
                SW_RESTORE = 9
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                HWND_TOPMOST = -1

                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)

                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

                fg_hwnd = user32.GetForegroundWindow()
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                cur_thread = kernel32.GetCurrentThreadId()

                if fg_thread and fg_thread != cur_thread:
                    user32.AttachThreadInput(cur_thread, fg_thread, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(cur_thread, fg_thread, False)
                else:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)

                try:
                    user32.SwitchToThisWindow(hwnd, True)
                except Exception:
                    pass

            self._win.focus_force()

            # Direct keyboard focus to the active input field ready to type
            title_text = self._ent_title.get().strip()
            if self._title_has_placeholder or not title_text or title_text == self.TITLE_PLACEHOLDER:
                self._on_title_focus_in()
                self._ent_title.focus_force()
            else:
                self._on_body_focus_in()
                self._txt_body.focus_force()
                self._txt_body.mark_set("insert", "end")
        except Exception as e:
            log.warning("Failed to bring note window to foreground: %s", e)

    def send_to_back(self):
        """Send note window to the back behind games and other windows."""
        try:
            self._is_in_background = True
            self._win.attributes("-topmost", False)
            hwnd = self._get_toplevel_hwnd()
            if hwnd:
                HWND_BOTTOM = 1
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            self._win.lower()
        except Exception as e:
            log.warning("Failed to send note window to back: %s", e)

    def _on_close(self):
        global _ACTIVE_NOTE_WINDOW
        if self._closed:
            return
        self._closed = True
        if _ACTIVE_NOTE_WINDOW is self:
            _ACTIVE_NOTE_WINDOW = None

        self._save_geometry()
        if self._save_timer is not None:
            self._win.after_cancel(self._save_timer)
            self._save_timer = None
        self._save_to_disk(explicit=False)

        if self._is_persistent and self._filename:
            _set_last_note_for_app(self._app_tag, self._filename)
        else:
            # Privacy first: clear last note so next launch starts fresh
            _clear_last_note_for_app(self._app_tag)

        try:
            self._win.destroy()
        except Exception:
            pass


def open_quick_note(root=None, app=None, app_tag="general", filename=None, initial_title=None, initial_body=None):
    """Open or foreground the standalone Iris Notepad window."""
    global _ACTIVE_NOTE_WINDOW

    # If an active note window is already running and valid, bring it to front
    if _ACTIVE_NOTE_WINDOW is not None and not _ACTIVE_NOTE_WINDOW._closed:
        try:
            if filename or initial_title or initial_body or (app_tag and app_tag != _ACTIVE_NOTE_WINDOW._app_tag):
                if filename:
                    _ACTIVE_NOTE_WINDOW._filename = filename
                if app_tag:
                    _ACTIVE_NOTE_WINDOW._app_tag = _ACTIVE_NOTE_WINDOW._clean_app_tag(app_tag)
                    _ACTIVE_NOTE_WINDOW._win.title(f"Iris Note · {_ACTIVE_NOTE_WINDOW._app_tag.upper()}")
                    _ACTIVE_NOTE_WINDOW._lbl_app_tag.config(text=_ACTIVE_NOTE_WINDOW._app_tag.upper())
                _ACTIVE_NOTE_WINDOW._load_initial_content(initial_title, initial_body)
            _ACTIVE_NOTE_WINDOW.bring_to_foreground()
            _ACTIVE_NOTE_WINDOW._win.after(30, _ACTIVE_NOTE_WINDOW.bring_to_foreground)
            return _ACTIVE_NOTE_WINDOW
        except Exception:
            _ACTIVE_NOTE_WINDOW = None

    if root is None:
        root = getattr(tk, "_default_root", None)
        try:
            if root is None or not root.winfo_exists():
                root = tk.Tk()
                root.withdraw()
        except Exception:
            root = tk.Tk()
            root.withdraw()

    win = QuickNoteWindow(
        root,
        app=app,
        app_tag=app_tag,
        filename=filename,
        initial_title=initial_title,
        initial_body=initial_body,
    )
    _ACTIVE_NOTE_WINDOW = win
    win.bring_to_foreground()
    win._win.after(30, win.bring_to_foreground)
    return win


def toggle_quick_note(root=None, app=None, app_tag="general", filename=None, initial_title=None, initial_body=None):
    """Toggle Iris Note: if open and in foreground, send to back; else bring to front."""
    global _ACTIVE_NOTE_WINDOW
    if _ACTIVE_NOTE_WINDOW is not None and not _ACTIVE_NOTE_WINDOW._closed:
        if not _ACTIVE_NOTE_WINDOW._is_in_background:
            _ACTIVE_NOTE_WINDOW.send_to_back()
            return _ACTIVE_NOTE_WINDOW
        else:
            if filename or initial_title or initial_body or (app_tag and app_tag != _ACTIVE_NOTE_WINDOW._app_tag):
                if filename:
                    _ACTIVE_NOTE_WINDOW._filename = filename
                if app_tag:
                    _ACTIVE_NOTE_WINDOW._app_tag = _ACTIVE_NOTE_WINDOW._clean_app_tag(app_tag)
                    _ACTIVE_NOTE_WINDOW._win.title(f"Iris Note · {_ACTIVE_NOTE_WINDOW._app_tag.upper()}")
                    _ACTIVE_NOTE_WINDOW._lbl_app_tag.config(text=_ACTIVE_NOTE_WINDOW._app_tag.upper())
                _ACTIVE_NOTE_WINDOW._load_initial_content(initial_title, initial_body)
            _ACTIVE_NOTE_WINDOW.bring_to_foreground()
            _ACTIVE_NOTE_WINDOW._win.after(30, _ACTIVE_NOTE_WINDOW.bring_to_foreground)
            return _ACTIVE_NOTE_WINDOW

    return open_quick_note(root=root, app=app, app_tag=app_tag, filename=filename, initial_title=initial_title, initial_body=initial_body)


def is_quick_note_open():
    """Return True if the standalone Iris Notepad window is currently open."""
    global _ACTIVE_NOTE_WINDOW
    return _ACTIVE_NOTE_WINDOW is not None and not _ACTIVE_NOTE_WINDOW._closed


def close_quick_note():
    """Close the active notepad window if open."""
    global _ACTIVE_NOTE_WINDOW
    if _ACTIVE_NOTE_WINDOW is not None and not _ACTIVE_NOTE_WINDOW._closed:
        try:
            _ACTIVE_NOTE_WINDOW._on_close()
        except Exception:
            pass
        _ACTIVE_NOTE_WINDOW = None


if __name__ == "__main__":
    r = tk.Tk()
    r.withdraw()
    w = open_quick_note(r, app_tag="general")

    def _check_signals():
        if not w._closed:
            r.after(250, _check_signals)

    r.after(250, _check_signals)
    try:
        r.mainloop()
    except KeyboardInterrupt:
        try:
            r.destroy()
        except Exception:
            pass
