from __future__ import annotations

import copy

from backends.comfyui_backend import _load_workflow
from backends.comfyui_backend import ComfyUIOutpaintBackend


def test_workflow_injection_updates_nodes() -> None:
    wf = _load_workflow("comfyui_workflows/flux_outpaint.json")
    backend = ComfyUIOutpaintBackend(base_url="http://127.0.0.1:8188", workflow_path="comfyui_workflows/flux_outpaint.json")

    prompt = copy.deepcopy(wf)
    out = backend._inject_params(
        prompt,
        image_name="test.png",
        zoom_out_percentage=0,
        expand_left=111,
        expand_right=222,
        expand_top=333,
        expand_bottom=444,
        num_images=3,
        prompt_text="hello world",
    )

    assert out["1"]["inputs"]["image"] == "test.png"
    assert out["2"]["inputs"]["left"] == 111
    assert out["2"]["inputs"]["right"] == 222
    assert out["2"]["inputs"]["top"] == 333
    assert out["2"]["inputs"]["bottom"] == 444

    # Prompt injection: only positive should be changed (node 5)
    assert out["5"]["inputs"]["text"] == "hello world"
    assert out["6"]["inputs"]["text"] == "blurry, artifacts, seam"

    assert out["8"]["inputs"]["batch_size"] == 3
