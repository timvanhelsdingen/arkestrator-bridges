"""Context-menu integrations for Arkestrator context capture.

The addon registers against Blender's runtime menu registry so the shared
`Add to Arkestrator Context` action appears across viewport, Outliner,
file/asset browser, properties, and other RMB menu surfaces instead of a small
hand-maintained subset.
"""

import os

import bmesh
import bpy
from bpy.props import StringProperty

# Module-level incrementing index for context items.
_next_context_index = 1
_menus_registered = False
_registered_menu_specs: tuple[tuple[str, str], ...] = ()
_MENU_LABEL = "Add to Arkestrator Context"
_MENU_NAME_EXTRAS = (
    "OUTLINER_MT_context_menu_view",
    "OUTLINER_MT_collection",
    "OUTLINER_MT_collection_new",
    "OUTLINER_MT_collection_view_layer",
    "OUTLINER_MT_collection_visibility",
    "OUTLINER_MT_object",
    "OUTLINER_MT_id_data",
    "OUTLINER_MT_edit_datablocks",
    "OUTLINER_MT_asset",
    "OUTLINER_MT_liboverride",
    "ASSETBROWSER_MT_asset",
    "ASSETBROWSER_MT_catalog",
)
_TEXT_FILE_EXTENSIONS = {
    ".cfg", ".cmd", ".conf", ".cpp", ".cs", ".css", ".csv", ".frag", ".gd",
    ".glsl", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json", ".md",
    ".mtl", ".osl", ".py", ".rs", ".sh", ".svg", ".toml", ".ts", ".tsx",
    ".txt", ".vert", ".xml", ".yaml", ".yml",
}
_MAX_INLINE_TEXT_BYTES = 256 * 1024
_GENERIC_ID_CONTEXT_ATTRS = (
    "id",
    "material",
    "texture",
    "world",
    "scene",
    "collection",
    "object",
    "active_object",
    "camera",
    "light",
    "brush",
    "image",
    "mask",
    "movieclip",
    "node_tree",
)


def _safe_name(value, fallback="Item") -> str:
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    text = str(value or "").strip()
    return text or fallback


def _safe_path(value, fallback="") -> str:
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    text = str(value or "").strip()
    return text or fallback


def _resolved_fs_path(value, fallback="") -> str:
    path = _safe_path(value, fallback)
    if not path:
        return fallback
    try:
        return bpy.path.abspath(path)
    except Exception:
        return path


def _file_browser_directory(context) -> str:
    space = getattr(context, "space_data", None)
    params = getattr(space, "params", None)
    return _resolved_fs_path(getattr(params, "directory", None), "")


def _menu_source(menu_name: str) -> str:
    if menu_name.startswith("VIEW3D_"):
        return "viewport"
    if menu_name.startswith("OUTLINER_"):
        return "outliner"
    if menu_name.startswith("FILEBROWSER_"):
        return "file_browser"
    if menu_name.startswith("ASSETBROWSER_"):
        return "asset_browser"
    if menu_name.startswith("TEXT_"):
        return "text_editor"
    if menu_name.startswith("NODE_"):
        return "node_editor"
    return "generic_context"


def _iter_menu_specs() -> tuple[tuple[str, str], ...]:
    menu_names = set(_MENU_NAME_EXTRAS)
    for name in dir(bpy.types):
        if name.endswith("_context_menu"):
            menu_names.add(name)

    specs = []
    for menu_name in sorted(menu_names):
        menu = getattr(bpy.types, menu_name, None)
        if menu is None:
            continue
        try:
            if not issubclass(menu, bpy.types.Menu):
                continue
        except TypeError:
            continue
        specs.append((menu_name, _menu_source(menu_name)))
    return tuple(specs)


def _send_context_item(ws, item: dict):
    global _next_context_index

    payload = {
        "index": _next_context_index,
        **item,
    }
    _next_context_index += 1
    ws.send_context_item(payload)
    return payload


def _push_grouped_item(ws, *, item_type: str, name: str, path: str, heading: str, selection_kind: str, items: list[dict]):
    if not items:
        return None

    if len(items) == 1:
        return _send_context_item(ws, items[0])

    summary_lines = []
    for entry in items:
        meta = entry.get("metadata", {}) or {}
        summary_lines.append(
            f"- {entry.get('name', 'Item')} ({meta.get('class', entry.get('type', item_type))}) at {entry.get('path', '')}"
        )

    item = {
        "type": item_type,
        "name": name,
        "path": path,
        "content": f"{heading}:\n" + "\n".join(summary_lines),
        "metadata": {
            "class": "SelectionGroup",
            "selection_group": True,
            "selection_kind": selection_kind,
            "count": len(items),
            "items": items,
        },
    }
    return _send_context_item(ws, item)


