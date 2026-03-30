---
name: scene-management
description: "Scene Management patterns and best practices for godot"
metadata:
  program: godot
  category: bridge
  title: Scene Management
  keywords: ["godot", "scene-management"]
  source: bridge-repo
---

# Godot Scene Management

## Creating Scenes via EditorInterface
- Get editor: `var ei = EditorInterface`
- Get edited scene root: `ei.get_edited_scene_root()`
- Open scene: `ei.open_scene_from_path("res://path/to/scene.tscn")`
- Save scene: `ei.save_scene()`

## Creating Nodes
- `var node = Node3D.new()` / `MeshInstance3D.new()` / `CharacterBody3D.new()`
- Set name: `node.name = "MyNode"`
- Add to tree: `parent.add_child(node)` then `node.owner = scene_root`
- Setting owner is CRITICAL for saving — without it, node won't persist

## Resources
- Create mesh: `var mesh = BoxMesh.new()` / `SphereMesh.new()` / `CapsuleMesh.new()`
- Assign: `mesh_instance.mesh = mesh`
- Materials: `var mat = StandardMaterial3D.new()`, set `albedo_color`, assign to mesh

## Project Settings
- `ProjectSettings.set_setting("application/run/main_scene", "res://main.tscn")`
- Must call `ProjectSettings.save()` after changes
