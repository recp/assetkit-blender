from __future__ import annotations

import math
import time
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
    AK_INTERPOLATION_LINEAR,
    AK_LIGHT_TYPE_DIRECTIONAL,
    AK_LIGHT_TYPE_POINT,
    AK_LIGHT_TYPE_SPOT,
    AK_PRIMITIVE_LINES,
    AK_PRIMITIVE_POINTS,
    AK_PROJECTION_ORTHOGRAPHIC,
    AK_PROJECTION_PERSPECTIVE,
)

from .animation import animation_action_slot
from .animation.common import _iter_action_fcurves
from .animation.transform import (
    _action_interpolation,
    _float_samples_changed,
    _set_scene_frame,
)
from .common import (
    _append_matrix_values,
    _assetkit_json_prop,
    _profile_enabled,
    _profile_log,
)
from .images import _ExportImageStore
from .materials import _material_bake_required, _material_tuple

_AKB_NATIVE_MESH_PAYLOAD = 0x414B4D46
_AKB_NATIVE_CURVE_PAYLOAD = 0x414B4356
_MESH_EXPORT_OBJECT_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
_ANIMATED_SCENE_FORMATS = frozenset((AK_FILE_TYPE_GLTF, AK_FILE_TYPE_GLB, AK_FILE_TYPE_DAE))
_STATIC_SCENE_MESH_FORMATS = frozenset(
    (AK_FILE_TYPE_3MF, AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY, AK_FILE_TYPE_WAVEFRONT)
)
_NATIVE_STATIC_MESH_PAYLOAD_FORMATS = frozenset((AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY))
_NO_MATERIAL_FORMATS = frozenset((AK_FILE_TYPE_STL,))
_NO_UV_COLOR_FORMATS = frozenset((AK_FILE_TYPE_STL,))
_STATIC_SCALE_FORMATS = frozenset((AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY, AK_FILE_TYPE_WAVEFRONT))
_RAW_Z_UP_FORMATS = frozenset(
    (AK_FILE_TYPE_3MF, AK_FILE_TYPE_DAE, AK_FILE_TYPE_PLY, AK_FILE_TYPE_STL, AK_FILE_TYPE_WAVEFRONT)
)


def _mesh_skin_setup(
    obj: bpy.types.Object,
    armature: bpy.types.Object | None,
    object_indices: dict[bpy.types.Object, int],
    bone_indices: dict[tuple[bpy.types.Object, str], int],
) -> tuple | None:
    if armature is None:
        return None

    armature_index = object_indices.get(armature)
    if armature_index is None:
        return None

    bones = list(getattr(armature.data, "bones", []) or [])
    if not bones:
        return None

    joint_bones = [
        bone for bone in bones
        if getattr(bone, "use_deform", True)
        and (armature, bone.name) in bone_indices
    ]
    if not joint_bones or len(joint_bones) > 65535:
        return None

    joint_by_name = {bone.name: index for index, bone in enumerate(joint_bones)}
    max_group_index = max((int(group.index) for group in getattr(obj, "vertex_groups", []) or []), default=-1)
    group_to_joint = [-1] * (max_group_index + 1) if max_group_index >= 0 else []
    for group in getattr(obj, "vertex_groups", []) or []:
        joint_index = joint_by_name.get(group.name)
        if joint_index is not None:
            group_to_joint[int(group.index)] = int(joint_index)

    if not any(joint_index >= 0 for joint_index in group_to_joint):
        return None

    joint_node_indices = tuple(bone_indices[(armature, bone.name)] for bone in joint_bones)
    inverse_bind_matrices = array("f")
    mesh_world_inv = obj.matrix_world.inverted_safe()
    armature_world = armature.matrix_world
    for bone in joint_bones:
        _append_matrix_values(
            inverse_bind_matrices,
            (mesh_world_inv @ (armature_world @ bone.matrix_local)).inverted_safe(),
        )

    return (
        tuple(group_to_joint),
        joint_node_indices,
        inverse_bind_matrices,
        armature_index,
    )


