# verbal-win.spec — PyInstaller spec for Windows build

import sys
import os

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
        'app.win_main',
        'faster_whisper',
        'google.generativeai',
        'groq',
        'pystray._win32',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
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
)
