# Unreal Engine 5 Bridge - Module Documentation

## Overview
Python-based UE5 editor plugin that connects to the Arkestrator server via WebSocket. Uses UE5's built-in PythonScriptPlugin for auto-startup and command execution. **No C++ compilation required** - works on Blueprint-only projects.

Adds "Ark +Context" toolbar buttons in Blueprint, Material, Animation, Niagara, and other asset editors, plus right-click context menus across Level Editor surfaces.

## Directory Structure
```
bridges/unreal/
├── MODULE.md
└── ArkestratorBridge/
    ├── ArkestratorBridge.uplugin              # Content-only plugin (no C++ modules)
    ├── Resources/
    │   └── arkestrator_icon_32.png            # Toolbar icon (not yet used — UE Slate limitation)
    └── Content/Python/
        ├── init_unreal.py                      # Auto-startup script (PythonScriptPlugin)
        └── arkestrator_bridge/
            ├── __init__.py                     # Core: register, WS dispatch, context push, public API
            ├── ws_client.py                    # Pure-stdlib WebSocket client (threaded I/O)
            ├── file_applier.py                 # File change application with path traversal protection
            ├── command_executor.py             # Python exec + UE console command execution
            ├── context_menu.py                 # ToolMenus context menus + toolbar buttons + BP graph node capture
            └── blueprint_utils.py              # Blueprint introspection (parent class, components, variables, functions, interfaces)
```

## Key Components

### init_unreal.py (Auto-Startup)
- PythonScriptPlugin auto-executes from `Content/Python/`
- Defers registration ~1 second (60 Slate ticks) to let editor finish loading
- Calls `arkestrator_bridge.register()`

### __init__.py (Core Module)
- **Tick callback**: `unreal.register_slate_post_tick_callback()` (~60Hz)
  - WS poll throttled to ~100ms
  - Context push throttled to ~3s
- **Message dispatch**: `job_complete`, `bridge_command`, `bridge_command_result`, `error`
- **Editor context**: project root, active level, selected actors/assets/folders/material nodes, engine version, actor count, Blueprint introspection (parent class, components, variables, functions, interfaces) for selected Blueprint assets
- **Config**: reads `~/.arkestrator/config.json` for apiKey and wsUrl
- **Public API**: `register()`, `unregister()`, `connect()`, `disconnect()`, `get_bridge()`

### ws_client.py (WebSocket Client)
- Pure Python stdlib (socket, struct, hashlib, threading, queue)
- RFC 6455 WebSocket frames, client-side only
- Threaded I/O: daemon thread for socket, main thread drains queue via `poll()`
- Connects with: `type=bridge`, `program=unreal`, `bridgeVersion`, `protocolVersion`, `key`, `name`, `programVersion`, `projectPath`, `workerName`, `machineId`, `osUser`
- Auto-reconnect: exponential backoff 3s → 30s, 10s stability check
- Shared-config auth/identity hot-reload: while reconnecting (and during read-loop timeout polls), client reloads `~/.arkestrator/config.json`; changed shared `apiKey`, followed `wsUrl`, `workerName`, or `machineId` triggers automatic reconnect using the updated credentials and canonical machine identity.
- Remote-relay reconnect hardening: if the followed `wsUrl` is a desktop-owned loopback relay and that relay is unavailable during reconnect, the client now tries shared `remoteWsUrl` directly before giving up.
- Close code 4001 handling (replaced connection, no reconnect)
- Stale detection: 180s without frames triggers reconnect (`STALE_TIMEOUT_S`=180.0)
- Handshake retry: up to 2 attempts (`HANDSHAKE_RETRY_ATTEMPTS`=2) with 0.5s delay

### file_applier.py
- `apply_file_changes(changes, project_root)` - create/modify/delete
- Path traversal protection via `os.path.realpath()` bounds check
- Binary support: base64-encoded `binaryContent` field
- Fallback project root: `unreal.Paths.project_dir()`

### command_executor.py
- `execute_commands(commands)` - returns `{executed, failed, skipped, errors}`
- **Python** (`python`/`py`): `exec(compile(script))` with `unreal` in globals
- **UE Console** (`ue_console`/`console`): `unreal.SystemLibrary.execute_console_command()`

### context_menu.py
- **Right-click context menus** via `unreal.ToolMenus`:
  - `LevelEditor.ActorContextMenu`
  - `LevelEditor.LevelViewportContextMenu`
  - `ContentBrowser.AssetContextMenu`
  - `ContentBrowser.FolderContextMenu`
  - `LevelEditor.MainMenu.Tools`
  - `GraphEditor.GraphContextMenu`
  - `GraphEditor.GraphNodeContextMenu`
