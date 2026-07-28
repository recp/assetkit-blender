from __future__ import annotations

import json
import math
from array import array

import bpy

from ..animation import animation_action_slot
from ..animation.common import _iter_action_fcurves
from ..images import _ExportImageStore
from .constants import (
    _AK_MAGFILTER_LINEAR,
    _AK_MAGFILTER_NEAREST,
    _AK_MINFILTER_LINEAR_MIPMAP_LINEAR,
    _AK_MINFILTER_NEAREST_MIPMAP_NEAREST,
    _AK_WRAP_CLAMP,
    _AK_WRAP_MIRROR,
    _AK_WRAP_REPEAT,
    _MATERIAL_TYPE_UNLIT,
)


def _assetkit_channel_mask(channel: int) -> int:
    if int(channel) == 1:
        return 2
    if int(channel) == 2:
        return 4
    if int(channel) == 3:
        return 8
    return 0


def _assetkit_json_prop(target: object | None, key: str) -> object | None:
    if target is None:
        return None
    try:
        raw = target.get(key)
    except AttributeError:
        return None
    if not raw or not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _principled_bsdf(material: bpy.types.Material):
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _volume_output_node(material: bpy.types.Material, node_type: str):
    node_tree = material.node_tree
    if not node_tree:
        return None
    output = node_tree.nodes.get("Material Output")
    if output is None:
        return None
    volume = output.inputs.get("Volume")
    if volume is None or not volume.is_linked:
        return None

    stack = [link.from_node for link in volume.links]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        node_id = id(node)
        if node_id in seen:
            continue
        seen.add(node_id)
        if node.type == node_type:
            return node
        for input_socket in getattr(node, "inputs", ()):
            if input_socket.is_linked:
                stack.extend(link.from_node for link in input_socket.links)
    return None


def _volume_absorption_node(material: bpy.types.Material):
    return _volume_output_node(material, "VOLUME_ABSORPTION")


def _volume_scatter_node(material: bpy.types.Material):
    return _volume_output_node(material, "VOLUME_SCATTER")


def _material_type(material: bpy.types.Material, bsdf, unlit_emission) -> int:
    if "assetkit_material_type" in material:
        return int(_prop_float(material, "assetkit_material_type", 0.0))
    if unlit_emission is not None and bsdf is None:
        return _MATERIAL_TYPE_UNLIT
    return 0


def _material_bake_required(material: bpy.types.Material | None, material_export_mode: str) -> bool:
    mode = (material_export_mode or "AUTO").upper()
    if mode in {"DIRECT", "NONE"}:
        return False
    if material is None or not material.use_nodes or not material.node_tree:
        return False
    if mode == "BAKE":
        return True
    return not _material_graph_directly_supported(material)


def _bake_uv_key(uv_slot_by_name: dict[str, int]) -> str:
    for name, slot in uv_slot_by_name.items():
        if int(slot) == 0:
            return str(name)
    return ""


def _material_graph_directly_supported(material: bpy.types.Material) -> bool:
    surface = _material_surface_socket(material)
    if surface is None or not surface.is_linked:
        return True

    node = _skip_reroute(surface.links[0].from_node)
    if node is None:
        return True

    if node.type == "BSDF_PRINCIPLED":
        for socket_name in (
            "Base Color",
            "Alpha",
            "Metallic",
            "Roughness",
            "Emission Color",
            "Normal",
        ):
            if not _socket_direct_texture_or_default(node.inputs.get(socket_name), set()):
                return False
        return True

    unlit_emission = _unlit_emission_node(material)
    if unlit_emission is not None:
        return _socket_direct_texture_or_default(unlit_emission.inputs.get("Color"), set())

    return False


def _material_surface_extractable(material: bpy.types.Material) -> bool:
    node = _material_surface_shader_node(material)
    if node is not None and node.type == "BSDF_PRINCIPLED":
        return True
    return _unlit_emission_node(material) is not None


def _material_surface_shader_node(material: bpy.types.Material):
    surface = _material_surface_socket(material)
    if surface is None or not surface.is_linked:
        return None
    return _skip_reroute(surface.links[0].from_node)


def _material_surface_socket(material: bpy.types.Material):
    node_tree = material.node_tree
    if not node_tree:
        return None
    output = None
    for node in node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and getattr(node, "is_active_output", True):
            output = node
            break
    if output is None:
        output = node_tree.nodes.get("Material Output")
    if output is None:
        return None
    return output.inputs.get("Surface")


