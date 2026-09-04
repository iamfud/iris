# Iris 3.0 — Security Audit

Date: 2026-09-02
Scope: `app/*.py`, `HTML/*.js`, `app/plugins/**`
Severity scale: CRITICAL / HIGH / MEDIUM / LOW / INFO

---

## Summary

Iris runs a LAN-facing HTTP + WebSocket server. By default `lan_access=true`, so the
server binds to `0.0.0.0:15502` (HTTP) and `0.0.0.0:15501` (WS) and is reachable from any
host on the local network (`app/ws_bridge.py:279-295`). Unauthenticated LAN peers are
blocked by session-token/password checks, so the effective trust boundary is *"any host
that holds a valid device session or the pairing token"*. Several findings are severe
primarily because arbitrary files/commands become reachable from that boundary.

Strong points observed (positive findings):
- Panel password uses **Argon2id** PHC hashes, verified constant-time; never returned over
  the API and excluded from the QR code (`app/panel_auth.py`, `app/ws_bridge.py:2694-2702`).
- HTTP access token is a 32-byte `secrets.token_urlsafe` value, compared with
  `hmac.compare_digest` (`app/ws_bridge.py:44,402,779`).
- Device records store only SHA-256 hashes of session tokens, not the tokens themselves.
- HTML escaping helpers (`esc`, `_esc`, `linkifyText`, `escapeHtml`) are applied
  consistently across user-controlled values in the panel and settings renderers.
- Path-traversal in library/media/icon file serving is mitigated by `os.path.basename()`.
- PowerShell subprocess calls pass paths via environment variables (`IRIS_ICON_PATH`,
  `IRIS_ICON_OUT`, `IRIS_APPX_LEAF`), avoiding PS string injection.

---

## Findings

### 1. `shell=True` command execution from user/device-controlled data — HIGH
- `app/panel_runtime.py:468-479` (`_open_path`) and `app/main_window.py:1586-1597`
  (`_safe_launch`)
- Both build a command string with executable + raw args and call
  `subprocess.Popen(f'"{exe}" {raw_args}', shell=True)` on platforms without
  `os.startfile`.
- Reached from `POST /api/panel/action` → `execute_slot()` (`app/panel_runtime.py:229-247`,
  `app/ws_bridge.py:2288-2299`), and from stored panel slots (`GROUP`/`SHORTCUT` types) whose
  `shortcut_path`/`shortcut_args` come from the panel config. Automations also dispatch
  slots here (`app/automations.py:291-298`).
- An authorized device session can post an arbitrary slot dict, so on non-Windows builds
  this is direct command injection; on Windows it falls to `os.startfile(exe, arguments=...)`
  (no shell), which still launches arbitrary attacker-picked executables.
- **Fix**: never use `shell=True`. Pass a list: `subprocess.Popen([exe] + shlex.split(raw_args))`.
  On Windows prefer `subprocess.Popen` with a list too; if `os.startfile` is required,
  validate the executable against an allow-list or require it be an absolute pathed real
  executable.

### 2. Arbitrary executable / URL / hotkey launch from LAN-authenticated peers — HIGH
- `app/panel_runtime.py:430-491` (`_open_path`, `_launch_exe`), `app/ws_bridge.py:2262-2287`
  (`_handle_open_url`), `app/ws_bridge.py:2288-2299` (`_handle_panel_action`).
- Any peer that reaches `_authorized()` (a paired phone, or desktop with the tray token)
  can:
  - launch arbitrary local executables via `_open_path` (`POST /api/panel/action`),
  - send arbitrary media keys and keyboard hotkey sequences
    (`app/panel_runtime.py:561-578`, `_media_key` at 613),
  - reset the realtime overlay/screenshot state, etc.
- This is "by design" for a paired mobile control surface, but the blast radius is elevated
  because (a) the server binds `0.0.0.0` by default, and (b) session tokens have a long
  `_DEVICE_TTL` and are only 32-byte HTTP cookies with `SameSite=Lax` (no `Secure`, and
  the transport is plain HTTP, so tokens traverse the LAN unencrypted and are injectable by
  an on-path LAN attacker).
- **Fix**: (a) default `lan_access` to loopback-only, or require explicit opt-in; (b) serve
  over HTTPS/TLS for LAN, or bind to loopback; (c) add `Secure`+`HttpOnly` cookie flags and
  consider short-lived sessions; (d) restrict destructive/launch endpoints to loopback peers
  when possible.

### 3. WebSocket token carried in URL query string — MEDIUM
- `app/ws_bridge.py:244-266` (`_ws_process_request`) accepts `?token=<_HTTP_TOKEN>` in the
  WebSocket handshake URL. `_HTTP_TOKEN` is the same token embedded in the pairing QR URL
  (`app/ws_bridge.py:333`) and embedded in `lan_url` config.
- Tokens in URLs can leak to browser history, proxies, and HTTP `Referer` headers, and the
  QR pairing URL itself exposes the token over the network.
- **Fix**: pass the token via a header or cookie for WS; avoid placing the raw long-lived
  token in a GET URL. Consider per-device one-time tokens instead of the shared HTTP token.

### 4. Plain-HTTP user_name / configuration transfer — MEDIUM
- `app/ws_bridge.py:1239-1242` (`_push_config_to_device`) and the whole HTTP API run over
  `http://` even when binding `0.0.0.0`. A LAN on-path attacker can read/write config and
  inject the `iris_session` cookie.
- **Fix**: TLS, or loopback binding, or at minimum explicit user opt-in warning for LAN mode.

