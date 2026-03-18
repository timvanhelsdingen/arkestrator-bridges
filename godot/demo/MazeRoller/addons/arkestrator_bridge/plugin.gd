@tool
extends EditorPlugin

const SETTING_SERVER_URL := "arkestrator_bridge/server_url"
const SETTING_AUTO_CONNECT := "arkestrator_bridge/auto_connect"
const SETTING_AUTO_SAVE_SCENE := "arkestrator_bridge/auto_save_scene"
const SETTING_AUTO_RELOAD_SCENE := "arkestrator_bridge/auto_reload_scene"
const SETTING_AUTO_APPLY_FILES := "arkestrator_bridge/auto_apply_files"
const SETTING_AUTO_EXECUTE_COMMANDS := "arkestrator_bridge/auto_execute_commands"
const DEFAULT_SERVER_URL := "ws://localhost:7800/ws"
const DEFAULT_AUTO_CONNECT := true
const DEFAULT_AUTO_SAVE_SCENE := true
const DEFAULT_AUTO_RELOAD_SCENE := true
const DEFAULT_AUTO_APPLY_FILES := true
const DEFAULT_AUTO_EXECUTE_COMMANDS := true

## How often (seconds) to check if editor context changed and push updates.
const CONTEXT_PUSH_INTERVAL := 2.0
const SHARED_CONFIG_REFRESH_INTERVAL := 3.0

var _ws_client: Node
var _file_applier_script: Script
var _command_executor_script: Script
var _context_menu_script: Script
var _dock: PanelContainer

# Context menu plugins (one per slot)
var _ctx_menu_scene_tree: EditorContextMenuPlugin
var _ctx_menu_filesystem: EditorContextMenuPlugin
var _ctx_menu_script_editor: EditorContextMenuPlugin
var _ctx_menu_script_code: EditorContextMenuPlugin

# Context bag tracking (items pushed to server immediately)
var _context_bag_next_index: int = 1

# Settings UI
var _server_url_edit: LineEdit
var _auto_connect_checkbox: CheckBox
var _auto_reload_checkbox: CheckBox
var _auto_apply_checkbox: CheckBox
var _auto_execute_commands_checkbox: CheckBox
var _connect_button: Button
var _status_label: Label

# State
var _pending_reload_scene: String = ""
var _context_push_timer: float = 0.0
var _last_editor_context_hash: int = 0
var _shared_config_refresh_timer: float = 0.0
var _last_shared_api_key: String = ""
var _last_shared_ws_url: String = ""
var _last_shared_worker_name: String = ""
var _last_shared_machine_id: String = ""
var _follow_shared_ws_url: bool = false
var _last_invalid_shared_api_key: String = ""


func _enter_tree() -> void:
	_ensure_settings()
	_load_file_applier()
	_create_ws_client()
	_create_dock()
	_register_context_menus()
	add_tool_menu_item("Arkestrator Bridge: Focus Dock", Callable(self, "_focus_dock"))
	# Register self so the AgentManager SDK can discover this bridge
	Engine.set_meta("arkestrator_bridge", self)
	# Connect to EditorFileSystem signals for persistent auto-reload support.
	# sources_changed fires when external files change on disk (catches repo-mode agents
	# that write files directly without going through the bridge's job_complete flow).
	# filesystem_changed fires after a scan completes — used to sequence scene reloads.
	var _efs := get_editor_interface().get_resource_filesystem()
	if _efs != null:
		if not _efs.is_connected("filesystem_changed", Callable(self, "_on_filesystem_changed")):
			_efs.connect("filesystem_changed", Callable(self, "_on_filesystem_changed"))
		if not _efs.is_connected("sources_changed", Callable(self, "_on_sources_changed")):
			_efs.connect("sources_changed", Callable(self, "_on_sources_changed"))
	if _read_setting(SETTING_AUTO_CONNECT, DEFAULT_AUTO_CONNECT):
		call_deferred("_auto_connect")


func _exit_tree() -> void:
	remove_tool_menu_item("Arkestrator Bridge: Focus Dock")
	_unregister_context_menus()
	# Unregister from SDK discovery
	if Engine.has_meta("arkestrator_bridge"):
		Engine.remove_meta("arkestrator_bridge")
	if _ws_client != null:
		_ws_client.disconnect_from_server()
		_ws_client.queue_free()
		_ws_client = null
	if _dock != null and is_instance_valid(_dock):
		remove_control_from_docks(_dock)
		_dock.queue_free()
	_dock = null
	# Disconnect filesystem signals
	var _efs := get_editor_interface().get_resource_filesystem()
	if _efs != null:
		if _efs.is_connected("filesystem_changed", Callable(self, "_on_filesystem_changed")):
			_efs.disconnect("filesystem_changed", Callable(self, "_on_filesystem_changed"))
		if _efs.is_connected("sources_changed", Callable(self, "_on_sources_changed")):
			_efs.disconnect("sources_changed", Callable(self, "_on_sources_changed"))


