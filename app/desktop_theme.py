"""Iris — Central Desktop Visual Theme & Style Tokens.

Defines the central colour palette, typography hierarchy, dimensions, and static 9-slice
TTK styling for Iris desktop tools.
"""

import ctypes
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

# Window & Surfaces — Deep Obsidian Dark Theme
BG_WINDOW = "#05070A"          # Deepest void background
BG_SURFACE_1 = "#090D12"       # Primary floating obsidian pill surface
BG_SURFACE_2 = "#0F141C"       # Secondary surface
BG_CONTROL = "#131A24"         # Dark pill button background
BG_CONTROL_HOVER = "#1B2432"   # Hover glow surface
BG_CONTROL_ACTIVE = "#232E3F"  # Pressed state

# Borders
BORDER_NORMAL = "#1C2532"      # Refined dark border
BORDER_SUBTLE = "#141B24"
BORDER_FOCUS = "#48B2E9"       # Iris Neon Accent Glow

# Text
TEXT_PRIMARY = "#F0F4F8"
TEXT_SECONDARY = "#9AAEC4"
TEXT_MUTED = "#5A6A7D"
TEXT_DISABLED = "#36414E"

# Unified Iris Neon Tokens
NEON_PRIMARY = "#48B2E9"       # Primary Cyan Neon (--theme-color-1 / --neon)
NEON_SECONDARY = "#B23AF6"     # Secondary Purple Neon (--theme-color-2 / --neon-purple)
NEON_CYAN_BRIGHT = "#00F0FF"   # High-intensity active glow
ACCENT_SUCCESS = "#2ECC71"
ACCENT_DANGER = "#FF3366"

# Backwards compatibility aliases
ACCENT_BLUE = NEON_PRIMARY
ACCENT_PURPLE = NEON_SECONDARY

# Typography
FONT_FAMILY = "Segoe UI"
FONT_WINDOW_TITLE = (FONT_FAMILY, 10, "bold")
FONT_TITLE = (FONT_FAMILY, 11, "bold")
FONT_EDITOR = (FONT_FAMILY, 10)
FONT_SECONDARY = (FONT_FAMILY, 9)
FONT_MUTED = (FONT_FAMILY, 8)

# Dimensions & Layout
PAD_WINDOW = 14
PAD_CARD = 10
RADIUS_WINDOW = 10
RADIUS_CARD = 8
RADIUS_CONTROL = 6

_style_cache = {}


def _hex_to_rgb(hex_str, default=(11, 15, 18)):
    try:
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _make_9slice_image(w, h, radius, fill_color, border_color, parent_bg=BG_WINDOW, border_width=1):
    """Render a static rounded rectangle image pre-composited against parent_bg for sub-pixel anti-aliasing."""
    scale = 4
    sw, sh = w * scale, h * scale
    sr = radius * scale
    sbw = border_width * scale

    # Pre-composite on solid parent_bg (RGB) to eliminate Tkinter GDI alpha-channel white halos
    img = Image.new("RGB", (sw, sh), _hex_to_rgb(parent_bg))
    draw = ImageDraw.Draw(img)
    half = sbw / 2.0
    draw.rounded_rectangle(
        [half, half, sw - 1 - half, sh - 1 - half],
        radius=sr,
        fill=_hex_to_rgb(fill_color),
        outline=_hex_to_rgb(border_color),
        width=int(sbw),
    )
    img_smooth = img.resize((w, h), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img_smooth)


