from __future__ import annotations

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Optional

from outpaint_config import SUPPORTED_INPUT_FORMATS, validate_input_image
from outpaint_generator import OutpaintGenerator, OutpaintResult, OutpaintSkipped


@dataclass
class QueueItem:
    path: str
    status: str = "pending"  # pending|processing|completed|failed|skipped
    error_message: Optional[str] = None
    output_paths: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


class QueueManager:
    MAX_QUEUE_SIZE = 50

    def __init__(
        self,
        *,
        config_getter: Callable[[], dict],
        log_callback: Callable[[str, str], None],
        queue_update_callback: Callable[[], None],
        processing_complete_callback: Callable[[QueueItem], None],
        fallback_switch_callback: Callable[[int], Optional[OutpaintGenerator]],
    ):
        self._get_config = config_getter
        self._log = log_callback
        self._on_queue_update = queue_update_callback
        self._on_item_complete = processing_complete_callback
        self._fallback_switch = fallback_switch_callback

        self._lock = threading.Lock()
        self._items: list[QueueItem] = []

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pause = threading.Event()

        self.is_running = False
        self.is_paused = False

    def get_items(self) -> list[QueueItem]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
        self._on_queue_update()

    def add_files(self, paths: list[str]) -> None:
        added = 0
        skipped = 0
        with self._lock:
            existing = {i.path for i in self._items}
            for p in paths:
                if len(self._items) >= self.MAX_QUEUE_SIZE:
                    break
                if p in existing:
                    skipped += 1
                    continue
                ext = os.path.splitext(p)[1].lower()
                if ext not in SUPPORTED_INPUT_FORMATS:
                    skipped += 1
                    continue
                ok, msg, _size = validate_input_image(p)
                if not ok:
                    self._items.append(QueueItem(path=p, status="failed", error_message=msg))
                    added += 1
                    continue
                self._items.append(QueueItem(path=p))
                added += 1

        if added:
            self._log(f"Added {added} item(s)", "info")
        if skipped:
            self._log(f"Skipped {skipped} item(s)", "warning")
        self._on_queue_update()

    def start(self, generator: OutpaintGenerator) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._pause.clear()
        self.is_paused = False
        self.is_running = True
        self._thread = threading.Thread(target=self._run, args=(generator,), daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self.is_paused = True
        self._pause.set()

    def resume(self) -> None:
        self.is_paused = False
        self._pause.clear()

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()
        self.is_paused = False

    def _desired_workers(self, cfg: dict) -> int:
        w = cfg.get("workers") or {}
        try:
            if cfg.get("backend") == "falai":
                return max(1, int(w.get("falai", 5) or 5))
            return max(1, int(w.get("comfyui", 2) or 2))
        except Exception:
            return 1

    def _max_workers(self, cfg: dict) -> int:
        w = cfg.get("workers") or {}
        try:
            return max(1, int(w.get("falai", 5) or 5), int(w.get("comfyui", 2) or 2))
        except Exception:
            return 5

    def _run(self, generator: OutpaintGenerator) -> None:
        consecutive_comfyui_failures = 0

        def pick_pending() -> list[QueueItem]:
            with self._lock:
                return [i for i in self._items if i.status == "pending"]

        ex: ThreadPoolExecutor | None = None
        fut_to_item: dict[Future[OutpaintResult], QueueItem] = {}

        try:
            cfg = self._get_config()
            max_workers = self._max_workers(cfg)
            ex = ThreadPoolExecutor(max_workers=max_workers)

            while not self._stop.is_set():
                if self._pause.is_set():
                    time.sleep(0.1)
                    continue

                cfg = self._get_config()
                desired_workers = self._desired_workers(cfg)
                pending = pick_pending()

                while pending and len(fut_to_item) < desired_workers and not self._stop.is_set() and not self._pause.is_set():
                    item = pending.pop(0)
                    with self._lock:
                        item.status = "processing"
                        item.error_message = None
                        item.output_paths = []
                    self._on_queue_update()
                    fut = ex.submit(generator.generate, item.path, cancel_event=self._stop)
                    fut_to_item[fut] = item

                if not fut_to_item:
                    if not pending:
                        break
                    time.sleep(0.1)
                    continue

                done, _ = wait(set(fut_to_item.keys()), timeout=0.2, return_when=FIRST_COMPLETED)
                for fut in done:
                    item = fut_to_item.pop(fut)
                    try:
                        res = fut.result()
                        with self._lock:
                            item.status = "completed"
                            item.output_paths = res.output_paths
                        consecutive_comfyui_failures = 0
                    except OutpaintSkipped as e:
                        with self._lock:
                            item.status = "skipped"
                            item.error_message = str(e)
                            item.output_paths = list(e.output_paths)
                        consecutive_comfyui_failures = 0
                    except CancelledError:
                        with self._lock:
                            item.status = "skipped"
                            item.error_message = "Cancelled"
                        consecutive_comfyui_failures = 0
                    except Exception as e:
                        with self._lock:
                            item.status = "failed"
                            item.error_message = str(e)
                        cfg = self._get_config()
                        if cfg.get("backend") == "comfyui":
                            consecutive_comfyui_failures += 1
                        else:
                            consecutive_comfyui_failures = 0

                    self._on_queue_update()
                    self._on_item_complete(item)

                    # Fallback prompt after 3 consecutive comfyui failures
                    cfg = self._get_config()
                    if cfg.get("backend") == "comfyui" and consecutive_comfyui_failures >= 3:
                        remaining = len(pick_pending()) + len(fut_to_item)
                        new_gen = self._fallback_switch(remaining)
                        if new_gen is not None:
                            generator = new_gen
                            consecutive_comfyui_failures = 0
                        else:
                            consecutive_comfyui_failures = 0

        finally:
            # Mark any in-flight items as stopped so UI doesn't stay stuck in "processing"
            if self._stop.is_set() and fut_to_item:
                with self._lock:
                    for item in fut_to_item.values():
                        if item.status == "processing":
                            item.status = "skipped"
                            item.error_message = "Stopped"
                self._on_queue_update()

            for fut in list(fut_to_item.keys()):
                fut.cancel()

            if ex is not None:
                ex.shutdown(wait=False, cancel_futures=True)

            self.is_running = False
            self.is_paused = False
            self._on_queue_update()
