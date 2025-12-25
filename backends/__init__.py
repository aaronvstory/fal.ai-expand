from __future__ import annotations

from abc import ABC, abstractmethod
import threading
from typing import Callable, Optional

from outpaint_config import OutpaintConfig


ProgressCallback = Callable[[str, str], None]


class OutpaintBackend(ABC):
    @abstractmethod
    def outpaint(
        self,
        image_path: str,
        *,
        zoom_out_percentage: int,
        expand_left: int,
        expand_right: int,
        expand_top: int,
        expand_bottom: int,
        num_images: int,
        prompt: str,
        output_format: str,
        enable_safety_checker: bool,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> list[bytes]:
        """Return raw image bytes for each generated output."""


def get_backend(config: OutpaintConfig) -> OutpaintBackend:
    if config.backend == "falai":
        from .falai_backend import FalAIOutpaintBackend

        return FalAIOutpaintBackend(api_key=config.falai_api_key)

    if config.backend == "comfyui":
        from .comfyui_backend import ComfyUIOutpaintBackend

        return ComfyUIOutpaintBackend(
            base_url=config.comfyui_url,
            workflow_path=config.comfyui_workflow_path,
        )

    raise ValueError(f"Unknown backend: {config.backend}")
