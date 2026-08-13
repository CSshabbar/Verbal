# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# Single-source the bundled version from config.APP_VERSION (MER-33) — this is
# the ONE place to bump for a release; the plist below reads it instead of a
# separate hardcoded string. Invoked with `whisperflow/` as CWD (matches how
# the relative `datas=` paths below already resolve), so '.' is on sys.path;
# insert it explicitly anyway so this doesn't silently break if that ever
# changes. NOTE: whatever this is at build time must match the version you
# register in `app_versions` (platform='mac') when publishing, or the
# auto-updater's comparison (updater.py) breaks — see context/05-conventions.md.
sys.path.insert(0, '.')
from app.config import APP_VERSION

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
        ('app/assets/fonts', 'app/assets/fonts'),
        ('app/assets/img', 'app/assets/img'),
        (fw_dir, 'faster_whisper'),
        (ct2_dir, 'ctranslate2'),
    ],
    hiddenimports=[
        'faster_whisper',
        'ctranslate2',
        'sounddevice',
        'soundfile',
        'numpy',
        'scipy',
        'scipy.signal',
        'rumps',
        'pyperclip',
        'websocket',
        # Device pairing's QR renderer — `app/pairing.py::qr_svg` imports it
        # inside the function, so a frozen build missing it fails only when the
        # user opens "Pair a device".
        'qrcode',
        'google.generativeai',
        'huggingface_hub',
        'objc',
        'WebKit',
        'Foundation',
        'AppKit',
        'Quartz',
        'ScreenCaptureKit',
        'CoreMedia',
        'app.flume_web_dashboard',
        # app.flume_popover is gone (IDI-183 — the menubar is a real NSMenu now).
        # flume_popover_html stays: flume_dashboard_html imports _mark_data_uri
        # from it for the sign-in pane's logo.
        'app.flume_popover_html',
        'app.menubar_menu',
        'app.overlay_html',
        'app.fonts_css',
        'app.recordings',
        'app.dictionary',
        'app.autolearn',
        'app.filetags',
        'app.auth',
        'app.permissions',
        'app.flume_dashboard_html',
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
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
    },
)
