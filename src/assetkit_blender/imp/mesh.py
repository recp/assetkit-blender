from __future__ import annotations

import time
from array import array
from collections import deque

import bpy

from ..assetkit import (
    MeshPrimitiveData,
    _profile_log,
    native_fill_triangle_loop_offsets_ptr,
    native_fill_u8_ptr,
)
from ..enums import (
    AK_FILE_TYPE_WAVEFRONT,
    AK_PRIMITIVE_POLYGONS,
    AK_PRIMITIVE_TRIANGLES,
)
from . import profile as _profile_state, textures as _textures
from .attributes import is_color_attribute_name as _is_color_attribute_name
from .buffers import buffer_view as _buffer_view
from .material import core as _materials, _deferred_material_node_timer
from .textures import _deferred_texture_timer

_DEFERRED_NORMAL_TIME_BUDGET = 0.006
_DEFERRED_NORMAL_TASKS: deque[tuple[bpy.types.Mesh, object, object | None, object | None]] = deque()
_DEFERRED_NORMAL_TIMER_ACTIVE = False
_BOOL_ARRAYS: dict[tuple[int, int], array] = {}
_TRI_LOOP_START_ARRAYS: dict[int, array] = {}
_TRI_LOOP_START_CACHE_LIMIT = 65536


def _uses_wavefront_smoothing(data: MeshPrimitiveData) -> bool:
    return (
        int(getattr(data, "file_type", 0) or 0) == AK_FILE_TYPE_WAVEFRONT
        and int(getattr(data, "primitive_type", 0) or 0) in (AK_PRIMITIVE_TRIANGLES, AK_PRIMITIVE_POLYGONS)
    )


def _ensure_object_material_slot(mesh: bpy.types.Mesh) -> int:
    if not mesh.materials:
        mesh.materials.append(None)
    return 0


def _assign_mesh_material(
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    material: bpy.types.Material,
    *,
    object_material_slot: bool = False,
) -> None:
    if object_material_slot:
        _assign_object_material_slot(obj, material)
        return
    if not mesh.materials:
        mesh.materials.append(material)
        return
    mesh.materials.append(material)


