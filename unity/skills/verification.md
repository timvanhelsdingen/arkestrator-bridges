---
title: Verification & Quality Assessment
category: bridge
---
# Unity Verification & Quality Assessment

## Scene Hierarchy Validation

Unity bridge commands use `language="unity_json"` with structured action payloads. Verification is done by re-reading bridge context and checking results.

### Verify GameObjects Exist via Bridge Context
After executing commands, re-read the bridge editor context and validate the scene state. The bridge context includes hierarchy information that can be parsed.

```json
[
  {"action": "ping"}
]
```
Execute a ping and check the returned bridge context for scene state. The editor context includes selected objects, scene hierarchy, and project information.

### Verify GameObject Creation
```json
[
  {"action": "create_game_object", "name": "Player", "parent": ""},
  {"action": "create_game_object", "name": "MeshRenderer", "parent": "Player"},
  {"action": "create_game_object", "name": "Collider", "parent": "Player"}
]
```
After creation, verify by re-reading bridge context. Check the command result for each action:
- `"success": true` for each action in the batch
- Error messages in `"error"` field if any action failed

### Verify Object Position
```json
[
  {"action": "set_position", "name": "Player", "x": 0, "y": 1, "z": 0}
]
```
Verify by checking the command result reports success. Follow up with a context refresh to confirm.

## Script Compilation Verification

### Check for Compiler Errors
Script compilation status is reflected in the Unity console. After writing C# scripts via file changes:

1. **Execute `refresh_assets`** to trigger recompilation:
```json
[
  {"action": "refresh_assets"}
]
```

2. **Check command result** — if compilation fails, Unity reports errors in the bridge response.

3. **Common compilation checks**:
   - Missing `using` directives
   - Type name mismatches
   - Missing method implementations for interfaces
   - Incorrect MonoBehaviour lifecycle method signatures

### Script Template Validation
When writing scripts, verify these patterns are correct before submitting:
```csharp
// Required for MonoBehaviour scripts
using UnityEngine;

public class MyScript : MonoBehaviour
{
    // Lifecycle methods — verify correct signatures
    void Start() { }
    void Update() { }
    void FixedUpdate() { }
    void OnDestroy() { }

    // Collision — verify correct parameter types
    void OnCollisionEnter(Collision collision) { }
    void OnTriggerEnter(Collider other) { }
}
```

## Build Verification

### Verify Scene Can Be Saved
```json
[
  {"action": "save_scenes"}
]
```
Check result for success. A failed save indicates scene corruption or missing references.

### Verify Scene Opens Without Errors
```json
[
  {"action": "open_scene", "path": "Assets/Scenes/MainScene.unity"}
]
```
Success = scene loads without errors. Failure = missing references, corrupted scene file, or invalid path.

## Asset Reference Validation

### Verify Assets Exist
```json
[
  {"action": "select_asset", "path": "Assets/Prefabs/Player.prefab"}
]
```
If the asset exists, the selection succeeds. If not, the command returns an error.

### Batch Asset Verification
```json
[
  {"action": "select_asset", "path": "Assets/Materials/PlayerMaterial.mat"},
  {"action": "select_asset", "path": "Assets/Textures/PlayerTexture.png"},
  {"action": "select_asset", "path": "Assets/Scripts/PlayerController.cs"}
]
```
Each action independently reports success or failure. Count errors across all actions.

### Verify Asset Refresh After File Changes
After applying file changes (scripts, prefabs, materials), always refresh:
```json
[
  {"action": "refresh_assets"}
]
```
This triggers Unity's AssetDatabase reimport. Check for compilation errors in the result.

## Component and Reference Checks

### Verify via Bridge Context
The bridge editor context includes:
- **Selected objects**: names, types, components
- **Scene hierarchy**: parent-child relationships
- **Project info**: active scene, project path

After making changes, request a context refresh and parse the returned metadata to verify:
- Objects exist in hierarchy
- Components are attached
- Properties have expected values

## Complete Verification Workflow

For any Unity task, follow this sequence:

1. **Execute commands** via `execute_command` with `unity_json` actions
2. **Check command results** — every action reports success/failure individually
3. **Refresh assets** if files were created or modified
4. **Verify scene state** by re-reading bridge context
5. **Save scenes** to confirm no corruption
6. **Check for compiler errors** if scripts were modified
7. **Report** PASS with evidence (action results, asset paths) or FAIL with specific errors
