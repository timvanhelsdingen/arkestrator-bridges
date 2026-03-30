---
name: verification
description: "Verification & Quality Assessment patterns and best practices for nuke"
metadata:
  program: nuke
  category: bridge
  title: Verification & Quality Assessment
  keywords: ["nuke", "verification"]
  source: bridge-repo
  auto-fetch: true
  priority: 60
---

# Nuke Verification & Quality Assessment

## Node Graph Validation

### Verify Nodes Exist
```python
import nuke

def verify_nodes(expected):
    """Verify nodes exist with expected class types.
    expected: dict of {node_name: class_type}
    """
    errors = 0
    for name, expected_class in expected.items():
        node = nuke.toNode(name)
        if node is None:
            print(f"VERIFY FAIL missing: {name}")
            errors += 1
            continue
        actual_class = node.Class()
        if actual_class != expected_class:
            print(f"VERIFY FAIL type: {name} expected={expected_class} got={actual_class}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS nodes: {len(expected)} nodes correct")
    return errors == 0

verify_nodes({
    "Read1": "Read",
    "Grade1": "Grade",
    "Merge1": "Merge2",
    "Write1": "Write",
})
```

### Verify Node Connections
```python
import nuke

def verify_connections(expected_connections):
    """Verify node wiring.
    expected_connections: list of (source_name, target_name, input_index)
    """
    errors = 0
    for src_name, tgt_name, inp_idx in expected_connections:
        src = nuke.toNode(src_name)
        tgt = nuke.toNode(tgt_name)

        if src is None:
            print(f"VERIFY FAIL connection: source '{src_name}' not found")
            errors += 1
            continue
        if tgt is None:
            print(f"VERIFY FAIL connection: target '{tgt_name}' not found")
            errors += 1
            continue

        actual_input = tgt.input(inp_idx)
        if actual_input is None:
            print(f"VERIFY FAIL connection: {tgt_name}[{inp_idx}] has no input (expected {src_name})")
            errors += 1
        elif actual_input.name() != src_name:
            print(f"VERIFY FAIL connection: {tgt_name}[{inp_idx}] expected={src_name} got={actual_input.name()}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS connections: {len(expected_connections)} wires correct")
    return errors == 0

verify_connections([
    ("Read1", "Grade1", 0),      # Read feeds into Grade
    ("Grade1", "Merge1", 1),     # Grade into Merge A input
    ("Read2", "Merge1", 0),      # Read2 into Merge B input
    ("Merge1", "Write1", 0),     # Merge into Write
])
```

## Read/Write Node File Path Verification

### Verify Read Node Paths
```python
import nuke
import os

def verify_read_paths(read_nodes):
    """Check Read nodes have valid file paths.
    read_nodes: list of node names
    """
    errors = 0
    for name in read_nodes:
        node = nuke.toNode(name)
        if node is None:
            print(f"VERIFY FAIL read: node '{name}' not found")
            errors += 1
            continue

        filepath = node["file"].value()
        if not filepath:
            print(f"VERIFY FAIL read: '{name}' has empty file path")
            errors += 1
            continue

        # Evaluate any TCL expressions
        evaluated = node["file"].evaluate()

        # Check first frame exists (for sequences, check frame 1 or first/last)
        first = node["first"].value()
        last = node["last"].value()

        # Replace frame pattern for existence check
        check_path = evaluated
        if os.path.exists(check_path):
            print(f"VERIFY OK read: '{name}' -> {filepath} (frames {int(first)}-{int(last)})")
        else:
            print(f"VERIFY WARN read: '{name}' file not found on disk: {check_path}")

    if errors == 0:
        print(f"VERIFY PASS reads: {len(read_nodes)} Read nodes have paths set")
    return errors == 0
```

### Verify Write Node Paths
```python
import nuke
import os

def verify_write_paths(write_nodes):
    """Check Write nodes have valid output paths with existing directories.
    write_nodes: list of node names
    """
    errors = 0
    for name in write_nodes:
        node = nuke.toNode(name)
        if node is None:
            print(f"VERIFY FAIL write: node '{name}' not found")
            errors += 1
            continue

        filepath = node["file"].value()
        if not filepath:
            print(f"VERIFY FAIL write: '{name}' has empty file path")
            errors += 1
            continue

        # Check output directory exists
        evaluated = node["file"].evaluate()
        output_dir = os.path.dirname(evaluated)
        if output_dir and not os.path.isdir(output_dir):
            print(f"VERIFY FAIL write: '{name}' output dir missing: {output_dir}")
            errors += 1
        else:
            file_type = node["file_type"].value()
            print(f"VERIFY OK write: '{name}' -> {filepath} (format={file_type})")

    if errors == 0:
        print(f"VERIFY PASS writes: {len(write_nodes)} Write nodes valid")
    return errors == 0
```

