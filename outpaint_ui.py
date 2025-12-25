from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from path_utils import get_config_path
from outpaint_diagnostics import run_diagnostics
from outpaint_generator import OutpaintGenerator, default_config_dict, iter_image_files_in_folder, load_outpaint_config, save_config_file


def migrate_kling_config_if_present(config_path: str) -> None:
    outpaint_path = Path(config_path)
    if outpaint_path.exists():
        return

    kling_path = Path(get_config_path("kling_config.json"))
    if not kling_path.exists():
        return

    loaded = json.loads(kling_path.read_text(encoding="utf-8"))
    migrated = default_config_dict()
    migrated["falai_api_key"] = (loaded.get("falai_api_key") or "").strip()
    migrated["output_folder"] = loaded.get("output_folder", "")
    migrated["use_source_folder"] = bool(loaded.get("use_source_folder", True))

    outpaint_path.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
    kling_path.rename(str(kling_path) + ".bak")


def _apply_overrides(merged: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    def set_if(name: str, key: str) -> None:
        v = getattr(args, name)
        if v is not None:
            merged[key] = v

    set_if("backend", "backend")
    set_if("falai_api_key", "falai_api_key")
    set_if("comfyui_url", "comfyui_url")
    set_if("comfyui_workflow_path", "comfyui_workflow_path")
    set_if("output_folder", "output_folder")
    set_if("output_suffix", "output_suffix")
    set_if("output_format", "output_format")
    set_if("zoom_out_percentage", "zoom_out_percentage")
    set_if("expand_left", "expand_left")
    set_if("expand_right", "expand_right")
    set_if("expand_top", "expand_top")
    set_if("expand_bottom", "expand_bottom")
    set_if("num_images", "num_images")
    set_if("prompt", "prompt")

    if args.use_source_folder is not None:
        merged["use_source_folder"] = bool(args.use_source_folder)

    if args.enable_safety_checker is not None:
        merged["enable_safety_checker"] = bool(args.enable_safety_checker)

    workers = merged.get("workers") or {"falai": 5, "comfyui": 2}
    if args.workers_falai is not None:
        workers["falai"] = int(args.workers_falai)
    if args.workers_comfyui is not None:
        workers["comfyui"] = int(args.workers_comfyui)
    merged["workers"] = workers

    return merged


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="fal.ai Image Outpainting Tool")
    parser.add_argument("path", nargs="?", help="Image file or folder to process")

    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("--diagnostics", action="store_true", help="Run diagnostics and exit")

    parser.add_argument("--backend", choices=["falai", "comfyui"], help="Backend to use")
    parser.add_argument("--falai-api-key", dest="falai_api_key", help="fal.ai API key")
    parser.add_argument("--comfyui-url", dest="comfyui_url", help="ComfyUI server URL")
    parser.add_argument("--workflow", dest="comfyui_workflow_path", help="ComfyUI workflow JSON path")

    parser.add_argument("--zoom", dest="zoom_out_percentage", type=int, help="Zoom out percentage (0-90)")
    parser.add_argument("--expand-left", type=int)
    parser.add_argument("--expand-right", type=int)
    parser.add_argument("--expand-top", type=int)
    parser.add_argument("--expand-bottom", type=int)
    parser.add_argument("--num-images", dest="num_images", type=int, help="Number of outputs per input (1-4)")
    parser.add_argument("--prompt", type=str)

    parser.add_argument("--output-format", dest="output_format", choices=["png", "jpeg", "webp"])
    parser.add_argument("--output-suffix", dest="output_suffix")
    parser.add_argument("--output-folder", dest="output_folder")

    parser.add_argument(
        "--use-source-folder",
        dest="use_source_folder",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Save outputs next to inputs",
    )

    parser.add_argument(
        "--enable-safety-checker",
        dest="enable_safety_checker",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="fal.ai only",
    )

    parser.add_argument("--workers-falai", type=int, help="Concurrent workers for fal.ai")
    parser.add_argument("--workers-comfyui", type=int, help="Concurrent workers for ComfyUI")
    parser.add_argument("--max-workers", type=int, help="Override max workers for this run")

    args = parser.parse_args(argv)

    config_path = get_config_path("outpaint_config.json")
    migrate_kling_config_if_present(config_path)

    cfg, errors, merged = load_outpaint_config(config_path)
    merged = _apply_overrides(merged, args)

    if args.diagnostics:
        report, _ok = run_diagnostics(merged)
        print(report)
        return 0

    # GUI should always launch even if config is incomplete; validation happens on Start/Test.
    if args.gui or not args.path:
        save_config_file(config_path, merged)
        from outpaint_gui.main_window import launch_gui

        launch_gui(config_path=config_path)
        return 0

    # Re-validate after overrides
    from outpaint_config import OutpaintConfig, collect_config_errors

    try:
        cfg = OutpaintConfig.model_validate({**default_config_dict(), **merged})
        errors = collect_config_errors(cfg)
    except Exception as e:
        cfg = None
        errors = [str(e)]

    if errors or cfg is None:
        print("Configuration errors:\n")
        for e in errors:
            print(f"- {e}\n")
        print(f"Fix config at: {config_path}")
        return 2

    gen = OutpaintGenerator(cfg)

    ok, msg = gen.check_backend_available()
    if not ok:
        print(f"Backend not ready: {msg}")
        return 3

    p = Path(args.path)
    if p.is_file():
        paths = [str(p)]
    else:
        paths = list(iter_image_files_in_folder(str(p)))

    if not paths:
        print("No images found")
        return 0

    def progress(done: int, total: int, current: str) -> None:
        print(f"[{done}/{total}] {os.path.basename(current)}")

    def log(message: str, level: str = "info") -> None:
        # Ensure failures are visible in CLI mode (generate_many swallows exceptions).
        if level in {"error", "warning"}:
            print(f"[{level}] {message}")

    gen.set_progress_callback(log)
    results = gen.generate_many(paths, max_workers=args.max_workers, per_item_callback=progress)
    if len(results) != len(paths):
        print(f"\nCompleted with failures: {len(results)}/{len(paths)} succeeded")
        save_config_file(config_path, merged)
        return 4
    save_config_file(config_path, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
