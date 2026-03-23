"""
Arkestrator — Connect action (called from the Arkestrator menu).
Starts the bridge in headless mode if not already running.
"""
import importlib
import importlib.util
import os
import sys

# Bootstrap the fusion package from this directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
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

# Import bridge module (it handles its own submodule registration)
_bridge_path = os.path.join(_this_dir, "arkestrator_bridge.py")
_fqn = "fusion.arkestrator_bridge"
if _fqn not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_fqn, _bridge_path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_fqn] = _mod
    _spec.loader.exec_module(_mod)

from fusion.arkestrator_bridge import get_or_create_bridge, get_fusion_app

fusion_app = get_fusion_app()
if fusion_app is None:
    print("[Arkestrator] ERROR: Could not find Fusion application.")
else:
    bridge = get_or_create_bridge(fusion_app)
    if bridge.connected:
        print("[Arkestrator] Already connected")
    else:
        print("[Arkestrator] Connecting...")
        bridge.connect()
