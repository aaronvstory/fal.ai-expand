"""
Path utilities for PyInstaller compatibility.
Provides functions to get correct paths whether running as script or frozen exe.
"""

import sys
import os
from pathlib import Path
from typing import Optional


def get_app_dir() -> str:
    """
    Get the directory where the application is located.
    
    When running as a script: Returns the directory containing the main .py file
    When running as frozen exe: Returns the directory containing the .exe
    
    Returns:
        str: Absolute path to the application directory
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (PyInstaller)
        # sys.executable points to the .exe file
        return os.path.dirname(sys.executable)
    else:
        # Running as a Python script
        # Use the directory of the main module
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_resource_dir() -> str:
    """
    Get the directory where bundled resources are located.
    
    When running as a script: Same as get_app_dir()
    When running as frozen exe: Returns the _MEIPASS temp directory
    
    This is for read-only bundled resources, not user data.
    
    Returns:
        str: Absolute path to the resource directory
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        # _MEIPASS contains extracted bundled files
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # Running as a Python script
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_config_path(filename: str = "outpaint_config.json") -> str:
    """
    Get the full path for a configuration file.
    Config files are stored next to the executable/script.
    
    Args:
        filename: Name of the config file
        
    Returns:
        str: Full path to the config file
    """
    return os.path.join(get_app_dir(), filename)


def get_log_path(filename: str = "outpaint_gui.log") -> str:
    """
    Get the full path for a log file.
    Log files are stored next to the executable/script.
    
    Args:
        filename: Name of the log file
        
    Returns:
        str: Full path to the log file
    """
    return os.path.join(get_app_dir(), filename)


def get_crash_log_path() -> str:
    """
    Get the full path for the crash log file.
    
    Returns:
        str: Full path to crash_log.txt
    """
    return os.path.join(get_app_dir(), "crash_log.txt")


def detect_comfyui_path() -> Optional[str]:
    """Best-effort ComfyUI install path detection (folder containing main.py)."""

    candidates: list[str] = []
    env = os.getenv("COMFYUI_PATH")
    if env:
        candidates.append(env)

    candidates.extend(
        [
            "G:/pinokio/api/comfy.git/app",
            "C:/pinokio/api/comfy.git/app",
            "D:/pinokio/api/comfy.git/app",
            "~/.pinokio/api/comfy.git/app",
            "~/pinokio/api/comfy.git/app",
            "C:/AI/ComfyUI",
            "D:/AI/ComfyUI",
            "~/ComfyUI",
            "~/.local/ComfyUI",
        ]
    )

    for raw in candidates:
        try:
            p = Path(os.path.expanduser(raw))
            if p.is_file() and p.name.lower() == "main.py":
                p = p.parent
            if (p / "main.py").exists() or (p / "comfy" / "__init__.py").exists():
                return str(p)
        except Exception:
            continue
    return None


def is_frozen() -> bool:
    """
    Check if running as a frozen executable.
    
    Returns:
        bool: True if running as exe, False if running as script
    """
    return getattr(sys, 'frozen', False)
