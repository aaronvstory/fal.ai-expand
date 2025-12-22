"""
Drop Zone Widget - Drag-and-drop area for image files with visual feedback.
"""

import tkinter as tk
from tkinter import filedialog
from typing import Callable, List
import os

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False


# Color palette
COLORS = {
    "bg_main": "#2D2D30",
    "bg_panel": "#3C3C41",
    "bg_drop": "#464649",
    "text_light": "#DCDCDC",
    "text_dim": "#B4B4B4",
    "drop_valid": "#329632",
    "drop_invalid": "#963232",
    "border": "#5A5A5E",
}

VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff', '.tif'}


class DropZone(tk.Frame):
    """Large drop zone for dragging image files and folders."""

    def __init__(self, parent, on_files_dropped: Callable[[List[str]], None], on_folder_dropped: Callable[[str], None] = None, **kwargs):
        """
        Initialize the drop zone.

        Args:
            parent: Parent widget
            on_files_dropped: Callback function that receives list of file paths
            on_folder_dropped: Callback function that receives folder path
        """
        super().__init__(parent, bg=COLORS["bg_panel"], **kwargs)
        self.on_files_dropped = on_files_dropped
        self.on_folder_dropped = on_folder_dropped
        self._default_bg = COLORS["bg_drop"]

        # Create the drop area
        self.drop_frame = tk.Frame(
            self,
            bg=self._default_bg,
            highlightbackground=COLORS["border"],
            highlightthickness=2
        )
        self.drop_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Icon/emoji label
        self.icon_label = tk.Label(
            self.drop_frame,
            text="🖼️",
            font=("Segoe UI Emoji", 48),
            bg=self._default_bg,
            fg=COLORS["text_light"]
        )
        self.icon_label.pack(pady=(40, 10))

        # Main instruction label
        self.main_label = tk.Label(
            self.drop_frame,
            text="DRAG IMAGES OR FOLDERS HERE",
            font=("Segoe UI", 14, "bold"),
            bg=self._default_bg,
            fg=COLORS["text_light"],
            cursor="hand2"
        )
        self.main_label.pack(pady=5)

        # Sub-instruction label
        self.sub_label = tk.Label(
            self.drop_frame,
            text="Left-click: select files • Right-click: select folder\n(.jpg, .png, .webp, .bmp, .gif, .tiff)",
            font=("Segoe UI", 10),
            bg=self._default_bg,
            fg=COLORS["text_dim"],
            cursor="hand2"
        )
        self.sub_label.pack(pady=(5, 40))

        # Bind click events: left-click for files, right-click for folder
        for widget in [self.drop_frame, self.icon_label, self.main_label, self.sub_label]:
            widget.bind("<Button-1>", self._on_click_browse)
            widget.bind("<Button-3>", self._on_right_click_browse_folder)
            widget.config(cursor="hand2")

        # Status label (shows during drag)
        self.status_label = tk.Label(
            self.drop_frame,
            text="",
            font=("Segoe UI", 11),
            bg=self._default_bg,
            fg=COLORS["text_light"]
        )
        self.status_label.pack(pady=5)

        # Register for drag-and-drop if available
        if HAS_DND:
            self._setup_dnd()
        else:
            # Fallback: show "click to browse" option
            self.main_label.config(text="CLICK TO SELECT FILES OR FOLDER")
            self.sub_label.config(text="Drag-drop not available. Left-click: files, Right-click: folder\n(.jpg, .png, .webp, .bmp, .gif, .tiff)")

    def _on_click_browse(self, event=None):
        """Handle left-click to open file browser dialog."""
        self._browse_files()

    def _browse_files(self):
        """Open file browser dialog for image files."""
        # Define file types for the dialog
        filetypes = [
            ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif"),
            ("JPEG files", "*.jpg *.jpeg"),
            ("PNG files", "*.png"),
            ("WebP files", "*.webp"),
            ("All files", "*.*")
        ]

        # Open file dialog - allow multiple file selection
        file_paths = filedialog.askopenfilenames(
            title="Select Images to Process",
            filetypes=filetypes
        )

        if file_paths:
            # Filter and validate files
            valid_files = []
            invalid_count = 0

            for file_path in file_paths:
                is_valid, result_type = self.validate_file(file_path)
                if is_valid and result_type == "file":
                    valid_files.append(file_path)
                else:
                    invalid_count += 1

            # Show status and call callback
            if valid_files:
                self.status_label.config(
                    text=f"Adding {len(valid_files)} file(s)...",
                    fg=COLORS["text_light"]
                )
                self.on_files_dropped(valid_files)

            if invalid_count > 0:
                self.status_label.config(
                    text=f"Skipped {invalid_count} invalid file(s)",
                    fg=COLORS["drop_invalid"]
                )

            # Clear status after delay
            self.after(2000, lambda: self.status_label.config(text=""))

    def _browse_folder(self):
        """Open folder browser dialog."""
        folder_path = filedialog.askdirectory(
            title="Select Folder to Process"
        )

        if folder_path and self.on_folder_dropped:
            self.status_label.config(
                text="Processing folder...",
                fg=COLORS["text_light"]
            )
            self.on_folder_dropped(folder_path)
            # Clear status after delay
            self.after(2000, lambda: self.status_label.config(text=""))

    def _on_right_click_browse_folder(self, event=None):
        """Handle right-click to open folder browser dialog."""
        self._browse_folder()

    def _setup_dnd(self):
        """Set up drag-and-drop handlers."""
        # Register all widgets in drop zone for DnD
        for widget in [self.drop_frame, self.icon_label, self.main_label,
                       self.sub_label, self.status_label]:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<DropEnter>>', self._on_drag_enter)
            widget.dnd_bind('<<DropLeave>>', self._on_drag_leave)
            widget.dnd_bind('<<Drop>>', self._on_drop)

    def _on_drag_enter(self, event):
        """Handle drag enter - show visual feedback."""
        self._set_highlight(COLORS["drop_valid"])
        self.status_label.config(text="DROP TO ADD TO QUEUE", fg=COLORS["text_light"])
        return event.action

    def _on_drag_leave(self, event):
        """Handle drag leave - reset visual feedback."""
        self._reset_highlight()
        self.status_label.config(text="")
        return event.action

    def _on_drop(self, event):
        """Handle file or folder drop."""
        self._reset_highlight()
        self.status_label.config(text="")

        # Parse dropped files/folders
        items = self._parse_drop_data(event.data)

        # Separate files and folders
        valid_files = []
        folders = []
        invalid_count = 0

        for item_path in items:
            is_valid, result_type = self.validate_file(item_path)
            if is_valid:
                if result_type == "folder":
                    folders.append(item_path)
                else:
                    valid_files.append(item_path)
            else:
                invalid_count += 1

        # Handle folders first (via callback)
        for folder in folders:
            if self.on_folder_dropped:
                self.status_label.config(
                    text=f"Processing folder...",
                    fg=COLORS["text_light"]
                )
                self.on_folder_dropped(folder)

        # Handle files
        if valid_files:
            self.status_label.config(
                text=f"Adding {len(valid_files)} file(s)...",
                fg=COLORS["text_light"]
            )
            self.on_files_dropped(valid_files)

        if invalid_count > 0:
            self.status_label.config(
                text=f"Skipped {invalid_count} invalid file(s)",
                fg=COLORS["drop_invalid"]
            )

        # Clear status after delay
        self.after(2000, lambda: self.status_label.config(text=""))

        return event.action

    def _parse_drop_data(self, data: str) -> List[str]:
        """Parse the dropped file data into a list of paths."""
        files = []

        # Handle different formats
        # Windows typically gives paths in {} braces if they contain spaces
        if '{' in data:
            # Parse {path1} {path2} format
            import re
            matches = re.findall(r'\{([^}]+)\}', data)
            files.extend(matches)
            # Also get unbraced paths
            remaining = re.sub(r'\{[^}]+\}', '', data).strip()
            if remaining:
                files.extend(remaining.split())
        else:
            # Simple space-separated paths
            files = data.split()

        # Clean up paths
        cleaned = []
        for f in files:
            f = f.strip()
            if f and os.path.exists(f):
                cleaned.append(f)

        return cleaned

    def validate_file(self, file_path: str) -> tuple:
        """
        Validate a file or folder for processing.

        Returns:
            (is_valid, result_type) where result_type is "file", "folder", or error message
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        if os.path.isdir(file_path):
            return True, "folder"

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in VALID_EXTENSIONS:
            return False, f"Unsupported format: {ext}"

        return True, "file"

    def _set_highlight(self, color: str):
        """Set the highlight color for drop feedback."""
        self.drop_frame.config(bg=color)
        self.icon_label.config(bg=color)
        self.main_label.config(bg=color)
        self.sub_label.config(bg=color)
        self.status_label.config(bg=color)

    def _reset_highlight(self):
        """Reset to default colors."""
        self._set_highlight(self._default_bg)


def create_dnd_root():
    """Create a TkinterDnD root window if available, otherwise regular Tk."""
    if HAS_DND:
        return TkinterDnD.Tk()
    else:
        return tk.Tk()
