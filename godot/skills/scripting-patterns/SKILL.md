---
name: scripting-patterns
description: "GDScript Patterns patterns and best practices for godot"
metadata:
  program: godot
  category: bridge
  title: GDScript Patterns
  keywords: ["godot", "gdscript", "patterns", "signals", "export", "ready"]
  source: bridge-repo
  related-skills: ["scene-management", "gdscript-api"]
---

# Godot GDScript Patterns

## Writing Scripts from Agent
- Write script content to res:// path using FileAccess
- Attach to node: `node.set_script(load("res://path/to/script.gd"))`
- Always use `var f = FileAccess.open(path, FileAccess.WRITE)` then `f.store_string(content)` then `f.close()`

## Common Script Templates

### CharacterBody3D Movement
- `_physics_process(delta)` for movement
- `move_and_slide()` after setting `velocity`
- Gravity: `velocity.y -= gravity * delta`
- Input: `Input.get_vector("left", "right", "forward", "back")`

### Area3D Detection
- Connect `body_entered` signal for collision detection
- Use `monitoring = true` and appropriate collision layers

## File Operations
- Read: `FileAccess.open(path, FileAccess.READ).get_as_text()`
- Write: `FileAccess.open(path, FileAccess.WRITE).store_string(content)`
- Check exists: `FileAccess.file_exists(path)`
