---
name: verification
description: "Verification & Quality Assessment patterns and best practices for blender"
metadata:
  program: blender
  category: bridge
  title: Verification & Quality Assessment
  keywords: ["blender", "verification", "validation", "testing", "quality"]
  source: bridge-repo
  auto-fetch: true
  priority: 60
---

# Blender Verification & Quality Assessment

## Render Comparison (Visual Verification)

When working toward a reference image or visual target, use programmatic render comparison to measure progress. Never claim visual quality without numeric scores.

### Iteration Strategy
- **During iteration**: render at 256x256 (or 512x512 max) for fast feedback
- **Final render**: full resolution only after scores meet threshold
- **Minimum cycles**: at least 5 render-compare iterations for complex creative tasks
- **Reference path**: keep constant throughout the task, never overwrite the reference
- **Intermediate renders**: discard after comparison, do not accumulate

### Render Comparison Template
```python
import bpy
import os
import struct
import math

def render_preview(output_path, width=256, height=256):
    """Render a preview at low resolution for comparison."""
    scene = bpy.context.scene
    # Save original settings
    orig_x = scene.render.resolution_x
    orig_y = scene.render.resolution_y
    orig_pct = scene.render.resolution_percentage
    orig_path = scene.render.filepath
    orig_fmt = scene.render.image_settings.file_format

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.filepath = output_path
    scene.render.image_settings.file_format = 'PNG'

    bpy.ops.render.render(write_still=True)

    # Restore
    scene.render.resolution_x = orig_x
    scene.render.resolution_y = orig_y
    scene.render.resolution_percentage = orig_pct
    scene.render.filepath = orig_path
    scene.render.image_settings.file_format = orig_fmt

    return os.path.exists(output_path) and os.path.getsize(output_path) > 0


def compare_images_bpy(ref_path, render_path):
    """Compare two images using Blender's built-in image loading.
    Returns a similarity score 0.0-1.0 based on histogram correlation
    and a pixel-level mean absolute error.
    """
    # Load images into Blender
    ref_img = bpy.data.images.load(ref_path, check_existing=False)
    rnd_img = bpy.data.images.load(render_path, check_existing=False)

    ref_pixels = list(ref_img.pixels)  # flat RGBA list
    rnd_pixels = list(rnd_img.pixels)

    ref_w, ref_h = ref_img.size[0], ref_img.size[1]
    rnd_w, rnd_h = rnd_img.size[0], rnd_img.size[1]

    # Clean up loaded images
    bpy.data.images.remove(ref_img)
    bpy.data.images.remove(rnd_img)

    if ref_w != rnd_w or ref_h != rnd_h:
        print(f"WARN: size mismatch ref={ref_w}x{ref_h} vs render={rnd_w}x{rnd_h}")
        return {"score": 0.0, "mae": 1.0, "error": "size_mismatch"}

    num_pixels = ref_w * ref_h

    # Calculate Mean Absolute Error (RGB only, skip alpha)
    total_diff = 0.0
    for i in range(num_pixels):
        base = i * 4
        for c in range(3):  # R, G, B
            total_diff += abs(ref_pixels[base + c] - rnd_pixels[base + c])
    mae = total_diff / (num_pixels * 3)

    # Build histograms (32 bins per channel)
    bins = 32
    ref_hist = [0] * (bins * 3)
    rnd_hist = [0] * (bins * 3)
    for i in range(num_pixels):
        base = i * 4
        for c in range(3):
            ref_bin = min(int(ref_pixels[base + c] * bins), bins - 1)
            rnd_bin = min(int(rnd_pixels[base + c] * bins), bins - 1)
            ref_hist[c * bins + ref_bin] += 1
            rnd_hist[c * bins + rnd_bin] += 1

    # Histogram correlation (Pearson)
    n = len(ref_hist)
    sum_r = sum(ref_hist)
    sum_d = sum(rnd_hist)
    sum_r2 = sum(x * x for x in ref_hist)
    sum_d2 = sum(x * x for x in rnd_hist)
    sum_rd = sum(ref_hist[i] * rnd_hist[i] for i in range(n))

    num = n * sum_rd - sum_r * sum_d
    den = math.sqrt((n * sum_r2 - sum_r ** 2) * (n * sum_d2 - sum_d ** 2))
    hist_corr = (num / den) if den > 0 else 0.0

    # Combined score: weight histogram correlation (global tone) and inverse MAE (pixel accuracy)
    pixel_score = max(0.0, 1.0 - mae * 4)  # MAE of 0.25 = score 0
    score = 0.5 * hist_corr + 0.5 * pixel_score

    return {
        "score": round(score, 4),
        "hist_correlation": round(hist_corr, 4),
        "pixel_score": round(pixel_score, 4),
        "mae": round(mae, 6),
    }


# --- Usage ---
ref = "/path/to/reference.png"
out = "/tmp/ark_verify_render.png"

if render_preview(out, width=256, height=256):
    result = compare_images_bpy(ref, out)
    print(f"VERIFY score={result['score']} hist={result['hist_correlation']} px={result['pixel_score']} mae={result['mae']}")
else:
    print("VERIFY FAIL: render produced no output")
```