def _is_id_like(value) -> bool:
    try:
        return isinstance(value, bpy.types.ID) or isinstance(value, bpy.types.Object)
    except TypeError:
        return False


def _build_object_metadata_static(obj) -> dict:
    meta = {
        "class": obj.type,
    }
    obj_props = {}
    if hasattr(obj, "location"):
        obj_props["location"] = f"({obj.location.x:.3f}, {obj.location.y:.3f}, {obj.location.z:.3f})"
    if hasattr(obj, "rotation_euler"):
        rotation = obj.rotation_euler
        obj_props["rotation"] = f"({rotation.x:.3f}, {rotation.y:.3f}, {rotation.z:.3f})"
    if hasattr(obj, "scale"):
        obj_props["scale"] = f"({obj.scale.x:.3f}, {obj.scale.y:.3f}, {obj.scale.z:.3f})"
    if obj.type == 'MESH' and obj.data:
        obj_props["vertices"] = len(obj.data.vertices)
        obj_props["faces"] = len(obj.data.polygons)
    if obj_props:
        meta["properties"] = obj_props
    return meta


def _iter_selected_node_editor_nodes(context):
    selected_nodes = getattr(context, "selected_nodes", None)
    if selected_nodes:
        return list(selected_nodes)

    space = getattr(context, "space_data", None)
    tree = getattr(space, "edit_tree", None)
    if tree is None:
        return []
    return [node for node in tree.nodes if getattr(node, "select", False)]


def _describe_node_owner(space) -> tuple[str, str]:
    owner = getattr(space, "id", None)
    owner_name = _safe_name(getattr(owner, "name_full", None), "NodeTree")
    owner_path = _safe_path(getattr(owner, "filepath", None), owner_name)
    return owner_name, owner_path


def _node_tree_path(space, tree) -> str:
    owner_name, owner_path = _describe_node_owner(space)
    tree_name = _safe_name(getattr(tree, "name", None), "NodeTree")
    if owner_path and owner_path != owner_name:
        return f"{owner_path}::{tree_name}"
    return f"{owner_name}::{tree_name}"


def _serialize_node_editor_node(context, node) -> dict:
    space = getattr(context, "space_data", None)
    tree = getattr(space, "edit_tree", None)
    tree_path = _node_tree_path(space, tree) if tree else "node_tree://blender"
    return {
        "type": "node",
        "name": _safe_name(getattr(node, "name", None), "Node"),
        "path": f"{tree_path}/{_safe_name(getattr(node, 'name', None), 'Node')}",
        "content": "",
        "metadata": {
            "class": _safe_name(getattr(node, "bl_idname", None), node.__class__.__name__),
            "tree_type": _safe_name(getattr(space, "tree_type", None), "NODE_EDITOR"),
            "node_tree": _safe_name(getattr(tree, "name", None), "NodeTree") if tree else "NodeTree",
            "owner": _describe_node_owner(space)[0],
            "location": list(getattr(node, "location", (0.0, 0.0))),
            "width": float(getattr(node, "width", 0.0)),
            "height": float(getattr(node, "height", 0.0)),
        },
    }


def _serialize_outliner_id(item) -> dict | None:
    if item is None:
        return None

    if isinstance(item, bpy.types.Object):
        return {
            "type": "node",
            "name": item.name,
            "path": item.name_full,
            "content": "",
            "metadata": _build_object_metadata_static(item),
        }

    item_name = _safe_name(getattr(item, "name_full", None) or getattr(item, "name", None), item.__class__.__name__)
    item_path = _safe_path(getattr(item, "filepath", None), item_name)
    item_type = "scene" if isinstance(item, bpy.types.Scene) else "resource"

    serialized = {
        "type": item_type,
        "name": item_name,
        "path": item_path,
        "content": "",
        "metadata": {
            "class": item.__class__.__name__,
        },
    }

    if isinstance(item, bpy.types.Text):
        serialized["type"] = "script"
        serialized["path"] = item.filepath if item.filepath else item.name
        serialized["content"] = item.as_string()
        serialized["metadata"]["extension"] = item.name.rsplit(".", 1)[-1] if "." in item.name else "py"
    elif isinstance(item, bpy.types.Material):
        serialized["metadata"]["node_tree"] = _safe_name(getattr(item.node_tree, "name", None), "")
    elif isinstance(item, bpy.types.Collection):
        serialized["metadata"]["children"] = len(item.children)
        serialized["metadata"]["objects"] = len(item.objects)
    elif isinstance(item, bpy.types.Image):
        serialized["type"] = "asset"
        serialized["path"] = item.filepath_from_user() or item_name
        serialized["metadata"]["size"] = list(getattr(item, "size", (0, 0)))
        serialized["metadata"]["source"] = _safe_name(getattr(item, "source", None), "UNKNOWN")
    else:
        if hasattr(item, "filepath"):
            filepath = _safe_path(getattr(item, "filepath", None), "")
            if filepath:
                serialized["path"] = filepath

    return serialized


