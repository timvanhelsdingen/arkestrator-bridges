"""Execute Python commands received from completed agent jobs."""

import traceback


def execute_commands(commands: list[dict]) -> dict:
    """Execute a list of CommandResult dicts.

    Each command has: language, script, description (optional).
    Only 'python'/'py'/'hscript' languages are supported.
    Returns {"executed": int, "failed": int, "skipped": int, "errors": list[str]}.
    """
    import hou

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

        if language in ("python", "py"):
            try:
                exec_globals = {
                    "__builtins__": __builtins__,
                    "hou": hou,
                }
                compiled = compile(script, f"<agent_command: {description}>", "exec")
                exec(compiled, exec_globals)
                executed += 1
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                errors.append(f"Command failed ({description}): {e}\n{tb}")
        elif language == "hscript":
            try:
                result = hou.hscript(script)
                if result[1]:  # stderr
                    errors.append(f"HScript warning ({description}): {result[1]}")
                executed += 1
            except Exception as e:
                failed += 1
                errors.append(f"HScript failed ({description}): {e}")
        else:
            skipped += 1
            errors.append(f"Unsupported language: {language} (skipped)")

    return {
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }
