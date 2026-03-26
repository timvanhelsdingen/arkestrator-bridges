"""
Arkestrator — Connect action (called from the Arkestrator menu).
Starts the bridge in headless mode if not already running.
"""
import importlib
import importlib.util
import os
import sys


def _resolve_arkestrator_dir():
    """Resolve the Arkestrator package directory via Fusion API or __file__."""
    # Try __file__ first (works when run directly, not via comp:RunScript)
    if "__file__" in dir() or "__file__" in globals():
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except NameError:
            pass
    # Use Fusion's MapPath API (always works inside Fusion)
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

# Import bridge module (it handles its own submodule registration)
_bridge_path = os.path.join(_this_dir, "arkestrator_bridge.py")
_fqn = "fusion.arkestrator_bridge"
if _fqn not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_fqn, _bridge_path)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_fqn] = _mod
    _spec.loader.exec_module(_mod)

from fusion.arkestrator_bridge import get_or_create_bridge, get_fusion_app, _run_headless
from fusion import config as _cfg

fusion_app = get_fusion_app()
if fusion_app is None:
    print("[Arkestrator] ERROR: Could not find Fusion application.")
else:
    bridge = get_or_create_bridge(fusion_app)
    if bridge.connected:
        print("[Arkestrator] Already connected")
    else:
        _conf = _cfg.read_config()
        _key = _cfg.get_api_key(_conf)
        _url = _cfg.get_ws_url(_conf)
        print(f"[Arkestrator] Config: url={_url}, key={'yes' if _key else 'MISSING'}")
        if not _key:
            print("[Arkestrator] ERROR: No API key configured")
        else:
            try:
                import websocket
                print(f"[Arkestrator] websocket-client: {websocket.__version__}")
            except ImportError:
                print("[Arkestrator] ERROR: websocket-client not installed!")
            print("[Arkestrator] Connecting...")
            bridge.connect()
            # Give the daemon thread a moment to attempt connection
            import time
            time.sleep(2)
            if bridge.connected:
                print("[Arkestrator] Connected!")
            else:
                print("[Arkestrator] WS not connected yet after 2s")
                # Check if thread is alive
                ws_thread = bridge._ws._thread
                print(f"[Arkestrator] WS thread alive: {ws_thread.is_alive() if ws_thread else 'no thread'}")
            # Keep this process alive with Fusion's event loop
            _run_headless(bridge, fusion_app)
