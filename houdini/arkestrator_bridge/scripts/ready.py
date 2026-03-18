"""Arkestrator Bridge UI-ready startup hook.

Houdini GUI sessions can load package scripts at slightly different stages than
headless/hython sessions. Running register() again here is safe and makes the
bridge startup resilient in the interactive app path.
"""

try:
    import arkestrator_bridge

    arkestrator_bridge.register()
except Exception as exc:
    print(f"[ArkestratorBridge] ready.py startup skipped: {exc}")
