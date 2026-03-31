---
name: procedural-modeling
description: "Procedural Modeling patterns and best practices for houdini"
metadata:
  program: houdini
  category: bridge
  title: Procedural Modeling
  keywords: ["houdini", "procedural", "modeling", "copy-to-points", "scatter", "for-each"]
  source: bridge-repo
  related-skills: ["sop-networks", "hom-scripting"]
---

# Houdini Procedural Modeling

## Copy to Points Pattern
1. Create base shape (box, custom geo)
2. Create point distribution (scatter on surface, circle, grid)
3. Add point attributes for variation (@pscale, @orient, @Cd)
4. copytopoints SOP to instance shape onto points

## L-Systems
- `geo.createNode("lsystem")`
- Set premise, rules, generations
- Good for trees, fractals, organic structures

## Sweep & Rails
- Create profile curve and rail curve
- `sweep` SOP: profile along rail path
- Good for pipes, roads, rails, cables

## Procedural UV
- `uvproject` for planar projection
- `uvunwrap` for automatic unwrapping
- `uvflatten` for interactive-style auto flatten

## Export
- File SOP: `node.parm("file").set("/path/to/output.bgeo.sc")`
- ROP Geometry: for rendering pipeline
- Alembic ROP: for animation export
- FBX/glTF: via ROP FBX Output or labs nodes
