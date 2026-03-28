# Arkestrator Bridges

Bridge plugins that connect DCC (Digital Content Creation) applications to the [Arkestrator](https://github.com/timvanhelsdingen/arkestrator) hub server. Each bridge is a thin WebSocket client that pushes live editor context, executes commands from AI agents, and applies file changes -- all without any job submission UI (that lives in the Arkestrator desktop client).

## Bridges

| Bridge | Application | Language | Status | Docs |
|--------|------------|----------|--------|------|
| Godot | Godot 4.x | GDScript | Stable | [docs/godot.md](docs/godot.md) |
| Blender | Blender 4.2+ | Python | Stable | [docs/blender.md](docs/blender.md) |
| Houdini | Houdini 20+ | Python, HScript | Stable | [docs/houdini.md](docs/houdini.md) |
| ComfyUI | ComfyUI | Python, Workflow JSON | Stable | [docs/comfyui.md](docs/comfyui.md) |
| Nuke | Nuke 13+ | Python, TCL | Experimental | [docs/nuke.md](docs/nuke.md) |
| Unity | Unity 2022+ | C# (unity_json) | Experimental | [docs/unity.md](docs/unity.md) |
| Unreal | Unreal Engine 5 | Python, UE Console | Experimental | [docs/unreal.md](docs/unreal.md) |
| Fusion | Blackmagic Fusion / DaVinci Resolve | Python, Lua | Experimental | [docs/fusion.md](docs/fusion.md) |

All bridges are version **0.1.54**, require Arkestrator **>= 0.1.40**, and support **Windows, macOS, and Linux**.

## How Bridges Work

1. The Arkestrator desktop client writes connection config to `~/.arkestrator/config.json`
2. Each bridge reads that config on startup to discover the server URL and auth credentials
3. The bridge connects via WebSocket and continuously pushes editor context (~3s interval, hash-deduplicated)
4. When an AI agent needs to run a command, the server routes it through the bridge to the DCC app
5. Results flow back through the same WebSocket connection

Every bridge supports: context capture, command execution, file delivery (with path traversal protection), client file access (agents can read files on the client machine), context menus, and auto-reconnect with exponential backoff.

## Installation

### Recommended: Arkestrator Desktop Client

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the bridge you need
4. Select the install location (auto-detected when possible)

### Manual

Download from the [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) page and extract to the correct location. See the individual bridge pages linked above for per-platform paths and detailed instructions.

## Contributing

To add a new bridge:

1. Create a new directory following the [standard bridge structure](#bridge-structure)
2. Implement the WebSocket client, command executor, file applier, and context capture
3. Write a `coordinator.md` and relevant `skills/` files
4. Add an entry to `registry.json`
5. Submit a PR

See the [Blender bridge](blender/) or [Houdini bridge](houdini/) as reference implementations. For full bridge development guidance, see [bridge-development.md](https://github.com/timvanhelsdingen/arkestrator/blob/main/docs/bridge-development.md) in the main repo.

## Bridge Structure

Each bridge follows the same directory layout:

```
<bridge>/
  arkestrator_bridge/       # Plugin code (Python/GDScript/C#)
  coordinator.md            # Agent coordinator script (execution rules for AI agents)
  skills/                   # Skill markdown files (domain knowledge for AI agents)
  MODULE.md                 # Current state documentation for this bridge
```

`registry.json` is the central inventory of all bridges -- metadata, install paths, skills, and coordinator scripts.

## Links

- [Arkestrator](https://github.com/timvanhelsdingen/arkestrator) -- Main server, desktop client, and protocol
- [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) -- Pre-built bridge packages

## License

[MIT](LICENSE)
