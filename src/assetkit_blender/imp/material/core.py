from __future__ import annotations

import json
import math
import time
from collections import deque
from dataclasses import replace

import bpy

from ...assetkit import (
    MeshPrimitiveData,
    TextureRefData,
    _native_meshes_from_raw,
    _profile_log,
)
from .. import profile as _profile_state, textures as _textures
from ..attributes import is_color_attribute_name as _is_color_attribute_name
from ..metadata import _set_assetkit_json_prop
from ..profile import _record_material_profile
from ..textures import (
    _cached_texture_image,
    _load_texture_image,
    _queue_deferred_texture_image,
    _set_texture_sampler_props,
    _should_defer_texture_image,
    _texture_color_space,
    _texture_extension,
    _texture_interpolation,
    _texture_node_cache_key,
    _texture_uv_slot,
)
from .animation import _apply_material_animation
from .common import (
    _blender_anisotropy_rotation,
    _has_input,
    _is_classic_lit_material,
    _is_specular_glossiness_material,
    _normal_map_node,
    _pbr_specular_level,
    _texture_info,
    _tuple_close,
)
from .constants import (
    _AK_MATERIAL_TYPE_BLINN,
    _AK_MATERIAL_TYPE_CONSTANT,
    _AK_MATERIAL_TYPE_LAMBERT,
    _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS,
    _AK_MATERIAL_TYPE_PHONG,
    _MATERIAL_TEXTURE_FIELDS,
    _TEXTURE_EXTENSION_DEFAULT,
    _TEXTURE_INTERPOLATION_DEFAULT,
)
from .shader import (
    _configure_unlit_shader,
    _ensure_gltf_settings_node,
    _has_diffuse_transmission,
    _has_volume_scatter,
    _link_anisotropy_texture,
    _link_base_color,
    _link_color_texture,
    _link_diffuse_transmission_shader,
    _link_emissive_texture,
    _link_factor_texture,
    _link_metallic_roughness_texture,
    _link_normal_texture,
    _link_occlusion_texture,
    _link_range_texture,
    _link_specular_glossiness_texture,
    _link_transparent_texture,
    _link_volume_absorption,
    _link_volume_scatter,
    _material_extra_for_custom_prop,
    _set_assetkit_material_props,
    _set_first_input,
    _set_input,
)

ACTIVE_TEMPLATE_CLONING = True
_MATERIAL_TEMPLATE_CACHE: dict[object, bpy.types.Material] = {}
_MATERIAL_CACHE_KEY_AUTO = object()
NO_MATERIAL_CACHE_KEY = object()
_DEFERRED_MATERIAL_NODE_TASKS: deque[tuple[object, ...]] = deque()
_DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = False
_DEFERRED_MATERIAL_NODE_TIME_BUDGET = 0.006


def has_deferred_work() -> bool:
    return bool(_DEFERRED_MATERIAL_NODE_TASKS)


def _apply_material_variants(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None = None,
) -> None:
    variants = data.material_variants or []
    if not variants:
        return

    obj["assetkit_material_variant_count"] = len(variants)
    for index, variant in enumerate(variants):
        prefix = f"assetkit_material_variant_{index}"
        obj[f"{prefix}_index"] = int(variant.get("variant_index") or 0)
        obj[f"{prefix}_name"] = variant.get("variant_name") or ""
        obj[f"{prefix}_material"] = variant.get("material_name") or ""
        material = _create_variant_material(data, variant, material_cache)
        if material:
            slot = _ensure_material_slot(obj.data, material)
            obj[f"{prefix}_slot"] = slot


def _ensure_material_slot(mesh: bpy.types.Mesh, material: bpy.types.Material) -> int:
    for index, slot_material in enumerate(mesh.materials):
        if slot_material == material:
            return index
    mesh.materials.append(material)
    return len(mesh.materials) - 1


def _create_variant_material(
    data: MeshPrimitiveData,
    variant: dict,
    material_cache: dict[object, bpy.types.Material] | None,
) -> bpy.types.Material | None:
    raw = variant.get("material")
    if isinstance(raw, dict):
        return _create_material(_variant_material_data(data, variant, raw), material_cache)
    if raw is None:
        return None
    material_data = _native_meshes_from_raw((raw,))
    if not material_data:
        return None
    return _create_material(material_data[0], material_cache)


def _variant_material_data(data: MeshPrimitiveData, variant: dict, raw: dict) -> MeshPrimitiveData:
    values = {
        "material_name": _variant_material_name(data, variant, raw),
        "base_color": tuple(raw.get("base_color") or data.base_color),
        "transparent_color": tuple(raw.get("transparent_color") or data.transparent_color),
        "emissive_color": tuple(raw.get("emissive_color") or data.emissive_color),
        "specular_color": tuple(raw.get("specular_color") or data.specular_color),
        "sheen_color": tuple(raw.get("sheen_color") or data.sheen_color),
        "volume_attenuation_color": tuple(raw.get("volume_attenuation_color") or data.volume_attenuation_color),
        "volume_scatter_color": tuple(raw.get("volume_scatter_color") or data.volume_scatter_color),
        "diffuse_transmission_color": tuple(
            raw.get("diffuse_transmission_color") or data.diffuse_transmission_color
        ),
        "metallic": _raw_float(raw, "metallic", data.metallic),
        "roughness": _raw_float(raw, "roughness", data.roughness),
        "alpha_cutoff": _raw_float(raw, "alpha_cutoff", data.alpha_cutoff),
        "transparent_amount": _raw_float(raw, "transparent_amount", data.transparent_amount),
        "opacity": _raw_float(raw, "opacity", data.opacity),
        "normal_scale": _raw_float(raw, "normal_scale", data.normal_scale),
        "occlusion_strength": _raw_float(raw, "occlusion_strength", data.occlusion_strength),
        "emissive_strength": _raw_float(raw, "emissive_strength", data.emissive_strength),
        "specular_strength": _raw_float(raw, "specular_strength", data.specular_strength),
        "ior": _raw_float(raw, "ior", data.ior),
        "clearcoat": _raw_float(raw, "clearcoat", data.clearcoat),
        "clearcoat_roughness": _raw_float(raw, "clearcoat_roughness", data.clearcoat_roughness),
        "clearcoat_normal_scale": _raw_float(raw, "clearcoat_normal_scale", data.clearcoat_normal_scale),
        "transmission": _raw_float(raw, "transmission", data.transmission),
        "sheen_roughness": _raw_float(raw, "sheen_roughness", data.sheen_roughness),
        "iridescence": _raw_float(raw, "iridescence", data.iridescence),
        "iridescence_ior": _raw_float(raw, "iridescence_ior", data.iridescence_ior),
        "iridescence_thickness_minimum": _raw_float(
            raw,
            "iridescence_thickness_minimum",
            data.iridescence_thickness_minimum,
        ),
        "iridescence_thickness_maximum": _raw_float(
            raw,
            "iridescence_thickness_maximum",
            data.iridescence_thickness_maximum,
        ),
        "volume_thickness": _raw_float(raw, "volume_thickness", data.volume_thickness),
        "volume_attenuation_distance": _raw_float(
            raw,
            "volume_attenuation_distance",
            data.volume_attenuation_distance,
        ),
        "volume_scatter_anisotropy": _raw_float(
            raw,
            "volume_scatter_anisotropy",
            data.volume_scatter_anisotropy,
        ),
        "anisotropy": _raw_float(raw, "anisotropy", data.anisotropy),
        "anisotropy_rotation": _raw_float(raw, "anisotropy_rotation", data.anisotropy_rotation),
        "diffuse_transmission": _raw_float(raw, "diffuse_transmission", data.diffuse_transmission),
        "dispersion": _raw_float(raw, "dispersion", data.dispersion),
        "alpha_mode": _raw_int(raw, "alpha_mode", data.alpha_mode),
        "transparent_inverted": bool(raw.get("transparent_inverted", data.transparent_inverted)),
        "double_sided": bool(raw.get("double_sided", data.double_sided)),
        "has_sheen": bool(raw.get("has_sheen", data.has_sheen)),
        "material_type": _raw_int(raw, "material_type", data.material_type),
        "file_type": _raw_int(raw, "file_type", data.file_type),
        "material_key": _raw_int(raw, "material_key", data.material_key),
        "texture_infos": _variant_texture_infos(data.texture_infos, raw.get("texture_infos") or {}),
        "material_extra": raw.get("material_extra"),
    }

    for name in _MATERIAL_TEXTURE_FIELDS:
        values[name] = raw.get(name) or getattr(data, name)

    return replace(data, **values)


