@tool
extends EditorContextMenuPlugin
## Context menu integration for Arkestrator Bridge.
## Adds "Add to Arkestrator Context" option in Scene Tree, FileSystem, and Script Editor
## right-click menus. Emits signal when user selects items to add to the context bag.

signal item_added(item: Dictionary)

## Which slot this instance is registered for (set by plugin.gd before registering)
var slot_type: int = -1

## Paths from the last _popup_menu call — used by callbacks to know the context
var _last_paths: PackedStringArray = PackedStringArray()


func _popup_menu(paths: PackedStringArray) -> void:
	_last_paths = paths
	# For the code editor slot, always show the menu even if paths is empty
	if paths.is_empty() and slot_type != EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR_CODE:
		return
	add_context_menu_item("Add to Arkestrator Context", Callable(self, "_on_add_to_context"))


func _on_add_to_context(selection: Variant) -> void:
	# For the script code editor slot, handle via stored paths + CodeEdit
	if slot_type == EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR_CODE:
		_handle_code_edit_selection(selection)
		return

	if selection == null:
		return

	# Selection type depends on the slot:
	# SCENE_TREE → Array of Node references
	# FILESYSTEM → PackedStringArray of file paths
	# SCRIPT_EDITOR → Array with a single Script reference
	if selection is PackedStringArray:
		_handle_filesystem_selection(selection as PackedStringArray)
	elif selection is Array:
		var arr := selection as Array
		if arr.is_empty():
			return
		if arr[0] is Script:
			_handle_script_selection(arr)
		elif arr[0] is Node:
			_handle_node_selection(arr)
		else:
			# Fallback: treat as paths
			var paths := PackedStringArray()
			for item in arr:
				paths.append(str(item))
			_handle_filesystem_selection(paths)
	else:
		push_warning("[ArkestratorBridge] Unexpected selection type: %s" % typeof(selection))


func _handle_node_selection(nodes: Array) -> void:
	var selected_items: Array[Dictionary] = []
	for node in nodes:
		if node == null or not (node is Node):
			continue
		var n := node as Node
		var script_path := ""
		if n.get_script() is Script:
			script_path = (n.get_script() as Script).resource_path

		var metadata := {
			"class": n.get_class(),
		}
		if not script_path.is_empty():
			metadata["script"] = script_path

		# Gather exported properties as key info
		var props := {}
		for prop in n.get_property_list():
			if prop.get("usage", 0) & PROPERTY_USAGE_EDITOR:
				var prop_name: String = prop.get("name", "")
				# Skip internal/meta properties
				if prop_name.begins_with("_") or prop_name in ["script", "resource_path", "resource_name"]:
					continue
				var val: Variant = n.get(prop_name)
				# Only include simple types (not objects/resources)
				if val is bool or val is int or val is float or val is String:
					props[prop_name] = val
				elif val is Vector2 or val is Vector3:
					props[prop_name] = str(val)
		if not props.is_empty():
			metadata["properties"] = props

		var node_path: String = str(n.get_path()) if n.is_inside_tree() else str(n.name)
		selected_items.append({
			"type": "node",
			"name": str(n.name),
			"path": node_path,
			"content": "",
			"metadata": metadata,
		})

	if selected_items.is_empty():
		return

	if selected_items.size() == 1:
		item_added.emit(selected_items[0])
		return

	var summary_lines: Array[String] = []
	for entry in selected_items:
		var meta := entry.get("metadata", {}) as Dictionary
		summary_lines.append(
			"- %s (%s) at %s" % [
				str(entry.get("name", "")),
				str(meta.get("class", "Node")),
				str(entry.get("path", "")),
			]
		)

	item_added.emit({
		"type": "node",
		"name": "Selection (%d nodes)" % selected_items.size(),
		"path": "selection://godot/nodes",
		"content": "Selected Godot nodes:\n%s" % "\n".join(summary_lines),
		"metadata": {
			"class": "SelectionGroup",
			"selection_group": true,
			"selection_kind": "nodes",
			"count": selected_items.size(),
			"items": selected_items,
		},
	})