def _mesh_payload(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    source_mesh: bpy.types.Mesh | None,
    file_type: int,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple, tuple | None],
    material_export_mode: str,
    material_bake_size: int,
    lighting_bake_mode: str,
    *,
    skin_setup: tuple | None = None,
    export_uv: bool = True,
    export_normals: bool = True,
    export_tangents: bool = True,
    export_vertex_colors: bool = True,
    export_attributes: bool = True,
    export_materials: bool = True,
    export_images: bool = True,
    export_shape_keys: bool = True,
    export_shape_key_normals: bool = True,
    export_shape_key_tangents: bool = True,
    export_shape_key_animations: bool = True,
    animation_bake_mode: str = "OFF",
    export_custom_properties: bool = True,
    ply_export_normals: bool = False,
    ply_export_uv: bool = True,
    ply_export_colors: bool = True,
    ply_export_triangulated: bool = False,
) -> tuple | None:
    profile = _profile_enabled()
    phase_started_at = time.perf_counter() if profile else 0.0
    is_stl = file_type in _NO_UV_COLOR_FORMATS
    is_ply = file_type == AK_FILE_TYPE_PLY
    is_static_mesh = file_type in _NATIVE_STATIC_MESH_PAYLOAD_FORMATS
    uv_layers = [] if is_stl or not export_uv or (is_ply and not ply_export_uv) else _uv_layers(mesh)
    color_layers = [] if is_stl or not export_vertex_colors or (is_ply and not ply_export_colors) else _color_attributes(mesh)
    layer_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile else 0.0
    phase_started_at = time.perf_counter() if profile else 0.0

    if is_stl:
        export_ply_normals = bool(export_normals and ply_export_normals) if is_ply else False
        native_payload = (
            _AKB_NATIVE_MESH_PAYLOAD,
            mesh,
            tuple(uv_layers),
            tuple(color_layers),
            (),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            _mesh_primitive_type_for_export(obj, mesh),
            _mesh_primitive_mode_for_export(obj, mesh),
            export_ply_normals,
            bool(ply_export_triangulated) if is_ply else True,
            bool(export_normals),
            bool(export_tangents and export_attributes),
        )
        native_payload_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile else 0.0
        if profile:
            _profile_log(
                f"mesh_payload name={mesh.name!r} loops={len(mesh.loops)} "
                f"layers={layer_ms:.3f}ms "
                f"morph=0.000ms native_tuple={native_payload_ms:.3f}ms"
            )
        return native_payload

    uv_names = tuple(layer.name for layer in uv_layers)
    uv_slot_by_name = {name: index for index, name in enumerate(uv_names)}
    fps = 24.0
    fps = float(context.scene.render.fps) / float(context.scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    if is_static_mesh:
        morph_targets = []
        morph_animation = None
    elif export_shape_keys and animation_bake_mode == "EVALUATED_MESH":
        baked = _evaluated_mesh_animation_bake(context, obj, mesh)
        if baked is not None:
            morph_targets, morph_animation = baked
        else:
            morph_targets = _shape_key_targets(mesh, source_mesh)
            morph_animation = (
                _shape_key_weight_animation(context, source_mesh, morph_targets)
                if export_shape_key_animations
                else None
            )
    else:
        morph_targets = _shape_key_targets(mesh, source_mesh) if export_shape_keys else []
        morph_animation = (
            _shape_key_weight_animation(context, source_mesh, morph_targets)
            if export_shape_key_animations
            else None
        )
    morph_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile else 0.0
    phase_started_at = time.perf_counter() if profile else 0.0

    native_payload = _native_mesh_payload(
        obj,
        mesh,
        uv_layers,
        color_layers,
        image_store,
        material_cache,
        uv_slot_by_name,
        uv_names,
        fps,
        context,
        file_type,
        material_export_mode,
        material_bake_size,
        lighting_bake_mode,
        variant_payload=None if is_static_mesh else _material_variant_payload(obj),
        skin_setup=None if is_static_mesh else skin_setup,
        morph_targets=morph_targets,
        morph_animation=morph_animation,
        ply_export_normals=ply_export_normals if is_ply else True,
        ply_export_triangulated=ply_export_triangulated if file_type == AK_FILE_TYPE_PLY else True,
        export_normals=export_normals,
        export_tangents=export_tangents and export_attributes,
        export_materials=export_materials,
        export_images=export_images,
        export_custom_properties=export_custom_properties,
    )
    native_payload_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile else 0.0
    if profile:
        _profile_log(
            f"mesh_payload name={mesh.name!r} loops={len(mesh.loops)} "
            f"layers={layer_ms:.3f}ms "
            f"morph={morph_ms:.3f}ms native_tuple={native_payload_ms:.3f}ms"
        )
    return native_payload


def _native_mesh_payload(
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    uv_layers: list,
    color_layers: list,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple, tuple | None],
    uv_slot_by_name: dict[str, int],
    uv_names: tuple[str, ...],
    fps: float,
    context: bpy.types.Context,
    file_type: int,
    material_export_mode: str,
    material_bake_size: int,
    lighting_bake_mode: str,
    *,
    variant_payload: tuple | None = None,
    skin_setup: tuple | None = None,
    morph_targets: list | None = None,
    morph_animation: tuple | None = None,
    ply_export_normals: bool = True,
    ply_export_triangulated: bool = True,
    export_normals: bool = True,
    export_tangents: bool = True,
    export_materials: bool = True,
    export_images: bool = True,
    export_custom_properties: bool = True,
):
    if file_type in _NO_MATERIAL_FORMATS or not export_materials or material_export_mode == "NONE":
        material_payloads = ()
        variant_payload = None
    else:
        material_payloads = tuple(
            _cached_material_tuple(
                _material_for_index(obj, mesh, index),
                image_store,
                material_cache,
                uv_slot_by_name,
                uv_names,
                fps,
                context,
                obj,
                mesh,
                index,
                file_type,
                material_export_mode,
                material_bake_size,
                lighting_bake_mode,
                export_images,
            )
            for index in range(len(mesh.materials))
        )
    skin_payload = None
    skin_mapping = None
    if skin_setup is not None:
        skin_mapping = skin_setup[0]
        skin_payload = (
            skin_setup[1],
            skin_setup[2],
            skin_setup[3],
        )
    morph_payload = _native_morph_payload(morph_targets, morph_animation)
    mixed_line_material_slot = -(2**31)
    if "assetkit_mixed_line_material_slot" in obj:
        try:
            mixed_line_material_slot = int(
                obj.get("assetkit_mixed_line_material_slot", -1)
            )
        except (TypeError, ValueError):
            mixed_line_material_slot = -1
    try:
        mixed_line_mode = int(obj.get("assetkit_mixed_line_mode", 0))
    except (TypeError, ValueError):
        mixed_line_mode = 0
    return (
        _AKB_NATIVE_MESH_PAYLOAD,
        mesh,
        tuple(uv_layers),
        tuple(color_layers),
        material_payloads,
        skin_mapping,
        skin_payload,
        morph_payload,
        variant_payload,
        _assetkit_json_prop(obj, "assetkit_mesh_extra_json") if export_custom_properties else None,
        _assetkit_json_prop(obj, "assetkit_geometry_extra_json") if export_custom_properties else None,
        _assetkit_json_prop(obj, "assetkit_primitive_extra_json") if export_custom_properties else None,
        _mesh_primitive_type_for_export(obj, mesh),
        _mesh_primitive_mode_for_export(obj, mesh),
        bool(ply_export_normals),
        bool(ply_export_triangulated),
        bool(export_normals),
        bool(export_tangents),
        mixed_line_material_slot,
        mixed_line_mode,
        (
            _assetkit_json_prop(obj, "assetkit_mixed_line_primitive_extra_json")
            if export_custom_properties
            else None
        ),
    )


