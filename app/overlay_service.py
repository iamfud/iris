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


class _BaseOverlay:
    """Common plumbing for a transient overlay window."""

    def __init__(self, root, duration_s=3.0):
        self._root = root
        self._duration = max(0.0, float(duration_s))
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.95)
        self._win.configure(bg=BG_CARD)
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

    Size is driven by content.  Positioned bottom-right with a
    fade-in / hold / fade-out animation.
    """

    def __init__(self, root, title="", subtitle="", fields=None, accent=None,
                 duration_s=4.0, position="bottom-right", margin=20):
        super().__init__(root, 0)

        accent = accent or NEON
        fields = fields or []
        pad, r = 16, 10

        self._win.attributes("-alpha", 0.0)
        self._win.configure(bg=BG)
        self._win.attributes("-transparentcolor", BG)

        # ---- build content first (packed for real widget measurement) ----
        inner = tk.Frame(self._win, bg=BG_CARD)
        inner.pack(padx=pad, pady=pad)

        tk.Label(inner, text=title, font=("Segoe UI", 18, "bold"),
                 fg=accent, bg=BG_CARD).pack(anchor=tk.W, pady=0)

        if subtitle:
            tk.Label(inner, text=subtitle, font=("Segoe UI", 10),
                     fg=FG, bg=BG_CARD).pack(anchor=tk.W, pady=(2, 8))

        for label, value in fields:
            row = tk.Frame(inner, bg=BG_CARD)
            row.pack(fill=tk.X)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     fg=FG, bg=BG_CARD).pack(side=tk.LEFT)
            tk.Label(row, text=str(value), font=("Segoe UI", 9, "bold"),
                     fg=FG, bg=BG_CARD).pack(side=tk.RIGHT)

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

        # ---- card background (PIL — rounded rect) ----------------------
        fr = tuple(int(BG_CARD[i:i + 2], 16) for i in (1, 3, 5))
        card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, width - 1, height - 1], r, fill=(*fr, 255))

        from PIL import ImageTk
        photo = ImageTk.PhotoImage(card)

        cv = tk.Canvas(self._win, bg=BG, highlightthickness=0,
                       borderwidth=0, bd=0)
        cv.place(x=0, y=0, width=width, height=height)
        cv.create_image(0, 0, anchor="nw", image=photo)
        cv.image = photo
        cv.tk.call("lower", cv._w)

        # ---- animation ------------------------------------------------
        self._fade(0.0, 0.95, 1000,
                   on_done=lambda: self._win.after(
                       int(duration_s * 1000),
                       lambda: self._fade(0.95, 0.0, 1000,
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
        self._win.geometry("340x90")
        sw = self._root.winfo_screenwidth()
        x = sw - 340 - 20
        y = 20 + offset_y
        self._win.geometry(f"340x90+{x}+{y}")

        border_frame = tk.Frame(self._win, bg="#48B2E9", padx=1, pady=1)
        border_frame.pack(fill=tk.BOTH, expand=True)

        card_bg = "#0E1B26"
        frame = tk.Frame(border_frame, bg=card_bg, padx=12, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        if app:
            tk.Label(
                frame, text=app.upper(), font=("Segoe UI", 8, "bold"),
                fg="#48B2E9", bg=card_bg,
            ).pack(anchor=tk.W)

        tk.Label(
            frame, text=title, font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF", bg=card_bg,
        ).pack(anchor=tk.W)

        if body:
            tk.Label(
                frame, text=body, font=("Segoe UI", 9),
                fg="#B0C4DE", bg=card_bg,
            ).pack(anchor=tk.W)

        self._finish(int(self._duration * 1000))


class BannerOverlay(_BaseOverlay):
    """Full-width strip at the top or bottom of the screen."""

    def __init__(self, root, message="", position="top", duration_s=2.5):
        super().__init__(root, duration_s)
        sw = self._root.winfo_screenwidth()
        height = 48
        y = 0 if position == "top" else self._root.winfo_screenheight() - height
        self._win.geometry(f"{sw}x{height}+0+{y}")

        label = tk.Label(
            self._win, text=message, font=("Segoe UI", 14, "bold"),
            fg=FG, bg=BG,
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
