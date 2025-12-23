# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Kling UI
Build with: pyinstaller kling_ui.spec
"""

import sys
from pathlib import Path

block_cipher = None

# Get the distribution directory
dist_dir = Path(SPECPATH)

# Collect all Python files in kling_gui package
kling_gui_files = []
kling_gui_path = dist_dir / 'kling_gui'
if kling_gui_path.exists():
    for py_file in kling_gui_path.glob('*.py'):
        kling_gui_files.append((str(py_file), 'kling_gui'))

# Data files to include
datas = [
    # Include the kling_gui package
    (str(dist_dir / 'kling_gui'), 'kling_gui'),
    # Include generator module
    (str(dist_dir / 'kling_generator_falai.py'), '.'),
    # Include dependency checker
    (str(dist_dir / 'dependency_checker.py'), '.'),
    # Include path utilities for frozen exe compatibility
    (str(dist_dir / 'path_utils.py'), '.'),
]

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'path_utils',
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinterdnd2',
    'requests',
    'PIL',
    'PIL.Image',
    'rich',
    'rich.console',
    'rich.progress',
    'rich.panel',
    'rich.text',
    'rich.table',
    'rich.live',
    'rich.spinner',
    'json',
    'logging',
    'threading',
    'concurrent.futures',
    'urllib.request',
    'urllib.parse',
    'base64',
    'hashlib',
    'selenium',
    'selenium.webdriver',
    'webdriver_manager',
    'webdriver_manager.chrome',
]

a = Analysis(
    [str(dist_dir / 'kling_automation_ui.py')],
    pathex=[str(dist_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(dist_dir / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Try to add tkinterdnd2 DLLs
try:
    import tkinterdnd2
    tkdnd_path = Path(tkinterdnd2.__file__).parent

    # Find and add tkdnd DLLs
    for dll_file in tkdnd_path.glob('**/*.dll'):
        rel_path = dll_file.relative_to(tkdnd_path).parent
        a.datas.append((str(dll_file), str(Path('tkinterdnd2') / rel_path), 'DATA'))

    for tcl_file in tkdnd_path.glob('**/*.tcl'):
        rel_path = tcl_file.relative_to(tkdnd_path).parent
        a.datas.append((str(tcl_file), str(Path('tkinterdnd2') / rel_path), 'DATA'))
except ImportError:
    print("Warning: tkinterdnd2 not found, drag-drop may not work in built exe")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KlingUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for error visibility
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KlingUI',
)
