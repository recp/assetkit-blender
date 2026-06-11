from __future__ import annotations

import json
import math
from array import array

import bpy

from ..assetkit import _native_module
from ..enums import (
    AK_INTERPOLATION_LINEAR,
    AK_INTERPOLATION_STEP,
    AKB_ANIM_MATERIAL_BASE_COLOR,
    AKB_ANIM_MATERIAL_EMISSIVE_COLOR,
    AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH,
    AKB_ANIM_MATERIAL_IOR,
    AKB_ANIM_MATERIAL_METALLIC,
    AKB_ANIM_MATERIAL_ROUGHNESS,
)
from .images import _ExportImageStore

_AK_WRAP_REPEAT = 1
_AK_WRAP_MIRROR = 2
_AK_WRAP_CLAMP = 3
_AK_MINFILTER_LINEAR_MIPMAP_LINEAR = 3
_AK_MINFILTER_NEAREST_MIPMAP_NEAREST = 4
_AK_MAGFILTER_LINEAR = 0
_AK_MAGFILTER_NEAREST = 1

_FEATURE_CLEARCOAT = 1
_FEATURE_SPECULAR = 2
_FEATURE_SPECULAR_GLOSSINESS = 3
_FEATURE_TRANSMISSION = 4
_FEATURE_SHEEN = 5
_FEATURE_IRIDESCENCE = 6
_FEATURE_VOLUME = 7
_FEATURE_ANISOTROPY = 8
_FEATURE_DISPERSION = 9
_FEATURE_DIFFUSE_TRANSMISSION = 10
_FEATURE_SUBSURFACE = 11
_FEATURE_IOR = 100

_MATERIAL_TYPE_UNLIT = 4
_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS = 6
_ANIM_TEXTURE_TRANSFORM_BASE = 1000
_ANIM_TEXTURE_TRANSFORM_STRIDE = 4
_ANIM_TEXTURE_TRANSFORM_OFFSET = 0
_ANIM_TEXTURE_TRANSFORM_SCALE = 1
_ANIM_TEXTURE_TRANSFORM_ROTATION = 2
_ANIM_TEXTURE_TRANSFORM_ROLES = (
    "base_color",
    "metallic_roughness",
    "occlusion",
    "normal",
    "emissive",
    "transparent",
    "specular",
    "specular_color",
    "clearcoat",
    "clearcoat_roughness",
    "clearcoat_normal",
    "transmission",
    "sheen_color",
    "sheen_roughness",
    "iridescence",
    "iridescence_thickness",
    "volume_thickness",
    "anisotropy",
    "diffuse_transmission",
    "diffuse_transmission_color",
)


