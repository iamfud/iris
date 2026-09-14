"""Iris — iPhone-shaped overlay main window."""

import logging
import threading
import time as _time
import tkinter as tk
import ctypes
import ctypes.wintypes

from PIL import Image, ImageDraw, ImageTk

from constants import BG, BG_CARD, DEFAULT_BRIGHTNESS, FG, FG_DIM, NEON, BUTTON, FONT_SM
from widgets import CircularGauge, RoundedButton, StepSlider, ToolTip
import mdi_icons
import colour_picker

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


def _apply_window_style(hwnd, alpha=0.9, corner_pref=3):
    try:
        user32 = ctypes.windll.user32
        root_parent = user32.GetAncestor(hwnd, 2) or user32.GetParent(hwnd) or hwnd
        dwm = ctypes.windll.dwmapi
        for h in {root_parent, hwnd}:
            dwm.DwmSetWindowAttribute(
                h, 33,
                ctypes.byref(ctypes.c_int(corner_pref)),
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


def _get_foreground_app_name(saved_hwnd=None):
    """Return the sanitised process name of the current foreground window (excluding Iris and system shells).

    Used to tag screenshot filenames so the Library can group captures by app.
    Falls back to ``"desktop"`` if the foreground window cannot be resolved.
    """
    import re as _re, os as _os
    try:
        import psutil
        pid = ctypes.c_ulong()
        my_pid = _os.getpid()

        def _is_shell_window(h):
            if not h:
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cls_buf, 256)
            cls_name = cls_buf.value
            if cls_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"):
                return True
            return False

        def _resolve_name(h):
            if not h or not user32.IsWindow(h):
                return None
            if _is_shell_window(h):
                return None
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if not pid.value or pid.value == my_pid:
                return None
            try:
                proc = psutil.Process(pid.value)
                pname = proc.name().lower()
                if pname in ("python.exe", "pythonw.exe", "iris.exe", "pywebview.exe", "explorer.exe"):
                    return None
                raw = _re.sub(r'\.exe$', '', pname, flags=_re.IGNORECASE).lower()
                raw = _re.sub(r'[^a-z0-9]+', '_', raw).strip('_')
                return raw or None
            except Exception:
                return None

        # 1. Try saved_hwnd first (if valid app)
        if saved_hwnd:
            name = _resolve_name(saved_hwnd)
            if name:
                return name

        # 2. Try current foreground window
        fg = user32.GetForegroundWindow()
        if fg and fg != saved_hwnd:
            name = _resolve_name(fg)
            if name:
                return name

        # 3. Fallback: scan top visible windows to find the first non-Iris, non-shell application
        top_name = None
        def _enum_cb(h, _):
            nonlocal top_name
            if top_name:
                return False
            if not user32.IsWindowVisible(h):
                return True
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rect))
            if (rect.right - rect.left < 60) or (rect.bottom - rect.top < 60):
                return True
            n = _resolve_name(h)
            if n:
                top_name = n
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
        return top_name or "desktop"
    except Exception:
        return "desktop"


