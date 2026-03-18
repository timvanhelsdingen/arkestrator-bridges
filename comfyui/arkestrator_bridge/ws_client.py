from __future__ import annotations

"""WebSocket client for Arkestrator server.

Uses only Python stdlib (socket, struct, hashlib) -- no external dependencies.
Runs WebSocket I/O in a daemon thread; dispatches messages to a queue
that is drained on the main thread via poll().
"""

import hashlib
import base64
import json
import os
import queue
import random
import socket
import ssl
import struct
import threading
import time
import uuid
from urllib.parse import urlparse, urlencode

BRIDGE_VERSION = "1.0.0"
PROTOCOL_VERSION = 1  # Must match server's PROTOCOL_VERSION
RECONNECT_BASE_S = 3.0
RECONNECT_MAX_S = 30.0
STALE_TIMEOUT_S = 180.0  # If no frame received in 180s, assume connection is dead
HANDSHAKE_RETRY_ATTEMPTS = 2  # Retry handshake once on failure before giving up
DEFAULT_SHARED_WS_URL = "ws://localhost:7800/ws"


def _is_loopback_ws_url(url: str) -> bool:
    """Return True when the bridge URL points at the local machine."""
    value = str(url or "").strip()
    if not value:
        return True
    try:
        host = urlparse(value).hostname or ""
    except Exception:
        return False
    host = host.strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _is_valid_api_key(value: str) -> bool:
    """Return True when value matches the generated Arkestrator raw-key format."""
    trimmed = str(value or "").strip()
    if len(trimmed) != 52 or not trimmed.startswith("ark_"):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in trimmed[4:])


# ---------------------------------------------------------------------------
# Minimal WebSocket frame helpers (RFC 6455, client-side only)
# ---------------------------------------------------------------------------

OPCODE_TEXT = 0x1
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


