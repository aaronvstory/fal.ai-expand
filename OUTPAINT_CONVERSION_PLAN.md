# Plan: Transform fal.ai Video Generator to Image Outpainting App

## Summary
Convert the existing fal.ai image-to-video batch processing app into an image outpainting tool with **dual backend support**: fal.ai (cloud) and ComfyUI (local).

**Current**: `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` → Outputs: `.mp4` videos
**Target**: `fal-ai/image-apps-v2/outpaint` OR `ComfyUI FLUX Fill` → Outputs: `.png` images

## User Decisions
- **Rename files**: Yes - `kling_*` → `outpaint_*`
- **Default zoom**: 30%
- **Output naming**: `{name}-expanded.png` (configurable suffix)
- **Multi-output**: Yes - support 1-4 images per input
- **Backend toggle**: Yes - user can switch between fal.ai and ComfyUI
- **ComfyUI path**: `G:\pinokio\api\comfy.git\app` (dynamic detection)

---

## Robustness Improvements (v2)

This plan incorporates 7 critical fixes for production reliability:

### Fix 1: Dynamic ComfyUI Path Detection
No hardcoded paths. Auto-detect Pinokio and standard installations:

```python
# backends/comfyui_backend.py
import os
from pathlib import Path

def detect_comfyui_path() -> Path:
    """Auto-detect ComfyUI installation across platforms"""
    candidates = [
        # User-specified (highest priority)
        os.environ.get("COMFYUI_PATH"),

        # Pinokio installations (common)
        Path("G:/pinokio/api/comfy.git/app"),
        Path("C:/pinokio/api/comfy.git/app"),
        Path(os.path.expanduser("~/pinokio/api/comfy.git/app")),

        # Standard installations
        Path("C:/AI/ComfyUI"),
        Path("D:/AI/ComfyUI"),
        Path(os.path.expanduser("~/ComfyUI")),
        Path("/opt/ComfyUI"),

        # Portable
        Path("./ComfyUI"),
    ]

    for path in candidates:
        if path and Path(path).exists():
            # Verify it's actually ComfyUI
            main_py = Path(path) / "main.py"
            comfyui_marker = Path(path) / "comfy" / "__init__.py"
            if main_py.exists() or comfyui_marker.exists():
                return Path(path)

    return None
```

### Fix 2: Robust Node Class-Type Matching
Never use fragile node IDs. Match by `class_type`:

```python
def find_node_by_class(workflow: dict, class_type: str) -> tuple[str, dict]:
    """Find node by class_type, returns (node_id, node_data)"""
    for node_id, node in workflow.items():
        if node.get("class_type") == class_type:
            return node_id, node
    return None, None

def find_all_nodes_by_class(workflow: dict, class_types: list) -> list:
    """Find all nodes matching any of the class_types"""
    return [
        (node_id, node) for node_id, node in workflow.items()
        if node.get("class_type") in class_types
    ]
```

### Fix 3: Model Availability Check
Verify required models before starting generation:

```python
def check_comfyui_ready(self) -> tuple[bool, str]:
    """Check if ComfyUI has required models for FLUX outpainting"""
    try:
        # Check server running
        response = requests.get(f"{self.url}/system_stats", timeout=5)
        if response.status_code != 200:
            return False, "ComfyUI server not responding"

        stats = response.json()

        # Check VRAM
        vram_gb = stats.get("system", {}).get("vram_total", 0) / (1024**3)
        if vram_gb < 12:
            return False, f"FLUX requires 12GB+ VRAM (detected: {vram_gb:.1f}GB)"

        # Check object_info for required node types
        obj_response = requests.get(f"{self.url}/object_info", timeout=10)
        available_nodes = set(obj_response.json().keys())

        required_nodes = {"LoadImage", "VAEEncode", "VAEDecode", "KSampler"}
        flux_nodes = {"UNETLoader", "DualCLIPLoader"}  # FLUX-specific

        missing = required_nodes - available_nodes
        if missing:
            return False, f"Missing required nodes: {missing}"

        if not flux_nodes & available_nodes:
            return False, "FLUX nodes not available - install FLUX models via ComfyUI Manager"

        return True, "ComfyUI ready with FLUX support"

    except requests.Timeout:
        return False, "ComfyUI server timeout - is it running?"
    except Exception as e:
        return False, f"ComfyUI check failed: {e}"
```

### Fix 4: Backend-Aware Worker Limits
Cloud can handle 5 concurrent, local GPU only 2:

