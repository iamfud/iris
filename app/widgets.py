"""Iris — Custom widgets."""

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont

from constants import BG, BG_CARD, NEON, NEON_DIM, NEON_GRN, NEON_RED, GAUGE_WARN, BUTTON_HOVER, BUTTON, BORDER, FG, FG_DIM, FONT_SM, DANGER, DANGER_HOVER, RADIUS_CARD

# ── Outside-click management ────────────────────────────────────
_outside_handlers = {}
_next_token = 0
_bound_root = None

def _bind_outside(root, cb):
    global _next_token, _bound_root
    token = _next_token
    _next_token += 1
    _outside_handlers[token] = cb
    if _bound_root is None:
        _bound_root = root
        root.bind_all("<Button-1>", _dispatch_outside, add=True)
    return token

def _unbind_outside(token):
    global _bound_root
    _outside_handlers.pop(token, None)
    if not _outside_handlers and _bound_root is not None:
        try:
            _bound_root.unbind_all("<Button-1>")
        except Exception:
            pass
        _bound_root = None

def _dispatch_outside(e):
    for cb in list(_outside_handlers.values()):
        try:
            cb(e)
        except Exception:
            pass


_FONT_CACHE = {}

def _load_font(family, size, bold=False):
    key = (family.lower(), size, bold)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    stems = {"consolas": "consola", "couriernew": "cour", "timesnewroman": "times"}
    name = stems.get(family.lower().replace(" ", ""), family.lower().replace(" ", ""))
    stem = f"{name}{'b' if bold else ''}"
    for p in [f"C:/Windows/Fonts/{stem}.ttf", f"C:/Windows/Fonts/{name}.ttf"]:
        try:
            fnt = ImageFont.truetype(p, size)
            _FONT_CACHE[key] = fnt
            return fnt
        except Exception:
            pass
    fnt = ImageFont.load_default()
    _FONT_CACHE[key] = fnt
    return fnt


class StepSlider:
    """Windows 11-style horizontal slider that snaps to discrete steps."""
    _TRACK_H = 6
    _THUMB_R = 10
    _H       = 28
    _PX      = 12

    def __init__(self, parent, steps, var, on_change=None, bg=BG_CARD,
                 track_fill=None, track_bg=None, thumb_color=None, px=12):
        self._steps       = steps
        self._var         = var
        self._cb          = on_change
        self._bg          = bg
        self._track_fill  = track_fill  if track_fill  is not None else NEON
        self._track_bg    = track_bg    if track_bg    is not None else NEON_DIM
        self._thumb_color = thumb_color if thumb_color is not None else BUTTON_HOVER
        self._thumb_img   = None
        self._px          = px
        self._cv    = tk.Canvas(parent, width=1, height=self._H, bg=bg,
                                highlightthickness=0, bd=0, cursor="hand2")
        self._cv.bind("<Configure>",  lambda e: self._draw())
        self._cv.bind("<Button-1>",   self._on_press)
        self._cv.bind("<B1-Motion>",  self._on_press)
        var.trace_add("write", lambda *_: self._draw())

    def place(self, **kw):
        self._cv.place(**kw)

    def _idx(self):
        val = self._var.get()
        try:
            return self._steps.index(val)
        except (ValueError, AttributeError):
            return 0

    def _rtrack(self, x1, y, x2, r, color):
        pts = [
            x1,    y-r,  x1,    y-r,
            x2,    y-r,  x2,    y-r,
            x2+r,  y-r,
            x2+r,  y,    x2+r,  y,
            x2+r,  y+r,
            x2,    y+r,  x2,    y+r,
            x1,    y+r,  x1,    y+r,
            x1-r,  y+r,
            x1-r,  y,    x1-r,  y,
            x1-r,  y-r,
        ]
        self._cv.create_polygon(pts, smooth=True, fill=color, outline="")

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        w = cv.winfo_width()
        if w < 20:
            return
        py = self._H // 2
        px = self._px
        tw = w - 2 * px
        r  = self._TRACK_H // 2
        n  = len(self._steps)
        tx = px + tw * self._idx() // max(n - 1, 1)

        self._rtrack(px, py, w - px, r, self._track_bg)
        if tx > px:
            self._rtrack(px, py, tx, r, self._track_fill)
        if self._thumb_img is None:
            self._thumb_img = self._make_thumb()
        cv.create_image(tx, py, anchor="center", image=self._thumb_img)

    def _make_thumb(self):
        import io as _io, base64 as _b64
        scale = 4
        tr    = self._THUMB_R
        ir    = max(2, tr - 5)
        size  = tr * 2 * scale
        cx = cy = size // 2

        def _hex(h):
            return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))

        def _luminance(h):
            r, g, b = _hex(h)
            return (0.299*r + 0.587*g + 0.114*b) / 255

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.ellipse([cx - tr*scale, cy - tr*scale, cx + tr*scale - 1, cy + tr*scale - 1],
                  fill=(*_hex(self._thumb_color), 255))
        inner_col = BG if _luminance(self._bg) > 0.3 else NEON
        d.ellipse([cx - ir*scale, cy - ir*scale, cx + ir*scale - 1, cy + ir*scale - 1],
                  fill=(*_hex(inner_col), 255))

        final = img.resize((tr * 2, tr * 2), Image.LANCZOS)
        buf   = _io.BytesIO()
        final.save(buf, format="PNG")
        b64   = _b64.b64encode(buf.getvalue()).decode("ascii")
        return tk.PhotoImage(data=b64, master=self._cv)

    def _on_press(self, e):
        w  = self._cv.winfo_width()
        px = self._px
        tw = w - 2 * px
        n  = len(self._steps)
        frac = max(0.0, min(1.0, (e.x - px) / max(tw, 1)))
        idx  = round(frac * (n - 1))
        new  = self._steps[idx]
        if new != self._var.get():
            self._var.set(new)
            if self._cb:
                self._cb()


