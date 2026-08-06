"""Iris — iPhone-shaped overlay main window."""

import logging
import time as _time
import tkinter as tk
import ctypes
import ctypes.wintypes

from PIL import Image, ImageDraw, ImageTk

from constants import BG, BG_CARD, DEFAULT_BRIGHTNESS, FG, FG_DIM, NEON, BUTTON, FONT_SM
from widgets import CircularGauge, StepSlider, ToolTip
import mdi_icons

log = logging.getLogger("iris.main_window")


def _find_ha_url(cfg):
    """Best-effort HA base URL from config."""
    raw = (cfg.get("ha_url") or "").strip().rstrip("/")
    return raw or None

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# ── Hardware-key SendInput structures (user's proven layout) ─────
PUL = ctypes.POINTER(ctypes.c_ulong)

class _KBD_INPUT(ctypes.Structure):
    _fields_ = [("wVk",         ctypes.c_ushort),
                ("wScan",       ctypes.c_ushort),
                ("dwFlags",     ctypes.c_ulong),
                ("time",        ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class _MOUSE_INPUT(ctypes.Structure):
    _fields_ = [("dx",          ctypes.c_long),
                ("dy",          ctypes.c_long),
                ("mouseData",   ctypes.c_ulong),
                ("dwFlags",     ctypes.c_ulong),
                ("time",        ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class _HW_INPUT(ctypes.Structure):
    _fields_ = [("uMsg",    ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("lParamH", ctypes.c_ushort)]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KBD_INPUT),
                ("mi", _MOUSE_INPUT),
                ("hi", _HW_INPUT)]

class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii",   _INPUT_UNION)]


def _hardware_key(scan_code, press=True):
    """Send a single key press/release via hardware scancode."""
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if not press:
        flags |= 0x0002  # KEYEVENTF_KEYUP
    extra = ctypes.c_ulong(0)
    ii = _INPUT_UNION()
    ii.ki = _KBD_INPUT(0, scan_code, flags, 0, ctypes.pointer(extra))
    inp = _INPUT(ctypes.c_ulong(1), ii)
    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_ulong]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

WS_EX_LAYERED = 0x80000
LWA_ALPHA = 0x2
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
GWL_EXSTYLE = -20


def _apply_window_style(hwnd, alpha=0.9):
    try:
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute(
            hwnd, 33,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass

    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    user32.SetLayeredWindowAttributes(hwnd, 0, int(alpha * 255), LWA_ALPHA)


def _set_round_rect(hwnd, w, h, r):
    hrgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r)
    user32.SetWindowRgn(hwnd, hrgn, True)


class MainWindow:
    W = 220
    H = 568
    RADIUS = 24
    ALPHA = 0.9

    def __init__(self, root, app, cfg=None):
        self.app = app
        self._root = root
        self._cfg = cfg or {}
        self._visible = False
        self._status_icons = {}
        self._drag_x = self._drag_y = self._drag_ox = self._drag_oy = None
        self._saved_foreground_hwnd = None
        self._sending_hotkey = False
        self._sticky_after_id = None
        self._sticky_leave_active = False

        self._win = tk.Toplevel(root)
        self._win.title("Iris")
        self._win.overrideredirect(True)
        self._win.configure(bg=BG)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        _m = 20  # fresh-install default: bottom-right with small margin
        x = self._cfg.get("panel_x")
        y = self._cfg.get("panel_y")
        if x is None:
            x = sw - self.W - _m
        if y is None:
            y = sh - self.H - _m
        self._panel_x = int(x)
        self._panel_y = int(y)
        self._win.geometry(f"{self.W}x{self.H}+{x}+{y}")

        hwnd = int(self._win.winfo_id())
        self._hwnd = hwnd
        _apply_window_style(hwnd, self.ALPHA)

        self._win.bind("<Map>", self._on_map)
        self._win.bind("<Escape>", lambda e: self.hide())
        self._win.bind("<FocusOut>", self._on_focusout)
        self._win.bind("<FocusIn>", self._on_focusin)

        self._build_ui()
        if self._cfg.get("panel_pin"):
            self._win.attributes("-topmost", True)
            self._pin_pinned = True
            icon = mdi_icons.render("pin", 16, (72, 178, 233))
            photo = ImageTk.PhotoImage(icon)
            self._pin_btn.config(image=photo)
            self._pin_btn.image = photo
        self._win.withdraw()

    def _on_map(self, event):
        self._win.after_idle(self._apply_region)

    def _apply_region(self):
        hwnd = int(self._win.winfo_id())
        w = self._win.winfo_width()
        h = self._win.winfo_height()
        if w > 1 and h > 1:
            _set_round_rect(hwnd, w, h, self.RADIUS)

    def _build_ui(self):
        self._sb = tk.Frame(self._win, bg=BG_CARD, height=28)
        self._sb.place(x=0, y=0, relwidth=1.0)
        self._sb.pack_propagate(False)

        self._lbl_port = tk.Label(
            self._sb, text="Offline",
            font=("Consolas", 9), fg=FG, bg=BG_CARD,
        )
        self._lbl_port.pack(side=tk.LEFT, padx=(10, 0))

        # Pin button (center)
        pin_icon = ImageTk.PhotoImage(mdi_icons.render("pin-outline", 16, (180, 180, 180)))
        self._pin_btn = tk.Label(
            self._sb, image=pin_icon, bg=BG_CARD, cursor="hand2",
            padx=4, pady=0,
        )
        self._pin_btn.image = pin_icon
        self._pin_btn.pack(side=tk.LEFT, expand=True)
        self._pin_pinned = False
        self._pin_btn.bind("<Button-1>", self._toggle_pin)
        self._pin_btn.bind("<ButtonRelease-1>", lambda e: None)  # prevent drag

        right_frame = tk.Frame(self._sb, bg=BG_CARD)
        right_frame.pack(side=tk.RIGHT, padx=(0, 10))

        self._status_bar = right_frame

        self._lbl_time = tk.Label(
            right_frame, text="--:--",
            font=("Consolas", 9), fg=FG, bg=BG_CARD,
        )
        self._lbl_time.pack(side=tk.RIGHT)

        self.register_status_icon("alarm", "bell-ring")

        gauge_size = 60
        gf = tk.Frame(self._win, bg=BG)
        self._gauge_frame = gf
        gf.place(x=15, y=36, width=190, height=gauge_size + 10)
        gf.columnconfigure(0, weight=1)
        gf.columnconfigure(1, weight=1)
        gf.columnconfigure(2, weight=1)

        self._gauge_cpu = CircularGauge(gf, "CPU", 100, "\u00b0", size=gauge_size)
        self._gauge_cpu.grid(row=0, column=0)

        self._gauge_gpu = CircularGauge(gf, "GPU", 100, "\u00b0", size=gauge_size)
        self._gauge_gpu.grid(row=0, column=1)

        self._gauge_fps = CircularGauge(gf, "FPS", 240, "", size=gauge_size)
        self._gauge_fps.grid(row=0, column=2)

        gf.bind("<Button-1>", self._on_gauge_click)
        for w in gf.winfo_children():
            w.bind("<Button-1>", self._on_gauge_click)

        self._sep_gauges = tk.Frame(self._win, bg=BG_CARD, height=1)

        self._build_button_panel()
        self._build_tiles()
        self._reflow_panel()
        self._update_status()

        # Drag window only from the status bar
        self._sb.bind("<Button-1>", self._sb_drag_start)
        self._sb.bind("<ButtonRelease-1>", self._sb_drag_end)
        self._win.bind("<B1-Motion>", self._sb_drag_move)

        # Right-click context menu
        self._ctx_menu = tk.Menu(self._win, tearoff=0, bg=BG_CARD, fg=FG,
                                 activebackground=NEON, activeforeground=BG)
        self._ctx_menu.add_command(label="Quit Iris", command=self.app._quit)
        self._win.bind("<Button-3>", self._show_ctx_menu)

    # ── Status bar drag (move window) ──────────────────────────────────

    def _toggle_pin(self, e=None):
        self._pin_pinned = not self._pin_pinned
        self._win.attributes("-topmost", self._pin_pinned)
        icon = mdi_icons.render("pin" if self._pin_pinned else "pin-outline", 16,
                                (72, 178, 233) if self._pin_pinned else (180, 180, 180))
        photo = ImageTk.PhotoImage(icon)
        self._pin_btn.config(image=photo)
        self._pin_btn.image = photo
        self._cfg["panel_pin"] = self._pin_pinned
        from config import save_config
        save_config(self._cfg)

    def _sb_drag_start(self, e):
        self._drag_x = e.x_root
        self._drag_y = e.y_root
        self._drag_ox = self._win.winfo_x()
        self._drag_oy = self._win.winfo_y()

    def _sb_drag_move(self, e):
        if self._drag_x is None:
            return
        x = self._drag_ox + (e.x_root - self._drag_x)
        y = self._drag_oy + (e.y_root - self._drag_y)
        self._win.geometry(f"+{x}+{y}")

    def _sb_drag_end(self, e):
        self._drag_x = self._drag_y = self._drag_ox = self._drag_oy = None
        self._panel_x = self._win.winfo_x()
        self._panel_y = self._win.winfo_y()
        self._cfg["panel_x"] = self._panel_x
        self._cfg["panel_y"] = self._panel_y
        from config import save_config
        save_config(self._cfg)

    # ── Context menu ────────────────────────────────────────────────

    def _show_ctx_menu(self, e):
        self._ctx_menu.tk_popup(e.x_root, e.y_root)

    # ── Custom button panel (with sub-panel navigation) ─────────────

    def _build_button_panel(self):
        _W = 190
        _X = (self.W - _W) // 2
        _PANEL_Y = 121
        _PANEL_H = 150

        self._btn_panel = tk.Frame(self._win, bg=BG)
        self._btn_panel.place(x=_X, y=_PANEL_Y, width=_W, height=_PANEL_H)
        self._btn_panel.pack_propagate(False)

        self._btn_canvas = tk.Canvas(
            self._btn_panel, bg=BG, highlightthickness=0,
            width=_W, height=_PANEL_H)
        self._btn_canvas.pack(fill=tk.BOTH, expand=True)

        self._btn_inner = tk.Frame(self._btn_canvas, bg=BG, width=_W)
        self._btn_canvas.create_window((0, 0), window=self._btn_inner, anchor="nw")

        self._btn_tile_refs = []
        self._btn_nav = []  # stack of panel button dicts being viewed
        self._render_buttons()

        self._btn_inner.bind("<Configure>",
            lambda e: self._btn_canvas.configure(
                scrollregion=self._btn_canvas.bbox("all")))
        self._btn_canvas.bind("<MouseWheel>", self._on_btn_wheel)
        self._btn_inner.bind("<MouseWheel>", self._on_btn_wheel)

    def btn_nav_root(self):
        """Pop back to root level."""
        self._btn_nav.clear()
        self._render_buttons()

    def btn_nav_push(self, panel_slot):
        """Push a panel context and re-render."""
        self._btn_nav.append(panel_slot)
        self._render_buttons()

    def btn_nav_pop(self):
        """Go up one level."""
        if self._btn_nav:
            self._btn_nav.pop()
        self._render_buttons()

    def set_overlay_state(self, on):
        self._overlay_on = on
        ov = self._ov_tiles
        self._btn_overlay.config(image=ov[2] if on else ov[0])

    def set_saved_foreground(self, hwnd):
        self._saved_foreground_hwnd = hwnd

    def refresh_buttons(self):
        self._render_buttons()

    def rebuild_panel(self):
        """Re-apply panel config (buttons + utility) after settings save."""
        try:
            from panel_actions import ensure_panel_defaults
            ensure_panel_defaults(self.app.cfg)
        except Exception:
            pass
        self._btn_nav = []
        self._render_buttons()
        self._render_utility_row()
        self._reflow_panel()

    def _render_utility_row(self):
        """Build the 4 utility tiles from panel_utility config (placement via reflow)."""
        frame = getattr(self, "_utility_frame", None)
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        self._utility_tile_refs = []
        _T, _GAP = 40, 10
        slots = self.app.cfg.get("panel_utility") or []
        for i in range(4):
            slot = slots[i] if i < len(slots) else {"type": "EMPTY", "icon": "border-none-variant"}
            if slot.get("type") == "EMPTY":
                continue
            icon = slot.get("icon") or "help-circle"
            fill = slot.get("color") or BG_CARD
            if not fill or fill == "RAINBOW":
                fill = BG_CARD
            imgs = [
                self._make_tile_photo(icon, fill, icon_scale=0.52),
                self._make_tile_photo(icon, self._adjust_hex(fill, 20), icon_scale=0.52),
            ]
            prs = self._make_tile_photo(icon, self._adjust_hex(fill, -20), icon_scale=0.52)
            self._utility_tile_refs.extend(imgs + [prs])
            btn = tk.Label(frame, image=imgs[0], bg=BG, cursor="hand2",
                           padx=0, pady=0, borderwidth=0)
            btn.place(x=i * (_T + _GAP), y=0)
            btn.bind("<Enter>", lambda e, imgs_=imgs, b=btn: b.config(image=imgs_[1]))
            btn.bind("<Leave>", lambda e, imgs_=imgs, b=btn: b.config(image=imgs_[0]))
            btn.bind("<ButtonPress-1>", lambda e, p=prs, b=btn: b.config(image=p))
            btn.bind("<ButtonRelease-1>",
                     lambda e, s=slot, imgs_=imgs, b=btn: (b.config(image=imgs_[0]), self._on_button_action(s)))
            name = slot.get("name") or ""
            if name:
                ToolTip(btn, name)

    @staticmethod
    def _place_or_forget(widget, show, **kw):
        if widget is None:
            return
        if show:
            widget.place(**kw)
        else:
            widget.place_forget()

    def _hardware_connected(self):
        """True when Iris hardware is on the serial link."""
        try:
            from serial_comm import serial_sender
            if serial_sender.connected_port() is not None:
                return True
        except Exception:
            pass
        try:
            return bool(getattr(self.app, "_online", False))
        except Exception:
            return False

    def _panel_section_flags(self):
        """(gauges, button_box, volume, brightness, mixer, utility) from cfg."""
        try:
            from panel_actions import (
                layout_enabled, slider_enabled, ensure_panel_defaults)
            ensure_panel_defaults(self.app.cfg)
            gauges = layout_enabled(self.app.cfg, "gauges")
            gcfg = self.app.cfg.get("panel_gauges") or {}
            if isinstance(gcfg, dict) and gcfg.get("enabled") is False:
                gauges = False
            box = layout_enabled(self.app.cfg, "button_box")
            sliders = layout_enabled(self.app.cfg, "sliders")
            vol = sliders and slider_enabled(self.app.cfg, "app_volume")
            # Brightness only when hardware is present (controls the device LEDs)
            bri = (sliders and slider_enabled(self.app.cfg, "brightness")
                   and self._hardware_connected())
            mix = sliders and slider_enabled(self.app.cfg, "app_mixer")
            util = layout_enabled(self.app.cfg, "utility")
            return gauges, box, vol, bri, mix, util
        except Exception:
            return True, True, True, False, True, True

    def _reflow_panel(self):
        """Stack visible sections top-down and shrink the window to fit."""
        gauges, box, vol, bri, mix, util = self._panel_section_flags()
        _W, _T, _GAP = 190, 40, 10
        _X = (self.W - _W) // 2
        GAUGE_H, BTN_H, SLIDER_H = 70, 150, 28
        TITLE_H, APP_H, SEP, BOTTOM = 16, 14, 1, 24

        y = 28 + 8

        self._place_or_forget(
            getattr(self, "_gauge_frame", None), gauges,
            x=_X, y=y, width=_W, height=GAUGE_H)
        if gauges:
            y += GAUGE_H + 5
            self._place_or_forget(
                getattr(self, "_sep_gauges", None), True, x=_X, y=y, width=_W)
            y += SEP + 10
        else:
            self._place_or_forget(getattr(self, "_sep_gauges", None), False)

        self._place_or_forget(
            getattr(self, "_btn_panel", None), box,
            x=_X, y=y, width=_W, height=BTN_H)
        if box:
            y += BTN_H + 10

        any_sl = vol or bri
        self._place_or_forget(
            getattr(self, "_sep_sliders", None), any_sl, x=_X, y=y, width=_W)
        if any_sl:
            y += SEP + 5

        if vol:
            self._place_or_forget(
                getattr(self, "_lbl_volume_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H + 1
            self._place_or_forget(
                getattr(self, "_lbl_volume_app", None), True,
                x=_X + 2, y=y, width=_W - 2, height=APP_H)
            y += APP_H + 1
            self._place_or_forget(
                getattr(self, "_slider_volume", None), True, x=_X, y=y, width=_W)
            y += SLIDER_H + 8
        else:
            self._place_or_forget(getattr(self, "_lbl_volume_title", None), False)
            self._place_or_forget(getattr(self, "_lbl_volume_app", None), False)
            self._place_or_forget(getattr(self, "_slider_volume", None), False)

        if bri:
            self._place_or_forget(
                getattr(self, "_lbl_brightness_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H + 1
            self._place_or_forget(
                getattr(self, "_slider_brightness", None), True, x=_X, y=y, width=_W)
            y += SLIDER_H + 8
        else:
            self._place_or_forget(getattr(self, "_lbl_brightness_title", None), False)
            self._place_or_forget(getattr(self, "_slider_brightness", None), False)

        self._mixer_enabled = bool(mix)
        if mix:
            mixer_h = max(getattr(self, "_mixer_h", 0) or 0, 1)
            self._place_or_forget(
                getattr(self, "_lbl_mixer_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H + 1
            self._place_or_forget(
                getattr(self, "_mixer_frame", None), True,
                x=_X, y=y, width=_W, height=mixer_h)
            y += mixer_h + 8
        else:
            self._place_or_forget(getattr(self, "_lbl_mixer_title", None), False)
            self._place_or_forget(getattr(self, "_mixer_frame", None), False)

        self._place_or_forget(
            getattr(self, "_sep_utility", None), util, x=_X, y=y, width=_W)
        if util:
            y += SEP + 10
            self._place_or_forget(
                getattr(self, "_utility_frame", None), True,
                x=_X, y=y, width=4 * _T + 3 * _GAP, height=_T)
            y += _T + 10
        else:
            self._place_or_forget(getattr(self, "_utility_frame", None), False)

        self._place_or_forget(
            getattr(self, "_sep_core", None), True, x=_X, y=y, width=_W)
        y += SEP + 12
        self._place_or_forget(
            getattr(self, "_core_frame", None), True,
            x=_X, y=y, width=4 * _T + 3 * _GAP, height=_T)
        y += _T + BOTTOM

        hero = getattr(self, "_hero_btn", None)
        if hero is not None:
            self._place_or_forget(hero, True, relx=0.5, y=y - 20, anchor=tk.CENTER, width=80, height=18)

        new_h = max(int(y), 28 + _T + BOTTOM)
        old_h = getattr(self, "_panel_h", None)
        if old_h is None:
            try:
                wh = int(self._win.winfo_height())
                old_h = wh if wh > 1 else self.H
            except Exception:
                old_h = self.H
        self._panel_h = new_h

        try:
            x = int(self._panel_x)
            wy = int(self._panel_y)
        except Exception:
            x, wy = 0, 0
        # Keep bottom edge fixed (panel usually sits near screen bottom)
        new_y = wy + old_h - new_h
        try:
            sw = int(self._win.winfo_screenwidth())
            sh = int(self._win.winfo_screenheight())
            if new_y < 0:
                new_y = 0
            if new_y + new_h > sh:
                new_y = max(0, sh - new_h)
            # Keep the panel fully on screen horizontally as well.
            if x < 0:
                x = 0
            if x + self.W > sw:
                x = max(0, sw - self.W)
        except Exception:
            pass
        self._win.geometry(f"{self.W}x{new_h}+{x}+{new_y}")
        self._panel_x = x
        self._panel_y = new_y
        try:
            self._win.update_idletasks()
            self._apply_region()
        except Exception:
            pass

    def _current_buttons(self):
        """Return the list of buttons to render at the current nav level."""
        if not self._btn_nav:
            return self.app.cfg.get("panel_board") or []
        return (self._btn_nav[-1].get("children") or [])

    def _render_buttons(self):
        for w in self._btn_inner.winfo_children():
            w.destroy()
        self._btn_tile_refs.clear()

        buttons = self._current_buttons()
        _T, _GAP = 40, 10
        _W = 190
        _COLS = 4
        col_offset = 0
        row_offset = 0

        # Back button if in a sub-panel — occupies grid slot 0
        if self._btn_nav:
            parent = self._btn_nav[-1]
            back_img = self._make_tile_photo("reply", BUTTON, icon_color=(72, 178, 233))
            back_hov = self._make_tile_photo("reply", self._adjust_hex(BUTTON, 20), icon_color=(72, 178, 233))
            self._btn_tile_refs.extend([back_img, back_hov])
            back_btn = tk.Label(self._btn_inner, image=back_img, bg=BG, cursor="hand2",
                                padx=0, pady=0, borderwidth=0)
            back_btn.place(x=0, y=0)
            def _bh(e, b=back_btn, h=back_hov, n=back_img): b.config(image=h)
            def _bl(e, b=back_btn, n=back_img): b.config(image=n)
            back_btn.bind("<Enter>", _bh)
            back_btn.bind("<Leave>", _bl)
            back_btn.bind("<ButtonRelease-1>", lambda e: self._win.after_idle(self.btn_nav_pop))
            back_btn.bind("<MouseWheel>", self._on_btn_wheel)

        # "+" empty-state prompt (only when no buttons exist at this level)
        if not buttons:
            _px = (_T + _GAP) if self._btn_nav else 0  # past back button
            plus_img = self._make_tile_photo("plus", BG_CARD)
            plus_hov = self._make_tile_photo("plus", self._adjust_hex(BG_CARD, 20))
            self._btn_tile_refs.extend([plus_img, plus_hov])
            plus_btn = tk.Label(self._btn_inner, image=plus_img, bg=BG, cursor="hand2",
                                padx=0, pady=0, borderwidth=0)
            plus_btn.place(x=_px, y=row_offset * (_T + _GAP))
            def _ph(e, b=plus_btn, h=plus_hov, n=plus_img): b.config(image=h)
            def _pl(e, b=plus_btn, n=plus_img): b.config(image=n)
            plus_btn.bind("<Enter>", _ph)
            plus_btn.bind("<Leave>", _pl)
            plus_btn.bind("<Button-1>", lambda e: self.app._open_settings())
            plus_btn.bind("<MouseWheel>", self._on_btn_wheel)
            plus_tip = tk.Label(self._btn_inner, text="Add",
                                font=("Segoe UI", 6), fg=FG, bg=BG)
            plus_tip.place(x=_px, y=row_offset * (_T + _GAP) + _T - 2, width=_T, height=12)
            plus_tip.bind("<MouseWheel>", self._on_btn_wheel)

        max_row = row_offset

        for i, slot in enumerate(buttons):
            if slot is None:
                continue
            idx = i + 1 if self._btn_nav else i  # shift by 1 for back button
            col = idx % _COLS
            row = idx // _COLS
            max_row = max(max_row, row)

            btype = slot.get("type", "")
            if btype == "AUDIO OUTPUT":
                cur_id = None
                try:
                    from win_platform import get_current_default_audio_output
                    cur_id = get_current_default_audio_output()
                except Exception:
                    pass
                alt_id = slot.get("audio_input_device_id_alt", "").strip()
                if alt_id and cur_id and cur_id == alt_id:
                    icon_name = slot.get("audio_alt_icon") or "headphones"
                else:
                    icon_name = slot.get("audio_primary_icon") or "speaker"
            else:
                icon_name = slot.get("icon") or "help-circle"
            fill = slot.get("color") or BG_CARD
            name = slot.get("name") or ""
            app_icon = slot.get("app_icon_path") or (slot.get("shortcut_path") if btype in ("SHORTCUT", "GROUP") else None)
            ring = NEON if btype == "GROUP" else None

            img = self._make_tile_photo(icon_name, fill, ring_hex=ring, app_icon_path=app_icon)
            hov = self._make_tile_photo(icon_name, self._adjust_hex(fill, 20), ring_hex=ring, app_icon_path=app_icon)
            prs = self._make_tile_photo(icon_name, self._adjust_hex(fill, -20), ring_hex=ring, app_icon_path=app_icon)
            self._btn_tile_refs.extend([img, hov, prs])

            btn = tk.Label(self._btn_inner, image=img, bg=BG, cursor="hand2",
                           padx=0, pady=0, borderwidth=0)
            btn.place(x=col * (_T + _GAP), y=row * (_T + _GAP))
            btn.bind("<MouseWheel>", self._on_btn_wheel)

            def _on_enter(e, b=btn, h=hov): b.config(image=h)
            def _on_leave(e, b=btn, n=img): b.config(image=n)
            def _on_press(e, b=btn, p=prs): b.config(image=p)
            def _on_release(e, b=btn, s=slot, n=img):
                b.config(image=n)
                self._on_button_action(s)

            btn.bind("<Enter>", _on_enter)
            btn.bind("<Leave>", _on_leave)
            btn.bind("<ButtonPress-1>", _on_press)
            btn.bind("<ButtonRelease-1>", _on_release)

            if name:
                ToolTip(btn, name)

        nrows = max_row + 1
        self._btn_inner.configure(height=nrows * (_T + _GAP) + _GAP)

    @staticmethod
    def _adjust_hex(hex_color, amount):
        try:
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
            r = max(0, min(255, r + amount))
            g = max(0, min(255, g + amount))
            b = max(0, min(255, b + amount))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def _on_btn_wheel(self, e):
        self._btn_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _on_button_action(self, slot):
        btype = slot.get("type", "")
        log.info("Button '%s' clicked — type=%s", slot.get("name",""), btype)

        import threading, subprocess

        if btype == "GROUP":
            path = slot.get("shortcut_path", "").strip()
            if path:
                threading.Thread(
                    target=lambda: subprocess.Popen(["cmd", "/c", "start", "", path]),
                    daemon=True,
                ).start()
            self.btn_nav_push(slot)
            return

        if btype == "PANEL":
            self.btn_nav_push(slot)
            return

        if btype == "SHORTCUT":
            path = slot.get("shortcut_path", "").strip()
            if path:
                threading.Thread(
                    target=lambda: subprocess.Popen(["cmd", "/c", "start", "", path]),
                    daemon=True,
                ).start()
        elif btype == "REST":
            self._do_rest_action(slot)
        elif btype == "OPENRGB":
            self._do_openrgb_action(slot)
        elif btype == "HOTKEY":
            self._do_hotkey_action(slot)
        elif btype == "AUDIO OUTPUT":
            self._do_audio_output_action(slot)
        elif btype == "STOPWATCH":
            self.app._toggle_stopwatch()
        elif btype == "MEDIA_PREV":
            self._media_prev()
        elif btype == "MEDIA_PLAY":
            self._media_play_pause()
        elif btype == "MEDIA_NEXT":
            self._media_next()
        elif btype == "MEDIA_EJECT":
            self._media_eject()
        elif btype == "EMPTY":
            pass
        elif btype.startswith("PLUGIN:"):
            parts = btype.split(":", 2)
            if len(parts) >= 3:
                pname, cid = parts[1], parts[2]
                try:
                    from plugin_manager import on_tap
                    # Pass type-specific value fields if present (e.g. profile)
                    val = slot.get(cid) or slot.get("value")
                    on_tap(pname, cid, val)
                except Exception as ex:
                    log.warning("PLUGIN tap failed: %s", ex)

    def _do_rest_action(self, slot):
        entity = slot.get("entity_id", "").strip()
        if not entity:
            return
        ha_url = _find_ha_url(self.app.cfg)
        if not ha_url:
            return
        token = self.app.cfg.get("ha_token", "").strip()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{ha_url}/api/services/homeassistant/toggle"
        payload = {"entity_id": entity}

        def _call():
            try:
                import requests as req
                r = req.post(url, json=payload, headers=headers, timeout=5)
                log.info("REST %s -> %s", entity, r.status_code)
            except Exception as ex:
                log.warning("REST action failed: %s", ex)

        import threading
        threading.Thread(target=_call, daemon=True).start()

    def _do_openrgb_action(self, slot):
        profile_name = slot.get("openrgb_profile", "").strip()
        if profile_name:
            from providers.openrgb import _list_profile_files, _profile_name_from_path, _apply_profile
            for fp in _list_profile_files():
                if _profile_name_from_path(fp) == profile_name:
                    import threading
                    threading.Thread(target=_apply_profile, args=(fp, profile_name), daemon=True).start()
                    return
        self._show_openrgb_picker()

    def _show_openrgb_picker(self):
        import math, colorsys, io, base64
        from PIL import Image

        popup = tk.Toplevel(self._win)
        popup.overrideredirect(True)
        popup.configure(bg=BG)
        popup.attributes("-topmost", True)

        WHEEL = 220
        S = WHEEL * 4
        cx = cy = S // 2
        radius_px = S // 2 - 4
        WR = S // 2 - 4  # wheel radius in source pixels

        wheel_img = Image.new("RGB", (S, S), (0, 0, 0))
        for y in range(S):
            for x in range(S):
                dx = x - cx
                dy = y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= radius_px:
                    hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360.0
                    sat = dist / WR
                    r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
                    wheel_img.putpixel((x, y), (int(r * 255), int(g * 255), int(b * 255)))

        wheel_img_small = wheel_img.resize((WHEEL, WHEEL), Image.LANCZOS)
        buf = io.BytesIO()
        wheel_img_small.save(buf, format="PNG")
        photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode("ascii"))

        scale = S / WHEEL
        canvas = tk.Canvas(popup, width=WHEEL, height=WHEEL, bg=BG,
                           highlightthickness=0, bd=0, cursor="crosshair")
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.pack(padx=16, pady=(0, 0))

        sel = canvas.create_oval(0, 0, 0, 0, outline="white", width=2)

        def _pos_from_rgb(r, g, b):
            h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            angle = math.radians(h * 360)
            dist = s * WR / scale
            wx = WHEEL // 2 + dist * math.cos(angle)
            wy = WHEEL // 2 + dist * math.sin(angle)
            return wx, wy

        def _apply_to_openrgb(rr, gg, bb):
            import threading as _th
            _th.Thread(target=self._apply_openrgb_color, args=(rr, gg, bb), daemon=True).start()

        def _set_color_from_rgb(rr, gg, bb):
            wx, wy = _pos_from_rgb(rr, gg, bb)
            hs = 4
            canvas.coords(sel, wx - hs, wy - hs, wx + hs, wy + hs)
            hex_var.set(f"#{rr:02x}{gg:02x}{bb:02x}".upper())
            _apply_to_openrgb(rr, gg, bb)

        def _pick(e):
            x, y = int(e.x * scale), int(e.y * scale)
            if x < 0 or x >= S or y < 0 or y >= S:
                return
            pr, pg, pb = wheel_img.getpixel((x, y))
            if (pr, pg, pb) == (0, 0, 0):
                return
            _set_color_from_rgb(pr, pg, pb)

        canvas.bind("<Button-1>", _pick)

        hex_var = tk.StringVar(value="")
        hex_frame = tk.Frame(popup, bg=BG)
        hex_frame.pack(fill=tk.X, padx=16, pady=(8, 0))
        tk.Label(hex_frame, text="Hex:", bg=BG, fg=FG_DIM,
                 font=FONT_SM).pack(side="left")
        hex_entry = tk.Entry(hex_frame, textvariable=hex_var, width=9,
                             bg=BG, fg=FG, insertbackground=FG,
                             relief="flat", bd=4, highlightthickness=1,
                             highlightcolor=NEON, highlightbackground=BG_CARD,
                             font=("Segoe UI", 14, "bold"))
        hex_entry.pack(side="left", padx=(4, 0))

        def _apply_hex(*_):
            c = hex_var.get().strip().lstrip("#")
            if len(c) != 6:
                return
            try:
                rr = int(c[0:2], 16)
                gg = int(c[2:4], 16)
                bb = int(c[4:6], 16)
            except ValueError:
                return
            _set_color_from_rgb(rr, gg, bb)

        hex_entry.bind("<Return>", _apply_hex)

        btn_frame = tk.Frame(popup, bg=BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=(12, 16))
        from widgets import RoundedButton
        RoundedButton(btn_frame, text="CLOSE", style="sec",
                      command=popup.destroy,
                      padx=6, pady=2, font=FONT_SM).pack(side="right")

        popup.bind("<Escape>", lambda e: popup.destroy())

        # Drag handle bar
        drag_bar = tk.Frame(popup, bg=BG_CARD, height=16, cursor="fleur")
        drag_bar.pack(fill=tk.X, before=canvas)
        drag_data = {"x": 0, "y": 0}
        def _drag_start(e):
            drag_data["x"] = e.x_root
            drag_data["y"] = e.y_root
        def _drag_move(e):
            dx = e.x_root - drag_data["x"]
            dy = e.y_root - drag_data["y"]
            drag_data["x"] = e.x_root
            drag_data["y"] = e.y_root
            popup.geometry(f"+{popup.winfo_x() + dx}+{popup.winfo_y() + dy}")
        drag_bar.bind("<Button-1>", _drag_start)
        drag_bar.bind("<B1-Motion>", _drag_move)

        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        mw = self._win.winfo_x() + self._win.winfo_width() // 2
        mh = self._win.winfo_y() + self._win.winfo_height() // 2
        popup.geometry(f"+{mw - pw // 2}+{mh - ph // 2}")
        popup.grab_set()

    def _apply_openrgb_color(self, r, g, b):
        try:
            from openrgb import OpenRGBClient
            from openrgb.utils import RGBColor
            cl = OpenRGBClient()
            cl.set_color(RGBColor(red=r, green=g, blue=b))
            log.info("OpenRGB colour #%02x%02x%02x applied", r, g, b)
        except ConnectionRefusedError:
            log.warning("[openrgb] SDK server not running — enable it in OpenRGB Settings")
        except Exception as ex:
            log.warning("OpenRGB colour apply failed: %s", ex)

    def _do_hotkey_action(self, slot):
        keys = slot.get("keys", [])
        if not keys:
            return

        title = getattr(self, '_saved_foreground_title', '')
        if not title:
            log.warning("[hotkey] no saved foreground title")
            return

        self._sending_hotkey = True
        self.hide()

        try:
            import pygetwindow as gw
            matches = gw.getWindowsWithTitle(title)
            if not matches:
                log.warning("[hotkey] window '%s' not found", title)
                return

            target = matches[0]
            log.info("[hotkey] activating '%s'", target.title)
            target.activate()
            _time.sleep(0.5)

            # Convert VK codes to hardware scancodes
            scans = []
            for vk in keys:
                scan = user32.MapVirtualKeyW(vk, 0)
                if scan:
                    scans.append(scan)

            if not scans:
                log.warning("[hotkey] no scancodes for vk=%s", keys)
                return

            # Press chord (all down, brief hold, all up)
            for scan in scans:
                _hardware_key(scan, press=True)
                _time.sleep(0.03)
            _time.sleep(0.08)
            for scan in reversed(scans):
                _hardware_key(scan, press=False)
                _time.sleep(0.03)

            log.info("[hotkey] sent via hardware scancodes to '%s'", title)
        except Exception as ex:
            log.error("[hotkey] error: %s", ex)
        finally:
            self._win.after(200, lambda: setattr(self, '_sending_hotkey', False))

    def _do_audio_output_action(self, slot):
        try:
            primary = slot.get("audio_input_device_id", "").strip()
            alt     = slot.get("audio_input_device_id_alt", "").strip()
            log.info("[audio] _do_audio_output_action primary=%s alt=%s", primary[:50] if primary else "", alt[:50] if alt else "")
            if not primary:
                log.warning("[audio] no primary device configured")
                return
            if not alt:
                device_key = primary
            else:
                from win_platform import get_current_default_audio_output
                current = get_current_default_audio_output()
                log.info("[audio] current default=%s", (current or "None")[:50])
                device_key = alt if current and current == primary else primary
            log.info("[audio] switching to %s", device_key[:50])
            import threading
            from win_platform import set_default_audio_output
            def _switch():
                set_default_audio_output(device_key)
                self._win.after(200, self._render_buttons)
            threading.Thread(target=_switch, daemon=True).start()
        except Exception as e:
            log.exception("[audio] _do_audio_output_action failed: %s", e)

    # ── Tile photo cache ──────────────────────────────────────────
    _tile_cache = {}

    def _make_tile_photo(self, mdi_name, fill_hex, ring_hex=None, icon_color=None,
                         app_icon_path=None, icon_scale=0.7):
        """4× supersampled PIL tile → PhotoImage (rounded rect + icon).

        If *app_icon_path* is set and the file exists, the application icon
        extracted via the Windows shell API replaces the MDI vector icon.
        """
        _T, _CR = 40, 8
        S = _T * 2
        R = _CR * 2
        bw = 4

        cache_key = (mdi_name, fill_hex, ring_hex, icon_color, app_icon_path, icon_scale)
        cached = self._tile_cache.get(cache_key)
        if cached is not None:
            return cached

        if fill_hex == "RAINBOW":
            return self._make_rainbow_tile(mdi_name, ring_hex, icon_color, app_icon_path,
                                           icon_scale, _T, _CR, S, R, bw, cache_key)

        frgb = tuple(int(fill_hex[i:i+2], 16) for i in (1, 3, 5))
        brgb = tuple(int(BG[i:i+2], 16) for i in (1, 3, 5))
        if icon_color:
            ic_rgb = icon_color
        else:
            lum = 0.299 * frgb[0] + 0.587 * frgb[1] + 0.114 * frgb[2]
            ic_rgb = (30, 30, 30) if lum > 160 else (224, 224, 224)

        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, S-1, S-1], R, fill=(*frgb, 255))

        # gloss
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S-1, S-1], R, fill=255)
        gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gloss)
        hm = int(S * 0.45)
        for y in range(hm):
            a = int(62 * (1 - y / hm))
            gd.line([(0, y), (S-1, y)], fill=(255, 255, 255, a))
        clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        clipped.paste(gloss, mask=mask)
        img = Image.alpha_composite(img, clipped)

        # Icon — app icon (extracted via PowerShell) or MDI fallback
        icon_drawn = False
        if app_icon_path:
            from win_platform import _extract_via_ps
            app_img = _extract_via_ps(app_icon_path, size=_T)
            if app_img:
                bbox = app_img.getbbox()
                if bbox:
                    app_img = app_img.crop(bbox)
                app_img = app_img.resize((_T, _T), Image.LANCZOS)
                app_img_s = app_img.resize((S, S), Image.LANCZOS)
                ox = (S - app_img_s.width) // 2
                oy = (S - app_img_s.height) // 2
                layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                layer.paste(app_img_s, (ox, oy), app_img_s)
                # Clip to rounded rect so ring/rounded corners show through
                mask_s = Image.new("L", (S, S), 0)
                ImageDraw.Draw(mask_s).rounded_rectangle((0, 0, S-1, S-1), R, fill=255)
                clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                clipped.paste(layer, mask=mask_s)
                img = Image.alpha_composite(img, clipped)
                icon_drawn = True
        if not icon_drawn:
            try:
                icon = mdi_icons.render(mdi_name, int(S * icon_scale), ic_rgb)
                if icon:
                    ox = (S - icon.width) // 2
                    oy = (S - icon.height) // 2
                    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                    layer.paste(icon, (ox, oy), icon)
                    img = Image.alpha_composite(img, layer)
            except Exception as e:
                log.warning("Icon render(%s) failed: %s", mdi_name, e)

        # Ring border on top of everything
        if ring_hex:
            rrgb = tuple(int(ring_hex[i:i+2], 16) for i in (1, 3, 5))
            ring_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            r_draw = ImageDraw.Draw(ring_img)
            r_draw.rounded_rectangle([0, 0, S-1, S-1], R, fill=(*rrgb, 255))
            r_draw.rounded_rectangle([bw, bw, S-1-bw, S-1-bw], max(0, R-bw), fill=(0, 0, 0, 0))
            img = Image.alpha_composite(img, ring_img)

        img = img.resize((_T, _T), Image.LANCZOS)
        base = Image.new("RGB", (_T, _T), brgb)
        base.paste(img, mask=img.split()[3])
        photo = ImageTk.PhotoImage(base)
        self._tile_cache[cache_key] = photo
        return photo

    def _make_rainbow_tile(self, mdi_name, ring_hex, icon_color, app_icon_path,
                           icon_scale, _T, _CR, S, R, bw, cache_key):
        brgb = tuple(int(BG[i:i+2], 16) for i in (1, 3, 5))
        if icon_color:
            ic_rgb = icon_color
        else:
            ic_rgb = (224, 224, 224)
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        import math, colorsys
        _cx = _cy = S // 2
        for _py in range(S):
            for _px in range(S):
                _dx = _px - _cx
                _dy = _py - _cy
                _hue = (math.degrees(math.atan2(_dy, _dx)) % 360) / 360.0
                _rr, _gg, _bb = colorsys.hsv_to_rgb(_hue, 1.0, 1.0)
                img.putpixel((_px, _py), (int(_rr*255), int(_gg*255), int(_bb*255)))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S-1, S-1], R, fill=255)
        _clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        _clipped.paste(img, mask=mask)
        img = _clipped
        gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gloss)
        hm = int(S * 0.45)
        for y in range(hm):
            a = int(62 * (1 - y / hm))
            gd.line([(0, y), (S-1, y)], fill=(255, 255, 255, a))
        clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        clipped.paste(gloss, mask=mask)
        img = Image.alpha_composite(img, clipped)
        icon_drawn = False
        if app_icon_path:
            from win_platform import _extract_via_ps
            app_img = _extract_via_ps(app_icon_path, size=_T)
            if app_img:
                bbox = app_img.getbbox()
                if bbox:
                    app_img = app_img.crop(bbox)
                app_img = app_img.resize((_T, _T), Image.LANCZOS)
                app_img_s = app_img.resize((S, S), Image.LANCZOS)
                ox = (S - app_img_s.width) // 2
                oy = (S - app_img_s.height) // 2
                layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                layer.paste(app_img_s, (ox, oy), app_img_s)
                mask_s = Image.new("L", (S, S), 0)
                ImageDraw.Draw(mask_s).rounded_rectangle((0, 0, S-1, S-1), R, fill=255)
                clipped2 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                clipped2.paste(layer, mask=mask_s)
                img = Image.alpha_composite(img, clipped2)
                icon_drawn = True
        if not icon_drawn:
            try:
                icon = mdi_icons.render(mdi_name, int(S * icon_scale), ic_rgb)
                if icon:
                    ox = (S - icon.width) // 2
                    oy = (S - icon.height) // 2
                    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                    layer.paste(icon, (ox, oy), icon)
                    img = Image.alpha_composite(img, layer)
            except Exception as e:
                log.warning("Icon render(%s) failed: %s", mdi_name, e)
        if ring_hex:
            rrgb = tuple(int(ring_hex[i:i+2], 16) for i in (1, 3, 5))
            ring_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            r_draw = ImageDraw.Draw(ring_img)
            r_draw.rounded_rectangle([0, 0, S-1, S-1], R, fill=(*rrgb, 255))
            r_draw.rounded_rectangle([bw, bw, S-1-bw, S-1-bw], max(0, R-bw), fill=(0, 0, 0, 0))
            img = Image.alpha_composite(img, ring_img)
        img = img.resize((_T, _T), Image.LANCZOS)
        base = Image.new("RGB", (_T, _T), brgb)
        base.paste(img, mask=img.split()[3])
        photo = ImageTk.PhotoImage(base)
        self._tile_cache[cache_key] = photo
        return photo

    def _make_tile_set(self, mdi_name, icon_scale=0.7):
        """Return [normal, hover, active, active-hover] PhotoImages."""
        col_normal = BG_CARD
        col_hover = "#353535"
        photos = [
            self._make_tile_photo(mdi_name, col_normal, icon_scale=icon_scale),
            self._make_tile_photo(mdi_name, col_hover, icon_scale=icon_scale),
            self._make_tile_photo(mdi_name, col_normal, NEON, (72, 178, 233), icon_scale=icon_scale),
            self._make_tile_photo(mdi_name, col_hover, NEON, (72, 178, 233), icon_scale=icon_scale),
        ]
        self._tile_refs.extend(photos)
        return photos

    def _on_brightness_change(self):
        if self.app:
            self.app._set_brightness(self._brightness_var.get())

    def _on_volume_change(self):
        if not getattr(self, "_volume_enabled", False):
            return
        try:
            import win_volume
            win_volume.set_active_app_volume(self._volume_var.get())
        except Exception:
            pass

    def _refresh_volume_ui(self):
        try:
            import win_volume
            state = win_volume.get_active_app_state()
        except Exception:
            state = {"app": None, "volume": None}
        vol = state.get("volume")
        app = state.get("app")
        if isinstance(vol, int):
            self._volume_enabled = True
            if self._volume_var.get() != vol:
                self._volume_var.set(vol)
            self._lbl_volume_app.config(text=app or "Application", fg=FG_DIM)
        else:
            self._volume_enabled = False
            label = (f"{app} — no audio") if app else "No audio session"
            self._lbl_volume_app.config(text=label, fg=FG_DIM)

    def _refresh_mixer_ui(self):
        """Refresh per-app volume rows from win_volume.list_sessions()."""
        if not getattr(self, "_mixer_enabled", False):
            return
        frame = getattr(self, "_mixer_frame", None)
        if frame is None:
            return
        try:
            import win_volume
            sessions = win_volume.list_sessions()
        except Exception:
            sessions = []
        key = tuple((s.get("pid"), s.get("volume"), s.get("name")) for s in sessions)
        if key == self._mixer_sig:
            return
        self._mixer_sig = key
        for w in frame.winfo_children():
            w.destroy()
        self._mixer_rows = []

        _LABEL_H, _SLIDER_H = 14, 26
        y = 0
        for s in sessions[:10]:
            pid = s.get("pid")
            name = s.get("name") or "Application"
            vol = s.get("volume")
            var = tk.IntVar(value=vol if isinstance(vol, int) else 0)
            lbl = tk.Label(frame, text=name, font=("Segoe UI", 8),
                           fg=FG_DIM, bg=BG, anchor="w")
            lbl.place(x=0, y=y, width=180, height=_LABEL_H)
            y += _LABEL_H
            sl = StepSlider(frame, list(range(101)), var,
                            on_change=lambda p=pid, v=var: self._set_mixer_volume(p, v.get()))
            sl.place(x=0, y=y, width=180, height=_SLIDER_H)
            y += _SLIDER_H + 6
            self._mixer_rows.append({"pid": pid, "var": var, "slider": sl, "label": lbl})

        if not self._mixer_rows:
            empty = tk.Label(frame, text="No apps playing", font=("Segoe UI", 8),
                             fg=FG_DIM, bg=BG, anchor="w")
            empty.place(x=0, y=0, width=180, height=_LABEL_H)
            y = _LABEL_H + 8

        self._mixer_h = y
        self._reflow_panel()

    def _set_mixer_volume(self, pid, value):
        try:
            import win_volume
            win_volume.set_session_volume(pid, max(0, min(100, value)))
        except Exception:
            pass

    # ── Media control helpers ───────────────────────────────────────
    @staticmethod
    def _send_media_key(vk):
        _EXTENDED = 0x0001
        _KEYUP    = 0x0002
        ctypes.windll.user32.keybd_event(vk, 0, _EXTENDED, 0)
        ctypes.windll.user32.keybd_event(vk, 0, _EXTENDED | _KEYUP, 0)

    def _media_prev(self):
        self._send_media_key(0xB1)  # VK_MEDIA_PREV_TRACK

    def _media_play_pause(self):
        self._send_media_key(0xB3)  # VK_MEDIA_PLAY_PAUSE

    def _media_next(self):
        self._send_media_key(0xB0)  # VK_MEDIA_NEXT_TRACK

    def _media_eject(self):
        if not self.app:
            return
        path = self.app.cfg.get("media_player_path", "").strip()
        if not path:
            return
        import threading, subprocess
        threading.Thread(target=lambda: subprocess.Popen([path], shell=False), daemon=True).start()

    def _build_tiles(self):
        self._tile_refs = []
        _W = 190
        _X = (self.W - _W) // 2
        _T, _GAP = 40, 10
        _TOTAL = 4 * _T + 3 * _GAP

        # Widgets created here; _reflow_panel places them and sets height.
        self._sep_sliders = tk.Frame(self._win, bg=BG_CARD, height=1)

        self._lbl_volume_title = tk.Label(
            self._win, text="App Volume", font=("Segoe UI", 10),
            fg=NEON, bg=BG, anchor="w")
        self._lbl_volume_app = tk.Label(
            self._win, text="No audio session", font=("Segoe UI", 8),
            fg=FG_DIM, bg=BG, anchor="w")
        self._volume_enabled = False
        self._volume_var = tk.IntVar(value=0)
        self._slider_volume = StepSlider(
            self._win, list(range(101)), self._volume_var,
            on_change=self._on_volume_change,
        )

        self._lbl_brightness_title = tk.Label(
            self._win, text="Display Brightness", font=("Segoe UI", 10),
            fg=NEON, bg=BG, anchor="w")
        self._brightness_var = tk.IntVar(value=self.app.cfg.get("brightness", DEFAULT_BRIGHTNESS))
        self._slider_brightness = StepSlider(
            self._win, list(range(5)), self._brightness_var,
            on_change=self._on_brightness_change,
        )

        self._mixer_enabled = False
        self._mixer_h = 0
        self._mixer_sig = None
        self._mixer_rows = []
        self._lbl_mixer_title = tk.Label(
            self._win, text="App Mixer", font=("Segoe UI", 10),
            fg=NEON, bg=BG, anchor="w")
        self._mixer_frame = tk.Frame(self._win, bg=BG)

        self._sep_utility = tk.Frame(self._win, bg=BG_CARD, height=1)
        self._utility_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        self._utility_frame.pack_propagate(False)
        self._utility_tile_refs = []
        self._render_utility_row()

        self._sep_core = tk.Frame(self._win, bg=BG_CARD, height=1)
        self._core_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        self._core_frame.pack_propagate(False)
        _tile_frame = self._core_frame

        self._pc_display_on = self.app.cfg.get("pc_stats_manual", False)
        self._overlay_on = False
        self._mic_muted = False

        # ── Pressed tile helpers ──
        _prs_fill = self._adjust_hex(BG_CARD, -20)

        # ── Tile 0: PC stats display toggle ──
        t0 = self._make_tile_set("monitor", icon_scale=0.52)
        prs0_off = self._make_tile_photo("monitor", _prs_fill, icon_scale=0.52)
        prs0_on  = self._make_tile_photo("monitor", _prs_fill, NEON, (72, 178, 233), icon_scale=0.52)
        self._tile_refs.extend([prs0_off, prs0_on])
        self._btn_display = tk.Label(_tile_frame, image=t0[0], bg=BG, cursor="hand2",
                                     padx=0, pady=0, borderwidth=0)
        self._btn_display.place(x=0, y=0)

        def _enter0(e):
            self._btn_display.config(image=t0[3] if self._pc_display_on else t0[1])
        def _leave0(e):
            self._btn_display.config(image=t0[2] if self._pc_display_on else t0[0])
        def _press0(e):
            self._btn_display.config(image=prs0_on if self._pc_display_on else prs0_off)
        def _release0(e):
            self._pc_display_on = not self._pc_display_on
            self._btn_display.config(image=t0[2] if self._pc_display_on else t0[0])
            self.app._toggle_pc_stats(self._pc_display_on)
        self._btn_display.bind("<Enter>", _enter0)
        self._btn_display.bind("<Leave>", _leave0)
        self._btn_display.bind("<ButtonPress-1>", _press0)
        self._btn_display.bind("<ButtonRelease-1>", _release0)

        if self._pc_display_on:
            self.app._toggle_pc_stats(True)

        # ── Tile 1: PC stats overlay toggle ──
        t1 = self._make_tile_set("speedometer", icon_scale=0.52)
        self._ov_tiles = t1
        prs1_off = self._make_tile_photo("speedometer", _prs_fill, icon_scale=0.52)
        prs1_on  = self._make_tile_photo("speedometer", _prs_fill, NEON, (72, 178, 233), icon_scale=0.52)
        self._tile_refs.extend([prs1_off, prs1_on])
        self._btn_overlay = tk.Label(_tile_frame, image=t1[0], bg=BG, cursor="hand2",
                                     padx=0, pady=0, borderwidth=0)
        self._btn_overlay.place(x=1 * (_T + _GAP), y=0)

        def _enter1(e):
            self._btn_overlay.config(image=t1[3] if self._overlay_on else t1[1])
        def _leave1(e):
            self._btn_overlay.config(image=t1[2] if self._overlay_on else t1[0])
        def _press1(e):
            self._btn_overlay.config(image=prs1_on if self._overlay_on else prs1_off)
        def _release1(e):
            self._overlay_on = not self._overlay_on
            self._btn_overlay.config(image=t1[2] if self._overlay_on else t1[0])
            self.app._toggle_overlay(self._overlay_on)
        self._btn_overlay.bind("<Enter>", _enter1)
        self._btn_overlay.bind("<Leave>", _leave1)
        self._btn_overlay.bind("<ButtonPress-1>", _press1)
        self._btn_overlay.bind("<ButtonRelease-1>", _release1)

        # ── Tile 2: Microphone mute toggle ──
        _mic_unmuted = self._make_tile_photo("microphone", BG_CARD, icon_scale=0.52)
        _mic_unmuted_hov = self._make_tile_photo("microphone", "#353535", icon_scale=0.52)
        _mic_muted_ph = self._make_tile_photo("microphone-off", BG_CARD, NEON, (72, 178, 233), icon_scale=0.52)
        _mic_muted_hov = self._make_tile_photo("microphone-off", "#353535", NEON, (72, 178, 233), icon_scale=0.52)
        _mic_prs_unmuted = self._make_tile_photo("microphone", _prs_fill, icon_scale=0.52)
        _mic_prs_muted = self._make_tile_photo("microphone-off", _prs_fill, NEON, (72, 178, 233), icon_scale=0.52)
        self._tile_refs.extend([_mic_unmuted, _mic_unmuted_hov, _mic_muted_ph, _mic_muted_hov,
                                _mic_prs_unmuted, _mic_prs_muted])
        self._btn_mic = tk.Label(_tile_frame, image=_mic_unmuted, bg=BG, cursor="hand2",
                                 padx=0, pady=0, borderwidth=0)
        self._btn_mic.place(x=2 * (_T + _GAP), y=0)

        def _enter_mic(e):
            self._btn_mic.config(image=_mic_muted_hov if self._mic_muted else _mic_unmuted_hov)
        def _leave_mic(e):
            self._btn_mic.config(image=_mic_muted_ph if self._mic_muted else _mic_unmuted)
        def _press_mic(e):
            self._btn_mic.config(image=_mic_prs_muted if self._mic_muted else _mic_prs_unmuted)
        def _release_mic(e):
            from win_platform import toggle_mic_mute
            result = toggle_mic_mute()
            if result is not None:
                self._mic_muted = result
            self._btn_mic.config(image=_mic_muted_ph if self._mic_muted else _mic_unmuted)
        self._btn_mic.bind("<Enter>", _enter_mic)
        self._btn_mic.bind("<Leave>", _leave_mic)
        self._btn_mic.bind("<ButtonPress-1>", _press_mic)
        self._btn_mic.bind("<ButtonRelease-1>", _release_mic)

        # ── Tile 3: Settings ──
        t3 = self._make_tile_set("cog", icon_scale=0.52)
        prs3 = self._make_tile_photo("cog", _prs_fill, icon_scale=0.52)
        self._tile_refs.append(prs3)
        self._btn_settings = tk.Label(_tile_frame, image=t3[0], bg=BG, cursor="hand2",
                                       padx=0, pady=0, borderwidth=0)
        self._btn_settings.place(x=3 * (_T + _GAP), y=0)
        self._btn_settings.bind("<Enter>", lambda e: self._btn_settings.config(image=t3[1]))
        self._btn_settings.bind("<Leave>", lambda e: self._btn_settings.config(image=t3[0]))
        self._btn_settings.bind("<ButtonPress-1>", lambda e: self._btn_settings.config(image=prs3))
        self._btn_settings.bind("<ButtonRelease-1>", lambda e: (
            self._btn_settings.config(image=t3[0]),
            self.app._open_settings(),
        ))

        # ── TEMP: hero overlay test button ──
        self._hero_btn = tk.Label(self._win, text="SHOW HERO", bg=NEON, fg=BG,
                            font=("Segoe UI", 7, "bold"), cursor="hand2")
        self._hero_btn.bind("<Button-1>", lambda e: self.app._overlays.hero(
            title="SOL",
            subtitle="Population: 24.3 Billion",
            fields=[
                ("Economy", "High Tech / Refinery"),
                ("Government", "Democracy"),
                ("Security", "High"),
                ("Allegiance", "Federation"),
            ],
            duration=6,
        ))

    def _on_gauge_click(self, e):
        if not self._overlay_on:
            self._overlay_on = True
            self._btn_overlay.config(image=self._ov_tiles[2])
            self.app._toggle_overlay(True)
        if not self._pin_pinned:
            self.hide()

    def _update_status(self):
        port = self.app._port
        self._lbl_port.config(text=port if port else "Offline")

        t = _time.localtime()
        self._lbl_time.config(text=f"{t.tm_hour:02d}:{t.tm_min:02d}")

        for p in self.app._providers:
            if hasattr(p, "snapshot"):
                try:
                    s = p.snapshot()
                    self._gauge_cpu.set_value(s.cpu_temp)
                    self._gauge_gpu.set_value(s.gpu_temp)
                    self._gauge_fps.set_value(s.fps)
                except Exception:
                    pass
                break

        if self._visible:
            self._refresh_volume_ui()
            self._refresh_mixer_ui()

        self._win.after(1000, self._update_status)

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def show(self):
        # _saved_foreground_hwnd was already set by the hotkey listener or
        # tray click BEFORE the panel appeared — don't re-fetch it.
        if not getattr(self, '_saved_foreground_hwnd', 0) or not user32.IsWindow(self._saved_foreground_hwnd):
            self._saved_foreground_hwnd = user32.GetForegroundWindow()
        if self._saved_foreground_hwnd:
            buf = ctypes.create_unicode_buffer(500)
            user32.GetWindowTextW(self._saved_foreground_hwnd, buf, 500)
            self._saved_foreground_title = buf.value
        else:
            self._saved_foreground_title = ""
        self._reflow_panel()
        self._win.deiconify()
        self._win.update_idletasks()
        self._apply_region()
        self._win.lift()
        self._win.focus_force()
        self._visible = True
        self._refresh_volume_ui()
        self._refresh_mixer_ui()
        # Snap mouse cursor to center of panel
        px = self._win.winfo_x()
        py = self._win.winfo_y()
        pw = self._win.winfo_width()
        ph = self._win.winfo_height()
        ctypes.windll.user32.SetCursorPos(px + pw // 2, py + ph // 2)

    def hide(self):
        if self._sticky_after_id:
            try:
                self._win.after_cancel(self._sticky_after_id)
            except Exception:
                pass
            self._sticky_after_id = None
            self._sticky_leave_active = False
        self._win.withdraw()
        self._visible = False

    def _on_power(self, e):
        if self._pin_pinned:
            self._pin_pinned = False
            self._win.attributes("-topmost", False)
            icon = mdi_icons.render("pin-outline", 16, (180, 180, 180))
            photo = ImageTk.PhotoImage(icon)
            self._pin_btn.config(image=photo)
            self._pin_btn.image = photo
            self._cfg["panel_pin"] = False
            from config import save_config
            save_config(self._cfg)
        self.hide()

    def _on_focusout(self, e):
        if self._sending_hotkey or self._pin_pinned:
            return
        if self._is_fullscreen_app():
            self._start_sticky_leave()
        else:
            self.hide()

    def _is_fullscreen_app(self):
        hwnd = self._saved_foreground_hwnd
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        try:
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            sx = user32.GetSystemMetrics(0)
            sy = user32.GetSystemMetrics(1)
            return (rect.left <= 0 and rect.top <= 0
                    and rect.right >= sx and rect.bottom >= sy)
        except Exception:
            return False

    def _start_sticky_leave(self):
        if self._sticky_leave_active:
            return
        self._sticky_leave_active = True

        def _check():
            if not self._visible:
                self._sticky_leave_active = False
                return
            try:
                pt = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                px = self._win.winfo_x()
                py = self._win.winfo_y()
                pw = self._win.winfo_width()
                ph = self._win.winfo_height()
                inside = (px <= pt.x <= px + pw and py <= pt.y <= py + ph)
                if inside:
                    self._sticky_after_id = self._win.after(100, _check)
                else:
                    self._sticky_leave_active = False
                    self.hide()
            except Exception:
                self._sticky_leave_active = False
                self.hide()

        self._sticky_after_id = self._win.after(2000, _check)

    def _on_focusin(self, e=None):
        if self._sticky_leave_active:
            self._sticky_leave_active = False
            if self._sticky_after_id:
                try:
                    self._win.after_cancel(self._sticky_after_id)
                except Exception:
                    pass
                self._sticky_after_id = None

    def set_alarm_indicator(self, active):
        self.set_status_icon("alarm", active)

    def set_status_icon(self, name, active):
        label = self._status_icons.get(name)
        if label is None:
            return
        if active:
            label.pack(side=tk.LEFT, padx=(0, 4))
        else:
            label.pack_forget()

    def register_status_icon(self, name, mdi_name, size=14, color=(255, 255, 255)):
        if name in self._status_icons:
            return self._status_icons[name]
        icon = ImageTk.PhotoImage(mdi_icons.render(mdi_name, size, color))
        label = tk.Label(
            self._status_bar, image=icon, bg=BG_CARD, padx=0, pady=0)
        label.image = icon
        label.pack_forget()
        self._status_icons[name] = label
        return label

    def close(self):
        self._win.destroy()