def _assign_object_material_slot(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    mesh = obj.data
    if mesh is None:
        return
    if not mesh.materials:
        mesh.materials.append(None)
    try:
        slot = obj.material_slots[0]
        slot.link = "OBJECT"
        slot.material = material
    except Exception:
        mesh.materials[0] = material


def _apply_point_attributes(mesh: bpy.types.Mesh, data: MeshPrimitiveData) -> None:
    if not data.point_attrs:
        return

    for attr in data.point_attrs:
        values = _buffer_view(attr.values_f32, "f")
        if values is None:
            continue

        name = attr.name or "assetkit_point_attr"
        width = int(attr.width or 0)
        if width == 1:
            blender_attr = mesh.attributes.new(name=name, type="FLOAT", domain="POINT")
            blender_attr.data.foreach_set("value", values)
        elif width == 2:
            if not _apply_vector_attribute(mesh, name, values, "FLOAT2", "POINT"):
                _apply_split_attribute(mesh, name, values, ("x", "y"), "POINT")
        elif width == 3:
            blender_attr = mesh.attributes.new(name=name, type="FLOAT_VECTOR", domain="POINT")
            blender_attr.data.foreach_set("vector", values)
        elif width == 4:
            if _is_color_attribute_name(name):
                blender_attr = mesh.color_attributes.new(name=name, type="FLOAT_COLOR", domain="POINT")
                blender_attr.data.foreach_set("color", values)
                if name == "Color":
                    _set_render_color_index(mesh, name)
            elif not _apply_vector_attribute(mesh, name, values, "FLOAT4", "POINT"):
                _apply_split_attribute(mesh, name, values, ("x", "y", "z", "w"), "POINT")


def _apply_vector_attribute(
    mesh: bpy.types.Mesh,
    name: str,
    values,
    data_type: str,
    domain: str,
) -> bool:
    try:
        blender_attr = mesh.attributes.new(name=name, type=data_type, domain=domain)
    except TypeError:
        return False
    except RuntimeError:
        return False

    try:
        blender_attr.data.foreach_set("vector", values)
    except Exception:
        try:
            mesh.attributes.remove(blender_attr)
        except Exception:
            pass
        return False
    return True


def _apply_split_attribute(
    mesh: bpy.types.Mesh,
    name: str,
    values,
    suffixes: tuple[str, ...],
    domain: str,
) -> None:
    count = _domain_element_count(mesh, domain)
    for component, suffix in enumerate(suffixes):
        out = array("f", [0.0]) * count
        for index in range(count):
            out[index] = values[index * len(suffixes) + component]
        blender_attr = mesh.attributes.new(name=f"{name}_{suffix}", type="FLOAT", domain=domain)
        blender_attr.data.foreach_set("value", out)


def _domain_element_count(mesh: bpy.types.Mesh, domain: str) -> int:
    if domain == "POINT":
        return len(mesh.vertices)
    if domain == "CORNER":
        return len(mesh.loops)
    if domain == "EDGE":
        return len(mesh.edges)
    if domain == "FACE":
        return len(mesh.polygons)
    return 0


def _mesh_attribute_ensure(mesh: bpy.types.Mesh, name: str, data_type: str, domain: str):
    attrs = getattr(mesh, "attributes", None)
    if attrs is None:
        return None

    try:
        attr = attrs.get(name)
        if attr is not None and (attr.domain != domain or attr.data_type != data_type):
            attrs.remove(attr)
            attr = None
        return attr or attrs.new(name, data_type, domain)
    except Exception:
        return None


def _set_mesh_positions(mesh: bpy.types.Mesh, vertices: memoryview) -> None:
    attr = _mesh_attribute_ensure(mesh, "position", "FLOAT_VECTOR", "POINT")
    if attr is not None:
        try:
            attr.data.foreach_set("vector", vertices)
            return
        except Exception:
            pass
    mesh.vertices.foreach_set("co", vertices)


def _set_mesh_loop_vertex_indices(mesh: bpy.types.Mesh, indices: memoryview) -> None:
    attr = _mesh_attribute_ensure(mesh, ".corner_vert", "INT", "CORNER")
    if attr is not None:
        try:
            attr.data.foreach_set("value", indices)
            return
        except Exception:
            pass
    mesh.loops.foreach_set("vertex_index", indices)


def _set_mesh_edges(mesh: bpy.types.Mesh, indices: memoryview) -> None:
    attr = _mesh_attribute_ensure(mesh, ".edge_verts", "INT32_2D", "EDGE")
    if attr is not None:
        try:
            attr.data.foreach_set("value", indices)
            return
        except Exception:
            pass
    mesh.edges.foreach_set("vertices", indices)


def _set_mesh_loop_starts(
    mesh: bpy.types.Mesh,
    loop_starts: object,
    loop_count: int,
    face_count: int,
) -> None:
    if loop_count == face_count * 3 and _set_triangle_mesh_loop_starts(mesh, face_count):
        return
    mesh.polygons.foreach_set("loop_start", _rna_i32_values(loop_starts))


def _set_triangle_mesh_loop_starts(mesh: bpy.types.Mesh, face_count: int) -> bool:
    if face_count <= 0:
        return False
    try:
        address = int(mesh.polygons[0].as_pointer())
    except Exception:
        return False
    if not address:
        return False
    if face_count > 1:
        try:
            if int(mesh.polygons[1].as_pointer()) - address != 4:
                return False
        except Exception:
            return False
    if native_fill_triangle_loop_offsets_ptr(address, face_count) is None:
        return False
    try:
        return (
            mesh.polygons[0].loop_start == 0
            and mesh.polygons[0].loop_total == 3
            and mesh.polygons[face_count - 1].loop_start == (face_count - 1) * 3
            and mesh.polygons[face_count - 1].loop_total == 3
        )
    except Exception:
        return False


def _rna_i32_values(values: object) -> object:
    if isinstance(values, array):
        return values
    if not isinstance(values, memoryview):
        view = _buffer_view(values, "i")
        if view is None:
            return values
        values = view
    if (
        isinstance(values, memoryview)
        and values.ndim == 1
        and values.format == "i"
        and len(values) > _TRI_LOOP_START_CACHE_LIMIT
    ):
        array_values = array("i")
        array_values.frombytes(values.cast("B"))
        return array_values
    return values


def _set_uv_layer_values(uv_layer: bpy.types.MeshUVLoopLayer, values: memoryview) -> None:
    uv_attr = getattr(uv_layer, "uv", None)
    if uv_attr is not None:
        try:
            uv_attr.foreach_set("vector", values)
            return
        except Exception:
            pass
    uv_layer.data.foreach_set("uv", values)


def _set_mesh_material_indices(mesh: bpy.types.Mesh, material_indices: object) -> None:
    if not material_indices:
        return
    values = _rna_i32_values(material_indices)
    attr = _mesh_attribute_ensure(mesh, "material_index", "INT", "FACE")
    if attr is not None:
        try:
            attr.data.foreach_set("value", values)
            return
        except Exception:
            pass
    mesh.polygons.foreach_set("material_index", values)


def _queue_deferred_custom_normals(
    mesh: bpy.types.Mesh,
    normals: object | None,
    vertex_normals: object | None,
    owner: object | None,
) -> bool:
    if normals is None or bpy.app.background:
        return False

    _set_mesh_smooth(mesh, True)
    _DEFERRED_NORMAL_TASKS.append((mesh, normals, vertex_normals, owner))
    global _DEFERRED_NORMAL_TIMER_ACTIVE
    if not _DEFERRED_NORMAL_TIMER_ACTIVE:
        _DEFERRED_NORMAL_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_custom_normals_timer, first_interval=0.001)
    return True


