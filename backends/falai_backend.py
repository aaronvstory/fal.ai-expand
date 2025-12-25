from __future__ import annotations

import base64
import io
import os
import time
import threading
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

from . import OutpaintBackend, ProgressCallback


class FalAIOutpaintBackend(OutpaintBackend):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.queue_url = "https://queue.fal.run/fal-ai/image-apps-v2/outpaint"

        # Freeimage.host API key - required for image upload
        # Default public guest key available in .env.example if needed
        self.freeimage_key = os.getenv("FREEIMAGE_API_KEY", "")

    def _progress(self, cb: Optional[ProgressCallback], message: str, level: str = "info"):
        if cb:
            cb(message, level)

    def _upload_to_freeimage(self, image_path: str, cb: Optional[ProgressCallback]) -> str:
        p = Path(image_path)

        buffer = io.BytesIO()
        with Image.open(p) as opened:
            img = opened

            # Only resize if image is unreasonably large (>4096px) to avoid upload issues
            max_size = 4096
            if img.width > max_size or img.height > max_size:
                self._progress(cb, f"⚠ Image too large ({img.width}x{img.height}), resizing to fit {max_size}px", "resize")
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            converted: Image.Image | None = None
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    src = img.convert("RGBA")
                    try:
                        background.paste(src, mask=src.split()[-1])
                    finally:
                        src.close()
                else:
                    background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                converted = background
                img = converted

            try:
                img.save(buffer, format="JPEG", quality=95, optimize=True)
            finally:
                if converted is not None:
                    converted.close()

        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")

        self._progress(cb, f"Uploading {p.name}…", "upload")
        resp = requests.post(
            "https://freeimage.host/api/1/upload",
            data={"key": self.freeimage_key, "action": "upload", "source": image_base64, "format": "json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status_code") != 200 or "image" not in data or "url" not in data["image"]:
            raise RuntimeError(f"freeimage upload failed: {data}")
        url = data["image"]["url"]
        self._progress(cb, f"✓ Uploaded: {url}", "upload")
        return url

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
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

        image_url = self._upload_to_freeimage(image_path, progress_callback)

        headers = {"Authorization": f"Key {self.api_key}", "Content-Type": "application/json"}
        status_headers = {"Authorization": f"Key {self.api_key}"}

        payload = {
            "image_url": image_url,
            "zoom_out_percentage": zoom_out_percentage,
            "expand_left": expand_left,
            "expand_right": expand_right,
            "expand_top": expand_top,
            "expand_bottom": expand_bottom,
            "num_images": num_images,
            "prompt": prompt or "",
            "enable_safety_checker": bool(enable_safety_checker),
            "output_format": output_format,
        }

        self._progress(progress_callback, "Submitting outpaint job…", "api")
        submit = requests.post(self.queue_url, headers=headers, json=payload, timeout=30)
        if submit.status_code == 402:
            raise RuntimeError("Payment required (insufficient credits)")
        submit.raise_for_status()
        submit_data = submit.json()
        status_url = submit_data.get("status_url")
        request_id = submit_data.get("request_id")
        if not status_url or not request_id:
            raise RuntimeError(f"Unexpected submit response: {submit_data}")
        self._progress(progress_callback, f"✓ Task created: {request_id}", "task")

        def sleep_with_cancel(seconds: float) -> None:
            if cancel_event is None:
                time.sleep(seconds)
                return
            end = time.time() + seconds
            while time.time() < end:
                if cancel_event.is_set():
                    raise CancelledError()
                time.sleep(min(0.2, end - time.time()))

        # Poll
        attempt = 0
        max_attempts = 240
        while attempt < max_attempts:
            sleep_with_cancel(5 if attempt < 24 else 10 if attempt < 60 else 15)
            attempt += 1

            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()

            resp = requests.get(status_url, headers=status_headers, timeout=30)
            if resp.status_code == 404:
                raise RuntimeError("Job not found (expired)")
            if resp.status_code == 429:
                time.sleep(30)
                continue
            resp.raise_for_status()

            status_data = resp.json()
            status = status_data.get("status")
            if status in ("IN_QUEUE", "IN_PROGRESS"):
                continue
            if status == "COMPLETED":
                output = status_data.get("output")
                images = None
                if isinstance(output, dict):
                    images = output.get("images")
                if images is None:
                    images = status_data.get("images")

                if images is None and status_data.get("response_url"):
                    r = requests.get(status_data["response_url"], headers=status_headers, timeout=30)
                    r.raise_for_status()
                    images = r.json().get("images")

                if not images:
                    raise RuntimeError(f"No images in response: {status_data}")

                results: list[bytes] = []
                for img in images:
                    if cancel_event is not None and cancel_event.is_set():
                        raise CancelledError()

                    url = img.get("url") if isinstance(img, dict) else (img if isinstance(img, str) else None)
                    if not url:
                        continue
                    self._progress(progress_callback, f"Downloading {url}", "download")
                    out = requests.get(url, timeout=120)
                    out.raise_for_status()
                    results.append(out.content)

                if not results:
                    raise RuntimeError("No downloadable images returned")
                return results

            if status in ("FAILED", "ERROR", "CANCELLED"):
                raise RuntimeError(status_data.get("error") or f"Job {status}")

        raise TimeoutError("Timeout waiting for fal.ai outpaint job")
