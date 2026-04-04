# ComfyUI Bridge - Module Documentation

## Overview
Standalone Python bridge connecting a running ComfyUI instance to the Arkestrator server. Unlike Blender/Houdini bridges that run inside a DCC app, this is a separate process that bridges the Arkestrator protocol to ComfyUI's HTTP API.

## Directory Structure
```
bridges/comfyui/
└── arkestrator_bridge/
    ├── __init__.py          # Entry point, message dispatch, public API
    ├── __main__.py          # CLI entry: python -m arkestrator_bridge
    ├── ws_client.py         # Stdlib WebSocket client (program="comfyui")
    ├── file_applier.py      # File change applier with path traversal protection
    ├── command_executor.py  # Execute workflows or Python commands
    ├── comfyui_client.py    # HTTP client for ComfyUI API
    └── context.py           # Editor context builder (node types, system stats)
```

## Key Components

### ws_client.py
Standard Arkestrator WebSocket client (stdlib only). Identical to Houdini bridge except `program="comfyui"`. `send_bridge_command_result()` accepts optional `stdout` and `stderr` parameters; `bridge_command_result` messages include these fields when non-empty. Stale timeout: 180s (`STALE_TIMEOUT_S`). Handshake retry: up to 2 attempts (`HANDSHAKE_RETRY_ATTEMPTS`=2) with 0.5s delay. Reconnect lifecycle now matches Blender/Houdini hardening: old thread is stopped before clearing the stop-event, preventing reconnect dead-threads and stale bridge metadata. It now also hot-refreshes `~/.arkestrator/config.json` during reconnect/read-loop polling, follows client-owned shared `workerName`/`machineId`, sends `machineId` on the WebSocket query string, auto-reconnects when shared `apiKey`, followed `wsUrl`, or shared identity changes, and falls back from a dead desktop relay URL to shared `remoteWsUrl` during reconnect.

### comfyui_client.py
HTTP client wrapping ComfyUI's REST API:
- `get_system_stats()` - VRAM usage, device info
- `get_object_info()` - available node types
- `get_queue()` - running/pending workflows
- `submit_workflow(workflow)` - queue a workflow, returns prompt_id
- `poll_result(prompt_id)` - poll until completion
- `get_image(filename)` - fetch generated image bytes
- `upload_image(filepath)` - upload input images

### command_executor.py
Handles two command languages:
- `"workflow"` / `"comfyui"` - submits workflow JSON to ComfyUI, polls for results, collects output artifacts (`images`, `videos`, `gifs`, `audio`, `files`) and infers stable `kind` values from filename extensions
- `"python"` / `"py"` - executes Python code via `exec()` (ComfyUI client available as `comfyui` in scope)
- Returns `{"executed": int, "failed": int, "skipped": int, "errors": list[str], "stdout": str, "stderr": str}` -- `stdout` and `stderr` capture the respective output streams during command execution

Bridge command results now send transport-safe artifact payloads:
- Always includes metadata (`filename`, `subfolder`, `type`, `sizeBytes`, `kind`, optional `mimeType`)
- Includes inline `base64` for artifacts up to `ARKESTRATOR_MAX_INLINE_OUTPUT_BYTES` (default 8 MiB) so cross-machine bridge workflows can relay generated files
- Omits base64 for oversized artifacts and sets `omittedReason` to keep WS traffic bounded

### context.py
Builds editor context from ComfyUI state:
- Available node categories + counts (cached, refreshed every 30s)
- System stats (VRAM, GPU info)
- Queue state (running/pending counts)

## Usage

### CLI (standalone)
```bash
python -m arkestrator_bridge
python -m arkestrator_bridge --comfyui-url http://localhost:8188
python -m arkestrator_bridge --server-url ws://myserver:7800/ws --api-key am_xxx
```

`--server-url` now accepts `ws://`, `wss://`, `http://`, `https://`, or bare `host:port`; it is normalized to a WebSocket URL and defaults to appending `/ws` when missing.

### macOS launcher
Repo helper launcher:
```bash
pnpm comfyui:mac
```

Finder-friendly shortcut:
```bash
scripts/start-comfyui-bridge-mac.command
```

Standalone app builder:
```bash
bash scripts/build-comfyui-launcher-app-mac.sh
```

Built app bundle:
```bash
tools/mac/Arkestrator ComfyUI Launcher.app
```

The macOS launcher opens Terminal sessions for both ComfyUI and the bridge. It resolves the ComfyUI checkout from `COMFYUI_DIR`, shared config (`~/.arkestrator/config.json` keys `comfyuiAppPath` / `comfyuiPath` / `comfyuiDir`), then common folders including `~/AI/ComfyUI` and `~/.arkestrator/comfyui/ComfyUI`.

### From Python
```python
import arkestrator_bridge
arkestrator_bridge.connect(comfyui_url="http://localhost:8188")

# Or use the public API
bridge = arkestrator_bridge.get_bridge()
if bridge:
    bridge.execute_workflow({"3": {"class_type": "KSampler", ...}})
```

## Skills
| Slug | Title | Description |
|------|-------|-------------|
| workflow-patterns | Workflow Patterns | Node creation, txt2img, PBR textures, upscale, inpaint, ControlNet workflow patterns |
| verification | Verification & Quality Assessment | Python patterns for checking workflow completion, outputs, models |
| api-patterns | Api Patterns | Workflow JSON structure, common nodes, model/delivery/scope policies |
| model-selection | Model Selection & Task Intelligence | Hardware-aware model selection, task classification (textures/photos/art/video), model search & auto-download |

The **model-selection** skill teaches the coordinator to:
- Check GPU VRAM before selecting models
- Classify requests into content types (PBR textures, photorealistic, concept art, video, upscale, inpaint)
- Understand that different content types need fundamentally different models (e.g. texture models for PBR, not photorealistic models)
- Search CivitAI/HuggingFace for task-specific models and download them
- Install custom nodes when needed

## Config
Auto-discovers from `~/.arkestrator/config.json`. In addition to `apiKey`/`wsUrl`, the bridge now also follows shared `workerName` and `machineId`. Optional `comfyuiUrl` field for ComfyUI address (defaults to `http://127.0.0.1:8188`).
