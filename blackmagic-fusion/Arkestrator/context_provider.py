"""
Arkestrator Fusion bridge — context provider.

Gathers editor context from every available Fusion source:
  - Composition metadata (name, filename, resolution, frame range, fps)
  - Active tool and its full settings
  - Selected tools with settings and connections
  - Flow graph topology (all tools + connections)
  - Loaders (media inputs with file paths and clip info)
  - Savers (render outputs with paths and format)
  - 3D scene tools (Shape3D, Merge3D, Camera3D, Light3D, etc.)
  - Modifiers and expressions on tools
  - Macros (custom GroupOperator tools)
  - Timeline state (current frame, render/global range)
  - Comp path mappings
  - Open script editors (if accessible)
"""

import hashlib
import json
import os
import traceback


def get_fusion_app():
    """Get the Fusion application object. Works in both Fusion Standalone and Resolve."""
    # In Fusion's script environment, these globals are available
    try:
        import fusionscript  # noqa: F401 — Fusion Python module
    except ImportError:
        pass

    # Try standard globals first
    for name in ("fusion", "fu", "bmd"):
        obj = _get_global(name)
        if obj is not None:
            if name == "bmd":
                try:
                    return obj.scriptapp("Fusion")
                except Exception:
                    pass
            else:
                return obj
    return None


def get_comp(fusion_app):
    """Get the current composition."""
    if fusion_app is None:
        return None
    try:
        return fusion_app.GetCurrentComp()
    except Exception:
        return None


def _get_global(name):
    """Safely retrieve a global variable."""
    import builtins
    return getattr(builtins, name, None) or globals().get(name)


# ---------------------------------------------------------------------------
# Editor context snapshot
# ---------------------------------------------------------------------------

def build_editor_context(fusion_app, comp):
    """
    Build the EditorContext payload for bridge_editor_context messages.
    Returns (editor_context_dict, files_list).
    """
    if comp is None:
        return _empty_context(), []

    attrs = _safe_call(comp.GetAttrs) or {}
    filename = attrs.get("COMPS_FileName", "") or ""
    project_root = os.path.dirname(filename) if filename else ""
    comp_name = attrs.get("COMPS_Name", "") or (comp.GetAttrs or {}).get("COMPS_Name", "")

    # Active tool
    active_tool = _safe_call(lambda: comp.ActiveTool)
    # activeFile = comp filename (used by server to derive bridge display name)
    # Do NOT set this to the tool name — that would rename the bridge on every tool click
    active_file = filename

    # Metadata — collect everything useful
    metadata = {
        "bridge_type": "fusion",
        "comp_name": comp_name,
        "comp_filename": filename,
    }

    # Resolution & frame rate
    prefs = _get_comp_prefs(comp)
    metadata["width"] = prefs.get("width")
    metadata["height"] = prefs.get("height")
    metadata["fps"] = prefs.get("fps")

    # Frame range
    metadata["render_start"] = attrs.get("COMPN_RenderStart")
    metadata["render_end"] = attrs.get("COMPN_RenderEnd")
    metadata["global_start"] = attrs.get("COMPN_GlobalStart")
    metadata["global_end"] = attrs.get("COMPN_GlobalEnd")
    metadata["current_frame"] = _safe_call(lambda: comp.CurrentTime)

    # Selected tools summary
    selected = _get_selected_tools(comp)
    if selected:
        metadata["selected_tools"] = [
            {"name": t.get("name"), "type": t.get("tool_id")} for t in selected
        ]

    # Active tool details
    if active_tool:
        metadata["active_tool"] = _describe_tool(active_tool)

    # Flow overview — all tools with types and connections
    flow_summary = _get_flow_summary(comp)
    if flow_summary:
        metadata["flow_tools_count"] = len(flow_summary)
        metadata["flow_summary"] = flow_summary

    # Loaders
    loaders = _get_loaders(comp)
    if loaders:
        metadata["loaders"] = loaders

    # Savers
    savers = _get_savers(comp)
    if savers:
        metadata["savers"] = savers

    # 3D tools
    tools_3d = _get_3d_tools(comp)
    if tools_3d:
        metadata["tools_3d"] = tools_3d

    # Macros / GroupOperators
    macros = _get_macros(comp)
    if macros:
        metadata["macros"] = macros

    # Path mappings
    path_map = _safe_call(comp.GetCompPathMap)
    if path_map:
        metadata["path_map"] = dict(path_map) if hasattr(path_map, "items") else {}

    # Strip None values
    metadata = {k: v for k, v in metadata.items() if v is not None}

    editor_context = {
        "projectRoot": project_root or os.getcwd(),
        "activeFile": active_file,
        "metadata": metadata,
    }

    # Files — include content of any script tools or open script editors
    files = _collect_script_files(comp)

    return editor_context, files


