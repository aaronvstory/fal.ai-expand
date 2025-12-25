from __future__ import annotations

import io
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import requests
from PIL import Image

from backends import ProgressCallback, get_backend
from outpaint_config import (
    OutpaintConfig,
    SUPPORTED_INPUT_FORMATS,
    check_output_size,
    collect_config_errors,
    validate_input_image,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutpaintResult:
    source_path: str
    output_paths: list[str]


def load_config_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_config_file(path: str, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def default_config_dict() -> dict:
    return {
        "backend": "falai",
        "falai_api_key": "",
        "enable_safety_checker": True,
        "comfyui_url": "http://127.0.0.1:8188",
        "comfyui_workflow_path": "comfyui_workflows/flux_outpaint.json",
        "output_folder": "",
        "use_source_folder": True,
        "output_suffix": "-expanded",
        "output_format": "png",
        "zoom_out_percentage": 30,
        "expand_left": 200,
        "expand_right": 200,
        "expand_top": 200,
        "expand_bottom": 200,
        "num_images": 1,
        "prompt": "",
        "workers": {"falai": 5, "comfyui": 2},
        "allow_reprocess": True,
        "reprocess_mode": "increment",
        "verbose_logging": True,
        "diagnostics_run": False,
        "folder_filter_pattern": "",
        "folder_match_mode": "partial",
        "window_geometry": "",
        "sash_dropzone": 200,
        "sash_queue": 280,
        "sash_log": 350,
    }


def load_outpaint_config(config_path: str) -> tuple[Optional[OutpaintConfig], list[str], dict]:
    base = default_config_dict()
    loaded = load_config_file(config_path)
    merged = {**base, **(loaded or {})}

    errors: list[str] = []
    try:
        cfg = OutpaintConfig.model_validate(merged)
    except Exception as e:
        # Pydantic ValidationError string is readable enough for GUI/CLI
        errors.append(str(e))
        cfg = None

    if cfg is not None:
        errors.extend(collect_config_errors(cfg))

    return cfg, errors, merged


def iter_image_files_in_folder(folder: str) -> Iterable[str]:
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        return
    for root, _dirs, files in os.walk(p):
        for fn in files:
            ext = Path(fn).suffix.lower()
            if ext in SUPPORTED_INPUT_FORMATS:
                yield str(Path(root) / fn)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    for i in range(2, 1000):
        cand = path.with_name(f"{stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
    raise ValueError(f"Too many versions of {path.name}")


class OutpaintGenerator:
    def __init__(self, config: OutpaintConfig):
        self.config = config
        self._backend = get_backend(config)
        self._progress_callback: Optional[ProgressCallback] = None
        self._fallback_attempted = False

    def set_progress_callback(self, callback: Optional[ProgressCallback]) -> None:
        self._progress_callback = callback

    def _progress(self, message: str, level: str = "info") -> None:
        if self._progress_callback:
            self._progress_callback(message, level)

    def _try_fallback_to_falai(self) -> bool:
        """Auto-fallback to falai backend if ComfyUI fails and API key is available."""
        if self._fallback_attempted or self.config.backend != "comfyui":
            return False

        self._fallback_attempted = True

        # Check if falai API key is configured
        if not self.config.falai_api_key or self.config.falai_api_key.strip() == "":
            self._progress("ComfyUI failed and no falai API key configured. Cannot auto-fallback.", "error")
            return False

        self._progress("ComfyUI backend failed. Auto-switching to falai backend...", "warning")

        try:
            from backends.falai_backend import FalAIOutpaintBackend
            self._backend = FalAIOutpaintBackend(api_key=self.config.falai_api_key)
            self._progress("Successfully switched to falai backend", "info")
            return True
        except Exception as e:
            self._progress(f"Failed to switch to falai backend: {e}", "error")
            return False

    def _outpaint_with_retry(self, image_path: str) -> list[bytes]:
        delays = [1, 2, 4]
        last_err: Exception | None = None
        for attempt, delay in enumerate([0, *delays], start=1):
            if delay:
                self._progress(f"Retrying in {delay}s…", "warning")
                time.sleep(delay)
            try:
                return self._backend.outpaint(
                    image_path,
                    zoom_out_percentage=self.config.zoom_out_percentage,
                    expand_left=self.config.expand_left,
                    expand_right=self.config.expand_right,
                    expand_top=self.config.expand_top,
                    expand_bottom=self.config.expand_bottom,
                    num_images=self.config.num_images,
                    prompt=self.config.prompt,
                    output_format=self.config.output_format,
                    enable_safety_checker=self.config.enable_safety_checker,
                    progress_callback=self._progress_callback,
                )
            except Exception as e:
                last_err = e

                # Detect ComfyUI crash/unavailability (connection refused, server crash)
                is_comfyui_crash = (
                    isinstance(e, requests.RequestException) and
                    ("connection refused" in str(e).lower() or
                     "connection error" in str(e).lower() or
                     "max retries" in str(e).lower())
                )

                # Try fallback to falai on ComfyUI crash
                if is_comfyui_crash and not self._fallback_attempted:
                    if self._try_fallback_to_falai():
                        # Retry immediately with new backend
                        try:
                            return self._backend.outpaint(
                                image_path,
                                zoom_out_percentage=self.config.zoom_out_percentage,
                                expand_left=self.config.expand_left,
                                expand_right=self.config.expand_right,
                                expand_top=self.config.expand_top,
                                expand_bottom=self.config.expand_bottom,
                                num_images=self.config.num_images,
                                prompt=self.config.prompt,
                                output_format=self.config.output_format,
                                enable_safety_checker=self.config.enable_safety_checker,
                                progress_callback=self._progress_callback,
                            )
                        except Exception as fallback_err:
                            self._progress(f"Fallback backend also failed: {fallback_err}", "error")
                            raise

                # Only retry transient failures
                transient = isinstance(e, (TimeoutError, requests.RequestException))
                if not transient:
                    raise
                if attempt >= 1 + len(delays):
                    raise

        assert last_err is not None
        raise last_err

    def check_backend_available(self) -> tuple[bool, str]:
        if getattr(self._backend, "check_available", None):
            return self._backend.check_available()  # type: ignore[attr-defined]
        return True, "OK"

    def _get_output_folder(self, image_path: str) -> Path:
        if self.config.use_source_folder:
            return Path(image_path).parent
        if self.config.output_folder:
            return Path(self.config.output_folder)
        return Path(image_path).parent

    def generate(self, image_path: str) -> OutpaintResult:
        ok, msg, size = validate_input_image(image_path)
        if not ok:
            raise ValueError(msg)

        assert size is not None
        size_check = check_output_size(
            size[0],
            size[1],
            self.config.zoom_out_percentage,
            self.config.expand_left,
            self.config.expand_right,
            self.config.expand_top,
            self.config.expand_bottom,
        )
        if size_check[0] is False:
            raise ValueError(size_check[1])
        if size_check[0] == "warning":
            self._progress(size_check[1], "warning")

        out_dir = self._get_output_folder(image_path)
        _ensure_dir(out_dir)

        stem = Path(image_path).stem
        fmt = self.config.output_format
        suffix = self.config.output_suffix

        out_bytes = self._outpaint_with_retry(image_path)

        outputs: list[str] = []
        for idx, b in enumerate(out_bytes, start=1):
            numbered = f"_{idx}" if len(out_bytes) > 1 else ""
            filename = f"{stem}{suffix}{numbered}.{fmt}"
            target = out_dir / filename

            if target.exists() and not self.config.allow_reprocess:
                continue

            if target.exists() and self.config.reprocess_mode == "increment":
                target = _next_available_path(target)

            # Normalize format
            img = Image.open(io.BytesIO(b))
            if fmt == "jpeg":
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(target, format="JPEG", quality=95)
            elif fmt == "webp":
                img.save(target, format="WEBP", quality=90)
            else:
                img.save(target, format="PNG")

            outputs.append(str(target))

        if not outputs:
            raise RuntimeError("No outputs written")

        return OutpaintResult(source_path=image_path, output_paths=outputs)

    def generate_many(
        self,
        image_paths: list[str],
        *,
        max_workers: Optional[int] = None,
        per_item_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[OutpaintResult]:
        workers = max_workers or (self.config.workers.falai if self.config.backend == "falai" else self.config.workers.comfyui)
        results: list[OutpaintResult] = []
        total = len(image_paths)
        done = 0
        durations: list[float] = []

        def work(p: str) -> OutpaintResult:
            return self.generate(p)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            start_times = {p: time.perf_counter() for p in image_paths}
            futs = {ex.submit(work, p): p for p in image_paths}
            for fut in as_completed(futs):
                src = futs[fut]
                done += 1
                dur = max(0.0, time.perf_counter() - start_times.get(src, time.perf_counter()))
                durations.append(dur)

                if durations:
                    avg = sum(durations) / len(durations)
                    eta = avg * (total - done)
                    self._progress(f"{done}/{total} complete • ETA {int(eta // 60)}m{int(eta % 60)}s", "progress")

                if per_item_callback:
                    per_item_callback(done, total, src)

                try:
                    results.append(fut.result())
                except Exception as e:
                    self._progress(f"Failed: {os.path.basename(src)} • {e}", "error")

        return results
