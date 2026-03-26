"""Execute Python and TCL commands received from completed agent jobs."""

import traceback


def execute_commands(commands: list[dict]) -> dict:
    """Execute a list of CommandResult dicts.

    Each command has: language, script, description (optional).
    Supported languages: python/py, tcl, nk (Nuke script).
    Returns {"executed": int, "failed": int, "skipped": int, "errors": list[str]}.
    """
    import nuke

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
                    "nuke": nuke,
                }
                compiled = compile(script, f"<agent_command: {description}>", "exec")
                exec(compiled, exec_globals)
                executed += 1
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                errors.append(f"Command failed ({description}): {e}\n{tb}")
        elif language == "tcl":
            try:
                result = nuke.tcl(script)
                if result:
                    print(f"[ArkestratorBridge] TCL result ({description}): {result}")
                executed += 1
            except Exception as e:
                failed += 1
                errors.append(f"TCL failed ({description}): {e}")
        elif language == "nk":
            try:
                nuke.nodePaste(script)
                executed += 1
            except Exception as e:
                failed += 1
                errors.append(f"NK paste failed ({description}): {e}")
        else:
            skipped += 1
            errors.append(f"Unsupported language: {language} (skipped)")

    return {
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }
