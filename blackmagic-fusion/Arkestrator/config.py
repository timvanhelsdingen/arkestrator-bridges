"""
Arkestrator bridge config — reads ~/.arkestrator/config.json
"""

import json
import os
import platform
import uuid
import hashlib
import getpass

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".arkestrator", "config.json")

# Bridge identity
BRIDGE_VERSION = "0.1.57"
PROGRAM = "fusion"


def read_config():
    """Read connection config from ~/.arkestrator/config.json."""
    if not os.path.isfile(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def get_machine_id():
    """Derive a stable machine ID from hostname + MAC fallback."""
    try:
        node = uuid.getnode()
        hostname = platform.node()
        raw = f"{hostname}-{node}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))
    except Exception:
        return str(uuid.uuid4())


def get_os_user():
    """Get current OS username."""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def get_worker_name():
    """Get worker/machine name."""
    return platform.node() or "unknown"


def get_ws_url(cfg):
    """Extract WebSocket URL from config, with fallback."""
    if not cfg:
        return "ws://localhost:7800/ws"
    return cfg.get("wsUrl") or cfg.get("serverUrl", "http://localhost:7800").replace("http", "ws") + "/ws"


def get_api_key(cfg):
    """Extract API key from config."""
    if not cfg:
        return None
    return cfg.get("apiKey")


def config_file_mtime():
    """Return mtime of config file for change detection."""
    try:
        return os.path.getmtime(CONFIG_PATH)
    except OSError:
        return 0
