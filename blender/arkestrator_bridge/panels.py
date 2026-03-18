"""UI Panels for the Arkestrator N-panel sidebar in 3D Viewport.

Thin bridge architecture: main panel shows connection status only.
All job submission UI lives in the Tauri client.
"""

import bpy


# ---------------------------------------------------------------------------
# Main Panel (connection status only)
# ---------------------------------------------------------------------------

class AGENTMGR_PT_main_panel(bpy.types.Panel):
    bl_label = "Arkestrator"
    bl_idname = "AGENTMGR_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Arkestrator"

    def draw(self, context):
        layout = self.layout
        if not hasattr(context.scene, 'agent_manager'):
            layout.label(text="Initializing…")
            return
        props = context.scene.agent_manager

        # Connection status
        row = layout.row()
        status_icon = 'LINKED' if props.is_connected else 'UNLINKED'
        row.label(text=f"Status: {props.connection_status}", icon=status_icon)

        # Connect/Disconnect button
        row = layout.row()
        ws_label = "Disconnect" if props.is_connected else "Connect"
        ws_icon = 'UNLINKED' if props.is_connected else 'LINKED'
        row.operator("agent_manager.connect", text=ws_label, icon=ws_icon)


# ---------------------------------------------------------------------------
# Settings Sub-Panel
# ---------------------------------------------------------------------------

class AGENTMGR_PT_settings(bpy.types.Panel):
    bl_label = "Settings"
    bl_idname = "AGENTMGR_PT_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Arkestrator"
    bl_parent_id = "AGENTMGR_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        try:
            prefs = context.preferences.addons[__package__].preferences
        except KeyError:
            layout.label(text="Addon preferences not available")
            return

        layout.prop(prefs, "server_url", text="Server URL")

        layout.separator()
        layout.prop(prefs, "auto_connect")
        layout.prop(prefs, "auto_reload")
        layout.prop(prefs, "auto_apply_files")
        layout.prop(prefs, "auto_execute_commands")