## Render Output Verification

### Verify Rendered Frames Exist
```python
import nuke
import os
import glob

def verify_render_output(write_node_name, expected_frames=None):
    """Check rendered output from a Write node."""
    node = nuke.toNode(write_node_name)
    if node is None:
        print(f"VERIFY FAIL render: node '{write_node_name}' not found")
        return False

    filepath = node["file"].evaluate()
    output_dir = os.path.dirname(filepath)

    if not os.path.isdir(output_dir):
        print(f"VERIFY FAIL render: output dir missing {output_dir}")
        return False

    # Glob for rendered frames
    # Replace frame number patterns with wildcard
    import re
    pattern = re.sub(r'%0\d+d|####|#+', '*', filepath)
    files = glob.glob(pattern)

    if len(files) == 0:
        print(f"VERIFY FAIL render: no output files matching {pattern}")
        return False

    if expected_frames and len(files) < expected_frames:
        print(f"VERIFY FAIL render: expected {expected_frames} frames, found {len(files)}")
        return False

    # Check files are non-trivial
    min_size = min(os.path.getsize(f) for f in files)
    total_size = sum(os.path.getsize(f) for f in files)
    if min_size < 100:
        print(f"VERIFY WARN render: smallest frame is only {min_size} bytes")

    print(f"VERIFY PASS render: {len(files)} frames, total {total_size} bytes")
    return True
```

## Expression / TCL Evaluation Checks

### Verify Expressions Evaluate
```python
import nuke

def verify_expressions(expression_checks):
    """Verify TCL/Python expressions on knobs evaluate without errors.
    expression_checks: list of (node_name, knob_name)
    """
    errors = 0
    for node_name, knob_name in expression_checks:
        node = nuke.toNode(node_name)
        if node is None:
            print(f"VERIFY FAIL expr: node '{node_name}' not found")
            errors += 1
            continue

        knob = node[knob_name]
        if not knob.hasExpression():
            continue  # No expression, skip

        try:
            value = knob.value()
            print(f"VERIFY OK expr: {node_name}.{knob_name} = {value}")
        except Exception as e:
            print(f"VERIFY FAIL expr: {node_name}.{knob_name} error: {e}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS expressions: {len(expression_checks)} knobs OK")
    return errors == 0
```

## Knob Value Validation

### Verify Knob Values
```python
import nuke

def verify_knob_values(knob_checks):
    """Verify knob values match expected.
    knob_checks: list of (node_name, knob_name, expected_value, tolerance)
    """
    errors = 0
    for node_name, knob_name, expected, tol in knob_checks:
        node = nuke.toNode(node_name)
        if node is None:
            print(f"VERIFY FAIL knob: node '{node_name}' not found")
            errors += 1
            continue

        try:
            actual = node[knob_name].value()
        except NameError:
            print(f"VERIFY FAIL knob: {node_name}.{knob_name} not found")
            errors += 1
            continue

        if isinstance(expected, (int, float)):
            if abs(float(actual) - float(expected)) > tol:
                print(f"VERIFY FAIL knob: {node_name}.{knob_name} expected={expected} got={actual}")
                errors += 1
        elif str(actual) != str(expected):
            print(f"VERIFY FAIL knob: {node_name}.{knob_name} expected='{expected}' got='{actual}'")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS knobs: {len(knob_checks)} values correct")
    return errors == 0

verify_knob_values([
    ("Grade1", "multiply", 1.5, 0.01),
    ("Grade1", "channels", "rgb", 0),
    ("Blur1", "size", 10.0, 0.1),
])
```

## Frame Range Validation

### Verify Project Frame Range
```python
import nuke

def verify_frame_range(expected_first=None, expected_last=None):
    """Check project frame range matches expected values."""
    root = nuke.root()
    first = int(root["first_frame"].value())
    last = int(root["last_frame"].value())

    errors = 0
    if expected_first is not None and first != expected_first:
        print(f"VERIFY FAIL frame range: first expected={expected_first} got={first}")
        errors += 1
    if expected_last is not None and last != expected_last:
        print(f"VERIFY FAIL frame range: last expected={expected_last} got={last}")
        errors += 1

    if errors == 0:
        print(f"VERIFY PASS frame range: {first}-{last}")
    return errors == 0
```

## Complete Verification Workflow

1. **Verify nodes** exist with correct types
2. **Verify connections** between nodes are wired correctly
3. **Verify knob values** match expected parameters
4. **Verify expressions** evaluate without errors
5. **Verify Read/Write paths** are set and directories exist
6. **Verify frame ranges** on Read/Write nodes
7. **Verify render output** if rendering was performed
8. **Report** PASS with node counts or FAIL with specific errors
