# Unity Bridge - Module Documentation

## Overview
Unity Editor bridge plugin that connects to Arkestrator via WebSocket and acts as a thin execution endpoint. It pushes editor context, accepts bridge commands, applies file changes, and executes structured Unity editor actions.

## Directory Structure
```
bridges/unity/
├── MODULE.md
└── ArkestratorBridge/
    └── Editor/
        ├── ArkestratorBridge.Editor.asmdef
        ├── ArkestratorBridge.cs
        ├── ArkestratorWebSocketClient.cs
        ├── ArkestratorCommandExecutor.cs
        ├── ArkestratorFileApplier.cs
        └── ArkestratorMiniJson.cs
```

Repository utility script:
- `scripts/install-unity-bridge.ps1` - copies `bridges/unity/ArkestratorBridge` into a Unity project's `Assets/ArkestratorBridge` path.

## Key Components

### ArkestratorBridge.cs
- Editor entry point (`[InitializeOnLoad]`)
- Auto-connect on startup from `~/.arkestrator/config.json`
- Sends standard bridge identity query params (`program=unity`, `bridgeVersion`, `programVersion`, `workerName`, `machineId`, `projectPath`)
- Follows client-owned shared `workerName` and `machineId` from `~/.arkestrator/config.json` and reconnects when shared auth/identity changes while the editor is connected
- Pushes `bridge_editor_context` every ~3 seconds when context hash changes
- Sends `bridge_context_item_add` from Unity menu actions:
  - `Arkestrator/Add Current Selection to Arkestrator Context`
  - `Assets/Add to Arkestrator Context`
  - `GameObject/Add to Arkestrator Context`
  - `CONTEXT/Component/Add to Arkestrator Context`
  - `CONTEXT/Transform/Add to Arkestrator Context`
- Handles incoming messages:
  - `job_complete`
  - `bridge_command`
  - `bridge_command_result`
  - `error`

### ArkestratorWebSocketClient.cs
- `ClientWebSocket` transport with reconnect backoff (3s -> 30s)
- Thread-safe send queue + main-thread event queue
- Poll-based dispatch from Unity editor update loop

### ArkestratorCommandExecutor.cs
- Executes command payloads with `language="unity_json"` (or `"json"`)
- Supported actions:
  - `ping`
  - `create_game_object`
  - `delete_game_object`
  - `set_position`
  - `open_scene`
  - `save_scenes`
  - `select_asset`
  - `refresh_assets`
- Uses editor-safe APIs (`Undo`, `EditorSceneManager`, `AssetDatabase`, `Selection`)

### ArkestratorFileApplier.cs
- Applies file create/modify/delete results under project root
- Supports UTF-8 text and base64 binary writes
- Path traversal protection via project-root bounded resolution

### ArkestratorMiniJson.cs
- Lightweight JSON parser/serializer used for bridge payloads and command parsing

## Config Auto-Discovery
- Reads `~/.arkestrator/config.json`
- Supports both camelCase and PascalCase keys:
  - `serverUrl` / `ServerUrl`
  - `wsUrl` / `WsUrl`
  - `apiKey` / `ApiKey`
  - `workerName` / `WorkerName`
  - `machineId` / `MachineId`

## Unity Menu
- `Arkestrator/Connect`
- `Arkestrator/Disconnect`
- `Arkestrator/Push Editor Context Now`
- `Arkestrator/Add Current Selection to Arkestrator Context`
- `Assets/Add to Arkestrator Context`
- `GameObject/Add to Arkestrator Context`
- `Component inspector context menu -> Add to Arkestrator Context`
- `Transform component context menu -> Add to Arkestrator Context`

## Install Notes
1. Copy `bridges/unity/ArkestratorBridge/` into your Unity project.
2. Keep scripts under an `Editor/` folder (already structured this way).
3. Ensure the Arkestrator desktop client has written `~/.arkestrator/config.json` (login once).
4. Open Unity Editor; the bridge auto-connects on load (or use the menu to connect manually).

PowerShell installer (from repo root):
```powershell
.\scripts\install-unity-bridge.ps1 -UnityProjectPath "C:\Path\To\UnityProject"
```
