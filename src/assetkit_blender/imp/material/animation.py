from __future__ import annotations

import math
from array import array

import bpy

from ...assetkit import MeshPrimitiveData
from ..animation.actions import (
    _animation_action_for,
    _blender_interpolation,
    _channel_frame_bounds,
    _channel_tangents,
    _ensure_fcurve,
    _fcurve_write_key,
    _merge_frame_bounds,
    _register_actions_frame_range,
    _stash_animation_actions,
    _write_fcurve_points,
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
from ..textures import _texture_transform_values_gltf_to_blender
from .common import (
    _assetkit_node,
    _blender_anisotropy_rotation,
    _first_input,
    _normal_map_node,
    _texture_info,
    _uses_pbr_specular_level,
)
from .constants import (
    _ANIM_MATERIAL_ALPHA_CUTOFF,
    _ANIM_MATERIAL_ANISOTROPY,
    _ANIM_MATERIAL_ANISOTROPY_ROTATION,
    _ANIM_MATERIAL_BASE_COLOR,
    _ANIM_MATERIAL_CLEARCOAT,
    _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE,
    _ANIM_MATERIAL_CLEARCOAT_ROUGHNESS,
    _ANIM_MATERIAL_DIFFUSE_TRANSMISSION,
    _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR,
    _ANIM_MATERIAL_DISPERSION,
    _ANIM_MATERIAL_EMISSIVE_COLOR,
    _ANIM_MATERIAL_EMISSIVE_STRENGTH,
    _ANIM_MATERIAL_IOR,
    _ANIM_MATERIAL_IRIDESCENCE,
    _ANIM_MATERIAL_IRIDESCENCE_IOR,
    _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM,
    _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
    _ANIM_MATERIAL_METALLIC,
    _ANIM_MATERIAL_NORMAL_SCALE,
    _ANIM_MATERIAL_OCCLUSION_STRENGTH,
    _ANIM_MATERIAL_ROUGHNESS,
    _ANIM_MATERIAL_SHEEN_COLOR,
    _ANIM_MATERIAL_SHEEN_ROUGHNESS,
    _ANIM_MATERIAL_SPECULAR,
    _ANIM_MATERIAL_SPECULAR_COLOR,
    _ANIM_MATERIAL_TRANSMISSION,
    _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR,
    _ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE,
    _ANIM_MATERIAL_VOLUME_THICKNESS,
    _ANIM_TEXTURE_TRANSFORM_BASE,
    _ANIM_TEXTURE_TRANSFORM_OFFSET,
    _ANIM_TEXTURE_TRANSFORM_ROLES,
    _ANIM_TEXTURE_TRANSFORM_ROTATION,
    _ANIM_TEXTURE_TRANSFORM_SCALE,
    _ANIM_TEXTURE_TRANSFORM_STRIDE,
)


def _apply_material_animation(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    bsdf,
    color_target,
    color_input: str,
    alpha_socket,
    settings_node=None,
) -> None:
    channels = data.material_anim_channels or []
    if not channels:
        return
    if mat.get("assetkit_material_animation_applied"):
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    end_frame = scene.frame_end
    frame_bounds: tuple[float, float] | None = None
    converted_texture_location_roles, tex_end_frame = _apply_texture_transform_location_animations(
        mat,
        data,
        actions,
        written_fcurves,
        channels,
        fps,
    )
    end_frame = max(end_frame, tex_end_frame)

    for channel in channels:
        target = _channel_target(channel)
        tex_role = _texture_anim_role(target)
        bounds = _channel_frame_bounds(channel, fps)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])
        if (
            tex_role in converted_texture_location_roles
            and _texture_anim_prop(target) == _ANIM_TEXTURE_TRANSFORM_OFFSET
        ):
            continue
        width = _material_anim_width(target)
        if width <= 0:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        if target_offset >= width:
            continue

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            owner, path, fcurve_index, group_name = _material_anim_channel_target(
                mat,
                bsdf,
                color_target,
                color_input,
                alpha_socket,
                settings_node,
                target,
                target_index,
            )
            if not owner or not path:
                continue

            action = _animation_action_for(mat, owner, actions, "" if owner == mat else "_Nodes", channel)
            write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
            coords = array("f", [0.0]) * (count * 2)
            for key_index in range(count):
                coords[key_index * 2] = times[key_index] * fps
                value = values[key_index * value_width + value_index]
                coords[key_index * 2 + 1] = _material_anim_output_value(data, target, value)

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
                    lambda value, target=target, data=data: _material_anim_output_tangent(
                        data,
                        target,
                        value,
                    )
                ),
            )

        end_frame = max(end_frame, int(times[count - 1] * fps + 0.5))

    _register_actions_frame_range(actions, frame_bounds)
    _stash_animation_actions(actions)
    if actions:
        mat["assetkit_material_animation_applied"] = True
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _material_anim_width(target: int) -> int:
    tex_prop = _texture_anim_prop(target)
    if tex_prop in {_ANIM_TEXTURE_TRANSFORM_OFFSET, _ANIM_TEXTURE_TRANSFORM_SCALE}:
        return 2
    if tex_prop == _ANIM_TEXTURE_TRANSFORM_ROTATION:
        return 1

    if target in {
        _ANIM_MATERIAL_BASE_COLOR,
    }:
        return 4
    if target in {
        _ANIM_MATERIAL_EMISSIVE_COLOR,
        _ANIM_MATERIAL_SPECULAR_COLOR,
        _ANIM_MATERIAL_SHEEN_COLOR,
        _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR,
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR,
    }:
        return 3
    if target in {
        _ANIM_MATERIAL_METALLIC,
        _ANIM_MATERIAL_ROUGHNESS,
        _ANIM_MATERIAL_ALPHA_CUTOFF,
        _ANIM_MATERIAL_EMISSIVE_STRENGTH,
        _ANIM_MATERIAL_NORMAL_SCALE,
        _ANIM_MATERIAL_OCCLUSION_STRENGTH,
        _ANIM_MATERIAL_SPECULAR,
        _ANIM_MATERIAL_IOR,
        _ANIM_MATERIAL_CLEARCOAT,
        _ANIM_MATERIAL_CLEARCOAT_ROUGHNESS,
        _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE,
        _ANIM_MATERIAL_TRANSMISSION,
        _ANIM_MATERIAL_SHEEN_ROUGHNESS,
        _ANIM_MATERIAL_IRIDESCENCE,
        _ANIM_MATERIAL_IRIDESCENCE_IOR,
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM,
        _ANIM_MATERIAL_VOLUME_THICKNESS,
        _ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE,
        _ANIM_MATERIAL_ANISOTROPY,
        _ANIM_MATERIAL_ANISOTROPY_ROTATION,
        _ANIM_MATERIAL_DISPERSION,
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION,
    }:
        return 1
    return 0


