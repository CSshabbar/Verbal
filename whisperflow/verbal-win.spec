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
import pywebview
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
        (fw_dir, 'faster_whisper'),
        (ct2_dir, 'ctranslate2'),
        # Include all dependencies
        (os.path.dirname(sounddevice.__file__), 'sounddevice'),
        (os.path.dirname(soundfile.__file__), 'soundfile'),
        (os.path.dirname(numpy.__file__), 'numpy'),
        (os.path.dirname(groq.__file__), 'groq'),
        (os.path.dirname(google.__file__), 'google'),
        (os.path.dirname(pyperclip.__file__), 'pyperclip'),
        (os.path.dirname(pyautogui.__file__), 'pyautogui'),
        (os.path.dirname(PIL.__file__), 'PIL'),
        (os.path.dirname(websocket.__file__), 'websocket'),
        (os.path.dirname(httpx.__file__), 'httpx'),
        (os.path.dirname(pystray.__file__), 'pystray'),
        (os.path.dirname(pywebview.__file__), 'pywebview'),
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
        'app.win_dashboard',
        'app.shared_dashboard',
        'app.win_main',
        'faster_whisper',
        'faster_whisper.utils',
        'faster_whisper.tokenizer',
        'faster_whisper.audio',
        'ctranslate2',
        'google.generativeai',
        'groq',
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
        'pywebview',
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
