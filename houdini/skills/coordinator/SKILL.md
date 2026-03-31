---
name: houdini-coordinator
description: "Coordinator script for houdini — manages live session execution, transport, and best practices"
metadata:
  program: houdini
  category: coordinator
  title: Houdini Coordinator
  keywords: ["houdini", "coordinator", "bridge", "hou", "python", "execute_command"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# Houdini Coordinator

You are connected to a live Houdini session through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="houdini", language="python", script="...")` to run Python/HOM code in the live session.
Scripts execute with full `hou` module access. Prefer live bridge for active HIP work, hython for offline analysis.

## Skills
Detailed operational knowledge for Houdini is provided via skills.
Use `am skills search <query>` or `am skills list --program houdini` to discover available patterns, techniques, and best practices.

## Execution
1. Build/modify required nodes and parameters.
2. Execute via `execute_command`.
3. Run deterministic validation and print PASS/FAIL.
4. Fix failures before continuing (max 3 fix loops).
5. Cache/render only after upstream validation passes.

## Best Practices — File & Project Organization
- Save geometry caches to `$HIP/geo/` (create the folder if needed)
- Save USD/USDA exports to `$HIP/usd/`
- Save VEX snippets/includes to `$HIP/vex/`
- Save simulation caches (FLIP, pyro, RBD) to `$HIP/cache/<simtype>/`
- Save renders to `$HIP/render/`
- Save texture/image outputs to `$HIP/tex/`
- Use `$HIP`-relative paths everywhere — never hardcode absolute paths
- Name nodes descriptively (e.g. `scatter_rocks`, `flip_ocean`, not `geo1`, `null1`)
- Use null nodes as clear output markers at the end of chains
- Keep the /obj level organized: one object per logical asset or setup
- Put reusable HDA definitions in `$HIP/hda/` if creating custom operators
- Always set the file path on File Cache SOPs before cooking — verify the directory exists

## Quality Requirements
- Verify nodes and wiring exist with correct parameters
- Verify outputs resolve to disk where relevant
- Print HIP file path, task type, changed nodes, and PASS/FAIL summary
- Handle errors gracefully with try/except
- Do not perform scene-wide destructive edits for narrow requests
- Report explicit PASS evidence, not assumptions
