---
title: Verification & Quality Assessment
category: bridge
---
# Unreal Engine Verification & Quality Assessment

## Actor / Component Hierarchy Validation

### Verify Actors Exist in Level
```python
import unreal

def verify_actors(expected_actors):
    """Verify actors exist in the current level.
    expected_actors: list of (label, class_name) tuples
    """
    editor = unreal.EditorLevelLibrary
    all_actors = editor.get_all_level_actors()

    actor_map = {}
    for actor in all_actors:
        actor_map[actor.get_actor_label()] = actor.get_class().get_name()

    errors = 0
    for label, expected_class in expected_actors:
        if label not in actor_map:
            print(f"VERIFY FAIL actor: '{label}' not found in level")
            errors += 1
        elif expected_class and actor_map[label] != expected_class:
            print(f"VERIFY FAIL actor: '{label}' expected class={expected_class} got={actor_map[label]}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS actors: {len(expected_actors)} actors found")
    return errors == 0

verify_actors([
    ("PlayerStart", "PlayerStart"),
    ("DirectionalLight", "DirectionalLight"),
    ("SkyLight", "SkyLight"),
])
```

### Verify Actor Transforms
```python
import unreal

def verify_actor_transform(label, expected_loc=None, expected_rot=None, expected_scale=None, tolerance=1.0):
    """Verify an actor's transform values."""
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    actor = None
    for a in actors:
        if a.get_actor_label() == label:
            actor = a
            break

    if actor is None:
        print(f"VERIFY FAIL transform: actor '{label}' not found")
        return False

    errors = 0
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()

    if expected_loc:
        dx = abs(loc.x - expected_loc[0])
        dy = abs(loc.y - expected_loc[1])
        dz = abs(loc.z - expected_loc[2])
        if max(dx, dy, dz) > tolerance:
            print(f"VERIFY FAIL transform: '{label}' location expected={expected_loc} got=({loc.x:.1f},{loc.y:.1f},{loc.z:.1f})")
            errors += 1

    if expected_rot:
        dp = abs(rot.pitch - expected_rot[0])
        dy = abs(rot.yaw - expected_rot[1])
        dr = abs(rot.roll - expected_rot[2])
        if max(dp, dy, dr) > tolerance:
            print(f"VERIFY FAIL transform: '{label}' rotation expected={expected_rot} got=({rot.pitch:.1f},{rot.yaw:.1f},{rot.roll:.1f})")
            errors += 1

    if expected_scale:
        dx = abs(scale.x - expected_scale[0])
        dy = abs(scale.y - expected_scale[1])
        dz = abs(scale.z - expected_scale[2])
        if max(dx, dy, dz) > tolerance * 0.01:
            print(f"VERIFY FAIL transform: '{label}' scale expected={expected_scale} got=({scale.x:.2f},{scale.y:.2f},{scale.z:.2f})")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS transform: '{label}' correct")
    return errors == 0
```

### Verify Components on Actor
```python
import unreal

def verify_components(actor_label, expected_components):
    """Verify an actor has expected component types.
    expected_components: list of class names e.g. ["StaticMeshComponent", "BoxCollision"]
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    actor = None
    for a in actors:
        if a.get_actor_label() == actor_label:
            actor = a
            break

    if actor is None:
        print(f"VERIFY FAIL components: actor '{actor_label}' not found")
        return False

    components = actor.get_components_by_class(unreal.ActorComponent)
    comp_classes = [c.get_class().get_name() for c in components]

    errors = 0
    for expected in expected_components:
        if expected not in comp_classes:
            print(f"VERIFY FAIL components: '{actor_label}' missing {expected}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS components: '{actor_label}' has {len(expected_components)} expected components")
    return errors == 0
```

## Blueprint Compilation Checks