```python
# outpaint_gui/queue_manager.py
BACKEND_WORKER_LIMITS = {
    "falai": 5,      # Cloud API handles concurrency
    "comfyui": 2,    # Local GPU - 2 max to avoid OOM
}

class QueueManager:
    def __init__(self, backend: str = "falai"):
        self.backend = backend
        self.max_workers = BACKEND_WORKER_LIMITS.get(backend, 3)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def update_backend(self, new_backend: str):
        """Switch backend and adjust worker pool"""
        if new_backend != self.backend:
            self.backend = new_backend
            old_executor = self.executor
            self.max_workers = BACKEND_WORKER_LIMITS.get(new_backend, 3)
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
            old_executor.shutdown(wait=False)
```

### Fix 5: Config Schema Validation
Validate on load to catch errors early:

```python
# config_schema.py
from dataclasses import dataclass, field
from typing import Literal
import json

@dataclass
class OutpaintConfig:
    # Backend
    backend: Literal["falai", "comfyui"] = "falai"
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_path: str = ""  # Auto-detected if empty
    comfyui_workflow: str = "flux_outpaint.json"
    falai_api_key: str = ""

    # Output
    output_folder: str = ""
    use_source_folder: bool = True
    output_format: Literal["png", "jpeg", "webp"] = "png"
    output_suffix: str = "-expanded"

    # Outpaint params
    zoom_out_percentage: int = 30
    expand_left: int = 0
    expand_right: int = 0
    expand_top: int = 0
    expand_bottom: int = 0
    num_images: int = 1
    prompt: str = ""
    enable_safety_checker: bool = True

    # Behavior
    duplicate_detection: bool = True
    allow_reprocess: bool = True
    delay_between_generations: float = 1.0

    def validate(self) -> list[str]:
        """Return list of validation errors"""
        errors = []

        if self.backend == "falai" and not self.falai_api_key:
            errors.append("Fal.ai API key required for cloud backend")

        if not 0 <= self.zoom_out_percentage <= 90:
            errors.append(f"zoom_out_percentage must be 0-90, got {self.zoom_out_percentage}")

        for attr in ["expand_left", "expand_right", "expand_top", "expand_bottom"]:
            val = getattr(self, attr)
            if not 0 <= val <= 700:
                errors.append(f"{attr} must be 0-700, got {val}")

        if not 1 <= self.num_images <= 4:
            errors.append(f"num_images must be 1-4, got {self.num_images}")

        if self.output_format not in ["png", "jpeg", "webp"]:
            errors.append(f"Invalid output_format: {self.output_format}")

        return errors

    @classmethod
    def load(cls, path: str) -> "OutpaintConfig":
        with open(path) as f:
            data = json.load(f)
        config = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        errors = config.validate()
        if errors:
            raise ValueError(f"Config validation failed: {errors}")
        return config
```

### Fix 6: UI Backend Toggle with Health Check
Immediate feedback when switching backends:

```python
# outpaint_gui/config_panel.py
def _on_backend_change(self):
    """Handle backend toggle with immediate health check"""
    backend = self.backend_var.get()

    if backend == "comfyui":
        # Immediate connection test
        self._update_status("Checking ComfyUI...", "yellow")

        url = self.comfyui_url_var.get()
        ready, message = self.comfyui_backend.check_comfyui_ready()

        if not ready:
            self._update_status(f"⚠ {message}", "red")

            # Offer to switch back or start ComfyUI
            if "VRAM" in message:
                result = messagebox.askyesno(
                    "Insufficient VRAM",
                    f"{message}\n\nFLUX models require 12GB+ VRAM.\n\n"
                    "Switch back to Fal.ai (cloud)?",
                    icon="warning"
                )
                if result:
                    self.backend_var.set("falai")
                    self._on_backend_change()
                    return
            elif "not responding" in message.lower():
                messagebox.showwarning(
                    "ComfyUI Not Running",
                    f"Start ComfyUI first:\n\n"
                    f"  cd {self.comfyui_path}\n"
                    f"  python main.py\n\n"
                    f"Then try again."
                )
        else:
            self._update_status(f"✓ {message}", "green")

    # Update worker limit display
    worker_limit = BACKEND_WORKER_LIMITS.get(backend, 3)
    self.worker_label.configure(text=f"Workers: {worker_limit}")

    # Enable/disable backend-specific settings
    self._update_settings_visibility(backend)
```

### Fix 7: Graceful Fallback During Batch
Offer to switch to fal.ai after repeated ComfyUI failures:

```python
# outpaint_gui/queue_manager.py
class QueueManager:
    def __init__(self):
        self.consecutive_failures = 0
        self.failure_threshold = 3

    def on_task_complete(self, success: bool):
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

            if (self.backend == "comfyui" and
                self.consecutive_failures >= self.failure_threshold):
                self._offer_fallback()

    def _offer_fallback(self):
        """Offer to switch to fal.ai after repeated failures"""
        remaining = self.get_pending_count()

        result = messagebox.askyesno(
            "ComfyUI Having Issues",
            f"ComfyUI failed {self.consecutive_failures} times in a row.\n\n"
            f"Remaining items: {remaining}\n\n"
            f"Switch to Fal.ai (cloud) for remaining items?\n"
            f"(~${remaining * 0.07:.2f} estimated cost)",
            icon="warning"
        )

        if result:
            self.switch_backend("falai")
            self.consecutive_failures = 0
```

