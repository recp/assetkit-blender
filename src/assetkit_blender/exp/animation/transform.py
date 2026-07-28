from __future__ import annotations

import math
from array import array

import bpy
import mathutils

from ...assetkit import _native_module
from ...enums import (
    AK_INTERPOLATION_LINEAR,
    AK_INTERPOLATION_STEP,
    AK_TARGET_POSITION,
    AK_TARGET_QUAT,
    AK_TARGET_SCALE,
    AKB_ANIM_VISIBILITY,
)

from ..common import _matrix_values
from ..visibility import (
    _object_uses_parent_source_visibility,
    _object_visibility_extra_value,
)
from .common import (
    _iter_action_fcurves,
    animation_action_slot,
    animation_channel_with_clip,
    animation_channels_with_clip,
)

_ANIMATION_TIMING_SCENE = "SCENE"
_ANIMATION_TIMING_CLIP = "CLIP"

_TRANSFORM_ANIMATION_PATHS = {
    "location",
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
    "delta_location",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
    "delta_scale",
}

_LOCATION_ANIMATION_PATHS = {"location", "delta_location"}
_ROTATION_ANIMATION_PATHS = {
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
}
_SCALE_ANIMATION_PATHS = {"scale", "delta_scale"}
_VISIBILITY_ANIMATION_PATHS = {"hide_viewport", "hide_render"}
_ANIMATION_FRAME_EPSILON = 1.0e-4
_BONE_PROP_LOCATION = 0
_BONE_PROP_ROTATION_AXIS_ANGLE = 1
_BONE_PROP_ROTATION_EULER = 2
_BONE_PROP_ROTATION_QUATERNION = 3
_BONE_PROP_SCALE = 4
_BONE_ROTATION_PATH_INDICES = (
    _BONE_PROP_ROTATION_AXIS_ANGLE,
    _BONE_PROP_ROTATION_EULER,
    _BONE_PROP_ROTATION_QUATERNION,
)
_BONE_TRANSFORM_PROPERTIES = (
    "location",
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
)
_POSE_PLAN_NAME = 0
_POSE_PLAN_PATHS = 1
_POSE_PLAN_FRAMES = 2
_POSE_PLAN_LOC_CURVES = 3
_POSE_PLAN_QUAT_CURVES = 4
_POSE_PLAN_SCALE_CURVES = 5
_POSE_PLAN_LOC_DEFAULTS = 6
_POSE_PLAN_QUAT_DEFAULTS = 7
_POSE_PLAN_SCALE_DEFAULTS = 8
_POSE_PLAN_LOC_INTERP = 9
_POSE_PLAN_ROT_INTERP = 10
_POSE_PLAN_SCALE_INTERP = 11
_POSE_PLAN_REST_MATRIX = 12
_POSE_PLAN_TIMES = 13
_POSE_PLAN_TRANSLATIONS = 14
_POSE_PLAN_ROTATIONS = 15
_POSE_PLAN_SCALES = 16
_POSE_PLAN_PREVIOUS_QUAT = 17
_POSE_PLAN_VALID = 18


def _collect_transform_animations(
    context: bpy.types.Context,
    objects: set[bpy.types.Object],
) -> dict[bpy.types.Object, tuple]:
    scene = context.scene
    frame = scene.frame_current
    subframe = scene.frame_subframe
    out: dict[bpy.types.Object, tuple] = {}
    changed_frame = False

    try:
        for obj in objects:
            payload, changed = _object_transform_animation(context, obj, objects)
            changed_frame = changed_frame or changed
            if payload:
                out[obj] = payload
    finally:
        if changed_frame:
            scene.frame_set(frame, subframe=subframe)

    return out


def _object_world_matrix(obj: bpy.types.Object, depsgraph) -> object:
    if getattr(obj, "constraints", None):
        return obj.evaluated_get(depsgraph).matrix_world.copy()
    return obj.matrix_world.copy()


def _collect_bone_animations(
    context: bpy.types.Context,
    armatures: set[bpy.types.Object],
) -> dict[tuple[bpy.types.Object, str], tuple]:
    scene = context.scene
    frame = scene.frame_current
    subframe = scene.frame_subframe
    out: dict[tuple[bpy.types.Object, str], tuple] = {}
    changed_frame = False

    try:
        for armature in armatures:
            animation_data = armature.animation_data
            action = animation_data.action if animation_data else None
            fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(animation_data))) if action else ()
            pose = getattr(armature, "pose", None)
            if pose is None:
                continue
            plans = _pose_bone_animation_plans(armature, action, fcurves)
            if not plans:
                continue
            payloads, changed = _sample_pose_bone_animation_plans(context, armature, action, fcurves, plans)
            changed_frame = changed_frame or changed
            out.update(payloads)
    finally:
        if changed_frame:
            scene.frame_set(frame, subframe=subframe)

    return out


def _normalize_scene_animation_payload_times(
    object_payloads: dict[bpy.types.Object, tuple],
    bone_payloads: dict[tuple[bpy.types.Object, str], tuple],
) -> tuple[dict[bpy.types.Object, tuple], dict[tuple[bpy.types.Object, str], tuple]]:
    min_by_clip: dict[tuple[str, object], float] = {}
    maps = (object_payloads, bone_payloads)

    for payload_map in maps:
        for payload in payload_map.values():
            for channel in payload or ():
                key = _animation_channel_clip_key(channel, payload)
                first = _animation_channel_first_time(channel)
                if first is None:
                    continue
                current = min_by_clip.get(key)
                if current is None or first < current:
                    min_by_clip[key] = first

    offsets = {
        key: value
        for key, value in min_by_clip.items()
        if abs(value) > _ANIMATION_FRAME_EPSILON
    }
    if not offsets:
        return object_payloads, bone_payloads

    return (
        {
            key: _shift_animation_payload_times(payload, offsets)
            for key, payload in object_payloads.items()
        },
        {
            key: _shift_animation_payload_times(payload, offsets)
            for key, payload in bone_payloads.items()
        },
    )


def _animation_channel_clip_key(channel: tuple, payload: tuple) -> tuple[str, object]:
    if len(channel) >= 7 and channel[6]:
        return "clip", str(channel[6])
    return "payload", id(payload)


def _animation_channel_time_view(channel: tuple):
    if len(channel) < 4:
        return None
    try:
        count = int(channel[3])
    except Exception:
        return None
    if count <= 0:
        return None
    try:
        view = memoryview(channel[1])
    except TypeError:
        return None
    if view.nbytes < count * 4:
        return None
    if view.format != "f" or view.itemsize != 4:
        try:
            view = view.cast("f")
        except TypeError:
            return None
    if len(view) < count:
        return None
    return view, count


def _animation_channel_first_time(channel: tuple) -> float | None:
    parsed = _animation_channel_time_view(channel)
    if parsed is None:
        return None
    view, _count = parsed
    return float(view[0])


def _shift_animation_payload_times(payload: tuple, offsets: dict[tuple[str, object], float]) -> tuple:
    changed = False
    shifted = []
    for channel in payload or ():
        offset = offsets.get(_animation_channel_clip_key(channel, payload), 0.0)
        if abs(offset) <= _ANIMATION_FRAME_EPSILON:
            shifted.append(channel)
            continue
        parsed = _animation_channel_time_view(channel)
        if parsed is None:
            shifted.append(channel)
            continue
        view, count = parsed
        times = array("f", (float(view[index]) - offset for index in range(count)))
        shifted.append((channel[0], times, *channel[2:]))
        changed = True
    return tuple(shifted) if changed else payload


def _pose_bone_animation_plans(
    armature: bpy.types.Object,
    action: bpy.types.Action | None,
    fcurves: tuple,
) -> list[list]:
    pose = getattr(armature, "pose", None)
    if pose is None:
        return []

    plans: list[list] = []
    fcurves_by_path = _fcurves_by_data_path(fcurves)
    curve_frame_cache: dict[int, tuple[float, ...]] = {}
    expanded_frame_cache: dict[tuple[float, ...], tuple[float, ...]] = {}
    for pose_bone in getattr(pose, "bones", []) or []:
        paths = _pose_bone_paths(armature, pose_bone.name)
        if not paths:
            continue

        constraints = getattr(pose_bone, "constraints", None)
        relevant_paths = tuple(path for path in paths if path)
        rotation_paths = tuple(
            paths[index]
            for index in _BONE_ROTATION_PATH_INDICES
            if paths[index]
        )
        relevant_curves = _fcurves_for_paths_index(fcurves_by_path, relevant_paths)
        has_fcurves = bool(relevant_curves)
        if not has_fcurves and (constraints is None or len(constraints) == 0):
            continue

        frames = (
            _action_keyframes_for_curve_items(relevant_curves, curve_frame_cache)
            if action is not None and has_fcurves
            else ()
        )
        if action is not None and has_fcurves:
            if _transform_curve_items_need_sampling(relevant_curves, rotation_paths):
                expanded = expanded_frame_cache.get(frames)
                if expanded is None:
                    expanded = _expanded_integer_sample_frames(frames)
                    expanded_frame_cache[frames] = expanded
                frames = expanded
        if len(frames) < 2:
            frames = _pose_bone_constraint_keyframes(pose_bone)
        if len(frames) < 2:
            continue

        loc_curves = tuple(_fcurves_for_path_index(fcurves_by_path, paths[_BONE_PROP_LOCATION], 3))
        quat_curves = tuple(
            _fcurves_for_path_index(fcurves_by_path, paths[_BONE_PROP_ROTATION_QUATERNION], 4)
        )
        scale_curves = tuple(_fcurves_for_path_index(fcurves_by_path, paths[_BONE_PROP_SCALE], 3))
        loc_defaults = (float(pose_bone.location.x), float(pose_bone.location.y), float(pose_bone.location.z))
        quat_defaults = tuple(float(value) for value in pose_bone.rotation_quaternion)
        scale_defaults = (float(pose_bone.scale.x), float(pose_bone.scale.y), float(pose_bone.scale.z))
        loc_interp = _curves_interpolation(loc_curves)
        rot_interp = _curves_interpolation(_fcurves_for_paths_index(fcurves_by_path, rotation_paths))
        scale_interp = _curves_interpolation(scale_curves)
        bone = pose_bone.bone
        rest_matrix = bone.parent.matrix_local.inverted_safe() @ bone.matrix_local if bone.parent else bone.matrix_local

        plans.append([
            pose_bone.name,
            paths,
            tuple(frames),
            loc_curves,
            quat_curves,
            scale_curves,
            loc_defaults,
            quat_defaults,
            scale_defaults,
            loc_interp,
            rot_interp,
            scale_interp,
            _matrix_values(rest_matrix),
            array("f"),
            array("f"),
            array("f"),
            array("f"),
            None,
            True,
        ])
    return plans


