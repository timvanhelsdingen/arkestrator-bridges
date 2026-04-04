---
name: model-selection
description: "Hardware-aware model selection, task classification, and automatic model download for ComfyUI"
metadata:
  program: comfyui
  category: bridge
  title: Model Selection & Task Intelligence
  keywords: ["comfyui", "models", "download", "hardware", "vram", "textures", "pbr", "civitai", "huggingface", "task-classification"]
  source: bridge-repo
  priority: 80
  related-skills: ["workflow-patterns", "api-patterns"]
---

# Model Selection & Task Intelligence

## Hardware Discovery (Always Do First)

Before selecting any model or building a workflow, determine the hardware constraints:

```python
import subprocess, json, os

# Get GPU info from ComfyUI's system stats
import comfy.model_management as mm

vram_total = mm.get_total_memory() / (1024**3)  # GB
vram_free  = mm.get_free_memory() / (1024**3)   # GB

# Also check via the API: GET /system_stats
# Returns: { "system": { "devices": [{ "name": "...", "type": "cuda", "vram_total": ..., "vram_free": ... }] } }

print(f"GPU VRAM: {vram_total:.1f} GB total, {vram_free:.1f} GB free")
```

### VRAM Guidelines
Use these as rough guidelines — actual usage varies by model, batch size, and workflow complexity:

| Available VRAM | Typical Fit | Notes |
|---------------|------------|-------|
| < 4 GB        | SD 1.5 (fp16) | May need `--lowvram` or `--cpu` offload |
| 4-8 GB        | SD 1.5 / SDXL (fp16) | SDXL may need offloading at lower VRAM |
| 8-12 GB       | SDXL / Flux (quantized) | Flux fp8/nf4 fits here |
| 12+ GB        | Most models | Comfortable for full-precision workflows |

**Always check VRAM before selecting a model. Never try to load a model that won't fit. But pick the best model for the task — not necessarily the biggest.**

---

## Task Classification

Classify every request into one of these categories BEFORE selecting models or building workflows. The category determines which models, prompts, and workflow structures to use.

### PBR Textures / Materials
**Identifying signals**: "texture", "material", "PBR", "tileable", "seamless", "albedo", "normal map", "roughness", "metallic", "height map", "displacement", "AO", "ambient occlusion"

**Critical rules**:
- Textures are FLAT — no perspective, no 3D objects, no scenes, no people
- Textures MUST tile seamlessly — use seamless/tiling workflows
- Output individual maps: albedo/diffuse, normal, roughness, metallic, height/displacement, AO
- Typical resolution: 1024x1024 or 2048x2048 (power of 2, square)
- Prompt structure: describe the surface material only — e.g. "worn wooden planks, scratches, natural grain" NOT "a photo of a wooden floor in a room"
- NEVER include scene descriptions, lighting setups, camera angles, or subjects in texture prompts
- Add negative prompt: "perspective, 3d render, objects, people, scene, photograph, depth of field, bokeh, shadows, text, watermark"

**Recommended models** (search in order of preference):
1. Texture-specialized checkpoints: search CivitAI for "texture", "material", "PBR", "seamless"
2. Stable Diffusion 1.5-based texture models (lower VRAM, good quality for textures)
3. For tiling: use the "Tiled KSampler" or "seamless tiling" custom nodes
4. For normal/roughness maps: use image-to-image with specialized normal map models, or depth estimation nodes

**Workflow pattern**:
- txt2img for albedo/diffuse → then derive other maps via img2img or specialized nodes
- Or use multi-output texture generation workflows if available
- Always verify tileability by tiling the output 2x2 and checking seams

### Concept Art / Illustrations
**Identifying signals**: "concept art", "illustration", "character design", "environment design", "stylized", "painting"

**Critical rules**:
- Use art/illustration-focused checkpoints, not photorealistic ones
- Match the art style to the request (anime, painterly, comic, etc.)
- Common resolutions: 768x1024 (portrait), 1024x768 (landscape), 1024x1024 (square)

**Recommended models**: Search CivitAI for the specific art style + "SDXL" or "SD1.5"

