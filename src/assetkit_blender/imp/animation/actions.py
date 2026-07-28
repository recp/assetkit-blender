from __future__ import annotations

import math
import os
from array import array

import bpy

from ..buffers import (
    buffer_view as _buffer_view,
    channel_clip_index as _channel_clip_index,
    channel_clip_name as _channel_clip_name,
    channel_count as _channel_count,
    channel_in_tangents as _channel_in_tangents,
    channel_interpolation as _channel_interpolation,
    channel_out_tangents as _channel_out_tangents,
    channel_times as _channel_times,
)

_INTERPOLATION_LINEAR = 1
_INTERPOLATION_HERMITE = 4
_INTERPOLATION_STEP = 6
_AK_ACTION_CLIP_INDEX_PROP = "assetkit_animation_clip_index"
_AK_ACTION_CLIP_NAME_PROP = "assetkit_animation_clip_name"
_AK_ACTION_CLIP_EXPORT_NAME_PROP = "assetkit_animation_clip_export_name"
_ACTION_CHANNELBAGS: dict[tuple[int, int], tuple[object, object]] = {}
_ACTION_CHANNEL_GROUPS: dict[tuple[int, str], object] = {}
_IMPORT_SHARED_ACTIONS: dict[tuple[int, str, str], bpy.types.Action] = {}
ACTION_FRAME_RANGES: dict[tuple[int, int], tuple[float, float]] = {}
_KEYFRAME_ENUM_VALUES: dict[tuple[str, str], int] = {}
_KEYFRAME_ENUM_ARRAYS: dict[tuple[int, int], array] = {}
_ACTION_SLOTS_SUPPORTED: bool | None = None
_USE_SHARED_ACTION_SLOTS = False
ACTIVE_SCOPE = ""
_IMPORT_ANIMATION_SCOPE_SERIAL = 0


def _new_import_animation_scope(filepath: str) -> str:
    global _IMPORT_ANIMATION_SCOPE_SERIAL

    stem = _safe_action_name(os.path.splitext(os.path.basename(filepath or ""))[0])
    if not stem:
        stem = "AssetKit"
    serial = _IMPORT_ANIMATION_SCOPE_SERIAL
    _IMPORT_ANIMATION_SCOPE_SERIAL = serial + 1
    return f"{stem}_{serial}"


def _action_frame_range(action: bpy.types.Action, owner: bpy.types.ID | None = None) -> tuple[float, float] | None:
    action_ptr = action.as_pointer()
    if owner is not None:
        cached = ACTION_FRAME_RANGES.get(_action_frame_range_key(action, owner))
        if cached is not None:
            return cached

    min_frame: float | None = None
    max_frame: float | None = None
    for (cached_action, _cached_owner), frame_range in ACTION_FRAME_RANGES.items():
        if cached_action != action_ptr:
            continue
        min_frame = frame_range[0] if min_frame is None else min(min_frame, frame_range[0])
        max_frame = frame_range[1] if max_frame is None else max(max_frame, frame_range[1])
    if min_frame is not None and max_frame is not None:
        return min_frame, max_frame

    for attr in ("curve_frame_range", "frame_range"):
        value = getattr(action, attr, None)
        if value is None:
            continue
        try:
            start = float(value[0])
            end = float(value[1])
        except (TypeError, ValueError, IndexError):
            continue
        if end > start:
            return start, end

    min_frame: float | None = None
    max_frame: float | None = None
    for fcurve in _iter_action_fcurves(action):
        for key in fcurve.keyframe_points:
            frame = float(key.co.x)
            min_frame = frame if min_frame is None else min(min_frame, frame)
            max_frame = frame if max_frame is None else max(max_frame, frame)

    if min_frame is not None and max_frame is not None:
        return min_frame, max_frame

    return None


def _iter_action_fcurves(action: bpy.types.Action):
    fcurves = getattr(action, "fcurves", None)
    if fcurves:
        yield from fcurves
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except Exception:
                    continue
                yield from getattr(channelbag, "fcurves", []) or []


def _channelbag_for_fcurve(action: bpy.types.Action, fcurve: bpy.types.FCurve):
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except Exception:
                    continue
                for candidate in getattr(channelbag, "fcurves", []) or []:
                    if candidate == fcurve:
                        return channelbag
    return None


