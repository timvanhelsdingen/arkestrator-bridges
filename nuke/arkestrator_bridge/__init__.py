"""Arkestrator Bridge -- Nuke package for connecting to the Arkestrator server.

Thin execution endpoint: connects via WebSocket, pushes editor context,
applies file changes, executes Python/TCL commands, and supports
cross-bridge communication. All job submission UI lives in the Tauri client.

Installation:
    Copy this package to ~/.nuke/ or add its parent to NUKE_PATH.
    Then in ~/.nuke/menu.py:
        import arkestrator_bridge
        arkestrator_bridge.register()
"""

from __future__ import annotations

import json
import os
import hashlib
import threading
from pathlib import Path

from .ws_client import WebSocketClient
from . import file_applier
from . import command_executor

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_ws_client: WebSocketClient | None = None
_last_editor_context_hash: str = ""
_poll_timer_active = False
_context_push_counter = 0
_context_bag_next_index = 1
_connected_script_path: str = ""
_connect_url: str = ""
_connect_api_key: str = ""
_qt_menu_hook_installed = False
_qt_menu_event_filter = None

def _script_path() -> str:
    """Return the current Nuke script file path, or empty string if unsaved.

    _script_path() always returns the node name 'Root', not the file path.
    The actual script path is stored in the 'name' knob on the root node.
    """
    try:
        import nuke
        path = nuke.root()["name"].value()
        return path if path else ""
    except Exception:
        return ""


try:
    from PySide2 import QtCore, QtWidgets  # type: ignore  -- Nuke ships PySide2
except Exception:
    try:
        from PySide6 import QtCore, QtWidgets  # type: ignore
    except Exception:
        QtCore = None  # type: ignore
        QtWidgets = None  # type: ignore


# ---------------------------------------------------------------------------
# WebSocket message dispatch (runs on main thread via timer)
# ---------------------------------------------------------------------------

def _on_ws_connected():
    global _context_bag_next_index, _last_editor_context_hash, _connected_script_path
    print("[ArkestratorBridge] WS connected!")
    _context_bag_next_index = 1
    _last_editor_context_hash = ""
    try:
        import nuke
        _connected_script_path = _script_path() or ""
    except Exception:
        _connected_script_path = ""
    if _ws_client:
        _ws_client.send_context_clear()
    _push_editor_context()


def _on_ws_disconnected():
    print("[ArkestratorBridge] WS disconnected")


def _on_ws_error(message: str):
    print(f"[ArkestratorBridge] WS error: {message}")


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
        print(f"[ArkestratorBridge] Error: [{code}] {message}")


def _handle_job_complete(payload: dict):
    """Handle job_complete message -- apply files or execute commands."""
    import nuke

    job_id = str(payload.get("jobId", ""))
    success = bool(payload.get("success", False))
    files_raw = payload.get("files", [])
    commands_raw = payload.get("commands", [])
    workspace_mode = str(payload.get("workspaceMode", ""))
    error_text = str(payload.get("error", ""))

    if error_text:
        print(f"[ArkestratorBridge] Job failed: {error_text}")
    elif success:
        print(f"[ArkestratorBridge] Job {job_id[:8]} completed successfully")

    if not success:
        return

    if workspace_mode == "command" and commands_raw:
        # Execute commands in main thread for thread safety
        def _exec():
            result = command_executor.execute_commands(commands_raw)
            executed = result.get("executed", 0)
            failed = result.get("failed", 0)
            print(f"[ArkestratorBridge] Commands: {executed} executed, {failed} failed")
            for err in result.get("errors", []):
                print(f"[ArkestratorBridge] cmd-error: {err}")

        nuke.executeInMainThread(_exec)
    elif files_raw:
        script_name = _script_path()
        project_root = os.path.dirname(script_name) if script_name else ""
        result = file_applier.apply_file_changes(files_raw, project_root)
        applied = result.get("applied", 0)
        failed = result.get("failed", 0)
        print(f"[ArkestratorBridge] Files: {applied} applied, {failed} failed")
        for err in result.get("errors", []):
            print(f"[ArkestratorBridge] file-error: {err}")
    else:
        print(f"[ArkestratorBridge] Job completed (no file changes or commands)")


