"""Operator classes for Arkestrator bridge.

Thin bridge architecture: only connection + editor context helpers.
All job submission UI lives in the Tauri client.
"""

import os

import bpy


def _get_prefs():
    return bpy.context.preferences.addons[__package__].preferences


def _get_ws_client():
    """Access the global ws_client instance from __init__.py."""
    from . import _ws_client
    return _ws_client


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class AGENTMGR_OT_connect(bpy.types.Operator):
    """Connect or disconnect from the Arkestrator server"""
    bl_idname = "agent_manager.connect"
    bl_label = "Connect"

    def execute(self, context):
        ws = _get_ws_client()
        if ws is None:
            self.report({'ERROR'}, "WebSocket client not initialized")
            return {'CANCELLED'}

        props = context.scene.agent_manager

        if ws.connected:
            ws.disconnect()
            props.connection_status = "Disconnected"
            props.is_connected = False
        else:
            prefs = _get_prefs()
            url = prefs.server_url.strip()
            api_key = ""

            # Read API key from shared config (~/.arkestrator/config.json)
            from . import _read_shared_config, _resolve_ws_url_from_shared, _sync_prefs_server_url
            shared = _read_shared_config()
            if shared:
                api_key = shared.get("apiKey", "")
                original_url = url
                url = _resolve_ws_url_from_shared(url, shared)
                _sync_prefs_server_url(prefs, url, original_url)

            if not url:
                props.connection_status = "Error: Server URL is empty"
                return {'CANCELLED'}

            project_path = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
            blend_name = os.path.basename(bpy.data.filepath) if bpy.data.filepath else "Untitled"

            ws.connect(
                url=url,
                api_key=api_key,
                project_path=project_path,
                project_name=blend_name,
                program_version=bpy.app.version_string,
            )
            props.connection_status = "Connecting..."

        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Editor context helpers (used by __init__.py for periodic pushes)
# ---------------------------------------------------------------------------

def _build_editor_context() -> dict:
    """Build the editor context dict for the current Blender state."""
    active_obj = bpy.context.active_object
    selected = bpy.context.selected_objects if hasattr(bpy.context, "selected_objects") else []
    active_space = getattr(bpy.context, "space_data", None)
    active_tree = getattr(active_space, "edit_tree", None)
    file_browser_directory = ""
    file_browser_browse_mode = None
    active_file_browser_entry = None
    active_asset_name = None

    selected_nodes = []
    for obj in selected:
        selected_nodes.append({
            "name": obj.name,
            "type": obj.type,
            "path": obj.name_full,
        })

    selected_editor_nodes = []
    if active_tree is not None:
        for node in active_tree.nodes:
            if not getattr(node, "select", False):
                continue
            selected_editor_nodes.append({
                "name": node.name,
                "type": getattr(node, "bl_idname", node.__class__.__name__),
                "path": f"{active_tree.name}/{node.name}",
            })

    selected_scripts = []
    for text in bpy.data.texts:
        selected_scripts.append(text.filepath if text.filepath else text.name)

    if getattr(active_space, "type", None) == "FILE_BROWSER":
        params = getattr(active_space, "params", None)
        directory = getattr(params, "directory", "") if params is not None else ""
        if isinstance(directory, bytes):
            directory = os.fsdecode(directory)
        directory = str(directory or "").strip()
        file_browser_directory = bpy.path.abspath(directory) if directory else ""
        file_browser_browse_mode = getattr(active_space, "browse_mode", None)

        active_file = getattr(bpy.context, "active_file", None)
        if active_file is not None:
            active_file_browser_entry = getattr(active_file, "relative_path", None) or getattr(active_file, "name", None)

        active_asset = getattr(bpy.context, "asset", None)
        if active_asset is not None:
            active_asset_name = getattr(active_asset, "name", None)

    blend_path = bpy.data.filepath or ""
    project_root = os.path.dirname(blend_path) if blend_path else ""

    return {
        "projectRoot": project_root,
        "activeFile": blend_path,
        "metadata": {
            "bridge_type": "blender",
            "active_scene": bpy.context.scene.name if bpy.context.scene else "",
            "blend_file_path": blend_path,
            "active_object": active_obj.name if active_obj else None,
            "selected_objects": [
                {"name": o.name, "type": o.type, "path": o.name_full}
                for o in selected
            ],
            "selected_node_editor_nodes": selected_editor_nodes,
            "active_node_tree": active_tree.name if active_tree else None,
            "active_editor_type": getattr(active_space, "type", None),
            "selected_scripts": selected_scripts,
            "file_browser_directory": file_browser_directory,
            "file_browser_browse_mode": file_browser_browse_mode,
            "active_file_browser_entry": active_file_browser_entry,
            "active_asset_name": active_asset_name,
        },
    }


def _gather_file_attachments() -> list[dict]:
    """Gather all open text blocks as file attachments."""
    files = []
    for text in bpy.data.texts:
        path = text.filepath if text.filepath else text.name
        files.append({
            "path": path,
            "content": text.as_string(),
        })
    return files
