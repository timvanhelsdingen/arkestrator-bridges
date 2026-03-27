"""Arkestrator Bridge -- Blender addon for connecting to the Arkestrator server.

Thin execution endpoint: connects via WebSocket, pushes editor context,
applies file changes, executes Python commands, and supports cross-bridge
communication. All job submission UI lives in the Tauri client.
"""

bl_info = {
    "name": "Arkestrator Bridge",
    "author": "Arkestrator",
    "version": (2, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Arkestrator",
    "description": "Bridge plugin connecting Blender to the Arkestrator hub",
    "category": "Development",
}

import json
from urllib.parse import urlparse

import bpy

from .preferences import AgentManagerPreferences
from .properties import (
    AgentManagerProperties,
    register_properties,
    unregister_properties,
)
from .operators import (
    AGENTMGR_OT_connect,
    _build_editor_context,
    _gather_file_attachments,
)
from .panels import (
    AGENTMGR_PT_main_panel,
    AGENTMGR_PT_settings,
)
from .context_menu import (
    AGENTMGR_OT_add_to_context,
    register_menus,
    unregister_menus,
)
from .ws_client import WebSocketClient
from . import file_applier
from . import command_executor

# ---------------------------------------------------------------------------
# Module-level WebSocket client (accessed by operators via _ws_client)
# ---------------------------------------------------------------------------

_ws_client: WebSocketClient | None = None
_timer_registered = False
_context_timer_registered = False
_last_editor_context_hash: str = ""


# ---------------------------------------------------------------------------
# All classes to register (ORDER MATTERS: PropertyGroups before Panels)
# ---------------------------------------------------------------------------

_classes = (
    # Preferences
    AgentManagerPreferences,
    # Property groups
    AgentManagerProperties,
    # Operators
    AGENTMGR_OT_connect,
    AGENTMGR_OT_add_to_context,
    # UI
    AGENTMGR_PT_main_panel,
    AGENTMGR_PT_settings,
)


# ---------------------------------------------------------------------------
# WebSocket message dispatch (runs on main thread via timer)
# ---------------------------------------------------------------------------

def _on_ws_connected():
    """Called when WebSocket connects (main thread)."""
    print("[ArkestratorBridge] WS connected!")
    scene = _get_active_scene()
    if scene and hasattr(scene, "agent_manager"):
        scene.agent_manager.connection_status = "Connected"
        scene.agent_manager.is_connected = True

    # Push editor context immediately on connect
    _push_editor_context()

    _tag_redraw()


def _on_ws_disconnected():
    """Called when WebSocket disconnects (main thread)."""
    scene = _get_active_scene()
    if scene and hasattr(scene, "agent_manager"):
        scene.agent_manager.connection_status = "Disconnected"
        scene.agent_manager.is_connected = False
    _tag_redraw()


def _on_ws_error(message: str):
    """Called when WebSocket encounters an error (main thread)."""
    print(f"[ArkestratorBridge] WS error: {message}")
    scene = _get_active_scene()
    if scene and hasattr(scene, "agent_manager"):
        scene.agent_manager.connection_status = message
        scene.agent_manager.is_connected = False
    _tag_redraw()


def _on_ws_message(msg: dict):
    """Dispatch an incoming WebSocket message (main thread)."""
    msg_type = msg.get("type", "")
    payload = msg.get("payload", {})

    # bridge_command, bridge_command_result, and job_complete must work even
    # with no active scene (they use bpy + addon prefs, not scene props)
    if msg_type == "bridge_command":
        _handle_bridge_command(payload)
        _tag_redraw()
        return

    if msg_type == "bridge_command_result":
        _handle_bridge_command_result(payload)
        _tag_redraw()
        return

    if msg_type == "bridge_file_read_request":
        _handle_file_read_request(msg)
        return

    if msg_type == "job_complete":
        scene = _get_active_scene()
        props = scene.agent_manager if (scene and hasattr(scene, "agent_manager")) else None
        _handle_job_complete(payload, props)
        _tag_redraw()
        return

    scene = _get_active_scene()
    if not scene or not hasattr(scene, "agent_manager"):
        return

    props = scene.agent_manager

    if msg_type == "error":
        code = str(payload.get("code", ""))
        message = str(payload.get("message", ""))
        props.connection_status = f"Error: [{code}] {message}"
        print(f"[ArkestratorBridge] Server error: [{code}] {message}")

    _tag_redraw()


def _handle_job_complete(payload: dict, props=None):
    """Handle job_complete message -- apply files or execute commands.

    ``props`` (scene.agent_manager) is optional so that command execution
    still works even when no active scene is available.  Status text
    updates are skipped when props is None.
    """
    job_id = str(payload.get("jobId", ""))
    success = bool(payload.get("success", False))
    files_raw = payload.get("files", [])
    commands_raw = payload.get("commands", [])
    workspace_mode = str(payload.get("workspaceMode", ""))
    error_text = str(payload.get("error", ""))

    def _set_status(text: str):
        if props is not None:
            props.connection_status = text

    if error_text:
        _set_status(f"Job failed: {error_text}")
        print(f"[ArkestratorBridge] Job {job_id[:8]} failed: {error_text}")
    elif success:
        print(f"[ArkestratorBridge] Job {job_id[:8]} finished successfully")

    if not success:
        return

    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
    except KeyError:
        print(f"[ArkestratorBridge] Job {job_id[:8]}: addon preferences not available, skipping execution")
        return

    if workspace_mode == "command" and commands_raw:
        if prefs.auto_execute_commands:
            result = command_executor.execute_commands(commands_raw)
            executed = result.get("executed", 0)
            failed = result.get("failed", 0)
            _set_status(f"Commands: {executed} executed, {failed} failed")
            for err in result.get("errors", []):
                print(f"[ArkestratorBridge] cmd-error: {err}")
        else:
            _set_status(f"{len(commands_raw)} command(s) received (auto-execute disabled)")
    elif files_raw:
        if prefs.auto_apply_files:
            import os
            project_root = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
            result = file_applier.apply_file_changes(files_raw, project_root)
            applied = result.get("applied", 0)
            failed = result.get("failed", 0)
            _set_status(f"Files: {applied} applied, {failed} failed")
            for err in result.get("errors", []):
                print(f"[ArkestratorBridge] file-error: {err}")
        else:
            _set_status(f"{len(files_raw)} file(s) received (auto-apply disabled)")
    else:
        _set_status("Job completed")

    # Auto-reload
    if prefs.auto_reload and bpy.data.filepath:
        try:
            bpy.ops.wm.revert_mainfile()
            print("[ArkestratorBridge] File reverted to pick up changes")
        except Exception:
            pass


def _handle_bridge_command(payload: dict):
    """Handle a bridge_command from another bridge or client, routed via the server."""
    sender_id = str(payload.get("senderId", ""))
    commands = payload.get("commands", [])
    correlation_id = str(payload.get("correlationId", ""))

    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
    except KeyError:
        prefs = None

    if prefs and not prefs.auto_execute_commands:
        print(f"[ArkestratorBridge] bridge-cmd: {len(commands)} command(s) from {sender_id[:8]} (auto-execute disabled)")
        if _ws_client:
            _ws_client.send_bridge_command_result(
                sender_id, correlation_id, True, 0, 0, len(commands),
                ["Auto-execute commands is disabled"],
            )
        return

    print(f"[ArkestratorBridge] bridge-cmd: Executing {len(commands)} command(s) from {sender_id[:8]}")

    result = command_executor.execute_commands(commands)
    executed = result.get("executed", 0)
    failed = result.get("failed", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", [])

    print(f"[ArkestratorBridge] bridge-cmd result: {executed} executed, {failed} failed, {skipped} skipped")
    for err in errors:
        print(f"[ArkestratorBridge] bridge-cmd-error: {err}")

    if _ws_client:
        _ws_client.send_bridge_command_result(
            sender_id, correlation_id, failed == 0, executed, failed, skipped, errors,
        )


def _handle_bridge_command_result(payload: dict):
    """Handle bridge_command_result -- log the result from a remote bridge."""
    bridge_id = str(payload.get("bridgeId", ""))
    program = str(payload.get("program", ""))
    success = bool(payload.get("success", False))
    executed = int(payload.get("executed", 0))
    failed = int(payload.get("failed", 0))
    skipped = int(payload.get("skipped", 0))
    errors = payload.get("errors", [])

    status = "success" if success else "failed"
    print(f"[ArkestratorBridge] bridge-cmd-result: {status} from {program} ({bridge_id[:8]}): {executed} executed, {failed} failed, {skipped} skipped")
    for err in errors:
        print(f"[ArkestratorBridge] bridge-cmd-error: {err}")


# ---------------------------------------------------------------------------
# File read (server-side agent reads files on client via bridge)
# ---------------------------------------------------------------------------

def _handle_file_read_request(msg: dict):
    """Handle bridge_file_read_request — read local files and send back to server."""
    import base64
    import os
    import uuid

    payload = msg.get("payload", {})
    correlation_id = str(payload.get("correlationId", ""))
    paths = payload.get("paths", [])
    if not correlation_id or not paths:
        return

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit

    results = []
    for file_path in paths:
        try:
            file_path = str(file_path)
            size = os.path.getsize(file_path)
            if size > MAX_FILE_SIZE:
                results.append({"path": file_path, "content": "", "encoding": "utf8", "size": size,
                                "error": f"File too large ({size} bytes, max {MAX_FILE_SIZE})"})
                continue

            with open(file_path, "rb") as f:
                raw = f.read()

            # Detect text vs binary
            text_exts = {".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                         ".py", ".gd", ".cs", ".js", ".ts", ".html", ".css", ".svg", ".xml",
                         ".obj", ".mtl", ".usda", ".vex", ".log", ".csv", ".blend1"}
            ext = os.path.splitext(file_path)[1].lower()
            if ext in text_exts:
                try:
                    content = raw.decode("utf-8")
                    results.append({"path": file_path, "content": content, "encoding": "utf8", "size": len(raw)})
                    continue
                except UnicodeDecodeError:
                    pass

            # Binary (images, blend files, etc.)
            content = base64.b64encode(raw).decode("ascii")
            results.append({"path": file_path, "content": content, "encoding": "base64", "size": len(raw)})

        except Exception as e:
            results.append({"path": file_path, "content": "", "encoding": "utf8", "size": 0,
                            "error": str(e)})

    if _ws_client:
        _ws_client.send_message({
            "type": "bridge_file_read_response",
            "id": str(uuid.uuid4()),
            "payload": {"correlationId": correlation_id, "files": results},
        })


# ---------------------------------------------------------------------------
# Editor context push (on connect + periodic)
# ---------------------------------------------------------------------------

def _push_editor_context():
    """Build and send the current editor context to the server."""
    global _last_editor_context_hash

    if not _ws_client or not _ws_client.connected:
        return

    try:
        editor_context = _build_editor_context()
        files = _gather_file_attachments()
    except Exception as e:
        print(f"[ArkestratorBridge] Failed to build editor context: {e}")
        return

    # Hash to avoid sending duplicate context
    ctx_str = json.dumps(editor_context, sort_keys=True) + json.dumps(files, sort_keys=True)
    import hashlib
    ctx_hash = hashlib.md5(ctx_str.encode("utf-8")).hexdigest()

    if ctx_hash == _last_editor_context_hash:
        return  # No change, skip

    _last_editor_context_hash = ctx_hash
    _ws_client.send_editor_context(editor_context, files)


def _context_push_timer():
    """Periodic timer: push editor context every ~3 seconds if changed."""
    try:
        if _ws_client and _ws_client.connected:
            _push_editor_context()
    except Exception as e:
        print(f"[ArkestratorBridge] Context push error: {e}")
    return 3.0  # Run again in 3 seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_scene():
    """Get the active scene safely."""
    try:
        return bpy.context.scene
    except Exception:
        return None


def _tag_redraw():
    """Force redraw of all 3D viewports to update the panel."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Timer callback -- polls WebSocket on main thread
# ---------------------------------------------------------------------------

def _timer_poll():
    """bpy.app.timers callback -- drains the WS incoming queue."""
    try:
        if _ws_client:
            _ws_client.poll()
    except Exception as e:
        # Must not raise -- Blender unregisters the timer on exception
        print(f"[ArkestratorBridge] Timer error: {e}")
    return 0.1  # Run again in 100ms


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register():
    global _ws_client, _timer_registered, _context_timer_registered

    for cls in _classes:
        bpy.utils.register_class(cls)

    register_properties()
    register_menus()

    # Create WebSocket client
    _ws_client = WebSocketClient()
    _ws_client.on_connected = _on_ws_connected
    _ws_client.on_disconnected = _on_ws_disconnected
    _ws_client.on_message = _on_ws_message
    _ws_client.on_error = _on_ws_error

    # Register timer for polling
    if not _timer_registered:
        bpy.app.timers.register(_timer_poll, persistent=True)
        _timer_registered = True

    # Register periodic context push timer
    if not _context_timer_registered:
        bpy.app.timers.register(_context_push_timer, persistent=True, first_interval=5.0)
        _context_timer_registered = True

    # Auto-connect if enabled (deferred to allow scene setup)
    bpy.app.timers.register(_auto_connect_deferred, first_interval=1.0)


def unregister():
    global _ws_client, _timer_registered, _context_timer_registered, _last_editor_context_hash

    # Disconnect WebSocket
    if _ws_client:
        _ws_client.disconnect()
        _ws_client = None

    # Unregister timers
    if _timer_registered:
        try:
            bpy.app.timers.unregister(_timer_poll)
        except Exception:
            pass
        _timer_registered = False

    if _context_timer_registered:
        try:
            bpy.app.timers.unregister(_context_push_timer)
        except Exception:
            pass
        _context_timer_registered = False

    _last_editor_context_hash = ""

    unregister_menus()
    unregister_properties()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


def _read_shared_config():
    """Read API key and server URL from shared config paths if available."""
    from pathlib import Path
    try:
        for dir_name in (".arkestrator",):
            config_path = Path.home() / dir_name / "config.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    return json.load(f)
    except Exception:
        pass
    return None


def _is_loopback_ws_url(url: str) -> bool:
    """Return True when the bridge URL is blank or points at the local machine."""
    value = str(url or "").strip()
    if not value:
        return True
    try:
        host = urlparse(value).hostname or ""
    except Exception:
        return False
    host = host.strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _resolve_ws_url_from_shared(preferred_url: str, shared: dict | None) -> str:
    """Prefer shared-config wsUrl whenever the bridge is still on a loopback/default URL."""
    url = str(preferred_url or "").strip()
    shared_ws = str((shared or {}).get("wsUrl", "")).strip()
    if shared_ws and (_is_loopback_ws_url(url) or url == shared_ws):
        return shared_ws
    return url


def _sync_prefs_server_url(prefs, resolved_url: str, original_url: str) -> None:
    """Keep the visible Blender preference in sync when it is following shared config."""
    if not prefs:
        return
    if _is_loopback_ws_url(original_url) and resolved_url and resolved_url != original_url:
        try:
            prefs.server_url = resolved_url
        except Exception:
            pass


def _auto_connect_deferred():
    """One-shot timer: auto-connect if preference is set."""
    try:
        print(f"[ArkestratorBridge] Auto-connect check, __package__={__package__}")
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.auto_connect and _ws_client:
            import os

            url = prefs.server_url.strip()
            api_key = ""

            # Read API key from shared config (~/.arkestrator/config.json)
            shared = _read_shared_config()
            if shared:
                api_key = shared.get("apiKey", "")
                original_url = url
                url = _resolve_ws_url_from_shared(url, shared)
                _sync_prefs_server_url(prefs, url, original_url)
                if api_key:
                    print("[ArkestratorBridge] Auto-loaded API key from shared config")

            print(f"[ArkestratorBridge] Connecting to {url}...")
            project_path = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
            blend_name = os.path.basename(bpy.data.filepath) if bpy.data.filepath else "Untitled"
            _ws_client.connect(
                url=url,
                api_key=api_key,
                project_path=project_path,
                project_name=blend_name,
                program_version=bpy.app.version_string,
            )
            scene = _get_active_scene()
            if scene and hasattr(scene, "agent_manager"):
                scene.agent_manager.connection_status = "Connecting..."
    except Exception:
        pass
    return None  # Don't repeat

