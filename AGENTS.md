# Rules

- Never write code unless I explicitly ask you to.
- Only answer questions, explain things, or make suggestions — no implementation without a direct order.

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

## Settings UI Architecture
- **Tkinter settings dialog** (`settings_dialog.py`) is **OBSOLETE** — do not modify or extend
- **Active settings UI**: HTML/pywebview panel served via `ws_bridge.py` HTTP bridge
- **Files**: `HTML/index.html` + `HTML/script.js` + `HTML/style.css` → served by `app/panel_window.py` via pywebview
- **Plugin settings**: Currently rendered ad-hoc in `script.js` (`renderPluginSettings`) — being replaced with declarative settings definitions