def _skip_reroute(node):
    seen: set[int] = set()
    while node is not None and node.type == "REROUTE":
        node_id = id(node)
        if node_id in seen:
            return None
        seen.add(node_id)
        input_socket = node.inputs[0] if len(node.inputs) > 0 else None
        if input_socket is None or not input_socket.is_linked:
            return None
        node = input_socket.links[0].from_node
    return node


def _socket_direct_texture_or_default(socket, seen: set[int]) -> bool:
    if socket is None or not socket.is_linked:
        return True
    if len(socket.links) != 1:
        return False
    return _direct_texture_node(socket.links[0].from_node, seen)


def _direct_texture_node(node, seen: set[int]) -> bool:
    node = _skip_reroute(node)
    if node is None:
        return False
    node_id = id(node)
    if node_id in seen:
        return False
    seen.add(node_id)

    if node.type == "TEX_IMAGE":
        return node.image is not None

    if node.type == "NORMAL_MAP":
        return _socket_direct_texture_or_default(node.inputs.get("Color"), seen)

    if node.type in {"SEPARATE_COLOR", "SEPARATE_RGB", "SEPRGB"}:
        color_socket = (
            node.inputs.get("Color")
            or node.inputs.get("Image")
            or (node.inputs[0] if len(node.inputs) > 0 else None)
        )
        return _socket_direct_texture_or_default(color_socket, seen)

    return False


def _unlit_emission_node(material: bpy.types.Material):
    node_tree = material.node_tree
    if not node_tree:
        return None
    output = node_tree.nodes.get("Material Output")
    if output is None:
        return None
    surface = output.inputs.get("Surface")
    ok, emission = _shader_socket_unlit_emission(surface, set())
    return emission if ok else None


def _shader_socket_unlit_emission(socket, seen: set[int]) -> tuple[bool, object | None]:
    if socket is None or not socket.is_linked:
        return False, None
    link = socket.links[0]
    node = link.from_node
    node_id = id(node)
    if node_id in seen:
        return False, None
    seen.add(node_id)

    if node.type == "EMISSION":
        return True, node
    if node.type == "BSDF_TRANSPARENT":
        return True, None
    if node.type == "MIX_SHADER":
        left = node.inputs[1] if len(node.inputs) > 1 else None
        right = node.inputs[2] if len(node.inputs) > 2 else None
        left_ok, left_emission = _shader_socket_unlit_emission(left, seen)
        right_ok, right_emission = _shader_socket_unlit_emission(right, seen)
        emission = left_emission if left_emission is not None else right_emission
        return left_ok and right_ok and emission is not None, emission
    return False, None


def _socket_default(node, identifier: str):
    socket = node.inputs.get(identifier)
    if socket is None or socket.is_linked:
        return None
    return getattr(socket, "default_value", None)


def _material_input_socket(material: bpy.types.Material, name: str):
    if not material.node_tree:
        return None
    for node in material.node_tree.nodes:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    return None


def _linked_image_channel(
    socket,
    uv_slot_by_name: dict[str, int] | None = None,
) -> tuple[bpy.types.Image | None, int, int]:
    image, channel, slot, _info = _linked_texture_info(socket, uv_slot_by_name)
    return image, channel, slot


def _linked_texture_info(
    socket,
    uv_slot_by_name: dict[str, int] | None = None,
) -> tuple[bpy.types.Image | None, int, int, tuple | None]:
    if socket is None or not socket.is_linked:
        return None, 0, 0, None

    stack = [(link.from_node, _texture_output_channel(link.from_socket)) for link in socket.links]
    seen: set[int] = set()
    uv_slot_by_name = uv_slot_by_name or {}

    while stack:
        node, channel = stack.pop()
        node_id = id(node)
        if node_id in seen:
            continue
        seen.add(node_id)

        if node.type == "TEX_IMAGE" and node.image is not None:
            slot = _texture_uv_slot(node, uv_slot_by_name)
            return node.image, channel, slot, _texture_info_tuple(node, slot)

        for input_socket in getattr(node, "inputs", ()):
            if not input_socket.is_linked:
                continue
            for link in input_socket.links:
                upstream_channel = _texture_output_channel(link.from_socket)
                if channel != 0 and upstream_channel == 0:
                    upstream_channel = channel
                stack.append((link.from_node, upstream_channel))

    return None, 0, 0, None


