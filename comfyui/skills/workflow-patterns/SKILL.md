---
name: workflow-patterns
description: "Workflow Patterns patterns and best practices for comfyui"
metadata:
  program: comfyui
  category: bridge
  title: Workflow Patterns
  keywords: ["comfyui", "workflow", "ksampler", "checkpoint", "vae", "clip", "nodes"]
  source: bridge-repo
  related-skills: ["api-patterns"]
---

# ComfyUI Workflow Patterns

## Node Creation
- Use the ComfyUI API to create and connect nodes
- Common node types: KSampler, CheckpointLoaderSimple, CLIPTextEncode, VAEDecode, SaveImage

## Basic txt2img Workflow
1. CheckpointLoaderSimple → load model
2. CLIPTextEncode × 2 → positive and negative prompts
3. EmptyLatentImage → set dimensions
4. KSampler → connect model, positive, negative, latent
5. VAEDecode → decode latent to image
6. SaveImage → save output

## Parameter Tips
- Steps: 20-30 for quality, 8-15 for speed
- CFG Scale: 7-8 typical, lower (3-5) for newer models
- Sampler: euler_ancestral for variety, dpmpp_2m for quality
- Scheduler: normal or karras

## Task-Specific Workflow Patterns

### PBR Texture Generation
1. CheckpointLoaderSimple → load **texture-specialized** checkpoint (NOT a generic photorealistic model)
2. CLIPTextEncode (positive) → describe surface material ONLY: "worn wooden planks, scratches, natural grain, flat top-down view, seamless tileable"
3. CLIPTextEncode (negative) → "perspective, 3d render, objects, people, scene, photograph, depth of field, bokeh, shadows, text, watermark, frame, border"
4. EmptyLatentImage → **square, power-of-2**: 1024x1024 or 2048x2048
5. KSampler → connect all; use model-recommended settings
6. VAEDecode → decode to image
7. SaveImage → save albedo/diffuse map
8. *Optional*: use img2img pipeline from albedo to generate normal, roughness, height maps
9. *Tiling*: use "Tiled KSampler" or seamless tiling custom nodes to ensure tileable output

**Critical**: Textures are FLAT — never use prompts that describe scenes, objects, or perspective views.

### Upscale Workflow
1. LoadImage → load source image
2. UpscaleModelLoader → load dedicated upscale model (RealESRGAN, 4x-UltraSharp, etc.)
3. ImageUpscaleWithModel → upscale
4. SaveImage → save result
- For images larger than VRAM allows: use tiled upscaling nodes

### Inpainting Workflow
1. LoadImage → load source image
2. LoadImage → load mask (white = edit area)
3. CheckpointLoaderSimple → load inpainting model variant if available
4. VAEEncode (with mask) → encode masked image to latent
5. CLIPTextEncode × 2 → prompts for the inpainted region
6. KSampler → denoise 0.5-0.8 for changes, 0.3-0.5 for subtle edits
7. VAEDecode → decode
8. SaveImage → save result

### ControlNet-Guided Generation
1. Load base checkpoint + ControlNet model (must match: SD1.5 ControlNet for SD1.5, SDXL for SDXL)
2. Load/preprocess control image (Canny, depth, pose, etc.)
3. Apply ControlNet conditioning to positive prompt
4. KSampler with combined conditioning
5. Decode and save

## Queue Management
- Queue prompt via API: POST /prompt with workflow JSON
- Check progress: GET /history/{prompt_id}
- Cancel: POST /interrupt
