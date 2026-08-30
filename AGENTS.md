# Rules

- Never write code unless I explicitly ask you to.
- Only answer questions, explain things, or make suggestions — no implementation without a direct order.
- Always consult `HTML/style.css` and use existing design tokens, components, buttons, and layout classes. NEVER invent ad-hoc styling or custom creative styles. All pages must use `.content` / `.settings-content` for standard page scrolling and `.panel-modal-backdrop` / `.panel-modal` for modals.

# Orientation Cheatsheet (READ THIS FIRST — web panel landscape)

The phone/PWA panel is ONE portrait DOM, rendered on the physical screen by rotating
the whole `.pv-screen` with `transform: rotate(-90deg)`. NEVER "fix" portrait and
landscape independently — the two are the same DOM, so every landscape fix must be
DERIVED from the rotation, not tuned by eye.

- `rotate(-90deg)` maps (in CSS coords, y-down): **portrait-right → screen-UP**,
  portrait-top → screen-LEFT, portrait-left → screen-DOWN, portrait-bottom → screen-RIGHT.
- Consequence A — **page stacking**: a horizontal page track (CSS +x = later pages)
  would put page 1 at the bottom and overflow ABOVE. Fixed in `style.css` by mirroring
  the track and un-mirroring each grid:
  `.pv-box .pv-track{ transform:scaleX(-1) }` and `.pv-track .pdev-grid{ transform:scaleX(-1) }`
  (two mirrors about different centres = pure translation, so button ORDER is preserved).
- Consequence B — **button order within a page**: a 4×3 grid (DOM `1234/5678/9101112`)
  rotated -90° reads on screen as `4 8 12 / 3 7 11 / 2 6 10 / 1 5 9`. Fixed in
  `boardPagesHtml` (`HTML/script.js`) for `is-landscape` by placing slot `perm[p]` at
  DOM position `p`, where `perm[p] = (3 - (p % 4)) * 3 + floor(p / 4)`. The DOM grid
  becomes `10 7 4 1 / 11 8 5 2 / 12 9 6 3` → on screen reads `123/456/789/101112`.
  `data-idx` always stays the slot's real board index (clicks/state updates unaffected).
