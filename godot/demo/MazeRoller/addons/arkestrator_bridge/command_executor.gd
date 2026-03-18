@tool
extends RefCounted
## Executes agent-generated GDScript commands within the Godot editor.
##
## Each command is expected to have a `language` and `script` field.
## For GDScript commands, a temporary script is created and its `run()`
## method is called with the EditorInterface as an argument.

## Execute a list of CommandResult dictionaries.
## Returns { "executed": int, "failed": int, "skipped": int, "errors": Array[String] }
static func execute_commands(commands: Array, editor_interface: EditorInterface) -> Dictionary:
	var executed := 0
	var failed := 0
	var skipped := 0
	var errors: Array[String] = []

	for cmd in commands:
		if not (cmd is Dictionary):
			skipped += 1
			continue

		var language := str(cmd.get("language", "")).to_lower()
		var script_text := str(cmd.get("script", ""))
		var description := str(cmd.get("description", ""))

		if script_text.strip_edges().is_empty():
			skipped += 1
			continue

		# Currently only GDScript is supported in the Godot bridge
		if language != "gdscript" and language != "gd":
			skipped += 1
			errors.append("Unsupported language: %s (skipped)" % language)
			continue

		var result := _execute_gdscript(script_text, editor_interface, description)
		if result.success:
			executed += 1
		else:
			failed += 1
			errors.append(result.error)

	return {
		"executed": executed,
		"failed": failed,
		"skipped": skipped,
		"errors": errors,
	}


## Execute a single GDScript snippet.
## The script must define a `run(editor: EditorInterface)` function.
## Returns { "success": bool, "error": String }
static func _execute_gdscript(script_text: String, editor_interface: EditorInterface, description: String) -> Dictionary:
	# Wrap the script if it doesn't already contain a run() function
	var source := script_text
	if source.find("func run(") < 0:
		# Strip leading 'extends' declarations before wrapping — they can't live inside a function body
		var raw_lines := source.split("\n")
		var first_code_line := 0
		while first_code_line < raw_lines.size() and raw_lines[first_code_line].strip_edges().begins_with("extends"):
			first_code_line += 1
		var body := "\n".join(raw_lines.slice(first_code_line))
		# Wrap bare code in a run() function
		var indented := ""
		for line in body.split("\n"):
			indented += "\t%s\n" % line
		source = "extends RefCounted\n\nfunc run(editor: EditorInterface) -> void:\n%s" % indented

	# Ensure it extends something
	if not source.strip_edges().begins_with("extends") and not source.strip_edges().begins_with("@"):
		source = "extends RefCounted\n\n%s" % source

	var gd_script := GDScript.new()
	gd_script.source_code = source
	var err := gd_script.reload()
	if err != OK:
		return {"success": false, "error": "Failed to compile GDScript: %s (%s)" % [error_string(err), description]}

	var instance = gd_script.new()
	if instance == null:
		return {"success": false, "error": "Failed to instantiate GDScript (%s)" % description}

	if not instance.has_method("run"):
		return {"success": false, "error": "GDScript has no run() method (%s)" % description}

	# Execute the run method
	var call_err: Variant = null
	call_err = instance.call("run", editor_interface)

	# If run() returns a Dictionary with an error, report it
	if call_err is Dictionary and call_err.has("error"):
		return {"success": false, "error": str(call_err.get("error", "Unknown error"))}

	return {"success": true, "error": ""}
