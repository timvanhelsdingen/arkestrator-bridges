---
name: python-api
description: "Python Api patterns and best practices for nuke"
metadata:
  program: nuke
  category: bridge
  title: Python Api
  keywords: ["nuke", "python", "api", "nuke-module", "callbacks", "knobs"]
  source: bridge-repo
  related-skills: ["compositing", "node-patterns", "nuke-nc-workarounds"]
---

# Nuke Python API Patterns

## Official Documentation
- Nuke Python Dev Guide: https://learn.foundry.com/nuke/developers/latest/pythondevguide/
- Nuke Python Reference: https://learn.foundry.com/nuke/developers/latest/pythonreference/
- Callbacks: https://learn.foundry.com/nuke/developers/latest/pythondevguide/callbacks.html

## Core API Access
- `nuke.createNode("Type")` -- create a node (verify return value; may be None in NC)
- `nuke.toNode("name")` -- find node by name (use `_ark_find_node()` for reliability)
- `nuke.selectedNodes()` -- get selected nodes
- `nuke.allNodes("ClassName")` -- class-filtered query (PREFERRED, reliable)
- `nuke.allNodes()` -- all nodes in current group (UNRELIABLE in NC -- use `_ark_all_nodes()`)
- `nuke.root()` -- root node (project settings)
- `nuke.executeInMainThread(func)` -- thread-safe execution
- `node.dependent()` -- downstream nodes (MOST RELIABLE for graph traversal)
- `node.dependencies()` -- upstream nodes (reliable)

> **NC Note:** See `nuke-nc-workarounds` skill for critical patterns when working with Nuke Non-Commercial.

## Common Patterns

### Node Creation and Wiring
```python
import nuke
blur = nuke.createNode("Blur")
blur["size"].setValue(10)
blur.setInput(0, source_node)

# Connect output to next node
merge = nuke.createNode("Merge2")
merge.setInput(0, bg)
merge.setInput(1, blur)
```

### Knob Access
```python
node = nuke.toNode("Grade1")
node["multiply"].setValue(1.5)
value = node["multiply"].value()
node["channels"].setValue("rgb")

# Animated knobs
node["multiply"].setAnimated()
node["multiply"].setValueAt(1.0, 1001)  # value, frame
node["multiply"].setValueAt(2.0, 1050)
```

### Expressions
```python
node["translate"].setExpression("curve")
node["size"].setExpression("[value parent.input0.width] / 2")
node["file"].setValue("[value root.name]/../output/comp.####.exr")
```

### Script Operations
```python
nuke.scriptSave("/path/to/script.nk")
nuke.scriptOpen("/path/to/script.nk")
nuke.scriptClear()

# Export selected as .nk
nuke.nodeCopy("/path/to/nodes.nk")
nuke.nodePaste("/path/to/nodes.nk")
```

### Rendering
```python
write = nuke.toNode("Write1")
nuke.execute(write, 1001, 1100)  # node, first, last
nuke.execute(write, 1001, 1100, 1)  # with step
```

### Node Graph Layout
```python
node.setXYpos(100, 200)
x, y = node.xpos(), node.ypos()

backdrop = nuke.nodes.BackdropNode(
    xpos=50, ypos=150,
    bdwidth=400, bdheight=300,
    label="Color Correction",
    note_font_size=42,
)
```

### Channels and Layers
```python
shuffle = nuke.createNode("Shuffle2")
shuffle["in1"].setValue("rgba")
shuffle["out1"].setValue("rgba")

# Add custom channel
nuke.Layer("custom", ["custom.red", "custom.green", "custom.blue", "custom.alpha"])
```

## Thread Safety
- Node graph operations MUST run on the main thread
- Use `nuke.executeInMainThread(callable)` from background threads
- The bridge handles this automatically for command execution

## Persistent Execution Context
- The bridge maintains a persistent Python context across `execute_command` calls
- Variables, node references, and imports survive between commands within a job
- Session resets on new jobs and WebSocket reconnects
- Bridge helpers (`_ark_sync_graph`, `_ark_all_nodes`, `_ark_find_node`) are pre-injected

## Scope Rules
- Keep edits narrowly scoped to the request
- Do not restructure entire scripts
- Use existing naming conventions
- Default output paths to project-relative locations
