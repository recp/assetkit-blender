from __future__ import annotations

import bpy
from mathutils import Matrix

from ...assetkit import MeshPrimitiveData
from ...enums import AK_FILE_TYPE_STL, AK_PRIMITIVE_TRIANGLES
from ..buffers import apply_matrix_buffer as _apply_matrix_buffer, matrix_from_buffer as _matrix_from_buffer
from ..context import ImportState
from ..material import _create_material
from ..mesh import _uses_wavefront_smoothing

ACTIVE_PREBUILT_MATERIALS_BY_ID: dict[int, bpy.types.Material | None] | None = None
_MATERIAL_NOT_PREBUILT = object()

def _effective_shading_mode(data: MeshPrimitiveData, shading_mode: str) -> str:
    mode = str(shading_mode or "AUTO").upper()
    if (
        mode in {"AUTO", "AS_IS"}
        and int(getattr(data, "file_type", 0) or 0) == AK_FILE_TYPE_STL
        and int(getattr(data, "primitive_type", 0) or 0) == AK_PRIMITIVE_TRIANGLES
    ):
        return "FLAT"
    return mode


def _group_wavefront_sharp_faces(primitives: list[MeshPrimitiveData], face_count: int) -> bytearray | bytes:
    if not primitives or face_count <= 0:
        return b""
    if not all(_uses_wavefront_smoothing(primitive) for primitive in primitives):
        return b""
    if any(primitive.normals_f32 or primitive.vertex_normals_f32 for primitive in primitives):
        return b""

    smooth_seen = any(bool(getattr(primitive, "smooth_shading", False)) for primitive in primitives)
    flat_seen = any(not bool(getattr(primitive, "smooth_shading", False)) for primitive in primitives)
    if not (smooth_seen and flat_seen):
        return b""

    sharp_faces = bytearray(face_count)
    face_offset = 0
    for primitive in primitives:
        count = int(primitive.face_count)
        if count <= 0:
            continue
        sharp_faces[face_offset: face_offset + count] = (
            b"\x00" if bool(getattr(primitive, "smooth_shading", False)) else b"\x01"
        ) * count
        face_offset += count
    return sharp_faces


def _mesh_node_parent(state: ImportState, node_index: int) -> tuple[bpy.types.Object | None, bool]:
    compact_plan = state.compact_instance_plan
    if compact_plan is not None:
        node = (state.node_data or {}).get(node_index)
        prototype_root_index = int(node.prototype_root_index) if node is not None else -1
        return (
            None if prototype_root_index >= 0 else state.coord_root,
            False,
        )

    cache = state.node_parent_cache
    if cache is not None:
        cached = cache.get(node_index)
        if cached is not None:
            return cached

    node_objects = state.node_objects
    deferred_build = state.deferred_scene_node_build
    if deferred_build is not None:
        required_indices = deferred_build.get("required_indices")
        if required_indices is None or node_index in required_indices:
            result = (None, True)
            if cache is not None:
                cache[node_index] = result
            return result

        node_data = state.node_data
        current = node_data.get(node_index)
        parent_index = int(current.parent_index) if current is not None else -1
        remaining = len(node_data)
        while parent_index >= 0 and remaining > 0:
            if parent_index in required_indices:
                result = (None, False)
                if cache is not None:
                    cache[node_index] = result
                return result
            current = node_data.get(parent_index)
            parent_index = int(current.parent_index) if current is not None else -1
            remaining -= 1

        prototype_root_index = int(current.prototype_root_index) if current is not None else -1
        result = (
            None if prototype_root_index >= 0 else state.coord_root,
            False,
        )
        if cache is not None:
            cache[node_index] = result
        return result

    node_parent = node_objects.get(node_index)
    if node_parent is not None:
        result = (node_parent, True)
        if cache is not None:
            cache[node_index] = result
        return result

    node_data = state.node_data
    current = node_data.get(node_index)
    parent_index = int(current.parent_index) if current is not None else -1
    remaining = len(node_data)
    while parent_index >= 0 and remaining > 0:
        parent = node_objects.get(parent_index)
        if parent is not None:
            result = (parent, False)
            if cache is not None:
                cache[node_index] = result
            return result
        current = node_data.get(parent_index)
        parent_index = int(current.parent_index) if current is not None else -1
        remaining -= 1

    prototype_root_index = int(current.prototype_root_index) if current is not None else -1
    result = (
        None if prototype_root_index >= 0 else state.coord_root,
        False,
    )
    if cache is not None:
        cache[node_index] = result
    return result


def _node_import_collection(
    state: ImportState,
    node_index: int,
    default_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    node = (state.node_data or {}).get(node_index)
    prototype_root_index = int(node.prototype_root_index) if node is not None else -1
    if prototype_root_index < 0:
        return default_collection
    return (state.prototype_collections or {}).get(
        prototype_root_index,
        default_collection,
    )


def _material_for_data(
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None,
) -> bpy.types.Material | None:
    prebuilt = ACTIVE_PREBUILT_MATERIALS_BY_ID
    if prebuilt is not None:
        material = prebuilt.get(id(data), _MATERIAL_NOT_PREBUILT)
        if material is not _MATERIAL_NOT_PREBUILT:
            return material
    return _create_material(data, material_cache)


def _compact_object_matrix(plan: dict, node_index: int) -> Matrix | None:
    matrices = plan["object_matrices"]
    matrix = matrices.get(node_index)
    if matrix is not None:
        return matrix

    source = plan["matrix_buffers"].get(node_index)
    if source is None:
        return None
    if isinstance(source, Matrix):
        matrix = source
    else:
        matrix = _matrix_from_buffer(source)
    if matrix is not None:
        matrices[node_index] = matrix
    return matrix


def _blender_natural_name_key(name: str) -> str:
    return str(name or "").casefold()


def _set_parent(obj: bpy.types.Object, parent: bpy.types.Object | None) -> None:
    if not parent:
        return

    obj.parent = parent
    obj.matrix_parent_inverse.identity()


def _apply_matrix(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    _apply_matrix_buffer(obj, data.matrix_f32)
