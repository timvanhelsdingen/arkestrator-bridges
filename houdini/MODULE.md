# Module: Houdini Bridge (`bridges/houdini/arkestrator_bridge/`)

## Purpose
Houdini Python package that connects to the Arkestrator server via WebSocket. Thin execution endpoint: pushes editor context, applies file changes, executes Python/HScript commands, and supports cross-bridge communication. All prompt/submission UI lives in the Tauri client.

## Recent Updates (2026-03-15)
- Connection stability improvements (2026-03-15): `ws_client.py` stale timeout increased from 90s to 180s for more tolerance of idle connections. Handshake retry support added (2 attempts with 0.5s delay) so transient handshake failures do not immediately fail the connection.

## Previous Updates (2026-03-13)
- Shared-config auth fallback hardening: `ws_client.py` now ignores malformed shared `apiKey` rewrites and retries reconnects with the last known-good key before failing. A bad `~/.arkestrator/config.json` write no longer strands Houdini offline after the next disconnect.
- Remote-relay reconnect hardening: when the desktop client's localhost relay becomes stale or disappears, `ws_client.py` now tries the shared-config `remoteWsUrl` directly during reconnect instead of staying pinned to a dead `127.0.0.1:<relay-port>` target. This keeps same-machine remote-server setups alive after relay failures.

## Architecture (v1.0.0 -- Thin Bridge)
Same thin bridge pattern as the Blender bridge. Bridges are execution endpoints only. They do NOT submit jobs or display job management UI. They provide:
- **Connection** to the server (auto-discover config, reconnect with exponential backoff)
- **Editor context** pushed to server on connect + periodically (every 3s if changed, hash-based dedup)
- **File application** from completed job results
- **Command execution** (Python + HScript) from completed job results
- **Cross-bridge commands** (receive and execute commands from other bridges)
- **Public SDK API** (`get_bridge()`) for third-party plugins to submit jobs through the bridge
- Runtime bytecode caches (`__pycache__`) are local-only artifacts and are not tracked in the repo.
- Headless/hython fallback polling is now resilient: if `hdefereval` is unavailable, bridge starts a direct background poll thread and keeps polling even before first WS connect, preventing immediate connect-then-disconnect loops.
- `scripts/python/pythonrc.py` startup is now resilient when Houdini executes pythonrc without `__file__`: it falls back to resolving the bridge package from `HOUDINI_PATH`/`HOUDINI_USER_PREF_DIR` before importing `arkestrator_bridge`.
- `scripts/python/ready.py` and `scripts/python/uiready.py` now also call `arkestrator_bridge.register()` during later startup phases and bootstrap the package root onto `sys.path` themselves, so the GUI app path can still auto-connect even if `pythonrc.py` was skipped or ran too early.
- `python3.11libs/pythonrc.py`, `ready.py`, and `uiready.py` now mirror the same bootstrap/register logic using SideFX's primary documented startup-hook locations for Houdini 21 / Python 3.11, giving package installs a deterministic GUI startup path in addition to `scripts/python/*`.
- `scripts/123.py` and `scripts/456.py` now also register the bridge during GUI scene startup/load, providing a last-resort interactive startup path even if earlier Python startup hooks were skipped.
- `arkestrator_bridge.json` now resolves the bridge root relative to the package file itself via `ARKESTRATOR_BRIDGE_DIR=$HOUDINI_PACKAGE_PATH/arkestrator_bridge`, then appends that directory to `HOUDINI_PATH` so repo checkouts and copied installs use the same layout across Windows, macOS, and Linux.
- `scripts/python/pythonrc.py` fallback resolution now derives candidate user-pref directories from Houdini/version context instead of assuming a Linux-only `~/houdini21.0` path.
- GUI startup now schedules one delayed reconnect watchdog via `startup_bootstrap.py`: if Houdini has still not established a bridge socket a few seconds after UI-ready, it re-reads shared config, forces one clean reconnect attempt, and writes connect/error/disconnect events to `~/Library/Preferences/houdini/21.0/arkestrator_startup.log`.
- Shared machine-identity follow pass: `ws_client.py` now consumes client-owned `workerName` and `machineId` from `~/.arkestrator/config.json`, sends `machineId` on the bridge query string, and hot-reconnects when shared identity changes so Houdini attaches to the same persistent worker row as the desktop client.
- WS auth/key rotation resilience: `ws_client.py` now reloads `~/.arkestrator/config.json` while reconnecting (and during read-loop timeouts), ignores malformed shared `apiKey` rewrites, and retries with the last known-good key if the newly shared auth no longer works.

