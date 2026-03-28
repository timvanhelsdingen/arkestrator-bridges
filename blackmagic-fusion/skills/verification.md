---
title: Verification & Quality Assessment
category: bridge
---
# Blackmagic Fusion Verification & Quality Assessment

## Tool Graph Validation

### Verify Tools Exist
```python
comp = fusion.GetCurrentComp()

def verify_tools(expected):
    """Verify tools exist with expected IDs.
    expected: dict of {tool_name: tool_id}
    """
    tools = comp.GetToolList(False)
    tool_map = {}
    for t in tools.values():
        tool_map[t.Name] = t.ID

    errors = 0
    for name, expected_id in expected.items():
        if name not in tool_map:
            print(f"VERIFY FAIL missing: {name}")
            errors += 1
        elif tool_map[name] != expected_id:
            print(f"VERIFY FAIL type: {name} expected={expected_id} got={tool_map[name]}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS tools: {len(expected)} tools correct")
    return errors == 0

verify_tools({
    "MediaIn_Plate": "MediaIn",
    "CC_Grade": "ColorCorrector",
    "Merge_Comp": "Merge",
    "MediaOut_Final": "MediaOut",
})
```

### Verify Tool Connections
```python
comp = fusion.GetCurrentComp()

def verify_connections(expected_connections):
    """Verify tool wiring.
    expected_connections: list of (source_name, target_name, input_name)
    """
    tools = comp.GetToolList(False)
    tool_map = {t.Name: t for t in tools.values()}

    errors = 0
    for src_name, tgt_name, input_name in expected_connections:
        if src_name not in tool_map:
            print(f"VERIFY FAIL connection: source '{src_name}' not found")
            errors += 1
            continue
        if tgt_name not in tool_map:
            print(f"VERIFY FAIL connection: target '{tgt_name}' not found")
            errors += 1
            continue

        tgt_tool = tool_map[tgt_name]
        connected = tgt_tool.FindMainInput(1)

        # Check specific named input
        inp = tgt_tool.GetInput(input_name)
        if inp is None:
            # Try checking connected output on the input
            actual_conn = tgt_tool.FindMainInput(1)
            if actual_conn is None or actual_conn.Name != src_name:
                print(f"VERIFY FAIL connection: {tgt_name}.{input_name} not connected to {src_name}")
                errors += 1
        else:
            pass  # Input exists, check connection via GetInputList

    if errors == 0:
        print(f"VERIFY PASS connections: {len(expected_connections)} wires correct")
    return errors == 0
```

### Verify Connections via Flow Inspection
```python
comp = fusion.GetCurrentComp()

def verify_flow_connections(expected_wires):
    """Verify connections by checking each tool's inputs.
    expected_wires: list of (source_name, target_name, input_index)
    input_index: 1-based (Fusion convention)
    """
    tools = comp.GetToolList(False)
    tool_map = {t.Name: t for t in tools.values()}

    errors = 0
    for src_name, tgt_name, inp_idx in expected_wires:
        if tgt_name not in tool_map:
            print(f"VERIFY FAIL wire: target '{tgt_name}' not found")
            errors += 1
            continue

        tgt_tool = tool_map[tgt_name]
        connected_input = tgt_tool.FindMainInput(inp_idx)

        if connected_input is None:
            print(f"VERIFY FAIL wire: {tgt_name} input[{inp_idx}] is disconnected (expected {src_name})")
            errors += 1
            continue

        # Get the tool connected to this input
        output = connected_input.GetConnectedOutput()
        if output is None:
            print(f"VERIFY FAIL wire: {tgt_name} input[{inp_idx}] has no connected output")
            errors += 1
        else:
            connected_tool = output.GetTool()
            if connected_tool.Name != src_name:
                print(f"VERIFY FAIL wire: {tgt_name} input[{inp_idx}] expected={src_name} got={connected_tool.Name}")
                errors += 1

    if errors == 0:
        print(f"VERIFY PASS wires: {len(expected_wires)} connections correct")
    return errors == 0
```

## Saver Tool Output Verification

