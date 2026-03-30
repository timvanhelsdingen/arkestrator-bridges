---
name: verification
description: "Verification & Quality Assessment patterns and best practices for comfyui"
metadata:
  program: comfyui
  category: bridge
  title: Verification & Quality Assessment
  keywords: ["comfyui", "verification"]
  source: bridge-repo
  auto-fetch: true
  priority: 60
---

# ComfyUI Verification & Quality Assessment

## Workflow Completion Verification

### Check Workflow Status via History
```python
import json
import urllib.request

COMFYUI_URL = "http://127.0.0.1:8188"

def verify_workflow_complete(prompt_id):
    """Check if a queued workflow has completed successfully."""
    url = f"{COMFYUI_URL}/history/{prompt_id}"
    try:
        req = urllib.request.urlopen(url)
        history = json.loads(req.read())
    except Exception as e:
        print(f"VERIFY FAIL history: could not fetch {url} — {e}")
        return False

    if prompt_id not in history:
        print(f"VERIFY FAIL history: prompt_id {prompt_id} not found (still queued or expired)")
        return False

    entry = history[prompt_id]
    status = entry.get("status", {})
    completed = status.get("completed", False)
    status_str = status.get("status_str", "unknown")

    if not completed or status_str != "success":
        messages = status.get("messages", [])
        print(f"VERIFY FAIL workflow: status={status_str} completed={completed}")
        for msg in messages:
            if msg[0] == "execution_error":
                print(f"  error: {msg[1].get('exception_message', 'unknown')}")
        return False

    # Check outputs
    outputs = entry.get("outputs", {})
    output_count = sum(len(v.get("images", [])) for v in outputs.values())
    print(f"VERIFY PASS workflow: prompt_id={prompt_id} outputs={output_count}")
    return True
```

### Check Queue Status
```python
import json
import urllib.request

def verify_queue_empty():
    """Check that the ComfyUI queue has no pending items."""
    url = f"{COMFYUI_URL}/queue"
    try:
        req = urllib.request.urlopen(url)
        queue = json.loads(req.read())
    except Exception as e:
        print(f"VERIFY FAIL queue: could not fetch — {e}")
        return False

    pending = len(queue.get("queue_pending", []))
    running = len(queue.get("queue_running", []))

    if pending > 0 or running > 0:
        print(f"VERIFY INFO queue: pending={pending} running={running}")
        return False

    print("VERIFY PASS queue: empty")
    return True
```

## Output Image Validation

### Verify Output Files Exist
```python
import os

def verify_output_image(filepath, min_width=None, min_height=None):
    """Check output image exists, has valid size and optionally check dimensions."""
    if not os.path.exists(filepath):
        print(f"VERIFY FAIL output: not found {filepath}")
        return False

    size = os.path.getsize(filepath)
    if size < 1000:
        print(f"VERIFY FAIL output: too small ({size} bytes) {filepath}")
        return False

    # Check format from extension
    ext = os.path.splitext(filepath)[1].lower()
    valid_formats = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]
    if ext not in valid_formats:
        print(f"VERIFY WARN output: unexpected format {ext}")

    # Read PNG dimensions from header (no external deps)
    if ext == ".png" and (min_width or min_height):
        try:
            with open(filepath, "rb") as f:
                header = f.read(24)
                if header[:8] == b'\x89PNG\r\n\x1a\n':
                    import struct
                    w = struct.unpack(">I", header[16:20])[0]
                    h = struct.unpack(">I", header[20:24])[0]
                    if min_width and w < min_width:
                        print(f"VERIFY FAIL output: width={w} < min={min_width}")
                        return False
                    if min_height and h < min_height:
                        print(f"VERIFY FAIL output: height={h} < min={min_height}")
                        return False
                    print(f"VERIFY PASS output: {filepath} ({w}x{h}, {size} bytes)")
                    return True
        except Exception:
            pass

    print(f"VERIFY PASS output: {filepath} ({size} bytes)")
    return True


def verify_comfyui_outputs(output_dir, expected_count=1):
    """Scan ComfyUI output directory for recent images."""
    if not os.path.isdir(output_dir):
        print(f"VERIFY FAIL output dir: not found {output_dir}")
        return False

    images = [f for f in os.listdir(output_dir)
              if os.path.splitext(f)[1].lower() in (".png", ".jpg", ".jpeg", ".webp")]

    if len(images) < expected_count:
        print(f"VERIFY FAIL output: found {len(images)} images, expected {expected_count}")
        return False

    # Sort by modification time, check most recent
    images.sort(key=lambda f: os.path.getmtime(os.path.join(output_dir, f)), reverse=True)
    latest = images[:expected_count]
    for img in latest:
        path = os.path.join(output_dir, img)
        verify_output_image(path)

    print(f"VERIFY PASS outputs: {len(images)} images in {output_dir}")
    return True
```

