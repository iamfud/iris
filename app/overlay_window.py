"""Iris — Floating stats overlay window (imported from Derek Version1)."""

import ctypes
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk as _ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from constants import BG, BG_CARD, NEON, NEON_GRN, NEON_RED, FG_DIM, GAUGE_WARN
from widgets import CircularGauge
import mdi_icons

FONT_SM = ("Segoe UI", 9)

_MAGNET_ZONE = 160
_SNAP_ZONE   = 40
_ALPHA_MAX   = 0.7
_FADE_STEPS  = 8
_FADE_MS     = 22
_HANDLE_H    = 22

_GWL_EXSTYLE       = -20
_WS_EX_LAYERED     = 0x80000
_WS_EX_TRANSPARENT = 0x20

_WIDTHS = {"gauges": 360, "compact": 270, "numbers": 100, "numline": 350}
_STYLES = ["gauges", "compact", "numbers", "numline"]
_NUMLINE_SIZES = {"S": 9, "M": 11, "L": 13}


class OverlayWindow:
    """Borderless always-click-through overlay fed by a stats provider."""

    def __init__(self, parent, stats_provider, fps_max=144, style="gauges",
                 on_close=None, numline_font_size="M"):
        self._provider        = stats_provider
        self._fps_max         = fps_max
        self._closed          = False
        self._on_close        = on_close
        self._style           = style if style in _WIDTHS else "gauges"
        self._dock            = "right"
        self._numline_fsize   = _NUMLINE_SIZES.get(str(numline_font_size), 11)

        self._gauges    = {}
        self._num_vars  = {}
        self._num_labels = {}

        self._handle_win = None
        self._hdrag_x  = self._hdrag_y  = self._hdrag_ox  = self._hdrag_oy  = None
        self._wdrag_x  = self._wdrag_y  = self._wdrag_ox  = self._wdrag_oy  = None

        self._win = tk.Toplevel(parent)
        self._win.configure(bg=BG_CARD if self._style == "numline" else BG)
        self._win.wm_overrideredirect(True)
        self._win.attributes("-alpha", 0.0)
        self._win.attributes("-topmost", True)
        self._win.update()

        self._build()
        if self._style != "numline":
            self._apply_click_through()
        self._pin_side("right")
        self._build_handle(parent)
        if self._style == "numline":
            self._handle_win.withdraw()
        self._fade_in()
        self._win.after(0, self._poll)

    def set_style(self, style):
        if style == self._style or style not in _WIDTHS:
            return
        prev = self._style
        self._views[prev].pack_forget()
        self._style = style
        self._views[style].pack(fill="x")
        self._win.update_idletasks()

        if style == "numline":
            self._win.configure(bg=BG_CARD)
            self._set_click_through(False)
            if self._handle_win:
                self._handle_win.withdraw()
        else:
            self._win.configure(bg=BG)
            self._set_click_through(True)
            if self._handle_win and prev == "numline":
                self._handle_win.deiconify()

        if self._dock:
            self._pin_side(self._dock)
        else:
            w = _WIDTHS[style]
            h = self._win.winfo_reqheight()
            self._win.geometry(f"{w}x{h}+{self._win.winfo_x()}+{self._win.winfo_y()}")
        if style != "numline":
            self._sync_handle()

    def fade_close(self, callback=None):
        try:
            cur = self._win.attributes("-alpha")
        except Exception:
            return
        nxt = cur - _ALPHA_MAX / _FADE_STEPS
        if nxt > 0:
            try:
                self._win.attributes("-alpha", nxt)
                if self._handle_win:
                    self._handle_win.attributes("-alpha", nxt)
            except Exception:
                return
            self._win.after(_FADE_MS, lambda: self.fade_close(callback))
        else:
            self._do_close(callback)

    def close(self):
        self.fade_close()

    # ── Build ──

    def _build(self):
        self._views = {}

        gv = tk.Frame(self._win, bg=BG)
        self._views["gauges"] = gv
        self._build_gauge_frame(gv, "gauges", size=110)

        cv = tk.Frame(self._win, bg=BG)
        self._views["compact"] = cv
        self._build_gauge_frame(cv, "compact", size=70)

        nv = tk.Frame(self._win, bg=BG)
        self._views["numbers"] = nv
        self._build_numbers_frame(nv)

        nlv = tk.Frame(self._win, bg=BG_CARD)
        self._views["numline"] = nlv
        self._build_numline_frame(nlv)

        self._views[self._style].pack(fill="x")
        self._win.update_idletasks()

    def _build_gauge_frame(self, parent, style_key, size):
        self._gauges[style_key] = {}
        inner = tk.Frame(parent, bg=BG, padx=8, pady=8)
        inner.pack(fill="x")
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(2, weight=1)
        for col, (key, label, vmax, unit) in enumerate([
            ("cpu_temp", "CPU", 100,           "\u00b0"),
            ("gpu_temp", "GPU", 100,           "\u00b0"),
            ("fps",      "FPS",      self._fps_max, ""),
        ]):
            f = tk.Frame(inner, bg=BG)
            f.grid(row=0, column=col, sticky="nsew")
            g = CircularGauge(f, label=label, max_value=vmax, unit=unit,
                              size=size, bg=BG)
            g.pack()
            self._gauges[style_key][key] = g

    def _build_numbers_frame(self, parent):
        self._num_labels["numbers"] = {}
        inner = tk.Frame(parent, bg=BG, padx=6, pady=8)
        inner.pack(fill="x")
        for key, label, unit in [
            ("cpu_temp", "CPU", "\u00b0"),
            ("gpu_temp", "GPU", "\u00b0"),
            ("fps",      "FPS", ""),
        ]:
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=BG, fg=FG_DIM,
                     font=("Segoe UI", 9), width=4, anchor="w").pack(side="left")
            var = tk.StringVar(value="\u2014")
            self._num_vars[key] = var
            val_lbl = tk.Label(row, textvariable=var, bg=BG, fg=NEON,
                               font=("Segoe UI", 20, "bold"), anchor="w")
            val_lbl.pack(side="left")
            self._num_labels["numbers"][key] = val_lbl

    def _build_numline_frame(self, parent):
        self._num_labels["numline"] = {}
        bar = tk.Frame(parent, bg=BG_CARD, padx=8, pady=6)
        bar.pack(fill="x")

        bar.bind("<Button-1>",        self._wdrag_start)
        bar.bind("<B1-Motion>",       self._wdrag_move)
        bar.bind("<ButtonRelease-1>", self._wdrag_end)

        close_lbl = tk.Label(bar, text="\u2715", bg=BG_CARD, fg=FG_DIM,
                             font=("Segoe UI", 10), cursor="hand2")
        close_lbl.pack(side="right", padx=(0, 2))
        close_lbl.bind("<Button-1>", self._close_click)

        self._mdi_cycle_num = mdi_icons.render_tk("application-brackets-outline", 14, (102, 102, 102))
        if self._mdi_cycle_num:
            cycle_lbl = tk.Label(bar, image=self._mdi_cycle_num, bg=BG_CARD, cursor="hand2")
        else:
            cycle_lbl = tk.Label(bar, text="\u229e", bg=BG_CARD, fg=FG_DIM,
                                 font=("Segoe UI", 10), cursor="hand2")
        cycle_lbl.pack(side="right", padx=(0, 8))
        cycle_lbl.bind("<Button-1>", self._cycle_style)

        fs = self._numline_fsize
        for i, (key, label, unit) in enumerate([
            ("cpu_temp", "CPU", "\u00b0"),
            ("gpu_temp", "GPU", "\u00b0"),
            ("fps",      "FPS", ""),
        ]):
            if key not in self._num_vars:
                self._num_vars[key] = tk.StringVar(value="\u2014")
            tk.Label(bar, text=label, bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", fs)).pack(side="left")
            w = 5 if key == "fps" else 3
            val_lbl = tk.Label(bar, textvariable=self._num_vars[key], bg=BG_CARD, fg=NEON,
                               font=("Segoe UI", fs, "bold"),
                               width=w, anchor="e")
            val_lbl.pack(side="left", padx=(2, 0))
            self._num_labels["numline"][key] = val_lbl

    # ── Window-level drag (numline only) ──

    def _wdrag_start(self, e):
        self._wdrag_x  = e.x_root
        self._wdrag_y  = e.y_root
        self._wdrag_ox = self._win.winfo_x()
        self._wdrag_oy = self._win.winfo_y()

    def _wdrag_move(self, e):
        if self._wdrag_x is None:
            return
        dx = e.x_root - self._wdrag_x
        dy = e.y_root - self._wdrag_y
        sx = self._win.winfo_screenwidth()
        sy = self._win.winfo_screenheight()
        w  = _WIDTHS["numline"]
        h  = self._win.winfo_height()
        tx = max(0, min(sx - w, self._wdrag_ox + dx))
        ty = max(0, min(sy - h, self._wdrag_oy + dy))
        dl = tx
        dr = (sx - w) - tx
        dist, ex = (dl, 0) if dl <= dr else (dr, sx - w)
        if dist <= _SNAP_ZONE:
            nx = ex
        elif dist <= _MAGNET_ZONE:
            t  = 1.0 - (dist - _SNAP_ZONE) / (_MAGNET_ZONE - _SNAP_ZONE)
            nx = int(tx + (ex - tx) * t * t * t)
        else:
            nx = tx
            self._dock = None
        self._win.geometry(f"{w}x{h}+{nx}+{ty}")

    def _wdrag_end(self, e):
        self._wdrag_x = None
        sx = self._win.winfo_screenwidth()
        nx = self._win.winfo_x()
        w  = _WIDTHS["numline"]
        if nx <= _SNAP_ZONE:
            self._dock = "left";  self._pin_side("left")
        elif nx + w >= sx - _SNAP_ZONE:
            self._dock = "right"; self._pin_side("right")

    # ── Drag handle ──

    @staticmethod
    def _make_drag_icon(size=16):
        if not _PIL_OK:
            return None
        scale = 4
        s     = size * scale
        bg_rgb = tuple(int(BG.lstrip("#")[i:i+2],     16) for i in (0, 2, 4))
        fg_rgb = tuple(int(FG_DIM.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        img  = Image.new("RGB", (s, s), bg_rgb)
        draw = ImageDraw.Draw(img)
        cx = cy  = s // 2
        arm      = int(s * 0.26)
        tip      = int(s * 0.46)
        hw       = int(s * 0.16)
        thick    = max(2, int(s * 0.07))
        draw.line([(cx, cy - arm), (cx, cy + arm)], fill=fg_rgb, width=thick)
        draw.line([(cx - arm, cy), (cx + arm, cy)], fill=fg_rgb, width=thick)
        draw.polygon([(cx-hw, cy-arm), (cx+hw, cy-arm), (cx,     cy-tip)], fill=fg_rgb)
        draw.polygon([(cx-hw, cy+arm), (cx+hw, cy+arm), (cx,     cy+tip)], fill=fg_rgb)
        draw.polygon([(cx+arm, cy-hw), (cx+arm, cy+hw), (cx+tip, cy    )], fill=fg_rgb)
        draw.polygon([(cx-arm, cy-hw), (cx-arm, cy+hw), (cx-tip, cy    )], fill=fg_rgb)
        img = img.resize((size, size), Image.LANCZOS)
        return _ImageTk.PhotoImage(img)

    def _build_handle(self, parent):
        hw = _WIDTHS[self._style]
        self._handle_win = tk.Toplevel(parent)
        self._handle_win.wm_overrideredirect(True)
        self._handle_win.attributes("-topmost", True)
        self._handle_win.attributes("-alpha", 0.0)
        self._handle_win.configure(bg=BG)

        bar = tk.Frame(self._handle_win, bg=BG, padx=4, pady=2)
        bar.pack(fill="both", expand=True)

        bar.bind("<Button-1>",        self._hdrag_start)
        bar.bind("<B1-Motion>",       self._hdrag_move)
        bar.bind("<ButtonRelease-1>", self._hdrag_end)

        close_lbl = tk.Label(bar, text="\u2715", bg=BG, fg=FG_DIM, font=FONT_SM, cursor="hand2")
        close_lbl.pack(side="right", padx=(0, 2))
        close_lbl.bind("<Button-1>", self._close_click)
        self._mdi_cycle = mdi_icons.render_tk("application-brackets-outline", 14, (102, 102, 102))
        if self._mdi_cycle:
            cycle_lbl = tk.Label(bar, image=self._mdi_cycle, bg=BG, cursor="hand2")
        else:
            cycle_lbl = tk.Label(bar, text="\u229e", bg=BG, fg=FG_DIM,
                                 font=FONT_SM, cursor="hand2")
        cycle_lbl.pack(side="right", padx=(0, 6))
        cycle_lbl.bind("<Button-1>", self._cycle_style)

        self._sync_handle()

    def _close_click(self, e):
        self.fade_close()
        return "break"

    def _cycle_style(self, e):
        self.set_style(_STYLES[(_STYLES.index(self._style) + 1) % len(_STYLES)])
        return "break"

    # ── Click-through ──

    def _apply_click_through(self):
        self._set_click_through(True)

    def _set_click_through(self, enabled):
        try:
            hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id()) or self._win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            if enabled:
                style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
            else:
                style = (style | _WS_EX_LAYERED) & ~_WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
        except Exception:
            pass

    # ── Positioning ──

    def _pin_side(self, side):
        win = self._win
        win.update_idletasks()
        w  = _WIDTHS[self._style]
        h  = win.winfo_reqheight()
        sx = win.winfo_screenwidth()
        sy = win.winfo_screenheight()
        x  = 0 if side == "left" else sx - w
        cur_y = win.winfo_y()
        y     = cur_y if 0 <= cur_y <= sy - h else (sy - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _sync_handle(self):
        if self._handle_win is None or self._closed or self._style == "numline":
            return
        try:
            self._win.update_idletasks()
            mx = self._win.winfo_x()
            my = self._win.winfo_y()
            mh = self._win.winfo_height()
            hw = _WIDTHS[self._style]
            self._handle_win.geometry(f"{hw}x{_HANDLE_H}+{mx}+{my + mh}")
        except Exception:
            pass

    # ── Handle drag ──

    def _hdrag_start(self, e):
        self._hdrag_x  = e.x_root
        self._hdrag_y  = e.y_root
        self._hdrag_ox = self._handle_win.winfo_x()
        self._hdrag_oy = self._handle_win.winfo_y()

    def _hdrag_move(self, e):
        if self._hdrag_x is None:
            return
        dx = e.x_root - self._hdrag_x
        dy = e.y_root - self._hdrag_y
        sx = self._handle_win.winfo_screenwidth()
        sy = self._handle_win.winfo_screenheight()
        w  = _WIDTHS[self._style]
        mh = self._win.winfo_height()

        true_hx = self._hdrag_ox + dx
        true_hy = self._hdrag_oy + dy
        true_hx = max(0, min(sx - w, true_hx))
        true_hy = max(mh, min(sy - _HANDLE_H, true_hy))

        dist_left  = true_hx
        dist_right = (sx - w) - true_hx
        if dist_left <= dist_right:
            dist, edge_x = dist_left, 0
        else:
            dist, edge_x = dist_right, sx - w

        if dist <= _SNAP_ZONE:
            hx = edge_x
        elif dist <= _MAGNET_ZONE:
            t  = 1.0 - (dist - _SNAP_ZONE) / (_MAGNET_ZONE - _SNAP_ZONE)
            hx = int(true_hx + (edge_x - true_hx) * t * t * t)
        else:
            hx = true_hx
            self._dock = None

        hy = true_hy
        self._handle_win.geometry(f"{w}x{_HANDLE_H}+{hx}+{hy}")
        self._win.geometry(f"{w}x{mh}+{hx}+{hy - mh}")

    def _hdrag_end(self, e):
        if self._hdrag_x is None:
            return
        self._hdrag_x = None
        sx = self._handle_win.winfo_screenwidth()
        hx = self._handle_win.winfo_x()
        w  = _WIDTHS[self._style]
        if hx <= _SNAP_ZONE:
            self._dock = "left"
            self._pin_side("left")
            self._sync_handle()
        elif hx + w >= sx - _SNAP_ZONE:
            self._dock = "right"
            self._pin_side("right")
            self._sync_handle()

    # ── Fade ──

    def _fade_in(self, step=0):
        alpha = _ALPHA_MAX * (step + 1) / _FADE_STEPS
        try:
            self._win.attributes("-alpha", alpha)
            if self._handle_win:
                self._handle_win.attributes("-alpha", alpha)
        except Exception:
            return
        if step < _FADE_STEPS - 1:
            self._win.after(_FADE_MS, lambda: self._fade_in(step + 1))

    def _do_close(self, callback=None):
        self._closed = True
        if self._handle_win is not None:
            try:
                self._handle_win.destroy()
            except Exception:
                pass
            self._handle_win = None
        try:
            self._win.destroy()
        except Exception:
            pass
        if self._on_close:
            self._on_close()
        if callback:
            callback()

    # ── Poll ──

    def _reassert_topmost(self):
        _HWND_TOPMOST = -1
        _SWP_FLAGS    = 0x0001 | 0x0002 | 0x0010
        for win in (self._win, self._handle_win):
            if win is None:
                continue
            try:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
                ctypes.windll.user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_FLAGS)
            except Exception:
                pass

    def _poll(self):
        if self._closed:
            return
        self._reassert_topmost()
        try:
            s = self._provider.snapshot()
            cpu_temp, gpu_temp, fps = s.cpu_temp, s.gpu_temp, s.fps
            cpu_max = getattr(s, "cpu_temp_max", 100)
            gpu_max = getattr(s, "gpu_temp_max", 100)
            fps_max = getattr(s, "refresh_rate", None) or getattr(s, "fps_max", 60) or 60
            if self._fps_max != fps_max:
                self._fps_max = fps_max
            fps_val = min(fps, self._fps_max) if fps is not None else None

            for gauge_map in self._gauges.values():
                cpu_g = gauge_map["cpu_temp"]
                gpu_g = gauge_map["gpu_temp"]
                fps_g = gauge_map["fps"]
                if cpu_g.max_value != cpu_max:
                    cpu_g.set_max(cpu_max)
                if gpu_g.max_value != gpu_max:
                    gpu_g.set_max(gpu_max)
                if fps_g.max_value != self._fps_max:
                    fps_g.set_max(self._fps_max)
                if cpu_g.unit != getattr(s, "cpu_temp_unit", "\u00b0C").replace("\u00b0", ""):
                    cpu_g.set_unit(getattr(s, "cpu_temp_unit", "\u00b0C").replace("\u00b0", ""))
                if gpu_g.unit != getattr(s, "gpu_temp_unit", "\u00b0C").replace("\u00b0", ""):
                    gpu_g.set_unit(getattr(s, "gpu_temp_unit", "\u00b0C").replace("\u00b0", ""))
                cpu_g.set_value(cpu_temp)
                gpu_g.set_value(gpu_temp)
                fps_g.set_value(fps_val)

            if self._num_vars:
                self._num_vars["cpu_temp"].set(f"{int(cpu_temp)}" if cpu_temp is not None else "\u2014")
                self._num_vars["gpu_temp"].set(f"{int(gpu_temp)}" if gpu_temp is not None else "\u2014")
                self._num_vars["fps"].set(f"{int(fps_val)}"      if fps_val  is not None else "\u2014")

            labels = self._num_labels.get(self._style, {})
            if "cpu_temp" in labels:
                labels["cpu_temp"].configure(fg=self._text_color("cpu_temp", cpu_temp, cpu_max))
                labels["gpu_temp"].configure(fg=self._text_color("gpu_temp", gpu_temp, gpu_max))
                labels["fps"].configure(fg=self._text_color("fps", fps_val, self._fps_max))
        except Exception:
            pass
        try:
            self._win.after(2000, self._poll)
        except Exception:
            pass

    def _text_color(self, key, value, max_value):
        if value is None:
            return NEON
        if key == "fps":
            if value < 55:
                return NEON_RED
            ratio = min(value, max_value) / max_value if max_value > 0 else 0
            return NEON_GRN if ratio >= 0.8 else NEON
        ratio = value / max_value if max_value > 0 else 0
        if ratio >= 0.9:
            return NEON_RED
        if ratio >= 0.65:
            return GAUGE_WARN
        return NEON
