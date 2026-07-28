from __future__ import annotations

from array import array

import bpy

from ...assetkit import SceneNodeData
from ..animation.actions import (
    _animation_action_name,
    _blender_interpolation,
    _channel_action_clip,
    _ensure_fcurve,
    _register_action_frame_range,
    _stash_animation_action,
    _write_fcurve_points,
)
from ..buffers import (
    buffer_view as _buffer_view,
    channel_count as _channel_count,
    channel_interpolation as _channel_interpolation,
    channel_target as _channel_target,
    channel_times as _channel_times,
    channel_value_width as _channel_value_width,
    channel_values as _channel_values,
)
from ..material import _sample_anim_scalar
from ..animation.object import _ANIM_VISIBILITY, _animation_key_times

def _effective_static_node_visibility_map(nodes: list[SceneNodeData]) -> dict[int, bool]:
    visibility: dict[int, bool] = {}
    animated = [_node_has_visibility_animation(node) for node in nodes]
    count = len(nodes)

    for index in range(count):
        if index in visibility:
            continue

        stack: list[int] = []
        seen: set[int] = set()
        current = index
        while 0 <= current < count and current not in visibility and current not in seen:
            seen.add(current)
            stack.append(current)
            current = nodes[current].parent_index

        inherited = visibility.get(current, True) if 0 <= current < count else True
        while stack:
            node_index = stack.pop()
            if not animated[node_index]:
                inherited = inherited and bool(nodes[node_index].visible)
            visibility[node_index] = inherited

    return visibility


def _node_object_visibility_map(
    nodes: list[SceneNodeData],
    static_visibility: dict[int, bool],
) -> dict[int, bool]:
    visibility: dict[int, bool] = {}
    for index, node in enumerate(nodes):
        inherited = static_visibility.get(index, True)
        visibility[index] = inherited and bool(node.visible) if _node_has_visibility_animation(node) else inherited
    return visibility


def _node_has_visibility_animation(node: SceneNodeData) -> bool:
    for channel in node.anim_channels or ():
        if _channel_target(channel) == _ANIM_VISIBILITY:
            return True
    return False


def _node_has_effective_visibility_animation(
    node_index: int,
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
) -> bool:
    if node_index < 0 or not node_data:
        return False
    for ancestor_index in _node_ancestor_chain(node_index, node_data):
        node = _node_data_get(node_data, ancestor_index)
        if node and _node_has_visibility_animation(node):
            return True
    return False


def _apply_effective_node_visibility_animation(
    obj: bpy.types.Object,
    node_index: int,
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
) -> None:
    if node_index < 0 or not node_data:
        return

    chain = _node_ancestor_chain(node_index, node_data)
    channels_by_clip = _visibility_channels_by_clip(chain, node_data)
    if not channels_by_clip:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    end_frame = scene.frame_end
    actions: list[bpy.types.Action] = []

    for clip_key, node_channels in channels_by_clip.items():
        channels = [channel for channel_list in node_channels.values() for channel in channel_list]
        key_times = _animation_key_times(channels)
        if not key_times:
            continue
        if key_times[0] > 0.0:
            key_times.insert(0, 0.0)

        action = _visibility_action_for(obj, channels[0])
        actions.append(action)
        _register_action_frame_range(action, key_times[0] * fps, key_times[-1] * fps, obj)
        coords = array("f", [0.0]) * (len(key_times) * 2)
        for key_index, time_value in enumerate(key_times):
            coords[key_index * 2] = time_value * fps
            coords[key_index * 2 + 1] = 0.0 if _effective_visibility_at_time(
                chain,
                node_data,
                node_channels,
                time_value,
            ) else 1.0

        for path in ("hide_viewport", "hide_render"):
            _remove_fcurves(action, path)
            fcurve = _ensure_fcurve(action, obj, path, None, group_name="Visibility")
            _write_fcurve_points(fcurve, coords, "CONSTANT")

        end_frame = max(end_frame, int(key_times[-1] * fps + 0.5))

    for action in actions:
        _stash_animation_action(obj, action)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _node_ancestor_chain(
    node_index: int,
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
) -> list[int]:
    chain: list[int] = []
    seen: set[int] = set()
    current = node_index
    while current >= 0 and current not in seen:
        node = _node_data_get(node_data, current)
        if node is None:
            break
        seen.add(current)
        chain.append(current)
        current = node.parent_index
    chain.reverse()
    return chain


def _visibility_channels_by_clip(
    chain: list[int],
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
) -> dict[tuple[int, str], dict[int, list[dict]]]:
    clips: dict[tuple[int, str], dict[int, list[dict]]] = {}
    for node_index in chain:
        node = _node_data_get(node_data, node_index)
        if not node:
            continue
        for channel in node.anim_channels or ():
            if _channel_target(channel) != _ANIM_VISIBILITY:
                continue
            clip_key = _channel_action_clip(channel)
            clips.setdefault(clip_key, {}).setdefault(node_index, []).append(channel)
    return clips


def _effective_visibility_at_time(
    chain: list[int],
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
    channels_by_node: dict[int, list[dict]],
    time_value: float,
) -> bool:
    for node_index in chain:
        node = _node_data_get(node_data, node_index)
        if not node:
            continue
        channels = channels_by_node.get(node_index)
        if channels:
            visible = _visibility_channels_value(channels, node.visible, time_value)
        else:
            visible = bool(node.visible)
        if not visible:
            return False
    return True


def _node_data_get(
    node_data: dict[int, SceneNodeData] | list[SceneNodeData],
    node_index: int,
) -> SceneNodeData | None:
    if isinstance(node_data, list):
        return node_data[node_index] if 0 <= node_index < len(node_data) else None
    return node_data.get(node_index)


def _visibility_channels_value(
    channels: list[dict],
    fallback: bool,
    time_value: float,
) -> bool:
    value = 1.0 if fallback else 0.0
    for channel in channels:
        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        interpolation = _blender_interpolation(_channel_interpolation(channel))
        value = _sample_anim_scalar(times, values, count, value_width, 0, time_value, interpolation)
    return value >= 0.5


def _visibility_action_for(obj: bpy.types.Object, channel: dict) -> bpy.types.Action:
    action = _existing_action_for_clip(obj, "", channel)
    if action:
        return action

    obj.animation_data_create()
    action = bpy.data.actions.new(_animation_action_name(obj.name, "", channel))
    clip_index, _clip_name = _channel_action_clip(channel)
    if obj.animation_data.action is None or clip_index == 0:
        obj.animation_data.action = action
    return action


def _existing_action_for_clip(
    obj: bpy.types.Object,
    suffix: str,
    channel: dict,
) -> bpy.types.Action | None:
    if not obj.animation_data:
        return None

    name = _animation_action_name(obj.name, suffix, channel)
    active = obj.animation_data.action
    if active and _action_name_matches(active.name, name):
        return active

    for track in obj.animation_data.nla_tracks:
        for strip in track.strips:
            action = strip.action
            if action and _action_name_matches(action.name, name):
                return action
    return None


def _action_name_matches(candidate: str, expected: str) -> bool:
    return candidate == expected or candidate.startswith(f"{expected}.")


def _remove_fcurves(action: bpy.types.Action, data_path: str) -> None:
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:
        return
    for fcurve in list(fcurves):
        if fcurve.data_path == data_path:
            fcurves.remove(fcurve)
