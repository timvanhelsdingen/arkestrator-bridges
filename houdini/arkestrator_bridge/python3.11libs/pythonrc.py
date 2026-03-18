"""Arkestrator Bridge early startup hook for Houdini 21 / Python 3.11."""

import os
import sys


def _ensure_bridge_on_sys_path():
    file_path = globals().get("__file__")
    if not file_path:
        return
    current = os.path.abspath(file_path)
    for _ in range(8):
        current = os.path.dirname(current)
        if os.path.basename(current) == "arkestrator_bridge":
            packages_dir = os.path.dirname(current)
            if packages_dir not in sys.path:
                sys.path.insert(0, packages_dir)
            return


try:
    _ensure_bridge_on_sys_path()
    import arkestrator_bridge

    arkestrator_bridge.register()
except Exception as exc:
    print(f"[ArkestratorBridge] python3.11libs/pythonrc.py skipped: {exc}")