def _maybe_read_text_file(path: str) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    extension = os.path.splitext(path)[1].lower()
    if extension not in _TEXT_FILE_EXTENSIONS:
        return None
    try:
        if os.path.getsize(path) > _MAX_INLINE_TEXT_BYTES:
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _file_browser_entry_path(directory: str, relative_path: str, name: str) -> str:
    if relative_path:
        if relative_path.startswith("//") or os.path.isabs(relative_path):
            return _resolved_fs_path(relative_path, relative_path)
        if directory:
            return os.path.normpath(os.path.join(directory, relative_path))
        return relative_path
    if directory:
        return os.path.normpath(os.path.join(directory, name))
    return name


def _serialize_file_browser_entry(context, entry) -> dict | None:
    if entry is None:
        return None

    directory = _file_browser_directory(context)
    name = _safe_name(getattr(entry, "name", None), "File")
    relative_path = _safe_path(getattr(entry, "relative_path", None), "")
    is_directory = bool(getattr(entry, "is_dir", False))
    path = _file_browser_entry_path(directory, relative_path, name)

    item_type = "resource"
    content = ""
    if not is_directory:
        inline_content = _maybe_read_text_file(path)
        if inline_content is not None:
            item_type = "script"
            content = inline_content

    metadata = {
        "class": entry.__class__.__name__,
        "directory": directory,
        "relative_path": relative_path,
        "is_directory": is_directory,
    }
    extension = os.path.splitext(name)[1].lower()
    if extension:
        metadata["extension"] = extension.lstrip(".")
    if os.path.exists(path):
        metadata["exists"] = True
        metadata["size_bytes"] = os.path.getsize(path) if os.path.isfile(path) else 0

    return {
        "type": item_type,
        "name": name,
        "path": path,
        "content": content,
        "metadata": metadata,
    }


def _serialize_asset_browser_item(context) -> dict | None:
    asset = getattr(context, "asset", None)
    active_file = getattr(context, "active_file", None)
    if asset is None and active_file is None:
        return None

    local_id = getattr(asset, "local_id", None) if asset is not None else None
    base = _serialize_outliner_id(local_id) if local_id is not None else None

    name = _safe_name(
        getattr(asset, "name", None)
        or getattr(active_file, "relative_path", None)
        or getattr(active_file, "name", None),
        "Asset",
    )
    library_path = _resolved_fs_path(getattr(asset, "full_library_path", None), "")
    relative_path = _safe_path(getattr(active_file, "relative_path", None), "")
    path = base["path"] if base is not None else library_path or relative_path or name
    if library_path and relative_path and base is None:
        path = f"{library_path}::{relative_path}"

    metadata = dict((base or {}).get("metadata", {}) or {})
    metadata.update({
        "class": "AssetRepresentation" if asset is not None else active_file.__class__.__name__,
        "asset_browser": True,
        "id_type": _safe_name(getattr(asset, "id_type", None), ""),
        "library_path": library_path,
        "relative_path": relative_path,
        "local_asset": bool(local_id),
    })
    if local_id is not None:
        metadata["local_id"] = _safe_name(getattr(local_id, "name_full", None), getattr(local_id, "name", None))

    return {
        "type": "asset",
        "name": base["name"] if base is not None else name,
        "path": path,
        "content": "",
        "metadata": metadata,
    }


