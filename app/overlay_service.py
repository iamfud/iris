"""Iris — transient overlay service.

Provides three overlay types that can be requested from plugins or internal
functions.  All public methods are safe to call from background threads; they
marshal work onto the Tkinter main loop via ``root.after(0, ...)``.

Cosmetics are intentionally minimal; this module is the architecture/ plumbing.
"""

import logging
import tkinter as tk

from PIL import Image, ImageDraw

from constants import BG, BG_CARD, FG, NEON

log = logging.getLogger("iris.overlays")


def _draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a filled rounded rectangle on a tkinter Canvas.

    Composes four corner arcs with edge-filling rectangles so the result
    appears as a single rounded-card shape.
    """
    d = 2 * r
    canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90,
                      style="pieslice", **kwargs)
    canvas.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90,
                      style="pieslice", **kwargs)
    canvas.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90,
                      style="pieslice", **kwargs)
    canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90,
                      style="pieslice", **kwargs)
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kwargs)
    canvas.create_rectangle(x1, y1 + r, x1 + r, y2 - r, **kwargs)
    canvas.create_rectangle(x2 - r, y1 + r, x2, y2 - r, **kwargs)


def _get_overlay_theme():
    """Fetch live theme tokens matching the active game/system theme and Tk panel."""
    neon = "#48B2E9"
    accent = "#B23AF6"
    bg = "#090D12"  # Deep obsidian surface matching Tk panel window

    try:
        import plugin_manager
        cfg = getattr(plugin_manager, "_cfg", None) or {}
        theme = cfg.get("theme") or {}
        if theme.get("neon"):
            neon = theme["neon"]
        if theme.get("accent"):
            accent = theme["accent"]
    except Exception:
        pass

    if neon == "#48B2E9":
        try:
            from desktop_theme import get_current_theme_colors
            tc = get_current_theme_colors()
            neon = tc.get("bright_neon_hex") or tc.get("neon_hex") or neon
            accent = tc.get("accent_hex") or accent
            bg = tc.get("theme_bg_hex") or bg
        except Exception:
            pass

    # Ensure background matches the Tk panel's obsidian palette with subtle ambient tint
    try:
        r = int(neon[1:3], 16)
        g = int(neon[3:5], 16)
        b = int(neon[5:7], 16)
        bg_r = max(5, min(22, int(8 + r * 0.02)))
        bg_g = max(7, min(22, int(10 + g * 0.02)))
        bg_b = max(10, min(26, int(14 + b * 0.02)))
        bg = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
    except Exception:
        bg = "#090D12"

    return {
        "neon": neon,
        "accent": accent,
        "bg": bg,
        "fg_sub": "#C8D6E5",
        "fg_dim": "#7A8A9E",
    }


class _BaseOverlay:
    """Common plumbing for a transient overlay window."""

    def __init__(self, root, duration_s=3.0):
        self._root = root
        self._duration = max(0.0, float(duration_s))
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.88)
        t = _get_overlay_theme()
        self._win.configure(bg=t["bg"])
        self._win.update_idletasks()

    def _finish(self, after_ms=0):
        """Schedule destruction of this overlay."""
        self._win.after(after_ms, self._destroy)

    def _destroy(self):
        try:
            self._win.destroy()
        except tk.TclError:
            pass

    def _center_on_screen(self, width, height):
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self._win.geometry(f"{width}x{height}+{x}+{y}")


class HeroOverlay(_BaseOverlay):
    """Rounded card for major events (e.g. entering a system).

    Size is driven by content. Positioned bottom-right with a
    fade-in / hold / fade-out animation.
    """

    def __init__(self, root, title="", subtitle="", fields=None, accent=None,
                 duration_s=4.0, position="bottom-right", margin=20):
        super().__init__(root, 0)

        t = _get_overlay_theme()
        prominent_neon = accent or t["neon"]
        card_bg = t["bg"]
        fg_sub = t["fg_sub"]

        fields = fields or []
        pad, r = 18, 12

        # Use an off-black key for canvas transparency outside the rounded card
        trans_key = "#030405"
        self._win.attributes("-alpha", 0.0)
        self._win.configure(bg=trans_key)
        self._win.attributes("-transparentcolor", trans_key)

        # ---- build content first (packed for real widget measurement) ----
        inner = tk.Frame(self._win, bg=card_bg)
        inner.pack(padx=pad, pady=pad)

        tk.Label(inner, text=title, font=("Segoe UI", 18, "bold"),
                 fg=prominent_neon, bg=card_bg).pack(anchor=tk.W, pady=0)

        if subtitle:
            tk.Label(inner, text=subtitle, font=("Segoe UI", 10),
                     fg=fg_sub, bg=card_bg).pack(anchor=tk.W, pady=(2, 8))

        for label, value in fields:
            row = tk.Frame(inner, bg=card_bg)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     fg=fg_sub, bg=card_bg).pack(side=tk.LEFT)
            tk.Label(row, text=str(value), font=("Segoe UI", 9, "bold"),
                     fg=prominent_neon, bg=card_bg).pack(side=tk.RIGHT, padx=(16, 0))

        self._win.update_idletasks()
        content_w = inner.winfo_reqwidth()
        content_h = inner.winfo_reqheight()

        # ---- size & position -------------------------------------------
        width = content_w + 2 * pad
        height = content_h + 2 * pad

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        if position == "bottom-right":
            x = sw - width - margin
            y = sh - height - margin
        else:
            x = (sw - width) // 2
            y = (sh - height) // 2

        self._win.geometry(f"{width}x{height}+{x}+{y}")

        # ---- card background (PIL — rounded rect with subtle neon outline) ----
        fr = tuple(int(card_bg[i:i + 2], 16) for i in (1, 3, 5))
        nr = tuple(int(prominent_neon[i:i + 2], 16) for i in (1, 3, 5)) if prominent_neon.startswith("#") and len(prominent_neon) >= 7 else (72, 178, 233)
        card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, width - 1, height - 1], r, fill=(*fr, 255), outline=(*nr, 160), width=1)

        from PIL import ImageTk
        photo = ImageTk.PhotoImage(card)

        cv = tk.Canvas(self._win, bg=trans_key, highlightthickness=0,
                       borderwidth=0, bd=0)
        cv.place(x=0, y=0, width=width, height=height)
        cv.create_image(0, 0, anchor="nw", image=photo)
        cv.image = photo
        cv.tk.call("lower", cv._w)

        # ---- animation ------------------------------------------------
        self._fade(0.0, 0.88, 500,
                   on_done=lambda: self._win.after(
                       int(duration_s * 1000),
                       lambda: self._fade(0.88, 0.0, 500,
                                          on_done=self._destroy)))

    def _fade(self, from_alpha, to_alpha, duration_ms, on_done=None):
        """Animate ``-alpha`` from *from_alpha* to *to_alpha* over
        *duration_ms* milliseconds, then call *on_done*."""
        steps = max(1, duration_ms // 32)
        delta = (to_alpha - from_alpha) / steps
        cur = [0]

        def _step():
            cur[0] += 1
            if cur[0] >= steps:
                self._win.attributes("-alpha", to_alpha)
                if on_done:
                    on_done()
            else:
                alpha = from_alpha + delta * cur[0]
                self._win.attributes("-alpha", alpha)
                self._win.after(32, _step)

        _step()


class ToastOverlay(_BaseOverlay):
    """Small top-right notification card."""

    def __init__(self, root, title="", body="", app="", duration_s=3.5, offset_y=0):
        super().__init__(root, duration_s)
        t = _get_overlay_theme()
        prominent_neon = t["neon"]
        accent_color = t["accent"]
        card_bg = t["bg"]
        fg_sub = t["fg_sub"]

        self._win.attributes("-alpha", 0.88)
        self._win.geometry("340x92")
        sw = self._root.winfo_screenwidth()
        x = sw - 340 - 20
        y = 20 + offset_y
        self._win.geometry(f"340x92+{x}+{y}")

        border_frame = tk.Frame(self._win, bg=prominent_neon, padx=1, pady=1)
        border_frame.pack(fill=tk.BOTH, expand=True)

        frame = tk.Frame(border_frame, bg=card_bg, padx=14, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        if app:
            tk.Label(
                frame, text=app.upper(), font=("Segoe UI", 8, "bold"),
                fg=accent_color, bg=card_bg,
            ).pack(anchor=tk.W)

        tk.Label(
            frame, text=title, font=("Segoe UI", 11, "bold"),
            fg=prominent_neon, bg=card_bg,
        ).pack(anchor=tk.W)

        if body:
            tk.Label(
                frame, text=body, font=("Segoe UI", 9),
                fg=fg_sub, bg=card_bg,
            ).pack(anchor=tk.W)

        self._finish(int(self._duration * 1000))


class BannerOverlay(_BaseOverlay):
    """Full-width strip at the top or bottom of the screen."""

    def __init__(self, root, message="", position="top", duration_s=2.5):
        super().__init__(root, duration_s)
        t = _get_overlay_theme()
        prominent_neon = t["neon"]
        card_bg = t["bg"]

        self._win.attributes("-alpha", 0.88)
        sw = self._root.winfo_screenwidth()
        height = 48
        y = 0 if position == "top" else self._root.winfo_screenheight() - height
        self._win.geometry(f"{sw}x{height}+0+{y}")

        border_frame = tk.Frame(self._win, bg=card_bg)
        border_frame.pack(fill=tk.BOTH, expand=True)

        border_line = tk.Frame(border_frame, bg=prominent_neon, height=2)
        if position == "top":
            border_line.pack(side=tk.BOTTOM, fill=tk.X)
        else:
            border_line.pack(side=tk.TOP, fill=tk.X)

        label = tk.Label(
            border_frame, text=message, font=("Segoe UI", 14, "bold"),
            fg=prominent_neon, bg=card_bg,
        )
        label.pack(fill=tk.BOTH, expand=True)

        self._finish(int(self._duration * 1000))


class OverlayService:
    """Entry point for all transient overlays.  Created by ``IrisApp``."""

    def __init__(self, root):
        self._root = root
        self._toasts = []
        self._toast_height = 110  # card + gap

    def hero(self, title="", subtitle="", fields=None, accent=None, duration=4.0):
        """Show a large centered hero card.

        ``fields`` is an iterable of ``(label, value)`` pairs.
        """
        self._root.after(0, self._show_hero, title, subtitle, fields, accent, duration)

    def toast(self, title="", body="", app="", duration=3.5):
        """Show a small top-right toast."""
        self._root.after(0, self._show_toast, title, body, app, duration)

    def banner(self, message="", position="top", duration=2.5):
        """Show a full-width banner strip at the top or bottom."""
        self._root.after(0, self._show_banner, message, position, duration)

    def _show_hero(self, title, subtitle, fields, accent, duration):
        try:
            HeroOverlay(self._root, title, subtitle, fields, accent, duration)
        except Exception:
            log.exception("hero overlay failed")

    def _show_toast(self, title, body, app, duration):
        try:
            offset_y = len(self._toasts) * self._toast_height
            ov = ToastOverlay(self._root, title, body, app, duration, offset_y)
            self._toasts.append(ov)
            # Remove from tracking when the window is destroyed.
            def _cleanup(w=ov._win):
                try:
                    self._toasts.remove(ov)
                except ValueError:
                    pass
            w = ov._win
            w.after(int(duration * 1000) + 100, _cleanup)
        except Exception:
            log.exception("toast overlay failed")

    def _show_banner(self, message, position, duration):
        try:
            BannerOverlay(self._root, message, position, duration)
        except Exception:
            log.exception("banner overlay failed")
