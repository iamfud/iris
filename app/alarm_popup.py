"""Iris — iPhone-styled alarm popup (rounded rect, dark, always-on-top)."""

import ctypes
import tkinter as tk

import logging

from constants import BG, BG_CARD, NEON

log = logging.getLogger("iris.alarm_popup")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WS_EX_LAYERED = 0x80000
LWA_ALPHA = 0x2
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
GWL_EXSTYLE = -20


def _apply_style(hwnd, alpha=0.92):
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


class AlarmPopup:
    W = 220
    RADIUS = 24
    MIN_H = 130
    MAX_H = 320

    def __init__(self, root, on_dismiss, on_snooze):
        self._on_dismiss = on_dismiss
        self._on_snooze = on_snooze

        self._win = tk.Toplevel(root)
        self._win.title("Iris Alarm")
        self._win.overrideredirect(True)
        self._win.configure(bg=BG)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._base_x = sw - self.W - 20
        self._base_y = sh - 80

        hwnd = int(self._win.winfo_id())
        _apply_style(hwnd)
        self._win.bind("<Map>", self._on_map)
        self._win.bind("<Escape>", lambda e: self._on_dismiss())

        self._build()
        self._win.withdraw()

    def _on_map(self, event):
        self._win.after_idle(self._apply_region)

    def _apply_region(self):
        hwnd = int(self._win.winfo_id())
        w = self._win.winfo_width()
        h = self._win.winfo_height()
        if w > 1 and h > 1:
            _set_round_rect(hwnd, w, h, self.RADIUS)

    def _build(self):
        bw, bh, gap = 88, 40, 10
        wrap_w = self.W - 32

        self._lbl_msg = tk.Label(
            self._win, text="", font=("Segoe UI", 13, "bold"),
            fg=NEON, bg=BG, wraplength=wrap_w, justify="center", anchor="center")

        self._sep = tk.Frame(self._win, bg=BG_CARD, height=1)

        self._btn_dismiss = tk.Button(
            self._win, text="DISMISS", font=("Segoe UI", 10, "bold"),
            fg="#fff", bg="#c0392b", activebackground="#e74c3c",
            activeforeground="#fff",
            relief="flat", bd=0, padx=0, pady=0, cursor="hand2",
            command=self._on_dismiss)

        self._btn_snooze = tk.Button(
            self._win, text="SNOOZE", font=("Segoe UI", 10, "bold"),
            fg="#fff", bg="#27ae60", activebackground="#2ecc71",
            activeforeground="#fff",
            relief="flat", bd=0, padx=0, pady=0, cursor="hand2",
            command=self._on_snooze)

        self._bw, self._bh, self._gap = bw, bh, gap

    def show(self, message):
        self._lbl_msg.config(text=message or "ALARM!")
        self._win.update_idletasks()

        msg_h = self._lbl_msg.winfo_reqheight()
        pad_top, pad_bot = 15, 15
        sep_gap = 10
        total_h = pad_top + msg_h + sep_gap + 1 + sep_gap + self._bh + pad_bot
        total_h = max(self.MIN_H, min(total_h, self.MAX_H))

        x = self._base_x
        y = self._base_y - total_h
        self._win.geometry(f"{self.W}x{total_h}+{x}+{y}")

        sep_y = pad_top + msg_h + sep_gap
        btn_y = sep_y + 1 + sep_gap

        self._lbl_msg.place(x=16, y=pad_top, width=self.W - 32, height=msg_h)
        self._sep.place(x=15, y=sep_y, width=self.W - 30)
        self._btn_dismiss.place(x=16, y=btn_y, width=self._bw, height=self._bh)
        self._btn_snooze.place(x=16 + self._bw + self._gap, y=btn_y, width=self._bw, height=self._bh)

        self._win.deiconify()
        self._win.update_idletasks()
        self._apply_region()
        self._win.lift()
        self._win.focus_force()

    def hide(self):
        self._win.withdraw()
