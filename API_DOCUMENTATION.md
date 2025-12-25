# 🚀 Outpaint API Documentation

## Overview

Production-ready REST API for AI-powered image outpainting with **automatic backend fallback** (ComfyUI → falai).

### Key Features
- ✅ **Auto-fallback** - Seamlessly switches to falai if ComfyUI crashes
- ✅ **FastAPI** - Modern, fast, with automatic OpenAPI docs
- ✅ **File upload** - Direct image upload via multipart/form-data
- ✅ **Flexible output** - Return files directly or JSON with paths
- ✅ **Health checks** - Monitor backend status and availability
- ✅ **CORS enabled** - Ready for frontend integration

---

## 🏁 Quick Start

### Installation

```bash
# Install API dependencies
pip install -r requirements_api.txt

# Or install individually
pip install fastapi uvicorn[standard] python-multipart
```

### Start Server

#### Method 1: Using Batch Script (Windows)
```bash
start_api_server.bat
```

#### Method 2: Command Line
```bash
# Development (with auto-reload)
python api_server.py --reload

# Production
python api_server.py --host 0.0.0.0 --port 8000
```

#### Method 3: Uvicorn Direct
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### Access API

- **API Endpoint**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **OpenAPI Schema**: http://localhost:8000/openapi.json

---

## 📋 API Endpoints

### 1. Root / Health Check

```http
GET /
```

**Response:**
```json
{
  "name": "Outpaint API",
  "version": "1.0.0",
  "status": "healthy",
  "endpoints": {
    "health": "/health",
    "outpaint": "/outpaint (POST)",
    "config": "/config (GET)",
    "backend_status": "/backend/status (GET)"
  }
}
```

---

### 2. Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "backend": {
    "type": "comfyui",
    "available": true,
    "message": "ComfyUI ready"
  },
  "auto_fallback": "enabled"
}
```

---

### 3. Get Configuration

```http
GET /config
```

**Response:**
```json
{
  "config": {
    "backend": "comfyui",
    "falai_api_key": "fal_abc12...***",
    "enable_safety_checker": true,
    "comfyui_url": "http://127.0.0.1:8188",
    "zoom_out_percentage": 30,
    "expand_left": 200,
    "expand_right": 200,
    "expand_top": 200,
    "expand_bottom": 200,
    "num_images": 1,
    "output_format": "png"
  },
  "auto_fallback": false
}
```

---

### 4. Backend Status

```http
GET /backend/status
```

**Response:**
```json
{
  "backend": "comfyui",
  "available": true,
  "message": "ComfyUI ready",
  "fallback_available": true
}
```

---

### 5. Outpaint Image ⭐ (Main Endpoint)

```http
POST /outpaint
Content-Type: multipart/form-data
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image` | File | **Required** | Image file to outpaint |
| `zoom_out_percentage` | int | 0 | Zoom out percentage (0-100) |
| `expand_left` | int | 200 | Pixels to expand left |
| `expand_right` | int | 200 | Pixels to expand right |
| `expand_top` | int | 200 | Pixels to expand top |
| `expand_bottom` | int | 200 | Pixels to expand bottom |
| `num_images` | int | 1 | Number of variations to generate |
| `prompt` | string | "" | Text prompt for AI generation |
| `output_format` | string | "png" | Output format (png/jpeg/webp) |
| `return_file` | bool | true | Return file directly or JSON |

#### Response (return_file=true)

Returns the outpainted image file directly with appropriate `Content-Type`.

**Headers:**
```
Content-Type: image/png
Content-Disposition: attachment; filename="outpaint_a1b2c3d4.png"
```

#### Response (return_file=false)

```json
{
  "success": true,
  "backend_used": "comfyui",
  "fallback_triggered": false,
  "output_path": "C:\\temp\\outpaint_api_xyz\\output.png",
  "num_outputs": 1,
  "message": "Outpaint completed successfully"
}
```

---

## 💻 Usage Examples

### cURL

```bash
# Basic outpaint
curl -X POST "http://localhost:8000/outpaint" \
  -F "image=@input.png" \
  -F "expand_left=300" \
  -F "expand_right=300" \
  --output result.png