func _handle_filesystem_selection(paths: PackedStringArray) -> void:
	var selected_items: Array[Dictionary] = []
	for path in paths:
		var path_str := str(path).strip_edges()
		if path_str.is_empty():
			continue

		var ext := path_str.get_extension().to_lower()
		var file_name := path_str.get_file()

		# Determine type based on extension
		var item_type := "asset"
		var content := ""
		var metadata := {}

		if ext in ["gd", "gdshader", "tres", "cfg", "tscn", "json", "txt", "md", "toml", "yaml", "yml", "csv", "xml", "html", "css", "js", "ts", "py", "sh", "bat"]:
			# Text-based files: read content
			if ext == "gd":
				item_type = "script"
			elif ext == "tscn":
				item_type = "scene"
			elif ext == "tres":
				item_type = "resource"
			else:
				item_type = "asset"

			var abs_path := path_str
			if path_str.begins_with("res://"):
				abs_path = ProjectSettings.globalize_path(path_str)
			if FileAccess.file_exists(abs_path):
				content = FileAccess.get_file_as_string(abs_path)
			metadata["extension"] = ext
		else:
			# Binary assets (images, audio, models, etc.)
			item_type = "asset"
			metadata["extension"] = ext
			# Try to get file size
			var abs_path := path_str
			if path_str.begins_with("res://"):
				abs_path = ProjectSettings.globalize_path(path_str)
			if FileAccess.file_exists(abs_path):
				var f := FileAccess.open(abs_path, FileAccess.READ)
				if f != null:
					metadata["size_bytes"] = f.get_length()
					f.close()

		selected_items.append({
			"type": item_type,
			"name": file_name,
			"path": path_str,
			"content": content,
			"metadata": metadata,
		})

	if selected_items.is_empty():
		return
	if selected_items.size() == 1:
		item_added.emit(selected_items[0])
		return

	var grouped_type := "asset"
	var first_type := str(selected_items[0].get("type", "asset"))
	var uniform_type := true
	for entry in selected_items:
		if str(entry.get("type", "asset")) != first_type:
			uniform_type = false
			break
	if uniform_type:
		grouped_type = first_type

	var summary_lines: Array[String] = []
	var content_chunks: Array[String] = []
	for entry in selected_items:
		summary_lines.append(
			"- [%s] %s" % [str(entry.get("type", "asset")), str(entry.get("path", ""))]
		)
		var entry_content := str(entry.get("content", ""))
		if not entry_content.is_empty():
			content_chunks.append(
				"## %s (%s)\n%s" % [
					str(entry.get("name", "")),
					str(entry.get("path", "")),
					entry_content,
				]
			)

	item_added.emit({
		"type": grouped_type,
		"name": "Selection (%d files)" % selected_items.size(),
		"path": "selection://godot/filesystem",
		"content": "\n\n".join(content_chunks),
		"metadata": {
			"class": "SelectionGroup",
			"selection_group": true,
			"selection_kind": "files",
			"count": selected_items.size(),
			"summary": summary_lines,
			"items": selected_items,
		},
	})


func _handle_code_edit_selection(selection: Variant) -> void:
	# Get script path from _last_paths (set by _popup_menu)
	var script_path := ""
	if not _last_paths.is_empty():
		script_path = str(_last_paths[0])

	var script_name := script_path.get_file() if not script_path.is_empty() else "selection"
	if script_path.is_empty():
		script_path = "(unknown)"

	# Try to get the CodeEdit from the selection
	var ce: CodeEdit = null
	if selection is Array:
		var arr := selection as Array
		if not arr.is_empty() and arr[0] is CodeEdit:
			ce = arr[0] as CodeEdit
	elif selection is CodeEdit:
		ce = selection as CodeEdit

	if ce != null:
		var selected_text := ce.get_selected_text()
		var has_selection := not selected_text.strip_edges().is_empty()

		if has_selection:
			var from_line := ce.get_selection_from_line() + 1
			var to_line := ce.get_selection_to_line() + 1
			item_added.emit({
				"type": "script",
				"name": "%s:%d-%d" % [script_name, from_line, to_line],
				"path": script_path,
				"content": selected_text,
				"metadata": {
					"extension": script_path.get_extension().to_lower(),
					"selection": true,
					"from_line": from_line,
					"to_line": to_line,
					"source_script": script_path,
				},
			})
		else:
			# No selection — read full file content from disk
			var content := ce.text
			if script_path != "(unknown)":
				var abs_path := script_path
				if script_path.begins_with("res://"):
					abs_path = ProjectSettings.globalize_path(script_path)
				if FileAccess.file_exists(abs_path):
					content = FileAccess.get_file_as_string(abs_path)
			item_added.emit({
				"type": "script",
				"name": script_name,
				"path": script_path,
				"content": content,
				"metadata": {"extension": script_path.get_extension().to_lower()},
			})
	else:
		# No CodeEdit available — use the stored script path to read file from disk
		if script_path == "(unknown)":
			push_warning("[ArkestratorBridge] Could not determine script for code context menu")
			return
		var content := ""
		var abs_path := script_path
		if script_path.begins_with("res://"):
			abs_path = ProjectSettings.globalize_path(script_path)
		if FileAccess.file_exists(abs_path):
			content = FileAccess.get_file_as_string(abs_path)
		item_added.emit({
			"type": "script",
			"name": script_name,
			"path": script_path,
			"content": content,
			"metadata": {"extension": script_path.get_extension().to_lower()},
		})


func _handle_script_selection(scripts: Array) -> void:
	var selected_items: Array[Dictionary] = []
	for script_ref in scripts:
		if script_ref == null or not (script_ref is Script):
			continue
		var s := script_ref as Script
		var path := s.resource_path
		var file_name := path.get_file()

		selected_items.append({
			"type": "script",
			"name": file_name,
			"path": path,
			"content": s.source_code,
			"metadata": {"extension": path.get_extension().to_lower()},
		})

	if selected_items.is_empty():
		return
	if selected_items.size() == 1:
		item_added.emit(selected_items[0])
		return

	var content_chunks: Array[String] = []
	var summary_lines: Array[String] = []
	for entry in selected_items:
		var path := str(entry.get("path", ""))
		summary_lines.append("- %s" % path)
		var entry_content := str(entry.get("content", ""))
		if not entry_content.is_empty():
			content_chunks.append(
				"## %s (%s)\n%s" % [
					str(entry.get("name", "")),
					path,
					entry_content,
				]
			)

	item_added.emit({
		"type": "script",
		"name": "Selection (%d scripts)" % selected_items.size(),
		"path": "selection://godot/scripts",
		"content": "\n\n".join(content_chunks),
		"metadata": {
			"extension": "multi",
			"class": "SelectionGroup",
			"selection_group": true,
			"selection_kind": "scripts",
			"count": selected_items.size(),
			"summary": summary_lines,
			"items": selected_items,
		},
	})
