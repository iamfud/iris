"""Emergency Key Release Script

Instantly broadcasts Key-Up events across all standard keys and modifiers
through both the Interception kernel driver and Windows SendInput.

Usage:
  python emergency_release.py
"""

import sys
import os

from keyboard_service import keyboard_service

def main():
    print("[*] Broadcasting emergency key release across all keys and modifiers...")
    keyboard_service.release_all_keys()
    print("[+] Done! All keys and modifiers have been released.")

if __name__ == "__main__":
    main()
