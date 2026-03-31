---
name: python-api
description: "Python Api patterns and best practices for blackmagic-fusion"
metadata:
  program: fusion
  category: bridge
  title: Python Api
  keywords: ["fusion", "python", "api", "comp", "tool", "scripting"]
  source: bridge-repo
---

# Fusion Python API Patterns

## Official Documentation
- Fusion scripting guide: https://documents.blackmagicdesign.com/UserManuals/FusionScriptingGuide.pdf
- Resolve scripting API: https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_Scripting_API.pdf
- VFXPedia Fusion scripting reference: https://www.steakunderwater.com/VFXPedia/

## Core API
- `fusion` / `fu` — the Fusion application object
- `comp = fusion.GetCurrentComp()` — active composition
- `comp.GetToolList(selected_only)` — get tools (returns 1-indexed dict)
- `comp.AddTool(tool_id, x, y)` — add a tool to the flow
- `comp.ActiveTool` — currently viewed tool

## Input/Output and Attributes
- `tool.GetInput(name, time)` / `tool.SetInput(name, value, time)` — read/write inputs
- `tool.GetAttrs()` — tool attributes (name, ID, position, etc.)
- `comp.GetAttrs()` — comp attributes (filename, frame range, etc.)
- `comp.GetPrefs()` — composition preferences (resolution, fps, etc.)

## Batch Editing
- `comp.Lock()` / `comp.Unlock()` — batch edits without UI updates
- `comp.StartUndo(name)` / `comp.EndUndo()` — wrap edits in an undo group

## Connections and Rendering
- `tool.ConnectInput(input_name, source_tool)` — wire tools together
- `comp.Render()` — render the current frame range

## Common Tool IDs
- 2D: `Merge`, `Transform`, `Background`, `ColorCorrector`, `Blur`, `Resize`, `Loader`, `Saver`, `Mask`, `BSplineMask`, `PolygonMask`, `Text`, `TextPlus`, `Tracker`, `Planar`, `ChannelBooleans`, `MatteControl`
- 3D: `Shape3D`, `Merge3D`, `Camera3D`, `Renderer3D`, `PointLight3D`, `DirectionalLight3D`, `FBXMesh3D`, `AlembicMesh3D`, `Transform3D`, `Text3D`

## Available Context Sources
The Fusion bridge can provide these context items (via "Add to Context"):
- **Selected Tools** — all currently selected tools with settings and connections
- **Active Tool** — the tool currently being viewed/edited
- **Tool Settings** — all input values for the active tool
- **Keyframes** — animation/keyframe data for the active tool
- **Full Composition** — complete comp structure (all tools, connections, settings)
- **Flow Graph** — node graph topology showing all tools and their connections
- **All Loaders** — media input tools with file paths and clip info
- **All Savers** — render output tools with paths and format settings
- **3D Scene** — 3D tools hierarchy (Shape3D, Merge3D, Camera3D, Light3D, etc.)
- **Modifiers & Expressions** — all modifiers (BezierSpline, Expression, etc.) across tools

## Important Notes
- Fusion uses 1-indexed dicts (Lua tables) — iterate with `.values()` in Python
- Always wrap multi-step edits in `comp.Lock()` / `comp.Unlock()`
- Use undo groups for undoable operations

## Scope Rules
- Keep edits narrowly scoped to the request
- Do not rebuild unrelated parts of the flow
- Use provided attachment/context paths directly

## Resource Contention
- Treat renders and heavy comp operations as `gpu_vram_heavy`
- Do not start a Fusion render on a worker already busy with another heavy GPU task