def _texture_uv_slot(node, uv_slot_by_name: dict[str, int]) -> int:
    vector = node.inputs.get("Vector")
    if vector is None or not vector.is_linked:
        return 0

    stack = [link.from_node for link in vector.links]
    seen: set[int] = set()
    while stack:
        item = stack.pop()
        item_id = id(item)
        if item_id in seen:
            continue
        seen.add(item_id)

        uv_name = ""
        if item.type == "UVMAP":
            uv_name = getattr(item, "uv_map", "") or ""
        elif item.type == "ATTRIBUTE":
            uv_name = getattr(item, "attribute_name", "") or ""
        if uv_name:
            return int(uv_slot_by_name.get(uv_name, 0))

        for input_socket in getattr(item, "inputs", ()):
            if not input_socket.is_linked:
                continue
            stack.extend(link.from_node for link in input_socket.links)

    return 0


def _texture_info_tuple(node, slot: int) -> tuple:
    sampler = _sampler_tuple(node)
    transform = _texture_transform_tuple(node, slot)
    texture_extra = _assetkit_json_prop(node, "assetkit_texture_extra_json")
    texref_extra = _assetkit_json_prop(node, "assetkit_texture_ref_extra_json")
    image_extra = _assetkit_json_prop(node, "assetkit_texture_image_extra_json")
    sampler_extra = _assetkit_json_prop(node, "assetkit_texture_sampler_extra_json")
    if (
        texture_extra is None
        and texref_extra is None
        and image_extra is None
        and sampler_extra is None
    ):
        return sampler + (transform,)
    return sampler + (transform, texture_extra, texref_extra, image_extra, sampler_extra)


def _sampler_tuple(node) -> tuple[int, int, int, int, int, int]:
    if any(
        key in node
        for key in (
            "assetkit_texture_wrap_s",
            "assetkit_texture_wrap_t",
            "assetkit_texture_wrap_p",
            "assetkit_texture_min_filter",
            "assetkit_texture_mag_filter",
            "assetkit_texture_mip_filter",
        )
    ):
        wrap_s = _node_int_prop(node, "assetkit_texture_wrap_s", _AK_WRAP_REPEAT)
        wrap_t = _node_int_prop(node, "assetkit_texture_wrap_t", _AK_WRAP_REPEAT)
        wrap_p = _node_int_prop(node, "assetkit_texture_wrap_p", wrap_t)
        min_filter = _node_int_prop(node, "assetkit_texture_min_filter", 0)
        mag_filter = _node_int_prop(node, "assetkit_texture_mag_filter", _AK_MAGFILTER_LINEAR)
        mip_filter = _node_int_prop(node, "assetkit_texture_mip_filter", 0)
        return int(wrap_s), int(wrap_t), int(wrap_p), int(min_filter), int(mag_filter), int(mip_filter)

    extension = getattr(node, "extension", "REPEAT")
    if extension in {"EXTEND", "CLIP"}:
        wrap_s = _AK_WRAP_CLAMP
    elif extension == "MIRROR":
        wrap_s = _AK_WRAP_MIRROR
    else:
        wrap_s = _AK_WRAP_REPEAT
    wrap_t = wrap_s
    wrap_p = wrap_t

    interpolation = getattr(node, "interpolation", "Linear")
    if interpolation == "Closest":
        min_filter = _AK_MINFILTER_NEAREST_MIPMAP_NEAREST
        mag_filter = _AK_MAGFILTER_NEAREST
    else:
        min_filter = _AK_MINFILTER_LINEAR_MIPMAP_LINEAR
        mag_filter = _AK_MAGFILTER_LINEAR

    return int(wrap_s), int(wrap_t), int(wrap_p), int(min_filter), int(mag_filter), 0


