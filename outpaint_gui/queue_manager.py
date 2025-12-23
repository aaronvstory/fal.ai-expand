"""
Queue Manager - Thread-safe queue for processing images with status tracking.
"""

import threading
import os
from dataclasses import dataclass, field
from typing import Callable, Optional, List
from pathlib import Path


VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff', '.tif'}


def get_output_video_path(image_path: str, output_folder: str) -> Path:
    """Get the default output video path for an image."""
    image_name = Path(image_path).stem
    return Path(output_folder) / f"{image_name}_kling.mp4"


def check_video_exists(image_path: str, output_folder: str) -> bool:
    """
    Check if a video already exists for this image.

    We treat either the base render or its looped sibling as "exists" to
    avoid overwriting/deleting a looped-only output.
    """
    base_path = get_output_video_path(image_path, output_folder)
    loop_path = base_path.with_name(f"{base_path.stem}_looped{base_path.suffix}")
    return base_path.exists() or loop_path.exists()


def get_next_available_path(image_path: str, output_folder: str) -> Path:
    """
    Find the next available filename with increment suffix.

    Examples:
        selfie_kling.mp4 exists -> returns selfie_kling_2.mp4
        selfie_kling_2.mp4 exists -> returns selfie_kling_3.mp4
    """
    image_name = Path(image_path).stem
    counter = 1

    while True:
        suffix = "" if counter == 1 else f"_{counter}"
        candidate = Path(output_folder) / f"{image_name}_kling{suffix}.mp4"
        candidate_loop = Path(output_folder) / f"{image_name}_kling{suffix}_looped.mp4"

        # Return first gap where neither base nor looped variant exists
        if not candidate.exists() and not candidate_loop.exists():
            return candidate

        counter += 1
        if counter > 999:  # Safety limit
            raise ValueError(f"Too many versions of {image_name}_kling.mp4")


@dataclass
class QueueItem:
    """Represents a single queued image with status tracking."""
    path: str
    status: str = "pending"  # "pending", "processing", "completed", "failed"
    error_message: Optional[str] = None
    output_path: Optional[str] = None

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def source_folder(self) -> str:
        return os.path.dirname(self.path)


