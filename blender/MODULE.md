# Module: Blender Bridge (`bridges/blender/arkestrator_bridge/`)

## Purpose
Blender addon that connects to the Arkestrator server via WebSocket. Thin execution endpoint: pushes editor context, applies file changes, executes Python commands, and supports cross-bridge communication. All prompt/submission UI lives in the Tauri client -- the bridge has no job creation UI.

## Connection & Auth Behavior
- **Stale timeout**: `ws_client.py` uses a 180s stale timeout for tolerance of idle connections.
- **Handshake retry**: 2 attempts with 0.5s delay so transient handshake failures (relay hiccups, DNS blips) do not immediately fail the connection.
- **Auth fallback**: `ws_client.py` ignores malformed shared `apiKey` rewrites and retries reconnect with the last known-good key before giving up. Tolerates bad `~/.arkestrator/config.json` writes without going offline permanently.
- **Remote-relay fallback**: When the desktop client’s localhost relay is unavailable during reconnect, `ws_client.py` tries the shared-config `remoteWsUrl` as a direct fallback.
- **Shared-config URL following**: Manual connect, deferred auto-connect, and reconnect treat any loopback/default WebSocket URL (`localhost`, `127.0.0.1`, `::1`, or blank) as shared-config-following. If `~/.arkestrator/config.json` contains a remote `wsUrl` from the desktop client login, the bridge adopts that remote URL unless the user explicitly set a non-loopback custom URL in Blender preferences.
- **Shared identity**: The bridge follows the client-owned `workerName` and `machineId` from `~/.arkestrator/config.json` and sends `machineId` on the WS query string, so remote servers attach the bridge to the same persistent worker record.
- **Runtime menu discovery**: `Add to Arkestrator Context` discovers Blender `Menu` types at runtime, appends itself to all available `*_context_menu` surfaces plus Outliner submenus, and adds file-browser / asset-browser capture with a generic context snapshot fallback for RMB menus.

## Architecture (v2.0.0 -- Thin Bridge)
Bridges are execution endpoints only. They do NOT submit jobs, display job management UI, or maintain local caches of configs/projects/jobs. The Tauri client handles all prompt/submission/queue management. Bridges provide:
- **Connection** to the server (settings, auto-connect, reconnect with exponential backoff)
- **Editor context** pushed to server on connect + periodically (every 3s if changed, hash-based dedup)
- **Context menu** "Add to Arkestrator Context" pushes items directly to server via WS (no local context bag storage)
- **File application** from completed job results
- **Command execution** (Python scripts) from completed job results
- **Cross-bridge commands** (receive and execute commands from other bridges)
- **Shared-config hot refresh**: while connected/reconnecting, the WS client now re-reads `~/.arkestrator/config.json`, ignores malformed `apiKey` rewrites, and retries reconnects with the last known-good key if the newly shared auth does not work.

## Files (9)
| File | Purpose |
|------|---------|
| `__init__.py` | `bl_info` (v2.0.0), class registration, `register()`/`unregister()`, WS message dispatch (`_on_ws_message`), timer polling (100ms), context push timer (3s), auto-connect (1s deferred), `_push_editor_context()` with MD5 hash dedup, `_read_shared_config()` for API key auto-discovery |
| `ws_client.py` | WebSocket client using Python stdlib (socket, struct, hashlib). `BRIDGE_VERSION = "1.0.0"`. Threaded with `queue.Queue` for main-thread dispatch. Exponential backoff reconnect (3s->30s), remote-relay fallback to `remoteWsUrl`, and last-known-good API-key retry if shared-config auth changes go bad. |
| `operators.py` | `AGENTMGR_OT_connect` operator, `_build_editor_context()` (active editor type, active node tree, selected node-editor nodes, plus file-browser/asset-browser metadata), `_gather_file_attachments()` |
| `panels.py` | `AGENTMGR_PT_main_panel` (connection status icon + label, connect/disconnect button), `AGENTMGR_PT_settings` (collapsible sub-panel) |
| `preferences.py` | `AgentManagerPreferences` (AddonPreferences) -- persistent settings (server_url, auto_connect, auto_save, auto_reload, auto_apply_files, auto_execute_commands) |
| `properties.py` | `AgentManagerProperties` (PropertyGroup) -- scene state: `connection_status`, `is_connected` |
| `context_menu.py` | `AGENTMGR_OT_add_to_context` operator. Registers at runtime against Blender `Menu` types (`*_context_menu` plus key Outliner submenus) so the action appears broadly across viewport, Outliner, File Browser, Asset Browser, properties, and other RMB menu surfaces. Captures object selections, edit-mesh component selections, Outliner IDs/data-blocks, text selections, node-editor nodes, file-browser entries, asset-browser items, and a generic editor-context snapshot fallback when Blender does not expose a dedicated selection API. Pushes items directly to server via `bridge_context_item_add` WS message using module-level `_next_context_index` counter. Menu registration is idempotent (`_menus_registered`) and tracks the discovered menu set for clean unregisters after addon reloads. |
| `file_applier.py` | `apply_file_changes()` -- write/delete files from FileChange arrays |
| `command_executor.py` | `execute_commands()` -- run Python scripts via `exec(compile(...))` |

