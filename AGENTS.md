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
