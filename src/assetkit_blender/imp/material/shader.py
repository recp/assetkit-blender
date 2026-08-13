from __future__ import annotations

import math
from dataclasses import replace

import bpy

from ...assetkit import MeshPrimitiveData, TextureRefData
from ..buffers import channel_target as _channel_target
from ..metadata import (
    _assetkit_extra_child,
    _assetkit_extra_children,
    _assetkit_extra_float_array,
    _assetkit_extra_path,
    _set_assetkit_json_prop,
    _set_prop_if_nondefault,
)
from ..textures import (
    _image_texture_channel,
    _image_texture_node,
    _separate_color_channel,
    _separate_color_node,
    _texture_channel_letters,
    _texture_channel_name,
    _texture_extension,
    _texture_interpolation,
    _uv_layer_name,
)
from .common import _has_input, _texture_info, _tuple_close
from .constants import (
    _ANIM_MATERIAL_DISPERSION,
    _ANIM_MATERIAL_IRIDESCENCE,
    _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
    _ANIM_MATERIAL_OCCLUSION_STRENGTH,
    _ANIM_MATERIAL_VOLUME_THICKNESS,
    _GLTF_SETTINGS_GROUP_NAME,
    _GLTF_SETTINGS_SOCKETS,
    _TEXTURE_EXTENSION_DEFAULT,
    _TEXTURE_MAG_FILTER_DEFAULT,
    _TEXTURE_MIN_FILTER_DEFAULT,
    _TEXTURE_MIP_FILTER_DEFAULT,
    _TEXTURE_INTERPOLATION_DEFAULT,
    _TEXTURE_WRAP_DEFAULT,
)

_GLTF_SETTINGS_GROUP_CACHE = None


def _configure_unlit_shader(
    mat: bpy.types.Material,
    alpha_mode: int,
):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")

    surface = output.inputs.get("Surface")
    if surface:
        for link in list(surface.links):
            links.remove(link)

    emission = nodes.new("ShaderNodeEmission")
    if not surface:
        return emission, None

    if alpha_mode:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(transparent.outputs.get("BSDF"), mix.inputs[1])
        links.new(emission.outputs.get("Emission"), mix.inputs[2])
        links.new(mix.outputs.get("Shader"), surface)
        return emission, mix.inputs.get("Fac")

    links.new(emission.outputs.get("Emission"), surface)
    return emission, None