---

## Architecture: Hybrid Backend System

```
┌─────────────────────────────────────────────────────────────────┐
│                    OUTPAINT TOOL (Your App)                     │
├─────────────────────────────────────────────────────────────────┤
│  UI Layer: Tkinter GUI / CLI                                    │
│  - Drag-and-drop, file selection, queue management              │
│  - Backend selector (fal.ai / ComfyUI toggle)                   │
├─────────────────────────────────────────────────────────────────┤
│  OutpaintGenerator (Unified Interface)                          │
│  - Common parameters: zoom_out_%, expand_*, prompt, num_images  │
│  - Routes to selected backend                                   │
├─────────────────┬───────────────────────────────────────────────┤
│  FalAIBackend   │  ComfyUIBackend                               │
│  - Cloud API    │  - Local API (http://127.0.0.1:8188)          │
│  - $0.035/MP    │  - Free (local GPU)                           │
│  - 10-30 sec    │  - 60-120 sec (RTX 4090)                      │
└─────────────────┴───────────────────────────────────────────────┘
```

---

## Files to Create/Rename

| Old Name | New Name | Notes |
|----------|----------|-------|
| `kling_generator_falai.py` | `outpaint_generator.py` | Unified interface |
| - | `backends/falai_backend.py` | fal.ai API wrapper |
| - | `backends/comfyui_backend.py` | ComfyUI API wrapper |
| - | `backends/__init__.py` | Backend exports |
| - | `comfyui_workflows/flux_outpaint.json` | ComfyUI workflow template |
| `kling_automation_ui.py` | `outpaint_ui.py` | CLI entry |
| `kling_gui/` | `outpaint_gui/` | GUI package |
| `kling_config.json` | `outpaint_config.json` | Config with backend option |
| `kling_history.json` | `outpaint_history.json` | History |
| `run_kling_ui.bat` | `run_outpaint_ui.bat` | Launcher |

---

## Implementation Steps

### Step 1: Create Backend System (`backends/`)

#### 1a. `backends/__init__.py`
```python
from .falai_backend import FalAIOutpaintBackend
from .comfyui_backend import ComfyUIOutpaintBackend

__all__ = ['FalAIOutpaintBackend', 'ComfyUIOutpaintBackend']
```

#### 1b. `backends/falai_backend.py`
Extract fal.ai-specific code from current `kling_generator_falai.py`:

```python
class FalAIOutpaintBackend:
    """fal.ai cloud backend for outpainting"""

    def __init__(self, api_key: str, verbose: bool = True):
        self.api_key = api_key
        self.verbose = verbose
        self.base_url = "https://queue.fal.run/fal-ai/image-apps-v2/outpaint"
        self.freeimage_key = "6d207e02198a847aa98d0a2a901485a5"
        self._progress_callback = None

    def outpaint(self, image_path: str, output_folder: str,
                 zoom_out_percentage: int = 30,
                 expand_left: int = 0, expand_right: int = 0,
                 expand_top: int = 0, expand_bottom: int = 0,
                 num_images: int = 1, prompt: str = "",
                 enable_safety_checker: bool = True,
                 output_format: str = "png",
                 output_suffix: str = "-expanded") -> list[str]:
        """
        Process single image through fal.ai
        Returns: List of output file paths
        """
        # 1. Upload to freeimage.host
        image_url = self._upload_image(image_path)

        # 2. Submit to fal.ai
        payload = {
            "image_url": image_url,
            "zoom_out_percentage": zoom_out_percentage,
            "expand_left": expand_left,
            "expand_right": expand_right,
            "expand_top": expand_top,
            "expand_bottom": expand_bottom,
            "num_images": num_images,
            "enable_safety_checker": enable_safety_checker,
            "output_format": output_format
        }
        if prompt:
            payload["prompt"] = prompt

        # 3. Poll for completion
        # 4. Download result images
        # 5. Save to output folder
        # Returns list of saved file paths
```

#### 1c. `backends/comfyui_backend.py`
New ComfyUI local backend with robust path detection and node matching:

