"""Arkestrator Bridge -- Unreal Engine 5 plugin for connecting to the Arkestrator server.

Thin execution endpoint: connects via WebSocket, pushes editor context,
applies file changes, executes Python/console commands, and supports
cross-bridge communication. All job submission UI lives in the Tauri client.

Installation (global):
    1. Copy ArkestratorBridge/ to your engine's Plugins/ directory
       e.g. C:\\Program Files\\Epic Games\\UE_5.x\\Engine\\Plugins\\
    2. Enable PythonScriptPlugin in Edit > Plugins > Scripting
    3. Enable Arkestrator Bridge in Edit > Plugins > Editor
    4. Restart the editor -- the bridge auto-registers via init_unreal.py
"""

from __future__ import annotations

import json
import os
import hashlib
import threading
import time

import unreal

from .ws_client import WebSocketClient
from . import file_applier
from . import command_executor
from . import context_menu

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_ws_client: WebSocketClient | None = None
_poll_handle = None  # Slate tick callback handle
_last_editor_context_hash: str = ""
_poll_timer_active = False
_poll_elapsed: float = 0.0  # Accumulated time for WS poll throttling
_context_push_elapsed: float = 0.0  # Accumulated time for context push throttling
_context_bag_next_index = 1
_connected_project_path: str = ""
_connect_url: str = ""
_connect_api_key: str = ""

# Throttle intervals (seconds)
_POLL_INTERVAL = 0.1  # WS poll every ~100ms
_CONTEXT_PUSH_INTERVAL = 3.0  # Context push every ~3s


# ---------------------------------------------------------------------------
# WebSocket message dispatch (runs on main thread via Slate tick)
# ---------------------------------------------------------------------------

def _on_ws_connected():
    global _context_bag_next_index, _last_editor_context_hash, _connected_project_path
    unreal.log("[ArkestratorBridge] WS connected!")
    # Reset context index and clear server-side context bag on every reconnect
    _context_bag_next_index = 1
    _last_editor_context_hash = ""
    _connected_project_path = unreal.Paths.project_dir() or ""
    context_menu.reset_context_index()
    if _ws_client:
        _ws_client.send_context_clear()
    _push_editor_context()


def _on_ws_disconnected():
    unreal.log("[ArkestratorBridge] WS disconnected")


def _on_ws_error(message: str):
    unreal.log_warning(f"[ArkestratorBridge] WS error: {message}")


def _on_ws_message(msg: dict):
    """Dispatch an incoming WebSocket message (main thread)."""
    msg_type = msg.get("type", "")
    payload = msg.get("payload", {})

    if msg_type == "job_complete":
        _handle_job_complete(payload)
    elif msg_type == "bridge_command":
        _handle_bridge_command(payload)
    elif msg_type == "bridge_command_result":
        _handle_bridge_command_result(payload)
    elif msg_type == "bridge_file_read_request":
        _handle_file_read_request(msg)
    elif msg_type == "error":
        code = str(payload.get("code", ""))
        message = str(payload.get("message", ""))
        unreal.log_warning(f"[ArkestratorBridge] Error: [{code}] {message}")


def _handle_job_complete(payload: dict):
    """Handle job_complete message -- apply files or execute commands."""
    job_id = str(payload.get("jobId", ""))
    success = bool(payload.get("success", False))
    files_raw = payload.get("files", [])
    commands_raw = payload.get("commands", [])
    workspace_mode = str(payload.get("workspaceMode", ""))
    error_text = str(payload.get("error", ""))

    if error_text:
        unreal.log_warning(f"[ArkestratorBridge] Job failed: {error_text}")
    elif success:
        unreal.log(f"[ArkestratorBridge] Job {job_id[:8]} completed successfully")

    if not success:
        return

    if workspace_mode == "command" and commands_raw:
        result = command_executor.execute_commands(commands_raw)
        executed = result.get("executed", 0)
        failed = result.get("failed", 0)
        unreal.log(f"[ArkestratorBridge] Commands: {executed} executed, {failed} failed")
        for err in result.get("errors", []):
            unreal.log_warning(f"[ArkestratorBridge] cmd-error: {err}")
    elif files_raw:
        project_root = unreal.Paths.project_dir() or ""
        result = file_applier.apply_file_changes(files_raw, project_root)
        applied = result.get("applied", 0)
        failed = result.get("failed", 0)
        unreal.log(f"[ArkestratorBridge] Files: {applied} applied, {failed} failed")
        for err in result.get("errors", []):
            unreal.log_warning(f"[ArkestratorBridge] file-error: {err}")
    else:
        unreal.log(f"[ArkestratorBridge] Job completed (no file changes or commands)")


