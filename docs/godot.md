# Godot Bridge

| | |
|---|---|
| **Application** | Godot 4.x |
| **Language** | GDScript |
| **Install Type** | Per-project (copied into each project) |
| **Status** | Stable |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Godot bridge is an editor plugin that connects a running Godot editor to the Arkestrator server. It provides:

- **Context capture** -- pushes scene hierarchy, open scripts, selected nodes, and project structure to the server every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs GDScript in the live editor via `execute_command(target="godot", language="gdscript", script="...")`
- **File operations** -- creates, modifies, and deletes project files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine (images, renders, project files) without syncing
- **Context menu** -- right-click "Add to Arkestrator Context" integration in the editor

Every GDScript command must define `func run(editor: EditorInterface) -> void:` as the entry point.

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Godot bridge
4. Select your Godot project directory

### Manual Installation

Download the latest `arkestrator-bridge-godot-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and copy the `addons/arkestrator_bridge/` folder into your Godot project's `addons/` directory.

```
your-project/
  addons/
    arkestrator_bridge/    <-- extract here
      plugin.gd
      plugin.cfg
      ws_client.gd
      command_executor.gd
      file_applier.gd
      context_menu.gd
```

Then enable the plugin in **Project > Project Settings > Plugins**.

This is a per-project install -- repeat for each Godot project you want to connect.

## Skills

The Godot bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Scene Management | Scene hierarchy, node creation, instancing, scene switching |
| GDScript Patterns | Scripting conventions, signal patterns, resource handling |
| GDScript API | Core GDScript and editor API reference |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with the Godot editor:

- All scripts must define `func run(editor: EditorInterface) -> void:`
- Agents must run headless syntax checks (`--check-only`) and runtime checks (`--quit-after 5`) after writing or editing scripts
- Changes are scoped to the request -- no unrelated scene or gameplay rewrites
- Agents use `res://` paths and follow Godot project conventions (PascalCase scenes/scripts, snake_case assets)
- Scene and script files should never be mutated via direct filesystem writes -- always use bridge execution

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json` (written by the desktop client)
- Because this is a per-project plugin, it must be installed separately in each Godot project
- The plugin runs inside the editor process and has full `EditorInterface` access
