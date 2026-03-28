---
title: Verification & Quality Assessment
category: bridge
---
# Godot Verification & Quality Assessment

## Headless Verification

Always run both checks before reporting a task as complete.

### Syntax Check (--check-only)
Validates all GDScript files parse without errors. Fast, no runtime needed.
```
run_headless_check(program="godot", args=["--headless", "--check-only", "--path", "<projectRoot>"], timeout=15000)
```
- Exit code 0 = all scripts parse OK
- Non-zero = syntax errors in one or more scripts
- Fix all syntax errors before proceeding to runtime check

### Runtime Check (--quit-after)
Launches the project headlessly for 5 seconds to catch runtime errors (missing resources, signal issues, null references).
```
run_headless_check(program="godot", args=["--headless", "--quit-after", "5", "--path", "<projectRoot>"], timeout=25000)
```
- Watch for ERROR and WARNING lines in output
- Crash or non-zero exit = runtime problem
- Timeout with no errors = likely OK

## Scene Tree Validation

### Verify Node Hierarchy
```gdscript
func run(editor: EditorInterface) -> void:
    var root = editor.get_edited_scene_root()
    if root == null:
        print("VERIFY FAIL: no scene open")
        return

    var expected = {
        "Player": "CharacterBody3D",
        "Player/CollisionShape3D": "CollisionShape3D",
        "Player/MeshInstance3D": "MeshInstance3D",
        "Player/Camera3D": "Camera3D",
        "WorldEnvironment": "WorldEnvironment",
        "DirectionalLight3D": "DirectionalLight3D",
    }

    var errors = 0
    for path in expected:
        var node = root.get_node_or_null(path)
        if node == null:
            print("VERIFY FAIL missing: " + path)
            errors += 1
        elif node.get_class() != expected[path]:
            print("VERIFY FAIL type: " + path + " expected=" + expected[path] + " got=" + node.get_class())
            errors += 1

    if errors == 0:
        print("VERIFY PASS scene tree: " + str(expected.size()) + " nodes correct")
    else:
        print("VERIFY FAIL scene tree: " + str(errors) + " errors")
```

### Verify Node Properties
```gdscript
func run(editor: EditorInterface) -> void:
    var root = editor.get_edited_scene_root()
    var node = root.get_node_or_null("Player")
    if node == null:
        print("VERIFY FAIL: Player not found")
        return

    var errors = 0

    # Check position
    var expected_pos = Vector3(0, 1, 0)
    if node.position.distance_to(expected_pos) > 0.01:
        print("VERIFY FAIL position: expected=" + str(expected_pos) + " got=" + str(node.position))
        errors += 1

    # Check collision shape exists and has a shape resource
    var col = node.get_node_or_null("CollisionShape3D")
    if col and col.shape == null:
        print("VERIFY FAIL: CollisionShape3D has no shape resource")
        errors += 1

    if errors == 0:
        print("VERIFY PASS Player: properties correct")
```

## Signal Connection Verification

### Check Signals Are Connected
```gdscript
func run(editor: EditorInterface) -> void:
    var root = editor.get_edited_scene_root()
    var errors = 0

    # Expected connections: [source_path, signal_name, target_path, method_name]
    var expected_signals = [
        ["Button", "pressed", ".", "_on_button_pressed"],
        ["Area3D", "body_entered", ".", "_on_area_body_entered"],
    ]

    for sig in expected_signals:
        var source = root.get_node_or_null(sig[0])
        if source == null:
            print("VERIFY FAIL signal source not found: " + sig[0])
            errors += 1
            continue

        var connections = source.get_signal_connection_list(sig[1])
        var found = false
        for conn in connections:
            var target = root.get_node_or_null(sig[2])
            if conn["callable"].get_method() == sig[3]:
                found = true
                break

        if not found:
            print("VERIFY FAIL signal: " + sig[0] + "." + sig[1] + " -> " + sig[3] + " not connected")
            errors += 1

    if errors == 0:
        print("VERIFY PASS signals: " + str(expected_signals.size()) + " connections verified")
```

## Script Attachment Verification

### Verify Scripts Are Attached
```gdscript
func run(editor: EditorInterface) -> void:
    var root = editor.get_edited_scene_root()
    var errors = 0

    var expected_scripts = {
        "Player": "res://scripts/player.gd",
        "Enemy": "res://scripts/enemy.gd",
    }

    for path in expected_scripts:
        var node = root.get_node_or_null(path)
        if node == null:
            print("VERIFY FAIL node not found: " + path)
            errors += 1
            continue

        var script = node.get_script()
        if script == null:
            print("VERIFY FAIL no script on: " + path)
            errors += 1
        elif script.resource_path != expected_scripts[path]:
            print("VERIFY FAIL script path: " + path + " expected=" + expected_scripts[path] + " got=" + script.resource_path)
            errors += 1

    if errors == 0:
        print("VERIFY PASS scripts: " + str(expected_scripts.size()) + " attachments correct")
```

## Resource Path Validation

### Verify Resources Exist
```gdscript
func run(editor: EditorInterface) -> void:
    var errors = 0
    var paths = [
        "res://scenes/main.tscn",
        "res://scripts/player.gd",
        "res://assets/textures/grass.png",
    ]

    for path in paths:
        if not ResourceLoader.exists(path):
            print("VERIFY FAIL resource not found: " + path)
            errors += 1

    if errors == 0:
        print("VERIFY PASS resources: " + str(paths.size()) + " paths valid")
    else:
        print("VERIFY FAIL resources: " + str(errors) + " missing")
```

### Verify Project Settings
```gdscript
func run(editor: EditorInterface) -> void:
    var errors = 0

    var main_scene = ProjectSettings.get_setting("application/run/main_scene")
    if main_scene == "" or main_scene == null:
        print("VERIFY FAIL: no main scene set")
        errors += 1
    elif not ResourceLoader.exists(main_scene):
        print("VERIFY FAIL: main scene does not exist: " + str(main_scene))
        errors += 1

    if errors == 0:
        print("VERIFY PASS project settings: main scene OK")
```

## Export / Build Verification

### Verify Export Presets Exist
```gdscript
func run(editor: EditorInterface) -> void:
    var path = "res://export_presets.cfg"
    if FileAccess.file_exists(path):
        print("VERIFY PASS export presets file exists")
    else:
        print("VERIFY WARN no export_presets.cfg — exports may not be configured")
```

## Complete Verification Workflow

For any Godot task, follow this sequence:

1. **Execute changes** via GDScript through `execute_command`
2. **Validate scene tree** (nodes exist, correct types, hierarchy intact)
3. **Validate properties** (transforms, resources, script attachments)
4. **Validate signals** if connections were created/modified
5. **Run syntax check** (`--check-only`) — must pass
6. **Run runtime check** (`--quit-after 5`) — must pass
7. **Report** PASS with evidence or FAIL with specific errors