def _variant_material_name(data: MeshPrimitiveData, variant: dict, raw: dict) -> str:
    name = raw.get("material_name") or variant.get("material_name") or ""
    if name:
        return str(name)

    base = data.material_name or data.name or "AssetKit Material"
    suffix = variant.get("variant_name") or f"Variant_{int(variant.get('variant_index') or 0)}"
    return f"{base}_{suffix}"


def _raw_float(raw: dict, key: str, fallback: float) -> float:
    value = raw.get(key)
    return float(value) if value is not None else float(fallback)


def _raw_int(raw: dict, key: str, fallback: int) -> int:
    value = raw.get(key)
    return int(value) if value is not None else int(fallback)


def _raw_texture_infos(raw_infos: dict) -> dict[str, TextureRefData]:
    texture_infos = {}
    for role, info in raw_infos.items():
        texture_infos[str(role)] = TextureRefData(
            role=str(role),
            path=info.get("path") or "",
            image_name=info.get("image_name") or "",
            sampler_name=info.get("sampler_name") or "",
            color_space=info.get("color_space") or "",
            channels=info.get("channels") or "",
            texcoord=info.get("texcoord") or "",
            coord_input_name=info.get("coord_input_name") or "",
            slot=int(info.get("slot") or 0),
            wrap_s=int(info.get("wrap_s") or 1),
            wrap_t=int(info.get("wrap_t") or 1),
            wrap_p=int(info.get("wrap_p") or 1),
            min_filter=int(info.get("min_filter") or 0),
            mag_filter=int(info.get("mag_filter") or 0),
            mip_filter=int(info.get("mip_filter") or 0),
            has_transform=bool(info.get("has_transform")),
            transform_offset=tuple(info.get("transform_offset") or (0.0, 0.0)),
            transform_scale=tuple(info.get("transform_scale") or (1.0, 1.0)),
            transform_rotation=_raw_float(info, "transform_rotation", 0.0),
            transform_slot=int(info.get("transform_slot") if info.get("transform_slot") is not None else -1),
            texture_extra=info.get("texture_extra"),
            texref_extra=info.get("texref_extra"),
            image_extra=info.get("image_extra"),
            sampler_extra=info.get("sampler_extra"),
        )
    return texture_infos


def _variant_texture_infos(
    base_infos: dict[str, TextureRefData] | None,
    raw_infos: dict,
) -> dict[str, TextureRefData]:
    texture_infos = {
        role: replace(info)
        for role, info in (base_infos or {}).items()
    }
    texture_infos.update(_raw_texture_infos(raw_infos))
    return texture_infos


