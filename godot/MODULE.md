# Module: Godot Bridge (`bridges/godot/addons/arkestrator_bridge/`)

**SOURCE OF TRUTH**: `bridges/godot/addons/arkestrator_bridge/` - the demo at `bridges/godot/demo/addons/` is just a copy.

## Purpose
Godot 4.6 EditorPlugin that connects to the Arkestrator server via WebSocket. Acts as a thin execution endpoint: pushes editor context and context items to the server, applies file changes, and executes GDScript commands. All prompt/submission UI and job management lives in the Tauri client - the bridge has no Task tab, no job submission, no agent config selector, no log viewer, no cancel button, and no dashboard button.

## Connection & Auth Behavior
- **Connect timeout**: `ws_client.gd` uses a 15s connect timeout (`CONNECT_TIMEOUT_S`) that triggers a retry when the WS handshake takes too long. Logs close code and close reason on disconnect for diagnostics.
- **Auth fallback**: `plugin.gd` ignores malformed shared `apiKey` rewrites, `ws_client.gd` keeps a last known-good key for reconnect attempts, and tolerates bad `~/.arkestrator/config.json` writes without dying permanently.
- **Remote-relay fallback**: `ws_client.gd` tries shared `remoteWsUrl` when reconnecting through a dead desktop-owned localhost relay, keeping remote-server sessions alive.
- **Shared identity**: Follows the client-owned `workerName` and `machineId` from `~/.arkestrator/config.json`, includes `machineId` on the WebSocket query string, and hot-reconnects when shared identity changes so the bridge collapses onto the same worker row as the desktop client.
- **Command-mode autosave**: `_on_job_complete` only auto-saves scenes for file-apply flows (`repo`/`sync`), not command-mode completions, to avoid save-trigger instability after live command execution.
- **Shared-credential hot-reload**: Monitors `~/.arkestrator/config.json` while connected/reconnecting and auto-reconnects when shared `apiKey` or `wsUrl` changes, so local/remote server switches work without manual plugin reset.

## Files (5 + config)
| File | Purpose |
|------|---------|
| `plugin.gd` | Main EditorPlugin - single-panel dock UI (no TabContainer), settings, WS callbacks, editor context gathering + periodic push, context item forwarding, scene operations, file application, command execution. Shared-config refresh now ignores malformed `apiKey` rewrites instead of forcing a bad reconnect. |
| `ws_client.gd` | WebSocket client with connect/disconnect/reconnect/poll, message serialization, signal-based dispatch. When using a desktop-owned localhost relay URL, reconnect now also tries shared `remoteWsUrl` as a direct fallback and retries with the last known-good API key before giving up. |
| `context_menu.gd` | EditorContextMenuPlugin - "Add to Arkestrator Context" right-click option for Scene Tree, FileSystem dock, Script Editor, Script Code Editor. Emits `item_added` signal with serialized item data |
| `file_applier.gd` | Static `apply_file_changes()` - writes/deletes files from FileChange arrays, triggers filesystem scan |
| `command_executor.gd` | Static `execute_commands()` - compiles+runs GDScript snippets in editor. Wraps bare code in `run(editor)` function |
| `plugin.cfg` | Godot plugin manifest (name: "Godot Arkestrator Bridge", version: 0.2.0) |

## Plugin Lifecycle
1. `_enter_tree()`: ensure settings -> load file_applier/command_executor/context_menu scripts -> create WS client node -> build dock UI -> register context menus (4 slots) -> add tool menu item ("Arkestrator Bridge: Focus Dock") -> auto-connect if enabled
2. `_process()`: poll WS client + reconnect tick (every frame) + shared-config credential refresh check (every 3 seconds) + periodic editor context push (2-second interval, only if context hash changed)
3. `_exit_tree()`: remove tool menu item -> unregister context menus -> disconnect WS -> remove dock -> cleanup

## Settings (Editor Settings, not project settings)
All settings are prefixed with `arkestrator_bridge/` in the Godot editor settings.

| Setting | Key | Default | Purpose |
|---------|-----|---------|---------|
| Server URL | `server_url` | `ws://localhost:7800/ws` | Server WebSocket endpoint |
| Auto-connect | `auto_connect` | `true` | Connect on plugin load |
| Auto-save scene | `auto_save_scene` | `true` | Save scene before applying file changes (`repo`/`sync`) |
| Auto-reload scene | `auto_reload_scene` | `true` | Reload scene after completion |
| Auto-apply files | `auto_apply_files` | `true` | Apply file changes automatically |
| Auto-execute commands | `auto_execute_commands` | `true` | Execute GDScript commands automatically |

### Removed Settings (moved to Tauri client)
- `api_key` - auto-discovered from `~/.arkestrator/config.json` (written by Tauri client on login)
- `worker_name` - sourced from client-written shared config `workerName` when available, with hostname fallback only for manual/no-config bridge use
- `machine_id` - sourced from client-written shared config `machineId`
- `dashboard_url`, `dashboard_path`, `default_project`

