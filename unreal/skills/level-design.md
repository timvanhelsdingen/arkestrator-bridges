---
title: Level Design
category: bridge
---
# Unreal Level Design

## Working with Levels via Bridge

### Opening a Level
```python
import unreal
unreal.EditorLevelLibrary.load_level("/Game/Maps/MainLevel")
```

### Saving the Current Level
```python
unreal.EditorLevelLibrary.save_current_level()
# Or save all dirty packages:
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
```

## Spawning and Managing Actors

### Spawning Actors
```python
# Spawn a static mesh actor
actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.StaticMeshActor,
    unreal.Vector(500, 0, 100),
    unreal.Rotator(0, 45, 0)
)
actor.set_actor_label("WallSection_01")

# Set the mesh
mesh = unreal.EditorAssetLibrary.load_asset("/Game/Meshes/SM_Wall")
actor.static_mesh_component.set_static_mesh(mesh)
```

### Finding Actors in the Level
```python
# Get all actors
all_actors = unreal.EditorLevelLibrary.get_all_level_actors()

# Filter by class
lights = unreal.GameplayStatics.get_all_actors_of_class(
    unreal.EditorLevelLibrary.get_editor_world(),
    unreal.PointLight
)

# Find by label/tag
for actor in all_actors:
    if actor.get_actor_label() == "PlayerStart_0":
        print(f"Found at {actor.get_actor_location()}")
```

### Transforming Actors
```python
actor.set_actor_location(unreal.Vector(100, 200, 0), False, True)
actor.set_actor_rotation(unreal.Rotator(0, 90, 0), False)
actor.set_actor_scale3d(unreal.Vector(2, 2, 2))
```

### Deleting Actors
```python
unreal.EditorLevelLibrary.destroy_actor(actor)
```

## Lighting

### Common Light Types
- `PointLight` — omnidirectional, for lamps/bulbs
- `SpotLight` — cone-shaped, for flashlights/stage lights
- `DirectionalLight` — parallel rays, for sun/moon
- `RectLight` — rectangular area, for screens/windows
- `SkyLight` — ambient fill from sky cubemap

### Spawning a Light
```python
light = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.PointLight,
    unreal.Vector(0, 0, 300)
)
light.set_actor_label("RoomLight_01")
light.point_light_component.set_editor_property("intensity", 5000.0)
light.point_light_component.set_editor_property("light_color", unreal.Color(255, 220, 180))
light.point_light_component.set_editor_property("attenuation_radius", 1000.0)
```

### Sky and Atmosphere
- `SkyAtmosphere` — physically-based sky rendering
- `ExponentialHeightFog` — distance/height-based fog
- `VolumetricCloud` — dynamic cloud layer
- Standard outdoor setup: DirectionalLight + SkyLight + SkyAtmosphere + ExponentialHeightFog

## Materials

### Assigning Materials
```python
material = unreal.EditorAssetLibrary.load_asset("/Game/Materials/M_BrickWall")
actor.static_mesh_component.set_material(0, material)
```

### Creating Material Instances
```python
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
factory = unreal.MaterialInstanceConstantFactoryNew()

parent_mat = unreal.EditorAssetLibrary.load_asset("/Game/Materials/M_Master")
factory.set_editor_property("initial_parent", parent_mat)

mi = asset_tools.create_asset("MI_RedBrick", "/Game/Materials", None, factory)
mi.set_editor_property("scalar_parameter_values", [...])

unreal.EditorAssetLibrary.save_asset("/Game/Materials/MI_RedBrick")
```

### Material Naming
- `M_` — base materials: `M_BrickWall`, `M_Metal_Rough`
- `MI_` — material instances: `MI_BrickWall_Red`, `MI_Metal_Worn`
- `MF_` — material functions: `MF_BlendByHeight`
- `T_` — textures: `T_Brick_D` (diffuse), `T_Brick_N` (normal), `T_Brick_ORM` (packed)

## Level Organization

### Folder Structure
- `/Game/Maps/` — level files (`.umap`)
- `/Game/Maps/SubLevels/` — streaming sub-levels
- Use World Partition for large open worlds (UE5 default for new levels)
- Use Level Instances for reusable level chunks

### Actor Organization
- Use Folders in the World Outliner to group actors by purpose
- Label actors descriptively: `Wall_Kitchen_01`, `Light_Hallway_Ceiling`
- Use Actor Tags for runtime queries: `actor.tags.append("Destructible")`

### World Partition (UE5)
- Automatic spatial streaming — no manual sub-level management
- Data Layers control actor groups (gameplay layers, lighting layers)
- One File Per Actor (OFPA) enables concurrent editing

## Asset Naming Conventions
- `SM_` — Static Mesh: `SM_Chair`, `SM_Rock_Large`
- `SK_` — Skeletal Mesh: `SK_Mannequin`, `SK_Weapon_Rifle`
- `BP_` — Blueprint: `BP_Door_Interactive`, `BP_PickupItem`
- `T_` — Texture: `T_Ground_D`, `T_Ground_N`, `T_Ground_ORM`
- `S_` — Sound: `S_Footstep_Concrete`, `S_Explosion`

## Common Pitfalls
- Always save the level after spawning or modifying actors
- Use `unreal.EditorAssetLibrary` for asset operations, not filesystem manipulation
- Actor labels are display names; use `get_name()` for the internal unique name
- World Partition levels must be loaded/checked out before editing actors in specific cells
- Static meshes need collision setup for physics interaction — check collision presets
