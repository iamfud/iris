"""Settings dialog for Iris — tabbed interface with Features and Alarm tabs."""

import base64
import ctypes
import datetime
import io
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog

import mdi_icons
from config import config_path, load_config, save_config
try:
    from PIL import Image, ImageDraw, ImageTk as ITK
    _PIL = True
except ImportError:
    _PIL = False

from constants import APP_NAME, APP_VERSION, BG, BG_CARD, FG, FG_DIM, FONT_UI, NEON, NEON_DIM, NEON_GRN, NEON_RED, BUTTON, BORDER, DANGER, DANGER_HOVER, DEFAULT_CONFIG, FONT_SM, HA_PALETTE, format_keys
from styles import apply_dark_theme
from widgets import RoundedButton, DarkCombobox, TabBar, Toggle, IrisScrollbar, ColourPicker, ToolTip
from win_platform import scan_media_apps

log = logging.getLogger("iris.settings")


def _pick_next_alarm(alarms):
    now = datetime.datetime.now()

    def _secs_until(alarm):
        mask = alarm.get("days", 127)
        h, m = alarm["hour"], alarm["minute"]
        for offset in range(8):
            d = now + datetime.timedelta(days=offset)
            fw = (d.weekday() + 1) % 7
            if not (mask >> fw) & 1:
                continue
            t = d.replace(hour=h, minute=m, second=0, microsecond=0)
            if t > now:
                return (t - now).total_seconds()
        return float("inf")

    return min(alarms, key=_secs_until)

FEATURE_KEYS = [
    ("feature_time", "Time display"),
    ("feature_date", "Date (alternates with time)"),
    ("feature_minute_bar", "Minute bar"),
    ("feature_eyes", "Animated eyes"),
    ("feature_notifications", "Notifications"),
    ("night_mode_enabled", "Night mode"),
    ("temp_alert", "Temp alert"),
    ("pc_stats_enabled", "PC Stats"),
]

CLOCK_MODE_OPTIONS = ["Small Clock", "Large Clock", "Day Clock"]

def _dark_titlebar(hwnd):
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 19
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass


class SettingsDialog:
    def __init__(self, parent, serial_sender, shared_cfg=None, initial_tab=0):
        self._serial = serial_sender
        self._cfg = shared_cfg if shared_cfg is not None else load_config()
        self._vars = {}
        self._text_vars = {}
        self._suppress_apply = True

        apply_dark_theme(parent)

        self._win = tk.Toplevel(parent, bg=BG)
        self._win.title("Iris Settings")
        self._win.update_idletasks()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        ww, wh = 420, 560
        self._win.geometry(f"{ww}x{wh}+{sw - ww - 40}+{sh - wh - 130}")
        self._win.minsize(380, 480)
        self._win.resizable(True, True)
        self._win.attributes("-topmost", True)

        self._win.update()
        try:
            kid = int(self._win.winfo_id())
            hwnd = ctypes.windll.user32.GetParent(kid)
            if not hwnd:
                hwnd = kid
        except Exception:
            hwnd = int(self._win.winfo_id())
        _dark_titlebar(hwnd)

        outer = tk.Frame(self._win, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)

        self._tabs = TabBar(outer, on_select=self._on_tab_selected)
        t_feat = self._tabs.add("FEATURES")
        t_alarm = self._tabs.add("ALARM")
        t_btns = self._tabs.add("BUTTONS")
        t_about = self._tabs.add("ABOUT")

        self._tab_alarm_index = 1
        self._tab_buttons_index = 2
        self._alarm_built = False
        self._buttons_built = False

        self._build_features(t_feat)
        self._build_alarm(t_alarm)
        self._build_buttons(t_btns)
        self._build_about(t_about)

        self._apply_config_to_ui(self._cfg)
        self._suppress_apply = False
        self._apply()

        # Bottom bar with OK / Cancel (right-aligned, uniform across all tabs)
        btn_bar = tk.Frame(outer, bg=BG)
        btn_bar.pack(fill=tk.X, padx=16, pady=(0, 12))
        btn_bar.columnconfigure(0, weight=1)
        RoundedButton(btn_bar, text="CANCEL", command=self._win.destroy).grid(row=0, column=1, padx=(0, 6))
        RoundedButton(btn_bar, text="OK", command=self._ok).grid(row=0, column=2)

        if initial_tab:
            self._tabs.select(initial_tab)
        self._win.grab_set()

        self._detect_media_apps()

    # ── FEATURES TAB ──────────────────────────────────────────

    def _make_toggle_row(self, parent, label, var, bg=BG):
        row = tk.Frame(parent, bg=bg, cursor="hand2")
        row.columnconfigure(0, weight=1)
        text = tk.Label(row, text=label, bg=bg, fg=FG, anchor="w",
                        font=("Segoe UI", 9), cursor="hand2")
        text.grid(row=0, column=0, sticky="ew", padx=(8, 10), pady=2)
        tog = Toggle(row, var, bg=bg)
        tog.grid(row=0, column=1, padx=(0, 8), pady=1)

        def _flip(_=None):
            var.set(not var.get())
            return "break"
        row.bind("<Button-1>", _flip)
        text.bind("<Button-1>", _flip)
        return row, tog, text, _flip

    def _update_minute_bar_state(self):
        disabled = self._clock_mode_var.get() == "Large Clock"
        if not hasattr(self, '_min_toggle'):
            return
        self._min_toggle.set_disabled(disabled)
        self._min_label.configure(fg=FG_DIM if disabled else FG)
        self._min_row.configure(cursor="arrow" if disabled else "hand2")
        if disabled:
            self._min_row.unbind("<Button-1>")
            self._min_label.unbind("<Button-1>")
        else:
            self._min_row.bind("<Button-1>", lambda e: self._min_flip(e))
            self._min_label.bind("<Button-1>", lambda e: self._min_flip(e))

    FEATURE_TIPS = {
        "feature_time": "Show/hide the current time on the display",
        "feature_date": "Alternate time display with the current date",
        "feature_minute_bar": "Visual minute progress bar on the display",
        "feature_eyes": "Animated eyes that follow motion",
        "feature_notifications": "Show phone/PC notifications on the display",
        "night_mode_enabled": "Dim the display during night hours",
        "temp_alert": "Flash when CPU/GPU temperature exceeds limits",
        "pc_stats_enabled": "Auto-show PC stats overlay when a game or temp alert is detected",
    }

    def _build_features(self, f):
        main = tk.Frame(f, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        main.columnconfigure(0, weight=1)

        r = 0

        # ── Clock Mode ────────────────────────────────────────
        tk.Label(main, text="Clock Mode", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=NEON).grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1
        self._clock_mode_var = tk.StringVar()
        def _on_clock_mode(*_):
            if self._suppress_apply:
                return
            self._update_minute_bar_state()
            self._apply()
        self._clock_mode_var.trace_add("write", _on_clock_mode)
        cm_frame = tk.Frame(main, bg=BG)
        cm_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        DarkCombobox(cm_frame, textvariable=self._clock_mode_var,
                     values=CLOCK_MODE_OPTIONS).pack(fill=tk.X)
        r += 1

        # ── Clock Display + Extras (2 columns) ────────────────
        tk.Frame(main, bg=NEON_DIM, height=1).grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=(10, 10))
        r += 1

        dual = tk.Frame(main, bg=BG)
        dual.grid(row=r, column=0, columnspan=2, sticky="ew", padx=2)
        dual.columnconfigure(0, weight=1)
        dual.columnconfigure(1, weight=1)
        r += 1

        # Left column — Clock Display
        left = tk.Frame(dual, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        tk.Label(left, text="Clock Display", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=NEON).pack(anchor="w", pady=(0, 8))
        for key, label in [("feature_time", "Time display"),
                           ("feature_date", "Date reminder"),
                           ("feature_minute_bar", "Minute bar")]:
            var = tk.BooleanVar()
            row_w, tog, text, flip = self._make_toggle_row(left, label, var, BG_CARD)
            row_w.pack(fill="x", padx=2, pady=2)
            self._vars[key] = var
            var.trace_add("write", lambda *_: self._apply() if not self._suppress_apply else None)
            tip = self.FEATURE_TIPS.get(key)
            if tip:
                ToolTip(row_w, tip)
            if key == "feature_minute_bar":
                self._min_row = row_w
                self._min_toggle = tog
                self._min_label = text
                self._min_flip = flip

        # Right column — Extras
        right = tk.Frame(dual, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(right, text="Extras", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=NEON).pack(anchor="w", pady=(0, 8))
        for key, label in [("feature_eyes", "Animated eyes"),
                           ("feature_notifications", "Notifications"),
                           ("night_mode_enabled", "Night mode"),
                           ("pc_stats_enabled", "PC Stats"),
                           ]:
            var = tk.BooleanVar()
            row_w, tog, text, flip = self._make_toggle_row(right, label, var, BG_CARD)
            row_w.pack(fill="x", padx=2, pady=2)
            self._vars[key] = var
            var.trace_add("write", lambda *_: self._apply() if not self._suppress_apply else None)
            tip = self.FEATURE_TIPS.get(key)
            if tip:
                ToolTip(row_w, tip)

        # ── Temp Alert ────────────────────────────────────────
        tk.Frame(main, bg=NEON_DIM, height=1).grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=(10, 10))
        r += 1
        tk.Label(main, text="Temp Alert", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=NEON).grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 8))
        r += 1

        # Toggle + CPU / GPU inline
        inline = tk.Frame(main, bg=BG)
        inline.grid(row=r, column=0, columnspan=2, sticky="ew", padx=2, pady=2)
        r += 1

        var = tk.BooleanVar()
        row_w, tog, text, flip = self._make_toggle_row(inline, "Temp alert", var, BG_CARD)
        row_w.pack(side="left", fill="x", expand=True)
        self._vars["temp_alert"] = var
        var.trace_add("write", lambda *_: self._apply() if not self._suppress_apply else None)
        tip = self.FEATURE_TIPS.get("temp_alert")
        if tip:
            ToolTip(row_w, tip)

        tk.Frame(inline, bg=BG, width=16).pack(side="left")

        tk.Label(inline, text="CPU", font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 4))
        self._cpu_lim_var = tk.StringVar(value=str(self._cfg.get("cpu_temp_lim", 90)))
        cpu_e = tk.Entry(inline, textvariable=self._cpu_lim_var, width=4,
                         bg=BG_CARD, fg=FG, insertbackground=FG,
                         relief="flat", bd=4, highlightthickness=1,
                         highlightcolor=NEON, highlightbackground=NEON_DIM,
                         font=("Segoe UI", 9))
        cpu_e.pack(side="left", padx=(0, 12))
        self._cpu_lim_var.trace_add("write", lambda *_: self._save_temp_limits())

        tk.Label(inline, text="GPU", font=FONT_SM, bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 4))
        self._gpu_lim_var = tk.StringVar(value=str(self._cfg.get("gpu_temp_lim", 90)))
        gpu_e = tk.Entry(inline, textvariable=self._gpu_lim_var, width=4,
                         bg=BG_CARD, fg=FG, insertbackground=FG,
                         relief="flat", bd=4, highlightthickness=1,
                         highlightcolor=NEON, highlightbackground=NEON_DIM,
                         font=("Segoe UI", 9))
        gpu_e.pack(side="left")

        # ── Media Player ──────────────────────────────────────
        tk.Frame(main, bg=NEON_DIM, height=1).grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=10)
        r += 1
        tk.Label(main, text="Media Player (for eject button)", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=NEON).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(0, 8))
        r += 1

        self._media_app_map = {}
        self._media_combo_var = tk.StringVar()
        self._media_combo = DarkCombobox(main, textvariable=self._media_combo_var)
        self._media_combo.grid(row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        self._media_combo._frame.bind("<<ComboboxSelected>>", self._on_media_app_selected)
        r += 1

        pf = tk.Frame(main, bg=BG)
        pf.grid(row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        self._media_path_var = tk.StringVar(value=self._cfg.get("media_player_path", ""))
        pe = tk.Entry(pf, textvariable=self._media_path_var,
                      bg=BG_CARD, fg=FG, insertbackground=FG,
                      relief="flat", bd=4, highlightthickness=1,
                      highlightcolor=NEON, highlightbackground=NEON_DIM,
                      font=("Segoe UI", 9))
        pe.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        browse_lbl = tk.Label(pf, text="BROWSE", bg=BUTTON, fg=FG,
                               font=("Segoe UI", 8, "bold"), padx=8, pady=5,
                               cursor="hand2")
        browse_lbl.pack(side=tk.RIGHT)
        browse_lbl.bind("<Button-1>", lambda e: self._browse_media())
        r += 1

        self._media_path_var.trace_add("write", lambda *_: self._save_media_player_path())

        # Spacer so tab content clears the OK/Cancel bar
        tk.Frame(main, bg=BG, height=16).grid(row=r, column=0, columnspan=2)

    # ── ALARM TAB ─────────────────────────────────────────────

    def _build_alarm(self, f):
        self._alarm_editing_id = None
        outer = tk.Frame(f, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=16)
        self._alarm_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        self._alarm_canvas.pack(fill="both", expand=True)

        self._alarm_frame = tk.Frame(self._alarm_canvas, bg=BG)
        self._alarm_canvas_win = self._alarm_canvas.create_window(
            (0, 0), window=self._alarm_frame, anchor="nw")

        def _sync_alarm_scrollregion():
            bbox = self._alarm_canvas.bbox("all")
            if not bbox:
                return
            view_h = max(1, self._alarm_canvas.winfo_height())
            content_h = max(view_h, bbox[3] - bbox[1])
            self._alarm_canvas.configure(scrollregion=(0, 0, bbox[2], content_h))
            if bbox[3] - bbox[1] <= view_h:
                self._alarm_canvas.yview_moveto(0)

        def _alarm_canvas_cfg(e):
            self._alarm_canvas.itemconfig(self._alarm_canvas_win, width=e.width)
            _sync_alarm_scrollregion()
        self._alarm_canvas.bind("<Configure>", _alarm_canvas_cfg)
        self._alarm_frame.bind("<Configure>", lambda _: _sync_alarm_scrollregion())

        def _alarm_wheel(e):
            self._alarm_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"
        self._alarm_canvas.bind("<MouseWheel>", _alarm_wheel)
        self._alarm_frame.bind("<MouseWheel>", _alarm_wheel)

        # Install wheel-event propagation on all child widgets
        _WHEEL_TAG = "_alarm_wheel"
        self._alarm_canvas.bind_class(_WHEEL_TAG, "<MouseWheel>", _alarm_wheel)

        def _install_wheel_tag(w):
            tags = w.bindtags()
            if tags[0] != _WHEEL_TAG:
                w.bindtags((_WHEEL_TAG,) + tags)
            for c in w.winfo_children():
                _install_wheel_tag(c)

        self._alarm_install_wheel = _install_wheel_tag
        _install_wheel_tag(self._alarm_frame)

    def _on_tab_selected(self, idx):
        if idx == self._tab_alarm_index and not self._alarm_built:
            self._alarm_built = True
            self._rebuild_alarm_view()
        if idx == self._tab_buttons_index and not self._buttons_built:
            self._buttons_built = True
            self._rebuild_buttons_view()

    def _rebuild_alarm_view(self):
        for w in self._alarm_frame.winfo_children():
            w.destroy()

        alarms = self._cfg.get("alarms", [])

        if self._alarm_editing_id is not None:
            self._build_alarm_edit(self._alarm_frame)
            if hasattr(self, '_alarm_install_wheel'):
                self._alarm_install_wheel(self._alarm_frame)
            return

        if not alarms:
            self._alarm_editing_id = "new"
            self._rebuild_alarm_view()
            return

        tk.Label(self._alarm_frame, text="ALARMS",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=NEON).pack(anchor="w")

        for alarm in alarms:
            self._build_alarm_card(self._alarm_frame, alarm)

        RoundedButton(self._alarm_frame, text="+ ADD ALARM", style="sec",
                      command=self._alarm_add_click).pack(anchor="w", pady=(8, 0))

        if hasattr(self, '_alarm_install_wheel'):
            self._alarm_install_wheel(self._alarm_frame)
        if hasattr(self, '_alarm_canvas'):
            self._alarm_canvas.after_idle(lambda: self._alarm_canvas.configure(
                scrollregion=self._alarm_canvas.bbox("all")))

    def _build_alarm_card(self, parent, alarm):
        border = tk.Frame(parent, bg=BORDER, bd=0)
        border.pack(fill="x", pady=(0, 8))
        card = tk.Frame(border, bg=BG_CARD, bd=0)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        row1 = tk.Frame(card, bg=BG_CARD)
        row1.pack(fill="x", padx=12, pady=(10, 4))

        time_str = f"{alarm['hour']:02d}:{alarm['minute']:02d}"
        tk.Label(row1, text=time_str, font=("Segoe UI", 22, "bold"),
                 fg=NEON, bg=BG_CARD).pack(side="left")

        toggle_var = tk.BooleanVar(value=alarm.get("enabled", True))

        def _on_toggle(a=alarm):
            a["enabled"] = toggle_var.get()
            self._save_alarms()

        Toggle(row1, toggle_var, on_change=_on_toggle, bg=BG_CARD).pack(side="right", padx=(6, 0))

        def _do_delete(a=alarm):
            self._cfg["alarms"] = [x for x in self._cfg.get("alarms", []) if x["id"] != a["id"]]
            self._save_alarms()
            self._rebuild_alarm_view()

        RoundedButton(row1, text="\u00d7", command=_do_delete, style="sec",
                      padx=8, pady=2, font=FONT_SM).pack(side="right", padx=(4, 0))

        def _edit(a=alarm):
            self._alarm_editing_id = a["id"]
            self._rebuild_alarm_view()

        RoundedButton(row1, text="EDIT", command=_edit, style="sec",
                      padx=8, pady=2, font=FONT_SM).pack(side="right", padx=(0, 4))

        row2 = tk.Frame(card, bg=BG_CARD)
        row2.pack(fill="x", padx=12, pady=(0, 4))

        days = alarm.get("days", 62)
        day_labels = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        day_bits = [1, 2, 3, 4, 5, 6, 0]
        for lbl, bit in zip(day_labels, day_bits):
            active = bool((days >> bit) & 1)
            tk.Label(row2, text=lbl, bg=BG_CARD,
                     fg=NEON if active else FG_DIM,
                     font=("Segoe UI", 8, "bold" if active else "normal")).pack(side="left", padx=(0, 4))

        msg = alarm.get("message", "").strip()
        if msg:
            tk.Label(card, text=msg, bg=BG_CARD, fg=FG_DIM,
                     font=FONT_SM, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def _build_alarm_edit(self, parent):
        data = self._alarm_editing_data()

        edit_border = tk.Frame(parent, bg=BORDER, bd=0)
        edit_border.pack(fill="x")
        edit_card = tk.Frame(edit_border, bg=BG_CARD, bd=0)
        edit_card.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(edit_card, bg=BG_CARD, padx=16, pady=16)
        inner.pack(fill="x")

        # ── header row: title left, ENABLED + toggle right ──
        hdr = tk.Frame(inner, bg=BG_CARD)
        hdr.pack(fill="x")

        tk.Label(hdr, text="NEW ALARM" if self._alarm_editing_id == "new" else "EDIT ALARM",
                 font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=NEON).pack(side="left")

        ena_frame = tk.Frame(hdr, bg=BG_CARD)
        ena_frame.pack(side="right")
        tk.Label(ena_frame, text="ENABLED", font=FONT_SM, bg=BG_CARD, fg=FG_DIM).pack(side="left", padx=(0, 6))

        ena_var = tk.BooleanVar(value=data.get("enabled", True))
        self._edit_enabled_var = ena_var
        Toggle(ena_frame, ena_var, bg=BG_CARD).pack(side="right")

        # ── time scrollers ──
        time_frame = tk.Frame(inner, bg=BG_CARD)
        time_frame.pack(pady=(14, 0))

        self._edit_hour_var = tk.IntVar(value=data["hour"])
        self._edit_min_var = tk.IntVar(value=data["minute"])

        def _make_spinner(frame, var, lo, hi):
            sf = tk.Frame(frame, bg=BG_CARD)
            sf.pack(side="left")

            def _up():
                var.set(lo if var.get() >= hi else var.get() + 1)

            def _down():
                var.set(hi if var.get() <= lo else var.get() - 1)

            up_lbl = tk.Label(sf, text="\u25b2", font=("Segoe UI", 8), fg=NEON,
                              bg=BG_CARD, cursor="hand2")
            up_lbl.pack()
            up_lbl.bind("<Button-1>", lambda e: _up())

            e = tk.Entry(sf, textvariable=var, width=3,
                         font=("Segoe UI", 24, "bold"), fg=NEON, bg=BG,
                         justify="center", relief="flat", bd=4,
                         highlightthickness=0)
            e.pack()

            def _mousewheel(ev):
                if ev.delta > 0:
                    _up()
                else:
                    _down()

            def _validate(*_):
                try:
                    v = int(var.get())
                    if v < lo:
                        var.set(lo)
                    elif v > hi:
                        var.set(hi)
                except ValueError:
                    var.set(lo)

            var.trace_add("write", _validate)
            e.bind("<FocusOut>", lambda e: _validate())
            e.bind("<MouseWheel>", _mousewheel)

            dn_lbl = tk.Label(sf, text="\u25bc", font=("Segoe UI", 8), fg=NEON,
                              bg=BG_CARD, cursor="hand2")
            dn_lbl.pack()
            dn_lbl.bind("<Button-1>", lambda e: _down())

            return sf

        _make_spinner(time_frame, self._edit_hour_var, 0, 23)
        tk.Label(time_frame, text=":", font=("Segoe UI", 24, "bold"),
                 fg=NEON, bg=BG_CARD).pack(side="left", padx=4)
        _make_spinner(time_frame, self._edit_min_var, 0, 59)

        # ── ACTIVE DAYS ──
        day_frame = tk.Frame(inner, bg=BG_CARD)
        day_frame.pack(fill="x", pady=(14, 6))

        day_labels = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        day_bits = [1, 2, 3, 4, 5, 6, 0]
        days = data.get("days", 62)

        self._edit_day_vars = [bool((days >> b) & 1) for b in day_bits]
        self._day_toggle_labels = day_labels
        self._day_toggle_bits = day_bits

        tk.Label(day_frame, text="ACTIVE DAYS", font=("Segoe UI", 8, "bold"),
                 bg=BG_CARD, fg=FG_DIM).pack(anchor="w")
        self._build_day_toggles(day_frame)

        # ── Message ──
        msg_frame = tk.Frame(inner, bg=BG_CARD)
        msg_frame.pack(fill="x", pady=(8, 0))
        tk.Label(msg_frame, text="Message", bg=BG_CARD, fg=FG_DIM,
                 font=FONT_SM).pack(anchor="w")

        self._edit_msg_var = tk.StringVar(value=data.get("message", ""))
        msg_entry = tk.Entry(msg_frame, textvariable=self._edit_msg_var,
                             bg=BG, fg=FG, insertbackground=FG,
                             relief="flat", bd=4, highlightthickness=1,
                             highlightcolor=NEON, highlightbackground=NEON_DIM,
                             font=FONT_SM)
        msg_entry.pack(fill="x", pady=(2, 0))

        # ── buttons ──
        btn_row = tk.Frame(inner, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(10, 0))

        if self._alarm_editing_id != "new":
            RoundedButton(btn_row, text="DELETE", style="sec",
                          bg=DANGER, hover=DANGER_HOVER,
                          command=self._alarm_delete_current).pack(side="left")

        RoundedButton(btn_row, text="CANCEL", style="sec",
                      command=self._alarm_cancel_edit).pack(side="right", padx=(4, 0))

        RoundedButton(btn_row, text="SAVE", style="prim",
                      command=self._alarm_save_edit).pack(side="right", padx=(0, 4))

    def _build_day_toggles(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x")
        for i, (lbl, bit) in enumerate(zip(self._day_toggle_labels, self._day_toggle_bits)):
            active = self._edit_day_vars[i]

            def _toggle(idx=i):
                self._edit_day_vars[idx] = not self._edit_day_vars[idx]
                self._build_day_toggles(parent)

            f = tk.Frame(row, bg=BG_CARD, cursor="hand2", padx=2, pady=2)
            f.pack(side="left", fill="x", expand=True)
            lbl_w = tk.Label(f, text=lbl,
                             font=("Segoe UI", 7, "bold" if active else "normal"),
                             fg=BG if active else FG_DIM,
                             bg=NEON if active else BUTTON,
                             padx=4, pady=4)
            lbl_w.pack(fill="x")
            lbl_w.bind("<Button-1>", lambda e, idx=i: _toggle(idx))
            f.bind("<Button-1>", lambda e, idx=i: _toggle(idx))

    def _alarm_editing_data(self):
        alarms = self._cfg.get("alarms", [])
        if self._alarm_editing_id == "new":
            return {"hour": 8, "minute": 0, "days": 62,
                    "enabled": True, "message": "", "show_eyes": True}
        for a in alarms:
            if a["id"] == self._alarm_editing_id:
                return a
        return {"hour": 8, "minute": 0, "days": 62,
                "enabled": True, "message": "", "show_eyes": True}

    def _alarm_add_click(self):
        self._alarm_editing_id = "new"
        self._rebuild_alarm_view()

    def _alarm_cancel_edit(self):
        self._alarm_editing_id = None
        self._rebuild_alarm_view()

    def _alarm_delete_current(self):
        if self._alarm_editing_id == "new":
            self._alarm_cancel_edit()
            return
        alarms = self._cfg.get("alarms", [])
        self._cfg["alarms"] = [a for a in alarms if a["id"] != self._alarm_editing_id]
        self._save_alarms()
        self._alarm_editing_id = None
        self._rebuild_alarm_view()

    def _alarm_save_edit(self):
        try:
            h = max(0, min(23, int(self._edit_hour_var.get())))
            m = max(0, min(59, int(self._edit_min_var.get())))
        except ValueError:
            return

        days = 0
        for i, bit in enumerate([1, 2, 3, 4, 5, 6, 0]):
            if self._edit_day_vars[i]:
                days |= (1 << bit)

        msg = self._edit_msg_var.get().strip()

        alarms = self._cfg.get("alarms", [])

        enabled = self._edit_enabled_var.get() if hasattr(self, '_edit_enabled_var') else True

        if self._alarm_editing_id == "new":
            new_id = max((a["id"] for a in alarms), default=0) + 1
            alarms.append({"id": new_id, "hour": h, "minute": m,
                           "days": days, "enabled": enabled,
                           "message": msg, "show_eyes": True})
        else:
            for a in alarms:
                if a["id"] == self._alarm_editing_id:
                    a.update(hour=h, minute=m, days=days,
                             enabled=enabled, message=msg, show_eyes=True)
                    break

        self._cfg["alarms"] = alarms
        self._save_alarms()
        self._alarm_editing_id = None
        self._rebuild_alarm_view()
        if self._serial:
            self._sync_next_alarm()

    def _save_alarms(self):
        save_config(self._cfg)

    # ── BUTTONS TAB ───────────────────────────────────────────

    def _build_buttons(self, f):
        _outer = tk.Frame(f, bg=BG)
        _outer.pack(fill="both", expand=True, padx=16, pady=16)

        self._btn_canvas = tk.Canvas(_outer, bg=BG, highlightthickness=0, bd=0)
        self._btn_canvas.pack(fill="both", expand=True)

        self._buttons_frame = tk.Frame(self._btn_canvas, bg=BG)
        self._btn_canvas_win = self._btn_canvas.create_window(
            (0, 0), window=self._buttons_frame, anchor="nw")

        def _sync_button_scrollregion():
            bbox = self._btn_canvas.bbox("all")
            if not bbox:
                return
            view_h = max(1, self._btn_canvas.winfo_height())
            content_h = max(view_h, bbox[3] - bbox[1])
            self._btn_canvas.configure(scrollregion=(0, 0, bbox[2], content_h))
            if bbox[3] - bbox[1] <= view_h:
                self._btn_canvas.yview_moveto(0)

        def _scroll():
            self._sync_button_scrollregion()

        def _on_canvas_cfg(e):
            self._btn_canvas.itemconfig(self._btn_canvas_win, width=e.width)
            self._sync_button_scrollregion()
        self._btn_canvas.bind("<Configure>", _on_canvas_cfg)

        self._sync_button_scrollregion = _sync_button_scrollregion
        self._buttons_frame.bind("<Configure>", lambda _: _scroll())
        def _wheel(e):
            first, last = self._btn_canvas.yview()
            if last - first >= 0.995:
                return "break"
            self._btn_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"
        self._btn_canvas.bind("<MouseWheel>", _wheel)
        self._buttons_frame.bind("<MouseWheel>", _wheel)

        # Install wheel-event propagation on all child widgets via bindtags
        _WHEEL_TAG = "_btns_wheel"
        self._btn_canvas.bind_class(_WHEEL_TAG, "<MouseWheel>", _wheel)

        def _install_wheel_tag(w):
            tags = w.bindtags()
            if tags[0] != _WHEEL_TAG:
                w.bindtags((_WHEEL_TAG,) + tags)
            for c in w.winfo_children():
                _install_wheel_tag(c)

        self._btn_install_wheel = _install_wheel_tag
        _install_wheel_tag(self._buttons_frame)

        self._btn_expanded = set()
        self._button_editing_slot = None
        self._button_new_parent = None

    _tile_cache = {}

    def _make_tile_photo(self, mdi_name, fill_hex, ring_hex=None, icon_color=None,
                         app_icon_path=None, icon_scale=0.7, bg_hex=None):
        cache_key = (mdi_name, fill_hex, ring_hex, icon_color, app_icon_path, icon_scale, bg_hex)
        cached = self._tile_cache.get(cache_key)
        if cached is not None:
            return cached

        _T, _CR = 40, 8
        S = _T * 4
        R = _CR * 4
        bw = 8

        frgb = tuple(int(fill_hex[i:i+2], 16) for i in (1, 3, 5))
        brgb = tuple(int((bg_hex or BG)[i:i+2], 16) for i in (1, 3, 5))
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

        if app_icon_path:
            from win_platform import _extract_via_ps
            app_img = _extract_via_ps(app_icon_path, size=_T)
            if app_img:
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
        # MDI fallback
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

    def _rebuild_buttons_view(self):
        for w in self._buttons_frame.winfo_children():
            w.destroy()

        if not hasattr(self, '_btn_expanded'):
            self._btn_expanded = set()
        self._btn_group_frames = {}
        if not hasattr(self, '_button_editing_slot'):
            self._button_editing_slot = None
        if not hasattr(self, '_button_new_parent'):
            self._button_new_parent = None

        if self._button_editing_slot is not None or self._button_new_parent is not None:
            slot = self._button_editing_slot
            self._build_button_edit(self._buttons_frame, slot)
            if hasattr(self, '_btn_install_wheel'):
                self._btn_install_wheel(self._buttons_frame)
            return

        header = tk.Frame(self._buttons_frame, bg=BG)
        header.pack(fill=tk.X, pady=(0, 8))
        tk.Label(header, text="CUSTOM BUTTONS",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=NEON).pack(side="left")

        cards_frame = tk.Frame(self._buttons_frame, bg=BG)
        cards_frame.pack(fill=tk.X)

        self._btn_card_photos = []
        board = self._cfg.get("ha_board") or []
        self._render_tree(cards_frame, board)

        RoundedButton(self._buttons_frame, text="+ ADD BUTTON", style="sec",
                      command=lambda: self._start_add(None)).pack(anchor="w", pady=(8, 0))

        # Force canvas layout so content isn't clipped
        self._buttons_frame.update_idletasks()
        if hasattr(self, '_btn_canvas') and self._btn_canvas.winfo_exists():
            cw = self._btn_canvas.winfo_width()
            if cw > 10:
                self._btn_canvas.itemconfig(self._btn_canvas_win, width=cw)
            self._sync_button_scrollregion()
        if hasattr(self, '_btn_install_wheel'):
            self._btn_install_wheel(self._buttons_frame)

    def _render_tree(self, parent, items, depth=0):
        for i, slot in enumerate(items):
            if slot is None:
                continue
            margin = depth * 20

            border = tk.Frame(parent, bg=BORDER, bd=0)
            border.pack(fill="x", pady=(0, 6), padx=(margin, 0))
            card = tk.Frame(border, bg=BG_CARD, bd=0)
            card.pack(fill="both", expand=True, padx=1, pady=1)
            row = tk.Frame(card, bg=BG_CARD)
            row.pack(fill="x", padx=10, pady=(6, 6))

            icon_mdi = slot.get("icon") or "help-circle"
            fill = slot.get("color") or BG_CARD
            app_icon = slot.get("app_icon_path") or (slot.get("shortcut_path") if slot.get("type") in ("SHORTCUT", "GROUP") else None)
            img = self._make_tile_photo(icon_mdi, fill, app_icon_path=app_icon, bg_hex=BG_CARD)
            self._btn_card_photos.append(img)
            tk.Label(row, image=img, bg=BG_CARD, padx=0, pady=0).pack(side="left", padx=(0, 8))

            info = tk.Frame(row, bg=BG_CARD)
            info.pack(side="left", fill="x", expand=True)
            name = (slot.get("name") or "Untitled").strip()
            name_lbl = tk.Label(info, text=name, font=("Segoe UI", 10, "bold"),
                                bg=BG_CARD, fg=FG, anchor="w")
            name_lbl.pack(fill="x")
            btype = slot.get("type", "")
            type_color = {"SHORTCUT": NEON, "REST": NEON_GRN, "HOTKEY": NEON_DIM, "OPENRGB": NEON_RED, "GROUP": NEON, "STOPWATCH": NEON_GRN}
            type_lbl = tk.Label(info, text=btype, font=("Segoe UI", 7),
                                bg=BG_CARD, fg=type_color.get(btype, FG_DIM), anchor="w")
            type_lbl.pack(fill="x")

            RoundedButton(row, text="EDIT", style="sec",
                          command=lambda s=slot: self._start_edit(s),
                          padx=6, pady=2, font=FONT_SM).pack(side="right", padx=(2, 0))
            RoundedButton(row, text="\u00d7", style="sec",
                          command=lambda s=slot: self._delete_slot(s),
                          padx=6, pady=2, font=FONT_SM).pack(side="right", padx=(2, 0))

            if btype == "GROUP":
                children = slot.get("children") or []
                sid = id(slot)
                expanded = sid in self._btn_expanded
                toggle_txt = "\u25bc" if expanded else "\u25b6"
                toggle_btn = RoundedButton(row, text=f"{toggle_txt} {len(children)}", style="sec",
                                           padx=6, pady=2, font=FONT_SM)
                toggle_btn.pack(side="right", padx=(2, 0))
                toggle_btn.configure(command=lambda s=sid: self._toggle_expand(s))

                # Click name/type labels to toggle expand
                name_lbl.bind("<Button-1>", lambda e, s=sid: self._toggle_expand(s), add="+")
                type_lbl.bind("<Button-1>", lambda e, s=sid: self._toggle_expand(s), add="+")

                # Always create sub-frame with children + ADD button; hide when collapsed
                sub = tk.Frame(parent, bg=BG)
                if children:
                    self._render_tree(sub, children, depth + 1)
                RoundedButton(sub, text="+ ADD", style="sec",
                              command=lambda p=slot: self._start_add(p.setdefault("children", [])),
                              padx=6, pady=2, font=FONT_SM).pack(anchor="w")
                if expanded:
                    sub.pack(fill=tk.X, padx=(margin + 20, 0), pady=(0, 6))
                self._btn_group_frames[sid] = (sub, margin, toggle_btn, slot)

    def _toggle_expand(self, sid):
        expanded = sid in self._btn_expanded
        entry = self._btn_group_frames.get(sid)
        if not entry:
            return
        sub, margin, toggle_btn, slot = entry
        children = slot.get("children") or []

        if expanded:
            self._btn_expanded.discard(sid)
            sub.pack_forget()
            toggle_btn.configure(text=f"\u25b6 {len(children)}")
        else:
            self._btn_expanded.add(sid)
            sub.pack(fill=tk.X, padx=(margin + 20, 0), pady=(0, 6))
            toggle_btn.configure(text=f"\u25bc {len(children)}")

    def _start_edit(self, slot):
        self._button_editing_slot = slot
        self._rebuild_buttons_view()

    def _start_add(self, parent_list):
        if parent_list is None:
            parent_list = self._cfg.setdefault("ha_board", [])
        self._button_new_parent = parent_list
        self._button_editing_slot = None
        self._rebuild_buttons_view()

    def _delete_slot(self, slot):
        def _find(items):
            for i, s in enumerate(items):
                if s is slot:
                    items.pop(i)
                    return True
                if s.get("type") == "GROUP":
                    if _find(s.get("children") or []):
                        return True
            return False
        _find(self._cfg.setdefault("ha_board", []))
        save_config(self._cfg)
        self._rebuild_buttons_view()

    def _build_button_edit(self, parent, slot, form_data=None):
        data = form_data if form_data is not None else (slot if slot else {})
        is_new = slot is None

        edit_border = tk.Frame(parent, bg=BORDER, bd=0)
        edit_border.pack(fill=tk.X)
        edit_card = tk.Frame(edit_border, bg=BG_CARD, bd=0)
        edit_card.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        inner = tk.Frame(edit_card, bg=BG_CARD, padx=16, pady=16)
        inner.pack(fill=tk.X)

        header_frame = tk.Frame(inner, bg=BG_CARD)
        header_frame.pack(fill=tk.X)
        back_btn = RoundedButton(header_frame, text="\u2190 Back", style="sec",
                                 command=self._cancel_edit, padx=8, pady=2, font=FONT_SM)
        back_btn.pack(side="left")
        ToolTip(back_btn, "Go back to the button list without saving")
        tk.Label(header_frame, text="EDIT BUTTON" if not is_new else "NEW BUTTON",
                 font=("Segoe UI", 10, "bold"), bg=BG_CARD, fg=NEON).pack(side="left", padx=(8, 0))

        # Name
        tk.Label(inner, text="Name", bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w", pady=(8, 0))
        name_var = tk.StringVar(value=data.get("name", ""))
        tk.Entry(inner, textvariable=name_var,
                 bg=BG, fg=FG, insertbackground=FG,
                 relief="flat", bd=4, highlightthickness=1,
                 highlightcolor=NEON, highlightbackground=NEON_DIM,
                 font=FONT_SM).pack(fill=tk.X, pady=(2, 0))

        # Type
        tk.Label(inner, text="Type", bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w", pady=(8, 0))
        type_var = tk.StringVar(value=data.get("type", "SHORTCUT"))
        type_choices = ["SHORTCUT", "REST", "HOTKEY", "OPENRGB", "GROUP", "STOPWATCH"]
        type_frame = tk.Frame(inner, bg=BG_CARD)
        type_frame.pack(fill=tk.X, pady=(2, 0))
        type_frame.columnconfigure(0, weight=1, uniform=type_frame)
        type_frame.columnconfigure(1, weight=1, uniform=type_frame)
        type_frame.columnconfigure(2, weight=1, uniform=type_frame)
        type_labels = []

        def _refresh_type_labels(*_):
            active = type_var.get()
            for name, lbl in type_labels:
                selected = name == active
                lbl.configure(bg=NEON if selected else BUTTON,
                              fg=BG if selected else FG)

        TYPE_TIPS = {
            "SHORTCUT": "Launch a program or shortcut file",
            "REST": "Trigger a Home Assistant REST API command",
            "HOTKEY": "Send a keyboard shortcut to the app underneath",
            "OPENRGB": "Apply an OpenRGB lighting profile",
            "GROUP": "Create a sub-panel with nested buttons (optionally also launch a shortcut)",
            "STOPWATCH": "Start a floating stopwatch / countdown timer",
        }
        for i, t in enumerate(type_choices):
            pill = tk.Label(type_frame, text=t, bg=BUTTON, fg=FG,
                            font=("Segoe UI", 8, "bold"), padx=8, pady=5,
                            cursor="hand2")
            pill.grid(row=i // 3, column=i % 3, padx=3, pady=(0, 4), sticky="ew")
            pill.bind("<Button-1>", lambda e, val=t: type_var.set(val))
            type_labels.append((t, pill))
            tip = TYPE_TIPS.get(t)
            if tip:
                ToolTip(pill, tip)
        type_var.trace_add("write", _refresh_type_labels)
        _refresh_type_labels()

        icon_var = tk.StringVar(value=data.get("icon", "help-circle"))
        color_var = tk.StringVar(value=data.get("color", ""))

        tk.Label(inner, text="Edit Icon", bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w", pady=(8, 0))

        # Preview tile (matches panel rendering)
        prev_row = tk.Frame(inner, bg=BG_CARD)
        prev_row.pack(fill=tk.X, pady=(4, 0))

        preview_photo = [None]
        def _update_preview_tile(*_):
            c = color_var.get() or BG_CARD
            i = icon_var.get() or "help-circle"
            ap = data.get("app_icon_path") or (data.get("shortcut_path") if data.get("type") in ("SHORTCUT", "GROUP") else "") or ""
            try:
                photo = self._make_tile_photo(i, c, app_icon_path=ap, bg_hex=BG_CARD)
                preview_photo[0] = photo
                for w in prev_row.winfo_children():
                    w.destroy()
                lbl = tk.Label(prev_row, image=photo, bg=BG_CARD, cursor="hand2")
                lbl.pack(side="left")
                lbl.bind("<Button-1>", lambda e: _open_inline_picker())
            except Exception:
                pass

        color_var.trace_add("write", _update_preview_tile)
        icon_var.trace_add("write", _update_preview_tile)
        _update_preview_tile()

        def _capture_state():
            d = {
                "name": name_var.get(),
                "type": type_var.get(),
                "icon": icon_var.get(),
                "color": color_var.get(),
                "app_icon_path": data.get("app_icon_path") or (data.get("shortcut_path") if data.get("type") in ("SHORTCUT", "GROUP") else "") or "",
            }
            for k, v in self._btn_field_vars.items():
                if hasattr(v, "get"):
                    d[k] = v.get()
                else:
                    d[k] = v
            return d

        def _rebuild_form(data_dict):
            for w in parent.winfo_children():
                w.destroy()
            self._build_button_edit(parent, slot, form_data=data_dict)

        # ── Combined inline icon + colour picker ──
        def _open_inline_picker():
            state = _capture_state()
            for w in parent.winfo_children():
                w.destroy()

            outer_border = tk.Frame(parent, bg=BORDER, bd=0)
            outer_border.pack(fill=tk.X)
            outer = tk.Frame(outer_border, bg=BG_CARD, padx=16, pady=16)
            outer.pack(fill=tk.X)

            icon_var = tk.StringVar(value=state["icon"])
            color_var = tk.StringVar(value=state["color"])
            app_icon_path_var = tk.StringVar(value=state.get("app_icon_path", ""))

            # Icon grid (6 × 6 = 36 icons, no search)
            icon_grid = tk.Frame(outer, bg=BG_CARD)
            icon_grid.pack(fill=tk.X, pady=(0, 10))
            self._icon_picker_photos = []
            icon_names = mdi_icons.COMMON_ICONS[:30]

            for i, name in enumerate(icon_names):
                cell = tk.Frame(icon_grid, bg=BG_CARD, cursor="hand2")
                cell.grid(row=i // 6, column=i % 6, padx=2, pady=2)
                img = None
                try:
                    r = mdi_icons.render(name, 24, (224, 224, 224))
                    if r:
                        buf = io.BytesIO()
                        r.save(buf, format="PNG")
                        img = tk.PhotoImage(
                            data=base64.b64encode(buf.getvalue()).decode("ascii"))
                except Exception:
                    pass
                self._icon_picker_photos.append(img)
                icon_lbl = tk.Label(cell, image=img, bg=BG_CARD, width=48, height=32, cursor="hand2")
                icon_lbl.pack(padx=2, pady=(4, 4))
                icon_lbl.bind("<Button-1>", lambda e, n=name: icon_var.set(n))

            # Colour picker (manual grid with preview gap bottom-right)
            color_grid = tk.Frame(outer, bg=BG_CARD)
            color_grid.pack(fill=tk.X, pady=(0, 8))
            sw = 28
            sh = 28
            gap = 4

            def _pick_color(c):
                color_var.set(c)

            for idx, color in enumerate(HA_PALETTE):
                cell = tk.Frame(color_grid, bg=color, width=sw, height=sh,
                                cursor="hand2", highlightbackground=BORDER, highlightthickness=1)
                cell.grid(row=idx // 10, column=idx % 10, padx=gap // 2, pady=gap // 2)
                cell.pack_propagate(False)
                cell.bind("<Button-1>", lambda e, c=color: _pick_color(c))

            # Replace first swatch with no-colour (clears fill)
            nocell = tk.Frame(color_grid, bg=BG_CARD, width=sw, height=sh,
                              cursor="hand2", highlightbackground=BORDER, highlightthickness=1)
            nocell.grid(row=0, column=0, padx=gap // 2, pady=gap // 2)
            nocell.pack_propagate(False)
            nocell_lbl = tk.Label(nocell, text="\u2715", fg="#888", bg=BG_CARD,
                                  font=("Segoe UI", 10), cursor="hand2")
            nocell_lbl.place(relx=0.5, rely=0.5, anchor="center")
            nocell_lbl.bind("<Button-1>", lambda e: (_pick_color(""), _update_preview()))
            nocell.bind("<Button-1>", lambda e: (_pick_color(""), _update_preview()))
            ToolTip(nocell, "Clear the tile background colour")

            # Preview tile in bottom-right 2×2 gap
            preview_frame = tk.Frame(color_grid, bg=BG_CARD,
                                     width=sw * 2 + gap, height=sh * 2 + gap,
                                     highlightbackground=BORDER, highlightthickness=1)
            preview_frame.grid(row=2, column=8, rowspan=2, columnspan=2,
                               padx=gap // 2, pady=gap // 2)
            preview_frame.pack_propagate(False)
            preview_frame.grid_propagate(False)

            _preview_tile = [None]
            def _update_preview(*_):
                c = color_var.get() or BG_CARD
                i = icon_var.get()
                ap = app_icon_path_var.get()
                try:
                    tw, th = sw * 2 + gap, sh * 2 + gap
                    S = tw * 4
                    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                    dr = ImageDraw.Draw(tile)
                    rr = 4 * 4
                    dr.rounded_rectangle((0, 0, S - 1, S - 1), rr, fill=c)
                    # gloss
                    mask = Image.new("L", (S, S), 0)
                    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), rr, fill=255)
                    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                    gd = ImageDraw.Draw(gloss)
                    hm = int(S * 0.45)
                    for y in range(hm):
                        a = int(62 * (1 - y / hm))
                        gd.line([(0, y), (S - 1, y)], fill=(255, 255, 255, a))
                    clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                    clipped.paste(gloss, mask=mask)
                    tile = Image.alpha_composite(tile, clipped)
                    # icon from file
                    icon_drawn = False
                    if ap:
                        from win_platform import _extract_via_ps
                        app_img = _extract_via_ps(ap, size=tw)
                        if app_img:
                            bbox = app_img.getbbox()
                            if bbox:
                                app_img = app_img.crop(bbox)
                            app_img = app_img.resize((tw, th), Image.LANCZOS)
                            bg_rgb = tuple(int((BG)[i:i+2], 16) for i in (1, 3, 5))
                            tile = Image.new("RGBA", (tw, th), (*bg_rgb, 255))
                            icon_layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
                            icon_layer.paste(app_img, (0, 0), app_img)
                            mask = Image.new("L", (tw, th), 0)
                            ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw-1, th-1), 4, fill=255)
                            tile = Image.composite(icon_layer, tile, mask)
                            icon_drawn = True
                    if not icon_drawn:
                        r = mdi_icons.render(i, int(S * 0.7), (255, 255, 255))
                        if r:
                            ox = (S - r.width) // 2
                            oy = (S - r.height) // 2
                            layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                            layer.paste(r, (ox, oy), r)
                            tile = Image.alpha_composite(tile, layer)
                    tile = tile.resize((tw, th), Image.LANCZOS)
                    base = Image.new("RGB", (tw, th), tuple(int(BG_CARD[i:i+2], 16) for i in (1, 3, 5)))
                    base.paste(tile, mask=tile.split()[3])
                    buf = io.BytesIO()
                    base.save(buf, format="PNG")
                    _preview_tile[0] = tk.PhotoImage(
                        data=base64.b64encode(buf.getvalue()).decode("ascii"))
                    for w in preview_frame.winfo_children():
                        w.destroy()
                    tk.Label(preview_frame, image=_preview_tile[0],
                             bg=BG_CARD).pack()
                except Exception:
                    pass

            color_var.trace_add("write", _update_preview)
            icon_var.trace_add("write", _update_preview)
            app_icon_path_var.trace_add("write", _update_preview)
            _update_preview()

            # Hex entry + browse EXE
            hex_f = tk.Frame(outer, bg=BG_CARD)
            hex_f.pack(fill=tk.X)
            tk.Label(hex_f, text="Hex:", bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(side="left")
            hex_entry = tk.Entry(hex_f, textvariable=color_var,
                                 bg=BG, fg=FG, insertbackground=FG,
                                 relief="flat", bd=4, highlightthickness=1,
                                 highlightcolor=NEON, highlightbackground=NEON_DIM,
                                 font=FONT_SM, width=9)
            hex_entry.pack(side="left", padx=(4, 8))
            ToolTip(hex_entry, "Type a hex colour code directly (e.g. #FF4400)")
            custom_icon_btn = RoundedButton(hex_f, text="Custom Icon", style="prim",
                                            bg=NEON_GRN, fg=BG, hover="#22ff99",
                                            command=lambda: _browse_icon(),
                                            padx=6, pady=7, font=FONT_SM)
            custom_icon_btn.pack(side="left")
            ToolTip(custom_icon_btn, "Pick an .exe, .lnk or .ico file to use as the tile icon")

            def _browse_icon():
                path = filedialog.askopenfilename(
                    title="Select application or icon",
                    filetypes=[("Executable", "*.exe"), ("Shortcut", "*.lnk"),
                               ("Icon", "*.ico"), ("All files", "*.*")],
                    parent=self._win,
                )
                if path:
                    app_icon_path_var.set(path)

            # OK / Cancel
            btn_row = tk.Frame(outer, bg=BG_CARD)
            btn_row.pack(fill=tk.X, pady=(12, 0))
            picker_cancel = RoundedButton(btn_row, text="CANCEL", style="sec",
                                          command=lambda: _rebuild_form(state))
            picker_cancel.pack(side="right", padx=(4, 0))
            ToolTip(picker_cancel, "Discard changes and go back")
            picker_ok = RoundedButton(btn_row, text="OK", style="prim",
                                      command=lambda: (
                                          state.update({"icon": icon_var.get(), "color": color_var.get(),
                                                        "app_icon_path": app_icon_path_var.get()}),
                                          _rebuild_form(state)
                                                      ))
            picker_ok.pack(side="right", padx=(0, 4))
            ToolTip(picker_ok, "Apply icon and colour changes")

        # Action-specific fields
        self._button_fields_frame = tk.Frame(inner, bg=BG_CARD)
        self._button_fields_frame.pack(fill=tk.X, pady=(8, 0))

        def _toggle_fields(*_):
            if not self._button_fields_frame.winfo_exists():
                return
            for w in self._button_fields_frame.winfo_children():
                w.destroy()
            t = type_var.get()

            if t in ("SHORTCUT", "GROUP"):
                tk.Label(self._button_fields_frame, text="Shortcut path" + (" (also opens sub-panel)" if t == "GROUP" else ""),
                         bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
                sv = tk.StringVar(value=data.get("shortcut_path", ""))
                sf = tk.Frame(self._button_fields_frame, bg=BG_CARD)
                sf.pack(fill=tk.X, pady=(2, 0))
                tk.Entry(sf, textvariable=sv,
                         bg=BG, fg=FG, insertbackground=FG,
                         relief="flat", bd=4, highlightthickness=1,
                         highlightcolor=NEON, highlightbackground=NEON_DIM,
                         font=FONT_SM).pack(side="left", fill=tk.X, expand=True)

                def _browse_shortcut():
                    path = filedialog.askopenfilename(
                        title="Select executable or shortcut",
                        filetypes=[("Executable", "*.exe"),
                                   ("Shortcut", "*.lnk"),
                                   ("All files", "*.*")],
                        parent=self._win,
                    )
                    if path:
                        sv.set(path)
                browse_lbl = tk.Label(sf, text="BROWSE", bg=BUTTON, fg=FG,
                                      font=("Segoe UI", 8, "bold"), padx=8, pady=5,
                                      cursor="hand2")
                browse_lbl.pack(side="right", padx=(2, 0))
                browse_lbl.bind("<Button-1>", lambda e: _browse_shortcut())

                self._btn_field_vars["shortcut_path"] = sv

            elif t == "REST":
                tk.Label(self._button_fields_frame, text="Entity ID",
                         bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
                ev = tk.StringVar(value=data.get("entity_id", ""))
                tk.Entry(self._button_fields_frame, textvariable=ev,
                         bg=BG, fg=FG, insertbackground=FG,
                         relief="flat", bd=4, highlightthickness=1,
                         highlightcolor=NEON, highlightbackground=NEON_DIM,
                         font=FONT_SM).pack(fill=tk.X, pady=(2, 0))
                self._btn_field_vars["entity_id"] = ev

            elif t == "OPENRGB":
                tk.Label(self._button_fields_frame, text="Profile name",
                         bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
                op = tk.StringVar(value=data.get("openrgb_profile", ""))
                tk.Entry(self._button_fields_frame, textvariable=op,
                         bg=BG, fg=FG, insertbackground=FG,
                         relief="flat", bd=4, highlightthickness=1,
                         highlightcolor=NEON, highlightbackground=NEON_DIM,
                         font=FONT_SM).pack(fill=tk.X, pady=(2, 0))
                self._btn_field_vars["openrgb_profile"] = op

            elif t == "HOTKEY":
                tk.Label(self._button_fields_frame, text="Keyboard shortcut",
                         bg=BG_CARD, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
                row = tk.Frame(self._button_fields_frame, bg=BG_CARD)
                row.pack(fill=tk.X, pady=(2, 0))
                keys = data.get("keys", [])
                self._btn_field_vars["_hotkey_keys"] = keys
                self._hotkey_var = tk.StringVar(value=format_keys(keys))
                self._hotkey_entry = tk.Entry(
                    row, textvariable=self._hotkey_var,
                    bg=BG, fg=FG, insertbackground=FG,
                    relief="flat", bd=4, highlightthickness=1,
                    highlightcolor=NEON, highlightbackground=NEON_DIM,
                    font=FONT_SM,
                )
                self._hotkey_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self._hotkey_entry.bind("<Button-1>", lambda e: self._record_hotkey())
                self._hotkey_entry.bind("<KeyPress>", self._block_key)
                self._hotkey_entry.bind("<KeyRelease>", self._on_release)

                clr_lbl = tk.Label(row, text="CLEAR", bg=BUTTON, fg=FG,
                                   font=("Segoe UI", 8, "bold"), padx=8, pady=5,
                                   cursor="hand2")
                clr_lbl.pack(side=tk.RIGHT, padx=(4, 0))
                clr_lbl.bind("<Button-1>", lambda e: self._clear_hotkey())

        type_var.trace_add("write", _toggle_fields)
        self._btn_field_vars = {}
        self._btn_field_vars["app_icon_path"] = tk.StringVar(value=data.get("app_icon_path", ""))
        self._win.after(10, _toggle_fields)

        # Save / Cancel
        btn_row = tk.Frame(inner, bg=BG_CARD)
        btn_row.pack(fill=tk.X, pady=(12, 0))

        if not is_new:
            def _delete_curr(s=slot):
                self._delete_slot(s)
                self._button_editing_slot = None
                self._button_new_parent = None
                self._rebuild_buttons_view()
            delete_btn = RoundedButton(btn_row, text="DELETE", style="sec",
                                       bg=DANGER, hover=DANGER_HOVER,
                                       command=_delete_curr)
            delete_btn.pack(side="left")
            ToolTip(delete_btn, "Delete this button permanently")

        cancel_btn = RoundedButton(btn_row, text="CANCEL", style="sec",
                                   command=self._cancel_edit)
        cancel_btn.pack(side="right", padx=(4, 0))
        ToolTip(cancel_btn, "Discard changes and return to button list")
        save_btn = RoundedButton(btn_row, text="SAVE", style="prim",
                                 command=lambda: self._button_save(
                                     name_var, type_var, icon_var, color_var, is_new))
        save_btn.pack(side="right", padx=(0, 4))
        ToolTip(save_btn, "Save this button to the config")

    def _cancel_edit(self):
        self._button_editing_slot = None
        self._button_new_parent = None
        self._rebuild_buttons_view()

    def _button_save(self, name_var, type_var, icon_var, color_var, is_new):
        new_data = {
            "name": name_var.get().strip(),
            "type": type_var.get(),
            "icon": icon_var.get().strip() or "help-circle",
            "color": (color_var.get().strip() or ""),
        }
        av = self._btn_field_vars.get("app_icon_path")
        if av and av.get().strip():
            new_data["app_icon_path"] = av.get().strip()

        t = type_var.get()
        if t == "SHORTCUT":
            sv = self._btn_field_vars.get("shortcut_path")
            new_data["shortcut_path"] = sv.get().strip() if sv else ""
        elif t == "REST":
            ev = self._btn_field_vars.get("entity_id")
            new_data["entity_id"] = ev.get().strip() if ev else ""
        elif t == "OPENRGB":
            op = self._btn_field_vars.get("openrgb_profile")
            new_data["openrgb_profile"] = op.get().strip() if op else ""
        elif t == "HOTKEY":
            new_data["keys"] = self._btn_field_vars.get("_hotkey_keys", [])
        elif t == "GROUP":
            new_data["children"] = []
            sv = self._btn_field_vars.get("shortcut_path")
            new_data["shortcut_path"] = sv.get().strip() if sv else ""

        if is_new:
            target = self._button_new_parent
            if target is not None:
                target.append(new_data)
        else:
            old = self._button_editing_slot
            if old is not None:
                old_children = old.get("children") if isinstance(old, dict) else None
                old.clear()
                old.update(new_data)
                if t == "GROUP" and old_children is not None:
                    old["children"] = old_children

        save_config(self._cfg)
        self._button_editing_slot = None
        self._button_new_parent = None
        self._rebuild_buttons_view()

    # ── Hotkey recording ──────────────────────────────────────

    def _record_hotkey(self):
        self._pressed_keys = set()
        self._hotkey_var.set("Press a key combination...")
        self._hotkey_entry.configure(bg=NEON, fg=BG)
        self._hotkey_entry.focus_set()
        self._recording_hotkey = True

    def _clear_hotkey(self):
        self._btn_field_vars["_hotkey_keys"] = []
        self._hotkey_var.set("")

    def _block_key(self, e):
        if not getattr(self, "_recording_hotkey", False):
            return "break"
        vk = e.keycode
        if vk == 27:
            self._stop_recording()
            return "break"

        self._pressed_keys.add(vk)

        modifiers = {16, 17, 18, 91, 92}
        mods = sorted(k for k in self._pressed_keys if k in modifiers)
        action = [k for k in self._pressed_keys if k not in modifiers]

        combo = list(mods)
        combo.extend(action)
        self._hotkey_var.set(format_keys(combo))

        if action:
            self._btn_field_vars["_hotkey_keys"] = combo
            self._stop_recording()
        return "break"

    def _on_release(self, e):
        if not getattr(self, "_recording_hotkey", False):
            return
        self._pressed_keys.discard(e.keycode)

    def _stop_recording(self):
        self._recording_hotkey = False
        self._hotkey_entry.configure(bg=BG, fg=FG)

    # ── Media player helpers ──────────────────────────────────

    def _on_media_app_selected(self, e=None):
        name = self._media_combo_var.get()
        path = self._media_app_map.get(name, "")
        if path:
            self._media_path_var.set(path)

    def _browse_media(self):
        path = filedialog.askopenfilename(
            title="Select media player",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            parent=self._win,
        )
        if path:
            self._media_path_var.set(path)

    def _save_media_player_path(self):
        self._cfg["media_player_path"] = self._media_path_var.get().strip()
        save_config(self._cfg)

    def _save_temp_limits(self):
        self._cfg["cpu_temp_lim"] = self._to_int(self._cpu_lim_var.get(), 90)
        self._cfg["gpu_temp_lim"] = self._to_int(self._gpu_lim_var.get(), 90)
        save_config(self._cfg)

    @staticmethod
    def _to_int(s, default):
        try:
            return int(s.strip())
        except (ValueError, AttributeError):
            return default

    def _detect_media_apps(self):
        if not hasattr(self, "_media_combo"):
            return

        def _do():
            apps = scan_media_apps()

            def _update():
                if not apps:
                    return
                self._media_app_map = dict(apps)
                names = [n for n, _ in apps]
                self._media_combo.values = names
                current = self._media_path_var.get().strip()
                match = next((n for n, p in apps if p == current), None)
                if match:
                    self._media_combo_var.set(match)
                elif names and not current:
                    self._media_combo_var.set(names[0])

            try:
                self._win.after(0, _update)
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    # ── ABOUT TAB ─────────────────────────────────────────────

    def _build_about(self, f):
        main = tk.Frame(f, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        tk.Label(main, text=APP_NAME, font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=NEON).pack(anchor="w", pady=(0, 2))
        tk.Label(main, text=f"Version {APP_VERSION}", font=FONT_UI,
                 bg=BG, fg=FG_DIM).pack(anchor="w", pady=(0, 20))

        tk.Label(main, text="A custom monitor control panel for ESP8266-driven\ndisplays.",
                 font=FONT_UI, bg=BG, fg=FG, justify="left").pack(anchor="w", pady=(0, 24))

        tk.Frame(main, bg=NEON_DIM, height=1).pack(fill=tk.X, pady=(0, 12))

        RoundedButton(main, text="Factory Reset", command=self._factory_reset,
                      padx=14, pady=6, fg=NEON_RED).pack(anchor="w")

        tk.Frame(main, bg=BG, height=16).pack()

    def _ok(self):
        self._apply()
        self._win.destroy()

    # ── Apply / Refresh / Factory Reset ───────────────────────

    def _refresh(self):
        if not self._serial or not self._serial.connected_port():
            return
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        cfg = self._serial.get_config(timeout=3)
        if cfg:
            self._win.after(0, lambda: self._finish_refresh(cfg))

    def _finish_refresh(self, cfg):
        self._suppress_apply = True
        self._apply_config_to_ui(cfg)
        self._suppress_apply = False

    def _apply_config_to_ui(self, cfg):
        for key, _ in FEATURE_KEYS:
            raw = cfg.get(key, "0")
            if isinstance(raw, bool):
                self._vars[key].set(raw)
            else:
                self._vars[key].set(str(raw) == "1")

        # Derive clock mode from individual config keys
        large = cfg.get("feature_large_clock", False)
        day = cfg.get("feature_day_clock", False)
        if day:
            self._clock_mode_var.set("Day Clock")
        elif large:
            self._clock_mode_var.set("Large Clock")
        else:
            self._clock_mode_var.set("Small Clock")

        if hasattr(self, '_update_minute_bar_state'):
            self._update_minute_bar_state()

    def _sync_next_alarm(self):
        alarms = [a for a in self._cfg.get("alarms", [])
                  if a.get("enabled", False) and a.get("days", 0)]
        if not alarms:
            self._serial.set_live("alarm_enabled", "0")
            self._serial.queue_on_connect("alarm_enabled", "0")
            return
        alarm = _pick_next_alarm(alarms)
        for key, val in [
            ("alarm_hour",           str(alarm["hour"])),
            ("alarm_minute",         str(alarm["minute"])),
            ("alarm_days",           str(alarm["days"])),
            ("alarm_enabled",        "1"),
            ("alarm_clear_dismiss",  "1"),
            ("alarm_message",        alarm.get("message", "").replace("=", " ").replace("\n", " ")[:120]),
        ]:
            self._serial.set_live(key, val)
            self._serial.queue_on_connect(key, val)

    def _apply(self):
        for key, _ in FEATURE_KEYS:
            self._cfg[key] = self._vars[key].get()
        for key, var in self._text_vars.items():
            self._cfg[key] = var.get().strip()
        self._cfg["media_player_path"] = self._media_path_var.get().strip()
        self._cfg["cpu_temp_lim"] = self._to_int(self._cpu_lim_var.get(), 90)
        self._cfg["gpu_temp_lim"] = self._to_int(self._gpu_lim_var.get(), 90)

        # Write clock mode back to individual config keys
        mode = self._clock_mode_var.get()
        self._cfg["feature_large_clock"] = (mode == "Large Clock")
        self._cfg["feature_day_clock"] = (mode == "Day Clock")

        # Send minute bar immediately so the device removes/hides it right away
        mb_val = "1" if self._vars["feature_minute_bar"].get() else "0"
        if mode == "Large Clock":
            mb_val = "0"
        if self._serial and self._serial.connected_port():
            self._serial.set_live("feature_minute_bar", mb_val)

        if self._cfg:
            save_config(self._cfg)
        if not self._serial or not self._serial.connected_port():
            return

        def send_changes():
            for key, _ in FEATURE_KEYS:
                if key == "feature_minute_bar":
                    continue
                val = "1" if self._vars[key].get() else "0"
                self._serial.set_live(key, val)
                time.sleep(0.02)
            self._serial.set_live("feature_large_clock", "1" if mode == "Large Clock" else "0")
            time.sleep(0.02)
            self._serial.set_live("feature_day_clock", "1" if mode == "Day Clock" else "0")
            time.sleep(0.02)
            self._sync_next_alarm()
            log.info("[settings] applied")

        threading.Thread(target=send_changes, daemon=True).start()

    def _factory_reset(self):
        defaults = dict(DEFAULT_CONFIG)
        save_config(defaults)
        self._cfg.clear()
        self._cfg.update(defaults)
        self._suppress_apply = True
        self._apply_config_to_ui(self._cfg)
        self._suppress_apply = False
        self._apply()
        if self._serial:

            def do_reset():
                self._serial.factory_reset_with_reboot()
                self._win.after(2000, self._refresh)

            threading.Thread(target=do_reset, daemon=True).start()
        log.info("[settings] factory reset done")