def _texture_transform_tuple(node, slot: int) -> tuple | None:
    vector = node.inputs.get("Vector")
    mapping = _previous_node(vector)
    if mapping is None or mapping.type != "MAPPING":
        return None

    vector_type = getattr(mapping, "vector_type", "POINT")
    if vector_type not in {"TEXTURE", "POINT", "VECTOR"}:
        return None

    rotation = mapping.inputs.get("Rotation")
    location = mapping.inputs.get("Location")
    scale = mapping.inputs.get("Scale")
    if rotation is None or scale is None:
        return None
    rot = rotation.default_value
    if abs(float(rot[0])) > 1.0e-5 or abs(float(rot[1])) > 1.0e-5:
        return None

    offset_x = 0.0
    offset_y = 0.0
    if vector_type != "VECTOR" and location is not None:
        offset_x = float(location.default_value[0])
        offset_y = float(location.default_value[1])
    mapping_transform = (
        offset_x,
        offset_y,
        float(rot[2]),
        float(scale.default_value[0]),
        float(scale.default_value[1]),
    )
    if vector_type == "TEXTURE":
        mapping_transform = _inverted_trs_mapping_node(mapping_transform)
        if mapping_transform is None:
            return None
    elif vector_type == "VECTOR":
        mapping_transform = (0.0, 0.0, mapping_transform[2], mapping_transform[3], mapping_transform[4])

    off_x, off_y, rot_z, scale_x, scale_y = _texture_transform_blender_to_gltf(mapping_transform)
    if (
        abs(off_x) <= 1.0e-6
        and abs(off_y) <= 1.0e-6
        and abs(rot_z) <= 1.0e-6
        and abs(scale_x - 1.0) <= 1.0e-6
        and abs(scale_y - 1.0) <= 1.0e-6
        and not _mapping_has_texture_transform_animation(mapping)
    ):
        return None
    return float(off_x), float(off_y), float(rot_z), float(scale_x), float(scale_y), int(slot)


def _mapping_has_texture_transform_animation(mapping) -> bool:
    node_tree = getattr(mapping, "id_data", None)
    anim_data = getattr(node_tree, "animation_data", None) if node_tree is not None else None
    action = getattr(anim_data, "action", None) if anim_data is not None else None
    if action is None:
        return False

    paths = set()
    for name in ("Location", "Rotation", "Scale"):
        socket = mapping.inputs.get(name)
        if socket is not None:
            paths.add(socket.path_from_id("default_value"))
    if not paths:
        return False

    for curve in _iter_action_fcurves(action, animation_action_slot(anim_data)):
        if curve.data_path in paths:
            return True
    return False


def _previous_node(socket):
    if socket is None or not socket.is_linked:
        return None
    link = socket.links[0]
    node = link.from_node
    while node is not None and node.type == "REROUTE":
        reroute_input = node.inputs[0] if node.inputs else None
        if reroute_input is None or not reroute_input.is_linked:
            return None
        node = reroute_input.links[0].from_node
    return node


def _inverted_trs_mapping_node(mapping_transform: tuple[float, float, float, float, float]) -> tuple | None:
    offset_x, offset_y, rotation, scale_x, scale_y = mapping_transform
    if abs(rotation) > 1.0e-5 and abs(scale_x - scale_y) > 1.0e-5:
        return None
    if abs(scale_x) < 1.0e-5 or abs(scale_y) < 1.0e-5:
        return None

    cos_r = math.cos(-rotation)
    sin_r = math.sin(-rotation)
    x = -offset_x
    y = -offset_y
    new_x = cos_r * x - sin_r * y
    new_y = sin_r * x + cos_r * y
    return new_x / scale_x, new_y / scale_y, -rotation, 1.0 / scale_x, 1.0 / scale_y


def _texture_transform_blender_to_gltf(
    mapping_transform: tuple[float, float, float, float, float],
) -> tuple[float, float, float, float, float]:
    offset_x, offset_y, rotation, scale_x, scale_y = mapping_transform
    return (
        offset_x - scale_y * math.sin(rotation),
        1.0 - offset_y - scale_y * math.cos(rotation),
        rotation,
        scale_x,
        scale_y,
    )


def _texture_output_channel(socket) -> int:
    identifier = getattr(socket, "identifier", "") or getattr(socket, "name", "")
    if identifier in {"Alpha", "A"}:
        return 3
    if identifier in {"Green", "G"}:
        return 1
    if identifier in {"Blue", "B"}:
        return 2
    return 0


def _prop_str(material: bpy.types.Material, key: str) -> str:
    value = material.get(key, "")
    return str(value) if value else ""


def _prop_float(material: bpy.types.Material, key: str, default: float) -> float:
    value = material.get(key, None)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _prop_color_values(
    material: bpy.types.Material,
    key: str,
    default: tuple[float, float, float, float],
) -> array:
    value = material.get(key, None)
    if value is None:
        color = default
    else:
        try:
            color = tuple(float(c) for c in value)
        except (TypeError, ValueError):
            color = default
    if len(color) < 4:
        color = (*color[:3], default[3])
    return array("f", (float(c) for c in color[:4]))


def _prop_texture_slot(material: bpy.types.Material, role: str) -> int:
    return int(_prop_float(material, f"assetkit_texture_{role}_slot", 0.0))