def _iter_generic_context_targets(context) -> list[dict]:
    items = []
    seen_paths = set()
    for attr_name in _GENERIC_ID_CONTEXT_ATTRS:
        value = getattr(context, attr_name, None)
        if not _is_id_like(value):
            continue
        serialized = _serialize_outliner_id(value)
        if serialized is None:
            continue
        if serialized["path"] in seen_paths:
            continue
        seen_paths.add(serialized["path"])
        serialized.setdefault("metadata", {})["context_attr"] = attr_name
        items.append(serialized)
    return items


def _build_context_snapshot_item(context) -> dict:
    from .operators import _build_editor_context

    editor_context = _build_editor_context()
    metadata = dict(editor_context.get("metadata", {}) or {})
    metadata["source"] = "context_menu_fallback"

    space = getattr(context, "space_data", None)
    directory = _file_browser_directory(context) if getattr(space, "type", None) == "FILE_BROWSER" else ""
    if directory:
        metadata["file_browser_directory"] = directory
        metadata["file_browser_browse_mode"] = getattr(space, "browse_mode", None)

    generic_targets = _iter_generic_context_targets(context)
    if generic_targets:
        metadata["active_targets"] = generic_targets

    editor_type = _safe_name(metadata.get("active_editor_type"), "UNKNOWN")
    summary_lines = [
        f"Editor: {editor_type}",
    ]
    if metadata.get("blend_file_path"):
        summary_lines.append(f"Blend File: {metadata['blend_file_path']}")
    if metadata.get("active_scene"):
        summary_lines.append(f"Scene: {metadata['active_scene']}")
    if metadata.get("active_object"):
        summary_lines.append(f"Active Object: {metadata['active_object']}")
    selected_objects = metadata.get("selected_objects") or []
    if selected_objects:
        summary_lines.append(f"Selected Objects: {len(selected_objects)}")
    if metadata.get("active_node_tree"):
        summary_lines.append(f"Active Node Tree: {metadata['active_node_tree']}")
    if directory:
        summary_lines.append(f"Directory: {directory}")
    if metadata.get("active_asset_name"):
        summary_lines.append(f"Active Asset: {metadata['active_asset_name']}")
    if generic_targets:
        summary_lines.append("Active Data:")
        for item in generic_targets:
            item_class = (item.get("metadata") or {}).get("class", item["type"])
            summary_lines.append(f"- {item['name']} ({item_class}) at {item['path']}")

    return {
        "type": "scene" if metadata.get("active_scene") else "resource",
        "name": f"Blender Context ({editor_type})",
        "path": f"context://blender/{editor_type.lower()}",
        "content": "\n".join(summary_lines),
        "metadata": metadata,
    }


def _get_ws_client():
    """Access the global ws_client instance from __init__.py."""
    from . import _ws_client
    return _ws_client


