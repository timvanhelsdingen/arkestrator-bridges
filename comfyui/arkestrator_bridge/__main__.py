"""CLI entry point for the ComfyUI bridge.

Usage:
    python -m arkestrator_bridge
    python -m arkestrator_bridge --comfyui-url http://localhost:8188
    python -m arkestrator_bridge --server-url ws://myserver:7800/ws --api-key am_xxx
"""

import argparse
import signal
import sys

from . import run, disconnect


def main():
    parser = argparse.ArgumentParser(
        prog="arkestrator_bridge",
        description="ComfyUI bridge for Arkestrator — connects ComfyUI to the Arkestrator hub",
    )
    parser.add_argument(
        "--server-url",
        default="",
        help="Arkestrator WebSocket URL (default: auto-discover from ~/.arkestrator/config.json)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Arkestrator API key (default: auto-discover from ~/.arkestrator/config.json)",
    )
    parser.add_argument(
        "--comfyui-url",
        default="",
        help="ComfyUI HTTP API URL (default: http://127.0.0.1:8188)",
    )

    args = parser.parse_args()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n[ArkestratorBridge] Received signal, shutting down...")
        disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    run(
        url=args.server_url,
        api_key=args.api_key,
        comfyui_url=args.comfyui_url,
    )


if __name__ == "__main__":
    main()

