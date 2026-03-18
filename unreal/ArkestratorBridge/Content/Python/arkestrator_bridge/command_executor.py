"""Execute Python and UE console commands received from completed agent jobs."""

import traceback


def execute_commands(commands: list[dict]) -> dict:
    """Execute a list of command dicts.

    Each command has: language, script, description (optional).
    Supported languages: 'python'/'py' and 'ue_console'/'console'.
    Returns {"executed": int, "failed": int, "skipped": int, "errors": list[str]}.
    """
    import unreal

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
                    "unreal": unreal,
                }
                compiled = compile(script, f"<agent_command: {description}>", "exec")
                exec(compiled, exec_globals)
                executed += 1
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                errors.append(f"Python command failed ({description}): {e}\n{tb}")
        elif language in ("ue_console", "console"):
            try:
                world = unreal.EditorLevelLibrary.get_editor_world()
                if world:
                    unreal.SystemLibrary.execute_console_command(world, script)
                else:
                    # Fallback: try with None context
                    unreal.SystemLibrary.execute_console_command(None, script)
                executed += 1
            except Exception as e:
                failed += 1
                errors.append(f"Console command failed ({description}): {e}")
        else:
            skipped += 1
            errors.append(f"Unsupported language: {language} (skipped)")

    return {
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }
