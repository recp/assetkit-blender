from __future__ import annotations

import json
from array import array

import bpy

from ...assetkit import (
    MeshPrimitiveData,
    native_animation_coords,
    native_animation_quat_slerp_coords,
)
from ..buffers import (
    buffer_view as _buffer_view,
    channel_count as _channel_count,
    channel_interpolation as _channel_interpolation,
    channel_is_partial as _channel_is_partial,
    channel_target as _channel_target,
    channel_target_offset as _channel_target_offset,
    channel_times as _channel_times,
    channel_value_width as _channel_value_width,
    channel_values as _channel_values,
)
from ..material import _texture_transform_sample_into
from .actions import (
    _animation_action_for,
    _blender_interpolation,
    _channel_frame_bounds,
    _channel_tangents,
    _ensure_fcurve,
    _fcurve_write_key,
    _merge_frame_bounds,
    _register_action_frame_range,
    _register_actions_frame_range,
    _stash_animation_actions,
    _write_fcurve_points,
)

_ANIM_TRANSLATION       = 1
_ANIM_ROTATION_QUAT     = 2
_ANIM_SCALE             = 3
_ANIM_MORPH_WEIGHTS     = 4
_ANIM_VISIBILITY        = 5
_ANIM_CAMERA_XFOV       = 6
_ANIM_CAMERA_YFOV       = 7
_ANIM_CAMERA_ZNEAR      = 8
_ANIM_CAMERA_ZFAR       = 9
_ANIM_CAMERA_ORTHO_XMAG = 10
_ANIM_CAMERA_ORTHO_YMAG = 11
_ANIM_LIGHT_COLOR       = 12
_ANIM_LIGHT_INTENSITY   = 13
_ANIM_LIGHT_RANGE       = 14
_ANIM_LIGHT_SPOT_INNER  = 15
_ANIM_LIGHT_SPOT_OUTER  = 16