def _sample_pose_bone_animation_plans(
    context: bpy.types.Context,
    armature: bpy.types.Object,
    action: bpy.types.Action | None,
    fcurves: tuple,
    plans: list[list],
) -> tuple[dict[tuple[bpy.types.Object, str], tuple], bool]:
    direct = _native_pose_bone_animation_payloads(armature, action, fcurves, plans)
    if direct is not False:
        return direct, False

    scene = context.scene
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    frame_plans: dict[float, list[list]] = {}
    for plan in plans:
        for frame in plan[_POSE_PLAN_FRAMES]:
            frame_plans.setdefault(float(frame), []).append(plan)

    changed_frame = False
    for frame in sorted(frame_plans):
        changed_frame = _set_scene_frame(scene, frame) or changed_frame
        depsgraph = context.evaluated_depsgraph_get()
        armature_eval = armature.evaluated_get(depsgraph)
        pose = armature_eval.pose
        if pose is None:
            for plan in frame_plans[frame]:
                plan[_POSE_PLAN_VALID] = False
            continue

        for plan in frame_plans[frame]:
            pose_bone = pose.bones.get(plan[_POSE_PLAN_NAME])
            if pose_bone is None:
                plan[_POSE_PLAN_VALID] = False
                continue

            matrix = _pose_bone_local_matrix(pose_bone)
            loc, rot, scale = matrix.decompose()
            quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
            previous_quat = plan[_POSE_PLAN_PREVIOUS_QUAT]
            if previous_quat is not None and _quat_dot(previous_quat, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            plan[_POSE_PLAN_PREVIOUS_QUAT] = quat

            plan[_POSE_PLAN_TIMES].append(float(frame) / fps)
            plan[_POSE_PLAN_TRANSLATIONS].extend((float(loc.x), float(loc.y), float(loc.z)))
            plan[_POSE_PLAN_ROTATIONS].extend(quat)
            plan[_POSE_PLAN_SCALES].extend((float(scale.x), float(scale.y), float(scale.z)))

    out: dict[tuple[bpy.types.Object, str], tuple] = {}
    for plan in plans:
        if not plan[_POSE_PLAN_VALID]:
            continue
        times = plan[_POSE_PLAN_TIMES]
        count = len(times)
        if count < 2:
            continue

        channels = []
        translations = plan[_POSE_PLAN_TRANSLATIONS]
        rotations = plan[_POSE_PLAN_ROTATIONS]
        scales = plan[_POSE_PLAN_SCALES]
        if _float_samples_changed(translations, 3):
            channels.append((AK_TARGET_POSITION, times, translations, count, plan[_POSE_PLAN_LOC_INTERP]))
        if _float_samples_changed(rotations, 4):
            channels.append((AK_TARGET_QUAT, times, rotations, count, plan[_POSE_PLAN_ROT_INTERP]))
        if _float_samples_changed(scales, 3):
            channels.append((AK_TARGET_SCALE, times, scales, count, plan[_POSE_PLAN_SCALE_INTERP]))
        if channels:
            out[(armature, plan[_POSE_PLAN_NAME])] = animation_channels_with_clip(channels, action)

    return out, changed_frame


def _native_pose_bone_animation_payloads(
    armature: bpy.types.Object,
    action: bpy.types.Action | None,
    fcurves: tuple,
    plans: list[list],
):
    module = _native_module()
    if module is None:
        return False
    helper = getattr(module, "export_pose_bone_anim_channels", None)
    if helper is None:
        return False

    out: dict[tuple[bpy.types.Object, str], tuple] = {}
    frame_values_cache: dict[tuple[float, ...], array] = {}
    fps = float(bpy.context.scene.render.fps) / float(bpy.context.scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    for plan in plans:
        paths = plan[_POSE_PLAN_PATHS]
        if not any(curve is not None for curve in plan[_POSE_PLAN_QUAT_CURVES]):
            return False
        euler_path = paths[_BONE_PROP_ROTATION_EULER]
        axis_path = paths[_BONE_PROP_ROTATION_AXIS_ANGLE]
        if any(
            fcurve.data_path == euler_path or fcurve.data_path == axis_path
            for fcurve in fcurves
        ):
            return False
        if any(
            curve is not None and getattr(curve, "keyframe_points", None) is None
            for curve in plan[_POSE_PLAN_LOC_CURVES] + plan[_POSE_PLAN_QUAT_CURVES] + plan[_POSE_PLAN_SCALE_CURVES]
        ):
            return False
        frames = plan[_POSE_PLAN_FRAMES]
        frame_values = frame_values_cache.get(frames)
        if frame_values is None:
            frame_values = array("f", frames)
            frame_values_cache[frames] = frame_values
        try:
            channels = helper(
                plan[_POSE_PLAN_REST_MATRIX],
                frame_values,
                plan[_POSE_PLAN_LOC_CURVES],
                plan[_POSE_PLAN_QUAT_CURVES],
                plan[_POSE_PLAN_SCALE_CURVES],
                plan[_POSE_PLAN_LOC_DEFAULTS],
                plan[_POSE_PLAN_QUAT_DEFAULTS],
                plan[_POSE_PLAN_SCALE_DEFAULTS],
                fps,
                int(plan[_POSE_PLAN_LOC_INTERP]),
                int(plan[_POSE_PLAN_ROT_INTERP]),
                int(plan[_POSE_PLAN_SCALE_INTERP]),
            )
        except Exception:
            return False
        if channels is False:
            return False
        if channels:
            out[(armature, plan[_POSE_PLAN_NAME])] = animation_channels_with_clip(tuple(channels), action)
    return out


def _object_transform_animation(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    included: set[bpy.types.Object],
) -> tuple[tuple | None, bool]:
    animation_data = obj.animation_data
    action = animation_data.action if animation_data else None
    if action is None:
        return None, False

    fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(animation_data)))
    if not fcurves:
        return None, False

    parent = obj.parent if obj.parent in included else None
    sample_transform = _transform_fcurves_need_sampling(fcurves, _BONE_TRANSFORM_PROPERTIES)
    visibility_channel = _object_visibility_animation_channel(context.scene, obj, fcurves)
    direct = None
    direct_allowed = parent is obj.parent and len(getattr(obj, "constraints", []) or ()) == 0
    if direct_allowed:
        direct = _object_transform_animation_direct(context, obj, action, fcurves)
        if direct == ():
            return (
                (animation_channel_with_clip(visibility_channel, action),)
                if visibility_channel else None
            ), False
    direct = (
        direct
        if direct_allowed and not sample_transform
        else None
    )
    if direct is not None:
        channels = list(direct)
        if visibility_channel:
            channels.append(visibility_channel)
        return (animation_channels_with_clip(channels, action) if channels else None), False

    frames = _action_transform_keyframes(action, fcurves)
    if sample_transform:
        frames = _expanded_integer_sample_frames(frames)
    if len(frames) < 2:
        return (
            (animation_channel_with_clip(visibility_channel, action),)
            if visibility_channel else None
        ), False

    scene = context.scene
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    times = array("f")
    translations = array("f")
    rotations = array("f")
    scales = array("f")
    previous_quat: tuple[float, float, float, float] | None = None
    changed_frame = False

    for frame in frames:
        changed_frame = _set_scene_frame(scene, frame) or changed_frame
        depsgraph = context.evaluated_depsgraph_get()
        matrix = _evaluated_local_matrix(obj, parent, depsgraph)
        loc, rot, scale = matrix.decompose()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous_quat is not None and _quat_dot(previous_quat, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous_quat = quat

        times.append(float(frame) / fps)
        translations.extend((float(loc.x), float(loc.y), float(loc.z)))
        rotations.extend(quat)
        scales.extend((float(scale.x), float(scale.y), float(scale.z)))

    count = len(times)
    if count < 2:
        return None

    channels = []
    if _float_samples_changed(translations, 3):
        channels.append((
            AK_TARGET_POSITION,
            times,
            translations,
            count,
            _action_interpolation(action, _LOCATION_ANIMATION_PATHS, fcurves),
        ))
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times,
            rotations,
            count,
            _action_interpolation(action, _ROTATION_ANIMATION_PATHS, fcurves),
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times,
            scales,
            count,
            _action_interpolation(action, _SCALE_ANIMATION_PATHS, fcurves),
        ))
    if visibility_channel:
        channels.append(visibility_channel)

    return (animation_channels_with_clip(channels, action) if channels else None), changed_frame


