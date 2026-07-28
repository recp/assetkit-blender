from __future__ import annotations

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
    AKB_EXPORT_ITEM_CAMERA,
    AKB_EXPORT_ITEM_CURVE,
    AKB_EXPORT_ITEM_JOINT,
    AKB_EXPORT_ITEM_LIGHT,
    AKB_EXPORT_ITEM_MESH,
    AKB_EXPORT_ITEM_NODE,
)

from .animation.transform import (
    _ANIMATION_TIMING_CLIP,
    _collect_bone_animations,
    _collect_transform_animations,
    _mesh_armature_object,
    _normalize_scene_animation_payload_times,
    _object_world_matrix,
    _set_scene_frame,
)
from .common import (
    _append_matrix_values,
    _assetkit_json_prop,
    _matrix_values,
    _profile_enabled,
    _profile_log,
)
from .images import _ExportImageStore
from .materials import _material_bake_required
from .mesh import (
    _camera_payload,
    _light_payload,
    _material_for_index,
    _material_variant_payload,
    _mesh_payload,
    _mesh_skin_setup,
)
from .visibility import (
    _is_assetkit_synthetic_helper_object,
    _object_visible_for_export,
)

_AKB_NATIVE_CURVE_PAYLOAD = 0x414B4356
_MESH_EXPORT_OBJECT_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
_ANIMATED_SCENE_FORMATS = frozenset((AK_FILE_TYPE_GLTF, AK_FILE_TYPE_GLB, AK_FILE_TYPE_DAE))
_STATIC_SCENE_MESH_FORMATS = frozenset(
    (AK_FILE_TYPE_3MF, AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY, AK_FILE_TYPE_WAVEFRONT)
)
_NATIVE_STATIC_MESH_PAYLOAD_FORMATS = frozenset((AK_FILE_TYPE_3MF, AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY))
_NO_MATERIAL_FORMATS = frozenset((AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY))
_NO_UV_COLOR_FORMATS = frozenset((AK_FILE_TYPE_3MF, AK_FILE_TYPE_STL))
_STATIC_SCALE_FORMATS = frozenset((AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY, AK_FILE_TYPE_WAVEFRONT))
_RAW_Z_UP_FORMATS = frozenset(
    (AK_FILE_TYPE_3MF, AK_FILE_TYPE_DAE, AK_FILE_TYPE_PLY, AK_FILE_TYPE_STL, AK_FILE_TYPE_WAVEFRONT)
)