# With custom prompt
curl -X POST "http://localhost:8000/outpaint" \
  -F "image=@photo.jpg" \
  -F "prompt=beautiful landscape" \
  -F "output_format=jpeg" \
  --output expanded.jpg

# Get JSON response
curl -X POST "http://localhost:8000/outpaint" \
  -F "image=@input.png" \
  -F "return_file=false"
```

### Python (requests)

```python
import requests

# Upload and outpaint
with open("input.png", "rb") as f:
    response = requests.post(
        "http://localhost:8000/outpaint",
        files={"image": f},
        data={
            "expand_left": 300,
            "expand_right": 300,
            "expand_top": 200,
            "expand_bottom": 200,
            "prompt": "beautiful scenery",
            "output_format": "png",
        }
    )

# Save result
with open("output.png", "wb") as f:
    f.write(response.content)

print("✓ Outpaint complete!")
```

### Python (httpx - async)

```python
import httpx
import asyncio

async def outpaint_image(image_path: str):
    async with httpx.AsyncClient() as client:
        with open(image_path, "rb") as f:
            response = await client.post(
                "http://localhost:8000/outpaint",
                files={"image": f},
                data={"expand_left": 250, "expand_right": 250},
                timeout=120.0,  # 2 minutes
            )

        with open("result.png", "wb") as f:
            f.write(response.content)

        return response.status_code == 200

# Run
success = asyncio.run(outpaint_image("input.png"))
```

### JavaScript (Fetch API)

```javascript
async function outpaintImage(file) {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('expand_left', 300);
    formData.append('expand_right', 300);
    formData.append('prompt', 'beautiful landscape');

    const response = await fetch('http://localhost:8000/outpaint', {
        method: 'POST',
        body: formData,
    });

    if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        // Display or download the image
        const img = document.createElement('img');
        img.src = url;
        document.body.appendChild(img);
    }
}

// Usage
const fileInput = document.querySelector('input[type="file"]');
fileInput.addEventListener('change', (e) => {
    outpaintImage(e.target.files[0]);
});
```

---

## 🔧 Configuration

### Environment Variables

Create `.env` file:

```bash
# Backend selection
OUTPAINT_BACKEND=comfyui  # or "falai"

# falai API key
FALAI_API_KEY=fal_xxxxxxxxxxxxxxxxxxxxxxxx

# ComfyUI settings
COMFYUI_URL=http://127.0.0.1:8188

# Server settings
API_HOST=0.0.0.0
API_PORT=8000
```

### Config File

Edit `outpaint_config.json`:

```json
{
  "backend": "comfyui",
  "falai_api_key": "fal_xxxxxxxx",
  "comfyui_url": "http://127.0.0.1:8188",
  "expand_left": 200,
  "expand_right": 200,
  "expand_top": 200,
  "expand_bottom": 200,
  "output_format": "png"
}
```

---

## 🛡️ Auto-Fallback Behavior

The API automatically handles backend failures:

```
Request → ComfyUI Backend
    ├─ Success → Return result ✓
    └─ Crash/Unavailable
        ↓
    Auto-detect failure
        ↓
    Switch to falai backend
        ↓
    Retry request
        ├─ Success → Return result ✓ (with fallback_triggered=true)
        └─ Failure → Return 500 error ✗
```

**Triggers for auto-fallback:**
- Connection refused (ComfyUI not running)
- Server crash during processing
- Timeout errors
- Any `RequestException` from ComfyUI

**Logged messages:**
```
INFO: Processing with backend: comfyui
WARNING: ComfyUI backend failed. Auto-switching to falai backend...
INFO: Successfully switched to falai backend
```

---

## 📊 Monitoring

### Health Check Endpoint

Use `/health` for monitoring:

```bash
# Check if API is healthy
curl http://localhost:8000/health