def _empty_context():
    return {
        "projectRoot": os.getcwd(),
        "metadata": {"bridge_type": "fusion"},
    }


# ---------------------------------------------------------------------------
# Context items — user-selected items for "Add to Context"
# ---------------------------------------------------------------------------

def build_context_item_for_active_tool(comp, index):
    """Build a ContextItem for the currently active tool."""
    active = _safe_call(lambda: comp.ActiveTool)
    if not active:
        return None
    return _tool_to_context_item(active, index)


def build_context_items_for_selected(comp, start_index):
    """Build ContextItems for all selected tools."""
    tools = _safe_call(lambda: comp.GetToolList(True))
    if not tools:
        return []
    items = []
    idx = start_index
    # Fusion returns a dict-like {1: tool, 2: tool, ...}
    tool_list = _dict_to_list(tools)
    for tool in tool_list:
        item = _tool_to_context_item(tool, idx)
        if item:
            items.append(item)
            idx += 1
    return items


def build_context_item_for_comp(comp, index):
    """Build a ContextItem representing the entire composition structure."""
    if not comp:
        return None
    attrs = _safe_call(comp.GetAttrs) or {}
    comp_name = attrs.get("COMPS_Name", "Untitled")

    # Build a text description of the full comp
    content_parts = [f"Composition: {comp_name}"]

    filename = attrs.get("COMPS_FileName", "")
    if filename:
        content_parts.append(f"File: {filename}")

    prefs = _get_comp_prefs(comp)
    content_parts.append(f"Resolution: {prefs.get('width', '?')}x{prefs.get('height', '?')}")
    content_parts.append(f"FPS: {prefs.get('fps', '?')}")
    content_parts.append(f"Range: {attrs.get('COMPN_RenderStart', '?')}-{attrs.get('COMPN_RenderEnd', '?')}")

    # All tools with connections
    tools = _safe_call(lambda: comp.GetToolList(False))
    if tools:
        tool_list = _dict_to_list(tools)
        content_parts.append(f"\nTools ({len(tool_list)}):")
        for t in tool_list:
            name = _safe_call(lambda: t.Name) or "?"
            tid = _safe_call(lambda: t.ID) or "?"
            inputs = _get_connected_inputs_summary(t)
            line = f"  {name} ({tid})"
            if inputs:
                line += f" <- {inputs}"
            content_parts.append(line)

    content = "\n".join(content_parts)

    return {
        "index": index,
        "type": "scene",
        "name": f"Comp: {comp_name}",
        "path": filename or comp_name,
        "content": content,
        "metadata": {
            "comp_name": comp_name,
            "tool_count": len(_dict_to_list(tools)) if tools else 0,
        },
    }


def build_context_item_for_loader(tool, index):
    """Build a ContextItem for a Loader tool with its media info."""
    if not tool:
        return None
    attrs = _safe_call(tool.GetAttrs) or {}
    name = _safe_call(lambda: tool.Name) or "Loader"
    clip_path = _safe_call(lambda: tool.GetInput("Clip", comp_current_time(tool))) or ""

    content_parts = [f"Loader: {name}"]
    if clip_path:
        content_parts.append(f"Clip: {clip_path}")

    # Get clip attributes
    clip_attrs = {}
    for key in ("TOOLN_Width", "TOOLN_Height", "TOOLST_Clip_FormatName"):
        val = attrs.get(key)
        if val is not None:
            clip_attrs[key] = val
    if clip_attrs:
        content_parts.append(f"Attributes: {json.dumps(clip_attrs)}")

    return {
        "index": index,
        "type": "asset",
        "name": name,
        "path": str(clip_path),
        "content": "\n".join(content_parts),
        "metadata": {"tool_id": "Loader", **clip_attrs},
    }


