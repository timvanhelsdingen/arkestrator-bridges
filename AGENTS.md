# Arkestrator Bridges - Agent Instructions

## Project Overview
Bridge plugins that connect DCC applications (Godot, Blender, Houdini, Nuke, ComfyUI, Unity, Unreal, Fusion) to the Arkestrator hub server. Each bridge is a thin WebSocket client that pushes editor context, executes commands, and applies file changes.

## Repository Structure
```
<bridge>/
  arkestrator_bridge/     # Python/GDScript package (the actual plugin)
    __init__.py           # Main module: WS dispatch, context, menus, public API
    ws_client.py          # WebSocket client (stdlib only, program=<bridge>)
    command_executor.py   # Language-specific command execution
    file_applier.py       # File create/modify/delete with path safety
  skills/                 # Skill markdown files (compositing, scripting, etc.)
  coordinator.md          # Agent coordinator script with execution rules
  MODULE.md               # Current state documentation for this bridge
registry.json             # Central registry of all bridges, skills, and coordinator scripts
```

## Documentation Requirements

**After making ANY changes to a bridge, you MUST update:**

1. **`<bridge>/MODULE.md`** — Reflects the current state of that bridge: files, public API, editor context schema, command languages, menu integration, protocol messages, and differences from other bridges. This is the authoritative reference for each bridge's capabilities.

2. **`README.md`** — Update the bridge table if a new bridge is added, removed, or renamed.

3. **`registry.json`** — Update the bridge entry if you change skills, coordinator scripts, install paths, detect paths, version, or stability level.

These docs are how other agents (and future sessions) understand what each bridge can do. Stale docs cause wrong assumptions and broken integrations. **Do not skip documentation updates.**

## Key Conventions

- All bridges follow the same thin-bridge pattern: connect, push context, execute commands, apply files. No job submission UI — that lives in the Tauri client.
- `ws_client.py` is identical across Python bridges except for `program=` in `_build_url`. Copy from an existing bridge when creating a new one.
- `file_applier.py` is standardized. Only the project root detection differs per DCC app.
- `command_executor.py` is DCC-specific. Each bridge supports different languages (Python, GDScript, HScript, TCL, Lua, etc.).
- Bridges auto-discover connection config from `~/.arkestrator/config.json` (written by the Tauri desktop client).
- Context items use `bridge_context_item_add` with incrementing `@N` index references.
- All commands that touch the DCC node graph must execute on the main thread (each DCC has its own mechanism for this).

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
- [ ] `registry.json` entry added/updated
- [ ] Skills and coordinator script created/updated
- [ ] `README.md` bridge table updated if new bridge

## Cross-Reference
- Main Arkestrator repo: https://github.com/timvanhelsdingen/arkestrator
- Protocol docs: see `packages/protocol/` in main repo
- Bridge development guide: see `docs/bridge-development.md` in main repo