def _apply_animation(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    *,
    skip_visibility: bool = False,
) -> None:
    channels = data.anim_channels or []
    if not channels:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0

    if any(_channel_target(channel) == _ANIM_ROTATION_QUAT for channel in channels):
        obj.rotation_mode = "QUATERNION"

    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    end_frame = scene.frame_end
    frame_bounds: tuple[float, float] | None = None
    converted_targets, cone_end_frame = _apply_light_spot_cone_animations(
        obj,
        channels,
        actions,
        written_fcurves,
        fps,
        start_frame,
    )
    end_frame = max(end_frame, cone_end_frame)

    for channel in channels:
        target = _channel_target(channel)
        if target in converted_targets:
            continue
        if target == _ANIM_VISIBILITY:
            if skip_visibility:
                continue
            action = _animation_action_for(obj, obj, actions, "", channel)
            end_frame = max(end_frame, _apply_visibility_animation_channel(obj, action, channel, fps, start_frame))
            bounds = _channel_frame_bounds(channel, fps, start_frame)
            if bounds is not None:
                frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])
            continue

        owner, path, width, group_name = _anim_channel_target(obj, target)
        if not owner or not path:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        bounds = _channel_frame_bounds(channel, fps, start_frame)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        if target_offset >= width:
            continue

        action = _animation_action_for(obj, owner, actions, "" if owner == obj else "_Data", channel)
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        if not is_partial:
            if _anim_channel_can_use_native_coords(target):
                coords_by_component: list[object | None] = [
                    (
                        native_animation_quat_slerp_coords(channel, component, fps)
                        if target == _ANIM_ROTATION_QUAT
                        and interpolation == "LINEAR"
                        and component_count == 4
                        and value_width == 4
                        else native_animation_coords(channel, component, fps)
                    )
                    for component in range(component_count)
                ]
            else:
                coords_by_component = [None] * component_count

            if any(coords is None for coords in coords_by_component):
                coords_by_component = [array("f", [0.0]) * (count * 2) for _ in range(component_count)]
                for key_index in range(count):
                    frame = start_frame + times[key_index] * fps
                    base = key_index * value_width
                    for component, coords in enumerate(coords_by_component):
                        coords[key_index * 2] = frame
                        coords[key_index * 2 + 1] = _anim_channel_value(
                            obj,
                            target,
                            values[base + component],
                        )

            for component, coords in enumerate(coords_by_component):
                target_index = target_offset + component
                fcurve_index = None if width == 1 else target_index
                write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
                if write_key in written_fcurves:
                    continue
                written_fcurves.add(write_key)
                fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
                _write_fcurve_points(
                    fcurve,
                    coords,
                    interpolation,
                    times=times,
                    fps=fps,
                    in_tangents=in_tangents,
                    out_tangents=out_tangents,
                    value_width=value_width,
                    value_index=component,
                    tangent_value=(
                        lambda value, target=target: _anim_channel_tangent_value(target, value)
                    ),
                )

            end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))
            continue

        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            fcurve_index = None if width == 1 else target_index
            write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
            coords = (
                native_animation_coords(channel, value_index, fps)
                if _anim_channel_can_use_native_coords(target)
                else None
            )
            if coords is None:
                coords = array("f", [0.0]) * (count * 2)
                for key_index in range(count):
                    coords[key_index * 2] = start_frame + times[key_index] * fps
                    coords[key_index * 2 + 1] = _anim_channel_value(
                        obj,
                        target,
                        values[key_index * value_width + value_index],
                    )

            _write_fcurve_points(
                fcurve,
                coords,
                interpolation,
                times=times,
                fps=fps,
                in_tangents=in_tangents,
                out_tangents=out_tangents,
                value_width=value_width,
                value_index=value_index,
                tangent_value=(
                    lambda value, target=target: _anim_channel_tangent_value(target, value)
                ),
            )

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    _register_actions_frame_range(actions, frame_bounds)
    _stash_animation_actions(actions)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _apply_light_spot_cone_animations(
    obj: bpy.types.Object,
    channels: list[dict],
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    written_fcurves: set[tuple[int, int, str, int]],
    fps: float,
    start_frame: float,
) -> tuple[set[int], int]:
    data = getattr(obj, "data", None)
    if obj.type != "LIGHT" or not data or getattr(data, "type", "") != "SPOT":
        return set(), bpy.context.scene.frame_end
    if not hasattr(data, "spot_size") or not hasattr(data, "spot_blend"):
        return set(), bpy.context.scene.frame_end

    cone_channels = {
        _ANIM_LIGHT_SPOT_INNER: [
            channel for channel in channels
            if _channel_target(channel) == _ANIM_LIGHT_SPOT_INNER
        ],
        _ANIM_LIGHT_SPOT_OUTER: [
            channel for channel in channels
            if _channel_target(channel) == _ANIM_LIGHT_SPOT_OUTER
        ],
    }
    if not cone_channels[_ANIM_LIGHT_SPOT_INNER] and not cone_channels[_ANIM_LIGHT_SPOT_OUTER]:
        return set(), bpy.context.scene.frame_end

    key_times = _animation_key_times(cone_channels[_ANIM_LIGHT_SPOT_INNER] + cone_channels[_ANIM_LIGHT_SPOT_OUTER])
    if not key_times:
        return set(), bpy.context.scene.frame_end

    outer_fallback = max(float(data.spot_size) * 0.5, 1.0e-6)
    inner_fallback = outer_fallback * max(0.0, min(1.0, 1.0 - float(data.spot_blend)))
    first_channel = cone_channels[_ANIM_LIGHT_SPOT_OUTER][0] if cone_channels[_ANIM_LIGHT_SPOT_OUTER] else cone_channels[_ANIM_LIGHT_SPOT_INNER][0]
    action = _animation_action_for(obj, data, actions, "_Data", first_channel)
    interpolation = _merged_animation_interpolation(cone_channels[_ANIM_LIGHT_SPOT_INNER] + cone_channels[_ANIM_LIGHT_SPOT_OUTER])
    converted: set[int] = set()
    _register_action_frame_range(action, start_frame + key_times[0] * fps, start_frame + key_times[-1] * fps, data)

    if cone_channels[_ANIM_LIGHT_SPOT_OUTER]:
        coords = array("f", [0.0]) * (len(key_times) * 2)
        for key_index, time_value in enumerate(key_times):
            outer = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_OUTER], outer_fallback, time_value)
            coords[key_index * 2] = start_frame + time_value * fps
            coords[key_index * 2 + 1] = max(0.0, float(outer)) * 2.0
        write_key = _fcurve_write_key(data, first_channel, "spot_size", None)
        if write_key not in written_fcurves:
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, data, "spot_size", None, group_name="Light")
            _write_fcurve_points(fcurve, coords, interpolation)
        converted.add(_ANIM_LIGHT_SPOT_OUTER)

    coords = array("f", [0.0]) * (len(key_times) * 2)
    for key_index, time_value in enumerate(key_times):
        inner = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_INNER], inner_fallback, time_value)
        outer = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_OUTER], outer_fallback, time_value)
        coords[key_index * 2] = start_frame + time_value * fps
        coords[key_index * 2 + 1] = _spot_blend_from_angles(inner, outer)
    write_key = _fcurve_write_key(data, first_channel, "spot_blend", None)
    if write_key not in written_fcurves:
        written_fcurves.add(write_key)
        fcurve = _ensure_fcurve(action, data, "spot_blend", None, group_name="Light")
        _write_fcurve_points(fcurve, coords, interpolation)
    converted.add(_ANIM_LIGHT_SPOT_INNER)

    return converted, int(start_frame + key_times[-1] * fps + 0.5)


