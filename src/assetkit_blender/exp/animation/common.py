from __future__ import annotations

import bpy

_AK_ACTION_CLIP_EXPORT_NAME_PROP = "assetkit_animation_clip_export_name"


def animation_action_slot(animation_data):
    return getattr(animation_data, "action_slot", None) if animation_data is not None else None


def animation_clip_name(action: bpy.types.Action | None) -> str:
    if action is None:
        return ""
    try:
        value = action.get(_AK_ACTION_CLIP_EXPORT_NAME_PROP)
        if value:
            return str(value).strip()[:96]
    except Exception:
        pass
    name = str(getattr(action, "name", "") or "").strip()
    return name[:96]


def animation_channel_with_clip(channel: tuple | None, action: bpy.types.Action | None) -> tuple | None:
    if channel is None:
        return None
    name = animation_clip_name(action)
    if not name or len(channel) >= 7:
        return channel
    return (*channel, 0, name)


def animation_channels_with_clip(channels: tuple | list, action: bpy.types.Action | None) -> tuple:
    if action is None:
        return tuple(channels)
    return tuple(
        wrapped
        for channel in channels
        if (wrapped := animation_channel_with_clip(channel, action)) is not None
    )


def _iter_action_fcurves(action: bpy.types.Action, slot=None):
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None and len(fcurves) > 0:
        yield from fcurves
        return

    action_slots = tuple(getattr(action, "slots", []) or ())
    if slot is not None:
        slots = (slot,)
    elif len(action_slots) == 1:
        slots = action_slots
    else:
        return
    if not slots:
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for current_slot in slots:
                try:
                    channelbag = strip.channelbag(current_slot)
                except Exception:
                    channelbag = None
                if channelbag is not None:
                    yield from getattr(channelbag, "fcurves", []) or []
