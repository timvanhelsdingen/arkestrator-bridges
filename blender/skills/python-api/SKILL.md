---
name: python-api
description: "Python Api patterns and best practices for blender"
metadata:
  program: blender
  category: bridge
  title: Python Api
  keywords: ["blender", "python-api"]
  source: bridge-repo
---

# Blender Python API Patterns

## Official Documentation
- Blender Python API: https://docs.blender.org/api/current/
- Best practices: https://docs.blender.org/api/current/info_best_practice.html
- Operators: https://docs.blender.org/api/current/bpy.ops.html

## Core API Access
- `bpy.data` — access all data blocks (meshes, materials, objects, scenes)
- `bpy.context` — current state (active object, selected objects, mode)
- `bpy.ops` — operators (modeling, mesh, object, render, etc.)
- `bpy.types` — type definitions for all Blender data

## Common Patterns

### Object Creation
```python
import bpy
mesh = bpy.data.meshes.new("MyMesh")
obj = bpy.data.objects.new("MyObject", mesh)
bpy.context.collection.objects.link(obj)
```

### Selection and Active Object
```python
bpy.ops.object.select_all(action='DESELECT')
obj = bpy.data.objects["MyObject"]
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
```

### Modifiers
```python
obj = bpy.context.active_object
mod = obj.modifiers.new(name="Subsurf", type='SUBSURF')
mod.levels = 2
bpy.ops.object.modifier_apply(modifier=mod.name)
```

### Material Assignment
```python
mat = bpy.data.materials.new("MyMaterial")
mat.use_nodes = True
obj.data.materials.append(mat)
```

### Context Overrides
When operators require specific context (mode, selection), set it explicitly before calling.
Use `bpy.context.view_layer.update()` after batch changes to ensure state is consistent.

## Scope Rules
- Keep edits narrowly scoped to the request
- Do not rebuild unrelated scene systems
- Do not run broad disk scans outside project paths
- Use provided attachment/context paths directly

## Resource Contention
- Treat renders, bake jobs, and heavy GPU operations as `gpu_vram_heavy`
- Do not overlap heavy Blender tasks with other GPU-heavy bridge operations on the same worker
