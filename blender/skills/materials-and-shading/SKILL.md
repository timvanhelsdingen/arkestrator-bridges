---
name: materials-and-shading
description: "Materials & Shading patterns and best practices for blender"
metadata:
  program: blender
  category: bridge
  title: Materials & Shading
  keywords: ["blender", "materials", "shading", "nodes", "principled-bsdf", "texture", "cycles", "eevee"]
  source: bridge-repo
  related-skills: ["rendering", "python-api"]
---

# Blender Materials & Shading

## Creating Materials via bpy
- Always check if material exists before creating: `bpy.data.materials.get("name")`
- Use `obj.data.materials.append(mat)` to assign
- For Cycles/EEVEE node materials: `mat.use_nodes = True` then work with `mat.node_tree.nodes`

## Common Node Setups
- Principled BSDF: `nodes.new("ShaderNodeBsdfPrincipled")` — set Base Color, Metallic, Roughness
- Image Texture: `nodes.new("ShaderNodeTexImage")` — load with `bpy.data.images.load(path)`
- Mix Shader: combine two shaders with a factor

## Tips
- Always link nodes: `mat.node_tree.links.new(output_socket, input_socket)`
- Remove default Principled BSDF before adding custom nodes if needed
- Use `mat.diffuse_color` for viewport display color (not render color)