class AGENTMGR_OT_add_to_context(bpy.types.Operator):
    """Add selected items to the Arkestrator context (pushed to server)."""

    bl_idname = "agent_manager.add_to_context"
    bl_label = _MENU_LABEL
    bl_options = {'REGISTER', 'UNDO'}

    source: StringProperty(default="viewport")

    def execute(self, context):
        ws = _get_ws_client()
        if ws is None or not ws.connected:
            self.report({'WARNING'}, "Not connected to server")
            return {'CANCELLED'}

        handlers = {
            "viewport": self._add_viewport_selection,
            "outliner": self._add_outliner_selection,
            "file_browser": self._add_file_browser_selection,
            "asset_browser": self._add_asset_browser_selection,
            "text_editor": self._add_text_block,
            "node_editor": self._add_node_selection,
            "generic_context": self._add_context_snapshot,
        }
        handler = handlers.get(self.source, self._add_context_snapshot)
        item = handler(context, ws)
        if item is None and self.source != "generic_context":
            item = self._add_context_snapshot(context, ws)
        if item is None:
            self.report({'WARNING'}, "Nothing available to add from this context")
            return {'CANCELLED'}

        screen = getattr(context, "screen", None)
        if screen is not None:
            for area in screen.areas:
                area.tag_redraw()

        self.report({'INFO'}, f"Added to context: @{item['index']} {item['name']}")
        return {'FINISHED'}

    def _add_viewport_selection(self, context, ws):
        if getattr(context, "mode", "") == "EDIT_MESH":
            item = self._add_mesh_component_selection(context, ws)
            if item is not None:
                return item
        return self._add_viewport_objects(context, ws)

    def _add_viewport_objects(self, context, ws):
        selected = list(getattr(context, "selected_objects", []) or [])
        if not selected:
            return None

        if len(selected) == 1:
            obj = selected[0]
            return _send_context_item(ws, {
                "type": "node",
                "name": obj.name,
                "path": obj.name_full,
                "content": "",
                "metadata": self._build_object_metadata(obj),
            })

        grouped_items = []
        for obj in selected:
            grouped_items.append({
                "type": "node",
                "name": obj.name,
                "path": obj.name_full,
                "content": "",
                "metadata": self._build_object_metadata(obj),
            })

        return _push_grouped_item(
            ws,
            item_type="node",
            name=f"Selection ({len(grouped_items)} objects)",
            path="selection://blender/objects",
            heading="Selected Blender objects",
            selection_kind="objects",
            items=grouped_items,
        )

    def _add_mesh_component_selection(self, context, ws):
        selections = []
        for obj in getattr(context, "objects_in_mode", []) or []:
            if obj is None or obj.type != 'MESH' or obj.data is None:
                continue
            try:
                bm = bmesh.from_edit_mesh(obj.data)
            except Exception:
                continue

            selected_verts = sum(1 for vert in bm.verts if vert.select)
            selected_edges = sum(1 for edge in bm.edges if edge.select)
            selected_faces = sum(1 for face in bm.faces if face.select)
            if selected_verts == 0 and selected_edges == 0 and selected_faces == 0:
                continue

            selections.append({
                "type": "node",
                "name": f"{obj.name} (mesh selection)",
                "path": f"{obj.name_full}#mesh-selection",
                "content": "",
                "metadata": {
                    **self._build_object_metadata(obj),
                    "selection_kind": "mesh_components",
                    "selected_vertices": selected_verts,
                    "selected_edges": selected_edges,
                    "selected_faces": selected_faces,
                },
            })

        return _push_grouped_item(
            ws,
            item_type="node",
            name=f"Mesh Selection ({len(selections)} object{'s' if len(selections) != 1 else ''})",
            path="selection://blender/mesh-components",
            heading="Selected Blender mesh components",
            selection_kind="mesh_components",
            items=selections,
        )

    def _add_outliner_selection(self, context, ws):
        selected_ids = getattr(context, "selected_ids", None)
        items = []
        if selected_ids:
            for entry in selected_ids:
                serialized = _serialize_outliner_id(entry)
                if serialized is not None:
                    items.append(serialized)

        if not items:
            return self._add_viewport_objects(context, ws)

        item_type = items[0]["type"] if len({entry["type"] for entry in items}) == 1 else "resource"
        return _push_grouped_item(
            ws,
            item_type=item_type,
            name=f"Selection ({len(items)} outliner item{'s' if len(items) != 1 else ''})",
            path="selection://blender/outliner",
            heading="Selected Blender Outliner items",
            selection_kind="outliner_ids",
            items=items,
        )

    def _add_file_browser_selection(self, context, ws):
        items = []

        selected_files = getattr(context, "selected_files", None)
        if selected_files:
            for entry in selected_files:
                serialized = _serialize_file_browser_entry(context, entry)
                if serialized is not None:
                    items.append(serialized)

        active_file = getattr(context, "active_file", None)
        if active_file is not None and not items:
            serialized = _serialize_file_browser_entry(context, active_file)
            if serialized is not None:
                items.append(serialized)

        if not items:
            return None

        item_type = items[0]["type"] if len({entry["type"] for entry in items}) == 1 else "resource"
        return _push_grouped_item(
            ws,
            item_type=item_type,
            name=f"Selection ({len(items)} file browser item{'s' if len(items) != 1 else ''})",
            path="selection://blender/file-browser",
            heading="Selected Blender file browser items",
            selection_kind="file_browser",
            items=items,
        )

    def _add_asset_browser_selection(self, context, ws):
        item = _serialize_asset_browser_item(context)
        if item is None:
            return None
        return _send_context_item(ws, item)

    def _add_text_block(self, context, ws):
        space = getattr(context, "space_data", None)
        text = getattr(space, "text", None)
        if text is None:
            return None

        text_name = text.name
        text_path = text.filepath if text.filepath else text.name

        selected_text = ""
        if hasattr(text, "select_end_line_index"):
            cur_line = text.current_line_index
            sel_line = text.select_end_line_index
            cur_char = text.current_character
            sel_char = text.select_end_character
            if cur_line != sel_line or cur_char != sel_char:
                lines = text.as_string().split("\n")
                start_line = min(cur_line, sel_line)
                end_line = max(cur_line, sel_line)
                if start_line == end_line:
                    start_char = min(cur_char, sel_char)
                    end_char = max(cur_char, sel_char)
                    selected_text = lines[start_line][start_char:end_char]
                else:
                    sel_lines = []
                    if cur_line < sel_line:
                        sel_lines.append(lines[cur_line][cur_char:])
                        for line_index in range(cur_line + 1, sel_line):
                            sel_lines.append(lines[line_index])
                        sel_lines.append(lines[sel_line][:sel_char])
                    else:
                        sel_lines.append(lines[sel_line][sel_char:])
                        for line_index in range(sel_line + 1, cur_line):
                            sel_lines.append(lines[line_index])
                        sel_lines.append(lines[cur_line][:cur_char])
                    selected_text = "\n".join(sel_lines)

        if selected_text.strip():
            from_line = min(text.current_line_index, text.select_end_line_index) + 1
            to_line = max(text.current_line_index, text.select_end_line_index) + 1
            item = {
                "type": "script",
                "name": f"{text_name}:{from_line}-{to_line}",
                "path": text_path,
                "content": selected_text,
                "metadata": {
                    "extension": text_name.rsplit(".", 1)[-1] if "." in text_name else "py",
                    "selection": True,
                    "from_line": from_line,
                    "to_line": to_line,
                    "source_script": text_path,
                },
            }
        else:
            item = {
                "type": "script",
                "name": text_name,
                "path": text_path,
                "content": text.as_string(),
                "metadata": {
                    "extension": text_name.rsplit(".", 1)[-1] if "." in text_name else "py",
                },
            }

        return _send_context_item(ws, item)

    def _add_node_selection(self, context, ws):
        nodes = [_serialize_node_editor_node(context, node) for node in _iter_selected_node_editor_nodes(context)]
        return _push_grouped_item(
            ws,
            item_type="node",
            name=f"Selection ({len(nodes)} nodes)",
            path="selection://blender/node-editor",
            heading="Selected Blender nodes",
            selection_kind="node_editor",
            items=nodes,
        )

    def _add_context_snapshot(self, context, ws):
        return _send_context_item(ws, _build_context_snapshot_item(context))

    def _build_object_metadata(self, obj) -> dict:
        return _build_object_metadata_static(obj)

    @staticmethod
    def _build_object_metadata_static(obj) -> dict:
        return _build_object_metadata_static(obj)