def _handle_bridge_command(payload: dict):
    """Handle a bridge_command from another bridge, routed via the server."""
    sender_id = str(payload.get("senderId", ""))
    commands = payload.get("commands", [])
    correlation_id = str(payload.get("correlationId", ""))

    unreal.log(f"[ArkestratorBridge] Executing {len(commands)} command(s) from {sender_id[:8]}")

    result = command_executor.execute_commands(commands)
    executed = result.get("executed", 0)
    failed = result.get("failed", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", [])
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    unreal.log(f"[ArkestratorBridge] Result: {executed} executed, {failed} failed, {skipped} skipped")

    if _ws_client:
        _ws_client.send_bridge_command_result(
            sender_id, correlation_id, failed == 0, executed, failed, skipped, errors,
            stdout=stdout, stderr=stderr,
        )


def _handle_bridge_command_result(payload: dict):
    """Handle bridge_command_result -- log the result from a remote bridge."""
    program = str(payload.get("program", ""))
    success = bool(payload.get("success", False))
    executed = int(payload.get("executed", 0))
    failed = int(payload.get("failed", 0))
    status = "success" if success else "failed"
    unreal.log(f"[ArkestratorBridge] bridge-cmd-result {status} from {program}: {executed} executed, {failed} failed")


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
                         ".obj", ".mtl", ".usda", ".vex", ".log", ".csv"}
            ext = os.path.splitext(file_path)[1].lower()
            if ext in text_exts:
                try:
                    content = raw.decode("utf-8")
                    results.append({"path": file_path, "content": content, "encoding": "utf8", "size": len(raw)})
                    continue
                except UnicodeDecodeError:
                    pass

            # Binary (images, etc.)
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
# Editor context push
# ---------------------------------------------------------------------------

def _build_editor_context() -> dict:
    """Build the editor context dict for the current UE5 editor state."""
    project_root = unreal.Paths.project_dir() or ""
    project_name = unreal.Paths.get_project_file_path() or ""
    if project_name:
        project_name = os.path.basename(project_name).replace(".uproject", "")

    # Engine version
    engine_version = ""
    try:
        engine_version = unreal.SystemLibrary.get_engine_version()
    except Exception:
        pass

    # Active level
    active_level = ""
    try:
        world = unreal.EditorLevelLibrary.get_editor_world()
        if world:
            active_level = world.get_name()
    except Exception:
        pass

    # Selected actors
    selected_actors = []
    selected_assets = []
    selected_folders = []
    selected_material_nodes = []
    total_actors = 0
    try:
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if actor_subsystem:
            for actor in actor_subsystem.get_selected_level_actors():
                loc = actor.get_actor_location()
                selected_actors.append({
                    "name": actor.get_actor_label(),
                    "class": actor.get_class().get_name(),
                    "path": actor.get_path_name(),
                    "location": f"({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f})",
                })
    except Exception:
        pass

    try:
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        total_actors = len(all_actors) if all_actors else 0
    except Exception:
        pass

    try:
        for asset in unreal.EditorUtilityLibrary.get_selected_assets():
            selected_assets.append({
                "name": asset.get_name(),
                "class": asset.get_class().get_name(),
                "path": asset.get_path_name(),
            })
    except Exception:
        pass

    # Enrich Blueprint assets with introspection data
    from .blueprint_utils import is_blueprint, get_blueprint_info
    EditorAssetLib = getattr(unreal, "EditorAssetLibrary", None)
    for asset_entry in selected_assets:
        if asset_entry.get("class") != "Blueprint":
            continue
        try:
            asset_obj = None
            if EditorAssetLib is not None:
                asset_obj = EditorAssetLib.load_asset(asset_entry["path"])
            if asset_obj and is_blueprint(asset_obj):
                bp_info = get_blueprint_info(asset_obj)
                if bp_info:
                    asset_entry["blueprint"] = bp_info
        except Exception:
            pass

    try:
        for folder_path in unreal.EditorUtilityLibrary.get_selected_folder_paths():
            folder_path = str(folder_path or "").strip()
            if not folder_path:
                continue
            selected_folders.append({
                "name": folder_path.rsplit("/", 1)[-1] or folder_path,
                "path": folder_path,
            })
    except Exception:
        pass

    material_library = getattr(unreal, "MaterialEditingLibrary", None)
    if material_library is not None and selected_assets:
        for asset in unreal.EditorUtilityLibrary.get_selected_assets():
            try:
                material_nodes = list(material_library.get_selected_nodes(asset))
            except Exception:
                material_nodes = []
            for node in material_nodes:
                try:
                    selected_material_nodes.append({
                        "name": node.get_name(),
                        "class": node.get_class().get_name(),
                        "path": node.get_path_name(),
                        "material": asset.get_name(),
                    })
                except Exception:
                    pass

    return {
        "projectRoot": project_root,
        "activeFile": active_level,
        "metadata": {
            "bridge_type": "unreal",
            "project_name": project_name,
            "engine_version": engine_version,
            "active_level": active_level,
            "selected_actors": selected_actors,
            "selected_assets": selected_assets,
            "selected_folders": selected_folders,
            "selected_material_nodes": selected_material_nodes,
            "total_actors": total_actors,
        },
    }


