"""Execute Python and TCL commands received from completed agent jobs.

Maintains a persistent execution context across commands within a session,
so node references and variables survive between execute_command calls.
Includes node graph synchronization to work around Nuke NC API quirks.
"""

import sys
import traceback
import io

# ---------------------------------------------------------------------------
# Persistent session state
# ---------------------------------------------------------------------------

_session_globals: dict | None = None


def _ensure_session() -> dict:
    """Return the persistent exec globals dict, creating it if needed.

    The session dict persists across execute_commands() calls so that
    node references and variables created in one command are available
    in subsequent commands within the same job.
    """
    global _session_globals
    if _session_globals is None:
        reset_session()
    return _session_globals  # type: ignore[return-value]


def reset_session() -> None:
    """Reset the persistent execution context.

    Called automatically when a new job starts or when the bridge reconnects,
    so stale references from a previous job don't bleed through.
    """
    global _session_globals
    import nuke

    _session_globals = {
        "__builtins__": __builtins__,
        "nuke": nuke,
    }

    # Inject helper utilities into the session
    _session_globals["_ark_sync_graph"] = _sync_node_graph
    _session_globals["_ark_all_nodes"] = _reliable_all_nodes
    _session_globals["_ark_find_node"] = _reliable_find_node


# ---------------------------------------------------------------------------
# Node graph synchronization helpers
# ---------------------------------------------------------------------------

def _sync_node_graph() -> None:
    """Force Nuke to synchronize its internal node graph state.

    Call this before any node enumeration to ensure allNodes() and toNode()
    return consistent results. This works around Nuke NC's tendency to return
    incomplete node lists when the graph hasn't been fully realized.
    """
    import nuke

    try:
        # Force Nuke to update its internal state
        nuke.root().begin()
        nuke.root().end()
    except Exception:
        pass

    try:
        # updateUI forces a full graph refresh in GUI mode
        nuke.updateUI()
    except Exception:
        pass

    try:
        # Touch the root node to force script state sync
        _ = nuke.root()["name"].value()
    except Exception:
        pass


def _reliable_all_nodes(class_filter: str = "", group=None) -> list:
    """Return all nodes with graph sync, working around NC enumeration bugs.

    For best results, use a class filter (e.g., "Read", "Write", "Merge2").
    Unfiltered allNodes() in Nuke NC can return inconsistent results.

    Args:
        class_filter: Optional node class name to filter by.
        group: Optional group node to search within (default: root).

    Returns:
        List of nuke.Node objects.
    """
    import nuke

    _sync_node_graph()

    try:
        if group is not None:
            group.begin()

        if class_filter:
            nodes = nuke.allNodes(class_filter)
        else:
            # Multi-pass enumeration: collect by known classes for reliability,
            # then fill gaps with a final unfiltered call
            seen_names = set()
            all_nodes = []

            # Common node classes in compositing workflows
            common_classes = [
                "Read", "Write", "Viewer", "Merge2", "Grade", "ColorCorrect",
                "Shuffle", "Shuffle2", "Blur", "Defocus", "Transform",
                "Reformat", "Crop", "Roto", "RotoPaint", "Tracker4",
                "Constant", "CheckerBoard", "Noise", "ColorWheel",
                "Dot", "BackdropNode", "StickyNote", "NoOp",
                "Premult", "Unpremult", "Copy", "ShuffleCopy",
                "Keyer", "Primatte", "IBKGizmo", "IBKColour",
                "Camera2", "Camera3", "Scene", "ScanlineRender",
                "Card2", "Sphere", "Cube", "Cylinder",
                "DeepRead", "DeepWrite", "DeepMerge", "DeepToImage",
                "Switch", "Dissolve", "TimeOffset", "FrameHold",
                "VectorCornerPin", "CornerPin2D", "SplineWarp3",
                "Glow", "ZDefocus", "GodRays", "LensDistortion",
                "Group", "Precomp",
                "AddChannels", "Remove", "ChannelMerge",
                "Expression", "BlinkScript",
                "Log2Lin", "OCIOColorSpace", "OCIODisplay",
            ]

            for cls in common_classes:
                try:
                    for n in nuke.allNodes(cls):
                        name = n.fullName()
                        if name not in seen_names:
                            seen_names.add(name)
                            all_nodes.append(n)
                except Exception:
                    pass

            # Final unfiltered pass to catch anything missed
            try:
                for n in nuke.allNodes():
                    name = n.fullName()
                    if name not in seen_names:
                        seen_names.add(name)
                        all_nodes.append(n)
            except Exception:
                pass

            nodes = all_nodes

        if group is not None:
            group.end()

        return nodes
    except Exception:
        if group is not None:
            try:
                group.end()
            except Exception:
                pass
        return []


def _reliable_find_node(name: str):
    """Find a node by name with graph sync, working around NC toNode() bugs.

    Falls back to allNodes() search if toNode() returns None.

    Args:
        name: The node name to search for.

    Returns:
        nuke.Node or None.
    """
    import nuke

    _sync_node_graph()

    # Primary: toNode
    try:
        node = nuke.toNode(name)
        if node is not None:
            return node
    except Exception:
        pass

    # Fallback: search allNodes by name
    try:
        for n in nuke.allNodes():
            if n.name() == name or n.fullName() == name:
                return n
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def execute_commands(commands: list[dict], *, new_session: bool = False) -> dict:
    """Execute a list of CommandResult dicts with persistent context.

    Each command has: language, script, description (optional).
    Supported languages: python/py, tcl, nk (Nuke script).

    The Python execution context is shared across all commands in the list
    AND persists across multiple execute_commands() calls within the same
    session (until reset_session() is called).

    Args:
        commands: List of command dicts.
        new_session: If True, reset the session before executing.

    Returns:
        {"executed": int, "failed": int, "skipped": int,
         "errors": list[str], "output": str}
    """
    import nuke

    if new_session:
        reset_session()

    session = _ensure_session()

    executed = 0
    failed = 0
    skipped = 0
    errors: list[str] = []
    output_parts: list[str] = []

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
                # Sync node graph before execution to ensure consistent state
                _sync_node_graph()

                # Capture stdout/stderr from the script
                capture = io.StringIO()
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = capture
                sys.stderr = capture

                try:
                    compiled = compile(script, f"<agent_command: {description}>", "exec")
                    exec(compiled, session)
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                captured = capture.getvalue()
                if captured:
                    output_parts.append(captured)

                executed += 1
            except Exception as e:
                failed += 1
                tb = traceback.format_exc()
                errors.append(f"Command failed ({description}): {e}\n{tb}")

                # Capture any partial output
                try:
                    captured = capture.getvalue()
                    if captured:
                        output_parts.append(captured)
                except Exception:
                    pass
        elif language == "tcl":
            try:
                result = nuke.tcl(script)
                if result:
                    msg = f"TCL ({description}): {result}"
                    print(f"[ArkestratorBridge] {msg}")
                    output_parts.append(result)
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
        "output": "\n".join(output_parts),
    }
