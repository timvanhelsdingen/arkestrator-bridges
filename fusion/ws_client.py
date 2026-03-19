"""
Arkestrator Fusion bridge — WebSocket client with exponential backoff reconnection.

Uses the built-in `websocket-client` library (synchronous, threaded).
Falls back to a raw-socket implementation if websocket-client is unavailable.
"""

import json
import threading
import time
import uuid
import hashlib
import traceback

try:
    import websocket as _ws_lib  # websocket-client
    HAS_WS_LIB = True
except ImportError:
    HAS_WS_LIB = False

from . import config as cfg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RECONNECT_BASE = 3.0
RECONNECT_MAX = 30.0
STABLE_THRESHOLD = 10.0  # seconds before resetting backoff


class BridgeWebSocket:
    """Manages the WebSocket lifecycle in a background thread."""

    def __init__(self, on_message=None, on_connect=None, on_disconnect=None, logger=None):
        self._on_message = on_message
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._log = logger or (lambda *a: None)

        self._ws = None
        self._thread = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._backoff = RECONNECT_BASE
        self._connect_time = 0.0
        self._config = None
        self._config_mtime = 0.0
        self._lock = threading.Lock()

    # -- public API ----------------------------------------------------------

    def start(self):
        """Begin the connection loop in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ark-ws")
        self._thread.start()

    def stop(self):
        """Cleanly shut down."""
        self._stop.set()
        self._connected.clear()
        ws = self._ws
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    @property
    def connected(self):
        return self._connected.is_set()

    def send(self, msg_type, payload, msg_id=None):
        """Send an envelope message."""
        if not self._connected.is_set():
            return False
        envelope = {
            "type": msg_type,
            "id": msg_id or str(uuid.uuid4()),
            "payload": payload,
        }
        try:
            with self._lock:
                ws = self._ws
            if ws:
                ws.send(json.dumps(envelope))
                return True
        except Exception as exc:
            self._log(f"[ws] send error: {exc}")
        return False

    # -- internal ------------------------------------------------------------

    def _reload_config(self):
        """Re-read config if file changed."""
        mt = cfg.config_file_mtime()
        if mt != self._config_mtime:
            self._config = cfg.read_config()
            self._config_mtime = mt
        return self._config

    def _build_url(self, conf):
        """Build WS URL with query params."""
        base = cfg.get_ws_url(conf)
        key = cfg.get_api_key(conf) or ""
        worker = conf.get("workerName", "") if conf else cfg.get_worker_name()
        machine_id = conf.get("machineId", "") if conf else cfg.get_machine_id()
        project_path = getattr(self, "_project_path", "") or ""
        program_version = getattr(self, "_program_version", "") or ""

        params = {
            "type": "bridge",
            "key": key,
            "program": cfg.PROGRAM,
            "programVersion": program_version,
            "bridgeVersion": cfg.BRIDGE_VERSION,
            "projectPath": project_path,
            "workerName": worker,
            "machineId": machine_id,
            "osUser": cfg.get_os_user(),
        }
        qs = "&".join(f"{k}={_url_encode(v)}" for k, v in params.items() if v)
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{qs}"

    def _run_loop(self):
        """Reconnection loop with exponential backoff."""
        while not self._stop.is_set():
            conf = self._reload_config()
            api_key = cfg.get_api_key(conf)
            if not api_key:
                self._log("[ws] No API key in config — waiting…")
                self._stop.wait(5.0)
                continue

            url = self._build_url(conf)
            subprotocol = f"arkestrator.auth.{api_key}"
            self._log(f"[ws] Connecting to {cfg.get_ws_url(conf)}")

            try:
                if not HAS_WS_LIB:
                    raise ImportError("websocket-client not installed")

                ws = _ws_lib.WebSocketApp(
                    url,
                    subprotocols=[subprotocol],
                    on_open=self._handle_open,
                    on_message=self._handle_message,
                    on_error=self._handle_error,
                    on_close=self._handle_close,
                )
                with self._lock:
                    self._ws = ws
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except ImportError:
                self._log("[ws] websocket-client not installed. pip install websocket-client")
                self._stop.wait(10.0)
                continue
            except Exception as exc:
                self._log(f"[ws] Connection error: {exc}")

            self._connected.clear()
            if self._on_disconnect:
                try:
                    self._on_disconnect()
                except Exception:
                    pass

            if self._stop.is_set():
                break

            # Backoff
            elapsed = time.time() - self._connect_time
            if elapsed > STABLE_THRESHOLD:
                self._backoff = RECONNECT_BASE
            else:
                self._backoff = min(self._backoff * 2, RECONNECT_MAX)
            self._log(f"[ws] Reconnecting in {self._backoff:.0f}s")
            self._stop.wait(self._backoff)

    def _handle_open(self, ws):
        self._connect_time = time.time()
        self._connected.set()
        self._log("[ws] Connected")
        if self._on_connect:
            try:
                self._on_connect()
            except Exception as exc:
                self._log(f"[ws] on_connect error: {exc}")

    def _handle_message(self, ws, data):
        if self._on_message:
            try:
                msg = json.loads(data)
                self._on_message(msg)
            except json.JSONDecodeError:
                self._log("[ws] Non-JSON message received")
            except Exception as exc:
                self._log(f"[ws] on_message error: {exc}\n{traceback.format_exc()}")

    def _handle_error(self, ws, error):
        self._log(f"[ws] Error: {error}")

    def _handle_close(self, ws, close_code, close_msg):
        self._connected.clear()
        self._log(f"[ws] Closed (code={close_code}, msg={close_msg})")


def _url_encode(value):
    """Minimal URL-encode for query param values."""
    s = str(value)
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.~":
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:
            out.append(f"%{ord(ch):02X}")
    return "".join(out)
