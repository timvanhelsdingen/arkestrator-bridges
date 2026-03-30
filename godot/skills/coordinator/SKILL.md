---
name: godot-coordinator
description: "Coordinator script for godot — manages live session execution, transport, and best practices"
metadata:
  program: godot
  category: coordinator
  title: Godot Coordinator
  keywords: ["godot", "coordinator", "bridge"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# Godot Coordinator

You are connected to a live Godot editor through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="godot", language="gdscript", script="...")` to run GDScript in the live editor.
Every script must define: `func run(editor: EditorInterface) -> void:`. Do not mutate project files via Bash/Write/Edit.

## Skills
Detailed operational knowledge for Godot is provided via skills.
Use `am skills search <query>` or `am skills list --program godot` to discover available patterns, techniques, and best practices.

## Execution
1. Write focused GDScript with `func run(editor: EditorInterface) -> void:`.
2. Execute via `execute_command`.
3. Fix errors immediately (max 3 fix loops).
4. Verify syntax and runtime.

## Best Practices — Project Organization
- Follow the Godot project structure:
  - Scenes in `scenes/` or organized by feature (`scenes/levels/`, `scenes/ui/`, `scenes/characters/`)
  - Scripts in `scripts/` mirroring the scene structure, or alongside their scene files
  - Assets (textures, models, audio) in `assets/` with subfolders by type (`assets/textures/`, `assets/models/`, `assets/audio/`)
  - Shaders in `shaders/`
  - Imported resources in `imports/` if using external tools
- Use `res://` paths everywhere — never hardcode absolute filesystem paths
- Name scenes and scripts with PascalCase matching the root node (e.g. `Player.tscn`, `Player.gd`)
- Name resources and assets with snake_case (e.g. `grass_texture.png`, `footstep_01.wav`)
- Keep one script per node; attach scripts to the node they control
- Use Godot's resource system (`.tres`) for data that should be shared or tweaked in the inspector
- Create directories with `DirAccess.make_dir_recursive_absolute()` before writing files

## Quality Requirements
- Verify operations succeed (check node existence, properties, scene state)
- Run syntax check: `run_headless_check(program="godot", args=["--headless", "--check-only", "--path", "<projectRoot>"], timeout=15000)`
- Run runtime check: `run_headless_check(program="godot", args=["--headless", "--quit-after", "5", "--path", "<projectRoot>"], timeout=25000)`
- Both checks must pass before reporting done
- Report explicit PASS evidence, not assumptions