def _set_assetkit_material_props(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    props = {
        "assetkit_iridescence": data.iridescence,
        "assetkit_iridescence_ior": data.iridescence_ior,
        "assetkit_iridescence_thickness_minimum": data.iridescence_thickness_minimum,
        "assetkit_iridescence_thickness_maximum": data.iridescence_thickness_maximum,
        "assetkit_volume_thickness": data.volume_thickness,
        "assetkit_volume_attenuation_color": data.volume_attenuation_color,
        "assetkit_volume_attenuation_distance": data.volume_attenuation_distance,
        "assetkit_volume_scatter_anisotropy": data.volume_scatter_anisotropy,
        "assetkit_anisotropy": data.anisotropy,
        "assetkit_anisotropy_rotation": data.anisotropy_rotation,
        "assetkit_diffuse_transmission": data.diffuse_transmission,
        "assetkit_diffuse_transmission_color": data.diffuse_transmission_color,
        "assetkit_dispersion": data.dispersion,
        "assetkit_transparent_color": data.transparent_color,
        "assetkit_transparent_amount": data.transparent_amount,
        "assetkit_opacity": data.opacity,
        "assetkit_transparent_inverted": bool(data.transparent_inverted),
        "assetkit_normal_scale": data.normal_scale,
        "assetkit_occlusion_strength": data.occlusion_strength,
        "assetkit_emissive_strength": data.emissive_strength,
        "assetkit_clearcoat_normal_scale": data.clearcoat_normal_scale,
        "assetkit_material_type": data.material_type,
        "assetkit_file_type": data.file_type,
        "assetkit_iridescence_texture": data.iridescence_texture,
        "assetkit_iridescence_thickness_texture": data.iridescence_thickness_texture,
        "assetkit_volume_thickness_texture": data.volume_thickness_texture,
        "assetkit_anisotropy_texture": data.anisotropy_texture,
        "assetkit_diffuse_transmission_texture": data.diffuse_transmission_texture,
        "assetkit_diffuse_transmission_color_texture": data.diffuse_transmission_color_texture,
        "assetkit_transparent_texture": data.transparent_texture,
    }
    if _material_extra_extension(data, "KHR_materials_ior") is not None or abs(float(data.ior) - 1.5) > 1e-6:
        props["assetkit_ior"] = data.ior
    scatter_color = _volume_scatter_color(data)
    if scatter_color:
        props["assetkit_volume_scatter_multiscatter_color"] = scatter_color
    for key, value in props.items():
        if _is_default_material_prop(key, value):
            continue
        mat[key] = value

    for role, info in (data.texture_infos or {}).items():
        prefix = f"assetkit_texture_{role}"
        _set_prop_if_nondefault(mat, f"{prefix}_slot", int(info.slot), 0)
        if info.image_name:
            mat[f"{prefix}_image_name"] = info.image_name
        if info.sampler_name:
            mat[f"{prefix}_sampler_name"] = info.sampler_name
        if info.color_space:
            mat[f"{prefix}_color_space"] = info.color_space
        if info.channels:
            mat[f"{prefix}_channels"] = info.channels
        if info.texcoord:
            mat[f"{prefix}_texcoord"] = info.texcoord
        if info.coord_input_name:
            mat[f"{prefix}_coord_input_name"] = info.coord_input_name
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_s", int(info.wrap_s), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_t", int(info.wrap_t), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_p", int(info.wrap_p), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_min_filter", int(info.min_filter), _TEXTURE_MIN_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_mag_filter", int(info.mag_filter), _TEXTURE_MAG_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_mip_filter", int(info.mip_filter), _TEXTURE_MIP_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_extension", _texture_extension(info), _TEXTURE_EXTENSION_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_interpolation", _texture_interpolation(info), _TEXTURE_INTERPOLATION_DEFAULT)
        _set_assetkit_json_prop(mat, f"{prefix}_texture_extra_json", info.texture_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_texref_extra_json", info.texref_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_image_extra_json", info.image_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_sampler_extra_json", info.sampler_extra)
        if info.has_transform:
            mat[f"{prefix}_transform_offset"] = info.transform_offset
            mat[f"{prefix}_transform_scale"] = info.transform_scale
            mat[f"{prefix}_transform_rotation"] = info.transform_rotation


_MATERIAL_PROP_DEFAULTS = {
    "assetkit_iridescence": 0.0,
    "assetkit_iridescence_ior": 1.3,
    "assetkit_iridescence_thickness_minimum": 100.0,
    "assetkit_iridescence_thickness_maximum": 400.0,
    "assetkit_volume_thickness": 0.0,
    "assetkit_volume_attenuation_color": (1.0, 1.0, 1.0),
    "assetkit_volume_attenuation_distance": math.inf,
    "assetkit_volume_scatter_multiscatter_color": (0.0, 0.0, 0.0),
    "assetkit_volume_scatter_anisotropy": 0.0,
    "assetkit_anisotropy": 0.0,
    "assetkit_anisotropy_rotation": 0.0,
    "assetkit_diffuse_transmission": 0.0,
    "assetkit_diffuse_transmission_color": (1.0, 1.0, 1.0),
    "assetkit_dispersion": 0.0,
    "assetkit_transparent_color": (1.0, 1.0, 1.0, 1.0),
    "assetkit_transparent_amount": 1.0,
    "assetkit_opacity": 1.0,
    "assetkit_transparent_inverted": False,
    "assetkit_normal_scale": 1.0,
    "assetkit_occlusion_strength": 1.0,
    "assetkit_emissive_strength": 1.0,
    "assetkit_clearcoat_normal_scale": 1.0,
}


def _is_default_material_prop(key: str, value) -> bool:
    if value == "":
        return True
    if key in {"assetkit_material_type", "assetkit_file_type"}:
        return False
    default = _MATERIAL_PROP_DEFAULTS.get(key)
    if default is None:
        return value == 0.0
    if isinstance(default, tuple):
        return _tuple_close(value, default)
    try:
        if float(value) == float(default):
            return True
        return abs(float(value) - float(default)) <= 1.0e-6
    except (TypeError, ValueError):
        return value == default


def _ensure_gltf_settings_node(mat: bpy.types.Material, data: MeshPrimitiveData, bsdf=None):
    if not _needs_gltf_settings_node(data, bsdf):
        return None

    group = _ensure_gltf_settings_group()
    if not group:
        return None

    node = mat.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.label = _GLTF_SETTINGS_GROUP_NAME
    node.location = (-220, -520)

    if not data.occlusion_texture:
        _set_input_if_nondefault(node, "Occlusion", data.occlusion_strength, 1.0)
    if not data.volume_thickness_texture:
        _set_input_if_nondefault(node, "Thickness", data.volume_thickness, 0.0)
    _set_input_if_nondefault(node, "Dispersion", data.dispersion, 0.0)
    if not data.iridescence_texture:
        _set_input_if_nondefault(node, "Iridescence Factor", data.iridescence, 0.0)
    if not data.iridescence_thickness_texture:
        _set_input_if_nondefault(
            node,
            "Iridescence Thickness Minimum",
            data.iridescence_thickness_minimum,
            100.0,
        )
    return node


def _needs_gltf_settings_node(data: MeshPrimitiveData, bsdf=None) -> bool:
    if data.occlusion_texture:
        return True

    if float(data.dispersion) != 0.0:
        return not _has_input(bsdf, ("Dispersion",))

    if float(data.volume_thickness) > 0.0 or data.volume_thickness_texture:
        if not _has_input(bsdf, ("Volume Thickness", "Thickness")):
            return True

    if (
        float(data.iridescence) != 0.0
        or data.iridescence_texture
        or float(data.iridescence_thickness_minimum) != 100.0
    ):
        if data.iridescence_texture and not _has_input(
            bsdf,
            ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        ):
            return True
        if data.iridescence_thickness_texture and not _has_input(bsdf, ("Thin Film Thickness",)):
            return True

    return _has_material_settings_animation_needing_node(data, bsdf)


def _has_material_settings_animation_needing_node(data: MeshPrimitiveData, bsdf=None) -> bool:
    for channel in data.material_anim_channels or ():
        target = _channel_target(channel)
        if target == _ANIM_MATERIAL_OCCLUSION_STRENGTH:
            return True
        if target == _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM:
            continue
        if target == _ANIM_MATERIAL_IRIDESCENCE and not _has_input(
            bsdf,
            ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        ):
            return True
        if target == _ANIM_MATERIAL_VOLUME_THICKNESS and not _has_input(bsdf, ("Volume Thickness", "Thickness")):
            return True
        if target == _ANIM_MATERIAL_DISPERSION and not _has_input(bsdf, ("Dispersion",)):
            return True
    return False


def _ensure_gltf_settings_group():
    global _GLTF_SETTINGS_GROUP_CACHE

    group = _GLTF_SETTINGS_GROUP_CACHE
    if group is not None:
        try:
            if bpy.data.node_groups.get(group.name) == group:
                return group
        except ReferenceError:
            pass

    group = bpy.data.node_groups.get(_GLTF_SETTINGS_GROUP_NAME)
    if group is None:
        group = bpy.data.node_groups.new(_GLTF_SETTINGS_GROUP_NAME, "ShaderNodeTree")
        group.nodes.new("NodeGroupInput").location = (-200, 0)
        group.nodes.new("NodeGroupOutput")

    if not group.get("assetkit_sockets_ready"):
        for name, default in _GLTF_SETTINGS_SOCKETS:
            _ensure_gltf_settings_socket(group, name, default)
        group["assetkit_sockets_ready"] = True
    _GLTF_SETTINGS_GROUP_CACHE = group
    return group


def _ensure_gltf_settings_socket(group, name: str, default: float) -> None:
    if _has_gltf_settings_socket(group, name):
        return

    socket = None
    interface = getattr(group, "interface", None)
    if interface is not None:
        try:
            socket = interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
        except TypeError:
            socket = interface.new_socket(name, socket_type="NodeSocketFloat")
        except Exception:
            socket = None

    if socket is None:
        try:
            socket = group.inputs.new("NodeSocketFloat", name)
        except Exception:
            socket = None

    if socket is not None:
        try:
            socket.default_value = default
        except Exception:
            pass


def _has_gltf_settings_socket(group, name: str) -> bool:
    for socket in getattr(group, "inputs", ()) or ():
        if socket.name == name:
            return True

    interface = getattr(group, "interface", None)
    for item in getattr(interface, "items_tree", ()) if interface is not None else ():
        if getattr(item, "item_type", "") == "SOCKET" and item.name == name:
            if getattr(item, "in_out", "INPUT") == "INPUT":
                return True
    return False


def _material_extra_extension(data: MeshPrimitiveData, name: str) -> object | None:
    extensions = _assetkit_extra_path(data.material_extra, "extensions")
    return _assetkit_extra_path(extensions, name)


_MAPPED_MATERIAL_EXTRA_EXTENSIONS = {
    "KHR_materials_anisotropy",
    "KHR_materials_clearcoat",
    "KHR_materials_diffuse_transmission",
    "KHR_materials_dispersion",
    "KHR_materials_emissive_strength",
    "KHR_materials_ior",
    "KHR_materials_iridescence",
    "KHR_materials_pbrSpecularGlossiness",
    "KHR_materials_sheen",
    "KHR_materials_specular",
    "KHR_materials_transmission",
    "KHR_materials_unlit",
    "KHR_materials_volume",
    "KHR_materials_volume_scatter",
    "ADOBE_materials_clearcoat_specular",
    "ADOBE_materials_clearcoat_tint",
    "ADOBE_materials_thin_transparency",
}


def _material_extra_for_custom_prop(data: MeshPrimitiveData) -> object | None:
    extra = data.material_extra
    if not isinstance(extra, dict):
        return extra

    children = _assetkit_extra_children(extra)
    if len(children) != 1 or children[0].get("name") != "extensions":
        return extra

    extensions = _assetkit_extra_children(children[0])
    if not extensions:
        return extra
    if all(str(ext.get("name") or "") in _MAPPED_MATERIAL_EXTRA_EXTENSIONS for ext in extensions):
        return None
    return extra


def _set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket:
        try:
            socket.default_value = value
        except TypeError:
            pass


def _set_input_if_nondefault(node, name: str, value: float, default: float) -> None:
    if abs(float(value) - float(default)) <= 1.0e-6:
        return
    _set_input(node, name, value)


def _set_first_input(node, names: tuple[str, ...], value) -> None:
    for name in names:
        socket = node.inputs.get(name)
        if socket:
            try:
                socket.default_value = value
            except TypeError:
                pass
            return


def _link_image(
    mat: bpy.types.Material,
    target,
    path: str,
    input_name: str,
    colorspace: str,
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return

    socket = target.inputs.get(input_name)
    if socket:
        mat.node_tree.links.new(tex.outputs["Color"], socket)


def _link_image_first(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return

    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(tex.outputs["Color"], socket)
            return


def _link_factor_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    channel: str,
    factor: float = 1.0,
    tex_info: TextureRefData | None = None,
) -> object | None:
    output = _factor_texture_output(mat, path, colorspace, channel, factor, tex_info)
    if not output:
        return None
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return output
    return None


def _factor_texture_output(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    channel: str,
    factor: float = 1.0,
    tex_info: TextureRefData | None = None,
):
    channel = _texture_channel_name(tex_info, channel)
    output = _image_texture_channel(mat, path, colorspace, channel, tex_info)
    if not output:
        return None
    if factor != 1.0:
        output = _multiply_value_factor(mat, output, factor, f"{channel} Factor")
    return output


def _link_specular_glossiness_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "specular")
    gloss_info = replace(tex_info, color_space="") if tex_info else None
    _link_color_texture(
        mat,
        bsdf,
        data.specular_texture,
        ("Specular Tint",),
        colorspace="sRGB",
        factor=(*data.specular_color, 1.0),
        tex_info=tex_info,
    )

    output = _image_texture_channel(mat, data.specular_texture, "Non-Color", "Alpha", gloss_info)
    if not output:
        return
    if data.specular_strength != 1.0:
        output = _multiply_value_factor(mat, output, data.specular_strength, "Glossiness Factor")
    output = _one_minus_value(mat, output, "Glossiness to Roughness")
    socket = bsdf.inputs.get("Roughness")
    if socket:
        mat.node_tree.links.new(output, socket)


def _link_range_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    channel: str,
    minimum: float,
    maximum: float,
    tex_info: TextureRefData | None = None,
) -> None:
    channel = _texture_channel_name(tex_info, channel)
    output = _image_texture_channel(mat, path, colorspace, channel, tex_info)
    if not output:
        return
    extent = float(maximum) - float(minimum)
    if extent != 1.0:
        output = _multiply_value_factor(mat, output, extent, f"{channel} Range")
    if minimum != 0.0:
        output = _add_value_factor(mat, output, float(minimum), f"{channel} Offset")
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return