def _deferred_custom_normals_timer() -> float | None:
    started_at = time.perf_counter()
    processed = 0
    profile_detail = _profile_state.stats is not None

    while _DEFERRED_NORMAL_TASKS:
        mesh, normals, vertex_normals, _owner = _DEFERRED_NORMAL_TASKS.popleft()
        try:
            if bpy.data.meshes.get(mesh.name) is mesh:
                _apply_shading(mesh, "AUTO", normals, vertex_normals, smooth_already=True)
                processed += 1
        except Exception:
            pass
        if time.perf_counter() - started_at >= _DEFERRED_NORMAL_TIME_BUDGET:
            break

    if profile_detail and processed:
        _profile_log(
            "deferred_custom_normals "
            f"meshes={processed} remaining={len(_DEFERRED_NORMAL_TASKS)} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )

    if _DEFERRED_NORMAL_TASKS:
        return 0.001

    global _DEFERRED_NORMAL_TIMER_ACTIVE
    _DEFERRED_NORMAL_TIMER_ACTIVE = False
    return None


def _drain_deferred_staging_work() -> None:
    while _materials.has_deferred_work():
        _deferred_material_node_timer()
    while _textures.has_deferred_work():
        _deferred_texture_timer()
    while _DEFERRED_NORMAL_TASKS:
        _deferred_custom_normals_timer()


def _apply_shading(
    mesh: bpy.types.Mesh,
    mode: str,
    normals: object | None,
    vertex_normals: object | None = None,
    apply_custom_normals: bool = True,
    smooth_already: bool = False,
) -> bool:
    mode = str(mode or "AUTO").upper()
    if mode == "AS_IS":
        return True

    if mode == "FLAT":
        _set_mesh_smooth(mesh, False)
        return True
    if mode == "SMOOTH":
        _set_mesh_smooth(mesh, True)
        return True

    if not normals and vertex_normals is None:
        _set_mesh_smooth(mesh, False)
        return True

    if not apply_custom_normals:
        _set_mesh_smooth(mesh, True)
        return False

    try:
        if vertex_normals is not None:
            if not _set_free_custom_normals(mesh, vertex_normals, "POINT"):
                mesh.normals_split_custom_set_from_vertices(vertex_normals)
        elif isinstance(normals, memoryview):
            if not _set_free_custom_normals(mesh, normals, "CORNER"):
                mesh.corner_normals.foreach_set("vector", normals)
        else:
            mesh.normals_split_custom_set(normals)
        if not smooth_already:
            _set_mesh_smooth(mesh, True)
        return True
    except Exception:
        if not smooth_already:
            _set_mesh_smooth(mesh, True)
        return False


def _set_free_custom_normals(mesh: bpy.types.Mesh, normals: object, domain: str) -> bool:
    count = len(mesh.vertices) if domain == "POINT" else len(mesh.loops)
    if count <= 0 or len(normals) != count * 3:
        return False

    attr = _mesh_attribute_ensure(mesh, "custom_normal", "FLOAT_VECTOR", domain)
    if attr is None:
        return False
    try:
        attr.data.foreach_set("vector", normals)
        return True
    except Exception:
        try:
            mesh.attributes.remove(attr)
        except Exception:
            pass
        return False


def _apply_wavefront_smoothing(
    mesh: bpy.types.Mesh,
    data: MeshPrimitiveData,
    mode: str,
    normals: object | None,
    vertex_normals: object | None,
) -> bool:
    if str(mode or "AUTO").upper() != "AUTO":
        return False
    if normals or vertex_normals is not None or not _uses_wavefront_smoothing(data):
        return False

    if data.sharp_faces_u8:
        return _set_mesh_sharp_faces(mesh, data.sharp_faces_u8)
    if bool(getattr(data, "smooth_shading", False)):
        _set_mesh_smooth(mesh, True)
    return True


def _set_mesh_sharp_faces(mesh: bpy.types.Mesh, sharp_faces: object) -> bool:
    if not mesh.polygons:
        return True

    count = len(mesh.polygons)
    values = _buffer_view(sharp_faces, "B")
    if values is None or len(values) < count:
        return False
    values = values[:count]

    attr = _mesh_attribute_ensure(mesh, "sharp_face", "BOOLEAN", "FACE")
    if attr is not None:
        try:
            attr.data.foreach_set("value", values)
            return True
        except Exception:
            try:
                copied = array("b")
                copied.frombytes(values.cast("B"))
                attr.data.foreach_set("value", copied)
                return True
            except Exception:
                pass

    try:
        mesh.polygons.foreach_set("use_smooth", array("b", (0 if value else 1 for value in values)))
    except Exception:
        for index, poly in enumerate(mesh.polygons):
            poly.use_smooth = not bool(values[index])
    return True


def _set_mesh_smooth(mesh: bpy.types.Mesh, smooth: bool) -> None:
    if not mesh.polygons:
        return

    count = len(mesh.polygons)
    if smooth and _mesh_already_smooth_by_default(mesh):
        return

    sharp = 0 if smooth else 1
    attr = _mesh_attribute_ensure(mesh, "sharp_face", "BOOLEAN", "FACE")
    if attr is not None:
        if _fill_bool_attribute_fast(attr, bool(sharp), count):
            return
        values = _bool_array(sharp, count)
        try:
            attr.data.foreach_set("value", values)
            return
        except Exception:
            pass

    values = _bool_array(1 if smooth else 0, count)
    try:
        mesh.polygons.foreach_set("use_smooth", values)
    except Exception:
        for poly in mesh.polygons:
            poly.use_smooth = smooth


def _mesh_already_smooth_by_default(mesh: bpy.types.Mesh) -> bool:
    try:
        if mesh.attributes.get("sharp_face") is not None:
            return False
        return bool(mesh.polygons[0].use_smooth)
    except Exception:
        return False


def _fill_bool_attribute_fast(attr: object, value: bool, count: int) -> bool:
    if count <= 0:
        return True
    try:
        address = int(attr.data[0].as_pointer())
        if count > 1 and int(attr.data[1].as_pointer()) - address != 1:
            return False
        if native_fill_u8_ptr(address, 1 if value else 0, count) is None:
            return False
        return bool(attr.data[0].value) == value and bool(attr.data[count - 1].value) == value
    except Exception:
        return False


def _bool_array(value: int, count: int) -> array:
    key = (1 if value else 0, count)
    cached = _BOOL_ARRAYS.get(key)
    if cached is not None:
        return cached
    values = array("b", [key[0]]) * count
    _BOOL_ARRAYS[key] = values
    return values


def _triangle_loop_starts(loop_count: int) -> array:
    if loop_count > _TRI_LOOP_START_CACHE_LIMIT:
        return array("i", range(0, loop_count, 3))
    cached = _TRI_LOOP_START_ARRAYS.get(loop_count)
    if cached is not None:
        return cached
    values = array("i", range(0, loop_count, 3))
    _TRI_LOOP_START_ARRAYS[loop_count] = values
    return values


def _set_render_color_index(mesh: bpy.types.Mesh, name: str = "Color") -> None:
    try:
        attributes = mesh.color_attributes
        index = attributes.find(name)
        if index < 0:
            return
        attributes.render_color_index = index
        try:
            attributes.active_color_index = index
        except Exception:
            pass
    except Exception:
        pass