- **Toolbar buttons** ("Ark +Context") registered on:
  - `LevelEditor.LevelEditorToolBar.User`
  - `AssetEditor.BlueprintEditor.ToolBar`
  - `AssetEditor.MaterialEditor.ToolBar`
  - `AssetEditor.NiagaraScriptToolkit.ToolBar` / `AssetEditor.NiagaraSystemToolkit.ToolBar`
  - `AssetEditor.AnimationEditor.ToolBar` / `AssetEditor.SkeletonEditor.ToolBar` / `AssetEditor.AnimationBlueprintEditor.ToolBar`
  - `AssetEditor.ControlRigEditor.ToolBar`
  - `AssetEditor.BehaviorTreeEditor.ToolBar`
  - `AssetEditor.MetasoundEditor.ToolBar`
- "Add to Arkestrator Context" captures actors, assets, folders, material nodes, Blueprint assets, and Blueprint graph nodes as `bridge_context_item_add`
- Module-level `_next_context_index` counter, resets on reconnect
- Idempotent registration

### blueprint_utils.py (Blueprint Introspection)
- `is_blueprint(asset)` - safe `isinstance` check against `unreal.Blueprint`
- `get_blueprint_info(asset)` - returns dict with parent class, components, variables, functions, interfaces
- Components via `simple_construction_script.get_all_nodes()` (works since UE4)
- Variables via generated class CDO property diff against parent class
- Functions via `function_graphs` attribute or CDO callable diff
- Interfaces via `implemented_interfaces()` or `generated_class().get_interfaces()`
- All API calls independently try/excepted; lists capped (50/50/50/20) with `truncated` flag

## Protocol Messages

### Sent
- `bridge_editor_context` - editor context + files (on connect + every 3s)
- `bridge_context_clear` - clear stale context on connect
- `bridge_context_item_add` - right-click "Add to Context" or toolbar button
- `bridge_command_send` - cross-bridge commands
- `bridge_command_result` - command execution results

### Handled
- `job_complete` - apply files or execute commands
- `bridge_command` - execute commands from another bridge
- `bridge_command_result` - log results
- `error` - server error notifications

## Editor Context Structure
```json
{
  "projectRoot": "/path/to/project/",
  "activeFile": "MapName",
  "metadata": {
    "bridge_type": "unreal",
    "project_name": "MyProject",
    "engine_version": "5.6.0-0+++UE5+Release-5.6",
    "active_level": "MapName",
    "selected_actors": [
      {"name": "Cube", "class": "StaticMeshActor", "path": "/Game/Maps/...", "location": "(0.0, 0.0, 100.0)"}
    ],
    "selected_assets": [
      {
        "name": "BP_Door", "class": "Blueprint", "path": "/Game/Blueprints/BP_Door.BP_Door",
        "blueprint": {
          "parent_class": "Actor",
          "parent_class_path": "/Script/Engine.Actor",
          "components": [
            {"name": "DefaultSceneRoot", "class": "SceneComponent", "is_root": true},
            {"name": "DoorMesh", "class": "StaticMeshComponent", "is_root": false}
          ],
          "variables": [
            {"name": "bIsOpen", "type": "bool"},
            {"name": "OpenSpeed", "type": "float"}
          ],
          "functions": ["ToggleDoor", "OnInteract"],
          "interfaces": ["BPI_Interactable"]
        }
      }
    ],
    "selected_folders": [
      {"name": "Blueprints", "path": "/Game/Blueprints"}
    ],
    "selected_material_nodes": [
      {"name": "Multiply_1", "class": "MaterialExpressionMultiply", "path": "/Engine/Transient...", "material": "M_Door"}
    ],
    "total_actors": 42
  }
}
```

## Public Python API
```python
import arkestrator_bridge

# Manual connect (auto-connect happens on startup if config exists)
arkestrator_bridge.connect(url="ws://localhost:7800/ws", api_key="am_...")

# SDK API for third-party scripts
bridge = arkestrator_bridge.get_bridge()
if bridge:
    job = bridge.submit_job("Create a blue cube at origin")
    ctx = bridge.get_editor_context()
    bridge.add_context_item({"type": "node", "name": "MyActor", ...})
```

## Installation (Engine-Level)
1. Copy `ArkestratorBridge/` folder to your UE5 engine's Plugins directory:
   - **Windows:** `C:\Program Files\Epic Games\UE_5.x\Engine\Plugins\ArkestratorBridge\`
   - **macOS:** `/Users/Shared/Epic Games/UE_5.x/Engine/Plugins/ArkestratorBridge/`
   - **Linux:** `~/UnrealEngine/Engine/Plugins/ArkestratorBridge/`
2. Enable **PythonScriptPlugin** in Edit > Plugins > Scripting (if not already enabled)
3. Enable **Arkestrator Bridge** in Edit > Plugins > Editor
4. Restart the editor
5. Ensure `~/.arkestrator/config.json` exists (created by Tauri client on login)
6. Bridge auto-connects on startup - check Output Log for `[ArkestratorBridge] Bridge registered successfully`

Once installed at the engine level, the plugin is available to **all** projects using that engine version - no per-project setup needed.

## Dependencies
- **Required:** PythonScriptPlugin (built into UE5 since 4.24)
- **No C++ compilation** - content-only plugin with empty `Modules` array
- **No external Python packages** - uses only Python stdlib
