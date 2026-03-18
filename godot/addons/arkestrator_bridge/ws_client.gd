@tool
extends Node
## WebSocket client for Arkestrator server.
## Handles connect, disconnect, reconnect, send, and message dispatch via signals.

signal connected
signal disconnected
signal reconnecting(seconds_remaining: float)
signal job_complete(job_id: String, success: bool, files: Array, commands: Array, workspace_mode: String, error_text: String)
signal error_received(code: String, message: String)
signal bridge_command_received(sender_id: String, commands: Array, correlation_id: String)
signal bridge_command_result_received(bridge_id: String, program: String, correlation_id: String, success: bool, executed: int, failed_count: int, skipped: int, errors: Array)

const RECONNECT_BASE_MS := 3000.0
const RECONNECT_MAX_MS := 30000.0
const CONNECT_TIMEOUT_S := 15.0  ## Max seconds to wait for WS handshake
const BRIDGE_VERSION := "1.0.0"
const PROTOCOL_VERSION := 1  ## Must match server's PROTOCOL_VERSION

var _ws := WebSocketPeer.new()
var _url := ""
var _api_key := ""
var _last_good_api_key := ""
## Worker name override. If empty, auto-detects from OS hostname.
var worker_name := ""
## Stable client-owned machine id from ~/.arkestrator/config.json.
var machine_id := ""
var _is_connected := false
var _should_reconnect := true
var _reconnect_timer := 0.0
var _reconnect_delay := RECONNECT_BASE_MS
var _waiting_reconnect := false
var _was_connected := false
var _connect_start_time := 0.0


func connect_to_server(url: String, api_key: String, next_worker_name: String = "", next_machine_id: String = "") -> int:
	_url = url
	_api_key = api_key
	worker_name = next_worker_name
	machine_id = next_machine_id
	_should_reconnect = true
	_reconnect_delay = RECONNECT_BASE_MS
	_waiting_reconnect = false
	return _do_connect()


func disconnect_from_server() -> void:
	_should_reconnect = false
	_waiting_reconnect = false
	if _is_connected or _ws.get_ready_state() != WebSocketPeer.STATE_CLOSED:
		_ws.close()
	_set_disconnected()


func is_connected_to_server() -> bool:
	return _is_connected


func is_reconnect_pending() -> bool:
	return _waiting_reconnect


func send_message(msg: Dictionary) -> void:
	if not _is_connected:
		return
	var json_text := JSON.stringify(msg)
	_ws.send_text(json_text)


func send_bridge_command(target: String, commands: Array, target_type: String = "program", correlation_id: String = "") -> void:
	var payload: Dictionary = {
		"target": target,
		"targetType": target_type,
		"commands": commands,
	}
	if not correlation_id.is_empty():
		payload["correlationId"] = correlation_id
	send_message({
		"type": "bridge_command_send",
		"id": _new_uuid(),
		"payload": payload,
	})


func send_bridge_command_result(sender_id: String, correlation_id: String, success: bool, executed: int, failed_count: int, skipped: int, errors: Array) -> void:
	send_message({
		"type": "bridge_command_result",
		"id": _new_uuid(),
		"payload": {
			"senderId": sender_id,
			"correlationId": correlation_id,
			"success": success,
			"executed": executed,
			"failed": failed_count,
			"skipped": skipped,
			"errors": errors,
		},
	})


func send_context_item(item: Dictionary) -> void:
	"""Send a bridge_context_item_add message to push a context item to the server."""
	send_message({
		"type": "bridge_context_item_add",
		"id": _new_uuid(),
		"payload": {
			"item": {
				"index": item.get("index", 0),
				"type": item.get("type", "asset"),
				"name": item.get("name", ""),
				"path": item.get("path", ""),
				"content": item.get("content", ""),
				"metadata": item.get("metadata", {}),
			},
		},
	})


func send_context_clear() -> void:
	"""Send a bridge_context_clear message to clear the context bag on the server."""
	send_message({
		"type": "bridge_context_clear",
		"id": _new_uuid(),
		"payload": {},
	})


func send_editor_context(editor_context: Dictionary, files: Array) -> void:
	"""Send a bridge_editor_context message to push the current editor context snapshot."""
	send_message({
		"type": "bridge_editor_context",
		"id": _new_uuid(),
		"payload": {
			"editorContext": editor_context,
			"files": files,
		},
	})


