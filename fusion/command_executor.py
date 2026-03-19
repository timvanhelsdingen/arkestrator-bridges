"""
Arkestrator Fusion bridge — command executor.

Executes Python and Lua scripts inside the Fusion runtime.
Supports both standalone Fusion and DaVinci Resolve's Fusion page.
"""

import traceback

# Languages this bridge supports
SUPPORTED_LANGUAGES = {"python", "py", "lua", "fusion_lua"}


def execute_commands(fusion_app, comp, commands, logger=None):
    """
    Execute a list of CommandResult dicts inside Fusion.

    Each command has: { language, script, description? }

    Returns dict: { executed, failed, skipped, errors, success }
    """
    log = logger or (lambda *a: None)
    executed = 0
    failed = 0
    skipped = 0
    errors = []

    for cmd in commands:
        language = (cmd.get("language") or "").lower().strip()
        script = cmd.get("script", "")
        description = cmd.get("description", "")

        if language not in SUPPORTED_LANGUAGES:
            skipped += 1
            errors.append(f"Unsupported language '{language}' (supported: {', '.join(sorted(SUPPORTED_LANGUAGES))})")
            log(f"[exec] Skipped: unsupported language '{language}'")
            continue

        if not script.strip():
            skipped += 1
            errors.append("Empty script")
            continue

        log(f"[exec] Running {language}: {description or script[:60]}...")

        try:
            if language in ("lua", "fusion_lua"):
                _execute_lua(fusion_app, comp, script)
            else:
                _execute_python(fusion_app, comp, script)
            executed += 1
            log(f"[exec] Success: {description or 'script'}")
        except Exception as exc:
            failed += 1
            tb = traceback.format_exc()
            error_msg = f"{description or 'script'}: {exc}\n{tb}"
            errors.append(error_msg)
            log(f"[exec] Failed: {error_msg}")

    return {
        "success": failed == 0 and skipped < len(commands),
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
    }


def _execute_python(fusion_app, comp, script):
    """
    Execute a Python script with fusion/comp in scope.

    The script gets these globals:
      - fusion / fu: the Fusion application
      - comp: the current composition
      - tool: the active tool (if any)
    """
    scope = {
        "fusion": fusion_app,
        "fu": fusion_app,
        "comp": comp,
        "__builtins__": __builtins__,
    }
    if comp:
        try:
            active = comp.ActiveTool
            if active:
                scope["tool"] = active
        except Exception:
            pass

    exec(compile(script, "<arkestrator>", "exec"), scope)


def _execute_lua(fusion_app, comp, script):
    """
    Execute a Lua script via Fusion's built-in Lua execution.

    Uses comp:Execute() which runs Lua in Fusion's script environment.
    """
    if comp is None:
        raise RuntimeError("No active composition for Lua execution")

    # comp:Execute() runs Lua code in the composition's script context
    # It has access to fusion, comp, and all Fusion Lua APIs
    result = comp.Execute(script)
    # Execute() returns None on success in most Fusion builds
    if result is False:
        raise RuntimeError("Lua script execution returned failure")