func _process(delta: float) -> void:
	if _ws_client != null:
		_ws_client.poll()
		_ws_client.reconnect_tick(delta)
		_shared_config_refresh_timer -= delta
		if _shared_config_refresh_timer <= 0.0:
			_shared_config_refresh_timer = SHARED_CONFIG_REFRESH_INTERVAL
			_refresh_shared_credentials_if_needed()

	# Periodic editor context push
	_context_push_timer -= delta
	if _context_push_timer <= 0.0:
		_context_push_timer = CONTEXT_PUSH_INTERVAL
		_push_editor_context_if_changed()


# --- WebSocket Client Setup ---

func _create_ws_client() -> void:
	var script_path := "%s/ws_client.gd" % (get_script() as Script).resource_path.get_base_dir()
	var ws_script := load(script_path) as Script
	if ws_script == null:
		push_error("[ArkestratorBridge] Failed to load ws_client.gd")
		return
	_ws_client = Node.new()
	_ws_client.set_script(ws_script)
	_ws_client.name = "ArkestratorBridgeWS"
	add_child(_ws_client)
	_ws_client.connected.connect(_on_ws_connected)
	_ws_client.disconnected.connect(_on_ws_disconnected)
	_ws_client.reconnecting.connect(_on_ws_reconnecting)
	_ws_client.job_complete.connect(_on_job_complete)
	_ws_client.error_received.connect(_on_error_received)
	_ws_client.bridge_command_received.connect(_on_bridge_command_received)
	_ws_client.bridge_command_result_received.connect(_on_bridge_command_result_received)


func _load_file_applier() -> void:
	var base_dir: String = (get_script() as Script).resource_path.get_base_dir()
	var script_path := "%s/file_applier.gd" % base_dir
	_file_applier_script = load(script_path) as Script
	if _file_applier_script == null:
		push_error("[ArkestratorBridge] Failed to load file_applier.gd")
	var cmd_path := "%s/command_executor.gd" % base_dir
	_command_executor_script = load(cmd_path) as Script
	if _command_executor_script == null:
		push_error("[ArkestratorBridge] Failed to load command_executor.gd")
	var ctx_path := "%s/context_menu.gd" % base_dir
	_context_menu_script = load(ctx_path) as Script
	if _context_menu_script == null:
		push_error("[ArkestratorBridge] Failed to load context_menu.gd")


func _register_context_menus() -> void:
	if _context_menu_script == null:
		return
	# Create one instance per slot
	_ctx_menu_scene_tree = _context_menu_script.new() as EditorContextMenuPlugin
	_ctx_menu_scene_tree.slot_type = EditorContextMenuPlugin.CONTEXT_SLOT_SCENE_TREE
	_ctx_menu_scene_tree.item_added.connect(_on_context_item_added)
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_SCENE_TREE, _ctx_menu_scene_tree)

	_ctx_menu_filesystem = _context_menu_script.new() as EditorContextMenuPlugin
	_ctx_menu_filesystem.slot_type = EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM
	_ctx_menu_filesystem.item_added.connect(_on_context_item_added)
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM, _ctx_menu_filesystem)

	_ctx_menu_script_editor = _context_menu_script.new() as EditorContextMenuPlugin
	_ctx_menu_script_editor.slot_type = EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR
	_ctx_menu_script_editor.item_added.connect(_on_context_item_added)
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR, _ctx_menu_script_editor)

	_ctx_menu_script_code = _context_menu_script.new() as EditorContextMenuPlugin
	_ctx_menu_script_code.slot_type = EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR_CODE
	_ctx_menu_script_code.item_added.connect(_on_context_item_added)
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_SCRIPT_EDITOR_CODE, _ctx_menu_script_code)


func _unregister_context_menus() -> void:
	if _ctx_menu_scene_tree != null:
		remove_context_menu_plugin(_ctx_menu_scene_tree)
		_ctx_menu_scene_tree = null
	if _ctx_menu_filesystem != null:
		remove_context_menu_plugin(_ctx_menu_filesystem)
		_ctx_menu_filesystem = null
	if _ctx_menu_script_editor != null:
		remove_context_menu_plugin(_ctx_menu_script_editor)
		_ctx_menu_script_editor = null
	if _ctx_menu_script_code != null:
		remove_context_menu_plugin(_ctx_menu_script_code)
		_ctx_menu_script_code = null