def _material_tuple(
    material: bpy.types.Material | None,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int] | None = None,
    fps: float = 24.0,
    *,
    context: bpy.types.Context | None = None,
    obj: bpy.types.Object | None = None,
    mesh: bpy.types.Mesh | None = None,
    material_index: int = -1,
    material_export_mode: str = "AUTO",
    material_bake_size: int = 1024,
) -> tuple | None:
    if material is None:
        return None

    base_color = [float(c) for c in material.diffuse_color]
    metallic = 0.0
    roughness = 1.0
    alpha = base_color[3] if len(base_color) > 3 else 1.0
    base_color_texture = None
    base_color_slot = 0
    base_color_info = None
    metallic_texture = None
    metallic_slot = 0
    metallic_info = None
    roughness_texture = None
    roughness_slot = 0
    roughness_info = None
    normal_texture = None
    normal_slot = 0
    normal_info = None
    metallic_image = None
    roughness_image = None
    metallic_channel = 0
    roughness_channel = 0
    alpha_image = None
    alpha_channel = 0
    alpha_slot = 0
    alpha_info = None
    opacity_texture = None
    opacity_slot = 0
    opacity_info = None
    normal_scale = 1.0
    opacity_inverted = bool(material.get("assetkit_transparent_inverted", False))
    opacity_baked = False
    occlusion_image = None
    occlusion_channel = 0
    occlusion_texture = None
    occlusion_slot = 0
    occlusion_info = None
    occlusion_strength = 1.0
    emissive_color = [0.0, 0.0, 0.0, 1.0]
    emissive_texture = None
    emissive_slot = 0
    emissive_info = None
    emissive_strength = 1.0
    features: list[tuple] = []
    uv_slot_by_name = uv_slot_by_name or {}
    bsdf = None
    unlit_emission = None
    baked_base_color_texture = None
    baked_visual_only = False

    if (
        context is not None
        and obj is not None
        and mesh is not None
        and material_index >= 0
        and _material_bake_required(material, material_export_mode)
    ):
        baked_visual_only = not _material_surface_extractable(material)
        baked_base_color_texture = image_store.shader_bake_path(
            context,
            obj,
            mesh,
            material,
            int(material_index),
            int(material_bake_size),
            f"{obj.name}_{material.name}",
            _bake_uv_key(uv_slot_by_name),
        )

    if material.use_nodes and material.node_tree and not baked_visual_only:
        bsdf = _principled_bsdf(material)
        unlit_emission = _unlit_emission_node(material)
        if bsdf is not None:
            base_color_image, base_color_channel, base_color_slot, base_color_info = _linked_texture_info(
                bsdf.inputs.get("Base Color"),
                uv_slot_by_name,
            )
            alpha_image, alpha_channel, alpha_slot, alpha_info = _linked_texture_info(
                bsdf.inputs.get("Alpha"),
                uv_slot_by_name,
            )
            metallic_image, metallic_channel, metallic_slot, metallic_info = _linked_texture_info(
                bsdf.inputs.get("Metallic"),
                uv_slot_by_name,
            )
            roughness_image, roughness_channel, roughness_slot, roughness_info = _linked_texture_info(
                bsdf.inputs.get("Roughness"),
                uv_slot_by_name,
            )
            emissive_image, emissive_channel, emissive_slot, emissive_info = _linked_texture_info(
                bsdf.inputs.get("Emission Color"),
                uv_slot_by_name,
            )
            if alpha_image is not None and (alpha_image != base_color_image or opacity_inverted):
                base_color_texture = image_store.base_color_alpha_path(
                    base_color_image,
                    base_color_channel,
                    alpha_image,
                    alpha_channel,
                    material.name,
                    opacity_inverted,
                )
                opacity_baked = True
                base_color_info = base_color_info or alpha_info
            elif base_color_image is not None:
                if base_color_channel != 0:
                    base_color_texture = image_store.rgb_channel_path(
                        base_color_image,
                        base_color_channel,
                        f"{material.name}_baseColor",
                    )
                else:
                    base_color_texture = image_store.path_for(base_color_image)
            metallic_texture = image_store.path_for(metallic_image) if metallic_image else None
            roughness_texture = image_store.path_for(roughness_image) if roughness_image else None
            normal_texture, normal_slot, normal_scale, normal_info = _normal_texture_info(
                bsdf.inputs.get("Normal"),
                image_store,
                uv_slot_by_name,
            )
            if emissive_image is not None:
                if emissive_channel != 0:
                    emissive_texture = image_store.rgb_channel_path(
                        emissive_image,
                        emissive_channel,
                        f"{material.name}_emissive",
                    )
                else:
                    emissive_texture = image_store.path_for(emissive_image)
            color = _socket_default(bsdf, "Base Color")
            if color is not None:
                base_color = [float(c) for c in color[:4]]
                alpha = base_color[3] if len(base_color) > 3 else alpha
            elif base_color_image is not None:
                base_color = [1.0, 1.0, 1.0, alpha]
            emission_color = _socket_default(bsdf, "Emission Color")
            if emission_color is not None:
                emissive_color = [float(c) for c in emission_color[:4]]
                if len(emissive_color) < 4:
                    emissive_color.append(1.0)
            emission_strength = _socket_default(bsdf, "Emission Strength")
            if emission_strength is not None:
                emissive_strength = max(float(emission_strength), 0.0)
                if (
                    "assetkit_emissive_strength" in material
                    and (emissive_strength <= 1.0e-6 or abs(emissive_strength - 1.0) <= 1.0e-6)
                ):
                    emissive_strength = max(_prop_float(material, "assetkit_emissive_strength", 1.0), 0.0)
            elif "assetkit_emissive_strength" in material:
                emissive_strength = max(_prop_float(material, "assetkit_emissive_strength", 1.0), 0.0)
            alpha_value = _socket_default(bsdf, "Alpha")
            if alpha_value is not None:
                alpha = float(alpha_value)
                if len(base_color) < 4:
                    base_color.append(alpha)
                else:
                    base_color[3] = alpha
            metallic_value = _socket_default(bsdf, "Metallic")
            if metallic_value is not None:
                metallic = float(metallic_value)
            elif metallic_image is not None:
                metallic = 1.0
            roughness_value = _socket_default(bsdf, "Roughness")
            if roughness_value is not None:
                roughness = float(roughness_value)
            elif roughness_image is not None:
                roughness = 1.0
            features = _material_feature_tuples(bsdf, material, image_store, uv_slot_by_name)
        elif unlit_emission is not None:
            base_color_image, base_color_channel, base_color_slot, base_color_info = _linked_texture_info(
                unlit_emission.inputs.get("Color"),
                uv_slot_by_name,
            )
            if base_color_image is not None:
                if base_color_channel != 0:
                    base_color_texture = image_store.rgb_channel_path(
                        base_color_image,
                        base_color_channel,
                        f"{material.name}_baseColor",
                    )
                else:
                    base_color_texture = image_store.path_for(base_color_image)
                base_color = [1.0, 1.0, 1.0, alpha]
            else:
                color = _socket_default(unlit_emission, "Color")
                if color is not None:
                    base_color = [float(c) for c in color[:4]]
                    alpha = base_color[3] if len(base_color) > 3 else alpha

        if alpha_image is not None and base_color_texture is not None:
            opacity_texture = base_color_texture
            opacity_slot = base_color_slot if base_color_image is not None else alpha_slot
            opacity_info = base_color_info if base_color_image is not None else alpha_info

        occlusion_socket = _material_input_socket(material, "Occlusion")
        if occlusion_socket is not None:
            occlusion_image, occlusion_channel, occlusion_slot, occlusion_info = _linked_texture_info(
                occlusion_socket,
                uv_slot_by_name,
            )
            if occlusion_image is not None:
                if occlusion_channel == 0:
                    occlusion_texture = image_store.path_for(occlusion_image)
                else:
                    occlusion_texture = image_store.channel_path(
                        occlusion_image,
                        occlusion_channel,
                        0,
                        f"{material.name}_occlusion",
                    )
            value = getattr(occlusion_socket, "default_value", None)
            if value is not None and not occlusion_socket.is_linked:
                occlusion_strength = _clamp01(float(value))

    if baked_base_color_texture is not None:
        base_color_texture = baked_base_color_texture
        base_color_slot = 0
        base_color_info = None
        base_color = [1.0, 1.0, 1.0, alpha]
        if opacity_texture == base_color_texture:
            opacity_texture = None
            opacity_info = None
            opacity_slot = 0

    if len(base_color) < 4:
        base_color = [*base_color[:3], alpha]
    base_color = [_clamp01(v) for v in base_color[:4]]
    emissive_color = [_clamp01(v) for v in emissive_color[:4]]
    if emissive_texture:
        if emissive_color[:3] == [0.0, 0.0, 0.0]:
            emissive_color = [1.0, 1.0, 1.0, emissive_color[3]]
    elif emissive_strength <= 0.0:
        emissive_color = [0.0, 0.0, 0.0, emissive_color[3]]
        emissive_strength = 1.0
    metallic = _clamp01(metallic)
    roughness = _clamp01(roughness)
    alpha = base_color[3]

    alpha_mode = 0
    alpha_cutoff = 0.5
    blend_method = getattr(material, "blend_method", "OPAQUE")
    if blend_method == "CLIP":
        alpha_mode = 2
        alpha_cutoff = float(getattr(material, "alpha_threshold", 0.5))
    elif alpha_image is not None:
        alpha_mode = 1
    elif alpha < 1.0:
        alpha_mode = 1

    double_sided = not bool(getattr(material, "use_backface_culling", False))
    color = array("f", base_color)
    emissive = array("f", emissive_color)
    needs_mr_pack = False
    if (
        metallic_texture is not None
        and metallic_texture == roughness_texture
        and metallic_channel == 2
        and roughness_channel == 1
    ):
        metallic_roughness_texture = metallic_texture
        metallic_roughness_slot = roughness_slot if roughness_image is not None else metallic_slot
        metallic_roughness_info = roughness_info if roughness_image is not None else metallic_info
    elif metallic_texture is not None or roughness_texture is not None:
        needs_mr_pack = True
        metallic_roughness_texture = None
        metallic_roughness_slot = roughness_slot if roughness_image is not None else metallic_slot
        metallic_roughness_info = roughness_info if roughness_image is not None else metallic_info
    else:
        metallic_roughness_texture = None
        metallic_roughness_slot = 0
        metallic_roughness_info = None

    if metallic_roughness_texture is None and needs_mr_pack:
        metallic_roughness_texture = image_store.metallic_roughness_path(
            None,
            0,
            metallic_image,
            metallic_channel,
            roughness_image,
            roughness_channel,
            metallic,
            roughness,
            material.name,
        )
        metallic_roughness_slot = roughness_slot if roughness_image is not None else metallic_slot

    material_type = _material_type(material, bsdf, unlit_emission)
    if baked_base_color_texture is not None and bsdf is None:
        material_type = _MATERIAL_TYPE_UNLIT
    animations = _material_animation_payload(material, bsdf, base_color, fps)

    return (
        material.name,
        color.tobytes(),
        metallic,
        roughness,
        alpha_mode,
        alpha_cutoff,
        double_sided,
        base_color_texture,
        int(base_color_slot),
        opacity_texture,
        int(opacity_slot),
        metallic_roughness_texture,
        int(metallic_roughness_slot),
        normal_texture,
        int(normal_slot),
        float(normal_scale),
        occlusion_texture,
        int(occlusion_slot),
        float(occlusion_strength),
        emissive.tobytes(),
        emissive_texture,
        int(emissive_slot),
        float(emissive_strength),
        base_color_info,
        opacity_info,
        metallic_roughness_info,
        normal_info,
        occlusion_info,
        emissive_info,
        int(material_type),
        bool(opacity_inverted and not opacity_baked),
        tuple(features),
        animations,
        _assetkit_json_prop(material, "assetkit_material_extra_json"),
    )


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
    if mode == "DIRECT":
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

    fcurves = tuple(_iter_action_fcurves(action))
    if not fcurves:
        return None

    channels: list[tuple] = []
    base_channel = _base_color_animation_channel(bsdf, fcurves, base_color, fps)
    if base_channel:
        channels.append(base_channel)
    channels.extend(_principled_material_animation_channels(bsdf, fcurves, fps))
    channels.extend(_texture_transform_animation_channels(material, fcurves, fps))
    return tuple(channels) if channels else None


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
    return int(target), times.tobytes(), values.tobytes(), len(times), int(interpolation)


