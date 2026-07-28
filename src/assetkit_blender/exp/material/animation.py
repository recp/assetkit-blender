from __future__ import annotations

from array import array

import bpy

from ...assetkit import _native_module
from ...enums import (
    AK_INTERPOLATION_LINEAR,
    AK_INTERPOLATION_STEP,
    AKB_ANIM_MATERIAL_BASE_COLOR,
    AKB_ANIM_MATERIAL_EMISSIVE_COLOR,
    AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH,
    AKB_ANIM_MATERIAL_IOR,
    AKB_ANIM_MATERIAL_METALLIC,
    AKB_ANIM_MATERIAL_ROUGHNESS,
)
from ..animation import animation_action_slot, animation_channels_with_clip
from ..animation.common import _iter_action_fcurves
from .common import _texture_transform_blender_to_gltf
from .constants import (
    _ANIM_TEXTURE_TRANSFORM_BASE,
    _ANIM_TEXTURE_TRANSFORM_OFFSET,
    _ANIM_TEXTURE_TRANSFORM_ROLES,
    _ANIM_TEXTURE_TRANSFORM_ROTATION,
    _ANIM_TEXTURE_TRANSFORM_SCALE,
    _ANIM_TEXTURE_TRANSFORM_STRIDE,
)


def _material_animation_payload(
    material: bpy.types.Material,
    bsdf,
    base_color: list[float],
    fps: float,
) -> tuple | None:
    if not material.node_tree:
        return None

    anim_data = getattr(material.node_tree, "animation_data", None)
    action = getattr(anim_data, "action", None) if anim_data else None
    if action is None:
        return None

    if fps <= 0.0:
        fps = 24.0

    fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(anim_data)))
    if not fcurves:
        return None

    channels: list[tuple] = []
    base_channel = _base_color_animation_channel(bsdf, fcurves, base_color, fps)
    if base_channel:
        channels.append(base_channel)
    channels.extend(_principled_material_animation_channels(bsdf, fcurves, fps))
    channels.extend(_texture_transform_animation_channels(material, fcurves, fps))
    return animation_channels_with_clip(channels, action) if channels else None


def _base_color_animation_channel(bsdf, fcurves: tuple, base_color: list[float], fps: float):
    if bsdf is None:
        return None

    base_socket = bsdf.inputs.get("Base Color")
    if base_socket is None:
        return None

    curves = [None, None, None, None]
    base_path = base_socket.path_from_id("default_value")
    _copy_socket_fcurves(fcurves, base_path, curves, 4)

    alpha_socket = bsdf.inputs.get("Alpha")
    if alpha_socket is not None:
        alpha_path = alpha_socket.path_from_id("default_value")
        _copy_socket_fcurves(fcurves, alpha_path, curves, 1, dst_offset=3)

    if not any(curves):
        return None

    helper = getattr(_native_module(), "export_aligned_anim_channel", None)
    if helper is None:
        return None

    channel = helper(
        int(AKB_ANIM_MATERIAL_BASE_COLOR),
        tuple(curves),
        tuple(float(v) for v in base_color[:4]),
        float(fps),
        0,
    )
    return channel if channel else None


def _principled_material_animation_channels(bsdf, fcurves: tuple, fps: float) -> list[tuple]:
    if bsdf is None:
        return []

    out: list[tuple] = []
    for socket_name, target, width, fallback in (
        ("Metallic", AKB_ANIM_MATERIAL_METALLIC, 1, (0.0,)),
        ("Roughness", AKB_ANIM_MATERIAL_ROUGHNESS, 1, (1.0,)),
        ("Emission Color", AKB_ANIM_MATERIAL_EMISSIVE_COLOR, 3, (0.0, 0.0, 0.0)),
        ("Emission Strength", AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH, 1, (1.0,)),
        ("IOR", AKB_ANIM_MATERIAL_IOR, 1, (1.5,)),
    ):
        channel = _socket_animation_channel(
            bsdf,
            fcurves,
            socket_name,
            int(target),
            int(width),
            tuple(float(v) for v in fallback),
            fps,
        )
        if channel:
            out.append(channel)
    return out


def _socket_animation_channel(
    bsdf,
    fcurves: tuple,
    socket_name: str,
    target: int,
    width: int,
    fallback: tuple[float, ...],
    fps: float,
):
    socket = bsdf.inputs.get(socket_name)
    if socket is None:
        return None

    curves = [None] * width
    _copy_socket_fcurves(fcurves, socket.path_from_id("default_value"), curves, width)
    if not any(curves):
        return None

    default = _socket_anim_default(socket, width, fallback)
    helper = getattr(_native_module(), "export_aligned_anim_channel", None)
    if helper is None:
        return None
    channel = helper(target, tuple(curves), default, float(fps), 0)
    return channel if channel else None


def _socket_anim_default(socket, width: int, fallback: tuple[float, ...]) -> tuple[float, ...]:
    value = getattr(socket, "default_value", None)
    if value is None:
        return fallback[:width]

    if width == 1:
        try:
            return (float(value),)
        except (TypeError, ValueError):
            return fallback[:1]

    try:
        values = tuple(float(value[i]) for i in range(width))
    except (TypeError, ValueError, IndexError):
        return fallback[:width]
    return values


