from __future__ import annotations

import platform
import sys
from importlib import metadata
from typing import Any, Tuple

from path_utils import detect_comfyui_path


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except Exception:
        return "not installed"


def run_diagnostics(config: dict[str, Any]) -> Tuple[str, bool]:
    lines: list[str] = []

    def row(label: str, ok: bool, detail: str) -> None:
        lines.append(f"{label:<18}│ {'✓' if ok else '✗'} {detail}")

    lines.append("SYSTEM DIAGNOSTICS")
    lines.append("=" * 70)

    row("Python", True, sys.version.split()[0])
    row("OS", True, f"{platform.system()} {platform.release()}")
    row("requests", _pkg_version("requests") != "not installed", _pkg_version("requests"))
    row("Pillow", _pkg_version("Pillow") != "not installed", _pkg_version("Pillow"))
    row("pydantic", _pkg_version("pydantic") != "not installed", _pkg_version("pydantic"))

    lines.append("-" * 70)

    api_key = (config.get("falai_api_key") or "").strip()
    row("fal.ai API key", bool(api_key), "present" if api_key else "missing")

    lines.append("-" * 70)

    comfy_path = detect_comfyui_path()
    row("ComfyUI Path", bool(comfy_path), comfy_path or "not found")

    comfy_ok = True
    comfy_msg = "skipped"
    try:
        from backends.comfyui_backend import ComfyUIOutpaintBackend

        base_url = str(config.get("comfyui_url") or "http://127.0.0.1:8188")
        workflow = str(config.get("comfyui_workflow_path") or "comfyui_workflows/flux_outpaint.json")
        b = ComfyUIOutpaintBackend(base_url=base_url, workflow_path=workflow)
        comfy_ok, comfy_msg = b.check_available()
    except Exception as e:
        comfy_ok = False
        comfy_msg = str(e)

    row("ComfyUI Server", comfy_ok, comfy_msg)

    overall_ok = all(
        (
            _pkg_version("requests") != "not installed",
            _pkg_version("Pillow") != "not installed",
            _pkg_version("pydantic") != "not installed",
        )
    )
    return "\n".join(lines), overall_ok
