"""Iris — Dark ttk theme for settings dialog."""

import tkinter as tk
from tkinter import ttk

from constants import BG, BG_CARD, FG, FG_DIM, NEON, NEON_DIM, BUTTON_HOVER


def apply_dark_theme(root=None):
    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".",              background=BG, foreground=FG, fieldbackground=BG,
                                    selectbackground=NEON, selectforeground=BG,
                                    troughcolor=BG_CARD, arrowcolor=NEON)

    s.configure("TFrame",         background=BG)
    s.configure("TLabel",         background=BG, foreground=FG)
    s.configure("Card.TLabel",    background=BG_CARD, foreground=FG)
    s.configure("Dim.TLabel",     background=BG, foreground=FG_DIM)

    s.configure("TCheckbutton",   background=BG, foreground=FG)
    s.map("TCheckbutton",        background=[("active", BG)], foreground=[("active", FG)])

    s.configure("TRadiobutton",   background=BG, foreground=FG)
    s.map("TRadiobutton",        background=[("active", BG)], foreground=[("active", FG)])

    s.configure("TEntry",         fieldbackground=BG_CARD, foreground=FG,
                                    insertcolor=FG, bordercolor=NEON_DIM)
    s.map("TEntry",              bordercolor=[("focus", NEON)])

    s.configure("TSpinbox",       fieldbackground=BG_CARD, foreground=FG,
                                    insertcolor=FG, bordercolor=NEON_DIM,
                                    arrowcolor=NEON, lightcolor=BG_CARD, darkcolor=BG_CARD)
    s.map("TSpinbox",            bordercolor=[("focus", NEON)])

    s.configure("TCombobox",      fieldbackground=BG_CARD, foreground=FG,
                                    arrowcolor=NEON, bordercolor=NEON_DIM)
    s.map("TCombobox",           bordercolor=[("focus", NEON)],
                                    fieldbackground=[("readonly", BG_CARD)])

    s.configure("TButton",        background=BUTTON_HOVER, foreground=FG,
                                    bordercolor=NEON_DIM, focuscolor=NEON)
    s.map("TButton",             background=[("active", NEON), ("pressed", NEON)],
                                    foreground=[("active", BG)])

    s.configure("TSeparator",     background=NEON_DIM)

    s.configure("Vertical.TScrollbar",   background=BG_CARD, troughcolor=BG,
                                          arrowcolor=NEON, bordercolor=BG)
    s.configure("Horizontal.TScrollbar", background=BG_CARD, troughcolor=BG,
                                          arrowcolor=NEON, bordercolor=BG)

    if root:
        root.option_add("*TCombobox*Listbox.background", BG)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", NEON)
        root.option_add("*TCombobox*Listbox.selectForeground", BG)
