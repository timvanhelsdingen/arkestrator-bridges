---
name: workflow-patterns
description: "Workflow Patterns patterns and best practices for comfyui"
metadata:
  program: comfyui
  category: bridge
  title: Workflow Patterns
  keywords: ["comfyui", "workflow-patterns"]
  source: bridge-repo
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

## Queue Management
- Queue prompt via API: POST /prompt with workflow JSON
- Check progress: GET /history/{prompt_id}
- Cancel: POST /interrupt