def _apply_assetkit_extra_props(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    obj["assetkit_primitive_type"] = int(data.primitive_type)
    obj["assetkit_primitive_mode"] = int(data.primitive_mode)
    obj["assetkit_vertex_count"] = int(data.vertex_count)
    obj["assetkit_loop_count"] = int(data.loop_count)
    obj["assetkit_face_count"] = int(data.face_count)
    obj["assetkit_node_index"] = int(data.node_index)
    obj["assetkit_zero_copy_flags"] = int(data.zero_copy_flags)
    _set_assetkit_json_prop(obj, "assetkit_primitive_extra_json", data.primitive_extra)
    _set_assetkit_json_prop(obj, "assetkit_mesh_extra_json", data.mesh_extra)
    _set_assetkit_json_prop(obj, "assetkit_geometry_extra_json", data.geometry_extra)
    _apply_gaussian_splat_props(obj, data)


def _apply_gaussian_splat_props(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    if not data.has_gsplat:
        return

    obj["assetkit_gaussian_splat"] = True
    obj["assetkit_gaussian_splat_kernel"] = _gsplat_kernel_name(data.gsplat_kernel)
    obj["assetkit_gaussian_splat_color_space"] = _gsplat_color_space_name(data.gsplat_color_space)
    obj["assetkit_gaussian_splat_projection"] = _gsplat_projection_name(data.gsplat_projection)
    obj["assetkit_gaussian_splat_sorting_method"] = _gsplat_sorting_method_name(
        data.gsplat_sorting_method
    )
    obj["assetkit_gaussian_splat_decoded_count"] = int(data.gsplat_decoded_count)
    obj["assetkit_gaussian_splat_kernel_value"] = int(data.gsplat_kernel)
    obj["assetkit_gaussian_splat_color_space_value"] = int(data.gsplat_color_space)
    obj["assetkit_gaussian_splat_projection_value"] = int(data.gsplat_projection)
    obj["assetkit_gaussian_splat_sorting_method_value"] = int(data.gsplat_sorting_method)


def _gsplat_kernel_name(value: int) -> str:
    return {
        1: "ellipse",
    }.get(int(value), "unknown")


def _gsplat_color_space_name(value: int) -> str:
    return {
        1: "srgb_rec709_display",
        2: "lin_rec709_display",
    }.get(int(value), "unknown")


def _gsplat_projection_name(value: int) -> str:
    return {
        0: "perspective",
        1: "orthographic",
    }.get(int(value), "unknown")


def _gsplat_sorting_method_name(value: int) -> str:
    return {
        0: "camera_distance",
        1: "none",
    }.get(int(value), "unknown")


def _create_material(
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None = None,
    *,
    cache_key: object = _MATERIAL_CACHE_KEY_AUTO,
) -> bpy.types.Material | None:
    profile_detail = _profile_state.stats is not None
    profile_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = profile_started_at
    cache_key_ms = 0.0

    def lap_ms() -> float:
        nonlocal phase_started_at
        if not profile_detail:
            return 0.0
        now = time.perf_counter()
        elapsed = (now - phase_started_at) * 1000.0
        phase_started_at = now
        return elapsed

    if cache_key is _MATERIAL_CACHE_KEY_AUTO:
        cache_key = _material_cache_key_for_data(data)
        cache_key_ms = lap_ms()
    if cache_key is NO_MATERIAL_CACHE_KEY:
        return None

    new_ms = 0.0
    simple_ms = 0.0
    nodes_ms = 0.0
    props_ms = 0.0
    settings_ms = 0.0
    textures_ms = 0.0
    animation_ms = 0.0

    if material_cache is not None and cache_key in material_cache:
        if profile_detail:
            _record_material_profile(
                cache_hit=True,
                cache_key_ms=cache_key_ms,
                new_ms=0.0,
                simple_ms=0.0,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return material_cache[cache_key]

    color_attr = _color_attribute_name(data)
    material_name = data.material_name or f"{data.name}_Material"
    base_color = _material_base_color(data)
    if (
        _textures.ACTIVE_LOAD_MODE != "DEFERRED"
        and _can_use_base_color_texture_fast_material(data, color_attr, base_color)
    ):
        mat = _copy_base_color_texture_template_material(material_name, data, base_color)
        new_ms = lap_ms()
        if mat is not None:
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=0.0,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    if (
        _textures.ACTIVE_LOAD_MODE != "DEFERRED"
        and _can_use_classic_texture_fast_material(data, color_attr)
    ):
        mat = _copy_classic_texture_template_material(material_name, data, base_color)
        new_ms = lap_ms()
        if mat is not None:
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=0.0,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    mat = bpy.data.materials.new(material_name)
    mat.diffuse_color = base_color
    new_ms = lap_ms()
    if _can_use_simple_material(data, color_attr):
        _configure_simple_material(mat, data, base_color)
        simple_ms = lap_ms()
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=simple_ms,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    if _can_defer_base_color_texture_material(data, color_attr, base_color):
        _configure_deferred_base_color_texture_material(mat, data, base_color)
        simple_ms = lap_ms()
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=simple_ms,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    if _can_use_scalar_principled_material(data, color_attr):
        if _configure_scalar_principled_material(mat, data, base_color):
            nodes_ms = lap_ms()
            _set_assetkit_material_props(mat, data)
            _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
            props_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=props_ms,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    if _can_use_classic_texture_fast_material(data, color_attr):
        if _configure_classic_texture_fast_material(mat, data, base_color):
            nodes_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    if _can_use_base_color_texture_fast_material(data, color_attr, base_color):
        if _configure_base_color_texture_fast_material(mat, data, base_color):
            nodes_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            nodes_ms = lap_ms()
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=0.0,
                nodes_ms=nodes_ms,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    color_target = bsdf
    color_input = "Base Color"
    alpha_socket = bsdf.inputs.get("Alpha")
    if _is_unlit_material(data):
        color_target, alpha_socket = _configure_unlit_shader(mat, data.alpha_mode)
        color_input = "Color"
    else:
        if _is_classic_lit_material(data):
            _set_input(bsdf, "Metallic", 0.0)
            _set_input(bsdf, "Roughness", _classic_roughness(data.specular_strength))
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _classic_specular(data))
        elif _is_specular_glossiness_material(data):
            _set_input(bsdf, "Metallic", 0.0)
            _set_input(bsdf, "Roughness", data.roughness)
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), 0.5)
        else:
            _set_input(bsdf, "Metallic", data.metallic)
            _set_input(bsdf, "Roughness", data.roughness)
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _pbr_specular_level(data))
        if _has_emission(data):
            _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))
            _set_first_input(bsdf, ("Emission Strength",), _emission_strength(data))
        if _has_specular(data):
            _set_first_input(bsdf, ("Specular Tint",), (*data.specular_color, 1.0))
        _set_first_input(bsdf, ("IOR",), _material_ior(data))
        if _has_clearcoat(data):
            _set_first_input(bsdf, ("Coat Weight", "Clearcoat"), data.clearcoat)
            _set_first_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), data.clearcoat_roughness)
        if _has_transmission(data):
            _set_first_input(bsdf, ("Transmission Weight", "Transmission"), data.transmission)
        if _has_sheen(data):
            _set_first_input(bsdf, ("Sheen Weight", "Sheen"), 1.0 if data.has_sheen else 0.0)
            _set_first_input(bsdf, ("Sheen Tint",), (*data.sheen_color, 1.0))
            _set_first_input(bsdf, ("Sheen Roughness",), data.sheen_roughness)
        if _has_anisotropy(data):
            _set_first_input(bsdf, ("Anisotropic",), data.anisotropy)
            _set_first_input(bsdf, ("Anisotropic Rotation",), _blender_anisotropy_rotation(data.anisotropy_rotation))
        if _has_iridescence(data):
            _set_first_input(bsdf, ("Thin Film IOR",), data.iridescence_ior)
            _set_first_input(bsdf, ("Thin Film Weight", "Iridescence Weight", "Iridescence"), data.iridescence)
            _set_first_input(bsdf, ("Thin Film Thickness",), data.iridescence_thickness_maximum)
        if data.dispersion:
            _set_first_input(bsdf, ("Dispersion",), data.dispersion)
        if _has_diffuse_transmission(data):
            _set_first_input(bsdf, ("Diffuse Transmission Weight", "Diffuse Transmission"), data.diffuse_transmission)
            _set_first_input(bsdf, ("Diffuse Transmission Color",), (*data.diffuse_transmission_color, 1.0))

    _set_input(color_target, color_input, base_color)
    if alpha_socket:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass
    nodes_ms = lap_ms()

    _set_assetkit_material_props(mat, data)
    _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
    props_ms = lap_ms()
    settings_node = _ensure_gltf_settings_node(mat, data, bsdf)
    settings_ms = lap_ms()

    previous_texture_node_cache = _textures.ACTIVE_NODE_CACHE
    previous_separate_color_cache = _textures.ACTIVE_SEPARATE_COLOR_CACHE
    _textures.ACTIVE_NODE_CACHE = {}
    _textures.ACTIVE_SEPARATE_COLOR_CACHE = {}
    try:
        if data.base_color_texture or color_attr:
            _link_base_color(mat, color_target, data, color_attr, color_input, alpha_socket)
        if data.metallic_roughness_texture:
            _link_metallic_roughness_texture(
                mat,
                bsdf,
                data.metallic_roughness_texture,
                _texture_info(data, "metallic_roughness"),
                metallic_factor=data.metallic,
                roughness_factor=data.roughness,
            )
        if data.occlusion_texture and bsdf == color_target:
            _link_occlusion_texture(mat, bsdf, data, settings_node)
        if data.normal_texture:
            _link_normal_texture(mat, bsdf, data.normal_texture, data.normal_scale, _texture_info(data, "normal"))
        if data.emissive_texture:
            _link_emissive_texture(
                mat,
                bsdf,
                data,
            )
        if data.transparent_texture and alpha_socket:
            _link_transparent_texture(mat, alpha_socket, data)
        if data.specular_texture:
            if int(data.material_type) == _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS:
                _link_specular_glossiness_texture(mat, bsdf, data)
            else:
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.specular_texture,
                    ("Specular IOR Level", "Specular"),
                    colorspace="Non-Color",
                    channel="Alpha",
                    factor=_pbr_specular_level(data),
                    tex_info=_texture_info(data, "specular"),
                )
        if data.specular_color_texture:
            _link_color_texture(
                mat,
                bsdf,
                data.specular_color_texture,
                ("Specular Tint",),
                colorspace="sRGB",
                factor=(*data.specular_color, 1.0),
                tex_info=_texture_info(data, "specular_color"),
            )
        if data.clearcoat_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.clearcoat_texture,
                ("Coat Weight", "Clearcoat"),
                colorspace="Non-Color",
                channel="Red",
                factor=data.clearcoat,
                tex_info=_texture_info(data, "clearcoat"),
            )
        if data.clearcoat_roughness_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.clearcoat_roughness_texture,
                ("Coat Roughness", "Clearcoat Roughness"),
                colorspace="Non-Color",
                channel="Green",
                factor=data.clearcoat_roughness,
                tex_info=_texture_info(data, "clearcoat_roughness"),
            )
        if data.clearcoat_normal_texture:
            _link_normal_texture(
                mat,
                bsdf,
                data.clearcoat_normal_texture,
                data.clearcoat_normal_scale,
                _texture_info(data, "clearcoat_normal"),
                input_name="Coat Normal",
            )
        if data.transmission_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.transmission_texture,
                ("Transmission Weight", "Transmission"),
                colorspace="Non-Color",
                channel="Red",
                factor=data.transmission,
                tex_info=_texture_info(data, "transmission"),
            )
        if data.sheen_color_texture:
            _link_color_texture(
                mat,
                bsdf,
                data.sheen_color_texture,
                ("Sheen Tint",),
                colorspace="sRGB",
                factor=(*data.sheen_color, 1.0),
                tex_info=_texture_info(data, "sheen_color"),
            )
        if data.sheen_roughness_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.sheen_roughness_texture,
                ("Sheen Roughness",),
                colorspace="Non-Color",
                channel="Alpha",
                factor=data.sheen_roughness,
                tex_info=_texture_info(data, "sheen_roughness"),
            )
        if data.iridescence_thickness_texture:
            _link_range_texture(
                mat,
                bsdf,
                data.iridescence_thickness_texture,
                ("Thin Film Thickness",),
                colorspace="Non-Color",
                channel="Green",
                minimum=data.iridescence_thickness_minimum,
                maximum=data.iridescence_thickness_maximum,
                tex_info=_texture_info(data, "iridescence_thickness"),
            )
        if data.iridescence_texture:
            iridescence_inputs = ("Thin Film Weight", "Iridescence Weight", "Iridescence")
            if _has_input(bsdf, iridescence_inputs):
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.iridescence_texture,
                    iridescence_inputs,
                    colorspace="Non-Color",
                    channel="Red",
                    factor=data.iridescence,
                    tex_info=_texture_info(data, "iridescence"),
                )
            elif settings_node:
                _link_factor_texture(
                    mat,
                    settings_node,
                    data.iridescence_texture,
                    ("Iridescence Factor",),
                    colorspace="Non-Color",
                    channel="Red",
                    factor=data.iridescence,
                    tex_info=_texture_info(data, "iridescence"),
                )
        if data.volume_thickness_texture:
            volume_inputs = ("Volume Thickness", "Thickness")
            if _has_input(bsdf, volume_inputs):
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.volume_thickness_texture,
                    volume_inputs,
                    colorspace="Non-Color",
                    channel="Green",
                    factor=data.volume_thickness,
                    tex_info=_texture_info(data, "volume_thickness"),
                )
            elif settings_node:
                _link_factor_texture(
                    mat,
                    settings_node,
                    data.volume_thickness_texture,
                    ("Thickness",),
                    colorspace="Non-Color",
                    channel="Green",
                    factor=data.volume_thickness,
                    tex_info=_texture_info(data, "volume_thickness"),
                )
        diffuse_transmission_inputs = ("Diffuse Transmission Weight", "Diffuse Transmission")
        if data.anisotropy_texture:
            _link_anisotropy_texture(mat, bsdf, data)
        if data.diffuse_transmission_texture and _has_input(bsdf, diffuse_transmission_inputs):
            _link_factor_texture(
                mat,
                bsdf,
                data.diffuse_transmission_texture,
                diffuse_transmission_inputs,
                colorspace="Non-Color",
                channel="Alpha",
                factor=data.diffuse_transmission,
                tex_info=_texture_info(data, "diffuse_transmission"),
            )
        if data.diffuse_transmission_color_texture and _has_input(bsdf, ("Diffuse Transmission Color",)):
            _link_color_texture(
                mat,
                bsdf,
                data.diffuse_transmission_color_texture,
                ("Diffuse Transmission Color",),
                colorspace="sRGB",
                factor=(*data.diffuse_transmission_color, 1.0),
                tex_info=_texture_info(data, "diffuse_transmission_color"),
            )
        if _has_diffuse_transmission(data) and not _has_input(bsdf, diffuse_transmission_inputs):
            _link_diffuse_transmission_shader(mat, data)
        if data.volume_thickness > 0.0:
            _link_volume_absorption(mat, data)
        if _has_volume_scatter(data):
            _link_volume_scatter(mat, data)
    finally:
        _textures.ACTIVE_NODE_CACHE = previous_texture_node_cache
        _textures.ACTIVE_SEPARATE_COLOR_CACHE = previous_separate_color_cache
    textures_ms = lap_ms()

    _apply_material_animation(mat, data, bsdf, color_target, color_input, alpha_socket, settings_node)
    animation_ms = lap_ms()

    if material_cache is not None:
        material_cache[cache_key] = mat
    if profile_detail:
        _record_material_profile(
            cache_hit=False,
            cache_key_ms=cache_key_ms,
            new_ms=new_ms,
            simple_ms=0.0,
            nodes_ms=nodes_ms,
            props_ms=props_ms,
            settings_ms=settings_ms,
            textures_ms=textures_ms,
            animation_ms=animation_ms,
            total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
        )
    return mat


