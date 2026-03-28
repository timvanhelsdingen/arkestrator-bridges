# ComfyUI Bridge

| | |
|---|---|
| **Application** | ComfyUI |
| **Language** | Python, Workflow JSON |
| **Install Type** | Standalone process |
| **Status** | Stable |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The ComfyUI bridge is a standalone Python process that runs alongside your ComfyUI instance and connects it to the Arkestrator server. It provides:

- **Context capture** -- pushes available models, custom nodes, workflow history, and runtime status every ~3 seconds (hash-deduplicated)
- **Command execution** -- submits workflow JSON or runs Python scripts via `execute_command(target="comfyui", language="workflow"|"comfyui"|"python", script="...")`
- **Workflow submission** -- agents build workflow JSON, submit it, poll for completion, and collect output artifacts
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine without syncing
- **Cross-machine delivery** -- output artifacts can be transferred to other connected workers via a two-step generate-then-deliver pattern

Use `workflow` or `comfyui` language for generation tasks so output artifacts are returned for downstream transfer.

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the ComfyUI bridge
4. Point to your ComfyUI installation

### Manual Installation

Download the latest `arkestrator-bridge-comfyui-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and extract `arkestrator_bridge/` alongside your ComfyUI instance.

Run the bridge as a standalone process:

```bash
python -m arkestrator_bridge
```

The bridge connects to your local ComfyUI API and to the Arkestrator server simultaneously.

## Skills

The ComfyUI bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Workflow Patterns | txt2img, img2img, upscale, inpaint, ControlNet, video generation workflows |
| API Patterns | ComfyUI API usage, prompt submission, history polling |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with ComfyUI:

- Agents build workflow JSON, submit it via the API, and poll for completion
- Models already installed in the environment are preferred; missing models are reported clearly
- Generation tasks (image, video, upscale, inpaint) are treated as GPU-heavy -- agents avoid overlapping with other heavy GPU tasks
- Cross-machine delivery uses a two-step pattern: generate on the ComfyUI worker, then transfer to the destination worker via a second bridge command
- Agents verify output existence, file size, and format before reporting done

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- Unlike other bridges, ComfyUI runs as a separate process (not a plugin inside the application)
- The bridge communicates with ComfyUI via its HTTP/WebSocket API
- Filesystem paths are machine-local -- a path on the ComfyUI worker does not exist on other workers