# --- Settings ---

func _ensure_settings() -> void:
	var es := get_editor_interface().get_editor_settings()
	if not es.has_setting(SETTING_SERVER_URL):
		es.set_setting(SETTING_SERVER_URL, DEFAULT_SERVER_URL)
	if not es.has_setting(SETTING_AUTO_CONNECT):
		es.set_setting(SETTING_AUTO_CONNECT, DEFAULT_AUTO_CONNECT)
	if not es.has_setting(SETTING_AUTO_SAVE_SCENE):
		es.set_setting(SETTING_AUTO_SAVE_SCENE, DEFAULT_AUTO_SAVE_SCENE)
	if not es.has_setting(SETTING_AUTO_RELOAD_SCENE):
		es.set_setting(SETTING_AUTO_RELOAD_SCENE, DEFAULT_AUTO_RELOAD_SCENE)
	if not es.has_setting(SETTING_AUTO_APPLY_FILES):
		es.set_setting(SETTING_AUTO_APPLY_FILES, DEFAULT_AUTO_APPLY_FILES)
	if not es.has_setting(SETTING_AUTO_EXECUTE_COMMANDS):
		es.set_setting(SETTING_AUTO_EXECUTE_COMMANDS, DEFAULT_AUTO_EXECUTE_COMMANDS)


func _read_setting(key: String, fallback: Variant) -> Variant:
	var es := get_editor_interface().get_editor_settings()
	if not es.has_setting(key):
		return fallback
	return es.get_setting(key)


func _write_setting(key: String, value: Variant) -> void:
	get_editor_interface().get_editor_settings().set_setting(key, value)


# --- Dock UI ---

func _create_dock() -> void:
	_dock = PanelContainer.new()
	_dock.name = "Arkestrator Bridge"
	_dock.size_flags_vertical = Control.SIZE_EXPAND_FILL

	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 6)
	_dock.add_child(root)

	# --- Title ---
	var title := Label.new()
	title.text = "Arkestrator Bridge"
	title.add_theme_font_size_override("font_size", 16)
	root.add_child(title)

	var sep := HSeparator.new()
	root.add_child(sep)

	# --- Server URL ---
	var url_label := Label.new()
	url_label.text = "Server URL:"
	root.add_child(url_label)
	_server_url_edit = LineEdit.new()
	_server_url_edit.text = str(_read_setting(SETTING_SERVER_URL, DEFAULT_SERVER_URL))
	_server_url_edit.placeholder_text = DEFAULT_SERVER_URL
	root.add_child(_server_url_edit)

	var sep2 := HSeparator.new()
	root.add_child(sep2)

	# --- Checkboxes ---
	_auto_connect_checkbox = CheckBox.new()
	_auto_connect_checkbox.text = "Auto-connect on plugin load"
	_auto_connect_checkbox.button_pressed = _read_setting(SETTING_AUTO_CONNECT, DEFAULT_AUTO_CONNECT) == true
	root.add_child(_auto_connect_checkbox)

	_auto_reload_checkbox = CheckBox.new()
	_auto_reload_checkbox.text = "Auto-reload scene on completion"
	_auto_reload_checkbox.button_pressed = _read_setting(SETTING_AUTO_RELOAD_SCENE, DEFAULT_AUTO_RELOAD_SCENE) == true
	root.add_child(_auto_reload_checkbox)

	_auto_apply_checkbox = CheckBox.new()
	_auto_apply_checkbox.text = "Auto-apply file changes"
	_auto_apply_checkbox.button_pressed = _read_setting(SETTING_AUTO_APPLY_FILES, DEFAULT_AUTO_APPLY_FILES) == true
	root.add_child(_auto_apply_checkbox)

	_auto_execute_commands_checkbox = CheckBox.new()
	_auto_execute_commands_checkbox.text = "Auto-execute commands"
	_auto_execute_commands_checkbox.button_pressed = _read_setting(SETTING_AUTO_EXECUTE_COMMANDS, DEFAULT_AUTO_EXECUTE_COMMANDS) == true
	root.add_child(_auto_execute_commands_checkbox)

	var sep3 := HSeparator.new()
	root.add_child(sep3)

	# --- Connect / Disconnect ---
	_connect_button = Button.new()
	_connect_button.text = "Connect"
	_connect_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_connect_button.pressed.connect(_on_connect_pressed)
	root.add_child(_connect_button)

	# --- Status ---
	_status_label = Label.new()
	_status_label.text = "Status: Disconnected"
	root.add_child(_status_label)

	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