## Dock UI (programmatic, no .tscn)
Single panel (PanelContainer, no TabContainer) docked at `DOCK_SLOT_RIGHT_UL`:
- **Title**: "Arkestrator Bridge" (Label, font_size 16)
- **HSeparator**
- **Server URL**: Label + LineEdit (placeholder: default URL)
- **HSeparator**
- **Checkboxes**: Auto-connect on plugin load, Auto-reload scene on completion, Auto-apply file changes, Auto-execute commands
- **HSeparator**
- **Connect/Disconnect** button (toggles text based on connection state)
- **Status** label (shows "Status: {text}")

### Removed UI (moved to Tauri client)
- Task tab with TabContainer (agent config selector, project selector, priority spinner, prompt TextEdit, "Add to Queue"/"Queue and Start" buttons, dependency picker, log viewer, cancel button, dashboard button)
- Context bag ItemList with @N references (items now push to server immediately instead of being stored locally)

## WebSocket Client (`ws_client.gd`)

### Signals
| Signal | Parameters | When Emitted |
|--------|------------|-------------|
| `connected` | (none) | WS connection established |
| `disconnected` | (none) | WS connection lost |
| `reconnecting` | `seconds_remaining: float` | Emitted each frame during reconnect wait with countdown |
| `job_complete` | `job_id, success, files, commands, workspace_mode, error_text` | Server sends job results |
| `error_received` | `code, message` | Server sends error |
| `bridge_command_received` | `sender_id, commands, correlation_id` | Cross-bridge command arrives |
| `bridge_command_result_received` | `bridge_id, program, correlation_id, success, executed, failed_count, skipped, errors` | Cross-bridge command result arrives |

### Removed Signals (submission moved to Tauri client)
- `job_accepted`, `job_started`, `job_log`, `job_dependency_blocked`, `agent_configs_received`, `job_list_received`, `project_list_received`

### Send Methods
| Method | Message Type | Purpose |
|--------|-------------|---------|
| `send_context_item(item)` | `bridge_context_item_add` | Push a context item to the server |
| `send_context_clear()` | `bridge_context_clear` | Clear the context bag on the server |
| `send_editor_context(editor_context, files)` | `bridge_editor_context` | Push current editor context snapshot |
| `send_bridge_command(target, commands, target_type, correlation_id)` | `bridge_command_send` | Send cross-bridge command |
| `send_bridge_command_result(sender_id, correlation_id, success, executed, failed_count, skipped, errors)` | `bridge_command_result` | Reply to cross-bridge command |
| `send_message(msg)` | (any) | Low-level: send raw dictionary as JSON |

### Removed Send Methods (submission moved to Tauri client)
- `submit_job()`, `cancel_job()`, `request_agent_configs()`, `request_job_list()`, `request_project_list()`

### Connection Details
- Connect URL includes query params: `type=bridge`, `key`, `name` (project name), `program=godot`, `programVersion` (e.g. "4.6.0.stable"), `bridgeVersion=1.0.0`, `projectPath`, `workerName`, `machineId`
- Connect timeout: 15s (`CONNECT_TIMEOUT_S`) - retries if WS handshake takes too long
- Disconnect logging: close code and close reason printed on every disconnect for diagnostics
- Reconnect: exponential backoff 3s base -> 30s max, automatic on disconnect
- Reconnect auth fallback: repeated reconnect attempts keep the last known-good `apiKey` in reserve, so a bad shared-config rewrite does not permanently break the bridge once it is already online.
- If the followed `wsUrl` is a loopback relay, reconnect now also tries shared `remoteWsUrl` before giving up, so a dead local relay does not strand the bridge offline.
- Added `is_reconnect_pending()` on `ws_client.gd` so plugin-level shared-config refresh can update credentials during active reconnect waits.
- UUID generation: manual v4 from `randi() % 256` random bytes

### Message Handling (`_handle_message`)
Dispatches incoming messages by type:
- `job_complete` -> emits `job_complete` signal
- `error` -> emits `error_received` signal
- `bridge_command` -> emits `bridge_command_received` signal
- `bridge_command_result` -> emits `bridge_command_result_received` signal
- All other types silently ignored

## Bridge-to-Server Messages
| Message Type | When Sent | Payload |
|-------------|-----------|---------|
| `bridge_context_item_add` | User right-clicks "Add to Arkestrator Context" | `{ item: { index, type, name, path, content, metadata } }` |
| `bridge_context_clear` | On WS connect (clears stale context) | `{}` |
| `bridge_editor_context` | On connect + every 2s if changed | `{ editorContext, files }` |
| `bridge_command_send` | Cross-bridge command dispatch | `{ target, targetType, commands, correlationId? }` |
| `bridge_command_result` | Reply to received bridge command | `{ senderId, correlationId, success, executed, failed, skipped, errors }` |

## Editor Context Gathering (`plugin.gd:_build_editor_context()`)
```
{
  projectRoot: globalized "res://",
  activeFile: scene_file_path,
  metadata: {
    active_scene: scene_file_path,
    selected_nodes: [{ name, type, path }],
    selected_scripts: [script_resource_paths]
  }
}
```
Also gathers file attachments via `_gather_file_attachments()`: reads content of all selected/open scripts and returns `[{ path, content }]`.