def _pose_bone_transform_animation(
    context: bpy.types.Context,
    armature: bpy.types.Object,
    bone_name: str,
    action: bpy.types.Action | None,
    fcurves: tuple | None = None,
) -> tuple[tuple | None, bool]:
    paths = _pose_bone_paths(armature, bone_name)
    if not paths:
        return None, False

    pose = getattr(armature, "pose", None)
    pose_bone = pose.bones.get(bone_name) if pose else None
    if fcurves is None:
        fcurves = (
            tuple(_iter_action_fcurves(action, animation_action_slot(getattr(armature, "animation_data", None))))
            if action is not None else ()
        )
    # Pose-bone fcurves store deltas over the rest pose, while exported node
    # channels need absolute local transforms. Sample the evaluated matrix so
    # rest rotations and imported axis wrappers are preserved.
    direct = None
    if direct is not None:
        return (direct if direct else None), False

    frames = (
        _action_keyframes_for_paths(action, tuple(path for path in paths if path), fcurves)
        if action is not None and fcurves
        else ()
    )
    if action is not None and fcurves and _transform_fcurves_need_sampling(fcurves, paths):
        frames = _expanded_integer_sample_frames(frames)
    if len(frames) < 2 and pose_bone is not None:
        frames = _pose_bone_constraint_keyframes(pose_bone)
    if len(frames) < 2:
        return None, False

    scene = context.scene
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    times = array("f")
    translations = array("f")
    rotations = array("f")
    scales = array("f")
    previous_quat: tuple[float, float, float, float] | None = None
    changed_frame = False

    for frame in frames:
        changed_frame = _set_scene_frame(scene, frame) or changed_frame
        depsgraph = context.evaluated_depsgraph_get()
        armature_eval = armature.evaluated_get(depsgraph)
        pose_bone = armature_eval.pose.bones.get(bone_name) if armature_eval.pose else None
        if pose_bone is None:
            return None, changed_frame

        matrix = _pose_bone_local_matrix(pose_bone)
        loc, rot, scale = matrix.decompose()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous_quat is not None and _quat_dot(previous_quat, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous_quat = quat

        times.append(float(frame) / fps)
        translations.extend((float(loc.x), float(loc.y), float(loc.z)))
        rotations.extend(quat)
        scales.extend((float(scale.x), float(scale.y), float(scale.z)))

    count = len(times)
    if count < 2:
        return None

    channels = []
    loc_paths = (paths[_BONE_PROP_LOCATION],) if paths[_BONE_PROP_LOCATION] else ()
    rot_paths = tuple(paths[index] for index in _BONE_ROTATION_PATH_INDICES if paths[index])
    scale_paths = (paths[_BONE_PROP_SCALE],) if paths[_BONE_PROP_SCALE] else ()
    loc_interp = (
        _action_interpolation(action, loc_paths, fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    rot_interp = (
        _action_interpolation(action, rot_paths, fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    scale_interp = (
        _action_interpolation(action, scale_paths, fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    if _float_samples_changed(translations, 3):
        channels.append((
            AK_TARGET_POSITION,
            times,
            translations,
            count,
            loc_interp,
        ))
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times,
            rotations,
            count,
            rot_interp,
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times,
            scales,
            count,
            scale_interp,
        ))

    return (animation_channels_with_clip(channels, action) if channels else None), changed_frame


def _object_transform_animation_direct(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    action: bpy.types.Action,
    fcurves: tuple | None = None,
) -> tuple | None:
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(getattr(obj, "animation_data", None))))
    if not fcurves:
        return None
    if getattr(obj, "constraints", None):
        return None
    if any(fcurve.data_path in _TRANSFORM_ANIMATION_PATHS and fcurve.data_path.startswith("delta_")
           for fcurve in fcurves):
        return None

    defaults = _object_transform_defaults(obj)
    return _transform_animation_direct(
        context.scene,
        action,
        fcurves,
        _BONE_TRANSFORM_PROPERTIES,
        defaults,
        getattr(obj, "rotation_mode", "XYZ"),
    )


def _object_visibility_animation_channel(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    fcurves: tuple,
) -> tuple | None:
    if _object_uses_parent_source_visibility(obj):
        return None

    viewport_curve = _scalar_fcurve_for_path(fcurves, "hide_viewport")
    render_curve = _scalar_fcurve_for_path(fcurves, "hide_render")
    if viewport_curve is None and render_curve is None:
        return None

    frames = _fcurve_keyframes([viewport_curve, render_curve])
    if len(frames) < 2:
        return None

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    extra_visible = _object_visibility_extra_value(obj)
    if extra_visible is not None:
        default_viewport = 0.0 if extra_visible else 1.0
        default_render = default_viewport
    else:
        default_viewport = 1.0 if bool(getattr(obj, "hide_viewport", False)) else 0.0
        default_render = 1.0 if bool(getattr(obj, "hide_render", False)) else 0.0
    times = array("f")
    values = array("B")
    for frame in frames:
        hidden_viewport = (
            float(viewport_curve.evaluate(frame)) if viewport_curve is not None else default_viewport
        ) >= 0.5
        hidden_render = (
            float(render_curve.evaluate(frame)) if render_curve is not None else default_render
        ) >= 0.5
        times.append(float(frame) / fps)
        values.append(0 if hidden_viewport or hidden_render else 1)

    if not _float_samples_changed(values, 1):
        return None

    return (
        AKB_ANIM_VISIBILITY,
        times,
        values,
        len(times),
        AK_INTERPOLATION_STEP,
    )


def _pose_bone_transform_animation_direct(
    context: bpy.types.Context,
    pose_bone,
    action: bpy.types.Action,
    paths: tuple[str, ...],
    fcurves: tuple | None = None,
) -> tuple | None:
    if pose_bone is None:
        return None
    if getattr(pose_bone, "constraints", None):
        return None
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action))
    if not fcurves:
        return None
    defaults = _pose_bone_transform_defaults(pose_bone)
    return _transform_animation_direct(context.scene, action, fcurves, paths, defaults, getattr(pose_bone, "rotation_mode", "XYZ"))


def _transform_animation_direct(
    scene: bpy.types.Scene,
    action: bpy.types.Action,
    fcurves: tuple,
    paths: tuple[str, ...],
    defaults: tuple[tuple[float, ...], ...],
    rotation_mode: str,
) -> tuple | None:
    relevant_paths = tuple(path for path in paths if path)
    if not any(fcurve.data_path in relevant_paths for fcurve in fcurves):
        return None

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    channels = []
    location_path = paths[_BONE_PROP_LOCATION]
    if location_path:
        channel = _direct_vec_channel(
            action,
            fcurves,
            location_path,
            defaults[_BONE_PROP_LOCATION],
            3,
            fps,
            AK_TARGET_POSITION,
        )
        if channel:
            channels.append(channel)

    rotation_channel = _direct_rotation_channel(
        action,
        fcurves,
        paths,
        defaults,
        rotation_mode,
        fps,
    )
    if rotation_channel:
        channels.append(rotation_channel)

    scale_path = paths[_BONE_PROP_SCALE]
    if scale_path:
        channel = _direct_vec_channel(
            action,
            fcurves,
            scale_path,
            defaults[_BONE_PROP_SCALE],
            3,
            fps,
            AK_TARGET_SCALE,
        )
        if channel:
            channels.append(channel)

    return tuple(channels) if channels else ()


def _direct_vec_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, ...],
    width: int,
    fps: float,
    target: int,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, width)
    native = _native_aligned_anim_channel(target, tuple(curves), defaults, fps, 0)
    if native is not False:
        return native

    aligned = _aligned_keyframe_values(curves, defaults, width)
    if aligned is not None:
        frames, values = aligned
        if len(frames) < 2 or not _float_samples_changed(values, width):
            return None
        times = array("f", (float(frame) / fps for frame in frames))
        return (
            target,
            times,
            values,
            len(times),
            _curves_interpolation(curves),
        )

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    for frame in frames:
        times.append(float(frame) / fps)
        for component in range(width):
            curve = curves[component]
            values.append(float(curve.evaluate(frame)) if curve is not None else defaults[component])

    if not _float_samples_changed(values, width):
        return None

    return (
        target,
        times,
        values,
        len(times),
        _curves_interpolation(curves),
    )