def get_current_theme_colors():
    """Fetch live theme colors from config matching the web portal and TK panel theme engine."""
    theme = {}
    try:
        from config import load_config
        cfg = load_config()
        if isinstance(cfg, dict) and "theme" in cfg:
            theme = cfg.get("theme") or {}
    except Exception:
        pass

    mode = theme.get("mode", "iris") if isinstance(theme, dict) else "iris"
    if mode == "monochrome":
        neon_hex = "#FFFFFF"
        accent_hex = "#888888"
    elif mode == "custom":
        neon_hex = theme.get("neon") or "#48B2E9"
        accent_hex = theme.get("accent") or "#B23AF6"
    else:  # "iris"
        neon_hex = "#48B2E9"
        accent_hex = "#B23AF6"

    neon_rgb = _hex_to_rgb(neon_hex, (72, 178, 233))
    accent_rgb = _hex_to_rgb(accent_hex, (178, 58, 246))

    # Compute perceived luminance for optimal text readability
    lum1 = (0.299 * neon_rgb[0] + 0.587 * neon_rgb[1] + 0.114 * neon_rgb[2]) / 255.0
    lum2 = (0.299 * accent_rgb[0] + 0.587 * accent_rgb[1] + 0.114 * accent_rgb[2]) / 255.0
    neon_text_hex = accent_hex if lum1 < 0.42 else neon_hex
    neon_text_rgb = accent_rgb if lum1 < 0.42 else neon_rgb
    bright_neon_hex = neon_hex if lum1 >= lum2 else accent_hex
    bright_neon_rgb = neon_rgb if lum1 >= lum2 else accent_rgb

    # Deep obsidian background with subtle dynamic neon tint matching webportal
    r1, g1, b1 = neon_rgb
    bg_r = max(0, min(255, int(7 + r1 * 0.03)))
    bg_g = max(0, min(255, int(9 + g1 * 0.03)))
    bg_b = max(0, min(255, int(12 + b1 * 0.03)))
    theme_bg_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"

    ctrl_r = max(0, min(255, int(15 + r1 * 0.05)))
    ctrl_g = max(0, min(255, int(20 + g1 * 0.05)))
    ctrl_b = max(0, min(255, int(28 + b1 * 0.05)))
    theme_ctrl_hex = f"#{ctrl_r:02x}{ctrl_g:02x}{ctrl_b:02x}"

    return {
        "neon_hex": neon_hex,
        "accent_hex": accent_hex,
        "neon_rgb": neon_rgb,
        "accent_rgb": accent_rgb,
        "neon_text_hex": neon_text_hex,
        "neon_text_rgb": neon_text_rgb,
        "bright_neon_hex": bright_neon_hex,
        "bright_neon_rgb": bright_neon_rgb,
        "theme_bg_hex": theme_bg_hex,
        "theme_ctrl_hex": theme_ctrl_hex,
    }


def init_desktop_styles(root=None, force=False):
    """Initialize static 9-slice TTK styles for Iris rounded cards and controls driven by the theme engine."""
    if "initialized" in _style_cache and not force:
        return

    try:
        t_colors = get_current_theme_colors()
        bg_surface = t_colors["theme_bg_hex"]
        bg_ctrl = t_colors["theme_ctrl_hex"]
        neon_primary = t_colors["neon_hex"]
        bright_neon = t_colors["bright_neon_hex"]

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Globally override clam theme's default light grey palettes
        style.configure(".", background=bg_surface, foreground=TEXT_PRIMARY, troughcolor=BG_WINDOW, bordercolor=bg_surface, darkcolor=bg_surface, lightcolor=bg_surface)
        style.configure("TFrame", background=bg_surface)
        style.configure("TLabel", background=bg_surface, foreground=TEXT_PRIMARY)

        # ── 1. Static 9-Slice Card Frame (8px Radius) ───────────────────
        sz_card = 24
        r_card = 8
        b_card = 8

        img_card_norm = _make_9slice_image(sz_card, sz_card, r_card, bg_surface, BORDER_SUBTLE, parent_bg=BG_WINDOW)
        img_card_focus = _make_9slice_image(sz_card, sz_card, r_card, bg_surface, neon_primary, parent_bg=BG_WINDOW)
        _style_cache["card_norm"] = img_card_norm
        _style_cache["card_focus"] = img_card_focus

        try:
            style.element_create("IrisCard.field", "image", img_card_norm, border=b_card, padding=4, sticky="nsew")
        except Exception:
            pass
        style.layout("Iris.Card.TFrame", [("IrisCard.field", {"sticky": "nsew"})])

        try:
            style.element_create("IrisCardFocus.field", "image", img_card_focus, border=b_card, padding=4, sticky="nsew")
        except Exception:
            pass
        style.layout("Iris.CardFocus.TFrame", [("IrisCardFocus.field", {"sticky": "nsew"})])

        # ── 2. Static 9-Slice Buttons (Seamless Dark Obsidian Pill 8px Radius) ─────
        sz_btn = 24
        r_btn = 8
        b_btn = 8

        # Normal button: seamless dark pill matching dynamic theme bg_ctrl
        btn_norm = _make_9slice_image(sz_btn, sz_btn, r_btn, bg_ctrl, bg_ctrl, parent_bg=bg_surface, border_width=1)
        btn_hover = _make_9slice_image(sz_btn, sz_btn, r_btn, BG_CONTROL_HOVER, neon_primary, parent_bg=bg_surface, border_width=1)
        btn_press = _make_9slice_image(sz_btn, sz_btn, r_btn, BG_CONTROL_ACTIVE, neon_primary, parent_bg=bg_surface, border_width=1)
        _style_cache["btn_norm"] = btn_norm
        _style_cache["btn_hover"] = btn_hover
        _style_cache["btn_press"] = btn_press

        try:
            style.element_create(
                "IrisBtn.button", "image", btn_norm,
                ("pressed", btn_press),
                ("active", btn_hover),
                border=b_btn, padding=(12, 6), sticky="nsew"
            )
        except Exception:
            pass
        style.layout("Iris.TButton", [
            ("IrisBtn.button", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
        ])
        style.configure("Iris.TButton", background=bg_surface, foreground=TEXT_PRIMARY, font=("Segoe UI", 9, "bold"), borderwidth=0, relief="flat")
        style.map("Iris.TButton", foreground=[("active", "#FFFFFF"), ("pressed", bright_neon)])

        # ── 2b. Static 9-Slice Compact Square Buttons (for Toolbars & Quick Actions) ──
        style.layout("Iris.Square.TButton", [
            ("IrisBtn.button", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})
        ])
        style.configure("Iris.Square.TButton", background=bg_surface, foreground=TEXT_PRIMARY, borderwidth=0, relief="flat", padding=(6, 6))
        style.map("Iris.Square.TButton", foreground=[("active", "#FFFFFF"), ("pressed", bright_neon)])

        # ── 3. Static 9-Slice Toolbar Floating Pill Frame (12px Radius) ──
        sz_bar = 32
        r_bar = 12
        b_bar = 12
        img_bar = _make_9slice_image(sz_bar, sz_bar, r_bar, bg_surface, "#161E28", parent_bg=BG_WINDOW, border_width=1)
        _style_cache["bar_norm"] = img_bar
        try:
            style.element_create("IrisBar.field", "image", img_bar, border=b_bar, padding=3, sticky="nsew")
        except Exception:
            pass
        style.layout("Iris.Toolbar.TFrame", [("IrisBar.field", {"sticky": "nsew"})])

        # ── 4. Understated Vertical Scrollbar ───────────────────────────
        style.configure(
            "Iris.Vertical.TScrollbar",
            gripcount=0,
            background=BG_CONTROL,
            darkcolor=BG_SURFACE_1,
            lightcolor=BG_SURFACE_1,
            troughcolor=BG_SURFACE_1,
            bordercolor=BG_SURFACE_1,
            arrowcolor=TEXT_MUTED,
        )
        style.map(
            "Iris.Vertical.TScrollbar",
            background=[("active", BG_CONTROL_HOVER), ("pressed", BG_CONTROL_ACTIVE)],
            arrowcolor=[("active", TEXT_PRIMARY)],
        )

        _style_cache["initialized"] = True
    except Exception as ex:
        pass


