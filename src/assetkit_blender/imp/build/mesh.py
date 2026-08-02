from __future__ import annotations

from array import array
from dataclasses import replace
import time

import bpy

from ...assetkit import (
    LoopFloatAttributeData,
    MeshPrimitiveData,
    NativeSimpleMeshData,
    SceneNodeData,
    _profile_log,
    native_buffer_sequences_equal,
    native_buffers_equal,
    native_fill_i32,
    native_offset_i32,
    native_write_offset_i32,
)
from ...enums import (
    AK_FILE_TYPE_COLLADA,
    AK_FILE_TYPE_WAVEFRONT,
    AK_PRIMITIVE_LINES,
    AK_PRIMITIVE_POINTS,
    AK_PRIMITIVE_POLYGONS,
    AK_PRIMITIVE_TRIANGLES,
)
from .. import profile as _profile_state
from ..buffers import buffer_view as _buffer_view, copy_buffer_bytes as _copy_buffer_bytes, matrix_from_values as _matrix_from_values
from ..context import ImportState
from ..material import _apply_assetkit_extra_props, _apply_material_variants, _has_material_data
from ..metadata import _set_assetkit_json_prop
from ..mesh import (
    _apply_point_attributes,
    _apply_shading,
    _apply_split_attribute,
    _apply_vector_attribute,
    _apply_wavefront_smoothing,
    _assign_mesh_material,
    _queue_deferred_custom_normals,
    _rna_i32_values,
    _set_mesh_edges,
    _set_mesh_loop_starts,
    _set_mesh_loop_vertex_indices,
    _set_mesh_material_indices,
    _set_mesh_positions,
    _set_render_color_index,
    _set_uv_layer_values,
    _triangle_loop_starts,
    _uses_wavefront_smoothing,
)
from ..animation.object import _apply_animation, _apply_morph_presets, _apply_shape_keys
from ..objects import _set_node_visibility
from ..profile import _record_finish_profile, _record_mesh_profile
from ..skin import _apply_skin, _apply_skin_bind_shape
from .common import (
    _apply_matrix,
    _blender_natural_name_key,
    _effective_shading_mode,
    _group_wavefront_sharp_faces,
    _material_for_data,
    _mesh_node_parent,
    _node_import_collection,
    _set_parent,
)
from .visibility import _apply_effective_node_visibility_animation, _node_has_effective_visibility_animation

