# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python desktop application being transformed from a video generation tool (Kling UI) into an **image outpainting tool** with dual backend support:
1. **fal.ai Cloud API** - Fast, paid, always available (`fal-ai/image-apps-v2/outpaint`)
2. **ComfyUI Local** - Free, slower, requires local GPU with FLUX Fill model

The transformation is tracked via Task Master in `.taskmaster/tasks/tasks.json`.

## Commands

### Setup & Run
```bash
# First-time setup (creates venv, installs deps)
run_kling_ui.bat

# Manual setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Run CLI interface
python kling_automation_ui.py

# Run GUI directly
python -c "from kling_gui import KlingGUIWindow; KlingGUIWindow().run()"
```

### Testing
```bash
# After transformation, tests will be in tests/
python -m pytest tests/

# Run single test file
python -m pytest tests/test_backends.py -v
```

### Build Executable
```bash
# Build with PyInstaller
build_exe.bat
# Output: dist/KlingUI.exe
```

### Task Master
```bash
# View all tasks
task-master list

# Get next task
task-master next

# Parse PRD to generate tasks
task-master parse-prd --input=.taskmaster/docs/prd.txt
```

## Architecture

### Current Structure (Pre-Transformation)
```
kling_automation_ui.py    # CLI entry point, menu system, config management
kling_generator_falai.py  # FalAIKlingGenerator class - fal.ai API integration
kling_gui/                # Tkinter GUI package
├── main_window.py        # Main window assembly, drag-drop handling
├── config_panel.py       # Model/prompt settings UI
├── queue_manager.py      # QueueItem, batch processing state
├── drop_zone.py          # Drag-drop widget (tkinterdnd2)
├── log_display.py        # Color-coded log output
└── video_looper.py       # FFmpeg ping-pong loop wrapper
path_utils.py             # PyInstaller compatibility (get_app_dir, get_config_path)
```

### Target Structure (Post-Transformation per PRD)
```
outpaint_ui.py            # Renamed CLI entry point
outpaint_generator.py     # Unified generator routing to backends
backends/
├── __init__.py           # Backend ABC, get_backend() factory
├── falai_backend.py      # FalAIOutpaintBackend
└── comfyui_backend.py    # ComfyUIOutpaintBackend
outpaint_gui/             # Renamed GUI package
comfyui_workflows/
└── flux_outpaint.json    # ComfyUI workflow template (created in P0.1)
tests/
├── test_backends.py
├── test_config.py
└── fixtures/             # Sample test images
```

### Key Patterns

**Config Management**: JSON config at `kling_config.json` (→ `outpaint_config.json`) with prompt slots, model selection, output preferences. Loaded via `path_utils.get_config_path()`.

**Generator Pattern**: `FalAIKlingGenerator` class handles image upload → fal.ai queue → poll → download. Progress reported via `set_progress_callback()`.

**GUI Threading**: Queue processing runs in background thread. GUI updates via Tkinter's `after()` method for thread safety.

**Frozen Exe Support**: `path_utils.py` abstracts paths for PyInstaller. Always use `get_app_dir()`, `get_config_path()`, etc.

## Key Implementation Notes

### fal.ai API Flow
1. Upload image to freeimage.host (base64 JPEG, max 1200px)
2. POST to `https://queue.fal.run/{endpoint}` with image_url
3. Poll status until complete
4. Download result from returned URL

### ComfyUI Integration (Target)
1. Detect installation via `COMFYUI_PATH` env or search common paths (`G:/pinokio/api/comfy.git/app`)
2. Check availability via `/system_stats` (VRAM) and `/object_info` (FLUX nodes)
3. Upload image via `/upload/image`
4. Inject params into workflow JSON by `class_type`, not node ID
5. Queue via `/prompt`, poll `/history/{prompt_id}`

### Backend Abstraction (Target)
```python
class Backend(ABC):
    @abstractmethod
    def outpaint(self, image_path: str, params: dict, progress_callback=None) -> list[str]:
        pass

def get_backend(name: str, config: OutpaintConfig) -> Backend:
    # Factory returns FalAIOutpaintBackend or ComfyUIOutpaintBackend
```

### Outpaint Parameters (Target)
- `zoom_out_percentage`: 0-90% (default 30%)
- `expand_left/right/top/bottom`: 0-700px each
- `num_images`: 1-4 outputs per input
- `prompt`: Optional text guidance
- `output_format`: png, jpeg, webp

## Configuration

Settings stored in `kling_config.json`:
- `falai_api_key`: Required for cloud backend
- `use_source_folder`: Save outputs alongside source images
- `current_model`: Active fal.ai endpoint
- `saved_prompts`: 3 prompt slots with quick switching
- `negative_prompts`: Model-aware negative prompts
- `verbose_logging`: Detailed API logs

## Dependencies

Core: `requests`, `Pillow`, `rich`
GUI: `tkinterdnd2` (drag-drop)
Optional: `selenium`, `webdriver-manager` (balance tracking)
Target: `pydantic` (config validation)

## Windows Notes

The batch launcher handles venv creation and cleans up the `nul` file bug (Windows Bash creates problematic `nul` files).