def _gather_file_attachments() -> list[dict]:
    """Gather relevant file attachments from the UE5 session.

    UE5 does not have open text files like Blender or Houdini,
    so this returns an empty list. Could be extended to gather
    Blueprint graph data or source files in the future.
    """
    return []


def _push_editor_context():
    """Build and send the current editor context to the server."""
    global _last_editor_context_hash

    if not _ws_client or not _ws_client.connected:
        return

    try:
        editor_context = _build_editor_context()
        files = _gather_file_attachments()
    except Exception as e:
        unreal.log_warning(f"[ArkestratorBridge] Failed to build editor context: {e}")
        return

    ctx_str = json.dumps(editor_context, sort_keys=True) + json.dumps(files, sort_keys=True)
    ctx_hash = hashlib.md5(ctx_str.encode("utf-8")).hexdigest()

    if ctx_hash == _last_editor_context_hash:
        return

    _last_editor_context_hash = ctx_hash
    _ws_client.send_editor_context(editor_context, files)


# ---------------------------------------------------------------------------
# Slate tick callback (UE5 main thread polling)
# ---------------------------------------------------------------------------

def _tick_callback(delta_time: float):
    """Called every Slate tick (~60Hz). Throttles WS poll and context push."""
    global _poll_elapsed, _context_push_elapsed

    _poll_elapsed += delta_time
    _context_push_elapsed += delta_time

    # WS poll every ~100ms
    if _poll_elapsed >= _POLL_INTERVAL:
        _poll_elapsed = 0.0
        if _ws_client:
            _ws_client.poll()

    # Context push every ~3s
    if _context_push_elapsed >= _CONTEXT_PUSH_INTERVAL:
        _context_push_elapsed = 0.0
        if _ws_client and _ws_client.connected:
            try:
                _push_editor_context()
            except Exception as e:
                print(f"[ArkestratorBridge] Context push error: {e}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _read_shared_config() -> dict | None:
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


# ---------------------------------------------------------------------------
# Public registration API
# ---------------------------------------------------------------------------

def connect(url: str = "", api_key: str = ""):
    """Connect to the Arkestrator server.

    If url/api_key are empty, auto-discovers from ~/.arkestrator/config.json.
    """
    global _ws_client, _poll_timer_active, _poll_handle
    global _connect_url, _connect_api_key, _connected_project_path

    if _ws_client is None:
        _ws_client = WebSocketClient()
        _ws_client.on_connected = _on_ws_connected
        _ws_client.on_disconnected = _on_ws_disconnected
        _ws_client.on_message = _on_ws_message
        _ws_client.on_error = _on_ws_error

    # Auto-discover config
    if not url or not api_key:
        shared = _read_shared_config()
        if shared:
            if not api_key:
                api_key = shared.get("apiKey", "")
            if not url:
                url = shared.get("wsUrl", "ws://localhost:7800/ws")

    if not url:
        url = "ws://localhost:7800/ws"

    # Avoid reconnect churn when called repeatedly with the same endpoint
    if _ws_client and _ws_client.connected and _connect_url == url and _connect_api_key == api_key:
        return

    project_root = unreal.Paths.project_dir() or ""
    project_name = unreal.Paths.get_project_file_path() or ""
    if project_name:
        project_name = os.path.basename(project_name).replace(".uproject", "")
    _connected_project_path = project_root
    _connect_url = url
    _connect_api_key = api_key

    # Engine version
    program_version = ""
    try:
        program_version = unreal.SystemLibrary.get_engine_version()
    except Exception:
        pass

    _ws_client.connect(
        url=url,
        api_key=api_key,
        project_path=project_root,
        project_name=project_name,
        program_version=program_version,
    )

    # Start Slate tick callback if not already running
    if not _poll_timer_active:
        _poll_handle = unreal.register_slate_post_tick_callback(_tick_callback)
        _poll_timer_active = True


def disconnect():
    """Disconnect from the Arkestrator server."""
    global _poll_timer_active, _poll_handle
    if _ws_client:
        _ws_client.disconnect()
    if _poll_timer_active and _poll_handle is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_poll_handle)
        except Exception:
            pass
        _poll_handle = None
        _poll_timer_active = False


