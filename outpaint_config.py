from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


OutputFormat = Literal["png", "jpeg", "webp"]
BackendName = Literal["falai", "comfyui"]


SUPPORTED_INPUT_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
MAX_IMAGE_PIXELS = 4096 * 4096


class WorkerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    falai: int = 5
    comfyui: int = 2


class OutpaintConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: BackendName = "falai"

    # fal.ai
    falai_api_key: str = ""
    enable_safety_checker: bool = True

    # ComfyUI
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_workflow_path: str = "comfyui_workflows/flux_outpaint.json"

    # IO
    output_folder: str = ""
    use_source_folder: bool = True
    output_suffix: str = "-expanded"
    output_format: OutputFormat = "png"

    # Outpaint params
    zoom_out_percentage: int = 30
    expand_mode: Literal["pixels", "percentage"] = "percentage"
    expand_percentage: int = 30
    expand_left: int = 0
    expand_right: int = 0
    expand_top: int = 0
    expand_bottom: int = 0
    num_images: int = 1
    prompt: str = ""

    # Processing
    workers: WorkerConfig = Field(default_factory=WorkerConfig)
    allow_reprocess: bool = True
    reprocess_mode: Literal["overwrite", "increment"] = "increment"
    verbose_logging: bool = True

    # GUI misc
    diagnostics_run: bool = False
    folder_filter_pattern: str = ""
    folder_match_mode: Literal["partial", "exact"] = "partial"
    window_geometry: str = ""
    sash_left_right: int = 380
    sash_queue_log: int = 600

    @field_validator("zoom_out_percentage")
    @classmethod
    def _zoom_range(cls, v: int) -> int:
        if not (0 <= v <= 90):
            raise ValueError("zoom_out_percentage must be in range 0-90")
        return v

    @field_validator("expand_percentage")
    @classmethod
    def _expand_pct_range(cls, v: int) -> int:
        if not (0 <= v <= 200):
            raise ValueError("expand_percentage must be in range 0-200")
        return v

    @field_validator("expand_left", "expand_right", "expand_top", "expand_bottom")
    @classmethod
    def _expand_range(cls, v: int) -> int:
        if not (0 <= v <= 700):
            raise ValueError("expand values must be in range 0-700")
        return v

    @field_validator("num_images")
    @classmethod
    def _num_images_range(cls, v: int) -> int:
        if not (1 <= v <= 4):
            raise ValueError("num_images must be in range 1-4")
        return v

    @field_validator("output_suffix")
    @classmethod
    def _suffix_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("output_suffix must not be empty")
        if "\x00" in v:
            raise ValueError("output_suffix contains invalid characters")
        if any(sep and sep in v for sep in ("/", "\\", os.sep, os.altsep)):
            raise ValueError("output_suffix must not contain path separators")
        if ":" in v:
            raise ValueError("output_suffix must not contain ':'")
        return v




def validate_output_folder(path: str) -> tuple[bool, str]:
    if not path:
        return True, "Using source folder"

    folder = Path(path)
    if not folder.exists():
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return False, f"Cannot create folder: {path}"
        except OSError as e:
            return False, f"Cannot create folder: {path} ({e})"

    test_file = folder / ".write_test"
    try:
        test_file.touch()
        test_file.unlink(missing_ok=True)
        return True, "Output folder writable"
    except PermissionError:
        return False, f"No write permission: {path}"
    except OSError as e:
        return False, f"Cannot write to folder: {path} ({e})"


def validate_input_image(path: str) -> tuple[bool, str, Optional[tuple[int, int]]]:
    p = Path(path)
    if not p.exists():
        return False, f"File not found: {path}", None
    if p.suffix.lower() not in SUPPORTED_INPUT_FORMATS:
        return False, f"Unsupported format: {p.suffix}", None

    try:
        from PIL import Image

        with Image.open(p) as img:
            w, h = img.size
            if w * h > MAX_IMAGE_PIXELS:
                return False, f"Image too large: {w}x{h} (max 4096x4096)", (w, h)
            return True, f"Valid image: {w}x{h}", (w, h)
    except Exception as e:
        return False, f"Cannot read image: {e}", None


def check_output_size(
    width: int,
    height: int,
    zoom_pct: int,
    expand_l: int,
    expand_r: int,
    expand_t: int,
    expand_b: int,
) -> tuple[bool | str, str]:
    scale = 1.0
    if zoom_pct > 0:
        scale = 1.0 / (1.0 - zoom_pct / 100.0)
    new_w = int(width * scale) + expand_l + expand_r
    new_h = int(height * scale) + expand_t + expand_b

    total_pixels = new_w * new_h
    # Increased limit for modern systems with sufficient RAM
    if total_pixels > 100_000_000:  # 100MP limit
        return False, f"Output {new_w}x{new_h} ({total_pixels/1e6:.1f}MP) exceeds 100MP limit"
    if total_pixels > 50_000_000:  # 50MP warning
        return "warning", f"Large output: {new_w}x{new_h} ({total_pixels/1e6:.1f}MP) - may be slow"
    return True, f"Output size OK: {new_w}x{new_h} ({total_pixels/1e6:.1f}MP)"


def collect_config_errors(cfg: OutpaintConfig) -> list[str]:
    errors: list[str] = []

    if cfg.backend == "falai" and not cfg.falai_api_key.strip():
        errors.append("falai_api_key is required when backend is 'falai'")

    if cfg.backend == "comfyui":
        p = Path(cfg.comfyui_workflow_path)
        if not p.is_absolute():
            candidates = [Path.cwd() / p, Path(__file__).resolve().parent / p]
            p = next((c for c in candidates if c.exists()), candidates[-1])
        if not p.exists():
            errors.append(f"ComfyUI workflow not found: {cfg.comfyui_workflow_path} (expected at {p})")

    ok, msg = validate_output_folder(cfg.output_folder)
    if not ok:
        errors.append(msg)

    return errors
