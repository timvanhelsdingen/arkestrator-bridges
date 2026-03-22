# ComfyUI API Patterns

## Official Documentation
- ComfyUI repository: https://github.com/comfyanonymous/ComfyUI
- API example: https://github.com/comfyanonymous/ComfyUI/blob/master/script_examples/basic_api_example.py
- ComfyUI wiki: https://github.com/comfyanonymous/ComfyUI/wiki

## Workflow Execution
Workflows are submitted as JSON node graphs via the API. Each node has a class type, inputs, and outputs that wire together.

### Workflow JSON Structure
```json
{
  "1": {
    "class_type": "KSampler",
    "inputs": {
      "model": ["2", 0],
      "positive": ["3", 0],
      "negative": ["4", 0],
      "latent_image": ["5", 0],
      "seed": 42,
      "steps": 20,
      "cfg": 7.0,
      "sampler_name": "euler",
      "scheduler": "normal",
      "denoise": 1.0
    }
  }
}
```

### Common Node Types
- `CheckpointLoaderSimple` — load SD checkpoints
- `CLIPTextEncode` — text-to-embedding (positive/negative prompts)
- `KSampler` — diffusion sampling
- `VAEDecode` — latent to image
- `SaveImage` / `PreviewImage` — output nodes
- `EmptyLatentImage` — create blank latent
- `LoadImage` — load image from disk
- `ImageScale` / `ImageUpscaleWithModel` — resize/upscale

## Model Policy
- Prefer models already installed and validated in the environment
- If required weights are missing and installation is allowed, install to correct ComfyUI model folders
- If installation is not allowed, fail clearly with exact missing models/nodes and alternatives

## Cross-Machine Delivery
- If user requests delivery to a path on another machine, do not write directly to that foreign path
- Generate on ComfyUI, capture returned artifact payload(s)
- Run a second bridge command on the destination worker (use `targetType:"id"`) to write the file
- Verify file existence/size/type on the destination worker before PASS

## Resource Contention
- Treat workflow generation/upscale/inpaint/video runs as `gpu_vram_heavy`
- Do not launch generation on a worker already busy with another heavy GPU task
- Lightweight inspection/model-list/history checks are fine during heavy tasks

## Scope Rules
- Reuse project workflow conventions when references exist
- Keep changes aligned to requested output
- Treat destination filesystem paths as machine-local
- Do not run broad scans outside project/configured source paths
