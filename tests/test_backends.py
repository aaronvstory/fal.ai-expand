from __future__ import annotations

from typing import Any

from outpaint_config import OutpaintConfig
from outpaint_generator import default_config_dict

from backends import get_backend
from backends.comfyui_backend import ComfyUIOutpaintBackend


class _Resp:
    def __init__(self, status_code: int, data: Any):
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self) -> Any:
        return self._data


def test_backend_factory_falai() -> None:
    d = default_config_dict()
    d.update({"backend": "falai", "falai_api_key": "x"})
    cfg = OutpaintConfig.model_validate(d)
    b = get_backend(cfg)
    assert b.__class__.__name__ == "FalAIOutpaintBackend"


def test_backend_factory_comfyui() -> None:
    d = default_config_dict()
    d.update({"backend": "comfyui"})
    cfg = OutpaintConfig.model_validate(d)
    b = get_backend(cfg)
    assert b.__class__.__name__ == "ComfyUIOutpaintBackend"


def test_comfyui_check_available_ok(monkeypatch) -> None:
    info = {
        "LoadImage": {},
        "KSampler": {"input": {"required": {"sampler_name": [["euler"], {}], "scheduler": [["normal"], {}]}}},
        "VAEEncode": {},
        "VAEDecode": {},
        "DualCLIPLoader": {
            "input": {
                "required": {
                    "clip_name1": [["clip_l.safetensors"], {}],
                    "clip_name2": [["t5xxl_fp8_e4m3fn.safetensors"], {}],
                    "type": [["flux"], {}],
                }
            }
        },
        "UNETLoader": {"input": {"required": {"unet_name": [["flux1-fill-dev-fp8.safetensors"], {}], "weight_dtype": [["default"], {}]}}},
    }

    def fake_get(url: str, timeout: int = 5):
        if url.endswith("/system_stats"):
            return _Resp(200, {"devices": [{"vram_total": 16 * 1024 * 1024 * 1024}]})
        raise AssertionError(url)

    monkeypatch.setattr("backends.comfyui_backend.requests.get", fake_get)
    monkeypatch.setattr(ComfyUIOutpaintBackend, "_get_object_info", lambda self: info)

    b = ComfyUIOutpaintBackend(base_url="http://127.0.0.1:8188", workflow_path="comfyui_workflows/flux_outpaint.json")
    ok, _msg = b.check_available()
    assert ok is True


def test_comfyui_check_available_low_vram(monkeypatch) -> None:
    info = {
        "LoadImage": {},
        "KSampler": {"input": {"required": {"sampler_name": [["euler"], {}], "scheduler": [["normal"], {}]}}},
        "VAEEncode": {},
        "VAEDecode": {},
        "DualCLIPLoader": {
            "input": {
                "required": {
                    "clip_name1": [["clip_l.safetensors"], {}],
                    "clip_name2": [["t5xxl_fp8_e4m3fn.safetensors"], {}],
                    "type": [["flux"], {}],
                }
            }
        },
        "UNETLoader": {"input": {"required": {"unet_name": [["flux1-fill-dev-fp8.safetensors"], {}], "weight_dtype": [["default"], {}]}}},
    }

    def fake_get(url: str, timeout: int = 5):
        if url.endswith("/system_stats"):
            return _Resp(200, {"devices": [{"vram_total": 4 * 1024 * 1024 * 1024}]})
        raise AssertionError(url)

    monkeypatch.setattr("backends.comfyui_backend.requests.get", fake_get)
    monkeypatch.setattr(ComfyUIOutpaintBackend, "_get_object_info", lambda self: info)

    b = ComfyUIOutpaintBackend(base_url="http://127.0.0.1:8188", workflow_path="comfyui_workflows/flux_outpaint.json")
    ok, msg = b.check_available()
    assert ok is False
    assert "VRAM" in msg
