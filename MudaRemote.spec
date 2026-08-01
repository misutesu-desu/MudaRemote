# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH)
hiddenimports = [
    'mudae_bot',
    'mudae_core',
    'requests',
    'discord',
    'discord.ext.commands',
    'discord.http',
    'inquirer',
    'keyring',
]
hiddenimports += collect_submodules('mudae_core')

a = Analysis(
    [str(project_root / 'mudae_preset_editor.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(project_root / 'mudae_emoji_assets'), 'mudae_emoji_assets')],
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
    a.binaries,
    a.datas,
    [],
    name='MudaRemote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Packed binaries are more likely to trigger heuristic antivirus engines.
    # Keep UPX disabled even when it happens to be installed on the build host.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project_root / 'icon.png')],
    version=str(project_root / 'packaging' / 'windows_version_info.txt'),
)