# Example response
{
  "status": "healthy",
  "backend": {
    "type": "comfyui",
    "available": true,
    "message": "ComfyUI ready"
  },
  "auto_fallback": "enabled"
}
```

### Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid image, parameters) |
| 500 | Server error (both backends failed) |
| 503 | Service unavailable (config error) |

---

## 🧪 Testing

### Manual Testing

```bash
# 1. Start server
python api_server.py

# 2. Test health
curl http://localhost:8000/health

# 3. Test outpaint
curl -X POST http://localhost:8000/outpaint \
  -F "image=@tests/fixtures/valid/gradient_512.png" \
  --output test_result.png

# 4. Verify output
ls -lh test_result.png
```

### Automated Testing

```python
# test_api.py
import httpx
import pytest

def test_health_check():
    response = httpx.get("http://localhost:8000/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_outpaint():
    with open("tests/fixtures/valid/gradient_512.png", "rb") as f:
        response = httpx.post(
            "http://localhost:8000/outpaint",
            files={"image": f},
            data={"expand_left": 100, "expand_right": 100},
            timeout=120.0,
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
```

---

## 🚀 Deployment

### Development

```bash
python api_server.py --reload
```

### Production (Gunicorn)

```bash
# Install gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn api_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Docker (Example)

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements_api.txt .
RUN pip install --no-cache-dir -r requirements_api.txt

COPY . .

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🔒 Security Considerations

### Production Checklist

- [ ] **API Key Protection** - Don't expose falai API key in responses
- [ ] **CORS Configuration** - Restrict `allow_origins` to specific domains
- [ ] **Rate Limiting** - Implement rate limiting (e.g., slowapi)
- [ ] **File Validation** - Validate uploaded file types and sizes
- [ ] **HTTPS** - Use HTTPS in production (nginx/caddy reverse proxy)
- [ ] **Authentication** - Add API key/OAuth for access control
- [ ] **Input Sanitization** - Validate all parameters
- [ ] **Temp File Cleanup** - Implement proper cleanup strategy

### Example: Add API Key Auth

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY = "your-secret-api-key"
api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

@app.post("/outpaint", dependencies=[Security(verify_api_key)])
async def outpaint(...):
    # Protected endpoint
    pass
```

---

## 📝 API Client Examples

### Full Python Client

```python
# outpaint_client.py
import requests
from pathlib import Path
from typing import Optional

class OutpaintClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def health_check(self) -> dict:
        """Check API health."""
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def outpaint(
        self,
        image_path: str,
        expand_left: int = 200,
        expand_right: int = 200,
        expand_top: int = 200,
        expand_bottom: int = 200,
        prompt: str = "",
        output_path: Optional[str] = None,
    ) -> str:
        """
        Outpaint an image.

        Args:
            image_path: Path to input image
            expand_*: Pixels to expand in each direction
            prompt: Text prompt for generation
            output_path: Where to save result (auto if None)

        Returns:
            Path to output image
        """
        with open(image_path, "rb") as f:
            response = requests.post(
                f"{self.base_url}/outpaint",
                files={"image": f},
                data={
                    "expand_left": expand_left,
                    "expand_right": expand_right,
                    "expand_top": expand_top,
                    "expand_bottom": expand_bottom,
                    "prompt": prompt,
                },
                timeout=120,
            )

        response.raise_for_status()

        # Save output
        if output_path is None:
            stem = Path(image_path).stem
            output_path = f"{stem}_outpainted.png"

        with open(output_path, "wb") as f:
            f.write(response.content)

        return output_path

# Usage
client = OutpaintClient()
print(client.health_check())
result = client.outpaint("input.png", expand_left=300, expand_right=300)
print(f"✓ Saved to: {result}")
```

---

## ✅ Ready for Integration!

Your API is now **production-ready** with:
- ✅ Auto-fallback ComfyUI → falai
- ✅ RESTful endpoints
- ✅ Interactive documentation
- ✅ Health monitoring
- ✅ Error handling
- ✅ CORS support
- ✅ File upload/download

**Start integrating with your application!** 🚀