## Addon Lifecycle
1. `register()`: register classes -> set up scene properties (`PointerProperty`) -> register context menus -> create `WebSocketClient` instance -> start WS poll timer (100ms, persistent) -> start context push timer (3s, persistent, first_interval=5s) -> schedule `_auto_connect_deferred` (1s)
2. WS poll timer (`_timer_poll`, 100ms): drains WS incoming queue, dispatches messages via `_on_ws_message`, redraws UI
3. Context push timer (`_context_push_timer`, 3s): calls `_push_editor_context()` -- builds editor context, hashes with MD5, sends `bridge_editor_context` only if hash differs from `_last_editor_context_hash`
4. Auto-connect (`_auto_connect_deferred`, 1s one-shot): checks `auto_connect` pref, reads shared config for API key if needed, calls `ws_client.connect()`
5. `unregister()`: disconnect WS -> unregister timers -> remove menus -> remove properties -> unregister classes

## Registered Classes (in order)
1. `AgentManagerPreferences` (AddonPreferences)
2. `AgentManagerProperties` (PropertyGroup)
3. `AGENTMGR_OT_connect` (Operator)
4. `AGENTMGR_OT_add_to_context` (Operator)
5. `AGENTMGR_PT_main_panel` (Panel)
6. `AGENTMGR_PT_settings` (Panel, child of main_panel)

## Settings (AddonPreferences -- persists across sessions)
| Setting | Default | Purpose |
|---------|---------|---------|
| `server_url` | `ws://localhost:7800/ws` | Server WebSocket endpoint |
| `auto_connect` | `True` | Connect on addon load |
| `auto_save` | `True` | Save .blend before operations |
| `auto_reload` | `True` | Revert file after completion |
| `auto_apply_files` | `True` | Apply file changes automatically |
| `auto_execute_commands` | `True` | Execute Python commands automatically |

### Removed Settings
- `api_key` - auto-discovered from `~/.arkestrator/config.json` (written by Tauri client on login)
- `worker_name` - sourced from the client-written shared config `workerName` (or an explicit bridge override) so the desktop client remains the canonical owner of machine identity
- `machine_id` - sourced from the same shared config `machineId` and sent alongside `workerName` so the server can join renamed same-machine bridge/client sockets

## Scene Properties (`AgentManagerProperties`)
| Property | Type | Purpose |
|----------|------|---------|
| `connection_status` | `StringProperty` | Display text for connection state (default: "Disconnected") |
| `is_connected` | `BoolProperty` | Whether WS is connected (default: False) |

## UI (N-Panel in 3D Viewport)
**Main Panel** (`AGENTMGR_PT_main_panel`, tab: "Arkestrator"):
- Connection status icon (LINKED/UNLINKED) + label showing `connection_status`
- Connect/Disconnect button (toggles based on `is_connected`)

**Settings Sub-Panel** (`AGENTMGR_PT_settings`, collapsible, default closed):
- Server URL
- Auto-connect, Auto-reload, Auto-apply, Auto-execute checkboxes

