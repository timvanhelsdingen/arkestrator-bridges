@tool
extends RefCounted
## Applies FileChange arrays from job_complete messages to the Godot project.


static func apply_file_changes(files: Array, project_root: String = "") -> Dictionary:
	var root := project_root.strip_edges()
	if root.is_empty():
		root = ProjectSettings.globalize_path("res://")

	var applied := 0
	var failed := 0
	var errors: Array[String] = []

	for entry in files:
		if not (entry is Dictionary):
			failed += 1
			continue
		var file_dict: Dictionary = entry
		var path := str(file_dict.get("path", "")).strip_edges()
		var content := str(file_dict.get("content", ""))
		var action := str(file_dict.get("action", "modify")).strip_edges().to_lower()

		if path.is_empty():
			failed += 1
			errors.append("Empty path in file change")
			continue

		var abs_path := _resolve_path(path, root)
		if abs_path.is_empty():
			failed += 1
			errors.append("Path traversal blocked for '%s'" % path)
			continue

		match action:
			"create", "modify":
				var dir_err := DirAccess.make_dir_recursive_absolute(abs_path.get_base_dir())
				if dir_err != OK and dir_err != ERR_ALREADY_EXISTS:
					failed += 1
					errors.append("mkdir failed for %s: %s" % [path, error_string(dir_err)])
					continue
				var encoding := str(file_dict.get("encoding", "utf8")).strip_edges().to_lower()
				var binary_content = file_dict.get("binaryContent", "")
				if encoding == "base64" and binary_content is String and not (binary_content as String).is_empty():
					var file := FileAccess.open(abs_path, FileAccess.WRITE)
					if file == null:
						failed += 1
						errors.append("Write failed for %s: %s" % [path, error_string(FileAccess.get_open_error())])
						continue
					file.store_buffer(Marshalls.base64_to_raw(binary_content as String))
					file.close()
				else:
					var file := FileAccess.open(abs_path, FileAccess.WRITE)
					if file == null:
						failed += 1
						errors.append("Write failed for %s: %s" % [path, error_string(FileAccess.get_open_error())])
						continue
					file.store_string(content)
					file.close()
				applied += 1
			"delete":
				if FileAccess.file_exists(abs_path):
					var rm_err := DirAccess.remove_absolute(abs_path)
					if rm_err != OK:
						failed += 1
						errors.append("Delete failed for %s: %s" % [path, error_string(rm_err)])
						continue
				applied += 1
			_:
				failed += 1
				errors.append("Unknown action '%s' for %s" % [action, path])

	return {
		"applied": applied,
		"failed": failed,
		"errors": errors,
	}


static func trigger_filesystem_scan(editor_interface: EditorInterface) -> void:
	if editor_interface == null:
		return
	var fs := editor_interface.get_resource_filesystem()
	if fs == null:
		return
	if fs.has_method("scan_sources"):
		fs.call_deferred("scan_sources")
	elif fs.has_method("scan"):
		fs.call_deferred("scan")


## Resolve a file path to an absolute path.
## Returns empty string if the resolved path escapes the project root (path traversal protection).
static func _resolve_path(path: String, project_root: String) -> String:
	var resolved: String
	if path.begins_with("res://"):
		resolved = ProjectSettings.globalize_path(path)
	elif path.is_absolute_path():
		resolved = path
	else:
		resolved = project_root.path_join(path)

	# Normalize to remove any ".." or "." components
	resolved = resolved.simplify_path()
	var real_root := project_root.simplify_path()

	# Ensure the resolved path stays within the project root
	if resolved != real_root and not resolved.begins_with(real_root + "/"):
		push_warning("Path traversal blocked: '%s' resolves to '%s' which is outside project root '%s'" % [path, resolved, real_root])
		return ""
	return resolved