## Installation
Copy the `arkestrator_bridge` package to one of:
- `$HOUDINI_USER_PREF_DIR/pythonX.Xlibs/`
- Any directory on `$HOUDINI_PATH` or `$PYTHONPATH`

Then in a startup script or shelf tool:
```python
import arkestrator_bridge
arkestrator_bridge.register()
```

## Files (18)
| File | Purpose |
|------|---------|
| `arkestrator_bridge.json` | Houdini package manifest. Resolves `ARKESTRATOR_BRIDGE_DIR` relative to the package file with `HOUDINI_PACKAGE_PATH`, then appends that directory to `HOUDINI_PATH` so the bridge package remains relocatable. |
| `__init__.py` | Main module: WS dispatch, editor context, register/unregister, auto-connect, public API (`get_bridge()`, `_BridgeAPI`). Timer polling via `hou.ui.addEventLoopCallback()` (10Hz) with fallback to thread poll for headless/hython. Tracks active HIP path changes and pushes updated editor context without forcing socket reconnects, so bridge presence stays stable while metadata still updates server-side. Also exposes `add_selected_nodes_to_context(kwargs)` for OPmenu right-click context pushes. Context collection supports network node selections, viewport geometry component selections (points/primitives/edges/vertices), and script-bearing parameter context (wrangle/python snippets), with grouped selection payloads for multi-item picks. On register, installs a Qt menu event filter that injects `Add to Arkestrator Context` into select-state viewport popup menus (the `Select All/No Geometry` RMB surface) for broader viewport-context coverage. |
| `ws_client.py` | WebSocket client using Python stdlib. Same as Blender bridge but with `program=houdini`. `BRIDGE_VERSION = "1.0.0"`. Reconnect path preserves thread lifecycle correctly (stop old thread, then clear stop-event before starting new thread), no-ops if URL metadata is unchanged, hot-refreshes shared-config credentials (`apiKey` / followed `wsUrl`) for automatic re-auth reconnects, ignores malformed shared-key rewrites, follows client-owned shared `workerName`/`machineId` instead of inventing a hostname, falls back from a dead desktop relay URL to shared `remoteWsUrl`, and retries with the last known-good key before giving up. |
| `file_applier.py` | `apply_file_changes()` - create/modify/delete files on disk. Supports binary files via `binaryContent` base64 + `encoding` field. Path traversal protection via `os.path.realpath()`. |
| `command_executor.py` | `execute_commands()` - Python via `exec()` + HScript via `hou.hscript()` |
| `scripts/123.py` | GUI new-scene startup hook. Re-runs bridge registration when Houdini starts into a new untitled session. |
| `scripts/456.py` | GUI file-load startup hook. Re-runs bridge registration when Houdini opens or finishes loading a HIP file. |
| `python3.11libs/pythonrc.py` | Early startup hook in SideFX's primary Houdini 21 startup location. Bootstraps the package root onto `sys.path` and attempts initial registration. |
| `python3.11libs/ready.py` | Post-startup hook in SideFX's primary Houdini 21 startup location. Re-runs registration after non-graphical startup completes. |
| `python3.11libs/uiready.py` | UI-ready hook in SideFX's primary Houdini 21 startup location. Re-runs registration once the interactive UI is available. |
| `scripts/python/pythonrc.py` | Early startup hook. Resolves the package onto `sys.path` and attempts initial bridge registration as soon as Houdini loads package startup scripts. |
| `scripts/python/ready.py` | Post-startup hook that re-runs `register()` after non-graphical startup completes, improving reliability when early startup is too soon. |
| `scripts/python/uiready.py` | GUI-ready startup hook that re-runs `register()` once Houdini's interactive UI is available, improving auto-connect reliability in the app process. |
| `startup_bootstrap.py` | Deferred GUI bootstrap helper. Schedules UI-thread bridge startup, performs the explicit post-UI `connect()`, and now adds a one-shot reconnect watchdog plus startup-log breadcrumbs for stubborn GUI offline cases. |
| `arkestrator_bridge/OPmenu.xml` | Houdini node/network right-click menu supplement (`Add to Arkestrator Context`) that forwards active selection context to `arkestrator_bridge.add_current_selection_to_context(kwargs)`. |
| `arkestrator_bridge/PARMmenu.xml` | Parameter RMB supplement (`Add to Arkestrator Context`) so wrangle/python/script parameter selections can be pushed directly from parm editor contexts. |
| `arkestrator_bridge/MainMenuCommon.xml` | Global top-menu entry `Arkestrator -> Add Current Selection to Arkestrator Context` for an always-available action path (also hotkey-bindable via Hotkey Manager). |
| `arkestrator_bridge/SelectCustomMenu` | Scene-viewer Component Groups custom-menu extension that adds `Add to Arkestrator Context` for viewport/component selection workflows. |
| `arkestrator_bridge/PaneTabTypeMenu.xml` | Pane-tab context menu supplement that adds `Add to Arkestrator Context` to pane right-click menus (including scene-viewer/viewport tabs), forwarding selection capture to `arkestrator_bridge.add_current_selection_to_context(kwargs)`. |

