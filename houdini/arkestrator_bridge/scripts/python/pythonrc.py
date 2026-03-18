"""Arkestrator Bridge auto-startup script.

This file is auto-executed by Houdini when the bridge package is installed,
because the package JSON adds the bridge directory to Houdini's package path.

We add the packages directory to sys.path here instead of using PYTHONPATH
in the package JSON, because Houdini's package system uses ';' as a path
separator which only works on Windows. This approach works cross-platform.
"""

import os
import sys

_BRIDGE_DIR_NAME = "arkestrator_bridge"


def _houdini_version_string():
    try:
        import hou  # type: ignore

        version = hou.applicationVersion()
        if isinstance(version, (tuple, list)) and len(version) >= 2:
            return f"{version[0]}.{version[1]}"
    except Exception:
        pass
    return ""


def _candidate_user_pref_dirs():
    seen = set()
    candidates = []

    def _add(path):
        normalized = os.path.abspath(path).strip() if path else ""
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    _add(os.environ.get("HOUDINI_USER_PREF_DIR", ""))

    try:
        import hou  # type: ignore

        _add(hou.homeHoudiniDirectory())
    except Exception:
        pass

    version = _houdini_version_string()
    if version:
        home = os.path.expanduser("~")
        _add(os.path.join(home, f"houdini{version}"))
        _add(os.path.join(home, "Library", "Preferences", "houdini", version))
        _add(os.path.join(home, "Documents", f"houdini{version}"))

    return candidates


def _resolve_packages_dir():
    # Preferred: derive by walking up from pythonrc.py until we hit the
    # arkestrator bridge package directory.
    file_path = globals().get("__file__")
    if file_path:
        current = os.path.abspath(file_path)
        for _ in range(8):
            current = os.path.dirname(current)
            if os.path.basename(current) == _BRIDGE_DIR_NAME:
                return os.path.dirname(current)

    # Houdini can execute pythonrc without defining __file__. Fallback to
    # package paths from HOUDINI_PATH / user pref dirs.
    houdini_path = os.environ.get("HOUDINI_PATH", "")
    if houdini_path:
        for sep in (";", os.pathsep):
            for raw_part in houdini_path.split(sep):
                part = raw_part.strip().strip('"')
                if not part or part == "&":
                    continue
                if os.path.basename(part) == _BRIDGE_DIR_NAME:
                    return os.path.dirname(part)

    for user_pref in _candidate_user_pref_dirs():
        if not user_pref:
            continue
        candidate = os.path.join(user_pref, "packages", _BRIDGE_DIR_NAME)
        if os.path.isdir(candidate):
            return os.path.dirname(candidate)

    return None


_packages_dir = _resolve_packages_dir()
if _packages_dir and _packages_dir not in sys.path:
    sys.path.insert(0, _packages_dir)

try:
    import arkestrator_bridge
    arkestrator_bridge.register()
except Exception as exc:
    print(f"[ArkestratorBridge] pythonrc startup skipped: {exc}")