def _create_import_object(
    primitive: MeshPrimitiveData,
    state: ImportState,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    node_objects = state.node_objects
    node_index = int(primitive.node_index)
    active_collection = _node_import_collection(state, node_index, collection)
    parent, use_node_parent = _mesh_node_parent(state, node_index)
    defer_animation = bool(state.node_animation_deferred)
    node_visibility_animation = bool(state.has_node_visibility_animation)
    preserve_tangents = bool(state.preserve_tangents)
    mesh_cache_key = _mesh_data_reuse_key(primitive, shading_mode, preserve_tangents)
    mesh_cache = state.mesh_cache if mesh_cache_key is not None else None
    if mesh_cache is not None:
        cached_entry = mesh_cache.get(mesh_cache_key)
        if (
            cached_entry is not None
            and _mesh_primitive_geometry_equal(cached_entry[1], primitive)
        ):
            cached_mesh = cached_entry[0]
            use_object_material_slot = _has_material_data(primitive)
            state.mesh_cache_hits += 1
            return _finish_mesh_object(
                cached_mesh,
                primitive,
                parent,
                node_objects=node_objects,
                node_data=state.node_data,
                node_visibility=state.node_visibility,
                material_cache=state.material_cache,
                skin_cache=state.skin_cache,
                apply_transform=not use_node_parent,
                apply_animation=(not use_node_parent and not defer_animation),
                apply_skin_animation=not bool(state.skin_animation_deferred),
                deferred_skin_animations=state.deferred_skin_animations,
                collection=active_collection,
                object_material_slot=use_object_material_slot,
                node_visibility_animation=node_visibility_animation,
            )

    objects = _create_mesh_object(
        primitive,
        parent,
        node_objects=node_objects,
        node_data=state.node_data,
        node_visibility=state.node_visibility,
        material_cache=state.material_cache,
        skin_cache=state.skin_cache,
        apply_transform=not use_node_parent,
        apply_animation=(not use_node_parent and not defer_animation),
        apply_skin_animation=not bool(state.skin_animation_deferred),
        deferred_skin_animations=state.deferred_skin_animations,
        shading_mode=shading_mode,
        defer_custom_normals=bool(state.defer_custom_normals),
        preserve_tangents=preserve_tangents,
        collection=active_collection,
        object_material_slot=False,
        node_visibility_animation=node_visibility_animation,
    )
    if mesh_cache is not None and len(objects) == 1 and isinstance(objects[0].data, bpy.types.Mesh):
        mesh_cache.setdefault(mesh_cache_key, (objects[0].data, primitive))
    return objects


class _GroupedMeshData:
    __slots__ = ("_source", "__dict__")

    def __init__(self, source: MeshPrimitiveData, **values) -> None:
        self._source = source
        self.__dict__.update(values)

    def __getattr__(self, name: str):
        return getattr(self._source, name)


def _create_grouped_mesh_object(
    primitives: list[MeshPrimitiveData],
    state: ImportState,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    profile_detail = _profile_state.stats is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    surface_primitives = [
        primitive
        for primitive in primitives
        if int(primitive.primitive_type) != AK_PRIMITIVE_LINES
    ]
    line_primitives = [
        primitive
        for primitive in primitives
        if int(primitive.primitive_type) == AK_PRIMITIVE_LINES
    ]
    first = surface_primitives[0]
    line_primitive = line_primitives[0] if len(line_primitives) == 1 else None
    node_objects = state.node_objects
    node_index = int(first.node_index)
    active_collection = _node_import_collection(state, node_index, collection)
    parent, use_node_parent = _mesh_node_parent(state, node_index)
    defer_animation = bool(state.node_animation_deferred)
    node_visibility_animation = bool(state.has_node_visibility_animation)
    preserve_tangents = bool(state.preserve_tangents)
    mesh_cache_key = _grouped_mesh_data_reuse_key(
        surface_primitives,
        line_primitive,
        shading_mode,
        preserve_tangents,
    )
    mesh_cache = state.mesh_cache if mesh_cache_key is not None else None
    if mesh_cache is not None:
        cached_entry = mesh_cache.get(mesh_cache_key)
        if (
            cached_entry is not None
            and _grouped_mesh_geometry_equal(
                cached_entry[1],
                cached_entry[2],
                surface_primitives,
                line_primitive,
            )
        ):
            cached_mesh = cached_entry[0]
            state.mesh_cache_hits += 1
            return _finish_cached_grouped_mesh_object(
                cached_mesh,
                surface_primitives,
                line_primitive,
                parent,
                node_data=state.node_data,
                node_visibility=state.node_visibility,
                material_cache=state.material_cache,
                apply_transform=not use_node_parent,
                apply_animation=(not use_node_parent and not defer_animation),
                collection=active_collection,
                node_visibility_animation=node_visibility_animation,
            )

    count_started_at = time.perf_counter() if profile_detail else 0.0
    surface_vertex_count = sum(int(primitive.vertex_count) for primitive in surface_primitives)
    total_loop_count = sum(int(primitive.loop_count) for primitive in surface_primitives)
    total_face_count = sum(int(primitive.face_count) for primitive in surface_primitives)
    total_edge_count = int(line_primitive.loop_count) // 2 if line_primitive else 0
    line_vertex_offset = (
        _line_surface_vertex_offset(line_primitive, surface_primitives)
        if line_primitive
        else -1
    )
    total_vertex_count = surface_vertex_count
    if line_primitive is not None and line_vertex_offset == surface_vertex_count:
        total_vertex_count += int(line_primitive.vertex_count)
    count_ms = (time.perf_counter() - count_started_at) * 1000.0 if profile_detail else 0.0

    skin_joint_width = max(1, int(first.skin_joint_width or 4))
    vertices = bytearray(total_vertex_count * 3 * 4)
    indices = bytearray(total_loop_count * 4)
    edges = bytearray(total_edge_count * 2 * 4)
    loop_starts = bytearray(total_face_count * 4)
    normals = bytearray(total_loop_count * 3 * 4) if first.normals_f32 else None
    vertex_normals = bytearray(total_vertex_count * 3 * 4) if first.vertex_normals_f32 else None
    tangents = bytearray(total_loop_count * 4 * 4) if first.tangents_f32 else None
    skin_joints = bytearray(total_vertex_count * skin_joint_width * 2) if first.has_skin else None
    skin_weights = bytearray(total_vertex_count * skin_joint_width * 4) if first.has_skin else None
    attr_started_at = time.perf_counter() if profile_detail else 0.0
    uv_sets = _group_loop_float_attrs(surface_primitives, "uv_sets")
    color_sets = _group_loop_float_attrs(surface_primitives, "color_sets")
    point_attrs = _group_line_point_attrs(
        line_primitive,
        total_vertex_count,
        line_vertex_offset,
    )
    has_materials = any(_has_material_data(primitive) for primitive in surface_primitives)
    material_indices = bytearray(total_face_count * 4) if has_materials else b""
    sharp_faces = _group_wavefront_sharp_faces(surface_primitives, total_face_count)
    attr_ms = (time.perf_counter() - attr_started_at) * 1000.0 if profile_detail else 0.0

    assemble_started_at = time.perf_counter() if profile_detail else 0.0
    vertex_offset = 0
    loop_offset = 0
    face_offset = 0
    for slot_index, primitive in enumerate(surface_primitives):
        primitive_vertices = _buffer_view(primitive.vertices_f32, "f")
        primitive_indices = _buffer_view(primitive.indices_u32, "i")
        if primitive_vertices is None or primitive_indices is None:
            return [
                obj
                for source in primitives
                for obj in _create_import_object(source, state, collection, shading_mode)
            ]

        _copy_buffer_bytes(vertices, vertex_offset * 3 * 4, primitive_vertices, "f")
        copied = native_write_offset_i32(indices, loop_offset * 4, primitive_indices, vertex_offset)
        if copied is None:
            shifted_indices = native_offset_i32(primitive_indices, vertex_offset)
            if shifted_indices is not None:
                _copy_buffer_bytes(indices, loop_offset * 4, shifted_indices, "i")
                copied = len(shifted_indices) * 4
        if copied is None:
            tmp_indices = array("i")
            for index in primitive_indices:
                tmp_indices.append(int(index) + vertex_offset)
            _copy_buffer_bytes(indices, loop_offset * 4, tmp_indices, "i")

        primitive_loop_starts = _buffer_view(primitive.loop_starts_i32, "i")
        if primitive_loop_starts is not None:
            copied = native_write_offset_i32(loop_starts, face_offset * 4, primitive_loop_starts, loop_offset)
            if copied is None:
                shifted_starts = native_offset_i32(primitive_loop_starts, loop_offset)
                if shifted_starts is not None:
                    _copy_buffer_bytes(loop_starts, face_offset * 4, shifted_starts, "i")
                    copied = len(shifted_starts) * 4
            if copied is None:
                tmp_starts = array("i")
                for start in primitive_loop_starts:
                    tmp_starts.append(int(start) + loop_offset)
                _copy_buffer_bytes(loop_starts, face_offset * 4, tmp_starts, "i")
        else:
            _copy_buffer_bytes(
                loop_starts,
                face_offset * 4,
                array("i", range(loop_offset, loop_offset + int(primitive.loop_count), 3)),
                "i",
            )

        if has_materials:
            face_count = int(primitive.face_count)
            if native_fill_i32(material_indices, face_offset * 4, slot_index, face_count) is None:
                _copy_buffer_bytes(material_indices, face_offset * 4, array("i", [slot_index]) * face_count, "i")
        if normals is not None:
            view = _buffer_view(primitive.normals_f32, "f")
            if view is not None:
                _copy_buffer_bytes(normals, loop_offset * 3 * 4, view, "f")
        if vertex_normals is not None:
            view = _buffer_view(primitive.vertex_normals_f32, "f")
            if view is not None:
                _copy_buffer_bytes(vertex_normals, vertex_offset * 3 * 4, view, "f")
        if tangents is not None:
            view = _buffer_view(primitive.tangents_f32, "f")
            if view is not None:
                _copy_buffer_bytes(tangents, loop_offset * 4 * 4, view, "f")
        if skin_joints is not None and skin_weights is not None:
            joint_view = _buffer_view(primitive.skin_joints_u16, "H")
            weight_view = _buffer_view(primitive.skin_weights_f32, "f")
            if joint_view is not None:
                _copy_buffer_bytes(skin_joints, vertex_offset * skin_joint_width * 2, joint_view, "H")
            if weight_view is not None:
                _copy_buffer_bytes(skin_weights, vertex_offset * skin_joint_width * 4, weight_view, "f")

        vertex_offset += int(primitive.vertex_count)
        loop_offset += int(primitive.loop_count)
        face_offset += int(primitive.face_count)
    if line_primitive is not None:
        line_indices = _buffer_view(line_primitive.indices_u32, "i")
        if line_indices is None or line_vertex_offset < 0:
            return [
                obj
                for source in primitives
                for obj in _create_import_object(source, state, collection, shading_mode)
            ]
        if line_vertex_offset == surface_vertex_count:
            line_vertices = _buffer_view(line_primitive.vertices_f32, "f")
            if line_vertices is None:
                return [
                    obj
                    for source in primitives
                    for obj in _create_import_object(source, state, collection, shading_mode)
                ]
            _copy_buffer_bytes(
                vertices,
                line_vertex_offset * 3 * 4,
                line_vertices,
                "f",
            )
        copied = native_write_offset_i32(edges, 0, line_indices, line_vertex_offset)
        if copied is None:
            shifted_indices = native_offset_i32(line_indices, line_vertex_offset)
            if shifted_indices is not None:
                copied = _copy_buffer_bytes(edges, 0, shifted_indices, "i")
        if copied is None:
            tmp_indices = array("i", (int(index) + line_vertex_offset for index in line_indices))
            _copy_buffer_bytes(edges, 0, tmp_indices, "i")
    assemble_ms = (time.perf_counter() - assemble_started_at) * 1000.0 if profile_detail else 0.0

    replace_started_at = time.perf_counter() if profile_detail else 0.0
    data = _GroupedMeshData(
        first,
        name=_group_mesh_name(first),
        vertex_count=total_vertex_count,
        loop_count=total_loop_count,
        face_count=total_face_count,
        edge_count=total_edge_count,
        vertices_f32=vertices,
        indices_u32=indices,
        edges_u32=edges,
        loop_starts_i32=loop_starts,
        loop_totals_i32=b"",
        normals_f32=normals or b"",
        vertex_normals_f32=vertex_normals or b"",
        tangents_f32=tangents or b"",
        uv_sets=uv_sets,
        color_sets=color_sets,
        point_attrs=point_attrs,
        point_attr_count=len(point_attrs),
        skin_joints_u16=skin_joints or b"",
        skin_weights_f32=skin_weights or b"",
        skin_vertex_count=total_vertex_count if first.has_skin else 0,
        sharp_faces_u8=sharp_faces,
    )
    replace_ms = (time.perf_counter() - replace_started_at) * 1000.0 if profile_detail else 0.0

    bulk_started_at = time.perf_counter() if profile_detail else 0.0
    objects = _create_grouped_mesh_object_bulk(
        data,
        surface_primitives,
        material_indices,
        parent,
        node_objects=node_objects,
        node_data=state.node_data,
        node_visibility=state.node_visibility,
        material_cache=state.material_cache,
        skin_cache=state.skin_cache,
        apply_transform=not use_node_parent,
        apply_animation=(not use_node_parent and not defer_animation),
        apply_skin_animation=not bool(state.skin_animation_deferred),
        deferred_skin_animations=state.deferred_skin_animations,
        has_materials=has_materials,
        shading_mode=shading_mode,
        defer_custom_normals=bool(state.defer_custom_normals),
        preserve_tangents=preserve_tangents,
        collection=active_collection,
        node_visibility_animation=node_visibility_animation,
        line_primitive=line_primitive,
        object_material_slots=mesh_cache is not None,
    )
    if (
        mesh_cache is not None
        and len(objects) == 1
        and isinstance(objects[0].data, bpy.types.Mesh)
    ):
        mesh_cache.setdefault(
            mesh_cache_key,
            (objects[0].data, tuple(surface_primitives), line_primitive),
        )
    if profile_detail:
        _profile_log(
            "create_grouped_mesh_object "
            f"primitives={len(primitives)} count={count_ms:.3f}ms "
            f"attrs={attr_ms:.3f}ms assemble={assemble_ms:.3f}ms "
            f"replace={replace_ms:.3f}ms bulk={(time.perf_counter() - bulk_started_at) * 1000.0:.3f}ms "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return objects


def _group_mesh_name(data: MeshPrimitiveData) -> str:
    name = data.name
    suffix = f"_{int(data.primitive_index)}"
    if suffix != "_0" and name.endswith(suffix):
        return name[: -len(suffix)]
    if name.endswith("_0"):
        return name[:-2]
    return name


def _line_surface_vertex_offset(
    line: MeshPrimitiveData,
    surfaces: list[MeshPrimitiveData],
) -> int:
    line_positions = _buffer_view(line.vertices_f32, "f")
    if line_positions is None:
        return -1
    line_bytes = line_positions.cast("B")
    vertex_offset = 0
    for surface in surfaces:
        surface_positions = _buffer_view(surface.vertices_f32, "f")
        if (
            surface_positions is not None
            and len(surface_positions) == len(line_positions)
            and surface_positions.cast("B") == line_bytes
        ):
            return vertex_offset
        vertex_offset += int(surface.vertex_count)
    return vertex_offset


def _group_line_point_attrs(
    line: MeshPrimitiveData | None,
    total_vertex_count: int,
    vertex_offset: int,
) -> list[LoopFloatAttributeData]:
    if line is None or vertex_offset < 0:
        return []

    grouped = []
    for attr in line.point_attrs or ():
        width = int(attr.width or 0)
        values = _buffer_view(attr.values_f32, "f")
        if width <= 0 or values is None:
            continue
        merged = bytearray(total_vertex_count * width * 4)
        copied = _copy_buffer_bytes(
            merged,
            vertex_offset * width * 4,
            values,
            "f",
        )
        if copied != len(values) * 4:
            continue
        grouped.append(_replace_loop_float_attr(attr, merged))
    return grouped


def _replace_loop_float_attr(
    attr: LoopFloatAttributeData,
    values_f32: object,
) -> LoopFloatAttributeData:
    if isinstance(attr, LoopFloatAttributeData):
        return replace(attr, values_f32=values_f32)
    return LoopFloatAttributeData(
        name=attr.name,
        set=int(attr.set),
        width=int(attr.width),
        values_f32=values_f32,
    )


def _group_loop_float_attrs(
    primitives: list[MeshPrimitiveData],
    attr_name: str,
) -> list[LoopFloatAttributeData]:
    first_attrs = getattr(primitives[0], attr_name) or []
    grouped: list[LoopFloatAttributeData] = []
    for attr_index, first_attr in enumerate(first_attrs):
        width = int(first_attr.width or 0)
        if width <= 0:
            return []
        values = bytearray(sum(int(primitive.loop_count) for primitive in primitives) * width * 4)
        byte_offset = 0
        for primitive in primitives:
            attrs = getattr(primitive, attr_name) or []
            if attr_index >= len(attrs):
                return []
            attr = attrs[attr_index]
            if int(attr.width or 0) != width:
                return []
            view = _buffer_view(attrs[attr_index].values_f32, "f")
            if view is None:
                return []
            copied = _copy_buffer_bytes(values, byte_offset, view, "f")
            if copied == 0:
                return []
            byte_offset += copied
        if byte_offset != len(values):
            return []
        grouped.append(_replace_loop_float_attr(first_attr, values))
    return grouped


def _create_grouped_mesh_object_bulk(
    data: MeshPrimitiveData,
    primitives: list[MeshPrimitiveData],
    material_indices: array,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    has_materials: bool = True,
    shading_mode: str = "AUTO",
    defer_custom_normals: bool = False,
    preserve_tangents: bool = False,
    collection: bpy.types.Collection | None = None,
    node_visibility_animation: bool = True,
    line_primitive: MeshPrimitiveData | None = None,
    object_material_slots: bool = False,
) -> list[bpy.types.Object]:
    total_started_at = time.perf_counter()
    profile_detail = _profile_state.stats is not None
    phase_started_at = total_started_at
    detail_parts: list[str] = []
    mesh = bpy.data.meshes.new(data.name)
    mesh.vertices.add(data.vertex_count)
    if data.edge_count:
        mesh.edges.add(data.edge_count)
    mesh.loops.add(data.loop_count)
    mesh.polygons.add(data.face_count)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"alloc={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    edges = _buffer_view(data.edges_u32, "i") if data.edges_u32 else None
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")
    if vertices is None or indices is None or loop_starts is None:
        raise RuntimeError("AssetKit native bridge returned incomplete grouped mesh buffers")
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"views={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    _set_mesh_positions(mesh, vertices)
    if edges is not None:
        _set_mesh_edges(mesh, edges)
    _set_mesh_loop_vertex_indices(mesh, indices)
    _set_mesh_loop_starts(mesh, loop_starts, int(data.loop_count), int(data.face_count))
    if loop_totals is not None and int(data.loop_count) != int(data.face_count) * 3:
        mesh.polygons.foreach_set("loop_total", _rna_i32_values(loop_totals))
    _set_mesh_material_indices(mesh, material_indices)
    _apply_point_attributes(mesh, data)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"topology={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    for index, attr in enumerate(data.uv_sets or ()):
        uvs = _buffer_view(attr.values_f32, "f")
        uv_layer = mesh.uv_layers.new(name=attr.name or ("UVMap" if index == 0 else f"UVMap.{index:03d}"))
        if uvs is not None:
            _set_uv_layer_values(uv_layer, uvs)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"uv={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    for index, attr in enumerate(data.color_sets or ()):
        colors = _buffer_view(attr.values_f32, "f")
        if colors is None:
            continue
        color_attr = mesh.color_attributes.new(
            name=attr.name or ("Color" if index == 0 else f"Color.{index:03d}"),
            type="FLOAT_COLOR",
            domain="CORNER",
        )
        color_attr.data.foreach_set("color", colors)
    if data.color_sets:
        _set_render_color_index(mesh)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"color={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    if preserve_tangents and data.tangents_f32:
        tangents = _buffer_view(data.tangents_f32, "f")
        if tangents is not None:
            if not _apply_vector_attribute(mesh, "assetkit_tangent", tangents, "FLOAT4", "CORNER"):
                _apply_split_attribute(mesh, "assetkit_tangent", tangents, ("x", "y", "z", "w"), "CORNER")
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"tangent={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    normals = _buffer_view(data.normals_f32, "f") if data.normals_f32 else None
    vertex_normals = _buffer_view(data.vertex_normals_f32, "f") if data.vertex_normals_f32 else None
    if str(shading_mode or "AUTO").upper() == "FLAT":
        shading_done = _apply_shading(mesh, shading_mode, normals, vertex_normals, apply_custom_normals=False)
    elif _apply_wavefront_smoothing(mesh, data, shading_mode, normals, vertex_normals):
        shading_done = True
    elif shading_mode != "SMOOTH" and not normals and vertex_normals is None:
        shading_done = True
    else:
        shading_done = _apply_shading(mesh, shading_mode, normals, vertex_normals, apply_custom_normals=False)
    mesh.update(calc_edges=True)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"update={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    if not shading_done and defer_custom_normals:
        shading_done = _queue_deferred_custom_normals(mesh, normals, vertex_normals, data)
    if not shading_done:
        _apply_shading(mesh, shading_mode, normals, vertex_normals, smooth_already=True)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"shading={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    active_collection = collection or bpy.context.collection
    _apply_skin_bind_shape(mesh, data)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"bind_shape={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if node_visibility is not None and data.node_index >= 0:
        _set_node_visibility(obj, node_visibility.get(data.node_index, True))
    if apply_transform:
        _apply_matrix(obj, data)
    active_collection.objects.link(obj)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"object={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    if object_material_slots:
        for _primitive in primitives:
            mesh.materials.append(None)
        if line_primitive is not None:
            mesh.materials.append(None)
        _assign_grouped_object_materials(
            obj,
            primitives,
            line_primitive,
            material_cache,
            int(data.edge_count),
        )
    elif has_materials:
        for primitive in primitives:
            material = _material_for_data(primitive, material_cache)
            if material:
                _assign_mesh_material(obj, mesh, material)
    if line_primitive is not None and not object_material_slots:
        line_material = _material_for_data(line_primitive, material_cache)
        line_material_slot = -1
        if line_material:
            for index, material in enumerate(mesh.materials):
                if material == line_material:
                    line_material_slot = index
                    break
            if line_material_slot < 0:
                mesh.materials.append(line_material)
                line_material_slot = len(mesh.materials) - 1
        obj["assetkit_mixed_line_material_slot"] = int(line_material_slot)
        obj["assetkit_mixed_line_mode"] = int(line_primitive.primitive_mode)
        obj["assetkit_mixed_line_edge_count"] = int(data.edge_count)
        _set_assetkit_json_prop(
            obj,
            "assetkit_mixed_line_primitive_extra_json",
            line_primitive.primitive_extra,
        )
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"materials={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    _apply_assetkit_extra_props(obj, data)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"extras={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    node_lookup = node_data or {}
    _apply_skin(
        obj,
        data,
        node_objects or {},
        node_lookup,
        active_collection,
        skin_cache,
        apply_animation=apply_skin_animation,
        deferred_skin_animations=deferred_skin_animations,
    )
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"skin={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    has_node_visibility_animation = (
        _node_has_effective_visibility_animation(data.node_index, node_lookup)
        if node_visibility_animation
        else False
    )
    if apply_animation and (data.anim_count or data.anim_channels):
        _apply_animation(obj, data, skip_visibility=has_node_visibility_animation)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"animation={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    if has_node_visibility_animation:
        _apply_effective_node_visibility_animation(obj, data.node_index, node_lookup)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"visibility={(now - phase_started_at) * 1000.0:.3f}ms")

    if profile_detail:
        _profile_log(
            "finish_grouped_mesh_object "
            f"name={obj.name!r} primitives={len(primitives)} "
            f"verts={data.vertex_count} faces={data.face_count} "
            f"elapsed={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
        _profile_log(
            "finish_grouped_mesh_object_detail "
            f"name={obj.name!r} primitives={len(primitives)} "
            + " ".join(detail_parts)
        )
    return [obj]


def _finish_cached_grouped_mesh_object(
    mesh: bpy.types.Mesh,
    primitives: list[MeshPrimitiveData],
    line_primitive: MeshPrimitiveData | None,
    parent: bpy.types.Object | None,
    *,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    collection: bpy.types.Collection | None = None,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    data = primitives[0]
    objects = _finish_mesh_object(
        mesh,
        data,
        parent,
        node_data=node_data,
        node_visibility=node_visibility,
        material_cache=material_cache,
        apply_transform=apply_transform,
        apply_animation=apply_animation,
        collection=collection,
        assign_material=False,
        node_visibility_animation=node_visibility_animation,
    )
    if objects:
        obj = objects[0]
        obj["assetkit_vertex_count"] = len(mesh.vertices)
        obj["assetkit_loop_count"] = len(mesh.loops)
        obj["assetkit_face_count"] = len(mesh.polygons)
        _assign_grouped_object_materials(
            obj,
            primitives,
            line_primitive,
            material_cache,
            int(line_primitive.loop_count) // 2 if line_primitive else 0,
        )
    return objects


def _assign_grouped_object_materials(
    obj: bpy.types.Object,
    primitives: list[MeshPrimitiveData],
    line_primitive: MeshPrimitiveData | None,
    material_cache: dict[object, bpy.types.Material] | None,
    edge_count: int,
) -> None:
    for slot_index, primitive in enumerate(primitives):
        slot = obj.material_slots[slot_index]
        slot.link = "OBJECT"
        slot.material = _material_for_data(primitive, material_cache)

    if line_primitive is None:
        return
    line_material_slot = len(primitives)
    slot = obj.material_slots[line_material_slot]
    slot.link = "OBJECT"
    line_material = _material_for_data(line_primitive, material_cache)
    slot.material = line_material
    if line_material is None:
        line_material_slot = -1
    obj["assetkit_mixed_line_material_slot"] = line_material_slot
    obj["assetkit_mixed_line_mode"] = int(line_primitive.primitive_mode)
    obj["assetkit_mixed_line_edge_count"] = edge_count
    _set_assetkit_json_prop(
        obj,
        "assetkit_mixed_line_primitive_extra_json",
        line_primitive.primitive_extra,
    )


def _mesh_import_units(primitives: list[MeshPrimitiveData]) -> list[MeshPrimitiveData | list[MeshPrimitiveData]]:
    units: list[MeshPrimitiveData | list[MeshPrimitiveData]] = []
    index = 0
    count = len(primitives)
    while index < count:
        primitive = primitives[index]
        key = _mesh_group_key(primitive)
        if key is None:
            units.append(primitive)
            index += 1
            continue

        group = [primitive]
        index += 1
        while index < count and _mesh_group_key(primitives[index]) == key:
            group.append(primitives[index])
            index += 1
        if (
            index < count
            and _line_primitive_can_join_surface_group(primitives[index], group)
        ):
            group.append(primitives[index])
            index += 1
        units.append(group if len(group) > 1 else primitive)

    return units


def _mesh_import_unit_sort_key(
    unit: MeshPrimitiveData | list[MeshPrimitiveData],
) -> tuple:
    first = unit[0] if isinstance(unit, list) else unit
    mesh_name = _group_mesh_name(first) if isinstance(unit, list) else first.name
    object_name = first.object_name or mesh_name
    return (
        _blender_natural_name_key(mesh_name),
        _blender_natural_name_key(object_name),
        int(first.node_index),
        int(first.primitive_index),
    )


def _sort_mesh_import_units_for_blender(
    units: list[MeshPrimitiveData | list[MeshPrimitiveData]],
) -> None:
    if len(units) > 1:
        units.sort(key=_mesh_import_unit_sort_key)


def _same_mesh_run(candidate: MeshPrimitiveData, first: MeshPrimitiveData) -> bool:
    return (
        int(candidate.node_index) == int(first.node_index)
        and int(candidate.mesh_key or 0) == int(first.mesh_key or 0)
    )


def _line_primitive_can_join_surface_group(
    line: MeshPrimitiveData,
    surfaces: list[MeshPrimitiveData],
) -> bool:
    if not surfaces or int(line.primitive_type) != AK_PRIMITIVE_LINES:
        return False
    first = surfaces[0]
    if not _same_mesh_run(line, first) or not line.vertices_f32 or not line.indices_u32:
        return False
    if line.instance_count or line.has_gsplat or line.has_skin:
        return False
    if line.morph_targets or line.morph_anim_channels or line.material_anim_channels:
        return False
    if line.material_variants:
        return False

    line_positions = _buffer_view(line.vertices_f32, "f")
    line_indices = _buffer_view(line.indices_u32, "i")
    return (
        line_positions is not None
        and len(line_positions) == int(line.vertex_count) * 3
        and line_indices is not None
        and len(line_indices) == int(line.loop_count)
        and len(line_indices) % 2 == 0
    )


def _mesh_group_key(primitive: MeshPrimitiveData) -> tuple | None:
    if int(primitive.primitive_type) not in (AK_PRIMITIVE_TRIANGLES, AK_PRIMITIVE_POLYGONS):
        return None
    mesh_key = int(primitive.mesh_key or 0)
    if not mesh_key or not primitive.vertices_f32 or not primitive.indices_u32:
        return None
    if primitive.instance_count or primitive.has_gsplat:
        return None
    if primitive.morph_targets or primitive.morph_anim_channels or primitive.material_anim_channels:
        return None
    if primitive.material_variants:
        return None
    if primitive.point_attr_count:
        return None

    uv_sig = _loop_attr_signature(primitive.uv_sets)
    color_sig = _loop_attr_signature(primitive.color_sets)
    if int(primitive.file_type or 0) == AK_FILE_TYPE_WAVEFRONT:
        mesh_key = 0

    return (
        int(primitive.node_index),
        mesh_key,
        int(primitive.primitive_mode),
        bool(primitive.has_skin),
        int(primitive.skin_root_node_index),
        int(primitive.skin_joint_count),
        int(primitive.skin_joint_width),
        bool(primitive.skin_mesh_in_bind_pose),
        bool(primitive.normals_f32),
        bool(primitive.vertex_normals_f32),
        bool(primitive.tangents_f32),
        uv_sig,
        color_sig,
    )


def _mesh_data_reuse_key(
    primitive: MeshPrimitiveData,
    shading_mode: str,
    preserve_tangents: bool = False,
) -> tuple | None:
    primitive_type = int(primitive.primitive_type)
    if primitive_type not in (AK_PRIMITIVE_TRIANGLES, AK_PRIMITIVE_LINES):
        return None
    if not primitive.vertices_f32 or not primitive.indices_u32:
        return None
    if (
        primitive_type == AK_PRIMITIVE_TRIANGLES
        and int(primitive.loop_count) != int(primitive.face_count) * 3
    ):
        return None
    if primitive.instance_count or primitive.has_gsplat:
        return None
    if primitive.has_skin or primitive.morph_targets or primitive.morph_anim_channels:
        return None
    if primitive.material_anim_channels or primitive.material_variants:
        return None
    if primitive_type != AK_PRIMITIVE_LINES and primitive.point_attr_count:
        return None
    file_type = int(primitive.file_type or 0)
    if file_type == AK_FILE_TYPE_COLLADA:
        geometry_key = int(primitive.geometry_key or 0)
        if geometry_key:
            # The bridge geometry key covers the exact mesh-buffer identity
            # and layout. DAE mesh_key identifies the per-node AkMesh wrapper,
            # so it intentionally differs for repeated references to one
            # geometry.
            source_key = (0, geometry_key)
        else:
            mesh_key = int(primitive.mesh_key or 0)
            if not mesh_key:
                return None
            source_key = (1, mesh_key, int(primitive.primitive_index))
    else:
        mesh_key = int(primitive.mesh_key or 0)
        if not mesh_key:
            geometry_key = int(primitive.geometry_key or 0)
            if not geometry_key:
                return None
            source_key = (0, geometry_key)
        else:
            source_key = (1, mesh_key, int(primitive.primitive_index))

    return (
        source_key,
        primitive_type,
        int(primitive.primitive_mode),
        int(primitive.vertex_count),
        int(primitive.loop_count),
        int(primitive.face_count),
        int(primitive.edge_count),
        bool(primitive.normals_f32),
        bool(primitive.vertex_normals_f32),
        bool(preserve_tangents and primitive.tangents_f32),
        bool(primitive.smooth_shading) if _uses_wavefront_smoothing(primitive) else False,
        _loop_attr_signature(primitive.uv_sets),
        _loop_attr_signature(primitive.color_sets),
        _loop_attr_signature(primitive.point_attrs),
        _has_material_data(primitive),
        shading_mode,
    )


def _line_mesh_data_reuse_key(
    primitive: MeshPrimitiveData,
) -> tuple | None:
    if int(primitive.primitive_type) != AK_PRIMITIVE_LINES:
        return None
    if not primitive.vertices_f32 or not primitive.indices_u32:
        return None
    if primitive.instance_count or primitive.has_gsplat:
        return None
    if primitive.has_skin or primitive.morph_targets or primitive.morph_anim_channels:
        return None
    if primitive.material_anim_channels or primitive.material_variants:
        return None
    geometry_key = int(getattr(primitive, "geometry_key", 0) or 0)
    if not geometry_key:
        return None
    return (
        geometry_key,
        int(primitive.primitive_mode),
        int(primitive.vertex_count),
        int(primitive.loop_count),
        _loop_attr_signature(primitive.point_attrs),
    )


def _grouped_mesh_data_reuse_key(
    surfaces: list[MeshPrimitiveData],
    line: MeshPrimitiveData | None,
    shading_mode: str,
    preserve_tangents: bool = False,
) -> tuple | None:
    if not surfaces:
        return None
    surface_keys = tuple(
        _mesh_data_reuse_key(primitive, shading_mode, preserve_tangents)
        for primitive in surfaces
    )
    if any(key is None for key in surface_keys):
        return None
    line_key = _line_mesh_data_reuse_key(line) if line is not None else None
    if line is not None and line_key is None:
        return None
    return (
        "group",
        surface_keys,
        line_key,
    )


def _buffer_bytes_equal(
    left: object,
    right: object,
    format_code: str,
) -> bool:
    left_view = _buffer_view(left, format_code)
    right_view = _buffer_view(right, format_code)
    if left_view is None or right_view is None:
        return left_view is None and right_view is None
    if len(left_view) != len(right_view):
        return False
    native_equal = native_buffers_equal(left_view, right_view)
    if native_equal is not None:
        return native_equal
    return left_view.cast("B") == right_view.cast("B")


def _mesh_primitive_geometry_equal(
    left: MeshPrimitiveData,
    right: MeshPrimitiveData,
) -> bool:
    # Callers only reach this check after an exact reuse-key lookup. Scalar
    # fields and attribute layouts are already part of that key; compare the
    # backing bytes here solely to defend against a 64-bit geometry-key hash
    # collision without repeating thousands of Python property reads.
    left_buffers = _mesh_primitive_geometry_buffers(left)
    right_buffers = _mesh_primitive_geometry_buffers(right)
    native_equal = native_buffer_sequences_equal(left_buffers, right_buffers)
    if native_equal is not None:
        return native_equal
    buffer_formats = (
        "f",
        "i",
        "i",
        "i",
        "i",
        "f",
        "f",
        "f",
        "B",
    )
    attr_format_count = (
        len(left.uv_sets or ())
        + len(left.color_sets or ())
        + len(left.point_attrs or ())
    )
    return all(
        _buffer_bytes_equal(left_buffer, right_buffer, format_code)
        for left_buffer, right_buffer, format_code in zip(
            left_buffers,
            right_buffers,
            buffer_formats + ("f",) * attr_format_count,
        )
    )


def _mesh_primitive_geometry_buffers(
    primitive: MeshPrimitiveData,
) -> tuple[object, ...]:
    if isinstance(primitive, NativeSimpleMeshData):
        return primitive._geometry_buffer_tuple()
    return (
        primitive.vertices_f32,
        primitive.indices_u32,
        primitive.edges_u32,
        primitive.loop_starts_i32,
        primitive.loop_totals_i32,
        primitive.normals_f32,
        primitive.vertex_normals_f32,
        primitive.tangents_f32,
        primitive.sharp_faces_u8,
        *(attr.values_f32 for attr in (primitive.uv_sets or ())),
        *(attr.values_f32 for attr in (primitive.color_sets or ())),
        *(attr.values_f32 for attr in (primitive.point_attrs or ())),
    )


def _grouped_mesh_geometry_equal(
    cached_surfaces: tuple[MeshPrimitiveData, ...],
    cached_line: MeshPrimitiveData | None,
    surfaces: list[MeshPrimitiveData],
    line: MeshPrimitiveData | None,
) -> bool:
    return (
        len(cached_surfaces) == len(surfaces)
        and all(
            _mesh_primitive_geometry_equal(cached, current)
            for cached, current in zip(cached_surfaces, surfaces)
        )
        and (
            (cached_line is None and line is None)
            or (
                cached_line is not None
                and line is not None
                and _mesh_primitive_geometry_equal(cached_line, line)
            )
        )
    )


def _loop_attr_signature(attrs: list[LoopFloatAttributeData] | None) -> tuple:
    return tuple((attr.name, int(attr.set), int(attr.width)) for attr in (attrs or ()))


def _create_mesh_object(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    shading_mode: str = "AUTO",
    defer_custom_normals: bool = False,
    preserve_tangents: bool = False,
    collection: bpy.types.Collection | None = None,
    object_material_slot: bool = False,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    effective_shading = _effective_shading_mode(data, shading_mode)

    if data.vertices_f32 and data.indices_u32:
        return _create_mesh_object_bulk(
            data,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            node_visibility=node_visibility,
            material_cache=material_cache,
            skin_cache=skin_cache,
            apply_transform=apply_transform,
            apply_animation=apply_animation,
            apply_skin_animation=apply_skin_animation,
            deferred_skin_animations=deferred_skin_animations,
            shading_mode=effective_shading,
            defer_custom_normals=defer_custom_normals,
            preserve_tangents=preserve_tangents,
            collection=collection,
            object_material_slot=object_material_slot,
            node_visibility_animation=node_visibility_animation,
        )

    mesh = bpy.data.meshes.new(data.name)
    mesh.from_pydata(data.vertices, [], data.faces)
    mesh.update(calc_edges=True)

    if data.uvs and len(data.uvs) >= len(mesh.loops):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, uv in enumerate(data.uvs[: len(mesh.loops)]):
            uv_layer.data[loop_index].uv = (uv[0], 1.0 - uv[1])

    normals = data.normals[: len(mesh.loops)] if data.normals else None
    if _apply_wavefront_smoothing(mesh, data, effective_shading, normals, None):
        pass
    elif not (defer_custom_normals and _queue_deferred_custom_normals(mesh, normals, None, data)):
        _apply_shading(mesh, effective_shading, normals)
    return _finish_mesh_object(
        mesh,
        data,
        parent,
        node_objects=node_objects,
        node_data=node_data,
        node_visibility=node_visibility,
        material_cache=material_cache,
        skin_cache=skin_cache,
        apply_transform=apply_transform,
        apply_animation=apply_animation,
        apply_skin_animation=apply_skin_animation,
        deferred_skin_animations=deferred_skin_animations,
        collection=collection,
        object_material_slot=object_material_slot,
        node_visibility_animation=node_visibility_animation,
    )


def _create_mesh_object_bulk(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    shading_mode: str = "AUTO",
    defer_custom_normals: bool = False,
    preserve_tangents: bool = False,
    collection: bpy.types.Collection | None = None,
    object_material_slot: bool = False,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    if data.primitive_type == AK_PRIMITIVE_LINES:
        return _create_line_mesh_object_bulk(
            data,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            node_visibility=node_visibility,
            material_cache=material_cache,
            skin_cache=skin_cache,
            apply_transform=apply_transform,
            apply_animation=apply_animation,
            apply_skin_animation=apply_skin_animation,
            deferred_skin_animations=deferred_skin_animations,
            collection=collection,
            node_visibility_animation=node_visibility_animation,
        )
    if data.primitive_type == AK_PRIMITIVE_POINTS:
        return _create_point_mesh_object_bulk(
            data,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            node_visibility=node_visibility,
            material_cache=material_cache,
            skin_cache=skin_cache,
            apply_transform=apply_transform,
            apply_animation=apply_animation,
            apply_skin_animation=apply_skin_animation,
            deferred_skin_animations=deferred_skin_animations,
            collection=collection,
            node_visibility_animation=node_visibility_animation,
        )

    profile_detail = _profile_state.stats is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    phase_total_ms = 0.0
    phase_samples: dict[str, float] = {}
    detail_parts: list[str] = []

    def lap_detail(name: str) -> None:
        nonlocal phase_started_at, phase_total_ms
        if not profile_detail:
            return
        now = time.perf_counter()
        elapsed = (now - phase_started_at) * 1000.0
        phase_total_ms += elapsed
        phase_samples[name] = phase_samples.get(name, 0.0) + elapsed
        detail_parts.append(f"{name}={elapsed:.3f}ms")
        phase_started_at = now

    mesh = bpy.data.meshes.new(data.name)

    mesh.vertices.add(data.vertex_count)
    mesh.loops.add(data.loop_count)
    mesh.polygons.add(data.face_count)
    lap_detail("alloc")

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")
    lap_detail("views")

    if vertices is None or indices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete mesh buffers")
    if loop_starts is None:
        loop_starts = _triangle_loop_starts(int(data.loop_count))

    _set_mesh_positions(mesh, vertices)
    _set_mesh_loop_vertex_indices(mesh, indices)
    _set_mesh_loop_starts(mesh, loop_starts, int(data.loop_count), int(data.face_count))
    if loop_totals is not None and int(data.loop_count) != int(data.face_count) * 3:
        mesh.polygons.foreach_set("loop_total", _rna_i32_values(loop_totals))
    _apply_point_attributes(mesh, data)
    lap_detail("topology")

    if data.uv_sets:
        for index, attr in enumerate(data.uv_sets):
            uvs = _buffer_view(attr.values_f32, "f")
            uv_layer = mesh.uv_layers.new(name=attr.name or ("UVMap" if index == 0 else f"UVMap.{index:03d}"))
            if uvs is not None:
                _set_uv_layer_values(uv_layer, uvs)
    elif data.uvs_f32:
        uvs = _buffer_view(data.uvs_f32, "f")
        uv_layer = mesh.uv_layers.new(name="UVMap")
        if uvs is not None:
            _set_uv_layer_values(uv_layer, uvs)
    lap_detail("uv")

    if data.color_sets:
        for index, attr in enumerate(data.color_sets):
            colors = _buffer_view(attr.values_f32, "f")
            if colors is not None:
                color_attr = mesh.color_attributes.new(
                    name=attr.name or ("Color" if index == 0 else f"Color.{index:03d}"),
                    type="FLOAT_COLOR",
                    domain="CORNER",
                )
                color_attr.data.foreach_set("color", colors)
        _set_render_color_index(mesh)
    elif data.colors_f32:
        colors = _buffer_view(data.colors_f32, "f")
        if colors is not None:
            color_attr = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
            color_attr.data.foreach_set("color", colors)
            _set_render_color_index(mesh)
    lap_detail("color")

    if preserve_tangents and data.tangents_f32:
        tangents = _buffer_view(data.tangents_f32, "f")
        if tangents is not None:
            if not _apply_vector_attribute(mesh, "assetkit_tangent", tangents, "FLOAT4", "CORNER"):
                _apply_split_attribute(mesh, "assetkit_tangent", tangents, ("x", "y", "z", "w"), "CORNER")
    lap_detail("tangent")

    normals = _buffer_view(data.normals_f32, "f") if data.normals_f32 else None
    vertex_normals = _buffer_view(data.vertex_normals_f32, "f") if data.vertex_normals_f32 else None
    if str(shading_mode or "AUTO").upper() == "FLAT":
        shading_done = _apply_shading(mesh, shading_mode, normals, vertex_normals, apply_custom_normals=False)
    elif _apply_wavefront_smoothing(mesh, data, shading_mode, normals, vertex_normals):
        shading_done = True
    elif shading_mode != "SMOOTH" and not normals and vertex_normals is None:
        shading_done = True
    else:
        shading_done = _apply_shading(mesh, shading_mode, normals, vertex_normals, apply_custom_normals=False)
    # Blender derives polygon edges faster than feeding large edge buffers here;
    # line primitives still use their dedicated edge path.
    mesh.update(calc_edges=False)
    lap_detail("update")
    if not shading_done and defer_custom_normals:
        shading_done = _queue_deferred_custom_normals(mesh, normals, vertex_normals, data)
    if not shading_done:
        _apply_shading(mesh, shading_mode, normals, vertex_normals, smooth_already=True)
    lap_detail("shading")
    objects = _finish_mesh_object(
        mesh,
        data,
        parent,
        node_objects=node_objects,
        node_data=node_data,
        node_visibility=node_visibility,
        material_cache=material_cache,
        skin_cache=skin_cache,
        apply_transform=apply_transform,
        apply_animation=apply_animation,
        apply_skin_animation=apply_skin_animation,
        deferred_skin_animations=deferred_skin_animations,
        collection=collection,
        object_material_slot=object_material_slot,
        node_visibility_animation=node_visibility_animation,
    )
    if profile_detail:
        total_ms = (time.perf_counter() - total_started_at) * 1000.0
        phase_samples["finish"] = max(0.0, total_ms - phase_total_ms)
        _record_mesh_profile(phase_samples, total_ms)
        if total_ms >= 10.0:
            _profile_log(
                "create_mesh_object_bulk_detail "
                f"name={data.name!r} verts={data.vertex_count} faces={data.face_count} "
                + " ".join(detail_parts)
                + f" finish={total_ms - phase_total_ms:.3f}ms "
                f"total={total_ms:.3f}ms"
            )
    return objects


def _create_line_mesh_object_bulk(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    collection: bpy.types.Collection | None = None,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    mesh = bpy.data.meshes.new(data.name)
    edge_count = data.loop_count // 2

    mesh.vertices.add(data.vertex_count)
    mesh.edges.add(edge_count)

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    if vertices is None or indices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete line buffers")

    _set_mesh_positions(mesh, vertices)
    if edge_count:
        _set_mesh_edges(mesh, indices)
    _apply_point_attributes(mesh, data)
    mesh.update(calc_edges=False)

    return _finish_mesh_object(
        mesh,
        data,
        parent,
        node_objects=node_objects,
        node_data=node_data,
        node_visibility=node_visibility,
        material_cache=material_cache,
        skin_cache=skin_cache,
        apply_transform=apply_transform,
        apply_animation=apply_animation,
        apply_skin_animation=apply_skin_animation,
        deferred_skin_animations=deferred_skin_animations,
        collection=collection,
        node_visibility_animation=node_visibility_animation,
    )


def _create_point_mesh_object_bulk(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    collection: bpy.types.Collection | None = None,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    mesh = bpy.data.meshes.new(data.name)

    mesh.vertices.add(data.vertex_count)
    vertices = _buffer_view(data.vertices_f32, "f")
    if vertices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete point buffers")

    _set_mesh_positions(mesh, vertices)
    _apply_point_attributes(mesh, data)
    mesh.update(calc_edges=False)

    return _finish_mesh_object(
        mesh,
        data,
        parent,
        node_objects=node_objects,
        node_data=node_data,
        node_visibility=node_visibility,
        material_cache=material_cache,
        skin_cache=skin_cache,
        apply_transform=apply_transform,
        apply_animation=apply_animation,
        apply_skin_animation=apply_skin_animation,
        deferred_skin_animations=deferred_skin_animations,
        collection=collection,
        node_visibility_animation=node_visibility_animation,
    )


def _finish_mesh_object(
    mesh: bpy.types.Mesh,
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    node_visibility: dict[int, bool] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    apply_skin_animation: bool = True,
    deferred_skin_animations: list | None = None,
    collection: bpy.types.Collection | None = None,
    assign_material: bool = True,
    object_material_slot: bool = False,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    profile_detail = _profile_state.stats is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    _apply_skin_bind_shape(mesh, data)
    if profile_detail:
        now = time.perf_counter()
        bind_shape_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    active_collection = collection or bpy.context.collection
    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if node_visibility is not None and data.node_index >= 0:
        _set_node_visibility(obj, node_visibility.get(data.node_index, True))
    if apply_transform:
        _apply_matrix(obj, data)
    active_collection.objects.link(obj)
    if profile_detail:
        now = time.perf_counter()
        object_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    if assign_material:
        material = _material_for_data(data, material_cache)
        if material:
            _assign_mesh_material(obj, mesh, material, object_material_slot=object_material_slot)
    if profile_detail:
        now = time.perf_counter()
        material_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    _apply_assetkit_extra_props(obj, data)
    if assign_material and data.material_variants:
        _apply_material_variants(obj, data, material_cache)
    if profile_detail:
        now = time.perf_counter()
        props_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    if data.morph_targets:
        _apply_shape_keys(obj, data)
    if data.morph_presets:
        _apply_morph_presets(obj, data)
    if profile_detail:
        now = time.perf_counter()
        morph_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    node_lookup = node_data or {}
    if data.has_skin:
        _apply_skin(
            obj,
            data,
            node_objects or {},
            node_lookup,
            active_collection,
            skin_cache,
            apply_animation=apply_skin_animation,
            deferred_skin_animations=deferred_skin_animations,
        )
    if profile_detail:
        now = time.perf_counter()
        skin_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    has_animation = bool(data.anim_count or data.anim_channels)
    has_node_visibility_animation = (
        _node_has_effective_visibility_animation(data.node_index, node_lookup)
        if node_visibility_animation and (has_animation or node_lookup)
        else False
    )
    if apply_animation and has_animation:
        _apply_animation(obj, data, skip_visibility=has_node_visibility_animation)
    if has_node_visibility_animation:
        _apply_effective_node_visibility_animation(obj, data.node_index, node_lookup)
    if profile_detail:
        now = time.perf_counter()
        animation_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now

    objects = _apply_instancing(obj, data, active_collection) if data.instance_count else [obj]
    if profile_detail:
        now = time.perf_counter()
        instancing_ms = (now - phase_started_at) * 1000.0
        total_ms = (now - total_started_at) * 1000.0
        _record_finish_profile(
            bind_shape_ms=bind_shape_ms,
            object_ms=object_ms,
            material_ms=material_ms,
            props_ms=props_ms,
            morph_ms=morph_ms,
            skin_ms=skin_ms,
            animation_ms=animation_ms,
            instancing_ms=instancing_ms,
            total_ms=total_ms,
        )
    if profile_detail and total_ms >= 10.0:
        _profile_log(
            "finish_mesh_object_detail "
            f"name={obj.name!r} "
            f"verts={data.vertex_count} faces={data.face_count} "
            f"bind_shape={bind_shape_ms:.3f}ms "
            f"object={object_ms:.3f}ms "
            f"material={material_ms:.3f}ms "
            f"props={props_ms:.3f}ms "
            f"morph={morph_ms:.3f}ms "
            f"skin={skin_ms:.3f}ms "
            f"animation={animation_ms:.3f}ms "
            f"instancing={instancing_ms:.3f}ms "
            f"total={total_ms:.3f}ms"
        )
    return objects


def _apply_instancing(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    count = int(data.instance_count or 0)
    matrices = _buffer_view(data.instance_matrices_f32, "f")
    if count <= 0 or matrices is None or len(matrices) < count * 16:
        return [obj]

    original = obj.matrix_local.copy()
    objects = [obj]
    group = obj.name
    obj.matrix_local = original @ _matrix_from_values(matrices, 0)
    obj["assetkit_instance_group"] = group
    obj["assetkit_instance_index"] = 0
    obj["assetkit_instance_count"] = count

    base_name = obj.name
    for index in range(1, count):
        duplicate = obj.copy()
        duplicate.data = obj.data
        duplicate.name = f"{base_name}_Instance_{index:03d}"
        duplicate.matrix_local = original @ _matrix_from_values(matrices, index * 16)
        duplicate["assetkit_instance_group"] = group
        duplicate["assetkit_instance_index"] = index
        duplicate["assetkit_instance_count"] = count
        collection.objects.link(duplicate)
        objects.append(duplicate)

    return objects