def register():
    """Register the bridge and auto-connect if config exists.

    Called automatically by init_unreal.py on editor startup.
    Can also be called manually from the Python console:
        import arkestrator_bridge
        arkestrator_bridge.register()
    """
    # Register context menus and toolbar button
    context_menu.register_menus()
    context_menu.register_toolbar_button()

    # Auto-connect if config exists
    shared = _read_shared_config()
    if shared and shared.get("apiKey"):
        connect()
        unreal.log("[ArkestratorBridge] Auto-connected to server")
    else:
        unreal.log("[ArkestratorBridge] No config found at ~/.arkestrator/config.json  -- open the Tauri client and log in first")


def unregister():
    """Disconnect and clean up."""
    context_menu.unregister_menus()
    disconnect()


# ---------------------------------------------------------------------------
# Public API for third-party plugins (SDK bridge-first integration)
# ---------------------------------------------------------------------------

def get_bridge():
    """Get the bridge public API object, or None if not connected.

    Usage from UE5 Python console or scripts:
        from arkestrator_bridge import get_bridge
        bridge = get_bridge()
        if bridge:
            job = bridge.submit_job("do something")
    """
    if _ws_client and _ws_client.connected:
        return _BridgeAPI()
    return None


class _BridgeAPI:
    """Public API object returned by get_bridge().

    Provides a clean interface for third-party tools to submit jobs
    through the bridge, automatically attaching editor context.
    """

    @property
    def connected(self) -> bool:
        return _ws_client is not None and _ws_client.connected

    def submit_job(
        self,
        prompt: str,
        *,
        priority: str = "normal",
        agent_config_id: str | None = None,
        target_worker: str | None = None,
        project_id: str | None = None,
        depends_on: list[str] | None = None,
        start_paused: bool = False,
        workspace_mode: str | None = None,
        context_items: list[dict] | None = None,
    ) -> dict:
        """Submit a job via REST, with editor context from the bridge.

        Returns the created job dict (includes "id", "status", etc.).
        """
        import urllib.request

        editor_context = _build_editor_context()
        files = _gather_file_attachments()

        body: dict = {
            "prompt": prompt,
            "priority": priority,
            "editorContext": editor_context,
            "files": files,
        }

        if agent_config_id:
            body["agentConfigId"] = agent_config_id
        if target_worker:
            body["targetWorkerName"] = target_worker
        if project_id:
            body["projectId"] = project_id
        if depends_on:
            body["dependsOn"] = depends_on
        if start_paused:
            body["startPaused"] = True
        if workspace_mode:
            body["preferredMode"] = workspace_mode
        if context_items:
            body["contextItems"] = context_items

        config = _read_shared_config() or {}
        ws_url = config.get("wsUrl", "ws://localhost:7800/ws")
        server_url = ws_url.replace("ws://", "http://").replace("wss://", "https://")
        if server_url.endswith("/ws"):
            server_url = server_url[:-3]
        api_key = config.get("apiKey", "")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/api/jobs",
            data=data,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_editor_context(self) -> dict:
        """Get the current UE5 editor context as a dict."""
        return _build_editor_context()

    def get_file_attachments(self) -> list[dict]:
        """Get file attachments (currently empty for UE5)."""
        return _gather_file_attachments()

    def add_context_item(self, item: dict) -> None:
        """Push a context item to the server's context bag for this bridge."""
        global _context_bag_next_index
        if _ws_client and _ws_client.connected:
            item["index"] = _context_bag_next_index
            _context_bag_next_index += 1
            _ws_client.send_context_item(item)
