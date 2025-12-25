from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog
from typing import Any, Callable


COLORS = {
    "bg_main": "#2D2D30",
    "bg_panel": "#3C3C41",
    "bg_input": "#464649",
    "text_light": "#DCDCDC",
    "text_dim": "#B4B4B4",
    "accent_blue": "#6496FF",
    "btn_green": "#329632",
}


class ConfigPanel(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        initial_config: dict[str, Any],
        on_config_changed: Callable[[dict[str, Any]], None],
        on_test_backend: Callable[[], None],
        on_save_config: Callable[[], None] | None = None,
    ):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self._on_config_changed = on_config_changed
        self._on_test_backend = on_test_backend
        self._on_save_config = on_save_config or (lambda: None)

        self._vars: dict[str, tk.Variable] = {}

        def s(name: str, default: str) -> tk.StringVar:
            v = tk.StringVar(value=str(initial_config.get(name, default) or default))
            self._vars[name] = v
            return v

        def i(name: str, default: int) -> tk.IntVar:
            v = tk.IntVar(value=int(initial_config.get(name, default) or default))
            self._vars[name] = v
            return v

        def b(name: str, default: bool) -> tk.BooleanVar:
            v = tk.BooleanVar(value=bool(initial_config.get(name, default)))
            self._vars[name] = v
            return v

        self.backend = s("backend", "falai")
        self.falai_api_key = s("falai_api_key", "")
        self.enable_safety_checker = b("enable_safety_checker", True)

        self.comfyui_url = s("comfyui_url", "http://127.0.0.1:8188")
        self.comfyui_workflow_path = s("comfyui_workflow_path", "comfyui_workflows/flux_outpaint.json")

        self.use_source_folder = b("use_source_folder", True)
        self.output_folder = s("output_folder", "")
        self.output_suffix = s("output_suffix", "-expanded")
        self.output_format = s("output_format", "png")

        self.zoom_out_percentage = i("zoom_out_percentage", 30)
        self.expand_mode = s("expand_mode", "percentage")
        self.expand_percentage = i("expand_percentage", 30)
        self.expand_left = i("expand_left", 0)
        self.expand_right = i("expand_right", 0)
        self.expand_top = i("expand_top", 0)
        self.expand_bottom = i("expand_bottom", 0)
        self.num_images = i("num_images", 1)
        self.prompt = s("prompt", "")

        self._expand_pct_spin: tk.Spinbox | None = None
        self._expand_px_spins: list[tk.Spinbox] = []

        self._configure_ttk_styles()
        self._build_ui()

        for v in self._vars.values():
            v.trace_add("write", lambda *_: self._emit_changed())

        self.expand_mode.trace_add("write", lambda *_: self._update_expand_mode_controls())

        self._update_expand_mode_controls()

        self._emit_changed()

    def _update_expand_mode_controls(self) -> None:
        mode = (self.expand_mode.get() or "percentage").lower()
        pct_state = "normal" if mode == "percentage" else "disabled"
        px_state = "normal" if mode == "pixels" else "disabled"

        if self._expand_pct_spin is not None:
            self._expand_pct_spin.configure(state=pct_state)
        for w in self._expand_px_spins:
            w.configure(state=px_state)

    def _configure_ttk_styles(self) -> None:
        """Configure ttk styles for dark mode LabelFrames."""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Dark.TLabelframe",
            background=COLORS["bg_panel"],
            bordercolor=COLORS["bg_input"],
            darkcolor=COLORS["bg_panel"],
            lightcolor=COLORS["bg_panel"],
            relief="solid",
            borderwidth=1,
        )

        style.configure(
            "Dark.TLabelframe.Label",
            background=COLORS["bg_panel"],
            foreground=COLORS["text_light"],
            font=("Segoe UI", 10, "bold"),
        )

    def _build_ui(self) -> None:
        """Build the GUI using LabelFrame sections and grid layout."""
        # Make the main container expand
        self.columnconfigure(0, weight=1)

        # Backend Selection Section
        row_idx = 0
        backend_frame = ttk.LabelFrame(
            self,
            text="Backend",
            style="Dark.TLabelframe",
            padding=(10, 8, 10, 8)
        )
        backend_frame.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(10, 5))
        backend_frame.columnconfigure(0, weight=1)

        self._build_backend_section(backend_frame)

        # Fal.ai Settings Section
        row_idx += 1
        falai_frame = ttk.LabelFrame(
            self,
            text="fal.ai",
            style="Dark.TLabelframe",
            padding=(10, 8, 10, 8)
        )
        falai_frame.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=5)
        falai_frame.columnconfigure(1, weight=1)

        self._build_falai_section(falai_frame)

        # ComfyUI Settings Section
        row_idx += 1
        comfy_frame = ttk.LabelFrame(
            self,
            text="ComfyUI",
            style="Dark.TLabelframe",
            padding=(10, 8, 10, 8)
        )
        comfy_frame.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=5)
        comfy_frame.columnconfigure(1, weight=1)

        self._build_comfyui_section(comfy_frame)

        # Output Settings Section
        row_idx += 1
        output_frame = ttk.LabelFrame(
            self,
            text="Output",
            style="Dark.TLabelframe",
            padding=(10, 8, 10, 8)
        )
        output_frame.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=5)
        output_frame.columnconfigure(1, weight=1)

        self._build_output_section(output_frame)

        # Outpaint Controls Section
        row_idx += 1
        outpaint_frame = ttk.LabelFrame(
            self,
            text="Outpaint",
            style="Dark.TLabelframe",
            padding=(10, 8, 10, 8)
        )
        outpaint_frame.grid(row=row_idx, column=0, sticky="ew", padx=10, pady=(5, 10))
        outpaint_frame.columnconfigure(1, weight=1)

        self._build_outpaint_section(outpaint_frame)

    def _build_backend_section(self, parent: ttk.LabelFrame) -> None:
        """Build backend selection controls."""
        radio_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        radio_frame.grid(row=0, column=0, sticky="w", pady=(0, 4))

        tk.Radiobutton(
            radio_frame,
            text="fal.ai (Cloud)",
            variable=self.backend,
            value="falai",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).grid(row=0, column=0, sticky="w")

        tk.Radiobutton(
            radio_frame,
            text="ComfyUI (Local)",
            variable=self.backend,
            value="comfyui",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Button container for Test and Save
        button_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        button_frame.grid(row=0, column=1, sticky="e")

        tk.Button(
            button_frame,
            text="Save",
            bg=COLORS["accent_blue"],
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=self._on_save_config,
            width=6,
        ).grid(row=0, column=0, padx=(0, 4))

        tk.Button(
            button_frame,
            text="Test",
            bg=COLORS["btn_green"],
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=self._on_test_backend,
            width=6,
        ).grid(row=0, column=1)

    def _build_falai_section(self, parent: ttk.LabelFrame) -> None:
        """Build fal.ai settings controls."""
        tk.Label(
            parent,
            text="API key",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=0, column=0, sticky="w", pady=3)

        tk.Entry(
            parent,
            textvariable=self.falai_api_key,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white",
            show="*"
        ).grid(row=0, column=1, sticky="ew", pady=3)

        tk.Checkbutton(
            parent,
            text="Enable safety checker",
            variable=self.enable_safety_checker,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 2))

    def _build_comfyui_section(self, parent: ttk.LabelFrame) -> None:
        """Build ComfyUI settings controls."""
        tk.Label(
            parent,
            text="Server URL",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=0, column=0, sticky="w", pady=3)

        tk.Entry(
            parent,
            textvariable=self.comfyui_url,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white"
        ).grid(row=0, column=1, sticky="ew", pady=3)

        tk.Label(
            parent,
            text="Workflow",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=1, column=0, sticky="w", pady=3)

        workflow_container = tk.Frame(parent, bg=COLORS["bg_panel"])
        workflow_container.grid(row=1, column=1, sticky="ew", pady=3)
        workflow_container.columnconfigure(0, weight=1)

        tk.Entry(
            workflow_container,
            textvariable=self.comfyui_workflow_path,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white"
        ).grid(row=0, column=0, sticky="ew")

        tk.Button(
            workflow_container,
            text="…",
            width=3,
            command=self._browse_workflow
        ).grid(row=0, column=1, sticky="e", padx=(6, 0))

    def _build_output_section(self, parent: ttk.LabelFrame) -> None:
        """Build output settings controls."""
        tk.Checkbutton(
            parent,
            text="Save next to source image",
            variable=self.use_source_folder,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 4))

        tk.Label(
            parent,
            text="Folder",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=1, column=0, sticky="w", pady=3)

        folder_container = tk.Frame(parent, bg=COLORS["bg_panel"])
        folder_container.grid(row=1, column=1, sticky="ew", pady=3)
        folder_container.columnconfigure(0, weight=1)

        tk.Entry(
            folder_container,
            textvariable=self.output_folder,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white"
        ).grid(row=0, column=0, sticky="ew")

        tk.Button(
            folder_container,
            text="…",
            width=3,
            command=self._browse_output_folder
        ).grid(row=0, column=1, sticky="e", padx=(6, 0))

        tk.Label(
            parent,
            text="Format",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=2, column=0, sticky="w", pady=3)

        format_menu = tk.OptionMenu(
            parent,
            self.output_format,
            "png",
            "jpeg",
            "webp"
        )
        format_menu.configure(
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            highlightthickness=0,
            width=10,
            anchor="w"
        )
        format_menu.grid(row=2, column=1, sticky="w", pady=3)

        tk.Label(
            parent,
            text="Suffix",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=3, column=0, sticky="w", pady=3)

        tk.Entry(
            parent,
            textvariable=self.output_suffix,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white"
        ).grid(row=3, column=1, sticky="ew", pady=3)

    def _build_outpaint_section(self, parent: ttk.LabelFrame) -> None:
        """Build outpaint controls section."""
        parent.columnconfigure(1, weight=1)

        # Warning label about zoom behavior
        warning_frame = tk.Frame(parent, bg="#B43232", relief="solid", borderwidth=1)
        warning_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        tk.Label(
            warning_frame,
            text="⚠ Zoom % SHRINKS the image (30 = shrink to 30%). Use Expand % instead!",
            bg="#B43232",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            wraplength=400,
            justify="left"
        ).pack(padx=8, pady=4)

        # Zoom control
        tk.Label(
            parent,
            text="Zoom % (shrink)",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=1, column=0, sticky="w", pady=3)

        tk.Scale(
            parent,
            from_=0,
            to=90,
            orient=tk.HORIZONTAL,
            variable=self.zoom_out_percentage,
            showvalue=True,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            highlightthickness=0,
            troughcolor=COLORS["bg_input"],
        ).grid(row=1, column=1, sticky="ew", pady=3)

        # Expand mode selector
        tk.Label(
            parent,
            text="Expand mode",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=2, column=0, sticky="w", pady=3)

        mode_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        mode_frame.grid(row=2, column=1, sticky="w", pady=3)

        tk.Radiobutton(
            mode_frame,
            text="Percentage",
            variable=self.expand_mode,
            value="percentage",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Radiobutton(
            mode_frame,
            text="Pixels",
            variable=self.expand_mode,
            value="pixels",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_light"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["text_light"],
        ).pack(side=tk.LEFT)

        # Percentage expansion control
        tk.Label(
            parent,
            text="Expand %",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=3, column=0, sticky="w", pady=3)

        self._expand_pct_spin = tk.Spinbox(
            parent,
            from_=0,
            to=200,
            textvariable=self.expand_percentage,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white",
            width=8,
        )
        self._expand_pct_spin.grid(row=3, column=1, sticky="w", pady=3)

        # Helper function for pixel spinbox creation
        def create_spinbox(var: tk.IntVar) -> tk.Spinbox:
            return tk.Spinbox(
                parent,
                from_=0,
                to=700,
                textvariable=var,
                bg=COLORS["bg_input"],
                fg=COLORS["text_light"],
                insertbackground="white",
                width=8,
            )

        # Pixel expansion controls
        tk.Label(
            parent,
            text="Expand left (px)",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=4, column=0, sticky="w", pady=3)
        w = create_spinbox(self.expand_left)
        w.grid(row=4, column=1, sticky="w", pady=3)
        self._expand_px_spins.append(w)

        tk.Label(
            parent,
            text="Expand right (px)",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=5, column=0, sticky="w", pady=3)
        w = create_spinbox(self.expand_right)
        w.grid(row=5, column=1, sticky="w", pady=3)
        self._expand_px_spins.append(w)

        tk.Label(
            parent,
            text="Expand top (px)",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=6, column=0, sticky="w", pady=3)
        w = create_spinbox(self.expand_top)
        w.grid(row=6, column=1, sticky="w", pady=3)
        self._expand_px_spins.append(w)

        tk.Label(
            parent,
            text="Expand bottom (px)",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=7, column=0, sticky="w", pady=3)
        w = create_spinbox(self.expand_bottom)
        w.grid(row=7, column=1, sticky="w", pady=3)
        self._expand_px_spins.append(w)

        # Num images
        tk.Label(
            parent,
            text="Num images",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=8, column=0, sticky="w", pady=3)

        tk.Spinbox(
            parent,
            from_=1,
            to=4,
            textvariable=self.num_images,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white",
            width=8,
        ).grid(row=8, column=1, sticky="w", pady=3)

        # Prompt
        tk.Label(
            parent,
            text="Prompt",
            width=14,
            anchor="w",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_dim"],
            font=("Segoe UI", 9)
        ).grid(row=9, column=0, sticky="w", pady=3)

        tk.Entry(
            parent,
            textvariable=self.prompt,
            bg=COLORS["bg_input"],
            fg=COLORS["text_light"],
            insertbackground="white"
        ).grid(row=9, column=1, sticky="ew", pady=3)

    def _browse_workflow(self) -> None:
        p = filedialog.askopenfilename(title="Select workflow JSON", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if p:
            self.comfyui_workflow_path.set(p)

    def _browse_output_folder(self) -> None:
        p = filedialog.askdirectory(title="Select output folder")
        if p:
            self.output_folder.set(p)

    def _emit_changed(self) -> None:
        cfg = self.get_config()
        self._on_config_changed(cfg)

    def get_config(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in self._vars.items():
            try:
                val = v.get()
                # Handle empty strings for IntVar
                if isinstance(v, tk.IntVar) and val == "":
                    val = 0
                out[k] = val
            except Exception:
                # If getting value fails, use default based on type
                if isinstance(v, tk.IntVar):
                    out[k] = 0
                elif isinstance(v, tk.BooleanVar):
                    out[k] = False
                else:
                    out[k] = ""

        # Keep types stable for JSON
        for k in (
            "zoom_out_percentage",
            "expand_left",
            "expand_right",
            "expand_top",
            "expand_bottom",
            "num_images",
        ):
            try:
                val = out.get(k, 0)
                # Handle empty string or None
                if val == "" or val is None:
                    out[k] = 0
                else:
                    out[k] = int(val)
            except Exception:
                out[k] = 0

        out["use_source_folder"] = bool(out.get("use_source_folder"))
        out["enable_safety_checker"] = bool(out.get("enable_safety_checker"))
        return out
