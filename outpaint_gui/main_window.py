from __future__ import annotations

import json
import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

import tkinter as tk
from tkinter import filedialog, messagebox

from path_utils import get_log_path
from outpaint_diagnostics import run_diagnostics
from outpaint_generator import (
    OutpaintGenerator,
    _deep_merge,
    default_config_dict,
    iter_image_files_in_folder,
    load_outpaint_config,
    save_config_file,
)

from .config_panel import ConfigPanel
from .drop_zone import DropZone, create_dnd_root
from .log_display import LogDisplay
from .queue_manager import QueueItem, QueueManager


COLORS = {
    "bg_main": "#2D2D30",
    "bg_panel": "#3C3C41",
    "bg_input": "#464649",
    "text_light": "#DCDCDC",
    "accent_blue": "#6496FF",
    "btn_green": "#329632",
    "btn_red": "#B43232",
}


class OutpaintGUIWindow:
    def __init__(self, *, config_path: str):
        self.config_path = config_path
        self.root = create_dnd_root()
        self.root.title("fal.ai Image Outpainting Tool")
        self.root.configure(bg=COLORS["bg_main"])

        self._setup_logging()

        base = default_config_dict()
        loaded: dict[str, Any] = {}
        try:
            p = Path(config_path)
            if p.exists():
                loaded = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        self.config: dict[str, Any] = _deep_merge(base, loaded or {})

        self.generator: Optional[OutpaintGenerator] = None
        self._save_timer: Optional[str] = None  # For debounced auto-save

        self._build_ui()

        self.queue_manager = QueueManager(
            config_getter=self._get_config_snapshot,
            log_callback=self._log,
            queue_update_callback=self._refresh_queue,
            processing_complete_callback=self._on_item_complete,
            fallback_switch_callback=self._fallback_switch,
        )
        self._refresh_queue()

        self._install_menu()
        self._maybe_run_first_diagnostics()

    def _setup_logging(self) -> None:
        log_path = get_log_path("outpaint_gui.log")
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        for h in list(root_logger.handlers):
            if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_path):
                return

        handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_logger.addHandler(handler)

    def _build_ui(self) -> None:
        self.root.geometry("1000x900")
        self.root.minsize(860, 720)

        # Main horizontal PanedWindow (config panel | main area)
        self.main_paned = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            bg=COLORS["bg_main"],
            sashrelief=tk.RAISED,
            opaqueresize=False
        )
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # Left pane - Config Panel
        left_container = tk.Frame(self.main_paned, bg=COLORS["bg_panel"])
        self.config_panel = ConfigPanel(
            left_container,
            initial_config=self.config,
            on_config_changed=self._on_config_changed,
            on_test_backend=self._test_backend,
            on_save_config=self._save_config,
        )
        self.config_panel.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.main_paned.add(left_container, minsize=300, width=self.config.get("sash_left_right", 380))

        # Right pane - Vertical PanedWindow (drop zone + queue | log)
        self.right_paned = tk.PanedWindow(
            self.main_paned,
            orient=tk.VERTICAL,
            sashwidth=5,
            bg=COLORS["bg_main"],
            sashrelief=tk.RAISED,
            opaqueresize=False
        )
        self.main_paned.add(self.right_paned, minsize=400)

        # Top section of right pane (drop zone + queue)
        top_container = tk.Frame(self.right_paned, bg=COLORS["bg_main"])

        self.drop_zone = DropZone(top_container, on_files_dropped=self._on_files_dropped, on_folder_dropped=self._on_folder_dropped)
        self.drop_zone.pack(fill=tk.BOTH, expand=False, padx=10, pady=(10, 5))

        queue_frame = tk.Frame(top_container, bg=COLORS["bg_panel"])
        queue_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(queue_frame, text="QUEUE", font=("Segoe UI", 10, "bold"), bg=COLORS["bg_panel"], fg=COLORS["text_light"]).pack(
            anchor="w", padx=10, pady=(8, 4)
        )

        self.queue_list = tk.Listbox(
            queue_frame,
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            font=("Consolas", 9),
            selectbackground=COLORS["accent_blue"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.queue_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        btns = tk.Frame(queue_frame, bg=COLORS["bg_panel"])
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))

        tk.Button(btns, text="Start", bg=COLORS["btn_green"], fg="white", font=("Segoe UI", 10, "bold"), command=self._start).pack(
            side=tk.LEFT
        )
        tk.Button(btns, text="Pause", bg=COLORS["bg_input"], fg=COLORS["text_light"], font=("Segoe UI", 10), command=self._toggle_pause).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(btns, text="Stop", bg=COLORS["btn_red"], fg="white", font=("Segoe UI", 10, "bold"), command=self._stop).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(btns, text="Clear", bg=COLORS["bg_input"], fg=COLORS["text_light"], font=("Segoe UI", 10), command=self._clear_queue).pack(
            side=tk.RIGHT
        )
        tk.Button(btns, text="Add Files…", bg=COLORS["bg_input"], fg=COLORS["text_light"], font=("Segoe UI", 10), command=self._browse_files).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        # Add top container to right paned
        self.right_paned.add(top_container, minsize=300)

        # Bottom section of right pane (log display)
        log_container = tk.Frame(self.right_paned, bg=COLORS["bg_main"])
        self.log_display = LogDisplay(log_container)
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Add log container to right paned with minimum height
        self.right_paned.add(log_container, minsize=100)

        # Restore sash positions after widgets are added
        self.root.after(100, self._restore_sash_positions)

        # Bind sash movement to save positions
        self.main_paned.bind("<ButtonRelease-1>", lambda e: self._on_sash_moved())
        self.right_paned.bind("<ButtonRelease-1>", lambda e: self._on_sash_moved())

    def _install_menu(self) -> None:
        menu = tk.Menu(self.root)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="Run diagnostics…", command=lambda: self._run_diagnostics(force=True))
        menu.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menu)

    def _maybe_run_first_diagnostics(self) -> None:
        if bool(self.config.get("diagnostics_run")):
            return
        self.root.after(250, lambda: self._run_diagnostics(force=False))

    def _run_diagnostics(self, *, force: bool) -> None:
        report, _ok = run_diagnostics(self._get_config_snapshot())
        messagebox.showinfo("System diagnostics", report)

        if not force:
            self.config = {**self.config, "diagnostics_run": True}
            save_config_file(self.config_path, self.config)

    def _log(self, message: str, level: str = "info") -> None:
        self.root.after(0, lambda: self.log_display.log(message, level))

    def _on_config_changed(self, cfg: dict[str, Any]) -> None:
        # Preserve non-UI config keys (workers, diagnostics_run, etc.)
        self.config = {**self.config, **cfg}
        # Auto-save with 2-second debounce
        self._schedule_auto_save()

    def _get_config_snapshot(self) -> dict[str, Any]:
        return dict(self.config)

    def _save_config(self) -> None:
        """Save current config to disk and show confirmation."""
        try:
            save_config_file(self.config_path, self.config)
            self._log("✓ Settings saved successfully", "success")
            messagebox.showinfo("Settings Saved", "Configuration has been saved successfully!")
        except Exception as e:
            self._log(f"✗ Failed to save settings: {e}", "error")
            messagebox.showerror("Save Failed", f"Failed to save configuration:\n{e}")

    def _schedule_auto_save(self) -> None:
        """Schedule auto-save with 2-second debounce to avoid excessive writes."""
        if self._save_timer:
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(2000, self._auto_save)

    def _auto_save(self) -> None:
        """Auto-save config without showing confirmation dialog."""
        try:
            save_config_file(self.config_path, self.config)
            self._log("✓ Settings auto-saved", "info")
        except Exception as e:
            self._log(f"✗ Auto-save failed: {e}", "error")
        finally:
            self._save_timer = None

    def _restore_sash_positions(self) -> None:
        """Restore saved sash positions from config."""
        try:
            # Restore horizontal split (left/right)
            left_right_pos = self.config.get("sash_left_right", 380)
            self.main_paned.sash_place(0, left_right_pos, 0)

            # Restore vertical split (queue/log)
            queue_log_pos = self.config.get("sash_queue_log", 600)
            self.right_paned.sash_place(0, 0, queue_log_pos)

            self._log(f"Restored sash positions: left={left_right_pos}px, queue={queue_log_pos}px", "info")
        except Exception as e:
            self._log(f"Failed to restore sash positions: {e}", "warning")

    def _on_sash_moved(self) -> None:
        """Save sash positions when user drags dividers."""
        try:
            # Get current positions (horizontal paned uses x, vertical paned uses y)
            left_right_pos, _ = self.main_paned.sash_coord(0)
            _, queue_log_pos = self.right_paned.sash_coord(0)

            # Update config
            self.config["sash_left_right"] = left_right_pos
            self.config["sash_queue_log"] = queue_log_pos

            # Auto-save with debounce
            self._schedule_auto_save()
        except Exception:
            pass  # Ignore errors during sash movement

    def _browse_files(self) -> None:
        filetypes = [("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif"), ("All files", "*.*")]
        files = filedialog.askopenfilenames(title="Select Images", filetypes=filetypes)
        if files:
            self._on_files_dropped(list(files))

    def _on_files_dropped(self, file_paths: list[str]) -> None:
        self.queue_manager.add_files(file_paths)

    def _on_folder_dropped(self, folder_path: str) -> None:
        files = list(iter_image_files_in_folder(folder_path))
        if not files:
            messagebox.showinfo("No images", "No supported images found in folder")
            return
        if messagebox.askyesno("Add folder", f"Add {len(files)} images from folder to queue?"):
            self.queue_manager.add_files(files)

    def _refresh_queue(self) -> None:
        def _do() -> None:
            self.queue_list.delete(0, tk.END)
            for item in self.queue_manager.get_items():
                name = os.path.basename(item.path)
                extra = ""
                if item.status == "completed" and item.output_paths:
                    extra = f" → {len(item.output_paths)} output(s)"
                if item.status == "failed" and item.error_message:
                    extra = f" • {item.error_message}"
                self.queue_list.insert(tk.END, f"[{item.status}] {name}{extra}")

        self.root.after(0, _do)

    def _validate_and_build_generator(self) -> Optional[OutpaintGenerator]:
        try:
            save_config_file(self.config_path, self.config)
        except Exception as e:
            messagebox.showerror("Cannot save config", str(e))
            return None

        try:
            cfg, errors, _merged = load_outpaint_config(self.config_path)
        except Exception as e:
            messagebox.showerror("Cannot load config", str(e))
            return None

        if errors or cfg is None:
            messagebox.showerror("Configuration error", "\n\n".join(errors) if errors else "Invalid configuration")
            return None
        gen = OutpaintGenerator(cfg)
        gen.set_progress_callback(self._log)
        return gen

    def _test_backend(self) -> None:
        gen = self._validate_and_build_generator()
        if not gen:
            return
        ok, msg = gen.check_backend_available()
        if ok:
            messagebox.showinfo("Backend OK", msg)
        else:
            messagebox.showwarning("Backend not ready", msg)

    def _start(self) -> None:
        gen = self._validate_and_build_generator()
        if not gen:
            return
        self.generator = gen
        self.queue_manager.start(gen)

    def _toggle_pause(self) -> None:
        if self.queue_manager.is_paused:
            self.queue_manager.resume()
            self._log("Resumed", "info")
        else:
            self.queue_manager.pause()
            self._log("Paused", "warning")

    def _stop(self) -> None:
        self.queue_manager.stop()
        self._log("Stopped", "warning")

    def _clear_queue(self) -> None:
        self.queue_manager.clear()

    def _on_item_complete(self, item: QueueItem) -> None:
        if item.status == "completed":
            self._log(f"✓ Completed: {os.path.basename(item.path)}", "success")
        elif item.status == "skipped":
            extra = f" • {item.error_message}" if item.error_message else ""
            self._log(f"↷ Skipped: {os.path.basename(item.path)}{extra}", "warning")
        elif item.status == "failed":
            self._log(f"✗ Failed: {os.path.basename(item.path)} • {item.error_message}", "error")

    def _fallback_switch(self, remaining: int) -> Optional[OutpaintGenerator]:
        done = threading.Event()
        result: dict[str, Optional[OutpaintGenerator]] = {"gen": None}

        def on_main() -> None:
            try:
                ok = messagebox.askyesno(
                    "ComfyUI repeatedly failed",
                    f"ComfyUI failed 3 times in a row. Switch to fal.ai for remaining {remaining} items?",
                )
                if not ok:
                    return

                self.config = {**self.config, "backend": "falai"}
                gen = self._validate_and_build_generator()
                if gen:
                    self._log("Switched backend to fal.ai", "warning")
                    result["gen"] = gen
            finally:
                done.set()

        self.root.after(0, on_main)
        done.wait()
        return result["gen"]

    def run(self) -> None:
        self.root.mainloop()


def launch_gui(*, config_path: str) -> None:
    OutpaintGUIWindow(config_path=config_path).run()
