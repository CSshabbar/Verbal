# verbal-win.spec — PyInstaller spec for Windows build

import sys
import os
import re

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

# Convert PNG icon to ICO for Windows. `assets/icon.png` is a tiny 44x44
# flat black mic silhouette meant for the menu-bar-style tray glyph
# (generate_menu_icon() in scripts/generate_icons.py), not a real app icon —
# using it here produced a blank/tiny-looking .exe and installer icon.
# `assets/app_icon.png` is the real 1024x1024 Flume brand icon.
icon_src = 'assets/app_icon.png'
icon_ico = 'assets/icon.ico'
# Regenerate when the .ico is MISSING *or* OLDER than app_icon.png. The old
# "only if missing" check meant a stale icon.ico lying around from a previous
# build (local dist/ dirs, a cached CI checkout) kept shipping the retired
# Verbal art after the 2026-08-25 mascot rebrand.
def _ico_stale():
    if not os.path.exists(icon_ico):
        return True
    try:
        return os.path.getmtime(icon_ico) < os.path.getmtime(icon_src)
    except OSError:
        return True
if os.path.exists(icon_src) and _ico_stale():
    from PIL import Image
    img = Image.open(icon_src)
    img.save(icon_ico, format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

# Windows file-version metadata (what Task Manager, Explorer "Details" and
# Settings > Apps display). Generated from config.APP_VERSION at build time so
# it can never drift: the checked-in version_info.txt shipped "Verbal
# Speech-to-Text 1.0.10" on every build through 1.0.35, which is why Task
# Manager still said "Verbal" long after the Flume rebrand (2026-08-28).
def _app_version():
    with open(os.path.join('app', 'config.py'), encoding='utf-8') as f:
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else '0.0.0'

def _write_version_info():
    ver = _app_version()
    nums = [int(x) for x in re.findall(r'\d+', ver)][:3]
    while len(nums) < 4:
        nums.append(0)
    tpl = open('version_info.txt', encoding='utf-8').read()
    tpl = re.sub(r'filevers=\([^)]*\)', 'filevers=(%d, %d, %d, %d)' % tuple(nums), tpl)
    tpl = re.sub(r'prodvers=\([^)]*\)', 'prodvers=(%d, %d, %d, %d)' % tuple(nums), tpl)
    tpl = re.sub(r"(u'(?:File|Product)Version', u')[^']*(')", r'\g<1>%s\g<2>' % ver, tpl)
    os.makedirs('build', exist_ok=True)
    out = os.path.join('build', 'version_info.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(tpl)
    return out

version_file = _write_version_info()

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
        # win_main.py's paste-blocked prompt (`from app import paste_guard`) is a
        # FUNCTION-level import too — declared explicitly per Rule #30 rather than
        # relying on bytecode scan.
        'app.paste_guard',
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
    [],
    exclude_binaries=True,
    name='Flume',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_ico if os.path.exists(icon_ico) else None,
    version=version_file,
)

# ONEDIR (COLLECT), not one-file — deliberately, 2026-08-28. The one-file exe
# was a ~9 MB bootloader that unpacked ~600 MB to %TEMP%\_MEIxxxx on EVERY
# launch and then spawned the real app as a CHILD Flume.exe: two processes in
# Task Manager, "End task" on the wrong one orphaned the child (still holding
# VerbalSingletonMutex_v1 → the next launch silently exited), slow cold starts,
# AV scanners chewing on the extraction, and a stale _MEI dir left behind on
# every crash. onedir is ONE process, no extraction, dist\Flume\Flume.exe +
# dist\Flume\_internal\. win_main._watch_bootloader_parent detects this
# layout and disarms itself; sys._MEIPASS now points at _internal, so every
# `sys._MEIPASS/...` asset lookup keeps working. verbal-setup.iss packages
# `dist\Flume\*` recursively (was `dist\Flume.exe`).
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Flume',
)