def _collect_scene_items(
    context: bpy.types.Context,
    *,
    file_type: int,
    selected_only: bool,
    object_filter: set[bpy.types.Object] | None,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple, tuple | None],
    mesh_payload_cache: dict[tuple[int, tuple[int, ...]], tuple | None],
    mesh_cleanup: list,
    material_export_mode: str,
    material_bake_size: int,
    lighting_bake_mode: str,
    export_visible: bool,
    export_renderable: bool,
    export_cameras: bool,
    export_lights: bool,
    export_custom_properties: bool,
    export_uv: bool,
    export_normals: bool,
    export_tangents: bool,
    export_vertex_colors: bool,
    export_attributes: bool,
    export_materials: bool,
    export_images: bool,
    export_animations: bool,
    export_skins: bool,
    export_shape_keys: bool,
    export_shape_key_normals: bool,
    export_shape_key_tangents: bool,
    export_shape_key_animations: bool,
    animation_bake_mode: str,
    animation_timing: str,
    apply_modifiers: bool,
    ply_export_normals: bool,
    ply_export_uv: bool,
    ply_export_colors: bool,
    ply_export_triangulated: bool,
) -> list[tuple]:
    profile = _profile_enabled()
    static_mesh_export = file_type in _STATIC_SCENE_MESH_FORMATS
    phase_started_at = time.perf_counter() if profile else 0.0
    depsgraph = context.evaluated_depsgraph_get()
    selected = set(context.selected_objects) if selected_only else None
    objects = list(context.scene.objects)
    exportable = {
        obj
        for obj in objects
        if not _is_assetkit_synthetic_helper_object(obj)
        and (not export_visible or not obj.hide_get(view_layer=context.view_layer))
        and (not export_renderable or not bool(getattr(obj, "hide_render", False)))
    }
    if static_mesh_export:
        return _collect_static_mesh_scene_items(
            context,
            depsgraph,
            objects,
            exportable,
            selected,
            object_filter,
            file_type,
            image_store,
            material_cache,
            mesh_payload_cache,
            mesh_cleanup,
            material_export_mode,
            material_bake_size,
            lighting_bake_mode,
            export_uv,
            export_normals,
            export_tangents,
            export_vertex_colors,
            export_attributes,
            export_materials,
            export_images,
            False,
            False,
            False,
            False,
            export_custom_properties,
            apply_modifiers,
            ply_export_normals,
            ply_export_uv,
            ply_export_colors,
            ply_export_triangulated,
            profile,
            phase_started_at,
        )
    payload_kinds: dict[bpy.types.Object, int] = {}
    mesh_armatures: dict[bpy.types.Object, bpy.types.Object] = {}
    included: set[bpy.types.Object] = set()
    world_matrices = {}
    if object_filter is None:
        instancing_groups, instancing_skips = _assetkit_instancing_groups(
            objects,
            exportable,
            selected,
        )
    else:
        instancing_groups, instancing_skips = {}, set()

    def include_export_chain(obj: bpy.types.Object) -> None:
        node = obj
        while node is not None and node in exportable:
            included.add(node)
            node = node.parent

    def include_skeleton_chain(obj: bpy.types.Object) -> None:
        node = obj
        while node is not None and not _is_assetkit_synthetic_helper_object(node):
            included.add(node)
            node = node.parent

    for obj in objects:
        if obj not in exportable:
            continue
        if object_filter is not None and obj not in object_filter:
            continue
        if selected is not None and obj not in selected:
            continue
        if obj in instancing_skips:
            continue

        if not static_mesh_export and export_cameras and obj.type == "CAMERA":
            payload_kinds[obj] = AKB_EXPORT_ITEM_CAMERA
            include_export_chain(obj)
        elif not static_mesh_export and export_lights and obj.type == "LIGHT":
            payload_kinds[obj] = AKB_EXPORT_ITEM_LIGHT
            include_export_chain(obj)
        elif file_type == AK_FILE_TYPE_DAE and _can_export_native_curve(obj):
            payload_kinds[obj] = AKB_EXPORT_ITEM_CURVE
            include_export_chain(obj)
        elif _object_type_exports_as_mesh(obj, file_type):
            payload_kinds[obj] = AKB_EXPORT_ITEM_MESH
            include_export_chain(obj)
            armature = (
                _mesh_armature_object(obj)
                if export_skins and not static_mesh_export and obj.type == "MESH"
                else None
            )
            if armature is not None:
                mesh_armatures[obj] = armature
                include_skeleton_chain(armature)
        elif not static_mesh_export and obj.type == "EMPTY":
            payload_kinds[obj] = AKB_EXPORT_ITEM_NODE
            include_export_chain(obj)

    if not payload_kinds:
        return []

    if profile:
        _profile_log(
            f"collect_scan objects={len(objects)} exportable={len(payload_kinds)} "
            f"included={len(included)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    for obj in included:
        world_matrices[obj] = _object_world_matrix(obj, depsgraph)
    for members in instancing_groups.values():
        for obj in members:
            if obj not in world_matrices:
                world_matrices[obj] = _object_world_matrix(obj, depsgraph)

    if profile:
        _profile_log(
            f"collect_world_matrices nodes={len(included)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    children: dict[bpy.types.Object | None, list[bpy.types.Object]] = {None: []}
    for obj in included:
        parent = obj.parent if obj.parent in included else None
        children.setdefault(parent, []).append(obj)
        children.setdefault(obj, [])

    order = {obj: index for index, obj in enumerate(objects)}
    for child_list in children.values():
        child_list.sort(key=lambda obj: order.get(obj, 0))

    out: list[list] = []
    object_indices: dict[bpy.types.Object, int] = {}
    bone_indices: dict[tuple[bpy.types.Object, str], int] = {}
    needed_armatures = set(mesh_armatures.values())

    if profile:
        _profile_log(
            f"collect_children roots={len(children.get(None, ()))} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    animation_payloads = (
        {}
        if static_mesh_export or not export_animations
        else _collect_transform_animations(context, included)
    )

    if profile:
        _profile_log(
            f"collect_object_anims count={len(animation_payloads)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    bone_animation_payloads = (
        {}
        if static_mesh_export or not export_animations
        else _collect_bone_animations(context, needed_armatures)
    )

    if profile:
        _profile_log(
            f"collect_bone_anims count={len(bone_animation_payloads)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    if animation_timing == _ANIMATION_TIMING_CLIP:
        animation_payloads, bone_animation_payloads = _normalize_scene_animation_payload_times(
            animation_payloads,
            bone_animation_payloads,
        )

    def append_bone_nodes(armature_obj: bpy.types.Object, parent_index: int) -> None:
        armature = armature_obj.data
        bones = list(getattr(armature, "bones", []) or [])
        if not bones:
            return

        bone_order = {bone.name: index for index, bone in enumerate(bones)}

        def sorted_bones(seq) -> list:
            return sorted(seq, key=lambda bone: bone_order.get(bone.name, 0))

        def append_bone(bone, parent_item_index: int) -> None:
            if bone.parent is not None:
                matrix = bone.parent.matrix_local.inverted_safe() @ bone.matrix_local
            else:
                matrix = bone.matrix_local

            index = len(out)
            bone_indices[(armature_obj, bone.name)] = index
            out.append([
                AKB_EXPORT_ITEM_JOINT,
                bone.name,
                _matrix_values(matrix),
                parent_item_index,
                None,
                bone_animation_payloads.get((armature_obj, bone.name)),
            ])
            for child in sorted_bones(getattr(bone, "children", []) or []):
                append_bone(child, index)

        roots = [bone for bone in bones if bone.parent is None]
        for root in sorted_bones(roots):
            append_bone(root, parent_index)

    def append_node(obj: bpy.types.Object, parent_index: int) -> None:
        kind = payload_kinds.get(obj, AKB_EXPORT_ITEM_NODE)
        parent = obj.parent if obj.parent in included else None
        matrix = _local_matrix_for_export(obj, parent, world_matrices)
        index = len(out)
        object_indices[obj] = index
        out.append([
            kind,
            obj.name,
            _matrix_values(matrix),
            parent_index,
            None,
            animation_payloads.get(obj),
            _assetkit_instancing_payload(obj, parent, world_matrices, instancing_groups),
            _assetkit_json_prop(obj, "assetkit_node_extra_json") if export_custom_properties else None,
            _object_visible_for_export(obj),
        ])
        if obj.type == "ARMATURE" and obj in needed_armatures:
            append_bone_nodes(obj, index)
        for child in children.get(obj, ()):
            append_node(child, index)

    for root in children.get(None, ()):
        append_node(root, -1)

    if profile:
        _profile_log(
            f"collect_node_items items={len(out)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    payload_count = 0
    to_mesh_ms = 0.0
    mesh_payload_ms = 0.0
    skin_setup_ms = 0.0
    for obj, kind in payload_kinds.items():
        item_index = object_indices.get(obj)
        if item_index is None:
            continue

        payload = None
        if kind == AKB_EXPORT_ITEM_CAMERA:
            payload = _camera_payload(context, obj)
        elif kind == AKB_EXPORT_ITEM_LIGHT:
            payload = _light_payload(obj)
        elif kind == AKB_EXPORT_ITEM_CURVE:
            payload = _curve_payload(obj)
        elif kind == AKB_EXPORT_ITEM_MESH:
            armature = mesh_armatures.get(obj)
            skin_setup_started_at = time.perf_counter() if profile else 0.0
            skin_setup = _mesh_skin_setup(
                obj,
                armature,
                object_indices,
                bone_indices,
            ) if armature is not None else None
            if profile and armature is not None:
                skin_setup_ms += (time.perf_counter() - skin_setup_started_at) * 1000.0

            obj_animation_bake_mode = _object_animation_bake_mode(
                obj,
                animation_bake_mode,
                skin_setup,
            )
            if skin_setup is not None:
                mesh_payload_started_at = time.perf_counter() if profile else 0.0
                payload = _mesh_payload(
                    context,
                    obj,
                    obj.data,
                    obj.data,
                    file_type,
                    image_store,
                    material_cache,
                    material_export_mode,
                    material_bake_size,
                    lighting_bake_mode,
                    skin_setup=skin_setup,
                    export_uv=export_uv,
                    export_normals=export_normals,
                    export_tangents=export_tangents,
                    export_vertex_colors=export_vertex_colors,
                    export_attributes=export_attributes,
                    export_materials=export_materials,
                    export_images=export_images,
                    export_shape_keys=export_shape_keys,
                    export_shape_key_normals=export_shape_key_normals,
                    export_shape_key_tangents=export_shape_key_tangents,
                    export_shape_key_animations=export_shape_key_animations and export_animations,
                    animation_bake_mode=obj_animation_bake_mode,
                    export_custom_properties=export_custom_properties,
                    ply_export_normals=ply_export_normals,
                    ply_export_uv=ply_export_uv,
                    ply_export_colors=ply_export_colors,
                    ply_export_triangulated=ply_export_triangulated,
                )
                if profile:
                    mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
            else:
                shared_key = (
                    None
                    if (
                        _mesh_material_bake_required(obj, material_export_mode)
                        or lighting_bake_mode == "FINAL"
                        or obj_animation_bake_mode == "EVALUATED_MESH"
                        or (static_mesh_export and _static_mesh_requires_evaluated_mesh(obj, apply_modifiers))
                    )
                    else _shared_mesh_payload_key(
                        obj,
                        ignore_modifiers=not apply_modifiers,
                    )
                )
                if shared_key is not None and shared_key in mesh_payload_cache:
                    payload = mesh_payload_cache[shared_key]
                elif shared_key is not None:
                    mesh_payload_started_at = time.perf_counter() if profile else 0.0
                    payload = _mesh_payload(
                        context,
                        obj,
                        obj.data,
                        obj.data,
                        file_type,
                        image_store,
                        material_cache,
                        material_export_mode,
                        material_bake_size,
                        lighting_bake_mode,
                        skin_setup=None,
                        export_uv=export_uv,
                        export_normals=export_normals,
                        export_tangents=export_tangents,
                        export_vertex_colors=export_vertex_colors,
                        export_attributes=export_attributes,
                        export_materials=export_materials,
                        export_images=export_images,
                        export_shape_keys=export_shape_keys,
                        export_shape_key_normals=export_shape_key_normals,
                        export_shape_key_tangents=export_shape_key_tangents,
                        export_shape_key_animations=export_shape_key_animations and export_animations,
                        animation_bake_mode=obj_animation_bake_mode,
                        export_custom_properties=export_custom_properties,
                        ply_export_normals=ply_export_normals,
                        ply_export_uv=ply_export_uv,
                        ply_export_colors=ply_export_colors,
                        ply_export_triangulated=ply_export_triangulated,
                    )
                    if profile:
                        mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
                    mesh_payload_cache[shared_key] = payload
                else:
                    scene = context.scene
                    saved_frame = scene.frame_current
                    saved_subframe = scene.frame_subframe
                    eval_depsgraph = depsgraph
                    if obj_animation_bake_mode == "EVALUATED_MESH":
                        _set_scene_frame(scene, float(scene.frame_start))
                        eval_depsgraph = context.evaluated_depsgraph_get()
                    try:
                        obj_eval = obj.evaluated_get(eval_depsgraph)
                        to_mesh_started_at = time.perf_counter() if profile else 0.0
                        if obj_animation_bake_mode == "EVALUATED_MESH":
                            mesh = bpy.data.meshes.new_from_object(obj_eval, depsgraph=eval_depsgraph)
                        else:
                            mesh = obj_eval.to_mesh()
                        if profile:
                            to_mesh_ms += (time.perf_counter() - to_mesh_started_at) * 1000.0
                        if mesh is not None:
                            if obj_animation_bake_mode == "EVALUATED_MESH":
                                mesh_cleanup.append(("mesh", mesh))
                            else:
                                mesh_cleanup.append(obj_eval)
                            mesh_payload_started_at = time.perf_counter() if profile else 0.0
                            payload = _mesh_payload(
                                context,
                                obj,
                                mesh,
                                obj.data if obj.type == "MESH" else None,
                                file_type,
                                image_store,
                                material_cache,
                                material_export_mode,
                                material_bake_size,
                                lighting_bake_mode,
                                skin_setup=None,
                                export_uv=export_uv,
                                export_normals=export_normals,
                                export_tangents=export_tangents,
                                export_vertex_colors=export_vertex_colors,
                                export_attributes=export_attributes,
                                export_materials=export_materials,
                                export_images=export_images,
                                export_shape_keys=export_shape_keys,
                                export_shape_key_normals=export_shape_key_normals,
                                export_shape_key_tangents=export_shape_key_tangents,
                                export_shape_key_animations=export_shape_key_animations and export_animations,
                                animation_bake_mode=obj_animation_bake_mode,
                                export_custom_properties=export_custom_properties,
                                ply_export_normals=ply_export_normals,
                                ply_export_uv=ply_export_uv,
                                ply_export_colors=ply_export_colors,
                                ply_export_triangulated=ply_export_triangulated,
                            )
                            if profile:
                                mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
                    finally:
                        if obj_animation_bake_mode == "EVALUATED_MESH":
                            scene.frame_set(saved_frame, subframe=saved_subframe)

        if payload is None:
            out[item_index][0] = AKB_EXPORT_ITEM_NODE
            continue

        out[item_index][4] = payload
        payload_count += 1

    if not out:
        return []

    if profile:
        _profile_log(
            f"collect_payloads payloads={payload_count} to_mesh={to_mesh_ms:.3f}ms "
            f"skin_setup={skin_setup_ms:.3f}ms "
            f"mesh_payload={mesh_payload_ms:.3f}ms "
            f"elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )

    return [tuple(item) for item in out]


def _collect_static_mesh_scene_items(
    context: bpy.types.Context,
    depsgraph,
    objects: list[bpy.types.Object],
    exportable: set[bpy.types.Object],
    selected: set[bpy.types.Object] | None,
    object_filter: set[bpy.types.Object] | None,
    file_type: int,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple, tuple | None],
    mesh_payload_cache: dict[tuple[int, tuple[int, ...]], tuple | None],
    mesh_cleanup: list,
    material_export_mode: str,
    material_bake_size: int,
    lighting_bake_mode: str,
    export_uv: bool,
    export_normals: bool,
    export_tangents: bool,
    export_vertex_colors: bool,
    export_attributes: bool,
    export_materials: bool,
    export_images: bool,
    export_shape_keys: bool,
    export_shape_key_normals: bool,
    export_shape_key_tangents: bool,
    export_shape_key_animations: bool,
    export_custom_properties: bool,
    apply_modifiers: bool,
    ply_export_normals: bool,
    ply_export_uv: bool,
    ply_export_colors: bool,
    ply_export_triangulated: bool,
    profile: bool,
    started_at: float,
) -> list[tuple]:
    out: list[tuple] = []
    mesh_payload_ms = 0.0
    to_mesh_ms = 0.0
    candidate_count = 0

    for obj in objects:
        if obj not in exportable:
            continue
        if object_filter is not None and obj not in object_filter:
            continue
        if selected is not None and obj not in selected:
            continue
        if not _object_type_exports_as_mesh(obj, file_type):
            continue

        candidate_count += 1
        payload = None
        source_mesh = obj.data if obj.type == "MESH" else None
        shared_key = (
            None
            if (
                _mesh_material_bake_required(obj, material_export_mode)
                or lighting_bake_mode == "FINAL"
                or _static_mesh_requires_evaluated_mesh(obj, apply_modifiers)
            )
            else _shared_mesh_payload_key(
                obj,
                ignore_modifiers=not apply_modifiers,
            )
        )

        if shared_key is not None and shared_key in mesh_payload_cache:
            payload = mesh_payload_cache[shared_key]
        else:
            mesh = source_mesh
            obj_eval = None
            if shared_key is None:
                obj_eval = obj.evaluated_get(depsgraph)
                to_mesh_started_at = time.perf_counter() if profile else 0.0
                mesh = obj_eval.to_mesh()
                if profile:
                    to_mesh_ms += (time.perf_counter() - to_mesh_started_at) * 1000.0
                if mesh is not None:
                    mesh_cleanup.append(obj_eval)

            if mesh is not None:
                mesh_payload_started_at = time.perf_counter() if profile else 0.0
                payload = _mesh_payload(
                    context,
                    obj,
                    mesh,
                    source_mesh,
                    file_type,
                    image_store,
                    material_cache,
                    material_export_mode,
                    material_bake_size,
                    lighting_bake_mode,
                    skin_setup=None,
                    export_uv=export_uv,
                    export_normals=export_normals,
                    export_tangents=export_tangents,
                    export_vertex_colors=export_vertex_colors,
                    export_attributes=export_attributes,
                    export_materials=export_materials,
                    export_images=export_images,
                    export_shape_keys=export_shape_keys,
                    export_shape_key_normals=export_shape_key_normals,
                    export_shape_key_tangents=export_shape_key_tangents,
                    export_shape_key_animations=export_shape_key_animations,
                    export_custom_properties=export_custom_properties,
                    ply_export_normals=ply_export_normals,
                    ply_export_uv=ply_export_uv,
                    ply_export_colors=ply_export_colors,
                    ply_export_triangulated=ply_export_triangulated,
                )
                if profile:
                    mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
            if shared_key is not None:
                mesh_payload_cache[shared_key] = payload

        if payload is None:
            continue

        out.append((
            AKB_EXPORT_ITEM_MESH,
            obj.name,
            _matrix_values(_object_world_matrix(obj, depsgraph)),
            -1,
            payload,
            None,
        ))

    if profile:
        _profile_log(
            f"collect_static_mesh candidates={candidate_count} items={len(out)} "
            f"to_mesh={to_mesh_ms:.3f}ms mesh_payload={mesh_payload_ms:.3f}ms "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )

    return out


def _can_export_native_curve(obj: bpy.types.Object) -> bool:
    if obj.type != "CURVE":
        return False

    curve = getattr(obj, "data", None)
    splines = getattr(curve, "splines", None)
    if curve is None or splines is None or len(splines) != 1:
        return False

    spline = splines[0]
    spline_type = getattr(spline, "type", "")
    if spline_type not in {"POLY", "NURBS"}:
        return False

    points = getattr(spline, "points", None)
    point_count = len(points) if points is not None else 0
    if point_count <= 1:
        return False

    if abs(float(getattr(curve, "bevel_depth", 0.0) or 0.0)) > 0.0:
        return False
    if abs(float(getattr(curve, "extrude", 0.0) or 0.0)) > 0.0:
        return False
    if getattr(curve, "bevel_object", None) is not None:
        return False
    if getattr(curve, "taper_object", None) is not None:
        return False
    if getattr(curve, "dimensions", "3D") == "2D" and getattr(curve, "fill_mode", "NONE") != "NONE":
        return False

    if spline_type == "NURBS":
        try:
            order = int(getattr(spline, "order_u", 0) or 0)
        except (TypeError, ValueError):
            return False
        if order <= 1 or order > point_count:
            return False

    return True


def _object_type_exports_as_mesh(obj: bpy.types.Object, file_type: int) -> bool:
    if file_type in {AK_FILE_TYPE_STL, AK_FILE_TYPE_PLY}:
        return obj.type == "MESH"
    return obj.type in _MESH_EXPORT_OBJECT_TYPES


def _curve_payload(obj: bpy.types.Object) -> tuple | None:
    curve = getattr(obj, "data", None)
    if curve is None:
        return None
    return (
        _AKB_NATIVE_CURVE_PAYLOAD,
        curve,
        _assetkit_json_prop(obj, "assetkit_geometry_extra_json"),
        _assetkit_json_prop(obj, "assetkit_curve_extra_json"),
    )


def _assetkit_instancing_groups(
    objects: list[bpy.types.Object],
    visible: set[bpy.types.Object],
    selected: set[bpy.types.Object] | None,
) -> tuple[dict[bpy.types.Object, tuple[bpy.types.Object, ...]], set[bpy.types.Object]]:
    groups: dict[tuple[object, int, int], list[bpy.types.Object]] = {}

    for obj in objects:
        if obj.type != "MESH" or obj not in visible:
            continue
        if selected is not None and obj not in selected:
            continue
        data = getattr(obj, "data", None)
        if data is None:
            continue
        count = _assetkit_int_prop(obj, "assetkit_instance_count", 0)
        index = _assetkit_int_prop(obj, "assetkit_instance_index", -1)
        if count <= 1 or index < 0 or index >= count:
            continue
        if getattr(obj, "animation_data", None) and obj.animation_data.action is not None:
            continue
        parent = obj.parent
        group = str(obj.get("assetkit_instance_group", "") or "")
        if group:
            key = (group, int(parent.as_pointer()) if parent else 0, int(count))
        else:
            key = (int(data.as_pointer()), int(parent.as_pointer()) if parent else 0, int(count))
        groups.setdefault(key, []).append(obj)

    reps: dict[bpy.types.Object, tuple[bpy.types.Object, ...]] = {}
    skips: set[bpy.types.Object] = set()
    for members in groups.values():
        count = _assetkit_int_prop(members[0], "assetkit_instance_count", 0)
        if len(members) != count:
            continue
        by_index: dict[int, bpy.types.Object] = {}
        valid = True
        for obj in members:
            index = _assetkit_int_prop(obj, "assetkit_instance_index", -1)
            if index in by_index:
                valid = False
                break
            by_index[index] = obj
        if not valid or sorted(by_index) != list(range(count)):
            continue

        rep = by_index[0]
        ordered = tuple(by_index[index] for index in range(count))
        reps[rep] = ordered
        skips.update(ordered[1:])

    return reps, skips


def _shared_mesh_payload_key(
    obj: bpy.types.Object,
    *,
    ignore_modifiers: bool = False,
) -> tuple[int, tuple[int, ...]] | None:
    mesh = obj.data if obj.type == "MESH" else None
    if mesh is None:
        return None
    if obj.modifiers and not ignore_modifiers:
        return None
    if _material_variant_payload(obj) is not None:
        return None
    if (
        _assetkit_json_prop(obj, "assetkit_mesh_extra_json") is not None
        or _assetkit_json_prop(obj, "assetkit_geometry_extra_json") is not None
        or _assetkit_json_prop(obj, "assetkit_primitive_extra_json") is not None
    ):
        return None

    slot_count = max(len(mesh.materials), len(getattr(obj, "material_slots", ()) or ()))
    materials = tuple(
        int(material.as_pointer()) if material is not None else 0
        for material in (_material_for_index(obj, mesh, index) for index in range(slot_count))
    )
    return int(mesh.as_pointer()), materials


def _static_mesh_requires_evaluated_mesh(obj: bpy.types.Object, apply_modifiers: bool) -> bool:
    if not apply_modifiers and obj.type == "MESH":
        return False
    if obj.type != "MESH":
        return True
    if getattr(obj, "modifiers", None):
        return True

    mesh = obj.data
    shape_keys = getattr(mesh, "shape_keys", None)
    key_blocks = getattr(shape_keys, "key_blocks", None)
    if key_blocks is None or len(key_blocks) <= 1:
        return False

    for key in key_blocks[1:]:
        try:
            if abs(float(getattr(key, "value", 0.0))) > 1.0e-6:
                return True
        except (TypeError, ValueError):
            return True
    return False


def _object_animation_bake_mode(
    obj: bpy.types.Object,
    animation_bake_mode: str,
    skin_setup: tuple | None,
) -> str:
    if animation_bake_mode != "EVALUATED_MESH" or skin_setup is not None or obj.type != "MESH":
        return "OFF"
    mesh = getattr(obj, "data", None)
    if mesh is None:
        return "OFF"
    if getattr(obj, "modifiers", None):
        return "EVALUATED_MESH"
    mesh_anim = getattr(mesh, "animation_data", None)
    if mesh_anim is not None and mesh_anim.action is not None:
        return "EVALUATED_MESH"
    shape_keys = getattr(mesh, "shape_keys", None)
    key_anim = getattr(shape_keys, "animation_data", None) if shape_keys is not None else None
    if key_anim is not None and key_anim.action is not None:
        return "EVALUATED_MESH"
    return "OFF"


def _mesh_material_bake_required(obj: bpy.types.Object, material_export_mode: str) -> bool:
    if material_export_mode in {"DIRECT", "NONE"}:
        return False
    mesh = obj.data if obj.type == "MESH" else None
    if mesh is None:
        return False
    slot_count = max(len(mesh.materials), len(getattr(obj, "material_slots", ()) or ()))
    for index in range(slot_count):
        if _material_bake_required(_material_for_index(obj, mesh, index), material_export_mode):
            return True
    return False


def _assetkit_int_prop(obj: bpy.types.Object, key: str, default: int) -> int:
    try:
        return int(obj.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def _local_matrix_for_export(
    obj: bpy.types.Object,
    parent: bpy.types.Object | None,
    world_matrices: dict[bpy.types.Object, object],
):
    matrix = world_matrices[obj]
    if parent is not None:
        matrix = world_matrices[parent].inverted_safe() @ matrix
    return matrix


def _assetkit_instancing_payload(
    obj: bpy.types.Object,
    parent: bpy.types.Object | None,
    world_matrices: dict[bpy.types.Object, object],
    instancing_groups: dict[bpy.types.Object, tuple[bpy.types.Object, ...]],
) -> tuple[array, int] | None:
    members = instancing_groups.get(obj)
    if not members or len(members) <= 1:
        return None

    base = _local_matrix_for_export(obj, parent, world_matrices)
    base_inv = base.inverted_safe()
    values = array("f")
    for member in members:
        matrix = _local_matrix_for_export(member, parent, world_matrices)
        _append_matrix_values(values, base_inv @ matrix)
    return values, len(members)
