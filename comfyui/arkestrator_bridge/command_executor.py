"""Execute commands received from Arkestrator.

Supports two command languages:
- "workflow" / "comfyui": Submit a ComfyUI workflow JSON and poll for results
- "python" / "py": Execute arbitrary Python code via exec()
"""

import base64
import json
import traceback


def _infer_kind(filename: str, hinted_kind: str) -> str:
    """Infer artifact kind from filename extension with fallback to hinted kind."""
    name = str(filename or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".exr")):
        return "image"
    if name.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v")):
        return "video"
    if name.endswith(".gif"):
        return "gif"
    if name.endswith((".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac")):
        return "audio"
    return hinted_kind or "file"


def _iter_node_artifacts(node_output: dict):
    """Yield artifact tuples as (kind_hint, artifact_info)."""
    pairs = [
        ("images", "image"),
        ("videos", "video"),
        ("gifs", "gif"),
        ("audio", "audio"),
        ("files", "file"),
    ]
    for key, kind in pairs:
        values = node_output.get(key, [])
        if not isinstance(values, list):
            continue
        for info in values:
            if isinstance(info, dict):
                yield kind, info


def execute_commands(commands: list[dict], comfyui_client=None) -> dict:
    """Execute a list of command dicts.

    Each command has: language, script, description (optional).
    Returns {"executed": int, "failed": int, "skipped": int, "errors": list[str], "outputs": list[dict]}.
    """
    executed = 0
    failed = 0
    skipped = 0
    errors: list[str] = []
    outputs: list[dict] = []

    for cmd in commands:
        if not isinstance(cmd, dict):
            skipped += 1
            continue

        language = str(cmd.get("language", "")).lower()
        script = str(cmd.get("script", ""))
        description = str(cmd.get("description", ""))

        if not script.strip():
            skipped += 1
            continue

        if language in ("workflow", "comfyui"):
            result = _execute_workflow(script, description, comfyui_client)
            if result["success"]:
                executed += 1
                outputs.extend(result.get("outputs", []))
            else:
                failed += 1
                errors.append(result["error"])

        elif language in ("python", "py"):
            try:
                exec_globals = {"__builtins__": __builtins__}
                if comfyui_client:
                    exec_globals["comfyui"] = comfyui_client
                compiled = compile(script, f"<agent_command: {description}>", "exec")
                exec(compiled, exec_globals)
                executed += 1
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                errors.append(f"Command failed ({description}): {e}\n{tb}")

        else:
            skipped += 1
            errors.append(f"Unsupported language: {language} (skipped)")

    return {
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "outputs": outputs,
    }


def _execute_workflow(workflow_json: str, description: str, comfyui_client) -> dict:
    """Submit a ComfyUI workflow and wait for results."""
    if comfyui_client is None:
        return {"success": False, "error": f"ComfyUI client not available ({description})"}

    try:
        workflow = json.loads(workflow_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid workflow JSON ({description}): {e}"}

    try:
        prompt_id = comfyui_client.submit_workflow(workflow)
        if not prompt_id:
            return {"success": False, "error": f"ComfyUI returned no prompt_id ({description})"}

        result = comfyui_client.poll_result(prompt_id, timeout=300.0)

        # Extract output artifacts
        outputs = []
        for node_id, node_output in result.get("outputs", {}).items():
            for kind_hint, artifact_info in _iter_node_artifacts(node_output):
                filename = artifact_info.get("filename", "")
                subfolder = artifact_info.get("subfolder", "")
                artifact_type = artifact_info.get("type", "output")

                try:
                    artifact_bytes = comfyui_client.get_image(filename, subfolder, artifact_type)
                    outputs.append({
                        "kind": _infer_kind(filename, kind_hint),
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": artifact_type,
                        "size": len(artifact_bytes),
                        "base64": base64.b64encode(artifact_bytes).decode("ascii"),
                    })
                except Exception as e:
                    errors_msg = f"Failed to fetch artifact {filename}: {e}"
                    print(f"[ArkestratorBridge] {errors_msg}")

        return {"success": True, "outputs": outputs}

    except TimeoutError:
        return {"success": False, "error": f"Workflow timed out ({description})"}
    except Exception as e:
        return {"success": False, "error": f"Workflow execution failed ({description}): {e}"}