## Model / Checkpoint Availability

### Verify Models Are Installed
```python
import os

def verify_models_available(comfyui_root, required_models):
    """Check that required model files exist in ComfyUI model directories.
    required_models: list of (subfolder, filename) e.g. [("checkpoints", "sd_xl_base_1.0.safetensors")]
    """
    errors = 0
    models_dir = os.path.join(comfyui_root, "models")

    for subfolder, filename in required_models:
        path = os.path.join(models_dir, subfolder, filename)
        if not os.path.exists(path):
            print(f"VERIFY FAIL model: not found {subfolder}/{filename}")
            errors += 1
        else:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb < 1:
                print(f"VERIFY WARN model: suspiciously small {subfolder}/{filename} ({size_mb:.1f}MB)")

    if errors == 0:
        print(f"VERIFY PASS models: {len(required_models)} models available")
    return errors == 0
```

### Check Models via API
```python
import json
import urllib.request

def verify_models_via_api(model_type, expected_names):
    """Query ComfyUI API for available models.
    model_type: "checkpoints", "loras", "vae", etc.
    """
    url = f"{COMFYUI_URL}/models/{model_type}"
    try:
        req = urllib.request.urlopen(url)
        available = json.loads(req.read())
    except Exception as e:
        print(f"VERIFY FAIL models API: {e}")
        return False

    errors = 0
    for name in expected_names:
        if name not in available:
            print(f"VERIFY FAIL model: '{name}' not in {model_type}")
            errors += 1

    if errors == 0:
        print(f"VERIFY PASS models: {len(expected_names)} {model_type} available")
    return errors == 0
```

## Node Configuration Validation

### Verify Workflow JSON Structure
```python
import json

def verify_workflow_structure(workflow_json):
    """Validate a workflow JSON has required nodes and connections."""
    if isinstance(workflow_json, str):
        workflow = json.loads(workflow_json)
    else:
        workflow = workflow_json

    errors = 0

    # Check required node types exist
    node_types = {nid: n.get("class_type", "") for nid, n in workflow.items()}

    required_types = ["CheckpointLoaderSimple", "KSampler", "VAEDecode"]
    has_output = any(t in ("SaveImage", "PreviewImage") for t in node_types.values())

    for req in required_types:
        if req not in node_types.values():
            print(f"VERIFY FAIL workflow: missing required node type {req}")
            errors += 1

    if not has_output:
        print("VERIFY FAIL workflow: no output node (SaveImage or PreviewImage)")
        errors += 1

    # Validate connections reference existing nodes
    for nid, node in workflow.items():
        inputs = node.get("inputs", {})
        for input_name, input_val in inputs.items():
            if isinstance(input_val, list) and len(input_val) == 2:
                ref_id = str(input_val[0])
                if ref_id not in workflow:
                    print(f"VERIFY FAIL workflow: node {nid} input '{input_name}' references missing node {ref_id}")
                    errors += 1

    if errors == 0:
        print(f"VERIFY PASS workflow: {len(workflow)} nodes, structure valid")
    return errors == 0
```

## Complete Verification Workflow

1. **Validate workflow JSON** (required nodes, valid connections)
2. **Verify models available** (checkpoints, LoRAs, VAEs needed by workflow)
3. **Submit workflow** and capture prompt_id
4. **Poll completion** via history API
5. **Verify output images** (exist, non-zero, correct dimensions/format)
6. **Report** PASS with output details or FAIL with specific errors