### Score Interpretation
| Score | Meaning | Action |
|-------|---------|--------|
| > 0.85 | Good match | Proceed to final render or accept |
| 0.70 - 0.85 | Needs work | Identify largest differences, iterate |
| < 0.70 | Poor match | Major rework needed, re-examine approach |

### Self-Assessment Rules
- **NEVER** claim "excellent match" or "looks great" without a numeric score
- Always print `VERIFY score=X.XX` so results are parseable
- If score < 0.85 after 3 iterations, step back and re-evaluate the approach
- Compare against the SAME reference every iteration, not against previous renders

## Object & Scene Validation

### Verify Objects Exist
```python
import bpy

def verify_objects(expected_names):
    """Check that all expected objects exist in the scene."""
    missing = []
    found = []
    for name in expected_names:
        if name in bpy.data.objects:
            found.append(name)
        else:
            missing.append(name)
    print(f"VERIFY objects: {len(found)}/{len(expected_names)} found")
    if missing:
        print(f"VERIFY FAIL missing: {missing}")
    return len(missing) == 0

verify_objects(["Camera", "Light", "MyMesh"])
```

### Verify Materials Assigned
```python
import bpy

def verify_materials(obj_material_map):
    """Check objects have expected materials assigned.
    obj_material_map: dict of {obj_name: [material_names]}
    """
    errors = []
    for obj_name, expected_mats in obj_material_map.items():
        obj = bpy.data.objects.get(obj_name)
        if not obj:
            errors.append(f"{obj_name}: object not found")
            continue
        actual_mats = [slot.material.name for slot in obj.material_slots if slot.material]
        for mat_name in expected_mats:
            if mat_name not in actual_mats:
                errors.append(f"{obj_name}: missing material '{mat_name}'")
    if errors:
        for e in errors:
            print(f"VERIFY FAIL {e}")
    else:
        print(f"VERIFY PASS materials: all {len(obj_material_map)} objects correct")
    return len(errors) == 0

verify_materials({
    "MyMesh": ["BaseMaterial"],
    "Floor": ["FloorMat"],
})
```

### Verify Transforms
```python
import bpy
import math

def verify_transform(obj_name, expected_loc=None, expected_rot=None, expected_scale=None, tolerance=0.01):
    """Verify an object's transform is within tolerance."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        print(f"VERIFY FAIL {obj_name}: not found")
        return False

    errors = []
    if expected_loc:
        for i, axis in enumerate("XYZ"):
            if abs(obj.location[i] - expected_loc[i]) > tolerance:
                errors.append(f"loc.{axis} expected={expected_loc[i]} got={obj.location[i]:.4f}")

    if expected_rot:  # Euler in degrees
        for i, axis in enumerate("XYZ"):
            actual_deg = math.degrees(obj.rotation_euler[i])
            if abs(actual_deg - expected_rot[i]) > tolerance * 100:
                errors.append(f"rot.{axis} expected={expected_rot[i]} got={actual_deg:.2f}")

    if expected_scale:
        for i, axis in enumerate("XYZ"):
            if abs(obj.scale[i] - expected_scale[i]) > tolerance:
                errors.append(f"scale.{axis} expected={expected_scale[i]} got={obj.scale[i]:.4f}")

    if errors:
        for e in errors:
            print(f"VERIFY FAIL {obj_name}: {e}")
    else:
        print(f"VERIFY PASS {obj_name}: transform correct")
    return len(errors) == 0
```

### Verify Modifier Stack
```python
import bpy

def verify_modifiers(obj_name, expected_modifiers):
    """Check an object has expected modifiers in order.
    expected_modifiers: list of (name, type) tuples
    """
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        print(f"VERIFY FAIL {obj_name}: not found")
        return False

    actual = [(m.name, m.type) for m in obj.modifiers]
    errors = []
    for exp_name, exp_type in expected_modifiers:
        match = any(a_type == exp_type and (exp_name is None or a_name == exp_name)
                     for a_name, a_type in actual)
        if not match:
            errors.append(f"missing modifier {exp_name} ({exp_type})")

    if errors:
        for e in errors:
            print(f"VERIFY FAIL {obj_name}: {e}")
    else:
        print(f"VERIFY PASS {obj_name}: {len(expected_modifiers)} modifiers present")
    return len(errors) == 0
```

## Render Output Validation

### Verify Render File Exists
```python
import bpy
import os

def verify_render_output(filepath):
    """Check render output exists and is non-trivial."""
    if not os.path.exists(filepath):
        print(f"VERIFY FAIL render output not found: {filepath}")
        return False
    size = os.path.getsize(filepath)
    if size < 1000:  # Less than 1KB is suspicious for an image
        print(f"VERIFY FAIL render output too small ({size} bytes): {filepath}")
        return False
    print(f"VERIFY PASS render output exists: {filepath} ({size} bytes)")
    return True
```

## Complete Verification Workflow

For any visual task, follow this sequence:

1. **Set up scene** (objects, materials, lighting, camera)
2. **Validate scene state** (objects exist, materials assigned, transforms correct)
3. **Render preview** at 256x256
4. **Compare to reference** if one exists
5. **Iterate** on differences (adjust materials, lighting, geometry)
6. **Re-render and re-compare** until score > 0.85
7. **Final render** at full resolution only after preview passes
8. **Validate output file** (exists, non-zero size, correct format)
