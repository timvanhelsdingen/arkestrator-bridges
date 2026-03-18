"""Helpers for deferring bridge startup onto Houdini's live UI session."""

from __future__ import annotations

import json
from pathlib import Path

import hou

_CALLBACK_ATTR = "_arkestrator_bridge_startup_callback"
_PENDING_ATTR = "_arkestrator_bridge_startup_pending"
_RETRY_CALLBACK_ATTR = "_arkestrator_bridge_startup_retry_callback"
_RETRY_PENDING_ATTR = "_arkestrator_bridge_startup_retry_pending"


def _read_shared_config() -> dict | None:
    try:
        config_path = Path.home() / ".arkestrator" / "config.json"
        if not config_path.exists():
            return None
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _log(logger, message: str) -> None:
    if logger is None:
        return
    try:
        logger(message)
    except Exception:
        pass


def _bridge_connected() -> bool:
    try:
        import arkestrator_bridge

        bridge = arkestrator_bridge.get_bridge()
        if bridge is not None and getattr(bridge, "connected", False):
            return True
        client = getattr(arkestrator_bridge, "_ws_client", None)
        return bool(client and client.connected)
    except Exception:
        return False


def bootstrap_bridge(logger=None) -> None:
    import arkestrator_bridge

    arkestrator_bridge.register()

    shared = _read_shared_config()
    if not shared:
        _log(logger, "startup_bootstrap: no shared config")
        return

    api_key = str(shared.get("apiKey", "")).strip()
    if not api_key:
        _log(logger, "startup_bootstrap: shared config missing apiKey")
        return

    ws_url = str(shared.get("wsUrl", "")).strip() or "ws://localhost:7800/ws"
    arkestrator_bridge.connect(url=ws_url, api_key=api_key)
    _log(logger, f"startup_bootstrap: connect requested {ws_url}")


def schedule_bridge_retry(logger=None, delay_ticks: int = 40) -> None:
    if getattr(hou, _RETRY_PENDING_ATTR, False):
        _log(logger, "startup_bootstrap: retry already scheduled")
        return

    ticks_remaining = max(int(delay_ticks), 0)

    def _callback():
        nonlocal ticks_remaining

        if ticks_remaining > 0:
            ticks_remaining -= 1
            return

        try:
            if _bridge_connected():
                _log(logger, "startup_bootstrap: retry skipped, already connected")
                return

            import arkestrator_bridge

            _log(logger, "startup_bootstrap: retry forcing reconnect")
            try:
                arkestrator_bridge.disconnect()
            except Exception:
                pass
            bootstrap_bridge(logger=logger)
        except Exception as exc:
            _log(logger, f"startup_bootstrap: retry error: {exc!r}")
            print(f"[ArkestratorBridge] deferred retry failed: {exc}")
        finally:
            try:
                hou.ui.removeEventLoopCallback(_callback)
            except Exception:
                pass
            setattr(hou, _RETRY_PENDING_ATTR, False)
            if getattr(hou, _RETRY_CALLBACK_ATTR, None) is _callback:
                try:
                    delattr(hou, _RETRY_CALLBACK_ATTR)
                except Exception:
                    pass

    setattr(hou, _RETRY_PENDING_ATTR, True)
    setattr(hou, _RETRY_CALLBACK_ATTR, _callback)
    hou.ui.addEventLoopCallback(_callback)
    _log(logger, f"startup_bootstrap: retry scheduled delay_ticks={ticks_remaining}")


def schedule_bridge_bootstrap(logger=None, delay_ticks: int = 2) -> None:
    if getattr(hou, _PENDING_ATTR, False):
        _log(logger, "startup_bootstrap: already scheduled")
        return

    ticks_remaining = max(int(delay_ticks), 0)

    def _callback():
        nonlocal ticks_remaining

        if ticks_remaining > 0:
            ticks_remaining -= 1
            return

        try:
            bootstrap_bridge(logger=logger)
            schedule_bridge_retry(logger=logger)
        except Exception as exc:
            _log(logger, f"startup_bootstrap: error: {exc!r}")
            print(f"[ArkestratorBridge] deferred bootstrap failed: {exc}")
        finally:
            try:
                hou.ui.removeEventLoopCallback(_callback)
            except Exception:
                pass
            setattr(hou, _PENDING_ATTR, False)
            if getattr(hou, _CALLBACK_ATTR, None) is _callback:
                try:
                    delattr(hou, _CALLBACK_ATTR)
                except Exception:
                    pass

    setattr(hou, _PENDING_ATTR, True)
    setattr(hou, _CALLBACK_ATTR, _callback)
    hou.ui.addEventLoopCallback(_callback)
    _log(logger, f"startup_bootstrap: scheduled delay_ticks={ticks_remaining}")
