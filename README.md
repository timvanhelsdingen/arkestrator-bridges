# Arkestrator Bridges

Bridge plugins that connect DCC (Digital Content Creation) applications to the [Arkestrator](https://github.com/timvanhelsdingen/arkestrator) hub server. Each bridge is a thin WebSocket client that pushes live editor context, executes commands from AI agents, and applies file changes -- all without any job submission UI (that lives in the Arkestrator desktop client).

## Bridges

| Bridge | Application | Install Type | Languages | Stability | Skills |
|--------|------------|--------------|-----------|-----------|--------|
| [Godot](#godot) | Godot 4.x | Per-project | GDScript | Stable | Scene Management, Scripting Patterns, GDScript API |
| [Blender](#blender) | Blender 4.2+ | User-level | Python | Stable | Materials & Shading, Rendering, Modeling, Python API |
| [Houdini](#houdini) | Houdini 20+ | User-level | Python, HScript | Stable | SOP Networks, Procedural Modeling, HOM Scripting |
| [ComfyUI](#comfyui) | ComfyUI | Standalone | Python, Workflow JSON | Stable | Workflow Patterns, API Patterns |
| [Nuke](#nuke) | Nuke 13+ | User-level | Python, TCL | Experimental | Compositing, Python API, Node Patterns |
| [Unity](#unity) | Unity 2022+ | Per-project | C# (unity_json) | Experimental | -- |
| [Unreal](#unreal) | Unreal Engine 5 | Engine-level | Python, UE Console | Experimental | -- |
| [Fusion](#fusion) | Blackmagic Fusion / DaVinci Resolve | User-level | Python, Lua | Experimental | Python API |

All bridges are version **0.1.54**, require Arkestrator **>= 0.1.40**, and support **Windows, macOS, and Linux**.

## Core Features

Every bridge implements the same protocol:

- **Context Capture** -- Live editor state (open files, selected nodes, scene hierarchy) pushed to the server every ~3 seconds, hash-deduplicated to avoid redundant updates
- **Command Execution** -- Run scripts in the application's native language(s) from server-side AI agents
- **File Delivery** -- Apply file create/modify/delete operations with path traversal protection
- **Client File Access** -- Server-side agents can read any file on the client machine via the `read_client_file` MCP tool (images, renders, project files) without file syncing
- **Context Menu** -- Right-click "Add to Arkestrator Context" integration in each application
- **Auto-Reconnect** -- WebSocket reconnects with exponential backoff; context cleared and re-sent on each reconnect

## How It Works

```
Arkestrator Server  <--WebSocket-->  Bridge Plugin  <-->  DCC Application
     (Bun/Hono)                    (thin client)         (Godot/Blender/etc.)
```

1. The Arkestrator desktop client writes connection config to `~/.arkestrator/config.json`
2. Each bridge reads that config on startup to discover the server URL and auth credentials
3. The bridge connects via WebSocket and continuously pushes editor context
4. When an AI agent needs to run a command, the server routes it through the bridge to the DCC app
5. Results flow back through the same WebSocket connection

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the bridge you need
4. Select the install location (auto-detected when possible)

The client handles downloading, extracting, and placing files in the correct location.

### Manual Installation

Download the latest release zip for your bridge from the [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) page and extract to the appropriate location:

#### Godot

Copy the `addons/arkestrator_bridge/` folder into your Godot project's `addons/` directory, then enable the plugin in **Project > Project Settings > Plugins**.

```
your-project/
  addons/
    arkestrator_bridge/    <-- extract here
      plugin.gd
      plugin.cfg
      ws_client.gd
      command_executor.gd
      file_applier.gd
      context_menu.gd
```

#### Blender

Extract `arkestrator_bridge/` to your Blender addons directory, then enable in **Edit > Preferences > Add-ons**.

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%/Blender Foundation/Blender/<version>/scripts/addons/arkestrator_bridge` |
| macOS | `~/Library/Application Support/Blender/<version>/scripts/addons/arkestrator_bridge` |
| Linux | `~/.config/blender/<version>/scripts/addons/arkestrator_bridge` |

#### Houdini

Extract the package to your Houdini packages directory. The bridge uses Houdini's package system (`arkestrator_bridge.json`).

| Platform | Path |
|----------|------|
| Windows | `%USERPROFILE%/Documents/houdini<version>/packages/` |
| macOS | `~/Library/Preferences/houdini/<version>/packages/` |
| Linux | `~/.houdini<version>/packages/` |

#### ComfyUI

The ComfyUI bridge runs as a standalone Python process alongside your ComfyUI instance. Extract `arkestrator_bridge/` and run it with `python -m arkestrator_bridge`.

#### Nuke

Extract `arkestrator_bridge/` to your `.nuke` directory and add an import to your `init.py` or `menu.py`.

| Platform | Path |
|----------|------|
| Windows | `%USERPROFILE%/.nuke/arkestrator_bridge` |
| macOS | `~/.nuke/arkestrator_bridge` |
| Linux | `~/.nuke/arkestrator_bridge` |

#### Unity

Copy `ArkestratorBridge/` into your Unity project's `Assets/` directory. The editor scripts load automatically.

```
your-project/
  Assets/
    ArkestratorBridge/    <-- extract here
      Editor/
        ArkestratorBridge.cs
        ArkestratorCommandExecutor.cs
        ArkestratorFileApplier.cs
        ArkestratorWebSocketClient.cs
        ArkestratorMiniJson.cs
        ArkestratorBridge.Editor.asmdef
```

#### Unreal Engine

Copy `ArkestratorBridge/` into your UE5 engine plugins directory and enable it in the editor.

| Platform | Path |
|----------|------|
| Windows | `C:/Program Files/Epic Games/UE_<version>/Engine/Plugins/ArkestratorBridge` |
| macOS | `/Users/Shared/Epic Games/UE_<version>/Engine/Plugins/ArkestratorBridge` |
| Linux | `~/UnrealEngine/Engine/Plugins/ArkestratorBridge` |

#### Fusion (Blackmagic Fusion / DaVinci Resolve)

Extract to the Fusion Config directory. Includes a `.fu` script for menu integration and a startup Lua loader.

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%/Blackmagic Design/Fusion/Config` |
| macOS | `~/Library/Application Support/Blackmagic Design/Fusion/Config` |
| Linux | `~/.fusion/BlackmagicDesign/Fusion/Config` |

## Bridge Structure

Each bridge follows the same directory layout:

```
<bridge>/
  arkestrator_bridge/       # Plugin code (Python/GDScript/C#)
    __init__.py             # Main module: WS dispatch, context capture, menus, public API
    ws_client.py            # WebSocket client (connects to server, handles reconnect)
    command_executor.py     # DCC-specific command execution (Python/GDScript/HScript/etc.)
    file_applier.py         # File create/modify/delete with path traversal protection
  coordinator.md            # Agent coordinator script (execution rules for AI agents)
  skills/                   # Skill markdown files (domain knowledge for AI agents)
    verification.md         # Verification & quality assessment patterns (all bridges)
    ...                     # DCC-specific skills (modeling, compositing, etc.)
  MODULE.md                 # Current state documentation for this bridge
```

**Coordinator scripts** define how AI agents should interact with each bridge -- execution rules, verification requirements, scope constraints, and documentation links. The full coordinator scripts are embedded in `registry.json` and include template variables (`{BRIDGE_LIST}`, `{BRIDGE_CONTEXT}`) that the server fills in at runtime.

**Skills** are markdown files containing domain knowledge that AI agents can load on demand. They cover application-specific patterns, API references, and best practices. Skills are registered in `registry.json` and served to agents by the Arkestrator server.

## Configuration

Bridges auto-discover the Arkestrator server via `~/.arkestrator/config.json`, which the Arkestrator desktop client writes automatically. The config contains the server URL, port, and authentication credentials. No manual configuration is needed if the desktop client is running.

## Registry

`registry.json` is the central inventory of all bridges. It defines:

- Bridge metadata (name, version, stability, supported platforms)
- Install paths and auto-detection paths per platform
- Skills and their source files
- Full coordinator scripts (embedded as strings)
- GitHub release asset naming for auto-update

The Arkestrator desktop client fetches this registry to manage bridge installation and updates.

## Contributing

To add a new bridge:

1. Create a new directory (e.g., `maya/`) following the standard bridge structure
2. Implement the WebSocket client, command executor, file applier, and context capture
3. Write a `coordinator.md` and relevant `skills/` files
4. Add an entry to `registry.json` with skills, coordinator script, install paths, and detect paths
5. Add a `MODULE.md` documenting the bridge's current state
6. Submit a PR

See the [Blender bridge](blender/) or [Houdini bridge](houdini/) as reference implementations.

## Links

- [Arkestrator](https://github.com/timvanhelsdingen/arkestrator) -- Main server, desktop client, and protocol
- [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) -- Pre-built bridge packages
