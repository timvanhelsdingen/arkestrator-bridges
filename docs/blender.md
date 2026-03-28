# Blender Bridge

| | |
|---|---|
| **Application** | Blender 4.2+ |
| **Language** | Python (bpy) |
| **Install Type** | User-level addon |
| **Status** | Stable |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Blender bridge is a Python addon that connects a running Blender instance to the Arkestrator server. It provides:

- **Context capture** -- pushes active scene, selected objects, collections, modifiers, materials, and outliner state every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs Python scripts with full `bpy` access in Blender's main thread via `execute_command(target="blender", language="python", script="...")`
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine (renders, textures, project files) without syncing
- **Context menu** -- right-click "Add to Arkestrator Context" integration
- **Preferences panel** -- connection status and settings in Edit > Preferences > Add-ons

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Blender bridge
4. Select your Blender version (auto-detected when possible)

### Manual Installation

Download the latest `arkestrator-bridge-blender-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and extract `arkestrator_bridge/` to your Blender addons directory:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%/Blender Foundation/Blender/<version>/scripts/addons/arkestrator_bridge` |
| macOS | `~/Library/Application Support/Blender/<version>/scripts/addons/arkestrator_bridge` |
| Linux | `~/.config/blender/<version>/scripts/addons/arkestrator_bridge` |

Then enable the addon in **Edit > Preferences > Add-ons** (search for "Arkestrator").

## Skills

The Blender bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Materials & Shading | Shader node patterns, material setup, texture workflows |
| Rendering | Cycles/EEVEE settings, output configuration, render optimization |
| Modeling | Mesh operations, modifiers, geometry workflows |
| Python API | bpy module reference, operator patterns, data access |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Blender:

- Scripts execute in Blender's main thread with full `bpy` access
- Agents must run deterministic validation scripts after each edit (object existence, transforms, materials, exports)
- Renders and bake jobs are treated as GPU-heavy -- agents will not overlap them with other heavy GPU tasks
- Changes are scoped to the request -- no broad scene rebuilds
- Scene mutation must happen through bridge execution, not direct filesystem writes

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- User-level install means the addon is available across all Blender projects for that version
- Includes `blender_manifest.toml` for Blender's extension system
