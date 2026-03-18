"""AddonPreferences — persistent settings stored in Blender user prefs."""

import bpy
from bpy.props import StringProperty, BoolProperty


class AgentManagerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    server_url: StringProperty(
        name="Server URL",
        default="ws://localhost:7800/ws",
        description="Arkestrator WebSocket server URL",
    )
    auto_connect: BoolProperty(
        name="Auto Connect",
        default=True,
        description="Connect to server when addon loads",
    )
    auto_save: BoolProperty(
        name="Auto Save",
        default=True,
        description="Save .blend file before submitting a job",
    )
    auto_reload: BoolProperty(
        name="Auto Reload",
        default=True,
        description="Reload .blend file after job completion",
    )
    auto_apply_files: BoolProperty(
        name="Auto Apply Files",
        default=True,
        description="Automatically apply file changes from completed jobs",
    )
    auto_execute_commands: BoolProperty(
        name="Auto Execute Commands",
        default=True,
        description="Automatically execute Python commands from completed jobs",
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Connection", icon='LINKED')
        box.prop(self, "server_url")
        box.prop(self, "auto_connect")

        box = layout.box()
        box.label(text="Behavior", icon='PREFERENCES')
        box.prop(self, "auto_save")
        box.prop(self, "auto_reload")
        box.prop(self, "auto_apply_files")
        box.prop(self, "auto_execute_commands")