def apply_dark_title_bar(hwnd):
    """Enable native Windows 10/11 immersive dark title bar with Iris palette."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        target_hwnds = [h for h in (parent, hwnd) if h]
        dwm = ctypes.windll.dwmapi

        for h in target_hwnds:
            # 1. DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win10 build 19041+ / Win11)
            dwm.DwmSetWindowAttribute(
                h, 20,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 2. DWMWA_CAPTION_COLOR = 35 (Win11 titlebar background #0B0F12 -> 0x00120F0B)
            dwm.DwmSetWindowAttribute(
                h, 35,
                ctypes.byref(ctypes.c_int(0x00120F0B)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 3. DWMWA_TEXT_COLOR = 36 (Win11 titlebar text #E6E9ED -> 0x00EDE9E6)
            dwm.DwmSetWindowAttribute(
                h, 36,
                ctypes.byref(ctypes.c_int(0x00EDE9E6)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 4. DWMWA_BORDER_COLOR = 34 (Win11 window border #252C34 -> 0x00342C25)
            dwm.DwmSetWindowAttribute(
                h, 34,
                ctypes.byref(ctypes.c_int(0x00342C25)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 5. DWMWA_WINDOW_CORNER_PREFERENCE = 33 (3 = DWMWCP_ROUND)
            dwm.DwmSetWindowAttribute(
                h, 33,
                ctypes.byref(ctypes.c_int(3)),
                ctypes.sizeof(ctypes.c_int),
            )
    except Exception:
        try:
            # Fallback for earlier Win10 builds (attribute 19)
            dwm.DwmSetWindowAttribute(
                hwnd, 19,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
        except Exception:
            pass


def create_iris_button(
    parent,
    text="",
    image=None,
    compound="left",
    command=None,
    style="Iris.TButton",
    cursor="hand2",
    **kwargs
):
    """Create a styled static rounded TTK button matching the visual tokens with optional MDI icon."""
    init_desktop_styles(parent)
    btn = ttk.Button(
        parent,
        text=text,
        image=image,
        compound=compound if image else "none",
        command=command,
        style=style,
        cursor=cursor,
    )
    if image:
        btn.image = image  # Prevent garbage collection
    return btn
