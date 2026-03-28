# Arkestrator Bridges - Agent Instructions

## Project Overview
Bridge plugins that connect DCC applications (Godot, Blender, Houdini, Nuke, ComfyUI, Unity, Unreal, Fusion) to the Arkestrator hub server. Each bridge is a thin WebSocket client that pushes editor context, executes commands, and applies file changes.

## Repository Structure
```
<bridge>/
  <plugin_dir>/             # Plugin code — varies by bridge (see below)
    __init__.py / plugin.gd / *.cs   # Main module
    ws_client.*             # WebSocket client
    command_executor.*      # Language-specific command execution
    file_applier.*          # File create/modify/delete with path safety
  skills/                   # Skill markdown files (domain knowledge for AI agents)
    verification.md         # Verification & quality assessment (all bridges)
    ...                     # DCC-specific skills
  coordinator.md            # Simplified coordinator reference (full version in registry.json)
  MODULE.md                 # Current state documentation for this bridge
registry.json               # Central registry: bridge metadata, skills, full coordinator scripts
scripts/                    # Repo-level tooling (bump-version.mjs)
```

### Plugin Directory Variants
- **Python bridges** (Blender, Houdini, ComfyUI, Nuke): `arkestrator_bridge/` with `.py` files
- **Godot**: `addons/arkestrator_bridge/` with `.gd` (GDScript) files + `plugin.cfg`
- **Unity**: `ArkestratorBridge/Editor/` with `.cs` files + `.asmdef`
- **Unreal**: `ArkestratorBridge/Content/Python/arkestrator_bridge/` with `.py` files + `.uplugin`
- **Fusion**: `Arkestrator/` with `.py` files + `Arkestrator.fu` (Fusion script loader) + `Scripts/Tool/` for context menu

## Documentation Requirements

**After making ANY changes to a bridge, you MUST update:**

1. **`<bridge>/MODULE.md`** — Reflects the current state of that bridge: files, public API, editor context schema, command languages, menu integration, protocol messages, and differences from other bridges. This is the authoritative reference for each bridge's capabilities.

2. **`README.md`** — Update the bridge table if a new bridge is added, removed, or renamed.

3. **`registry.json`** — Update the bridge entry if you change skills, coordinator scripts, install paths, detect paths, version, or stability level.

These docs are how other agents (and future sessions) understand what each bridge can do. Stale docs cause wrong assumptions and broken integrations. **Do not skip documentation updates.**

## Key Conventions

- All bridges follow the same thin-bridge pattern: connect, push context, execute commands, apply files. No job submission UI — that lives in the Tauri client.
- `ws_client.py` is identical across Python bridges except for `program=` in `_build_url`. Copy from an existing bridge when creating a new one.
- `file_applier.py` / `file_applier.gd` / `ArkestratorFileApplier.cs` is standardized. Only the project root detection differs per DCC app.
- `command_executor.*` is DCC-specific. Each bridge supports different languages (Python, GDScript, HScript, TCL, Lua, unity_json, ue_console, etc.).
- Bridges auto-discover connection config from `~/.arkestrator/config.json` (written by the Tauri desktop client).
- Context items use `bridge_context_item_add` with incrementing `@N` index references.
- All commands that touch the DCC node graph must execute on the main thread (each DCC has its own mechanism for this).
- Full coordinator scripts live in `registry.json` (not in the `coordinator.md` files, which are simplified references). The registry versions include template variables (`{BRIDGE_LIST}`, `{BRIDGE_CONTEXT}`) filled by the server at runtime.

## Bridge Inventory

| Bridge | Language | Install Type | Stability |
|--------|----------|-------------|-----------|
| godot | GDScript | Per-project (`addons/`) | Stable |
| blender | Python | User-level addon | Stable |
| houdini | Python | User-level package | Stable |
| comfyui | Python | Standalone process | Stable |
| nuke | Python | User-level (`~/.nuke/`) | Experimental |
| unity | C# | Per-project (`Assets/`) | Experimental |
| unreal | Python + C++ | Engine plugin | Experimental |
| fusion | Python + Lua | User-level config | Experimental |

## Bridge Development Checklist

When creating or modifying a bridge:
- [ ] WebSocket connects and reconnects with exponential backoff
- [ ] Editor context pushes on connect + every ~3s (hash-deduped)
- [ ] Context clear sent on every reconnect
- [ ] Commands execute in the correct languages with proper error reporting
- [ ] File changes applied with path traversal protection
- [ ] Context menu integration ("Add to Arkestrator Context")
- [ ] Public API (`get_bridge()`) works for third-party plugins
- [ ] `MODULE.md` updated with current state
- [ ] `registry.json` entry added/updated (skills, coordinator script, install paths, detect paths)
- [ ] Skills and coordinator script created/updated
- [ ] `README.md` bridge table updated if new bridge

## Cross-Reference
- Main Arkestrator repo: https://github.com/timvanhelsdingen/arkestrator
- Protocol docs: see `packages/protocol/` in main repo
- Bridge development guide: see `docs/bridge-development.md` in main repo
