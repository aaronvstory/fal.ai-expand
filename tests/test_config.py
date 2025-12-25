from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from outpaint_config import OutpaintConfig, collect_config_errors


def test_config_range_validation() -> None:
    with pytest.raises(ValidationError):
        OutpaintConfig.model_validate({"zoom_out_percentage": 999})

    with pytest.raises(ValidationError):
        OutpaintConfig.model_validate({"expand_left": -1})

    with pytest.raises(ValidationError):
        OutpaintConfig.model_validate({"num_images": 9})


def test_collect_errors_requires_api_key_for_falai() -> None:
    cfg = OutpaintConfig.model_validate({"backend": "falai", "falai_api_key": ""})
    errs = collect_config_errors(cfg)
    assert any("falai_api_key" in e for e in errs)


def test_collect_errors_workflow_missing_for_comfyui(tmp_path: Path) -> None:
    cfg = OutpaintConfig.model_validate({"backend": "comfyui", "comfyui_workflow_path": str(tmp_path / "missing.json")})
    errs = collect_config_errors(cfg)
    assert any("workflow" in e.lower() for e in errs)
