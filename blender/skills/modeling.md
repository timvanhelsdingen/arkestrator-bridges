---
title: Modeling Basics
category: bridge
---
# Blender Modeling

## Creating Primitives
- `bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))`
- `bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)`
- `bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=2)`

## Modifiers
- Add: `obj.modifiers.new(name="Subsurf", type='SUBSURF')`
- Apply: `bpy.ops.object.modifier_apply(modifier="Subsurf")` (context-dependent)
- Common: SUBSURF, MIRROR, ARRAY, BOOLEAN, SOLIDIFY

## Transforms
- `obj.location = (x, y, z)`
- `obj.rotation_euler = (rx, ry, rz)` (radians)
- `obj.scale = (sx, sy, sz)`
- Apply transforms: `bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)`

## Scene Cleanup
- Delete object: `bpy.data.objects.remove(obj, do_unlink=True)`
- Delete all: iterate `bpy.data.objects` and remove each
- Purge orphan data: `bpy.ops.outliner.orphans_purge(do_recursive=True)`