def _iter_action_fcurves(action: bpy.types.Action):
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None and len(fcurves) > 0:
        yield from fcurves
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except (AttributeError, TypeError, RuntimeError):
                    channelbag = None
                if channelbag is not None:
                    yield from getattr(channelbag, "fcurves", []) or []


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

    for curve in _iter_action_fcurves(action):
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


def _material_feature_tuples(
    bsdf,
    material: bpy.types.Material,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
) -> list[tuple]:
    features: list[tuple] = []
    material_type = int(_prop_float(material, "assetkit_material_type", 0.0))
    is_spec_gloss = material_type == _MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS

    ior = _socket_float(bsdf, "IOR", _prop_float(material, "assetkit_ior", 1.5))
    if not is_spec_gloss and ("assetkit_ior" in material or abs(ior - 1.5) > 1.0e-6):
        features.append((_FEATURE_IOR, float(ior)))

    clearcoat = _scalar_texture_payload(
        bsdf.inputs.get("Coat Weight"),
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=0,
        name=f"{material.name}_clearcoat",
    )
    clearcoat_roughness = _scalar_texture_payload(
        bsdf.inputs.get("Coat Roughness"),
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=1,
        name=f"{material.name}_clearcoatRoughness",
    )
    clearcoat_normal = _normal_texture_info(bsdf.inputs.get("Coat Normal"), image_store, uv_slot_by_name)
    clearcoat_active = (
        _scalar_texture_used(clearcoat, 0.0)
        or clearcoat_roughness[1] is not None
        or clearcoat_normal[0] is not None
    )
    if clearcoat_active:
        features.append((
            _FEATURE_CLEARCOAT,
            *clearcoat,
            *clearcoat_roughness,
            clearcoat_normal[0],
            int(clearcoat_normal[1]),
            float(clearcoat_normal[2]),
            clearcoat_normal[3],
        ))

    specular_factor = _scalar_texture_payload(
        bsdf.inputs.get("Specular IOR Level"),
        image_store,
        uv_slot_by_name,
        default=0.5,
        linked_default=0.5,
        scale=2.0,
        target_channel=3,
        name=f"{material.name}_specular",
    )
    specular_color = _color_texture_payload(
        bsdf.inputs.get("Specular Tint"),
        image_store,
        uv_slot_by_name,
        default=(1.0, 1.0, 1.0, 1.0),
        name=f"{material.name}_specularColor",
    )
    if is_spec_gloss:
        spec_gloss_specular, spec_gloss_glossiness = _specular_glossiness_payload(
            bsdf.inputs.get("Specular Tint"),
            bsdf.inputs.get("Roughness"),
            image_store,
            uv_slot_by_name,
            name=material.name,
        )
        features.append((
            _FEATURE_SPECULAR_GLOSSINESS,
            *_color_texture_payload(
                bsdf.inputs.get("Base Color"),
                image_store,
                uv_slot_by_name,
                default=(1.0, 1.0, 1.0, 1.0),
                name=f"{material.name}_specGlossDiffuse",
            ),
            *spec_gloss_specular,
            *spec_gloss_glossiness,
        ))
    elif _scalar_texture_used(specular_factor, 1.0) or _color_texture_used(specular_color, 1.0):
        features.append((
            _FEATURE_SPECULAR,
            *specular_factor,
            *specular_color,
        ))

    transmission = _scalar_texture_payload(
        bsdf.inputs.get("Transmission Weight"),
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=0,
        name=f"{material.name}_transmission",
    )
    transmission_used = _scalar_texture_used(transmission, 0.0)
    if transmission_used:
        features.append((_FEATURE_TRANSMISSION, *transmission))

    sheen_weight = _socket_float(bsdf, "Sheen Weight", 0.0)
    sheen_color = _color_texture_payload(
        bsdf.inputs.get("Sheen Tint"),
        image_store,
        uv_slot_by_name,
        default=(0.0, 0.0, 0.0, 1.0),
        name=f"{material.name}_sheenColor",
    )
    sheen_roughness = _scalar_texture_payload(
        bsdf.inputs.get("Sheen Roughness"),
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=3,
        name=f"{material.name}_sheenRoughness",
    )
    sheen_socket = bsdf.inputs.get("Sheen Weight")
    sheen_active = sheen_weight > 0.0 or (sheen_socket is not None and sheen_socket.is_linked)
    if sheen_active or sheen_color[1] is not None or sheen_roughness[1] is not None:
        features.append((
            _FEATURE_SHEEN,
            *sheen_color,
            *sheen_roughness,
        ))

    thin_film = _scalar_texture_payload_first(
        material,
        ("Thin Film Weight", "Iridescence Weight", "Iridescence", "Iridescence Factor"),
        "iridescence",
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=0,
    )
    thin_film_thickness = _scalar_texture_payload_first(
        material,
        ("Thin Film Thickness",),
        "iridescence_thickness",
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=_prop_float(material, "assetkit_iridescence_thickness_maximum", 400.0),
        target_channel=1,
    )
    thin_film_ior = _socket_float_from_socket(
        _material_input_socket(material, "Thin Film IOR"),
        _prop_float(material, "assetkit_iridescence_ior", 1.3),
    )
    thin_film_min = _socket_float_from_socket(
        _material_input_socket(material, "Iridescence Thickness Minimum"),
        _prop_float(material, "assetkit_iridescence_thickness_minimum", 100.0),
    )
    thin_film_max = _prop_float(material, "assetkit_iridescence_thickness_maximum", 400.0)
    if thin_film_thickness[0] > 0.0:
        thin_film_max = max(float(thin_film_thickness[0]), float(thin_film_min))
    thin_film_source_prop = any(
        key in material
        for key in (
            "assetkit_iridescence",
            "assetkit_iridescence_texture",
            "assetkit_iridescence_thickness_texture",
            "assetkit_iridescence_ior",
            "assetkit_iridescence_thickness_minimum",
            "assetkit_iridescence_thickness_maximum",
        )
    )
    thin_film_active = (
        _scalar_texture_used(thin_film, 0.0)
        or _scalar_texture_used(thin_film_thickness, 0.0)
        or (
            thin_film_source_prop
            and (
                abs(thin_film_ior - 1.3) > 1.0e-6
                or abs(thin_film_min - 100.0) > 1.0e-6
                or abs(thin_film_max - 400.0) > 1.0e-6
            )
        )
    )
    if thin_film_active:
        features.append((
            _FEATURE_IRIDESCENCE,
            *thin_film,
            *thin_film_thickness,
            float(thin_film_ior),
            float(thin_film_min),
            float(thin_film_max),
        ))

    volume_used = False
    thickness_socket = _material_input_socket(material, "Thickness")
    if transmission_used and thickness_socket is not None:
        thickness = _scalar_texture_payload(
            thickness_socket,
            image_store,
            uv_slot_by_name,
            default=0.0,
            linked_default=1.0,
            target_channel=1,
            name=f"{material.name}_volumeThickness",
        )
        attenuation_color = _color_socket_bytes(_material_input_socket(material, "Color"), (1.0, 1.0, 1.0, 1.0))
        density = _socket_float_from_socket(_material_input_socket(material, "Density"), 0.0)
        attenuation_distance = (1.0 / density) if density > 0.0 else float("inf")
        if _scalar_texture_used(thickness, 0.0):
            features.append((
                _FEATURE_VOLUME,
                *thickness,
                attenuation_color,
                float(attenuation_distance),
            ))
            volume_used = True

    custom_volume_thickness = _prop_float(material, "assetkit_volume_thickness", 0.0)
    custom_volume_texture = _prop_str(material, "assetkit_volume_thickness_texture")
    if not volume_used and (custom_volume_thickness > 0.0 or custom_volume_texture):
        features.append((
            _FEATURE_VOLUME,
            float(custom_volume_thickness if custom_volume_thickness > 0.0 else 1.0),
            custom_volume_texture,
            _prop_texture_slot(material, "volume_thickness"),
            _prop_texture_info_tuple(material, "volume_thickness"),
            _prop_color_bytes(material, "assetkit_volume_attenuation_color", (1.0, 1.0, 1.0, 1.0)),
            float(_prop_float(material, "assetkit_volume_attenuation_distance", float("inf"))),
        ))
        volume_used = True

    volume_absorption = _volume_absorption_node(material)
    if transmission_used and not volume_used and volume_absorption is not None:
        attenuation_color = _color_socket_bytes(
            volume_absorption.inputs.get("Color"),
            (1.0, 1.0, 1.0, 1.0),
        )
        density = _socket_float(volume_absorption, "Density", 0.0)
        attenuation_distance = (1.0 / density) if density > 0.0 else float("inf")
        features.append((
            _FEATURE_VOLUME,
            1.0,
            None,
            0,
            None,
            attenuation_color,
            float(attenuation_distance),
        ))
        volume_used = True

    anisotropy = _scalar_texture_payload(
        bsdf.inputs.get("Anisotropic"),
        image_store,
        uv_slot_by_name,
        default=0.0,
        linked_default=1.0,
        target_channel=2,
        name=f"{material.name}_anisotropy",
    )
    anisotropy_rotation = _socket_float(bsdf, "Anisotropic Rotation", 0.0) * (math.pi * 2.0)
    if (
        not _scalar_texture_used(anisotropy, 0.0)
        and ("assetkit_anisotropy" in material or "assetkit_anisotropy_texture" in material)
    ):
        anisotropy = (
            _prop_float(material, "assetkit_anisotropy", 0.0),
            _prop_str(material, "assetkit_anisotropy_texture"),
            _prop_texture_slot(material, "anisotropy"),
            _prop_texture_info_tuple(material, "anisotropy"),
        )
        anisotropy_rotation = _prop_float(material, "assetkit_anisotropy_rotation", anisotropy_rotation)
    if _scalar_texture_used(anisotropy, 0.0) or abs(anisotropy_rotation) > 1.0e-6:
        features.append((
            _FEATURE_ANISOTROPY,
            *anisotropy,
            float(anisotropy_rotation),
        ))

    dispersion = _socket_float_from_socket(_material_input_socket(material, "Dispersion"), 0.0)
    dispersion_used = False
    if volume_used and dispersion > 0.0:
        features.append((_FEATURE_DISPERSION, float(dispersion)))
        dispersion_used = True

    custom_dispersion = _prop_float(material, "assetkit_dispersion", 0.0)
    if volume_used and not dispersion_used:
        if dispersion > 0.0:
            features.append((_FEATURE_DISPERSION, float(dispersion)))
            dispersion_used = True
        elif custom_dispersion > 0.0:
            features.append((_FEATURE_DISPERSION, float(custom_dispersion)))
            dispersion_used = True

    diffuse_transmission = _prop_float(material, "assetkit_diffuse_transmission", 0.0)
    diffuse_transmission_texture = _prop_str(material, "assetkit_diffuse_transmission_texture")
    diffuse_transmission_color_texture = _prop_str(material, "assetkit_diffuse_transmission_color_texture")
    diffuse_transmission_color = _prop_color_bytes(
        material,
        "assetkit_diffuse_transmission_color",
        (1.0, 1.0, 1.0, 1.0),
    )
    if (
        diffuse_transmission > 0.0
        or diffuse_transmission_texture
        or diffuse_transmission_color_texture
    ):
        features.append((
            _FEATURE_DIFFUSE_TRANSMISSION,
            float(diffuse_transmission if diffuse_transmission > 0.0 else 1.0),
            diffuse_transmission_texture,
            _prop_texture_slot(material, "diffuse_transmission"),
            _prop_texture_info_tuple(material, "diffuse_transmission"),
            diffuse_transmission_color,
            diffuse_transmission_color_texture,
            _prop_texture_slot(material, "diffuse_transmission_color"),
            _prop_texture_info_tuple(material, "diffuse_transmission_color"),
        ))

    volume_scatter_color = _prop_color_bytes(
        material,
        "assetkit_volume_scatter_multiscatter_color",
        (0.0, 0.0, 0.0, 1.0),
    )
    volume_scatter_anisotropy = _prop_float(material, "assetkit_volume_scatter_anisotropy", 0.0)
    volume_scatter_values = array("f")
    volume_scatter_values.frombytes(volume_scatter_color)
    custom_scatter_used = (
        volume_scatter_anisotropy != 0.0
        or any(abs(float(value)) > 1.0e-6 for value in volume_scatter_values[:3])
    )
    if custom_scatter_used:
        features.append((
            _FEATURE_SUBSURFACE,
            0.0,
            volume_scatter_color,
            array("f", [0.0, 0.0, 0.0, 1.0]).tobytes(),
            float(volume_scatter_anisotropy),
        ))
    elif (volume_scatter := _volume_scatter_node(material)) is not None:
        scatter_color = _color_socket_bytes(
            volume_scatter.inputs.get("Color"),
            (0.0, 0.0, 0.0, 1.0),
        )
        scatter_values = array("f")
        scatter_values.frombytes(scatter_color)
        scatter_anisotropy = _socket_float(volume_scatter, "Anisotropy", 0.0)
        if scatter_anisotropy != 0.0 or any(abs(float(value)) > 1.0e-6 for value in scatter_values[:3]):
            features.append((
                _FEATURE_SUBSURFACE,
                0.0,
                scatter_color,
                array("f", [0.0, 0.0, 0.0, 1.0]).tobytes(),
                float(scatter_anisotropy),
            ))
            custom_scatter_used = True

    subsurface_weight = _socket_float(bsdf, "Subsurface Weight", 0.0)
    if subsurface_weight > 0.0 and not custom_scatter_used:
        radius = _socket_default(bsdf, "Subsurface Radius")
        radius_bytes = array("f", [
            float(radius[0]) if radius is not None and len(radius) > 0 else 1.0,
            float(radius[1]) if radius is not None and len(radius) > 1 else 0.2,
            float(radius[2]) if radius is not None and len(radius) > 2 else 0.1,
            1.0,
        ]).tobytes()
        features.append((
            _FEATURE_SUBSURFACE,
            float(subsurface_weight),
            _color_socket_bytes(bsdf.inputs.get("Base Color"), (1.0, 1.0, 1.0, 1.0)),
            radius_bytes,
            float(_socket_float(bsdf, "Subsurface Anisotropy", 0.0)),
        ))

    return features


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