def _can_use_simple_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if data.material_anim_channels:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return False
    if data.texture_infos:
        return False
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return False
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return False
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return False
    if float(data.volume_thickness) > 0.0 or float(data.dispersion) != 0.0:
        return False
    return True


def _can_use_scalar_principled_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if data.material_anim_channels:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return False
    if data.texture_infos:
        return False
    if float(data.volume_thickness) > 0.0 or _has_volume_scatter(data):
        return False
    return True


def _can_use_base_color_texture_fast_material(
    data: MeshPrimitiveData,
    color_attr: str,
    base_color: tuple[float, float, float, float],
) -> bool:
    if color_attr or not data.base_color_texture:
        return False
    if data.material_anim_channels:
        return False
    if data.material_extra or data.material_variants:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS if name != "base_color_texture"):
        return False
    texture_infos = data.texture_infos or {}
    if any(role != "base_color" for role in texture_infos):
        return False
    tex_info = _texture_info(data, "base_color")
    if tex_info is not None:
        if tex_info.has_transform or _texture_uv_slot(tex_info) != 0:
            return False
        if tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra:
            return False
    if not _tuple_close(base_color, (1.0, 1.0, 1.0, 1.0)):
        return False
    if data.alpha_mode or abs(float(data.opacity) - 1.0) > 1e-6:
        return False
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return False
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return False
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return False
    return float(data.volume_thickness) <= 0.0 and float(data.dispersion) == 0.0


def _can_use_classic_texture_fast_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if not _is_classic_lit_material(data):
        return False
    if data.material_anim_channels or data.material_extra or data.material_variants:
        return False
    if not data.base_color_texture and not data.normal_texture:
        return False
    if (
        data.metallic_roughness_texture
        or data.occlusion_texture
        or data.emissive_texture
        or data.transparent_texture
        or data.specular_texture
        or data.specular_color_texture
        or data.clearcoat_texture
        or data.clearcoat_roughness_texture
        or data.clearcoat_normal_texture
        or data.transmission_texture
        or data.sheen_color_texture
        or data.sheen_roughness_texture
        or data.iridescence_texture
        or data.iridescence_thickness_texture
        or data.volume_thickness_texture
        or data.anisotropy_texture
        or data.diffuse_transmission_texture
        or data.diffuse_transmission_color_texture
    ):
        return False
    if (
        data.alpha_mode
        or data.transparent_inverted
        or abs(float(data.opacity) - 1.0) > 1e-6
        or abs(float(data.transparent_amount) - 1.0) > 1e-6
        or abs(float(data.occlusion_strength) - 1.0) > 1e-6
        or abs(float(data.emissive_strength) - 1.0) > 1e-6
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
        or abs(float(data.transmission)) > 1e-6
        or abs(float(data.sheen_roughness)) > 1e-6
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.volume_thickness)) > 1e-6
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
        or abs(float(data.diffuse_transmission)) > 1e-6
        or abs(float(data.dispersion)) > 1e-6
        or data.has_sheen
    ):
        return False

    texture_infos = data.texture_infos or {}
    if any(role not in {"base_color", "normal"} for role in texture_infos):
        return False
    for role in ("base_color", "normal"):
        tex_info = _texture_info(data, role)
        if tex_info is None:
            continue
        if tex_info.has_transform or _texture_uv_slot(tex_info) != 0:
            return False
        if tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra:
            return False
    return True


def _can_defer_base_color_texture_material(
    data: MeshPrimitiveData,
    color_attr: str,
    base_color: tuple[float, float, float, float],
) -> bool:
    return (
        _textures.ACTIVE_LOAD_MODE == "DEFERRED"
        and _can_use_base_color_texture_fast_material(data, color_attr, base_color)
    )


def _configure_deferred_base_color_texture_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> None:
    mat.diffuse_color = base_color
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)
    _set_material_scalar(mat, "metallic", data.metallic)
    _set_material_scalar(mat, "roughness", data.roughness)
    _set_material_scalar(mat, "specular_intensity", _pbr_specular_level(data))
    try:
        mat["assetkit_deferred_material_nodes"] = True
        mat["assetkit_deferred_base_color_texture"] = data.base_color_texture
    except Exception:
        pass
    _queue_deferred_material_nodes(
        mat,
        data.base_color_texture,
        _texture_info(data, "base_color"),
        base_color,
        float(data.metallic),
        float(data.roughness),
        _is_double_sided_material(data),
    )