def _set_fcurve_group(fcurve: bpy.types.FCurve, channelbag, group_name: str) -> None:
    if not group_name or not channelbag:
        return
    try:
        current = getattr(fcurve, "group", None)
        if current is not None and getattr(current, "name", None) == group_name:
            return
    except Exception:
        pass
    try:
        fcurve.group = _channelbag_group(channelbag, group_name)
    except Exception:
        pass


def _new_channelbag_fcurve(channelbag, data_path: str, index: int | None, group_name: str):
    try:
        if index is None:
            return channelbag.fcurves.new(data_path=data_path, group_name=group_name)
        return channelbag.fcurves.new(data_path=data_path, index=index, group_name=group_name)
    except TypeError:
        if index is None:
            fcurve = channelbag.fcurves.new(data_path=data_path)
        else:
            fcurve = channelbag.fcurves.new(data_path=data_path, index=index)
        _set_fcurve_group(fcurve, channelbag, group_name)
        return fcurve


def _channelbag_group(channelbag, group_name: str):
    key = (id(channelbag), group_name)
    group = _ACTION_CHANNEL_GROUPS.get(key)
    if group is not None:
        return group
    if group_name not in channelbag.groups:
        group = channelbag.groups.new(group_name)
    else:
        group = channelbag.groups[group_name]
    _ACTION_CHANNEL_GROUPS[key] = group
    return group


def _reset_action_cache() -> None:
    _ACTION_CHANNELBAGS.clear()
    _ACTION_CHANNEL_GROUPS.clear()
    _IMPORT_SHARED_ACTIONS.clear()
    ACTION_FRAME_RANGES.clear()


def _merge_frame_bounds(
    bounds: tuple[float, float] | None,
    start: float,
    end: float,
) -> tuple[float, float]:
    if bounds is None:
        return float(start), float(end)
    return min(bounds[0], float(start)), max(bounds[1], float(end))


def _action_frame_range_key(action: bpy.types.Action, owner: bpy.types.ID | None = None) -> tuple[int, int]:
    return action.as_pointer(), owner.as_pointer() if owner is not None else 0


def _channel_frame_bounds(
    channel: object,
    fps: float,
    start_frame: float = 0.0,
) -> tuple[float, float] | None:
    count = _channel_count(channel)
    times = _buffer_view(_channel_times(channel), "f")
    if count <= 0 or times is None:
        return None
    last = min(count, len(times)) - 1
    if last < 0:
        return None
    start = float(start_frame) + float(times[0]) * fps
    end = float(start_frame) + float(times[last]) * fps
    return start, end


def _register_action_frame_range(
    action: bpy.types.Action,
    start: float,
    end: float,
    owner: bpy.types.ID | None = None,
) -> None:
    if end < start:
        return
    key = _action_frame_range_key(action, owner)
    existing = ACTION_FRAME_RANGES.get(key)
    ACTION_FRAME_RANGES[key] = _merge_frame_bounds(existing, start, end)


def _register_actions_frame_range(
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    bounds: tuple[float, float] | None,
) -> None:
    if not actions or bounds is None:
        return
    for owner, action in actions.values():
        _register_action_frame_range(action, bounds[0], bounds[1], owner)


def _animation_action_for(
    obj: bpy.types.Object,
    owner: bpy.types.ID,
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    suffix: str,
    channel: dict | None = None,
) -> bpy.types.Action:
    clip_index, clip_name = _channel_action_clip(channel)
    key = (owner.as_pointer(), clip_index, suffix)
    cached = actions.get(key)
    if cached:
        action = cached[1]
        _tag_animation_action_clip(action, channel)
        return action

    owner.animation_data_create()
    action = _shared_animation_action(suffix, channel)
    if action is None:
        action = _new_animation_action(_animation_action_name(obj.name, suffix, channel))
    _tag_animation_action_clip(action, channel)
    if owner.animation_data.action is None or clip_index == 0:
        owner.animation_data.action = action
        slot = _ensure_action_channelbag(action, owner)[0]
        _set_animation_data_slot(owner, slot)
    actions[key] = (owner, action)
    return action


