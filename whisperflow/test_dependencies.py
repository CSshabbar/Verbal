#!/usr/bin/env python3
"""
test_dependencies.py - Test script to verify all dependencies are available
"""

import sys
import traceback

def test_import(module_name):
    try:
        __import__(module_name)
        print(f"✓ {module_name}")
        return True
    except ImportError as e:
        print(f"✗ {module_name} - {e}")
        return False
    except Exception as e:
        print(f"? {module_name} - {e}")
        return False

def main():
    print("Testing Verbal dependencies...")
    print("=" * 40)
    
    # Core dependencies
    deps = [
        "faster_whisper",
        "ctranslate2",
        "sounddevice",
        "soundfile",
        "numpy",
        "groq",
        "google.generativeai",
        "pyperclip",
        "pyautogui",
        "PIL",
        "websocket",
        "httpx",
        "pystray",
        "pywebview",
        "pynput",
        "rumps",  # Mac only, might fail on Windows
    ]
    
    failed = 0
    for dep in deps:
        if not test_import(dep):
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