def _material_variant_payload(obj: bpy.types.Object) -> tuple | None:
    try:
        count = int(obj.get("assetkit_material_variant_count") or 0)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None

    out: list[tuple[int, str, int]] = []
    for index in range(count):
        prefix = f"assetkit_material_variant_{index}"
        try:
            variant_index = int(obj.get(f"{prefix}_index") or index)
            slot = int(obj.get(f"{prefix}_slot"))
        except (TypeError, ValueError):
            continue
        if slot < 0:
            continue
        out.append((variant_index, str(obj.get(f"{prefix}_name") or ""), slot))
    return tuple(out) if out else None


def _mesh_primitive_type_for_export(obj: bpy.types.Object, mesh: bpy.types.Mesh) -> int:
    try:
        value = int(obj.get("assetkit_primitive_type", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    if value:
        return value
    if len(mesh.polygons) == 0:
        return AK_PRIMITIVE_LINES if len(mesh.edges) > 0 else AK_PRIMITIVE_POINTS
    return 0


def _mesh_primitive_mode_for_export(obj: bpy.types.Object, mesh: bpy.types.Mesh) -> int:
    try:
        value = int(obj.get("assetkit_primitive_mode", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    if value:
        return value
    if len(mesh.polygons) == 0 and len(mesh.edges) > 0:
        return 1
    return 0


def _native_morph_payload(morph_targets: list | None, morph_animation: tuple | None) -> tuple | None:
    if not morph_targets:
        return None
    basis = morph_targets[0][1]
    return (
        basis,
        tuple(target[2] for target in morph_targets),
        tuple(target[0] for target in morph_targets),
        tuple(target[3] for target in morph_targets),
        morph_animation,
    )


def _cached_material_tuple(
    material: bpy.types.Material | None,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple, tuple | None],
    uv_slot_by_name: dict[str, int],
    uv_names: tuple[str, ...],
    fps: float,
    context: bpy.types.Context,
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    material_index: int,
    file_type: int,
    material_export_mode: str,
    material_bake_size: int,
    lighting_bake_mode: str,
    export_images: bool = True,
) -> tuple | None:
    if material is None:
        return None
    if lighting_bake_mode == "FINAL" or _material_bake_required(material, material_export_mode):
        key = (
            int(material.as_pointer()),
            int(obj.as_pointer()),
            int(mesh.as_pointer()),
            int(material_index),
            uv_names,
            material_export_mode,
            int(material_bake_size),
            lighting_bake_mode,
            int(file_type or 0),
            bool(export_images),
        )
    else:
        key = (int(material.as_pointer()), uv_names, int(file_type or 0), bool(export_images))
    cached = material_cache.get(key)
    if cached is not None or key in material_cache:
        return cached
    cached = _material_tuple(
        material,
        image_store,
        uv_slot_by_name,
        fps,
        context=context,
        obj=obj,
        mesh=mesh,
        material_index=material_index,
        file_type=file_type,
        material_export_mode=material_export_mode,
        material_bake_size=material_bake_size,
        lighting_bake_mode=lighting_bake_mode,
        export_images=export_images,
    )
    material_cache[key] = cached
    return cached


def _camera_payload(context: bpy.types.Context, obj: bpy.types.Object) -> tuple | None:
    cam = obj.data
    render = context.scene.render
    width = float(render.resolution_x) * float(render.pixel_aspect_x)
    height = float(render.resolution_y) * float(render.pixel_aspect_y)
    if width <= 0.0 or height <= 0.0:
        width = 1.0
        height = 1.0
    aspect = width / height

    if cam.type == "PERSP":
        payload = (
            AK_PROJECTION_PERSPECTIVE,
            _camera_yfov(cam.angle, width, height, cam.sensor_fit),
            aspect,
            float(cam.clip_start),
            float(cam.clip_end),
            0.0,
            0.0,
            _assetkit_json_prop(cam, "assetkit_camera_extra_json"),
        )
    elif cam.type == "ORTHO":
        scene_square = max(width, height)
        xmag = float(cam.ortho_scale) * (width / scene_square) * 0.5
        ymag = float(cam.ortho_scale) * (height / scene_square) * 0.5
        payload = (
            AK_PROJECTION_ORTHOGRAPHIC,
            0.0,
            aspect,
            float(cam.clip_start),
            float(cam.clip_end),
            xmag,
            ymag,
            _assetkit_json_prop(cam, "assetkit_camera_extra_json"),
        )
    else:
        return None

    return payload


def _light_payload(obj: bpy.types.Object) -> tuple | None:
    light = obj.data
    if light.type == "SUN":
        light_type = AK_LIGHT_TYPE_DIRECTIONAL
    elif light.type == "POINT":
        light_type = AK_LIGHT_TYPE_POINT
    elif light.type == "SPOT":
        light_type = AK_LIGHT_TYPE_SPOT
    else:
        return None

    color = array("f", (float(light.color[0]), float(light.color[1]), float(light.color[2])))
    intensity = float(light.energy)
    light_range = float(light.cutoff_distance) if getattr(light, "use_custom_distance", False) else 0.0
    inner = 0.0
    outer = 0.0
    falloff = 1.0

    if light.type == "SPOT":
        outer = float(light.spot_size) * 0.5
        inner = outer - outer * float(light.spot_blend)

    payload = (
        light_type,
        color,
        intensity,
        light_range,
        inner,
        outer,
        falloff,
        _assetkit_json_prop(light, "assetkit_light_extra_json"),
    )
    return payload


def _camera_yfov(angle: float, width: float, height: float, sensor_fit: str) -> float:
    aspect = width / height
    if width >= height:
        if sensor_fit != "VERTICAL":
            return 2.0 * math.atan(math.tan(angle * 0.5) / aspect)
        return float(angle)

    if sensor_fit != "HORIZONTAL":
        return float(angle)
    return 2.0 * math.atan(math.tan(angle * 0.5) / aspect)


def _material_for_index(
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    index: int,
) -> bpy.types.Material | None:
    slots = getattr(obj, "material_slots", None)
    if slots is not None and 0 <= index < len(slots):
        slot = slots[index]
        material = getattr(slot, "material", None)
        if material is not None or getattr(slot, "link", "DATA") == "OBJECT":
            return material
    if 0 <= index < len(mesh.materials):
        return mesh.materials[index]
    return None


def _uv_layers(mesh: bpy.types.Mesh) -> list:
    layers = getattr(mesh, "uv_layers", None)
    if layers is None:
        return []

    out = []
    active = getattr(layers, "active", None)
    if active is not None and len(active.data) >= len(mesh.loops):
        out.append(active)

    for layer in layers:
        if len(layer.data) < len(mesh.loops):
            continue
        if active is not None and layer.name == active.name:
            continue
        out.append(layer)

    return out


def _color_attributes(mesh: bpy.types.Mesh) -> list:
    attrs = getattr(mesh, "color_attributes", None)
    if attrs is None:
        return []

    out = []
    active = getattr(attrs, "active_color", None)
    if _color_attribute_exportable(mesh, active):
        out.append(active)

    for attr in attrs:
        if not _color_attribute_exportable(mesh, attr):
            continue
        if active is not None and attr.name == active.name:
            continue
        out.append(attr)

    return out


def _color_attribute_exportable(mesh: bpy.types.Mesh, attr) -> bool:
    if attr is None or attr.domain not in {"CORNER", "POINT"}:
        return False
    if attr.domain == "CORNER":
        return len(attr.data) >= len(mesh.loops)
    return len(attr.data) >= len(mesh.vertices)


class _EvaluatedMeshPositionData:
    __slots__ = ("_coords", "_count")

    def __init__(self, coords: array):
        self._coords = coords
        self._count = len(coords) // 3

    def __len__(self) -> int:
        return self._count

    def foreach_get(self, prop: str, buffer) -> None:
        if prop != "co":
            raise AttributeError(prop)
        buffer[:] = self._coords


class _EvaluatedMeshShapeKey:
    __slots__ = ("name", "data")

    def __init__(self, name: str, coords: array):
        self.name = name
        self.data = _EvaluatedMeshPositionData(coords)


def _mesh_position_array(mesh: bpy.types.Mesh) -> array:
    coords = array("f", [0.0]) * (len(mesh.vertices) * 3)
    if coords:
        mesh.vertices.foreach_get("co", coords)
    return coords


def _mesh_topology_signature(mesh: bpy.types.Mesh) -> tuple | None:
    vertex_count = len(mesh.vertices)
    loop_count = len(mesh.loops)
    polygon_count = len(mesh.polygons)
    if vertex_count == 0 or loop_count == 0 or polygon_count == 0:
        return None

    loop_vertices = array("i", [0]) * loop_count
    poly_loop_starts = array("i", [0]) * polygon_count
    poly_loop_totals = array("i", [0]) * polygon_count
    poly_materials = array("i", [0]) * polygon_count
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    mesh.polygons.foreach_get("loop_start", poly_loop_starts)
    mesh.polygons.foreach_get("loop_total", poly_loop_totals)
    mesh.polygons.foreach_get("material_index", poly_materials)
    return (
        vertex_count,
        loop_count,
        polygon_count,
        loop_vertices,
        poly_loop_starts,
        poly_loop_totals,
        poly_materials,
    )


def _float_array_matches(a: array, b: array, epsilon: float = 1.0e-6) -> bool:
    if len(a) != len(b):
        return False
    for index, value in enumerate(a):
        if abs(float(value) - float(b[index])) > epsilon:
            return False
    return True


def _evaluated_mesh_frame_name(frame: int) -> str:
    return f"Frame_{frame:04d}" if frame >= 0 else f"Frame_m{abs(frame):04d}"


def _evaluated_mesh_animation_frames(scene: bpy.types.Scene) -> tuple[int, ...]:
    start = int(scene.frame_start)
    end = int(scene.frame_end)
    if end <= start:
        return ()
    return tuple(range(start, end + 1))


def _evaluated_mesh_animation_bake(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    base_mesh: bpy.types.Mesh,
) -> tuple[list, tuple] | None:
    scene = context.scene
    frames = _evaluated_mesh_animation_frames(scene)
    if len(frames) < 2:
        return None

    topology = _mesh_topology_signature(base_mesh)
    if topology is None:
        return None

    basis_coords = _mesh_position_array(base_mesh)
    positions: list[tuple[int, array]] = [(frames[0], basis_coords)]
    changed = False
    saved_frame = scene.frame_current
    saved_subframe = scene.frame_subframe
    try:
        for frame in frames[1:]:
            _set_scene_frame(scene, float(frame))
            depsgraph = context.evaluated_depsgraph_get()
            obj_eval = obj.evaluated_get(depsgraph)
            sample_mesh = bpy.data.meshes.new_from_object(obj_eval, depsgraph=depsgraph)
            try:
                if sample_mesh is None or _mesh_topology_signature(sample_mesh) != topology:
                    return None
                coords = _mesh_position_array(sample_mesh)
                if not changed and not _float_array_matches(coords, basis_coords):
                    changed = True
                positions.append((frame, coords))
            finally:
                if sample_mesh is not None:
                    bpy.data.meshes.remove(sample_mesh)
    finally:
        scene.frame_set(saved_frame, subframe=saved_subframe)

    if not changed or len(positions) < 2:
        return None

    target_count = len(positions) - 1
    basis = _EvaluatedMeshShapeKey("Basis", basis_coords)
    morph_targets = []
    for frame, coords in positions[1:]:
        name = _evaluated_mesh_frame_name(frame)
        morph_targets.append((name, basis, _EvaluatedMeshShapeKey(name, coords), 0.0))

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    times = array("f")
    values = array("f")
    for sample_index, (frame, _coords) in enumerate(positions):
        times.append(float(frame) / fps)
        active_target = sample_index - 1
        for target_index in range(target_count):
            values.append(1.0 if target_index == active_target else 0.0)

    return morph_targets, (
        times,
        values,
        len(times),
        target_count,
        AK_INTERPOLATION_LINEAR,
    )


def _shape_key_targets(mesh: bpy.types.Mesh, source_mesh: bpy.types.Mesh | None) -> list:
    if source_mesh is None or len(mesh.vertices) != len(source_mesh.vertices):
        return []

    shape_keys = getattr(source_mesh, "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", None)
    if key_blocks is None or len(key_blocks) <= 1:
        return []

    basis = key_blocks[0]
    if len(basis.data) < len(mesh.vertices):
        return []

    out = []
    for key in key_blocks[1:]:
        if len(key.data) < len(mesh.vertices):
            continue
        out.append((key.name, basis, key, float(getattr(key, "value", 0.0))))
    return out


def _shape_key_weight_animation(
    context: bpy.types.Context,
    source_mesh: bpy.types.Mesh | None,
    morph_targets: list,
) -> tuple | None:
    if source_mesh is None or not morph_targets:
        return None

    shape_keys = getattr(source_mesh, "shape_keys", None)
    animation_data = getattr(shape_keys, "animation_data", None)
    action = animation_data.action if animation_data else None
    if action is None:
        return None
    fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(animation_data)))
    if not fcurves:
        return None

    path_to_index: dict[str, int] = {}
    defaults = array("f")
    for index, target in enumerate(morph_targets):
        _name, _basis, key, weight = target
        try:
            path = key.path_from_id("value")
        except Exception:
            continue
        path_to_index[path] = index
        defaults.append(float(weight))

    target_count = len(morph_targets)
    if len(defaults) != target_count or not path_to_index:
        return None

    fcurves_by_index: dict[int, bpy.types.FCurve] = {}
    frames: set[float] = set()
    for fcurve in fcurves:
        index = path_to_index.get(fcurve.data_path)
        if index is None:
            continue
        fcurves_by_index[index] = fcurve
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))

    if len(frames) < 2:
        return None

    fps = float(context.scene.render.fps) / float(context.scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    times = array("f")
    values = array("f")
    for frame in sorted(frames):
        times.append(float(frame) / fps)
        for target_index in range(target_count):
            fcurve = fcurves_by_index.get(target_index)
            value = fcurve.evaluate(frame) if fcurve is not None else defaults[target_index]
            values.append(float(value))

    if not _float_samples_changed(values, target_count):
        return None

    interpolation = _action_interpolation(action, set(path_to_index), fcurves)
    return (
        times,
        values,
        len(times),
        target_count,
        interpolation,
    )