def _direct_rotation_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    paths: tuple[str, ...],
    defaults: tuple[tuple[float, ...], ...],
    rotation_mode: str,
    fps: float,
) -> tuple | None:
    quat_path = paths[_BONE_PROP_ROTATION_QUATERNION]
    euler_path = paths[_BONE_PROP_ROTATION_EULER]
    axis_path = paths[_BONE_PROP_ROTATION_AXIS_ANGLE]

    if quat_path and any(curve.data_path == quat_path for curve in fcurves):
        return _direct_quat_channel(
            action,
            fcurves,
            quat_path,
            defaults[_BONE_PROP_ROTATION_QUATERNION],
            fps,
        )
    if euler_path and any(curve.data_path == euler_path for curve in fcurves):
        return _direct_euler_channel(
            action,
            fcurves,
            euler_path,
            defaults[_BONE_PROP_ROTATION_EULER],
            rotation_mode,
            fps,
        )
    if axis_path and any(curve.data_path == axis_path for curve in fcurves):
        return _direct_axis_angle_channel(
            action,
            fcurves,
            axis_path,
            defaults[_BONE_PROP_ROTATION_AXIS_ANGLE],
            fps,
        )
    return None


def _direct_quat_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float, float],
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 4)
    native = _native_aligned_anim_channel(AK_TARGET_QUAT, tuple(curves), defaults, fps, 1)
    if native is not False:
        return native

    aligned = _aligned_keyframe_values(curves, defaults, 4)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        for index, frame in enumerate(frames):
            offset = index * 4
            quat = (
                raw_values[offset + 1],
                raw_values[offset + 2],
                raw_values[offset + 3],
                raw_values[offset],
            )
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    for frame in frames:
        raw = [
            float(curves[i].evaluate(frame)) if curves[i] is not None else defaults[i]
            for i in range(4)
        ]
        quat = (raw[1], raw[2], raw[3], raw[0])
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))


