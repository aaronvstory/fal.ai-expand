from __future__ import annotations

import json
import time
import threading
import uuid
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Any, Optional

import requests

from path_utils import detect_comfyui_path

from . import OutpaintBackend, ProgressCallback


def _progress(cb: Optional[ProgressCallback], message: str, level: str = "info"):
    if cb:
        cb(message, level)


def _load_workflow(workflow_path: str) -> dict[str, Any]:
    p = Path(workflow_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent.parent / workflow_path
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], dict):
        return data["prompt"]
    if isinstance(data, dict):
        return data
    raise ValueError("Unsupported workflow format")


def find_all_nodes_by_class(prompt: dict[str, Any], class_types: set[str]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in class_types:
            out.append((str(node_id), node))
    return out


def find_node_by_class(prompt: dict[str, Any], class_types: set[str]) -> Optional[tuple[str, dict[str, Any]]]:
    nodes = find_all_nodes_by_class(prompt, class_types)
    return nodes[0] if nodes else None


def _resolve_node_ref(ref: Any) -> Optional[str]:
    # ComfyUI uses [node_id, output_index]
    if isinstance(ref, list) and len(ref) >= 1:
        return str(ref[0])
    return None


def _extract_history_error(job: dict[str, Any], prompt: dict[str, Any]) -> Optional[str]:
    """Best-effort extraction of an execution error from /history/{prompt_id}."""
    status = job.get("status")
    if not isinstance(status, dict):
        status = {}

    status_str = str(status.get("status_str") or "").lower()
    messages = status.get("messages")
    if not isinstance(messages, list):
        messages = job.get("messages") if isinstance(job.get("messages"), list) else []

    # If ComfyUI marks the job as error but provides no message details.
    if status_str == "error" and not messages:
        return "ComfyUI execution failed (status=error). Check the ComfyUI console/log for details."

    for m in messages:
        kind: str = ""
        payload: Any = None

        if isinstance(m, list) and len(m) == 2:
            kind, payload = str(m[0]), m[1]
        elif isinstance(m, dict):
            kind = str(m.get("type") or m.get("message_type") or "message")
            payload = m
        else:
            continue

        if "error" not in kind.lower() and kind not in {"execution_error", "execution_interrupted"}:
            continue

        node_id = None
        exc_msg = None
        exc_type = None
        if isinstance(payload, dict):
            node_id = payload.get("node_id") or payload.get("node") or payload.get("nodeId")
            exc_msg = payload.get("exception_message") or payload.get("message") or payload.get("details")
            exc_type = payload.get("exception_type") or payload.get("exception") or payload.get("error")

        node_desc = ""
        if node_id is not None:
            node = prompt.get(str(node_id))
            if isinstance(node, dict):
                ct = node.get("class_type")
                node_desc = f" (node {node_id}: {ct})" if ct else f" (node {node_id})"
            else:
                node_desc = f" (node {node_id})"

        parts = ["ComfyUI execution error" + node_desc]
        if exc_type:
            parts.append(str(exc_type))
        if exc_msg:
            parts.append(str(exc_msg))
        return ": ".join(parts)

    return None


class ComfyUIOutpaintBackend(OutpaintBackend):
    def __init__(self, base_url: str, workflow_path: str):
        self.base_url = base_url.rstrip("/")
        self.workflow_path = workflow_path

    def _get_object_info(self) -> dict[str, Any]:
        resp = requests.get(f"{self.base_url}/object_info", timeout=5)
        resp.raise_for_status()
        info = resp.json()
        if not isinstance(info, dict):
            raise RuntimeError("Unexpected /object_info response")
        return info

    @staticmethod
    def _choice_list(info: dict[str, Any], class_type: str, input_name: str) -> list[Any]:
        node = info.get(class_type)
        if not isinstance(node, dict):
            return []
        inputs = node.get("input")
        if not isinstance(inputs, dict):
            return []
        req = inputs.get("required")
        if not isinstance(req, dict):
            return []
        spec = req.get(input_name)
        if isinstance(spec, list) and spec and isinstance(spec[0], list):
            return list(spec[0])
        return []

    def check_available(self) -> tuple[bool, str]:
        def _bytes_to_gb(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                x = float(v)
            except Exception:
                return None
            # Heuristics: bytes vs MB vs GB
            if x > 1024 * 1024 * 1024:
                return x / (1024 * 1024 * 1024)
            if x > 1024 * 16:
                return x / 1024.0
            return x

        try:
            stats_resp = requests.get(f"{self.base_url}/system_stats", timeout=5)
            if stats_resp.status_code != 200:
                return False, f"ComfyUI not responding: HTTP {stats_resp.status_code}"
            stats = stats_resp.json()
        except Exception as e:
            hint = ""
            try:
                comfy_path = detect_comfyui_path()
                if comfy_path:
                    p = Path(comfy_path)
                    python_cmd = "python"
                    pinokio_py = p / "env" / "Scripts" / "python.exe"
                    if pinokio_py.exists():
                        python_cmd = str(pinokio_py)
                    hint = (
                        f"\nDetected ComfyUI install at: {p}"
                        f"\nStart it with: cd \"{p}\" && \"{python_cmd}\" main.py --listen 127.0.0.1 --port 8188"
                        f"\nThen open: {self.base_url}"
                    )
            except Exception:
                hint = ""

            return False, f"ComfyUI not reachable: {e}{hint}"

        # VRAM check (best-effort parsing)
        try:
            devices = stats.get("devices") if isinstance(stats, dict) else None
            vram_gb: Optional[float] = None
            if isinstance(devices, list) and devices:
                totals: list[float] = []
                for d in devices:
                    if not isinstance(d, dict):
                        continue
                    for key in ("vram_total", "vram_total_bytes", "vramTotal", "total_vram"):
                        gb = _bytes_to_gb(d.get(key))
                        if gb is not None:
                            totals.append(gb)
                            break
                if totals:
                    vram_gb = max(totals)
            if vram_gb is not None and vram_gb < 12.0:
                return False, f"GPU VRAM too low for FLUX: {vram_gb:.1f}GB detected (need >= 12GB)"
        except Exception:
            pass

        try:
            info = self._get_object_info()
        except Exception as e:
            return False, f"ComfyUI /object_info error: {e}"

        # Core nodes
        required_any = {"LoadImage", "KSampler", "VAEEncode", "VAEDecode"}
        missing_core = [n for n in required_any if n not in info]
        if missing_core:
            return False, f"Required nodes missing: {', '.join(sorted(missing_core))}"

        # Validate workflow JSON can be loaded and contains the required nodes.
        workflow_classes: set[str] = set()
        try:
            wf = _load_workflow(self.workflow_path)
            self._validate_workflow(wf)
            workflow_classes = {n.get("class_type") for n in wf.values() if isinstance(n, dict)}
        except Exception as e:
            return False, f"Workflow invalid: {e}"

        # Loader node availability + model choices (workflow-aware).
        issues: list[str] = []

        flux_unet_ok = any(k in info for k in ("UNETLoader", "CheckpointLoaderSimple", "FluxModelLoader", "DiffusionModelLoader"))
        flux_clip_ok = any(k in info for k in ("DualCLIPLoader", "CLIPLoader", "TripleCLIPLoader"))
        if not flux_unet_ok:
            issues.append(
                "FLUX model loader node not found (expected UNETLoader or fallback). Install FLUX via ComfyUI Manager (search 'FLUX'), then restart ComfyUI."
            )
        if not flux_clip_ok:
            issues.append(
                "FLUX CLIP loader node not found (expected DualCLIPLoader or fallback). Install FLUX via ComfyUI Manager (search 'FLUX'), then restart ComfyUI."
            )

        if "UNETLoader" in workflow_classes:
            unets = self._choice_list(info, "UNETLoader", "unet_name")
            if not unets:
                ckpts = self._choice_list(info, "CheckpointLoaderSimple", "ckpt_name")
                hint = ""
                if ckpts:
                    hint = (
                        " Hint: you have models in CheckpointLoaderSimple (models/checkpoints), but UNETLoader is empty. "
                        "FLUX UNET files must be in ComfyUI/models/unet (not models/checkpoints) to appear in UNETLoader."
                    )
                issues.append(
                    "Workflow uses UNETLoader but no UNET models are installed (UNETLoader.unet_name list is empty). "
                    "Install a FLUX Fill UNET (e.g. flux1-fill-*.safetensors) and restart ComfyUI." + hint
                )
            else:
                # Outpainting workflows require a FLUX Fill model; base/schnell UNETs often produce poor/incorrect fills.
                if not any("fill" in str(u).lower() for u in unets):
                    sample = ", ".join(str(u) for u in unets[:10])
                    issues.append(
                        "FLUX Fill UNET not found in UNETLoader list. Install a FLUX Fill model (flux1-fill-*.safetensors) into models/unet and restart ComfyUI. "
                        f"Found UNETs: {sample}"
                    )

        if "CheckpointLoaderSimple" in workflow_classes:
            ckpts = self._choice_list(info, "CheckpointLoaderSimple", "ckpt_name")
            if not ckpts:
                issues.append(
                    "Workflow uses CheckpointLoaderSimple but no checkpoints are available (CheckpointLoaderSimple.ckpt_name list is empty)."
                )

        if "DualCLIPLoader" in workflow_classes:
            c1 = self._choice_list(info, "DualCLIPLoader", "clip_name1")
            c2 = self._choice_list(info, "DualCLIPLoader", "clip_name2")
            if not c1:
                issues.append(
                    "Workflow uses DualCLIPLoader but clip_name1 list is empty (install FLUX clip_l). "
                    "Ensure clip_l.safetensors is in ComfyUI/models/clip, then restart ComfyUI."
                )
            if not c2:
                issues.append(
                    "Workflow uses DualCLIPLoader but clip_name2 list is empty (install FLUX t5xxl). "
                    "Ensure t5xxl*.safetensors is in ComfyUI/models/clip, then restart ComfyUI."
                )

        if "CLIPLoader" in workflow_classes:
            clips = self._choice_list(info, "CLIPLoader", "clip_name")
            if not clips:
                issues.append("Workflow uses CLIPLoader but no CLIP models are available (CLIPLoader.clip_name list is empty).")

        if issues:
            return False, "\n".join(issues)

        return True, "ComfyUI ready"

    def _upload_image(self, image_path: str, cb: Optional[ProgressCallback]) -> str:
        _progress(cb, f"Uploading to ComfyUI: {Path(image_path).name}", "upload")
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{self.base_url}/upload/image",
                files={"image": f},
                data={"type": "input", "overwrite": "true"},
                timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
        name = data.get("name")
        if not name:
            raise RuntimeError(f"Unexpected upload response: {data}")
        return name

    def _inject_params(
        self,
        prompt: dict[str, Any],
        *,
        image_name: str,
        zoom_out_percentage: int,
        expand_left: int,
        expand_right: int,
        expand_top: int,
        expand_bottom: int,
        num_images: int,
        prompt_text: str,
        object_info: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        # LoadImage
        load = find_node_by_class(prompt, {"LoadImage"})
        if load:
            _, node = load
            node.setdefault("inputs", {})
            node["inputs"]["image"] = image_name

        # ImagePadForOutpaint
        pad = find_node_by_class(prompt, {"ImagePadForOutpaint"})
        if pad:
            _, node = pad
            node.setdefault("inputs", {})
            inp = node["inputs"]
            for k, v in (
                ("left", expand_left),
                ("right", expand_right),
                ("top", expand_top),
                ("bottom", expand_bottom),
                ("expand_left", expand_left),
                ("expand_right", expand_right),
                ("expand_top", expand_top),
                ("expand_bottom", expand_bottom),
                ("pad_left", expand_left),
                ("pad_right", expand_right),
                ("pad_top", expand_top),
                ("pad_bottom", expand_bottom),
            ):
                if k in inp or k.startswith("expand_") or k.startswith("pad_"):
                    inp[k] = v

            # Required by current ComfyUI versions
            inp.setdefault("feathering", 20)

        # Prompt injection: use KSampler wiring if possible
        ks = find_node_by_class(prompt, {"KSampler"})
        if ks:
            _, ks_node = ks
            ks_inputs = ks_node.get("inputs", {})
            pos_id = _resolve_node_ref(ks_inputs.get("positive"))
            neg_id = _resolve_node_ref(ks_inputs.get("negative"))
            if pos_id and pos_id in prompt:
                pos_node = prompt[pos_id]
                pos_node.setdefault("inputs", {})
                if "text" in pos_node["inputs"]:
                    pos_node["inputs"]["text"] = prompt_text
            # Do not touch negative prompt node
            _ = neg_id

        # Batch size: try KSampler, else EmptyLatentImage
        if ks:
            _, ks_node = ks
            ks_node.setdefault("inputs", {})
            if "batch_size" in ks_node["inputs"]:
                ks_node["inputs"]["batch_size"] = num_images

            # Required by current ComfyUI versions
            ks_node["inputs"].setdefault("denoise", 1.0)

        latent = find_node_by_class(prompt, {"EmptyLatentImage"})
        if latent:
            _, lnode = latent
            lnode.setdefault("inputs", {})
            if "batch_size" in lnode["inputs"]:
                lnode["inputs"]["batch_size"] = num_images

        # Zoom-out: if workflow has a scale node, set it
        if zoom_out_percentage > 0:
            scale = 1.0 / (1.0 - zoom_out_percentage / 100.0)
            scale_node = find_node_by_class(prompt, {"ImageScaleBy", "ImageScale", "ImageResize"})
            if scale_node:
                _, snode = scale_node
                snode.setdefault("inputs", {})
                if "scale_by" in snode["inputs"]:
                    snode["inputs"]["scale_by"] = scale
                elif "scale" in snode["inputs"]:
                    snode["inputs"]["scale"] = scale

        # Fix up loader nodes (required inputs + valid selections)
        if object_info is not None:
            # UNETLoader
            unet = find_node_by_class(prompt, {"UNETLoader"})
            if unet:
                _, u = unet
                u.setdefault("inputs", {})
                dtype_choices = self._choice_list(object_info, "UNETLoader", "weight_dtype")
                u["inputs"].setdefault("weight_dtype", "default" if "default" in dtype_choices else (dtype_choices[0] if dtype_choices else "default"))

                unet_choices = self._choice_list(object_info, "UNETLoader", "unet_name")
                if unet_choices:
                    if u["inputs"].get("unet_name") not in unet_choices:
                        preferred = None
                        for c in unet_choices:
                            s = str(c).lower()
                            if "flux" in s and "fill" in s:
                                preferred = c
                                break
                        if preferred is None:
                            for c in unet_choices:
                                if "flux" in str(c).lower():
                                    preferred = c
                                    break
                        u["inputs"]["unet_name"] = preferred if preferred is not None else unet_choices[0]
                else:
                    raise RuntimeError("No UNET models available for UNETLoader (install FLUX Fill models and restart ComfyUI).")

            # DualCLIPLoader
            dclip = find_node_by_class(prompt, {"DualCLIPLoader"})
            if dclip:
                _, c = dclip
                c.setdefault("inputs", {})

                type_choices = self._choice_list(object_info, "DualCLIPLoader", "type")
                c["inputs"].setdefault("type", "flux" if "flux" in type_choices else (type_choices[0] if type_choices else "flux"))

                c1_choices = self._choice_list(object_info, "DualCLIPLoader", "clip_name1")
                c2_choices = self._choice_list(object_info, "DualCLIPLoader", "clip_name2")
                if c1_choices:
                    if c["inputs"].get("clip_name1") not in c1_choices:
                        preferred = None
                        for cc in c1_choices:
                            if "clip_l" in str(cc).lower():
                                preferred = cc
                                break
                        c["inputs"]["clip_name1"] = preferred if preferred is not None else c1_choices[0]
                else:
                    raise RuntimeError("No CLIP models available for DualCLIPLoader (install FLUX clip_l and restart ComfyUI).")
                if c2_choices:
                    if c["inputs"].get("clip_name2") not in c2_choices:
                        preferred = None
                        for cc in c2_choices:
                            s = str(cc).lower()
                            if "t5" in s and "fp8" in s:
                                preferred = cc
                                break
                        if preferred is None:
                            for cc in c2_choices:
                                if "t5" in str(cc).lower():
                                    preferred = cc
                                    break
                        c["inputs"]["clip_name2"] = preferred if preferred is not None else c2_choices[0]
                else:
                    raise RuntimeError("No T5 models available for DualCLIPLoader (install FLUX t5xxl and restart ComfyUI).")

            # VAELoader
            vae = find_node_by_class(prompt, {"VAELoader"})
            if vae:
                _, v = vae
                v.setdefault("inputs", {})
                vae_choices = self._choice_list(object_info, "VAELoader", "vae_name")
                if vae_choices and v["inputs"].get("vae_name") not in vae_choices:
                    preferred = None
                    for cc in vae_choices:
                        s = str(cc).lower()
                        if s == "pixel_space":
                            continue
                        if s == "ae.safetensors" or s.startswith("ae") or "flux" in s:
                            preferred = cc
                            break
                    if preferred is None:
                        for cc in vae_choices:
                            if str(cc).lower() != "pixel_space":
                                preferred = cc
                                break
                    v["inputs"]["vae_name"] = preferred if preferred is not None else vae_choices[0]

        return prompt

    def _validate_workflow(self, prompt: dict[str, Any]) -> None:
        required = {
            "LoadImage",
            "ImagePadForOutpaint",
            "KSampler",
            "VAEEncode",
            "VAEDecode",
            "SaveImage",
        }

        present = {node.get("class_type") for node in prompt.values() if isinstance(node, dict)}
        missing = sorted(required - set(present))
        if missing:
            raise ValueError(f"Workflow missing required node(s): {', '.join(missing)}")

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
        _ = output_format
        _ = enable_safety_checker

        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

        ok, msg = self.check_available()
        if not ok:
            raise RuntimeError(msg)

        uploaded_name = self._upload_image(image_path, progress_callback)
        wf = _load_workflow(self.workflow_path)
        wf = json.loads(json.dumps(wf))  # deep copy

        self._validate_workflow(wf)

        wf = self._inject_params(
            wf,
            image_name=uploaded_name,
            zoom_out_percentage=zoom_out_percentage,
            expand_left=expand_left,
            expand_right=expand_right,
            expand_top=expand_top,
            expand_bottom=expand_bottom,
            num_images=num_images,
            prompt_text=prompt or "",
            object_info=self._get_object_info(),
        )

        client_id = f"outpaint-{uuid.uuid4().hex[:8]}"
        _progress(progress_callback, "Submitting ComfyUI prompt…", "api")
        submit = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": wf, "client_id": client_id},
            timeout=30,
        )
        if submit.status_code != 200:
            raise RuntimeError(f"ComfyUI /prompt failed: HTTP {submit.status_code} {submit.text}")
        prompt_id = submit.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"Unexpected /prompt response: {submit.text}")

        # Poll history
        for _i in range(600):
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()
            time.sleep(1)
            hist = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=30)
            if hist.status_code != 200:
                continue
            data = hist.json()
            if str(prompt_id) not in data:
                continue
            job = data[str(prompt_id)]

            err = _extract_history_error(job, wf)
            if err:
                raise RuntimeError(err)

            outputs = job.get("outputs", {})
            images: list[dict[str, Any]] = []
            for out in outputs.values():
                if isinstance(out, dict) and "images" in out:
                    images.extend(out.get("images") or [])
            if not images:
                continue

            results: list[bytes] = []
            for im in images:
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError()
                filename = im.get("filename")
                subfolder = im.get("subfolder", "")
                ftype = im.get("type", "output")
                if not filename:
                    continue
                view = requests.get(
                    f"{self.base_url}/view",
                    params={"filename": filename, "subfolder": subfolder, "type": ftype},
                    timeout=120,
                )
                view.raise_for_status()
                results.append(view.content)

            if results:
                return results

        raise TimeoutError("Timeout waiting for ComfyUI history")