```python
import requests
import json
import uuid
import time
import os
from pathlib import Path

class ComfyUIOutpaintBackend:
    """ComfyUI local backend for outpainting"""

    def __init__(self, url: str = "http://127.0.0.1:8188",
                 comfyui_path: str = None, verbose: bool = True):
        self.url = url
        self.verbose = verbose
        self.client_id = str(uuid.uuid4())
        self._progress_callback = None
        self.workflow_template = None

        # Auto-detect ComfyUI path if not provided
        self.comfyui_path = Path(comfyui_path) if comfyui_path else self._detect_comfyui_path()
        if self.comfyui_path:
            self.output_dir = self.comfyui_path / "output"
        else:
            self.output_dir = None

    def _detect_comfyui_path(self) -> Path:
        """Auto-detect ComfyUI installation"""
        candidates = [
            os.environ.get("COMFYUI_PATH"),
            Path("G:/pinokio/api/comfy.git/app"),  # User's installation
            Path("C:/pinokio/api/comfy.git/app"),
            Path(os.path.expanduser("~/pinokio/api/comfy.git/app")),
            Path("C:/AI/ComfyUI"),
            Path("D:/AI/ComfyUI"),
            Path(os.path.expanduser("~/ComfyUI")),
        ]
        for path in candidates:
            if path and Path(path).exists():
                main_py = Path(path) / "main.py"
                if main_py.exists():
                    self._report_progress(f"Detected ComfyUI at: {path}")
                    return Path(path)
        return None

    def is_available(self) -> bool:
        """Check if ComfyUI server is running"""
        try:
            response = requests.get(f"{self.url}/system_stats", timeout=5)
            return response.status_code == 200
        except:
            return False

    def check_ready(self) -> tuple[bool, str]:
        """Full health check including VRAM and models"""
        try:
            response = requests.get(f"{self.url}/system_stats", timeout=5)
            if response.status_code != 200:
                return False, "ComfyUI server not responding"

            stats = response.json()
            vram_gb = stats.get("system", {}).get("vram_total", 0) / (1024**3)
            if vram_gb < 12:
                return False, f"FLUX requires 12GB+ VRAM (detected: {vram_gb:.1f}GB)"

            return True, f"ComfyUI ready ({vram_gb:.1f}GB VRAM)"
        except requests.Timeout:
            return False, "ComfyUI server timeout"
        except Exception as e:
            return False, f"Check failed: {e}"

    def load_workflow(self, workflow_path: str = None):
        """Load workflow JSON template"""
        if workflow_path is None:
            workflow_path = Path(__file__).parent.parent / "comfyui_workflows" / "flux_outpaint.json"
        with open(workflow_path) as f:
            self.workflow_template = json.load(f)

    def outpaint(self, image_path: str, output_folder: str,
                 zoom_out_percentage: int = 30,
                 expand_left: int = 0, expand_right: int = 0,
                 expand_top: int = 0, expand_bottom: int = 0,
                 num_images: int = 1, prompt: str = "",
                 output_format: str = "png",
                 output_suffix: str = "-expanded",
                 **kwargs) -> list[str]:
        """
        Process single image through local ComfyUI
        Returns: List of output file paths
        """
        if not self.workflow_template:
            self.load_workflow()

        # 1. Upload image to ComfyUI
        image_name = self._upload_image(image_path)

        # 2. Prepare workflow with parameters
        workflow = self._prepare_workflow(
            image_name=image_name,
            zoom_out_percentage=zoom_out_percentage,
            expand_left=expand_left,
            expand_right=expand_right,
            expand_top=expand_top,
            expand_bottom=expand_bottom,
            prompt=prompt or "natural scene extension, seamless blend",
            num_images=num_images
        )

        # 3. Queue prompt
        prompt_id = self._queue_prompt(workflow)

        # 4. Wait for completion with progress updates
        comfy_outputs = self._wait_for_completion(prompt_id)

        # 5. Copy outputs to target folder with proper naming
        return self._save_outputs(
            comfy_outputs, image_path, output_folder,
            output_suffix, output_format
        )

    def _upload_image(self, image_path: str) -> str:
        """Upload image to ComfyUI input folder"""
        with open(image_path, 'rb') as f:
            response = requests.post(
                f"{self.url}/upload/image",
                files={'image': (Path(image_path).name, f, 'image/png')}
            )
        result = response.json()
        self._report_progress(f"Uploaded to ComfyUI: {result['name']}")
        return result['name']

    def _prepare_workflow(self, image_name, zoom_out_percentage,
                         expand_left, expand_right, expand_top, expand_bottom,
                         prompt, num_images) -> dict:
        """Inject parameters into workflow template using robust class_type matching"""
        import copy
        workflow = copy.deepcopy(self.workflow_template)

        # Helper for robust node finding
        def find_nodes_by_class(class_types):
            return [(nid, n) for nid, n in workflow.items()
                    if n.get('class_type') in class_types]

        def set_input_safe(node, key, value):
            """Set input only if key exists in node"""
            if 'inputs' in node and key in node.get('inputs', {}):
                node['inputs'][key] = value
                return True
            return False

        # LoadImage - set source image
        for node_id, node in find_nodes_by_class(['LoadImage']):
            set_input_safe(node, 'image', image_name)

        # Outpaint/expansion parameters - try multiple node types
        pad_classes = ['ImagePadForOutpaint', 'OutpaintPad', 'ImagePad',
                       'InpaintModelConditioning', 'ImageBlend']
        for node_id, node in find_nodes_by_class(pad_classes):
            set_input_safe(node, 'left', expand_left)
            set_input_safe(node, 'right', expand_right)
            set_input_safe(node, 'top', expand_top)
            set_input_safe(node, 'bottom', expand_bottom)

        # Zoom/scale - multiple possible node types
        scale_classes = ['ImageScale', 'ImageScaleBy', 'ImageResize']
        for node_id, node in find_nodes_by_class(scale_classes):
            scale = 1.0 - (zoom_out_percentage / 100.0)
            set_input_safe(node, 'scale', scale)
            set_input_safe(node, 'scale_by', scale)

        # Prompt - find positive prompt nodes (avoid negative)
        prompt_classes = ['CLIPTextEncode', 'CLIPTextEncodeSDXL', 'ConditioningCombine']
        for node_id, node in find_nodes_by_class(prompt_classes):
            # Skip if this looks like a negative prompt node
            if 'negative' in node_id.lower():
                continue
            set_input_safe(node, 'text', prompt)

        # Batch size - find sampler or latent nodes
        batch_classes = ['EmptyLatentImage', 'KSampler', 'KSamplerAdvanced',
                         'SamplerCustom', 'BasicScheduler']
        for node_id, node in find_nodes_by_class(batch_classes):
            set_input_safe(node, 'batch_size', num_images)

        return workflow

    def _queue_prompt(self, workflow: dict) -> str:
        """Submit workflow to ComfyUI queue"""
        response = requests.post(
            f"{self.url}/prompt",
            json={"prompt": workflow, "client_id": self.client_id}
        )
        prompt_id = response.json()['prompt_id']
        self._report_progress(f"Queued prompt: {prompt_id}")
        return prompt_id

    def _wait_for_completion(self, prompt_id: str, timeout: int = 600) -> list:
        """Poll until generation completes"""
        start_time = time.time()
        last_progress = 0

        while time.time() - start_time < timeout:
            # Check history
            response = requests.get(f"{self.url}/history/{prompt_id}")
            history = response.json()

            if prompt_id in history:
                status = history[prompt_id]
                if status.get('status', {}).get('completed', False):
                    self._report_progress("Generation completed!")
                    return self._extract_outputs(status.get('outputs', {}))

            # Check progress via queue
            queue_response = requests.get(f"{self.url}/queue")
            queue = queue_response.json()

            # Report progress
            running = queue.get('queue_running', [])
            for item in running:
                if item[1] == prompt_id:
                    # Progress info if available
                    progress = item[3].get('value', 0) if len(item) > 3 else 0
                    if progress > last_progress:
                        self._report_progress(f"Progress: {progress}%")
                        last_progress = progress

            time.sleep(1)

        raise TimeoutError(f"ComfyUI generation timed out after {timeout}s")

    def _extract_outputs(self, outputs: dict) -> list:
        """Parse ComfyUI output structure"""
        output_files = []
        for node_id, node_output in outputs.items():
            if 'images' in node_output:
                for img in node_output['images']:
                    output_files.append({
                        'filename': img['filename'],
                        'subfolder': img.get('subfolder', ''),
                        'type': img.get('type', 'output')
                    })
        return output_files

    def _save_outputs(self, comfy_outputs: list, source_path: str,
                     output_folder: str, suffix: str, format: str) -> list[str]:
        """Copy ComfyUI outputs to target folder with proper naming"""
        saved_paths = []
        stem = Path(source_path).stem

        # Use auto-detected ComfyUI output folder (not hardcoded!)
        if not self.output_dir or not self.output_dir.exists():
            raise RuntimeError(
                f"ComfyUI output directory not found. "
                f"Detected path: {self.comfyui_path}, "
                f"Expected output at: {self.output_dir}"
            )

        for idx, out in enumerate(comfy_outputs):
            src = self.output_dir / out['subfolder'] / out['filename']

            if not src.exists():
                self._report_progress(f"Warning: Output not found: {src}", "warning")
                continue

            if len(comfy_outputs) == 1:
                dst_name = f"{stem}{suffix}.{format}"
            else:
                dst_name = f"{stem}{suffix}_{idx+1}.{format}"

            dst = Path(output_folder) / dst_name

            # Copy file
            import shutil
            shutil.copy2(src, dst)
            saved_paths.append(str(dst))
            self._report_progress(f"Saved: {dst_name}")

        return saved_paths

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def _report_progress(self, message: str, level: str = "info"):
        if self._progress_callback:
            self._progress_callback(message, level)
        elif self.verbose:
            print(f"[ComfyUI] {message}")
```