## Public API

### Module-level functions
| Function | Purpose |
|----------|---------|
| `register()` | Auto-connect if config exists, start poll timer |
| `unregister()` | Disconnect and clean up |
| `connect(url, api_key)` | Manual connect (auto-discovers from `~/.arkestrator/config.json` if empty) |
| `disconnect()` | Graceful disconnect |
| `get_bridge()` | Returns `_BridgeAPI` instance if connected, `None` otherwise |

### `_BridgeAPI` (returned by `get_bridge()`)
| Method | Purpose |
|--------|---------|
| `submit_job(prompt, **kwargs)` | Submit a job via REST with auto-gathered Houdini editor context |
| `get_editor_context()` | Get current Houdini state as dict |
| `get_file_attachments()` | Get VEX/Python snippets from selected nodes |
| `add_context_item(item)` | Push a context item to the server's context bag |

## Editor Context
```json
{
  "projectRoot": "/path/to/hip/directory",
  "activeFile": "/path/to/file.hip",
  "metadata": {
    "bridge_type": "houdini",
    "hip_file_path": "/path/to/file.hip",
    "current_network": "/obj/geo1",
    "selected_nodes": [{"name": "box1", "type": "box", "path": "/obj/geo1/box1"}],
    "selected_scripts": []
  }
}
```

File attachments: Python SOP code and wrangle VEX snippets from selected nodes.

## Command Execution
- **Python**: `exec(compile(...))` with `hou` in globals
- **HScript**: `hou.hscript(script)` - captures stderr as warnings
- Unsupported languages are skipped with error message

## Protocol Messages
Same as Blender bridge - see `bridges/blender/MODULE.md` for full protocol reference.

## Differences from Blender Bridge
| Aspect | Blender | Houdini |
|--------|---------|---------|
| Registration | `bpy.utils.register_class()` | `register()` function call |
| UI | N-Panel in 3D Viewport | No built-in panel (use shelf tool) |
| Timer | `bpy.app.timers.register()` | `hou.ui.addEventLoopCallback()` |
| Context menu | Right-click "Add to Arkestrator Context" | Multiple paths: `OPmenu.xml` (node/network RMB), `PARMmenu.xml` (parameter RMB), `SelectCustomMenu` (viewport `Component Groups` submenu), `PaneTabTypeMenu.xml` (pane/tab RMB, including Scene Viewer tabs), and global `MainMenuCommon.xml` (`Arkestrator` top menu) |
| Commands | Python only | Python + HScript |
| File attachments | All open text blocks | VEX/Python from selected nodes |
| Headless mode | N/A | Thread-based poll fallback for hython |