# --- Actions ---

func _read_shared_config() -> Dictionary:
	"""Read API key from shared config paths if available."""
	var home := ""
	if OS.has_feature("windows"):
		home = OS.get_environment("USERPROFILE")
	else:
		home = OS.get_environment("HOME")
	if home.is_empty():
		return {}
	for config_dir in [".arkestrator"]:
		var config_path := home.path_join(config_dir).path_join("config.json")
		if not FileAccess.file_exists(config_path):
			continue
		var file := FileAccess.open(config_path, FileAccess.READ)
		if file == null:
			continue
		var text := file.get_as_text()
		file.close()
		var parsed = JSON.parse_string(text)
		if parsed is Dictionary:
			return parsed
	return {}


func _is_loopback_ws_url(url: String) -> bool:
	var value := url.strip_edges().to_lower()
	if value.is_empty():
		return true
	return (
		value.begins_with("ws://localhost")
		or value.begins_with("wss://localhost")
		or value.begins_with("ws://127.0.0.1")
		or value.begins_with("wss://127.0.0.1")
		or value.begins_with("ws://[::1]")
		or value.begins_with("wss://[::1]")
	)


func _is_valid_api_key(value: String) -> bool:
	var trimmed := value.strip_edges()
	if not trimmed.begins_with("ark_") or trimmed.length() != 52:
		return false
	for idx in range(4, trimmed.length()):
		var code := trimmed.unicode_at(idx)
		var is_number := code >= 48 and code <= 57
		var is_lower_hex := code >= 97 and code <= 102
		var is_upper_hex := code >= 65 and code <= 70
		if not (is_number or is_lower_hex or is_upper_hex):
			return false
	return true


func _shared_api_key(shared: Dictionary) -> String:
	var raw_key := str(shared.get("apiKey", "")).strip_edges()
	if raw_key.is_empty():
		_last_invalid_shared_api_key = ""
		return ""
	if not _is_valid_api_key(raw_key):
		if raw_key != _last_invalid_shared_api_key:
			push_warning("[ArkestratorBridge] Ignoring malformed shared API key")
			_last_invalid_shared_api_key = raw_key
		return ""
	_last_invalid_shared_api_key = ""
	return raw_key


func _apply_shared_bridge_identity(shared: Dictionary) -> void:
	if _ws_client == null:
		return
	var worker := str(shared.get("workerName", "")).strip_edges()
	var machine := str(shared.get("machineId", "")).strip_edges()
	_ws_client.worker_name = worker
	_ws_client.machine_id = machine
	_last_shared_worker_name = worker
	_last_shared_machine_id = machine


func _auto_connect() -> void:
	var url := str(_read_setting(SETTING_SERVER_URL, DEFAULT_SERVER_URL)).strip_edges()
	var key := ""
	var follow_shared_ws := _is_loopback_ws_url(url)

	# Read API key from shared config (~/.arkestrator/config.json)
	var shared := _read_shared_config()
	key = _shared_api_key(shared)
	if shared.has("wsUrl") and follow_shared_ws:
		url = str(shared["wsUrl"])
	if not key.is_empty():
		print("[ArkestratorBridge] Auto-loaded API key from shared config")
	_apply_shared_bridge_identity(shared)
	_last_shared_api_key = key
	_last_shared_ws_url = str(shared.get("wsUrl", ""))
	_follow_shared_ws_url = follow_shared_ws

	if url.is_empty():
		return
	_ws_client.connect_to_server(url, key, _last_shared_worker_name, _last_shared_machine_id)
	_update_status("Connecting...")


func _on_connect_pressed() -> void:
	if _ws_client != null and _ws_client.is_connected_to_server():
		_ws_client.disconnect_from_server()
		_save_settings()
		return

	var url := _server_url_edit.text.strip_edges()
	var key := ""
	var follow_shared_ws := _is_loopback_ws_url(url)

	# Read API key from shared config (~/.arkestrator/config.json)
	var shared := _read_shared_config()
	key = _shared_api_key(shared)
	if shared.has("wsUrl") and follow_shared_ws:
		url = str(shared["wsUrl"])
	_apply_shared_bridge_identity(shared)
	_last_shared_api_key = key
	_last_shared_ws_url = str(shared.get("wsUrl", ""))
	_follow_shared_ws_url = follow_shared_ws

	if url.is_empty():
		_update_status("Error: Server URL is empty")
		return
	_save_settings()
	_ws_client.connect_to_server(url, key, _last_shared_worker_name, _last_shared_machine_id)
	_update_status("Connecting...")


