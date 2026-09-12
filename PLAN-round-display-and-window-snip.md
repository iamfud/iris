# PLAN — Window-Snip Mode + Generic Round WebView (Aura / Stats)

Two features, related but independent. Both are documentation-first designs; nothing below is implemented.

---

## Feature 1 — Window-Snip Capture Mode

Hover-and-click to capture a *single target window* (exact borders), matching Snipping Tool's
"Window" mode. Sits alongside the existing `fullscreen` / `zone` capture paths.

### Current capture surface (grounding)
- `app/main_window.py:1263` `start_screenshot(slot, direct, mode)` dispatches `capture_mode`:
  `fullscreen` → `start_fullscreen_screenshot`, `zone` → `start_direct_screenshot`, else toolbar.
- `app/vision.py:788` `RegionSelector` — fullscreen dim overlay (Tk canvas), drag a rect,
  returns `(x,y,w,h)` in **virtual screen** coords. This is the reuse point for the selector UI.
- `app/capture_toolbar.py:520` `_on_screenshot` (zone) and `:483` `capture_fullscreen_direct` —
  both end in `_save_screenshot_and_ocr` → library + sidecar JSON + viewer.
- `app/win_platform.py:1141` has `EnumWindows` callback pattern; `GetWindowRect` used at `:1343`.
  `app/win_resolver.py` maps exe→display name (used for app tagging).

### Design
Add a **third zone mode: snap-to-window** instead of freehand drag.

1. **`WindowSnapSelector` in `app/vision.py`** (new class, mirrors `RegionSelector`):
   - Fullscreen dim + crosshair overlay, same virtual-screen geometry as `RegionSelector`.
   - On mouse-move: `WindowFromPoint` → climb to top-level hwnd (`GetAncestor(GA_ROOT)`) →
     draw a snap rectangle at the window's bounds (neon outline, like the drag rect at
     `vision.py:850`).
   - On click: capture that window's rect; Esc cancels (reuses `_on_escape` pattern).
   - **Windows to ignore**: own PID trees (Iris main, toolbar, notepad, viewer), classes
     `Progman`, `Shell_TrayWnd`, tooltip/popup classes, cloaked windows
     (`DwmGetWindowAttribute(DWMWA_CLOAKED)`), zero-size / offscreen.
   - **Bounds**: use `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` when available
     (correct for rounded/borderless Windows 11), else `GetWindowRect`. Returns **physical**
     px; document explicit conversion to virtual-screen coords (DPI), since `RegionSelector`
     and `vision.capture` operate in virtual coords.
2. **New helper in `app/win_platform.py`**: `top_window_rect_at(x, y)` and a small
   `top_level_window_rects()` enumerator (filtered per the ignore list above).
3. **`capture_toolbar.py`**: add a "Window" button (`mdi_icons` `window-maximize` or similar)
   → `_on_window_screenshot()` mirroring `_on_screenshot` (`select_region` → new
   `WindowSnapSelector`, then `_save_screenshot_and_ocr` + `open_viewer`).
4. **`main_window.py`**: accept `capture_mode: "window"` in `start_screenshot` dispatch, so a
   slot/binding can trigger window-capture directly (same plumbing as `zone`).

### Edge cases to resolve at implementation
- DPI mix (cursor physical vs overlay virtual) — clamp like `region_to_bbox` already does.
- Capturing a window that overlaps the overlay itself → exclude via PID check buys this for free.
- Minimized windows → excluded (no rect worth capturing).
- The overlay must be hidden ~150ms before capture so DWM clears it (existing pattern in
  `capture_fullscreen_direct:491`).

### Acceptance
Window capture lands in the library, opens the annotation viewer, gets per-app tag + sidecar,
pops to phone — identical pipeline to zone. Hotkey/slot `capture_mode` works.

---

## Feature 2 — Generic Round WebView (Aura + Stats as one opt-in addon)

Turn the Kraken LCD page and the Aura page into a **single multi-purpose "round screen"
add-on plugin**, driven by a radius + shape config instead of being Kraken-specific.

### What exists today (grounding)
- `HTML/kraken.html` + `HTML/kraken.js` — dual ring-gauge stats page. 640 buffer drawn into
  `#screen`, clipped to a circle via `#screen.shape-circle { border-radius:50% }`. No clock.
  Polls `/api/panel/live` at 1 Hz; WS theme sync.
- `HTML/theme.html` + `HTML/theme.js` — Aura: lerping full-bleed dual-neon wash + dither +
  dark top/bottom gradient. No polling; WS theme sync only.
- Both served by `ws_bridge` HTTP on 15502; WS on 15501.
- Webview window pattern: `app/desktop_panel.py:344` `_run()` — `webview.create_window(
  frameless=True, easy_drag=False, ...)` + events, run in a separate process.