class QueueManager:
    """Thread-safe queue manager for image processing."""

    MAX_QUEUE_SIZE = 50

    def __init__(
        self,
        generator,
        config_getter: Callable[[], dict],
        log_callback: Callable[[str, str], None],
        queue_update_callback: Callable[[], None],
        processing_complete_callback: Callable[[QueueItem], None] = None
    ):
        """
        Initialize the queue manager.

        Args:
            generator: FalAIKlingGenerator instance
            config_getter: Function that returns current config dict
            log_callback: Function(message, level) for logging
            queue_update_callback: Function called when queue changes
            processing_complete_callback: Function called when an item finishes
        """
        self.items: List[QueueItem] = []
        self.lock = threading.Lock()
        self.generator = generator
        self.get_config = config_getter
        self.log = log_callback
        self.update_queue_display = queue_update_callback
        self.on_processing_complete = processing_complete_callback

        self.is_paused = False
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self._stop_flag = False

    def log_verbose(self, message: str, level: str = "info"):
        """Log a message only if verbose mode is enabled."""
        config = self.get_config()
        if config.get("verbose_gui_mode", False):
            self.log(message, level)

    def validate_file(self, file_path: str) -> tuple:
        """
        Validate a file for processing.

        Returns:
            (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in VALID_EXTENSIONS:
            return False, f"Unsupported format: {ext}"

        # Check if already in queue
        with self.lock:
            for item in self.items:
                if item.path == file_path and item.status in ("pending", "processing"):
                    return False, "Already in queue"

        return True, ""

    def add_to_queue(self, file_path: str) -> tuple:
        """
        Add a file to the processing queue.

        Returns:
            (success, message)
        """
        # Validate file
        is_valid, error = self.validate_file(file_path)
        if not is_valid:
            return False, error

        with self.lock:
            # Check queue limit
            pending_count = sum(1 for item in self.items if item.status in ("pending", "processing"))
            if pending_count >= self.MAX_QUEUE_SIZE:
                return False, f"Queue full ({self.MAX_QUEUE_SIZE} items max)"

            # Add to queue
            item = QueueItem(path=file_path)
            self.items.append(item)

        self.update_queue_display()
        self.log(f"Added to queue: {os.path.basename(file_path)}", "info")

        # Start processing if not already running
        if not self.is_running and not self.is_paused:
            self.start_processing()

        return True, "Added to queue"

    def start_processing(self):
        """Start the worker thread to process queue items."""
        if self.is_running:
            return

        self._stop_flag = False
        self.is_running = True
        self.is_paused = False
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        self.log("Processing started", "info")

    def pause_processing(self):
        """Pause processing after current item completes."""
        self.is_paused = True
        self.log("Processing paused", "warning")

    def resume_processing(self):
        """Resume processing."""
        self.is_paused = False
        if not self.is_running:
            self.start_processing()
        else:
            self.log("Processing resumed", "info")

    def stop_processing(self):
        """Stop processing completely."""
        self._stop_flag = True
        self.is_paused = True

    def retry_failed(self):
        """Re-queue all failed items."""
        count = 0
        with self.lock:
            for item in self.items:
                if item.status == "failed":
                    item.status = "pending"
                    item.error_message = None
                    count += 1

        if count > 0:
            self.update_queue_display()
            self.log(f"Retrying {count} failed item(s)", "info")
            if not self.is_running and not self.is_paused:
                self.start_processing()
        return count

    def clear_queue(self):
        """Remove all pending and failed items from queue."""
        with self.lock:
            self.items = [item for item in self.items if item.status in ("processing", "completed")]
        self.update_queue_display()
        self.log("Queue cleared", "info")

    def remove_item(self, index: int):
        """Remove a specific item by index."""
        with self.lock:
            if 0 <= index < len(self.items):
                item = self.items[index]
                if item.status not in ("processing",):
                    self.items.pop(index)
                    self.update_queue_display()
                    return True
        return False

    def get_items(self) -> List[QueueItem]:
        """Get a copy of all queue items."""
        with self.lock:
            return list(self.items)

    def get_pending_count(self) -> int:
        """Get count of pending items."""
        with self.lock:
            return sum(1 for item in self.items if item.status == "pending")

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with self.lock:
            return {
                "pending": sum(1 for item in self.items if item.status == "pending"),
                "processing": sum(1 for item in self.items if item.status == "processing"),
                "completed": sum(1 for item in self.items if item.status == "completed"),
                "failed": sum(1 for item in self.items if item.status == "failed"),
                "total": len(self.items)
            }

    def _get_next_pending(self) -> Optional[QueueItem]:
        """Get next pending item and mark it as processing."""
        with self.lock:
            for item in self.items:
                if item.status == "pending":
                    item.status = "processing"
                    return item
        return None

    def _process_queue(self):
        """Worker thread that processes queue items."""
        while not self._stop_flag:
            # Check if paused
            if self.is_paused:
                self.is_running = False
                return

            # Get next item
            item = self._get_next_pending()
            if item is None:
                # No more items to process
                self.is_running = False
                self.log("Queue processing complete", "success")
                return

            self.update_queue_display()
            self.log(f"Processing: {item.filename}", "info")

            try:
                # Get current config
                config = self.get_config()
                use_source_folder = config.get("use_source_folder", True)
                output_folder = config.get("output_folder", "")
                prompt = self._get_current_prompt(config)
                negative_prompt = self._get_current_negative_prompt(config)
                allow_reprocess = config.get("allow_reprocess", False)
                reprocess_mode = config.get("reprocess_mode", "increment")

                # Verbose: Show configuration being used
                self.log_verbose(f"  Model: {self.generator.model_display_name}", "api")
                self.log_verbose(f"  Duration: {config.get('video_duration', 10)}s", "debug")
                if prompt:
                    prompt_preview = prompt[:60] + "..." if len(prompt) > 60 else prompt
                    self.log_verbose(f"  Prompt: {prompt_preview}", "debug")

                # Determine output folder
                if use_source_folder:
                    actual_output = item.source_folder
                    self.log_verbose(f"  Output: source folder", "debug")
                elif not output_folder or not os.path.isdir(output_folder):
                    # Custom folder selected but not set or invalid - use source folder
                    actual_output = item.source_folder
                    self.log(f"No valid output folder set - saving to source folder", "warning")
                else:
                    actual_output = output_folder
                    self.log_verbose(f"  Output: {actual_output}", "debug")

                # Check if video already exists
                video_exists = check_video_exists(item.path, actual_output)
                custom_output_path = None

                if video_exists:
                    if not allow_reprocess:
                        # Reprocessing disabled - fail with clear message
                        existing_path = get_output_video_path(item.path, actual_output)
                        item.status = "failed"
                        item.error_message = f"Video already exists: {existing_path.name}. Enable 'Allow reprocessing' to regenerate."
                        self.log(f"Skipped: {item.filename} - video already exists", "warning")
                        self.log(f"  Existing: {existing_path}", "info")
                        self.log(f"  Enable 'Allow reprocessing' to regenerate", "info")
                        self.update_queue_display()
                        if self.on_processing_complete:
                            self.on_processing_complete(item)
                        continue

                    elif reprocess_mode == "overwrite":
                        # Overwrite mode - delete existing file
                        existing_path = get_output_video_path(item.path, actual_output)
                        try:
                            existing_path.unlink()
                            self.log(f"Deleted existing: {existing_path.name}", "warning")
                        except Exception as e:
                            self.log(f"Could not delete existing file: {e}", "error")
                            item.status = "failed"
                            item.error_message = f"Could not delete existing file: {e}"
                            self.update_queue_display()
                            if self.on_processing_complete:
                                self.on_processing_complete(item)
                            continue

                    elif reprocess_mode == "increment":
                        # Increment mode - find next available filename
                        try:
                            next_path = get_next_available_path(item.path, actual_output)
                            custom_output_path = str(next_path)
                            self.log(f"Will save as: {next_path.name} (incremented)", "info")
                        except ValueError as e:
                            item.status = "failed"
                            item.error_message = str(e)
                            self.log(f"Error: {e}", "error")
                            self.update_queue_display()
                            if self.on_processing_complete:
                                self.on_processing_complete(item)
                            continue

                # Process the image
                # Skip duplicate check if we've already handled it (overwrite mode deleted file,
                # increment mode uses custom path)
                skip_check = video_exists and reprocess_mode == "overwrite"
                result = self._generate_video(
                    item, actual_output, prompt, negative_prompt, use_source_folder, custom_output_path,
                    skip_duplicate_check=skip_check
                )

                if result:
                    item.status = "completed"
                    item.output_path = result
                    self.log(f"Completed: {item.filename}", "success")
                    self.log(f"Saved to: {result}", "info")

                    # Check if loop video is enabled
                    if config.get("loop_videos", False):
                        self._loop_video(result, item)
                else:
                    item.status = "failed"
                    item.error_message = "Generation failed"
                    self.log(f"Failed: {item.filename}", "error")

            except Exception as e:
                item.status = "failed"
                item.error_message = str(e)
                self.log(f"Error processing {item.filename}: {e}", "error")

            self.update_queue_display()

            if self.on_processing_complete:
                self.on_processing_complete(item)

        self.is_running = False

    def _generate_video(
        self,
        item: QueueItem,
        output_folder: str,
        prompt: str,
        negative_prompt: str,
        use_source_folder: bool,
        custom_output_path: Optional[str] = None,
        skip_duplicate_check: bool = False
    ) -> Optional[str]:
        """
        Generate video using the generator.

        Args:
            item: Queue item being processed
            output_folder: Output folder path
            prompt: Generation prompt
            negative_prompt: Negative prompt (optional, model-dependent)
            use_source_folder: Whether to save to source folder
            custom_output_path: Optional custom output path (for increment mode)
            skip_duplicate_check: Whether to skip duplicate detection

        Returns:
            Output path on success, None on failure
        """
        # Respect model capability: if not supported, drop negative_prompt
        supports_negative = self.get_config().get("model_capabilities", {}).get(
            self.generator.base_url.replace("https://queue.fal.run/", ""), False
        )
        neg_for_payload = negative_prompt if supports_negative else None

        # Set up verbose callback for generator progress
        def progress_callback(message: str, level: str = "info"):
            self.log_verbose(message, level)

        # Attach callback to generator if verbose mode
        config = self.get_config()
        if config.get("verbose_gui_mode", False):
            self.generator.set_progress_callback(progress_callback)
        else:
            self.generator.set_progress_callback(None)

        # For increment mode, we need to handle the output path ourselves
        if custom_output_path:
            # Generate with skip_duplicate_check since we've already handled it
            result = self.generator.create_kling_generation(
                character_image_path=item.path,
                output_folder=output_folder,
                custom_prompt=prompt,
                negative_prompt=neg_for_payload,
                use_source_folder=use_source_folder,
                skip_duplicate_check=True  # We've already handled duplicate check
            )

            if result and custom_output_path != result:
                # Rename to custom path (incremented filename)
                try:
                    import shutil
                    shutil.move(result, custom_output_path)
                    return custom_output_path
                except Exception as e:
                    self.log(f"Could not rename output: {e}", "warning")
                    return result  # Return original path if rename fails

            return result
        else:
            # Normal generation
            return self.generator.create_kling_generation(
                character_image_path=item.path,
                output_folder=output_folder,
                custom_prompt=prompt,
                negative_prompt=neg_for_payload,
                use_source_folder=use_source_folder,
                skip_duplicate_check=skip_duplicate_check
            )

    def _loop_video(self, video_path: str, item: QueueItem):
        """
        Create a looped version of the generated video.

        Args:
            video_path: Path to the generated video
            item: Queue item being processed
        """
        try:
            from .video_looper import create_looped_video

            self.log(f"Creating looped video...", "info")

            # Create looped version (adds _looped suffix)
            looped_path = create_looped_video(
                input_path=video_path,
                suffix="_looped",
                overwrite=True,
                log_callback=self.log
            )

            if looped_path:
                self.log(f"Looped video saved: {os.path.basename(looped_path)}", "success")
            else:
                self.log(f"Failed to create looped video", "warning")

        except ImportError:
            self.log("Video looper module not available", "warning")
        except Exception as e:
            self.log(f"Error creating looped video: {e}", "warning")

    def _get_current_prompt(self, config: dict) -> str:
        """Get the current prompt from config."""
        slot = config.get("current_prompt_slot", 1)
        saved_prompts = config.get("saved_prompts", {})
        return saved_prompts.get(str(slot), "") or ""

    def _get_current_negative_prompt(self, config: dict) -> str:
        """Get current negative prompt from config."""
        slot = config.get("current_prompt_slot", 1)
        saved = config.get("negative_prompts", {})
        return saved.get(str(slot), "") or ""