func _refresh_shared_credentials_if_needed() -> void:
	if _ws_client == null:
		return
	# Only hot-refresh while actively connected/reconnecting.
	if not _ws_client.is_connected_to_server() and not _ws_client.is_reconnect_pending():
		return

	var shared := _read_shared_config()
	if shared.is_empty():
		return

	var new_key := _shared_api_key(shared)
	var new_ws := str(shared.get("wsUrl", ""))
	var new_worker_name := str(shared.get("workerName", "")).strip_edges()
	var new_machine_id := str(shared.get("machineId", "")).strip_edges()
	var effective_key := _last_shared_api_key if new_key.is_empty() else new_key
	var key_changed := not new_key.is_empty() and new_key != _last_shared_api_key
	var ws_changed := _follow_shared_ws_url and not new_ws.is_empty() and new_ws != _last_shared_ws_url
	var worker_changed := new_worker_name != _last_shared_worker_name
	var machine_changed := new_machine_id != _last_shared_machine_id
	if not key_changed and not ws_changed and not worker_changed and not machine_changed:
		return

	_last_shared_api_key = effective_key
	_last_shared_ws_url = new_ws
	_last_shared_worker_name = new_worker_name
	_last_shared_machine_id = new_machine_id
	_ws_client.worker_name = new_worker_name
	_ws_client.machine_id = new_machine_id

	var next_url := _server_url_edit.text.strip_edges()
	if _follow_shared_ws_url and not new_ws.is_empty():
		next_url = new_ws
	if next_url.is_empty():
		return

	_ws_client.connect_to_server(next_url, effective_key, new_worker_name, new_machine_id)
	_update_status("Updated shared credentials detected - reconnecting")


# --- WebSocket Callbacks ---

func _on_ws_connected() -> void:
	_update_status("Connected")
	_connect_button.text = "Disconnect"
	# Reset context bag index on new connection
	_context_bag_next_index = 1
	# Clear any stale context on the server
	_ws_client.send_context_clear()
	# Push current editor context immediately
	_push_editor_context()


func _on_ws_disconnected() -> void:
	_update_status("Disconnected")
	_connect_button.text = "Connect"


func _on_ws_reconnecting(seconds_remaining: float) -> void:
	_update_status("Reconnecting in %ds..." % ceili(seconds_remaining))


func _on_job_complete(_job_id: String, success: bool, files: Array, commands: Array, workspace_mode: String, error_text: String) -> void:
	if not error_text.is_empty():
		_update_status("Job failed: %s" % error_text)
	elif success:
		_update_status("Job completed")

	if success:
		if workspace_mode == "command" and not commands.is_empty():
			# Command mode: execute generated scripts
			if _auto_execute_commands_checkbox.button_pressed and _command_executor_script != null:
				var result: Dictionary = _command_executor_script.execute_commands(commands, get_editor_interface())
				var executed := int(result.get("executed", 0))
				var cmd_failed := int(result.get("failed", 0))
				_update_status("Commands: %d executed, %d failed" % [executed, cmd_failed])
			else:
				_update_status("%d command(s) received (auto-execute disabled)" % commands.size())
		elif not files.is_empty():
			# Auto-save scene only for file-apply flows (repo/sync), not command-mode execution.
			# Command-mode saves are best left explicit/manual to avoid editor instability.
			if _read_setting(SETTING_AUTO_SAVE_SCENE, DEFAULT_AUTO_SAVE_SCENE) == true:
				_save_active_scene()
			# Repo/sync mode: apply file changes
			if _auto_apply_checkbox.button_pressed and _file_applier_script != null:
				var result: Dictionary = _file_applier_script.apply_file_changes(files)
				var applied := int(result.get("applied", 0))
				var file_failed := int(result.get("failed", 0))
				_update_status("Files: %d applied, %d failed" % [applied, file_failed])
				_file_applier_script.trigger_filesystem_scan(get_editor_interface())

		# Auto-reload scene
		if _auto_reload_checkbox.button_pressed:
			_try_reload_active_scene()


func _on_error_received(code: String, message: String) -> void:
	_update_status("Error: [%s] %s" % [code, message])


