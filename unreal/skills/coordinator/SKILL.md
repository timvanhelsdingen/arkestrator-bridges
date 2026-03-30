---
name: unreal-coordinator
description: "Coordinator script for unreal — manages live session execution, transport, and best practices"
metadata:
  program: unreal
  category: coordinator
  title: Unreal Coordinator
  keywords: ["unreal", "coordinator", "bridge"]
  source: bridge-repo
  priority: 70
  auto-fetch: true
---

# Unreal Engine Coordinator

You are connected to Unreal Engine through Arkestrator.

## Connected Applications
{BRIDGE_LIST}

## Pre-loaded Bridge Context
{BRIDGE_CONTEXT}

## Transport
Use `execute_command(target="unreal", language="python", script="...")` for Python, or `language="ue_console"` for console commands.
Scripts execute with full Unreal Python API access. Use `/Game/...` paths consistently for content operations.

## Skills
Detailed operational knowledge for Unreal Engine is provided via skills.
Use `am skills search <query>` or `am skills list --program unreal` to discover available patterns, techniques, and best practices.

## Execution
1. Write focused Python or console command.
2. Execute via `execute_command`.
3. Fix errors immediately (max 3 fix loops).
4. Verify actor/asset state.

## Best Practices — Project Organization
- Follow Unreal Engine content structure:
  - Use `/Game/` as the content root
  - Organize by feature: `/Game/Characters/`, `/Game/Environments/`, `/Game/UI/`
  - Blueprints in feature folders alongside related assets
  - Materials in `/Game/Materials/` or within feature folders
  - Textures in `/Game/Textures/` or within feature folders
  - Meshes in `/Game/Meshes/` or `/Game/StaticMeshes/`
  - Maps/levels in `/Game/Maps/`
  - Imported source assets in `/Game/Source/`
- Use PascalCase for assets: `BP_PlayerCharacter`, `M_GrassMaterial`, `T_RockDiffuse`
- Prefix conventions: `BP_` (Blueprint), `M_` (Material), `MI_` (Material Instance), `T_` (Texture), `SM_` (Static Mesh), `SK_` (Skeletal Mesh), `ABP_` (Anim Blueprint), `WBP_` (Widget Blueprint)
- Never use `/Game/` root directly for assets — always organize in subfolders
- Use `unreal.EditorAssetLibrary` for asset operations, not direct filesystem manipulation
- Save assets and levels after modifications

## Quality Requirements
- Verify created/edited actors/assets exist and are valid
- Verify properties/locations/paths match request
- Save required assets/levels
- Report explicit PASS evidence, not assumptions
