# Houdini HOM/Python Scripting

## Official Documentation
- HOM overview: https://www.sidefx.com/docs/houdini/hom/
- hou module: https://www.sidefx.com/docs/houdini/hom/hou/
- SOP nodes: https://www.sidefx.com/docs/houdini/nodes/sop/
- DOP nodes: https://www.sidefx.com/docs/houdini/nodes/dop/
- Solaris docs: https://www.sidefx.com/docs/houdini/solaris/
- Karma render settings: https://www.sidefx.com/docs/houdini/nodes/lop/karmarendersettings.html
- SideFX content library: https://www.sidefx.com/contentlibrary/
- Tokeru Houdini notes: https://www.tokeru.com/cgwiki/?title=Houdini

## Core API
- `hou.node("/obj/geo1")` — access nodes by path
- `hou.hipFile.save()` / `hou.hipFile.load()` — file operations
- `hou.pwd()` — current node context
- `hou.ui` — UI interaction (viewports, dialogs)

## Common Patterns

### Node Creation
```python
import hou
obj = hou.node("/obj")
geo = obj.createNode("geo", "my_geo")
box = geo.createNode("box", "base_box")
box.parm("sizex").set(2.0)
```

### Parameter Access
```python
node = hou.node("/obj/geo1/box1")
node.parm("sizex").set(5.0)
value = node.parm("sizex").eval()
node.parmTuple("size").set((1, 2, 3))
```

### Node Connections
```python
merge = geo.createNode("merge")
merge.setInput(0, box)
merge.setInput(1, sphere)
merge.setDisplayFlag(True)
merge.setRenderFlag(True)
```

### Geometry Access
```python
node = hou.node("/obj/geo1/output0")
geo = node.geometry()
points = geo.points()
for pt in points:
    pos = pt.position()
```

## Live vs Headless
- Prefer live bridge for active HIP work
- Prefer hython for non-active-file analysis/validation
- State which mode was used and why

## Scope Rules
- Do not force pyro workflows unless explicitly requested
- Do not force Solaris/Karma for SOP-only tasks
- Keep edits narrow and request-aligned
- Default output paths to project-local locations (`projectRoot` or `$HIP`)
- If HIP resolves under temp paths, re-anchor to `projectRoot`

## Resource Contention
- Treat Karma/Mantra/Husk renders and heavy sim/cache operations as `gpu_vram_heavy`
- Do not overlap heavy Houdini steps with other GPU-heavy bridge tasks on the same worker
