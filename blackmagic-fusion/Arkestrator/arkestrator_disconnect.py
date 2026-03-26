"""
Arkestrator — Disconnect action (called from the Arkestrator menu).
Sends a disconnect command to the running bridge process via file IPC.
"""

import json
import os
import tempfile

_CMD_PATH = os.path.join(tempfile.gettempdir(), "arkestrator_fusion_cmd.json")

try:
    with open(_CMD_PATH, "w") as f:
        json.dump({"action": "disconnect"}, f)
    print("[Arkestrator] Disconnect command sent")
except Exception as exc:
    print(f"[Arkestrator] Failed to send disconnect: {exc}")