class MainWindow:
    W = 220
    H = 568
    RADIUS = 24
    ALPHA = 0.98
    PAGE_H = 150  # one button page (4x3 grid) = the track's page size

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
        self._picker_active = False
        self._picker_session = None
        self._picker_hex_lbl = None
        self._picker_rgb_lbl = None
        self._picker_capture_btn = None
        self._picked_hex = None
        # Screenshot state
        self._screenshot_active  = False
        self._screenshot_slot    = {}
        self._screenshot_img     = None   # PIL Image of last capture
        self._screenshot_b64     = None   # JPEG b64 for phone delivery
        self._screenshot_w       = 0
        self._screenshot_h       = 0
        self._screenshot_ts      = 0.0
        self._screenshot_lbl     = None   # preview tk.Label in dialog
        self._screenshot_open_btn= None   # open in browser overlay button
        self._screenshot_monitor = 0      # selected monitor index
        self._screenshot_fname   = None   # last saved png filename
        self._capture_toolbar    = None   # transient top-centre capture toolbar

        self._win = tk.Toplevel(root)
        self._win.withdraw()
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

    def _get_theme_colors(self):
        """Return (accent_rgb, neon_rgb, accent_hex, neon_hex, theme_bg_hex, theme_dark_hex) exactly matching web portal theme engine."""
        theme = {}
        try:
            from config import load_config
            fresh_cfg = load_config()
            if isinstance(fresh_cfg, dict) and "theme" in fresh_cfg:
                theme = fresh_cfg.get("theme") or {}
        except Exception:
            pass
        if not theme and hasattr(self, "app") and getattr(self.app, "cfg", None):
            theme = self.app.cfg.get("theme") or {}
        if not theme and hasattr(self, "_cfg") and isinstance(self._cfg, dict):
            theme = self._cfg.get("theme") or {}

        mode = theme.get("mode", "iris") if isinstance(theme, dict) else "iris"
        if mode == "monochrome":
            neon_hex = "#FFFFFF"
            accent_hex = "#666666"
        elif mode == "custom":
            neon_hex = theme.get("neon") or "#48B2E9"
            accent_hex = theme.get("accent") or "#B23AF6"
        else:  # "iris"
            neon_hex = "#48B2E9"
            accent_hex = "#B23AF6"

        def _hex_to_rgb(h, def_rgb):
            try:
                h = str(h).lstrip("#")
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except Exception:
                return def_rgb

        neon_rgb = _hex_to_rgb(neon_hex, (72, 178, 233))
        accent_rgb = _hex_to_rgb(accent_hex, (178, 58, 246))

        # Check perceived luminance of both Neon 1 and Neon 2
        lum1 = (0.299 * neon_rgb[0] + 0.587 * neon_rgb[1] + 0.114 * neon_rgb[2]) / 255.0
        lum2 = (0.299 * accent_rgb[0] + 0.587 * accent_rgb[1] + 0.114 * accent_rgb[2]) / 255.0
        neon_text_hex = accent_hex if lum1 < 0.42 else neon_hex
        neon_text_rgb = accent_rgb if lum1 < 0.42 else neon_rgb
        bright_neon_hex = neon_hex if lum1 >= lum2 else accent_hex
        bright_neon_rgb = neon_rgb if lum1 >= lum2 else accent_rgb

        r1, g1, b1 = neon_rgb
        bg_r = max(0, min(255, int(8 + r1 * 0.05)))
        bg_g = max(0, min(255, int(8 + g1 * 0.05)))
        bg_b = max(0, min(255, int(10 + b1 * 0.05)))
        dark_r = max(0, bg_r - 4)
        dark_g = max(0, bg_g - 4)
        dark_b = max(0, bg_b - 4)
        theme_bg_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
        theme_dark_hex = f"#{dark_r:02x}{dark_g:02x}{dark_b:02x}"

        return accent_rgb, neon_rgb, accent_hex, neon_hex, theme_bg_hex, theme_dark_hex, neon_text_hex, neon_text_rgb, bright_neon_hex, bright_neon_rgb

    def _generate_webportal_bg(self, W, H):
        """Generate the exact webportal background (top muted Neon 1 radial glow over dark Neon 1 gradient)."""
        from PIL import Image, ImageDraw, ImageFilter
        W = max(1, int(W))
        H = max(1, int(H))

        neon_rgb = self._get_theme_colors()[1]
        r1, g1, b1 = neon_rgb
        # Muted Neon 1 background tint
        bg_r = max(0, min(255, int(8 + r1 * 0.05)))
        bg_g = max(0, min(255, int(8 + g1 * 0.05)))
        bg_b = max(0, min(255, int(10 + b1 * 0.05)))
        dark_r = max(0, bg_r - 4)
        dark_g = max(0, bg_g - 4)
        dark_b = max(0, bg_b - 4)

        cache_key = (W, H, r1, g1, b1, bg_r, bg_g, bg_b, dark_r, dark_g, dark_b)
        global _BG_IMAGE_CACHE
        if "_BG_IMAGE_CACHE" not in globals():
            _BG_IMAGE_CACHE = {}
        if cache_key in _BG_IMAGE_CACHE:
            return _BG_IMAGE_CACHE[cache_key]

        img = Image.new("RGBA", (W, H))
        draw = ImageDraw.Draw(img)
        c1 = (dark_r, dark_g, dark_b)
        c2 = (bg_r, bg_g, bg_b)

        for y in range(H):
            t = y / max(1, H - 1)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

        # Fast vector glow with native GaussianBlur (< 2ms vs 350ms pixel loop)
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow_layer)
        cx = W / 2.0
        cy = -0.10 * H
        rx = (W * 1.20) / 2.0
        ry = (H * 0.80) / 2.0
        gdraw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(*neon_rgb, 26))
        gdraw.ellipse([cx - rx * 0.6, cy - ry * 0.6, cx + rx * 0.6, cy + ry * 0.6], fill=(*neon_rgb, 20))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=int(W * 0.12)))

        final_img = Image.alpha_composite(img, glow_layer).convert("RGB")
        _BG_IMAGE_CACHE[cache_key] = final_img
        return final_img

    def _update_bg_image(self, w, h):
        try:
            if not hasattr(self, "_bg_canvas"):
                return
            bg_img = self._generate_webportal_bg(w, h)
            self._bg_photo = ImageTk.PhotoImage(bg_img)
            self._bg_canvas.delete("all")
            self._bg_canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")
        except Exception as e:
            log.warning("Failed to render background gradient: %s", e)

    def reload_theme(self, force=False):
        """Re-apply active theme colors across background, gauges, and sliders."""
        try:
            theme_cfg = self._cfg.get("theme", {}) if hasattr(self, "_cfg") and isinstance(self._cfg, dict) else {}
            theme_sig = (theme_cfg.get("mode"), theme_cfg.get("accent"), theme_cfg.get("neon"), self.W, getattr(self, "_panel_h", self.H))
            if not force and getattr(self, "_applied_theme_sig", None) == theme_sig:
                return
            self._applied_theme_sig = theme_sig

            accent_rgb, neon_rgb, accent_hex, neon_hex, theme_bg, theme_dark, neon_text_hex, neon_text_rgb = self._get_theme_colors()[:8]
            self._win.configure(bg=theme_bg)
            if hasattr(self, "_bg_canvas"):
                self._bg_canvas.configure(bg=theme_bg)
            self._update_bg_image(self.W, getattr(self, "_panel_h", self.H))

            # Status bar & Header
            for w in (getattr(self, "_sb", None), getattr(self, "_lbl_port", None), getattr(self, "_pin_btn", None), getattr(self, "_status_bar", None), getattr(self, "_lbl_time", None)):
                if w:
                    try: w.configure(bg=theme_dark)
                    except Exception: pass

            # Gauges
            gf = getattr(self, "_gauge_frame", None)
            if gf:
                try: gf.configure(bg=theme_bg)
                except Exception: pass
            for g in (getattr(self, "_gauge_cpu", None), getattr(self, "_gauge_gpu", None), getattr(self, "_gauge_fps", None)):
                if g and hasattr(g, "set_theme_colors"):
                    g.set_theme_colors(accent_rgb, neon_rgb, bg=theme_bg)

            # Sliders
            for sl in (getattr(self, "_slider_volume", None), getattr(self, "_slider_master", None), getattr(self, "_slider_brightness", None)):
                if sl and hasattr(sl, "set_theme_colors"):
                    sl.set_theme_colors(neon_rgb, accent_rgb, bg=theme_bg)

            # Titles / labels (always pure white)
            for lbl in (getattr(self, "_lbl_volume_title", None), getattr(self, "_lbl_master_title", None), getattr(self, "_lbl_brightness_title", None)):
                if lbl:
                    try: lbl.configure(fg="#FFFFFF", bg=theme_bg)
                    except Exception: pass

            # Button containers
            for bf in (getattr(self, "_btn_panel", None), getattr(self, "_btn_canvas", None), getattr(self, "_btn_inner", None),
                       getattr(self, "_utility_frame", None), getattr(self, "_core_frame", None), getattr(self, "_mixer_frame", None)):
                if bf:
                    try: bf.configure(bg=theme_bg)
                    except Exception: pass

            if getattr(self, "_pin_pinned", False):
                icon = mdi_icons.render("pin", 16, neon_text_rgb)
                photo = ImageTk.PhotoImage(icon)
                self._pin_btn.config(image=photo)
                self._pin_btn.image = photo
            self._mixer_sig = None
            self._refresh_mixer_ui()
            self._tile_cache.clear()
            self._build_tiles()
            self._render_utility_row()
            self._render_core_row()
            self._render_buttons()
            self._reflow_panel()

            toolbar = getattr(self, "_capture_toolbar", None)
            if toolbar is not None:
                try:
                    toolbar.refresh_theme()
                except Exception as ex:
                    log.warning("reload_theme toolbar refresh error: %s", ex)
        except Exception as e:
            log.warning("reload_theme error: %s", e)

    def _build_ui(self):
        self._bg_canvas = tk.Canvas(self._win, width=self.W, height=self.H, bg=BG, highlightthickness=0, bd=0)
        self._bg_canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self._update_bg_image(self.W, self.H)

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

        vals = self._get_theme_colors()
        accent_rgb, neon_rgb, theme_bg = vals[0], vals[1], vals[4]
        self._gauge_cpu = CircularGauge(gf, "CPU", 100, "\u00b0", size=gauge_size, bg=theme_bg)
        self._gauge_cpu.set_theme_colors(accent_rgb, neon_rgb, bg=theme_bg)
        self._gauge_cpu.grid(row=0, column=0)

        self._gauge_gpu = CircularGauge(gf, "GPU", 100, "\u00b0", size=gauge_size, bg=theme_bg)
        self._gauge_gpu.set_theme_colors(accent_rgb, neon_rgb, bg=theme_bg)
        self._gauge_gpu.grid(row=0, column=1)

        self._gauge_fps = CircularGauge(gf, "FPS", 240, "", size=gauge_size, bg=theme_bg)
        self._gauge_fps.set_theme_colors(accent_rgb, neon_rgb, bg=theme_bg)
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
        self._ctx_menu.add_command(label="Quick Actions Toolbar", command=lambda: self.start_screenshot(direct=False))
        self._ctx_menu.add_command(label="Iris Settings", command=self.app._open_settings)
        self._ctx_menu.add_separator()
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
        try:
            ov = getattr(self, "_ov_tiles", None)
            btn = getattr(self, "_btn_overlay", None)
            if ov and btn and btn.winfo_exists():
                btn.config(image=ov[2] if on else ov[0])
        except Exception:
            pass

    def set_saved_foreground(self, hwnd):
        self._saved_foreground_hwnd = hwnd

    def refresh_buttons(self):
        self._render_buttons()

    def rebuild_panel(self):
        """Re-apply panel config (buttons + utility + core) after settings save."""
        try:
            from panel_actions import ensure_panel_defaults
            ensure_panel_defaults(self.app.cfg)
        except Exception:
            pass
        self._btn_nav = []
        self._render_buttons()
        self._render_utility_row()
        self._render_core_row()
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
            btype = slot.get("type", "")
            app_icon = slot.get("app_icon_path")
            if not app_icon and slot.get("use_app_icon"):
                app_icon = (self.app.cfg.get("media_player_path") or "").strip() or None
            imgs = [
                self._make_tile_photo(icon, fill, icon_scale=0.52, app_icon_path=app_icon),
                self._make_tile_photo(icon, self._adjust_hex(fill, 20), icon_scale=0.52, app_icon_path=app_icon),
            ]
            prs = self._make_tile_photo(icon, self._adjust_hex(fill, -20), icon_scale=0.52, app_icon_path=app_icon)
            theme_bg = self._get_theme_colors()[4]
            btn = tk.Label(frame, image=imgs[0], bg=theme_bg, cursor="hand2",
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

    def _render_core_row(self):
        """Build the 4 core tiles from panel_core config. Fully dynamic — replaces hardcoded tiles."""
        frame = getattr(self, "_core_frame", None)
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        self._core_tile_refs = []
        self._btn_overlay = None
        self._btn_mic = None
        self._btn_display = None
        self._ov_tiles = None
        _T, _GAP = 40, 10
        from panel_actions import default_core, DEFAULT_CORE
        slots = self.app.cfg.get("panel_core") or default_core()
        theme_bg = self._get_theme_colors()[4]
        _prs_fill_base = self._adjust_hex(BG_CARD, -20)

        for i in range(4):
            slot = slots[i] if i < len(slots) else {"type": "EMPTY", "icon": "border-none-variant"}
            if slot.get("type") == "EMPTY":
                continue
            core_act = slot.get("core_action", "")
            if not core_act:
                # Fallback for legacy / plain CORE slots without explicit core_action
                core_act = ["display", "overlay", "mic", "settings"][i]

            # Icon
            icon = slot.get("icon") or (DEFAULT_CORE[i]["icon"] if i < len(DEFAULT_CORE) else "star-circle")

            # Background fill
            fill = slot.get("color") or BG_CARD
            if not fill or fill == "RAINBOW":
                fill = BG_CARD
            _hov_fill = self._adjust_hex(fill, 20)
            _prs_fill = self._adjust_hex(fill, -20)

            app_icon = slot.get("app_icon_path")
            if not app_icon and slot.get("use_app_icon"):
                app_icon = (self.app.cfg.get("media_player_path") or "").strip() or None

            # Mic slot gets special two-state image set
            if core_act in ("mic", "mic_mute"):
                mic_un = self._make_tile_photo("microphone", fill, icon_scale=0.52)
                mic_un_h = self._make_tile_photo("microphone", _hov_fill, icon_scale=0.52)
                mic_mut = self._make_tile_photo("microphone-off", fill, NEON, (72, 178, 233), icon_scale=0.52)
                mic_mut_h = self._make_tile_photo("microphone-off", _hov_fill, NEON, (72, 178, 233), icon_scale=0.52)
                prs_un = self._make_tile_photo("microphone", _prs_fill, icon_scale=0.52)
                prs_mut = self._make_tile_photo("microphone-off", _prs_fill, NEON, (72, 178, 233), icon_scale=0.52)
                self._core_tile_refs.extend([mic_un, mic_un_h, mic_mut, mic_mut_h, prs_un, prs_mut])
                # t_set[0]=normal-off, [1]=hover-off, [2]=normal-on, [3]=hover-on
                t_set = [mic_un, mic_un_h, mic_mut, mic_mut_h]
                prs_off, prs_on = prs_un, prs_mut
            else:
                t_set = [
                    self._make_tile_photo(icon, fill, icon_scale=0.52, app_icon_path=app_icon),
                    self._make_tile_photo(icon, _hov_fill, icon_scale=0.52, app_icon_path=app_icon),
                    self._make_tile_photo(icon, fill, NEON, (72, 178, 233), icon_scale=0.52, app_icon_path=app_icon),
                    self._make_tile_photo(icon, _hov_fill, NEON, (72, 178, 233), icon_scale=0.52, app_icon_path=app_icon),
                ]
                prs_off = self._make_tile_photo(icon, _prs_fill, icon_scale=0.52, app_icon_path=app_icon)
                prs_on = self._make_tile_photo(icon, _prs_fill, NEON, (72, 178, 233), icon_scale=0.52, app_icon_path=app_icon)
                self._core_tile_refs.extend(t_set + [prs_off, prs_on])

            # Initial active state
            is_active = self._is_core_active(core_act, slot)
            initial_img = t_set[2] if is_active else t_set[0]

            btn = tk.Label(frame, image=initial_img, bg=theme_bg, cursor="hand2",
                           padx=0, pady=0, borderwidth=0)
            btn.place(x=i * (_T + _GAP), y=0)

            # Store well-known references for state sync
            if core_act in ("overlay",) or slot.get("entity") == "system.overlay":
                self._btn_overlay = btn
                self._ov_tiles = t_set
            elif core_act in ("display",) or slot.get("entity") == "system.display":
                self._btn_display = btn
            elif core_act in ("mic", "mic_mute") or slot.get("entity") == "system.mic_mute":
                self._btn_mic = btn

            def _make_binds(b=btn, ts=t_set, poff=prs_off, pon=prs_on, act=core_act, s=slot):
                def _enter(e):
                    active = self._is_core_active(act, s)
                    b.config(image=ts[3] if active else ts[1])
                def _leave(e):
                    active = self._is_core_active(act, s)
                    b.config(image=ts[2] if active else ts[0])
                def _press(e):
                    active = self._is_core_active(act, s)
                    b.config(image=pon if active else poff)
                def _release(e):
                    self._on_button_action(s)
                    self._root.after(80, self._sync_core_tiles)
                b.bind("<Enter>", _enter)
                b.bind("<Leave>", _leave)
                b.bind("<ButtonPress-1>", _press)
                b.bind("<ButtonRelease-1>", _release)
            _make_binds()

            name = slot.get("name") or core_act.replace("_", " ").title()
            if name:
                ToolTip(btn, name)

    def _is_core_active(self, act, slot):
        """Return True if the core action's toggle state is currently ON."""
        ent = slot.get("entity", "")
        if act == "display" or ent == "system.display":
            return bool(getattr(self, "_pc_display_on", False))
        if act == "overlay" or ent == "system.overlay":
            return bool(getattr(self, "_overlay_on", False))
        if act in ("mic", "mic_mute") or ent == "system.mic_mute":
            return bool(getattr(self, "_mic_muted", False))
        return False

    def _sync_core_tiles(self):
        """Update all dynamic core tile images to reflect current toggle states."""
        try:
            ov = getattr(self, "_ov_tiles", None)
            btn_ov = getattr(self, "_btn_overlay", None)
            if ov and btn_ov:
                try:
                    if btn_ov.winfo_exists():
                        btn_ov.config(image=ov[2] if self._overlay_on else ov[0])
                except Exception:
                    pass
        except Exception:
            pass

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
        """(gauges, button_box, volume, master_volume, brightness, mixer, utility) from cfg."""
        try:
            from panel_actions import (
                layout_enabled, slider_enabled, ensure_panel_defaults)
            ensure_panel_defaults(self.app.cfg)
            gauges = layout_enabled(self.app.cfg, "gauges", target="local")
            box = layout_enabled(self.app.cfg, "button_box", target="local") or self._picker_active or self._screenshot_active
            sliders = layout_enabled(self.app.cfg, "sliders", target="local")
            vol = sliders and slider_enabled(self.app.cfg, "app_volume")
            mvol = sliders and slider_enabled(self.app.cfg, "master_volume")
            # Brightness only when hardware is present (controls the device LEDs)
            bri = (sliders and slider_enabled(self.app.cfg, "brightness")
                   and self._hardware_connected())
            mix = sliders and slider_enabled(self.app.cfg, "app_mixer")
            util = layout_enabled(self.app.cfg, "utility", target="local")
            return gauges, box, vol, mvol, bri, mix, util
        except Exception:
            return True, True, True, True, False, True, True

    def _reflow_panel(self):
        """Stack visible sections top-down and shrink the window to fit."""
        gauges, box, vol, mvol, bri, mix, util = self._panel_section_flags()
        _W, _T, _GAP = 190, 40, 10
        _X = (self.W - _W) // 2
        GAUGE_H, BTN_H, SLIDER_H = 70, 150, 24
        TITLE_H, SEP, BOTTOM = 11, 1, 24

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

        any_sl = vol or mvol or bri
        self._place_or_forget(
            getattr(self, "_sep_sliders", None), any_sl, x=_X, y=y, width=_W)
        if any_sl:
            y += SEP + 3

        if vol:
            self._place_or_forget(
                getattr(self, "_lbl_volume_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H
            self._place_or_forget(
                getattr(self, "_slider_volume", None), True, x=_X, y=y, width=_W)
            y += SLIDER_H + 2
        else:
            self._place_or_forget(getattr(self, "_lbl_volume_title", None), False)
            self._place_or_forget(getattr(self, "_slider_volume", None), False)

        if mvol:
            self._place_or_forget(
                getattr(self, "_lbl_master_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H
            self._place_or_forget(
                getattr(self, "_slider_master", None), True, x=_X, y=y, width=_W)
            y += SLIDER_H + 2
        else:
            self._place_or_forget(getattr(self, "_lbl_master_title", None), False)
            self._place_or_forget(getattr(self, "_slider_master", None), False)

        self._mixer_enabled = bool(mix)
        if mix:
            mixer_h = max(getattr(self, "_mixer_h", 0) or 0, 1)
            self._place_or_forget(
                getattr(self, "_mixer_frame", None), True,
                x=_X, y=y, width=_W, height=mixer_h)
            y += mixer_h + 8
        else:
            self._place_or_forget(getattr(self, "_mixer_frame", None), False)
            if hasattr(self, "_mixer_frame") and self._mixer_frame:
                for w in self._mixer_frame.winfo_children():
                    w.place_forget()
                    w.destroy()
            self._mixer_sig = None
            self._mixer_rows = []
            self._mixer_h = 0

        if bri:
            self._place_or_forget(
                getattr(self, "_lbl_brightness_title", None), True,
                x=_X + 2, y=y, width=_W - 2, height=TITLE_H)
            y += TITLE_H
            self._place_or_forget(
                getattr(self, "_slider_brightness", None), True, x=_X, y=y, width=_W)
            y += SLIDER_H + 2
        else:
            self._place_or_forget(getattr(self, "_lbl_brightness_title", None), False)
            self._place_or_forget(getattr(self, "_slider_brightness", None), False)

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
        self._update_bg_image(self.W, new_h)
        try:
            self._win.update_idletasks()
            self._apply_region()
        except Exception:
            pass

    def _current_buttons(self):
        """Return the list of buttons to render at the current nav level."""
        if not self._btn_nav:
            return self.app.cfg.get("panel_board") or []
        top = self._btn_nav[-1]
        # 1. Inline children (if present)
        kids = top.get("children")
        if kids:
            return kids
        # 2. Target profile board lookup (by profile_id or target_profile name/id)
        prof_id = top.get("profile_id") or top.get("target_profile")
        if prof_id:
            profiles = self.app.cfg.get("panel_profiles") or []
            for p in profiles:
                if isinstance(p, dict) and (p.get("id") == prof_id or p.get("name") == prof_id):
                    return p.get("board") or []
        return []

    def _render_buttons(self):
        for w in self._btn_inner.winfo_children():
            w.destroy()
        self._btn_tile_refs.clear()

        buttons = self._current_buttons()
        _T, _GAP = 40, 10
        _COLS = 4
        _ROWS = 3
        _PAGE_SLOTS = _COLS * _ROWS  # 12 tiles per page, like the phone grid
        _PAGE = self.PAGE_H
        _OFF = (_PAGE - (_ROWS * _T + (_ROWS - 1) * _GAP)) // 2  # centre grid in page

        if self._picker_active:
            self._build_picker_page(y0=0)
            self._btn_page_count_override = 1
            self._btn_inner.configure(height=_PAGE)
            self._btn_canvas.configure(scrollregion=(0, 0, 0, _PAGE))
            self._btn_canvas.yview_moveto(0)
            return

        if self._screenshot_active:
            self._build_screenshot_page(y0=0)
            self._btn_page_count_override = 1
            self._btn_inner.configure(height=_PAGE)
            self._btn_canvas.configure(scrollregion=(0, 0, 0, _PAGE))
            self._btn_canvas.yview_moveto(0)
            return

        in_nav = bool(self._btn_nav)

        # Paginate the board into full 4x3 pages; placeholders fill empty slots
        pages = [buttons[i:i + _PAGE_SLOTS] for i in range(0, max(len(buttons), 1), _PAGE_SLOTS)]

        for pi, page in enumerate(pages):
            y0 = pi * _PAGE + _OFF
            slots = list(page)
            if pi == 0 and in_nav:
                slots = [None] + slots  # back tile owns grid slot 0
            for i in range(_PAGE_SLOTS):
                slot = slots[i] if i < len(slots) else None
                x = (i % _COLS) * (_T + _GAP)
                y = y0 + (i // _COLS) * (_T + _GAP)

                vals = self._get_theme_colors()
                neon_rgb, theme_bg, neon_text_rgb = vals[1], vals[4], vals[7]

                # Back button if in a sub-panel — occupies grid slot 0
                if pi == 0 and in_nav and i == 0:
                    back_img = self._make_tile_photo("reply", BUTTON, icon_color=neon_text_rgb)
                    back_hov = self._make_tile_photo("reply", self._adjust_hex(BUTTON, 20), icon_color=neon_text_rgb)
                    self._btn_tile_refs.extend([back_img, back_hov])
                    back_btn = tk.Label(self._btn_inner, image=back_img, bg=theme_bg, cursor="hand2",
                                        padx=0, pady=0, borderwidth=0)
                    back_btn.place(x=x, y=y)
                    def _bh(e, b=back_btn, h=back_hov, n=back_img): b.config(image=h)
                    def _bl(e, b=back_btn, n=back_img): b.config(image=n)
                    back_btn.bind("<Enter>", _bh)
                    back_btn.bind("<Leave>", _bl)
                    back_btn.bind("<ButtonRelease-1>", lambda e: self._win.after_idle(self.btn_nav_pop))
                    back_btn.bind("<MouseWheel>", self._on_btn_wheel)
                    continue

                # "+" empty-state prompt (top-left slot when nothing configured)
                if not buttons and pi == 0 and i == 0:
                    plus_img = self._make_tile_photo("plus", BG_CARD)
                    plus_hov = self._make_tile_photo("plus", self._adjust_hex(BG_CARD, 20))
                    self._btn_tile_refs.extend([plus_img, plus_hov])
                    plus_btn = tk.Label(self._btn_inner, image=plus_img, bg=theme_bg, cursor="hand2",
                                        padx=0, pady=0, borderwidth=0)
                    plus_btn.place(x=x, y=y)
                    def _ph(e, b=plus_btn, h=plus_hov, n=plus_img): b.config(image=h)
                    def _pl(e, b=plus_btn, n=plus_img): b.config(image=n)
                    plus_btn.bind("<Enter>", _ph)
                    plus_btn.bind("<Leave>", _pl)
                    plus_btn.bind("<Button-1>", lambda e: self.app._open_settings())
                    plus_btn.bind("<MouseWheel>", self._on_btn_wheel)
                    plus_tip = tk.Label(self._btn_inner, text="Add",
                                        font=("Segoe UI", 6), fg=FG, bg=theme_bg)
                    plus_tip.place(x=x, y=y + _T - 2, width=_T, height=12)
                    plus_tip.bind("<MouseWheel>", self._on_btn_wheel)
                    continue

                # Empty / EMPTY slot → faint placeholder tile (empty grid slot)
                if slot is None or slot.get("type") == "EMPTY":
                    ph = self._make_placeholder_photo()
                    phl = tk.Label(self._btn_inner, image=ph, bg=theme_bg,
                                   padx=0, pady=0, borderwidth=0)
                    phl.place(x=x, y=y)
                    phl.bind("<MouseWheel>", self._on_btn_wheel)
                    continue

                btype = slot.get("type", "")
                name = slot.get("name") or ""
                if btype == "AUDIO OUTPUT":
                    cur_id = None
                    try:
                        from win_platform import get_current_default_audio_output
                        cur_id = get_current_default_audio_output()
                    except Exception:
                        pass
                    alt_id = slot.get("audio_input_device_id_alt", "").strip()
                    is_alt = bool(alt_id and cur_id and (cur_id.strip().lower() == alt_id.lower() or alt_id.lower() in cur_id.strip().lower() or cur_id.strip().lower() in alt_id.lower()))
                    if is_alt:
                        icon_name = slot.get("audio_alt_icon") or "headphones"
                    else:
                        icon_name = slot.get("audio_primary_icon") or "speaker"
                    if not name or name == "Audio":
                        name = slot.get("audio_input_device_name_alt") if is_alt else (slot.get("audio_input_device_name") or "Speakers")
                else:
                    icon_name = slot.get("icon") or "help-circle"
                fill = slot.get("color") or BG_CARD
                name = slot.get("name") or ""
                app_icon = slot.get("app_icon_path") or (slot.get("shortcut_path") if btype in ("SHORTCUT", "GROUP") else None)
                if not app_icon and slot.get("use_app_icon"):
                    app_icon = (self.app.cfg.get("media_player_path") or "").strip() or None
                ring = NEON if btype == "GROUP" else None

                img = self._make_tile_photo(icon_name, fill, ring_hex=ring, app_icon_path=app_icon)
                hov = self._make_tile_photo(icon_name, self._adjust_hex(fill, 20), ring_hex=ring, app_icon_path=app_icon)
                prs = self._make_tile_photo(icon_name, self._adjust_hex(fill, -20), ring_hex=ring, app_icon_path=app_icon)
                self._btn_tile_refs.extend([img, hov, prs])

                btn = tk.Label(self._btn_inner, image=img, bg=theme_bg, cursor="hand2",
                               padx=0, pady=0, borderwidth=0)
                btn.place(x=x, y=y)
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

        # Track height = one page per grid page
        page_count = len(pages)
        self._btn_page_count_override = page_count
        self._btn_inner.configure(height=page_count * _PAGE)
        self._snap_btn_view()
        self._win.after_idle(self._snap_btn_view)

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

    def _btn_page_count(self):
        try:
            h = getattr(self, "_btn_page_count_override", None)
            if h:
                return max(1, int(h))
            self._win.update_idletasks()
            inner_h = max(1, int(self._btn_inner.winfo_reqheight()))
            return max(1, int(round(inner_h / float(self.PAGE_H))))
        except Exception:
            return 1

    def _snap_btn_view(self):
        """Scroll the button track to the appropriate page."""
        try:
            self._win.update_idletasks()
            num = max(1, self._btn_page_count())
            inner_h = max(1, num * self.PAGE_H)
            self._btn_canvas.configure(scrollregion=(0, 0, 0, inner_h))
            self._btn_canvas.yview_moveto(0)
        except Exception:
            pass

    # ── Colour picker (screen grab via low-level mouse hook) ───────────

    def start_colour_picker(self):
        """Pop the panel up with the colour-picker page and arm the first grab."""
        if self._picker_session is not None:
            self._picker_session.end()
            self._picker_session = None
        self._picker_active = True
        self._picked_hex = (self.app.cfg.get("colour_picker_value") or None)
        self._render_buttons()
        self.show()
        self._arm_colour_picker()

    def _arm_colour_picker(self):
        """Start a fresh grab session. Safe to call repeatedly."""
        if self._picker_session is not None:
            self._picker_session.end()
            self._picker_session = None
        self._picker_session = colour_picker.ColourPickSession(
            exclude_hwnd=self._hwnd,
            root=self._root,
            on_preview=self._picker_preview,
            on_colour=self._picker_colour,
            on_cancel=self._picker_cancel,
        )
        self._picker_session.begin()

    def _finish_colour_picker(self):
        if self._picker_session:
            self._picker_session.end()
            self._picker_session = None
        self._picker_active = False
        self._picker_hex_lbl = self._picker_rgb_lbl = None
        self._picker_capture_btn = None
        self._click_guard = True
        self._render_buttons()

    # ── Screenshot (screen grab via vision.py + iconify) ────────────────

    def start_screenshot(self, slot=None, direct=True, mode="auto"):
        """Trigger screenshot capture."""
        slot_mode = (slot.get("capture_mode") if isinstance(slot, dict) else None) or mode
        if slot_mode == "fullscreen" or (slot_mode == "auto" and direct):
            self.start_fullscreen_screenshot(slot)
            return
        if slot_mode == "zone":
            self.start_direct_screenshot(slot)
            return

        try:
            if self._capture_toolbar is None:
                from capture_toolbar import CaptureToolbar
                self._capture_toolbar = CaptureToolbar(self._root, self.app)
            self._capture_toolbar.show(slot)
        except Exception as ex:
            log.warning("Failed to open capture toolbar: %s", ex)

    def start_fullscreen_screenshot(self, slot=None):
        """Silently capture active monitor/game with zero focus disruption and no minimization."""
        try:
            saved = getattr(self, "_saved_foreground_hwnd", None)
            app_tag = _get_foreground_app_name(saved) if saved else "game"
            if self._capture_toolbar is None:
                from capture_toolbar import CaptureToolbar
                self._capture_toolbar = CaptureToolbar(self._root, self.app)
            self._capture_toolbar.capture_fullscreen_direct(app_tag=app_tag, notify=True)
        except Exception as ex:
            log.warning("Failed to start fullscreen screenshot: %s", ex)

    def start_direct_screenshot(self, slot=None):
        """Invoke rectangular crosshair zone capture directly, save screenshot, run OCR, and open annotation viewer."""
        try:
            # Clear any prior screenshot so a polling phone never sees a stale image
            # (phone/PC clock skew would otherwise make a previous capture look 'newer').
            if self.app is not None and getattr(self.app, "screenshot_last", None) is not None:
                self.app.screenshot_last = None
            saved = getattr(self, "_saved_foreground_hwnd", None)
            app_tag = _get_foreground_app_name(saved) if saved else "desktop"

            def _capture():
                try:
                    import vision
                    rect = vision.select_region(self._root, timeout=90)
                    if rect:
                        x, y, w, h = rect
                        img = vision.capture((x, y, x + w, y + h))
                        if self._capture_toolbar is None:
                            from capture_toolbar import CaptureToolbar
                            self._capture_toolbar = CaptureToolbar(self._root, self.app)
                        fname = self._capture_toolbar._save_screenshot_and_ocr(img, app_tag)
                        if fname:
                            try:
                                import viewer_window
                                viewer_window.open_viewer(fname)
                            except Exception as ex:
                                log.warning("Failed to open screenshot annotation editor: %s", ex)
                except Exception as ex:
                    log.warning("Direct capture failed: %s", ex)

            # Briefly hide overlay window if visible and not pinned
            if hasattr(self, "hide") and not getattr(self, "_pin_pinned", False):
                self.hide()

            self._root.after(150, lambda: threading.Thread(target=_capture, daemon=True, name="iris-direct-capture").start())
        except Exception as ex:
            log.warning("Failed to start direct screenshot: %s", ex)

    def start_quick_note(self, app_tag=None, engine=None, toggle=False):
        """Open or toggle the dedicated Notepad window."""
        try:
            if not app_tag:
                saved = getattr(self, "_saved_foreground_hwnd", None)
                app_tag = _get_foreground_app_name(saved)
            import notepad_window
            notepad_window.open_notepad(app_tag=app_tag, engine=engine, toggle=toggle)
        except Exception as ex:
            log.warning("Failed to open quick note: %s", ex)

    def _scroll_btn_to_screenshot(self):
        """Scroll the button track so the screenshot page is in view."""
        try:
            num = max(1, self._btn_page_count())
            inner_h = max(1, num * self.PAGE_H)
            self._btn_canvas.configure(scrollregion=(0, 0, 0, inner_h))
            self._btn_canvas.yview_moveto((num - 1) / float(num))
        except Exception:
            pass

    def _build_screenshot_page(self, y0):
        import vision as _vision
        _W, _PH = 190, self.PAGE_H
        frm = tk.Frame(self._btn_inner, bg=BG, width=_W, height=_PH)
        frm.place(x=0, y=y0)
        frm.pack_propagate(False)

        tk.Label(frm, text="SCREENSHOT", font=("Segoe UI", 6, "bold"),
                 fg=FG_DIM, bg=BG).place(x=0, y=6, width=_W, height=12)

        # Preview thumbnail area
        self._screenshot_lbl = tk.Label(
            frm, bg="#111111", text="No capture yet",
            font=("Segoe UI", 7), fg=FG_DIM,
            relief="flat", anchor="center")
        self._screenshot_lbl.bind("<MouseWheel>", self._on_btn_wheel)
        if self._screenshot_img is not None:
            self._update_screenshot_preview()

        # Monitor dropdown — only shown when more than one monitor is present
        monitors = _vision.monitor_rects()
        n_mon = len(monitors)

        if n_mon > 1:
            mon_labels = [
                f"Monitor {i + 1}  ({m['w']}×{m['h']})"
                for i, m in enumerate(monitors)
            ]
            mon_idx = max(0, min(self._screenshot_monitor, n_mon - 1))
            self._ss_mon_var = tk.StringVar(value=mon_labels[mon_idx])

            mon_menu = tk.OptionMenu(frm, self._ss_mon_var, *mon_labels)
            mon_menu.config(
                bg="#1a1a1a", fg=FG, activebackground=NEON,
                font=("Segoe UI", 7), relief="flat",
                highlightthickness=0, width=22, anchor="w")
            mon_menu["menu"].config(bg="#1a1a1a", fg=FG,
                                    activebackground=NEON, activeforeground=BG)
            mon_menu.place(x=6, y=98, width=178, height=20)
            mon_menu.bind("<MouseWheel>", self._on_btn_wheel)
            # preview sits between title (y=18) and monitor (y=98)
            _pv_h = 98 - 22 - 4
            btn_y = 122

            def _on_mon_change(*_):
                try:
                    self._screenshot_monitor = mon_labels.index(
                        self._ss_mon_var.get())
                except ValueError:
                    pass
            self._ss_mon_var.trace_add("write", _on_mon_change)
        else:
            # no monitor — push buttons to the bottom, preview fills the gap
            btn_y = _PH - 6 - 26          # 150 - 6 - 26 = 118
            _pv_h = btn_y - 22 - 4        # 92

        self._screenshot_lbl.place(x=6, y=22, width=178, height=_pv_h)

        # Capture buttons — 3 across: Screenshot (fullscreen) | Snipping Tool | Done
        _btn_h, _btn_gap = 26, 4
        _btn_y0 = 6
        _total_w = _W - 2 * _btn_y0  # usable width
        _done_w = 48
        _snip_w = 64
        _full_w = _total_w - _snip_w - _done_w - 2 * _btn_gap
        full_btn = RoundedButton(
            frm, text="Screenshot", style="sec",
            command=self._screenshot_grab_full,
            font=("Segoe UI", 8, "bold"))
        full_btn.place(x=_btn_y0, y=btn_y, width=_full_w, height=_btn_h)

        snip_btn = RoundedButton(
            frm, text="Snipping Tool", style="sec",
            command=self._screenshot_grab_area,
            font=("Segoe UI", 8, "bold"))
        snip_btn.place(x=_btn_y0 + _full_w + _btn_gap, y=btn_y, width=_snip_w, height=_btn_h)

        bright_neon = self._get_theme_colors()[8]
        done_btn = RoundedButton(
            frm, text="Done", style="prim", bg=bright_neon,
            command=self._finish_screenshot,
            font=("Segoe UI", 8, "bold"))
        done_btn.place(x=_btn_y0 + _full_w + _btn_gap + _snip_w + _btn_gap, y=btn_y, width=_done_w, height=_btn_h)

        for w in (full_btn, snip_btn, done_btn):
            w.bind("<MouseWheel>", self._on_btn_wheel)

    def _screenshot_grab_full(self):
        """Hide the window, wait, then capture the selected monitor."""
        import threading
        self._win.withdraw()

        def _capture():
            import vision as _vision
            monitors = _vision.monitor_rects()
            idx = max(0, min(self._screenshot_monitor, len(monitors) - 1))
            m = monitors[idx]
            bbox = (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
            try:
                img = _vision.capture(bbox)
                self._root.after(0, lambda: self._on_screenshot_done(img))
            except Exception as exc:
                log.warning("screenshot full capture failed: %s", exc)
                self._root.after(0, self._win.deiconify)

        self._root.after(
            200, lambda: threading.Thread(
                target=_capture, daemon=True, name="iris-screenshot-full"
            ).start()
        )

    def _screenshot_grab_area(self):
        """Hide the window, show the region selector, then capture."""
        import threading
        self._win.withdraw()

        def _capture():
            import vision as _vision
            rect = _vision.select_region(self._root, timeout=90)
            if rect:
                x, y, w, h = rect
                try:
                    img = _vision.capture((x, y, x + w, y + h))
                    self._root.after(0, lambda: self._on_screenshot_done(img))
                    return
                except Exception as exc:
                    log.warning("screenshot area capture failed: %s", exc)
            self._root.after(0, self._win.deiconify)

        self._root.after(
            150, lambda: threading.Thread(
                target=_capture, daemon=True, name="iris-screenshot-area"
            ).start()
        )

    def _on_screenshot_done(self, img):
        """Called on the Tk thread once the capture thread has a PIL image."""
        import io, base64, time as _time
        self._win.deiconify()
        self._screenshot_img = img
        self._screenshot_ts  = _time.time()
        self._screenshot_w   = img.width
        self._screenshot_h   = img.height
        self._save_screenshot_to_disk(img)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=62, optimize=True)
        self._screenshot_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        # Make available for GET /api/screenshot/latest
        if self.app is not None:
            self.app.screenshot_last = {
                "img": self._screenshot_b64,
                "fmt": "jpeg",
                "w":   self._screenshot_w,
                "h":   self._screenshot_h,
                "ts":  self._screenshot_ts,
            }
        self._update_screenshot_preview()

    def _save_screenshot_to_disk(self, img):
        """Persist the capture as a PNG in the configured screenshot folder."""
        import os, time as _tm
        try:
            folder = (self.app.cfg.get("screenshot_dir") or "").strip() if self.app is not None else ""
            if not folder:
                folder = os.path.join(os.path.expanduser("~"), "Documents", "Iris", "Screenshots")
            folder = os.path.abspath(folder)
            os.makedirs(folder, exist_ok=True)
            app_tag = (self._screenshot_app or "desktop").lower()
            fname = "iris_%s_%s.png" % (app_tag, _tm.strftime("%Y%m%d_%H%M%S"))
            path = os.path.join(folder, fname)
            img.save(path, format="PNG")
            self._screenshot_fname = fname
            log.info("screenshot saved: %s", path)
        except Exception as exc:
            log.warning("screenshot save failed: %s", exc)

    def _open_screenshot_in_browser(self):
        """Open the captured screenshot directly in the Iris Library browser."""
        try:
            import panel_window
            fname = self._screenshot_fname or ""
            params = {"view": "library", "file": fname} if fname else {"view": "library"}
            panel_window.open_panel(query_params=params)
        except Exception as exc:
            log.warning("Failed to open screenshot in Iris browser: %s", exc)

    def _update_screenshot_preview(self):
        """Resize the captured image, composite the white MDI open-in-new icon, and show it in the dialog preview label."""
        if self._screenshot_lbl is None or self._screenshot_img is None:
            return
        try:
            from PIL import Image, ImageTk
            import mdi_icons
            thumb = self._screenshot_img.copy()
            thumb.thumbnail((178, 72), Image.LANCZOS)
            thumb = thumb.convert("RGBA")
            
            # Composite white MDI open-in-new icon in the center of the thumbnail
            try:
                # Primary white open-in-new icon with subtle drop shadow
                ic_size = 24
                ic_shadow = mdi_icons.render("open-in-new", ic_size, (0, 0, 0))
                ic_glyph = mdi_icons.render("open-in-new", ic_size, (255, 255, 255))
                if ic_glyph is not None:
                    cx = (thumb.width - ic_size) // 2
                    cy = (thumb.height - ic_size) // 2
                    if ic_shadow is not None:
                        thumb.paste(ic_shadow, (cx + 1, cy + 1), ic_shadow)
                    thumb.paste(ic_glyph, (cx, cy), ic_glyph)
            except Exception as e:
                log.debug("failed to overlay mdi open-in-new icon: %s", e)

            photo = ImageTk.PhotoImage(thumb)
            self._screenshot_lbl.config(image=photo, text="", cursor="hand2")
            self._screenshot_lbl.bind("<Button-1>", lambda e: self._open_screenshot_in_browser())
            self._screenshot_lbl._photo = photo  # keep reference to prevent GC
        except Exception as exc:
            log.warning("screenshot preview update failed: %s", exc)

    def _finish_screenshot(self):
        """Close the screenshot dialog and return to the button grid."""
        self._screenshot_active = False
        self._screenshot_lbl    = None
        self._click_guard = True
        self._render_buttons()
        # Restore focus to the previous active application
        saved = getattr(self, "_saved_foreground_hwnd", None)
        if saved and user32.IsWindow(saved):
            try:
                user32.SetForegroundWindow(saved)
            except Exception:
                pass

    def _scroll_btn_to_picker(self):
        """Scroll the button track so the colour-picker page is in view."""
        try:
            num = max(1, self._btn_page_count())
            inner_h = max(1, num * self.PAGE_H)
            self._btn_canvas.configure(scrollregion=(0, 0, 0, inner_h))
            self._btn_canvas.yview_moveto((num - 1) / float(num))
        except Exception:
            pass

    def _build_picker_page(self, y0):
        _W, _PH = 190, self.PAGE_H
        frm = tk.Frame(self._btn_inner, bg=BG, width=_W, height=_PH)
        frm.place(x=0, y=y0)
        frm.pack_propagate(False)

        tk.Label(frm, text="COLOUR PICKER", font=("Segoe UI", 6, "bold"),
                 fg=FG_DIM, bg=BG).place(x=0, y=6, width=_W, height=12)

        self._picker_hex_lbl = tk.Label(frm, text=self._picked_hex or "#------",
                                        font=("Consolas", 16, "bold"),
                                        fg=self._picked_hex or NEON, bg=BG)
        self._picker_hex_lbl.place(x=0, y=22, width=_W, height=30)

        self._picker_rgb_lbl = tk.Label(frm, text="rgb(—, —, —)",
                                        font=("Consolas", 8), fg=FG, bg=BG)
        self._picker_rgb_lbl.place(x=0, y=54, width=_W, height=14)

        tip = tk.Label(frm, text="Hover the display to preview, click to grab.",
                       font=("Segoe UI", 6), fg=FG_DIM, bg=BG)
        tip.place(x=0, y=72, width=_W, height=14)

        # Two buttons centered: eyedropper + Done
        _btn_h, _btn_gap = 28, 6
        _pick_w = 36
        _done_w = _W - _pick_w - _btn_gap - 12   # 6px margin each side

        pick_btn = RoundedButton(
            frm, style="sec", icon="eyedropper",
            command=self._arm_colour_picker,
            font=("Segoe UI", 8, "bold"))
        pick_btn.place(x=6, y=102, width=_pick_w, height=_btn_h)
        pick_btn.bind("<MouseWheel>", self._on_btn_wheel)

        bright_neon = self._get_theme_colors()[8]
        done = RoundedButton(frm, text="Done", style="prim", bg=bright_neon,
                             command=self._finish_colour_picker,
                             font=("Segoe UI", 8, "bold"))
        done.place(x=6 + _pick_w + _btn_gap, y=102, width=_done_w, height=_btn_h)

        for w in (self._picker_hex_lbl, self._picker_rgb_lbl, tip, done, pick_btn):
            w.bind("<MouseWheel>", self._on_btn_wheel)

        self._picker_hex_lbl.bind("<Button-1>", lambda e: self._copy_picked("hex"))
        self._picker_rgb_lbl.bind("<Button-1>", lambda e: self._copy_picked("rgb"))

    def _copy_picked(self, which):
        """Copy the current hex or rgb value to the clipboard."""
        try:
            value = self._picked_hex
            if not value:
                return
            if which == "rgb" and self._picker_rgb_lbl is not None:
                cur = self._picker_rgb_lbl.cget("text")
                if cur.startswith("rgb("):
                    value = cur
            self._root.clipboard_clear()
            self._root.clipboard_append(value)
            self._root.update()
            self._picker_hex_lbl.config(fg=NEON)
            self._picker_rgb_lbl.config(fg=FG)
        except Exception as e:
            log.warning("copy picked colour failed: %s", e)

    def _picker_preview(self, hexs, rgb):
        if self._picker_hex_lbl is not None:
            try:
                self._picker_hex_lbl.config(text=hexs, fg=hexs)
                self._picker_rgb_lbl.config(text="rgb(%d, %d, %d)" % rgb)
            except Exception:
                pass

    def _picker_colour(self, hexs, rgb):
        """A colour was grabbed — lock it, persist it, and notify the phone."""
        self._picked_hex = hexs
        self._picker_preview(hexs, rgb)
        try:
            self.app.cfg["colour_picker_value"] = hexs
            from config import save_config
            save_config(self.app.cfg)
        except Exception as e:
            log.warning("save picked colour failed: %s", e)
        try:
            from serial_comm import serial_sender
            serial_sender.notify("colour.picker.last", "Colour Picked", hexs, theme="purple")
        except Exception as e:
            log.warning("colour picker notify failed: %s", e)

    def _picker_cancel(self):
        """Session cancelled — keep the page up so the value is still readable."""

    def _on_btn_wheel(self, e):
        """Page-based scroll: one wheel notch = one full page."""
        try:
            num_pages = self._btn_page_count()
            cur = self._btn_canvas.yview()[0]
            page = max(0, min(num_pages - 1, int(round(cur * num_pages))))
            delta = int(-1 * (e.delta / 120))  # +1 on wheel down (Windows)
            page = max(0, min(num_pages - 1, page + delta))
            self._btn_canvas.yview_moveto(page / num_pages)
        except Exception:
            pass

    def _on_button_action(self, slot):
        if getattr(self, '_click_guard', False):
            self._click_guard = False
            return
        btype = slot.get("type", "")
        log.info("Button '%s' clicked — type=%s", slot.get("name",""), btype)

        import threading, os, subprocess

        def _safe_launch(p, args=None):
            if not p:
                return
            import shutil
            import shlex
            raw_path = os.path.expandvars(os.path.expanduser(str(p).strip().strip('"\'')))
            raw_args = os.path.expandvars(str(args or "").strip())
            if not raw_args and not os.path.isfile(raw_path):
                try:
                    parts = shlex.split(raw_path, posix=False)
                    if parts:
                        first_token = parts[0].strip('"\'')
                        first_token = os.path.expandvars(os.path.expanduser(first_token))
                        which_p = shutil.which(first_token) or (first_token if os.path.isfile(first_token) else None)
                        if which_p and os.path.isfile(which_p):
                            raw_path = which_p
                            raw_args = raw_path[len(parts[0]):].strip()
                except Exception:
                    pass

            exe = shutil.which(raw_path) or raw_path
            try:
                if raw_args:
                    if hasattr(os, "startfile"):
                        os.startfile(exe, arguments=raw_args)
                    else:
                        import shlex
                        subprocess.Popen([exe, *shlex.split(raw_args)], shell=False)
                else:
                    if hasattr(os, "startfile"):
                        os.startfile(exe)
                    else:
                        subprocess.Popen([exe], shell=False)
            except Exception as ex:
                log.warning("Launch shortcut failed: %s", ex)

        if btype == "GROUP":
            path = slot.get("shortcut_path", "").strip()
            s_args = slot.get("shortcut_args", "").strip()
            if path:
                threading.Thread(
                    target=lambda: _safe_launch(path, s_args),
                    daemon=True,
                ).start()
            self.btn_nav_push(slot)
            return

        if btype == "PANEL":
            self.btn_nav_push(slot)
            return

        if btype == "CORE":
            core_act = slot.get("core_action", "").strip()
            if core_act == "display":
                self._pc_display_on = not self._pc_display_on
                self.app._toggle_pc_stats(self._pc_display_on)
                return
            elif core_act == "overlay":
                self._overlay_on = not self._overlay_on
                self.app._toggle_overlay(self._overlay_on)
                return
            elif core_act in ("mic", "mic_mute"):
                from win_platform import toggle_mic_mute
                res = toggle_mic_mute()
                if res is not None:
                    self._mic_muted = res
                return
            elif core_act == "settings":
                self.app._open_settings()
                return
            elif core_act == "toolbar":
                if hasattr(self.app, "_toggle_capture_toolbar"):
                    self.app._toggle_capture_toolbar()
                return
            elif core_act in ("lighting", "lighting_sync"):
                if hasattr(self.app, "_toggle_lighting_sync"):
                    self.app._toggle_lighting_sync()
                return
            elif core_act == "colour_picker":
                self.start_colour_picker()
                return
            elif core_act in ("screenshot", "screenshot_full"):
                self.start_screenshot(slot, mode="fullscreen")
                return
            elif core_act == "screenshot_zone":
                self.start_screenshot(slot, mode="zone")
                return
            elif core_act in ("note", "note_native", "note_webview"):
                self.start_quick_note(toggle=True)
                return
            elif core_act == "borderless_toggle":
                from win_platform import toggle_borderless_window
                toggle_borderless_window()
                return
            elif core_act == "stopwatch":
                if hasattr(self.app, "_toggle_stopwatch"):
                    self.app._toggle_stopwatch()
                return
            elif core_act == "countdown":
                if hasattr(self.app, "_toggle_countdown"):
                    self.app._toggle_countdown()
                return
            # Unknown core_action — fall through to entity dispatch below


        ent = slot.get("entity", "").strip()
        if ent == "media.player" or ent == "media.eject" or btype == "MEDIA_EJECT":
            self._media_eject()
            return
        if ent == "media.play_pause" or btype == "MEDIA_PLAY":
            self._media_play_pause()
            return
        if ent == "media.next" or btype == "MEDIA_NEXT":
            self._media_next()
            return
        if ent == "media.prev" or btype == "MEDIA_PREV":
            self._media_prev()
            return
        if ent == "system.lighting_sync":
            if hasattr(self.app, "_toggle_lighting_sync"):
                self.app._toggle_lighting_sync()
            return
        if ent == "system.display":
            self.app._toggle_pc_stats()
            return
        if ent == "system.overlay":
            self.app._toggle_overlay()
            return
        if ent == "system.mic_mute":
            from win_platform import toggle_mic_mute
            toggle_mic_mute()
            return
        if ent == "system.settings":
            self.app._open_settings()
            return
        if ent == "system.colour_picker":
            self.start_colour_picker()
            return
        if ent == "system.screenshot" or btype == "SCREENSHOT":
            self.start_screenshot(slot)
            return
        if ent == "system.note" or btype == "NOTE":
            self.start_quick_note()
            return

        if btype in ("OPENRGB", "RGB") or slot.get("openrgb_profile") or ent.startswith(("openrgb.", "rgb.")) or slot.get("plugin") in ("openrgb", "rgb"):
            self._do_openrgb_action(slot)
            return

        if btype == "SHORTCUT":
            path = slot.get("shortcut_path", "").strip()
            s_args = slot.get("shortcut_args", "").strip()
            if path:
                threading.Thread(
                    target=lambda: _safe_launch(path, s_args),
                    daemon=True,
                ).start()
        elif btype == "REST":
            self._do_rest_action(slot)
        elif btype == "HOTKEY":
            self._do_hotkey_action(slot)
        elif btype == "AUDIO OUTPUT":
            self._do_audio_output_action(slot)
        elif btype == "STOPWATCH":
            self.app._toggle_stopwatch()
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
        elif slot.get("plugin") or "." in ent:
            try:
                from panel_runtime import execute_slot
                threading.Thread(target=lambda: execute_slot(slot), daemon=True).start()
            except Exception as ex:
                log.warning("Plugin execute_slot failed: %s", ex)

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
        import threading
        def _apply():
            try:
                from panel_runtime import _openrgb_action
                if _openrgb_action(slot):
                    return
            except Exception as ex:
                log.warning("openrgb action via panel_runtime failed: %s", ex)
            profile_name = (slot.get("openrgb_profile") or "").strip()
            if not profile_name:
                self._root.after(0, self._show_openrgb_picker)
        threading.Thread(target=_apply, daemon=True).start()

    def _show_openrgb_picker(self):
        import math, colorsys, io, base64
        from PIL import Image

        popup = tk.Toplevel(self._win)
        popup.overrideredirect(True)
        popup.configure(bg=BG)
        popup.attributes("-topmost", True)

        WHEEL = 220
        cx = cy = WHEEL // 2
        radius_px = WHEEL // 2 - 2

        global _OPENRGB_WHEEL_B64
        if "_OPENRGB_WHEEL_B64" not in globals() or _OPENRGB_WHEEL_B64 is None:
            wheel_img = Image.new("RGB", (WHEEL, WHEEL), (28, 30, 34))
            px = wheel_img.load()
            for y in range(WHEEL):
                for x in range(WHEEL):
                    dx = x - cx
                    dy = y - cy
                    dist = math.hypot(dx, dy)
                    if dist <= radius_px:
                        hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360.0
                        sat = dist / radius_px
                        r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
                        px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
            buf = io.BytesIO()
            wheel_img.save(buf, format="PNG")
            _OPENRGB_WHEEL_B64 = base64.b64encode(buf.getvalue()).decode("ascii")

        photo = tk.PhotoImage(data=_OPENRGB_WHEEL_B64)
        canvas = tk.Canvas(popup, width=WHEEL, height=WHEEL, bg=BG,
                           highlightthickness=0, bd=0, cursor="crosshair")
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.pack(padx=16, pady=(0, 0))

        sel = canvas.create_oval(0, 0, 0, 0, outline="white", width=2)
        WR = radius_px

        def _pos_from_rgb(r, g, b):
            h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            angle = math.radians(h * 360)
            dist = s * WR
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
            x, y = int(e.x), int(e.y)
            dx = x - cx
            dy = y - cy
            dist = math.hypot(dx, dy)
            if dist > radius_px:
                return
            hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360.0
            sat = dist / radius_px
            r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
            _set_color_from_rgb(int(r * 255), int(g * 255), int(b * 255))

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
        hotkey = (slot.get("hotkey") or "").strip()
        if not hotkey:
            legacy_keys = slot.get("keys", [])
            if legacy_keys:
                hotkey = legacy_keys

        if not hotkey:
            return

        title = getattr(self, '_saved_foreground_title', '')
        self._sending_hotkey = True
        self.hide()

        try:
            if title:
                import pygetwindow as gw
                matches = gw.getWindowsWithTitle(title)
                if matches:
                    matches[0].activate()
                    _time.sleep(0.15)

            from keyboard_service import keyboard_service
            keyboard_service.send_sequence(hotkey)
            log.info("[hotkey] sent '%s' via hardware keyboard_service", hotkey)
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
                current = get_current_default_audio_output(ttl=0)
                log.info("[audio] current default=%s", (current or "None")[:50])
                device_key = alt if current and current == primary else primary
            log.info("[audio] switching to %s", device_key[:50])
            import threading
            from win_platform import set_default_audio_output
            def _switch():
                set_default_audio_output(device_key)
                self._win.after(100, self._render_buttons)
                try:
                    import ws_bridge
                    ws_bridge.broadcast({"type": "panel_update"})
                except Exception:
                    pass
            threading.Thread(target=_switch, daemon=True).start()
        except Exception as e:
            log.exception("[audio] _do_audio_output_action failed: %s", e)

    # ── Tile photo cache ──────────────────────────────────────────
    _tile_cache = {}

    @staticmethod
    def _parse_hex(hex_str, default=(43, 43, 43)):
        if isinstance(hex_str, str) and len(hex_str) >= 7 and hex_str.startswith("#"):
            try:
                return tuple(int(hex_str[i:i+2], 16) for i in (1, 3, 5))
            except (ValueError, TypeError):
                pass
        return default

    def _make_placeholder_photo(self):
        """Empty tile — a faint filled rounded rect, no border."""
        cached = self._tile_cache.get("__placeholder__")
        if cached is not None:
            return cached
        _T, _CR = 40, 8
        S = _T * 2
        R = _CR * 2
        brgb = self._parse_hex(BG, default=(12, 13, 15))
        frgb = self._parse_hex(BG_CARD, default=(43, 43, 43))
        # Phone renders the tile at opacity .3 — approximate by blending toward BG
        blend = tuple(int(frgb[i] * 0.35 + brgb[i] * 0.65) for i in range(3))
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, S - 1, S - 1], R, fill=(*blend, 255))
        img = img.resize((_T, _T), Image.LANCZOS)
        base = Image.new("RGB", (_T, _T), brgb)
        base.paste(img, mask=img.split()[3])
        photo = ImageTk.PhotoImage(base)
        self._tile_cache["__placeholder__"] = photo
        return photo

    def _apply_flat_tile_shading(self, img, S, R):
        """Apply smooth inner shadow and subtle bottom shadow rim to a tile."""
        from PIL import ImageFilter
        # 1. Soft inner shadow vignette
        inv_mask = Image.new("L", (S + 8, S + 8), 255)
        ImageDraw.Draw(inv_mask).rounded_rectangle([4, 4, S + 3, S + 3], R, fill=0)
        inv_blur = inv_mask.filter(ImageFilter.GaussianBlur(radius=3))
        inner_shadow_alpha = inv_blur.crop((4, 4, S + 4, S + 4))

        inner_alpha = inner_shadow_alpha.point(lambda p: int(p * 0.45))
        inner_shadow_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        inner_shadow_layer.paste((0, 0, 0, 255), mask=inner_alpha)

        btn_mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(btn_mask).rounded_rectangle([0, 0, S-1, S-1], R, fill=255)
        clipped_shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        clipped_shadow.paste(inner_shadow_layer, mask=btn_mask)
        img = Image.alpha_composite(img, clipped_shadow)

        # 2. Subtle micro-border outline
        border_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        bd = ImageDraw.Draw(border_layer)
        bd.rounded_rectangle([0, 0, S-1, S-1], R, outline=(255, 255, 255, 20), width=2)
        img = Image.alpha_composite(img, border_layer)
        return img

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

        if not fill_hex or not isinstance(fill_hex, str):
            fill_hex = BG_CARD if isinstance(BG_CARD, str) else "#2B2B2B"

        cache_key = (mdi_name, fill_hex, ring_hex, icon_color, app_icon_path, icon_scale)
        cached = self._tile_cache.get(cache_key)
        if cached is not None:
            return cached

        if fill_hex == "RAINBOW":
            return self._make_rainbow_tile(mdi_name, ring_hex, icon_color, app_icon_path,
                                           icon_scale, _T, _CR, S, R, bw, cache_key)

        frgb = self._parse_hex(fill_hex, default=(43, 43, 43))
        brgb = self._parse_hex(BG, default=(12, 13, 15))
        if icon_color:
            ic_rgb = icon_color
        else:
            lum = (frgb[0] * 299 + frgb[1] * 587 + frgb[2] * 114) / 1000.0
            ic_rgb = (10, 10, 10) if lum >= 150 else (255, 255, 255)

        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, S-1, S-1], R, fill=(*frgb, 255))
        img = self._apply_flat_tile_shading(img, S, R)

        # Icon — app icon (extracted via PowerShell) or MDI fallback
        icon_drawn = False
        if app_icon_path:
            from win_platform import _extract_via_ps
            app_img = _extract_via_ps(app_icon_path, size=_T)
            if app_img:
                bbox = app_img.getbbox()
                if bbox:
                    app_img = app_img.crop(bbox)
                icon_sz = int(S * icon_scale)
                app_img_s = app_img.resize((icon_sz, icon_sz), Image.LANCZOS)
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
            rrgb = self._parse_hex(ring_hex, default=(72, 178, 233))
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
        brgb = self._parse_hex(BG, default=(12, 13, 15))
        if icon_color:
            ic_rgb = icon_color
        else:
            ic_rgb = (10, 10, 10)
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
        img = self._apply_flat_tile_shading(_clipped, S, R)
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
            rrgb = self._parse_hex(ring_hex, default=(72, 178, 233))
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

    def _on_master_volume_change(self):
        try:
            import win_volume
            win_volume.set_master_volume(self._master_var.get())
        except Exception:
            pass

    def _refresh_master_ui(self):
        try:
            import win_volume
            state = win_volume.get_master_state()
        except Exception:
            state = {"volume": None}
        vol = state.get("volume")
        if isinstance(vol, int) and self._master_var.get() != vol:
            self._master_var.set(vol)

    def _refresh_volume_ui(self):
        try:
            import win_volume
            state = win_volume.get_active_app_state()
        except Exception:
            state = {"app": None, "volume": None}
        vol = state.get("volume")
        if isinstance(vol, int):
            self._volume_enabled = True
            if self._volume_var.get() != vol:
                self._volume_var.set(vol)
        else:
            self._volume_enabled = False

    def _refresh_mixer_ui(self):
        """Refresh per-app volume rows from win_volume.list_sessions()."""
        frame = getattr(self, "_mixer_frame", None)
        if not getattr(self, "_mixer_enabled", False):
            if frame is not None:
                for w in frame.winfo_children():
                    w.place_forget()
                    w.destroy()
            self._mixer_sig = None
            self._mixer_rows = []
            self._mixer_h = 0
            return
        if frame is None:
            return
        try:
            import win_volume
            sessions = win_volume.list_sessions()
        except Exception:
            sessions = []
        key = tuple((s.get("pid"), s.get("volume"), s.get("exe") or s.get("name")) for s in sessions)
        if key == self._mixer_sig:
            return
        self._mixer_sig = key
        for w in frame.winfo_children():
            w.destroy()
        self._mixer_rows = []

        _LABEL_H, _SLIDER_H = 12, 24
        y = 0
        accent_rgb, neon_rgb, accent_hex, neon_hex, theme_bg = self._get_theme_colors()[:5]
        for s in sessions[:10]:
            pid = s.get("pid")
            name = (s.get("exe") or s.get("name") or "Application").upper()
            vol = s.get("volume")
            var = tk.IntVar(value=vol if isinstance(vol, int) else 0)
            lbl = tk.Label(frame, text=name, font=("Segoe UI", 7, "bold"),
                           fg="#FFFFFF", bg=theme_bg, anchor="w")
            lbl.place(x=0, y=y, width=190, height=_LABEL_H)
            y += _LABEL_H
            sl = StepSlider(frame, list(range(101)), var, bg=theme_bg,
                            on_change=lambda p=pid, v=var: self._set_mixer_volume(p, v.get()))
            sl.set_theme_colors(neon_rgb, accent_rgb, bg=theme_bg)
            sl.place(x=0, y=y, width=190, height=_SLIDER_H)
            y += _SLIDER_H + 2
            self._mixer_rows.append({"pid": pid, "var": var, "slider": sl, "label": lbl})

        if not self._mixer_rows:
            empty = tk.Label(frame, text="NO APPS PLAYING", font=("Segoe UI", 7, "bold"),
                             fg=FG_DIM, bg=theme_bg, anchor="w")
            empty.place(x=0, y=0, width=190, height=_LABEL_H)
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
        path = ""
        if self.app and getattr(self.app, "cfg", None):
            path = (self.app.cfg.get("media_player_path") or "").strip()
        if not path:
            try:
                from config import load_config
                path = (load_config().get("media_player_path") or "").strip()
            except Exception:
                pass
        if not path:
            return
        import threading, os, subprocess
        from win_platform import bring_media_player_to_foreground
        def _launch():
            try:
                if not bring_media_player_to_foreground(path):
                    if path:
                        if hasattr(os, "startfile"):
                            os.startfile(path)
                        else:
                            subprocess.Popen([path], shell=False)
            except Exception as ex:
                log.warning("media eject launch failed: %s", ex)
        threading.Thread(target=_launch, daemon=True).start()

    def _build_tiles(self):
        # Destroy previous tile widgets if re-building (e.g. reload_theme)
        for attr in ("_sep_sliders", "_lbl_volume_title", "_slider_volume",
                     "_lbl_master_title", "_slider_master", "_lbl_brightness_title",
                     "_slider_brightness", "_mixer_frame", "_sep_utility",
                     "_utility_frame", "_sep_core", "_core_frame"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
                setattr(self, attr, None)

        self._tile_refs = []
        _W = 190
        _X = (self.W - _W) // 2
        _T, _GAP = 40, 10
        _TOTAL = 4 * _T + 3 * _GAP

        # Widgets created here; _reflow_panel places them and sets height.
        self._sep_sliders = tk.Frame(self._win, bg=BG_CARD, height=1)

        accent_rgb, neon_rgb, accent_hex, neon_hex, theme_bg = self._get_theme_colors()[:5]

        self._lbl_volume_title = tk.Label(
            self._win, text="APP VOLUME", font=("Segoe UI", 7, "bold"),
            fg="#FFFFFF", bg=theme_bg, anchor="w")
        self._volume_enabled = False
        self._volume_var = tk.IntVar(value=0)
        self._slider_volume = StepSlider(
            self._win, list(range(101)), self._volume_var, bg=theme_bg,
            on_change=self._on_volume_change,
        )
        self._slider_volume.set_theme_colors(neon_rgb, accent_rgb, bg=theme_bg)

        self._lbl_master_title = tk.Label(
            self._win, text="MASTER VOLUME", font=("Segoe UI", 7, "bold"),
            fg="#FFFFFF", bg=theme_bg, anchor="w")
        self._master_var = tk.IntVar(value=0)
        self._slider_master = StepSlider(
            self._win, list(range(101)), self._master_var, bg=theme_bg,
            on_change=self._on_master_volume_change,
        )
        self._slider_master.set_theme_colors(neon_rgb, accent_rgb, bg=theme_bg)

        self._lbl_brightness_title = tk.Label(
            self._win, text="DISPLAY BRIGHTNESS", font=("Segoe UI", 7, "bold"),
            fg="#FFFFFF", bg=theme_bg, anchor="w")
        self._brightness_var = tk.IntVar(value=self.app.cfg.get("brightness", DEFAULT_BRIGHTNESS))
        self._slider_brightness = StepSlider(
            self._win, list(range(5)), self._brightness_var, bg=theme_bg,
            on_change=self._on_brightness_change,
        )
        self._slider_brightness.set_theme_colors(neon_rgb, accent_rgb, bg=theme_bg)

        self._mixer_enabled = False
        self._mixer_h = 0
        self._mixer_sig = None
        self._mixer_rows = []
        self._mixer_frame = tk.Frame(self._win, bg=BG)

        self._sep_utility = tk.Frame(self._win, bg=BG_CARD, height=1)
        self._utility_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        self._utility_frame.pack_propagate(False)
        self._utility_tile_refs = []
        self._render_utility_row()

        self._sep_core = tk.Frame(self._win, bg=BG_CARD, height=1)
        self._core_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        self._core_frame.pack_propagate(False)

        # Initialise toggle state before rendering so _is_core_active is correct
        self._pc_display_on = self.app.cfg.get("pc_stats_manual", False)
        self._overlay_on = False
        self._mic_muted = False
        self._btn_overlay = None
        self._btn_display = None
        self._btn_mic = None
        self._ov_tiles = None
        self._core_tile_refs = []

        self._render_core_row()

        if self._pc_display_on:
            self.app._toggle_pc_stats(True)

    def _on_gauge_click(self, e):
        if not self._overlay_on:
            self._overlay_on = True
            self.set_overlay_state(True)
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
                    fps_max = getattr(s, "refresh_rate", None) or getattr(s, "fps_max", 60) or 60
                    if self._gauge_fps.max_value != fps_max:
                        self._gauge_fps.set_max(fps_max)
                    cpu_max = getattr(s, "cpu_temp_max", 100)
                    gpu_max = getattr(s, "gpu_temp_max", 100)
                    cpu_unit = getattr(s, "cpu_temp_unit", "\u00b0C").replace("\u00b0", "")
                    gpu_unit = getattr(s, "gpu_temp_unit", "\u00b0C").replace("\u00b0", "")
                    if self._gauge_cpu.max_value != cpu_max:
                        self._gauge_cpu.set_max(cpu_max)
                    if self._gauge_gpu.max_value != gpu_max:
                        self._gauge_gpu.set_max(gpu_max)
                    if self._gauge_cpu.unit != cpu_unit:
                        self._gauge_cpu.set_unit(cpu_unit)
                    if self._gauge_gpu.unit != gpu_unit:
                        self._gauge_gpu.set_unit(gpu_unit)
                except Exception:
                    pass
                break

        if self._visible:
            self._refresh_volume_ui()
            self._refresh_master_ui()
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

        # Instant display reveal (< 1ms)
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()
        self._visible = True

        # Snap mouse cursor to center of panel
        px = self._win.winfo_x()
        py = self._win.winfo_y()
        pw = self._win.winfo_width()
        ph = self._win.winfo_height()
        ctypes.windll.user32.SetCursorPos(px + pw // 2, py + ph // 2)

        # Asynchronously sync audio and check theme mutations on idle
        self._win.after_idle(self._async_show_sync)

    def _async_show_sync(self):
        if not self._visible:
            return
        self.reload_theme(force=False)
        self._refresh_volume_ui()
        self._refresh_master_ui()
        self._refresh_mixer_ui()

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
        if self._sending_hotkey or self._pin_pinned or self._picker_active:
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
