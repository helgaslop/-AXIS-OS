# -*- mode: python ; coding: utf-8 -*-
import os, sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath('.')

# ── Datas ────────────────────────────────────────────────────────────────────
datas = [
    ('gui/ui',   'gui/ui'),
    ('data',     'data'),
    ('assets',   'assets'),
    ('version.txt', '.'),
]

def _try_pkg(pkg):
    try:
        return collect_data_files(pkg)
    except Exception:
        return []

datas += _try_pkg('PyQt6')
datas += _try_pkg('spotipy')
datas += _try_pkg('speech_recognition')
datas += _try_pkg('openai')
datas += _try_pkg('anthropic')
datas += _try_pkg('google.generativeai')

# ── Hidden imports ────────────────────────────────────────────────────────────
hidden = [
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebChannel',
    'PyQt6.QtNetwork',
    'PyQt6.QtPrintSupport',
    'spotipy', 'spotipy.oauth2',
    'openai', 'anthropic',
    'google.generativeai',
    'psutil', 'requests',
    'winreg', 'ctypes', 'ctypes.wintypes',
    'json', 'threading', 'subprocess',
    'core.paths', 'core.log_bridge', 'core.ai_manager', 'core.system_monitor',
    'gui.bridge', 'gui.handlers',
]

try:
    import speech_recognition
    hidden += ['speech_recognition', 'pyaudio']
except ImportError:
    pass

try:
    import pyttsx3
    hidden += ['pyttsx3', 'pyttsx3.drivers', 'pyttsx3.drivers.sapi5']
except ImportError:
    pass

# ── Binaries: explicitly include python DLL + VC++ runtime ───────────────────
binaries = collect_dynamic_libs('PyQt6')

# Include python3xx.dll from the Python install
py_dll = os.path.join(os.path.dirname(sys.executable), f'python{sys.version_info.major}{sys.version_info.minor}.dll')
if os.path.exists(py_dll):
    binaries.append((py_dll, '.'))

# Include VC++ runtime DLLs if present alongside python
vcrt_dir = os.path.dirname(sys.executable)
for dll_name in ['vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll']:
    dll_path = os.path.join(vcrt_dir, dll_name)
    if os.path.exists(dll_path):
        binaries.append((dll_path, '.'))

# ── Icon ──────────────────────────────────────────────────────────────────────
icon_path = os.path.join(ROOT, 'data', 'icon_panel.ico')
icon_arg  = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'test', 'unittest'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AXIS_OS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_arg,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='AXIS_OS',
)
