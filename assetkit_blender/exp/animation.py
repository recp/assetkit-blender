from __future__ import annotations

import bpy


def animation_action_slot(animation_data):
    return getattr(animation_data, "action_slot", None) if animation_data is not None else None


def animation_clip_name(action: bpy.types.Action | None) -> str:
    if action is None:
        return ""
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
