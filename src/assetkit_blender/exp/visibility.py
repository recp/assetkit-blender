from __future__ import annotations

import bpy

from .animation import animation_action_slot
from .animation.common import _iter_action_fcurves
from .common import _assetkit_extra_path, _assetkit_json_prop

_VISIBILITY_ANIMATION_PATHS = {"hide_viewport", "hide_render"}


def _object_visible_for_export(obj: bpy.types.Object) -> bool:
    return not _object_hidden_for_visibility_export(obj)


def _object_hidden_for_visibility_export(obj: bpy.types.Object) -> bool:
    if _object_uses_parent_source_visibility(obj):
        return False
    visible = _object_visibility_extra_value(obj)
    if visible is not None:
        return not visible
    if _object_has_ancestor_source_visibility(obj):
        return False
    if bool(obj.get("assetkit_helper_hidden", False)):
        return False
    return bool(getattr(obj, "hide_viewport", False) or getattr(obj, "hide_render", False))


def _object_visibility_extra_value(obj: bpy.types.Object) -> bool | None:
    extra = _assetkit_json_prop(obj, "assetkit_node_extra_json")
    visible = _assetkit_extra_path(extra, "extensions", "KHR_node_visibility", "visible")
    if not isinstance(visible, dict):
        return None
    value = visible.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return None


def _object_uses_parent_source_visibility(obj: bpy.types.Object) -> bool:
    parent = getattr(obj, "parent", None)
    if parent is None:
        return False
    if "assetkit_node_index" not in obj:
        return False
    if not bool(parent.get("assetkit_helper_object", False)):
        return False
    if _object_visibility_extra_value(parent) is not None:
        return True
    animation_data = parent.animation_data
    action = animation_data.action if animation_data else None
    return action is not None and _action_has_visibility_animation(action, animation_action_slot(animation_data))


def _object_has_ancestor_source_visibility(obj: bpy.types.Object) -> bool:
    if "assetkit_node_index" not in obj and not bool(obj.get("assetkit_helper_object", False)):
        return False
    parent = getattr(obj, "parent", None)
    while parent is not None:
        if _object_visibility_extra_value(parent) is not None:
            return True
        animation_data = parent.animation_data
        action = animation_data.action if animation_data else None
        if action is not None and _action_has_visibility_animation(action, animation_action_slot(animation_data)):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _action_has_visibility_animation(action: bpy.types.Action, slot=None) -> bool:
    for fcurve in _iter_action_fcurves(action, slot):
        if fcurve.data_path in _VISIBILITY_ANIMATION_PATHS:
            return True
    return False


def _is_assetkit_synthetic_helper_object(obj: bpy.types.Object) -> bool:
    if not bool(obj.get("assetkit_helper_object", False)):
        return False
    if (
        not bool(obj.get("assetkit_coordinate_root", False))
        and obj.name not in {"AssetKit Root", "AssetKit Coordinate Root", "AssetKit Coordinates"}
    ):
        return False
    if _assetkit_json_prop(obj, "assetkit_node_extra_json") is not None:
        return False
    animation_data = obj.animation_data
    if animation_data and animation_data.action:
        return False
    return True
