# Nuke Bridge

| | |
|---|---|
| **Application** | Nuke 13+ |
| **Language** | Python, TCL |
| **Install Type** | User-level |
| **Status** | Experimental |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Nuke bridge is a Python package that connects a running Nuke session to the Arkestrator server. It provides:

- **Context capture** -- pushes node graph structure, selected nodes, knob values, format settings, and frame ranges every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs Python scripts with full `nuke` module access via `execute_command(target="nuke", language="python", script="...")`, or TCL via `language="tcl"`
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine without syncing
- **Context menu** -- right-click "Add to Arkestrator Context" integration
- **Thread safety** -- all commands are executed in the main thread via `nuke.executeInMainThread()`

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Nuke bridge
4. Select your Nuke installation

### Manual Installation

Download the latest `arkestrator-bridge-nuke-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and extract `arkestrator_bridge/` to your `.nuke` directory:

| Platform | Path |
|----------|------|
| Windows | `%USERPROFILE%/.nuke/arkestrator_bridge` |
| macOS | `~/.nuke/arkestrator_bridge` |
| Linux | `~/.nuke/arkestrator_bridge` |

Then add an import to your `init.py` or `menu.py`:

```python
import arkestrator_bridge
```

## Skills

The Nuke bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Compositing | Merge operations, keying, color correction, deep compositing |
| Python API | nuke module reference, node creation, knob manipulation |
| Node Patterns | Common node graph patterns, flow conventions, Gizmo/Group usage |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Nuke:

- Python scripts use the `nuke` module; TCL commands run via `nuke.tcl()`
- Node graph conventions: top-to-bottom flow, Reads at top, Writes at bottom, B input (left) for background, A input (right) for foreground
- Nodes are named descriptively: `{element}_{operation}` (e.g., `fg_grade`, `bg_despill`)
- Renders and DeepImage operations are treated as GPU-heavy -- agents avoid overlapping with other heavy tasks
- Agents verify node existence, connections, Write node paths, and frame ranges before reporting done
- No comp-wide restructuring for narrow requests

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- Experimental status -- core functionality works but may have rough edges
- User-level install means the bridge is available across all Nuke projects
- Uses `[value root.name]` for project-relative paths in Write nodes