def build_context_item_for_saver(tool, index):
    """Build a ContextItem for a Saver tool with output info."""
    if not tool:
        return None
    name = _safe_call(lambda: tool.Name) or "Saver"
    clip_path = _safe_call(lambda: tool.GetInput("Clip", comp_current_time(tool))) or ""

    content_parts = [f"Saver: {name}", f"Output: {clip_path}"]

    # Format info
    fmt = _safe_call(lambda: tool.GetInput("OutputFormat", comp_current_time(tool)))
    if fmt:
        content_parts.append(f"Format: {fmt}")

    return {
        "index": index,
        "type": "asset",
        "name": name,
        "path": str(clip_path),
        "content": "\n".join(content_parts),
        "metadata": {"tool_id": "Saver", "output_path": str(clip_path)},
    }


def build_context_item_for_3d_scene(comp, index):
    """Build a ContextItem summarizing the 3D scene hierarchy."""
    tools_3d = _get_3d_tools(comp)
    if not tools_3d:
        return None

    content_parts = [f"3D Scene ({len(tools_3d)} tools):"]
    for t in tools_3d:
        content_parts.append(f"  {t['name']} ({t['type']})")
        if t.get("inputs"):
            for inp_name, inp_val in t["inputs"].items():
                content_parts.append(f"    {inp_name}: {inp_val}")

    return {
        "index": index,
        "type": "scene",
        "name": "3D Scene",
        "path": "3d_scene",
        "content": "\n".join(content_parts),
        "metadata": {"tool_count": len(tools_3d)},
    }


def build_context_item_for_modifiers(comp, index):
    """Build a ContextItem for all modifiers/expressions in the comp."""
    modifiers = _get_all_modifiers(comp)
    if not modifiers:
        return None

    content_parts = [f"Modifiers & Expressions ({len(modifiers)}):"]
    for m in modifiers:
        content_parts.append(f"  {m['tool']}.{m['input']}: {m['modifier_type']}")
        if m.get("expression"):
            content_parts.append(f"    Expression: {m['expression']}")

    return {
        "index": index,
        "type": "resource",
        "name": "Modifiers & Expressions",
        "path": "modifiers",
        "content": "\n".join(content_parts),
        "metadata": {"count": len(modifiers)},
    }


def build_context_item_for_settings(tool, index):
    """Build a ContextItem with all settings/inputs of a specific tool."""
    if not tool:
        return None
    name = _safe_call(lambda: tool.Name) or "Tool"
    tid = _safe_call(lambda: tool.ID) or "?"
    settings = _get_tool_settings(tool)

    content_parts = [f"Tool Settings: {name} ({tid})"]
    for k, v in settings.items():
        content_parts.append(f"  {k}: {v}")

    return {
        "index": index,
        "type": "resource",
        "name": f"Settings: {name}",
        "path": name,
        "content": "\n".join(content_parts),
        "metadata": {"tool_id": tid, "settings_count": len(settings)},
    }


def build_context_item_for_flow_graph(comp, index):
    """Build a ContextItem showing the full node graph topology."""
    tools = _safe_call(lambda: comp.GetToolList(False))
    if not tools:
        return None
    tool_list = _dict_to_list(tools)

    content_parts = [f"Flow Graph ({len(tool_list)} nodes):"]
    content_parts.append("")

    for t in tool_list:
        name = _safe_call(lambda: t.Name) or "?"
        tid = _safe_call(lambda: t.ID) or "?"
        conns = _get_connected_inputs_detail(t)
        line = f"{name} [{tid}]"
        if conns:
            sources = ", ".join(f"{c['from_tool']}.{c['from_output']}" for c in conns)
            line += f"  <--  {sources}"
        content_parts.append(line)

    return {
        "index": index,
        "type": "scene",
        "name": "Flow Graph",
        "path": "flow_graph",
        "content": "\n".join(content_parts),
        "metadata": {"node_count": len(tool_list)},
    }