## WebSocket Client (`ws_client.py`)
- **No external dependencies** -- uses Python stdlib (socket, struct, hashlib, base64, ssl, json, uuid, threading, queue)
- Daemon thread for I/O, `queue.Queue` for thread-safe message passing
- `bpy.app.timers` polls queue at 100ms intervals on main thread
- Connect URL includes query params: `type=bridge`, `key`, `name`, `program=blender`, `programVersion`, `bridgeVersion=1.0.0`, `projectPath`, `workerName`, `machineId`
- `workerName` is only sent when explicitly supplied or when `~/.arkestrator/config.json` contains the client-owned canonical `workerName`; otherwise the bridge leaves worker identity resolution to the server fallback path
- Stale detection: 180s without frames triggers reconnect (`STALE_TIMEOUT_S`=180.0)
- Handshake retry: up to 2 attempts (`HANDSHAKE_RETRY_ATTEMPTS`=2) with 0.5s delay between retries
- Reconnect: exponential backoff 3s->30s (`RECONNECT_BASE_S`=3.0, `RECONNECT_MAX_S`=30.0)
- Backoff is only reset to 3s if the connection stayed up >10s (short-lived connections keep backing off)
- `_stop_event.clear()` is called AFTER `join()` so new thread always starts with a clean event
- On reconnect attempts (and during 1s socket timeout polls), shared config credentials are reloaded; changed `apiKey`, shared-followed `wsUrl`, shared `workerName`, or shared `machineId` trigger automatic reconnect with refreshed identity/auth.
- If the followed `wsUrl` is a desktop-owned loopback relay, reconnect now also tries shared `remoteWsUrl` before giving up so a dead local relay does not strand the bridge offline.
- RFC 6455 frame handling: TEXT, CLOSE, PING/PONG opcodes
- Send is thread-safe via `_send_lock` (threading.Lock)
- Internal queue messages: `_connected`, `_disconnected`, `_error` (dispatched by `poll()`)
- Disconnect reason is printed to stdout (visible in Blender System Console) for every disconnect

### Methods
| Method | Purpose |
|--------|---------|
| `connect(url, api_key, worker_name, project_path, project_name, program_version, machine_id?)` | Start connection (non-blocking, spawns background thread) |
| `disconnect()` | Graceful disconnect (stops reconnect loop) |
| `send_message(msg)` | Send a JSON message (thread-safe) |
| `send_context_item(item)` | Push a single context item to server (`bridge_context_item_add`) |
| `send_context_clear()` | Tell server to clear context bag for this bridge (`bridge_context_clear`) |
| `send_editor_context(editor_context, files)` | Push editor context snapshot (`bridge_editor_context`) |
| `send_bridge_command(target, commands, target_type, correlation_id)` | Send commands to another bridge (`bridge_command_send`) |
| `send_bridge_command_result(sender_id, correlation_id, success, executed, failed, skipped, errors, stdout?, stderr?)` | Send command execution results back (`bridge_command_result`) |
| `poll()` | Drain incoming queue -- call from main thread (bpy.app.timers) |

## Protocol Messages

### Sent by Bridge
| Message Type | When | Payload |
|-------------|------|---------|
| `bridge_context_item_add` | User right-clicks "Add to Arkestrator Context" | `{ item: { index, type, name, path, content, metadata } }` |
| `bridge_context_clear` | Available via `ws_client.send_context_clear()` | `{}` |
| `bridge_editor_context` | On connect + every 3s if changed (MD5 hash dedup) | `{ editorContext: {...}, files: [...] }` |
| `bridge_command_send` | Cross-bridge command routing | `{ target, targetType, commands, correlationId? }` |
| `bridge_command_result` | After executing a received bridge command | `{ senderId, correlationId, success, executed, failed, skipped, errors, stdout?, stderr? }` |

### Handled by Bridge
| Message Type | Action | Scene Guard |
|-------------|--------|-------------|
| `job_complete` | Apply files or execute commands based on `workspaceMode` | No (props optional) |
| `bridge_command` | Execute Python commands from another bridge | No |
| `bridge_command_result` | Log results from a remote bridge command | No |
| `error` | Display error in status + log | Yes (requires scene) |