def _configure_base_color_texture_fast_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    tex_info = _texture_info(data, "base_color")
    if tex_info is None:
        return _configure_plain_base_color_texture_fast_material(mat, data, base_color)

    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    bsdf_inputs = bsdf.inputs
    if abs(float(data.metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = data.metallic
    if abs(float(data.roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = data.roughness

    colorspace = _texture_color_space(tex_info, "sRGB")
    path = data.base_color_texture
    image = _cached_texture_image(path, colorspace) if _should_defer_texture_image(path) else _load_texture_image(path, colorspace)
    if not image and not _should_defer_texture_image(path):
        return False

    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if tex_info is not None:
        _set_texture_sampler_props(tex, tex_info)
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)

    color_socket = bsdf_inputs.get("Base Color")
    color_output = tex.outputs.get("Color")
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    return True


def _configure_plain_base_color_texture_fast_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    bsdf_inputs = bsdf.inputs
    if abs(float(data.metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = data.metallic
    if abs(float(data.roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = data.roughness

    path = data.base_color_texture
    image = _cached_texture_image(path, "sRGB") if _should_defer_texture_image(path) else _load_texture_image(path, "sRGB")
    if not image and not _should_defer_texture_image(path):
        return False

    tex = tree.nodes.new("ShaderNodeTexImage")
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, "sRGB", store_props=False)

    color_socket = bsdf_inputs.get("Base Color")
    color_output = tex.outputs.get("Color")
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    return True


def _copy_base_color_texture_template_material(
    name: str,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bpy.types.Material | None:
    if not ACTIVE_TEMPLATE_CLONING:
        return _copy_base_color_texture_empty_template_material(name, data, base_color)

    key = _base_color_texture_template_key(data)
    if key is None:
        return None

    template = _MATERIAL_TEMPLATE_CACHE.get(key)
    if template is not None and not _material_ref_alive(template):
        _MATERIAL_TEMPLATE_CACHE.pop(key, None)
        template = None

    if template is None:
        template = bpy.data.materials.new(".AssetKit_BaseColorTexture_Template")
        try:
            template["assetkit_internal_template"] = True
        except Exception:
            pass
        if not _configure_base_color_texture_fast_material(template, data, (1.0, 1.0, 1.0, 1.0)):
            try:
                bpy.data.materials.remove(template)
            except Exception:
                pass
            return None
        _MATERIAL_TEMPLATE_CACHE[key] = template

    try:
        mat = template.copy()
    except Exception:
        return None

    mat.name = name
    mat.diffuse_color = base_color
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if bsdf:
        _set_input(bsdf, "Metallic", data.metallic)
        _set_input(bsdf, "Roughness", data.roughness)
        _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _pbr_specular_level(data))
    else:
        _set_material_scalar(mat, "metallic", data.metallic)
        _set_material_scalar(mat, "roughness", data.roughness)
        _set_material_scalar(mat, "specular_intensity", _pbr_specular_level(data))
    return mat


def _copy_base_color_texture_empty_template_material(
    name: str,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bpy.types.Material | None:
    key = ("base-color-texture-empty-template", int(data.material_type))
    template = _MATERIAL_TEMPLATE_CACHE.get(key)
    if template is not None and not _material_ref_alive(template):
        _MATERIAL_TEMPLATE_CACHE.pop(key, None)
        template = None

    if template is None:
        template = bpy.data.materials.new(".AssetKit_BaseColorTexture_EmptyTemplate")
        try:
            template["assetkit_internal_template"] = True
        except Exception:
            pass
        template.use_nodes = True
        if not template.node_tree or not template.node_tree.nodes.get("Principled BSDF"):
            try:
                bpy.data.materials.remove(template)
            except Exception:
                pass
            return None
        _MATERIAL_TEMPLATE_CACHE[key] = template

    try:
        mat = template.copy()
    except Exception:
        return None

    mat.name = name
    mat.diffuse_color = base_color
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return mat

    bsdf_inputs = bsdf.inputs
    if abs(float(data.metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = data.metallic
    if abs(float(data.roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = data.roughness
    specular_level = _pbr_specular_level(data)
    if abs(float(specular_level) - 0.5) > 1e-6:
        _set_first_input(bsdf, ("Specular IOR Level", "Specular"), specular_level)

    tex_info = _texture_info(data, "base_color")
    tex = _new_fast_image_texture_node(
        tree,
        data.base_color_texture,
        tex_info,
        _texture_color_space(tex_info, "sRGB"),
    )
    color_socket = bsdf_inputs.get("Base Color")
    color_output = tex.outputs.get("Color") if tex else None
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    return mat


def _base_color_texture_template_key(data: MeshPrimitiveData) -> object | None:
    tex_info = _texture_info(data, "base_color")
    colorspace = _texture_color_space(tex_info, "sRGB")
    texture_key = _texture_node_cache_key(data.base_color_texture, colorspace, tex_info)
    if texture_key is None:
        return None
    return ("base-color-texture-template", int(data.material_type), texture_key)


def _copy_classic_texture_template_material(
    name: str,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bpy.types.Material | None:
    if not ACTIVE_TEMPLATE_CLONING:
        return None

    key = _classic_texture_template_key(data)
    if key is None:
        return None

    template = _MATERIAL_TEMPLATE_CACHE.get(key)
    if template is not None and not _material_ref_alive(template):
        _MATERIAL_TEMPLATE_CACHE.pop(key, None)
        template = None

    if template is None:
        template = bpy.data.materials.new(".AssetKit_ClassicTexture_Template")
        try:
            template["assetkit_internal_template"] = True
        except Exception:
            pass
        if not _configure_classic_texture_fast_material(template, data, (1.0, 1.0, 1.0, 1.0)):
            try:
                bpy.data.materials.remove(template)
            except Exception:
                pass
            return None
        _MATERIAL_TEMPLATE_CACHE[key] = template

    try:
        mat = template.copy()
    except Exception:
        return None

    mat.name = name
    mat.diffuse_color = base_color
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if bsdf:
        _set_input(bsdf, "Base Color", base_color)
        _set_input(bsdf, "Metallic", 0.0)
        _set_input(bsdf, "Roughness", _classic_roughness(data.specular_strength))
        _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _classic_specular(data))
        _set_input(
            bsdf,
            "Emission Color",
            (*data.emissive_color, 1.0) if _has_emission(data) else (0.0, 0.0, 0.0, 1.0),
        )
        _set_first_input(bsdf, ("Emission Strength",), _emission_strength(data) if _has_emission(data) else 0.0)
        _set_first_input(
            bsdf,
            ("Specular Tint",),
            (*data.specular_color, 1.0) if _has_specular(data) else (1.0, 1.0, 1.0, 1.0),
        )
        _set_first_input(bsdf, ("IOR",), _material_ior(data))

    normal_map = _normal_map_node(mat, "normal")
    if normal_map:
        scale = normal_map.inputs.get("Strength")
        if scale:
            try:
                scale.default_value = data.normal_scale
            except TypeError:
                pass
    return mat


def _classic_texture_template_key(data: MeshPrimitiveData) -> object | None:
    base_key: object = None
    normal_key: object = None

    if data.base_color_texture:
        base_info = _texture_info(data, "base_color")
        base_key = _texture_node_cache_key(
            data.base_color_texture,
            _texture_color_space(base_info, "sRGB"),
            base_info,
        )
        if base_key is None:
            return None

    if data.normal_texture:
        normal_info = _texture_info(data, "normal")
        normal_key = _texture_node_cache_key(
            data.normal_texture,
            _texture_color_space(normal_info, "Non-Color"),
            normal_info,
        )
        if normal_key is None:
            return None

    return ("classic-texture-template", int(data.material_type), base_key, normal_key)


def _material_ref_alive(mat: bpy.types.Material) -> bool:
    try:
        return bpy.data.materials.get(mat.name) == mat
    except ReferenceError:
        return False
    except Exception:
        return False


def _reset_material_template_cache() -> None:
    if not _MATERIAL_TEMPLATE_CACHE:
        return

    templates = tuple(_MATERIAL_TEMPLATE_CACHE.values())
    _MATERIAL_TEMPLATE_CACHE.clear()
    for mat in templates:
        try:
            if bpy.data.materials.get(mat.name) == mat:
                bpy.data.materials.remove(mat)
        except ReferenceError:
            pass
        except Exception:
            pass


def _new_fast_image_texture_node(tree, path: str, tex_info: TextureRefData | None, colorspace: str):
    if not path:
        return None
    image = _cached_texture_image(path, colorspace) if _should_defer_texture_image(path) else _load_texture_image(path, colorspace)
    if not image and not _should_defer_texture_image(path):
        return None

    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if tex_info is not None:
        _set_texture_sampler_props(tex, tex_info)
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)
    return tex


def _configure_classic_texture_fast_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Roughness", _classic_roughness(data.specular_strength))
    _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _classic_specular(data))
    if _has_emission(data):
        _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))
        _set_first_input(bsdf, ("Emission Strength",), _emission_strength(data))
    if _has_specular(data):
        _set_first_input(bsdf, ("Specular Tint",), (*data.specular_color, 1.0))
    _set_first_input(bsdf, ("IOR",), _material_ior(data))

    base_info = _texture_info(data, "base_color")
    base_tex = _new_fast_image_texture_node(
        tree,
        data.base_color_texture,
        base_info,
        _texture_color_space(base_info, "sRGB"),
    )
    if base_tex and color_socket:
        color_output = base_tex.outputs.get("Color")
        if color_output:
            tree.links.new(color_output, color_socket)

    normal_info = _texture_info(data, "normal")
    normal_tex = _new_fast_image_texture_node(
        tree,
        data.normal_texture,
        normal_info,
        _texture_color_space(normal_info, "Non-Color"),
    )
    normal_socket = bsdf_inputs.get("Normal")
    if normal_tex and normal_socket:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        normal_map.label = "AssetKit normal"
        try:
            normal_map["assetkit_normal_role"] = "normal"
        except Exception:
            pass
        if abs(float(data.normal_scale) - 1.0) > 1e-6:
            scale = normal_map.inputs.get("Strength")
            if scale:
                scale.default_value = data.normal_scale
        color_output = normal_tex.outputs.get("Color")
        color_input = normal_map.inputs.get("Color")
        normal_output = normal_map.outputs.get("Normal")
        if color_output and color_input:
            tree.links.new(color_output, color_input)
        if normal_output:
            tree.links.new(normal_output, normal_socket)
    return True


def _configure_scalar_principled_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    diffuse_transmission_inputs = ("Diffuse Transmission Weight", "Diffuse Transmission")
    if _has_diffuse_transmission(data) and not _has_input(bsdf, diffuse_transmission_inputs):
        return False
    if float(data.dispersion) != 0.0 and not _has_input(bsdf, ("Dispersion",)):
        return False

    inputs = bsdf.inputs

    def set_input(name: str, value) -> None:
        socket = inputs.get(name)
        if socket:
            try:
                socket.default_value = value
            except TypeError:
                pass

    def set_first(names: tuple[str, ...], value) -> None:
        for name in names:
            socket = inputs.get(name)
            if socket:
                try:
                    socket.default_value = value
                except TypeError:
                    pass
                return

    set_input("Base Color", base_color)
    set_input("Metallic", data.metallic)
    set_input("Roughness", data.roughness)
    set_first(("Specular IOR Level", "Specular"), _pbr_specular_level(data))
    set_first(("IOR",), _material_ior(data))

    alpha_socket = inputs.get("Alpha")
    if alpha_socket:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass

    if _has_emission(data):
        set_input("Emission Color", (*data.emissive_color, 1.0))
        set_first(("Emission Strength",), _emission_strength(data))
    if _has_specular(data):
        set_first(("Specular Tint",), (*data.specular_color, 1.0))
    if _has_clearcoat(data):
        set_first(("Coat Weight", "Clearcoat"), data.clearcoat)
        set_first(("Coat Roughness", "Clearcoat Roughness"), data.clearcoat_roughness)
    if _has_transmission(data):
        set_first(("Transmission Weight", "Transmission"), data.transmission)
    if _has_sheen(data):
        set_first(("Sheen Weight", "Sheen"), 1.0 if data.has_sheen else 0.0)
        set_first(("Sheen Tint",), (*data.sheen_color, 1.0))
        set_first(("Sheen Roughness",), data.sheen_roughness)
    if _has_anisotropy(data):
        set_first(("Anisotropic",), data.anisotropy)
        set_first(("Anisotropic Rotation",), _blender_anisotropy_rotation(data.anisotropy_rotation))
    if _has_iridescence(data):
        set_first(("Thin Film IOR",), data.iridescence_ior)
        set_first(("Thin Film Weight", "Iridescence Weight", "Iridescence"), data.iridescence)
        set_first(("Thin Film Thickness",), data.iridescence_thickness_maximum)
    if data.dispersion:
        set_first(("Dispersion",), data.dispersion)
    if _has_diffuse_transmission(data):
        set_first(diffuse_transmission_inputs, data.diffuse_transmission)
        set_first(("Diffuse Transmission Color",), (*data.diffuse_transmission_color, 1.0))

    return True


def _queue_deferred_material_nodes(
    mat: bpy.types.Material,
    path: str,
    tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
    double_sided: bool,
) -> None:
    if not path:
        return

    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    _DEFERRED_MATERIAL_NODE_TASKS.append(
        (mat, path, tex_info, base_color, metallic, roughness, double_sided)
    )
    if not _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE:
        _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_material_node_timer, first_interval=0.001)


def _queue_deferred_classic_material_nodes(
    mat: bpy.types.Material,
    base_path: str,
    base_tex_info: TextureRefData | None,
    normal_path: str,
    normal_tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    roughness: float,
    specular: float,
    has_specular_tint: bool,
    specular_color: tuple[float, float, float],
    has_emission: bool,
    emissive_color: tuple[float, float, float],
    emissive_strength: float,
    ior: float,
    normal_scale: float,
    double_sided: bool,
) -> None:
    if not base_path and not normal_path:
        return

    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    _DEFERRED_MATERIAL_NODE_TASKS.append(
        (
            "classic",
            mat,
            base_path,
            base_tex_info,
            normal_path,
            normal_tex_info,
            base_color,
            roughness,
            specular,
            has_specular_tint,
            specular_color,
            has_emission,
            emissive_color,
            emissive_strength,
            ior,
            normal_scale,
            double_sided,
        )
    )
    if not _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE:
        _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_material_node_timer, first_interval=0.001)


def _deferred_material_node_timer() -> float | None:
    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    started_at = time.perf_counter()
    processed = 0
    profile_detail = _profile_state.stats is not None

    while _DEFERRED_MATERIAL_NODE_TASKS:
        task = _DEFERRED_MATERIAL_NODE_TASKS.popleft()
        mat = task[1] if task and task[0] == "classic" else task[0]
        try:
            if _material_ref_alive(mat):
                if task and task[0] == "classic":
                    _apply_deferred_classic_texture_material(*task[1:])
                else:
                    _apply_deferred_base_color_texture_material(*task)
                processed += 1
        except Exception:
            pass
        if time.perf_counter() - started_at >= _DEFERRED_MATERIAL_NODE_TIME_BUDGET:
            if profile_detail and processed:
                _profile_log(
                    "deferred_material_nodes "
                    f"materials={processed} remaining={len(_DEFERRED_MATERIAL_NODE_TASKS)} "
                    f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
                )
            return 0.001

    _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = False
    if profile_detail and processed:
        _profile_log(
            "deferred_material_nodes "
            f"materials={processed} remaining=0 "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return None


def _material_ref_alive(mat: bpy.types.Material) -> bool:
    try:
        return bpy.data.materials.get(mat.name) is mat
    except Exception:
        return False


def _apply_deferred_base_color_texture_material(
    mat: bpy.types.Material,
    path: str,
    tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
    double_sided: bool,
) -> None:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    if abs(float(metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = metallic
    if abs(float(roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = roughness

    colorspace = _texture_color_space(tex_info, "sRGB")
    image = _cached_texture_image(path, colorspace)
    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if tex_info is not None:
        _set_texture_sampler_props(tex, tex_info)
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)

    color_output = tex.outputs.get("Color")
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    try:
        mat["assetkit_deferred_material_nodes"] = False
    except Exception:
        pass


def _apply_deferred_classic_texture_material(
    mat: bpy.types.Material,
    base_path: str,
    base_tex_info: TextureRefData | None,
    normal_path: str,
    normal_tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    roughness: float,
    specular: float,
    has_specular_tint: bool,
    specular_color: tuple[float, float, float],
    has_emission: bool,
    emissive_color: tuple[float, float, float],
    emissive_strength: float,
    ior: float,
    normal_scale: float,
    double_sided: bool,
) -> None:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Roughness", roughness)
    _set_first_input(bsdf, ("Specular IOR Level", "Specular"), specular)
    if has_emission:
        _set_input(bsdf, "Emission Color", (*emissive_color, 1.0))
        _set_first_input(bsdf, ("Emission Strength",), emissive_strength)
    if has_specular_tint:
        _set_first_input(bsdf, ("Specular Tint",), (*specular_color, 1.0))
    _set_first_input(bsdf, ("IOR",), ior)

    base_tex = _new_fast_image_texture_node(
        tree,
        base_path,
        base_tex_info,
        _texture_color_space(base_tex_info, "sRGB"),
    )
    if base_tex and color_socket:
        color_output = base_tex.outputs.get("Color")
        if color_output:
            tree.links.new(color_output, color_socket)

    normal_tex = _new_fast_image_texture_node(
        tree,
        normal_path,
        normal_tex_info,
        _texture_color_space(normal_tex_info, "Non-Color"),
    )
    normal_socket = bsdf_inputs.get("Normal")
    if normal_tex and normal_socket:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        if abs(float(normal_scale) - 1.0) > 1e-6:
            scale = normal_map.inputs.get("Strength")
            if scale:
                scale.default_value = normal_scale
        color_output = normal_tex.outputs.get("Color")
        color_input = normal_map.inputs.get("Color")
        normal_output = normal_map.outputs.get("Normal")
        if color_output and color_input:
            tree.links.new(color_output, color_input)
        if normal_output:
            tree.links.new(normal_output, normal_socket)
    try:
        mat["assetkit_deferred_material_nodes"] = False
    except Exception:
        pass


def _configure_simple_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> None:
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)
    if _has_nondefault_assetkit_material_props(data):
        _set_assetkit_material_props(mat, data)
    _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
    if not getattr(mat, "use_nodes", False):
        _set_material_scalar(mat, "metallic", data.metallic)
        _set_material_scalar(mat, "roughness", data.roughness)
        _set_material_scalar(mat, "specular_intensity", _pbr_specular_level(data))
        return
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return
    _set_input(bsdf, "Base Color", base_color)
    if abs(float(data.metallic)) > 1e-6:
        _set_input(bsdf, "Metallic", data.metallic)
    if abs(float(data.roughness) - 0.5) > 1e-6:
        _set_input(bsdf, "Roughness", data.roughness)
    specular_level = _pbr_specular_level(data)
    if abs(float(specular_level) - 0.5) > 1e-6:
        _set_first_input(bsdf, ("Specular IOR Level", "Specular"), specular_level)
    alpha_socket = bsdf.inputs.get("Alpha") if abs(float(data.opacity) - 1.0) > 1e-6 else None
    if alpha_socket is not None:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass


def _set_material_scalar(mat: bpy.types.Material, attr: str, value: float) -> None:
    if not hasattr(mat, attr):
        return
    try:
        setattr(mat, attr, float(value))
    except TypeError:
        pass


def _has_nondefault_assetkit_material_props(data: MeshPrimitiveData) -> bool:
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return True
    if data.texture_infos:
        return True
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return True
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return True
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return True
    return (
        float(data.volume_thickness) > 0.0
        or float(data.dispersion) != 0.0
        or bool(data.transparent_inverted)
        or abs(float(data.opacity) - 1.0) > 1.0e-6
        or not _tuple_close(data.transparent_color, (1.0, 1.0, 1.0, 1.0))
    )


def _has_material_data(data: MeshPrimitiveData) -> bool:
    if (
        not data.material_name
        and not data.material_key
        and not data.material_type
        and not data.alpha_mode
        and not data.transparent_inverted
        and not data.texture_infos
        and not data.color_sets
        and not data.base_color_texture
        and not data.metallic_roughness_texture
        and not data.occlusion_texture
        and not data.normal_texture
        and not data.emissive_texture
        and not data.transparent_texture
        and not data.specular_texture
        and not data.specular_color_texture
        and not data.clearcoat_texture
        and not data.clearcoat_roughness_texture
        and not data.clearcoat_normal_texture
        and not data.transmission_texture
        and not data.sheen_color_texture
        and not data.sheen_roughness_texture
        and not data.iridescence_texture
        and not data.iridescence_thickness_texture
        and not data.volume_thickness_texture
        and not data.anisotropy_texture
        and not data.diffuse_transmission_texture
        and not data.diffuse_transmission_color_texture
    ):
        return False
    if data.material_name:
        return True
    if _color_attribute_name(data):
        return True
    return _material_cache_key(data) != _default_material_cache_key()


def _material_cache_key_for_data(data: MeshPrimitiveData) -> object:
    if (
        not data.material_name
        and not data.material_key
        and not data.material_type
        and not data.alpha_mode
        and not data.transparent_inverted
        and not data.texture_infos
        and not data.color_sets
        and not data.base_color_texture
        and not data.metallic_roughness_texture
        and not data.occlusion_texture
        and not data.normal_texture
        and not data.emissive_texture
        and not data.transparent_texture
        and not data.specular_texture
        and not data.specular_color_texture
        and not data.clearcoat_texture
        and not data.clearcoat_roughness_texture
        and not data.clearcoat_normal_texture
        and not data.transmission_texture
        and not data.sheen_color_texture
        and not data.sheen_roughness_texture
        and not data.iridescence_texture
        and not data.iridescence_thickness_texture
        and not data.volume_thickness_texture
        and not data.anisotropy_texture
        and not data.diffuse_transmission_texture
        and not data.diffuse_transmission_color_texture
    ):
        return NO_MATERIAL_CACHE_KEY
    if data.material_name:
        return _material_cache_key(data)
    if _color_attribute_name(data):
        return _material_cache_key(data)
    cache_key = _material_cache_key(data)
    if cache_key == _default_material_cache_key():
        return NO_MATERIAL_CACHE_KEY
    return cache_key


def _material_base_color(data: MeshPrimitiveData) -> tuple[float, float, float, float]:
    if _uses_transparent_as_surface_color(data):
        return (
            float(data.transparent_color[0]),
            float(data.transparent_color[1]),
            float(data.transparent_color[2]),
            float(data.base_color[3]),
        )
    return data.base_color


def _uses_transparent_as_surface_color(data: MeshPrimitiveData) -> bool:
    if data.base_color_texture or data.transparent_texture:
        return False
    if not _is_default_rgb(data.base_color):
        return False
    if _is_default_rgb(data.transparent_color):
        return False
    return True


def _is_default_rgb(values: tuple[float, ...]) -> bool:
    return len(values) >= 3 and all(abs(float(value) - 1.0) <= 1e-6 for value in values[:3])


def _is_unlit_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) == _AK_MATERIAL_TYPE_CONSTANT


def _classic_roughness(shininess: float) -> float:
    value = max(float(shininess), 0.0)
    if value <= 0.0:
        return 1.0
    return max(0.0, min(1.0, math.sqrt(2.0 / (value + 2.0))))


def _classic_specular(data: MeshPrimitiveData) -> float:
    if int(data.material_type) == _AK_MATERIAL_TYPE_LAMBERT:
        return 0.0
    return max(0.0, min(1.0, max(float(v) for v in data.specular_color)))


def _material_ior(data: MeshPrimitiveData) -> float:
    if _is_specular_glossiness_material(data):
        return 1000.0
    return data.ior


def _is_double_sided_material(data: MeshPrimitiveData) -> bool:
    return bool(data.double_sided)


def _set_transparency_overlap(mat: bpy.types.Material, enabled: bool) -> None:
    if hasattr(mat, "use_transparency_overlap"):
        mat.use_transparency_overlap = enabled
    elif hasattr(mat, "show_transparent_back"):
        mat.show_transparent_back = enabled


def _set_material_alpha_mode(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    alpha_mode = int(data.alpha_mode)
    if alpha_mode == 0:
        if getattr(mat, "blend_method", "OPAQUE") != "OPAQUE":
            mat.blend_method = "OPAQUE"
    elif alpha_mode == 1:
        if _prefers_hashed_transparency(data):
            _set_material_enum(mat, "blend_method", "HASHED", "BLEND")
            _set_material_enum(mat, "surface_render_method", "DITHERED")
        else:
            mat.blend_method = "BLEND"
            _set_material_enum(mat, "surface_render_method", "BLENDED")
        _set_transparency_overlap(mat, True)
    elif alpha_mode == 2:
        mat.blend_method = "CLIP"
        _set_material_enum(mat, "surface_render_method", "DITHERED")
        mat.alpha_threshold = data.alpha_cutoff
        _set_transparency_overlap(mat, False)


def _prefers_hashed_transparency(data: MeshPrimitiveData) -> bool:
    if not data.transparent_texture and not _uses_transparent_as_surface_color(data):
        return False
    return bool(data.transparent_inverted)


def _set_material_enum(mat: bpy.types.Material, attr: str, *values: str) -> bool:
    if not hasattr(mat, attr):
        return False
    prop = mat.bl_rna.properties.get(attr)
    enum_values = {item.identifier for item in prop.enum_items} if prop else set()
    for value in values:
        if not enum_values or value in enum_values:
            try:
                setattr(mat, attr, value)
                return True
            except TypeError:
                continue
    return False


def _has_emission(data: MeshPrimitiveData) -> bool:
    if data.emissive_texture:
        return True
    return any(abs(float(value)) > 1e-6 for value in data.emissive_color)


def _has_specular(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.specular_texture)
        or bool(data.specular_color_texture)
        or abs(float(data.specular_strength) - 1.0) > 1e-6
        or not _is_default_rgb(data.specular_color)
    )


def _has_clearcoat(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.clearcoat_texture)
        or bool(data.clearcoat_roughness_texture)
        or bool(data.clearcoat_normal_texture)
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
    )


def _has_transmission(data: MeshPrimitiveData) -> bool:
    return bool(data.transmission_texture) or abs(float(data.transmission)) > 1e-6


def _has_sheen(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.has_sheen)
        or bool(data.sheen_color_texture)
        or bool(data.sheen_roughness_texture)
        or any(abs(float(value)) > 1e-6 for value in data.sheen_color)
        or abs(float(data.sheen_roughness)) > 1e-6
    )


def _has_anisotropy(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.anisotropy_texture)
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
    )


def _has_iridescence(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.iridescence_texture)
        or bool(data.iridescence_thickness_texture)
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.iridescence_ior) - 1.3) > 1e-6
        or abs(float(data.iridescence_thickness_minimum) - 100.0) > 1e-6
        or abs(float(data.iridescence_thickness_maximum) - 400.0) > 1e-6
    )


def _emission_strength(data: MeshPrimitiveData) -> float:
    return float(data.emissive_strength) if _has_emission(data) else 0.0


def _material_cache_key(data: MeshPrimitiveData) -> object:
    color_attr = _color_attribute_name(data)
    native_key = int(getattr(data, "material_key", 0) or 0)
    if native_key and _preserve_native_material_identity(data):
        return ("native", int(data.file_type), native_key, color_attr)
    visual_key = _fast_visual_material_cache_key(data, color_attr)
    if visual_key is not None:
        return visual_key
    return (
        "props",
        data.material_name,
        color_attr,
        _round_tuple(data.base_color),
        _round_tuple(data.emissive_color),
        _round_tuple(data.specular_color),
        _round_tuple(data.sheen_color),
        _round_tuple(data.transparent_color),
        _round_tuple(data.volume_attenuation_color),
        _round_tuple(data.diffuse_transmission_color),
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        round(float(data.opacity), 6),
        round(float(data.alpha_cutoff), 6),
        round(float(data.transparent_amount), 6),
        round(float(data.normal_scale), 6),
        round(float(data.occlusion_strength), 6),
        round(float(data.emissive_strength), 6),
        round(float(data.specular_strength), 6),
        round(float(data.ior), 6),
        round(float(data.clearcoat), 6),
        round(float(data.clearcoat_roughness), 6),
        round(float(data.clearcoat_normal_scale), 6),
        round(float(data.transmission), 6),
        round(float(data.sheen_roughness), 6),
        round(float(data.iridescence), 6),
        round(float(data.iridescence_ior), 6),
        round(float(data.iridescence_thickness_minimum), 6),
        round(float(data.iridescence_thickness_maximum), 6),
        round(float(data.volume_thickness), 6),
        round(float(data.volume_attenuation_distance), 6),
        round(float(data.anisotropy), 6),
        round(float(data.anisotropy_rotation), 6),
        round(float(data.diffuse_transmission), 6),
        round(float(data.dispersion), 6),
        int(data.alpha_mode),
        bool(data.transparent_inverted),
        _is_double_sided_material(data),
        bool(data.has_sheen),
        int(data.material_type),
        int(data.file_type),
        data.base_color_texture,
        data.metallic_roughness_texture,
        data.occlusion_texture,
        data.normal_texture,
        data.emissive_texture,
        data.transparent_texture,
        data.specular_texture,
        data.specular_color_texture,
        data.clearcoat_texture,
        data.clearcoat_roughness_texture,
        data.clearcoat_normal_texture,
        data.transmission_texture,
        data.sheen_color_texture,
        data.sheen_roughness_texture,
        data.iridescence_texture,
        data.iridescence_thickness_texture,
        data.volume_thickness_texture,
        data.anisotropy_texture,
        data.diffuse_transmission_texture,
        data.diffuse_transmission_color_texture,
        _texture_infos_cache_key(data.texture_infos),
        _json_cache_key(data.material_extra),
    )


def _preserve_native_material_identity(data: MeshPrimitiveData) -> bool:
    return bool(
        data.material_name
        or data.material_extra
        or data.material_anim_channels
        or data.material_variants
    )


def _fast_visual_material_cache_key(data: MeshPrimitiveData, color_attr: str) -> object | None:
    key = _fast_simple_native_base_color_texture_key(data)
    if key is not None and not color_attr:
        return key
    key = _fast_base_color_texture_visual_key(data, color_attr)
    if key is not None:
        return key
    return None


def _fast_simple_native_base_color_texture_key(data: MeshPrimitiveData) -> object | None:
    if not getattr(data, "simple_native", False) or not data.base_color_texture:
        return None
    return (
        "visual-base-color-texture",
        int(data.file_type),
        int(data.material_type),
        data.base_color_texture,
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        bool(data.double_sided),
        _texture_infos_cache_key(data.texture_infos),
    )


def _fast_base_color_texture_visual_key(data: MeshPrimitiveData, color_attr: str) -> object | None:
    if color_attr or not data.base_color_texture:
        return None
    if _preserve_native_material_identity(data):
        return None
    if data.texture_infos or data.color_sets or data.colors_f32 or data.point_attrs:
        return None

    material_type = int(data.material_type)
    if material_type in {
        _AK_MATERIAL_TYPE_PHONG,
        _AK_MATERIAL_TYPE_BLINN,
        _AK_MATERIAL_TYPE_LAMBERT,
        _AK_MATERIAL_TYPE_CONSTANT,
        _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS,
    }:
        return None
    if (
        data.metallic_roughness_texture
        or data.occlusion_texture
        or data.normal_texture
        or data.emissive_texture
        or data.transparent_texture
        or data.specular_texture
        or data.specular_color_texture
        or data.clearcoat_texture
        or data.clearcoat_roughness_texture
        or data.clearcoat_normal_texture
        or data.transmission_texture
        or data.sheen_color_texture
        or data.sheen_roughness_texture
        or data.iridescence_texture
        or data.iridescence_thickness_texture
        or data.volume_thickness_texture
        or data.anisotropy_texture
        or data.diffuse_transmission_texture
        or data.diffuse_transmission_color_texture
    ):
        return None
    if (
        data.alpha_mode
        or data.transparent_inverted
        or abs(float(data.opacity) - 1.0) > 1e-6
        or abs(float(data.transparent_amount) - 1.0) > 1e-6
        or abs(float(data.normal_scale) - 1.0) > 1e-6
        or abs(float(data.occlusion_strength) - 1.0) > 1e-6
        or abs(float(data.emissive_strength) - 1.0) > 1e-6
        or abs(float(data.specular_strength) - 1.0) > 1e-6
        or abs(float(data.ior) - 1.5) > 1e-6
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
        or abs(float(data.clearcoat_normal_scale) - 1.0) > 1e-6
        or abs(float(data.transmission)) > 1e-6
        or abs(float(data.sheen_roughness)) > 1e-6
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.iridescence_ior) - 1.3) > 1e-6
        or abs(float(data.iridescence_thickness_minimum) - 100.0) > 1e-6
        or abs(float(data.iridescence_thickness_maximum) - 400.0) > 1e-6
        or abs(float(data.volume_thickness)) > 1e-6
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
        or abs(float(data.diffuse_transmission)) > 1e-6
        or abs(float(data.dispersion)) > 1e-6
        or data.has_sheen
    ):
        return None
    if (
        not _tuple_close(data.base_color, (1.0, 1.0, 1.0, 1.0))
        or not _tuple_close(data.emissive_color, (0.0, 0.0, 0.0))
        or not _tuple_close(data.specular_color, (1.0, 1.0, 1.0))
        or not _tuple_close(data.sheen_color, (0.0, 0.0, 0.0))
        or not _tuple_close(data.transparent_color, (1.0, 1.0, 1.0, 1.0))
        or not _tuple_close(data.volume_attenuation_color, (1.0, 1.0, 1.0))
        or not _tuple_close(data.diffuse_transmission_color, (1.0, 1.0, 1.0))
    ):
        return None

    return (
        "visual-base-color-texture",
        int(data.file_type),
        int(data.material_type),
        data.base_color_texture,
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        bool(data.double_sided),
    )


