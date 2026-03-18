"""Context menu integration for Arkestrator context capture.

Uses Unreal ToolMenus to surface "Add to Arkestrator Context" across
level, viewport, content browser, and top-menu entry points. The action
captures whichever editor selection types are currently available:
actors, assets, folders, and material graph node selections when the
active material editor exposes them.
"""

from __future__ import annotations

import unreal

_MENU_LABEL = "Add to Arkestrator Context"
_menus_registered = False
_next_context_index = 1
_registered_entries: list[tuple[str, str]] = []
_MENU_TARGETS = (
    ("LevelEditor.ActorContextMenu", "Add selected actors to Arkestrator context"),
    ("LevelEditor.LevelViewportContextMenu", "Add the current viewport selection to Arkestrator context"),
    ("ContentBrowser.AssetContextMenu", "Add selected assets to Arkestrator context"),
    ("ContentBrowser.FolderContextMenu", "Add selected folders to Arkestrator context"),
    ("LevelEditor.MainMenu.Tools", "Add the current editor selection to Arkestrator context"),
)


def reset_context_index():
    """Reset the context index counter (called on reconnect)."""
    global _next_context_index
    _next_context_index = 1


def _get_ws_client():
    from . import _ws_client
    return _ws_client


def _next_index() -> int:
    global _next_context_index
    value = _next_context_index
    _next_context_index += 1
    return value


def _push_single_item(ws, item: dict) -> dict:
    enriched = {
        "index": _next_index(),
        **item,
    }
    ws.send_context_item(enriched)
    return enriched