def _apply_texture_transform_location_animations(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    written_fcurves: set[tuple[int, int, str, int]],
    channels: list[dict],
    fps: float,
) -> tuple[set[str], int]:
    by_role: dict[str, dict[int, list[dict]]] = {}
    for channel in channels:
        target = _channel_target(channel)
        role = _texture_anim_role(target)
        prop = _texture_anim_prop(target)
        if role and prop in {
            _ANIM_TEXTURE_TRANSFORM_OFFSET,
            _ANIM_TEXTURE_TRANSFORM_SCALE,
            _ANIM_TEXTURE_TRANSFORM_ROTATION,
        }:
            by_role.setdefault(role, {}).setdefault(prop, []).append(channel)

    converted_roles: set[str] = set()
    end_frame = bpy.context.scene.frame_end

    for role, prop_channels in by_role.items():
        tex_info = _texture_info(data, role)
        mapping = _texture_mapping_node(mat, role)
        if not tex_info or not mapping:
            continue
        socket = mapping.inputs.get("Location")
        if not socket:
            continue

        key_times = _texture_transform_key_times(prop_channels)
        if not key_times:
            continue

        path = socket.path_from_id("default_value")
        action = _animation_action_for(mat, mat.node_tree, actions, "_Nodes", _first_texture_transform_channel(prop_channels))
        interpolation = _texture_transform_location_interpolation(prop_channels)

        coords = [array("f", [0.0]) * (len(key_times) * 2) for _ in range(2)]
        for key_index, time_value in enumerate(key_times):
            offset = _texture_transform_sample_vec2(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_OFFSET, []),
                tex_info.transform_offset,
                time_value,
            )
            scale = _texture_transform_sample_vec2(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_SCALE, []),
                tex_info.transform_scale,
                time_value,
            )
            rotation = _texture_transform_sample_scalar(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_ROTATION, []),
                float(tex_info.transform_rotation),
                time_value,
            )
            blender_offset, _, _ = _texture_transform_values_gltf_to_blender(offset, rotation, scale)
            frame = time_value * fps
            for component in range(2):
                coords[component][key_index * 2] = frame
                coords[component][key_index * 2 + 1] = blender_offset[component]

        first_channel = _first_texture_transform_channel(prop_channels)
        for component in range(2):
            write_key = _fcurve_write_key(mat.node_tree, first_channel, path, component)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, mat.node_tree, path, component, group_name="Texture Transform")
            _write_fcurve_points(fcurve, coords[component], interpolation)

        converted_roles.add(role)
        end_frame = max(end_frame, int(key_times[-1] * fps + 0.5))

    return converted_roles, end_frame