class CircularGauge(tk.Canvas):
    def __init__(self, parent, label, max_value, unit="", size=70, thickness=None, bg=BG, **kw):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, **kw)
        self.label = label
        self.max_value = max(1.0, float(max_value))
        self.unit = unit
        self.size = size
        self.thickness = thickness if thickness is not None else max(3, size // 10)
        self._value = None
        self._tk_img = None
        self._draw("\u2014")

    def _last_text(self):
        return getattr(self, "_last_center_text", None)

    def set_max(self, max_value):
        self.max_value = max(1.0, float(max_value))
        self._draw(self._value_text(self._value))

    def set_value(self, value):
        self._value = value
        text = self._value_text(value)
        if text == self._last_text():
            return
        self._draw(text)

    def _value_text(self, value):
        if value is None:
            return "\u2014"
        return f"{int(round(value))}{self.unit}"

    def _gauge_color(self, ratio):
        if not self.unit:
            return NEON_GRN if ratio >= 0.8 else NEON
        if ratio < 0.65:
            return NEON
        if ratio < 0.9:
            return GAUGE_WARN
        return NEON_RED

    def _draw(self, center_text):
        self._last_center_text = center_text
        import io as _io, base64 as _b64
        self.delete("all")
        scale = 2
        w = self.size * scale
        h = self.size * scale
        pad = 8 * scale
        thick = self.thickness * scale
        x0 = y0 = pad
        x1 = y1 = w - pad

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        def _rgb(c):
            c = c.lstrip("#")
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

        start = 135
        sweep = 270

        d.arc((x0, y0, x1, y1), start=start, end=start + sweep,
              fill=_rgb(BG_CARD) + (255,), width=thick)

        ratio = 0.0
        if self._value is not None:
            v = max(0.0, min(float(self._value), self.max_value))
            ratio = v / self.max_value
            col = _rgb(self._gauge_color(ratio)) + (255,)
            d.arc((x0, y0, x1, y1), start=start, end=start + sweep * ratio,
                  fill=col, width=thick)

        val_font = _load_font("Segoe UI", max(8, int(self.size * 0.22 * scale)))
        sub_font = _load_font("Segoe UI", max(6, int(self.size * 0.12 * scale)))
        cx = cy = (self.size * scale) // 2

        vb = d.textbbox((0, 0), center_text, font=val_font)
        d.text((cx - (vb[2] - vb[0]) // 2, cy - 8 * scale - (vb[3] - vb[1]) // 2),
               center_text, fill=_rgb(NEON) + (255,), font=val_font)

        lb = d.textbbox((0, 0), self.label, font=sub_font)
        d.text((cx - (lb[2] - lb[0]) // 2, h - (lb[3] - lb[1]) - 4 * scale),
               self.label, fill=(255, 255, 255, 255), font=sub_font)

        img = img.resize((self.size, self.size), Image.Resampling.LANCZOS)

        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        self._tk_img = tk.PhotoImage(
            data=_b64.b64encode(buf.getvalue()).decode("ascii"), master=self)
        self.create_image(0, 0, anchor="nw", image=self._tk_img)


class RoundedButton(tk.Canvas):
    """PIL-rendered flat button with anti-aliased rounded corners."""

    _render_cache = {}

    def __init__(self, parent, text="", command=None, style="sec",
                 radius=6, fg=None, bg=None, hover=None,
                 font=None, padx=14, pady=7, **kw):
        import tkinter.font as _tkf
        self._command = command
        self._radius  = radius
        self._text    = text
        self._font    = font or FONT_SM
        self._inside  = False
        self._disabled = False
        self._img     = None
        self._last_wh = (0, 0)
        self._inside_changed = True

        if style == "prim":
            self._bg    = bg    or NEON
            self._fg    = fg    or BG
            self._hover = hover or "#5cc8f8"
        else:
            self._bg    = bg    or BUTTON_HOVER
            self._fg    = fg    or FG
            self._hover = hover or "#454545"

        try:
            self._pbg = parent.cget("bg")
        except Exception:
            self._pbg = BG

        _f  = _tkf.Font(font=self._font)
        tw  = _f.measure(text)
        th  = _f.metrics("linespace")
        w   = tw + padx * 2
        h   = th + pady * 2

        super().__init__(parent, width=w, height=h,
                         highlightthickness=0, bd=0,
                         bg=self._pbg, cursor="hand2", **kw)

        self.bind("<Configure>",       lambda e: self._on_configure())
        self.bind("<Enter>",           lambda e: self._enter())
        self.bind("<Leave>",           lambda e: self._leave())
        self.bind("<Button-1>",        lambda e: self._press())
        self.bind("<ButtonRelease-1>", lambda e: self._release())

    def _on_configure(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if (w, h) == self._last_wh and not self._inside_changed:
            return
        self._last_wh = (w, h)
        self._inside_changed = False
        self._render()

    def _enter(self):
        self._inside = True
        self._inside_changed = True
        self._render()

    def _leave(self):
        self._inside = False
        self._inside_changed = True
        self._render()

    def _press(self):
        if self._command:
            self._command()

    def _release(self):
        pass

    def _render(self, *_):
        import io as _io, base64 as _b64
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2 or h < 2:
            return

        col = self._hover if self._inside else self._bg
        scale = 2
        cache_key = (w, h, col, self._radius, self._pbg)
        cached = self._render_cache.get(cache_key)
        if cached is not None:
            self._img = cached
            self.delete("all")
            self.create_image(0, 0, anchor="nw", image=self._img)
            self.create_text(w // 2, h // 2, text=self._text, fill=self._fg, font=self._font)
            return

        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, sw - 1, sh - 1],
                            radius=self._radius * scale,
                            fill=(*self._parse(col), 255))
        final = img.resize((w, h), Image.LANCZOS)
        bg_img = Image.new("RGBA", (w, h), (*self._parse(self._pbg), 255))
        bg_img.alpha_composite(final)
        buf = _io.BytesIO()
        bg_img.convert("RGB").save(buf, format="PNG")
        self._img = tk.PhotoImage(
            data=_b64.b64encode(buf.getvalue()).decode("ascii"), master=self)
        self._render_cache[cache_key] = self._img
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._img)
        self.create_text(w // 2, h // 2, text=self._text, fill=self._fg, font=self._font)

    @staticmethod
    def _parse(hex_color):
        c = hex_color.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    def config(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
        if "command" in kw:
            self._command = kw.pop("command")
        super().config(**kw)
        self._render()

    configure = config


class DarkCombobox:
    """Custom combobox — tk.Frame + Entry + Label arrow + Toplevel Listbox."""

    def __init__(self, parent, values=None, textvariable=None, **kw):
        self._values = values or []
        self._popup = None
        self._dropdown_open = False
        self._outside_token = None

        self._frame = tk.Frame(parent, bg=BG)
        self._entry = tk.Entry(self._frame, textvariable=textvariable,
                               bg=BG, fg=FG, insertbackground=NEON,
                               font=FONT_SM, relief="flat", bd=5,
                                highlightthickness=1,
                                highlightcolor=NEON, highlightbackground=BG_CARD)
        self._entry.bind("<Key>", lambda e: "break")
        self._entry.pack(side="left", fill="x", expand=True)
        self._arrow = tk.Label(self._frame, text="\u25BC", bg=BG, fg=NEON,
                               font=("Segoe UI", 10), padx=8, pady=3, cursor="hand2")
        self._arrow.pack(side="right")

        self._entry.bind("<Button-1>", lambda e: self.toggle())
        self._arrow.bind("<Button-1>", lambda e: self.toggle())

        if textvariable is None:
            textvariable = tk.StringVar()
        self._var = textvariable

    def toggle(self):
        if self._dropdown_open:
            self._hide()
        else:
            self._show()

    def _show(self):
        self._dropdown_open = True
        self._popup = tk.Toplevel(self._frame)
        self._popup.wm_overrideredirect(True)
        self._popup.configure(bg=BG_CARD)
        self._popup.attributes("-topmost", True)
        self._popup.focus_set()

        lb = tk.Listbox(self._popup, bg=BG_CARD, fg=FG,
                        font=FONT_SM, bd=0, highlightthickness=0,
                        selectbackground=NEON, selectforeground=BG,
                        activestyle="none", relief="flat",
                        exportselection=False)
        lb.pack(fill="both", expand=True, padx=2, pady=2)

        for v in self._values:
            lb.insert("end", f"  {v}  ")

        cur = self._var.get()
        if cur in self._values:
            idx = self._values.index(cur)
            lb.selection_set(idx)
            lb.activate(idx)
            lb.see(idx)

        lb.bind("<ButtonRelease-1>", lambda e: self._select(lb))
        lb.bind("<Motion>", lambda e: self._hover(lb, e))

        self._popup.update_idletasks()
        x = self._frame.winfo_rootx()
        y = self._frame.winfo_rooty() + self._frame.winfo_height()
        w = max(self._frame.winfo_width(), 200)
        h = min(len(self._values) * 20, 160)
        self._popup.geometry(f"{w}x{h}+{x}+{y}")

        root = self._frame.winfo_toplevel()
        self._outside_token = _bind_outside(root, self._hide_outside)

    def _hide(self):
        self._dropdown_open = False
        if self._outside_token is not None:
            _unbind_outside(self._outside_token)
            self._outside_token = None
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _select(self, lb):
        sel = lb.curselection()
        if sel:
            self._var.set(lb.get(sel[0]).strip())
            self._frame.event_generate("<<ComboboxSelected>>")
        self._hide()

    def _hover(self, lb, e):
        idx = lb.nearest(e.y)
        if 0 <= idx < lb.size():
            lb.selection_clear(0, "end")
            lb.selection_set(idx)
            lb.activate(idx)

    def _hide_outside(self, e):
        if not self._popup:
            return
        w = e.widget
        while w:
            if w == self._popup or w == self:
                return
            w = w.master
        self._hide()

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, v):
        self._values = v

    def get(self):
        return self._var.get()

    def set(self, v):
        self._var.set(v)

    def bind(self, seq, cb, **kw):
        self._frame.bind(seq, cb, **kw)

    def pack(self, **kw):
        self._frame.pack(**kw)

    def grid(self, **kw):
        self._frame.grid(**kw)

    def place(self, **kw):
        self._frame.place(**kw)


class Toggle:
    """PIL-rendered pill toggle switch — on/off with neon track."""

    W = 36
    H = 20

    def __init__(self, parent, var, on_change=None, bg=BG_CARD):
        self._var = var
        self._on_change = on_change
        self._bg = bg
        self._disabled = False

        self._canvas = tk.Canvas(parent, width=self.W, height=self.H,
                                 highlightthickness=0, bd=0, bg=bg,
                                 cursor="hand2")
        self._canvas.bind("<Button-1>", lambda e: self._click())
        self._var.trace_add("write", lambda *_: self._draw())

        self._img_off = self._render(False)
        self._img_on = self._render(True)
        self._img_disabled_off = self._disabled_render(False)
        self._img_disabled_on = self._disabled_render(True)
        self._draw()

    def _render(self, on):
        import io as _io, base64 as _b64
        scale = 4
        sw, sh = self.W * scale, self.H * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = self.H * scale // 2
        track = NEON if on else "#252525"
        thumb_color = "#0a0a0a" if on else "#444444"
        d.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=r,
                            fill=(*_parse(track), 255))
        thumb_size = (self.H - 6) * scale
        tx = (self.W - self.H + 3) * scale if on else 3 * scale
        d.ellipse([tx, 3 * scale, tx + thumb_size, sh - 3 * scale - 1],
                  fill=(*_parse(thumb_color), 255))
        final = img.resize((self.W, self.H), Image.LANCZOS)
        bg_img = Image.new("RGBA", (self.W, self.H), (*_parse(self._bg), 255))
        bg_img.alpha_composite(final)
        buf = _io.BytesIO()
        bg_img.convert("RGB").save(buf, format="PNG")
        return tk.PhotoImage(data=_b64.b64encode(buf.getvalue()).decode("ascii"),
                             master=self._canvas)

    def _disabled_render(self, on):
        import io as _io, base64 as _b64
        scale = 4
        sw, sh = self.W * scale, self.H * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = self.H * scale // 2
        track = "#2a2a2a" if on else "#1a1a1a"
        d.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=r,
                            fill=(*_parse(track), 255))
        thumb_size = (self.H - 6) * scale
        tx = (self.W - self.H + 3) * scale if on else 3 * scale
        d.ellipse([tx, 3 * scale, tx + thumb_size, sh - 3 * scale - 1],
                  fill=(*_parse("#444444"), 255))
        final = img.resize((self.W, self.H), Image.LANCZOS)
        bg_img = Image.new("RGBA", (self.W, self.H), (*_parse(self._bg), 255))
        bg_img.alpha_composite(final)
        buf = _io.BytesIO()
        bg_img.convert("RGB").save(buf, format="PNG")
        return tk.PhotoImage(data=_b64.b64encode(buf.getvalue()).decode("ascii"),
                             master=self._canvas)

    def _draw(self):
        self._canvas.delete("all")
        if self._disabled:
            img = self._img_disabled_on if self._var.get() else self._img_disabled_off
            self._canvas.create_image(self.W // 2, self.H // 2, image=img)
        else:
            self._canvas.create_image(self.W // 2, self.H // 2,
                                      image=self._img_on if self._var.get() else self._img_off)

    def _click(self):
        if self._disabled:
            return
        self._var.set(not self._var.get())
        if self._on_change:
            self._on_change()

    def set_disabled(self, disabled):
        self._disabled = disabled
        if disabled:
            self._canvas.configure(cursor="arrow")
        else:
            self._canvas.configure(cursor="hand2")
        self._draw()

    def pack(self, **kw):
        self._canvas.pack(**kw)

    def grid(self, **kw):
        self._canvas.grid(**kw)

    @property
    def canvas(self):
        return self._canvas


class TabBar:
    """Top tab bar with neon underline — returns content frames."""

    def __init__(self, parent, on_select=None):
        self._parent = parent
        self._tabs = []
        self._btns = []
        self._active = 0
        self._on_select = on_select

        self._bar = tk.Frame(parent, bg=BG, height=38)
        self._bar.pack(fill="x")
        self._bar.pack_propagate(False)

        self._line = tk.Frame(parent, bg=NEON_DIM, height=1)
        self._line.pack(fill="x")

        self._body = tk.Frame(parent, bg=BG)
        self._body.pack(fill="both", expand=True)

    def add(self, label):
        idx = len(self._tabs)
        frame = tk.Frame(self._body, bg=BG)

        col = tk.Frame(self._bar, bg=BG, cursor="hand2")
        col.pack(side="left", fill="y")
        col.bind("<Button-1>", lambda e, i=idx: self.select(i))

        lbl = tk.Label(col, text=label, bg=BG, fg=FG_DIM,
                       font=("Segoe UI", 9, "bold"),
                       padx=16, pady=10)
        lbl.pack()
        lbl.bind("<Button-1>", lambda e, i=idx: self.select(i))

        ul = tk.Frame(col, bg=BG, height=2)
        ul.pack(fill="x")

        self._tabs.append(frame)
        self._btns.append((col, lbl, ul))

        if idx == 0:
            self._show(0)

        return frame

    def select(self, idx):
        self._active = idx
        self._show(idx)
        if self._on_select:
            self._on_select(idx)

    def _show(self, idx):
        for i, (_, lbl, ul) in enumerate(self._btns):
            active = i == idx
            lbl.configure(fg=NEON if active else FG_DIM)
            ul.configure(bg=NEON if active else BG)
        for i, f in enumerate(self._tabs):
            if i == idx:
                f.place(relx=0, rely=0, relwidth=1, relheight=1)
            else:
                f.place_forget()


class IrisScrollbar(tk.Canvas):
    """Canvas-rendered vertical scrollbar for dark Iris surfaces."""

    def __init__(self, parent, command=None, width=10, bg=BG, **kw):
        super().__init__(parent, width=width, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", **kw)
        self._command = command
        self._first = 0.0
        self._last = 1.0
        self._drag_y = None
        self._width = width
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_y", None))

    def set(self, first, last):
        self._first = max(0.0, min(1.0, float(first)))
        self._last = max(self._first, min(1.0, float(last)))
        self._draw()

    def _thumb_bounds(self):
        h = max(1, self.winfo_height())
        span = max(0.08, self._last - self._first)
        th = max(28, int(h * span))
        y1 = int((h - th) * self._first / max(1e-6, 1.0 - span))
        y1 = max(0, min(h - th, y1))
        return y1, y1 + th

    def _draw(self):
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        pad = 2
        self.create_rectangle(w // 2 - 1, 0, w // 2 + 1, h, fill=BG_CARD, outline="")
        if self._last - self._first >= 0.995:
            return
        y1, y2 = self._thumb_bounds()
        self.create_rectangle(pad, y1, w - pad, y2, fill=NEON, outline="")

    def _press(self, event):
        y1, y2 = self._thumb_bounds()
        if y1 <= event.y <= y2:
            self._drag_y = event.y - y1
            return
        direction = -1 if event.y < y1 else 1
        if self._command:
            self._command("scroll", direction * 4, "units")

    def _drag(self, event):
        if self._drag_y is None or not self._command:
            return
        h = max(1, self.winfo_height())
        y1, y2 = self._thumb_bounds()
        th = y2 - y1
        span = max(0.08, self._last - self._first)
        track = max(1, h - th)
        target = max(0.0, min(1.0 - span, (event.y - self._drag_y) / track * (1.0 - span)))
        self._command("moveto", target)


def neon_card(parent, **kw):
    """PIL-rendered rounded card frame with BORDER outline."""
    f = tk.Frame(parent, bg=BG, **kw)
    f.pack(fill="x", pady=(0, 8))
    canvas = tk.Canvas(f, highlightthickness=0, bd=0, bg=BG)
    canvas.pack(fill="both", expand=True)

    def _render(_=None):
        canvas.update_idletasks()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 2 or h < 2:
            canvas.after(10, _render)
            return
        scale = 2
        sw, sh = w * scale, h * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, sw - 1, sh - 1],
                            radius=RADIUS_CARD * scale,
                            fill=(*_parse(BG_CARD), 255),
                            outline=(*_parse(BORDER), 255),
                            width=2 * scale)
        final = img.resize((w, h), Image.LANCZOS)
        bg_img = Image.new("RGBA", (w, h), (*_parse(BG), 255))
        bg_img.alpha_composite(final)
        import io as _io, base64 as _b64
        buf = _io.BytesIO()
        bg_img.convert("RGB").save(buf, format="PNG")
        canvas._tk_img = tk.PhotoImage(
            data=_b64.b64encode(buf.getvalue()).decode("ascii"), master=canvas)
        canvas.delete("all")
        canvas.create_image(w // 2, h // 2, image=canvas._tk_img)

    f.bind("<Configure>", _render)
    return f


def _parse(hex_color):
    c = hex_color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class ColourDropdown(tk.Frame):
    """A swatch preview + dropdown arrow; opens ColourPicker popup on click."""

    def __init__(self, parent, variable, palette, **kw):
        super().__init__(parent, bg=BORDER, **kw)
        self._palette = list(palette)
        self._var     = variable
        self._popup   = None
        self._open    = False
        self._outside_token = None

        self._preview = tk.Canvas(self, width=24, height=24, bg=BG,
                                  highlightthickness=0, bd=0, cursor="hand2")
        self._preview.pack(side="left", padx=(4, 4), pady=4)
        self._swatch_id = self._preview.create_rectangle(
            2, 2, 22, 22, fill=variable.get(), outline="", width=0)

        self._entry = tk.Entry(self, textvariable=variable,
                               bg=BG, fg=FG, insertbackground=NEON,
                               font=FONT_SM, relief="flat", bd=6,
                               highlightthickness=0)
        self._entry.pack(side="left", fill="x", expand=True)

        self._arrow = tk.Label(self, text="\u25BC", bg=BORDER, fg=NEON,
                               font=("Segoe UI", 10), padx=8, pady=3, cursor="hand2")
        self._arrow.pack(side="right")

        for w in (self._preview, self._entry, self._arrow):
            w.bind("<Button-1>", lambda e: self.toggle())
        variable.trace_add("write", lambda *_: self._sync_preview())

    def _sync_preview(self):
        try:
            self._preview.itemconfig(self._swatch_id, fill=self._var.get())
        except Exception:
            pass

    def toggle(self):
        if self._open:
            self._hide()
        else:
            self._show()

    def _show(self):
        self.update_idletasks()
        px = self.winfo_rootx()
        py = self.winfo_rooty() + self.winfo_height()

        self._open = True
        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.configure(bg=BORDER)
        self._popup.attributes("-topmost", True)
        self._popup.transient(self.winfo_toplevel())

        picker = ColourPicker(self._popup, self._var, self._palette,
                              bg=BG, cols=6)
        picker.pack(padx=1, pady=1)
        picker.bind("<Button-1>", lambda e: self._hide(), add=True)

        self._popup.geometry(f"+{px}+{py}")

        root = self.winfo_toplevel()
        self._outside_token = _bind_outside(root, self._hide_outside)

    def _hide(self):
        self._open = False
        if self._outside_token is not None:
            _unbind_outside(self._outside_token)
            self._outside_token = None
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _hide_outside(self, e):
        if not self._popup:
            return
        w = e.widget
        while w:
            if w == self._popup or w == self:
                return
            w = w.master
        self._hide()


class IconDropdown(tk.Frame):
    """Icon preview + entry + dropdown arrow; opens filtered MDI icon grid popup."""

    def __init__(self, parent, variable, **kw):
        super().__init__(parent, bg=BORDER, **kw)
        self._var   = variable
        self._popup = None
        self._open  = False
        self._outside_token = None

        self._preview = tk.Canvas(self, width=24, height=24, bg=BG,
                                  highlightthickness=0, bd=0, cursor="hand2")
        self._preview.pack(side="left", padx=(4, 4), pady=4)
        self._preview_img = None
        self._preview_id = self._preview.create_rectangle(
            2, 2, 22, 22, fill=BG, outline="", width=0)

        self._entry = tk.Entry(self, textvariable=variable,
                               bg=BG, fg=FG, insertbackground=NEON,
                               font=FONT_SM, relief="flat", bd=6,
                               highlightthickness=0)
        self._entry.pack(side="left", fill="x", expand=True)

        self._arrow = tk.Label(self, text="\u25BC", bg=BORDER, fg=NEON,
                               font=("Segoe UI", 10), padx=8, pady=3, cursor="hand2")
        self._arrow.pack(side="right")

        for w in (self._preview, self._entry, self._arrow):
            w.bind("<Button-1>", lambda e: self.toggle())

        self._entry.bind("<KeyRelease>", self._on_key)
        variable.trace_add("write", lambda *_: self._sync_preview())
        self._sync_preview()

    def toggle(self):
        if self._open:
            self._hide()
        else:
            self._show()

    def _sync_preview(self):
        import mdi_icons
        try:
            img = mdi_icons.render_tk(self._var.get(), 18, (224, 224, 224))
        except Exception:
            img = None
        self._preview_img = img
        self._preview.delete("all")
        if img:
            self._preview.create_image(12, 12, image=img)
        else:
            self._preview.create_rectangle(2, 2, 22, 22, fill=BG, outline="", width=0)

    def _on_key(self, e):
        if self._open:
            self._rebuild_grid()
        else:
            self._show()

    def _rebuild_grid(self):
        if not self._open or not self._popup:
            return
        grid = getattr(self._popup, "_grid", None)
        if not grid:
            return
        for w in grid.winfo_children():
            w.destroy()

        import mdi_icons
        from PIL import ImageTk as _ITk

        query = self._var.get().strip().lower()
        names = [n for n in mdi_icons.COMMON_ICONS if not query or query in n]
        cols = 5
        cell_w = 54

        def _pick(name):
            self._var.set(name)
            self._hide()

        self._popup._icon_photos = []
        for i, name in enumerate(names[:40]):
            cell = tk.Frame(grid, bg=BG_CARD, cursor="hand2", width=cell_w, height=44)
            cell.grid(row=i // cols, column=i % cols, padx=1, pady=1)
            cell.grid_propagate(False)
            try:
                r = mdi_icons.render(name, 22, (224, 224, 224))
                img = _ITk.PhotoImage(r) if r else None
            except Exception:
                img = None
            self._popup._icon_photos.append(img)
            lbl = tk.Label(cell, image=img, bg=BG_CARD, cursor="hand2")
            lbl.place(relx=0.5, y=22, anchor="center")
            lbl.bind("<Button-1>", lambda e, n=name: _pick(n))
            cell.bind("<Button-1>", lambda e, n=name: _pick(n))

        self._popup.update_idletasks()

    def _show(self):
        self._open = True
        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.configure(bg=BORDER)
        self._popup.attributes("-topmost", True)
        self._popup.focus_set()

        import mdi_icons
        from PIL import ImageTk as _ITk

        cols = 5
        cell_w = 54
        query = self._var.get().strip().lower()
        names = [n for n in mdi_icons.COMMON_ICONS if not query or query in n]

        def _pick(name):
            self._var.set(name)
            self._hide()

        grid = tk.Frame(self._popup, bg=BG)
        grid.pack(fill="both", expand=True, padx=1, pady=1)

        photos = []
        for i, name in enumerate(names[:40]):
            cell = tk.Frame(grid, bg=BG_CARD, width=cell_w, height=44, cursor="hand2")
            cell.grid(row=i // cols, column=i % cols, padx=1, pady=1)
            cell.grid_propagate(False)
            try:
                r = mdi_icons.render(name, 22, (224, 224, 224))
                img = _ITk.PhotoImage(r) if r else None
            except Exception:
                img = None
            photos.append(img)
            lbl = tk.Label(cell, image=img, bg=BG_CARD, cursor="hand2")
            lbl.place(relx=0.5, y=22, anchor="center")
            lbl.bind("<Button-1>", lambda e, n=name: _pick(n))
            cell.bind("<Button-1>", lambda e, n=name: _pick(n))

        self._popup._icon_photos = photos

        self._popup.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = cols * cell_w + 20
        h = min(40 // cols + 1, 8) * 48 + 4
        h = min(h, self.winfo_screenheight() - y - 40)
        self._popup.geometry(f"{w}x{h}+{x}+{y}")
        self._popup.lift()

        root = self.winfo_toplevel()
        self._outside_token = _bind_outside(root, self._hide_outside)

    def _hide(self):
        self._open = False
        if self._outside_token is not None:
            _unbind_outside(self._outside_token)
            self._outside_token = None
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _hide_outside(self, e):
        if not self._popup:
            return
        fx = self.winfo_rootx()
        fy = self.winfo_rooty()
        fw = self.winfo_width()
        fh = self.winfo_height()
        px = self._popup.winfo_rootx()
        py = self._popup.winfo_rooty()
        pw = self._popup.winfo_width()
        ph = self._popup.winfo_height()
        if not (fx <= e.x_root <= fx + fw and fy <= e.y_root <= fy + fh) and \
           not (px <= e.x_root <= px + pw and py <= e.y_root <= py + ph):
            self._hide()


class ColourPicker(tk.Canvas):
    """Clickable colour swatch grid. Links to a StringVar."""

    _SW  = 28
    _SH  = 28
    _GAP = 4
    _PAD = 4
    _COLS = 6

    def __init__(self, parent, variable, palette, bg=BG_CARD, cols=None, **kw):
        cols = cols or self._COLS
        rows = (len(palette) + cols - 1) // cols
        w = self._PAD * 2 + cols * self._SW + (cols - 1) * self._GAP
        h = self._PAD * 2 + rows * self._SH + (rows - 1) * self._GAP
        super().__init__(parent, width=w, height=h, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._palette = list(palette)
        self._var     = variable
        self._ncols   = cols
        self._sel_tag = None
        self._draw()
        variable.trace_add("write", lambda *_: self._update_sel())
        self.bind("<Button-1>", self._on_click)

    def _rect(self, idx):
        col = idx % self._ncols
        row = idx // self._ncols
        x = self._PAD + col * (self._SW + self._GAP)
        y = self._PAD + row * (self._SH + self._GAP)
        return x, y, x + self._SW, y + self._SH

    def _draw(self):
        self.delete("all")
        for i, color in enumerate(self._palette):
            x1, y1, x2, y2 = self._rect(i)
            self.create_rectangle(x1, y1, x2, y2, fill=color, outline="",
                                  width=0)
        self._sel_tag = self.create_rectangle(0, 0, 0, 0,
                                              outline="white", width=2)
        self._update_sel()

    def _update_sel(self):
        cur = self._var.get()
        self.delete(self._sel_tag)
        if cur in self._palette:
            idx = self._palette.index(cur)
            x1, y1, x2, y2 = self._rect(idx)
            p = 2
            self._sel_tag = self.create_rectangle(
                x1 - p, y1 - p, x2 + p, y2 + p,
                outline="white", width=2)
        else:
            self._sel_tag = self.create_rectangle(
                0, 0, 0, 0, outline="white", width=2)

    def _on_click(self, e):
        for i in range(len(self._palette)):
            x1, y1, x2, y2 = self._rect(i)
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self._var.set(self._palette[i])
                return


class ToolTip:
    """A simple hover-tooltip for any tkinter widget (topmost, no show delay).
    Binds to all descendants so it fires regardless of which child is hovered.
    """

    def __init__(self, widget, text):
        self._widget = widget
        self._text = text
        self._tip_win = None
        self._hide_after = None
        self._root_x = 0
        self._root_y = 0
        self._bind_all(widget)

    def _bind_all(self, w):
        w.bind("<Enter>", self._enter, add="+")
        w.bind("<Leave>", self._leave, add="+")
        w.bind("<ButtonPress>", self._leave, add="+")
        for child in w.winfo_children():
            self._bind_all(child)

    def _enter(self, event=None):
        if self._hide_after:
            self._widget.after_cancel(self._hide_after)
            self._hide_after = None
        self._root_x = event.x_root if event else self._widget.winfo_rootx()
        self._root_y = event.y_root if event else self._widget.winfo_rooty()
        self._show()

    def _leave(self, event=None):
        if self._hide_after:
            self._widget.after_cancel(self._hide_after)
        self._hide_after = self._widget.after(80, self._hide)

    def _show(self):
        if self._tip_win:
            return
        x = self._root_x + 12
        y = self._root_y - 28
        self._tip_win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#111111")
        lbl = tk.Label(tw, text=self._text, justify="left",
                       bg="#111111", fg="#e0e0e0",
                       font=("Segoe UI", 8), padx=8, pady=4)
        lbl.pack()

    def _hide(self):
        self._hide_after = None
        if self._tip_win:
            self._tip_win.destroy()
            self._tip_win = None