def _copy_socket_fcurves(
    fcurves: tuple,
    data_path: str,
    out: list,
    width: int,
    *,
    dst_offset: int = 0,
) -> None:
    for curve in fcurves:
        if curve.data_path != data_path:
            continue
        index = int(curve.array_index)
        if index < 0 or index >= width:
            continue
        dst_index = dst_offset + index
        if dst_index < len(out):
            out[dst_index] = curve


def _texture_transform_animation_channels(
    material: bpy.types.Material,
    fcurves: tuple,
    fps: float,
) -> list[tuple]:
    out: list[tuple] = []
    for role_index, role in enumerate(_ANIM_TEXTURE_TRANSFORM_ROLES):
        if role == "transparent":
            continue
        mapping = _mapping_node_for_role(material, role)
        if mapping is None:
            continue
        out.extend(_mapping_texture_transform_channels(mapping, fcurves, role_index, fps))
    return out


def _mapping_node_for_role(material: bpy.types.Material, role: str):
    node_tree = material.node_tree
    if not node_tree:
        return None
    for node in node_tree.nodes:
        if node.type == "MAPPING" and node.get("assetkit_texture_role") == role:
            return node
    return None


def _mapping_texture_transform_channels(mapping, fcurves: tuple, role_index: int, fps: float) -> list[tuple]:
    location = mapping.inputs.get("Location")
    rotation = mapping.inputs.get("Rotation")
    scale = mapping.inputs.get("Scale")
    if location is None or rotation is None or scale is None:
        return []

    loc_curves = _curves_for_socket(fcurves, location.path_from_id("default_value"), 2)
    rot_curves = _curves_for_socket(fcurves, rotation.path_from_id("default_value"), 3)
    scale_curves = _curves_for_socket(fcurves, scale.path_from_id("default_value"), 2)
    curves = tuple(curve for curve in (*loc_curves, rot_curves[2], *scale_curves) if curve)
    if not curves:
        return []

    frames = _animation_frames(curves)
    if len(frames) < 2:
        return []

    loc_default = tuple(float(location.default_value[i]) for i in range(2))
    rot_default = float(rotation.default_value[2])
    scale_default = tuple(float(scale.default_value[i]) for i in range(2))
    times = array("f", (float(frame) / fps for frame in frames))
    offsets = array("f")
    scales = array("f")
    rotations = array("f")

    for frame in frames:
        loc_x = _eval_fcurve(loc_curves[0], frame, loc_default[0])
        loc_y = _eval_fcurve(loc_curves[1], frame, loc_default[1])
        rot_z = _eval_fcurve(rot_curves[2], frame, rot_default)
        scale_x = _eval_fcurve(scale_curves[0], frame, scale_default[0])
        scale_y = _eval_fcurve(scale_curves[1], frame, scale_default[1])
        off_x, off_y, gltf_rot, gltf_scale_x, gltf_scale_y = _texture_transform_blender_to_gltf(
            (loc_x, loc_y, rot_z, scale_x, scale_y)
        )
        offsets.extend((off_x, off_y))
        scales.extend((gltf_scale_x, gltf_scale_y))
        rotations.append(gltf_rot)

    interpolation = _animation_interpolation(curves)
    out: list[tuple] = []
    if _animated_values_changed(offsets, 2):
        out.append(_texture_transform_channel(role_index, _ANIM_TEXTURE_TRANSFORM_OFFSET, times, offsets, interpolation))
    if _animated_values_changed(scales, 2):
        out.append(_texture_transform_channel(role_index, _ANIM_TEXTURE_TRANSFORM_SCALE, times, scales, interpolation))
    if _animated_values_changed(rotations, 1):
        out.append(_texture_transform_channel(role_index, _ANIM_TEXTURE_TRANSFORM_ROTATION, times, rotations, interpolation))
    return out


def _curves_for_socket(fcurves: tuple, data_path: str, width: int) -> list:
    out = [None] * width
    _copy_socket_fcurves(fcurves, data_path, out, width)
    return out


def _animation_frames(fcurves: tuple) -> list[float]:
    frames: set[float] = set()
    for curve in fcurves:
        for key in curve.keyframe_points:
            frames.add(float(key.co.x))
    return sorted(frames)


def _eval_fcurve(curve, frame: float, fallback: float) -> float:
    if curve is None:
        return float(fallback)
    try:
        return float(curve.evaluate(frame))
    except Exception:
        return float(fallback)


def _animation_interpolation(fcurves: tuple) -> int:
    found = False
    for curve in fcurves:
        for key in curve.keyframe_points:
            found = True
            if getattr(key, "interpolation", "LINEAR") != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _animated_values_changed(values: array, width: int) -> bool:
    if len(values) <= width:
        return False
    first = tuple(values[i] for i in range(width))
    for index in range(width, len(values), width):
        for component in range(width):
            if abs(float(values[index + component]) - float(first[component])) > 1.0e-6:
                return True
    return False


def _texture_transform_channel(
    role_index: int,
    prop: int,
    times: array,
    values: array,
    interpolation: int,
) -> tuple:
    target = _ANIM_TEXTURE_TRANSFORM_BASE + role_index * _ANIM_TEXTURE_TRANSFORM_STRIDE + prop
    return int(target), times, values, len(times), int(interpolation)


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
                except (AttributeError, TypeError, RuntimeError):
                    channelbag = None
                if channelbag is not None:
                    yield from getattr(channelbag, "fcurves", []) or []
