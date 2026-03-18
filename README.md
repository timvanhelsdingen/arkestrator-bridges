# Arkestrator Bridges

Bridge plugins for connecting DCC applications to [Arkestrator](https://github.com/timvanhelsdingen/arkestrator).

## Available Bridges

| Bridge | Application | Type | Description |
|--------|------------|------|-------------|
| Godot | Godot 4.x | Per-project | GDScript plugin — context capture, file apply, command execution |
| Blender | Blender 4.2+ | User-level | Python addon — context capture, file apply, command execution |
| Houdini | Houdini 20+ | User-level | Python package — context capture, file apply, HScript/Python execution |
| ComfyUI | ComfyUI | Standalone | Python bridge — workflow submission, context, command execution |
| Unity | Unity 2022+ | Per-project | C# editor scripts — context capture, file apply, command execution |
| Unreal | UE5 | Engine-level | Python plugin — context capture, file apply, command execution |

## Installation

Bridges are installed through the Arkestrator desktop client:

1. Open Arkestrator → Settings → Bridge Plugins
2. Click "Check for Updates" to load the registry
3. Click "Install" on the bridge you need
4. Select the install location (auto-detected when possible)

## Manual Installation

Download the latest release and extract the bridge zip for your application.

## Contributing

To add a new bridge, submit a PR with:
1. Your bridge code in a new directory (e.g., `maya/`)
2. An entry in `registry.json`
3. Update the packaging step in `.github/workflows/release.yml`

## Release

To create a new bridge release:
```bash
git tag v0.1.45
git push origin --tags
```