def _link_color_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    factor: tuple[float, float, float, float],
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return
    output = _multiply_color_factor(mat, tex.outputs.get("Color"), factor, "Color Factor")
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return


def _link_base_color(
    mat: bpy.types.Material,
    target,
    data: MeshPrimitiveData,
    color_attr: str,
    color_input: str = "Base Color",
    alpha_socket=None,
) -> None:
    color_output = None
    alpha_output = None

    if data.base_color_texture:
        tex = _image_texture_node(mat, data.base_color_texture, "sRGB", _texture_info(data, "base_color"))
        if tex:
            color_output = tex.outputs.get("Color")
            alpha_output = tex.outputs.get("Alpha") if data.alpha_mode else None

    if color_attr:
        vertex_color = _vertex_color_node(mat, color_attr)
        if vertex_color:
            color_output = _multiply_color_outputs(
                mat,
                color_output,
                vertex_color.outputs.get("Color"),
                "Vertex Color",
            )
            if data.alpha_mode:
                alpha_output = _multiply_value_outputs(
                    mat,
                    alpha_output,
                    vertex_color.outputs.get("Alpha"),
                    "Vertex Alpha",
                )

    if color_output:
        color_output = _multiply_color_factor(mat, color_output, data.base_color, "Base Color Factor")
    if data.alpha_mode and alpha_output:
        alpha_output = _multiply_value_factor(mat, alpha_output, data.opacity, "Base Alpha Factor")

    base_color = target.inputs.get(color_input)
    if base_color and color_output:
        mat.node_tree.links.new(color_output, base_color)
    if data.alpha_mode and alpha_socket and alpha_output:
        mat.node_tree.links.new(alpha_output, alpha_socket)


