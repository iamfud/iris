"""Iris Keybinder — Single-Key Test & Hardware Scanner Utility

Usage:
  python test_keyboard_input.py --scan          (Scan all 10 slots and list connected hardware)
  python test_keyboard_input.py 1               (Tap key 1 on auto-detected desktop keyboard)
  python test_keyboard_input.py 1 --device 2    (Tap key 1 specifically targeting Device Slot 2)
  python test_keyboard_input.py space           (Tap Space on auto-detected desktop keyboard)
"""

import sys
import os
import time
import argparse
import subprocess

from keyboard_service import key_engine, resolve_key
from device_scanner import scan_devices


def check_driver_service() -> str:
    try:
        res = subprocess.run(["sc.exe", "query", "interception"], capture_output=True, text=True)
        if res.returncode == 0 and "RUNNING" in res.stdout:
            return "RUNNING"
        elif res.returncode == 0:
            return "INSTALLED_NOT_RUNNING"
        else:
            return "NOT_INSTALLED"
    except Exception as e:
        return f"UNKNOWN ({e})"


def run_hardware_scan():
    print("=" * 70)
    print("        INTERCEPTION HARDWARE DEVICE SCANNER (SLOTS 1-10)")
    print("=" * 70)
    
    if not key_engine.is_interception_active():
        print("[!] Interception driver is not active. Cannot query hardware slots.")
        return

    devices = scan_devices(key_engine._interception_dll, key_engine._context)
    if not devices:
        print("[!] No keyboard devices found on Interception bus.")
        return

    print(f"{'SLOT':<6} | {'TYPE / CLASSIFICATION':<24} | {'VENDOR / DESCRIPTION':<28} | {'HARDWARE ID'}")
    print("-" * 70)
    for d in devices:
        is_auto = " [AUTO-TARGET]" if d.slot == key_engine.target_device else ""
        print(f"Slot {d.slot:<2} | {d.device_type + is_auto:<24} | {d.description:<28} | {d.hardware_id}")
    print("=" * 70)
    print(f"[*] Current Auto-Selected Target Slot: Slot {key_engine.target_device}")
    print("=" * 70)


def run_tap_test(key_name: str, device: int = None, use_directinput: bool = False, delay: int = 3):
    mapping = resolve_key(key_name)
    if not mapping:
        print(f"\n[!] Error: '{key_name}' is not in the key lookup table.")
        print("    Supported examples: 0..9, a..z, f1..f24, space, enter, tab, delete, home, end, esc")
        return

    scancode, is_extended = mapping
    target_slot = device if device is not None else key_engine.target_device
    backend_name = "DIRECTINPUT (SendInput)" if use_directinput else f"INTERCEPTION (Targeting Slot {target_slot})"

    print("\n" + "-" * 55)
    print(f"  TARGET KEY        : '{key_name.upper()}'")
    print(f"  HARDWARE SCANCODE : 0x{scancode:02X} ({scancode}) {'[Extended E0]' if is_extended else ''}")
    print(f"  OUTPUT CHANNEL    : {backend_name}")
    print("-" * 55)
    print(f"[!] >>> Please ALT-TAB to your game or Notepad now! <<<")
    for i in range(delay, 0, -1):
        print(f"    Firing in {i} second(s)...")
        time.sleep(1.0)

    print(f"    >>> FIRING '{key_name.upper()}' NOW! <<<")
    success = key_engine.tap_key(key_name, use_directinput=use_directinput, device=target_slot)
    print(f"[+] Result: {'SUCCESS (Key pressed and released cleanly)' if success else 'FAILED'}\n")


def interactive_menu():
    run_hardware_scan()
    while True:
        print("\n--- TEST MENU ---")
        print("  [V] View / Scan Connected Hardware Devices")
        print("  [1] Tap Key '1'")
        print("  [2] Tap Key '2'")
        print("  [3] Tap Key '3'")
        print("  [4] Tap Key '4'")
        print("  [S] Tap Key 'Space'")
        print("  [F] Tap Key 'F13'")
        print("  [Q] Exit")
        print("  (Or enter: '<key> [slot]' e.g. '1 2' to tap key 1 on slot 2)")
        
        choice = input("\nEnter choice or key: ").strip()
        if not choice:
            continue
        
        c_lower = choice.lower()
        if c_lower == "v" or c_lower == "scan":
            run_hardware_scan()
        elif c_lower == "q" or c_lower == "exit":
            print("Exiting.")
            break
        elif c_lower == "s":
            run_tap_test("space")
        elif c_lower == "f":
            run_tap_test("f13")
        else:
            parts = choice.split()
            key = parts[0]
            dev = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            run_tap_test(key, device=dev)


def main():
    parser = argparse.ArgumentParser(description="Iris Single-Key Test & Device Scanner")
    parser.add_argument("key", nargs="?", type=str, help="Key to test (e.g. 1, 2, space, f13)")
    parser.add_argument("--scan", action="store_true", help="Scan all 10 slots and list connected devices")
    parser.add_argument("--device", type=int, help="Target specific device slot (1..10)")
    parser.add_argument("--directinput", action="store_true", help="Force DirectInput SendInput")
    parser.add_argument("--delay", type=int, default=3, help="Countdown delay in seconds")
    args = parser.parse_args()

    if args.scan:
        run_hardware_scan()
        return

    if args.key:
        run_tap_test(args.key, device=args.device, use_directinput=args.directinput, delay=args.delay)
        return

    interactive_menu()


if __name__ == "__main__":
    main()
