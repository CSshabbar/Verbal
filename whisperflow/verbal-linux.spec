# verbal-linux.spec — PyInstaller spec for Linux build

import os

from PyInstaller.utils.hooks import collect_data_files

# Import-only sanity check: fail the build early and loudly if a runtime dep is missing
# from the environment rather than producing a binary that dies on first launch.
# NOTE: the module is `webview`; `pywebview` is only the DISTRIBUTION name and importing
# it raises ModuleNotFoundError.
import faster_whisper
import ctranslate2
import sounddevice
import soundfile
import numpy
import groq
import google.generativeai
import pyperclip
import pyautogui
import PIL
import websocket
import httpx
import pystray
import webview
import scipy

# gi (PyGObject) is REQUIRED on Linux, not optional: without it pystray falls back to the
# _xorg backend (Icon.HAS_MENU is False, and the icon will not dock on GNOME/Wayland) and
# pywebview finds no GUI toolkit at all. It only ever installs system-wide, so the build
# interpreter must be able to see system site-packages.
try:
    import gi
except ImportError as e:
    raise SystemExit(
        "verbal-linux.spec: PyGObject (gi) is not importable.\n"
        "  sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1 gir1.2-webkit2-4.1\n"
        "and build from a venv created with --system-site-packages.\n"
        f"  ({e})"
    )

# Real data payloads only.
#
# Do NOT add `(os.path.dirname(<module>.__file__), '<module>')` entries. For a single-FILE
# module such as sounddevice/soundfile that resolves to site-packages itself and copies the
# entire tree (~700MB, twice) into the archive; for packages it duplicates .so files at the
# destinations PyInstaller's own binary analysis targets, bypassing RPATH rewriting and
# missing the sibling *.libs dirs. PyInstaller collects all of these correctly on its own.
datas = [
    ('assets/icon.png', 'assets'),
    ('assets/icon_active.png', 'assets'),
    ('assets/sounds/start.wav', 'assets/sounds'),
    ('assets/sounds/stop.wav', 'assets/sounds'),
    ('assets/sounds/done.wav', 'assets/sounds'),
    # Flume design system — theme.py / fonts_css.py / flume_popover_html.py resolve these
    # under sys._MEIPASS at runtime, so the dashboard renders unstyled without them.
    ('app/assets/fonts', 'app/assets/fonts'),
    ('app/assets/img', 'app/assets/img'),
]
# Pulls faster_whisper's bundled assets (silero_vad_v6.onnx) without duplicating its .so files.
datas += collect_data_files('faster_whisper')

a = Analysis(
    ['app/linux_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'app.recorder',
        'app.transcriber',
        'app.ai_cleanup',
        'app.config',
        'app.sync',
        'app.updater',
        'app.linux_injector',
        'app.linux_overlay',
        'app.shared_dashboard',
        'app.linux_main',
        # shared_dashboard imports these lazily INSIDE functions, so modulegraph cannot
        # see them. Deliberately excluded: app.theme / app.permissions / app.autolearn
        # (AppKit/PyObjC at module scope — macOS only).
        'app.dictionary',
        'app.recordings',
        'app.pairing',
        'app.auth',
        'app.fonts_css',
        'app.flume_dashboard_html',
        'app.win_dashboard',
        'faster_whisper',
        'faster_whisper.utils',
        'faster_whisper.tokenizer',
        'faster_whisper.audio',
        'ctranslate2',
        'google.generativeai',
        'groq',
        'webview',
        'webview.platforms.gtk',
        # GTK/AppIndicator stack. The gi hooks collect the matching typelibs.
        'gi',
        'gi.repository.Gtk',
        'gi.repository.AyatanaAppIndicator3',
        'gi.repository.WebKit2',
        'pystray',
        'pystray._appindicator',
        'pystray._gtk',
        'pystray._xorg',
        'pystray._dummy',
        'pynput.keyboard._xorg',
        'pynput.mouse._xorg',
        # uinput is the only Wayland-capable pynput backend (needs /dev/uinput perms).
        'pynput.keyboard._uinput',
        'pynput.mouse._uinput',
        # linux_overlay is pure tkinter; needs system python3-tk on the BUILD host.
        'tkinter',
        'dotenv',
        'av',
        'av.codec',
        'av.container',
        'av.audio',
        'av.video',
        'av.filter',
        'av.stream',
        'av.format',
        'av.packet',
        'av.frame',
        'av.dictionary',
        'av.logging',
        'av.plane',
        'av.subtitle',
        'av.error',
        'sounddevice',
        'soundfile',
        'numpy',
        'pyperclip',
        'pyautogui',
        'PIL',
        'websocket',
        'httpx',
        'scipy',
        'scipy.signal',
        'scipy.fftpack',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Verbal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is frequently absent, and compressing a onefile Linux binary is a known source of
    # loader problems for no meaningful gain here.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False has no effect on Linux (there is no windowed bootloader); logs go to
    # the launching terminal and to ~/.verbal/logs/app.log either way.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # No icon= : PyInstaller ignores it on Linux ("supported only on Windows and macOS").
    # The app icon comes from the .desktop file instead — see packaging/verbal.desktop.
)
