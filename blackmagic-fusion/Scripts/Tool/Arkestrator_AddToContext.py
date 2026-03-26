"""
Arkestrator — Add selected tool(s) to Arkestrator context.

This is a Fusion "Tool Script" — it appears under the Script > submenu
when right-clicking a tool/node in the flow view.

Fusion automatically provides these globals:
  - fusion  : the Fusion application object
  - comp    : the active composition
  - tool    : the tool that was right-clicked
"""

import json
import sys
import os

# ---------------------------------------------------------------------------
# Bootstrap the Arkestrator package so we can import bridge modules
# ---------------------------------------------------------------------------
_config_dir = None
for _candidate in [
    os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design", "Fusion", "Config", "Arkestrator"),
    os.path.join(os.environ.get("APPDATA", ""), "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion", "Config", "Arkestrator"),
]:
    if os.path.isdir(_candidate):
        _config_dir = _candidate
        break

if _config_dir is None:
    print("[Arkestrator] ERROR: Cannot find Arkestrator config directory")
else:
    # Register as the 'fusion' package if not already done
    _parent = os.path.dirname(_config_dir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

    import importlib
    import importlib.util
    _fqn = "fusion"
    if _fqn not in sys.modules:
        _spec = importlib.util.spec_from_file_location(
            _fqn,
            os.path.join(_config_dir, "__init__.py"),
            submodule_search_locations=[_config_dir],
        )
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules[_fqn] = _mod
        _spec.loader.exec_module(_mod)

    from fusion.arkestrator_bridge import get_or_create_bridge

    bridge = get_or_create_bridge(fusion)

    if not bridge.connected:
        print("[Arkestrator] Bridge is not connected. Use Arkestrator > Connect first.")
    else:
        # Gather info about the right-clicked tool and any selected tools
        selected_tools = comp.GetToolList(True) or {}  # selected tools
        tools_to_add = []

        # Always include the right-clicked tool
        if tool is not None:
            tools_to_add.append(tool)

        # Add any other selected tools
        for _idx, _t in selected_tools.items():
            if _t.Name != (tool.Name if tool else ""):
                tools_to_add.append(_t)

        if not tools_to_add:
            print("[Arkestrator] No tools to add to context.")
        else:
            # Build a context snippet for the selected tools
            tool_infos = []
            for t in tools_to_add:
                info = {"name": t.Name, "type": t.ID}
                # Get inputs/settings
                inp_list = t.GetInputList() or {}
                settings = {}
                for _k, inp in inp_list.items():
                    try:
                        attrs = inp.GetAttrs() or {}
                        name = attrs.get("INPS_Name", str(_k))
                        val = inp[comp.CurrentTime]
                        if val is not None and not callable(val):
                            settings[name] = str(val) if not isinstance(val, (int, float, bool)) else val
                    except Exception:
                        pass
                if settings:
                    info["settings"] = settings

                # Get connections
                connections = []
                for _k, inp in inp_list.items():
                    try:
                        src = inp.GetConnectedOutput()
                        if src:
                            src_tool = src.GetTool()
                            if src_tool:
                                connections.append({
                                    "input": inp.Name if hasattr(inp, "Name") else str(_k),
                                    "from_tool": src_tool.Name,
                                })
                    except Exception:
                        pass
                if connections:
                    info["connections"] = connections

                tool_infos.append(info)

            # Send as a context snippet via the bridge
            snippet = {
                "type": "fusion_tools",
                "description": f"Fusion tools added to context: {', '.join(t['name'] for t in tool_infos)}",
                "tools": tool_infos,
            }

            # Use the bridge WS to send a context_add message
            bridge._ws.send_json({
                "type": "bridge_context_add",
                "payload": {
                    "snippet": json.dumps(snippet, indent=2),
                    "source": "fusion",
                    "label": ", ".join(t["name"] for t in tool_infos),
                },
            })

            names = ", ".join(t["name"] for t in tool_infos)
            print(f"[Arkestrator] Added to context: {names}")