def _direct_euler_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float],
    rotation_mode: str,
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 3)
    aligned = _aligned_keyframe_values(curves, defaults, 3)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        order = rotation_mode if rotation_mode in {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"} else "XYZ"
        for index, frame in enumerate(frames):
            offset = index * 3
            euler = mathutils.Euler((
                raw_values[offset],
                raw_values[offset + 1],
                raw_values[offset + 2],
            ), order)
            rot = euler.to_quaternion()
            quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    order = rotation_mode if rotation_mode in {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"} else "XYZ"
    for frame in frames:
        euler = mathutils.Euler((
            float(curves[0].evaluate(frame)) if curves[0] is not None else defaults[0],
            float(curves[1].evaluate(frame)) if curves[1] is not None else defaults[1],
            float(curves[2].evaluate(frame)) if curves[2] is not None else defaults[2],
        ), order)
        rot = euler.to_quaternion()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))


def _direct_axis_angle_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float, float],
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 4)
    aligned = _aligned_keyframe_values(curves, defaults, 4)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        for index, frame in enumerate(frames):
            offset = index * 4
            angle = raw_values[offset]
            axis = mathutils.Vector((
                raw_values[offset + 1],
                raw_values[offset + 2],
                raw_values[offset + 3],
            ))
            if axis.length_squared <= 1.0e-12:
                axis = mathutils.Vector((0.0, 0.0, 1.0))
            rot = mathutils.Quaternion(axis.normalized(), angle)
            quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    for frame in frames:
        angle = float(curves[0].evaluate(frame)) if curves[0] is not None else defaults[0]
        axis = mathutils.Vector((
            float(curves[1].evaluate(frame)) if curves[1] is not None else defaults[1],
            float(curves[2].evaluate(frame)) if curves[2] is not None else defaults[2],
            float(curves[3].evaluate(frame)) if curves[3] is not None else defaults[3],
        ))
        if axis.length_squared <= 1.0e-12:
            axis = mathutils.Vector((0.0, 0.0, 1.0))
        rot = mathutils.Quaternion(axis.normalized(), angle)
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times, values, len(times), _curves_interpolation(curves))


def _fcurves_for_path(fcurves: tuple, path: str, width: int) -> list:
    out = [None] * width
    for curve in fcurves:
        if curve.data_path == path and 0 <= curve.array_index < width:
            out[curve.array_index] = curve
    return out


def _fcurves_by_data_path(fcurves: tuple) -> dict[str, tuple]:
    by_path: dict[str, list] = {}
    for curve in fcurves:
        by_path.setdefault(curve.data_path, []).append(curve)
    return {path: tuple(curves) for path, curves in by_path.items()}


def _fcurves_for_path_index(fcurves_by_path: dict[str, tuple], path: str, width: int) -> list:
    out = [None] * width
    if not path:
        return out
    for curve in fcurves_by_path.get(path, ()):
        index = curve.array_index
        if 0 <= index < width:
            out[index] = curve
    return out


def _fcurves_for_paths_index(fcurves_by_path: dict[str, tuple], paths: tuple[str, ...]) -> tuple:
    if not paths:
        return ()
    curves = []
    for path in paths:
        curves.extend(fcurves_by_path.get(path, ()))
    return tuple(curves)


def _scalar_fcurve_for_path(fcurves: tuple, path: str):
    for curve in fcurves:
        if curve.data_path == path:
            return curve
    return None