func poll() -> void:
	if _waiting_reconnect:
		return
	_ws.poll()
	var state := _ws.get_ready_state()

	# Detect handshake timeout: if connecting for too long, close and retry
	if state == WebSocketPeer.STATE_CONNECTING:
		if _connect_start_time > 0.0:
			var elapsed := (Time.get_ticks_msec() / 1000.0) - _connect_start_time
			if elapsed > CONNECT_TIMEOUT_S:
				print("[ArkestratorBridge] WS connect timeout after %.0fs — retrying" % elapsed)
				_ws.close()
				_set_disconnected()
				if _should_reconnect and not _waiting_reconnect:
					_start_reconnect_wait()
				return

	if state == WebSocketPeer.STATE_OPEN:
		if not _is_connected:
			_connect_start_time = 0.0
			_is_connected = true
			_was_connected = true
			if _is_valid_api_key(_api_key):
				_last_good_api_key = _api_key
			_reconnect_delay = RECONNECT_BASE_MS
			connected.emit()
		while _ws.get_available_packet_count() > 0:
			var raw := _ws.get_packet().get_string_from_utf8()
			_handle_message(raw)
	elif state == WebSocketPeer.STATE_CLOSED:
		if _is_connected or _was_connected:
			var close_code := _ws.get_close_code()
			var close_reason := _ws.get_close_reason()
			if close_code == 4001:
				# Replaced by a newer connection — do NOT reconnect
				print("[ArkestratorBridge] WS disconnect: replaced by newer connection (4001) — not reconnecting")
				_should_reconnect = false
			elif close_code > 0:
				print("[ArkestratorBridge] WS disconnect: code=%d reason=%s" % [close_code, close_reason if not close_reason.is_empty() else "(none)"])
			else:
				print("[ArkestratorBridge] WS disconnect: connection lost (no close frame)")
			_set_disconnected()
		if _should_reconnect and not _waiting_reconnect:
			_start_reconnect_wait()


func reconnect_tick(delta: float) -> void:
	if not _waiting_reconnect:
		return
	_reconnect_timer -= delta
	if _reconnect_timer <= 0.0:
		_waiting_reconnect = false
		_do_connect()
	else:
		reconnecting.emit(_reconnect_timer)


# --- Internal ---

func _do_connect() -> int:
	var last_error := ERR_CANT_CONNECT
	var errors: PackedStringArray = []
	for attempt in _connection_attempt_urls():
		var full_url := str(attempt.get("url", ""))
		var attempt_key := str(attempt.get("api_key", ""))
		var label := str(attempt.get("label", "primary"))
		_ws = WebSocketPeer.new()
		var err := _ws.connect_to_url(full_url)
		if err == OK:
			_connect_start_time = Time.get_ticks_msec() / 1000.0
			_api_key = attempt_key
			if label != "primary":
				print("[ArkestratorBridge] WebSocket relay unavailable; using %s" % label)
			return OK
		last_error = err
		errors.append("%s: %s" % [label, error_string(err)])

	if not errors.is_empty():
		push_error("[ArkestratorBridge] WebSocket connect failed: %s" % "; ".join(errors))
	else:
		push_error("[ArkestratorBridge] WebSocket connect failed: %s" % error_string(last_error))
	return last_error


func _connection_attempt_urls() -> Array:
	var attempts: Array = []
	var seen := {}
	_add_connection_attempt(attempts, seen, "primary", _url, _api_key)
	if _is_loopback_ws_url(_url):
		var shared := _read_shared_config()
		var remote_ws := str(shared.get("remoteWsUrl", "")).strip_edges()
		if not remote_ws.is_empty() and remote_ws != _url:
			_add_connection_attempt(attempts, seen, "remote fallback", remote_ws, _api_key)
		if not _last_good_api_key.is_empty() and _last_good_api_key != _api_key:
			_add_connection_attempt(attempts, seen, "last known good key", _url, _last_good_api_key)
			if not remote_ws.is_empty() and remote_ws != _url:
				_add_connection_attempt(
					attempts,
					seen,
					"remote fallback (last good key)",
					remote_ws,
					_last_good_api_key
				)
	elif not _last_good_api_key.is_empty() and _last_good_api_key != _api_key:
		_add_connection_attempt(attempts, seen, "last known good key", _url, _last_good_api_key)
	return attempts


func _build_full_url(base_url: String) -> String:
	return _build_full_url_with_key(base_url, _api_key)


func _add_connection_attempt(attempts: Array, seen: Dictionary, label: String, base_url: String, api_key: String) -> void:
	var next_url := base_url.strip_edges()
	if next_url.is_empty():
		return
	var dedupe_key := "%s|%s" % [next_url, api_key]
	if seen.has(dedupe_key):
		return
	seen[dedupe_key] = true
	attempts.append({
		"label": label,
		"url": _build_full_url_with_key(next_url, api_key),
		"api_key": api_key,
	})


