"""Arkestrator Bridge UI-ready startup hook for Houdini 21 / Python 3.11."""

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


def _bootstrap_bridge():
    _ensure_bridge_on_sys_path()
    from arkestrator_bridge.startup_bootstrap import schedule_bridge_bootstrap

    schedule_bridge_bootstrap()


try:
    _bootstrap_bridge()
    try:
        from PySide6 import QtCore  # type: ignore
    except Exception:
        try:
            from PySide2 import QtCore  # type: ignore
        except Exception:
            QtCore = None  # type: ignore
    if QtCore is not None:
        QtCore.QTimer.singleShot(1500, _bootstrap_bridge)
except Exception as exc:
    print(f"[ArkestratorBridge] python3.11libs/uiready.py skipped: {exc}")
