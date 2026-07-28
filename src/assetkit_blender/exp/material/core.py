from __future__ import annotations

from array import array

import bpy

from ...enums import AK_FILE_TYPE_WAVEFRONT
from ..images import _ExportImageStore
from .animation import _material_animation_payload
from .common import (
    _assetkit_channel_mask,
    _assetkit_json_prop,
    _bake_uv_key,
    _clamp01,
    _linked_texture_info,
    _material_bake_required,
    _material_input_socket,
    _material_surface_extractable,
    _material_type,
    _normal_texture_info,
    _principled_bsdf,
    _prop_float,
    _socket_default,
    _unlit_emission_node,
)
from .constants import _MATERIAL_TYPE_UNLIT
from .features import _material_feature_tuples


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
    file_type: int = 0,
    material_export_mode: str = "AUTO",
    material_bake_size: int = 1024,
    lighting_bake_mode: str = "OFF",
    export_images: bool = True,
) -> tuple | None:
    if material is None:
        return None

    base_color = [float(c) for c in material.diffuse_color]
    metallic = 0.0
    roughness = 1.0
    alpha = base_color[3] if len(base_color) > 3 else 1.0
    base_color_image = None
    base_color_channel = 0
    base_color_texture = None
    base_color_slot = 0
    base_color_info = None
    metallic_texture = None
    metallic_slot = 0
    metallic_info = None
    roughness_texture = None
    roughness_slot = 0
    roughness_info = None
    obj_metallic_texture = None
    obj_metallic_slot = 0
    obj_metallic_channel = 0
    obj_metallic_info = None
    obj_roughness_texture = None
    obj_roughness_slot = 0
    obj_roughness_channel = 0
    obj_roughness_info = None
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
    emissive_image = None
    emissive_channel = 0
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
    lighting_baked = False

    if (
        context is not None
        and obj is not None
        and mesh is not None
        and material_index >= 0
        and export_images
    ):
        bake_name = f"{obj.name}_{material.name}"
        bake_uv = _bake_uv_key(uv_slot_by_name)
        if (lighting_bake_mode or "OFF").upper() == "FINAL":
            baked_base_color_texture = image_store.lighting_bake_path(
                context,
                obj,
                mesh,
                material,
                int(material_index),
                int(material_bake_size),
                bake_name,
                bake_uv,
            )
            lighting_baked = baked_base_color_texture is not None
        if baked_base_color_texture is None and _material_bake_required(material, material_export_mode):
            baked_visual_only = not _material_surface_extractable(material)
            baked_base_color_texture = image_store.shader_bake_path(
                context,
                obj,
                mesh,
                material,
                int(material_index),
                int(material_bake_size),
                bake_name,
                bake_uv,
            )

    if material.use_nodes and material.node_tree and not baked_visual_only:
        bsdf = _principled_bsdf(material)
        unlit_emission = _unlit_emission_node(material)
        if bsdf is not None:
            if export_images:
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
            if export_images:
                features = _material_feature_tuples(bsdf, material, image_store, uv_slot_by_name)
        elif unlit_emission is not None:
            if export_images:
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
            if export_images:
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
        if lighting_baked:
            metallic = 0.0
            roughness = 1.0
            metallic_image = None
            roughness_image = None
            metallic_texture = None
            roughness_texture = None
            metallic_info = None
            roughness_info = None
            obj_metallic_texture = None
            obj_roughness_texture = None
            normal_texture = None
            normal_info = None
            normal_slot = 0
            normal_scale = 1.0
            occlusion_texture = None
            occlusion_info = None
            occlusion_slot = 0
            occlusion_strength = 1.0
            emissive_texture = None
            emissive_info = None
            emissive_slot = 0
            emissive_color = [0.0, 0.0, 0.0, 1.0]
            emissive_strength = 1.0

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
    export_obj = int(file_type or 0) == AK_FILE_TYPE_WAVEFRONT
    if export_obj:
        if metallic_image is not None:
            obj_metallic_texture = image_store.path_for(metallic_image)
            obj_metallic_slot = metallic_slot
            obj_metallic_channel = _assetkit_channel_mask(metallic_channel)
            obj_metallic_info = metallic_info
        if roughness_image is not None:
            obj_roughness_texture = image_store.path_for(roughness_image)
            obj_roughness_slot = roughness_slot
            obj_roughness_channel = _assetkit_channel_mask(roughness_channel)
            obj_roughness_info = roughness_info
        metallic_roughness_texture = None
        metallic_roughness_slot = roughness_slot if roughness_image is not None else metallic_slot
        metallic_roughness_info = roughness_info if roughness_image is not None else metallic_info
    elif (
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
    if lighting_baked:
        material_type = _MATERIAL_TYPE_UNLIT
    elif baked_base_color_texture is not None and bsdf is None:
        material_type = _MATERIAL_TYPE_UNLIT
    animations = None if lighting_baked else _material_animation_payload(material, bsdf, base_color, fps)

    return (
        material.name,
        color,
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
        emissive,
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
        obj_metallic_texture,
        int(obj_metallic_slot),
        int(obj_metallic_channel),
        obj_metallic_info,
        obj_roughness_texture,
        int(obj_roughness_slot),
        int(obj_roughness_channel),
        obj_roughness_info,
    )
