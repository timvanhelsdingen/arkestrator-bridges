# Unity Bridge

| | |
|---|---|
| **Application** | Unity 2022+ |
| **Language** | C# (unity_json structured actions) |
| **Install Type** | Per-project (copied into Assets/) |
| **Status** | Experimental |
| **Version** | 0.1.54 |
| **Platforms** | Windows, macOS, Linux |

## What It Does

The Unity bridge consists of C# editor scripts that connect the Unity Editor to the Arkestrator server. It provides:

- **Context capture** -- pushes active scene hierarchy, selected objects/assets, project structure, and inspector state every ~3 seconds (hash-deduplicated)
- **Command execution** -- runs structured JSON actions via `execute_command(target="unity", language="unity_json", script="...")` (not raw C#)
- **File operations** -- creates, modifies, and deletes files with path traversal protection
- **Client file access** -- server-side agents can read any file on the client machine without syncing
- **Context menu** -- "Add to Arkestrator Context" integration in the editor

Commands use a structured `unity_json` format rather than raw C# for safety and consistency. Batch arrays are supported for related operations.

## Installation

### Via Arkestrator Desktop Client (Recommended)

1. Open **Arkestrator** and go to **Settings > Bridge Plugins**
2. Click **Check for Updates** to load the registry
3. Click **Install** on the Unity bridge
4. Select your Unity project directory

### Manual Installation

Download the latest `arkestrator-bridge-unity-v*.zip` from [Releases](https://github.com/timvanhelsdingen/arkestrator-bridges/releases) and copy `ArkestratorBridge/` into your Unity project's `Assets/` directory:

```
your-project/
  Assets/
    ArkestratorBridge/    <-- extract here
      Editor/
        ArkestratorBridge.cs
        ArkestratorCommandExecutor.cs
        ArkestratorFileApplier.cs
        ArkestratorWebSocketClient.cs
        ArkestratorMiniJson.cs
        ArkestratorBridge.Editor.asmdef
```

The editor scripts load automatically via Unity's assembly definition system. No manual enabling is required.

## Skills

The Unity bridge includes these skills (domain knowledge for AI agents):

| Skill | Description |
|-------|-------------|
| Scene Hierarchy | Scene structure, GameObject management, component patterns |
| Unity C# Scripting Patterns | MonoBehaviour lifecycle, coroutines, Unity API conventions |
| Prefabs & Assets | Prefab workflows, AssetDatabase operations, asset management |
| Verification | Quality assessment and validation patterns |

## Coordinator Summary

The coordinator script tells AI agents how to interact with Unity:

- Commands use `unity_json` structured actions only -- raw C# is not sent to the bridge
- Agents re-read bridge context after each batch to verify changes took effect
- Scene saves and `AssetDatabase.Refresh()` are triggered when applicable
- Changes are scoped to the request -- no broad scene restructuring
- Agents follow Unity naming conventions: PascalCase assets, organized subfolders under `Assets/`

## Notes

- The bridge auto-discovers the Arkestrator server via `~/.arkestrator/config.json`
- Experimental status -- core functionality works but may have rough edges
- Per-project install means the bridge must be copied into each Unity project's `Assets/` directory
- The bridge uses a minimal JSON parser (`ArkestratorMiniJson.cs`) to avoid external dependencies
- All editor scripts live under an `Editor/` assembly definition so they are excluded from game builds
