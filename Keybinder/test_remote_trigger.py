"""Iris Keybinder — Remote Phone Button Test Server

Starts a lightweight HTTP server on your local Wi-Fi network.
Open the displayed URL on your phone or tablet to tap buttons
and send instant hardware keystrokes to your active PC game without Alt-Tabbing!

Usage:
  python test_remote_trigger.py
"""

import sys
import os
import socket
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from keyboard_service import key_engine, resolve_key
from device_scanner import scan_devices

PORT = 5000
log = logging.getLogger("remote_trigger")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_local_ip() -> str:
    """Detect the local Wi-Fi / Ethernet LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not actually connect, just retrieves local interface IP routed to LAN
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Iris Remote Key Trigger</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; -webkit-user-select: none; }
        body {
            background-color: #0b0e14;
            color: #e2e8f0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            padding: 20px 16px;
        }
        h1 { font-size: 20px; font-weight: 700; color: #38bdf8; margin-bottom: 6px; }
        p.sub { font-size: 13px; color: #94a3b8; margin-bottom: 20px; text-align: center; }
        
        .device-select-wrap {
            width: 100%;
            max-width: 400px;
            background: #1e293b;
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #334155;
        }
        .device-select-wrap label { font-size: 12px; font-weight: 600; color: #94a3b8; display: block; margin-bottom: 6px; }
        select {
            width: 100%;
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid #475569;
            padding: 10px;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
            width: 100%;
            max-width: 400px;
        }
        button.btn {
            background: #1e293b;
            color: #f8fafc;
            border: 2px solid #334155;
            border-radius: 16px;
            padding: 24px 12px;
            font-size: 18px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.1s ease;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        button.btn span.sub { font-size: 11px; font-weight: 500; color: #64748b; }
        button.btn:active, button.btn.pressed {
            background: #0284c7;
            border-color: #38bdf8;
            transform: scale(0.96);
            box-shadow: 0 0 16px rgba(56, 189, 248, 0.6);
        }
        .btn.full { grid-column: span 2; padding: 20px; }
        
        #log-bar {
            margin-top: 24px;
            font-size: 12px;
            color: #10b981;
            background: #064e3b;
            padding: 8px 16px;
            border-radius: 20px;
            opacity: 0;
            transition: opacity 0.3s;
        }
    </style>
</head>
<body>
    <h1>Iris Remote Trigger</h1>
    <p class="sub">Tap buttons to send instant hardware keys to your active PC game</p>

    <div class="device-select-wrap">
        <label for="dev-select">TARGET KEYBOARD CHANNEL:</label>
        <select id="dev-select">
            {{DEVICE_OPTIONS}}
        </select>
    </div>

    <div class="grid">
        <button class="btn" onclick="sendKey('1')">KEY 1 <span class="sub">Slot / Hotbar 1</span></button>
        <button class="btn" onclick="sendKey('2')">KEY 2 <span class="sub">Slot / Hotbar 2</span></button>
        <button class="btn" onclick="sendKey('3')">KEY 3 <span class="sub">Slot / Hotbar 3</span></button>
        <button class="btn" onclick="sendKey('4')">KEY 4 <span class="sub">Slot / Hotbar 4</span></button>
        <button class="btn" onclick="sendKey('e')">KEY E <span class="sub">Interact / Action</span></button>
        <button class="btn" onclick="sendKey('f13')">KEY F13 <span class="sub">Macro Key</span></button>
        <button class="btn full" onclick="sendKey('space')">SPACEBAR <span class="sub">Jump / Primary</span></button>
    </div>

    <div id="log-bar">Triggered</div>

    <script>
        function sendKey(key) {
            const dev = document.getElementById('dev-select').value;
            const logEl = document.getElementById('log-bar');
            
            logEl.innerText = `Sent '${key.toUpperCase()}' to Slot ${dev}`;
            logEl.style.opacity = '1';
            setTimeout(() => { logEl.style.opacity = '0'; }, 1200);

            fetch(`/api/tap?key=${encodeURIComponent(key)}&device=${encodeURIComponent(dev)}`, { method: 'POST' })
                .catch(err => console.error(err));
        }
    </script>
</body>
</html>
"""


class RemoteRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            # Build device options
            options = []
            if key_engine.detected_devices:
                for d in key_engine.detected_devices:
                    selected = "selected" if d.slot == key_engine.target_device else ""
                    options.append(f'<option value="{d.slot}" {selected}>Slot {d.slot}: {d.description}</option>')
            else:
                for slot in range(1, 6):
                    selected = "selected" if slot == key_engine.target_device else ""
                    options.append(f'<option value="{slot}" {selected}>Slot {slot}</option>')

            page = HTML_PAGE.replace("{{DEVICE_OPTIONS}}", "\n".join(options))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/tap":
            qs = parse_qs(parsed.query)
            key = qs.get("key", [""])[0]
            dev_str = qs.get("device", [""])[0]
            dev = int(dev_str) if dev_str.isdigit() else key_engine.target_device

            if key:
                log.info("[remote] Received trigger for key='%s' on Slot %d", key, dev)
                success = key_engine.tap_key(key, device=dev)
                self.send_response(200 if success else 500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success, "key": key, "device": dev}).encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress standard HTTP request spam in terminal
        pass


def main():
    local_ip = get_local_ip()
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, RemoteRequestHandler)

    print("=" * 65)
    print("      IRIS REMOTE PHONE TRIGGER TEST SERVER IS RUNNING")
    print("=" * 65)
    print(f"[*] Open this URL on your Phone / Tablet browser:")
    print(f"\n      >>>  http://{local_ip}:{PORT}  <<<\n")
    print(f"[*] Auto-Detected Desktop Keyboard Target: Slot {key_engine.target_device}")
    print("[*] Leave this terminal window running, start your game, and tap buttons on your phone!")
    print("[*] Press Ctrl+C in this terminal to stop the server.")
    print("=" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping remote test server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
