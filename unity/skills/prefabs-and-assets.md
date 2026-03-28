---
title: Prefabs & Assets
category: bridge
---
# Unity Prefabs & Asset Management

## Asset Operations via Bridge

### Selecting an Asset
```json
{"action": "select_asset", "path": "Assets/Prefabs/Player.prefab"}
```
- Selects and pings the asset in the Project window
- Path must be project-relative (starts with `Assets/`)

### Refreshing the Asset Database
```json
{"action": "refresh_assets"}
```
- Must be called after any file-system changes (creating, moving, deleting files)
- Triggers Unity's import pipeline for new/modified assets

## Prefab Workflows

### Creating Prefabs via File Apply
Prefabs are `.prefab` files in YAML format. The recommended workflow:
1. Write a C# editor script that creates the GameObject hierarchy
2. Apply the script as a file change
3. Run `refresh_assets` to compile
4. Execute the script to create and save the prefab

### Prefab Best Practices
- Store prefabs in `Assets/Prefabs/` organized by category
- Name with PascalCase: `PlayerCharacter.prefab`, `EnemySpawner.prefab`
- Prefab variants inherit from a base — use for enemy types, weapon variants
- Nested prefabs: prefabs inside prefabs maintain their own override chain
- Always unpack prefab instances before making structural changes if needed

### Common Prefab Patterns
- **Actor prefab**: root GameObject with components, children for visuals/colliders
- **UI prefab**: Canvas child with RectTransform, layout groups, nested elements
- **Environment prefab**: parent empty with positioned child meshes, colliders, triggers

## Asset Creation & Loading

### Creating Assets via Script (File Apply)
```csharp
// Material
var mat = new Material(Shader.Find("Standard"));
mat.color = Color.red;
AssetDatabase.CreateAsset(mat, "Assets/Materials/RedMaterial.mat");

// ScriptableObject
var data = ScriptableObject.CreateInstance<WeaponData>();
data.weaponName = "Sword";
AssetDatabase.CreateAsset(data, "Assets/Data/Sword.asset");

AssetDatabase.SaveAssets();
AssetDatabase.Refresh();
```

### Loading Assets at Runtime
```csharp
// Resources folder (built into player)
var prefab = Resources.Load<GameObject>("Prefabs/Bullet");

// Addressables (recommended for larger projects)
var handle = Addressables.LoadAssetAsync<GameObject>("Bullet");
handle.Completed += op => { /* use op.Result */ };
```

### Asset Path Conventions
- `Assets/Scenes/` — scene files (`.unity`)
- `Assets/Scripts/` — C# scripts (`.cs`)
- `Assets/Prefabs/` — prefab assets (`.prefab`)
- `Assets/Materials/` — materials (`.mat`)
- `Assets/Textures/` — textures (`.png`, `.jpg`, `.tga`, `.exr`)
- `Assets/Models/` — 3D models (`.fbx`, `.obj`)
- `Assets/Audio/` — sound files (`.wav`, `.ogg`, `.mp3`)
- `Assets/UI/` — UI assets, sprites, fonts
- `Assets/Shaders/` — shader files (`.shader`, `.hlsl`)
- `Assets/Resources/` — runtime-loadable via `Resources.Load`

## Resource Management Tips
- Avoid `Resources/` for large projects — use Addressables instead
- Keep texture import settings appropriate (max size, compression format)
- Use asset bundles or Addressables for downloadable content
- Call `AssetDatabase.SaveAssets()` after creating assets programmatically
- Use `AssetDatabase.GUIDToAssetPath()` and `AssetDatabase.AssetPathToGUID()` for stable references
- `.meta` files are auto-generated — never delete them manually or GUIDs break
