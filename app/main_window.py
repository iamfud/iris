"""Iris — iPhone-shaped overlay main window."""

import logging
import time as _time
import tkinter as tk
import ctypes
import ctypes.wintypes

from PIL import Image, ImageDraw, ImageTk

from constants import BG, BG_CARD, FG, FG_DIM, NEON, BUTTON
from widgets import CircularGauge, StepSlider
import mdi_icons

log = logging.getLogger("iris.main_window")


def _find_ha_url(cfg):
    """Best-effort HA base URL from config."""
    raw = (cfg.get("ha_url") or "").strip().rstrip("/")
    return raw or None

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_ulong]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

# SendInput structures
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint


def _send_keys_sendinput(vk_codes, key_up=False):
    """Send keyboard events via SendInput."""
    n = len(vk_codes)
    arr = (INPUT * n)()
    for i, vk in enumerate(vk_codes):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki.wVk = vk
        arr[i].ki.wScan = 0
        arr[i].ki.dwFlags = KEYEVENTF_KEYUP if key_up else 0
        arr[i].ki.time = 0
        arr[i].ki.dwExtraInfo = None
    return user32.SendInput(n, arr, ctypes.sizeof(INPUT))


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
    H = 504
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

        self._win = tk.Toplevel(root)
        self._win.title("Iris")
        self._win.overrideredirect(True)
        self._win.configure(bg=BG)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        x = self._cfg.get("panel_x") or sw - self.W - 100
        y = self._cfg.get("panel_y") or sh - self.H - 100
        self._win.geometry(f"{self.W}x{self.H}+{x}+{y}")

        hwnd = int(self._win.winfo_id())
        self._hwnd = hwnd
        _apply_window_style(hwnd, self.ALPHA)

        self._win.bind("<Map>", self._on_map)
        self._win.bind("<Escape>", lambda e: self.hide())
        self._win.bind("<FocusOut>", self._on_focusout)

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

        tk.Frame(self._win, bg=BG_CARD, height=1).place(
            x=15, y=36 + gauge_size + 10 + 5, width=190)

        self._build_button_panel()
        self._build_tiles()
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
        self._cfg["panel_x"] = self._win.winfo_x()
        self._cfg["panel_y"] = self._win.winfo_y()
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

    def _current_buttons(self):
        """Return the list of buttons to render at the current nav level."""
        if not self._btn_nav:
            return self.app.cfg.get("ha_board") or []
        return (self._btn_nav[-1].get("children") or [])

    def _render_buttons(self):
        for w in self._btn_inner.winfo_children():
            w.destroy()
        self._btn_tile_refs.clear()

        buttons = self._current_buttons()
        _T, _GAP = 40, 10
        _W = 190
        _COLS = 4
        row_offset = 0

        # Back button if in a sub-panel
        if self._btn_nav:
            parent = self._btn_nav[-1]
            back_img = self._make_tile_photo("arrow-left", BUTTON)
            self._btn_tile_refs.append(back_img)
            back_btn = tk.Label(self._btn_inner, image=back_img, bg=BG, cursor="hand2",
                                padx=0, pady=0, borderwidth=0)
            back_btn.place(x=0, y=0)
            back_btn.bind("<Button-1>", lambda e: self.btn_nav_pop())
            back_btn.bind("<MouseWheel>", self._on_btn_wheel)

            back_lbl = tk.Label(self._btn_inner, text=parent.get("name",""),
                                font=("Segoe UI", 8), fg=NEON, bg=BG, anchor="w")
            back_lbl.place(x=_T + _GAP, y=0, width=_W - _T - _GAP, height=_T)
            back_lbl.bind("<Button-1>", lambda e: self.btn_nav_pop())
            back_lbl.bind("<MouseWheel>", self._on_btn_wheel)

            row_offset = 1

        # "+" empty-state prompt (only when no buttons exist at this level)
        if not buttons:
            plus_img = self._make_tile_photo("plus", BG_CARD)
            self._btn_tile_refs.append(plus_img)
            plus_btn = tk.Label(self._btn_inner, image=plus_img, bg=BG, cursor="hand2",
                                padx=0, pady=0, borderwidth=0)
            plus_btn.place(x=0, y=row_offset * (_T + _GAP))
            plus_btn.bind("<Button-1>", lambda e: self.app._open_settings(tab=2))
            plus_btn.bind("<MouseWheel>", self._on_btn_wheel)
            plus_tip = tk.Label(self._btn_inner, text="Add",
                                font=("Segoe UI", 6), fg=FG, bg=BG)
            plus_tip.place(x=0, y=row_offset * (_T + _GAP) + _T - 2, width=_T, height=12)
            plus_tip.bind("<MouseWheel>", self._on_btn_wheel)

        max_row = row_offset

        for i, slot in enumerate(buttons):
            if slot is None:
                continue
            col = i % _COLS
            row = row_offset + i // _COLS
            max_row = max(max_row, row)

            icon_name = slot.get("icon") or "help-circle"
            fill = slot.get("color") or BG_CARD
            name = slot.get("name") or ""
            app_icon = slot.get("app_icon_path") or (slot.get("shortcut_path") if slot.get("type") in ("SHORTCUT", "GROUP") else None)

            img = self._make_tile_photo(icon_name, fill, app_icon_path=app_icon)
            self._btn_tile_refs.append(img)

            btn = tk.Label(self._btn_inner, image=img, bg=BG, cursor="hand2",
                           padx=0, pady=0, borderwidth=0)
            btn.place(x=col * (_T + _GAP), y=row * (_T + _GAP))
            btn.bind("<MouseWheel>", self._on_btn_wheel)

            def _handler(s=slot):
                return lambda e, s=s: self._on_button_action(s)
            btn.bind("<Button-1>", _handler())

        nrows = max_row + 1
        self._btn_inner.configure(height=nrows * (_T + _GAP) + _GAP)

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
                    target=lambda: subprocess.Popen(path, shell=True),
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
                    target=lambda: subprocess.Popen(path, shell=True),
                    daemon=True,
                ).start()
        elif btype == "REST":
            self._do_rest_action(slot)
        elif btype == "OPENRGB":
            self._do_openrgb_action(slot)
        elif btype == "HOTKEY":
            self._do_hotkey_action(slot)
        elif btype == "STOPWATCH":
            self.app._toggle_stopwatch()

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
        profile = slot.get("openrgb_profile", "").strip()
        if not profile:
            return

        def _call():
            try:
                from providers.openrgb import OpenRGBProvider
                # Use SDK client directly
                from openrgb import OpenRGBClient as ORC
                cl = ORC()
                profiles = cl.load_profile(profile)
                if profiles:
                    cl.apply_profile(profiles[0])
                    log.info("OpenRGB profile '%s' applied", profile)
                cl.disconnect()
            except Exception as ex:
                log.warning("OpenRGB action failed: %s", ex)

        import threading
        threading.Thread(target=_call, daemon=True).start()

    def _do_hotkey_action(self, slot):
        keys = slot.get("keys", [])
        if not keys:
            return

        self._sending_hotkey = True
        hwnd = getattr(self, '_saved_foreground_hwnd', None)
        self.hide()

        try:
            if hwnd and user32.IsWindow(hwnd):
                ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            _time.sleep(0.2)

            def _vk_str(vk):
                if 48 <= vk <= 57:
                    return chr(vk)
                if 65 <= vk <= 90:
                    return chr(vk).lower()
                return {
                    8: "backspace", 9: "tab", 13: "enter", 16: "shift",
                    17: "ctrl", 18: "alt", 27: "esc", 32: "space",
                    33: "page up", 34: "page down", 35: "end", 36: "home",
                    37: "left", 38: "up", 39: "right", 40: "down",
                    45: "insert", 46: "delete", 91: "windows", 92: "windows",
                    112: "f1", 113: "f2", 114: "f3", 115: "f4",
                    116: "f5", 117: "f6", 118: "f7", 119: "f8",
                    120: "f9", 121: "f10", 122: "f11", 123: "f12",
                    144: "num lock", 186: ";", 187: "=", 188: ",",
                    189: "-", 190: ".", 191: "/", 192: "`",
                    219: "[", 220: "\\", 221: "]", 222: "'",
                }.get(vk)

            parts = [_vk_str(vk) for vk in keys if _vk_str(vk) is not None]
            if parts:
                import keyboard as _kb
                hotkey = "+".join(parts)
                _kb.press(hotkey)
                _time.sleep(0.15)
                _kb.release(hotkey)
                log.info("  Hotkey sent: %s", hotkey)
            else:
                log.warning("  No mapped keys for vk=%s", keys)
        except Exception as ex:
            log.error("Hotkey error: %s", ex)
        finally:
            self._win.after(200, lambda: setattr(self, '_sending_hotkey', False))

    # ── Tile photo cache ──────────────────────────────────────────
    _tile_cache = {}

    def _make_tile_photo(self, mdi_name, fill_hex, ring_hex=None, icon_color=None,
                         app_icon_path=None, icon_scale=0.7):
        """4× supersampled PIL tile → PhotoImage (rounded rect + icon).

        If *app_icon_path* is set and the file exists, the application icon
        extracted via the Windows shell API replaces the MDI vector icon.
        """
        _T, _CR = 40, 8
        S = _T * 4
        R = _CR * 4
        bw = 8

        cache_key = (mdi_name, fill_hex, ring_hex, icon_color, app_icon_path, icon_scale)
        cached = self._tile_cache.get(cache_key)
        if cached is not None:
            return cached

        frgb = tuple(int(fill_hex[i:i+2], 16) for i in (1, 3, 5))
        brgb = tuple(int(BG[i:i+2], 16) for i in (1, 3, 5))
        ic_rgb = icon_color or (224, 224, 224)

        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if ring_hex:
            rrgb = tuple(int(ring_hex[i:i+2], 16) for i in (1, 3, 5))
            draw.rounded_rectangle([0, 0, S-1, S-1], R, fill=(*rrgb, 255))
            draw.rounded_rectangle([bw, bw, S-1-bw, S-1-bw], max(0, R-bw), fill=(*frgb, 255))
        else:
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
                # Trim transparent padding, then fill the tile
                bbox = app_img.getbbox()
                if bbox:
                    app_img = app_img.crop(bbox)
                app_img = app_img.resize((_T, _T), Image.LANCZOS)
                tile = Image.new("RGBA", (_T, _T), (*brgb, 255))
                icon_layer = Image.new("RGBA", (_T, _T), (0, 0, 0, 0))
                icon_layer.paste(app_img, (0, 0), app_img)
                mask = Image.new("L", (_T, _T), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, _T-1, _T-1), _CR, fill=255)
                img = Image.composite(icon_layer, tile, mask)
                base = Image.new("RGB", (_T, _T), brgb)
                base.paste(img, mask=img.split()[3])
                photo = ImageTk.PhotoImage(base)
                self._tile_cache[cache_key] = photo
                return photo
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
        threading.Thread(target=lambda: subprocess.Popen(path, shell=True), daemon=True).start()

    def _build_tiles(self):
        self._tile_refs = []
        _W = 190                     # uniform content width
        _X = (self.W - _W) // 2      # left margin (15)
        _T, _GAP = 40, 10
        _TOTAL = 4 * _T + 3 * _GAP  # 190 — exactly matches _W
        _BY = self.H - 30 - _T      # tile top (30px from bottom to clear corner)

        # ════════════════════════════════════════════════════════════
        #  Display panel (top separator → title → slider)
        # ════════════════════════════════════════════════════════════

        # ── Display top separator ──
        tk.Frame(self._win, bg=BG_CARD, height=1).place(
            x=_X, y=_BY - 148, width=_W)

        # ── Title "Display" ──
        tk.Label(self._win, text="Display", font=("Segoe UI", 10),
                 fg=NEON, bg=BG, anchor="w").place(
            x=_X + 2, y=_BY - 143, width=_W - 2, height=16)

        # ── Brightness slider (5 steps via StepSlider) ──
        self._brightness_var = tk.IntVar(value=self.app.cfg.get("brightness", 3))
        self._slider_brightness = StepSlider(
            self._win, list(range(5)), self._brightness_var,
            on_change=self._on_brightness_change,
        )
        self._slider_brightness.place(x=_X, y=_BY - 123, width=_W)

        # ════════════════════════════════════════════════════════════
        #  Separator B — above media tiles (15px padding each side)
        # ════════════════════════════════════════════════════════════
        tk.Frame(self._win, bg=BG_CARD, height=1).place(
            x=_X, y=_BY - 80, width=_W)

        # ════════════════════════════════════════════════════════════
        #  Media controls row (back, play/pause, forward, eject)
        # ════════════════════════════════════════════════════════════

        _media_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        _media_frame.place(x=_X, y=_BY - 65)
        _media_frame.pack_propagate(False)

        _media_specs = [
            ("skip-previous", self._media_prev),
            ("play-pause",    self._media_play_pause),
            ("skip-next",     self._media_next),
            ("eject",         self._media_eject),
        ]

        for i, (icon, cb) in enumerate(_media_specs):
            imgs = self._make_tile_set(icon, icon_scale=0.52)
            btn = tk.Label(_media_frame, image=imgs[0], bg=BG, cursor="hand2",
                           padx=0, pady=0, borderwidth=0)
            btn.place(x=i * (_T + _GAP), y=0)
            btn.bind("<Enter>", lambda e, imgs_=imgs, b=btn: b.config(image=imgs_[1]))
            btn.bind("<Leave>", lambda e, imgs_=imgs, b=btn: b.config(image=imgs_[0]))
            btn.bind("<Button-1>", lambda e, c=cb: (c(), "break")[1])
            self._tile_refs.extend(imgs)

        # ════════════════════════════════════════════════════════════
        #  Separator A — between media & bottom tiles (15px each side)
        # ════════════════════════════════════════════════════════════
        tk.Frame(self._win, bg=BG_CARD, height=1).place(
            x=_X, y=_BY - 12, width=_W)

        # ════════════════════════════════════════════════════════════
        #  Bottom tile row (display toggle, overlay, settings, exit)
        # ════════════════════════════════════════════════════════════
        _tile_frame = tk.Frame(self._win, bg=BG, width=_TOTAL, height=_T)
        _tile_frame.place(x=_X, y=_BY)
        _tile_frame.pack_propagate(False)

        self._pc_display_on = self.app.cfg.get("pc_stats_manual", False)
        self._overlay_on = False

        # ── Tile 0: PC stats display toggle ──
        t0 = self._make_tile_set("monitor", icon_scale=0.52)
        self._btn_display = tk.Label(_tile_frame, image=t0[0], bg=BG, cursor="hand2",
                                     padx=0, pady=0, borderwidth=0)
        self._btn_display.place(x=0, y=0)

        def _enter0(e):
            self._btn_display.config(image=t0[3] if self._pc_display_on else t0[1])
        def _leave0(e):
            self._btn_display.config(image=t0[2] if self._pc_display_on else t0[0])
        def _click0(e):
            self._pc_display_on = not self._pc_display_on
            self._btn_display.config(image=t0[2] if self._pc_display_on else t0[0])
            self.app._toggle_pc_stats(self._pc_display_on)
            return "break"
        self._btn_display.bind("<Enter>", _enter0)
        self._btn_display.bind("<Leave>", _leave0)
        self._btn_display.bind("<Button-1>", _click0)

        if self._pc_display_on:
            self.app._toggle_pc_stats(True)

        # ── Tile 1: PC stats overlay toggle ──
        t1 = self._make_tile_set("speedometer", icon_scale=0.52)
        self._ov_tiles = t1
        self._btn_overlay = tk.Label(_tile_frame, image=t1[0], bg=BG, cursor="hand2",
                                     padx=0, pady=0, borderwidth=0)
        self._btn_overlay.place(x=1 * (_T + _GAP), y=0)

        def _enter1(e):
            self._btn_overlay.config(image=t1[3] if self._overlay_on else t1[1])
        def _leave1(e):
            self._btn_overlay.config(image=t1[2] if self._overlay_on else t1[0])
        def _click1(e):
            self._overlay_on = not self._overlay_on
            self._btn_overlay.config(image=t1[2] if self._overlay_on else t1[0])
            self.app._toggle_overlay(self._overlay_on)
            return "break"
        self._btn_overlay.bind("<Enter>", _enter1)
        self._btn_overlay.bind("<Leave>", _leave1)
        self._btn_overlay.bind("<Button-1>", _click1)

        # ── Tile 2: Settings (static) ──
        t2 = self._make_tile_set("cog", icon_scale=0.52)
        self._btn_settings = tk.Label(_tile_frame, image=t2[0], bg=BG, cursor="hand2",
                                      padx=0, pady=0, borderwidth=0)
        self._btn_settings.place(x=2 * (_T + _GAP), y=0)
        self._btn_settings.bind("<Enter>", lambda e: self._btn_settings.config(image=t2[1]))
        self._btn_settings.bind("<Leave>", lambda e: self._btn_settings.config(image=t2[0]))
        self._btn_settings.bind("<Button-1>", lambda e: self.app._open_settings() or "break")

        # ── Tile 3: Exit (static) ──
        t3 = self._make_tile_set("power", icon_scale=0.52)
        self._btn_exit = tk.Label(_tile_frame, image=t3[0], bg=BG, cursor="hand2",
                                  padx=0, pady=0, borderwidth=0)
        self._btn_exit.place(x=3 * (_T + _GAP), y=0)
        self._btn_exit.bind("<Enter>", lambda e: self._btn_exit.config(image=t3[1]))
        self._btn_exit.bind("<Leave>", lambda e: self._btn_exit.config(image=t3[0]))
        self._btn_exit.bind("<Button-1>", lambda e: (self.hide(), "break")[1])

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

        self._win.after(1000, self._update_status)

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self._saved_foreground_hwnd = user32.GetForegroundWindow()
        self._win.deiconify()
        self._win.update_idletasks()
        self._apply_region()
        self._win.lift()
        self._win.focus_force()
        self._visible = True

    def hide(self):
        self._win.withdraw()
        self._visible = False

    def _on_focusout(self, e):
        if not self._sending_hotkey and not self._pin_pinned:
            self.hide()

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