**Note:** `job_complete`, `bridge_command`, and `bridge_command_result` are handled before the scene guard so they work even without an active scene. Status text updates are skipped when scene props are unavailable.

## Editor Context (`operators.py:_build_editor_context()`)
```json
{
  "projectRoot": "/path/to/blend/directory",
  "activeFile": "/path/to/file.blend",
  "metadata": {
    "bridge_type": "blender",
    "active_scene": "Scene",
    "blend_file_path": "/path/to/file.blend",
    "active_object": "Cube",
    "selected_objects": [{"name": "Cube", "type": "MESH", "path": "Cube"}],
    "selected_node_editor_nodes": [{"name": "Principled BSDF", "type": "ShaderNodeBsdfPrincipled", "path": "Material.001/Principled BSDF"}],
    "active_node_tree": "Material.001 NodeTree",
    "active_editor_type": "NODE_EDITOR",
    "selected_scripts": ["script.py"]
  }
}
```
File attachments (`_gather_file_attachments()`): all open `bpy.data.texts` blocks as `{path, content}`.

Periodic push: hashed with MD5 (`hashlib.md5`), only sent when content changes. Hash covers both `editorContext` and `files` (JSON-serialized with `sort_keys=True`).

## Context Menu Integration (`context_menu.py`)
Menu coverage is registered defensively against Blender's runtime `Menu` registry:
- All available `*_context_menu` menu types are discovered at runtime and get the Arkestrator entry automatically.
- Additional Outliner RMB submenus such as `OUTLINER_MT_object`, `OUTLINER_MT_collection`, `OUTLINER_MT_id_data`, `OUTLINER_MT_asset`, and related view/edit menus are explicitly included because Blender routes some scene-tree right-click flows through those menus instead of the top-level `OUTLINER_MT_context_menu`.
- Source-specific capture handles `VIEW3D_*`, Outliner, File Browser, Asset Browser, Text Editor, and Node Editor.
- Other RMB menus fall back to a serialized editor-context snapshot so the action remains usable even when Blender only exposes generic active-context data.

Items are pushed directly to the server via `bridge_context_item_add` WS message using module-level `_next_context_index` counter (no local context bag storage). Counter increments per item added. Requires active WS connection; reports warning if disconnected.
Multi-selection is grouped into a single context item where appropriate (`Selection (N objects)`, `Mesh Selection (...)`, `Selection (N nodes)`, etc.) so the client sees one `@N` reference per selection set instead of one item per element.

### Object metadata captured
- `class` (object type: MESH, CAMERA, LIGHT, etc.)
- `properties.location` (x, y, z formatted to 3 decimal places)
- `properties.rotation` (euler x, y, z)
- `properties.scale` (x, y, z)
- `properties.vertices` / `properties.faces` (MESH objects only)

### Text block context
- Full script content if no selection
- Selected text with `from_line`/`to_line` metadata if selection exists
- Extension detected from text block name (falls back to "py")

### File / Asset browser context
- File Browser: captures selected or active `FileSelectEntry` items, resolves paths relative to the current browser directory, and inlines text-like file contents when the file is small enough to be safely embedded.
- Asset Browser: captures the active `AssetRepresentation`, including local-ID linkage when the asset comes from the current blend file.
- Fallback snapshots include file-browser directory, browse mode, active asset name, and other editor-context metadata so even generic RMB menus can still add a useful context item.

## File Application (`file_applier.py`)
- `apply_file_changes(changes, project_root)` -- create/modify/delete files
- **Binary file support**: checks `encoding` field - if `"base64"` and `binaryContent` present, writes binary via `base64.b64decode()`. Otherwise writes text content as UTF-8.
- Path resolution: absolute paths resolved via `os.path.realpath()`, relative resolved against blend file dir or cwd
- **Path traversal protection**: `_resolve_path()` uses `os.path.realpath()` to resolve symlinks and `..` components, then verifies the result stays within the project root. Raises `ValueError` (caught and logged as error) if a path escapes the root.
- Creates parent directories as needed (`os.makedirs(..., exist_ok=True)`)
- Returns `{"applied": int, "failed": int, "errors": list[str]}`

