"""Iris — Custom widgets."""

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont

from constants import BG, BG_CARD, NEON, NEON_DIM, NEON_GRN, NEON_RED, GAUGE_WARN, BUTTON_HOVER, FG, FONT_SM, DANGER, DANGER_HOVER

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
    _H       = 24
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

    def place_forget(self):
        self._cv.place_forget()

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

        grad_a = (178, 58, 246)     # #B23AF6
        grad_b = (121, 232, 252)    # #79E8FC

        def _lerp(t):
            t = max(0.0, min(1.0, t))
            col = tuple(int(grad_a[i] + (grad_b[i] - grad_a[i]) * t) for i in range(3))
            return "#%02x%02x%02x" % col

        self._rtrack(px, py, w - px, r, self._track_bg)
        if tx > px:
            span = tx - px
            cols = max(2, int(span))
            for i in range(cols):
                x0 = px + span * i / cols
                x1 = px + span * (i + 1) / cols
                cv.create_line(x0, py, x1, py, width=self._TRACK_H,
                               capstyle="round", fill=_lerp(i / (cols - 1)))
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
        self.unit = unit.replace("\u00b0", "")
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

    def set_unit(self, unit):
        self.unit = unit.replace("\u00b0", "")
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
        return f"{int(round(value))}"

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
        grad_a = (178, 58, 246)     # #B23AF6
        grad_b = (121, 232, 252)    # #79E8FC

        def _lerp(t):
            return tuple(int(grad_a[i] + (grad_b[i] - grad_a[i]) * t) for i in range(3)) + (255,)

        d.arc((x0, y0, x1, y1), start=start, end=start + sweep,
              fill=_rgb(BG_CARD) + (255,), width=thick)

        ratio = 0.0
        if self._value is not None:
            v = max(0.0, min(float(self._value), self.max_value))
            ratio = v / self.max_value
            span = sweep * ratio
            n = max(1, int(round(span / 4)))
            for i in range(n):
                a0 = start + span * i / n
                a1 = start + span * (i + 1) / n
                d.arc((x0, y0, x1, y1), start=a0, end=a1,
                      fill=_lerp(i / n), width=thick)

        val_font = _load_font("Segoe UI", max(8, int(self.size * 0.22 * scale)), bold=True)
        sub_font = _load_font("Segoe UI", max(6, int(self.size * 0.12 * scale)))
        cx = cy = (self.size * scale) // 2

        vb = d.textbbox((0, 0), center_text, font=val_font)
        d.text((cx - (vb[2] - vb[0]) // 2, cy - 5 * scale - (vb[3] - vb[1]) // 2),
               center_text, fill=(255, 255, 255, 255), font=val_font)

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
                 font=None, padx=14, pady=7, icon=None, **kw):
        import tkinter.font as _tkf
        self._command = command
        self._radius  = radius
        self._text    = text
        self._icon    = icon      # MDI char or None
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
        elif style == "danger":
            self._bg    = bg    or DANGER
            self._fg    = fg    or "#ffffff"
            self._hover = hover or DANGER_HOVER
        else:
            self._bg    = bg    or BUTTON_HOVER
            self._fg    = fg    or FG
            self._hover = hover or "#454545"

        try:
            self._pbg = parent.cget("bg")
        except Exception:
            self._pbg = BG

        if self._icon:
            w = _tkf.Font(font=self._font).metrics("linespace") + padx * 2
            h = w
        else:
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
            if self._icon:
                import mdi_icons
                _rgb = self._parse(self._fg)
                icon_photo = mdi_icons.render_tk(self._icon, int(h * 0.5), _rgb)
                if icon_photo:
                    self._icon_photo = icon_photo
                    self.create_image(w // 2, h // 2, image=icon_photo)
            else:
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
        if self._icon:
            import mdi_icons
            _rgb = self._parse(self._fg)
            icon_photo = mdi_icons.render_tk(self._icon, int(h * 0.5), _rgb)
            if icon_photo:
                self._icon_photo = icon_photo
                self.create_image(w // 2, h // 2, image=icon_photo)
        else:
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