func _on_bridge_command_received(sender_id: String, commands: Array, correlation_id: String) -> void:
	if not _auto_execute_commands_checkbox.button_pressed:
		print("[ArkestratorBridge] %d command(s) from %s (auto-execute disabled)" % [commands.size(), sender_id.substr(0, 8)])
		_ws_client.send_bridge_command_result(sender_id, correlation_id, true, 0, 0, commands.size(), ["Auto-execute commands is disabled"])
		return

	if _command_executor_script == null:
		print("[ArkestratorBridge] Command executor not loaded")
		_ws_client.send_bridge_command_result(sender_id, correlation_id, false, 0, 0, 0, ["Command executor not loaded"])
		return

	print("[ArkestratorBridge] Executing %d command(s) from %s" % [commands.size(), sender_id.substr(0, 8)])
	var result: Dictionary = _command_executor_script.execute_commands(commands, get_editor_interface())
	var executed := int(result.get("executed", 0))
	var cmd_failed := int(result.get("failed", 0))
	var cmd_skipped := int(result.get("skipped", 0))
	var cmd_errors: Array = result.get("errors", [])

	print("[ArkestratorBridge] Result: %d executed, %d failed, %d skipped" % [executed, cmd_failed, cmd_skipped])
	_ws_client.send_bridge_command_result(sender_id, correlation_id, cmd_failed == 0, executed, cmd_failed, cmd_skipped, cmd_errors)


func _on_bridge_command_result_received(bridge_id: String, program: String, correlation_id: String, success: bool, executed: int, failed_count: int, skipped: int, errors: Array) -> void:
	var status := "success" if success else "failed"
	print("[ArkestratorBridge] bridge-cmd-result %s from %s (%s): %d executed, %d failed, %d skipped" % [status, program, bridge_id.substr(0, 8), executed, failed_count, skipped])
	for err in errors:
		print("[ArkestratorBridge] bridge-cmd-error: %s" % str(err))


# --- Context Items (push to server immediately) ---

func _on_context_item_added(item: Dictionary) -> void:
	if _ws_client == null or not _ws_client.is_connected_to_server():
		_update_status("Not connected - context item not sent")
		return
	item["index"] = _context_bag_next_index
	_context_bag_next_index += 1
	_ws_client.send_context_item(item)
	_update_status("Sent to context: @%d %s" % [item["index"], item.get("name", "")])


# --- Editor Context Push ---

func _push_editor_context() -> void:
	if _ws_client == null or not _ws_client.is_connected_to_server():
		return
	var editor_context := _build_editor_context()
	var files := _gather_file_attachments(editor_context)
	_ws_client.send_editor_context(editor_context, files)
	# Update hash so periodic check knows about this push
	_last_editor_context_hash = _hash_editor_context(editor_context)


func _push_editor_context_if_changed() -> void:
	if _ws_client == null or not _ws_client.is_connected_to_server():
		return
	var editor_context := _build_editor_context()
	var current_hash := _hash_editor_context(editor_context)
	if current_hash != _last_editor_context_hash:
		_last_editor_context_hash = current_hash
		var files := _gather_file_attachments(editor_context)
		_ws_client.send_editor_context(editor_context, files)


func _hash_editor_context(ctx: Dictionary) -> int:
	# Simple hash based on active scene + selected nodes + selected scripts
	var parts: PackedStringArray = PackedStringArray()
	parts.append(str(ctx.get("activeFile", "")))
	var metadata: Dictionary = ctx.get("metadata", {}) as Dictionary
	var nodes: Array = metadata.get("selected_nodes", []) as Array
	for n in nodes:
		if n is Dictionary:
			parts.append("%s:%s:%s" % [str(n.get("name", "")), str(n.get("type", "")), str(n.get("path", ""))])
	var scripts: Array = metadata.get("selected_scripts", []) as Array
	for s in scripts:
		parts.append(str(s))
	return "|".join(parts).hash()


# --- Editor Context ---

func _build_editor_context() -> Dictionary:
	var editor := get_editor_interface()
	var scene_root := editor.get_edited_scene_root()
	var selection := editor.get_selection()
	var selected_nodes: Array = []
	if selection != null:
		selected_nodes = selection.get_selected_nodes()

	var selected_entries: Array[Dictionary] = []
	var selected_scripts_map := {}
	for node in selected_nodes:
		if node == null or not (node is Node):
			continue
		var node_path := ""
		if scene_root != null and scene_root == node:
			node_path = "."
		elif scene_root != null and scene_root.is_ancestor_of(node):
			node_path = str(scene_root.get_path_to(node))
		else:
			node_path = str(node.get_path())
		selected_entries.append({
			"name": node.name,
			"type": node.get_class(),
			"path": node_path,
		})
		var script_path := _get_script_path(node.get_script())
		if not script_path.is_empty():
			selected_scripts_map[script_path] = true

	var script_editor := editor.get_script_editor()
	if script_editor != null:
		if script_editor.has_method("get_current_script"):
			var current: Variant = script_editor.call("get_current_script")
			var p := _get_script_path(current)
			if not p.is_empty():
				selected_scripts_map[p] = true
		if script_editor.has_method("get_open_scripts"):
			var open_scripts: Variant = script_editor.call("get_open_scripts")
			if open_scripts is Array:
				for s in open_scripts:
					var p := _get_script_path(s)
					if not p.is_empty():
						selected_scripts_map[p] = true

	var selected_scripts: Array[String] = []
	for key in selected_scripts_map.keys():
		selected_scripts.append(str(key))
	selected_scripts.sort()

	var active_scene := ""
	if scene_root != null:
		active_scene = scene_root.scene_file_path

	return {
		"projectRoot": ProjectSettings.globalize_path("res://"),
		"activeFile": active_scene,
		"metadata": {
			"active_scene": active_scene,
			"selected_nodes": selected_entries,
			"selected_scripts": selected_scripts,
		},
	}