def _spot_blend_from_angles(inner: float, outer: float) -> float:
    outer = max(float(outer), 1.0e-6)
    inner = max(0.0, min(float(inner), outer))
    return max(0.0, min(1.0, 1.0 - inner / outer))


def _animation_key_times(channels: list[dict]) -> list[float]:
    values: set[float] = set()
    for channel in channels:
        count = _channel_count(channel)
        times = _buffer_view(_channel_times(channel), "f")
        if count <= 0 or times is None:
            continue
        for index in range(min(count, len(times))):
            values.add(float(times[index]))
    return sorted(values)


def _merged_animation_interpolation(channels: list[dict]) -> str:
    for channel in channels:
        if _blender_interpolation(_channel_interpolation(channel)) != "CONSTANT":
            return "LINEAR"
    return "CONSTANT"


def _animation_sample_scalar(
    channels: list[dict],
    fallback: float,
    time_value: float,
) -> float:
    values = [float(fallback)]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0]


def _anim_channel_target(
    obj: bpy.types.Object,
    target: int,
) -> tuple[bpy.types.ID | None, str, int, str]:
    path, width = _anim_target_path(target)
    if path:
        return obj, path, width, "Transform"

    data = getattr(obj, "data", None)
    if obj.type == "CAMERA" and data:
        if target == _ANIM_CAMERA_XFOV:
            return data, "angle_x", 1, "Camera"
        if target == _ANIM_CAMERA_YFOV:
            return data, "angle_y", 1, "Camera"
        if target == _ANIM_CAMERA_ZNEAR:
            return data, "clip_start", 1, "Camera"
        if target == _ANIM_CAMERA_ZFAR:
            return data, "clip_end", 1, "Camera"
        if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG}:
            return data, "ortho_scale", 1, "Camera"

    if obj.type == "LIGHT" and data:
        if target == _ANIM_LIGHT_COLOR:
            return data, "color", 3, "Light"
        if target == _ANIM_LIGHT_INTENSITY:
            return data, "energy", 1, "Light"
        if target == _ANIM_LIGHT_RANGE and hasattr(data, "cutoff_distance"):
            return data, "cutoff_distance", 1, "Light"
        if target == _ANIM_LIGHT_SPOT_OUTER and hasattr(data, "spot_size"):
            return data, "spot_size", 1, "Light"
        if target == _ANIM_LIGHT_SPOT_INNER and hasattr(data, "spot_blend"):
            return data, "spot_blend", 1, "Light"

    return None, "", 0, ""


def _anim_channel_value(obj: bpy.types.Object, target: int, value: float) -> float:
    if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG, _ANIM_LIGHT_SPOT_OUTER}:
        return value * 2.0

    if target == _ANIM_LIGHT_SPOT_INNER:
        data = getattr(obj, "data", None)
        outer = getattr(data, "spot_size", 0.0) * 0.5 if data else 0.0
        if outer <= 1.0e-6:
            return 0.0
        return max(0.0, min(1.0, 1.0 - value / outer))

    return value


def _anim_channel_tangent_value(target: int, value: float) -> float:
    if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG, _ANIM_LIGHT_SPOT_OUTER}:
        return value * 2.0
    return value