func _build_full_url_with_key(base_url: String, api_key: String) -> String:
	var full_url := base_url
	if not api_key.is_empty():
		if full_url.find("?") >= 0:
			full_url += "&key=%s" % api_key
		else:
			full_url += "?key=%s" % api_key
	if full_url.find("type=") < 0:
		if full_url.find("?") >= 0:
			full_url += "&type=bridge"
		else:
			full_url += "?type=bridge"

	# Send bridge metadata as query params
	var project_name := ProjectSettings.get_setting("application/config/name", "Unknown Project") as String
	var version_info: Dictionary = Engine.get_version_info()
	var program_version := "%s.%s.%s.%s" % [
		version_info.get("major", 0),
		version_info.get("minor", 0),
		version_info.get("patch", 0),
		version_info.get("status", "stable"),
	]
	var project_path := ProjectSettings.globalize_path("res://")

	var effective_worker := worker_name.strip_edges()
	if effective_worker.is_empty():
		effective_worker = _get_hostname()

	full_url += "&name=%s" % project_name.uri_encode()
	full_url += "&program=godot"
	full_url += "&programVersion=%s" % program_version.uri_encode()
	full_url += "&bridgeVersion=%s" % BRIDGE_VERSION.uri_encode()
	full_url += "&protocolVersion=%d" % PROTOCOL_VERSION
	full_url += "&projectPath=%s" % project_path.uri_encode()
	full_url += "&workerName=%s" % effective_worker.uri_encode()
	var effective_machine_id := machine_id.strip_edges()
	if not effective_machine_id.is_empty():
		full_url += "&machineId=%s" % effective_machine_id.uri_encode()
	# Send OS username for server-side dedup across bridges on the same machine
	var os_user := OS.get_environment("USER") # macOS/Linux
	if os_user.is_empty():
		os_user = OS.get_environment("USERNAME") # Windows
	if not os_user.is_empty():
		full_url += "&osUser=%s" % os_user.uri_encode()

	return full_url


func _read_shared_config() -> Dictionary:
	var home := ""
	if OS.has_feature("windows"):
		home = OS.get_environment("USERPROFILE")
	else:
		home = OS.get_environment("HOME")
	if home.is_empty():
		return {}
	var config_path := home.path_join(".arkestrator").path_join("config.json")
	if not FileAccess.file_exists(config_path):
		return {}
	var file := FileAccess.open(config_path, FileAccess.READ)
	if file == null:
		return {}
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


func _set_disconnected() -> void:
	var was := _is_connected
	_is_connected = false
	if was:
		disconnected.emit()


func _start_reconnect_wait() -> void:
	_waiting_reconnect = true
	_reconnect_timer = _reconnect_delay / 1000.0
	_reconnect_delay = minf(_reconnect_delay * 2.0, RECONNECT_MAX_MS)


func _handle_message(raw: String) -> void:
	var parsed: Variant = JSON.parse_string(raw)
	if parsed == null or not (parsed is Dictionary):
		return
	var msg: Dictionary = parsed
	var msg_type := str(msg.get("type", ""))
	var payload: Dictionary = msg.get("payload", {}) as Dictionary

	match msg_type:
		"job_complete":
			var files_raw: Array = payload.get("files", []) as Array
			var commands_raw: Array = payload.get("commands", []) as Array
			var ws_mode := str(payload.get("workspaceMode", ""))
			job_complete.emit(
				str(payload.get("jobId", "")),
				bool(payload.get("success", false)),
				files_raw,
				commands_raw,
				ws_mode,
				str(payload.get("error", ""))
			)
		"error":
			error_received.emit(str(payload.get("code", "")), str(payload.get("message", "")))
		"bridge_command":
			var sender_id := str(payload.get("senderId", ""))
			var cmds: Array = payload.get("commands", []) as Array
			var corr_id := str(payload.get("correlationId", ""))
			bridge_command_received.emit(sender_id, cmds, corr_id)
		"bridge_command_result":
			bridge_command_result_received.emit(
				str(payload.get("bridgeId", "")),
				str(payload.get("program", "")),
				str(payload.get("correlationId", "")),
				bool(payload.get("success", false)),
				int(payload.get("executed", 0)),
				int(payload.get("failed", 0)),
				int(payload.get("skipped", 0)),
				payload.get("errors", []) as Array,
			)
		_:
			pass


func _get_hostname() -> String:
	# COMPUTERNAME on Windows, HOSTNAME or HOST on Unix
	var hostname := OS.get_environment("COMPUTERNAME")
	if hostname.is_empty():
		hostname = OS.get_environment("HOSTNAME")
	if hostname.is_empty():
		hostname = OS.get_environment("HOST")
	# Fallback: run `hostname` command (works on macOS/Linux/Windows)
	if hostname.is_empty():
		var output: Array = []
		var exit_code := OS.execute("hostname", [], output, true)
		if exit_code == 0 and output.size() > 0:
			hostname = str(output[0]).strip_edges()
	if hostname.is_empty():
		hostname = "unknown"
	return hostname


func _new_uuid() -> String:
	# Simple v4 UUID using crypto random bytes
	var bytes := PackedByteArray()
	bytes.resize(16)
	for i in range(16):
		bytes[i] = randi() % 256
	# Set version (4) and variant (10xx)
	bytes[6] = (bytes[6] & 0x0F) | 0x40
	bytes[8] = (bytes[8] & 0x3F) | 0x80
	var hex := bytes.hex_encode()
	return "%s-%s-%s-%s-%s" % [
		hex.substr(0, 8),
		hex.substr(8, 4),
		hex.substr(12, 4),
		hex.substr(16, 4),
		hex.substr(20, 12),
	]
