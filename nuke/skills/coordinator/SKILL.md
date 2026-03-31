---
name: nuke-coordinator
description: "Coordinator script for nuke — manages live session execution, transport, and best practices"
metadata:
  program: nuke
  category: coordinator
  title: Nuke Coordinator
  keywords: ["nuke", "coordinator", "bridge", "python", "nuke-api", "execute_command"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# Nuke Coordinator

You are connected to a live Nuke session through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="nuke", language="python", script="...")` to run Python code in the live Nuke session.
Scripts execute with full `nuke` module access. Use `language="tcl"` for TCL commands.
All commands are executed in the main thread via `nuke.executeInMainThread()` for thread safety.

## Skills
Detailed operational knowledge for Nuke is provided via skills.
Use `am skills search <query>` or `am skills list --program nuke` to discover available patterns, techniques, and best practices.

## Execution
1. Build/modify required nodes and connections.
2. Execute via `execute_command`.
3. Run deterministic validation and print PASS/FAIL.
4. Fix failures before continuing (max 3 fix loops).
5. Render only after upstream validation passes.

## Best Practices -- File & Project Organization
- Save render outputs to `[value root.name]/../renders/` or a project-defined output path
- Save temp comps/precomps to `[value root.name]/../precomp/`
- Use `[value root.name]` for project-relative paths in Write nodes
- Never hardcode absolute paths in production scripts
- Name nodes descriptively (e.g. `fg_grade`, `bg_denoise`, `final_comp`)
- Use Backdrop nodes to organize logical sections
- Use Dot nodes for clean graph routing
- Keep the main composite chain as a clean vertical backbone

## Node Graph Conventions
- Flow direction: top-to-bottom
- Reads at the top, Writes at the bottom
- Background plate on the left (B input), foreground on the right (A input)
- Use consistent naming: `{element}_{operation}` (e.g., `plate_denoise`, `cg_grade`)
- Group reusable setups into Gizmos or Group nodes

## Quality Requirements
- Verify nodes exist and are connected correctly
- Verify Write node paths resolve to valid directories
- Verify frame ranges are set correctly on Read/Write nodes
- Print node count, key connections, and PASS/FAIL summary
- Handle errors gracefully with try/except
- Do not restructure entire comps for narrow requests
- Report explicit PASS evidence, not assumptions

## Resource Contention
- Treat renders, DeepImage operations, and heavy 3D (ScanlineRender) as `gpu_vram_heavy`
- Do not overlap heavy Nuke tasks with other GPU-heavy bridge operations on the same worker
