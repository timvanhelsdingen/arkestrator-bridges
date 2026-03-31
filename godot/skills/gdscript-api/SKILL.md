---
name: gdscript-api
description: "Gdscript Api patterns and best practices for godot"
metadata:
  program: godot
  category: bridge
  title: Gdscript Api
  keywords: ["godot", "gdscript", "api", "editor", "interface", "plugin"]
  source: bridge-repo
  related-skills: ["scene-management", "scripting-patterns"]
---

# GDScript API Patterns

## Official Documentation
- Godot class reference: https://docs.godotengine.org/en/stable/classes/index.html
- EditorInterface API: https://docs.godotengine.org/en/stable/classes/class_editorinterface.html
- GDScript basics: https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_basics.html

## Entry Point
All bridge scripts must define:
```gdscript
func run(editor: EditorInterface) -> void:
    # Your code here
    pass
```

The `editor` parameter provides access to the full EditorInterface API.

## Common Patterns

### Accessing the Scene Tree
```gdscript
var edited_scene = editor.get_edited_scene_root()
var node = edited_scene.get_node("Path/To/Node")
```

### Creating Nodes
```gdscript
var sprite = Sprite2D.new()
sprite.name = "MySprite"
edited_scene.add_child(sprite)
sprite.owner = edited_scene  # Required for saving to .tscn
```

### Resource Loading
```gdscript
var texture = load("res://assets/texture.png")
var scene = load("res://scenes/my_scene.tscn")
var instance = scene.instantiate()
```

### File System Access
```gdscript
var fs = editor.get_resource_filesystem()
fs.scan()  # Refresh after adding files
```

### Saving Scenes
```gdscript
var packed = PackedScene.new()
packed.pack(edited_scene)
ResourceSaver.save(packed, "res://scenes/my_scene.tscn")
```

## Key Node Types
- `Node2D`, `Node3D` — base spatial nodes
- `CharacterBody2D/3D` — physics-based characters
- `RigidBody2D/3D` — physics simulation
- `Area2D/3D` — trigger zones
- `Camera2D/3D` — viewports
- `Control`, `Label`, `Button` — UI nodes
- `AnimationPlayer` — animation playback
- `TileMap` — 2D tile-based levels

## Signals
```gdscript
node.connect("signal_name", callable)
node.signal_name.emit()
```

## Scope Rules
- Keep changes request-scoped
- Avoid unrelated scene or gameplay rewrites
- Use provided attachment/context paths directly