### Step 2: Create `outpaint_generator.py` (Unified Interface)

```python
import logging
from pathlib import Path
from typing import Optional, List
from backends import FalAIOutpaintBackend, ComfyUIOutpaintBackend

logger = logging.getLogger(__name__)

class OutpaintGenerator:
    """Unified outpainting generator with backend selection"""

    BACKENDS = {
        "falai": FalAIOutpaintBackend,
        "comfyui": ComfyUIOutpaintBackend
    }

    def __init__(self,
                 backend: str = "falai",
                 api_key: str = None,
                 comfyui_url: str = "http://127.0.0.1:8188",
                 verbose: bool = True):
        """
        Args:
            backend: "falai" or "comfyui"
            api_key: fal.ai API key (required for falai backend)
            comfyui_url: ComfyUI server URL (for comfyui backend)
            verbose: Enable logging
        """
        self.backend_name = backend
        self.verbose = verbose
        self._progress_callback = None

        # Initialize selected backend
        if backend == "falai":
            if not api_key:
                raise ValueError("API key required for fal.ai backend")
            self.backend = FalAIOutpaintBackend(api_key=api_key, verbose=verbose)
        elif backend == "comfyui":
            self.backend = ComfyUIOutpaintBackend(url=comfyui_url, verbose=verbose)
            if not self.backend.is_available():
                logger.warning("ComfyUI not available at %s", comfyui_url)
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def set_progress_callback(self, callback):
        self._progress_callback = callback
        self.backend.set_progress_callback(callback)

    def check_backend_available(self) -> bool:
        """Check if selected backend is available"""
        if self.backend_name == "falai":
            return True  # Cloud always available if API key valid
        elif self.backend_name == "comfyui":
            return self.backend.is_available()
        return False

    def generate(self, image_path: str, output_folder: str = None,
                 zoom_out_percentage: int = 30,
                 expand_left: int = 0, expand_right: int = 0,
                 expand_top: int = 0, expand_bottom: int = 0,
                 num_images: int = 1, prompt: str = "",
                 enable_safety_checker: bool = True,
                 output_format: str = "png",
                 output_suffix: str = "-expanded",
                 use_source_folder: bool = False,
                 skip_duplicate_check: bool = False) -> Optional[List[str]]:
        """
        Generate outpainted image(s)

        Returns:
            List of output file paths, or None if failed
        """
        # Determine output folder
        if use_source_folder:
            actual_output_folder = str(Path(image_path).parent)
        elif output_folder:
            actual_output_folder = output_folder
        else:
            actual_output_folder = str(Path.home() / "Downloads")

        # Check for duplicates
        if not skip_duplicate_check:
            if self._check_duplicate_exists(image_path, actual_output_folder,
                                           output_suffix, output_format):
                if self.verbose:
                    logger.info(f"Skipping {Path(image_path).name} - already exists")
                return None

        try:
            # Call backend
            return self.backend.outpaint(
                image_path=image_path,
                output_folder=actual_output_folder,
                zoom_out_percentage=zoom_out_percentage,
                expand_left=expand_left,
                expand_right=expand_right,
                expand_top=expand_top,
                expand_bottom=expand_bottom,
                num_images=num_images,
                prompt=prompt,
                enable_safety_checker=enable_safety_checker,
                output_format=output_format,
                output_suffix=output_suffix
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return None

    def _check_duplicate_exists(self, image_path: str, output_folder: str,
                               suffix: str, format: str) -> bool:
        """Check if output already exists"""
        stem = Path(image_path).stem
        output_path = Path(output_folder) / f"{stem}{suffix}.{format}"
        return output_path.exists()
```

