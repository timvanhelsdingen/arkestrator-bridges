# Unreal Engine Bridge

| | |
|---|---|
| **Application** | Unreal Engine 5 |
| **Language** | Python, UE Console commands |
| **Install Type** | Engine-level plugin |
| **Status** | Experimental |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Unreal bridge is a hybrid C++/Python engine plugin that connects the Unreal Editor to the Arkestrator server. It provides:

- **Context capture** -- pushes level actors, selected objects, asset browser state, and project structure every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs Python scripts via `execute_command(target="unreal", language="python", script="...")` or console commands via `language="ue_console"`
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine without syncing
- **Blueprint graph menu hooks** -- context menu integration for adding items to Arkestrator context

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Unreal bridge
4. Select your Unreal Engine version

### Manual Installation

Download the latest `arkestrator-bridge-unreal-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and copy `ArkestratorBridge/` into your UE5 engine plugins directory:

| Platform | Path |
|----------|------|
| Windows | `C:/Program Files/Epic Games/UE_<version>/Engine/Plugins/ArkestratorBridge` |
| macOS | `/Users/Shared/Epic Games/UE_<version>/Engine/Plugins/ArkestratorBridge` |
| Linux | `~/UnrealEngine/Engine/Plugins/ArkestratorBridge` |

Then enable the plugin in the Unreal Editor via **Edit > Plugins** (search for "Arkestrator").

## Skills

The Unreal bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Blueprint Patterns | Blueprint class patterns, event graphs, component wiring |
| C++ Gameplay Patterns | Actor lifecycle, UObject system, gameplay framework |
| Level Design | Actor placement, level streaming, landscape operations |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Unreal:

- Python scripts have full Unreal Python API access; console commands use `ue_console` language
- Agents use `/Game/...` paths consistently for content operations
- Standard Unreal naming prefixes are followed: `BP_`, `M_`, `MI_`, `T_`, `SM_`, `SK_`, `ABP_`, `WBP_`
- Agents verify actor/asset existence and properties before reporting done
- Assets and levels are saved after modifications

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- Experimental status -- core functionality works but may have rough edges
- Engine-level install means the plugin is available across all projects using that engine version
- The plugin includes both C++ and Python components; Python bridge code lives under `Content/Python/arkestrator_bridge/`
- Requires Unreal's Python plugin to be enabled
