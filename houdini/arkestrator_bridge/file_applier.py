"""Apply file changes from completed job results to disk."""

import base64
import os


def apply_file_changes(changes: list[dict], project_root: str = "") -> dict:
    """Apply a list of FileChange dicts to the filesystem.

    Each change has: path, content, action (create/modify/delete).
    Returns {"applied": int, "failed": int, "errors": list[str]}.
    """
    if not project_root:
        try:
            import hou
            hip = hou.hipFile.path()
            if hip:
                project_root = os.path.dirname(hip)
        except Exception:
            pass
        if not project_root:
            project_root = os.getcwd()

    applied = 0
    failed = 0
    errors: list[str] = []

    for entry in changes:
        if not isinstance(entry, dict):
            failed += 1
            continue

        path = str(entry.get("path", "")).strip()
        content = str(entry.get("content", ""))
        action = str(entry.get("action", "modify")).strip().lower()

        if not path:
            failed += 1
            errors.append("Empty path in file change")
            continue

        try:
            abs_path = _resolve_path(path, project_root)
        except ValueError as e:
            failed += 1
            errors.append(str(e))
            continue

        if action in ("create", "modify"):
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                encoding = str(entry.get("encoding", "utf8")).strip().lower()
                binary_content = entry.get("binaryContent")
                if encoding == "base64" and binary_content:
                    with open(abs_path, "wb") as f:
                        f.write(base64.b64decode(binary_content))
                else:
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(content)
                applied += 1
            except OSError as e:
                failed += 1
                errors.append(f"Write failed for {path}: {e}")
        elif action == "delete":
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                applied += 1
            except OSError as e:
                failed += 1
                errors.append(f"Delete failed for {path}: {e}")
        else:
            failed += 1
            errors.append(f"Unknown action '{action}' for {path}")

    return {"applied": applied, "failed": failed, "errors": errors}


def _resolve_path(path: str, project_root: str) -> str:
    """Resolve a file path to an absolute path within the project root.

    Uses realpath to resolve symlinks and prevent path traversal attacks.
    Raises ValueError if the resolved path escapes the project root.
    """
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        resolved = os.path.realpath(os.path.join(project_root, path))

    if project_root:
        root_real = os.path.realpath(project_root)
        if not resolved.startswith(root_real + os.sep) and resolved != root_real:
            raise ValueError(f"Path escapes project root: {path}")

    return resolved
