from __future__ import annotations

import math

import bpy

from ...assetkit import MeshPrimitiveData, TextureRefData
from .constants import (
    _AK_MATERIAL_TYPE_BLINN,
    _AK_MATERIAL_TYPE_LAMBERT,
    _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS,
    _AK_MATERIAL_TYPE_PHONG,
)


def _first_input(node, names: tuple[str, ...]):
    if not node:
        return None

    for name in names:
        socket = node.inputs.get(name)
        if socket:
            return socket

    return None


def _has_input(node, names: tuple[str, ...]) -> bool:
    return _first_input(node, names) is not None


def _normal_map_node(mat: bpy.types.Material, role: str):
    return _assetkit_node(mat, "assetkit_normal_role", role)


def _assetkit_node(mat: bpy.types.Material, key: str, value: str):
    node_tree = mat.node_tree
    if not node_tree:
        return None

    for node in node_tree.nodes:
        if node.get(key) == value:
            return node

    return None


def _is_classic_lit_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) in {
        _AK_MATERIAL_TYPE_PHONG,
        _AK_MATERIAL_TYPE_BLINN,
        _AK_MATERIAL_TYPE_LAMBERT,
    }


def _is_specular_glossiness_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) == _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS


def _uses_pbr_specular_level(data: MeshPrimitiveData) -> bool:
    return not _is_classic_lit_material(data) and not _is_specular_glossiness_material(data)


def _pbr_specular_level(data: MeshPrimitiveData) -> float:
    return 0.5 * max(0.0, float(data.specular_strength))


def _blender_anisotropy_rotation(rotation: float) -> float:
    return float(rotation) / (2.0 * math.pi)


def _tuple_close(value, default: tuple[float, ...]) -> bool:
    try:
        values = tuple(value)
    except TypeError:
        return False

    if len(values) != len(default):
        return False

    return all(abs(float(item) - float(expected)) <= 1.0e-6 for item, expected in zip(values, default))


def _texture_info(data: MeshPrimitiveData, role: str) -> TextureRefData | None:
    infos = data.texture_infos or {}
    info = infos.get(role)
    if info is not None:
        return info
    if role == "normal":
        return infos.get("height")
    if role == "specular":
        return infos.get("specular_level")
    return None
