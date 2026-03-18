"""Execute Python commands received from completed agent jobs."""

import traceback


def execute_commands(commands: list[dict]) -> dict:
    """Execute a list of CommandResult dicts.

    Each command has: language, script, description (optional).
    Only 'python'/'py' language is supported.
    Returns {"executed": int, "failed": int, "skipped": int, "errors": list[str]}.
    """
    import bpy

    executed = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

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

        if language not in ("python", "py"):
            skipped += 1
            errors.append(f"Unsupported language: {language} (skipped)")
            continue

        try:
            # Provide bpy and common modules in the exec namespace
            exec_globals = {
                "__builtins__": __builtins__,
                "bpy": bpy,
            }
            compiled = compile(script, f"<agent_command: {description}>", "exec")
            exec(compiled, exec_globals)
            executed += 1
        except Exception as e:
            failed += 1
            tb = traceback.format_exc()
            errors.append(f"Command failed ({description}): {e}\n{tb}")

    return {
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }
