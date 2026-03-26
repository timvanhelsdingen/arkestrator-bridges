"""
Arkestrator Fusion Bridge — main entry point.

Can be launched in two modes:
  1. Auto-start (headless): via Arkestrator.fu on comp open/create
     - Connects in the background, no UI panel
     - Set ARKESTRATOR_HEADLESS=1 env var before running
  2. Manual (with panel): via Arkestrator menu > Show Panel, or legacy script
     - Opens the dockable UI panel with connection controls

The bridge is a singleton — multiple calls reuse the same instance.

Works with:
  - Blackmagic Fusion (standalone)
  - DaVinci Resolve's Fusion page
"""

import importlib
import importlib.util
import json
import os
import sys
import threading
import time
import traceback

# ---------------------------------------------------------------------------
# Bootstrap: register this directory as the "fusion" package so that
# `from fusion import config` etc. work regardless of the install directory
# name (blackmagic-fusion, Arkestrator, etc.).
# ---------------------------------------------------------------------------


def _resolve_arkestrator_dir():
    """Resolve the Arkestrator package directory via Fusion API or __file__."""
    if "__file__" in dir() or "__file__" in globals():
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except NameError:
            pass
    for _g in ("fusion", "fu", "app", "comp"):
        _obj = globals().get(_g)
        if _obj is not None and hasattr(_obj, "MapPath"):
            try:
                mapped = str(_obj.MapPath("Config:/Arkestrator/") or "")
                if mapped and os.path.isdir(mapped):
                    return mapped.rstrip("/\\")
            except Exception:
                pass
    return None


_this_dir = _resolve_arkestrator_dir()
if _this_dir is None:
    raise RuntimeError("[Arkestrator] Cannot resolve Arkestrator directory")
_parent_dir = os.path.dirname(_this_dir)

if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

if "fusion" not in sys.modules:
    _init_path = os.path.join(_this_dir, "__init__.py")
    if os.path.isfile(_init_path):
        _spec = importlib.util.spec_from_file_location(
            "fusion", _init_path,
            submodule_search_locations=[_this_dir],
        )
        _pkg = importlib.util.module_from_spec(_spec)
        sys.modules["fusion"] = _pkg
        _spec.loader.exec_module(_pkg)

# Register submodules that haven't been loaded yet
for _mod_name in ["config", "ws_client", "context_provider", "command_executor", "file_applier"]:
    _fqn = f"fusion.{_mod_name}"
    if _fqn not in sys.modules:
        _mod_path = os.path.join(_this_dir, f"{_mod_name}.py")
        if os.path.isfile(_mod_path):
            _mod_spec = importlib.util.spec_from_file_location(_fqn, _mod_path)
            _mod = importlib.util.module_from_spec(_mod_spec)
            sys.modules[_fqn] = _mod
            _mod_spec.loader.exec_module(_mod)

from fusion import config as cfg
from fusion.ws_client import BridgeWebSocket
from fusion.context_provider import (
    get_fusion_app,
    get_comp,
    build_editor_context,
    build_context_items_for_selected,
    build_context_item_for_active_tool,
    build_context_item_for_comp,
    build_context_item_for_loader,
    build_context_item_for_saver,
    build_context_item_for_3d_scene,
    build_context_item_for_modifiers,
    build_context_item_for_settings,
    build_context_item_for_flow_graph,
    build_context_item_for_keyframes,
    context_hash,
)
from fusion.command_executor import execute_commands, SUPPORTED_LANGUAGES
from fusion.file_applier import apply_file_changes


# ---------------------------------------------------------------------------
# Singleton bridge instance
#
# Fusion's comp:RunScript() runs each script in a fresh module context, so
# module-level globals do NOT persist across calls.  We store the singleton
# on Python's `builtins` module, which is shared by the entire interpreter
# session and survives across RunScript invocations.
# ---------------------------------------------------------------------------

import builtins as _builtins

_bridge_lock = threading.Lock()
_BUILTIN_KEY = "_arkestrator_fusion_bridge"


def get_bridge():
    """Return the existing bridge instance, or None."""
    return getattr(_builtins, _BUILTIN_KEY, None)


def get_or_create_bridge(fusion_app, log_fn=None):
    """Return the singleton bridge, creating it if needed."""
    with _bridge_lock:
        existing = getattr(_builtins, _BUILTIN_KEY, None)
        if existing is not None:
            return existing
        bridge = FusionBridge(fusion_app, log_fn=log_fn)
        setattr(_builtins, _BUILTIN_KEY, bridge)
        return bridge