def _shared_animation_action(suffix: str, channel: dict | None) -> bpy.types.Action | None:
    global _ACTION_SLOTS_SUPPORTED
    if not _USE_SHARED_ACTION_SLOTS:
        return None
    if _ACTION_SLOTS_SUPPORTED is False:
        return None

    clip_index, clip_name = _channel_action_clip(channel)
    key = (clip_index, clip_name, suffix)
    action = _IMPORT_SHARED_ACTIONS.get(key)
    if action is not None:
        return action

    action = _new_animation_action(_shared_animation_action_name(suffix, channel))
    if getattr(action, "slots", None) is None or getattr(action, "layers", None) is None:
        _ACTION_SLOTS_SUPPORTED = False
        bpy.data.actions.remove(action)
        return None

    _ACTION_SLOTS_SUPPORTED = True
    _IMPORT_SHARED_ACTIONS[key] = action
    return action


def _new_animation_action(name: str) -> bpy.types.Action:
    action = bpy.data.actions.new(name)
    _ensure_action_layer_strip(action)
    return action


def _ensure_action_layer_strip(action: bpy.types.Action):
    layers = getattr(action, "layers", None)
    if layers is None:
        return None

    if len(layers) == 0:
        try:
            layer = layers.new("layer0")
        except TypeError:
            layer = layers.new(name="layer0")
    else:
        layer = layers[0]

    strips = getattr(layer, "strips", None)
    if strips is None:
        return None
    if len(strips) == 0:
        try:
            return strips.new(type="KEYFRAME")
        except TypeError:
            return strips.new("KEYFRAME")
    return strips[0]


def _ensure_action_channelbag(action: bpy.types.Action, owner: bpy.types.ID):
    key = (action.as_pointer(), owner.as_pointer())
    cached = _ACTION_CHANNELBAGS.get(key)
    if cached:
        return cached

    strip = _ensure_action_layer_strip(action)
    slots = getattr(action, "slots", None)
    if strip is None or slots is None:
        return None, None

    slot = None
    for candidate in slots:
        if (
            getattr(candidate, "target_id_type", "") == owner.id_type
            and getattr(candidate, "name_display", getattr(candidate, "name", "")) == owner.name
        ):
            slot = candidate
            break
    if slot is None:
        try:
            slot = slots.new(owner.id_type, owner.name)
        except TypeError:
            slot = slots.new(id_type=owner.id_type, name=owner.name)

    try:
        channelbag = strip.channelbag(slot)
    except Exception:
        channelbag = None
    if channelbag is None:
        try:
            channelbag = strip.channelbags.new(slot)
        except Exception:
            channelbag = None
    if channelbag is None:
        return slot, None

    _ACTION_CHANNELBAGS[key] = (slot, channelbag)
    return slot, channelbag


def _set_animation_data_slot(owner: bpy.types.ID, slot) -> None:
    animation_data = getattr(owner, "animation_data", None)
    if animation_data is None or not hasattr(animation_data, "action_slot"):
        return
    try:
        animation_data.action_slot = slot
    except Exception:
        pass


def _tag_animation_action_clip(action: bpy.types.Action | None, channel: dict | None) -> None:
    if action is None or channel is None:
        return

    clip_index = _channel_clip_index(channel)
    clip_name = _safe_action_name(_channel_clip_name(channel))
    display_name = clip_name or f"Animation_{clip_index}"
    scope = ACTIVE_SCOPE
    export_name = f"{scope}_{display_name}" if scope else display_name
    try:
        action[_AK_ACTION_CLIP_INDEX_PROP] = int(clip_index)
        action[_AK_ACTION_CLIP_NAME_PROP] = display_name
        action[_AK_ACTION_CLIP_EXPORT_NAME_PROP] = export_name[:96]
    except Exception:
        pass


def _animation_action_name(base_name: str, suffix: str, channel: dict | None) -> str:
    clip_index, clip_name = _channel_action_clip(channel)
    if clip_name:
        return f"{base_name}_AssetKit_{clip_name}{suffix}"
    if clip_index:
        return f"{base_name}_AssetKit_Animation_{clip_index}{suffix}"
    return f"{base_name}_AssetKit{suffix}"


def _shared_animation_action_name(suffix: str, channel: dict | None) -> str:
    clip_index, clip_name = _channel_action_clip(channel)
    if clip_name:
        return f"AssetKit_{clip_name}{suffix}"
    if clip_index:
        return f"AssetKit_Animation_{clip_index}{suffix}"
    return f"AssetKit{suffix}"


def _channel_action_clip(channel: dict | None) -> tuple[int, str]:
    clip_index = _channel_clip_index(channel)
    clip_name = _safe_action_name(_channel_clip_name(channel))
    return clip_index, clip_name


