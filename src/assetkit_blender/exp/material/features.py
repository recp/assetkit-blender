from __future__ import annotations

import math
from array import array

import bpy

from ..images import _ExportImageStore
from .common import (
    _color_socket_values,
    _color_texture_payload,
    _color_texture_used,
    _float_payload_view,
    _material_input_socket,
    _normal_texture_info,
    _prop_color_values,
    _prop_float,
    _prop_str,
    _prop_texture_info_tuple,
    _prop_texture_slot,
    _scalar_texture_payload,
    _scalar_texture_payload_first,
    _scalar_texture_used,
    _socket_default,
    _socket_float,
    _socket_float_from_socket,
    _specular_glossiness_payload,
    _volume_absorption_node,
    _volume_scatter_node,
)
from .constants import (
    _FEATURE_ANISOTROPY,
    _FEATURE_CLEARCOAT,
    _FEATURE_DIFFUSE_TRANSMISSION,
    _FEATURE_DISPERSION,
    _FEATURE_IOR,
    _FEATURE_IRIDESCENCE,
    _FEATURE_SHEEN,
    _FEATURE_SPECULAR,
    _FEATURE_SPECULAR_GLOSSINESS,
    _FEATURE_SUBSURFACE,
    _FEATURE_TRANSMISSION,
    _FEATURE_VOLUME,
    _MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS,
)


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
        attenuation_color = _color_socket_values(_material_input_socket(material, "Color"), (1.0, 1.0, 1.0, 1.0))
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
            _prop_color_values(material, "assetkit_volume_attenuation_color", (1.0, 1.0, 1.0, 1.0)),
            float(_prop_float(material, "assetkit_volume_attenuation_distance", float("inf"))),
        ))
        volume_used = True

    volume_absorption = _volume_absorption_node(material)
    if transmission_used and not volume_used and volume_absorption is not None:
        attenuation_color = _color_socket_values(
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
    diffuse_transmission_color = _prop_color_values(
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

    volume_scatter_color = _prop_color_values(
        material,
        "assetkit_volume_scatter_multiscatter_color",
        (0.0, 0.0, 0.0, 1.0),
    )
    volume_scatter_anisotropy = _prop_float(material, "assetkit_volume_scatter_anisotropy", 0.0)
    volume_scatter_values = _float_payload_view(volume_scatter_color)
    custom_scatter_used = (
        volume_scatter_anisotropy != 0.0
        or any(abs(float(value)) > 1.0e-6 for value in volume_scatter_values[:3])
    )
    if custom_scatter_used:
        features.append((
            _FEATURE_SUBSURFACE,
            0.0,
            volume_scatter_color,
            array("f", (0.0, 0.0, 0.0, 1.0)),
            float(volume_scatter_anisotropy),
        ))
    elif (volume_scatter := _volume_scatter_node(material)) is not None:
        scatter_color = _color_socket_values(
            volume_scatter.inputs.get("Color"),
            (0.0, 0.0, 0.0, 1.0),
        )
        scatter_values = _float_payload_view(scatter_color)
        scatter_anisotropy = _socket_float(volume_scatter, "Anisotropy", 0.0)
        if scatter_anisotropy != 0.0 or any(abs(float(value)) > 1.0e-6 for value in scatter_values[:3]):
            features.append((
                _FEATURE_SUBSURFACE,
                0.0,
                scatter_color,
                array("f", (0.0, 0.0, 0.0, 1.0)),
                float(scatter_anisotropy),
            ))
            custom_scatter_used = True

    subsurface_weight = _socket_float(bsdf, "Subsurface Weight", 0.0)
    if subsurface_weight > 0.0 and not custom_scatter_used:
        radius = _socket_default(bsdf, "Subsurface Radius")
        radius_values = array("f", (
            float(radius[0]) if radius is not None and len(radius) > 0 else 1.0,
            float(radius[1]) if radius is not None and len(radius) > 1 else 0.2,
            float(radius[2]) if radius is not None and len(radius) > 2 else 0.1,
            1.0,
        ))
        features.append((
            _FEATURE_SUBSURFACE,
            float(subsurface_weight),
            _color_socket_values(bsdf.inputs.get("Base Color"), (1.0, 1.0, 1.0, 1.0)),
            radius_values,
            float(_socket_float(bsdf, "Subsurface Anisotropy", 0.0)),
        ))

    return features
