---
name: verification
description: "Verification & Quality Assessment patterns and best practices for houdini"
metadata:
  program: houdini
  category: bridge
  title: Verification & Quality Assessment
  keywords: ["houdini", "verification", "validation", "testing", "quality"]
  source: bridge-repo
  auto-fetch: true
  priority: 60
---

# Houdini Verification & Quality Assessment

## Node Network Validation

### Verify Nodes Exist and Have Correct Types
```python
import hou

def verify_nodes(expected):
    """Verify nodes exist with expected types.
    expected: dict of {path: type_name}
    """
    errors = 0
    for path, expected_type in expected.items():
        node = hou.node(path)
        if node is None:
            print(f"VERIFY FAIL missing: {path}")
            errors += 1
            continue
        actual_type = node.type().name()
        if actual_type != expected_type:
            print(f"VERIFY FAIL type: {path} expected={expected_type} got={actual_type}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS nodes: {len(expected)} nodes correct")
    else:
        print(f"VERIFY FAIL nodes: {errors} errors")
    return errors == 0

verify_nodes({
    "/obj/geo1": "geo",
    "/obj/geo1/box1": "box",
    "/obj/geo1/transform1": "xform",
    "/obj/geo1/output0": "output",
})
```

### Verify Node Connections
```python
import hou

def verify_connections(expected_connections):
    """Verify node wiring.
    expected_connections: list of (output_path, input_path, input_index)
    """
    errors = 0
    for out_path, in_path, in_idx in expected_connections:
        out_node = hou.node(out_path)
        in_node = hou.node(in_path)
        if out_node is None:
            print(f"VERIFY FAIL connection: source not found {out_path}")
            errors += 1
            continue
        if in_node is None:
            print(f"VERIFY FAIL connection: target not found {in_path}")
            errors += 1
            continue

        actual_input = in_node.input(in_idx)
        if actual_input is None or actual_input.path() != out_node.path():
            actual_name = actual_input.path() if actual_input else "None"
            print(f"VERIFY FAIL connection: {in_path}[{in_idx}] expected={out_path} got={actual_name}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS connections: {len(expected_connections)} wires correct")
    return errors == 0

verify_connections([
    ("/obj/geo1/box1", "/obj/geo1/transform1", 0),
    ("/obj/geo1/transform1", "/obj/geo1/output0", 0),
])
```

### Verify Parameter Values
```python
import hou

def verify_parameters(param_checks):
    """Verify parameter values.
    param_checks: list of (node_path, parm_name, expected_value, tolerance)
    """
    errors = 0
    for node_path, parm_name, expected, tol in param_checks:
        node = hou.node(node_path)
        if node is None:
            print(f"VERIFY FAIL param: node not found {node_path}")
            errors += 1
            continue

        parm = node.parm(parm_name)
        if parm is None:
            print(f"VERIFY FAIL param: {node_path}/{parm_name} not found")
            errors += 1
            continue

        actual = parm.eval()
        if isinstance(expected, (int, float)):
            if abs(actual - expected) > tol:
                print(f"VERIFY FAIL param: {node_path}/{parm_name} expected={expected} got={actual}")
                errors += 1
        elif str(actual) != str(expected):
            print(f"VERIFY FAIL param: {node_path}/{parm_name} expected={expected} got={actual}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS params: {len(param_checks)} parameters correct")
    return errors == 0

verify_parameters([
    ("/obj/geo1/box1", "sizex", 2.0, 0.001),
    ("/obj/geo1/box1", "sizey", 1.0, 0.001),
    ("/obj/geo1/transform1", "tx", 5.0, 0.001),
])
```

## Cook Status Checks

### Verify Nodes Cook Successfully
```python
import hou

def verify_cook_status(node_paths):
    """Force-cook nodes and check for errors."""
    errors = 0
    for path in node_paths:
        node = hou.node(path)
        if node is None:
            print(f"VERIFY FAIL cook: node not found {path}")
            errors += 1
            continue
        try:
            node.cook(force=True)
            warnings = node.warnings()
            cook_errors = node.errors()
            if cook_errors:
                print(f"VERIFY FAIL cook: {path} errors={cook_errors}")
                errors += 1
            elif warnings:
                print(f"VERIFY WARN cook: {path} warnings={warnings}")
            else:
                pass  # OK
        except hou.OperationFailed as e:
            print(f"VERIFY FAIL cook: {path} exception={e}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS cook: {len(node_paths)} nodes cooked OK")
    return errors == 0

verify_cook_status([
    "/obj/geo1/box1",
    "/obj/geo1/transform1",
    "/obj/geo1/output0",
])
```

## Geometry Validation