def _fcurve_write_key(
    owner: bpy.types.ID,
    channel: dict,
    data_path: str,
    index: int | None,
) -> tuple[int, int, str, int]:
    clip_index, _clip_name = _channel_action_clip(channel)
    return (
        owner.as_pointer(),
        clip_index,
        data_path,
        -1 if index is None else int(index),
    )


def _safe_action_name(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in name.strip())
    return out[:96]


def _stash_animation_actions(actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]]) -> None:
    for owner, action in actions.values():
        if not action or _action_frame_range(action, owner) is None:
            continue
        _stash_animation_action(owner, action)


def _stash_animation_action(owner: bpy.types.ID, action: bpy.types.Action) -> None:
    try:
        owner.animation_data_create()
        tracks = owner.animation_data.nla_tracks
    except Exception:
        return

    for track in tracks:
        if any(strip.action == action for strip in track.strips):
            return

    frame_range = _action_frame_range(action, owner)
    strip_start = frame_range[0] if frame_range is not None else float(bpy.context.scene.frame_start)

    try:
        track = tracks.new(prev=None)
        track.name = action.name
        strip = track.strips.new(action.name, int(math.floor(strip_start)), action)
    except Exception:
        return

    _set_nla_strip_action_slot(strip, action, owner)
    if frame_range is not None:
        start, end = frame_range
        try:
            strip.action_frame_start = start
            strip.action_frame_end = end
            strip.frame_start = start
            strip.frame_end = max(start, end)
        except Exception:
            pass
    track.lock = True
    track.mute = True


def _set_nla_strip_action_slot(strip, action: bpy.types.Action, owner: bpy.types.ID) -> None:
    if not hasattr(strip, "action_slot"):
        return

    slot = _ACTION_CHANNELBAGS.get((action.as_pointer(), owner.as_pointer()), (None, None))[0]
    if slot is not None:
        try:
            strip.action_slot = slot
            return
        except Exception:
            pass

    slot = None
    for candidate in getattr(action, "slots", []):
        if getattr(candidate, "target_id_type", "") == owner.id_type:
            slot = candidate
            break
    if slot is None:
        slots = list(getattr(action, "slots", []))
        slot = slots[0] if slots else None
    if slot is None:
        return

    try:
        strip.action_slot = slot
    except Exception:
        pass


def _ensure_fcurve(
    action: bpy.types.Action,
    obj: bpy.types.ID,
    data_path: str,
    index: int | None,
    group_name: str = "Transform",
):
    slot, channelbag = _ensure_action_channelbag(action, obj)
    if channelbag is not None:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        return _new_channelbag_fcurve(channelbag, data_path, index, group_name)

    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        existing = _find_fcurve(fcurves, data_path, index)
        if existing is not None:
            return existing
        if index is None:
            return fcurves.new(data_path=data_path, action_group=group_name)
        return fcurves.new(data_path=data_path, index=index, action_group=group_name)

    ensure = getattr(action, "fcurve_ensure_for_datablock", None)
    if not ensure:
        raise RuntimeError("Blender Action API does not expose fcurve creation")

    try:
        obj.animation_data_create()
        if obj.animation_data.action != action:
            obj.animation_data.action = action
    except Exception:
        pass

    if index is None:
        fcurve = ensure(obj, data_path, group_name=group_name)
    else:
        fcurve = ensure(obj, data_path, index=index, group_name=group_name)
    if len(fcurve.keyframe_points) == 0:
        return fcurve

    channelbag = _channelbag_for_fcurve(action, fcurve)
    if not channelbag:
        return fcurve
    if index is None:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        fcurve = _new_channelbag_fcurve(channelbag, data_path, None, group_name)
    else:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        fcurve = _new_channelbag_fcurve(channelbag, data_path, index, group_name)
    return fcurve


def _find_fcurve(fcurves, data_path: str, index: int | None):
    try:
        if index is None:
            found = fcurves.find(data_path)
        else:
            found = fcurves.find(data_path, index=index)
        if found is not None:
            return found
    except Exception:
        pass

    for fcurve in fcurves:
        try:
            if fcurve.data_path != data_path:
                continue
            if index is None or int(fcurve.array_index) == int(index):
                return fcurve
        except Exception:
            continue
    return None


def _channel_tangents(channel: dict) -> tuple[object | None, object | None]:
    if _channel_interpolation(channel) != _INTERPOLATION_HERMITE:
        return None, None

    in_tangents = _buffer_view(_channel_in_tangents(channel), "f")
    out_tangents = _buffer_view(_channel_out_tangents(channel), "f")
    if in_tangents is None or out_tangents is None:
        return None, None
    return in_tangents, out_tangents


