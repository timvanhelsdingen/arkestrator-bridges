"""Editor context builder for ComfyUI bridge.

Gathers available node types, system stats, and queue state
from the ComfyUI API and formats them as bridge editor context.
"""

import time


# Cache for object_info (node types) — refreshed every 30s
_node_cache: dict = {}
_node_cache_time: float = 0.0
_NODE_CACHE_TTL = 30.0


def build_editor_context(comfyui_client) -> dict:
    """Build the editor context dict from ComfyUI state.

    Returns the standard bridge context format:
    {projectRoot, activeFile, metadata: {bridge_type, ...}}
    """
    global _node_cache, _node_cache_time

    metadata: dict = {
        "bridge_type": "comfyui",
    }

    if comfyui_client is None:
        return {
            "projectRoot": "",
            "activeFile": "",
            "metadata": metadata,
        }

    # System stats (VRAM, devices)
    try:
        stats = comfyui_client.get_system_stats()
        system = stats.get("system", {})
        metadata["vram_total"] = system.get("vram_total", 0)
        metadata["vram_free"] = system.get("vram_free", 0)
        devices = stats.get("devices", [])
        if devices:
            metadata["gpu"] = devices[0].get("name", "unknown")
            metadata["torch_vram_total"] = devices[0].get("vram_total", 0)
            metadata["torch_vram_free"] = devices[0].get("vram_free", 0)
    except Exception:
        pass

    # Queue state
    try:
        queue_info = comfyui_client.get_queue()
        running = queue_info.get("queue_running", [])
        pending = queue_info.get("queue_pending", [])
        metadata["queue_running"] = len(running)
        metadata["queue_pending"] = len(pending)
    except Exception:
        pass

    # Available node types (cached)
    now = time.monotonic()
    if now - _node_cache_time > _NODE_CACHE_TTL or not _node_cache:
        try:
            _node_cache = comfyui_client.get_object_info()
            _node_cache_time = now
        except Exception:
            pass

    if _node_cache:
        # Send node category summary rather than the full object_info
        categories: dict[str, int] = {}
        for node_name, node_info in _node_cache.items():
            cat = node_info.get("category", "uncategorized")
            categories[cat] = categories.get(cat, 0) + 1
        metadata["node_categories"] = categories
        metadata["total_nodes"] = len(_node_cache)

    return {
        "projectRoot": "",
        "activeFile": "",
        "metadata": metadata,
    }


def gather_file_attachments() -> list[dict]:
    """Gather file attachments from ComfyUI.

    ComfyUI doesn't have open files like a DCC app,
    so this returns an empty list.
    """
    return []
