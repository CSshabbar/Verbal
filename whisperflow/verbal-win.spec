# verbal-win.spec — PyInstaller spec for Windows build

import sys
import os

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
# The PyPI package is named "pywebview" but its importable top-level module
# is "webview" — confirmed by inspecting the actual wheel contents (it ships
# a `webview/` dir, not `pywebview/`). `import pywebview` here was always
# wrong and made every Windows build fail at spec-parse time with
# ModuleNotFoundError; the real app code (win_main.py) already correctly
# uses `import webview` and was never affected by this (2026-08-22).
import webview
import scipy

fw_dir = os.path.dirname(faster_whisper.__file__)
ct2_dir = os.path.dirname(ctranslate2.__file__)

# Convert PNG icon to ICO for Windows
icon_src = 'assets/icon.png'
icon_ico = 'assets/icon.ico'
if os.path.exists(icon_src) and not os.path.exists(icon_ico):
    from PIL import Image
    img = Image.open(icon_src)
    img.save(icon_ico, format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

a = Analysis(
    ['app/win_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icon.png', 'assets'),
        ('assets/icon_active.png', 'assets'),
        ('assets/sounds/start.wav', 'assets/sounds'),
        ('assets/sounds/stop.wav', 'assets/sounds'),
        ('assets/sounds/done.wav', 'assets/sounds'),
        # Flume UI fonts (Geist + JetBrains Mono). fonts_css.py / theme.py read
        # them from sys._MEIPASS/app/assets/fonts, so the dest must mirror that.
        ('app/assets/fonts', 'app/assets/fonts'),
        (fw_dir, 'faster_whisper'),
        (ct2_dir, 'ctranslate2'),
        # sounddevice.py / soundfile.py are bare single-file modules sitting
        # directly in site-packages (not package folders) — os.path.dirname()
        # of either one's __file__ resolves to the WHOLE site-packages
        # directory, not a per-package folder. That would have silently
        # duplicated every installed dependency (numpy/scipy/ctranslate2
        # included) into these two datas entries, likely enough extra
        # gigabytes to risk a disk-space or timeout failure on the runner —
        # found by inspecting __file__ paths directly rather than waiting for
        # that to surface as its own confusing failure (2026-08-22). Both
        # libraries actually only need their own native-binary sidecar
        # package (`import _sounddevice_data` / `import _soundfile_data` —
        # confirmed by reading their source), so bundle exactly that.
        (os.path.join(os.path.dirname(sounddevice.__file__), '_sounddevice_data'), '_sounddevice_data'),
        (os.path.join(os.path.dirname(soundfile.__file__), '_soundfile_data'), '_soundfile_data'),
        (os.path.dirname(numpy.__file__), 'numpy'),
        (os.path.dirname(groq.__file__), 'groq'),
        # `google` is a PEP 420 namespace package (no single __init__.py, so
        # __file__ is None — confirmed live: TypeError, "expected str, bytes
        # or os.PathLike object, not NoneType", 2026-08-22). Go through the
        # concrete `google.generativeai` submodule instead and step up two
        # directories to reach the namespace folder that actually holds it.
        (os.path.dirname(os.path.dirname(google.generativeai.__file__)), 'google'),
        (os.path.dirname(pyperclip.__file__), 'pyperclip'),
        (os.path.dirname(pyautogui.__file__), 'pyautogui'),
        (os.path.dirname(PIL.__file__), 'PIL'),
        (os.path.dirname(websocket.__file__), 'websocket'),
        (os.path.dirname(httpx.__file__), 'httpx'),
        (os.path.dirname(pystray.__file__), 'pystray'),
        (os.path.dirname(webview.__file__), 'webview'),
        (os.path.dirname(scipy.__file__), 'scipy'),
    ],
    hiddenimports=[
        'app.recorder',
        'app.transcriber',
        'app.ai_cleanup',
        'app.config',
        'app.sync',
        'app.updater',
        'app.win_injector',
        'app.win_overlay',
        'app.win_dashboard',  # retired tkinter fallback — kept as last-resort UI
        'app.shared_dashboard',
        'app.win_main',
        # Flume UI renderers (shared with macOS). These build the HTML that the
        # WebView2-hosted dashboard/popover/overlay/meeting surfaces load.
        'app.flume_dashboard_html',
        'app.flume_popover_html',
        'app.overlay_html',
        'app.meeting_html',
        # (app.meeting_hud_html was here — the separate meeting HUD was deleted
        # in IDI-179; a hiddenimport for a missing module fails the build.)
        'app.autolearn_widget',
        'app.fonts_css',
        # Lazily imported (function-level) by win_main.py/shared_dashboard.py —
        # declared explicitly per Rule #30 rather than relying on bytecode scan.
        'app.insights',
        # IDI-216 team layer. Imported at FUNCTION level from dictionary.py,
        # shared_dashboard.py and auth.py, so bytecode analysis won't reach it —
        # a frozen build without it would fail only when a user opens Team or
        # dictates while in one (Hard Rule #30).
        'app.organizations',
        # NOTE: app.theme is intentionally NOT listed — it imports AppKit/Foundation
        # at module load time and is macOS-only. Adding it would break the frozen
        # Windows exe. Windows uses fonts_css.py (base64 @font-face) instead.
        # Windows-native modules (added by the native-parity workstream). Listed
        # ahead of time so the frozen exe bundles them once they land.
        'app.win_system_audio',
        'app.win_editwatch',
        'app.win_ax',
        # Third-party deps used by the Windows-native modules above.
        'uiautomation',
        'comtypes',
        'comtypes.client',
        'faster_whisper',
        'faster_whisper.utils',
        'faster_whisper.tokenizer',
        'faster_whisper.audio',
        'ctranslate2',
        'google.generativeai',
        'groq',
        # Device pairing's QR renderer. `app/pairing.py::qr_svg` imports this
        # INSIDE the function, so a frozen build that misses it fails only when
        # the user opens "Pair a device" — listed explicitly rather than trusting
        # bytecode analysis of a lazy import.
        'qrcode',
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'pystray._win32',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
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
        'pystray',
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_ico if os.path.exists(icon_ico) else None,
    version='version_info.txt',
)