def _write_fcurve_points(
    fcurve,
    coords,
    interpolation: str,
    *,
    times=None,
    fps: float = 1.0,
    in_tangents=None,
    out_tangents=None,
    value_width: int = 0,
    value_index: int = 0,
    tangent_value=None,
) -> None:
    count = len(coords) // 2
    _clear_fcurve_points(fcurve)
    fcurve.keyframe_points.add(count)
    fcurve.keyframe_points.foreach_set("co", coords)

    use_cubic = (
        interpolation == "BEZIER"
        and times is not None
        and in_tangents is not None
        and out_tangents is not None
        and value_width > 0
        and count > 0
    )

    _foreach_set_keyframe_enum(
        fcurve.keyframe_points,
        "interpolation",
        "BEZIER" if use_cubic else interpolation,
        count,
    )

    if use_cubic:
        _apply_cubic_handles(
            fcurve,
            coords,
            times,
            fps,
            in_tangents,
            out_tangents,
            value_width,
            value_index,
            tangent_value,
        )

    if use_cubic:
        fcurve.update()


def _clear_fcurve_points(fcurve) -> None:
    points = fcurve.keyframe_points
    if not points:
        return
    try:
        points.clear()
        return
    except Exception:
        pass
    while points:
        try:
            points.remove(points[-1], fast=True)
        except TypeError:
            points.remove(points[-1])
        except Exception:
            break


def _foreach_set_keyframe_enum(points, prop: str, value: str, count: int) -> None:
    enum_value = _keyframe_enum_value(prop, value)
    if enum_value is None:
        for point in points:
            setattr(point, prop, value)
        return
    try:
        points.foreach_set(prop, _keyframe_enum_array(enum_value, count))
    except Exception:
        for point in points:
            setattr(point, prop, value)


def _keyframe_enum_array(enum_value: int, count: int) -> array:
    key = (enum_value, count)
    cached = _KEYFRAME_ENUM_ARRAYS.get(key)
    if cached is not None:
        return cached
    typecode = "B" if 0 <= int(enum_value) <= 255 else "i"
    values = array(typecode, [enum_value]) * count
    _KEYFRAME_ENUM_ARRAYS[key] = values
    return values


def _keyframe_enum_value(prop: str, value: str) -> int | None:
    key = (prop, value)
    cached = _KEYFRAME_ENUM_VALUES.get(key)
    if cached is not None:
        return cached
    try:
        enum_value = bpy.types.Keyframe.bl_rna.properties[prop].enum_items[value].value
    except Exception:
        return None
    _KEYFRAME_ENUM_VALUES[key] = enum_value
    return enum_value


def _apply_cubic_handles(
    fcurve,
    coords,
    times,
    fps: float,
    in_tangents,
    out_tangents,
    value_width: int,
    value_index: int,
    tangent_value,
) -> None:
    points = fcurve.keyframe_points
    count = len(points)
    for index, point in enumerate(points):
        frame = coords[index * 2]
        value = coords[index * 2 + 1]
        point.handle_left_type = "FREE"
        point.handle_right_type = "FREE"

        if index > 0:
            dt = max(0.0, float(times[index] - times[index - 1]))
            tangent = _output_tangent(in_tangents[index * value_width + value_index], tangent_value)
            point.handle_left = (frame - (dt * fps) / 3.0, value - (tangent * dt) / 3.0)
        else:
            point.handle_left = (frame, value)

        if index + 1 < count:
            dt = max(0.0, float(times[index + 1] - times[index]))
            tangent = _output_tangent(out_tangents[index * value_width + value_index], tangent_value)
            point.handle_right = (frame + (dt * fps) / 3.0, value + (tangent * dt) / 3.0)
        else:
            point.handle_right = (frame, value)


def _output_tangent(value: float, tangent_value) -> float:
    if tangent_value is None:
        return float(value)
    converted = tangent_value(float(value))
    return float(value) if converted is None else float(converted)


def _blender_interpolation(interpolation: int) -> str:
    if interpolation == _INTERPOLATION_STEP:
        return "CONSTANT"
    if interpolation == _INTERPOLATION_HERMITE:
        return "BEZIER"
    if interpolation == _INTERPOLATION_LINEAR:
        return "LINEAR"
    return "LINEAR"