# ---------------------------------------------------------------------------
# Bridge state
# ---------------------------------------------------------------------------

class FusionBridge:
    """Core bridge logic — coordinates WebSocket, context, and execution."""

    def __init__(self, fusion_app, log_fn=None):
        self.fusion = fusion_app
        self._log_fn = log_fn or print
        self._ws = BridgeWebSocket(
            on_message=self._on_message,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            logger=self._log,
        )
        self._context_index = 0
        self._last_context_hash = ""
        self._context_timer = None
        self._context_stop = threading.Event()
        self._auto_apply_files = True
        self._auto_execute_commands = True

    def _log(self, msg):
        try:
            self._log_fn(str(msg))
        except Exception:
            pass

    # -- Connection ----------------------------------------------------------

    def connect(self):
        """Start the WebSocket connection."""
        comp = get_comp(self.fusion)
        if comp:
            attrs = comp.GetAttrs() or {}
            filename = attrs.get("COMPS_FileName", "")
            self._ws._project_path = os.path.dirname(filename) if filename else ""
        else:
            self._ws._project_path = ""

        # Detect Fusion version
        try:
            version = str(self.fusion.Version)
        except Exception:
            version = "unknown"
        self._ws._program_version = version

        self._ws.start()

    def disconnect(self):
        """Stop the WebSocket connection."""
        self._context_stop.set()
        self._ws.stop()

    @property
    def connected(self):
        return self._ws.connected

    # -- WebSocket callbacks -------------------------------------------------

    def _on_connect(self):
        """Called when WebSocket connects — clear context, start pushing."""
        self._context_index = 0
        self._last_context_hash = ""

        # Clear stale context
        self._ws.send("bridge_context_clear", {})

        # Push initial context
        self._push_editor_context()

        # Start periodic context push
        self._context_stop.clear()
        self._context_timer = threading.Thread(
            target=self._context_loop, daemon=True, name="ark-ctx"
        )
        self._context_timer.start()

    def _on_disconnect(self):
        """Called when WebSocket disconnects."""
        self._context_stop.set()

    def _on_message(self, msg):
        """Handle incoming WebSocket messages."""
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        msg_id = msg.get("id", "")

        if msg_type == "job_complete":
            self._handle_job_complete(payload)
        elif msg_type == "bridge_command":
            self._handle_bridge_command(payload)
        elif msg_type == "file_deliver":
            self._handle_file_deliver(payload)
        elif msg_type == "error":
            self._log(f"[server] Error: {payload.get('code')}: {payload.get('message')}")

    # -- Context pushing -----------------------------------------------------

    def _context_loop(self):
        """Push editor context every 2-3 seconds when state changes."""
        while not self._context_stop.is_set():
            try:
                self._push_editor_context()
            except Exception as exc:
                self._log(f"[ctx] Error: {exc}")
            self._context_stop.wait(2.5)

    def _push_editor_context(self):
        """Send bridge_editor_context if state changed."""
        comp = get_comp(self.fusion)
        editor_ctx, files = build_editor_context(self.fusion, comp)

        h = context_hash(editor_ctx, files)
        if h == self._last_context_hash:
            return
        self._last_context_hash = h

        # Update project path on the WS client for reconnections
        project_root = editor_ctx.get("projectRoot", "")
        if project_root:
            self._ws._project_path = project_root

        self._ws.send("bridge_editor_context", {
            "editorContext": editor_ctx,
            "files": files,
        })

    # -- Context item actions ------------------------------------------------

    def add_selected_to_context(self):
        """Add all selected tools to context."""
        comp = get_comp(self.fusion)
        if not comp:
            self._log("[ctx] No active composition")
            return 0
        items = build_context_items_for_selected(comp, self._context_index + 1)
        for item in items:
            self._context_index += 1
            item["index"] = self._context_index
            self._ws.send("bridge_context_item_add", {"item": item})
            self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return len(items)

    def add_active_tool_to_context(self):
        """Add the active (viewed) tool to context."""
        comp = get_comp(self.fusion)
        if not comp:
            self._log("[ctx] No active composition")
            return False
        self._context_index += 1
        item = build_context_item_for_active_tool(comp, self._context_index)
        if not item:
            self._context_index -= 1
            self._log("[ctx] No active tool")
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_comp_to_context(self):
        """Add full composition structure to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        self._context_index += 1
        item = build_context_item_for_comp(comp, self._context_index)
        if not item:
            self._context_index -= 1
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_flow_graph_to_context(self):
        """Add the full node graph topology to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        self._context_index += 1
        item = build_context_item_for_flow_graph(comp, self._context_index)
        if not item:
            self._context_index -= 1
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_loaders_to_context(self):
        """Add all Loader tools to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return 0
        try:
            loaders = comp.GetToolList(False, "Loader")
        except Exception:
            return 0
        if not loaders:
            return 0
        count = 0
        tool_list = list(loaders.values()) if hasattr(loaders, "values") else []
        for tool in tool_list:
            self._context_index += 1
            item = build_context_item_for_loader(tool, self._context_index)
            if item:
                self._ws.send("bridge_context_item_add", {"item": item})
                self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
                count += 1
            else:
                self._context_index -= 1
        return count

    def add_savers_to_context(self):
        """Add all Saver tools to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return 0
        try:
            savers = comp.GetToolList(False, "Saver")
        except Exception:
            return 0
        if not savers:
            return 0
        count = 0
        tool_list = list(savers.values()) if hasattr(savers, "values") else []
        for tool in tool_list:
            self._context_index += 1
            item = build_context_item_for_saver(tool, self._context_index)
            if item:
                self._ws.send("bridge_context_item_add", {"item": item})
                self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
                count += 1
            else:
                self._context_index -= 1
        return count

    def add_3d_scene_to_context(self):
        """Add the 3D scene hierarchy to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        self._context_index += 1
        item = build_context_item_for_3d_scene(comp, self._context_index)
        if not item:
            self._context_index -= 1
            self._log("[ctx] No 3D tools found")
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_modifiers_to_context(self):
        """Add all modifiers and expressions to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        self._context_index += 1
        item = build_context_item_for_modifiers(comp, self._context_index)
        if not item:
            self._context_index -= 1
            self._log("[ctx] No modifiers found")
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_tool_settings_to_context(self, tool=None):
        """Add detailed settings of a tool (default: active tool) to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        if tool is None:
            try:
                tool = comp.ActiveTool
            except Exception:
                pass
        if not tool:
            self._log("[ctx] No tool specified or active")
            return False
        self._context_index += 1
        item = build_context_item_for_settings(tool, self._context_index)
        if not item:
            self._context_index -= 1
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    def add_keyframes_to_context(self, tool=None):
        """Add keyframe/animation data for a tool to context."""
        comp = get_comp(self.fusion)
        if not comp:
            return False
        if tool is None:
            try:
                tool = comp.ActiveTool
            except Exception:
                pass
        if not tool:
            self._log("[ctx] No tool specified or active")
            return False
        self._context_index += 1
        item = build_context_item_for_keyframes(tool, self._context_index)
        if not item:
            self._context_index -= 1
            self._log("[ctx] No keyframes found on this tool")
            return False
        self._ws.send("bridge_context_item_add", {"item": item})
        self._log(f"[ctx] Added @{self._context_index}: {item['name']}")
        return True

    # -- Command execution ---------------------------------------------------

    def _handle_job_complete(self, payload):
        """Handle job_complete: apply files and/or execute commands."""
        workspace_mode = payload.get("workspaceMode", "command")
        commands = payload.get("commands", [])
        files = payload.get("files", [])
        job_id = payload.get("jobId", "?")

        self._log(f"[job] Complete: {job_id} (mode={workspace_mode}, "
                  f"cmds={len(commands)}, files={len(files)})")

        # Apply files for repo/sync modes
        if files and workspace_mode in ("repo", "sync"):
            if self._auto_apply_files:
                comp = get_comp(self.fusion)
                project_root = ""
                if comp:
                    attrs = comp.GetAttrs() or {}
                    filename = attrs.get("COMPS_FileName", "")
                    project_root = os.path.dirname(filename) if filename else ""
                result = apply_file_changes(project_root, files, self._log)
                self._log(f"[job] Files applied: {result['applied']}, "
                          f"skipped: {result['skipped']}")
            else:
                self._log(f"[job] Auto-apply files disabled, skipping {len(files)} files")

        # Execute commands for command mode
        if commands and workspace_mode == "command":
            if self._auto_execute_commands:
                comp = get_comp(self.fusion)
                result = execute_commands(self.fusion, comp, commands, self._log)
                self._log(f"[job] Commands: executed={result['executed']}, "
                          f"failed={result['failed']}, skipped={result['skipped']}")
            else:
                self._log(f"[job] Auto-execute disabled, skipping {len(commands)} commands")

    def _handle_bridge_command(self, payload):
        """Handle bridge_command: execute and respond."""
        sender_id = payload.get("senderId", "")
        correlation_id = payload.get("correlationId", "")
        commands = payload.get("commands", [])

        self._log(f"[cmd] Received {len(commands)} commands (corr={correlation_id})")

        comp = get_comp(self.fusion)
        result = execute_commands(self.fusion, comp, commands, self._log)

        # Send result back
        self._ws.send("bridge_command_result", {
            "senderId": sender_id,
            "correlationId": correlation_id,
            "success": result["success"],
            "executed": result["executed"],
            "failed": result["failed"],
            "skipped": result["skipped"],
            "errors": result["errors"],
        })

    def _handle_file_deliver(self, payload):
        """Handle file_deliver messages."""
        files = payload.get("files", [])
        project_path = payload.get("projectPath", "")
        source = payload.get("source", "unknown")

        if not project_path:
            comp = get_comp(self.fusion)
            if comp:
                attrs = comp.GetAttrs() or {}
                filename = attrs.get("COMPS_FileName", "")
                project_path = os.path.dirname(filename) if filename else ""

        self._log(f"[file] Delivering {len(files)} files from {source}")

        if self._auto_apply_files and project_path:
            result = apply_file_changes(project_path, files, self._log)
            self._log(f"[file] Delivered: {result['applied']}, skipped: {result['skipped']}")
        else:
            self._log("[file] Auto-apply disabled or no project path")


# ---------------------------------------------------------------------------
# UI Panel (Fusion UI Manager)
# ---------------------------------------------------------------------------

def create_ui_panel(bridge):
    """
    Create a dockable UI panel in Fusion with connection controls
    and context actions.
    """
    fusion_app = bridge.fusion
    if not fusion_app:
        print("[Arkestrator] No Fusion app found")
        return

    ui = fusion_app.UIManager
    disp = ui.UIDispatcher if hasattr(ui, "UIDispatcher") else None
    if not ui or not disp:
        # Fallback: headless mode (no UI) — just connect
        print("[Arkestrator] No UI Manager — running headless")
        bridge.connect()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            bridge.disconnect()
        return

    # Build the panel layout
    win = disp.AddWindow({
        "ID": "ArkWin",
        "WindowTitle": "Arkestrator",
        "Geometry": [100, 100, 320, 520],
        "Spacing": 4,
    }, [
        ui.VGroup({"Spacing": 4}, [
            # Status
            ui.HGroup({"Spacing": 4}, [
                ui.Label({
                    "ID": "StatusLabel",
                    "Text": "Disconnected",
                    "Alignment": {"AlignLeft": True},
                    "StyleSheet": "color: #e74c3c; font-weight: bold;",
                }),
            ]),

            # Connect / Disconnect
            ui.HGroup({"Spacing": 4}, [
                ui.Button({"ID": "ConnectBtn", "Text": "Connect"}),
                ui.Button({"ID": "DisconnectBtn", "Text": "Disconnect", "Enabled": False}),
            ]),

            ui.VGap(4),
            ui.Label({"Text": "── Add to Context ──", "Alignment": {"AlignHCenter": True},
                       "StyleSheet": "color: #888;"}),

            # Context actions
            ui.Button({"ID": "AddSelectedBtn", "Text": "Selected Tools",
                        "ToolTip": "Add all selected tools to AI context"}),
            ui.Button({"ID": "AddActiveBtn", "Text": "Active Tool",
                        "ToolTip": "Add the currently viewed tool to AI context"}),
            ui.Button({"ID": "AddToolSettingsBtn", "Text": "Tool Settings (Active)",
                        "ToolTip": "Add all settings/inputs of the active tool"}),
            ui.Button({"ID": "AddKeyframesBtn", "Text": "Keyframes (Active)",
                        "ToolTip": "Add keyframe data for the active tool"}),
            ui.Button({"ID": "AddCompBtn", "Text": "Full Composition",
                        "ToolTip": "Add the full comp structure to context"}),
            ui.Button({"ID": "AddFlowBtn", "Text": "Flow Graph",
                        "ToolTip": "Add the node graph topology to context"}),
            ui.Button({"ID": "AddLoadersBtn", "Text": "All Loaders",
                        "ToolTip": "Add all media inputs to context"}),
            ui.Button({"ID": "AddSaversBtn", "Text": "All Savers",
                        "ToolTip": "Add all render outputs to context"}),
            ui.Button({"ID": "Add3DBtn", "Text": "3D Scene",
                        "ToolTip": "Add the 3D scene hierarchy to context"}),
            ui.Button({"ID": "AddModifiersBtn", "Text": "Modifiers & Expressions",
                        "ToolTip": "Add all modifiers and expressions to context"}),

            ui.VGap(4),
            ui.Label({"Text": "── Options ──", "Alignment": {"AlignHCenter": True},
                       "StyleSheet": "color: #888;"}),

            ui.HGroup({"Spacing": 4}, [
                ui.CheckBox({"ID": "AutoApplyChk", "Text": "Auto-apply files", "Checked": True}),
            ]),
            ui.HGroup({"Spacing": 4}, [
                ui.CheckBox({"ID": "AutoExecChk", "Text": "Auto-execute commands", "Checked": True}),
            ]),

            ui.VGap(8),

            # Log area
            ui.TextEdit({
                "ID": "LogArea",
                "ReadOnly": True,
                "StyleSheet": "font-family: monospace; font-size: 11px; background: #1e1e1e; color: #ccc;",
            }),
        ]),
    ])

    items = win.GetItems()
    log_area = items.get("LogArea")
    status_label = items.get("StatusLabel")

    def ui_log(msg):
        """Append to the log area."""
        if log_area:
            try:
                existing = log_area.PlainText or ""
                lines = existing.split("\n")
                # Keep last 200 lines
                if len(lines) > 200:
                    lines = lines[-200:]
                lines.append(str(msg))
                log_area.PlainText = "\n".join(lines)
            except Exception:
                pass
        print(msg)

    bridge._log_fn = ui_log

    def update_status():
        """Update connection status label."""
        if bridge.connected:
            status_label.Text = "Connected"
            status_label.StyleSheet = "color: #2ecc71; font-weight: bold;"
            items["ConnectBtn"].Enabled = False
            items["DisconnectBtn"].Enabled = True
        else:
            status_label.Text = "Disconnected"
            status_label.StyleSheet = "color: #e74c3c; font-weight: bold;"
            items["ConnectBtn"].Enabled = True
            items["DisconnectBtn"].Enabled = False

    # Status polling timer
    status_stop = threading.Event()

    def status_poll():
        while not status_stop.is_set():
            try:
                update_status()
            except Exception:
                pass
            status_stop.wait(2.0)

    status_thread = threading.Thread(target=status_poll, daemon=True, name="ark-status")
    status_thread.start()

    # -- Event handlers ------------------------------------------------------

    def on_connect(ev):
        ui_log("[ui] Connecting...")
        bridge.connect()
        # Give WS thread time to establish connection
        time.sleep(1.5)
        update_status()
        if bridge.connected:
            ui_log("[ui] Connected!")
        else:
            ui_log("[ui] Connection failed — check config")

    def on_disconnect(ev):
        ui_log("[ui] Disconnecting...")
        bridge.disconnect()
        update_status()

    def on_add_selected(ev):
        ui_log(f"[ui] add_selected: connected={bridge.connected}")
        if not bridge.connected:
            ui_log("[ui] Not connected — click Connect first")
            return
        try:
            comp = get_comp(bridge.fusion)
            ui_log(f"[ui] comp={comp}")
            if comp:
                tools = comp.GetToolList(True)
                ui_log(f"[ui] selected tools raw: {tools}")
                all_tools = comp.GetToolList(False)
                ui_log(f"[ui] all tools count: {len(all_tools) if all_tools else 0}")
            count = bridge.add_selected_to_context()
            ui_log(f"[ui] Added {count} selected tools")
        except Exception as exc:
            ui_log(f"[ui] ERROR: {exc}")
            import traceback
            traceback.print_exc()

    def on_add_active(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_active_tool_to_context()

    def on_add_tool_settings(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_tool_settings_to_context()

    def on_add_keyframes(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_tool_keyframes_to_context()

    def on_add_comp(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_comp_to_context()

    def on_add_flow(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_flow_graph_to_context()

    def on_add_loaders(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        count = bridge.add_loaders_to_context()
        ui_log(f"[ui] Added {count} loaders")

    def on_add_savers(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        count = bridge.add_savers_to_context()
        ui_log(f"[ui] Added {count} savers")

    def on_add_3d(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_3d_scene_to_context()

    def on_add_modifiers(ev):
        if not bridge.connected:
            ui_log("[ui] Not connected")
            return
        bridge.add_modifiers_to_context()

    def on_auto_apply_changed(ev):
        bridge._auto_apply_files = items["AutoApplyChk"].Checked

    def on_auto_exec_changed(ev):
        bridge._auto_execute_commands = items["AutoExecChk"].Checked

    def on_close(ev):
        status_stop.set()
        bridge.disconnect()
        disp.ExitLoop()

    # Wire events
    win.On.ConnectBtn.Clicked = on_connect
    win.On.DisconnectBtn.Clicked = on_disconnect
    win.On.AddSelectedBtn.Clicked = on_add_selected
    win.On.AddActiveBtn.Clicked = on_add_active
    win.On.AddToolSettingsBtn.Clicked = on_add_tool_settings
    win.On.AddKeyframesBtn.Clicked = on_add_keyframes
    win.On.AddCompBtn.Clicked = on_add_comp
    win.On.AddFlowBtn.Clicked = on_add_flow
    win.On.AddLoadersBtn.Clicked = on_add_loaders
    win.On.AddSaversBtn.Clicked = on_add_savers
    win.On.Add3DBtn.Clicked = on_add_3d
    win.On.AddModifiersBtn.Clicked = on_add_modifiers
    win.On.AutoApplyChk.Clicked = on_auto_apply_changed
    win.On.AutoExecChk.Clicked = on_auto_exec_changed
    win.On.ArkWin.Close = on_close

    # Auto-connect if config exists
    conf = cfg.read_config()
    key = cfg.get_api_key(conf) if conf else None
    url = cfg.get_ws_url(conf) if conf else None
    ui_log(f"[ui] Config: url={url}, key={'yes' if key else 'MISSING'}")
    if conf and key:
        ui_log("[ui] Auto-connecting...")
        bridge.connect()
        # Give WS thread time to connect before showing panel
        time.sleep(2)
        if bridge.connected:
            ui_log("[ui] Connected!")
        else:
            ui_log("[ui] WS thread started but not connected yet — check console")
            # Print thread status for debugging
            import threading
            for t in threading.enumerate():
                ui_log(f"[ui] Thread: {t.name} alive={t.is_alive()} daemon={t.daemon}")
    else:
        ui_log("[ui] No config/key — use Connect button")

    win.Show()
    ui_log("[ui] Panel shown, entering RunLoop...")
    disp.RunLoop()
    win.Hide()


# ---------------------------------------------------------------------------
# Headless event loop — keeps fuscript.exe alive using Fusion's UIDispatcher
# ---------------------------------------------------------------------------

def _run_headless(bridge, fusion_app):
    """Run the bridge in headless mode using Fusion's UIDispatcher.

    Creates a minimal hidden window and runs disp.RunLoop() to keep the
    fuscript.exe process alive.  This is the same mechanism the UI Panel
    uses — disp.RunLoop() is Fusion's own event loop, so it keeps the
    process alive while remaining responsive (not blocking Fusion's UI).

    When Fusion closes, the dispatcher exits and RunLoop() returns.
    """
    ui = fusion_app.UIManager
    if not ui:
        print("[Arkestrator] No UIManager available — cannot run headless")
        return

    # Get UIDispatcher — same approach as create_ui_panel()
    disp = getattr(ui, "UIDispatcher", None)
    if not disp:
        # Try bmd global (available in direct RunScript contexts)
        try:
            disp = bmd.UIDispatcher(ui)  # noqa: F821
        except (NameError, AttributeError):
            pass
    if not disp:
        print("[Arkestrator] No UIDispatcher available — cannot run headless")
        return

    # Create a minimal hidden window (dispatcher needs at least one window)
    _win_id = "ArkHeadless"
    win = disp.AddWindow(
        {
            "ID": _win_id,
            "WindowTitle": "Arkestrator Bridge",
            "Geometry": [0, 0, 1, 1],
        },
        ui.VGroup([
            ui.Label({"ID": "StatusLabel", "Text": "Bridge running"}),
        ]),
    )

    def on_close(ev):
        bridge.disconnect()
        disp.ExitLoop()

    win.On[_win_id].Close = on_close

    # -- Command file IPC ---------------------------------------------------
    # Other fuscript.exe processes (e.g. add_context, disconnect) can't access
    # this bridge instance directly.  They write a JSON command to a known
    # temp file, and this timer picks it up and executes it.
    import tempfile as _tmpmod
    _cmd_path = os.path.join(_tmpmod.gettempdir(), "arkestrator_fusion_cmd.json")

    def _check_commands(ev=None):
        """Check for IPC command files and execute them."""
        if not os.path.isfile(_cmd_path):
            return
        try:
            with open(_cmd_path, "r") as f:
                raw = f.read()
            os.remove(_cmd_path)
            cmd = json.loads(raw)
            action = cmd.get("action", "")

            if action == "add_selected":
                count = bridge.add_selected_to_context()
                print(f"[Arkestrator] Added {count} selected tool(s) to context")
            elif action == "add_active":
                bridge.add_active_tool_to_context()
                print("[Arkestrator] Added active tool to context")
            elif action == "add_comp":
                bridge.add_comp_to_context()
                print("[Arkestrator] Added comp to context")
            elif action == "add_flow":
                bridge.add_flow_graph_to_context()
            elif action == "add_loaders":
                bridge.add_loaders_to_context()
            elif action == "add_savers":
                bridge.add_savers_to_context()
            elif action == "add_3d":
                bridge.add_3d_scene_to_context()
            elif action == "add_modifiers":
                bridge.add_modifiers_to_context()
            elif action == "add_settings":
                bridge.add_tool_settings_to_context()
            elif action == "add_keyframes":
                bridge.add_tool_keyframes_to_context()
            elif action == "disconnect":
                bridge.disconnect()
                disp.ExitLoop()
            else:
                print(f"[Arkestrator] Unknown IPC command: {action}")
        except Exception as exc:
            print(f"[Arkestrator] IPC error: {exc}")

    # Poll for command files in a daemon thread (reliable cross-process IPC).
    # We know daemon threads work here because the WS thread uses the same pattern.
    _ipc_stop = threading.Event()

    def _ipc_poll_loop():
        while not _ipc_stop.is_set():
            _check_commands()
            _ipc_stop.wait(0.5)  # 500ms poll interval

    _ipc_thread = threading.Thread(target=_ipc_poll_loop, daemon=True, name="ark-ipc")
    _ipc_thread.start()

    # Show the window (required for RunLoop to stay active).
    # The window is 1x1 pixel, effectively invisible.
    win.Show()

    print("[Arkestrator] Bridge running (headless event loop)")

    # disp.RunLoop() blocks here — keeps fuscript.exe alive.
    # Returns when Fusion closes or disp.ExitLoop() is called.
    disp.RunLoop()
    _ipc_stop.set()

    print("[Arkestrator] Bridge event loop exited")
    bridge.disconnect()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Launch the Arkestrator Fusion bridge.

    Behaviour depends on environment:
      ARKESTRATOR_HEADLESS=1  -> connect + headless event loop (auto-start)
      Otherwise               -> open the UI panel (manual mode)

    Both modes use Fusion's UIDispatcher.RunLoop() to keep fuscript.exe
    alive for the entire session.  Daemon threads (WS, context push) survive
    because the process stays alive.
    """
    fusion_app = get_fusion_app()
    if fusion_app is None:
        print("[Arkestrator] ERROR: Could not find Fusion application.")
        return

    headless = os.environ.get("ARKESTRATOR_HEADLESS", "0") == "1"
    bridge = get_or_create_bridge(fusion_app)

    if headless:
        if bridge.connected:
            print("[Arkestrator] Already connected (headless)")
            return

        conf = cfg.read_config()
        if not conf or not cfg.get_api_key(conf):
            print("[Arkestrator] No config/API key found — skipping auto-connect")
            return

        print("[Arkestrator] Auto-connecting (headless)...")
        bridge.connect()
        _run_headless(bridge, fusion_app)
    else:
        # Manual mode: show the UI panel (blocking event loop)
        create_ui_panel(bridge)


if __name__ == "__main__":
    main()