def _handle_bridge_command(payload: dict):
    """Handle a bridge_command from another bridge, routed via the server."""
    import nuke

    sender_id = str(payload.get("senderId", ""))
    commands = payload.get("commands", [])
    correlation_id = str(payload.get("correlationId", ""))

    print(f"[ArkestratorBridge] Executing {len(commands)} command(s) from {sender_id[:8]}")

    def _exec():
        result = command_executor.execute_commands(commands)
        executed = result.get("executed", 0)
        failed = result.get("failed", 0)
        skipped = result.get("skipped", 0)
        errors = result.get("errors", [])

        print(f"[ArkestratorBridge] Result: {executed} executed, {failed} failed, {skipped} skipped")

        if _ws_client:
            _ws_client.send_bridge_command_result(
                sender_id, correlation_id, failed == 0, executed, failed, skipped, errors,
            )

    nuke.executeInMainThread(_exec)


def _handle_bridge_command_result(payload: dict):
    """Handle bridge_command_result -- log the result from a remote bridge."""
    program = str(payload.get("program", ""))
    success = bool(payload.get("success", False))
    executed = int(payload.get("executed", 0))
    failed = int(payload.get("failed", 0))
    status = "success" if success else "failed"
    print(f"[ArkestratorBridge] bridge-cmd-result {status} from {program}: {executed} executed, {failed} failed")


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
    """Build the editor context dict for the current Nuke state."""
    import nuke

    script_name = _script_path() or ""
    project_root = os.path.dirname(script_name) if script_name else ""

    # Selected nodes
    selected_nodes = []
    for node in nuke.selectedNodes():
        node_class = node.Class()
        node_data = {
            "name": node.name(),
            "type": node_class,
            "path": node.fullName(),
        }
        # Add key knob values for context
        if node_class == "Read":
            file_knob = node.knob("file")
            if file_knob:
                node_data["file"] = file_knob.value()
        elif node_class == "Write":
            file_knob = node.knob("file")
            if file_knob:
                node_data["file"] = file_knob.value()
        selected_nodes.append(node_data)

    # Format info from root
    format_info = ""
    try:
        fmt = nuke.root().format()
        if fmt:
            format_info = f"{fmt.width()}x{fmt.height()}"
    except Exception:
        pass

    # Frame range
    first_frame = int(nuke.root().knob("first_frame").value()) if nuke.root().knob("first_frame") else 1
    last_frame = int(nuke.root().knob("last_frame").value()) if nuke.root().knob("last_frame") else 100

    return {
        "projectRoot": project_root,
        "activeFile": script_name,
        "metadata": {
            "bridge_type": "nuke",
            "script_path": script_name,
            "format": format_info,
            "frame_range": f"{first_frame}-{last_frame}",
            "selected_nodes": [
                {"name": n["name"], "type": n["type"], "path": n["path"]}
                for n in selected_nodes
            ],
        },
    }


def _gather_file_attachments() -> list[dict]:
    """Gather relevant file attachments from the Nuke session.

    Collects Python knob code, expression scripts, and Gizmo definitions
    from selected nodes.
    """
    import nuke

    files = []
    try:
        for node in nuke.selectedNodes():
            node_class = node.Class()

            # Python knobs (e.g., on BlinkScript, custom Python panels)
            for knob_name in ("knobChanged", "onCreate", "onDestroy",
                              "beforeRender", "afterRender", "beforeFrameRender",
                              "afterFrameRender", "kernelSource"):
                knob = node.knob(knob_name)
                if knob and hasattr(knob, "value"):
                    value = knob.value()
                    if value and isinstance(value, str) and value.strip():
                        files.append({
                            "path": f"{node.fullName()}/{knob_name}",
                            "content": value,
                        })

            # Expression knobs
            for knob in node.knobs().values():
                if hasattr(knob, "hasExpression") and knob.hasExpression():
                    try:
                        expr = knob.toScript()
                        if expr and expr.strip():
                            files.append({
                                "path": f"{node.fullName()}/{knob.name()}_expr",
                                "content": expr,
                            })
                    except Exception:
                        pass
    except Exception:
        pass
    return files


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

    ctx_str = json.dumps(editor_context, sort_keys=True) + json.dumps(files, sort_keys=True)
    ctx_hash = hashlib.md5(ctx_str.encode("utf-8")).hexdigest()

    if ctx_hash == _last_editor_context_hash:
        return

    _last_editor_context_hash = ctx_hash
    _ws_client.send_editor_context(editor_context, files)


