"""Blueprint introspection utilities for the Arkestrator UE5 bridge.

Extracts parent class, components, variables, functions, and interfaces
from Blueprint assets.  Every UE5 API call is independently try/excepted
so partial data is returned when APIs are unavailable across engine versions.
"""

from __future__ import annotations

import unreal

# List caps to keep context payloads reasonable
_MAX_COMPONENTS = 50
_MAX_VARIABLES = 50
_MAX_FUNCTIONS = 50
_MAX_INTERFACES = 20

# Engine-level properties/callables to exclude from variable/function diffing.
# These appear on virtually every CDO and are never user-defined.
_BUILTIN_SKIP = frozenset({
    "call", "cast", "execute_ubergraph", "get_class", "get_default_object",
    "get_editor_property", "get_fname", "get_full_name", "get_name",
    "get_outer", "get_outermost", "get_path_name", "get_typed_outer",
    "get_world", "is_a", "modify", "rename", "set_editor_properties",
    "set_editor_property", "static_class",
})


def is_blueprint(asset) -> bool:
    """Return True if *asset* is an ``unreal.Blueprint`` instance."""
    bp_class = getattr(unreal, "Blueprint", None)
    if bp_class is None:
        return False
    try:
        return isinstance(asset, bp_class)
    except Exception:
        return False


def get_blueprint_info(asset) -> dict | None:
    """Return a dict of introspected Blueprint data, or None on failure.

    Each section (parent, components, variables, functions, interfaces) is
    extracted independently so a failure in one does not prevent the others.
    """
    if not is_blueprint(asset):
        return None

    info: dict = {}

    _extract_parent_class(asset, info)
    _extract_components(asset, info)
    _extract_variables(asset, info)
    _extract_functions(asset, info)
    _extract_interfaces(asset, info)

    # Only return if we got at least *something* useful
    if not info:
        return None
    return info


# ------------------------------------------------------------------
# Sub-extractors
# ------------------------------------------------------------------

def _extract_parent_class(asset, info: dict) -> None:
    try:
        parent = asset.parent_class
        if parent:
            info["parent_class"] = parent.get_name()
            info["parent_class_path"] = parent.get_path_name()
    except Exception:
        pass


def _extract_components(asset, info: dict) -> None:
    components: list[dict] = []
    try:
        scs = asset.simple_construction_script
        if scs is None:
            # Data-only Blueprints (no Actor base) have no SCS
            info["components"] = []
            return

        root_node = None
        try:
            root_node = scs.get_default_scene_root_node()
        except Exception:
            pass

        try:
            all_nodes = scs.get_all_nodes()
        except Exception:
            all_nodes = []

        for node in all_nodes:
            try:
                comp = node.component_template
                if comp is None:
                    continue
                entry: dict = {
                    "name": comp.get_name(),
                    "class": comp.get_class().get_name(),
                }
                if root_node is not None:
                    entry["is_root"] = (node == root_node)
                components.append(entry)
            except Exception:
                continue

            if len(components) >= _MAX_COMPONENTS:
                break
    except Exception:
        pass

    truncated = len(components) >= _MAX_COMPONENTS
    info["components"] = components
    if truncated:
        info.setdefault("truncated", []).append("components")


def _extract_variables(asset, info: dict) -> None:
    variables: list[dict] = []
    try:
        gen_class = asset.generated_class()
        if gen_class is None:
            info["variables"] = []
            return

        get_default = getattr(unreal, "get_default_object", None)
        if get_default is None:
            info["variables"] = []
            return

        cdo = get_default(gen_class)
        if cdo is None:
            info["variables"] = []
            return

        # Collect parent properties to diff against
        parent_props: set[str] = set()
        try:
            parent_class = asset.parent_class
            if parent_class:
                parent_cdo = get_default(parent_class)
                if parent_cdo:
                    parent_props = set(dir(parent_cdo))
        except Exception:
            pass

        cdo_attrs = sorted(dir(cdo))
        for attr_name in cdo_attrs:
            if attr_name.startswith("_"):
                continue
            if attr_name in parent_props:
                continue
            if attr_name.lower() in _BUILTIN_SKIP:
                continue
            try:
                val = getattr(cdo, attr_name, None)
                if callable(val):
                    continue
                variables.append({
                    "name": attr_name,
                    "type": type(val).__name__ if val is not None else "unknown",
                })
            except Exception:
                continue

            if len(variables) >= _MAX_VARIABLES:
                break
    except Exception:
        pass

    truncated = len(variables) >= _MAX_VARIABLES
    info["variables"] = variables
    if truncated:
        info.setdefault("truncated", []).append("variables")


def _extract_functions(asset, info: dict) -> None:
    functions: list[str] = []

    # Strategy 1: function_graphs attribute (when exposed)
    try:
        func_graphs = getattr(asset, "function_graphs", None)
        if func_graphs:
            for graph in func_graphs:
                try:
                    name = graph.get_name()
                    if name and not name.startswith("_"):
                        functions.append(name)
                except Exception:
                    continue
    except Exception:
        pass

    # Strategy 2: CDO callable diff (fallback / supplement)
    if not functions:
        try:
            gen_class = asset.generated_class()
            if gen_class:
                get_default = getattr(unreal, "get_default_object", None)
                if get_default:
                    cdo = get_default(gen_class)
                    parent_funcs: set[str] = set()
                    try:
                        parent_class = asset.parent_class
                        if parent_class:
                            parent_cdo = get_default(parent_class)
                            if parent_cdo:
                                parent_funcs = {
                                    n for n in dir(parent_cdo)
                                    if not n.startswith("_")
                                    and callable(getattr(parent_cdo, n, None))
                                }
                    except Exception:
                        pass

                    if cdo:
                        for attr_name in sorted(dir(cdo)):
                            if attr_name.startswith("_"):
                                continue
                            if attr_name in parent_funcs:
                                continue
                            if attr_name.lower() in _BUILTIN_SKIP:
                                continue
                            try:
                                val = getattr(cdo, attr_name, None)
                                if callable(val):
                                    functions.append(attr_name)
                            except Exception:
                                continue

                            if len(functions) >= _MAX_FUNCTIONS:
                                break
        except Exception:
            pass

    truncated = len(functions) >= _MAX_FUNCTIONS
    info["functions"] = functions[:_MAX_FUNCTIONS]
    if truncated:
        info.setdefault("truncated", []).append("functions")


def _extract_interfaces(asset, info: dict) -> None:
    interfaces: list[str] = []

    # Strategy 1: asset.implemented_interfaces()
    try:
        implemented = asset.implemented_interfaces()
        if implemented:
            for iface in implemented:
                try:
                    interfaces.append(iface.get_name())
                except Exception:
                    interfaces.append(str(iface))
                if len(interfaces) >= _MAX_INTERFACES:
                    break
    except Exception:
        pass

    # Strategy 2: generated_class().get_interfaces() (fallback)
    if not interfaces:
        try:
            gen_class = asset.generated_class()
            if gen_class:
                iface_classes = gen_class.get_interfaces()
                if iface_classes:
                    for ic in iface_classes:
                        try:
                            interfaces.append(ic.get_name())
                        except Exception:
                            interfaces.append(str(ic))
                        if len(interfaces) >= _MAX_INTERFACES:
                            break
        except Exception:
            pass

    truncated = len(interfaces) >= _MAX_INTERFACES
    info["interfaces"] = interfaces[:_MAX_INTERFACES]
    if truncated:
        info.setdefault("truncated", []).append("interfaces")