### Verify Point/Primitive Counts
```python
import hou

def verify_geometry(node_path, min_points=None, max_points=None,
                    min_prims=None, max_prims=None, expected_attribs=None):
    """Validate geometry output of a SOP node."""
    node = hou.node(node_path)
    if node is None:
        print(f"VERIFY FAIL geo: node not found {node_path}")
        return False

    geo = node.geometry()
    if geo is None:
        print(f"VERIFY FAIL geo: no geometry on {node_path}")
        return False

    errors = 0
    num_points = len(geo.points())
    num_prims = len(geo.prims())

    if min_points is not None and num_points < min_points:
        print(f"VERIFY FAIL geo: {node_path} points={num_points} < min={min_points}")
        errors += 1
    if max_points is not None and num_points > max_points:
        print(f"VERIFY FAIL geo: {node_path} points={num_points} > max={max_points}")
        errors += 1
    if min_prims is not None and num_prims < min_prims:
        print(f"VERIFY FAIL geo: {node_path} prims={num_prims} < min={min_prims}")
        errors += 1
    if max_prims is not None and num_prims > max_prims:
        print(f"VERIFY FAIL geo: {node_path} prims={num_prims} > max={max_prims}")
        errors += 1

    # Verify attributes exist
    if expected_attribs:
        for attr_name, attr_type in expected_attribs:
            # attr_type: "point", "prim", "vertex", "detail"
            attrib = None
            if attr_type == "point":
                attrib = geo.findPointAttrib(attr_name)
            elif attr_type == "prim":
                attrib = geo.findPrimAttrib(attr_name)
            elif attr_type == "vertex":
                attrib = geo.findVertexAttrib(attr_name)
            elif attr_type == "detail":
                attrib = geo.findGlobalAttrib(attr_name)
            if attrib is None:
                print(f"VERIFY FAIL geo: {node_path} missing {attr_type} attrib '{attr_name}'")
                errors += 1

    if errors == 0:
        print(f"VERIFY PASS geo: {node_path} points={num_points} prims={num_prims}")
    return errors == 0

verify_geometry(
    "/obj/geo1/output0",
    min_points=8,
    min_prims=6,
    expected_attribs=[("N", "point"), ("Cd", "point")],
)
```

## Output File Validation

### Verify Cached/Rendered Files Exist
```python
import hou
import os

def verify_output_files(file_patterns):
    """Check output files exist and are non-trivial.
    file_patterns: list of (path, min_size_bytes)
    """
    errors = 0
    for filepath, min_size in file_patterns:
        # Expand Houdini variables
        expanded = hou.text.expandString(filepath)
        if not os.path.exists(expanded):
            print(f"VERIFY FAIL output: not found {expanded}")
            errors += 1
            continue
        size = os.path.getsize(expanded)
        if size < min_size:
            print(f"VERIFY FAIL output: too small {expanded} ({size} bytes < {min_size})")
            errors += 1
        else:
            print(f"VERIFY OK output: {expanded} ({size} bytes)")

    if errors == 0:
        print(f"VERIFY PASS outputs: {len(file_patterns)} files valid")
    return errors == 0

verify_output_files([
    ("$HIP/geo/terrain.bgeo.sc", 1000),
    ("$HIP/render/beauty.exr", 5000),
])
```

## Render Output Verification

### Verify Render Completion
```python
import hou
import os
import glob

def verify_render_output(rop_path, expected_frames=None):
    """Verify a ROP node rendered successfully."""
    node = hou.node(rop_path)
    if node is None:
        print(f"VERIFY FAIL render: ROP not found {rop_path}")
        return False

    # Get output path from ROP
    output_parm = node.parm("vm_picture") or node.parm("sopoutput") or node.parm("picture")
    if output_parm is None:
        print(f"VERIFY FAIL render: no output path on {rop_path}")
        return False

    output_path = output_parm.eval()
    output_dir = os.path.dirname(output_path)

    if not os.path.isdir(output_dir):
        print(f"VERIFY FAIL render: output dir missing {output_dir}")
        return False

    # Check for rendered files (glob with frame pattern)
    pattern = output_path.replace("$F4", "*").replace("$F", "*")
    files = glob.glob(pattern)

    if len(files) == 0:
        print(f"VERIFY FAIL render: no output files matching {pattern}")
        return False

    if expected_frames and len(files) < expected_frames:
        print(f"VERIFY FAIL render: expected {expected_frames} frames, found {len(files)}")
        return False

    total_size = sum(os.path.getsize(f) for f in files)
    print(f"VERIFY PASS render: {len(files)} frames, {total_size} bytes total")
    return True
```

## Complete Verification Workflow

1. **Validate node network** (nodes exist, correct types, proper connections)
2. **Validate parameters** (values match intent)
3. **Force-cook** and check for errors/warnings
4. **Validate geometry** (point/prim counts, attributes present)
5. **Validate output files** if caching or rendering was involved
6. **Report** PASS with counts or FAIL with specific errors
