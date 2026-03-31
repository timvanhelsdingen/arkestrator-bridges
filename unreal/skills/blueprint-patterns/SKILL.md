---
name: blueprint-patterns
description: "Blueprint Patterns patterns and best practices for unreal"
metadata:
  program: unreal
  category: bridge
  title: Blueprint Patterns
  keywords: ["unreal", "blueprint", "nodes", "graph", "variables", "events"]
  source: bridge-repo
  related-skills: ["cpp-gameplay", "level-design"]
---

# Unreal Blueprint Patterns

## Working with Blueprints via Bridge

The Unreal bridge executes Python scripts with full `unreal` module access. Blueprint introspection is available through `blueprint_utils` and the `unreal.EditorAssetLibrary` / `unreal.AssetToolsHelpers` APIs.

## Creating Blueprint Assets
```python
import unreal

factory = unreal.BlueprintFactory()
factory.set_editor_property("parent_class", unreal.Actor)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
bp = asset_tools.create_asset("BP_MyActor", "/Game/Blueprints", None, factory)

# Save after creation
unreal.EditorAssetLibrary.save_asset("/Game/Blueprints/BP_MyActor")
```

## Loading and Inspecting Blueprints
```python
bp = unreal.EditorAssetLibrary.load_asset("/Game/Blueprints/BP_MyActor")

# Check if it's a Blueprint
if isinstance(bp, unreal.Blueprint):
    parent = bp.parent_class
    print(f"Parent class: {parent.get_name()}")

    # Inspect components via SimpleConstructionScript
    scs = bp.simple_construction_script
    if scs:
        for node in scs.get_all_nodes():
            comp = node.component_template
            print(f"Component: {comp.get_name()} ({comp.get_class().get_name()})")
```

## Blueprint Naming Conventions
- `BP_` prefix for Actor Blueprints: `BP_PlayerCharacter`, `BP_Door`
- `WBP_` for Widget Blueprints: `WBP_MainMenu`, `WBP_HealthBar`
- `ABP_` for Animation Blueprints: `ABP_PlayerAnimInstance`
- `BPI_` for Blueprint Interfaces: `BPI_Interactable`, `BPI_Damageable`
- `BPFL_` for Blueprint Function Libraries: `BPFL_MathHelpers`
- `E_` for Enumerations: `E_WeaponType`, `E_GameState`
- `S_` for Structs: `S_ItemData`, `S_QuestInfo`

## Event Graph Patterns

### Common Event Nodes
- **BeginPlay** — initialization logic, bind delegates
- **Tick** — per-frame logic (use sparingly, prefer timers)
- **EndPlay** — cleanup, unbind delegates
- **Any Damage / Point Damage / Radial Damage** — damage handling
- **Actor Begin/End Overlap** — trigger volumes, proximity detection

### Input Handling
- **Enhanced Input** (UE5 preferred): Input Actions + Input Mapping Contexts
- Bind in BeginPlay, not in the construction script
- Use Input Action events (Started, Triggered, Completed) for different press states

### Blueprint-C++ Communication
- **BlueprintCallable** — C++ function callable from Blueprint event graphs
- **BlueprintImplementableEvent** — C++ declares, Blueprint implements
- **BlueprintNativeEvent** — C++ provides default, Blueprint can override
- Expose variables with `BlueprintReadWrite` or `BlueprintReadOnly`

## Best Practices
- Keep event graphs focused — one responsibility per graph
- Use functions and macros for reusable logic
- Collapse complex node groups into named functions
- Use Blueprint Interfaces for cross-Blueprint communication instead of direct casting
- Avoid Tick when possible — use Timers, delegates, or event-driven patterns
- Comment node groups with Comment Boxes for readability
- Keep Blueprint-only logic for prototyping; move performance-critical paths to C++

## Organizing Blueprint Assets
- `/Game/Blueprints/Characters/` — character BPs
- `/Game/Blueprints/Items/` — item/pickup BPs
- `/Game/Blueprints/UI/` — widget BPs
- `/Game/Blueprints/Environment/` — interactive environment BPs
- `/Game/Blueprints/GameFramework/` — GameMode, GameState, PlayerController BPs