def _draw_menu_entry(self, source: str):
    op = self.layout.operator(
        "agent_manager.add_to_context",
        text=_MENU_LABEL,
        icon='EXPORT',
    )
    op.source = source


def draw_viewport_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "viewport")


def draw_outliner_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "outliner")


def draw_file_browser_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "file_browser")


def draw_asset_browser_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "asset_browser")


def draw_text_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "text_editor")


def draw_node_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "node_editor")


def draw_generic_menu(self, context):
    self.layout.separator()
    _draw_menu_entry(self, "generic_context")


def register_menus():
    global _menus_registered, _registered_menu_specs
    if _menus_registered:
        return

    draw_map = {
        "viewport": draw_viewport_menu,
        "outliner": draw_outliner_menu,
        "file_browser": draw_file_browser_menu,
        "asset_browser": draw_asset_browser_menu,
        "text_editor": draw_text_menu,
        "node_editor": draw_node_menu,
        "generic_context": draw_generic_menu,
    }
    _registered_menu_specs = _iter_menu_specs()
    for menu_name, source in _registered_menu_specs:
        menu = getattr(bpy.types, menu_name, None)
        draw_fn = draw_map[source]
        if menu is None:
            continue
        menu.append(draw_fn)
    _menus_registered = True


def unregister_menus():
    global _menus_registered, _registered_menu_specs
    if not _menus_registered:
        return

    draw_map = {
        "viewport": draw_viewport_menu,
        "outliner": draw_outliner_menu,
        "file_browser": draw_file_browser_menu,
        "asset_browser": draw_asset_browser_menu,
        "text_editor": draw_text_menu,
        "node_editor": draw_node_menu,
        "generic_context": draw_generic_menu,
    }
    for menu_name, source in reversed(_registered_menu_specs):
        menu = getattr(bpy.types, menu_name, None)
        if menu is None:
            continue
        draw_fn = draw_map[source]
        try:
            menu.remove(draw_fn)
        except Exception:
            pass
    _registered_menu_specs = ()
    _menus_registered = False