def _link_occlusion_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
    settings_node=None,
) -> None:
    tex = _image_texture_node(mat, data.occlusion_texture, "Non-Color", _texture_info(data, "occlusion"))
    if not tex:
        return

    ao_output = _separate_color_channel(
        mat,
        tex.outputs.get("Color"),
        _texture_channel_name(_texture_info(data, "occlusion"), "Red"),
    )
    strength = max(0.0, min(1.0, float(data.occlusion_strength)))
    if strength != 1.0:
        ao_output = _multiply_value_factor(mat, ao_output, strength, "Occlusion Strength")
        ao_output = _add_value_factor(mat, ao_output, 1.0 - strength, "Occlusion Base")
    if settings_node and ao_output:
        socket = settings_node.inputs.get("Occlusion")
        if socket:
            mat.node_tree.links.new(ao_output, socket)


def _link_emissive_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    emission = bsdf.inputs.get("Emission Color")
    if not emission:
        return

    tex = _image_texture_node(mat, data.emissive_texture, "sRGB", _texture_info(data, "emissive"))
    if not tex:
        return

    color_output = _multiply_color_factor(
        mat,
        tex.outputs.get("Color"),
        (*data.emissive_color, 1.0),
        "Emissive Factor",
    )
    if color_output:
        mat.node_tree.links.new(color_output, emission)


