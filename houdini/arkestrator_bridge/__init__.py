"""Arkestrator Bridge -- Houdini package for connecting to the Arkestrator server.

Thin execution endpoint: connects via WebSocket, pushes editor context,
applies file changes, executes Python/HScript commands, and supports
cross-bridge communication. All job submission UI lives in the Tauri client.

Installation:
    Copy this package to $HOUDINI_USER_PREF_DIR/pythonX.Xlibs/
    or add its parent directory to $HOUDINI_PATH or $PYTHONPATH.

    Then register the Python Panel:
        import arkestrator_bridge
        arkestrator_bridge.register()
"""

from __future__ import annotations

import json
import os
import hashlib
import threading
from pathlib import Path

import hou

from .ws_client import WebSocketClient
from . import file_applier
from . import command_executor

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_ws_client: WebSocketClient | None = None
_timer_event: hou.hipFile | None = None
_last_editor_context_hash: str = ""
_poll_timer_active = False
_context_push_counter = 0
_context_bag_next_index = 1
_connected_hip_path: str = ""
_connect_url: str = ""
_connect_api_key: str = ""
_qt_menu_hook_installed = False
_qt_menu_event_filter = None
_LOG_PATH = Path.home() / "Library" / "Preferences" / "houdini" / "21.0" / "arkestrator_startup.log"

try:
    from PySide6 import QtCore, QtWidgets  # type: ignore
except Exception:
    try:
        from PySide2 import QtCore, QtWidgets  # type: ignore
    except Exception:
        QtCore = None  # type: ignore
        QtWidgets = None  # type: ignore


# ---------------------------------------------------------------------------
# WebSocket message dispatch (runs on main thread via timer)
# ---------------------------------------------------------------------------

def _append_startup_log(message: str) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except Exception:
        pass

def _on_ws_connected():
    global _context_bag_next_index, _last_editor_context_hash, _connected_hip_path
    print("[ArkestratorBridge] WS connected!")
    _append_startup_log("[ArkestratorBridge] WS connected!")
    # Reset context index and clear server-side context bag on every reconnect
    _context_bag_next_index = 1
    _last_editor_context_hash = ""
    _connected_hip_path = hou.hipFile.path() or ""
    if _ws_client:
        _ws_client.send_context_clear()
    _push_editor_context()


def _on_ws_disconnected():
    print("[ArkestratorBridge] WS disconnected")
    _append_startup_log("[ArkestratorBridge] WS disconnected")


