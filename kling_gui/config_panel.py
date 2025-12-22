"""
Config Panel Widget - Model selection, output mode, and prompt editing.
With dynamic model fetching from fal.ai API.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional, List, Dict
import threading
import time
import os
import re
import logging


# Color palette
COLORS = {
    "bg_main": "#2D2D30",
    "bg_panel": "#3C3C41",
    "bg_input": "#464649",
    "text_light": "#DCDCDC",
    "text_dim": "#B4B4B4",
    "accent_blue": "#6496FF",
    "border": "#5A5A5E",
    "warning": "#FFB347",
    "success": "#64FF64",
    "error": "#FF6464",
}

# Minimal fallback - ONLY used when API fails AND no cache exists
# Models change frequently - this is just a safety net with user's preferred model
# The app dynamically fetches all available models from fal.ai API
FALLBACK_MODELS = [
    {"name": "Kling V2.5 Turbo Pro", "endpoint": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video", "duration": 10},
]

# fal.ai URLs for model browsing and API reference
FAL_MODELS_URL = "https://fal.ai/models?categories=image-to-video"
FAL_EXPLORE_URL = "https://fal.ai/explore/models"
FAL_API_DOCS_URL = "https://docs.fal.ai"

# Vague model names that should be replaced with parsed endpoint names
# Using frozenset for O(1) lookup performance
VAGUE_MODEL_NAMES = frozenset(['kling video', 'pixverse', 'wan effects', 'longcat video', 'pika'])

# Precompiled regex patterns for word-boundary matching of vague names
# Compiled once at module load to avoid per-call compilation overhead
# Pattern: (?<!\w)name(?!\w) matches 'name' only when not surrounded by word characters
# e.g., 'pika' matches "Pika Video" but NOT "Pikachu Model"
VAGUE_MODEL_PATTERNS = {
    name: re.compile(rf'(?<!\w){re.escape(name)}(?!\w)', re.IGNORECASE)
    for name in VAGUE_MODEL_NAMES
}

# UI Configuration
COMBOBOX_DROPDOWN_HEIGHT = 25  # Number of items visible in dropdown (default ~10)

# Module logger
logger = logging.getLogger(__name__)


def parse_endpoint_to_display_name(endpoint_id: str) -> str:
    """
    Parse fal.ai endpoint ID into a human-readable display name.

    Examples:
        fal-ai/kling-video/v2.5-turbo/pro/image-to-video → Kling v2.5 Turbo Pro
        fal-ai/kling-video/v2.6/pro/image-to-video → Kling v2.6 Pro
        fal-ai/veo3.1/image-to-video → Veo 3.1
        fal-ai/sora-2/image-to-video → Sora 2
    """
    if not endpoint_id:
        return "Unknown"

    # Remove common prefixes/suffixes
    parts = endpoint_id.replace("fal-ai/", "").replace("/image-to-video", "").replace("/video-to-video", "")

    # Split by / to get components
    components = [p for p in parts.split("/") if p]

    if not components:
        return endpoint_id

    # Build display name from components
    display_parts = []
    for comp in components:
        # Clean up component
        comp = comp.replace("-", " ").replace("_", " ")
        # Capitalize properly
        if comp.startswith("v") and any(c.isdigit() for c in comp):
            # Version number: v2.5-turbo → v2.5 Turbo
            display_parts.append(comp.replace(" ", "-").title().replace("-", " "))
        else:
            display_parts.append(comp.title())

    result = " ".join(display_parts)

    # Clean up common patterns
    result = result.replace("Kling Video", "Kling")
    result = result.replace("  ", " ")

    return result.strip()


class ModelFetcher:
    """Fetches available models from fal.ai API dynamically."""

    CACHE_TTL = 3600  # 1 hour cache (models don't change that often)

    @staticmethod
    def fetch_models(api_key: str, callback: Callable[[List[Dict], Optional[str]], None]):
        """
        Fetch models in a background thread.

        Args:
            api_key: fal.ai API key
            callback: Called with (models_list, error_message) when done
        """
        def _fetch():
            try:
                import requests
                headers = {"Authorization": f"Key {api_key}"}
                all_models = []
                cursor = None

                # Paginate through all results
                while True:
                    params = {"category": "image-to-video", "status": "active", "limit": 50}
                    if cursor:
                        params["cursor"] = cursor

                    response = requests.get(
                        "https://api.fal.ai/v1/models",
                        params=params,
                        headers=headers,
                        timeout=15
                    )

                    if response.status_code != 200:
                        # Log detail for debugging but don't expose to user (may contain sensitive info)
                        detail = response.text[:200] if response.text else ""
                        logger.debug("Fal API error %s: %s", response.status_code, detail)
                        callback([], f"API error {response.status_code}")
                        return

                    data = response.json()
                    for m in data.get("models", []):
                        endpoint_id = m.get("endpoint_id", "")
                        metadata = m.get("metadata", {})
                        api_display_name = metadata.get("display_name", "")

                        # Smart display name selection:
                        # 1. Check if API name is too vague (known problematic names)
                        # 2. Check if API name has version info (v2.5, 2.1, etc.)
                        # 3. If endpoint has version but API name doesn't, use parsed name
                        # Normalize for fuzzy checks (convert hyphens/underscores to spaces)
                        name_for_match = re.sub(r'[-_]+', ' ', api_display_name).strip()

                        # Check if name matches a known vague pattern using precompiled regexes
                        # Patterns use word-boundary matching to avoid false positives
                        # e.g., 'pika' matches 'Pika Video' but not 'Pikachu Model'
                        is_vague = any(
                            pattern.search(name_for_match)
                            for pattern in VAGUE_MODEL_PATTERNS.values()
                        )

                        # Check if name has version info (v2, v2.5, 2.1, 1.6, etc.)
                        # Match: "v" followed by digits, OR digits with decimal (not "Video 01")
                        has_version_in_name = bool(
                            re.search(r'\bv\d+(?:\.\d+)?', api_display_name, re.IGNORECASE) or
                            re.search(r'\b\d+\.\d+\b', api_display_name)  # Like "2.1" or "1.6"
                        )

                        # Check if endpoint has version info
                        has_version_in_endpoint = bool(re.search(r'/v\d+\.?\d*', endpoint_id))

                        # Use parsed name if: no API name, vague name, or endpoint has version but name doesn't
                        if not api_display_name or is_vague or (has_version_in_endpoint and not has_version_in_name):
                            display_name = parse_endpoint_to_display_name(endpoint_id)
                        else:
                            display_name = api_display_name

                        all_models.append({
                            "name": display_name,
                            "endpoint": endpoint_id,
                            "duration": metadata.get("duration_estimate", 10),
                            "description": metadata.get("description", "")[:100],
                        })

                    # Check for more pages
                    if data.get("has_more") and data.get("next_cursor"):
                        cursor = data["next_cursor"]
                    else:
                        break

                if all_models:
                    # Sort models: Kling first, then other popular models, then rest alphabetically
                    def sort_key(m):
                        name_lower = m["name"].lower()
                        endpoint_lower = m["endpoint"].lower()
                        # Priority tiers
                        if "kling" in name_lower or "kling" in endpoint_lower:
                            # Further sort Kling by version (higher versions first)
                            if "v2.6" in endpoint_lower:
                                return (0, 0, name_lower)
                            elif "v2.5" in endpoint_lower:
                                if "turbo" in endpoint_lower:
                                    return (0, 1, name_lower)
                                else:
                                    return (0, 2, name_lower)
                            else:
                                return (0, 9, name_lower)
                        elif "veo" in name_lower or "sora" in name_lower:
                            return (1, 0, name_lower)
                        elif "ltx" in name_lower or "pixverse" in name_lower:
                            return (2, 0, name_lower)
                        else:
                            return (3, 0, name_lower)

                    all_models.sort(key=sort_key)
                    callback(all_models, None)
                else:
                    callback([], "No models found")

            except Exception as e:
                callback([], str(e))

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

    @staticmethod
    def get_cached_or_fallback(config: dict) -> List[Dict]:
        """Get cached models or fallback list."""
        cached = config.get("cached_models", {})
        cached_list = cached.get("models", [])
        cached_time = cached.get("timestamp", 0)

        # If cache exists, use it (even if stale - background refresh will update)
        # Only fall back if no cached models at all
        if cached_list:
            return cached_list

        return FALLBACK_MODELS

    @staticmethod
    def cache_models(config: dict, models: List[Dict]):
        """Save models to config cache."""
        config["cached_models"] = {
            "models": models,
            "timestamp": time.time()
        }


class ConfigPanel(tk.Frame):
    """Configuration panel for model, output, and prompt settings."""

    def __init__(
        self,
        parent,
        config: dict,
        on_config_changed: Callable[[dict], None],
        **kwargs
    ):
        """
        Initialize the config panel.

        Args:
            parent: Parent widget
            config: Current configuration dict
            on_config_changed: Callback when config changes
        """
        super().__init__(parent, bg=COLORS["bg_panel"], **kwargs)
        self.config = config
        self.on_config_changed = on_config_changed

        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        """Set up the configuration UI."""
        # Header
        header = tk.Label(
            self,
            text="⚙ CONFIGURATION",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"]
        )
        header.pack(fill=tk.X, padx=10, pady=(5, 10))

        # Main config frame
        config_frame = tk.Frame(self, bg=COLORS["bg_input"], padx=10, pady=10)
        config_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Row 1: Model selection
        row1 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row1.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            row1,
            text="Model:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        # Display model name from CLI config (read-only)
        model_name = self.config.get("model_display_name", "Kling 2.5 Turbo Pro")
        self.model_label = tk.Label(
            row1,
            text=model_name,
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["bg_main"],
            fg=COLORS["accent_blue"],
            padx=10,
            pady=4,
            anchor="w",
            width=35
        )
        self.model_label.pack(side=tk.LEFT, padx=(5, 10))

        # Duration and price labels
        self.duration_label = tk.Label(
            row1,
            text="Duration: 10s",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.duration_label.pack(side=tk.LEFT, padx=5)

        self.price_label = tk.Label(
            row1,
            text="$0.07/sec",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["accent_blue"]
        )
        self.price_label.pack(side=tk.LEFT, padx=5)

        # Row 2: Output mode
        row2 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row2.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            row2,
            text="Output:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.output_mode_var = tk.StringVar(value="source")
        self.source_radio = tk.Radiobutton(
            row2,
            text="Source Folder",
            variable=self.output_mode_var,
            value="source",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_output_mode_changed
        )
        self.source_radio.pack(side=tk.LEFT, padx=(5, 10))

        self.custom_radio = tk.Radiobutton(
            row2,
            text="Custom:",
            variable=self.output_mode_var,
            value="custom",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_output_mode_changed
        )
        self.custom_radio.pack(side=tk.LEFT)

        self.output_path_var = tk.StringVar()
        self.output_entry = tk.Entry(
            row2,
            textvariable=self.output_path_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            insertbackground=COLORS["text_light"],
            width=30
        )
        self.output_entry.pack(side=tk.LEFT, padx=5)

        self.browse_btn = tk.Button(
            row2,
            text="Browse...",
            font=("Segoe UI", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            command=self._browse_output_folder
        )
        self.browse_btn.pack(side=tk.LEFT, padx=5)

        # Row 3: Prompt controls
        row3 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row3.pack(fill=tk.X)

        tk.Label(
            row3,
            text="Prompt:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.edit_prompt_btn = tk.Button(
            row3,
            text="Edit Prompt / Change Model...",
            font=("Segoe UI", 9),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            command=self._show_prompt_editor
        )
        self.edit_prompt_btn.pack(side=tk.LEFT, padx=(5, 15))

        tk.Label(
            row3,
            text="Slot:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"]
        ).pack(side=tk.LEFT)

        self.slot_var = tk.IntVar(value=1)
        for i in range(1, 4):
            rb = tk.Radiobutton(
                row3,
                text=str(i),
                variable=self.slot_var,
                value=i,
                font=("Segoe UI", 9),
                bg=COLORS["bg_input"],
                fg=COLORS["text_light"],
                selectcolor=COLORS["bg_main"],
                activebackground=COLORS["bg_input"],
                activeforeground=COLORS["text_light"],
                command=self._on_slot_changed
            )
            rb.pack(side=tk.LEFT, padx=2)

        # Prompt preview
        self.prompt_preview = tk.Label(
            row3,
            text="",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"],
            anchor="w"
        )
        self.prompt_preview.pack(side=tk.LEFT, padx=(15, 0), fill=tk.X, expand=True)

        # Row 4: Loop Video option
        row4 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row4.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            row4,
            text="Options:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.loop_video_var = tk.BooleanVar(value=False)
        self.loop_checkbox = tk.Checkbutton(
            row4,
            text="Loop Video (ping-pong effect)",
            variable=self.loop_video_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_loop_changed
        )
        self.loop_checkbox.pack(side=tk.LEFT, padx=5)

        self.loop_info_label = tk.Label(
            row4,
            text="(requires FFmpeg)",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.loop_info_label.pack(side=tk.LEFT, padx=5)

        # Row 5: Reprocess options
        row5 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row5.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            row5,
            text="",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.reprocess_var = tk.BooleanVar(value=False)
        self.reprocess_checkbox = tk.Checkbutton(
            row5,
            text="Allow reprocessing",
            variable=self.reprocess_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_reprocess_changed
        )
        self.reprocess_checkbox.pack(side=tk.LEFT, padx=5)

        # Reprocess mode radio buttons (initially hidden)
        self.reprocess_mode_frame = tk.Frame(row5, bg=COLORS["bg_input"])
        self.reprocess_mode_frame.pack(side=tk.LEFT, padx=(10, 0))

        self.reprocess_mode_var = tk.StringVar(value="increment")

        self.overwrite_radio = tk.Radiobutton(
            self.reprocess_mode_frame,
            text="Overwrite",
            variable=self.reprocess_mode_var,
            value="overwrite",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_reprocess_mode_changed
        )
        self.overwrite_radio.pack(side=tk.LEFT, padx=2)

        self.increment_radio = tk.Radiobutton(
            self.reprocess_mode_frame,
            text="Increment (_2, _3...)",
            variable=self.reprocess_mode_var,
            value="increment",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_reprocess_mode_changed
        )
        self.increment_radio.pack(side=tk.LEFT, padx=2)

        # Initially hide reprocess mode options
        self._update_reprocess_mode_visibility()

        # Row 6: Verbose logging toggle
        row6 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row6.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            row6,
            text="Logging:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.verbose_gui_var = tk.BooleanVar(value=False)
        self.verbose_checkbox = tk.Checkbutton(
            row6,
            text="Verbose Mode",
            variable=self.verbose_gui_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_verbose_changed
        )
        self.verbose_checkbox.pack(side=tk.LEFT, padx=5)

        self.verbose_info_label = tk.Label(
            row6,
            text="(show detailed processing info)",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.verbose_info_label.pack(side=tk.LEFT, padx=5)

        # Row 7: Folder Filter options
        row7 = tk.Frame(config_frame, bg=COLORS["bg_input"])
        row7.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            row7,
            text="Folder:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=8,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.folder_pattern_var = tk.StringVar(value="")
        self.folder_pattern_entry = tk.Entry(
            row7,
            textvariable=self.folder_pattern_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            insertbackground=COLORS["text_light"],
            width=20
        )
        self.folder_pattern_entry.pack(side=tk.LEFT, padx=5)
        self.folder_pattern_entry.bind("<FocusOut>", self._on_folder_pattern_changed)
        self.folder_pattern_entry.bind("<Return>", self._on_folder_pattern_changed)

        tk.Label(
            row7,
            text="Match:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"]
        ).pack(side=tk.LEFT, padx=(10, 5))

        self.folder_match_mode_var = tk.StringVar(value="partial")
        self.partial_radio = tk.Radiobutton(
            row7,
            text="Partial",
            variable=self.folder_match_mode_var,
            value="partial",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_folder_match_mode_changed
        )
        self.partial_radio.pack(side=tk.LEFT, padx=2)

        self.exact_radio = tk.Radiobutton(
            row7,
            text="Exact",
            variable=self.folder_match_mode_var,
            value="exact",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_main"],
            activebackground=COLORS["bg_input"],
            activeforeground=COLORS["text_light"],
            command=self._on_folder_match_mode_changed
        )
        self.exact_radio.pack(side=tk.LEFT, padx=2)

        self.folder_info_label = tk.Label(
            row7,
            text="(required for folder processing)",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.folder_info_label.pack(side=tk.LEFT, padx=10)

    def _load_config(self):
        """Load configuration values into UI."""
        # Model (display only - set via CLI)
        model_name = self.config.get("model_display_name", "Kling 2.5 Turbo Pro")
        self.model_label.config(text=model_name)

        # Output mode
        if self.config.get("use_source_folder", True):
            self.output_mode_var.set("source")
        else:
            self.output_mode_var.set("custom")
        self.output_path_var.set(self.config.get("output_folder", ""))
        self._update_output_entry_state()

        # Prompt slot
        self.slot_var.set(self.config.get("current_prompt_slot", 1))
        self._update_prompt_preview()

        # Duration
        duration = self.config.get("video_duration", 10)
        self.duration_label.config(text=f"Duration: {duration}s")

        # Loop video option
        self.loop_video_var.set(self.config.get("loop_videos", False))
        self._check_ffmpeg_status()

        # Reprocess options
        self.reprocess_var.set(self.config.get("allow_reprocess", False))
        self.reprocess_mode_var.set(self.config.get("reprocess_mode", "increment"))
        self._update_reprocess_mode_visibility()

        # Verbose GUI mode
        self.verbose_gui_var.set(self.config.get("verbose_gui_mode", False))

        # Folder filter options
        self.folder_pattern_var.set(self.config.get("folder_filter_pattern", ""))
        self.folder_match_mode_var.set(self.config.get("folder_match_mode", "partial"))

    def _check_ffmpeg_status(self):
        """Check if FFmpeg is available and update UI."""
        try:
            from .video_looper import check_ffmpeg_available
            available, message = check_ffmpeg_available()
            if available:
                self.loop_info_label.config(text="(FFmpeg ready)", fg="#64FF64")
            else:
                self.loop_info_label.config(text="(FFmpeg not found)", fg="#FF6464")
        except Exception:
            self.loop_info_label.config(text="(requires FFmpeg)", fg=COLORS["text_dim"])

    def _on_loop_changed(self):
        """Handle loop video checkbox change."""
        self.config["loop_videos"] = self.loop_video_var.get()
        status = "enabled" if self.loop_video_var.get() else "disabled"
        self._notify_change(f"Loop video {status}")

    def _on_reprocess_changed(self):
        """Handle reprocess checkbox change."""
        self.config["allow_reprocess"] = self.reprocess_var.get()
        self._update_reprocess_mode_visibility()
        status = "enabled" if self.reprocess_var.get() else "disabled"
        self._notify_change(f"Reprocessing {status}")

    def _on_reprocess_mode_changed(self):
        """Handle reprocess mode radio change."""
        mode = self.reprocess_mode_var.get()
        self.config["reprocess_mode"] = mode
        self._notify_change(f"Reprocess mode set to {mode}")

    def _on_verbose_changed(self):
        """Handle verbose mode checkbox change."""
        self.config["verbose_gui_mode"] = self.verbose_gui_var.get()
        status = "enabled" if self.verbose_gui_var.get() else "disabled"
        self._notify_change(f"Verbose mode {status}")

    def _on_folder_pattern_changed(self, event=None):
        """Handle folder pattern entry change."""
        pattern = self.folder_pattern_var.get().strip()
        self.config["folder_filter_pattern"] = pattern
        if pattern:
            self._notify_change(f"Folder pattern set to '{pattern}'")
        else:
            self._notify_change("Folder pattern cleared")

    def _on_folder_match_mode_changed(self):
        """Handle folder match mode radio change."""
        mode = self.folder_match_mode_var.get()
        self.config["folder_match_mode"] = mode
        self._notify_change(f"Folder match mode set to {mode}")

    def _update_reprocess_mode_visibility(self):
        """Show/hide reprocess mode options based on checkbox."""
        if self.reprocess_var.get():
            self.overwrite_radio.config(state="normal")
            self.increment_radio.config(state="normal")
        else:
            self.overwrite_radio.config(state="disabled")
            self.increment_radio.config(state="disabled")

    def _on_output_mode_changed(self):
        """Handle output mode radio change."""
        is_source = self.output_mode_var.get() == "source"
        self.config["use_source_folder"] = is_source
        self._update_output_entry_state()
        mode_desc = "source folder" if is_source else "custom folder"
        self._notify_change(f"Output mode set to {mode_desc}")

    def _update_output_entry_state(self):
        """Enable/disable output path entry based on mode."""
        if self.output_mode_var.get() == "source":
            self.output_entry.config(state="disabled")
            self.browse_btn.config(state="disabled")
        else:
            self.output_entry.config(state="normal")
            self.browse_btn.config(state="normal")

    def _browse_output_folder(self):
        """Open folder browser for output path."""
        folder = filedialog.askdirectory(
            title="Select Output Folder",
            initialdir=self.output_path_var.get() or "."
        )
        if folder:
            self.output_path_var.set(folder)
            self.config["output_folder"] = folder
            self._notify_change(f"Output folder set to {folder}")

    def _on_slot_changed(self):
        """Handle prompt slot change."""
        slot = self.slot_var.get()
        self.config["current_prompt_slot"] = slot
        self._update_prompt_preview()
        self._notify_change(f"Prompt slot changed to {slot}")

    def _update_prompt_preview(self):
        """Update the prompt preview label."""
        slot = self.slot_var.get()
        saved_prompts = self.config.get("saved_prompts", {})
        prompt = saved_prompts.get(str(slot), "")

        if prompt:
            # Truncate for preview
            preview = prompt[:50] + "..." if len(prompt) > 50 else prompt
            self.prompt_preview.config(text=f"  ({preview})")
        else:
            self.prompt_preview.config(text="  (empty)")

    def _show_prompt_editor(self):
        """Show the prompt editor dialog."""
        dialog = PromptEditorDialog(
            self.winfo_toplevel(),
            config=self.config
        )

        if dialog.result is not None:
            # Update ALL saved prompts (user may have edited multiple slots)
            if "all_prompts" in dialog.result:
                self.config["saved_prompts"] = dialog.result["all_prompts"]
            else:
                # Fallback: just update the current slot
                saved_prompts = self.config.get("saved_prompts", {})
                saved_prompts[str(dialog.result["slot"])] = dialog.result["prompt"]
                self.config["saved_prompts"] = saved_prompts

            # Update negative prompts
            if "all_negative_prompts" in dialog.result:
                self.config["negative_prompts"] = dialog.result["all_negative_prompts"]

            # Persist capability cache
            if "model_capabilities" in dialog.result:
                self.config["model_capabilities"] = dialog.result["model_capabilities"]

            # Update current slot
            self.config["current_prompt_slot"] = dialog.result["slot"]
            self.slot_var.set(dialog.result["slot"])

            # Update model if changed
            self.config["current_model"] = dialog.result["model_endpoint"]
            self.config["model_display_name"] = dialog.result["model_name"]
            self.model_label.config(text=dialog.result["model_name"])

            # Update duration based on model
            self.config["video_duration"] = dialog.result["duration"]
            self.duration_label.config(text=f"Duration: {dialog.result['duration']}s")

            self._update_prompt_preview()
            self._notify_change(f"Settings updated: {dialog.result['model_name']}, slot {dialog.result['slot']}")

    def _notify_change(self, description: str = None):
        """Notify that config has changed."""
        if self.on_config_changed:
            self.on_config_changed(self.config, description)

    def get_config(self) -> dict:
        """Get current configuration."""
        return self.config.copy()

    def cleanup(self):
        """Clean up tkinter variables to prevent thread-related errors on exit.

        This must be called before the root window is destroyed to avoid
        'main thread is not in main loop' errors on Python 3.14+.
        """
        # List all tkinter variable attributes to clean up
        var_attrs = [
            'output_mode_var', 'output_path_var', 'slot_var',
            'loop_video_var', 'reprocess_var', 'reprocess_mode_var',
            'verbose_gui_var', 'folder_pattern_var', 'folder_match_mode_var'
        ]
        for attr in var_attrs:
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except Exception:
                    pass


class PromptEditorDialog(tk.Toplevel):
    """Modal dialog for editing prompts with slot and model selection."""

    def __init__(self, parent, config: dict):
        super().__init__(parent)
        self.title("Edit Prompt & Settings")
        self.result = None
        self.config = config
        # Pre-set attributes so event callbacks remain safe even if UI setup aborts early
        self.text = None
        self.custom_status = None
        self.prompt_label = None
        self.duration_label = None
        self.neg_badge = None
        self.neg_status = None
        # IMPORTANT: Make a deep copy so cancel doesn't affect original config
        original_prompts = config.get("saved_prompts", {"1": "", "2": "", "3": ""})
        original_negative_prompts = config.get("negative_prompts", {"1": "", "2": "", "3": ""})
        self.capabilities = config.get("model_capabilities", {})
        self.saved_prompts = {k: (v if v else "") for k, v in original_prompts.items()}
        self.saved_negative_prompts = {k: (v if v else "") for k, v in original_negative_prompts.items()}

        # Model list - start with cached/fallback, then fetch fresh
        self.models = ModelFetcher.get_cached_or_fallback(config)
        self.is_loading_models = False

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Configure window
        self.configure(bg=COLORS["bg_panel"])
        self.geometry("900x820")
        self.minsize(720, 560)

        # Increase Combobox dropdown height to show more models at once
        # Scoped to toplevel window to avoid affecting other windows in the process
        # Guarded to prevent crashes in headless or unusual Tk backend environments
        try:
            root = self.winfo_toplevel()
            root.option_add('*TCombobox*Listbox.height', COMBOBOX_DROPDOWN_HEIGHT)
        except tk.TclError as e:
            logger.warning("Failed to set combobox dropdown height: %s", e)

        # Style to ensure Combobox text is visible on dark background
        # NOTE: Do NOT use style.theme_use() - it breaks global ttk rendering
        style = ttk.Style(self)
        style.configure(
            "Dialog.TCombobox",
            fieldbackground=COLORS["bg_input"],
            background=COLORS["bg_panel"],
            foreground="#000000",  # Black text on light combobox
            arrowcolor=COLORS["text_light"]
        )
        # Map ensures text is visible in all states
        style.map("Dialog.TCombobox",
            fieldbackground=[("readonly", COLORS["bg_input"]), ("disabled", "#666666")],
            foreground=[("readonly", "#000000"), ("disabled", "#999999")],
            selectbackground=[("readonly", COLORS["accent_blue"])],
            selectforeground=[("readonly", "#FFFFFF")]
        )

        # Create UI
        self._setup_ui()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        # Fetch fresh models if API key exists
        api_key = config.get("falai_api_key", "")
        if api_key:
            self._refresh_models()

        # Wait for dialog to close
        self.wait_window()

    def _setup_ui(self):
        """Set up the dialog UI with slot and model selectors."""
        # Title
        tk.Label(
            self,
            text="✏️ PROMPT & MODEL SETTINGS",
            font=("Segoe UI", 12, "bold"),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"]
        ).pack(padx=10, pady=(10, 5), anchor="w")

        # Top controls frame
        controls_frame = tk.Frame(self, bg=COLORS["bg_input"], padx=10, pady=10)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        # Row 1: Slot Selection
        slot_row = tk.Frame(controls_frame, bg=COLORS["bg_input"])
        slot_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            slot_row,
            text="Prompt Slot:",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.slot_var = tk.IntVar(value=self.config.get("current_prompt_slot", 1))
        self.current_slot = self.slot_var.get()  # Track current slot for saving before switch

        for i in range(1, 4):
            rb = tk.Radiobutton(
                slot_row,
                text=f"Slot {i}",
                variable=self.slot_var,
                value=i,
                font=("Segoe UI", 10),
                bg=COLORS["bg_input"],
                fg=COLORS["text_light"],
                selectcolor=COLORS["bg_main"],
                activebackground=COLORS["bg_input"],
                activeforeground=COLORS["text_light"],
                command=self._on_slot_changed
            )
            rb.pack(side=tk.LEFT, padx=10)

        # Row 2: Model Selection
        model_row = tk.Frame(controls_frame, bg=COLORS["bg_input"])
        model_row.pack(fill=tk.X, pady=(0, 5))

        tk.Label(
            model_row,
            text="Model:",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)

        # Find current model index
        current_model = self.config.get("current_model", "")
        model_names = [m["name"] for m in self.models]
        current_index = 0
        for i, m in enumerate(self.models):
            if m["endpoint"] == current_model:
                current_index = i
                break

        self.model_var = tk.StringVar(value=model_names[current_index] if model_names else "Loading...")
        self.model_combo = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=model_names,
            state="readonly",
            font=("Segoe UI", 10),
            width=28,
            style="Dialog.TCombobox"
        )
        self.model_combo.pack(side=tk.LEFT, padx=5)
        if model_names:
            self.model_combo.current(current_index)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)

        # Refresh button
        self.refresh_btn = tk.Button(
            model_row,
            text="🔄",
            font=("Segoe UI", 10),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            width=3,
            command=self._refresh_models
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=2)

        # Duration label
        duration = self.models[current_index]["duration"] if self.models else 10
        self.duration_label = tk.Label(
            model_row,
            text=f"Duration: {duration}s",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["accent_blue"]
        )
        self.duration_label.pack(side=tk.LEFT, padx=5)

        # Model count and status
        self.model_status = tk.Label(
            model_row,
            text=f"({len(self.models)} models)",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.model_status.pack(side=tk.LEFT, padx=5)

        # Negative prompt row (capability-aware)
        neg_row = tk.Frame(controls_frame, bg=COLORS["bg_input"])
        neg_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            neg_row,
            text="Negative:",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.neg_var = tk.StringVar(value=self.saved_negative_prompts.get(str(self.slot_var.get()), ""))
        self.neg_entry = tk.Entry(
            neg_row,
            textvariable=self.neg_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            insertbackground=COLORS["text_light"],
            width=60
        )
        self.neg_entry.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        self.neg_badge = tk.Label(
            neg_row,
            text="Checking",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS.get("warning", "#FFB347"),
            fg="black",
            padx=6,
            pady=2
        )
        self.neg_badge.pack(side=tk.LEFT, padx=4)

        self.neg_status = tk.Label(
            neg_row,
            text="Checking support...",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.neg_status.pack(side=tk.LEFT, padx=5)

        # Kick off capability check for initially selected model
        if self.models:
            self._check_negative_support(self.models[current_index]["endpoint"])
        else:
            self.neg_status.config(text="No models loaded", fg=COLORS.get("warning", "#FFB347"))
            self.neg_entry.config(state="disabled")

        # Row 3: Browse models link
        link_row = tk.Frame(controls_frame, bg=COLORS["bg_input"])
        link_row.pack(fill=tk.X)

        tk.Label(
            link_row,
            text="",
            bg=COLORS["bg_input"],
            width=12
        ).pack(side=tk.LEFT)

        browse_link = tk.Label(
            link_row,
            text="📋 Browse all models on fal.ai →",
            font=("Segoe UI", 9, "underline"),
            bg=COLORS["bg_input"],
            fg=COLORS["accent_blue"],
            cursor="hand2"
        )
        browse_link.pack(side=tk.LEFT, padx=5)
        browse_link.bind("<Button-1>", lambda e: os.startfile(FAL_MODELS_URL) if os.name == 'nt' else None)

        # Row 4: Custom model endpoint entry
        custom_row = tk.Frame(controls_frame, bg=COLORS["bg_input"])
        custom_row.pack(fill=tk.X, pady=(8, 0))

        tk.Label(
            custom_row,
            text="Custom:",
            font=("Segoe UI", 9),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"],
            width=12,
            anchor="w"
        ).pack(side=tk.LEFT)

        self.custom_endpoint_var = tk.StringVar(value="")
        self.custom_entry = tk.Entry(
            custom_row,
            textvariable=self.custom_endpoint_var,
            font=("Consolas", 9),
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            insertbackground=COLORS["text_light"],
            width=40
        )
        self.custom_entry.pack(side=tk.LEFT, padx=5)

        # Placeholder text
        self.custom_entry.insert(0, "fal-ai/kling-video/v2.5/pro/image-to-video")
        self.custom_entry.config(fg=COLORS["text_dim"])

        def on_custom_focus_in(e):
            if self.custom_entry.get() == "fal-ai/kling-video/v2.5/pro/image-to-video":
                self.custom_entry.delete(0, tk.END)
                self.custom_entry.config(fg=COLORS["text_light"])

        def on_custom_focus_out(e):
            if not self.custom_entry.get().strip():
                self.custom_entry.insert(0, "fal-ai/kling-video/v2.5/pro/image-to-video")
                self.custom_entry.config(fg=COLORS["text_dim"])

        self.custom_entry.bind("<FocusIn>", on_custom_focus_in)
        self.custom_entry.bind("<FocusOut>", on_custom_focus_out)

        self.use_custom_btn = tk.Button(
            custom_row,
            text="Use Custom",
            font=("Segoe UI", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            command=self._use_custom_endpoint
        )
        self.use_custom_btn.pack(side=tk.LEFT, padx=5)

        # Custom endpoint status
        self.custom_status = tk.Label(
            custom_row,
            text="",
            font=("Segoe UI", 8),
            bg=COLORS["bg_input"],
            fg=COLORS["text_dim"]
        )
        self.custom_status.pack(side=tk.LEFT, padx=5)

        # Prompt label
        prompt_label_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        prompt_label_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        self.prompt_label = tk.Label(
            prompt_label_frame,
            text=f"Prompt for Slot {self.slot_var.get()}:",
            font=("Segoe UI", 10),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"]
        )
        self.prompt_label.pack(side=tk.LEFT)

        # Character count
        self.char_count = tk.Label(
            prompt_label_frame,
            text="0 chars",
            font=("Segoe UI", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"]
        )
        self.char_count.pack(side=tk.RIGHT)

        # Text area with scrollbar
        text_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, side=tk.TOP)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=COLORS["bg_main"],
            fg=COLORS["text_light"],
            insertbackground=COLORS["text_light"],
            yscrollcommand=scrollbar.set,
            padx=10,
            pady=10
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text.yview)

        # Bind text changes for character count
        self.text.bind("<KeyRelease>", self._update_char_count)

        # Load initial prompt for current slot
        self._load_prompt_for_slot(self.slot_var.get())

        # Button frame
        btn_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        btn_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)

        # Info label
        tk.Label(
            btn_frame,
            text="💾 Changes are saved to kling_config.json",
            font=("Segoe UI", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"]
        ).pack(side=tk.LEFT)

        # Cancel button
        tk.Button(
            btn_frame,
            text="✖ Cancel",
            font=("Segoe UI", 10),
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            width=12,
            command=self._cancel
        ).pack(side=tk.RIGHT, padx=5, pady=(5, 0))

        # Save button
        tk.Button(
            btn_frame,
            text="💾 Save",
            font=("Segoe UI", 10, "bold"),
            bg="#329632",
            fg="white",
            width=12,
            command=self._save
        ).pack(side=tk.RIGHT, padx=5, pady=(5, 0))

    def _on_slot_changed(self):
        """Handle slot selection change - save current and load new slot's prompt."""
        # Guard: ensure UI widgets are initialized before accessing them
        if not getattr(self, "text", None) or not getattr(self, "prompt_label", None):
            return

        # Save current slot's text before switching
        current_text = self.text.get("1.0", tk.END).strip()
        self.saved_prompts[str(self.current_slot)] = current_text
        self.saved_negative_prompts[str(self.current_slot)] = self.neg_var.get().strip()

        # Switch to new slot
        new_slot = self.slot_var.get()
        self.current_slot = new_slot
        self.prompt_label.config(text=f"Prompt for Slot {new_slot}:")
        self._load_prompt_for_slot(new_slot)

    def _load_prompt_for_slot(self, slot: int):
        """Load prompt text for the specified slot."""
        prompt = self.saved_prompts.get(str(slot), "") or ""
        neg_prompt = self.saved_negative_prompts.get(str(slot), "") or ""
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", prompt)
        self.neg_var.set(neg_prompt)
        self._update_char_count()

    def _on_model_changed(self, event=None):
        """Handle model selection change."""
        # Guard: ensure UI widgets are initialized before accessing them
        if not getattr(self, "custom_status", None) or not getattr(self, "duration_label", None):
            return

        model_name = self.model_var.get()
        for m in self.models:
            if m["name"] == model_name:
                self.duration_label.config(text=f"Duration: {m['duration']}s")
                # Clear custom status when selecting from dropdown
                self.custom_status.config(text="", fg=COLORS["text_dim"])
                self._check_negative_support(m["endpoint"])
                break

    def _use_custom_endpoint(self):
        """Use the custom endpoint from the entry field."""
        custom_endpoint = self.custom_entry.get().strip()
        placeholder = "fal-ai/kling-video/v2.5/pro/image-to-video"

        if not custom_endpoint or custom_endpoint == placeholder:
            self.custom_status.config(text="Enter endpoint first", fg="#FF6464")
            return

        # Validate format (should start with fal-ai/ or be a valid path)
        if not custom_endpoint.startswith("fal-ai/") and "/" not in custom_endpoint:
            self.custom_status.config(text="Invalid format", fg="#FF6464")
            return

        # Create display name from endpoint
        display_name = parse_endpoint_to_display_name(custom_endpoint)

        # Add to models list if not already there
        existing = next((m for m in self.models if m["endpoint"] == custom_endpoint), None)
        if not existing:
            custom_model = {
                "name": f"[Custom] {display_name}",
                "endpoint": custom_endpoint,
                "duration": 10,  # Default duration
                "description": "Custom endpoint"
            }
            self.models.insert(0, custom_model)

            # Update dropdown
            model_names = [m["name"] for m in self.models]
            self.model_combo["values"] = model_names

        # Select the custom model
        for i, m in enumerate(self.models):
            if m["endpoint"] == custom_endpoint:
                self.model_combo.current(i)
                self.model_var.set(m["name"])
                self.duration_label.config(text=f"Duration: {m['duration']}s")
                break

        self.custom_status.config(text="✓ Custom model set", fg="#64FF64")
        # Trigger negative prompt capability check for custom endpoint
        self._check_negative_support(custom_endpoint)

    def _refresh_models(self):
        """Fetch fresh model list from fal.ai API."""
        if self.is_loading_models:
            return

        api_key = self.config.get("falai_api_key", "")
        if not api_key:
            self.model_status.config(text="(No API key)", fg="#FF6464")
            return

        self.is_loading_models = True
        self.refresh_btn.config(state="disabled")
        self.model_status.config(text="(Loading...)", fg=COLORS["accent_blue"])

        def on_models_fetched(models, error):
            # Run on main thread
            self.after(0, lambda: self._update_models(models, error))

        ModelFetcher.fetch_models(api_key, on_models_fetched)

    def _check_negative_support(self, endpoint_id: str):
        """Detect if the selected model supports negative_prompt via its OpenAPI schema."""
        # Use cached capability if present
        cached = self.capabilities.get(endpoint_id)
        if cached is not None:
            self._apply_negative_support(cached)
            return

        self.neg_status.config(text="Checking support...", fg=COLORS["text_dim"])
        self.neg_badge.config(text="Checking", bg=COLORS["warning"], fg="black")
        self.neg_entry.config(state="disabled")

        def worker():
            supported = False
            try:
                import requests
                url = f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={endpoint_id}"
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    props = resp.json().get("paths", {})
                    for pdata in props.values():
                        for info in pdata.values():
                            schema_props = (
                                info.get("requestBody", {})
                                .get("content", {})
                                .get("application/json", {})
                                .get("schema", {})
                                .get("properties", {})
                            )
                            if any("negative" in k.lower() for k in schema_props.keys()):
                                supported = True
                                break
                        if supported:
                            break
            except Exception as e:
                logger.debug(f"Negative prompt capability check failed: {e}")

            # Schedule cache update and UI apply on main thread for thread safety
            def update_on_main():
                if not self.winfo_exists():
                    return
                self.capabilities[endpoint_id] = supported
                self.config["model_capabilities"] = self.capabilities
                self._apply_negative_support(supported)

            self.after(0, update_on_main)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_negative_support(self, supported: bool):
        """Enable/disable negative prompt entry based on support."""
        if supported:
            self.neg_entry.config(state="normal")
            self.neg_status.config(text="Supported by model", fg=COLORS["success"])
            self.neg_badge.config(text="Supported", bg=COLORS["success"], fg="black")
        else:
            self.neg_entry.delete(0, tk.END)
            self.neg_entry.config(state="disabled")
            self.neg_status.config(text="Not supported by this model", fg=COLORS["text_dim"])
            self.neg_badge.config(text="Unsupported", bg=COLORS["error"], fg="white")

    def _update_models(self, models: list, error: str):
        """Update model dropdown with fetched models."""
        # Safety check: dialog may have been closed before callback fired
        if not self.winfo_exists():
            return

        self.is_loading_models = False
        self.refresh_btn.config(state="normal")

        if error:
            self.model_status.config(text=f"(Error: {error[:20]})", fg="#FF6464")
            return

        if not models:
            self.model_status.config(text="(No models found)", fg="#FF6464")
            return

        # Update models list
        self.models = models
        ModelFetcher.cache_models(self.config, models)

        # Update dropdown
        model_names = [m["name"] for m in models]
        self.model_combo["values"] = model_names

        # Try to keep current selection
        current_endpoint = self.config.get("current_model", "")
        new_index = 0
        for i, m in enumerate(models):
            if m["endpoint"] == current_endpoint:
                new_index = i
                break

        self.model_combo.current(new_index)
        self.model_var.set(model_names[new_index])
        self.duration_label.config(text=f"Duration: {models[new_index]['duration']}s")
        self.model_status.config(text=f"({len(models)} models)", fg="#64FF64")
        self._check_negative_support(models[new_index]["endpoint"])

    def _update_char_count(self, event=None):
        """Update character count label."""
        text = self.text.get("1.0", tk.END).strip()
        self.char_count.config(text=f"{len(text)} chars")

    def _get_selected_model(self) -> dict:
        """Get the selected model details."""
        model_name = self.model_var.get()
        for m in self.models:
            if m["name"] == model_name:
                return m
        # Fallback to first model or a default
        if self.models:
            return self.models[0]
        return {"name": "Unknown", "endpoint": "", "duration": 10}

    def _save(self):
        """Save and close with all settings."""
        # Save current slot's text to local dict
        current_text = self.text.get("1.0", tk.END).strip()
        self.saved_prompts[str(self.current_slot)] = current_text
        self.saved_negative_prompts[str(self.current_slot)] = self.neg_var.get().strip()

        model = self._get_selected_model()
        self.result = {
            "slot": self.slot_var.get(),
            "prompt": current_text,
            "model_name": model["name"],
            "model_endpoint": model["endpoint"],
            "duration": model["duration"],
            "all_prompts": self.saved_prompts.copy(),  # Include all edited prompts
            "all_negative_prompts": self.saved_negative_prompts.copy(),
            "model_capabilities": self.capabilities
        }
        self.destroy()

    def _cancel(self):
        """Cancel and close."""
        self.result = None
        self.destroy()
