"""Arkestrator Bridge early startup hook for Houdini 21 / Python 3.11.

Only ensures the bridge package is on sys.path. Actual registration and
connection happen later via uiready.py when the Houdini UI is ready.
"""

import os
import sys

_BRIDGE_DIR_NAME = "arkestrator_bridge"


def _ensure_bridge_on_sys_path():
    file_path = globals().get("__file__")
    if not file_path:
        return
    current = os.path.abspath(file_path)
    for _ in range(8):
        current = os.path.dirname(current)
        if os.path.basename(current) == _BRIDGE_DIR_NAME:
            packages_dir = os.path.dirname(current)
            if packages_dir not in sys.path:
                sys.path.insert(0, packages_dir)
            return


_ensure_bridge_on_sys_path()