def _refresh_connection_metadata_if_needed():
    """Track active script path changes without reconnecting the bridge socket."""
    global _connected_script_path

    if not _ws_client or not _ws_client.connected:
        return

    try:
        import nuke
        current_script = _script_path() or ""
    except Exception:
        return

    if current_script == _connected_script_path:
        return

    _connected_script_path = current_script
    project_name = os.path.basename(current_script) if current_script else "Untitled"
    print(f"[ArkestratorBridge] Active script changed: {project_name}")


# ---------------------------------------------------------------------------
# Timer-based polling (Nuke main thread)
# ---------------------------------------------------------------------------

_poll_timer_obj = None


def _poll_timer():
    """Called periodically to poll the WebSocket and push context."""
    global _context_push_counter

    if _ws_client:
        _ws_client.poll()

    # Push editor context every ~3 seconds (timer runs at ~10Hz)
    _context_push_counter += 1
    if _context_push_counter >= 30:
        _context_push_counter = 0
        if _ws_client and _ws_client.connected:
            try:
                _refresh_connection_metadata_if_needed()
                _push_editor_context()
            except Exception as e:
                print(f"[ArkestratorBridge] Context push error: {e}")


def _start_qt_timer():
    """Start a Qt-based timer for main-thread polling."""
    global _poll_timer_obj, _poll_timer_active
    if _poll_timer_active:
        return

    if QtCore is None:
        _start_thread_poll()
        return

    try:
        _poll_timer_obj = QtCore.QTimer()
        _poll_timer_obj.timeout.connect(_poll_timer)
        _poll_timer_obj.start(100)  # 10Hz
        _poll_timer_active = True
    except Exception:
        _start_thread_poll()


def _stop_qt_timer():
    """Stop the Qt timer."""
    global _poll_timer_obj, _poll_timer_active
    if _poll_timer_obj:
        try:
            _poll_timer_obj.stop()
            _poll_timer_obj.deleteLater()
        except Exception:
            pass
        _poll_timer_obj = None
    _poll_timer_active = False


def _start_thread_poll():
    """Fallback poll loop for terminal/render mode."""
    import time
    global _poll_timer_active
    _poll_timer_active = True

    def _loop():
        while _poll_timer_active and _ws_client is not None:
            try:
                _poll_timer()
            except Exception as e:
                print(f"[ArkestratorBridge] Poll loop error: {e}")
            time.sleep(0.1)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _read_shared_config() -> dict | None:
    """Read API key and server URL from shared config paths if available."""
    try:
        config_path = Path.home() / ".arkestrator" / "config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Context menu -- "Add to Arkestrator Context"
# ---------------------------------------------------------------------------

def _node_metadata(node) -> dict:
    """Build metadata for a nuke.Node."""
    import nuke
    meta = {
        "node_class": node.Class(),
    }
    # Add key properties based on node class
    node_class = node.Class()
    if node_class in ("Read", "Write"):
        file_knob = node.knob("file")
        if file_knob:
            meta["file"] = file_knob.value()
        fmt_knob = node.knob("format")
        if fmt_knob:
            meta["format"] = str(fmt_knob.value())
    elif node_class == "Grade":
        for k in ("blackpoint", "whitepoint", "multiply", "add", "gamma"):
            knob = node.knob(k)
            if knob:
                meta[k] = str(knob.value())
    elif node_class == "ColorCorrect":
        for k in ("saturation", "contrast", "gamma", "gain", "offset"):
            knob = node.knob(k)
            if knob:
                meta[k] = str(knob.value())
    elif node_class == "Merge2":
        op_knob = node.knob("operation")
        if op_knob:
            meta["operation"] = op_knob.value()
    elif node_class == "Transform":
        for k in ("translate", "rotate", "scale", "center"):
            knob = node.knob(k)
            if knob:
                meta[k] = str(knob.value())
    elif node_class == "Roto":
        meta["type"] = "roto"
    elif node_class == "RotoPaint":
        meta["type"] = "rotopaint"
    elif node_class in ("Tracker4", "Tracker3"):
        meta["type"] = "tracker"
    elif node_class == "Camera2":
        for k in ("focal", "haperture", "vaperture"):
            knob = node.knob(k)
            if knob:
                meta[k] = str(knob.value())
    elif node_class == "BlinkScript":
        kernel_knob = node.knob("kernelSource")
        if kernel_knob:
            meta["kernel_source"] = kernel_knob.value()

    # Add input connections
    inputs = []
    for i in range(node.inputs()):
        inp = node.input(i)
        if inp:
            inputs.append({"index": i, "name": inp.name(), "class": inp.Class()})
    if inputs:
        meta["inputs"] = inputs

    return meta