### Photorealistic Images
**Identifying signals**: "photo", "realistic", "portrait", "photograph", "product shot"

**Critical rules**:
- Use photorealistic checkpoints (Juggernaut XL, RealVisXL, etc.)
- Include camera/lens details in prompts for realism
- Use appropriate aspect ratios for the subject

### Video Generation
**Identifying signals**: "video", "animation", "animate", "motion", "AnimateDiff", "SVD"

**Critical rules**:
- Check VRAM carefully — video generation is extremely memory-intensive
- AnimateDiff for SD1.5 (~6 GB+), SVD for higher quality (~12 GB+)
- Keep frame counts reasonable for available VRAM (16-24 frames typical)
- Lower resolution than image generation (512x512 for AnimateDiff)

### Upscaling
**Identifying signals**: "upscale", "enhance", "super resolution", "enlarge", "4x", "2x"

**Critical rules**:
- Use dedicated upscale models (RealESRGAN, NMKD-Siax, 4x-UltraSharp)
- Upscale models go in `models/upscale_models/`
- Consider tiled upscaling for large images to stay within VRAM
- For creative upscale: use img2img at higher resolution with low denoise (0.2-0.4)

### Inpainting / Editing
**Identifying signals**: "inpaint", "edit", "fix", "replace", "remove", "fill"

**Critical rules**:
- Use inpainting-specific model variants when available (e.g. `*-inpainting.safetensors`)
- Provide proper mask — white = edit area, black = keep area
- Set denoise appropriately: 0.5-0.8 for changes, 0.3-0.5 for subtle edits

### ControlNet / Guided Generation
**Identifying signals**: "pose", "depth", "edge", "canny", "openpose", "reference", "structure"

**Critical rules**:
- Match ControlNet model to the base checkpoint (SD1.5 ControlNet for SD1.5 models, SDXL ControlNet for SDXL)
- ControlNet models go in `models/controlnet/`
- Multiple ControlNets stack VRAM usage

---

## Model Search & Download

### Step 1: Check What's Already Installed

```python
import os, json

# List installed models by category
comfy_path = os.environ.get("COMFYUI_PATH", "")  # or detect from server info
model_dirs = {
    "checkpoints": os.path.join(comfy_path, "models", "checkpoints"),
    "loras": os.path.join(comfy_path, "models", "loras"),
    "vae": os.path.join(comfy_path, "models", "vae"),
    "controlnet": os.path.join(comfy_path, "models", "controlnet"),
    "upscale_models": os.path.join(comfy_path, "models", "upscale_models"),
    "clip": os.path.join(comfy_path, "models", "clip"),
    "unet": os.path.join(comfy_path, "models", "unet"),
}

for category, path in model_dirs.items():
    if os.path.exists(path):
        files = [f for f in os.listdir(path) if f.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin'))]
        print(f"{category}: {files}")
```

Also query via API: the bridge context should list available checkpoints and models.

### Step 2: Determine What's Needed

Based on task classification, determine:
1. What base checkpoint is best suited (SD1.5, SDXL, Flux, SD3.5)
2. Whether specialized LoRAs would help
3. Whether ControlNet/upscale/VAE models are needed
4. Whether custom nodes need to be installed

### Step 3: Search for Models

Search these sources for the best model for the task:

**CivitAI** (primary source for fine-tuned models):
- Use the web to search CivitAI for task-specific models
- Search terms: combine the content type + base model + "comfyui"
- Example: "PBR texture seamless SDXL" or "photorealistic portrait SDXL"
- Prefer models with high download counts and ratings
- Check model page for recommended settings (steps, CFG, sampler, resolution)

**Hugging Face** (primary source for base models and research models):
- Flux models: `black-forest-labs/FLUX.1-dev`, `black-forest-labs/FLUX.1-schnell`
- SD3.5: `stabilityai/stable-diffusion-3.5-large`
- SDXL: `stabilityai/stable-diffusion-xl-base-1.0`

### Step 4: Download Models

