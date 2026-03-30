---
name: compositing
description: "Compositing patterns and best practices for nuke"
metadata:
  program: nuke
  category: bridge
  title: Compositing
  keywords: ["nuke", "compositing"]
  source: bridge-repo
---

# Nuke Compositing Patterns

## Official Documentation
- Nuke Python API: https://learn.foundry.com/nuke/developers/latest/pythondevguide/
- Nuke Python Reference: https://learn.foundry.com/nuke/developers/latest/pythonreference/
- TCL Reference: https://learn.foundry.com/nuke/content/comp_environment/tcl_scripting/tcl_scripting.html
- Node Reference: https://learn.foundry.com/nuke/content/reference_guide/node_reference.html

## Core Node Patterns

### Read/Write Pipeline
```python
import nuke
read = nuke.createNode("Read")
read["file"].setValue("/path/to/input.####.exr")
read["first"].setValue(1001)
read["last"].setValue(1100)

write = nuke.createNode("Write")
write["file"].setValue("/path/to/output.####.exr")
write["file_type"].setValue("exr")
write.setInput(0, read)
```

### Color Correction Chain
```python
grade = nuke.createNode("Grade")
grade["multiply"].setValue([1.2, 1.0, 0.9, 1.0])  # RGBA
grade["gamma"].setValue(0.95)
grade.setInput(0, source_node)

cc = nuke.createNode("ColorCorrect")
cc["saturation"].setValue(1.1)
cc.setInput(0, grade)
```

### Merge Operations
```python
merge = nuke.createNode("Merge2")
merge["operation"].setValue("over")
merge.setInput(0, bg_node)   # B input (background)
merge.setInput(1, fg_node)   # A input (foreground)
```

### Keying Workflow
```python
keyer = nuke.createNode("Keylight")
keyer.setInput(0, plate_node)
# Set screen color from clean plate or picker

premult = nuke.createNode("Premult")
premult.setInput(0, keyer)
```

### Transform/Reformat
```python
transform = nuke.createNode("Transform")
transform["translate"].setValue([100, 50])
transform["rotate"].setValue(15)
transform["scale"].setValue(1.2)
transform["center"].setValue([960, 540])

reformat = nuke.createNode("Reformat")
reformat["type"].setValue("to format")
reformat["format"].setValue("HD_1080")
```

## Best Practices
- Always set frame ranges on Read nodes explicitly
- Use Dot nodes to organize complex graphs
- Group related operations into Group or Gizmo nodes
- Use Backdrop nodes to visually organize sections
- Set Write node paths relative to project root when possible
- Use `[value root.name]` TCL expression for project-relative paths

## Scope Rules
- Keep compositing edits narrowly scoped to the request
- Do not restructure entire comp trees for narrow fixes
- Use existing naming conventions in the project
- Respect existing channel/layer setups

## Resource Contention
- Treat renders and heavy DeepImage operations as `gpu_vram_heavy`
- Do not overlap heavy Nuke tasks with other GPU-heavy bridge operations on the same worker