def _first_texture_transform_channel(prop_channels: dict[int, list[dict]]) -> dict:
    for prop in (
        _ANIM_TEXTURE_TRANSFORM_OFFSET,
        _ANIM_TEXTURE_TRANSFORM_SCALE,
        _ANIM_TEXTURE_TRANSFORM_ROTATION,
    ):
        channels = prop_channels.get(prop) or []
        if channels:
            return channels[0]
    return {}


def _texture_transform_key_times(prop_channels: dict[int, list[dict]]) -> list[float]:
    values: set[float] = set()
    for channels in prop_channels.values():
        for channel in channels:
            count = _channel_count(channel)
            times = _buffer_view(_channel_times(channel), "f")
            if count <= 0 or times is None:
                continue
            for index in range(min(count, len(times))):
                values.add(float(times[index]))
    return sorted(values)


def _texture_transform_location_interpolation(prop_channels: dict[int, list[dict]]) -> str:
    interpolation = "CONSTANT"
    for channels in prop_channels.values():
        for channel in channels:
            if _blender_interpolation(_channel_interpolation(channel)) != "CONSTANT":
                return "LINEAR"
    return interpolation


def _texture_transform_sample_vec2(
    channels: list[dict],
    fallback: tuple[float, float],
    time_value: float,
) -> tuple[float, float]:
    values = [float(fallback[0]), float(fallback[1])]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0], values[1]


def _texture_transform_sample_scalar(
    channels: list[dict],
    fallback: float,
    time_value: float,
) -> float:
    values = [float(fallback)]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0]


def _texture_transform_sample_into(values: list[float], channel: dict, time_value: float) -> None:
    count = _channel_count(channel)
    value_width = _channel_value_width(channel)
    target_offset = _channel_target_offset(channel)
    is_partial = _channel_is_partial(channel)
    times = _buffer_view(_channel_times(channel), "f")
    raw_values = _buffer_view(_channel_values(channel), "f")
    if count <= 0 or value_width <= 0 or times is None or raw_values is None:
        return

    width = len(values)
    if target_offset >= width:
        return
    component_count = 1 if is_partial else min(width - target_offset, value_width)
    interpolation = _blender_interpolation(_channel_interpolation(channel))
    for component in range(component_count):
        target_index = target_offset + component
        value_index = 0 if is_partial else component
        values[target_index] = _sample_anim_scalar(times, raw_values, count, value_width, value_index, time_value, interpolation)


def _sample_anim_scalar(
    times: memoryview,
    values: memoryview,
    count: int,
    value_width: int,
    value_index: int,
    time_value: float,
    interpolation: str,
) -> float:
    if count <= 1 or time_value <= float(times[0]):
        return float(values[value_index])

    last = min(count, len(times)) - 1
    if time_value >= float(times[last]):
        return float(values[last * value_width + value_index])

    prev = 0
    for index in range(1, last + 1):
        if time_value <= float(times[index]):
            prev = index - 1
            next_index = index
            break
    else:
        return float(values[last * value_width + value_index])

    prev_value = float(values[prev * value_width + value_index])
    if interpolation == "CONSTANT":
        return prev_value

    next_time = float(times[next_index])
    prev_time = float(times[prev])
    if next_time <= prev_time:
        return prev_value
    next_value = float(values[next_index * value_width + value_index])
    factor = (time_value - prev_time) / (next_time - prev_time)
    return prev_value + (next_value - prev_value) * factor