### 5. `os.startfile` on server-chosen paths derived from config — MEDIUM
- `app/ws_bridge.py:1286-1295` (`_handle_plugins_open_folder` → `os.startfile(folder)`),
  `app/panel_runtime.py:462-479`, `app/main_window.py:2305-2307`.
- `_handle_plugins_open_folder` opens a fixed app-controlled folder so low risk, but panel
  actions open user/device-controlled paths. Tightening per Finding 1/2 covers these.

### 6. Arbitrary plugin config / automation write from any authorized peer — MEDIUM
- `app/ws_bridge.py:1251-1264` (`_handle_save_plugin_config`),
  `app/ws_bridge.py:1137-1188` (`_handle_save_config`), `app/ws_bridge.py:627-631`
  (automation save), `app/ws_bridge.py:1923` (`_handle_save_panel`).
- An authorized device can re-write plugin config, panel board (including
  `shortcut_path`/`shortcut_args`), and automation rules — feeding Findings 1/2 and any
  plugin-specific behaviours.
- **Fix**: restrict config/plugin/automation writes to loopback peers (desktop panel), since
  a phone should not rewrite host configuration.

### 7. Automation hotkey / slot execution surface — MEDIUM
- `app/automations.py:276-362` dispatches `hotkey`, `slot`, `openrgb`, `sound`, and
  `notification` actions from stored rules. Combined with Find 6, an attacker who can write
  a rule can trigger arbitrary hotkeys and slots.
- **Fix**: validate/whitelist action types at save time and restrict rule creation to
  loopback/trusted config writers.

### 8. Login / pairing reachable from LAN without rate limiting — LOW
- `app/ws_bridge.py:811-877` (`_handle_login`) and `app/ws_bridge.py:763-809`
  (`_handle_pair`) are reachable from any LAN peer. `_handle_pair` is constant-time token
  safe, and `_handle_login` uses Argon2id (slow). No explicit attempt throttling/account
  lockout is present.
- **Fix**: add per-source-IP rate limiting / small delay on failed password attempts.

### 9. `_host_ok` DNS-rebinding guard only active in loopback mode — LOW
- `app/ws_bridge.py:424-429`. When `lan_access=true` (default) `_is_loopback_mode()` is
  false, so `_host_ok()` is a no-op and the Host header is not validated — DNS-rebinding /
  Host-header policies are not enforced on the LAN path.
- **Fix**: validate the `Host` header in all modes (or bind loopback by default).

### 10. Library sidecar / note writes not restricted to recognized names — LOW
- `app/ws_bridge.py:1531-1559` (`_handle_library_save_sidecar`),
  `app/ws_bridge.py:1561-1608` (note save). Both `os.path.basename()` the filename so path
  traversal is prevented, which is good. Remaining risk is that an authorized peer can write
  arbitrary content to `.json`/`.txt` files inside the notes/screenshots library folders.
- **Fix**: confine writes to the library directories only and validate the filename matches
  the expected `iris_*` pattern.

### 11. `_serve_login` / `_serve_apk` / static serving under loopback-only in some paths — LOW
- `app/ws_bridge.py:1051-1087`. `_serve_apk` serves the installer to any peer (LAN default);
  this is benign but should be noticed: any LAN host can download `Iris.apk`.
- `_serve_media` (`app/ws_bridge.py:725-743`) serves any file in `<root>/media` by basename,
  but note it is reachable at `GET /media/<name>` for any peer when LAN mode is on (auth is
  not required for the `/media/` branch — it is not prefixed with `/api/`). Only files
  physically placed in `media/` are exposed.

---

## Severity roll-up

| # | Issue | File(s) | Severity |
|---|-------|---------|----------|
| 1 | `shell=True` from device-controlled args | `panel_runtime.py:474`, `main_window.py:1592` | HIGH |
| 2 | Arbitrary exe/URL/hotkey launch from authorized LAN peer | `panel_runtime.py:430-491`, `ws_bridge.py:2262-2299` | HIGH |
| 3 | WS token in query string | `ws_bridge.py:244-266`, `333` | MEDIUM |
| 4 | Plain-HTTP config/user_name over LAN | `ws_bridge.py:1239-1242` | MEDIUM |
| 5 | `os.startfile` on config-derived paths | `panel_runtime.py`, `ws_bridge.py:1286` | MEDIUM |
| 6 | Arbitrary plugin/config/automation writes from peers | `ws_bridge.py:1137,1251,627,1923` | MEDIUM |
| 7 | Automation hotkey/slot surface | `automations.py:276-362` | MEDIUM |
| 8 | No rate limiting on login/pair | `ws_bridge.py:763,811` | LOW |
| 9 | Host-header check only in loopback mode | `ws_bridge.py:424-429` | LOW |
| 10 | Library file writes not pattern-restricted | `ws_bridge.py:1531,1561` | LOW |
| 11 | APK/media exposure, static `/media/` unauth | `ws_bridge.py:725,1069` | LOW |

---

## Recommended remediation priorities

1. **Remove `shell=True`** everywhere; pass `[exe] + args` lists (`panel_runtime.py`,
   `main_window.py`). This is the single highest-value change.
2. **Default to loopback binding** (`lan_access=false`) and make LAN mode an explicit,
   warned opt-in; add TLS for any LAN exposure.
3. **Restrict write/launch endpoints** (config, plugin config, automations, panel action)
   to loopback/desktop peers; treat paired phones as read-only or scoped control only.
4. Move the WS auth token out of the URL (header/cookie) and use short-lived per-device
   tokens.
5. Set `Secure`/`HttpOnly` on session cookies, add login/rate limiting, and validate the
   `Host` header in all modes.
