# -*- mode: python ; coding: utf-8 -*-
# pyinstaller release_gui.spec --noconfirm

a = Analysis(
    ['release_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('data/icon_panel.ico', 'data'),
    ],
    hiddenimports=['PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui'],
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
    name='AXIS_Release',
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
    icon='data/icon_panel.ico',
    onefile=True,

)