def _material_anim_channel_target(
    mat: bpy.types.Material,
    bsdf,
    color_target,
    color_input: str,
    alpha_socket,
    settings_node,
    target: int,
    target_index: int,
) -> tuple[bpy.types.ID | None, str, int | None, str]:
    tex_role = _texture_anim_role(target)
    tex_prop = _texture_anim_prop(target)
    if tex_role:
        mapping = _texture_mapping_node(mat, tex_role)
        if mapping:
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_OFFSET:
                socket = mapping.inputs.get("Location")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), target_index, "Texture Transform"
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_SCALE:
                socket = mapping.inputs.get("Scale")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), target_index, "Texture Transform"
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_ROTATION:
                socket = mapping.inputs.get("Rotation")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), 2, "Texture Transform"

    if target == _ANIM_MATERIAL_BASE_COLOR:
        socket = alpha_socket if target_index == 3 and alpha_socket else _first_input(color_target, (color_input,))
        if not socket:
            return None, "", None, ""
        index = None if socket == alpha_socket else target_index
        return mat.node_tree, socket.path_from_id("default_value"), index, "Material"

    if target == _ANIM_MATERIAL_NORMAL_SCALE:
        node = _normal_map_node(mat, "normal")
        socket = _first_input(node, ("Strength",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Normal"

    if target == _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE:
        node = _normal_map_node(mat, "clearcoat_normal")
        socket = _first_input(node, ("Strength",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Normal"

    socket_target = {
        _ANIM_MATERIAL_METALLIC: ("Metallic",),
        _ANIM_MATERIAL_ROUGHNESS: ("Roughness",),
        _ANIM_MATERIAL_EMISSIVE_STRENGTH: ("Emission Strength",),
        _ANIM_MATERIAL_SPECULAR: ("Specular IOR Level", "Specular"),
        _ANIM_MATERIAL_IOR: ("IOR",),
        _ANIM_MATERIAL_CLEARCOAT: ("Coat Weight", "Clearcoat"),
        _ANIM_MATERIAL_CLEARCOAT_ROUGHNESS: ("Coat Roughness", "Clearcoat Roughness"),
        _ANIM_MATERIAL_TRANSMISSION: ("Transmission Weight", "Transmission"),
        _ANIM_MATERIAL_SHEEN_ROUGHNESS: ("Sheen Roughness",),
        _ANIM_MATERIAL_ANISOTROPY: ("Anisotropic",),
        _ANIM_MATERIAL_ANISOTROPY_ROTATION: ("Anisotropic Rotation",),
        _ANIM_MATERIAL_IRIDESCENCE: ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        _ANIM_MATERIAL_IRIDESCENCE_IOR: ("Thin Film IOR",),
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM: ("Thin Film Thickness",),
        _ANIM_MATERIAL_VOLUME_THICKNESS: ("Volume Thickness",),
        _ANIM_MATERIAL_DISPERSION: ("Dispersion",),
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION: ("Diffuse Transmission Weight", "Diffuse Transmission"),
    }.get(target)
    if socket_target:
        socket = _first_input(bsdf, socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Material"

    color_socket_target = {
        _ANIM_MATERIAL_EMISSIVE_COLOR: ("Emission Color",),
        _ANIM_MATERIAL_SPECULAR_COLOR: ("Specular Tint",),
        _ANIM_MATERIAL_SHEEN_COLOR: ("Sheen Tint",),
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR: ("Diffuse Transmission Color",),
    }.get(target)
    if color_socket_target:
        socket = _first_input(bsdf, color_socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Material"

    if target == _ANIM_MATERIAL_ALPHA_CUTOFF:
        return mat, "alpha_threshold", None, "Material"

    if target == _ANIM_MATERIAL_DIFFUSE_TRANSMISSION:
        node = _assetkit_node(mat, "assetkit_diffuse_transmission_node", "mix")
        socket = _first_input(node, ("Fac",))
        if socket and not socket.is_linked:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Diffuse Transmission"

    if target == _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR:
        node = _assetkit_node(mat, "assetkit_diffuse_transmission_node", "translucent")
        socket = _first_input(node, ("Color",))
        if socket and not socket.is_linked:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Diffuse Transmission"

    if target == _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR:
        node = _assetkit_node(mat, "assetkit_volume_node", "absorption")
        socket = _first_input(node, ("Color",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Volume"

    settings_socket_target = {
        _ANIM_MATERIAL_OCCLUSION_STRENGTH: ("Occlusion",),
        _ANIM_MATERIAL_IRIDESCENCE: ("Iridescence Factor",),
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM: ("Iridescence Thickness Minimum",),
        _ANIM_MATERIAL_VOLUME_THICKNESS: ("Thickness",),
        _ANIM_MATERIAL_DISPERSION: ("Dispersion",),
    }.get(target)
    if settings_socket_target:
        socket = _first_input(settings_node, settings_socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "glTF Material Output"

    prop = _material_anim_custom_prop(target)
    if prop:
        if prop not in mat:
            mat[prop] = (0.0, 0.0, 0.0) if _material_anim_width(target) > 1 else 0.0
        return mat, f'["{prop}"]', None if _material_anim_width(target) == 1 else target_index, "AssetKit"

    return None, "", None, ""


def _material_anim_output_value(data: MeshPrimitiveData, target: int, value: float) -> float:
    if target == _ANIM_MATERIAL_SPECULAR and _uses_pbr_specular_level(data):
        return float(value) * 0.5
    if target == _ANIM_MATERIAL_ANISOTROPY_ROTATION:
        return _blender_anisotropy_rotation(value)
    return float(value)


def _material_anim_output_tangent(data: MeshPrimitiveData, target: int, value: float) -> float:
    if target == _ANIM_MATERIAL_SPECULAR and _uses_pbr_specular_level(data):
        return float(value) * 0.5
    if target == _ANIM_MATERIAL_ANISOTROPY_ROTATION:
        return float(value) / (2.0 * math.pi)
    return float(value)


def _texture_anim_role(target: int) -> str:
    if target < _ANIM_TEXTURE_TRANSFORM_BASE:
        return ""
    offset = target - _ANIM_TEXTURE_TRANSFORM_BASE
    role_index = offset // _ANIM_TEXTURE_TRANSFORM_STRIDE
    if role_index < 0 or role_index >= len(_ANIM_TEXTURE_TRANSFORM_ROLES):
        return ""
    return _ANIM_TEXTURE_TRANSFORM_ROLES[role_index]


def _texture_anim_prop(target: int) -> int:
    if target < _ANIM_TEXTURE_TRANSFORM_BASE:
        return -1
    return (target - _ANIM_TEXTURE_TRANSFORM_BASE) % _ANIM_TEXTURE_TRANSFORM_STRIDE


def _texture_mapping_node(mat: bpy.types.Material, role: str):
    node_tree = mat.node_tree
    if not node_tree or not role:
        return None
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeMapping" and node.get("assetkit_texture_role") == role:
            return node
    return None


def _material_anim_custom_prop(target: int) -> str:
    return {
        _ANIM_MATERIAL_NORMAL_SCALE: "assetkit_normal_scale",
        _ANIM_MATERIAL_OCCLUSION_STRENGTH: "assetkit_occlusion_strength",
        _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE: "assetkit_clearcoat_normal_scale",
        _ANIM_MATERIAL_IRIDESCENCE: "assetkit_iridescence",
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM: "assetkit_iridescence_thickness_minimum",
        _ANIM_MATERIAL_VOLUME_THICKNESS: "assetkit_volume_thickness",
        _ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE: "assetkit_volume_attenuation_distance",
        _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR: "assetkit_volume_attenuation_color",
        _ANIM_MATERIAL_DISPERSION: "assetkit_dispersion",
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION: "assetkit_diffuse_transmission",
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR: "assetkit_diffuse_transmission_color",
    }.get(target, "")