def _native_aligned_anim_channel(
    target: int,
    curves: tuple,
    defaults: tuple[float, ...],
    fps: float,
    mode: int,
):
    module = _native_module()
    if module is None:
        return False
    helper = getattr(module, "export_aligned_anim_channel", None)
    if helper is None:
        return False
    return helper(int(target), curves, defaults, float(fps), int(mode))


def _aligned_keyframe_values(
    curves: list,
    defaults: tuple[float, ...],
    width: int,
) -> tuple[tuple[float, ...], array] | None:
    co_arrays = [_fcurve_co_values(curve) if curve is not None else None for curve in curves]
    present = [co for co in co_arrays if co is not None]
    if not present:
        return None
    first = present[0]
    count = len(first) // 2
    if count < 2:
        return None
    frames = tuple(float(first[index * 2]) for index in range(count))
    values = array("f")
    for frame_index, frame in enumerate(frames):
        for component in range(width):
            co = co_arrays[component]
            if co is None:
                values.append(defaults[component])
                continue
            if len(co) != count * 2:
                return None
            if abs(float(co[frame_index * 2]) - frame) > 1.0e-6:
                return None
            values.append(float(co[frame_index * 2 + 1]))
    return frames, values


def _fcurve_co_values(curve) -> array | None:
    if curve is None:
        return None
    points = getattr(curve, "keyframe_points", None)
    if points is None:
        return None
    count = len(points)
    if count <= 0:
        return None
    values = array("f", [0.0]) * (count * 2)
    try:
        points.foreach_get("co", values)
    except Exception:
        for index, key in enumerate(points):
            values[index * 2] = float(key.co.x)
            values[index * 2 + 1] = float(key.co.y)
    return values


def _fcurve_keyframes(curves: list) -> tuple[float, ...]:
    frames: set[float] = set()
    for curve in curves:
        if curve is None:
            continue
        for key in curve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _fcurve_frame_values(curve, cache: dict[int, tuple[float, ...]]) -> tuple[float, ...]:
    key = int(curve.as_pointer()) if hasattr(curve, "as_pointer") else id(curve)
    cached = cache.get(key)
    if cached is not None:
        return cached

    points = curve.keyframe_points
    count = len(points)
    if count <= 0:
        frames = ()
    else:
        values = array("f", [0.0]) * (count * 2)
        try:
            points.foreach_get("co", values)
            frames = tuple(float(values[index * 2]) for index in range(count))
        except Exception:
            frames = tuple(float(keyframe.co.x) for keyframe in points)
    cache[key] = frames
    return frames


def _action_keyframes_for_curve_items(
    curves: tuple,
    frame_cache: dict[int, tuple[float, ...]] | None = None,
) -> tuple[float, ...]:
    if not curves:
        return ()
    if frame_cache is None:
        frame_cache = {}

    first = _fcurve_frame_values(curves[0], frame_cache)
    if all(_fcurve_frame_values(curve, frame_cache) == first for curve in curves[1:]):
        return first

    frames: set[float] = set()
    for curve in curves:
        frames.update(_fcurve_frame_values(curve, frame_cache))
    return tuple(sorted(frames))


def _curves_interpolation(curves: list) -> int:
    found = False
    for curve in curves:
        if curve is None:
            continue
        for key in curve.keyframe_points:
            found = True
            if key.interpolation != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _object_transform_defaults(obj: bpy.types.Object) -> tuple[tuple[float, ...], ...]:
    return (
        (float(obj.location.x), float(obj.location.y), float(obj.location.z)),
        tuple(float(value) for value in obj.rotation_axis_angle),
        (float(obj.rotation_euler.x), float(obj.rotation_euler.y), float(obj.rotation_euler.z)),
        tuple(float(value) for value in obj.rotation_quaternion),
        (float(obj.scale.x), float(obj.scale.y), float(obj.scale.z)),
    )


def _pose_bone_transform_defaults(pose_bone) -> tuple[tuple[float, ...], ...]:
    return (
        (float(pose_bone.location.x), float(pose_bone.location.y), float(pose_bone.location.z)),
        tuple(float(value) for value in pose_bone.rotation_axis_angle),
        (float(pose_bone.rotation_euler.x), float(pose_bone.rotation_euler.y), float(pose_bone.rotation_euler.z)),
        tuple(float(value) for value in pose_bone.rotation_quaternion),
        (float(pose_bone.scale.x), float(pose_bone.scale.y), float(pose_bone.scale.z)),
    )


def _action_transform_keyframes(action: bpy.types.Action, fcurves: tuple | None = None) -> tuple[float, ...]:
    frames: set[float] = set()
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in _TRANSFORM_ANIMATION_PATHS:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _expanded_integer_sample_frames(frames: tuple[float, ...]) -> tuple[float, ...]:
    if len(frames) < 2:
        return frames

    start = math.floor(frames[0])
    end = math.ceil(frames[-1])
    if end <= start:
        return _dedupe_animation_frames(frames)

    sampled = [float(frame) for frame in range(start, end + 1)]
    for frame in frames:
        value = _canonical_animation_frame(frame)
        nearest = round(value)
        if start <= nearest <= end and abs(value - nearest) <= _ANIMATION_FRAME_EPSILON:
            continue
        sampled.append(value)
    return _dedupe_animation_frames(tuple(sorted(sampled)))