## Command Execution (`command_executor.py`)
- `execute_commands(commands)` -- filters for `python`/`py` language, skips unsupported
- Executes via `exec(compile(code, "<agent_command: description>", "exec"), {"__builtins__": __builtins__, "bpy": bpy})`
- Returns `{"executed": int, "failed": int, "skipped": int, "errors": list[str], "stdout": str, "stderr": str}`
- `stdout` and `stderr` capture the respective output streams during command execution
- Errors include full traceback (`traceback.format_exc()`)

## Job Completion Handling (`__init__.py:_handle_job_complete()`)
On `job_complete`:
1. If `error` field present -> log failure, return
2. If `workspaceMode == "command"` + has commands + `auto_execute_commands` -> run Python commands via `command_executor`
3. If has files + `auto_apply_files` -> apply file changes via `file_applier`
4. If `auto_reload` + blend file saved -> `bpy.ops.wm.revert_mainfile()` to pick up disk changes

## API Key Auto-Discovery
On connect (auto or manual), the addon always reads `~/.arkestrator/config.json` for the API key (`apiKey` field). It also picks up `wsUrl`, `workerName`, and `machineId` from the config whenever the Blender preference is still blank or loopback/default (`localhost`, `127.0.0.1`, `::1`), so remote server logins from the desktop client propagate cleanly to the bridge. This file is written by the Tauri client on every successful login. There is no manual API key entry - it is fully automatic.

## Cross-Bridge Commands
Both incoming and outgoing cross-bridge commands are supported:
- **Receiving**: `bridge_command` messages are dispatched in `_on_ws_message()` -> `_handle_bridge_command()`. Checks `auto_execute_commands` setting, runs commands via `command_executor.execute_commands()`, sends result back via `send_bridge_command_result()`.
- **Sending**: `ws_client.send_bridge_command(target, commands)` sends commands to other bridges by program name or ID.
- **Results**: `bridge_command_result` messages are handled in `_on_ws_message()` -> `_handle_bridge_command_result()`, logged to stdout.

## Removed in v2.1 (Further Thinning)
- `AGENTMGR_PT_log` panel (log sub-panel with last 5 lines) - use Blender's System Console for output
- `log_text` scene property - all logging now goes to stdout (`print()`)
- `dashboard_path` and `default_project` preferences - not needed in a thin bridge
- `get_bridge()` function and `_BridgeAPI` class - job submission belongs in Tauri client only
- `_append_log()` and `_append_log_safe()` helper functions

## Removed in v2 (Thin Bridge Rework)
The following were removed as job submission UI moved to the Tauri client:

**Operators removed:**
- `AGENTMGR_OT_submit_paused`, `AGENTMGR_OT_submit_start` (job submission)
- `AGENTMGR_OT_cancel_job` (job cancellation)
- `AGENTMGR_OT_open_dashboard` (open Tauri client)
- `AGENTMGR_OT_context_remove`, `AGENTMGR_OT_context_clear`, `AGENTMGR_OT_insert_reference` (local context bag management)

**Panels/UI removed:**
- `AGENTMGR_UL_context_bag` (UIList for context bag)
- Agent config selector, project selector, priority selector
- Auto-save checkbox, dependency field, prompt text area, submit buttons, cancel button, dashboard button

**Properties removed:**
- `AGENTMGR_ContextItem` PropertyGroup (local context bag item)
- Scene collection property for context bag
- Scene properties: `prompt`, `agent_config`, `project_override`, `priority`, `dependency`, `auto_save`, `active_job_id`, `context_bag_next_index`

**WS methods removed:**
- `submit_job()`, `cancel_job()`, `request_agent_configs()`, `request_job_list()`, `request_project_list()`

**Message handlers removed:**
- `job_accepted`, `job_started`, `job_log`, `job_dependency_blocked`
- `agent_config_list_response`, `job_list_response`, `project_list_response`

**Caches removed:**
- Local caches for agent configs, projects, and jobs (were used for enum dropdowns in v1)
