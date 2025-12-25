"""
FastAPI Server for Outpaint Tool
Provides REST API endpoints for image outpainting with auto-fallback support
"""

from __future__ import annotations

import io
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import uvicorn

from outpaint_generator import OutpaintGenerator, OutpaintResult
from outpaint_config import OutpaintConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Outpaint API",
    description="AI-powered image outpainting with automatic backend fallback",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global config (loaded from outpaint_config.json)
_config: Optional[OutpaintConfig] = None
_generator: Optional[OutpaintGenerator] = None


def _ensure_generator() -> OutpaintGenerator:
    """Lazy-load the generator with current config."""
    global _config, _generator

    if _generator is None:
        from outpaint_generator import load_outpaint_config

        config, errors, _ = load_outpaint_config("outpaint_config.json")
        if errors:
            raise RuntimeError(f"Config errors: {'; '.join(errors)}")

        if config is None:
            raise RuntimeError("Failed to load config")

        _config = config
        _generator = OutpaintGenerator(config)

        # Set progress callback for logging
        def progress_callback(message: str, level: str = "info"):
            if level == "error":
                logger.error(f"Generator: {message}")
            elif level == "warning":
                logger.warning(f"Generator: {message}")
            else:
                logger.info(f"Generator: {message}")

        _generator.set_progress_callback(progress_callback)

    return _generator


@app.get("/")
async def root():
    """API root endpoint with health check."""
    return {
        "name": "Outpaint API",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": {
            "health": "/health",
            "outpaint": "/outpaint (POST)",
            "config": "/config (GET)",
            "backend_status": "/backend/status (GET)",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        generator = _ensure_generator()
        backend_ok, backend_msg = generator.check_backend_available()

        return {
            "status": "healthy",
            "backend": {
                "type": generator.config.backend,
                "available": backend_ok,
                "message": backend_msg,
            },
            "auto_fallback": "enabled" if generator.config.backend == "comfyui" else "not_needed",
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/config")
async def get_config():
    """Get current configuration (sensitive fields redacted)."""
    try:
        generator = _ensure_generator()
        config_dict = generator.config.model_dump()

        # Redact sensitive fields
        if "falai_api_key" in config_dict:
            key = config_dict["falai_api_key"]
            config_dict["falai_api_key"] = f"{key[:8]}..." if key and len(key) > 8 else "***"

        return {
            "config": config_dict,
            "auto_fallback": generator._fallback_attempted,
        }
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(status_code=500, detail=f"Config error: {str(e)}")


@app.get("/backend/status")
async def backend_status():
    """Check backend availability."""
    try:
        generator = _ensure_generator()
        ok, msg = generator.check_backend_available()

        return {
            "backend": generator.config.backend,
            "available": ok,
            "message": msg,
            "fallback_available": bool(generator.config.falai_api_key),
        }
    except Exception as e:
        logger.error(f"Backend status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backend check failed: {str(e)}")


@app.post("/outpaint")
async def outpaint(
    image: UploadFile = File(..., description="Image file to outpaint"),
    zoom_out_percentage: int = Form(0, description="Zoom out percentage (0-100)"),
    expand_left: int = Form(200, description="Pixels to expand left"),
    expand_right: int = Form(200, description="Pixels to expand right"),
    expand_top: int = Form(200, description="Pixels to expand top"),
    expand_bottom: int = Form(200, description="Pixels to expand bottom"),
    num_images: int = Form(1, description="Number of images to generate"),
    prompt: str = Form("", description="Text prompt for generation"),
    output_format: str = Form("png", description="Output format (png, jpeg, webp)"),
    return_file: bool = Form(True, description="Return file directly or JSON with URL"),
):
    """
    Outpaint an image with automatic backend fallback.

    - **image**: Image file to outpaint
    - **zoom_out_percentage**: 0-100 (default: 0)
    - **expand_left/right/top/bottom**: Pixels to expand (default: 200)
    - **num_images**: Number of variations (default: 1)
    - **prompt**: Text prompt for AI generation
    - **output_format**: png, jpeg, or webp (default: png)
    - **return_file**: If true, returns image file; if false, returns JSON with path
    """
    temp_dir = None
    temp_input = None

    try:
        generator = _ensure_generator()

        # Validate input
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Invalid image file")

        # Create temp directory for processing
        temp_dir = Path(tempfile.mkdtemp(prefix="outpaint_api_"))
        temp_input = temp_dir / f"input_{uuid.uuid4().hex}.png"

        # Save uploaded image
        image_data = await image.read()
        img = Image.open(io.BytesIO(image_data))
        img.save(temp_input, format="PNG")
        logger.info(f"Saved input image: {temp_input}")

        # Create request-scoped config (thread-safe, no global mutation)
        request_config = generator.config.model_copy(update={
            "zoom_out_percentage": zoom_out_percentage,
            "expand_left": expand_left,
            "expand_right": expand_right,
            "expand_top": expand_top,
            "expand_bottom": expand_bottom,
            "num_images": num_images,
            "prompt": prompt,
            "output_format": output_format,
            "output_folder": str(temp_dir),
            "use_source_folder": False,
        })

        # Create request-scoped generator to avoid race conditions
        request_generator = OutpaintGenerator(request_config)
        request_generator.set_progress_callback(lambda msg, lvl="info": logger.info(f"Generator: {msg}"))

        # Generate outpaint
        logger.info(f"Processing with backend: {request_config.backend}")
        result: OutpaintResult = request_generator.generate(str(temp_input))
        backend_used = request_config.backend

        if not result.output_paths:
            raise HTTPException(status_code=500, detail="No outputs generated")

        # Return first output
        output_path = Path(result.output_paths[0])

        if return_file:
            # Return file directly
            return FileResponse(
                output_path,
                media_type=f"image/{output_format}",
                filename=f"outpaint_{uuid.uuid4().hex[:8]}.{output_format}",
            )
        else:
            # Return JSON with file info
            return JSONResponse({
                "success": True,
                "backend_used": backend_used,
                "fallback_triggered": request_generator._fallback_attempted,
                "output_path": str(output_path),
                "num_outputs": len(result.output_paths),
                "message": "Outpaint completed successfully",
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Outpaint failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Outpaint failed: {str(e)}")

    finally:
        # Cleanup temp files (optional - keep for debugging)
        # if temp_dir and temp_dir.exists():
        #     import shutil
        #     shutil.rmtree(temp_dir, ignore_errors=True)
        pass


@app.post("/outpaint/batch")
async def outpaint_batch(
    images: list[UploadFile] = File(..., description="Multiple images to outpaint"),
    # ... same parameters as /outpaint ...
):
    """
    Batch outpaint multiple images (TODO: implement).
    """
    raise HTTPException(status_code=501, detail="Batch processing not yet implemented")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Outpaint API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════╗
║        Outpaint API Server Starting...        ║
╠════════════════════════════════════════════════╣
║  URL: http://{args.host}:{args.port}                    ║
║  Docs: http://{args.host}:{args.port}/docs             ║
║  Auto-fallback: ComfyUI → falai (enabled)    ║
╚════════════════════════════════════════════════╝
""")

    uvicorn.run(
        "api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