### Periodic Context Push
- 2-second timer (`CONTEXT_PUSH_INTERVAL`) in `_process()` calls `_push_editor_context_if_changed()`
- Hash is computed from: active scene path, selected node names/types/paths, selected script paths
- On change, pushes `bridge_editor_context` message to server
- Also pushes immediately on WS connect (via `_on_ws_connected`)

### On WS Connect
1. Reset context bag index counter to 1
2. Send `bridge_context_clear` to server (clears any stale context)
3. Push current editor context immediately

## Context Item Flow
1. User right-clicks in Scene Tree / FileSystem / Script Editor / Script Code Editor
2. `context_menu.gd` emits `item_added` signal with item data (type, name, path, content, metadata)
3. `plugin.gd:_on_context_item_added()` assigns an `@N` index (incrementing counter) and sends `bridge_context_item_add` to server immediately
4. Server stores item in bridge's context bag
5. On reconnect, `bridge_context_clear` resets the server-side bag and the local index counter
6. Multi-selection (`Scene Tree`, `FileSystem`, `Script Editor`) is grouped into one selection context item so users get one `@N` reference for the selected set.

### Context Menu Item Types
- **Node selection** (Scene Tree): type=`node`, includes class name, script path, exported properties
- **Filesystem selection**: type varies (`script`/`scene`/`resource`/`asset`), includes file content for text files, file size for binary files
- **Script Editor**: type=`script`, includes source_code
- **Script Code Editor**: type=`script`, includes selected text (with line range metadata) or full file content if no selection

## File Application (`file_applier.gd`)
- `apply_file_changes(files, project_root)` -- iterates FileChange array
  - `create`/`modify`: mkdir recursive + write file. **Binary file support**: checks `encoding` field - if `"base64"` and `binaryContent` present, writes binary via `Marshalls.base64_to_raw()`. Otherwise writes text content as UTF-8.
  - `delete`: remove file
- `trigger_filesystem_scan(editor_interface)`: deferred scan via EditorInterface.get_resource_filesystem()
- Path resolution (`_resolve_path`): handles `res://` paths, absolute paths, relative paths (resolved against project root)
- **Path traversal protection**: `_resolve_path()` uses `simplify_path()` to normalize `..` components, then verifies the result stays within the project root. Returns empty string and logs `push_warning()` if a path escapes the root; caller skips the file and records the error.
- Returns `{ applied, failed, errors }`

## Command Execution (`command_executor.gd`)
- `execute_commands(commands, editor_interface)` -- iterates CommandResult array
- Only supports `gdscript`/`gd` language (skips others with error message)
- Wraps bare code (no `func run(`) in `extends RefCounted\nfunc run(editor: EditorInterface) -> void:\n\t...`
- Ensures script has `extends` declaration
- Compiles via `GDScript.new()` + `reload()`, instantiates, calls `run(editor_interface)`
- Returns `{ executed, failed, skipped, errors }`

## Job Completion Handling (`_on_job_complete`)
On `job_complete` signal:
1. Update status label (failed or completed)
2. If success:
   a. If **command mode** + has commands + `auto_execute_commands` enabled -> execute GDScript commands via command_executor
   b. If **repo/sync mode** + has files:
      - Optional **auto-save scene** first (if `auto_save_scene` enabled)
      - Apply file changes via file_applier when `auto_apply_files` is enabled + trigger filesystem scan
   c. If `auto_reload_scene` enabled -> reload active scene (waits for filesystem scan to complete first)

## Cross-Bridge Command Handling
- `_on_bridge_command_received()`: executes commands from other bridges (e.g. Blender sending GDScript to Godot)
  - Checks auto-execute setting, reports back via `send_bridge_command_result()`
  - Skips with result if auto-execute disabled or command_executor not loaded
- `_on_bridge_command_result_received()`: logs results of commands sent to other bridges

## API Key Auto-Discovery
On auto-connect or manual connect, the plugin always reads `~/.arkestrator/config.json` (via `_read_shared_config()`) for the API key. Also picks up `wsUrl` from the config if the user hasn't customized the server URL (still using default). This file is written by the Tauri client on every successful login. There is no manual API key entry - it is fully automatic.

## Context Menu Slots
4 `EditorContextMenuPlugin` instances registered via `add_context_menu_plugin()`:
- `CONTEXT_SLOT_SCENE_TREE` -- callback receives `Array[Node]`
- `CONTEXT_SLOT_FILESYSTEM` -- callback receives `PackedStringArray` of file paths
- `CONTEXT_SLOT_SCRIPT_EDITOR` -- callback receives `Array[Script]`
- `CONTEXT_SLOT_SCRIPT_EDITOR_CODE` -- callback receives `Array` with CodeEdit; uses `_last_paths` from `_popup_menu()` for script path resolution

## Known Gaps / TODOs
- UUID uses `randi() % 256` not `Crypto.generate_random_bytes()` (sufficient for message IDs)
