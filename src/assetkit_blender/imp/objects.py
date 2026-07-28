from __future__ import annotations

import bpy

from .animation.actions import _iter_action_fcurves


def _set_node_visibility(obj: bpy.types.Object, visible: bool) -> None:
    hidden = not bool(visible)
    obj.hide_viewport = hidden
    obj.hide_render = hidden


def _hide_helper_object(obj: bpy.types.Object, hide_empty: bool = False) -> None:
    obj["assetkit_helper_object"] = True
    if obj.type == "EMPTY":
        if hide_empty:
            _hide_empty_helper_object(obj)
        return

    obj.hide_select = True
    action = obj.animation_data.action if obj.animation_data else None
    if action and any(fcurve.data_path in {"hide_viewport", "hide_render"} for fcurve in _iter_action_fcurves(action)):
        return

    obj.hide_viewport = True
    obj.hide_render = True
    obj["assetkit_helper_hidden"] = True


def _keep_helper_object_visible(obj: bpy.types.Object) -> None:
    obj["assetkit_helper_object"] = True
    obj.hide_select = False
    obj.hide_viewport = False
    obj.hide_render = False
    if obj.get("assetkit_helper_hidden"):
        try:
            del obj["assetkit_helper_hidden"]
        except Exception:
            obj["assetkit_helper_hidden"] = False


def _hide_empty_helper_object(obj: bpy.types.Object) -> None:
    if obj.get("assetkit_helper_hidden"):
        return
    if not obj.get("assetkit_helper_object"):
        obj["assetkit_helper_object"] = True
    obj.hide_select = True
    try:
        obj.hide_set(True)
    except Exception:
        pass
    obj.hide_viewport = True
    obj.hide_render = True
    obj["assetkit_helper_hidden"] = True
