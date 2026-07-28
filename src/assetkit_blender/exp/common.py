from __future__ import annotations

import json
import os
import sys
from array import array

import bpy

from ..enums import (
    AK_FILE_TYPE_3MF,
    AK_FILE_TYPE_DAE,
    AK_FILE_TYPE_GLB,
    AK_FILE_TYPE_GLTF,
    AK_FILE_TYPE_PLY,
    AK_FILE_TYPE_STL,
    AK_FILE_TYPE_WAVEFRONT,
)

EXPORT_FORMATS = (
    ("GLTF", "glTF", "Export .gltf with external .bin/resources", AK_FILE_TYPE_GLTF, ".gltf"),
    ("GLB", "GLB", "Export binary .glb", AK_FILE_TYPE_GLB, ".glb"),
    ("DAE", "COLLADA (.dae)", "Export COLLADA .dae", AK_FILE_TYPE_DAE, ".dae"),
    ("OBJ", "Wavefront OBJ (.obj)", "Export Wavefront OBJ .obj/.mtl", AK_FILE_TYPE_WAVEFRONT, ".obj"),
    ("STL", "STL (.stl)", "Export STL triangle mesh", AK_FILE_TYPE_STL, ".stl"),
    ("PLY", "PLY (.ply)", "Export Polygon File Format mesh", AK_FILE_TYPE_PLY, ".ply"),
    ("3MF", "3MF (.3mf)", "Export 3D Manufacturing Format package", AK_FILE_TYPE_3MF, ".3mf"),
)

_PROFILE_ENABLED: bool | None = None


def _profile_enabled() -> bool:
    global _PROFILE_ENABLED

    if _PROFILE_ENABLED is not None:
        return _PROFILE_ENABLED

    value = os.environ.get("ASSETKIT_BLENDER_PROFILE")
    if value is None or value == "":
        _PROFILE_ENABLED = False
    else:
        _PROFILE_ENABLED = value.lower() not in {"0", "false", "off", "no"}
    return _PROFILE_ENABLED


def _profile_log(message: str) -> None:
    if _profile_enabled():
        print(f"[AssetKit Python] {message}", file=sys.stderr, flush=True)


def _export_document_extra(context: bpy.types.Context) -> object | None:
    scene = context.scene
    targets = (
        scene,
        getattr(context, "collection", None),
        getattr(scene, "world", None),
    )
    for target in targets:
        extra = _assetkit_json_prop(target, "assetkit_document_extra_json")
        if _document_extra_has_exportable_root_extension(extra):
            return extra
    return None


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


def _document_extra_has_exportable_root_extension(extra: object | None) -> bool:
    extensions = _assetkit_extra_path(extra, "extensions")
    if isinstance(extensions, dict) and any(
        isinstance(child, dict) and bool(child.get("name"))
        for child in (extensions.get("children") or ())
    ):
        return True
    required = _assetkit_extra_path(extra, "extensionsRequired")
    return isinstance(required, dict) and any(
        isinstance(child, dict) and bool(child.get("value"))
        for child in (required.get("children") or ())
    )


def _assetkit_extra_path(value: object | None, *path: str) -> object | None:
    node = value
    for name in path:
        node = _assetkit_extra_child(node, name)
        if node is None:
            return None
    return node


def _assetkit_extra_child(value: object | None, name: str) -> object | None:
    if not isinstance(value, dict):
        return None
    for child in value.get("children") or ():
        if isinstance(child, dict) and child.get("name") == name:
            return child
    return None


def _append_matrix_values(values: array, matrix) -> None:
    for col in range(4):
        for row in range(4):
            values.append(float(matrix[row][col]))


def _matrix_values(matrix) -> array:
    values = array("f")
    _append_matrix_values(values, matrix)
    return values


def file_type_from_format(fmt: str) -> int:
    for identifier, _name, _description, file_type, _suffix in EXPORT_FORMATS:
        if identifier == fmt:
            return file_type
    return AK_FILE_TYPE_GLTF


def suffix_from_format(fmt: str) -> str:
    for identifier, _name, _description, _file_type, suffix in EXPORT_FORMATS:
        if identifier == fmt:
            return suffix
    return ".gltf"


def suffix_from_file_type(file_type: int) -> str:
    for _identifier, _name, _description, known_file_type, suffix in EXPORT_FORMATS:
        if known_file_type == file_type:
            return suffix
    return ".gltf"