- Gesture axes also swap: screen-X ≈ portrait-Y (pan the `.pv-scroll`), screen-Y ≈
  portrait-X (pan the button track / pages). `.pv-scroll` must allow `pan-x pan-y`
  (touch-action is the intersection along the ancestor chain — a `pan-x`-only ancestor
  vetoes the box's screen-Y paging).

# Session Memory — 2026-08-16

## Dedicated Media Player Button Settings & Live Album Art
- **Button Card Display Options**:
  - Added **`App Icon`** (`use_app_icon`) sub-toggle under **`Show Icon`** in the button edit modal. Gated so it is disabled/dimmed when `Show Icon` is disabled.
  - When enabled, overrides MDI glyphs with the configured media player application icon (or shortcut icon).
  - Added **`Display Album Art`** (`show_album_art`) toggle in the button edit modal.
- **Dynamic Tile Background Rendering**:
  - Live album art dynamically renders inside `.pdev-tile` via `.pdev-album-art-bg` (`background-size: cover; filter: brightness(0.6)`) whenever media is playing.
  - Smooth fallback to the normal theme background plate when stopped or when no art is available.
  - MDI glyphs, app icons, and status/name bars sit on top at `z-index: 2` with subtle drop shadows.
- **Universal Media Artwork Extraction**:
  - `MediaProvider` (`app/providers/media.py`) extracts high-resolution live artwork byte streams from Windows SMTC (`GlobalSystemMediaTransportControlsSessionMediaProperties.thumbnail` via `winrt.windows.storage.streams`) for Spotify, Apple Music, YouTube (Chrome/Edge), VLC, Tidal, foobar2000, etc.
  - Also extracts embedded artwork from iTunes via COM API (`track.Artwork.Item(1)`).
  - Exposes `GET /api/media/art` in `app/ws_bridge.py` with ETag cache validation.

## Theme Engine (Iris / Monochrome / 2-Colour Custom) & Remote Sync
- Linked unified theme tokens on `:root`: `--theme-color-1` (Accent), `--theme-color-2` (Neon), `--neon`, `--neon-purple`, `--theme-gradient-h`, `--theme-gradient-v`, `--scrollbar-thumb`, `--theme-glow`.
- Automatically drives:
  - Top header glowing accent line (`header::after`)
  - Universal webkit scrollbar gradients (`--scrollbar-thumb` from Accent at 0% to Neon at 100%)
  - Gauges (CSS `conic-gradient` circular rings starting at Accent at 0% and sweeping to Neon at 100%)
  - Sliders, range tracks, toggle buttons, and `.neon` active glow highlights
- Config stored in `config.json` under `"theme": { "mode": "iris"|"monochrome"|"custom", "accent": "#hex", "neon": "#hex" }`.
- New **Appearance** section added to Settings page (`app/settings_pages.json` & `settings_renderer.js`) with 3 clickable preset cards, custom native color pickers with hex inputs, and a live preview swatch.
- **Remote WebSocket Theme Sync & PWA Cache Clear**:
  - `Apply Theme` saves configuration and calls `POST /api/portal/reload` (`ws_bridge._handle_portal_reload`).
  - Broadcasts `{ type: "theme", theme: {...} }` and `{ type: "reload", hard: true }` across all connected phones/PWAs/kiosk browsers.
- **Personalization & Settings Organization**:
  - Moved `user_name` ("Your Name") setting from Companion Device into a new **Personalization** card on the main Settings panel (`app/settings_pages.json`).
  - Automatically personalizes welcome greetings on Dashboard, system notifications, and hardware sync.
  - Added **Media Player** card to Settings panel with automatic detection of installed media players (Spotify, VLC, Windows Media Player, foobar2000, MusicBee, AIMP, iTunes, Tidal, Plexamp, etc.), live app icon preview extraction, custom executable path input, and native file browser integration (`media_player_path`).

## Intelligent Masonry Layout for Settings Panel
- Replaced standard rigid CSS grid (`display: grid`) on `.settings-content` with **CSS Column-Masonry** (`columns: 2 380px; column-gap: 24px;`).
- Section cards (`.settings-section`) use `display: inline-flex; width: 100%; break-inside: avoid;` to stack vertically in column flow without dead vertical row gaps.
- Wide / complex sections (Appearance Theme Engine, Network Pairing & QR, Devices list) use `.settings-section-wide` / `.settings-section-full` with `column-span: all;` to span full-width rows cleanly.
- Automatic wide section detection in `HTML/settings_renderer.js` and declarative `"full_width": true` support in `app/settings_pages.json`.



# Session Memory — 2026-08-06

## Button configurator: app-icon auto-pull (Phase 1)
- New endpoint `GET /api/panel/icon?path=<exe>` (`ws_bridge._handle_panel_icon`) → PNG of the exe's icon, cached in `_APP_ICON_CACHE` keyed by normalized abs path (extract once via PowerShell, serve fast to the 1s web-panel poll).
- **Fixed latent bug**: `win_platform._extract_via_ps` always returned `None` — its `.format()` collided with the PowerShell `try { } catch { }` braces (KeyError). Rewritten to pass BOTH input path and output temp path via env vars (`IRIS_ICON_PATH`/`IRIS_ICON_OUT`), no string interpolation. Verified: extracts 32×32 RGBA from cmd/explorer/notepad.
- Edit action modal (`renderActionModal`/`wireActionModal` in `script.js`): when Type = SHORTCUT ("App / Shortcut"), an "App icon" row (`pe-appicon-wrap`) with live `<img id="pe-appicon-preview">` auto-loads from `/api/panel/icon` on Browse or path input (400ms debounce); preview is a blob: URL (CSP allows `img-src blob:`).
- Save stores `app_icon_path = shortcut_path` for SHORTCUT (sanitize_slot keeps it via `_SLOT_KEYS`).
- Web panel tiles (`panelTileHtml`): SHORTCUT/GROUP with `app_icon_path`/`shortcut_path` render `<img class="pdev-iapp">` instead of the MDI glyph; CSP blocks inline `onerror`, so fallback to MDI is wired via `addEventListener("error")` in `wirePanelView`.
- Desktop app already auto-extracts via `main_window.py` (`app_icon_path or shortcut_path` → `_make_tile_photo`), now actually works since `_extract_via_ps` is fixed.

# Session Memory — 2026-08-06

## Web portal: phone boots into live panel; PC keeps dashboard
- `startPolling()`: `if (IS_APP || !IS_MOBILE) renderPage(); else { currentPage="panel"; portalAutoPanel=true; fetchPanel(); }`. Only real phones (`IS_MOBILE`, `max-width:768px` or iOS) land straight on the live panel; the desktop app window and PC browsers open the dashboard "as before".
- This matters because the PC's settings cog (tray "Iris Settings" + the cog tile) opens the web portal — it must land on the dashboard, not the phone panel.
- `portalAutoPanel` flag in `script.js`; `fetchPanel()` → `openPanelView()` when set (live device screen), else `renderPanel()` (editor).
- Unpaired phone still gets pairing message (server-side `_serve_index`); paired phone → live panel.

# Session Memory — 2026-07-01

## Hotkey mechanism
- Uses `keyboard` library (SendInput via scan codes)
- Flow: hide() → sleep(0.1) → SwitchToThisWindow(saved_hwnd) → sleep(0.2) → press() → sleep(0.15) → release()
- Works for standard Windows apps (Notepad, browsers, etc.)
- Does NOT work for DirectInput/Raw Input games (Elite Dangerous) — `SendInput` blocked during gameplay
- Does NOT work for fullscreen exclusive games — Windows minimizes them when overlay appears
- Edge/Chrome block `SendInput` via UIPI regardless of focus state
- Previous approaches that failed: `PostMessage`, `AttachThreadInput`+`SetForegroundWindow`, `_make_noactivate`

## User name feature
- Text field in Settings > Features > Clock Display section
- Sent to device on every keystroke (debounced 300ms via `after_cancel`/`after`)
- Also queued on reconnect: saved in config, requeued after `_queue_defaults()` in `main.py`
- Placeholder "Your Name" shown when empty, stripped before save/send

## Architecture notes
- `_on_focusout` hides overlay when focus lost (gated by `_sending_hotkey` and `_pin_pinned`)
- `show()` saves foreground window, uses `focus_force()`, `lift()`
- Global hotkey: Ctrl+Alt+I (registered in `main.py` listener thread via `RegisterHotKey`)
- Overlay window: `overrideredirect(True)`, no frame

## Known limitations
- DirectInput games reject `SendInput` — only solution is kernel driver (Interception) or game using borderless windowed mode
- No WS_EX_NOACTIVATE attempted successfully — caused issues with `_on_focusout`

# Audit — 2026-07-09

## Bugs (all fixed on 2026-07-09)
- Race condition: `_queue_defaults()` queued `temp_alert: "0"` before `StatsProvider.start()` could override to `"1"`. **Fix:** moved `_queue_defaults()` after `_setup_providers()` and changed to use `queue_on_connect_default()` (only sets key if absent), so provider overrides win.
- Log file path built from `sys.argv[0]` dir (`main.py:31`) — not writable when packaged. **Fix:** uses `%APPDATA%/Iris` when frozen, falls back to `__file__` dir in source.
- `self._media_provider` attribute (`main.py:56`) never used outside `self._providers` list. **Fix:** made it a local variable.
- Duplicate time sync writes on reconnect (`serial_comm.py:276,284`). **Fix:** `_keepalive` records `_last_time_sync` timestamp; `_time_sync_loop` skips if synced within the last interval.
- `sync_alarm_indicator` (`main.py:147-148`) used `days=0` (falsy) to suppress indicator, which was confusing. **Fix:** now shows indicator if any alarm has `enabled=True`, regardless of `days`.

## Security (both fixed on 2026-07-09)
- PowerShell command injection in `win_platform.py:342-373`: `_extract_via_ps` previously interpolated file path into PS command with only `'` escaped. **Fix:** path is now passed via `$env:IRIS_ICON_PATH` environment variable, eliminating string injection.
- `subprocess.Popen(path, shell=True)` in `main_window.py` for user-configured shortcuts. **Fix:** changed to `Popen([path], shell=False)` — paths are executable filenames, not command lines.

## Orphaned / Dead Code (not fixed — informational only)
- `providers/steam.py` — complete stub, never instantiated. `BaseProvider` (`__init__.py`) never inherited.
- All provider `menu_items()` methods — 6 providers define them, none are ever called. Tray menu is hardcoded in `tray.py`.
- `IrisScrollbar` (`widgets.py:703`) — defined but never used.
- `neon_card` (`widgets.py:764`) — defined but never called.
- `icon_browser.py` — standalone, never imported by app.
- Test debris: `test_debug.py`, `test_hotkey.py`, `test_hotkey2.py`, `test_rtss.py`, `app/test.py`, `app/test2.py`, `app/_dump_profile.py`, `app/err.txt`.

# Session Memory — 2026-07-26

## MAX7219 failsafe (implemented this session)
- **Root cause**: No protection against SPI corruption causing all 256 LEDs to light up (~5A draw, melts 3D-printed case)
- **Three-layer firmware failsafe added**:
  1. Pixel-count watchdog: `drawPixel()` increments counter, `clearDisplay()` resets it, `endFrame()` triggers shutdown if >160 lit pixels. Normal screens peak ~80-100px.
  2. Serial heartbeat timeout: 60s with no serial command → display forced off. Prevents runaway after PC app crash/disconnect.
  3. Periodic MAX7219 register re-init: every 30s re-sends SCANLIMIT, DECODE, INTENSITY, TEST, SHUTDOWN registers to correct minor SPI corruption.
- **Restore mechanism**: any serial command from PC clears failsafe, re-inits registers, re-renders
- **New serial message**: `SAFETY:led_overload` — separate from `OVERHEAT:active` (which is PC CPU/GPU temp only)
- **PC handler**: beep + log warning, does NOT send `display_on=0`
- **Files changed**: `core/core.h`, `main.ino`, `core/renderer.h`, `core/serial.h`, `app/main.py`

## Plugin Architecture Proposal (reviewed this session)
- **Core principle**: plugins only gather data and publish events; Iris core decides output routing
- **Architecture**: Plugin → Event Bus → Capability Manager → (Dashboard, Overlay, Hardware, MQTT, etc.)
- **Signals**: strongly typed (String, Float, Boolean, Percentage, etc.) with metadata; advertise compatible capabilities
- **Key design patterns chosen**: Topic-based Pub/Sub, Strategy (managers), Chain of Responsibility (trigger pipeline), Observer (signal state), Bulkhead (plugin crash isolation)

### Critical feedback given:
- **Event Bus needs topic-based routing** with wildcard subscriptions, not broadcast. Also needs structured event logging, backpressure handling, and per-signal rate limiting.
- **"Capabilities" conflate transport, rendering, and action** — should be separated into Renderer (how to display), Transport (where to send), Action (what to do). Use Strategy Pattern.
- **Signal metadata should be minimal** — plugin only provides required fields (id, name, type, category); UI-derived fields (priority, colour, icon) set by user config; update_frequency inferred from arrival rate.
- **Missing: Derived/Computed Signals** — signals that transform other signals (e.g. CPU-GPU temp differential). This is where trigger/automation logic lives.
- **Trigger system should be composable pipeline**: Change Detection → Condition Filter → Rate Limit → Dispatch. Not a flat list of alternatives.
- **Plugin lifecycle undefined** — need discovery (entry points/directory scan), crash isolation (sandboxed execution), hot reload capability, and schema versioning.
- **Need a Signal Registry** separate from Event Bus — holds definitions, current values, supports queries ("show me all Float°C signals").
- **Migration path**: build new system alongside old, wrap existing `serial_sender` usage as HardwareManager, rewrite plugins one-by-one, switch over. Don't refactor in place.

### Proposed folder structure:
```
iris/
├── core/          # bus.py, registry.py, pipeline.py, engine.py
├── signals/       # types.py, derived.py, triggers.py
├── plugins/       # base.py, loader.py, per-plugin dirs with manifest.json
├── managers/      # base.py, hardware/, display/, transport/, notifications/, logging/, ai/
├── config/        # routing.py, schema.py, ui/settings.py
└── app/           # main.py
```

# Session Memory — 2026-07-28

## WiFi radio disabled (all-pixels-on investigation)
- ESP8266 RF modem is ON by default at boot even with zero WiFi code in the sketch — background radio activity can glitch HSPI transactions to the MAX7219 (suspected cause of intermittent all-pixels-on fault)
- Fix in `firmware/d1mini/main/main.ino` setup(): `WiFi.persistent(false)` → `WiFi.mode(WIFI_OFF)` → `WiFi.forceSleepBegin()` + `delay(1)`, before Serial/mx init; requires `#include <ESP8266WiFi.h>`
- The 250ms all-pixels flash at startup is the intentional boot self-test (`TEST=ON` in setup), NOT the fault
- No arduino-cli/PlatformIO on this machine — firmware compiles via Arduino IDE only

## Settings UI Architecture
- **Tkinter settings dialog** (`settings_dialog.py`) is **OBSOLETE** — do not modify or extend
- **Active settings UI**: HTML/pywebview panel served via `ws_bridge.py` HTTP bridge
- **Files**: `HTML/index.html` + `HTML/script.js` + `HTML/style.css` → served by `app/panel_window.py` via pywebview
- **Plugin settings**: Currently rendered ad-hoc in `script.js` (`renderPluginSettings`) — being replaced with declarative settings definitions

# Session Memory — 2026-07-31

## Vision System Plan (NOT IMPLEMENTED — design only)

Vision = generic screen analysis system. NOT game-specific, NOT a "health bar detector". New root Settings page "Vision" where users create one or more Vision Sensors. Each sensor monitors a small screen region and raises an Iris event when a configurable condition is met. Phase 1: colour-based detection only (Colour Percentage / Pixel Match / Average Brightness). No OCR, template matching, or ML.

### Design decisions (confirmed with user)
- **Event consumers (Phase 1)**: every sensor always produces a measured value/state via `poll()`/`snapshot()`; when its "Hardware Display" output toggle is on, a triggered event also sends `serial_sender.send_notification(event_name, event_message)`. No overlay/sound consumers yet.
- **Anchoring**: regions stored as percentages of the display/monitor the region was captured on. Runtime bbox = monitor rect × region%. No window tracking.
- **Pixel math**: pure Pillow `ImageGrab` + sampled pixel grid (≤ ~4k samples/measurement). No numpy.

### Sensor schema (`cfg["plugins"]["vision"]["sensors"]`)
```json
{
  "id": "vs_1", "name": "Health Low", "enabled": true,
  "exe": "EliteDangerous64.exe",
  "mode": "color_percentage",          // | "pixel_match" | "average_brightness"
  "anchor": {"x":0, "y":0, "w":1920, "h":1080},  // display rect at calibration
  "region": {"x_pct":45, "y_pct":70, "w_pct":20, "h_pct":3},
  "color": "#ff0000",
  "pixel": {"x_pct":50, "y_pct":50},              // used by pixel_match
  "tolerance": 40,                     // RGB Euclidean distance, 0-255
  "threshold": 30.0, "direction": "below",        // "above" | "below"
  "poll_rate": 1.0, "cooldown_s": 10.0,
  "event_name": "Health Low", "event_message": "Hull below 30%",
  "output_display": true, "created": 0
}
```
Modes measure: colour % (0–100), pixel match (0/100), avg brightness (0–255). Event fires on the **rising edge** of threshold crossing (false→true) with configurable cooldown.

### New files
- `app/vision.py` — reusable screen engine (no game logic): `virtual_screen_bounds()`/`monitor_rects()`/`monitor_containing()` via `EnumDisplayMonitors`; `RegionSelector` (fullscreen dim Tk overlay, drag rectangle, Esc cancels, auto-confirm on release); `select_region(root, timeout)` marshals to Tk main thread via `root.after()` + `threading.Event` (HTTP thread blocks, mainloop keeps running); `resolve_exe_for_point(x,y)` via `WindowFromPoint`→PID→`psutil`; `capture(bbox)`/`region_to_bbox`/`screenshot_b64`; `measure(draft)` → `{value, active, mode, sampled}`.
- `app/plugins/vision/plugin.json` — `type: service`, capabilities `status`/`outputs`/`live_data`, output id `display` ("Hardware Display"). Auto-discovered by `plugin_manager` — no `main.py` change needed.
- `app/plugins/vision/connector.py` — `VisionSensorManager`: 0.5s tick re-reads sensors from cfg (hot-apply) → per enabled sensor, `is_exe_running(exe)` gates a per-sensor capture thread (near-zero CPU when apps closed); capture loop at `poll_rate` Hz → `measure()` → edge detection + cooldown → optional `send_notification`; caches runtime state for `poll()`/`snapshot()`.
- `app/plugins/vision/plugin.py` — thin `Plugin` wrapper (start/stop/poll/snapshot) delegating to the manager.

### Modified files
- `app/ws_bridge.py` — switch `HTTPServer` → `ThreadingHTTPServer` (blocking capture must not stall the panel's 1s poll). Endpoints: `GET /api/vision/sensors` (config + live state), `POST /api/vision/sensors` (create), `POST /api/vision/sensors/<id>` (update), `POST /api/vision/sensors/<id>/delete`, `POST /api/vision/capture` → `{exe, anchor, region, screenshot_b64}`, `POST /api/vision/test` (draft body → fresh `{value, active}`, stateless, works even if exe not running).
- `app/panel_window.py` — add `hide_panel()`/`show_panel()` to `_JSApi` (panel hides during region capture).
- `HTML/index.html` — sidebar nav item `data-page="vision"`, icon `visibility`, label "Vision".
- `HTML/script.js` — dispatch branch + `renderVision()` (sensor cards: name/exe/status dot/live value/enable/Test/Edit/Delete/Add) + `renderVisionWizard()` (5 steps: 1 Capture Region, 2 Eyedropper on preview canvas, 3 Process auto-detect, 4 Configure, 5 Test live polling `/api/vision/test` ~0.5s).
- `HTML/style.css` — sensor cards, wizard stepper, preview canvas, colour swatch, big live readout (reuse `--neon-*` tokens).

### Runtime behaviour
- Vision is a service plugin → runs whenever enabled; each sensor's capture thread runs only while its exe is alive.
- Config edits hot-apply on the next manager tick (no restart).

### Known limitations (accepted for Phase 1)
- Exclusive-fullscreen games may minimize when the dim overlay appears during calibration (same constraint as hotkey) — calibrate in borderless-windowed. Runtime capture unaffected.
- DRM/protected content captures black.
- Display-relative anchoring: moving the app to a different monitor moves the captured region off target.