def add_selected_nodes_to_context(kwargs: dict | None = None) -> int:
    """Add selected Nuke nodes to the Arkestrator context bag.

    Captures nodes with their key properties, expressions, and connections.
    """
    import nuke

    bridge = get_bridge()
    if not bridge:
        nuke.message("Arkestrator bridge is not connected.\nConnect first, then try again.")
        return 0

    nodes = nuke.selectedNodes()
    # Fallback: menu clicks can sometimes clear selection state before the
    # callback fires.  Re-check via the 'selected' knob on all nodes.
    if not nodes:
        nodes = [n for n in nuke.allNodes() if n.knob("selected") and n["selected"].value()]
    if not nodes:
        print("[ArkestratorBridge] No nodes selected.")
        return 0

    added = 0

    if len(nodes) == 1:
        node = nodes[0]
        try:
            # Single node: send with full metadata
            item = {
                "type": "node",
                "name": node.name(),
                "path": node.fullName(),
                "metadata": _node_metadata(node),
            }
            # Include script content for BlinkScript nodes
            if node.Class() == "BlinkScript":
                kernel = node.knob("kernelSource")
                if kernel:
                    item["content"] = kernel.value()
            bridge.add_context_item(item)
            added = 1
        except Exception as exc:
            print(f"[ArkestratorBridge] Failed adding node context {node.fullName()}: {exc}")
    else:
        # Multiple nodes: group into one context item
        grouped_items = []
        summary_lines = []
        for node in nodes:
            try:
                entry = {
                    "name": node.name(),
                    "path": node.fullName(),
                    **_node_metadata(node),
                }
                grouped_items.append(entry)
                summary_lines.append(f"- {node.name()} ({node.Class()}) at {node.fullName()}")
            except Exception as exc:
                print(f"[ArkestratorBridge] Failed collecting node {node.fullName()}: {exc}")

        if grouped_items:
            try:
                bridge.add_context_item({
                    "type": "node",
                    "name": f"Selection ({len(grouped_items)} nodes)",
                    "path": "selection://nuke/nodes",
                    "content": "Selected Nuke nodes:\n" + "\n".join(summary_lines),
                    "metadata": {
                        "class": "SelectionGroup",
                        "selection_group": True,
                        "selection_kind": "nodes",
                        "count": len(grouped_items),
                        "items": grouped_items,
                    },
                })
                added = len(grouped_items)
            except Exception as exc:
                print(f"[ArkestratorBridge] Failed adding node selection group: {exc}")

    if added > 0:
        msg = f"Added {added} Nuke context item{'s' if added != 1 else ''}."
        print(f"[ArkestratorBridge] {msg}")

    return added


def add_viewer_context(kwargs: dict | None = None) -> int:
    """Add current viewer node and its input chain to context."""
    import nuke

    bridge = get_bridge()
    if not bridge:
        nuke.message("Arkestrator bridge is not connected.")
        return 0

    viewer = nuke.activeViewer()
    if not viewer:
        nuke.message("No active viewer.")
        return 0

    viewer_node = viewer.node()
    if not viewer_node:
        return 0

    # Get the active input of the viewer
    active_input = viewer.activeInput()
    input_node = viewer_node.input(active_input) if active_input is not None else None

    items = []
    if input_node:
        items.append({
            "name": input_node.name(),
            "path": input_node.fullName(),
            **_node_metadata(input_node),
        })

    if not items:
        return 0

    bridge.add_context_item({
        "type": "node",
        "name": f"Viewer Input ({items[0]['name']})",
        "path": f"viewer://nuke/{viewer_node.name()}",
        "content": f"Active viewer input: {items[0]['name']} ({items[0].get('node_class', '')})",
        "metadata": {
            "class": "ViewerContext",
            "viewer_node": viewer_node.name(),
            "active_input": active_input,
            "items": items,
        },
    })
    print(f"[ArkestratorBridge] Added viewer context: {items[0]['name']}")
    return 1


def add_script_to_context(kwargs: dict | None = None) -> int:
    """Add the current Nuke script (.nk) as a context item."""
    import nuke

    bridge = get_bridge()
    if not bridge:
        nuke.message("Arkestrator bridge is not connected.")
        return 0

    script_name = _script_path()
    if not script_name or script_name == "Root":
        nuke.message("No script file saved.")
        return 0

    # Export script to string
    try:
        script_content = nuke.toNode("root").toScript()
    except Exception:
        script_content = ""

    bridge.add_context_item({
        "type": "scene",
        "name": os.path.basename(script_name),
        "path": script_name,
        "content": script_content if len(script_content) < 256 * 1024 else "",
        "metadata": {
            "class": "NukeScript",
            "format": _build_editor_context().get("metadata", {}).get("format", ""),
            "frame_range": _build_editor_context().get("metadata", {}).get("frame_range", ""),
        },
    })
    print(f"[ArkestratorBridge] Added script context: {os.path.basename(script_name)}")
    return 1


