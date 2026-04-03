# Module: Nuke Bridge (`nuke/arkestrator_bridge/`)

## Purpose
Nuke Python package that connects to the Arkestrator server via WebSocket. Thin execution endpoint: pushes editor context, applies file changes, executes Python/TCL commands, and supports cross-bridge communication. All prompt/submission UI lives in the Tauri client.

## Architecture (v1.0.0 -- Thin Bridge)
Same thin bridge pattern as the Blender/Houdini bridges. Bridges are execution endpoints only. They do NOT submit jobs or display job management UI. They provide:
- **Connection** to the server (auto-discover config, reconnect with exponential backoff)
- **Editor context** pushed to server on connect + periodically (every 3s if changed, hash-based dedup)
- **File application** from completed job results
- **Command execution** (Python + TCL + NK paste) from completed job results
- **Cross-bridge commands** (receive and execute commands from other bridges)
- **Public SDK API** (`get_bridge()`) for third-party plugins to submit jobs through the bridge
- **Context menu** integration via Nuke menu bar and node graph right-click

## Installation
Copy the `arkestrator_bridge` package to `~/.nuke/` or any directory on `NUKE_PATH`.

Then in `~/.nuke/menu.py`:
```python
import arkestrator_bridge
arkestrator_bridge.register()
```

## Files (5)
| File | Purpose |
|------|---------|
| `__init__.py` | Main module: WS dispatch, editor context, register/unregister, auto-connect, public API (`get_bridge()`, `_BridgeAPI`). Timer polling via Qt QTimer (10Hz) with thread fallback for render/terminal mode. Tracks active script path changes and pushes updated context. Menu setup for top-level Arkestrator menu and node graph right-click. Context capture for selected nodes, viewer input, and full script. |
| `ws_client.py` | WebSocket client using Python stdlib. Same as Blender/Houdini bridge but with `program=nuke`. `BRIDGE_VERSION = "1.0.0"`. Full reconnect path with shared-config credential refresh, remote relay fallback, and last-known-good key retry. |
| `command_executor.py` | `execute_commands()` - Python via `exec()` + TCL via `nuke.tcl()` + NK paste via `nuke.nodePaste()`. All Python commands are executed in main thread via `nuke.executeInMainThread()`. |
| `file_applier.py` | `apply_file_changes()` - create/modify/delete files on disk. Supports binary files via `binaryContent` base64 + `encoding` field. Path traversal protection via `os.path.realpath()`. |
| `menu.py` | Integrated into `__init__.py._setup_menus()` -- adds Arkestrator top-level menu and Node Graph right-click submenu. |

## Public API

### Module-level functions
| Function | Purpose |
|----------|---------|
| `register()` | Auto-connect if config exists, setup menus, start poll timer |
| `unregister()` | Disconnect and clean up |
| `connect(url, api_key)` | Manual connect (auto-discovers from `~/.arkestrator/config.json` if empty) |
| `disconnect()` | Graceful disconnect |
| `get_bridge()` | Returns `_BridgeAPI` instance if connected, `None` otherwise |

### `_BridgeAPI` (returned by `get_bridge()`)
| Method | Purpose |
|--------|---------|
| `submit_job(prompt, **kwargs)` | Submit a job via REST with auto-gathered Nuke editor context |
| `get_editor_context()` | Get current Nuke state as dict |
| `get_file_attachments()` | Get expression/script snippets from selected nodes |
| `add_context_item(item)` | Push a context item to the server's context bag |

### Context capture functions
| Function | Purpose |
|----------|---------|
| `add_selected_nodes_to_context()` | Add selected nodes with metadata to context |
| `add_viewer_context()` | Add active viewer input node to context |
| `add_script_to_context()` | Add the current .nk script as context |

## Editor Context
```json
{
  "projectRoot": "/path/to/nuke/project",
  "activeFile": "/path/to/script.nk",
  "metadata": {
    "bridge_type": "nuke",
    "script_path": "/path/to/script.nk",
    "format": "1920x1080",
    "frame_range": "1001-1100",
    "selected_nodes": [{"name": "Grade1", "type": "Grade", "path": "Grade1"}]
  }
}
```

File attachments: Python callback scripts, expression knobs, and BlinkScript kernels from selected nodes.

## Command Execution
- **Python**: `exec(compile(...))` with `nuke` in globals, wrapped in `nuke.executeInMainThread()`
- **TCL**: `nuke.tcl(script)` - returns result string
- **NK**: `nuke.nodePaste(script)` - pastes Nuke script snippet as nodes
- Unsupported languages are skipped with error message
- Returns `{"executed": int, "failed": int, "skipped": int, "errors": list[str], "stdout": str, "stderr": str}`
- `stdout` and `stderr` capture the respective output streams during command execution

## Menu Integration
- **Top-level menu**: `Nuke > Arkestrator` with Add Nodes/Viewer/Script to Context, Connect/Disconnect
- **Node Graph right-click**: `Arkestrator` submenu with Add Nodes and Viewer context actions

## Protocol Messages
Same protocol as other bridges -- see `bridges/blender/MODULE.md` for full reference. Notably, `bridge_command_result` messages include optional `stdout` and `stderr` fields when non-empty, and `send_bridge_command_result()` accepts optional `stdout` and `stderr` parameters.

## Differences from Other Bridges
| Aspect | Blender | Houdini | Nuke |
|--------|---------|---------|------|
| Registration | `bpy.utils.register_class()` | `register()` function | `register()` + `menu.py` |
| UI | N-Panel in 3D Viewport | No built-in panel | Top menu + Node Graph RMB |
| Timer | `bpy.app.timers.register()` | `hou.ui.addEventLoopCallback()` | Qt QTimer |
| Thread safety | bpy main thread | hou main thread | `nuke.executeInMainThread()` |
| Commands | Python only | Python + HScript | Python + TCL + NK paste |
| File attachments | All open text blocks | VEX/Python from nodes | Expressions/callbacks/kernels |
| Context menu | Runtime-discovered RMB menus | XML menu files + Qt hook | Nuke menu API |