- Plugin contract: `app/plugin_manager.py` — `plugin.json` (type `service`), thin `plugin.py`
  wrapper, optional `connector.py` with `get_settings()` for declarative settings
  (pattern: `app/plugins/pc_stats/connector.py:47`, controls `toggle`/`slider`).
- Kraken USB auto-detect already exists: `ws_bridge._get_kraken_usb()` returns
  `{found, pid, model, resolution, shape}` — can seed default radius.

### Design — new plugin `round_display`
1. **`app/plugins/round_display/plugin.json`** — type `service`, capabilities
   `configuration: true`, `status: true`. `description`: "Multi-purpose round display —
   Aura colour wash or live hardware stats on a configurable circular webview."
2. **Settings (declarative, via `get_settings()`)** under
   `cfg["plugins"]["round_display"]`:
   | Key | Type | Default | Notes |
   |-----|------|---------|-------|
   | `enabled` | toggle | false | **opt-in — disabled by default** (featherweight rule) |
   | `screen` | select | `aura` | `aura` \| `stats` (UI label: "Aura" / "Stats") |
   | `radius` | slider | 320 | px, range ~80–640, step 4 (= Kraken Z 640 LCD half-width) |
   | `shape` | select | `circle` | `circle` \| `square` (map to existing `.shape-*` CSS) |
   | `always_on_top` | toggle | true | frameless always-on-top display |
3. **`plugin.py` wrapper** (`app/plugins/round_display/plugin.py`) + **`surface.py`**:
   - `start()` → spawn a `multiprocessing.Process` (like `viewer_window.py:122` / desktop
     panel) running a pywebview window;
   - `stop()` → terminate process, save window geometry;
   - config changes (radius/screen/shape) on next check → respawn window with new geometry.
   No `poll()` needed — run when enabled, sleep when disabled.
4. **Webview window** (`round_surface_window`):
   - `frameless=True, transparent=True` if the pywebview/EdgeWebView2 backend supports alpha
     (verify; if unsupported fallback = dark frameless square window). With `transparent`,
     `body{background:transparent}` + `.shape-circle` yields a **true circular edge-to-edge
     window on the desktop** — pure round webview, not marooned in a black square.
   - Window size = `radius*2` (+ padding via DPR). Geometry persisted in plugin config.
   - URL: `http://127.0.0.1:15502/{theme.html|kraken.html}?r=<radius>&shape=<shape>&t=<ts>`.
5. **Page parameterisation** (the "add a radius option somewhere"):
   - **`kraken.html/js`**: read `?r=` → set `#screen` width/height to `r*2` and scale the
     inner SVG buffer to fit; read `?shape=` → apply/remove `.shape-circle`. i.e. the
     existing 640-hardcoded buffer becomes `r`-driven. Defaults stay 320/circle when no param.
   - **`theme.html/js`**: already full-bleed — no change needed for radius; it fills whatever
     window it lives in. Only the `transparent` background bit matters (`theme.html` body bg
     → transparent).
   - **Naming**: keep file names (`kraken.html`) for compatibility, but the *UI copy* becomes
     "Stats" — the page is a graph dashboard, not Kraken-specific.
6. **Auto-detect nicety**: if `screen=stats` and `_get_kraken_usb()` finds a device, offer
   its `resolution`/`shape` as a "Detected: Kraken Z (320px circle)" hint + one-click apply
   (optional settings row). Not required for the LCD-less user.

### Featherweight compliance
- Disabled by default → plugin loads nothing (manager starts nothing).
- While enabled: exactly one webview (browser surface) idle except Stats' existing 1 Hz
  poll / theme WS. This is the *product* (an always-on output display), same stance as the
  Aura/Kraken discussion — legitimate active work, not idle drift.

### Open implementation questions (resolve when building)
- pywebview `transparent=True` on EdgeChromium backend — confirm alpha works on Windows;
  fallback documented above.
- Round webview needs **no-drag** but user may want to move it: add a "move mode" toggle or
  `easy_drag=True` with a drag handle in the page.
- Whether `radius` should be px or independent of DPR (multiply by `window.devicePixelRatio`).

### Acceptance
Enabling the plugin opens a circular (or square) frameless always-on-top window that renders
Aura or Stats; radius and shape changes respawn it correctly; disabling it closes it and frees
the process. Works with no Kraken hardware attached (generic round display).

---

## Sequencing (suggested)
1. **Round webview** first — largest user-visible win, independent, reuses all existing pages.
2. **Window-snap** second — additive mode on existing capture plumbing, low blast radius.
3. Both shipped as opt-in; no changes to default behaviour of `theme.html`/`kraken.html`
   when opened directly.

## Notes
- No `kraken.html` layout changes required for the plan; only radius/shape parametrisation.
- `sw.js` cache version bump needed when `kraken.js` changes (see prior audits: v119).
- AGENTS rule: any new Settings UI must use `HTML/style.css` tokens + existing
  `.settings-*`/modal classes — the plugin settings here are fully declarative via
  `get_settings()`, so no ad-hoc styling is introduced.