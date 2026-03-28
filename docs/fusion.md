# Fusion Bridge

| | |
|---|---|
| **Application** | Blackmagic Fusion / DaVinci Resolve (Fusion page) |
| **Language** | Python, Lua |
| **Install Type** | User-level |
| **Status** | Experimental |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Fusion bridge connects a running Blackmagic Fusion or DaVinci Resolve Fusion page to the Arkestrator server. It provides:

- **Context capture** -- pushes comp structure, active/selected tools, flow graph layout, and tool parameters every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs Python scripts via `execute_command(target="fusion", language="python", script="...")` or Lua scripts via `language="lua"`
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine without syncing
- **Menu integration** -- `.fu` script adds Arkestrator entries to the Fusion menus

Python scripts receive `fusion`/`fu` (application object), `comp` (current composition), and `tool` (active tool) as globals. Lua scripts run via `comp:Execute()`.

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Fusion bridge
4. Select your Fusion installation

### Manual Installation

Download the latest `arkestrator-bridge-fusion-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and extract to the Fusion Config directory:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%/Blackmagic Design/Fusion/Config` |
| macOS | `~/Library/Application Support/Blackmagic Design/Fusion/Config` |
| Linux | `~/.fusion/BlackmagicDesign/Fusion/Config` |

The bridge includes:
- `Arkestrator/` -- Python bridge package (ws_client, command_executor, context_provider, file_applier)
- `Arkestrator.fu` -- Fusion script for menu integration
- `Scripts/` -- Startup Lua loader
- `install.py` -- Helper script for automated installation

### DaVinci Resolve

The bridge also works with the Fusion page in DaVinci Resolve. Detection paths include Resolve-specific locations:

| Platform | Resolve Path |
|----------|-------------|
| Windows | `%APPDATA%/Blackmagic Design/DaVinci Resolve/Fusion/` |
| macOS | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/` |
| Linux | `~/.local/share/DaVinciResolve/Fusion/` |

## Skills

The Fusion bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Fusion:

- Python scripts have access to `fusion`/`fu`, `comp`, and `tool` globals
- Agents wrap batch operations in `comp.Lock()` / `comp.Unlock()` to avoid UI thrashing
- Tools are created with `comp.AddTool()`, connected via `SetInput()`, and inspected with `GetAttrs()`/`GetInputList()`
- Undoable edits use `comp.StartUndo("description")` / `comp.EndUndo(true)`
- Agents verify tool existence, connections, Loader/Saver paths, and render settings before reporting done
- Comp mutation must happen through bridge execution, not direct filesystem writes

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- Experimental status -- core functionality works but may have rough edges
- Works with both standalone Fusion and DaVinci Resolve's Fusion page
- The `.fu` script provides menu integration; the Lua startup loader initializes the bridge on Fusion launch
