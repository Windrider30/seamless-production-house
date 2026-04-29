# -*- mode: python ; coding: utf-8 -*-
# macOS .app bundle spec — produces dist/SeamlessProductionHouse.app
import os
from PyInstaller.utils.hooks import collect_all

datas = [('src', 'src')]
binaries = []
hiddenimports = [
    'customtkinter', 'tkinterdnd2', 'cv2',
    'PIL', 'PIL._tkinter_finder', 'requests', 'psutil', 'numpy',
]

tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Bundle FFmpeg/FFprobe if present in bin/ (placed there by the CI workflow)
for name in ('ffmpeg', 'ffprobe'):
    src = os.path.join('bin', name)
    if os.path.isfile(src):
        binaries.append((src, 'bin'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SeamlessProductionHouse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SeamlessProductionHouse',
)

app = BUNDLE(
    coll,
    name='SeamlessProductionHouse.app',
    icon=None,
    bundle_identifier='com.seamless.productionhouse',
    info_plist={
        'CFBundleDisplayName': 'Seamless Production House',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '12.0',
    },
)