# ---------------------------------------------------------------------------
# Public registration API
# ---------------------------------------------------------------------------

def connect(url: str = "", api_key: str = ""):
    """Connect to the Arkestrator server.

    If url/api_key are empty, auto-discovers from ~/.arkestrator/config.json.
    """
    global _ws_client, _connect_url, _connect_api_key, _connected_script_path
    import nuke

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

    # Avoid reconnect churn
    if (
        _ws_client
        and _connect_url == url
        and _connect_api_key == api_key
        and (_ws_client.connected or _ws_client.connecting)
    ):
        return

    script_name = _script_path() or ""
    project_path = os.path.dirname(script_name) if script_name else ""
    project_name = os.path.basename(script_name) if script_name else "Untitled"
    _connected_script_path = script_name
    _connect_url = url
    _connect_api_key = api_key

    # Get Nuke version
    program_version = ""
    try:
        program_version = f"{nuke.NUKE_VERSION_MAJOR}.{nuke.NUKE_VERSION_MINOR}v{nuke.NUKE_VERSION_RELEASE}"
    except Exception:
        pass

    _ws_client.connect(
        url=url,
        api_key=api_key,
        project_path=project_path,
        project_name=project_name,
        program_version=program_version,
    )

    # Start poll timer
    _start_qt_timer()


def disconnect():
    """Disconnect from the Arkestrator server."""
    if _ws_client:
        _ws_client.disconnect()
    _stop_qt_timer()


def register():
    """Register the bridge and auto-connect if config exists.

    Call this from ~/.nuke/menu.py:
        import arkestrator_bridge
        arkestrator_bridge.register()
    """
    _setup_menus()

    shared = _read_shared_config()
    if shared and shared.get("apiKey"):
        connect()
        print("[ArkestratorBridge] Auto-connected to server")
    else:
        print("[ArkestratorBridge] No config found at ~/.arkestrator/config.json  -- call arkestrator_bridge.connect(url, api_key)")


def unregister():
    """Disconnect and clean up."""
    disconnect()


# ---------------------------------------------------------------------------
# Nuke menu setup
# ---------------------------------------------------------------------------

def _setup_menus():
    """Add Arkestrator menu items to Nuke's menu bar and node graph."""
    import nuke

    # Top-level menu bar
    menu_bar = nuke.menu("Nuke")
    ark_menu = menu_bar.addMenu("Arkestrator")
    ark_menu.addCommand("Add Selected Nodes to Context", add_selected_nodes_to_context)
    ark_menu.addCommand("Add Viewer Input to Context", add_viewer_context)
    ark_menu.addCommand("Add Script to Context", add_script_to_context)
    ark_menu.addSeparator()
    ark_menu.addCommand("Connect", lambda: connect())
    ark_menu.addCommand("Disconnect", lambda: disconnect())

    # Node graph right-click menu
    node_menu = nuke.menu("Node Graph")
    ark_node_menu = node_menu.addMenu("Arkestrator")
    ark_node_menu.addCommand("Add Selected Nodes to Context", add_selected_nodes_to_context)
    ark_node_menu.addCommand("Add Viewer Input to Context", add_viewer_context)


# ---------------------------------------------------------------------------
# Public API for third-party plugins (SDK bridge-first integration)
# ---------------------------------------------------------------------------

def get_bridge():
    """Get the bridge public API object, or None if not connected.

    Usage from other Nuke scripts or the Python SDK:
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
        """Submit a job via REST, with editor context from the bridge."""
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
        """Get the current Nuke editor context as a dict."""
        return _build_editor_context()

    def get_file_attachments(self) -> list[dict]:
        """Get expression/script snippets from selected nodes."""
        return _gather_file_attachments()

    def add_context_item(self, item: dict) -> None:
        """Push a context item to the server's context bag for this bridge."""
        global _context_bag_next_index
        if _ws_client and _ws_client.connected:
            item["index"] = _context_bag_next_index
            _context_bag_next_index += 1
            _ws_client.send_context_item(item)
