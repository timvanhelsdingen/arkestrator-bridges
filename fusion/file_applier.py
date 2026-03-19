"""
Arkestrator Fusion bridge — file applier.

Applies file changes (create/modify/delete) with path traversal protection.
"""

import base64
import os


def apply_file_changes(project_root, files, logger=None):
    """
    Apply a list of FileChange dicts to disk.

    Each change has: { path, content, action, binaryContent?, encoding? }

    Returns dict: { applied, skipped, errors }
    """
    log = logger or (lambda *a: None)
    applied = 0
    skipped = 0
    errors = []

    if not project_root:
        errors.append("No project root — cannot apply file changes")
        return {"applied": 0, "skipped": len(files), "errors": errors}

    project_root = os.path.realpath(project_root)

    for fc in files:
        rel_path = fc.get("path", "")
        action = fc.get("action", "create")
        content = fc.get("content", "")
        binary_content = fc.get("binaryContent")
        encoding = fc.get("encoding", "utf8")

        if not rel_path:
            skipped += 1
            errors.append("Empty path in file change")
            continue

        # Resolve and validate path
        abs_path = os.path.realpath(os.path.join(project_root, rel_path))
        if not abs_path.startswith(project_root + os.sep) and abs_path != project_root:
            skipped += 1
            errors.append(f"Path traversal blocked: {rel_path}")
            log(f"[file] BLOCKED path traversal: {rel_path} -> {abs_path}")
            continue

        try:
            if action == "delete":
                if os.path.exists(abs_path):
                    os.remove(abs_path)
                    applied += 1
                    log(f"[file] Deleted: {rel_path}")
                else:
                    skipped += 1
                    log(f"[file] Skip delete (not found): {rel_path}")

            elif action in ("create", "modify"):
                # Ensure parent directory exists
                parent = os.path.dirname(abs_path)
                if not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)

                if encoding == "base64" or binary_content:
                    data = base64.b64decode(binary_content or content)
                    with open(abs_path, "wb") as f:
                        f.write(data)
                else:
                    with open(abs_path, "w", encoding="utf-8", newline="") as f:
                        f.write(content)

                applied += 1
                log(f"[file] {action.title()}d: {rel_path}")

            else:
                skipped += 1
                errors.append(f"Unknown action '{action}' for {rel_path}")

        except Exception as exc:
            skipped += 1
            errors.append(f"{rel_path}: {exc}")
            log(f"[file] Error: {rel_path}: {exc}")

    return {"applied": applied, "skipped": skipped, "errors": errors}
