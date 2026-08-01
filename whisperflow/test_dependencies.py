#!/usr/bin/env python3
"""
test_dependencies.py - Test script to verify all dependencies are available
"""

import sys
import platform

def test_import(label, module_name=None):
    module_name = module_name or label
    try:
        __import__(module_name)
        print(f"✓ {label} ({module_name})" if label != module_name else f"✓ {label}")
        return True
    except ImportError as e:
        print(f"✗ {label} ({module_name}) - {e}" if label != module_name else f"✗ {label} - {e}")
        return False
    except Exception as e:
        print(f"? {label} ({module_name}) - {e}" if label != module_name else f"? {label} - {e}")
        return False

def main():
    print("Testing Verbal dependencies...")
    print("=" * 40)
    
    # Core dependencies
    deps = [
        ("faster-whisper", "faster_whisper"),
        ("ctranslate2", "ctranslate2"),
        ("sounddevice", "sounddevice"),
        ("soundfile", "soundfile"),
        ("numpy", "numpy"),
        ("groq", "groq"),
        ("google-generativeai", "google.generativeai"),
        ("pyperclip", "pyperclip"),
        ("pyautogui", "pyautogui"),
        ("Pillow", "PIL"),
        ("websocket-client", "websocket"),
        ("httpx", "httpx"),
        ("pystray", "pystray"),
        # pywebview is the distribution name; its importable package is `webview`.
        ("pywebview", "webview"),
        ("pynput", "pynput"),
    ]
    system = platform.system()
    if system == "Darwin":
        deps.append(("rumps", "rumps"))
    elif system == "Linux":
        # recorder.py imports scipy at module scope on Linux too.
        deps.append(("scipy", "scipy"))
    
    failed = 0
    for label, module_name in deps:
        if not test_import(label, module_name):
            failed += 1
    
    print("=" * 40)
    if failed == 0:
        print("All dependencies OK!")
        return 0
    else:
        print(f"{failed} dependencies failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