### Step 3: Create `outpaint_config.json`

```json
{
  "backend": "falai",

  "comfyui_url": "http://127.0.0.1:8188",
  "comfyui_path": "",
  "comfyui_workflow": "flux_outpaint.json",

  "falai_api_key": "<your-existing-key>",

  "output_folder": "",
  "use_source_folder": true,
  "verbose_logging": true,
  "verbose_gui_mode": true,
  "duplicate_detection": true,

  "zoom_out_percentage": 30,
  "expand_left": 0,
  "expand_right": 0,
  "expand_top": 0,
  "expand_bottom": 0,
  "num_images": 1,
  "enable_safety_checker": true,
  "output_format": "png",
  "output_suffix": "-expanded",
  "prompt": "",

  "allow_reprocess": true,
  "reprocess_mode": "increment",
  "folder_filter_pattern": "",
  "folder_match_mode": "partial",
  "delay_between_generations": 1,

  "window_geometry": "1160x1024+378+1",
  "sash_dropzone": 310,
  "sash_queue": 185,
  "sash_log": 138
}
```

**Note:** `comfyui_path` is auto-detected if empty. Candidates searched in order:
1. `COMFYUI_PATH` environment variable
2. `G:/pinokio/api/comfy.git/app` (user's Pinokio installation)
3. `C:/pinokio/api/comfy.git/app`
4. `C:/AI/ComfyUI`, `D:/AI/ComfyUI`
5. `~/ComfyUI`

### Step 4: Update GUI - Backend Selector

#### 4a. `outpaint_gui/config_panel.py` - Add Backend Section

```
┌─────────────────────────────────────────────────────────────────┐
│ BACKEND SELECTION                                               │
├─────────────────────────────────────────────────────────────────┤
│ ◉ Fal.ai (Cloud)          ○ ComfyUI (Local)                    │
│   - $0.035/megapixel        - Free (uses your GPU)             │
│   - 10-30 seconds           - 60-120 seconds                   │
│   - Always available        - Requires ComfyUI running         │
│                                                                 │
│ ┌─ Fal.ai Settings ────────────────────────────────────────────┐│
│ │ API Key: [************************] [Test]                   ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│ ┌─ ComfyUI Settings ───────────────────────────────────────────┐│
│ │ Server URL: [http://127.0.0.1:8188] [Test Connection]        ││
│ │ Status: ● Connected / ○ Not Running                          ││
│ │ Workflow: [flux_outpaint.json ▼]                             ││
│ └──────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│ OUTPAINT SETTINGS                                               │
├─────────────────────────────────────────────────────────────────┤
│ Zoom Out: [========30%========] 0-90%                           │
│                                                                 │
│ ┌─ Directional Expansion (pixels) ─────────────────────────────┐│
│ │           Top: [  0  ] (0-700)                               ││
│ │   Left: [  0  ]          Right: [  0  ]                      ││
│ │         Bottom: [  0  ]                                      ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│ Number of Images: [1 ▼] (1-4)                                   │
│ Output Format: [PNG ▼] (png/jpeg/webp)                          │
│ Output Suffix: [-expanded]                                      │
│ [✓] Enable Safety Checker (fal.ai only)                         │
│                                                                 │
│ Optional Prompt (guidance):                                     │
│ ┌──────────────────────────────────────────────────────────────┐│
│ │ e.g. "with a beautiful sunset background"                    ││
│ └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Widget Implementation:**
```python
# Backend selection frame
self.backend_frame = ttk.LabelFrame(parent, text="Backend Selection")

# Radio buttons
self.backend_var = tk.StringVar(value=config.get('backend', 'falai'))
ttk.Radiobutton(self.backend_frame, text="Fal.ai (Cloud)",
                variable=self.backend_var, value="falai",
                command=self._on_backend_change)
ttk.Radiobutton(self.backend_frame, text="ComfyUI (Local)",
                variable=self.backend_var, value="comfyui",
                command=self._on_backend_change)

# ComfyUI status indicator
self.comfyui_status_label = ttk.Label(self.backend_frame, text="● Not Running")
self.comfyui_status_label.configure(foreground='red')

# Test connection button
ttk.Button(self.backend_frame, text="Test Connection",
           command=self._test_comfyui_connection)

def _on_backend_change(self):
    """Handle backend toggle"""
    backend = self.backend_var.get()
    # Enable/disable relevant settings
    if backend == "falai":
        self.safety_checker_cb.configure(state='normal')
    else:
        self.safety_checker_cb.configure(state='disabled')

    # Update status
    self._update_comfyui_status()

def _test_comfyui_connection(self):
    """Test ComfyUI server connection"""
    url = self.comfyui_url_var.get()
    try:
        response = requests.get(f"{url}/system_stats", timeout=5)
        if response.status_code == 200:
            self.comfyui_status_label.configure(text="● Connected", foreground='green')
            messagebox.showinfo("Success", "ComfyUI is running!")
        else:
            raise Exception(f"Status {response.status_code}")
    except Exception as e:
        self.comfyui_status_label.configure(text="● Not Running", foreground='red')
        messagebox.showerror("Error", f"Cannot connect to ComfyUI:\n{e}")
```

### Step 5: Create ComfyUI Workflow Directory

```
outpaint_gui/
├── comfyui_workflows/
│   ├── flux_outpaint.json       # FLUX Fill Dev workflow
│   ├── sdxl_outpaint.json       # SDXL alternative
│   └── README.md                # Setup instructions
```

#### `comfyui_workflows/README.md`
```markdown
# ComfyUI Workflow Setup

## Required Models for FLUX Fill Outpainting

1. **FLUX.1 Fill Dev FP8** (~23GB)
   - Download via ComfyUI Manager or HuggingFace
   - Place in: `ComfyUI/models/diffusion_models/`

2. **CLIP Models**
   - `clip_l.safetensors`
   - `t5xxl_fp8_e4m3fn.safetensors`
   - Place in: `ComfyUI/models/clip/`

3. **VAE**
   - `ae.safetensors`
   - Place in: `ComfyUI/models/vae/`

## Creating Your Own Workflow

1. Open ComfyUI in browser
2. Build outpainting workflow with nodes:
   - LoadImage
   - ImagePadForOutpaint (or similar)
   - FLUX Fill sampler
   - SaveImage
3. Click Save → Export API Format
4. Save as `.json` in this folder
5. Update `outpaint_config.json` to use your workflow
```

### Step 6: Update CLI (`outpaint_ui.py`)

```
╔══════════════════════════════════════════════════════════════════╗
║                      IMAGE OUTPAINT TOOL                         ║
╠══════════════════════════════════════════════════════════════════╣
║  Backend: [Fal.ai - Cloud] / [ComfyUI - Local]                   ║
╠══════════════════════════════════════════════════════════════════╣
║  1. Switch Backend (currently: Fal.ai)                           ║
║  2. Change Zoom Out Percentage (currently: 30%)                  ║
║  3. Set Directional Expansion                                    ║
║  4. Edit Optional Prompt                                         ║
║  5. Select Input Folder                                          ║
║  6. Select Single Image                                          ║
║  7. Launch GUI                                                   ║
║  8. Settings                                                     ║
║  0. Exit                                                         ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## API Comparison

| Parameter | Fal.ai | ComfyUI |
|-----------|--------|---------|
| `image_url` / `image` | URL (upload to host) | Local file (upload to ComfyUI) |
| `zoom_out_percentage` | 0-90 | Converted to scale factor |
| `expand_left/right/top/bottom` | 0-700px | Direct node input |
| `num_images` | 1-4 | Batch size node |
| `prompt` | Optional | Required (has default) |
| `enable_safety_checker` | Yes | N/A (local) |
| `output_format` | png/jpeg/webp | Depends on SaveImage node |

---

## Preserved Functionality

Both backends support:
- ✅ Drag-and-drop individual files/folders
- ✅ File/folder selection dialogs
- ✅ Batch processing with progress tracking
- ✅ Duplicate detection and naming
- ✅ Source folder vs custom output folder
- ✅ Queue management (max 50 items)
- ✅ Backend-aware workers: **5 for fal.ai, 2 for ComfyUI** (GPU constraint)
- ✅ Graceful fallback: offers to switch to fal.ai after 3 ComfyUI failures
- ✅ History tracking
- ✅ Windows launcher

---

## Execution Order

1. Create `backends/` directory structure
2. Create `backends/falai_backend.py` (extract from current code)
3. Create `backends/comfyui_backend.py` (new)
4. Create `outpaint_generator.py` (unified interface)
5. Create `comfyui_workflows/` with template workflow
6. Create `outpaint_gui/` package with backend selector
7. Create `outpaint_ui.py` (CLI with backend option)
8. Create `outpaint_config.json` with dual-backend settings
9. Create `run_outpaint_ui.bat`
10. Test both backends independently
11. (Optional) Remove old `kling_*` files

---

## Cost/Speed Comparison

| Metric | Fal.ai (Cloud) | ComfyUI (Local) |
|--------|----------------|-----------------|
| Cost per 2MP image | ~$0.07 | $0 (electricity ~$0.001) |
| Generation time | 10-30 seconds | 60-120 seconds (RTX 4090) |
| Requires | API key + internet | GPU + ComfyUI running |
| Break-even point | - | ~100 images |

**Recommendation**: Use fal.ai for quick jobs, ComfyUI for large batches.

---

## Notes

### ComfyUI Setup
- **Auto-detection**: Paths searched automatically including Pinokio at `G:\pinokio\api\comfy.git\app`
- **Starting server**: `cd G:\pinokio\api\comfy.git\app && python main.py`
- **Workflow JSON**: Export from ComfyUI after testing manually (Save → Export API Format)
- **VRAM requirement**: FLUX Fill Dev requires 12GB+ VRAM

### Robustness Features
- **Dynamic path detection**: No hardcoded paths - works across installations
- **Node class_type matching**: Workflow parameters injected by node type, not fragile IDs
- **Model availability check**: Verifies FLUX nodes and VRAM before generation
- **Backend-aware workers**: 5 concurrent for cloud, 2 for local GPU
- **Config validation**: Dataclass-based schema catches errors on load
- **Graceful fallback**: Offers to switch to fal.ai after 3 consecutive ComfyUI failures

### Output
- fal.ai safety checker not available in ComfyUI (local = unfiltered)
- Both backends share same output naming: `{name}-expanded.png`
- Multi-image outputs: `{name}-expanded_1.png`, `{name}-expanded_2.png`, etc.