def _make_frame(opcode: int, payload: bytes, mask: bool = True) -> bytes:
    """Build a single WebSocket frame."""
    header = bytearray()
    header.append(0x80 | opcode)  # FIN + opcode

    length = len(payload)
    mask_bit = 0x80 if mask else 0x00
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65536:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", length))

    if mask:
        mask_key = struct.pack("!I", random.getrandbits(32))
        header.extend(mask_key)
        masked = bytearray(payload)
        for i in range(len(masked)):
            masked[i] ^= mask_key[i % 4]
        return bytes(header) + bytes(masked)
    return bytes(header) + payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket."""
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data.extend(chunk)
    return bytes(data)


def _read_frame(sock: socket.socket):
    """Read one WebSocket frame. Returns (opcode, payload_bytes)."""
    hdr = _recv_exact(sock, 2)
    opcode = hdr[0] & 0x0F
    masked = bool(hdr[1] & 0x80)
    length = hdr[1] & 0x7F

    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]

    mask_key = _recv_exact(sock, 4) if masked else None
    payload = bytearray(_recv_exact(sock, length))
    if mask_key:
        for i in range(len(payload)):
            payload[i] ^= mask_key[i % 4]
    return opcode, bytes(payload)


def _ws_handshake(sock: socket.socket, host: str, path: str, port: int) -> None:
    """Perform the WebSocket opening handshake."""
    key = base64.b64encode(os.urandom(16)).decode()
    # Include port in Host header if non-standard
    if port in (80, 443):
        host_header = host
    else:
        host_header = f"{host}:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())

    # Read response headers (with a generous timeout for slow starts)
    old_timeout = sock.gettimeout()
    sock.settimeout(10.0)
    response = b""
    try:
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed during handshake")
            response += chunk
    finally:
        sock.settimeout(old_timeout)

    # Split headers from any trailing frame data
    header_end = response.index(b"\r\n\r\n")
    header_block = response[:header_end].decode("utf-8", errors="replace")

    status_line = header_block.split("\r\n")[0]
    if "101" not in status_line:
        raise ConnectionError(f"WebSocket handshake failed: {status_line}")


# ---------------------------------------------------------------------------
# WebSocket Client
# ---------------------------------------------------------------------------

class WebSocketClient:
    """Thread-safe WebSocket client for the Arkestrator protocol.

    Usage:
        client = WebSocketClient()
        client.on_message = my_handler   # called on main thread via poll()
        client.connect("ws://localhost:7800/ws", api_key="am_...")
        # In a timer: client.poll()
    """

    def __init__(self):
        self._sock: socket.socket | None = None
        self._url = ""
        self._api_key = ""
        self._machine_id = ""
        self._worker_name = ""
        self._project_path = ""
        self._project_name = ""
        self._program_version = ""
        self._full_url = ""
        self._last_shared_ws_url = ""
        self._last_good_api_key = ""
        self._is_connected = False
        self._should_reconnect = True
        self._reconnect_delay = RECONNECT_BASE_S
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._incoming: queue.Queue = queue.Queue()

        # Callbacks set by __init__.py, called on main thread from poll()
        self.on_message = None  # callable(msg_dict)
        self.on_connected = None  # callable()
        self.on_disconnected = None  # callable()
        self.on_error = None  # callable(error_message: str)

    # -- Public API ----------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._is_connected

    def connect(self, url: str, api_key: str = "",
                worker_name: str = "", machine_id: str = "", project_path: str = "",
                project_name: str = "", program_version: str = "") -> None:
        """Start connection (non-blocking). Spawns background thread."""
        # Guard: if already connected to the same server/auth endpoint, avoid
        # metadata-only reconnect churn.
        if self._is_connected and self._url == url and self._api_key == api_key:
            return

        self._url = url
        self._api_key = api_key
        self._machine_id = (machine_id or "").strip()
        self._worker_name = (worker_name or "").strip()
        self._project_path = project_path or ""
        self._project_name = project_name or ""
        self._program_version = program_version or ""
        self._should_reconnect = True
        self._reconnect_delay = RECONNECT_BASE_S

        # Track whether current URL is following shared-config wsUrl so live
        # config rotations can move this bridge between servers automatically.
        shared = self._read_shared_config()
        shared_machine = str((shared or {}).get("machineId", "")).strip()
        if shared_machine and not self._machine_id:
            self._machine_id = shared_machine
        shared_worker = str((shared or {}).get("workerName", "")).strip()
        if shared_worker and not self._worker_name:
            self._worker_name = shared_worker
        shared_ws = str((shared or {}).get("wsUrl", "")).strip()
        if shared_ws and url == shared_ws:
            self._last_shared_ws_url = shared_ws
        elif _is_loopback_ws_url(url):
            self._last_shared_ws_url = DEFAULT_SHARED_WS_URL
        else:
            self._last_shared_ws_url = ""

        # Build full URL with query params
        full_url = self._build_url(
            url, api_key, self._worker_name, self._machine_id, project_path,
            project_name, program_version,
        )

        # No-op if already connected with identical metadata.
        if self._is_connected and getattr(self, "_full_url", "") == full_url:
            return

        self._full_url = full_url

        # Stop old thread BEFORE clearing the event, so the new thread
        # starts with _stop_event = False (not True from the old stop signal).
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2)

        self._stop_event.clear()  # Clear AFTER old thread is stopped
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._should_reconnect = False
        self._stop_event.set()
        self._close_socket()

    def send_message(self, msg: dict) -> None:
        """Send a JSON message. Thread-safe."""
        if not self._is_connected or self._sock is None:
            return
        try:
            data = json.dumps(msg).encode("utf-8")
            frame = _make_frame(OPCODE_TEXT, data)
            with self._send_lock:
                self._sock.sendall(frame)
        except Exception:
            pass  # Connection will be detected as broken on next read

    # -- Context methods (push to server) ------------------------------------

    def send_context_item(self, item: dict) -> None:
        """Push a single context item to the server."""
        self.send_message({
            "type": "bridge_context_item_add",
            "id": str(uuid.uuid4()),
            "payload": {"item": item},
        })

    def send_context_clear(self) -> None:
        """Tell the server to clear the context bag for this bridge."""
        self.send_message({
            "type": "bridge_context_clear",
            "id": str(uuid.uuid4()),
            "payload": {},
        })

    def send_editor_context(self, editor_context: dict, files: list) -> None:
        """Push current editor context snapshot to the server."""
        self.send_message({
            "type": "bridge_editor_context",
            "id": str(uuid.uuid4()),
            "payload": {
                "editorContext": editor_context,
                "files": files,
            },
        })

    # -- Cross-bridge commands -----------------------------------------------

    def send_bridge_command(self, target: str, commands: list[dict],
                            target_type: str = "program",
                            correlation_id: str = "") -> None:
        """Send commands to another bridge via the server."""
        payload = {
            "target": target,
            "targetType": target_type,
            "commands": commands,
        }
        if correlation_id:
            payload["correlationId"] = correlation_id
        self.send_message({
            "type": "bridge_command_send",
            "id": str(uuid.uuid4()),
            "payload": payload,
        })

    def send_bridge_command_result(self, sender_id: str, correlation_id: str,
                                   success: bool, executed: int, failed: int,
                                   skipped: int, errors: list[str],
                                   outputs: list[dict] | None = None) -> None:
        """Send bridge command execution results back to server for routing."""
        payload = {
            "senderId": sender_id,
            "correlationId": correlation_id,
            "success": success,
            "executed": executed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }
        if outputs:
            payload["outputs"] = outputs
        self.send_message({
            "type": "bridge_command_result",
            "id": str(uuid.uuid4()),
            "payload": payload,
        })

    def poll(self) -> None:
        """Drain incoming queue -- call from main thread."""
        for _ in range(100):
            try:
                msg = self._incoming.get_nowait()
            except queue.Empty:
                break

            msg_type = msg.get("type", "")
            if msg_type == "_connected":
                if self.on_connected:
                    self.on_connected()
            elif msg_type == "_disconnected":
                if self.on_disconnected:
                    self.on_disconnected()
            elif msg_type == "_error":
                if self.on_error:
                    self.on_error(msg.get("message", "Unknown error"))
            else:
                if self.on_message:
                    self.on_message(msg)

    # -- Internal ------------------------------------------------------------

    def _build_url(self, url: str, api_key: str, worker_name: str,
                   machine_id: str, project_path: str, project_name: str,
                   program_version: str) -> str:
        sep = "&" if "?" in url else "?"
        params = {
            "type": "bridge",
            "program": "comfyui",
            "bridgeVersion": BRIDGE_VERSION,
            "protocolVersion": str(PROTOCOL_VERSION),
        }
        if api_key:
            params["key"] = api_key
        if project_name:
            params["name"] = project_name
        if program_version:
            params["programVersion"] = program_version
        if project_path:
            params["projectPath"] = project_path
        effective_worker = (worker_name or "").strip()
        if effective_worker:
            params["workerName"] = effective_worker
        effective_machine_id = (machine_id or "").strip()
        if effective_machine_id:
            params["machineId"] = effective_machine_id
        try:
            import getpass
            params["osUser"] = getpass.getuser()
        except Exception:
            pass
        return url + sep + urlencode(params)

    def _read_shared_config(self) -> dict | None:
        """Read ~/.arkestrator/config.json if present."""
        try:
            config_path = os.path.join(os.path.expanduser("~"), ".arkestrator", "config.json")
            if not os.path.exists(config_path):
                return None
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _connection_attempt_urls(self) -> list[tuple[str, str, str, str]]:
        """Return distinct reconnect attempts with current and last-known-good keys."""
        attempts: list[tuple[str, str, str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add_attempt(label: str, base_url: str, api_key: str) -> None:
            base = str(base_url or "").strip()
            key = str(api_key or "").strip()
            if not base:
                return
            identity = (base, key)
            if identity in seen:
                return
            seen.add(identity)
            attempts.append((
                label,
                base,
                key,
                self._build_url(
                    base,
                    key,
                    self._worker_name,
                    self._machine_id,
                    self._project_path,
                    self._project_name,
                    self._program_version,
                ),
            ))

        add_attempt("primary", self._url, self._api_key)
        shared = self._read_shared_config()
        remote_ws = str((shared or {}).get("remoteWsUrl", "")).strip()
        if _is_loopback_ws_url(self._url) and remote_ws and remote_ws != self._url:
            add_attempt(
                "remote fallback",
                remote_ws,
                self._api_key,
            )
        if self._last_good_api_key and self._last_good_api_key != self._api_key:
            add_attempt("last known good key", self._url, self._last_good_api_key)
            if _is_loopback_ws_url(self._url) and remote_ws and remote_ws != self._url:
                add_attempt("remote fallback (last good key)", remote_ws, self._last_good_api_key)
        return attempts

    def _refresh_connect_credentials(self) -> bool:
        """Refresh API key / ws URL from shared config.

        Returns True when connection params changed and reconnect should occur.
        """
        shared = self._read_shared_config()
        if not shared:
            return False

        changed = False

        shared_key = str(shared.get("apiKey", "")).strip()
        if shared_key and not _is_valid_api_key(shared_key):
            shared_key = ""
        if shared_key and shared_key != self._api_key and not self._is_connected:
            self._api_key = shared_key
            changed = True

        shared_machine = str(shared.get("machineId", "")).strip()
        if shared_machine and shared_machine != self._machine_id and not self._is_connected:
            self._machine_id = shared_machine
            changed = True

        shared_worker = str(shared.get("workerName", "")).strip()
        if shared_worker and shared_worker != self._worker_name and not self._is_connected:
            self._worker_name = shared_worker
            changed = True

        shared_ws = str(shared.get("wsUrl", "")).strip()
        follows_shared_url = (
            _is_loopback_ws_url(self._url)
            or (self._last_shared_ws_url and self._url == self._last_shared_ws_url)
        )
        if shared_ws and follows_shared_url:
            if self._url != shared_ws:
                self._url = shared_ws
                changed = True
            self._last_shared_ws_url = shared_ws

        if changed:
            self._full_url = self._build_url(
                self._url,
                self._api_key,
                self._worker_name,
                self._machine_id,
                self._project_path,
                self._project_name,
                self._program_version,
            )
        return changed

    def _run_loop(self) -> None:
        """Background thread: connect -> read -> reconnect loop."""
        self._connect_time: float = 0.0
        while not self._stop_event.is_set():
            try:
                self._refresh_connect_credentials()
                self._do_connect()
                self._read_loop()
            except ConnectionRefusedError:
                self._incoming.put({
                    "type": "_error",
                    "message": "Connection refused -- is the server running?",
                })
            except ConnectionError as e:
                msg = str(e)
                if "401" in msg:
                    self._incoming.put({
                        "type": "_error",
                        "message": "Authentication failed (401) -- check API key",
                    })
                else:
                    self._incoming.put({
                        "type": "_error",
                        "message": f"Connection error: {msg}",
                    })
            except OSError as e:
                self._incoming.put({
                    "type": "_error",
                    "message": f"Network error: {e}",
                })
            except Exception as e:
                self._incoming.put({
                    "type": "_error",
                    "message": f"Error: {e}",
                })
            finally:
                was_connected = self._is_connected
                self._is_connected = False
                self._close_socket()
                if was_connected:
                    self._incoming.put({"type": "_disconnected"})

            if not self._should_reconnect or self._stop_event.is_set():
                break

            # Only reset backoff if the connection was stable (stayed up >10s).
            # Short-lived connections keep the current delay to avoid rapid loops.
            uptime = time.monotonic() - self._connect_time if self._connect_time else 0.0
            if uptime > 10.0:
                self._reconnect_delay = RECONNECT_BASE_S

            print(f"[ArkestratorBridge] WS reconnecting in {self._reconnect_delay:.0f}s...")
            self._stop_event.wait(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, RECONNECT_MAX_S
            )

    def _do_connect(self) -> None:
        """Create socket, do TLS if wss://, perform WS handshake."""
        errors: list[str] = []

        for label, base_url, attempt_key, connect_url in self._connection_attempt_urls():
            parsed = urlparse(connect_url)
            use_ssl = parsed.scheme in ("wss", "https")
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if use_ssl else 80)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query

            # Retry handshake up to HANDSHAKE_RETRY_ATTEMPTS times to handle
            # transient failures (e.g., relay hiccups, DNS blips).
            last_exc: Exception | None = None
            for attempt in range(HANDSHAKE_RETRY_ATTEMPTS):
                raw_sock = None
                sock = None
                try:
                    raw_sock = socket.create_connection((host, port), timeout=10)
                    raw_sock.settimeout(1.0)  # Non-blocking reads with 1s timeout

                    if use_ssl:
                        ctx = ssl.create_default_context()
                        sock = ctx.wrap_socket(raw_sock, server_hostname=host)
                    else:
                        sock = raw_sock

                    _ws_handshake(sock, host, path, port)
                    self._sock = sock
                    self._is_connected = True
                    self._connect_time = time.monotonic()
                    self._api_key = attempt_key
                    if _is_valid_api_key(attempt_key):
                        self._last_good_api_key = attempt_key
                    self._full_url = self._build_url(
                        self._url,
                        self._api_key,
                        self._worker_name,
                        self._machine_id,
                        self._project_path,
                        self._project_name,
                        self._program_version,
                    )
                    if label != "primary":
                        print(
                            f"[ArkestratorBridge] WS relay unavailable; using {label} "
                            f"{parsed.hostname or host}:{port}"
                        )
                    if attempt > 0:
                        print(f"[ArkestratorBridge] WS connected on retry {attempt + 1}")
                    self._incoming.put({"type": "_connected"})
                    return
                except Exception as exc:
                    last_exc = exc
                    for candidate in (sock, raw_sock):
                        if candidate is None:
                            continue
                        try:
                            candidate.close()
                        except Exception:
                            pass
                    if attempt < HANDSHAKE_RETRY_ATTEMPTS - 1:
                        print(f"[ArkestratorBridge] WS handshake attempt {attempt + 1} failed ({exc}), retrying...")
                        time.sleep(0.5)  # Brief pause before retry

            errors.append(f"{label}: {last_exc}")

        raise ConnectionError("; ".join(errors) if errors else "Failed to connect")

    def _read_loop(self) -> None:
        """Read frames until disconnected or stopped."""
        last_frame_time = time.monotonic()
        while not self._stop_event.is_set() and self._is_connected:
            try:
                opcode, payload = _read_frame(self._sock)
            except socket.timeout:
                if self._refresh_connect_credentials():
                    self._incoming.put({
                        "type": "_error",
                        "message": "Detected updated shared bridge credentials -- reconnecting",
                    })
                    break
                # Check if connection is stale (no frames for too long)
                stale_elapsed = time.monotonic() - last_frame_time
                if stale_elapsed > STALE_TIMEOUT_S:
                    print(f"[ArkestratorBridge] WS disconnect: stale (no data received in {stale_elapsed:.0f}s)")
                    self._incoming.put({
                        "type": "_error",
                        "message": f"Connection stale (no data received in {stale_elapsed:.0f}s), reconnecting",
                    })
                    break
                continue
            except (ConnectionError, OSError):
                break

            last_frame_time = time.monotonic()

            if opcode == OPCODE_TEXT:
                try:
                    msg = json.loads(payload.decode("utf-8"))
                    self._incoming.put(msg)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            elif opcode == OPCODE_PING:
                # Respond with pong
                try:
                    frame = _make_frame(OPCODE_PONG, payload)
                    with self._send_lock:
                        self._sock.sendall(frame)
                except Exception:
                    break
            elif opcode == OPCODE_CLOSE:
                # Send close back
                try:
                    frame = _make_frame(OPCODE_CLOSE, b"")
                    with self._send_lock:
                        self._sock.sendall(frame)
                except Exception:
                    pass
                break

    def _close_socket(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