def _on_ws_error(message: str):
    print(f"[ArkestratorBridge] WS error: {message}")
    _append_startup_log(f"[ArkestratorBridge] WS error: {message}")


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
        result = command_executor.execute_commands(commands_raw)
        executed = result.get("executed", 0)
        failed = result.get("failed", 0)
        print(f"[ArkestratorBridge] Commands: {executed} executed, {failed} failed")
        for err in result.get("errors", []):
            print(f"[ArkestratorBridge] cmd-error: {err}")
    elif files_raw:
        hip_path = hou.hipFile.path()
        project_root = os.path.dirname(hip_path) if hip_path else ""
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
    sender_id = str(payload.get("senderId", ""))
    commands = payload.get("commands", [])
    correlation_id = str(payload.get("correlationId", ""))

    print(f"[ArkestratorBridge] Executing {len(commands)} command(s) from {sender_id[:8]}")

    result = command_executor.execute_commands(commands)
    executed = result.get("executed", 0)
    failed = result.get("failed", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", [])
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    print(f"[ArkestratorBridge] Result: {executed} executed, {failed} failed, {skipped} skipped")

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
    """Build the editor context dict for the current Houdini state."""
    hip_path = hou.hipFile.path() or ""
    project_root = os.path.dirname(hip_path) if hip_path else ""

    # Selected nodes
    selected_nodes = []
    for node in hou.selectedNodes():
        selected_nodes.append({
            "name": node.name(),
            "type": node.type().name(),
            "path": node.path(),
        })

    # Current network editor path
    current_network = ""
    try:
        desktop = hou.ui.curDesktop()
        if desktop:
            pane_tab = desktop.paneTabOfType(hou.paneTabType.NetworkEditor)
            if pane_tab:
                current_network = pane_tab.pwd().path()
    except Exception:
        pass

    # Open Python source editors / VEX snippets
    selected_scripts = []
    try:
        for pane_tab in hou.ui.curDesktop().paneTabs():
            if pane_tab.type() == hou.paneTabType.PythonShell:
                selected_scripts.append("Python Shell")
    except Exception:
        pass

    return {
        "projectRoot": project_root,
        "activeFile": hip_path,
        "metadata": {
            "bridge_type": "houdini",
            "hip_file_path": hip_path,
            "current_network": current_network,
            "selected_nodes": [
                {"name": n["name"], "type": n["type"], "path": n["path"]}
                for n in selected_nodes
            ],
            "selected_scripts": selected_scripts,
        },
    }


def _gather_file_attachments() -> list[dict]:
    """Gather relevant file attachments from the Houdini session.

    Collects Python SOP code, wrangle VEX snippets, and HDA scripts
    from selected nodes.
    """
    files = []
    try:
        for node in hou.selectedNodes():
            # Python SOPs
            if node.type().name() in ("python", "pythonsop"):
                code = node.parm("python").eval() if node.parm("python") else ""
                if code:
                    files.append({
                        "path": f"{node.path()}/python",
                        "content": code,
                    })
            # Wrangle VEX
            elif "wrangle" in node.type().name().lower():
                snippet = node.parm("snippet")
                if snippet:
                    files.append({
                        "path": f"{node.path()}/vex",
                        "content": snippet.eval(),
                    })
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
    """Track active hip path changes without reconnecting the bridge socket."""
    global _connected_hip_path

    if not _ws_client or not _ws_client.connected:
        return

    current_hip_path = hou.hipFile.path() or ""
    if current_hip_path == _connected_hip_path:
        return

    _connected_hip_path = current_hip_path
    project_name = os.path.basename(current_hip_path) if current_hip_path else "Untitled"
    print(f"[ArkestratorBridge] Active hip changed: {project_name}")


# ---------------------------------------------------------------------------
# Timer-based polling (Houdini main thread)
# ---------------------------------------------------------------------------

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

    return True  # Keep timer alive


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
    global _ws_client, _poll_timer_active, _connect_url, _connect_api_key, _connected_hip_path
    _install_qt_menu_hook()

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

    # Avoid reconnect churn when startup/file events call connect() repeatedly
    # with the same endpoint. Active file/path metadata is sent via editor
    # context and mirrored server-side without reconnecting.
    if (
        _ws_client
        and _connect_url == url
        and _connect_api_key == api_key
        and (_ws_client.connected or _ws_client.connecting)
    ):
        return

    hip_path = hou.hipFile.path() or ""
    project_path = os.path.dirname(hip_path) if hip_path else ""
    project_name = os.path.basename(hip_path) if hip_path else "Untitled"
    _connected_hip_path = hip_path
    _connect_url = url
    _connect_api_key = api_key
    _append_startup_log(
        f"[ArkestratorBridge] connect start url={url} project={project_name} "
        f"has_api_key={'yes' if bool(api_key) else 'no'}"
    )

    _ws_client.connect(
        url=url,
        api_key=api_key,
        project_path=project_path,
        project_name=project_name,
        program_version=hou.applicationVersionString(),
    )

    # Start poll timer if not already running
    if not _poll_timer_active:
        try:
            hou.ui.addEventLoopCallback(_poll_callback)
            _poll_timer_active = True
            _append_startup_log("[ArkestratorBridge] poll callback registered on hou.ui")
        except Exception:
            # Fallback for headless/hython sessions: start a polling thread.
            # Some environments don't provide hdefereval; start directly.
            try:
                import hdefereval
                hdefereval.executeInMainThreadWithResult(_start_thread_poll)
                _append_startup_log("[ArkestratorBridge] poll fallback started via hdefereval")
            except Exception:
                _start_thread_poll()
                _append_startup_log("[ArkestratorBridge] poll fallback started via background thread")


def disconnect():
    """Disconnect from the Arkestrator server."""
    global _poll_timer_active
    if _ws_client:
        _ws_client.disconnect()
    if _poll_timer_active:
        try:
            hou.ui.removeEventLoopCallback(_poll_callback)
        except Exception:
            pass
        _poll_timer_active = False


def _poll_callback():
    """Event loop callback for Houdini UI thread."""
    _poll_timer()


def _start_thread_poll():
    """Fallback poll loop for headless/hython mode."""
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


def _is_selector_popup_menu(menu) -> bool:
    """Heuristic check for viewport selector RMB menus."""
    if QtWidgets is None:
        return False
    title = ""
    try:
        title = str(menu.title() or "").strip().lower()
    except Exception:
        title = ""
    if title.startswith("select "):
        return True
    try:
        texts = [str(a.text() or "").replace("&", "").strip() for a in menu.actions()]
    except Exception:
        return False
    if not texts:
        return False
    has_select_all = any(t.startswith("Select All ") for t in texts)
    has_select_none = any(t.startswith("Select No ") for t in texts)
    return has_select_all and has_select_none


def _inject_selector_context_action(menu) -> None:
    """Add the bridge context action to matching selector popup menus."""
    try:
        existing = [str(a.text() or "").strip() for a in menu.actions()]
    except Exception:
        existing = []

    if "Add to Arkestrator Context" in existing:
        return

    try:
        menu.addSeparator()
        action = menu.addAction("Add to Arkestrator Context")
        action.triggered.connect(lambda *_: add_current_selection_to_context(None))
    except Exception as exc:
        print(f"[ArkestratorBridge] Failed to inject selector popup action: {exc}")


def _install_qt_menu_hook() -> None:
    """Install a global Qt event filter to inject selector popup actions."""
    global _qt_menu_hook_installed, _qt_menu_event_filter
    if _qt_menu_hook_installed or QtCore is None or QtWidgets is None:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    class _ArkestratorMenuEventFilter(QtCore.QObject):
        def eventFilter(self, obj, event):  # noqa: N802 - Qt naming
            try:
                if (
                    event.type() in (QtCore.QEvent.Show, QtCore.QEvent.ShowToParent, QtCore.QEvent.Polish)
                    and isinstance(obj, QtWidgets.QMenu)
                    and _is_selector_popup_menu(obj)
                ):
                    _inject_selector_context_action(obj)
            except Exception:
                pass
            return False

    try:
        _qt_menu_event_filter = _ArkestratorMenuEventFilter(app)
        app.installEventFilter(_qt_menu_event_filter)
        _qt_menu_hook_installed = True
        print("[ArkestratorBridge] Installed selector popup menu hook.")
    except Exception as exc:
        print(f"[ArkestratorBridge] Failed to install selector popup hook: {exc}")


def register():
    """Register the bridge and auto-connect if config exists.

    Call this from your Houdini startup script or shelf tool:
        import arkestrator_bridge
        arkestrator_bridge.register()
    """
    _install_qt_menu_hook()

    shared = _read_shared_config()
    if shared and shared.get("apiKey"):
        connect()
        print("[ArkestratorBridge] Auto-connected to server")
    else:
        print("[ArkestratorBridge] No config found at ~/.arkestrator/config.json  — call arkestrator_bridge.connect(url, api_key)")


def unregister():
    """Disconnect and clean up."""
    disconnect()


# ---------------------------------------------------------------------------
# Public API for third-party plugins (SDK bridge-first integration)
# ---------------------------------------------------------------------------

def get_bridge():
    """Get the bridge public API object, or None if not connected.

    Usage from other Houdini scripts or the Python SDK:
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
        """Get the current Houdini editor context as a dict."""
        return _build_editor_context()

    def get_file_attachments(self) -> list[dict]:
        """Get VEX/Python snippets from selected nodes."""
        return _gather_file_attachments()

    def add_context_item(self, item: dict) -> None:
        """Push a context item to the server's context bag for this bridge."""
        global _context_bag_next_index
        if _ws_client and _ws_client.connected:
            item["index"] = _context_bag_next_index
            _context_bag_next_index += 1
            _ws_client.send_context_item(item)


def _node_metadata(node) -> dict:
    """Build basic metadata for a hou.Node."""
    return {
        "node_type": node.type().name(),
        "network_category": node.type().category().name(),
    }


def _add_unique_node(nodes: list, seen: set[str], node) -> None:
    """Append a node once by path."""
    if not isinstance(node, hou.Node):
        return
    try:
        path = node.path()
    except Exception:
        return
    if path in seen:
        return
    seen.add(path)
    nodes.append(node)


def _collect_nodes_from_menu_kwargs(kwargs: dict | None = None) -> list:
    """Return unique hou.Node items from OPmenu kwargs, scene viewer, or selection."""
    nodes: list = []
    seen: set[str] = set()

    if kwargs:
        for item in (kwargs.get("items") or []):
            _add_unique_node(nodes, seen, item)

        _add_unique_node(nodes, seen, kwargs.get("node"))
        _add_unique_node(nodes, seen, kwargs.get("pwd"))

        parm = kwargs.get("parm")
        if isinstance(parm, hou.Parm):
            _add_unique_node(nodes, seen, parm.node())

        for parm_item in (kwargs.get("parms") or []):
            if isinstance(parm_item, hou.Parm):
                _add_unique_node(nodes, seen, parm_item.node())

        pane = kwargs.get("pane")
        try:
            if pane and pane.type() == hou.paneTabType.SceneViewer:
                _add_unique_node(nodes, seen, pane.currentNode())
        except Exception:
            pass

    for node in hou.selectedNodes():
        _add_unique_node(nodes, seen, node)

    return nodes


def _scene_viewers_from_kwargs(kwargs: dict | None = None) -> list:
    """Collect scene viewers from kwargs + current desktop."""
    viewers: list = []
    seen: set[int] = set()

    def _push(viewer) -> None:
        if viewer is None:
            return
        try:
            if viewer.type() != hou.paneTabType.SceneViewer:
                return
        except Exception:
            return
        ident = id(viewer)
        if ident in seen:
            return
        seen.add(ident)
        viewers.append(viewer)

    if kwargs:
        _push(kwargs.get("pane"))

    try:
        desktop = hou.ui.curDesktop()
        if desktop:
            for pane in desktop.paneTabs():
                _push(pane)
    except Exception:
        pass

    return viewers


def _selection_type_name(selection) -> str:
    """Best-effort selection type name for hou.Selection."""
    try:
        sel_type = selection.selectionType()
        raw = str(sel_type)
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        return raw.lower()
    except Exception:
        return "components"


def _selection_text(selection, node, from_strings: str = "") -> str:
    """Best-effort selection expression text."""
    if from_strings:
        return from_strings
    try:
        geo = node.geometry()
        if geo:
            try:
                return selection.selectionString(geo, force_numeric=True)
            except TypeError:
                return selection.selectionString(geo)
    except Exception:
        pass
    return ""


def _collect_component_selection_context(kwargs: dict | None = None) -> tuple[list[dict], list]:
    """Collect viewport point/prim/edge/vertex selections.

    Returns:
        (selection entries, nodes referenced by those selections)
    """
    entries: list[dict] = []
    nodes: list = []
    seen_entries: set[tuple[str, str, str]] = set()
    seen_nodes: set[str] = set()

    for viewer in _scene_viewers_from_kwargs(kwargs):
        try:
            geometry_selection = viewer.currentGeometrySelection()
        except Exception:
            geometry_selection = None

        if geometry_selection is None:
            continue

        try:
            selection_nodes = list(geometry_selection.nodes())
        except Exception:
            selection_nodes = []

        try:
            selection_objs = list(geometry_selection.selections())
        except Exception:
            selection_objs = []

        try:
            selection_strings = list(geometry_selection.selectionStrings())
        except Exception:
            selection_strings = []

        for i, node in enumerate(selection_nodes):
            if not isinstance(node, hou.Node):
                continue

            selection_obj = selection_objs[i] if i < len(selection_objs) else None
            selection_kind = _selection_type_name(selection_obj) if selection_obj else "components"
            selection_expr = ""
            if i < len(selection_strings):
                selection_expr = str(selection_strings[i] or "").strip()
            if selection_obj:
                selection_expr = _selection_text(selection_obj, node, selection_expr)

            key = (node.path(), selection_kind, selection_expr)
            if key in seen_entries:
                continue
            seen_entries.add(key)

            count = 0
            if selection_obj is not None:
                try:
                    count = int(selection_obj.numSelected())
                except Exception:
                    count = 0

            entries.append({
                "name": node.name(),
                "path": node.path(),
                "node_type": node.type().name(),
                "network_category": node.type().category().name(),
                "selection_kind": selection_kind,
                "selection": selection_expr,
                "selection_count": count,
            })

            path = node.path()
            if path not in seen_nodes:
                seen_nodes.add(path)
                nodes.append(node)

    return entries, nodes


def _script_language_from_name(name: str) -> str:
    low = name.lower()
    if "python" in low:
        return "python"
    if "vex" in low or "wrangle" in low or "snippet" in low:
        return "vex"
    return "text"


def _script_item_from_parm(parm) -> dict | None:
    """Extract script context item from a parameter when it looks script-like."""
    if not isinstance(parm, hou.Parm):
        return None

    parm_name = ""
    try:
        parm_name = parm.name()
    except Exception:
        return None

    low = parm_name.lower()
    if not any(token in low for token in ("snippet", "vex", "python", "script", "code", "expr")):
        return None

    value = ""
    try:
        value = parm.unexpandedString()
    except Exception:
        try:
            value = parm.evalAsString()
        except Exception:
            value = ""

    if not value or not value.strip():
        return None

    node = parm.node()
    node_path = node.path() if isinstance(node, hou.Node) else ""
    node_name = node.name() if isinstance(node, hou.Node) else "parameter"
    language = _script_language_from_name(parm_name)

    return {
        "type": "script",
        "name": f"{node_name}:{parm_name}",
        "path": parm.path(),
        "content": value,
        "metadata": {
            "class": "HoudiniParmScript",
            "language": language,
            "parm_name": parm_name,
            "node_path": node_path,
        },
    }


def _script_items_from_node(node) -> list[dict]:
    """Extract known node-embedded scripts (wrangles/python)."""
    if not isinstance(node, hou.Node):
        return []

    items: list[dict] = []
    type_name = node.type().name().lower()
    candidates: list[tuple[str, str]] = []
    if type_name in ("python", "pythonsop"):
        candidates.append(("python", "python"))
    if "wrangle" in type_name:
        candidates.append(("snippet", "vex"))

    for parm_name, language in candidates:
        parm = node.parm(parm_name)
        if not isinstance(parm, hou.Parm):
            continue
        try:
            content = parm.unexpandedString()
        except Exception:
            try:
                content = parm.evalAsString()
            except Exception:
                content = ""
        if not content or not content.strip():
            continue
        items.append({
            "type": "script",
            "name": f"{node.name()}:{parm_name}",
            "path": parm.path(),
            "content": content,
            "metadata": {
                "class": "HoudiniNodeScript",
                "language": language,
                "parm_name": parm_name,
                "node_path": node.path(),
                "node_type": node.type().name(),
            },
        })

    return items


def _collect_script_context_items(kwargs: dict | None, nodes: list) -> list[dict]:
    """Collect script snippets from node parms and explicit parm context."""
    items: list[dict] = []
    seen_paths: set[str] = set()

    def _push(item: dict | None) -> None:
        if not item:
            return
        path = str(item.get("path", ""))
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        items.append(item)

    for node in nodes:
        for item in _script_items_from_node(node):
            _push(item)

    if kwargs:
        parm = kwargs.get("parm")
        if isinstance(parm, hou.Parm):
            _push(_script_item_from_parm(parm))
        for parm_item in (kwargs.get("parms") or []):
            if isinstance(parm_item, hou.Parm):
                _push(_script_item_from_parm(parm_item))
        for item in (kwargs.get("items") or []):
            if isinstance(item, hou.Parm):
                _push(_script_item_from_parm(item))

    return items


def _push_node_context_items(bridge, nodes: list) -> int:
    """Push node context items; groups multi-selection into one item."""
    if not nodes:
        return 0

    if len(nodes) == 1:
        node = nodes[0]
        try:
            bridge.add_context_item({
                "type": "node",
                "name": node.name(),
                "path": node.path(),
                "metadata": _node_metadata(node),
            })
            return 1
        except Exception as exc:
            print(f"[ArkestratorBridge] Failed adding node context {node.path()}: {exc}")
            return 0

    grouped_items: list[dict] = []
    summary_lines: list[str] = []
    for node in nodes:
        try:
            entry = {
                "name": node.name(),
                "path": node.path(),
                **_node_metadata(node),
            }
            grouped_items.append(entry)
            summary_lines.append(f"- {entry['name']} ({entry['node_type']}) at {entry['path']}")
        except Exception as exc:
            print(f"[ArkestratorBridge] Failed collecting node context {node.path()}: {exc}")

    if not grouped_items:
        return 0

    try:
        bridge.add_context_item({
            "type": "node",
            "name": f"Selection ({len(grouped_items)} nodes)",
            "path": "selection://houdini/nodes",
            "content": "Selected Houdini nodes:\n" + "\n".join(summary_lines),
            "metadata": {
                "class": "SelectionGroup",
                "selection_group": True,
                "selection_kind": "nodes",
                "count": len(grouped_items),
                "items": grouped_items,
            },
        })
        return len(grouped_items)
    except Exception as exc:
        print(f"[ArkestratorBridge] Failed adding node selection group: {exc}")
        return 0


def _push_component_context_items(bridge, selections: list[dict]) -> int:
    """Push viewport component selection context items."""
    if not selections:
        return 0

    if len(selections) == 1:
        entry = selections[0]
        try:
            label = entry.get("selection_kind", "components")
            bridge.add_context_item({
                "type": "node",
                "name": f"{entry['name']} ({label})",
                "path": f"{entry['path']}#{label}",
                "content": str(entry.get("selection", "")),
                "metadata": {
                    "class": "GeometrySelection",
                    "selection_group": False,
                    **entry,
                },
            })
            return 1
        except Exception as exc:
            print(f"[ArkestratorBridge] Failed adding component selection {entry.get('path', '')}: {exc}")
            return 0

    summary_lines = []
    for entry in selections:
        selection_text = str(entry.get("selection", "")).strip()
        detail = f": {selection_text}" if selection_text else ""
        summary_lines.append(
            f"- {entry['name']} ({entry.get('selection_kind', 'components')}) at {entry['path']}{detail}"
        )

    try:
        bridge.add_context_item({
            "type": "node",
            "name": f"Viewport Selection ({len(selections)} component sets)",
            "path": "selection://houdini/components",
            "content": "Selected Houdini viewport components:\n" + "\n".join(summary_lines),
            "metadata": {
                "class": "SelectionGroup",
                "selection_group": True,
                "selection_kind": "components",
                "count": len(selections),
                "items": selections,
            },
        })
        return len(selections)
    except Exception as exc:
        print(f"[ArkestratorBridge] Failed adding component selection group: {exc}")
        return 0


def _push_script_context_items(bridge, scripts: list[dict]) -> int:
    """Push script snippets (wrangle/python/parm selections) to context bag."""
    added = 0
    for item in scripts:
        try:
            bridge.add_context_item(item)
            added += 1
        except Exception as exc:
            print(f"[ArkestratorBridge] Failed adding script context {item.get('path', '')}: {exc}")
    return added


def add_selected_nodes_to_context(kwargs: dict | None = None) -> int:
    """Add selected Houdini context to Arkestrator context bag.

    Captures nodes, viewport component selections, and script-bearing contexts
    (e.g. wrangle snippets / python parms) so this action works from more
    than just network node selections.
    """
    bridge = get_bridge()
    if not bridge:
        try:
            hou.ui.displayMessage(
                "Arkestrator bridge is not connected.\nConnect first, then try again.",
                severity=hou.severityType.Warning,
            )
        except Exception:
            print("[ArkestratorBridge] Bridge is not connected; cannot add context item(s).")
        return 0

    nodes = _collect_nodes_from_menu_kwargs(kwargs)
    component_selections, component_nodes = _collect_component_selection_context(kwargs)
    nodes_by_path: dict[str, object] = {}
    for node in nodes:
        if isinstance(node, hou.Node):
            nodes_by_path[node.path()] = node
    for node in component_nodes:
        if isinstance(node, hou.Node):
            nodes_by_path[node.path()] = node
    script_items = _collect_script_context_items(kwargs, list(nodes_by_path.values()))

    if not nodes and not component_selections and not script_items:
        try:
            hou.ui.displayMessage(
                "No node/component/script selection found to add to context.",
                severity=hou.severityType.Message,
            )
        except Exception:
            print("[ArkestratorBridge] No node/component/script selection found.")
        return 0

    added = 0
    added += _push_node_context_items(bridge, nodes)
    added += _push_component_context_items(bridge, component_selections)
    added += _push_script_context_items(bridge, script_items)

    if added > 0:
        if added == 1:
            message = "Added 1 Houdini context item."
        else:
            message = f"Added {added} Houdini context items."
        try:
            hou.ui.setStatusMessage(message, severity=hou.severityType.Message)
        except Exception:
            print(f"[ArkestratorBridge] {message}")
    return added


def add_current_selection_to_context(kwargs: dict | None = None) -> int:
    """Alias for global/menu actions that add current Houdini selection context."""
    return add_selected_nodes_to_context(kwargs)


# Best-effort early install for viewport selector popup injection.
try:
    if hasattr(hou, "isUIAvailable") and hou.isUIAvailable():
        _install_qt_menu_hook()
except Exception:
    pass