def _default_material_cache_key() -> object:
    return (
        "props",
        "",
        "",
        (1.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        1.0,
        1.0,
        1.0,
        0.5,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.5,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.3,
        100.0,
        400.0,
        0.0,
        math.inf,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        False,
        False,
        0,
        0,
        *(("",) * 20),
        (),
        "",
        "",
    )


def _round_tuple(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(float(value), 6) for value in values)


def _texture_infos_cache_key(texture_infos: dict[str, TextureRefData] | None) -> tuple:
    if not texture_infos:
        return ()

    items = []
    for role, info in sorted(texture_infos.items()):
        items.append(
            (
                role,
                info.path,
                info.image_name,
                info.sampler_name,
                info.color_space,
                info.channels,
                info.texcoord,
                info.coord_input_name,
                int(info.slot),
                int(info.wrap_s),
                int(info.wrap_t),
                int(info.wrap_p),
                int(info.min_filter),
                int(info.mag_filter),
                int(info.mip_filter),
                bool(info.has_transform),
                _round_tuple(info.transform_offset),
                _round_tuple(info.transform_scale),
                round(float(info.transform_rotation), 6),
                int(info.transform_slot),
                _json_cache_key(info.texture_extra),
                _json_cache_key(info.texref_extra),
                _json_cache_key(info.image_extra),
                _json_cache_key(info.sampler_extra),
            )
        )
    return tuple(items)


def _json_cache_key(value: object | None) -> str:
    if not value:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)


def _color_attribute_name(data: MeshPrimitiveData) -> str:
    if data.color_sets:
        return data.color_sets[0].name or "Color"
    for attr in data.point_attrs or ():
        name = attr.name or ""
        if _is_color_attribute_name(name):
            return name
    if data.colors_f32:
        return "Color"
    return ""
