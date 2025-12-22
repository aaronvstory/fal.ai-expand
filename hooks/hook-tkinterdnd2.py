"""
PyInstaller hook for tkinterdnd2
Ensures the tkdnd library files are included in the build.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Collect all data files from tkinterdnd2 (TCL scripts, etc.)
datas = collect_data_files('tkinterdnd2')

# Collect any dynamic libraries
binaries = collect_dynamic_libs('tkinterdnd2')
