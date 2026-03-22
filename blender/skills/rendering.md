---
title: Rendering
category: bridge
---
# Blender Rendering

## Render Setup
- Set engine: `bpy.context.scene.render.engine = 'CYCLES'` or `'BLENDER_EEVEE_NEXT'`
- Resolution: `scene.render.resolution_x`, `scene.render.resolution_y`
- Output path: `scene.render.filepath = "/path/to/output"`
- File format: `scene.render.image_settings.file_format = 'PNG'`

## Camera
- Set active camera: `scene.camera = cam_obj`
- Frame the scene: use `bpy.ops.view3d.camera_to_view_selected()` in viewport context

## Executing Render
- Still: `bpy.ops.render.render(write_still=True)`
- Animation: `bpy.ops.render.render(animation=True)`
- Always verify output file exists and has non-zero size after render

## GPU/VRAM
- Treat renders as gpu_vram_heavy operations
- Never start a render while another heavy GPU task is running on the same worker