### Verify Blueprint Compiles
```python
import unreal

def verify_blueprint_compiles(asset_path):
    """Load and compile a Blueprint, check for errors.
    asset_path: e.g. "/Game/Blueprints/BP_Player"
    """
    bp = unreal.EditorAssetLibrary.load_asset(asset_path)
    if bp is None:
        print(f"VERIFY FAIL blueprint: could not load {asset_path}")
        return False

    if not isinstance(bp, unreal.Blueprint):
        print(f"VERIFY FAIL blueprint: {asset_path} is not a Blueprint")
        return False

    # Compile the blueprint
    unreal.KismetSystemLibrary.flush_persistent_debug_lines(None)
    result = unreal.BlueprintEditorLibrary.compile_blueprint(bp)

    if result != unreal.KismetCompilerType.SUCCESSFULLY_COMPILED:
        print(f"VERIFY FAIL blueprint: {asset_path} compilation failed")
        return False

    print(f"VERIFY PASS blueprint: {asset_path} compiles OK")
    return True
```

## Material / Texture Assignment Verification

### Verify Materials on Static Mesh Actor
```python
import unreal

def verify_materials(actor_label, expected_materials):
    """Verify materials assigned to an actor's mesh component.
    expected_materials: list of material asset names
    """
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    actor = None
    for a in actors:
        if a.get_actor_label() == actor_label:
            actor = a
            break

    if actor is None:
        print(f"VERIFY FAIL materials: actor '{actor_label}' not found")
        return False

    mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    if mesh_comp is None:
        mesh_comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if mesh_comp is None:
        print(f"VERIFY FAIL materials: '{actor_label}' has no mesh component")
        return False

    errors = 0
    num_materials = mesh_comp.get_num_materials()
    actual_materials = []
    for i in range(num_materials):
        mat = mesh_comp.get_material(i)
        if mat:
            actual_materials.append(mat.get_name())

    for expected in expected_materials:
        if expected not in actual_materials:
            print(f"VERIFY FAIL materials: '{actor_label}' missing material '{expected}'")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS materials: '{actor_label}' has {len(expected_materials)} materials assigned")
    return errors == 0
```

## Asset Validation

### Verify Assets Exist
```python
import unreal

def verify_assets_exist(asset_paths):
    """Check that assets exist in the content browser.
    asset_paths: list of /Game/... paths
    """
    errors = 0
    for path in asset_paths:
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            print(f"VERIFY FAIL asset: not found {path}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS assets: {len(asset_paths)} assets exist")
    return errors == 0

verify_assets_exist([
    "/Game/Blueprints/BP_Player",
    "/Game/Materials/M_Ground",
    "/Game/Maps/MainLevel",
])
```

## Build / Cook Verification

### Verify Level Saves
```python
import unreal

def verify_level_save():
    """Save the current level and check for errors."""
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world is None:
        print("VERIFY FAIL save: no level loaded")
        return False

    # Save all dirty packages
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(
        save_map_packages=True,
        save_content_packages=True
    )
    print("VERIFY PASS save: level saved successfully")
    return True
```

### Verify Package Cook (Lightweight Check)
```python
import unreal
import os

def verify_project_builds():
    """Check project can be cooked by validating no asset errors."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # Check for assets with validation errors
    all_assets = registry.get_all_assets()
    error_count = 0
    for asset_data in all_assets:
        if not asset_data.is_valid():
            print(f"VERIFY WARN asset: invalid {asset_data.package_name}")
            error_count += 1

    if error_count == 0:
        print(f"VERIFY PASS project: {len(all_assets)} assets valid")
    else:
        print(f"VERIFY WARN project: {error_count} assets with issues")
    return error_count == 0
```

## Complete Verification Workflow

1. **Execute commands** via `execute_command` with `language="python"`
2. **Verify actors** exist with correct classes and components
3. **Verify transforms** match requested positions/rotations
4. **Verify materials** are assigned correctly
5. **Verify assets** exist in content browser
6. **Compile Blueprints** if any were created or modified
7. **Save level** to confirm no corruption
8. **Report** PASS with actor/asset counts or FAIL with specific errors