def _prop_color_bytes(
    material: bpy.types.Material,
    key: str,
    default: tuple[float, float, float, float],
) -> bytes:
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
    return array("f", [float(c) for c in color[:4]]).tobytes()


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
) -> tuple[bytes, str | None, int, tuple | None]:
    image, channel, slot, info = _linked_texture_info(socket, uv_slot_by_name)
    if image is None:
        uri = None
    elif channel != 0:
        uri = image_store.rgb_channel_path(image, channel, name or image.name)
    else:
        uri = image_store.path_for(image)
    return _color_socket_bytes(socket, default), uri, int(slot), info


def _specular_glossiness_payload(
    specular_socket,
    roughness_socket,
    image_store: _ExportImageStore,
    uv_slot_by_name: dict[str, int],
    *,
    name: str,
) -> tuple[
    tuple[bytes, str | None, int, tuple | None],
    tuple[float, str | None, int, tuple | None],
]:
    specular_color = _color_socket_bytes(specular_socket, (1.0, 1.0, 1.0, 1.0))
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


def _color_socket_bytes(socket, default: tuple[float, float, float, float]) -> bytes:
    if socket is not None and not socket.is_linked:
        value = getattr(socket, "default_value", default)
        color = [float(v) for v in value[:4]]
    else:
        color = [float(v) for v in default[:4]]
    while len(color) < 4:
        color.append(1.0)
    return array("f", [_clamp01(v) for v in color[:4]]).tobytes()


def _scalar_texture_used(payload: tuple[float, str | None, int, tuple | None], default: float) -> bool:
    return abs(float(payload[0]) - float(default)) > 1.0e-6 or payload[1] is not None


def _color_texture_used(payload: tuple[bytes, str | None, int, tuple | None], default: float) -> bool:
    if payload[1] is not None:
        return True
    vals = array("f")
    vals.frombytes(payload[0])
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
