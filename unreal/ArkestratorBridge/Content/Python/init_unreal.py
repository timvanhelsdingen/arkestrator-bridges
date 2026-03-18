"""Arkestrator Bridge auto-startup for Unreal Engine 5.

PythonScriptPlugin auto-executes this file because it resides in a
Content/Python/ directory that is on the Python path.
"""

import unreal

_init_done = False
_tick_count = 0
_startup_handle = None


def _deferred_init():
    """One-shot init: import and register the bridge after editor is ready."""
    global _init_done
    if _init_done:
        return
    _init_done = True

    try:
        import arkestrator_bridge
        arkestrator_bridge.register()
        unreal.log("[ArkestratorBridge] Bridge registered successfully")
    except Exception as e:
        unreal.log_error(f"[ArkestratorBridge] Failed to register bridge: {e}")
        import traceback
        unreal.log_error(traceback.format_exc())


def _startup_tick(delta_time):
    """Wait ~1 second (60 ticks at 60Hz) then register the bridge."""
    global _tick_count, _startup_handle
    _tick_count += 1
    # Wait for editor to finish loading before registering
    if _tick_count >= 60:
        _deferred_init()
        if _startup_handle is not None:
            unreal.unregister_slate_post_tick_callback(_startup_handle)
            _startup_handle = None


_startup_handle = unreal.register_slate_post_tick_callback(_startup_tick)
