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
        # IDI-216 team layer. Imported at FUNCTION level from dictionary.py,
        # shared_dashboard.py and auth.py, so bytecode analysis won't reach it —
        # a frozen build without it would fail only when a user opens Team or
        # dictates while in one (Hard Rule #30).
        'app.organizations',
        'app.autolearn',
        'app.filetags',
        'app.auth',
        'app.permissions',
        'app.flume_dashboard_html',
        # Lazily imported (function-level) by main.py/shared_dashboard.py —
        # declared explicitly per Rule #30 rather than relying on bytecode scan.
        'app.insights',
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
    name='Flume',
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
    name='Flume',
)

# Deliberately unsigned here (no codesign_identity/entitlements_file) — CI
# signs every nested binary + this bundle itself with hardened runtime AFTER
# this build step (see .github/workflows/build-release.yml's "Code-sign the
# app bundle" step + whisperflow/entitlements.plist), then notarizes the DMG.
# PyInstaller's own signing here can't do the leaf-then-bundle ordering
# hardened runtime needs, so don't add codesign_identity to this call.
app = BUNDLE(
    coll,
    name='Flume.app',
    icon='assets/Verbal.icns',
    # Intentionally UNCHANGED: 'com.verbal.app' stays the bundle identifier
    # even though the product is now branded "Flume". macOS keys TCC grants
    # (mic/accessibility/screen-recording) and Sparkle/our own updater's
    # "same app, new version" logic off this identifier, not off the display
    # name. Changing it would make every existing install look like a brand
    # new, never-authorized app: users would lose their already-granted
    # permissions and the in-app updater would appear to be migrating
    # between two unrelated apps. That's a product decision bigger than a
    # rename, so it's deliberately out of scope here — 'CFBundleName'/
    # 'CFBundleDisplayName' below carry the actual user-visible rebrand.
    bundle_identifier='com.verbal.app',
    info_plist={
        'CFBundleName': 'Flume',
        'CFBundleDisplayName': 'Flume',
        'NSMicrophoneUsageDescription': 'Flume needs microphone access for voice dictation.',
        'NSAccessibilityUsageDescription': 'Flume needs accessibility access to inject text into apps.',
        'LSUIElement': False,
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
    },
)