def _prop_texture_info_tuple(material: bpy.types.Material, role: str) -> tuple | None:
    prefix = f"assetkit_texture_{role}"
    wrap_s = int(_prop_float(material, f"{prefix}_wrap_s", _AK_WRAP_REPEAT))
    wrap_t = int(_prop_float(material, f"{prefix}_wrap_t", _AK_WRAP_REPEAT))
    wrap_p = int(_prop_float(material, f"{prefix}_wrap_p", wrap_t))
    min_filter = int(_prop_float(material, f"{prefix}_min_filter", 0))
    mag_filter = int(_prop_float(material, f"{prefix}_mag_filter", _AK_MAGFILTER_LINEAR))
    mip_filter = int(_prop_float(material, f"{prefix}_mip_filter", 0))
    slot = _prop_texture_slot(material, role)
    transform = None
    if (
        f"{prefix}_transform_offset" in material
        or f"{prefix}_transform_scale" in material
        or f"{prefix}_transform_rotation" in material
    ):
        offset = _prop_vec(material, f"{prefix}_transform_offset", (0.0, 0.0), 2)
        scale = _prop_vec(material, f"{prefix}_transform_scale", (1.0, 1.0), 2)
        rotation = _prop_float(material, f"{prefix}_transform_rotation", 0.0)
        transform = (
            float(offset[0]),
            float(offset[1]),
            float(rotation),
            float(scale[0]),
            float(scale[1]),
            int(slot),
        )
    texture_extra = _assetkit_json_prop(material, f"{prefix}_texture_extra_json")
    texref_extra = _assetkit_json_prop(material, f"{prefix}_texref_extra_json")
    image_extra = _assetkit_json_prop(material, f"{prefix}_image_extra_json")
    sampler_extra = _assetkit_json_prop(material, f"{prefix}_sampler_extra_json")
    if (
        wrap_s == _AK_WRAP_REPEAT
        and wrap_t == _AK_WRAP_REPEAT
        and wrap_p == _AK_WRAP_REPEAT
        and min_filter == 0
        and mag_filter == _AK_MAGFILTER_LINEAR
        and mip_filter == 0
        and transform is None
        and texture_extra is None
        and texref_extra is None
        and image_extra is None
        and sampler_extra is None
    ):
        return None
    if (
        texture_extra is None
        and texref_extra is None
        and image_extra is None
        and sampler_extra is None
    ):
        return wrap_s, wrap_t, wrap_p, min_filter, mag_filter, mip_filter, transform
    return (
        wrap_s, wrap_t, wrap_p,
        min_filter, mag_filter, mip_filter,
        transform,
        texture_extra, texref_extra, image_extra, sampler_extra,
    )


