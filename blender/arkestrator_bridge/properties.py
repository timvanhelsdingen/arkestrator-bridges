"""PropertyGroups for per-scene runtime state."""

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import PropertyGroup


# ---------------------------------------------------------------------------
# Scene-level state (thin — only connection + log)
# ---------------------------------------------------------------------------

class AgentManagerProperties(PropertyGroup):
    connection_status: StringProperty(name="Status", default="Disconnected")
    is_connected: BoolProperty(name="Connected", default=False)


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------

def register_properties():
    bpy.types.Scene.agent_manager = bpy.props.PointerProperty(
        type=AgentManagerProperties
    )


def unregister_properties():
    if hasattr(bpy.types.Scene, "agent_manager"):
        del bpy.types.Scene.agent_manager