def _link_volume_absorption(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output or "Volume" not in output.inputs:
        return

    try:
        volume = nodes.new("ShaderNodeVolumeAbsorption")
    except Exception:
        return
    volume.label = "AssetKit Volume Absorption"
    volume["assetkit_volume_node"] = "absorption"

    color = volume.inputs.get("Color")
    if color:
        color.default_value = (*data.volume_attenuation_color, 1.0)

    density = volume.inputs.get("Density")
    if density:
        distance = float(data.volume_attenuation_distance)
        density.default_value = 1.0 / distance if distance > 0.0 else 0.0

    volume_output = volume.outputs.get("Volume")
    if volume_output:
        links.new(volume_output, output.inputs["Volume"])


def _has_volume_scatter(data: MeshPrimitiveData) -> bool:
    return bool(_volume_scatter_color(data))


def _volume_scatter_color(data: MeshPrimitiveData) -> tuple[float, float, float] | None:
    if not _tuple_close(data.volume_scatter_color, (0.0, 0.0, 0.0)):
        return tuple(max(0.0, min(1.0, float(value))) for value in data.volume_scatter_color)

    ext = _material_extra_extension(data, "KHR_materials_volume_scatter")
    color = _assetkit_extra_float_array(_assetkit_extra_child(ext, "multiscatterColor"), 3)
    if len(color) != 3:
        color = _assetkit_extra_float_array(_assetkit_extra_child(ext, "multiscatterColorFactor"), 3)
    if len(color) != 3:
        return None
    return tuple(max(0.0, min(1.0, float(value))) for value in color)


def _link_volume_scatter(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    color = _volume_scatter_color(data)
    if not color:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output or "Volume" not in output.inputs:
        return

    try:
        scatter = nodes.new("ShaderNodeVolumeScatter")
    except Exception:
        return
    scatter.label = "AssetKit Volume Scatter"
    scatter["assetkit_volume_node"] = "scatter"

    color_socket = scatter.inputs.get("Color")
    if color_socket:
        color_socket.default_value = (*color, 1.0)

    density = scatter.inputs.get("Density")
    if density:
        distance = float(data.volume_attenuation_distance)
        if distance > 0.0 and math.isfinite(distance):
            density.default_value = min(1.0 / distance, 1.0)
        else:
            density.default_value = max(0.0, min(float(data.volume_thickness), 1.0))

    anisotropy = scatter.inputs.get("Anisotropy")
    if anisotropy:
        anisotropy.default_value = max(-1.0, min(1.0, float(data.volume_scatter_anisotropy)))

    volume_output = scatter.outputs.get("Volume")
    volume_input = output.inputs.get("Volume")
    if not volume_output or not volume_input:
        return

    previous = volume_input.links[0].from_socket if volume_input.links else None
    if previous is None:
        links.new(volume_output, volume_input)
        return

    try:
        add = nodes.new("ShaderNodeAddShader")
    except Exception:
        return
    add.label = "AssetKit Volume"
    for link in list(volume_input.links):
        links.remove(link)
    links.new(previous, add.inputs[0])
    links.new(volume_output, add.inputs[1])
    links.new(add.outputs.get("Shader"), volume_input)


def _vertex_color_node(mat: bpy.types.Material, name: str):
    nodes = mat.node_tree.nodes
    try:
        node = nodes.new("ShaderNodeVertexColor")
        node.layer_name = name
    except Exception:
        try:
            node = nodes.new("ShaderNodeAttribute")
            node.attribute_name = name
        except Exception:
            return None
    return node


def _multiply_color_outputs(
    mat: bpy.types.Material,
    output_a,
    output_b,
    label: str,
):
    if output_a is None:
        return output_b
    if output_b is None:
        return output_a

    node = _new_color_multiply_node(mat, label)
    if not node:
        return output_a

    inputs = _color_multiply_inputs(node)
    output = _color_multiply_output(node)
    if not inputs or output is None:
        return output_a

    mat.node_tree.links.new(output_a, inputs[0])
    mat.node_tree.links.new(output_b, inputs[1])
    return output


def _multiply_color_factor(
    mat: bpy.types.Material,
    output,
    factor: tuple[float, float, float, float],
    label: str,
):
    color = tuple(float(value) for value in factor[:3])
    if color == (1.0, 1.0, 1.0):
        return output

    node = _new_color_multiply_node(mat, label)
    if not node:
        return output

    inputs = _color_multiply_inputs(node)
    result = _color_multiply_output(node)
    if not inputs or result is None:
        return output

    mat.node_tree.links.new(output, inputs[0])
    try:
        inputs[1].default_value = (*color, 1.0)
    except TypeError:
        pass
    return result


def _new_color_multiply_node(mat: bpy.types.Material, label: str):
    nodes = mat.node_tree.nodes
    try:
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = "MULTIPLY"
        node.inputs["Fac"].default_value = 1.0
    except Exception:
        try:
            node = nodes.new("ShaderNodeMix")
            node.data_type = "RGBA"
            node.blend_type = "MULTIPLY"
            node.inputs["Factor"].default_value = 1.0
        except Exception:
            return None
    node.label = label
    return node


def _color_multiply_inputs(node) -> tuple[object, object] | None:
    if "Color1" in node.inputs and "Color2" in node.inputs:
        return node.inputs["Color1"], node.inputs["Color2"]
    if len(node.inputs) >= 8:
        return node.inputs[6], node.inputs[7]
    return None


def _color_multiply_output(node):
    if "Color" in node.outputs:
        return node.outputs["Color"]
    if len(node.outputs) >= 3:
        return node.outputs[2]
    return None


def _multiply_value_outputs(
    mat: bpy.types.Material,
    output_a,
    output_b,
    label: str,
):
    if output_a is None:
        return output_b
    if output_b is None:
        return output_a

    node = _new_value_multiply_node(mat, label)
    if not node:
        return output_a

    mat.node_tree.links.new(output_a, node.inputs[0])
    mat.node_tree.links.new(output_b, node.inputs[1])
    return node.outputs[0]


def _multiply_value_factor(
    mat: bpy.types.Material,
    output,
    factor: float,
    label: str,
):
    if factor == 1.0:
        return output

    node = _new_value_multiply_node(mat, label)
    if not node:
        return output

    mat.node_tree.links.new(output, node.inputs[0])
    node.inputs[1].default_value = factor
    return node.outputs[0]


def _add_value_factor(
    mat: bpy.types.Material,
    output,
    value: float,
    label: str,
):
    if value == 0.0:
        return output

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return output
    node.label = label
    node.operation = "ADD"
    mat.node_tree.links.new(output, node.inputs[0])
    node.inputs[1].default_value = value
    return node.outputs[0]


def _one_minus_value(mat: bpy.types.Material, output, label: str):
    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return output
    node.label = label
    node.operation = "SUBTRACT"
    node.inputs[0].default_value = 1.0
    mat.node_tree.links.new(output, node.inputs[1])
    return node.outputs[0]


def _mix_color_factor(
    mat: bpy.types.Material,
    output,
    base: tuple[float, float, float],
    factor: float,
    label: str,
):
    if output is None:
        return None

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMixRGB")
        node.blend_type = "MIX"
        node.inputs["Fac"].default_value = factor
        node.inputs["Color1"].default_value = (*base, 1.0)
        mat.node_tree.links.new(output, node.inputs["Color2"])
        node.label = label
        return node.outputs["Color"]
    except Exception:
        pass

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMix")
    except Exception:
        return output
    node.data_type = "RGBA"
    node.blend_type = "MIX"
    node.inputs["Factor"].default_value = factor
    node.inputs[6].default_value = (*base, 1.0)
    node.label = label
    mat.node_tree.links.new(output, node.inputs[7])
    return node.outputs[2]


def _new_value_multiply_node(mat: bpy.types.Material, label: str):
    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return None
    node.label = label
    node.operation = "MULTIPLY"
    return node


def _link_base_color_texture(mat: bpy.types.Material, bsdf, data: MeshPrimitiveData) -> None:
    _link_base_color(mat, bsdf, data, "")


def _link_transparent_texture(
    mat: bpy.types.Material,
    alpha_socket,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "transparent")
    tex = _image_texture_node(mat, data.transparent_texture, "Non-Color", tex_info)
    if not tex:
        return

    channel = _texture_channel_name(tex_info, "")
    if channel:
        if channel == "Alpha":
            output = tex.outputs.get("Alpha") or _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent Alpha")
        else:
            output = _separate_color_channel(mat, tex.outputs.get("Color"), channel)
    elif set(_texture_channel_letters(tex_info)) >= {"R", "G", "B"}:
        output = _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent RGB")
    else:
        output = tex.outputs.get("Alpha") or _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent Alpha")

    if not output:
        return

    if float(data.transparent_amount) != 1.0:
        output = _multiply_value_factor(mat, output, data.transparent_amount, "Transparent Amount")

    if data.transparent_inverted:
        output = _one_minus_value(mat, output, "Transparent Invert")

    _replace_socket_link(mat, alpha_socket, output)


def _has_diffuse_transmission(data: MeshPrimitiveData) -> bool:
    return (
        float(data.diffuse_transmission) > 0.0
        or bool(data.diffuse_transmission_texture)
        or bool(data.diffuse_transmission_color_texture)
    )


def _link_diffuse_transmission_shader(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output:
        return
    surface = output.inputs.get("Surface")
    if not surface:
        return

    previous = surface.links[0].from_socket if surface.links else None
    if previous is None:
        bsdf = nodes.get("Principled BSDF")
        previous = bsdf.outputs.get("BSDF") if bsdf else None
    if previous is None:
        return

    try:
        translucent = nodes.new("ShaderNodeBsdfTranslucent")
        mix = nodes.new("ShaderNodeMixShader")
    except Exception:
        return
    translucent.label = "AssetKit Diffuse Transmission"
    translucent["assetkit_diffuse_transmission_node"] = "translucent"
    mix.label = "AssetKit Diffuse Transmission"
    mix["assetkit_diffuse_transmission_node"] = "mix"

    color_socket = translucent.inputs.get("Color")
    if color_socket:
        color_socket.default_value = (*data.diffuse_transmission_color, 1.0)
        if data.diffuse_transmission_color_texture:
            _link_color_texture(
                mat,
                translucent,
                data.diffuse_transmission_color_texture,
                ("Color",),
                colorspace="sRGB",
                factor=(*data.diffuse_transmission_color, 1.0),
                tex_info=_texture_info(data, "diffuse_transmission_color"),
            )

    factor_output = None
    if data.diffuse_transmission_texture:
        factor_output = _factor_texture_output(
            mat,
            data.diffuse_transmission_texture,
            "Non-Color",
            "Alpha",
            data.diffuse_transmission,
            _texture_info(data, "diffuse_transmission"),
        )
    factor = mix.inputs.get("Fac")
    if factor_output and factor:
        links.new(factor_output, factor)
    elif factor:
        factor.default_value = max(0.0, min(1.0, float(data.diffuse_transmission)))

    for link in list(surface.links):
        links.remove(link)
    links.new(previous, mix.inputs[1])
    links.new(translucent.outputs.get("BSDF"), mix.inputs[2])
    links.new(mix.outputs.get("Shader"), surface)


def _link_anisotropy_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "anisotropy")
    tex = _image_texture_node(mat, data.anisotropy_texture, "Non-Color", tex_info)
    if not tex:
        return

    separate = _separate_color_node(mat, tex.outputs["Color"])
    if not separate:
        return

    strength = separate.outputs.get("Blue")
    if strength:
        if data.anisotropy != 1.0:
            strength = _multiply_value_factor(mat, strength, data.anisotropy, "Anisotropy Factor")
        socket = bsdf.inputs.get("Anisotropic")
        if socket:
            mat.node_tree.links.new(strength, socket)

    rotation = _anisotropy_rotation_output(mat, separate, data.anisotropy_rotation)
    socket = bsdf.inputs.get("Anisotropic Rotation")
    if rotation and socket:
        mat.node_tree.links.new(rotation, socket)

    tangent = bsdf.inputs.get("Tangent")
    if tangent:
        try:
            tangent_node = mat.node_tree.nodes.new("ShaderNodeTangent")
            tangent_node.direction_type = "UV_MAP"
            tangent_node.uv_map = _uv_layer_name(tex_info.slot if tex_info else 0)
            mat.node_tree.links.new(tangent_node.outputs["Tangent"], tangent)
        except Exception:
            pass


def _anisotropy_rotation_output(
    mat: bpy.types.Material,
    separate,
    factor_rotation: float,
):
    red = separate.outputs.get("Red")
    green = separate.outputs.get("Green")
    if not red or not green:
        return None

    x = _add_value_factor(mat, _multiply_value_factor(mat, red, 2.0, "Anisotropy X Scale"), -1.0, "Anisotropy X Bias")
    y = _add_value_factor(mat, _multiply_value_factor(mat, green, 2.0, "Anisotropy Y Scale"), -1.0, "Anisotropy Y Bias")

    try:
        atan = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return None
    atan.label = "Anisotropy Rotation"
    atan.operation = "ARCTAN2"
    mat.node_tree.links.new(y, atan.inputs[0])
    mat.node_tree.links.new(x, atan.inputs[1])
    output = atan.outputs[0]

    if factor_rotation != 0.0:
        output = _add_value_factor(mat, output, factor_rotation, "Anisotropy Rotation Factor")

    return _multiply_value_factor(mat, output, 1.0 / (2.0 * math.pi), "Anisotropy Rotation Units")


def _replace_socket_link(mat: bpy.types.Material, socket, output) -> None:
    if not socket or not output:
        return
    for link in list(socket.links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(output, socket)


def _rgb_to_luminance(mat: bpy.types.Material, output, label: str):
    if output is None:
        return None
    try:
        node = mat.node_tree.nodes.new("ShaderNodeRGBToBW")
    except Exception:
        return output
    node.label = label
    mat.node_tree.links.new(output, node.inputs["Color"])
    return node.outputs["Val"]


def _link_metallic_roughness_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    tex_info: TextureRefData | None = None,
    metallic_factor: float = 1.0,
    roughness_factor: float = 1.0,
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color", tex_info)
    if not tex:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    separate = nodes.new("ShaderNodeSeparateColor")
    links.new(tex.outputs["Color"], separate.inputs["Color"])

    roughness = bsdf.inputs.get("Roughness")
    metallic = bsdf.inputs.get("Metallic")
    if roughness:
        roughness_output = separate.outputs["Green"]
        if roughness_factor != 1.0:
            roughness_output = _multiply_value_factor(mat, roughness_output, roughness_factor, "Roughness Factor")
        links.new(roughness_output, roughness)
    if metallic:
        metallic_output = separate.outputs["Blue"]
        if metallic_factor != 1.0:
            metallic_output = _multiply_value_factor(mat, metallic_output, metallic_factor, "Metallic Factor")
        links.new(metallic_output, metallic)


def _link_normal_texture_node(
    mat: bpy.types.Material,
    bsdf,
    tex,
    strength: float,
    tex_info: TextureRefData | None = None,
    input_name: str = "Normal",
):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    is_height = bool(tex_info and tex_info.role == "height")
    normal_node = nodes.new("ShaderNodeBump" if is_height else "ShaderNodeNormalMap")
    role = "clearcoat_normal" if input_name == "Coat Normal" else "normal"
    normal_node.label = f"AssetKit {'height' if is_height else role}"
    normal_node["assetkit_normal_role"] = role
    normal_node["assetkit_normal_kind"] = "height" if is_height else "normal"
    normal_node.inputs["Strength"].default_value = strength
    source_input = normal_node.inputs.get("Height" if is_height else "Color")
    color_output = tex.outputs.get("Color")
    if color_output and source_input:
        links.new(color_output, source_input)
    normal = bsdf.inputs.get(input_name)
    if normal:
        links.new(normal_node.outputs["Normal"], normal)
    return normal_node


def _link_normal_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    strength: float,
    tex_info: TextureRefData | None = None,
    input_name: str = "Normal",
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color", tex_info)
    if not tex:
        return

    _link_normal_texture_node(mat, bsdf, tex, strength, tex_info, input_name)
