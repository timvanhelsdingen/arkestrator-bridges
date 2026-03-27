from __future__ import annotations

"""Arkestrator Bridge -- ComfyUI bridge for connecting to the Arkestrator server.

Standalone bridge process that connects to both the Arkestrator server (WebSocket)
and a running ComfyUI instance (HTTP API). Translates between the Arkestrator
bridge protocol and ComfyUI's workflow execution API.

Usage:
    python -m arkestrator_bridge
    python -m arkestrator_bridge --comfyui-url http://localhost:8188
"""

import json
import hashlib
import mimetypes
import os
import threading
import time
from urllib.parse import urlparse, urlunparse

from .ws_client import WebSocketClient
from .comfyui_client import ComfyUIClient
from . import file_applier
from . import command_executor
from . import context

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_ws_client: WebSocketClient | None = None
_comfyui_client: ComfyUIClient | None = None
_last_editor_context_hash: str = ""
_poll_thread: threading.Thread | None = None
_running = False
_context_bag_next_index = 1
MAX_BRIDGE_OUTPUT_ITEMS = 20
MAX_INLINE_OUTPUT_BYTES = max(
    64 * 1024,
    int(os.environ.get("ARKESTRATOR_MAX_INLINE_OUTPUT_BYTES", str(8 * 1024 * 1024))),
)


# ---------------------------------------------------------------------------
# WebSocket message dispatch
# ---------------------------------------------------------------------------

def _on_ws_connected():
    global _context_bag_next_index, _last_editor_context_hash
    print("[ArkestratorBridge] WS connected to Arkestrator server")
    # Reset context index and clear server-side context bag on every reconnect
    _context_bag_next_index = 1
    _last_editor_context_hash = ""
    if _ws_client:
        _ws_client.send_context_clear()
    _push_editor_context()


def _on_ws_disconnected():
    print("[ArkestratorBridge] WS disconnected from Arkestrator server")


def _on_ws_error(message: str):
    print(f"[ArkestratorBridge] WS error: {message}")


