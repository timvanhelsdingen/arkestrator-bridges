---
name: fusion-coordinator
description: "Coordinator script for blackmagic-fusion — manages live session execution, transport, and best practices"
metadata:
  program: fusion
  category: coordinator
  title: Blackmagic-fusion Coordinator
  keywords: ["fusion", "coordinator", "bridge"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# Blackmagic Fusion Coordinator

You are connected to a live Blackmagic Fusion session through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="fusion", language="python", script="...")` for Python, or `language="lua"` for Lua scripts.
Scripts execute with full Fusion API access. Both standalone Fusion and DaVinci Resolve's Fusion page are supported.

## Skills
Detailed operational knowledge for Fusion is provided via skills.
Use `am skills search <query>` or `am skills list --program fusion` to discover available patterns, techniques, and best practices.

## Execution
1. Write focused Fusion Python or Lua script.
2. Execute via `execute_command`.
3. Read output and fix errors (max 3 fix loops).
4. Verify state with a follow-up check script.

## Best Practices — Comp & File Organization
- Save comp files (`.comp`) in a project-level `comps/` or `fusion/` directory
- Save rendered output to `renders/` or `output/` relative to the project
- Name tools descriptively: `MediaIn_Plate`, `Merge_FG_BG`, `CC_Grade_Hero` — not default names like `Merge1`
- Group related tools visually with underlay nodes for readability
- Use Loader/Saver paths relative to the project root when possible
- Keep footage/plates in a `footage/` or `plates/` folder
- Save masks and mattes to `mattes/`
- Use consistent frame padding in output paths (e.g. `render_####.exr`)
- Create output directories before rendering if they don't exist

## Quality Requirements
- Verify tools exist with expected names, types, and connections
- Wrap multi-step edits in `comp.Lock()` / `comp.Unlock()` to avoid UI thrashing
- Use `comp.StartUndo("description")` / `comp.EndUndo(true)` for undoable edits
- Handle errors gracefully with try/except
- Report explicit PASS evidence, not assumptions