def _node_int_prop(node, key: str, default: int) -> int:
    try:
        value = node.get(key, default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _prop_vec(
    material: bpy.types.Material,
    key: str,
    default: tuple[float, ...],
    size: int,
) -> tuple[float, ...]:
    value = material.get(key, None)
    if value is None:
        return default
    try:
        vals = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        return default
    if len(vals) < size:
        return (*vals, *default[len(vals):size])
    return vals[:size]


def _socket_float(node, identifier: str, default: float) -> float:
    value = _socket_default(node, identifier)
    if value is None:
        return float(default)
    return float(value)


def _socket_float_from_socket(socket, default: float) -> float:
    if socket is None or socket.is_linked:
        return float(default)
    return float(getattr(socket, "default_value", default))


def _scalar_texture_payload(
    socket,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
    *,
    default: float,
    linked_default: float,
    scale: float = 1.0,
    target_channel: int | None = None,
    name: str | None = None,
) -> tuple[float, str | None, int, tuple | None]:
    image, channel, slot, info = _linked_texture_info(socket, uv_slot_by_name)
    uri = None
    if image is not None:
        if target_channel is not None and channel != 0 and channel != target_channel:
            uri = image_store.channel_path(
                image,
                channel,
                target_channel,
                name or image.name,
            )
        else:
            uri = image_store.path_for(image)
    if socket is not None and not socket.is_linked:
        value = float(getattr(socket, "default_value", default))
    elif uri is not None:
        value = float(linked_default)
    else:
        value = float(default)
    value *= float(scale)
    if value > 1.0 and scale != 1.0:
        value = 1.0
    return value, uri, int(slot), info


def _scalar_texture_payload_first(
    material: bpy.types.Material,
    socket_names: tuple[str, ...],
    role: str,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
    *,
    default: float,
    linked_default: float,
    target_channel: int | None = None,
) -> tuple[float, str | None, int, tuple | None]:
    socket = None
    for name in socket_names:
        socket = _material_input_socket(material, name)
        if socket is not None:
            break

    payload = _scalar_texture_payload(
        socket,
        image_store,
        uv_slot_by_name,
        default=default,
        linked_default=linked_default,
        target_channel=target_channel,
        name=f"{material.name}_{role}",
    )
    if payload[1] is not None:
        return payload

    texture = _prop_str(material, f"assetkit_{role}_texture")
    if not texture:
        return payload

    value = payload[0]
    if abs(float(value) - float(default)) <= 1.0e-6:
        value = linked_default
    return (
        float(value),
        texture,
        _prop_texture_slot(material, role),
        _prop_texture_info_tuple(material, role),
    )


def _color_texture_payload(
    socket,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
    *,
    default: tuple[float, float, float, float],
    name: str | None = None,
) -> tuple[object, str | None, int, tuple | None]:
    image, channel, slot, info = _linked_texture_info(socket, uv_slot_by_name)
    if image is None:
        uri = None
    elif channel != 0:
        uri = image_store.rgb_channel_path(image, channel, name or image.name)
    else:
        uri = image_store.path_for(image)
    return _color_socket_values(socket, default), uri, int(slot), info


def _specular_glossiness_payload(
    specular_socket,
    roughness_socket,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
    *,
    name: str,
) -> tuple[
    tuple[object, str | None, int, tuple | None],
    tuple[float, str | None, int, tuple | None],
]:
    specular_color = _color_socket_values(specular_socket, (1.0, 1.0, 1.0, 1.0))
    spec_image, spec_channel, spec_slot, spec_info = _linked_texture_info(specular_socket, uv_slot_by_name)
    gloss_image, gloss_channel, gloss_slot, gloss_info = _linked_texture_info(roughness_socket, uv_slot_by_name)

    if roughness_socket is not None and not roughness_socket.is_linked:
        roughness = float(getattr(roughness_socket, "default_value", 0.0))
        glossiness = 1.0 - roughness
    else:
        glossiness = 1.0
    glossiness = _clamp01(glossiness)

    if spec_image is None and gloss_image is None:
        return (
            (specular_color, None, 0, None),
            (glossiness, None, 0, None),
        )

    if (
        spec_image is not None
        and gloss_image is not None
        and spec_image == gloss_image
        and spec_channel == 0
        and gloss_channel == 3
    ):
        uri = image_store.path_for(spec_image)
    else:
        uri = image_store.specular_glossiness_path(
            spec_image,
            spec_channel,
            gloss_image,
            gloss_channel,
            specular_color,
            glossiness,
            name,
        )

    slot = spec_slot if spec_image is not None else gloss_slot
    info = spec_info if spec_image is not None else gloss_info
    return (
        (specular_color, uri, int(slot), info),
        (glossiness, uri, int(slot), info),
    )


def _color_socket_values(socket, default: tuple[float, float, float, float]) -> array:
    if socket is not None and not socket.is_linked:
        value = getattr(socket, "default_value", default)
        color = [float(v) for v in value[:4]]
    else:
        color = [float(v) for v in default[:4]]
    while len(color) < 4:
        color.append(1.0)
    return array("f", (_clamp01(v) for v in color[:4]))


def _float_payload_view(payload: object):
    try:
        view = memoryview(payload)
    except TypeError:
        return ()
    if view.nbytes < 4:
        return ()
    if view.format == "f" and view.itemsize == 4:
        return view
    try:
        return view.cast("f")
    except TypeError:
        return ()


def _scalar_texture_used(payload: tuple[float, str | None, int, tuple | None], default: float) -> bool:
    return abs(float(payload[0]) - float(default)) > 1.0e-6 or payload[1] is not None


def _color_texture_used(payload: tuple[object, str | None, int, tuple | None], default: float) -> bool:
    if payload[1] is not None:
        return True
    vals = _float_payload_view(payload[0])
    return any(abs(float(vals[i]) - float(default)) > 1.0e-6 for i in range(min(3, len(vals))))


def _normal_texture_info(
    socket,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
) -> tuple[str | None, int, float, tuple | None]:
    image, _channel, slot, info = _linked_texture_info(socket, uv_slot_by_name)
    path = image_store.path_for(image) if image else None
    scale = 1.0

    if socket is not None and socket.is_linked:
        for link in socket.links:
            node = link.from_node
            if node.type != "NORMAL_MAP":
                continue
            strength = node.inputs.get("Strength")
            if strength is not None and not strength.is_linked:
                scale = float(strength.default_value)
            break

    return path, slot, scale, info


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