def _canonical_animation_frame(frame: float) -> float:
    value = float(frame)
    nearest = round(value)
    if abs(value - nearest) <= _ANIMATION_FRAME_EPSILON:
        return float(nearest)
    return value


def _dedupe_animation_frames(frames: tuple[float, ...]) -> tuple[float, ...]:
    if len(frames) < 2:
        return frames

    out: list[float] = []
    previous: float | None = None
    for frame in frames:
        value = _canonical_animation_frame(frame)
        if previous is not None and abs(value - previous) <= _ANIMATION_FRAME_EPSILON:
            continue
        out.append(value)
        previous = value
    return tuple(out)


def _transform_fcurves_need_sampling(fcurves: tuple, paths: tuple[str, ...]) -> bool:
    if not fcurves:
        return False

    transform_paths = tuple(path for path in paths if path)
    rotation_paths = tuple(paths[index] for index in _BONE_ROTATION_PATH_INDICES if paths[index])
    if not transform_paths:
        return False

    for fcurve in fcurves:
        path = fcurve.data_path
        if path not in transform_paths:
            continue

        is_rotation = path in rotation_paths
        for key in fcurve.keyframe_points:
            interpolation = key.interpolation
            if interpolation not in {"CONSTANT", "LINEAR"}:
                return True
            if is_rotation and interpolation != "CONSTANT":
                return True
    return False


def _transform_curve_items_need_sampling(curves: tuple, rotation_paths: tuple[str, ...]) -> bool:
    rotation_path_set = set(rotation_paths)
    for curve in curves:
        if curve.data_path not in rotation_path_set:
            continue
        for key in curve.keyframe_points:
            interpolation = key.interpolation
            if interpolation not in {"CONSTANT", "LINEAR"}:
                return True
            if interpolation != "CONSTANT":
                return True
    for curve in curves:
        if curve.data_path in rotation_path_set:
            continue
        for key in curve.keyframe_points:
            interpolation = key.interpolation
            if interpolation not in {"CONSTANT", "LINEAR"}:
                return True
    return False


def _action_keyframes_for_paths(
    action: bpy.types.Action,
    paths,
    fcurves: tuple | None = None,
) -> tuple[float, ...]:
    frames: set[float] = set()
    if not paths:
        return ()
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _action_interpolation(
    action: bpy.types.Action,
    paths,
    fcurves: tuple | None = None,
) -> int:
    if not paths:
        return AK_INTERPOLATION_LINEAR
    found = False
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            found = True
            if key.interpolation != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _pose_bone_paths(armature: bpy.types.Object, bone_name: str) -> tuple[str, ...]:
    pose = getattr(armature, "pose", None)
    pose_bone = pose.bones.get(bone_name) if pose else None
    if pose_bone is None:
        return ()

    out: list[str] = [""] * len(_BONE_TRANSFORM_PROPERTIES)
    found = False
    index = 0
    for prop in _BONE_TRANSFORM_PROPERTIES:
        try:
            out[index] = pose_bone.path_from_id(prop)
            found = True
        except Exception:
            pass
        index += 1
    return tuple(out) if found else ()


def _pose_bone_constraint_keyframes(pose_bone) -> tuple[float, ...]:
    frames: set[float] = set()
    for constraint in getattr(pose_bone, "constraints", []) or []:
        target = getattr(constraint, "target", None)
        if target is not None:
            _collect_object_animation_keyframes(target, frames)
    return tuple(sorted(frames))


def _collect_object_animation_keyframes(obj: bpy.types.Object, frames: set[float]) -> None:
    seen: set[int] = set()
    while obj is not None:
        key = int(obj.as_pointer())
        if key in seen:
            return
        seen.add(key)

        animation_data = obj.animation_data
        action = animation_data.action if animation_data else None
        if action is not None:
            for fcurve in _iter_action_fcurves(action, animation_action_slot(animation_data)):
                for point in fcurve.keyframe_points:
                    frames.add(float(point.co.x))

        obj = obj.parent


def _pose_bone_local_matrix(pose_bone):
    if pose_bone.parent is not None:
        return pose_bone.parent.matrix.inverted_safe() @ pose_bone.matrix
    return pose_bone.matrix.copy()


def _set_scene_frame(scene: bpy.types.Scene, frame: float) -> bool:
    base = math.floor(frame)
    subframe = float(frame - base)
    if scene.frame_current == int(base) and abs(scene.frame_subframe - subframe) <= 1.0e-6:
        return False
    scene.frame_set(int(base), subframe=subframe)
    return True


def _evaluated_local_matrix(
    obj: bpy.types.Object,
    parent: bpy.types.Object | None,
    depsgraph: bpy.types.Depsgraph,
):
    matrix = obj.evaluated_get(depsgraph).matrix_world.copy()
    if parent is not None:
        matrix = parent.evaluated_get(depsgraph).matrix_world.inverted_safe() @ matrix
    return matrix


def _quat_dot(a: tuple[float, float, float, float],
              b: tuple[float, float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


def _float_samples_changed(values: array, width: int) -> bool:
    if width <= 0 or len(values) <= width:
        return False
    first = values[:width]
    for index in range(width, len(values), width):
        for component in range(width):
            if abs(values[index + component] - first[component]) > 1.0e-6:
                return True
    return False


def _mesh_armature_object(obj: bpy.types.Object) -> bpy.types.Object | None:
    for modifier in getattr(obj, "modifiers", []) or []:
        if modifier.type != "ARMATURE":
            continue
        armature = getattr(modifier, "object", None)
        if armature is not None and armature.type == "ARMATURE":
            return armature
    return None