```python
import urllib.request, os

def download_model(url, dest_dir, filename):
    """Download a model file to the correct ComfyUI directory."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    if os.path.exists(dest_path):
        print(f"Already exists: {dest_path}")
        return dest_path

    print(f"Downloading {filename} to {dest_dir}...")
    # For large files, use wget/curl subprocess for better progress/resume
    import subprocess
    result = subprocess.run(
        ["wget", "-c", "-O", dest_path, url],
        capture_output=True, text=True
    )
    # Fallback: try curl if wget unavailable
    if result.returncode != 0:
        result = subprocess.run(
            ["curl", "-L", "-C", "-", "-o", dest_path, url],
            capture_output=True, text=True
        )

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"Downloaded: {dest_path} ({os.path.getsize(dest_path) / 1e9:.1f} GB)")
        return dest_path
    else:
        raise RuntimeError(f"Download failed for {filename}")

# Example: download an upscale model
# download_model(
#     "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth",
#     os.path.join(comfy_path, "models", "upscale_models"),
#     "realesr-general-x4v3.pth"
# )
```

### Step 5: Install Custom Nodes If Needed

Some tasks require custom nodes (e.g., tiled generation, AnimateDiff, IPAdapter):

```python
import subprocess, os

custom_nodes_dir = os.path.join(comfy_path, "custom_nodes")

def install_custom_node(repo_url, node_name):
    """Clone a custom node repo into ComfyUI's custom_nodes directory."""
    dest = os.path.join(custom_nodes_dir, node_name)
    if os.path.exists(dest):
        print(f"Already installed: {node_name}")
        return
    subprocess.run(["git", "clone", repo_url, dest], check=True)
    # Install requirements if they exist
    req_file = os.path.join(dest, "requirements.txt")
    if os.path.exists(req_file):
        subprocess.run(["pip", "install", "-r", req_file], check=True)
    print(f"Installed: {node_name} — restart ComfyUI to load")
```

**Important**: After installing custom nodes, ComfyUI usually needs a restart to pick them up. Check if the node class is available before assuming it loaded.

---

## Model Selection Decision Tree

```
Request received
  │
  ├─ Classify task type (see Task Classification above)
  │
  ├─ Check hardware (VRAM, GPU)
  │    └─ Determine max model size and resolution
  │
  ├─ Check installed models
  │    ├─ Suitable model found → use it
  │    └─ No suitable model → search & download
  │         ├─ Search CivitAI / HuggingFace for task-specific model
  │         ├─ Verify model fits in VRAM budget
  │         ├─ Download to correct ComfyUI directory
  │         └─ Verify model loads successfully
  │
  ├─ Check if custom nodes needed
  │    ├─ Nodes available → proceed
  │    └─ Nodes missing → install, may need restart
  │
  └─ Build workflow with selected model + task-appropriate settings
       └─ Apply task-specific rules (tiling, resolution, prompting, etc.)
```

---

## Common Pitfalls

1. **Using photorealistic models for textures** — produces photos of surfaces with perspective/depth instead of flat tileable textures. "Careful prompting" does NOT fix this — the model's training data determines what it can produce. DreamShaper, Juggernaut, RealVis etc. are WRONG for textures regardless of prompt.
2. **Ignoring VRAM limits** — causes OOM crashes or silent quality degradation from aggressive offloading
3. **Wrong resolution for the model** — SD1.5 trained at 512, SDXL at 1024, Flux at 1024+; wrong resolution = artifacts
4. **Generic prompts** — "a wooden texture" is too vague; "seamless weathered oak wood planks, natural grain detail, scratches, flat surface, top-down view" is actionable
5. **Not checking for specialized models** — a generic SDXL model will never match a texture-fine-tuned model for PBR output. With 24GB VRAM and internet access, there is NO excuse for not downloading the right model.
6. **Ignoring available VRAM headroom** — if a better-suited model exists that fits your VRAM, use it. But don't force a larger model when a well-matched smaller one does the job — a texture-specialized SD1.5 model can outperform a generic SDXL model for that specific task.
7. **Skipping tiling verification** — generating a "seamless" texture without verifying it actually tiles
