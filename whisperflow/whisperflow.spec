# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Find faster_whisper and ctranslate2 data
import faster_whisper
fw_dir = os.path.dirname(faster_whisper.__file__)
import ctranslate2
ct2_dir = os.path.dirname(ctranslate2.__file__)

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/icon.png', 'assets'),
        ('assets/icon_active.png', 'assets'),
        (fw_dir, 'faster_whisper'),
        (ct2_dir, 'ctranslate2'),
    ],
    hiddenimports=[
        'faster_whisper',
        'ctranslate2',
        'sounddevice',
        'soundfile',
        'numpy',
        'rumps',
        'pyperclip',
        'pyautogui',
        'google.generativeai',
        'huggingface_hub',
        'objc',
        'Foundation',
        'AppKit',
        'Quartz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Verbal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Verbal',
)

app = BUNDLE(
    coll,
    name='Verbal.app',
    icon='assets/Verbal.icns',
    bundle_identifier='com.verbal.app',
    info_plist={
        'NSMicrophoneUsageDescription': 'Verbal needs microphone access for voice dictation.',
        'NSAccessibilityUsageDescription': 'Verbal needs accessibility access to inject text into apps.',
        'LSUIElement': False,
        'CFBundleShortVersionString': '1.3.0',
    },
)