def _push_grouped_item(ws, *, item_type: str, name: str, path: str, heading: str, selection_kind: str, items: list[dict]) -> dict | None:
    if not items:
        return None

    if len(items) == 1:
        return _push_single_item(ws, items[0])

    summary_lines = []
    for entry in items:
        meta = entry.get("metadata", {}) or {}
        label = meta.get("class", entry.get("type", item_type))
        detail = meta.get("selection", "")
        suffix = f": {detail}" if detail else ""
        summary_lines.append(f"- {entry.get('name', 'Item')} ({label}) at {entry.get('path', '')}{suffix}")

    grouped = {
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
    return _push_single_item(ws, grouped)


def _selected_level_actors() -> list[dict]:
    items: list[dict] = []
    try:
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    except Exception:
        actor_subsystem = None

    if not actor_subsystem:
        return items

    try:
        selected = list(actor_subsystem.get_selected_level_actors())
    except Exception:
        selected = []

    for actor in selected:
        try:
            loc = actor.get_actor_location()
            items.append({
                "type": "node",
                "name": actor.get_actor_label(),
                "path": actor.get_path_name(),
                "content": "",
                "metadata": {
                    "class": actor.get_class().get_name(),
                    "location": f"({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f})",
                },
            })
        except Exception:
            continue
    return items


def _selected_assets() -> list[dict]:
    items: list[dict] = []
    asset_entries: list = []

    try:
        asset_entries = list(unreal.EditorUtilityLibrary.get_selected_assets())
    except Exception:
        asset_entries = []

    for asset in asset_entries:
        try:
            class_name = asset.get_class().get_name()
        except Exception:
            class_name = asset.__class__.__name__
        try:
            asset_name = asset.get_name()
        except Exception:
            asset_name = str(asset)
        try:
            asset_path = asset.get_path_name()
        except Exception:
            asset_path = asset_name

        items.append({
            "type": "asset",
            "name": asset_name,
            "path": asset_path,
            "content": "",
            "metadata": {
                "class": class_name,
            },
        })

    return items


def _selected_folder_items() -> list[dict]:
    items: list[dict] = []
    try:
        folders = list(unreal.EditorUtilityLibrary.get_selected_folder_paths())
    except Exception:
        folders = []

    for folder in folders:
        folder_path = str(folder or "").strip()
        if not folder_path:
            continue
        folder_name = folder_path.rsplit("/", 1)[-1] or folder_path
        items.append({
            "type": "asset",
            "name": folder_name,
            "path": folder_path,
            "content": "",
            "metadata": {
                "class": "ContentBrowserFolder",
                "folder_path": folder_path,
            },
        })

    return items


def _selected_material_nodes() -> list[dict]:
    items: list[dict] = []
    try:
        selected_assets = list(unreal.EditorUtilityLibrary.get_selected_assets())
    except Exception:
        selected_assets = []

    material_library = getattr(unreal, "MaterialEditingLibrary", None)
    if material_library is None:
        return items

    for asset in selected_assets:
        try:
            selected_nodes = list(material_library.get_selected_nodes(asset))
        except Exception:
            continue

        if not selected_nodes:
            continue

        asset_name = asset.get_name() if hasattr(asset, "get_name") else str(asset)
        asset_path = asset.get_path_name() if hasattr(asset, "get_path_name") else asset_name

        for node in selected_nodes:
            try:
                node_name = node.get_name()
            except Exception:
                node_name = str(node)
            try:
                node_path = node.get_path_name()
            except Exception:
                node_path = f"{asset_path}:{node_name}"

            items.append({
                "type": "node",
                "name": f"{asset_name}:{node_name}",
                "path": node_path,
                "content": "",
                "metadata": {
                    "class": node.get_class().get_name() if hasattr(node, "get_class") else node.__class__.__name__,
                    "selection_kind": "material_nodes",
                    "material": asset_name,
                    "material_path": asset_path,
                },
            })

    return items


def _selected_blueprint_items() -> list[dict]:
    """Build rich context items for selected Blueprint assets."""
    from .blueprint_utils import is_blueprint, get_blueprint_info
    items: list[dict] = []
    try:
        selected_assets = list(unreal.EditorUtilityLibrary.get_selected_assets())
    except Exception:
        return items

    for asset in selected_assets:
        if not is_blueprint(asset):
            continue

        try:
            asset_name = asset.get_name()
        except Exception:
            asset_name = str(asset)
        try:
            asset_path = asset.get_path_name()
        except Exception:
            asset_path = asset_name

        bp_info = get_blueprint_info(asset)

        # Build human-readable content summary
        content_lines = [f"Blueprint: {asset_name}"]
        if bp_info:
            if bp_info.get("parent_class"):
                content_lines.append(f"Parent: {bp_info['parent_class']}")
            comps = bp_info.get("components", [])
            if comps:
                content_lines.append(f"Components ({len(comps)}):")
                for c in comps[:20]:
                    root_tag = " [root]" if c.get("is_root") else ""
                    content_lines.append(f"  - {c['name']} ({c['class']}){root_tag}")
            vars_ = bp_info.get("variables", [])
            if vars_:
                content_lines.append(f"Variables ({len(vars_)}):")
                for v in vars_[:20]:
                    content_lines.append(f"  - {v['name']}: {v['type']}")
            funcs = bp_info.get("functions", [])
            if funcs:
                content_lines.append(f"Functions ({len(funcs)}): {', '.join(funcs[:20])}")
            ifaces = bp_info.get("interfaces", [])
            if ifaces:
                content_lines.append(f"Interfaces: {', '.join(ifaces)}")

        metadata: dict = {
            "class": "Blueprint",
            "selection_kind": "blueprints",
        }
        if bp_info:
            metadata["blueprint"] = bp_info

        items.append({
            "type": "asset",
            "name": asset_name,
            "path": asset_path,
            "content": "\n".join(content_lines),
            "metadata": metadata,
        })

    return items


def _on_add_to_context():
    """Callback for the menu item."""
    ws = _get_ws_client()
    if ws is None or not ws.connected:
        unreal.log_warning("[ArkestratorBridge] Not connected to server")
        return

    actor_items = _selected_level_actors()
    asset_items = _selected_assets()
    folder_items = _selected_folder_items()
    material_node_items = _selected_material_nodes()
    blueprint_items = _selected_blueprint_items()

    added = 0
    for grouped in (
        _push_grouped_item(
            ws,
            item_type="node",
            name=f"Selection ({len(actor_items)} actors)",
            path="selection://unreal/actors",
            heading="Selected Unreal actors",
            selection_kind="actors",
            items=actor_items,
        ),
        _push_grouped_item(
            ws,
            item_type="asset",
            name=f"Selection ({len(asset_items)} assets)",
            path="selection://unreal/assets",
            heading="Selected Unreal assets",
            selection_kind="assets",
            items=asset_items,
        ),
        _push_grouped_item(
            ws,
            item_type="asset",
            name=f"Selection ({len(folder_items)} folders)",
            path="selection://unreal/folders",
            heading="Selected Unreal content folders",
            selection_kind="folders",
            items=folder_items,
        ),
        _push_grouped_item(
            ws,
            item_type="node",
            name=f"Selection ({len(material_node_items)} material nodes)",
            path="selection://unreal/material-nodes",
            heading="Selected Unreal material graph nodes",
            selection_kind="material_nodes",
            items=material_node_items,
        ),
        _push_grouped_item(
            ws,
            item_type="asset",
            name=f"Selection ({len(blueprint_items)} blueprints)",
            path="selection://unreal/blueprints",
            heading="Selected Unreal Blueprints",
            selection_kind="blueprints",
            items=blueprint_items,
        ),
    ):
        if grouped is not None:
            added += 1

    if added == 0:
        unreal.log("[ArkestratorBridge] No selected actors/assets/folders/material nodes/blueprints")
    elif added == 1:
        unreal.log("[ArkestratorBridge] Added 1 selection group to Arkestrator context")
    else:
        unreal.log(f"[ArkestratorBridge] Added {added} selection groups to Arkestrator context")


def _menu_exists(tool_menus, menu_name: str) -> bool:
    try:
        finder = getattr(tool_menus, "find_menu", None)
        if finder is None:
            return True
        return finder(menu_name) is not None
    except Exception:
        return False


def register_menus():
    """Register the context menu entries via ToolMenus."""
    global _menus_registered
    if _menus_registered:
        return

    try:
        tool_menus = unreal.ToolMenus.get()
        _registered_entries.clear()
        for menu_name, tooltip in _MENU_TARGETS:
            if not _menu_exists(tool_menus, menu_name):
                continue

            entry_name = f"Arkestrator_{menu_name.replace('.', '_')}_AddContext"
            menu = tool_menus.extend_menu(menu_name)
            if not menu:
                continue

            entry = unreal.ToolMenuEntry(
                name=entry_name,
                type=unreal.MultiBlockType.MENU_ENTRY,
                insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
            )
            entry.set_label(_MENU_LABEL)
            entry.set_tool_tip(tooltip)
            entry.set_string_command(
                unreal.ToolMenuStringCommandType.PYTHON,
                "",
                "from arkestrator_bridge.context_menu import _on_add_to_context; _on_add_to_context()",
            )
            menu.add_menu_entry("", entry)
            _registered_entries.append((menu_name, entry_name))

        tool_menus.refresh_all_widgets()
        _menus_registered = True
    except Exception as exc:
        # ToolMenus API varies across UE versions; missing surfaces should not crash startup.
        print(f"[ArkestratorBridge] Failed to register context menus: {exc}")


def unregister_menus():
    """Clean up state on unregister."""
    global _menus_registered, _next_context_index
    try:
        tool_menus = unreal.ToolMenus.get()
        for menu_name, entry_name in _registered_entries:
            if not _menu_exists(tool_menus, menu_name):
                continue
            menu = tool_menus.find_menu(menu_name) if hasattr(tool_menus, "find_menu") else tool_menus.extend_menu(menu_name)
            if not menu:
                continue
            try:
                menu.remove_menu_entry("", entry_name)
            except Exception:
                pass
        tool_menus.refresh_all_widgets()
    except Exception:
        pass

    _registered_entries.clear()
    _menus_registered = False
    _next_context_index = 1
