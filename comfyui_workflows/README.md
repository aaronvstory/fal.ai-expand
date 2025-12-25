# ComfyUI workflows

This folder contains ComfyUI workflow templates used by the local (ComfyUI) backend.

## flux_outpaint.json

`flux_outpaint.json` is a starter template. For best results, create and test your own workflow in ComfyUI and export it as **API Format**, then overwrite this file.

Expected nodes (by `class_type`):
- `LoadImage`
- `ImagePadForOutpaint`
- `VAEEncode` / `VAEDecode` / `VAELoader`
- `KSampler`
- `CLIPTextEncode` (positive + negative)
- `DualCLIPLoader` (or compatible alternative)
- `UNETLoader` (or compatible alternative)
- `SaveImage`