def _apply_visibility_animation_channel(
    obj: bpy.types.Object,
    action: bpy.types.Action,
    channel: dict,
    fps: float,
    start_frame: float,
) -> int:
    count = _channel_count(channel)
    value_width = _channel_value_width(channel)
    times = _buffer_view(_channel_times(channel), "f")
    values = _buffer_view(_channel_values(channel), "f")
    if count <= 0 or value_width <= 0 or times is None or values is None:
        return bpy.context.scene.frame_end

    coords = array("f", [0.0]) * (count * 2)
    for key_index in range(count):
        coords[key_index * 2] = start_frame + times[key_index] * fps
        coords[key_index * 2 + 1] = 0.0 if values[key_index * value_width] >= 0.5 else 1.0

    for path in ("hide_viewport", "hide_render"):
        fcurve = _ensure_fcurve(action, obj, path, None, group_name="Visibility")
        _write_fcurve_points(fcurve, coords, "CONSTANT")

    return int(start_frame + times[count - 1] * fps + 0.5)


def _apply_shape_keys(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    targets = data.morph_targets or []
    if not targets:
        return

    vertex_count = len(obj.data.vertices)
    obj.shape_key_add(name="Basis", from_mix=False)
    for index, target in enumerate(targets):
        if target.vertex_count != vertex_count:
            continue
        coords = _buffer_view(target.positions_f32, "f")
        if coords is None or len(coords) != vertex_count * 3:
            continue

        key = obj.shape_key_add(name=target.name or f"AssetKit Morph {index}", from_mix=False)
        key.data.foreach_set("co", coords)
        key.value = target.weight

    obj.data.update()
    _apply_shape_key_animation(obj, data)


def _apply_shape_key_animation(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    channels = data.morph_anim_channels or []
    shape_keys = obj.data.shape_keys
    if not channels or not shape_keys:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0
    end_frame = scene.frame_end

    shape_keys.animation_data_create()
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    frame_bounds: tuple[float, float] | None = None

    for channel in channels:
        if _channel_target(channel) != _ANIM_MORPH_WEIGHTS:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        bounds = _channel_frame_bounds(channel, fps, start_frame)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        component_count = 1 if is_partial else value_width
        action = _animation_action_for(obj, shape_keys, actions, "_Morph", channel)
        for component in range(component_count):
            key_index = target_offset + component + 1
            if key_index >= len(shape_keys.key_blocks):
                continue

            key = shape_keys.key_blocks[key_index]
            value_index = 0 if is_partial else component
            path = key.path_from_id("value")
            write_key = _fcurve_write_key(shape_keys, channel, path, 0)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, shape_keys, key.path_from_id("value"), 0, group_name="Shape Keys")
            coords = array("f", [0.0]) * (count * 2)
            for frame_index in range(count):
                coords[frame_index * 2] = start_frame + times[frame_index] * fps
                coords[frame_index * 2 + 1] = values[frame_index * value_width + value_index]

            _write_fcurve_points(
                fcurve,
                coords,
                interpolation,
                times=times,
                fps=fps,
                in_tangents=in_tangents,
                out_tangents=out_tangents,
                value_width=value_width,
                value_index=value_index,
            )

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    _register_actions_frame_range(actions, frame_bounds)
    _stash_animation_actions(actions)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _apply_morph_presets(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    presets = data.morph_presets or []
    shape_keys = obj.data.shape_keys if obj.data else None
    if not presets or not shape_keys or len(shape_keys.key_blocks) <= 1:
        return

    target_count = len(shape_keys.key_blocks) - 1
    written = 0
    for preset in presets:
        name = str(preset.get("name") or f"Preset {written + 1}")
        weights = [float(value) for value in preset.get("weights") or ()]
        if not weights:
            continue

        prefix = f"assetkit_morph_preset_{written}"
        obj[f"{prefix}_name"] = name
        obj[f"{prefix}_weights_json"] = json.dumps(
            weights[:target_count],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        obj[f"{prefix}_target_count"] = min(target_count, len(weights))
        written += 1

    if written:
        obj["assetkit_morph_preset_count"] = written


def _anim_channel_can_use_native_coords(target: int) -> bool:
    return target in {_ANIM_TRANSLATION, _ANIM_ROTATION_QUAT, _ANIM_SCALE}


def _anim_target_path(target: int) -> tuple[str, int]:
    if target == _ANIM_TRANSLATION:
        return "location", 3
    if target == _ANIM_ROTATION_QUAT:
        return "rotation_quaternion", 4
    if target == _ANIM_SCALE:
        return "scale", 3
    return "", 0
