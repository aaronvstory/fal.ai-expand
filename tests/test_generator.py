from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from outpaint_config import OutpaintConfig
from outpaint_generator import OutpaintGenerator, default_config_dict


class FakeBackend:
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
        progress_callback=None,
        cancel_event=None,
    ) -> list[bytes]:
        _ = (image_path, zoom_out_percentage, expand_left, expand_right, expand_top, expand_bottom, prompt, output_format, enable_safety_checker, cancel_event)
        outs: list[bytes] = []
        for _i in range(num_images):
            img = Image.new("RGB", (32, 24), (10, 20, 30))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            outs.append(buf.getvalue())
        return outs


def test_generator_writes_numbered_outputs(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(src, format="PNG")

    d = default_config_dict()
    d.update(
        {
            "backend": "falai",
            "falai_api_key": "x",
            "use_source_folder": True,
            "output_format": "jpeg",
            "num_images": 2,
            "reprocess_mode": "increment",
        }
    )
    cfg = OutpaintConfig.model_validate(d)

    gen = OutpaintGenerator(cfg)
    gen._backend = FakeBackend()  # type: ignore[attr-defined]

    r1 = gen.generate(str(src))
    assert len(r1.output_paths) == 2

    p0 = Path(r1.output_paths[0])
    p1 = Path(r1.output_paths[1])
    assert p0.exists() and p1.exists()
    assert p0.suffix.lower() == ".jpeg"

    # Re-run should increment filenames
    r2 = gen.generate(str(src))
    assert all(Path(p).exists() for p in r2.output_paths)
    assert any(Path(p).stem.endswith("_2") for p in r2.output_paths)
