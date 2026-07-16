"""Floating stopwatch / countdown overlay — dismissable, reappears on timer end."""

import ctypes
import threading
import time
import tkinter as tk

import pystray
from PIL import Image, ImageDraw

from constants import BG, BG_CARD, NEON, FG_DIM, FONT_SM
from serial_comm import serial_sender

_ALPHA         = 0.88
_W             = 230
_START_BG      = "#1e3a4a"
_STOP_BG       = "#3a1e1e"
_WARN_SECS     = 10
_TONE_HZ_LOW   = 500
_TONE_HZ_HIGH  = 2000


def _make_tray_image(size=32):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=6,
                        fill=(72, 178, 233, 255))
    cx = cy = size // 2
    r = size // 2 - 6
    d.arc([cx - r, cy - r, cx + r, cy + r], -90, 270,
          fill=(255, 255, 255, 255), width=3)
    d.line([cx, cy - r + 2, cx, cy + r - 3],
           fill=(255, 255, 255, 255), width=2)
    d.line([cx, cy, cx + r - 3, cy],
           fill=(255, 255, 255, 255), width=2)
    return img


class StopwatchOverlay:
    def __init__(self, parent):
        self._parent    = parent
        self._elapsed   = 0.0
        self._running   = False
        self._start_t   = 0.0
        self._visible   = False
        self._countdown = False
        self._cd_mins   = 5
        self._cd_secs   = 0

        self._win         = None
        self._time_var    = None
        self._cd_mins_var = None
        self._cd_secs_var = None
        self._start_lbl   = None
        self._run_frame   = None
        self._edit_frame  = None
        self._mode_lbl    = None
        self._mode_photos = {}
        self._last_beep_sec   = -1
        self._countdown_done  = False
        self._drag_x = self._drag_y = self._drag_ox = self._drag_oy = None
        self._tray_icon = None

    def is_countdown(self):
        return self._countdown

    def start_countdown(self):
        if not self._countdown:
            self._toggle_mode()

    def toggle(self):
        if self._visible:
            self._hide()
        else:
            self._show()

    def _build(self):
        win = tk.Toplevel(self._parent)
        win.wm_overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", _ALPHA)
        win.configure(bg=BG_CARD)
        self._win = win

        self._time_var    = tk.StringVar(value="00:00.0")
        self._cd_mins_var = tk.StringVar(value=f"{self._cd_mins:02d}")
        self._cd_secs_var = tk.StringVar(value=f"{self._cd_secs:02d}")

        self._run_frame = tk.Frame(win, bg=BG_CARD)
        time_lbl = tk.Label(self._run_frame, textvariable=self._time_var,
                            bg=BG_CARD, fg=NEON,
                            font=("Segoe UI", 34, "bold"), padx=16, pady=4,
                            cursor="fleur")
        time_lbl.pack(fill="x")
        self._bind_drag(self._run_frame)
        self._bind_drag(time_lbl)

        self._edit_frame = tk.Frame(win, bg=BG_CARD)
        self._build_edit_frame()

        bar = tk.Frame(win, bg=BG, padx=10, pady=3)
        bar.pack(side="bottom", fill="x")

        self._start_lbl = tk.Label(
            bar, text="START", bg=_START_BG, fg=NEON,
            font=("Segoe UI", 9, "bold"), padx=12, pady=3, cursor="hand2")
        self._start_lbl.pack(side="left", padx=(0, 6))
        self._start_lbl.bind("<Button-1>", lambda e: self._toggle_running())

        reset_lbl = tk.Label(
            bar, text="RESET", bg=BG, fg=FG_DIM,
            font=("Segoe UI", 9, "bold"), padx=12, pady=3, cursor="hand2")
        reset_lbl.pack(side="left", padx=(0, 6))
        reset_lbl.bind("<Button-1>", lambda e: self._reset())

        self._mode_lbl = tk.Label(bar, bg=BG, cursor="hand2", padx=6, pady=3)
        self._mode_lbl.pack(side="left")
        self._mode_lbl.bind("<Button-1>", lambda e: self._toggle_mode())
        self._load_mode_icons()
        self._update_mode_icon()

        close_lbl = tk.Label(bar, text="✕", bg=BG, fg=FG_DIM,
                             font=FONT_SM, cursor="hand2")
        close_lbl.pack(side="right", padx=(0, 2))
        close_lbl.bind("<Button-1>", lambda e: self._hide())

        self._switch_display()

        win.update_idletasks()
        sx = win.winfo_screenwidth()
        sy = win.winfo_screenheight()
        w  = max(_W, win.winfo_reqwidth())
        h  = win.winfo_reqheight()
        win.geometry(f"{w}x{h}+{sx - w - 20}+{(sy - h) // 2}")

    def _build_edit_frame(self):
        ef = self._edit_frame

        row = tk.Frame(ef, bg=BG_CARD, padx=16, pady=4)
        row.pack()
        self._bind_drag(row)

        def _spin_btn(parent, text, cmd):
            lbl = tk.Label(parent, text=text, bg=BG_CARD, fg=NEON,
                           font=("Segoe UI", 10), cursor="hand2", pady=0)
            lbl.pack()
            def _handler(e, c=cmd):
                c()
                return "break"
            lbl.bind("<Button-1>", _handler)

        mf = tk.Frame(row, bg=BG_CARD)
        mf.pack(side="left")
        _spin_btn(mf, "\u25b2", lambda: self._adj_mins(1))
        m_disp = tk.Label(mf, textvariable=self._cd_mins_var, bg=BG_CARD, fg=NEON,
                          font=("Segoe UI", 34, "bold"), width=2, cursor="fleur")
        m_disp.pack(pady=0)
        m_disp.bind("<MouseWheel>",
                    lambda e: self._adj_mins(1 if e.delta > 0 else -1))
        self._bind_drag(m_disp)
        _spin_btn(mf, "\u25bc", lambda: self._adj_mins(-1))

        tk.Label(row, text=":", bg=BG_CARD, fg=FG_DIM,
                 font=("Segoe UI", 34, "bold")).pack(side="left", padx=4)

        sf = tk.Frame(row, bg=BG_CARD)
        sf.pack(side="left")
        _spin_btn(sf, "\u25b2", lambda: self._adj_secs(1))
        s_disp = tk.Label(sf, textvariable=self._cd_secs_var, bg=BG_CARD, fg=NEON,
                          font=("Segoe UI", 34, "bold"), width=2, cursor="fleur")
        s_disp.pack(pady=0)
        s_disp.bind("<MouseWheel>",
                    lambda e: self._adj_secs(1 if e.delta > 0 else -1))
        self._bind_drag(s_disp)
        _spin_btn(sf, "\u25bc", lambda: self._adj_secs(-1))

    def _bind_drag(self, widget):
        widget.bind("<Button-1>",        self._drag_start)
        widget.bind("<B1-Motion>",       self._drag_move)
        widget.bind("<ButtonRelease-1>", self._drag_end)

    def _load_mode_icons(self):
        try:
            from mdi_icons import render_tk
            fg = tuple(int(FG_DIM.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            sw = render_tk("timer",        18, fg) or render_tk("timer-outline", 18, fg)
            cd = render_tk("timer-sand",  18, fg) or render_tk("timer",         18, fg)
            if sw:
                self._mode_photos["stopwatch"] = sw
            if cd:
                self._mode_photos["countdown"] = cd
        except Exception:
            pass

    def _update_mode_icon(self):
        if not self._mode_lbl:
            return
        key   = "stopwatch" if not self._countdown else "countdown"
        photo = self._mode_photos.get(key)
        if photo:
            self._mode_lbl.configure(image=photo, text="", compound="none")
        else:
            self._mode_lbl.configure(
                image="",
                text="\u23f1" if not self._countdown else "\u23f3",
                fg=FG_DIM, font=("Segoe UI", 14))

    def _toggle_mode(self):
        if self._running:
            return
        self._countdown       = not self._countdown
        self._elapsed         = 0.0
        self._start_t         = 0.0
        self._last_beep_sec   = -1
        self._countdown_done  = False
        self._update_mode_icon()
        self._update_time_var()
        self._switch_display()

    def _switch_display(self):
        show_edit = self._countdown and not self._running
        if show_edit:
            self._run_frame.pack_forget()
            self._edit_frame.pack(fill="x")
        else:
            self._edit_frame.pack_forget()
            self._run_frame.pack(fill="x")

    def _show(self):
        self._remove_tray_icon()
        if self._win is None:
            self._build()
        else:
            try:
                self._win.deiconify()
                self._win.lift()
            except Exception:
                self._build()
        self._visible = True
        self._tick()
        self._topmost_tick()

    def _ensure_visible(self):
        self._remove_tray_icon()
        self._visible = True
        if self._win:
            try:
                self._win.deiconify()
                self._win.lift()
            except Exception:
                pass

    def _topmost_tick(self):
        if not self._visible:
            return
        try:
            if self._win and self._win.winfo_exists():
                _HWND_TOPMOST = -1
                _SWP_FLAGS    = 0x0001 | 0x0002 | 0x0010
                hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id()) or self._win.winfo_id()
                ctypes.windll.user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_FLAGS)
        except Exception:
            pass
        self._win.after(2000, self._topmost_tick)

    def _hide(self):
        self._visible = False
        if self._win:
            try:
                self._win.withdraw()
            except Exception:
                pass
        if self._running:
            self._ensure_tray_icon()
        else:
            self._remove_tray_icon()
            serial_sender.set_live("stopwatch", "")

    @property
    def _countdown_target(self):
        return self._cd_mins * 60 + self._cd_secs

    def _adj_mins(self, delta):
        if self._running:
            return
        self._cd_mins = max(0, min(99, self._cd_mins + delta))
        if self._cd_mins_var:
            self._cd_mins_var.set(f"{self._cd_mins:02d}")

    def _adj_secs(self, delta):
        if self._running:
            return
        self._cd_secs = max(0, min(59, self._cd_secs + delta))
        if self._cd_secs_var:
            self._cd_secs_var.set(f"{self._cd_secs:02d}")

    def _toggle_running(self):
        if self._running:
            self._elapsed      += time.time() - self._start_t
            self._running       = False
            self._last_beep_sec = -1
            if not self._visible:
                self._remove_tray_icon()
                serial_sender.set_live("stopwatch", "")
            if self._start_lbl:
                self._start_lbl.configure(text="START", fg=NEON, bg=_START_BG)
            self._switch_display()
        else:
            if self._countdown and self._countdown_target == 0:
                return
            self._start_t         = time.time()
            self._running         = True
            self._last_beep_sec   = -1
            self._countdown_done  = False
            if self._start_lbl:
                self._start_lbl.configure(text="STOP", fg="#ff5050", bg=_STOP_BG)
            self._switch_display()

    def _reset(self):
        self._elapsed         = 0.0
        self._running         = False
        self._start_t         = 0.0
        self._last_beep_sec   = -1
        self._countdown_done  = False
        if not self._visible:
            self._remove_tray_icon()
            serial_sender.set_live("stopwatch", "")
        if self._start_lbl:
            self._start_lbl.configure(text="START", fg=NEON, bg=_START_BG)
        self._update_time_var()
        self._switch_display()

    def _beep(self, secs_remaining):
        t    = 1.0 - secs_remaining / _WARN_SECS
        freq = int(_TONE_HZ_LOW * (_TONE_HZ_HIGH / _TONE_HZ_LOW) ** t)
        serial_sender.set_live("tone", str(freq))

    def _update_time_var(self):
        if not self._time_var:
            return
        if self._countdown:
            total = float(self._countdown_target)
        else:
            total = self._elapsed
        self._time_var.set(self._format(total))

    @staticmethod
    def _format(total):
        mins   = int(total) // 60
        secs   = int(total) % 60
        tenths = int(total * 10) % 10
        if mins >= 60:
            h = mins // 60
            m = mins % 60
            return f"{h:02d}:{m:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}.{tenths}"

    def _tick(self):
        if not self._running and not self._visible:
            return
        alive = self._win and self._win.winfo_exists() if self._win else False

        elapsed = self._elapsed + (time.time() - self._start_t if self._running else 0.0)

        if self._countdown:
            total = max(0.0, self._countdown_target - elapsed)

            if self._running and total <= _WARN_SECS:
                sec = int(total)
                if sec != self._last_beep_sec:
                    self._last_beep_sec = sec
                    self._beep(sec)

            if self._running and total < 0.05:
                self._elapsed         = 0.0
                self._running         = False
                self._start_t         = 0.0
                self._last_beep_sec   = -1
                self._countdown_done  = True
                serial_sender.set_live("stopwatch", "done")
                self._remove_tray_icon()
                if self._start_lbl:
                    self._start_lbl.configure(text="START", fg=NEON, bg=_START_BG)
                self._switch_display()
                self._ensure_visible()
        else:
            total = elapsed

        if alive and not (self._countdown and not self._running):
            self._time_var.set(self._format(total))

        if self._running and not self._countdown_done:
            prefix = "c:" if self._countdown else "s:"
            serial_sender.set_live("stopwatch", prefix + self._format(total))

        ms = 100
        if self._running and not self._visible:
            ms = 1000
        if alive:
            self._win.after(ms, self._tick)
        elif self._running:
            threading.Timer(ms / 1000.0, self._tick).start()

    # ── Tray icon ─────────────────────────────────────────────

    def _ensure_tray_icon(self):
        if self._tray_icon is not None:
            return
        def _on_click(*_):
            self._show()
        self._tray_icon = pystray.Icon(
            "Iris-Timer",
            _make_tray_image(32),
            self._time_var.get() if self._time_var else "Timer",
            menu=pystray.Menu(
                pystray.MenuItem("Show", _on_click, default=True),
                pystray.MenuItem("Reset", lambda *_: self._reset()),
            ),
        )
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _remove_tray_icon(self):
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _drag_start(self, e):
        self._drag_x  = e.x_root
        self._drag_y  = e.y_root
        self._drag_ox = self._win.winfo_x()
        self._drag_oy = self._win.winfo_y()

    def _drag_move(self, e):
        if self._drag_x is None:
            return
        dx = e.x_root - self._drag_x
        dy = e.y_root - self._drag_y
        self._win.geometry(f"+{self._drag_ox + dx}+{self._drag_oy + dy}")

    def _drag_end(self, e):
        self._drag_x = None
