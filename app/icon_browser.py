"""Standalone icon browser — visually browse all MDI icons and pick favourites."""

import sys
import os
import tkinter as tk
from pathlib import Path

_app_dir = Path(__file__).parent.resolve()
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

import mdi_icons

COLS = 8
ICON_SIZE = 36
CELL_W = 64
CELL_H = 62


class IconBrowser:
    def __init__(self):
        self._names = self._load_names()
        self._selected: set[str] = set()
        self._photos: dict[str, tk.PhotoImage] = {}
        self._cells: dict[int, list[tk.Widget]] = {}
        self._filtered = list(self._names)

        self._root = tk.Tk()
        self._root.title("MDI Icon Browser")
        self._root.geometry("680x620")
        self._root.configure(bg="#111")

        self._build_top()
        self._build_canvas()
        self._build_search()

        self._render_visible()
        self._root.mainloop()

    # ── helpers ────────────────────────────────────────────────────

    def _load_names(self) -> list[str]:
        p = _app_dir.parent / "all_mdi_icons.txt"
        if p.exists():
            return [line.strip() for line in p.read_text("utf-8").splitlines() if line.strip()]
        return []

    @property
    def _total_h(self) -> int:
        rows = (len(self._filtered) + COLS - 1) // COLS
        return max(1, rows * CELL_H + 4)

    @property
    def _row_count(self) -> int:
        return (len(self._filtered) + COLS - 1) // COLS

    # ── UI build ───────────────────────────────────────────────────

    def _build_top(self):
        top = tk.Frame(self._root, bg="#1a1a1a")
        top.pack(fill=tk.X, padx=0, pady=0)

        tk.Label(top, text=f"{len(self._names)} icons",
                 fg="#888", bg="#1a1a1a", font=("Segoe UI", 10),
                 padx=12, pady=8).pack(side=tk.LEFT)

        self._lbl_count = tk.Label(top, text="0 selected",
                                    fg="#888", bg="#1a1a1a",
                                    font=("Segoe UI", 10))
        self._lbl_count.pack(side=tk.LEFT, padx=(4, 0))

        btn_f = tk.Frame(top, bg="#1a1a1a")
        btn_f.pack(side=tk.RIGHT, padx=8)

        for txt, cmd in [("Save & Close", self._save_close),
                         ("Close", self._root.destroy)]:
            tk.Button(btn_f, text=txt, command=cmd,
                      bg="#333", fg="#eee", activebackground="#555",
                      relief=tk.FLAT, padx=10, cursor="hand2",
                      font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)

    def _build_canvas(self):
        body = tk.Frame(self._root, bg="#111")
        body.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(body, bg="#111", highlightthickness=0,
                                 width=COLS * CELL_W + 4)
        sb = tk.Scrollbar(body, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg="#111")
        self._inner_id = self._canvas.create_window(
            (2, 2), window=self._inner, anchor="nw", tags="inner")

        self._canvas.bind("<Configure>", self._on_canvas_conf)
        self._canvas.bind("<MouseWheel>", self._on_scroll)
        self._canvas.bind("<Button-4>", self._on_scroll_linux_up)
        self._canvas.bind("<Button-5>", self._on_scroll_linux_dn)

    def _build_search(self):
        bot = tk.Frame(self._root, bg="#1a1a1a")
        bot.pack(fill=tk.X)

        tk.Label(bot, text="Filter:", fg="#888", bg="#1a1a1a",
                 font=("Segoe UI", 10), padx=8).pack(side=tk.LEFT)

        self._search_var = tk.StringVar()
        self._search_var.trace("w", self._on_search)
        ent = tk.Entry(bot, textvariable=self._search_var,
                       bg="#2a2a2a", fg="#eee", insertbackground="#eee",
                       relief=tk.FLAT, font=("Segoe UI", 10))
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=6)

    # ── scroll / resize ────────────────────────────────────────────

    def _on_canvas_conf(self, e):
        self._canvas.itemconfig(self._inner_id, width=e.width - 4)
        self._rebuild_inner_height()
        self._render_visible()

    def _on_scroll(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self._render_visible()

    def _on_scroll_linux_up(self, e):
        self._canvas.yview_scroll(-3, "units")
        self._render_visible()

    def _on_scroll_linux_dn(self, e):
        self._canvas.yview_scroll(3, "units")
        self._render_visible()

    def _rebuild_inner_height(self):
        self._inner.configure(height=self._total_h)
        self._canvas.configure(scrollregion=(0, 0, COLS * CELL_W + 4, self._total_h))

    # ── search ─────────────────────────────────────────────────────

    def _on_search(self, *_):
        q = self._search_var.get().strip().lower()
        if q:
            self._filtered = [n for n in self._names if q in n]
        else:
            self._filtered = list(self._names)
        self._clear_cells()
        self._rebuild_inner_height()
        self._render_visible()

    # ── cell management ────────────────────────────────────────────

    def _clear_cells(self):
        for items in self._cells.values():
            for w in items:
                w.destroy()
        self._cells.clear()

    def _visible_rows(self) -> tuple[int, int]:
        yv = self._canvas.yview()
        total = self._total_h
        top_px = int(yv[0] * total)
        bot_px = int(yv[1] * total)
        cw = self._canvas.winfo_height() or 600
        first = max(0, (top_px - cw) // CELL_H)
        last = min(self._row_count, (bot_px + cw) // CELL_H + 2)
        return first, last

    def _render_visible(self):
        first, last = self._visible_rows()
        visible = set(range(first, last + 1))

        gone = [r for r in self._cells if r not in visible]
        for r in gone:
            for w in self._cells[r]:
                w.destroy()
            del self._cells[r]

        if not self._filtered:
            return

        for r in visible:
            if r not in self._cells:
                self._create_row(r)

    def _create_row(self, row: int):
        items: list[tk.Widget] = []
        y = row * CELL_H
        for col in range(COLS):
            idx = row * COLS + col
            if idx >= len(self._filtered):
                break
            name = self._filtered[idx]
            x = col * CELL_W

            f = tk.Frame(self._inner, bg="#111", width=CELL_W, height=CELL_H)
            f.place(x=x, y=y, width=CELL_W, height=CELL_H)

            photo = self._get_photo(name)

            lbl = tk.Label(f, image=photo, bg="#111", cursor="hand2")
            lbl.pack(expand=True)

            txt = tk.Label(f, text=name[:18], bg="#111", fg="#888",
                          font=("Consolas", 6), anchor="center")
            txt.pack(side=tk.BOTTOM)

            is_sel = name in self._selected
            bg = "#1a5a2a" if is_sel else "#111"
            f.config(bg=bg)
            lbl.config(bg=bg)
            txt.config(bg=bg)

            def _click(n=name, fr=f, lb=lbl, tx=txt):
                self._toggle(n, fr, lb, tx)

            for w in (f, lbl, txt):
                w.bind("<Button-1>", lambda e, c=_click: c())

            items.append(f)
        self._cells[row] = items

    def _get_photo(self, name: str) -> tk.PhotoImage:
        cached = self._photos.get(name)
        if cached:
            return cached
        from PIL import Image, ImageTk, ImageDraw
        img = mdi_icons.render(name, ICON_SIZE, (200, 200, 200))
        if img is None:
            img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (60, 60, 60, 255))
            ImageDraw.Draw(img).text((2, 2), "?", fill=(120, 120, 120))
        photo = ImageTk.PhotoImage(img)
        self._photos[name] = photo
        return photo

    def _toggle(self, name, frame, lbl, txt):
        if name in self._selected:
            self._selected.remove(name)
            bg = "#111"
        else:
            self._selected.add(name)
            bg = "#1a5a2a"
        frame.config(bg=bg)
        lbl.config(bg=bg)
        txt.config(bg=bg)
        self._lbl_count.config(text=f"{len(self._selected)} selected")

    def _save_close(self):
        if not self._selected:
            self._root.destroy()
            return
        p = _app_dir.parent / "selected_icons.txt"
        p.write_text("\n".join(sorted(self._selected)), encoding="utf-8")
        print(f"Saved {len(self._selected)} icons to {p}")
        self._root.destroy()


if __name__ == "__main__":
    IconBrowser()