def build_context_item_for_keyframes(tool, index):
    """Build a ContextItem with keyframe/animation data for a tool."""
    if not tool:
        return None
    name = _safe_call(lambda: tool.Name) or "Tool"
    keyframes = _get_tool_keyframes(tool)
    if not keyframes:
        return None

    content_parts = [f"Keyframes: {name}"]
    for kf in keyframes:
        content_parts.append(f"  {kf['input']}: {len(kf['frames'])} keys")
        for frame, val in kf["frames"][:20]:  # Limit to first 20
            content_parts.append(f"    Frame {frame}: {val}")
        if len(kf["frames"]) > 20:
            content_parts.append(f"    ... and {len(kf['frames']) - 20} more")

    return {
        "index": index,
        "type": "resource",
        "name": f"Keyframes: {name}",
        "path": f"{name}/keyframes",
        "content": "\n".join(content_parts),
        "metadata": {"animated_inputs": len(keyframes)},
    }


# ---------------------------------------------------------------------------
# Hash for dedup
# ---------------------------------------------------------------------------

def context_hash(editor_context, files):
    """Hash the context for change detection."""
    raw = json.dumps(editor_context, sort_keys=True, default=str) + json.dumps(files, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_call(fn):
    """Call fn() and return None on any error."""
    try:
        return fn()
    except Exception:
        return None


def comp_current_time(tool_or_comp):
    """Get current time from a tool's parent comp."""
    try:
        comp = tool_or_comp.Comp if hasattr(tool_or_comp, "Comp") else tool_or_comp
        return comp.CurrentTime
    except Exception:
        return 0


def _dict_to_list(fusion_dict):
    """Convert Fusion's 1-indexed dict to a Python list."""
    if fusion_dict is None:
        return []
    if isinstance(fusion_dict, (list, tuple)):
        return list(fusion_dict)
    if hasattr(fusion_dict, "values"):
        return list(fusion_dict.values())
    # Fusion returns table-like objects with numeric keys
    result = []
    i = 1
    while True:
        try:
            item = fusion_dict[i]
            if item is None:
                break
            result.append(item)
            i += 1
        except (KeyError, IndexError, TypeError):
            break
    return result


def _describe_tool(tool):
    """Build a summary dict for a single tool."""
    name = _safe_call(lambda: tool.Name) or "?"
    tid = _safe_call(lambda: tool.ID) or "?"
    attrs = _safe_call(tool.GetAttrs) or {}

    desc = {
        "name": name,
        "tool_id": tid,
        "enabled": attrs.get("TOOLB_PassThrough") is not True,
    }

    # Position in flow
    pos = attrs.get("TOOLS_RegID")
    if pos:
        desc["reg_id"] = pos

    return desc


def _tool_to_context_item(tool, index):
    """Convert a Fusion tool to a ContextItem dict."""
    name = _safe_call(lambda: tool.Name) or "Tool"
    tid = _safe_call(lambda: tool.ID) or "?"

    # Determine context item type
    item_type = "node"
    if tid in ("Loader",):
        item_type = "asset"
    elif tid in ("Fuse", "RunScript"):
        item_type = "script"
    elif tid == "GroupOperator":
        item_type = "resource"
    elif tid in ("Renderer3D", "Shape3D", "Merge3D", "Camera3D", "PointLight3D",
                 "DirectionalLight3D", "AmbientLight3D", "SpotLight3D", "FBXMesh3D",
                 "AlembicMesh3D", "SurfaceFBXMesh3D", "Text3D", "ImagePlane3D",
                 "ReplaceNormals3D", "Transform3D"):
        item_type = "scene"

    # Build content: tool settings + connections
    content_parts = [f"{name} ({tid})"]

    settings = _get_tool_settings(tool)
    if settings:
        content_parts.append("\nSettings:")
        for k, v in settings.items():
            content_parts.append(f"  {k}: {v}")

    conns = _get_connected_inputs_detail(tool)
    if conns:
        content_parts.append("\nConnections:")
        for c in conns:
            content_parts.append(f"  {c['input']} <- {c['from_tool']}.{c['from_output']}")

    # For Fuse tools, try to get the script content
    if tid == "Fuse":
        fuse_file = _safe_call(lambda: tool.GetInput("FuseFile", comp_current_time(tool)))
        if fuse_file and os.path.isfile(str(fuse_file)):
            try:
                with open(str(fuse_file), "r", encoding="utf-8", errors="replace") as f:
                    script = f.read()
                content_parts.append(f"\nFuse Script ({fuse_file}):")
                content_parts.append(script[:10000])  # Limit size
            except Exception:
                pass

    return {
        "index": index,
        "type": item_type,
        "name": name,
        "path": name,
        "content": "\n".join(content_parts),
        "metadata": {
            "tool_id": tid,
            "enabled": (_safe_call(tool.GetAttrs) or {}).get("TOOLB_PassThrough") is not True,
        },
    }


def _get_selected_tools(comp):
    """Return list of dicts describing selected tools."""
    tools = _safe_call(lambda: comp.GetToolList(True))
    if not tools:
        return []
    result = []
    for t in _dict_to_list(tools):
        name = _safe_call(lambda: t.Name)
        tid = _safe_call(lambda: t.ID)
        if name or tid:
            result.append({"name": name, "tool_id": tid})
    return result


def _get_tool_settings(tool):
    """Get all current input values for a tool."""
    settings = {}
    try:
        inputs = tool.GetInputList()
        if not inputs:
            return settings
        ct = comp_current_time(tool)
        for _key, inp in (inputs.items() if hasattr(inputs, "items") else []):
            try:
                inp_attrs = inp.GetAttrs()
                inp_name = inp_attrs.get("INPS_Name", str(_key))
                # Skip hidden/non-user inputs
                if inp_attrs.get("INPB_Hidden"):
                    continue
                val = inp[ct]
                if val is not None and not callable(val):
                    # Simplify complex objects
                    settings[inp_name] = _simplify_value(val)
            except Exception:
                continue
    except Exception:
        pass
    return settings


def _simplify_value(val):
    """Convert Fusion values to JSON-safe types."""
    if isinstance(val, (int, float, bool, str)):
        return val
    if isinstance(val, dict):
        return {str(k): _simplify_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_simplify_value(v) for v in val]
    return str(val)


def _get_connected_inputs_summary(tool):
    """Get a brief summary of connected inputs."""
    try:
        inputs = tool.GetInputList()
        if not inputs:
            return ""
        conns = []
        for _key, inp in (inputs.items() if hasattr(inputs, "items") else []):
            try:
                conn = inp.GetConnectedOutput()
                if conn:
                    src_tool = conn.GetTool()
                    if src_tool:
                        conns.append(_safe_call(lambda: src_tool.Name) or "?")
            except Exception:
                continue
        return ", ".join(conns) if conns else ""
    except Exception:
        return ""


def _get_connected_inputs_detail(tool):
    """Get detailed connection info for a tool's inputs."""
    result = []
    try:
        inputs = tool.GetInputList()
        if not inputs:
            return result
        for _key, inp in (inputs.items() if hasattr(inputs, "items") else []):
            try:
                conn = inp.GetConnectedOutput()
                if conn:
                    src_tool = conn.GetTool()
                    if src_tool:
                        inp_attrs = inp.GetAttrs()
                        result.append({
                            "input": inp_attrs.get("INPS_Name", str(_key)),
                            "from_tool": _safe_call(lambda: src_tool.Name) or "?",
                            "from_output": _safe_call(lambda: conn.GetAttrs().get("OUTS_Name", "Output")) or "Output",
                        })
            except Exception:
                continue
    except Exception:
        pass
    return result


def _get_flow_summary(comp):
    """Get a compact summary of all tools in the flow."""
    tools = _safe_call(lambda: comp.GetToolList(False))
    if not tools:
        return None
    summary = []
    for t in _dict_to_list(tools):
        name = _safe_call(lambda: t.Name)
        tid = _safe_call(lambda: t.ID)
        if name:
            entry = {"name": name, "type": tid}
            conns = _get_connected_inputs_summary(t)
            if conns:
                entry["from"] = conns
            summary.append(entry)
    return summary if summary else None


def _get_loaders(comp):
    """Get all Loader tools with clip info."""
    tools = _safe_call(lambda: comp.GetToolList(False, "Loader"))
    if not tools:
        return None
    result = []
    ct = _safe_call(lambda: comp.CurrentTime) or 0
    for t in _dict_to_list(tools):
        name = _safe_call(lambda: t.Name) or "Loader"
        clip = _safe_call(lambda: t.GetInput("Clip", ct)) or ""
        entry = {"name": name, "clip": str(clip)}
        # Clip attributes
        attrs = _safe_call(t.GetAttrs) or {}
        for k in ("TOOLN_Width", "TOOLN_Height", "TOOLST_Clip_FormatName",
                   "TOOLIT_Clip_TrimIn", "TOOLIT_Clip_TrimOut", "TOOLIT_Clip_Length"):
            v = attrs.get(k)
            if v is not None:
                entry[k] = v
        result.append(entry)
    return result if result else None


def _get_savers(comp):
    """Get all Saver tools with output paths."""
    tools = _safe_call(lambda: comp.GetToolList(False, "Saver"))
    if not tools:
        return None
    result = []
    ct = _safe_call(lambda: comp.CurrentTime) or 0
    for t in _dict_to_list(tools):
        name = _safe_call(lambda: t.Name) or "Saver"
        clip = _safe_call(lambda: t.GetInput("Clip", ct)) or ""
        fmt = _safe_call(lambda: t.GetInput("OutputFormat", ct))
        entry = {"name": name, "output": str(clip)}
        if fmt:
            entry["format"] = str(fmt)
        result.append(entry)
    return result if result else None


def _get_3d_tools(comp):
    """Get all 3D-related tools."""
    types_3d = [
        "Shape3D", "Merge3D", "Camera3D", "Renderer3D",
        "PointLight3D", "DirectionalLight3D", "AmbientLight3D", "SpotLight3D",
        "FBXMesh3D", "AlembicMesh3D", "SurfaceFBXMesh3D",
        "Text3D", "ImagePlane3D", "Transform3D",
        "ReplaceNormals3D", "Cube3D", "SphereMap", "Sphere3D",
        "Torus3D", "Cylinder3D", "Cone3D", "Plane3D",
        "Bender3D", "Displace3D", "Fog3D", "SoftClip3D",
    ]
    result = []
    for tid in types_3d:
        tools = _safe_call(lambda: comp.GetToolList(False, tid))
        if tools:
            for t in _dict_to_list(tools):
                name = _safe_call(lambda: t.Name) or tid
                entry = {"name": name, "type": tid}
                # Key 3D inputs
                key_inputs = _get_key_3d_inputs(t)
                if key_inputs:
                    entry["inputs"] = key_inputs
                result.append(entry)
    return result if result else None


def _get_key_3d_inputs(tool):
    """Get key input values for a 3D tool (transform, material, etc.)."""
    inputs = {}
    ct = comp_current_time(tool)
    key_names = [
        "Transform3DOp.Translate.X", "Transform3DOp.Translate.Y", "Transform3DOp.Translate.Z",
        "Transform3DOp.Rotate.X", "Transform3DOp.Rotate.Y", "Transform3DOp.Rotate.Z",
        "Transform3DOp.Scale.X", "Transform3DOp.Scale.Y", "Transform3DOp.Scale.Z",
        "AoV", "NearClip", "FarClip",  # Camera
        "Intensity", "Color.Red", "Color.Green", "Color.Blue",  # Lights
        "Shape", "Size", "Subdivision",  # Shape3D
    ]
    for name in key_names:
        val = _safe_call(lambda: tool.GetInput(name, ct))
        if val is not None:
            inputs[name] = _simplify_value(val)
    return inputs if inputs else None


def _get_macros(comp):
    """Get all GroupOperator (macro) tools."""
    tools = _safe_call(lambda: comp.GetToolList(False, "GroupOperator"))
    if not tools:
        return None
    result = []
    for t in _dict_to_list(tools):
        name = _safe_call(lambda: t.Name) or "Group"
        # Count tools inside the group
        inner_tools = _safe_call(lambda: t.GetToolList(False))
        inner_count = len(_dict_to_list(inner_tools)) if inner_tools else 0
        entry = {"name": name, "inner_tool_count": inner_count}
        result.append(entry)
    return result if result else None


def _get_all_modifiers(comp):
    """Get all modifiers/expressions across all tools."""
    tools = _safe_call(lambda: comp.GetToolList(False))
    if not tools:
        return []
    result = []
    for t in _dict_to_list(tools):
        tool_name = _safe_call(lambda: t.Name) or "?"
        try:
            inputs = t.GetInputList()
            if not inputs:
                continue
            for _key, inp in (inputs.items() if hasattr(inputs, "items") else []):
                try:
                    # Check for connected modifier
                    conn = inp.GetConnectedOutput()
                    if conn:
                        mod_tool = conn.GetTool()
                        if mod_tool:
                            mod_id = _safe_call(lambda: mod_tool.ID) or ""
                            # Is it a modifier (BezierSpline, Expression, etc.)?
                            if mod_id in ("BezierSpline", "Polyline", "Expression",
                                          "LookUpTable", "Gradient", "Path",
                                          "XYPath", "Shake", "Perturb",
                                          "Probe", "FromImage", "Calculation"):
                                inp_attrs = inp.GetAttrs()
                                entry = {
                                    "tool": tool_name,
                                    "input": inp_attrs.get("INPS_Name", str(_key)),
                                    "modifier_type": mod_id,
                                }
                                # For Expression modifiers, get the expression text
                                if mod_id == "Expression":
                                    expr = _safe_call(lambda: mod_tool.GetInput("Expression",
                                                      comp_current_time(mod_tool)))
                                    if expr:
                                        entry["expression"] = str(expr)
                                result.append(entry)
                except Exception:
                    continue
        except Exception:
            continue
    return result


def _get_tool_keyframes(tool):
    """Get keyframe data for animated inputs on a tool."""
    result = []
    try:
        inputs = tool.GetInputList()
        if not inputs:
            return result
        for _key, inp in (inputs.items() if hasattr(inputs, "items") else []):
            try:
                inp_attrs = inp.GetAttrs()
                # Check if the input has keyframes (connected to a BezierSpline)
                conn = inp.GetConnectedOutput()
                if conn:
                    mod_tool = conn.GetTool()
                    if mod_tool and _safe_call(lambda: mod_tool.ID) == "BezierSpline":
                        # Get keyframes from the spline
                        spline_points = _safe_call(lambda: mod_tool.GetKeyFrames())
                        if spline_points:
                            frames = []
                            if isinstance(spline_points, dict):
                                for frame, val in sorted(spline_points.items()):
                                    frames.append((frame, _simplify_value(val)))
                            inp_name = inp_attrs.get("INPS_Name", str(_key))
                            if frames:
                                result.append({"input": inp_name, "frames": frames})
            except Exception:
                continue
    except Exception:
        pass
    return result


def _collect_script_files(comp):
    """Collect content from script tools and open script editors."""
    files = []

    # RunScript and Fuse tools
    for tid in ("RunScript", "Fuse"):
        tools = _safe_call(lambda: comp.GetToolList(False, tid))
        if not tools:
            continue
        for t in _dict_to_list(tools):
            name = _safe_call(lambda: t.Name) or tid
            ct = comp_current_time(t)
            if tid == "Fuse":
                fuse_file = _safe_call(lambda: t.GetInput("FuseFile", ct))
                if fuse_file and os.path.isfile(str(fuse_file)):
                    try:
                        with open(str(fuse_file), "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        files.append({"path": str(fuse_file), "content": content[:50000]})
                    except Exception:
                        pass
            elif tid == "RunScript":
                script_file = _safe_call(lambda: t.GetInput("Source", ct))
                if script_file and os.path.isfile(str(script_file)):
                    try:
                        with open(str(script_file), "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        files.append({"path": str(script_file), "content": content[:50000]})
                    except Exception:
                        pass

    return files


def _get_comp_prefs(comp):
    """Get composition preferences (resolution, fps, etc.)."""
    result = {}
    prefs = _safe_call(comp.GetPrefs)
    if prefs and isinstance(prefs, dict):
        # Navigate nested Comp prefs
        cp = prefs.get("Comp", {})
        frame_fmt = cp.get("FrameFormat", {}) if isinstance(cp, dict) else {}
        if isinstance(frame_fmt, dict):
            result["width"] = frame_fmt.get("Width")
            result["height"] = frame_fmt.get("Height")
            result["fps"] = frame_fmt.get("Rate")
    return result
