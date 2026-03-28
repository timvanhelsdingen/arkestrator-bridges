---
title: Scene Hierarchy
category: bridge
---
# Unity Scene Hierarchy

## Working with GameObjects via unity_json

The Unity bridge uses structured JSON actions, not raw C#. All scene manipulation goes through `unity_json` commands.

### Creating GameObjects
```json
{"action": "create_game_object", "name": "Player", "position": [0, 1, 0]}
```
- Optionally set `parentPath` to nest under an existing object: `"parentPath": "Environment/Props"`
- Created objects are automatically registered with Undo
- The new object becomes the active selection

### Deleting GameObjects
```json
{"action": "delete_game_object", "path": "Environment/Props/OldCrate"}
```
- Use `path` (hierarchy path with `/` separators) or `name` (finds first match via `GameObject.Find`)
- Path-based lookup is preferred — it's unambiguous for nested hierarchies

### Setting Position
```json
{"action": "set_position", "path": "Player", "position": [5, 0, -3]}
```
- Position is world-space `[x, y, z]`
- Supports both `path` and `name` for target lookup

## Scene Operations

### Opening a Scene
```json
{"action": "open_scene", "path": "Assets/Scenes/MainMenu.unity"}
```
- Path must be a project-relative asset path (starts with `Assets/`)
- Opens in Single mode — replaces the current scene

### Saving Scenes
```json
{"action": "save_scenes"}
```
- Saves all currently open scenes
- Always call after making scene changes that should persist

### Refreshing Assets
```json
{"action": "refresh_assets"}
```
- Triggers `AssetDatabase.Refresh()` — required after creating or moving files on disk

## Hierarchy Path Conventions
- Paths use `/` as separator: `Canvas/Panel/Button`
- Root objects have no prefix: `"Player"`, `"Main Camera"`
- The bridge resolves paths by walking `Transform.Find` from root
- Use empty GameObjects as organizational folders: `"--- Environment ---"`, `"--- UI ---"`

## Batching Operations
Send an array of actions to execute multiple operations atomically:
```json
[
  {"action": "create_game_object", "name": "SpawnPoint_A", "position": [10, 0, 0]},
  {"action": "create_game_object", "name": "SpawnPoint_B", "position": [-10, 0, 0]},
  {"action": "save_scenes"}
]
```

## Common Pitfalls
- Always save scenes after modifications — unsaved changes are lost on play mode or domain reload
- `GameObject.Find` only finds active objects — inactive objects must be located by hierarchy path
- Creating objects without specifying a parent places them at the scene root
- Position values are world-space; for local-space positioning, set parent first then position