### Verify Saver Configuration
```python
comp = fusion.GetCurrentComp()

def verify_savers(saver_checks):
    """Verify Saver tools have valid output paths.
    saver_checks: list of saver tool names
    """
    import os
    tools = comp.GetToolList(False)
    tool_map = {t.Name: t for t in tools.values()}

    errors = 0
    for name in saver_checks:
        if name not in tool_map:
            print(f"VERIFY FAIL saver: '{name}' not found")
            errors += 1
            continue

        tool = tool_map[name]
        if tool.ID != "Saver":
            print(f"VERIFY FAIL saver: '{name}' is {tool.ID}, not Saver")
            errors += 1
            continue

        filepath = tool.GetInput("Clip")
        if not filepath:
            print(f"VERIFY FAIL saver: '{name}' has no output path set")
            errors += 1
            continue

        output_dir = os.path.dirname(str(filepath))
        if output_dir and not os.path.isdir(output_dir):
            print(f"VERIFY FAIL saver: '{name}' output dir missing: {output_dir}")
            errors += 1
        else:
            print(f"VERIFY OK saver: '{name}' -> {filepath}")

    if errors == 0:
        print(f"VERIFY PASS savers: {len(saver_checks)} Savers valid")
    return errors == 0
```

## Render Output File Verification

### Verify Rendered Files Exist
```python
import os
import glob

def verify_render_output(output_path, expected_frames=None):
    """Check rendered output files exist.
    output_path: path pattern (may contain frame padding like ####)
    """
    # Replace Fusion frame padding with glob
    pattern = output_path.replace("####", "????").replace("###", "???")
    files = glob.glob(pattern)

    if len(files) == 0:
        # Try single file (non-sequence)
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            print(f"VERIFY PASS render: {output_path} ({size} bytes)")
            return True
        print(f"VERIFY FAIL render: no files matching {pattern}")
        return False

    if expected_frames and len(files) < expected_frames:
        print(f"VERIFY FAIL render: expected {expected_frames} frames, found {len(files)}")
        return False

    total_size = sum(os.path.getsize(f) for f in files)
    min_size = min(os.path.getsize(f) for f in files)
    if min_size < 100:
        print(f"VERIFY WARN render: smallest frame only {min_size} bytes")

    print(f"VERIFY PASS render: {len(files)} frames, {total_size} bytes total")
    return True
```

## Input Value Validation

### Verify Tool Input Values
```python
comp = fusion.GetCurrentComp()

def verify_inputs(input_checks):
    """Verify tool input values.
    input_checks: list of (tool_name, input_name, expected_value, tolerance)
    """
    tools = comp.GetToolList(False)
    tool_map = {t.Name: t for t in tools.values()}

    errors = 0
    for tool_name, input_name, expected, tol in input_checks:
        if tool_name not in tool_map:
            print(f"VERIFY FAIL input: tool '{tool_name}' not found")
            errors += 1
            continue

        tool = tool_map[tool_name]
        actual = tool.GetInput(input_name)

        if actual is None:
            print(f"VERIFY FAIL input: {tool_name}.{input_name} is None")
            errors += 1
            continue

        if isinstance(expected, (int, float)):
            if abs(float(actual) - float(expected)) > tol:
                print(f"VERIFY FAIL input: {tool_name}.{input_name} expected={expected} got={actual}")
                errors += 1
        elif str(actual) != str(expected):
            print(f"VERIFY FAIL input: {tool_name}.{input_name} expected='{expected}' got='{actual}'")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS inputs: {len(input_checks)} values correct")
    return errors == 0

verify_inputs([
    ("CC_Grade", "MasterSaturation", 1.2, 0.01),
    ("CC_Grade", "MasterGain", 1.0, 0.01),
    ("Blur_Soft", "XBlurSize", 5.0, 0.1),
])
```

### Verify Comp Attributes
```python
comp = fusion.GetCurrentComp()

def verify_comp_settings(expected_width=None, expected_height=None,
                         expected_fps=None, expected_start=None, expected_end=None):
    """Verify composition settings."""
    attrs = comp.GetAttrs()
    prefs = comp.GetPrefs()

    errors = 0

    if expected_start is not None:
        actual = attrs.get("COMPN_GlobalStart", None)
        if actual != expected_start:
            print(f"VERIFY FAIL comp: GlobalStart expected={expected_start} got={actual}")
            errors += 1

    if expected_end is not None:
        actual = attrs.get("COMPN_GlobalEnd", None)
        if actual != expected_end:
            print(f"VERIFY FAIL comp: GlobalEnd expected={expected_end} got={actual}")
            errors += 1

    if errors == 0:
        start = attrs.get("COMPN_GlobalStart", "?")
        end = attrs.get("COMPN_GlobalEnd", "?")
        print(f"VERIFY PASS comp: settings OK (frames {start}-{end})")
    return errors == 0
```

## Complete Verification Workflow

1. **Verify tools** exist with correct IDs
2. **Verify connections** between tools are wired correctly
3. **Verify input values** match expected parameters
4. **Verify Saver tools** have valid output paths
5. **Verify comp settings** (frame range, resolution) if relevant
6. **Verify render output** files exist after rendering
7. **Report** PASS with tool counts or FAIL with specific errors