func _gather_file_attachments(editor_context: Dictionary) -> Array:
	var files: Array = []
	var metadata: Dictionary = editor_context.get("metadata", {}) as Dictionary
	var scripts: Array = metadata.get("selected_scripts", []) as Array
	for script_path in scripts:
		var path_str := str(script_path).strip_edges()
		if path_str.is_empty():
			continue
		var abs_path := path_str
		if path_str.begins_with("res://"):
			abs_path = ProjectSettings.globalize_path(path_str)
		if not FileAccess.file_exists(abs_path):
			continue
		var content := FileAccess.get_file_as_string(abs_path)
		files.append({
			"path": path_str,
			"content": content,
		})
	return files


func _get_script_path(script_value: Variant) -> String:
	if script_value == null:
		return ""
	if script_value is Script:
		return (script_value as Script).resource_path.strip_edges()
	if script_value is Resource:
		return (script_value as Resource).resource_path.strip_edges()
	return ""


# --- Scene Operations ---

func _save_active_scene() -> void:
	var editor := get_editor_interface()
	if editor.has_method("save_scene"):
		editor.call("save_scene")
	elif editor.has_method("save_all_scenes"):
		editor.call("save_all_scenes")


func _try_reload_active_scene() -> void:
	var editor := get_editor_interface()
	var scene_root := editor.get_edited_scene_root()
	if scene_root == null:
		return
	var scene_path := scene_root.scene_file_path
	if scene_path.is_empty():
		return
	# Store the scene path; _on_filesystem_changed will pick it up after the scan.
	# Set it before starting the scan to avoid the race where the signal fires
	# before _pending_reload_scene is populated.
	_pending_reload_scene = scene_path
	var fs := editor.get_resource_filesystem()
	if fs != null and fs.has_method("scan"):
		fs.scan()
	else:
		call_deferred("_reload_scene", scene_path)


func _on_filesystem_changed() -> void:
	# Permanent handler (connected in _enter_tree). Fires after every scan completes.
	if _pending_reload_scene.is_empty():
		return
	var scene_path := _pending_reload_scene
	_pending_reload_scene = ""
	call_deferred("_reload_scene", scene_path)


func _on_sources_changed(exist: bool) -> void:
	# Fires when external files on disk change (EditorFileSystem watcher).
	# This catches the case where a repo-mode agent writes files directly without
	# going through the bridge's job_complete flow.
	if not exist:
		return
	if not _auto_reload_checkbox.button_pressed:
		return
	_try_reload_active_scene()


func _reload_scene(scene_path: String) -> void:
	var editor := get_editor_interface()
	if editor.has_method("reload_scene_from_path"):
		editor.call("reload_scene_from_path", scene_path)
	elif editor.has_method("open_scene_from_path"):
		editor.call("open_scene_from_path", scene_path)
	_update_status("Scene reloaded")


# --- Helpers ---

func _update_status(text: String) -> void:
	if _status_label != null:
		_status_label.text = "Status: %s" % text


func _save_settings() -> void:
	if _server_url_edit != null:
		_write_setting(SETTING_SERVER_URL, _server_url_edit.text.strip_edges())
	if _auto_connect_checkbox != null:
		_write_setting(SETTING_AUTO_CONNECT, _auto_connect_checkbox.button_pressed)
	if _auto_reload_checkbox != null:
		_write_setting(SETTING_AUTO_RELOAD_SCENE, _auto_reload_checkbox.button_pressed)
	if _auto_apply_checkbox != null:
		_write_setting(SETTING_AUTO_APPLY_FILES, _auto_apply_checkbox.button_pressed)
	if _auto_execute_commands_checkbox != null:
		_write_setting(SETTING_AUTO_EXECUTE_COMMANDS, _auto_execute_commands_checkbox.button_pressed)


