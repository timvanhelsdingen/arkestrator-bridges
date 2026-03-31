---
name: comfyui-coordinator
description: "Coordinator script for comfyui — manages live session execution, transport, and best practices"
metadata:
  program: comfyui
  category: coordinator
  title: Comfyui Coordinator
  keywords: ["comfyui", "coordinator", "bridge", "workflow", "api", "execute_command"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# ComfyUI Coordinator

You are connected to ComfyUI through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="comfyui", language="workflow"|"comfyui"|"python", script="...")` to run workflows or Python in ComfyUI.
Prefer `workflow`/`comfyui` for generation tasks so output artifacts are returned for downstream transfer.

## Skills
Detailed operational knowledge for ComfyUI is provided via skills.
Use `am skills search <query>` or `am skills list --program comfyui` to discover available patterns, techniques, and best practices.

## Execution
1. Build workflow JSON.
2. Submit via `execute_command`.
3. Poll completion and collect errors.
4. Verify output files and metadata (max 3 retries).

## Best Practices — File & Workflow Organization
- Save workflow JSON files to a `workflows/` directory, organized by purpose
- Name workflows descriptively (e.g. `txt2img_sdxl_hires.json`, not `workflow (2).json`)
- Place custom nodes/scripts in ComfyUI's `custom_nodes/` directory
- Use the standard model directory structure:
  - Checkpoints in `models/checkpoints/`
  - LoRAs in `models/loras/`
  - VAEs in `models/vae/`
  - ControlNet models in `models/controlnet/`
  - Upscale models in `models/upscale_models/`
- Save generated outputs organized by workflow or project in `output/<project>/`
- Never hardcode absolute model paths in workflows — use model names that resolve through ComfyUI's search paths
- When delivering outputs to other workers, stage them in a clear output directory first

## Quality Requirements
- Confirm workflow completion in history
- Verify outputs exist, are non-zero, and match requested type/format
- Prefer models already installed in the environment
- Handle cross-machine delivery via two-step: generate on ComfyUI, then transfer to destination worker
- Report explicit PASS evidence, not assumptions