def _on_ws_message(msg: dict):
    """Dispatch an incoming WebSocket message."""
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
    """Handle job_complete message -- execute workflows or apply files."""
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
        result = command_executor.execute_commands(commands_raw, _comfyui_client)
        executed = result.get("executed", 0)
        failed = result.get("failed", 0)
        outputs = result.get("outputs", [])
        print(f"[ArkestratorBridge] Commands: {executed} executed, {failed} failed, {len(outputs)} output(s)")
        for err in result.get("errors", []):
            print(f"[ArkestratorBridge] cmd-error: {err}")
    elif files_raw:
        project_root = os.getcwd()
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

    result = command_executor.execute_commands(commands, _comfyui_client)
    executed = result.get("executed", 0)
    failed = result.get("failed", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", [])
    outputs = result.get("outputs", [])

    print(f"[ArkestratorBridge] Result: {executed} executed, {failed} failed, {skipped} skipped, {len(outputs)} output(s)")

    metadata_outputs = _build_transport_outputs(outputs)

    if _ws_client:
        _ws_client.send_bridge_command_result(
            sender_id, correlation_id, failed == 0, executed, failed, skipped, errors, metadata_outputs,
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


def _build_transport_outputs(outputs: list[dict]) -> list[dict]:
    """Prepare command outputs for WS transport.

    Includes base64 only for artifacts within MAX_INLINE_OUTPUT_BYTES so
    cross-bridge workflows can copy files across machines without flooding WS.
    """
    transport_outputs = []
    for out in outputs[:MAX_BRIDGE_OUTPUT_ITEMS]:
        if not isinstance(out, dict):
            continue

        filename = str(out.get("filename", ""))
        subfolder = str(out.get("subfolder", ""))
        artifact_type = str(out.get("type", ""))
        kind = str(out.get("kind", "image"))
        size_bytes = int(out.get("size", 0) or 0)
        mime_type = mimetypes.guess_type(filename)[0]

        item = {
            "filename": filename,
            "subfolder": subfolder,
            "type": artifact_type,
            "sizeBytes": size_bytes,
            "kind": kind,
        }
        if mime_type:
            item["mimeType"] = mime_type

        base64_payload = out.get("base64")
        if isinstance(base64_payload, str) and base64_payload:
            estimated_size = size_bytes if size_bytes > 0 else int((len(base64_payload) * 3) / 4)
            if estimated_size <= MAX_INLINE_OUTPUT_BYTES:
                item["base64"] = base64_payload
            else:
                item["omittedReason"] = f"base64_omitted_size_limit_{MAX_INLINE_OUTPUT_BYTES}"

        transport_outputs.append(item)

    return transport_outputs


# ---------------------------------------------------------------------------
# Editor context push
# ---------------------------------------------------------------------------

def _push_editor_context():
    """Build and send the current editor context to the server."""
    global _last_editor_context_hash

    if not _ws_client or not _ws_client.connected:
        return

    try:
        editor_context = context.build_editor_context(_comfyui_client)
        files = context.gather_file_attachments()
    except Exception as e:
        print(f"[ArkestratorBridge] Failed to build editor context: {e}")
        return

    ctx_str = json.dumps(editor_context, sort_keys=True) + json.dumps(files, sort_keys=True)
    ctx_hash = hashlib.md5(ctx_str.encode("utf-8")).hexdigest()

    if ctx_hash == _last_editor_context_hash:
        return

    _last_editor_context_hash = ctx_hash
    _ws_client.send_editor_context(editor_context, files)


# ---------------------------------------------------------------------------
# Poll loop (runs in main thread or background thread)
# ---------------------------------------------------------------------------

def _poll_loop():
    """Blocking poll loop for standalone operation."""
    context_counter = 0
    while _running:
        if _ws_client:
            _ws_client.poll()

        # Push editor context every ~3 seconds (loop runs at ~10Hz)
        context_counter += 1
        if context_counter >= 30:
            context_counter = 0
            if _ws_client and _ws_client.connected:
                try:
                    _push_editor_context()
                except Exception as e:
                    print(f"[ArkestratorBridge] Context push error: {e}")

        time.sleep(0.1)


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


def _normalize_server_ws_url(url: str) -> str:
    """Accept http/ws/bare host input and normalize to a websocket URL."""
    raw = str(url or "").strip()
    if not raw:
        return "ws://localhost:7800/ws"
    if "://" not in raw:
        raw = f"ws://{raw}"

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme == "http":
        scheme = "ws"
    elif scheme == "https":
        scheme = "wss"
    elif scheme not in ("ws", "wss"):
        return raw

    path = parsed.path or ""
    if not path or path == "/":
        path = "/ws"
    elif not path.endswith("/ws"):
        path = f"{path.rstrip('/')}/ws"

    return urlunparse((scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect(url: str = "", api_key: str = "", comfyui_url: str = ""):
    """Connect to both Arkestrator server and ComfyUI instance.

    If url/api_key are empty, auto-discovers from ~/.arkestrator/config.json.
    """
    global _ws_client, _comfyui_client

    # Auto-discover config
    shared = _read_shared_config()
    if not url:
        url = (shared or {}).get("wsUrl", "ws://localhost:7800/ws")
    url = _normalize_server_ws_url(url)
    if not api_key:
        api_key = (shared or {}).get("apiKey", "")
    if not comfyui_url:
        comfyui_url = (shared or {}).get("comfyuiUrl", "http://127.0.0.1:8188")

    # Create ComfyUI client
    _comfyui_client = ComfyUIClient(comfyui_url)
    if _comfyui_client.is_available():
        print(f"[ArkestratorBridge] ComfyUI available at {comfyui_url}")
    else:
        print(f"[ArkestratorBridge] WARNING: ComfyUI not reachable at {comfyui_url}")

    # Create WebSocket client
    if _ws_client is None:
        _ws_client = WebSocketClient()
        _ws_client.on_connected = _on_ws_connected
        _ws_client.on_disconnected = _on_ws_disconnected
        _ws_client.on_message = _on_ws_message
        _ws_client.on_error = _on_ws_error

    # Get ComfyUI version for program_version
    program_version = ""
    try:
        stats = _comfyui_client.get_system_stats()
        program_version = str(stats.get("system", {}).get("comfyui_version", ""))
    except Exception:
        pass

    _ws_client.connect(
        url=url,
        api_key=api_key,
        project_name="ComfyUI",
        program_version=program_version,
    )


def disconnect():
    """Disconnect from both servers."""
    global _running
    _running = False
    if _ws_client:
        _ws_client.disconnect()


def run(url: str = "", api_key: str = "", comfyui_url: str = ""):
    """Connect and run the blocking poll loop. Use for standalone operation."""
    global _running
    connect(url, api_key, comfyui_url)
    _running = True
    print("[ArkestratorBridge] Bridge running. Press Ctrl+C to stop.")
    try:
        _poll_loop()
    except KeyboardInterrupt:
        print("\n[ArkestratorBridge] Shutting down...")
    finally:
        disconnect()


def register():
    """Register the bridge and auto-connect if config exists.

    For use from other Python scripts:
        import arkestrator_bridge
        arkestrator_bridge.register()
    """
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
# Public API for third-party integration (SDK bridge-first)
# ---------------------------------------------------------------------------

def get_bridge():
    """Get the bridge public API object, or None if not connected.

    Usage:
        from arkestrator_bridge import get_bridge
        bridge = get_bridge()
        if bridge:
            job = bridge.submit_job("generate an image of a cat")
    """
    if _ws_client and _ws_client.connected:
        return _BridgeAPI()
    return None


class _BridgeAPI:
    """Public API object returned by get_bridge()."""

    @property
    def connected(self) -> bool:
        return _ws_client is not None and _ws_client.connected

    @property
    def comfyui_available(self) -> bool:
        return _comfyui_client is not None and _comfyui_client.is_available()

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

        editor_context = context.build_editor_context(_comfyui_client)
        files = context.gather_file_attachments()

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

    def execute_workflow(self, workflow: dict, timeout: float = 300.0) -> dict:
        """Submit a ComfyUI workflow and wait for results.

        Returns the history entry with outputs.
        """
        if _comfyui_client is None:
            raise RuntimeError("ComfyUI client not available")
        prompt_id = _comfyui_client.submit_workflow(workflow)
        return _comfyui_client.poll_result(prompt_id, timeout=timeout)

    def get_editor_context(self) -> dict:
        """Get the current ComfyUI context as a dict."""
        return context.build_editor_context(_comfyui_client)

    def get_file_attachments(self) -> list[dict]:
        """Get file attachments (empty for ComfyUI)."""
        return context.gather_file_attachments()

    def add_context_item(self, item: dict) -> None:
        """Push a context item to the server's context bag for this bridge."""
        global _context_bag_next_index
        if _ws_client and _ws_client.connected:
            item["index"] = _context_bag_next_index
            _context_bag_next_index += 1
            _ws_client.send_context_item(item)