func _focus_dock() -> void:
	if _dock != null:
		_dock.visible = true


# --- Public API (for AgentManager SDK and third-party plugins) ---

## Submit a job through this bridge, automatically attaching editor context.
## Returns the created job Dictionary (includes "id", "status", etc.),
## or an empty Dictionary on failure.
##
## [param prompt] The task prompt for the AI agent.
## [param options] Optional dict with: priority, agentConfigId,
##     targetWorkerName, projectId, dependsOn, startPaused, preferredMode,
##     contextItems.
func submit_job(prompt: String, options: Dictionary = {}) -> Dictionary:
	var editor_context := _build_editor_context()
	var files := _gather_file_attachments(editor_context)

	var body: Dictionary = {
		"prompt": prompt,
		"priority": options.get("priority", "normal"),
		"editorContext": editor_context,
		"files": files,
	}

	if options.has("agentConfigId"):
		body["agentConfigId"] = options["agentConfigId"]
	if options.has("targetWorkerName"):
		body["targetWorkerName"] = options["targetWorkerName"]
	if options.has("projectId"):
		body["projectId"] = options["projectId"]
	if options.has("dependsOn"):
		body["dependsOn"] = options["dependsOn"]
	if options.get("startPaused", false):
		body["startPaused"] = true
	if options.has("preferredMode"):
		body["preferredMode"] = options["preferredMode"]
	if options.has("contextItems"):
		body["contextItems"] = options["contextItems"]

	# Read server config
	var config := _read_shared_config()
	var ws_url := str(config.get("wsUrl", "ws://localhost:7800/ws"))
	var server_url := ws_url.replace("ws://", "http://").replace("wss://", "https://")
	if server_url.ends_with("/ws"):
		server_url = server_url.substr(0, server_url.length() - 3)
	var api_key := str(config.get("apiKey", ""))

	# Synchronous HTTP POST (runs inline; if async needed, use the SDK instead)
	var http := HTTPClient.new()
	var parsed := _parse_url(server_url + "/api/jobs")
	var err := http.connect_to_host(parsed.host, parsed.port)
	if err != OK:
		push_error("[ArkestratorBridge] HTTP connect failed: %s" % error_string(err))
		return {}

	# Wait for connection
	while http.get_status() == HTTPClient.STATUS_CONNECTING or http.get_status() == HTTPClient.STATUS_RESOLVING:
		http.poll()
		OS.delay_msec(50)

	if http.get_status() != HTTPClient.STATUS_CONNECTED:
		push_error("[ArkestratorBridge] HTTP connection failed (status %d)" % http.get_status())
		return {}

	var headers := PackedStringArray([
		"Content-Type: application/json",
		"Authorization: Bearer %s" % api_key,
	])
	var json_body := JSON.stringify(body)
	err = http.request(HTTPClient.METHOD_POST, "/api/jobs", headers, json_body)
	if err != OK:
		push_error("[ArkestratorBridge] HTTP request failed: %s" % error_string(err))
		return {}

	# Wait for response
	while http.get_status() == HTTPClient.STATUS_REQUESTING:
		http.poll()
		OS.delay_msec(50)

	if http.get_status() != HTTPClient.STATUS_BODY and http.get_status() != HTTPClient.STATUS_CONNECTED:
		push_error("[ArkestratorBridge] HTTP unexpected status: %d" % http.get_status())
		return {}

	var response_body := PackedByteArray()
	while http.get_status() == HTTPClient.STATUS_BODY:
		http.poll()
		var chunk := http.read_response_body_chunk()
		if chunk.size() > 0:
			response_body.append_array(chunk)
		OS.delay_msec(10)

	var response_text := response_body.get_string_from_utf8()
	var result = JSON.parse_string(response_text)
	if result is Dictionary:
		_update_status("Job submitted: %s" % str(result.get("id", "")).substr(0, 8))
		return result
	return {}


func _parse_url(url: String) -> Dictionary:
	## Parse a URL into host, port, scheme components.
	var scheme := "http"
	var working := url
	if working.begins_with("https://"):
		scheme = "https"
		working = working.substr(8)
	elif working.begins_with("http://"):
		working = working.substr(7)

	# Strip path
	var slash_pos := working.find("/")
	if slash_pos >= 0:
		working = working.substr(0, slash_pos)

	# Extract port
	var port := 80 if scheme == "http" else 443
	var colon_pos := working.find(":")
	if colon_pos >= 0:
		port = int(working.substr(colon_pos + 1))
		working = working.substr(0, colon_pos)

	return {"host": working, "port": port, "scheme": scheme}
