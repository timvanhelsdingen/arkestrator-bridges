"""
Arkestrator — Show Panel action (called from the Arkestrator menu).
Opens the UI panel, creating the bridge if needed.
"""
import importlib
import importlib.util
import os
import sys


def _resolve_arkestrator_dir():
    """Resolve the Arkestrator package directory via Fusion API or __file__."""
    if "__file__" in dir() or "__file__" in globals():
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except NameError:
            pass
    for _g in ("fusion", "fu", "app", "comp"):
        _obj = globals().get(_g)
        if _obj is not None and hasattr(_obj, "MapPath"):
            try:
                mapped = str(_obj.MapPath("Config:/Arkestrator/") or "")
                if mapped and os.path.isdir(mapped):
                    return mapped.rstrip("/\\")
            except Exception:
                pass
    return None


_this_dir = _resolve_arkestrator_dir()
if _this_dir is None:
    raise RuntimeError("[Arkestrator] Cannot resolve Arkestrator directory")
_parent_dir = os.path.dirname(_this_dir)

if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

if "fusion" not in sys.modules:
    _init_path = os.path.join(_this_dir, "__init__.py")
    if os.path.isfile(_init_path):
        _spec = importlib.util.spec_from_file_location(
            "fusion", _init_path, submodule_search_locations=[_this_dir])
        _pkg = importlib.util.module_from_spec(_spec)
        sys.modules["fusion"] = _pkg
        _spec.loader.exec_module(_pkg)

_bridge_path = os.path.join(_this_dir, "arkestrator_bridge.py")
_fqn = "fusion.arkestrator_bridge"
if _fqn not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_fqn, _bridge_path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_fqn] = _mod
    _spec.loader.exec_module(_mod)

from fusion.arkestrator_bridge import get_or_create_bridge, get_fusion_app, create_ui_panel

fusion_app = get_fusion_app()
if fusion_app is None:
    print("[Arkestrator] ERROR: Could not find Fusion application.")
else:
    bridge = get_or_create_bridge(fusion_app)
    create_ui_panel(bridge)
