# Houdini Bridge

| | |
|---|---|
| **Application** | Houdini 20+ |
| **Language** | Python (HOM), HScript |
| **Install Type** | User-level (Houdini package system) |
| **Status** | Stable |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Houdini bridge is a Python package that connects a running Houdini session to the Arkestrator server. It provides:

- **Context capture** -- pushes node networks, selected nodes, parameters, SOP geometry info, and scene hierarchy every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs Python/HOM scripts with full `hou` module access via `execute_command(target="houdini", language="python", script="...")`
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine (caches, renders, HIP files) without syncing
- **Context menu** -- right-click "Add to Arkestrator Context" integration

The bridge supports both live session execution and hython for offline analysis/validation.

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Houdini bridge
4. Select your Houdini version (auto-detected when possible)

### Manual Installation

Download the latest `arkestrator-bridge-houdini-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and extract the package to your Houdini packages directory:

| Platform | Path |
|----------|------|
| Windows | `%USERPROFILE%/Documents/houdini<version>/packages/` |
| macOS | `~/Library/Preferences/houdini/<version>/packages/` |
| Linux | `~/.houdini<version>/packages/` |

The bridge uses Houdini's package system. The extracted `arkestrator_bridge.json` package descriptor tells Houdini where to find the bridge code.

## Skills

The Houdini bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| SOP Networks | Surface operator patterns, geometry processing, VEX snippets |
| Procedural Modeling | Scatter, copy-to-points, L-systems, terrain generation |
| HOM Scripting | hou module reference, node creation, parameter manipulation |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Houdini:

- Scripts execute with full `hou` module access in the live session
- Agents prefer live bridge for active HIP work, hython for offline analysis
- Validation is mandatory: verify nodes, wiring, parameters, and output paths before reporting done
- Renders, sims, and cache operations are treated as GPU-heavy -- agents serialize them to avoid resource contention
- Default output paths use `$HIP`-relative locations, never absolute paths
- No scene-wide destructive edits for narrow requests

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- User-level install means the bridge is available across all Houdini projects for that version
- The bridge does not force pyro/Solaris workflows unless explicitly requested by the user
- When the live HIP resolves to a temp directory, agents re-anchor outputs to `projectRoot`
