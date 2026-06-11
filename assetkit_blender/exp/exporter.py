from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
from array import array
from pathlib import Path

import bpy
import mathutils

from ..assetkit import (
    AssetKitError,
    _native_module,
)
from ..enums import (
    AK_DAE_EXPORT_INDEX_AUTO,
    AK_DAE_EXPORT_INDEX_SINGLE,
    AK_DAE_EXPORT_VERSION_AUTO,
    AK_FILE_TYPE_DAE,
    AK_FILE_TYPE_GLB,
    AK_FILE_TYPE_GLTF,
    AK_INTERPOLATION_LINEAR,
    AK_INTERPOLATION_STEP,
    AK_LIGHT_TYPE_DIRECTIONAL,
    AK_LIGHT_TYPE_POINT,
    AK_LIGHT_TYPE_SPOT,
    AK_PRIMITIVE_LINES,
    AK_PRIMITIVE_POINTS,
    AKB_EXPORT_ITEM_CAMERA,
    AKB_EXPORT_ITEM_CURVE,
    AKB_EXPORT_ITEM_JOINT,
    AKB_EXPORT_ITEM_LIGHT,
    AKB_EXPORT_ITEM_MESH,
    AKB_EXPORT_ITEM_NODE,
    AK_OK,
    AK_PROJECTION_ORTHOGRAPHIC,
    AK_PROJECTION_PERSPECTIVE,
    AK_TARGET_POSITION,
    AK_TARGET_QUAT,
    AK_TARGET_SCALE,
    AK_TARGET_WEIGHTS,
    AKB_ANIM_VISIBILITY,
    AKB_LOAD_COORD_RAW,
    AKB_LOAD_COORD_TRANSFORM,
    AKB_LOAD_COORD_Y_UP,
    AKB_LOAD_COORD_Z_UP,
)
from .images import _ExportImageStore
from .materials import _material_tuple

EXPORT_FORMATS = (
    ("GLTF", "glTF", "Export .gltf with external .bin/resources", AK_FILE_TYPE_GLTF, ".gltf"),
    ("GLB", "GLB", "Export binary .glb", AK_FILE_TYPE_GLB, ".glb"),
    ("DAE", "COLLADA (.dae)", "Export COLLADA .dae", AK_FILE_TYPE_DAE, ".dae"),
)

_AKB_NATIVE_MESH_PAYLOAD = 0x414B4D46
_AKB_NATIVE_CURVE_PAYLOAD = 0x414B4356
_MESH_EXPORT_OBJECT_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

_TRANSFORM_ANIMATION_PATHS = {
    "location",
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
    "delta_location",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
    "delta_scale",
}

_LOCATION_ANIMATION_PATHS = {"location", "delta_location"}
_ROTATION_ANIMATION_PATHS = {
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "delta_rotation_euler",
    "delta_rotation_quaternion",
}
_SCALE_ANIMATION_PATHS = {"scale", "delta_scale"}
_VISIBILITY_ANIMATION_PATHS = {"hide_viewport", "hide_render"}
_BONE_TRANSFORM_PROPERTIES = {
    "location",
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
}
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


def export_scene(
    context: bpy.types.Context,
    filepath: str | os.PathLike[str],
    file_type: int,
    *,
    selected_only: bool = False,
    dae_version: int = AK_DAE_EXPORT_VERSION_AUTO,
    dae_index_mode: int = AK_DAE_EXPORT_INDEX_SINGLE,
    coordinate_system: int | None = None,
    coordinate_conversion: int | None = None,
) -> int:
    module = _native_module()
    if module is None:
        raise AssetKitError("AssetKit native Blender bridge is not available")

    path = Path(filepath)
    suffix = suffix_from_file_type(file_type)
    if path.suffix.lower() != suffix:
        path = path.with_suffix(suffix)

    profile = _profile_enabled()
    started_at = time.perf_counter() if profile else 0.0
    with tempfile.TemporaryDirectory(prefix="akb-export-images-") as image_tmp:
        image_store = _ExportImageStore(Path(image_tmp))
        material_cache: dict[tuple[int, tuple[str, ...]], tuple | None] = {}
        mesh_payload_cache: dict[tuple[int, tuple[int, ...]], tuple | None] = {}
        mesh_cleanup = []
        collect_started_at = time.perf_counter() if profile else 0.0
        items = _collect_scene_items(
            context,
            file_type=file_type,
            selected_only=selected_only,
            image_store=image_store,
            material_cache=material_cache,
            mesh_payload_cache=mesh_payload_cache,
            mesh_cleanup=mesh_cleanup,
        )
        if not items:
            raise AssetKitError("No exportable scene objects found")
        if profile:
            _profile_log(
                f"collect_scene_items items={len(items)} meshes_to_clear={len(mesh_cleanup)} "
                f"elapsed={(time.perf_counter() - collect_started_at) * 1000.0:.3f}ms"
            )

        try:
            native_started_at = time.perf_counter() if profile else 0.0
            doc_extra = _export_document_extra(context)
            export_coord_system = (
                AKB_LOAD_COORD_Z_UP
                if coordinate_system is None and file_type == AK_FILE_TYPE_DAE
                else AKB_LOAD_COORD_Y_UP
                if coordinate_system is None
                else int(coordinate_system)
            )
            export_coord_conversion = (
                AKB_LOAD_COORD_RAW
                if coordinate_conversion is None and file_type == AK_FILE_TYPE_DAE
                else AKB_LOAD_COORD_TRANSFORM
                if coordinate_conversion is None
                else int(coordinate_conversion)
            )
            result = int(module.export_scene(
                os.fspath(path.parent),
                int(file_type),
                path.name,
                items,
                doc_extra,
                int(dae_version),
                int(dae_index_mode),
                export_coord_system,
                export_coord_conversion,
                _assetkit_blender_authoring_tool(),
            ))
            if profile:
                _profile_log(
                    f"native_export elapsed={(time.perf_counter() - native_started_at) * 1000.0:.3f}ms"
                )
        finally:
            cleanup_started_at = time.perf_counter() if profile else 0.0
            for obj_eval in mesh_cleanup:
                obj_eval.to_mesh_clear()
            if profile:
                _profile_log(
                    f"mesh_cleanup count={len(mesh_cleanup)} "
                    f"elapsed={(time.perf_counter() - cleanup_started_at) * 1000.0:.3f}ms"
                )
    if result != AK_OK:
        raise AssetKitError(f"AssetKit export failed: result={result}")
    if profile:
        _profile_log(
            f"export_scene total={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return result


def _assetkit_blender_authoring_tool() -> str:
    root_name = __package__.split(".", 1)[0]
    root_mod = sys.modules.get(root_name)
    info = getattr(root_mod, "bl_info", {}) if root_mod is not None else {}
    version = info.get("version") if isinstance(info, dict) else None
    if isinstance(version, tuple) and version:
        return "AssetKit Blender v" + ".".join(str(part) for part in version)
    return "AssetKit Blender"


def _collect_scene_items(
    context: bpy.types.Context,
    *,
    file_type: int,
    selected_only: bool,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple[int, tuple[str, ...]], tuple | None],
    mesh_payload_cache: dict[tuple[int, tuple[int, ...]], tuple | None],
    mesh_cleanup: list,
) -> list[tuple]:
    profile = _profile_enabled()
    phase_started_at = time.perf_counter() if profile else 0.0
    depsgraph = context.evaluated_depsgraph_get()
    selected = set(context.selected_objects) if selected_only else None
    objects = list(context.scene.objects)
    exportable = {
        obj
        for obj in objects
        if not _is_assetkit_synthetic_helper_object(obj)
        and not obj.hide_get(view_layer=context.view_layer)
    }
    payload_kinds: dict[bpy.types.Object, int] = {}
    mesh_armatures: dict[bpy.types.Object, bpy.types.Object] = {}
    included: set[bpy.types.Object] = set()
    world_matrices = {}
    instancing_groups, instancing_skips = _assetkit_instancing_groups(
        objects,
        exportable,
        selected,
    )

    def include_export_chain(obj: bpy.types.Object) -> None:
        node = obj
        while node is not None and node in exportable:
            included.add(node)
            node = node.parent

    def include_skeleton_chain(obj: bpy.types.Object) -> None:
        node = obj
        while node is not None:
            included.add(node)
            node = node.parent

    for obj in objects:
        if obj not in exportable:
            continue
        if selected is not None and obj not in selected:
            continue
        if obj in instancing_skips:
            continue

        if obj.type == "CAMERA":
            payload_kinds[obj] = AKB_EXPORT_ITEM_CAMERA
            include_export_chain(obj)
        elif obj.type == "LIGHT":
            payload_kinds[obj] = AKB_EXPORT_ITEM_LIGHT
            include_export_chain(obj)
        elif file_type == AK_FILE_TYPE_DAE and _can_export_native_curve(obj):
            payload_kinds[obj] = AKB_EXPORT_ITEM_CURVE
            include_export_chain(obj)
        elif obj.type in _MESH_EXPORT_OBJECT_TYPES:
            payload_kinds[obj] = AKB_EXPORT_ITEM_MESH
            include_export_chain(obj)
            armature = _mesh_armature_object(obj) if obj.type == "MESH" else None
            if armature is not None:
                mesh_armatures[obj] = armature
                include_skeleton_chain(armature)
        elif obj.type == "EMPTY":
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

    animation_payloads = _collect_transform_animations(context, included)

    if profile:
        _profile_log(
            f"collect_object_anims count={len(animation_payloads)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

    bone_animation_payloads = _collect_bone_animations(context, needed_armatures)

    if profile:
        _profile_log(
            f"collect_bone_anims count={len(bone_animation_payloads)} elapsed={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )
        phase_started_at = time.perf_counter()

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
                _matrix_bytes(matrix),
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
            _matrix_bytes(matrix),
            parent_index,
            None,
            animation_payloads.get(obj),
            _assetkit_instancing_payload(obj, parent, world_matrices, instancing_groups),
            _assetkit_json_prop(obj, "assetkit_node_extra_json"),
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

            if skin_setup is not None:
                mesh_payload_started_at = time.perf_counter() if profile else 0.0
                payload = _mesh_payload(
                    context,
                    obj,
                    obj.data,
                    obj.data,
                    image_store,
                    material_cache,
                    skin_setup=skin_setup,
                )
                if profile:
                    mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
            else:
                shared_key = _shared_mesh_payload_key(obj)
                if shared_key is not None and shared_key in mesh_payload_cache:
                    payload = mesh_payload_cache[shared_key]
                elif shared_key is not None:
                    mesh_payload_started_at = time.perf_counter() if profile else 0.0
                    payload = _mesh_payload(
                        context,
                        obj,
                        obj.data,
                        obj.data,
                        image_store,
                        material_cache,
                        skin_setup=None,
                    )
                    if profile:
                        mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0
                    mesh_payload_cache[shared_key] = payload
                else:
                    obj_eval = obj.evaluated_get(depsgraph)
                    to_mesh_started_at = time.perf_counter() if profile else 0.0
                    mesh = obj_eval.to_mesh()
                    if profile:
                        to_mesh_ms += (time.perf_counter() - to_mesh_started_at) * 1000.0
                    if mesh is not None:
                        mesh_cleanup.append(obj_eval)
                        mesh_payload_started_at = time.perf_counter() if profile else 0.0
                        payload = _mesh_payload(
                            context,
                            obj,
                            mesh,
                            obj.data if obj.type == "MESH" else None,
                            image_store,
                            material_cache,
                            skin_setup=None,
                        )
                        if profile:
                            mesh_payload_ms += (time.perf_counter() - mesh_payload_started_at) * 1000.0

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


def _shared_mesh_payload_key(obj: bpy.types.Object) -> tuple[int, tuple[int, ...]] | None:
    mesh = obj.data if obj.type == "MESH" else None
    if mesh is None:
        return None
    if obj.modifiers:
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
) -> tuple[bytes, int] | None:
    members = instancing_groups.get(obj)
    if not members or len(members) <= 1:
        return None

    base = _local_matrix_for_export(obj, parent, world_matrices)
    base_inv = base.inverted_safe()
    values = array("f")
    for member in members:
        matrix = _local_matrix_for_export(member, parent, world_matrices)
        _append_matrix_values(values, base_inv @ matrix)
    return values.tobytes(), len(members)


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


def _collect_transform_animations(
    context: bpy.types.Context,
    objects: set[bpy.types.Object],
) -> dict[bpy.types.Object, tuple]:
    scene = context.scene
    frame = scene.frame_current
    subframe = scene.frame_subframe
    out: dict[bpy.types.Object, tuple] = {}
    changed_frame = False

    try:
        for obj in objects:
            payload, changed = _object_transform_animation(context, obj, objects)
            changed_frame = changed_frame or changed
            if payload:
                out[obj] = payload
    finally:
        if changed_frame:
            scene.frame_set(frame, subframe=subframe)

    return out


def _object_world_matrix(obj: bpy.types.Object, depsgraph) -> object:
    if getattr(obj, "constraints", None):
        return obj.evaluated_get(depsgraph).matrix_world.copy()
    return obj.matrix_world.copy()


def _collect_bone_animations(
    context: bpy.types.Context,
    armatures: set[bpy.types.Object],
) -> dict[tuple[bpy.types.Object, str], tuple]:
    scene = context.scene
    frame = scene.frame_current
    subframe = scene.frame_subframe
    out: dict[tuple[bpy.types.Object, str], tuple] = {}
    changed_frame = False

    try:
        for armature in armatures:
            animation_data = armature.animation_data
            action = animation_data.action if animation_data else None
            if action is None:
                continue
            fcurves = tuple(_iter_action_fcurves(action))
            if not fcurves:
                continue
            pose = getattr(armature, "pose", None)
            if pose is None:
                continue
            for pose_bone in getattr(pose, "bones", []) or []:
                payload, changed = _pose_bone_transform_animation(
                    context,
                    armature,
                    pose_bone.name,
                    action,
                    fcurves,
                )
                changed_frame = changed_frame or changed
                if payload:
                    out[(armature, pose_bone.name)] = payload
    finally:
        if changed_frame:
            scene.frame_set(frame, subframe=subframe)

    return out


def _object_transform_animation(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    included: set[bpy.types.Object],
) -> tuple[tuple | None, bool]:
    animation_data = obj.animation_data
    action = animation_data.action if animation_data else None
    if action is None:
        return None, False

    fcurves = tuple(_iter_action_fcurves(action))
    if not fcurves:
        return None, False

    visibility_channel = _object_visibility_animation_channel(context.scene, obj, fcurves)
    direct = _object_transform_animation_direct(context, obj, action, fcurves)
    if direct is not None:
        channels = list(direct)
        if visibility_channel:
            channels.append(visibility_channel)
        return (tuple(channels) if channels else None), False

    frames = _action_transform_keyframes(action)
    if len(frames) < 2:
        return ((visibility_channel,) if visibility_channel else None), False

    scene = context.scene
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    parent = obj.parent if obj.parent in included else None
    times = array("f")
    translations = array("f")
    rotations = array("f")
    scales = array("f")
    previous_quat: tuple[float, float, float, float] | None = None
    changed_frame = False

    for frame in frames:
        changed_frame = _set_scene_frame(scene, frame) or changed_frame
        depsgraph = context.evaluated_depsgraph_get()
        matrix = _evaluated_local_matrix(obj, parent, depsgraph)
        loc, rot, scale = matrix.decompose()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous_quat is not None and _quat_dot(previous_quat, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous_quat = quat

        times.append(float(frame) / fps)
        translations.extend((float(loc.x), float(loc.y), float(loc.z)))
        rotations.extend(quat)
        scales.extend((float(scale.x), float(scale.y), float(scale.z)))

    count = len(times)
    if count < 2:
        return None

    channels = []
    if _float_samples_changed(translations, 3):
        channels.append((
            AK_TARGET_POSITION,
            times.tobytes(),
            translations.tobytes(),
            count,
            _action_interpolation(action, _LOCATION_ANIMATION_PATHS),
        ))
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times.tobytes(),
            rotations.tobytes(),
            count,
            _action_interpolation(action, _ROTATION_ANIMATION_PATHS),
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times.tobytes(),
            scales.tobytes(),
            count,
            _action_interpolation(action, _SCALE_ANIMATION_PATHS),
        ))
    if visibility_channel:
        channels.append(visibility_channel)

    return (tuple(channels) if channels else None), changed_frame


def _pose_bone_transform_animation(
    context: bpy.types.Context,
    armature: bpy.types.Object,
    bone_name: str,
    action: bpy.types.Action,
    fcurves: tuple | None = None,
) -> tuple[tuple | None, bool]:
    paths = _pose_bone_paths(armature, bone_name)
    if not paths:
        return None, False

    pose = getattr(armature, "pose", None)
    pose_bone = pose.bones.get(bone_name) if pose else None
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action))
    direct = _pose_bone_transform_animation_direct(context, pose_bone, action, paths, fcurves)
    if direct is not None:
        return (direct if direct else None), False

    frames = _action_keyframes_for_paths(action, set(paths.values()))
    if len(frames) < 2:
        return None, False

    scene = context.scene
    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    times = array("f")
    translations = array("f")
    rotations = array("f")
    scales = array("f")
    previous_quat: tuple[float, float, float, float] | None = None
    changed_frame = False

    for frame in frames:
        changed_frame = _set_scene_frame(scene, frame) or changed_frame
        depsgraph = context.evaluated_depsgraph_get()
        armature_eval = armature.evaluated_get(depsgraph)
        pose_bone = armature_eval.pose.bones.get(bone_name) if armature_eval.pose else None
        if pose_bone is None:
            return None, changed_frame

        matrix = _pose_bone_local_matrix(pose_bone)
        loc, rot, scale = matrix.decompose()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous_quat is not None and _quat_dot(previous_quat, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous_quat = quat

        times.append(float(frame) / fps)
        translations.extend((float(loc.x), float(loc.y), float(loc.z)))
        rotations.extend(quat)
        scales.extend((float(scale.x), float(scale.y), float(scale.z)))

    count = len(times)
    if count < 2:
        return None

    channels = []
    if _float_samples_changed(translations, 3):
        channels.append((
            AK_TARGET_POSITION,
            times.tobytes(),
            translations.tobytes(),
            count,
            _action_interpolation(action, set(paths[prop] for prop in ("location",) if prop in paths)),
        ))
    rotation_paths = {
        paths[prop] for prop in ("rotation_axis_angle", "rotation_euler", "rotation_quaternion")
        if prop in paths
    }
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times.tobytes(),
            rotations.tobytes(),
            count,
            _action_interpolation(action, rotation_paths),
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times.tobytes(),
            scales.tobytes(),
            count,
            _action_interpolation(action, set(paths[prop] for prop in ("scale",) if prop in paths)),
        ))

    return (tuple(channels) if channels else None), changed_frame


def _object_transform_animation_direct(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    action: bpy.types.Action,
    fcurves: tuple | None = None,
) -> tuple | None:
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action))
    if not fcurves:
        return None
    if getattr(obj, "constraints", None):
        return None
    if any(fcurve.data_path in _TRANSFORM_ANIMATION_PATHS and fcurve.data_path.startswith("delta_")
           for fcurve in fcurves):
        return None

    paths = {
        "location": "location",
        "rotation_axis_angle": "rotation_axis_angle",
        "rotation_euler": "rotation_euler",
        "rotation_quaternion": "rotation_quaternion",
        "scale": "scale",
    }
    defaults = _object_transform_defaults(obj)
    return _transform_animation_direct(context.scene, action, fcurves, paths, defaults, getattr(obj, "rotation_mode", "XYZ"))


def _object_visibility_animation_channel(
    scene: bpy.types.Scene,
    obj: bpy.types.Object,
    fcurves: tuple,
) -> tuple | None:
    if _object_uses_parent_source_visibility(obj):
        return None

    viewport_curve = _scalar_fcurve_for_path(fcurves, "hide_viewport")
    render_curve = _scalar_fcurve_for_path(fcurves, "hide_render")
    if viewport_curve is None and render_curve is None:
        return None

    frames = _fcurve_keyframes([viewport_curve, render_curve])
    if len(frames) < 2:
        return None

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    extra_visible = _object_visibility_extra_value(obj)
    if extra_visible is not None:
        default_viewport = 0.0 if extra_visible else 1.0
        default_render = default_viewport
    else:
        default_viewport = 1.0 if bool(getattr(obj, "hide_viewport", False)) else 0.0
        default_render = 1.0 if bool(getattr(obj, "hide_render", False)) else 0.0
    times = array("f")
    values = array("B")
    for frame in frames:
        hidden_viewport = (
            float(viewport_curve.evaluate(frame)) if viewport_curve is not None else default_viewport
        ) >= 0.5
        hidden_render = (
            float(render_curve.evaluate(frame)) if render_curve is not None else default_render
        ) >= 0.5
        times.append(float(frame) / fps)
        values.append(0 if hidden_viewport or hidden_render else 1)

    if not _float_samples_changed(values, 1):
        return None

    return (
        AKB_ANIM_VISIBILITY,
        times.tobytes(),
        values.tobytes(),
        len(times),
        AK_INTERPOLATION_STEP,
    )


def _pose_bone_transform_animation_direct(
    context: bpy.types.Context,
    pose_bone,
    action: bpy.types.Action,
    paths: dict[str, str],
    fcurves: tuple | None = None,
) -> tuple | None:
    if pose_bone is None:
        return None
    if getattr(pose_bone, "constraints", None):
        return None
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action))
    if not fcurves:
        return None
    defaults = _pose_bone_transform_defaults(pose_bone)
    return _transform_animation_direct(context.scene, action, fcurves, paths, defaults, getattr(pose_bone, "rotation_mode", "XYZ"))


def _transform_animation_direct(
    scene: bpy.types.Scene,
    action: bpy.types.Action,
    fcurves: tuple,
    paths: dict[str, str],
    defaults: dict[str, tuple[float, ...]],
    rotation_mode: str,
) -> tuple | None:
    relevant_paths = {path for path in paths.values() if path}
    if not any(fcurve.data_path in relevant_paths for fcurve in fcurves):
        return None

    fps = float(scene.render.fps) / float(scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    channels = []
    location_path = paths.get("location")
    if location_path:
        channel = _direct_vec_channel(
            action,
            fcurves,
            location_path,
            defaults.get("location", (0.0, 0.0, 0.0)),
            3,
            fps,
            AK_TARGET_POSITION,
        )
        if channel:
            channels.append(channel)

    rotation_channel = _direct_rotation_channel(
        action,
        fcurves,
        paths,
        defaults,
        rotation_mode,
        fps,
    )
    if rotation_channel:
        channels.append(rotation_channel)

    scale_path = paths.get("scale")
    if scale_path:
        channel = _direct_vec_channel(
            action,
            fcurves,
            scale_path,
            defaults.get("scale", (1.0, 1.0, 1.0)),
            3,
            fps,
            AK_TARGET_SCALE,
        )
        if channel:
            channels.append(channel)

    return tuple(channels) if channels else ()


def _direct_vec_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, ...],
    width: int,
    fps: float,
    target: int,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, width)
    native = _native_aligned_anim_channel(target, tuple(curves), defaults, fps, 0)
    if native is not False:
        return native

    aligned = _aligned_keyframe_values(curves, defaults, width)
    if aligned is not None:
        frames, values = aligned
        if len(frames) < 2 or not _float_samples_changed(values, width):
            return None
        times = array("f", (float(frame) / fps for frame in frames))
        return (
            target,
            times.tobytes(),
            values.tobytes(),
            len(times),
            _curves_interpolation(curves),
        )

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    for frame in frames:
        times.append(float(frame) / fps)
        for component in range(width):
            curve = curves[component]
            values.append(float(curve.evaluate(frame)) if curve is not None else defaults[component])

    if not _float_samples_changed(values, width):
        return None

    return (
        target,
        times.tobytes(),
        values.tobytes(),
        len(times),
        _curves_interpolation(curves),
    )


def _direct_rotation_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    paths: dict[str, str],
    defaults: dict[str, tuple[float, ...]],
    rotation_mode: str,
    fps: float,
) -> tuple | None:
    quat_path = paths.get("rotation_quaternion")
    euler_path = paths.get("rotation_euler")
    axis_path = paths.get("rotation_axis_angle")

    if quat_path and any(curve.data_path == quat_path for curve in fcurves):
        return _direct_quat_channel(
            action,
            fcurves,
            quat_path,
            defaults.get("rotation_quaternion", (1.0, 0.0, 0.0, 0.0)),
            fps,
        )
    if euler_path and any(curve.data_path == euler_path for curve in fcurves):
        return _direct_euler_channel(
            action,
            fcurves,
            euler_path,
            defaults.get("rotation_euler", (0.0, 0.0, 0.0)),
            rotation_mode,
            fps,
        )
    if axis_path and any(curve.data_path == axis_path for curve in fcurves):
        return _direct_axis_angle_channel(
            action,
            fcurves,
            axis_path,
            defaults.get("rotation_axis_angle", (0.0, 0.0, 1.0, 0.0)),
            fps,
        )
    return None


def _direct_quat_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float, float],
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 4)
    native = _native_aligned_anim_channel(AK_TARGET_QUAT, tuple(curves), defaults, fps, 1)
    if native is not False:
        return native

    aligned = _aligned_keyframe_values(curves, defaults, 4)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        for index, frame in enumerate(frames):
            offset = index * 4
            quat = (
                raw_values[offset + 1],
                raw_values[offset + 2],
                raw_values[offset + 3],
                raw_values[offset],
            )
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    for frame in frames:
        raw = [
            float(curves[i].evaluate(frame)) if curves[i] is not None else defaults[i]
            for i in range(4)
        ]
        quat = (raw[1], raw[2], raw[3], raw[0])
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))


def _direct_euler_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float],
    rotation_mode: str,
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 3)
    aligned = _aligned_keyframe_values(curves, defaults, 3)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        order = rotation_mode if rotation_mode in {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"} else "XYZ"
        for index, frame in enumerate(frames):
            offset = index * 3
            euler = mathutils.Euler((
                raw_values[offset],
                raw_values[offset + 1],
                raw_values[offset + 2],
            ), order)
            rot = euler.to_quaternion()
            quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    order = rotation_mode if rotation_mode in {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"} else "XYZ"
    for frame in frames:
        euler = mathutils.Euler((
            float(curves[0].evaluate(frame)) if curves[0] is not None else defaults[0],
            float(curves[1].evaluate(frame)) if curves[1] is not None else defaults[1],
            float(curves[2].evaluate(frame)) if curves[2] is not None else defaults[2],
        ), order)
        rot = euler.to_quaternion()
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))


def _direct_axis_angle_channel(
    action: bpy.types.Action,
    fcurves: tuple,
    path: str,
    defaults: tuple[float, float, float, float],
    fps: float,
) -> tuple | None:
    curves = _fcurves_for_path(fcurves, path, 4)
    aligned = _aligned_keyframe_values(curves, defaults, 4)
    if aligned is not None:
        frames, raw_values = aligned
        if len(frames) < 2:
            return None
        times = array("f")
        values = array("f")
        previous: tuple[float, float, float, float] | None = None
        for index, frame in enumerate(frames):
            offset = index * 4
            angle = raw_values[offset]
            axis = mathutils.Vector((
                raw_values[offset + 1],
                raw_values[offset + 2],
                raw_values[offset + 3],
            ))
            if axis.length_squared <= 1.0e-12:
                axis = mathutils.Vector((0.0, 0.0, 1.0))
            rot = mathutils.Quaternion(axis.normalized(), angle)
            quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
            if previous is not None and _quat_dot(previous, quat) < 0.0:
                quat = (-quat[0], -quat[1], -quat[2], -quat[3])
            previous = quat
            times.append(float(frame) / fps)
            values.extend(quat)
        if not _float_samples_changed(values, 4):
            return None
        return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))

    frames = _fcurve_keyframes(curves)
    if len(frames) < 2:
        return None

    times = array("f")
    values = array("f")
    previous: tuple[float, float, float, float] | None = None
    for frame in frames:
        angle = float(curves[0].evaluate(frame)) if curves[0] is not None else defaults[0]
        axis = mathutils.Vector((
            float(curves[1].evaluate(frame)) if curves[1] is not None else defaults[1],
            float(curves[2].evaluate(frame)) if curves[2] is not None else defaults[2],
            float(curves[3].evaluate(frame)) if curves[3] is not None else defaults[3],
        ))
        if axis.length_squared <= 1.0e-12:
            axis = mathutils.Vector((0.0, 0.0, 1.0))
        rot = mathutils.Quaternion(axis.normalized(), angle)
        quat = (float(rot.x), float(rot.y), float(rot.z), float(rot.w))
        if previous is not None and _quat_dot(previous, quat) < 0.0:
            quat = (-quat[0], -quat[1], -quat[2], -quat[3])
        previous = quat
        times.append(float(frame) / fps)
        values.extend(quat)

    if not _float_samples_changed(values, 4):
        return None
    return (AK_TARGET_QUAT, times.tobytes(), values.tobytes(), len(times), _curves_interpolation(curves))


def _fcurves_for_path(fcurves: tuple, path: str, width: int) -> list:
    out = [None] * width
    for curve in fcurves:
        if curve.data_path == path and 0 <= curve.array_index < width:
            out[curve.array_index] = curve
    return out


def _scalar_fcurve_for_path(fcurves: tuple, path: str):
    for curve in fcurves:
        if curve.data_path == path:
            return curve
    return None


def _native_aligned_anim_channel(
    target: int,
    curves: tuple,
    defaults: tuple[float, ...],
    fps: float,
    mode: int,
):
    module = _native_module()
    if module is None:
        return False
    helper = getattr(module, "export_aligned_anim_channel", None)
    if helper is None:
        return False
    return helper(int(target), curves, defaults, float(fps), int(mode))


def _aligned_keyframe_values(
    curves: list,
    defaults: tuple[float, ...],
    width: int,
) -> tuple[tuple[float, ...], array] | None:
    co_arrays = [_fcurve_co_values(curve) if curve is not None else None for curve in curves]
    present = [co for co in co_arrays if co is not None]
    if not present:
        return None
    first = present[0]
    count = len(first) // 2
    if count < 2:
        return None
    frames = tuple(float(first[index * 2]) for index in range(count))
    values = array("f")
    for frame_index, frame in enumerate(frames):
        for component in range(width):
            co = co_arrays[component]
            if co is None:
                values.append(defaults[component])
                continue
            if len(co) != count * 2:
                return None
            if abs(float(co[frame_index * 2]) - frame) > 1.0e-6:
                return None
            values.append(float(co[frame_index * 2 + 1]))
    return frames, values


def _fcurve_co_values(curve) -> array | None:
    if curve is None:
        return None
    points = getattr(curve, "keyframe_points", None)
    if points is None:
        return None
    count = len(points)
    if count <= 0:
        return None
    values = array("f", [0.0]) * (count * 2)
    try:
        points.foreach_get("co", values)
    except Exception:
        for index, key in enumerate(points):
            values[index * 2] = float(key.co.x)
            values[index * 2 + 1] = float(key.co.y)
    return values


def _fcurve_keyframes(curves: list) -> tuple[float, ...]:
    frames: set[float] = set()
    for curve in curves:
        if curve is None:
            continue
        for key in curve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _curves_interpolation(curves: list) -> int:
    found = False
    for curve in curves:
        if curve is None:
            continue
        for key in curve.keyframe_points:
            found = True
            if key.interpolation != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _object_transform_defaults(obj: bpy.types.Object) -> dict[str, tuple[float, ...]]:
    return {
        "location": (float(obj.location.x), float(obj.location.y), float(obj.location.z)),
        "rotation_axis_angle": tuple(float(value) for value in obj.rotation_axis_angle),
        "rotation_euler": (float(obj.rotation_euler.x), float(obj.rotation_euler.y), float(obj.rotation_euler.z)),
        "rotation_quaternion": tuple(float(value) for value in obj.rotation_quaternion),
        "scale": (float(obj.scale.x), float(obj.scale.y), float(obj.scale.z)),
    }


def _pose_bone_transform_defaults(pose_bone) -> dict[str, tuple[float, ...]]:
    return {
        "location": (float(pose_bone.location.x), float(pose_bone.location.y), float(pose_bone.location.z)),
        "rotation_axis_angle": tuple(float(value) for value in pose_bone.rotation_axis_angle),
        "rotation_euler": (float(pose_bone.rotation_euler.x), float(pose_bone.rotation_euler.y), float(pose_bone.rotation_euler.z)),
        "rotation_quaternion": tuple(float(value) for value in pose_bone.rotation_quaternion),
        "scale": (float(pose_bone.scale.x), float(pose_bone.scale.y), float(pose_bone.scale.z)),
    }


def _action_transform_keyframes(action: bpy.types.Action) -> tuple[float, ...]:
    frames: set[float] = set()
    for fcurve in _iter_action_fcurves(action):
        if fcurve.data_path not in _TRANSFORM_ANIMATION_PATHS:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _action_keyframes_for_paths(action: bpy.types.Action, paths: set[str]) -> tuple[float, ...]:
    frames: set[float] = set()
    if not paths:
        return ()
    for fcurve in _iter_action_fcurves(action):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _action_interpolation(action: bpy.types.Action, paths: set[str]) -> int:
    if not paths:
        return AK_INTERPOLATION_LINEAR
    found = False
    for fcurve in _iter_action_fcurves(action):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            found = True
            if key.interpolation != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _iter_action_fcurves(action: bpy.types.Action):
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None and len(fcurves) > 0:
        yield from fcurves
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except Exception:
                    channelbag = None
                if channelbag is not None:
                    yield from getattr(channelbag, "fcurves", []) or []


def _pose_bone_paths(armature: bpy.types.Object, bone_name: str) -> dict[str, str]:
    pose = getattr(armature, "pose", None)
    pose_bone = pose.bones.get(bone_name) if pose else None
    if pose_bone is None:
        return {}

    out: dict[str, str] = {}
    for prop in _BONE_TRANSFORM_PROPERTIES:
        try:
            out[prop] = pose_bone.path_from_id(prop)
        except Exception:
            pass
    return out


def _pose_bone_local_matrix(pose_bone):
    if pose_bone.parent is not None:
        return pose_bone.parent.matrix.inverted_safe() @ pose_bone.matrix
    return pose_bone.matrix.copy()


def _set_scene_frame(scene: bpy.types.Scene, frame: float) -> bool:
    base = math.floor(frame)
    subframe = float(frame - base)
    if scene.frame_current == int(base) and abs(scene.frame_subframe - subframe) <= 1.0e-6:
        return False
    scene.frame_set(int(base), subframe=subframe)
    return True


def _evaluated_local_matrix(
    obj: bpy.types.Object,
    parent: bpy.types.Object | None,
    depsgraph: bpy.types.Depsgraph,
):
    matrix = obj.evaluated_get(depsgraph).matrix_world.copy()
    if parent is not None:
        matrix = parent.evaluated_get(depsgraph).matrix_world.inverted_safe() @ matrix
    return matrix


def _quat_dot(a: tuple[float, float, float, float],
              b: tuple[float, float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


def _float_samples_changed(values: array, width: int) -> bool:
    if width <= 0 or len(values) <= width:
        return False
    first = values[:width]
    for index in range(width, len(values), width):
        for component in range(width):
            if abs(values[index + component] - first[component]) > 1.0e-6:
                return True
    return False


def _mesh_armature_object(obj: bpy.types.Object) -> bpy.types.Object | None:
    for modifier in getattr(obj, "modifiers", []) or []:
        if modifier.type != "ARMATURE":
            continue
        armature = getattr(modifier, "object", None)
        if armature is not None and armature.type == "ARMATURE":
            return armature
    return None


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
    armature_world = armature.matrix_world
    for bone in joint_bones:
        _append_matrix_values(
            inverse_bind_matrices,
            (armature_world @ bone.matrix_local).inverted_safe(),
        )

    return (
        tuple(group_to_joint),
        joint_node_indices,
        inverse_bind_matrices.tobytes(),
        armature_index,
    )


def _mesh_payload(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    source_mesh: bpy.types.Mesh | None,
    image_store: "_ExportImageStore",
    material_cache: dict[tuple[int, tuple[str, ...]], tuple | None],
    *,
    skin_setup: tuple | None = None,
) -> tuple | None:
    profile = _profile_enabled()
    phase_started_at = time.perf_counter() if profile else 0.0
    uv_layers = _uv_layers(mesh)
    uv_names = tuple(layer.name for layer in uv_layers)
    uv_slot_by_name = {name: index for index, name in enumerate(uv_names)}
    color_layers = _color_attributes(mesh)
    layer_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile else 0.0
    phase_started_at = time.perf_counter() if profile else 0.0
    fps = float(context.scene.render.fps) / float(context.scene.render.fps_base or 1.0)
    if fps <= 0.0:
        fps = 24.0

    morph_targets = _shape_key_targets(mesh, source_mesh)
    morph_animation = _shape_key_weight_animation(
        context,
        source_mesh,
        morph_targets,
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
        variant_payload=_material_variant_payload(obj),
        skin_setup=skin_setup,
        morph_targets=morph_targets,
        morph_animation=morph_animation,
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
    material_cache: dict[tuple[int, tuple[str, ...]], tuple | None],
    uv_slot_by_name: dict[str, int],
    uv_names: tuple[str, ...],
    fps: float,
    *,
    variant_payload: tuple | None = None,
    skin_setup: tuple | None = None,
    morph_targets: list | None = None,
    morph_animation: tuple | None = None,
):
    material_payloads = tuple(
        _cached_material_tuple(
            _material_for_index(obj, mesh, index),
            image_store,
            material_cache,
            uv_slot_by_name,
            uv_names,
            fps,
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
        _assetkit_json_prop(obj, "assetkit_mesh_extra_json"),
        _assetkit_json_prop(obj, "assetkit_geometry_extra_json"),
        _assetkit_json_prop(obj, "assetkit_primitive_extra_json"),
        _mesh_primitive_type_for_export(obj, mesh),
        _mesh_primitive_mode_for_export(obj, mesh),
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
    material_cache: dict[tuple[int, tuple[str, ...]], tuple | None],
    uv_slot_by_name: dict[str, int],
    uv_names: tuple[str, ...],
    fps: float,
) -> tuple | None:
    if material is None:
        return None
    key = (int(material.as_pointer()), uv_names)
    cached = material_cache.get(key)
    if cached is not None or key in material_cache:
        return cached
    cached = _material_tuple(material, image_store, uv_slot_by_name, fps)
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
        color.tobytes(),
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
    for fcurve in _iter_action_fcurves(action):
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

    interpolation = _action_interpolation(action, set(path_to_index))
    return (
        times.tobytes(),
        values.tobytes(),
        len(times),
        target_count,
        interpolation,
    )


def _append_matrix_values(values: array, matrix) -> None:
    for col in range(4):
        for row in range(4):
            values.append(float(matrix[row][col]))


def _matrix_bytes(matrix) -> bytes:
    values = array("f")
    _append_matrix_values(values, matrix)
    return values.tobytes()


def _object_visible_for_export(obj: bpy.types.Object) -> bool:
    return not _object_hidden_for_visibility_export(obj)


def _object_hidden_for_visibility_export(obj: bpy.types.Object) -> bool:
    if _object_uses_parent_source_visibility(obj):
        return False
    visible = _object_visibility_extra_value(obj)
    if visible is not None:
        return not visible
    if _object_has_ancestor_source_visibility(obj):
        return False
    if bool(obj.get("assetkit_helper_hidden", False)):
        return False
    return bool(getattr(obj, "hide_viewport", False) or getattr(obj, "hide_render", False))


def _object_visibility_extra_value(obj: bpy.types.Object) -> bool | None:
    extra = _assetkit_json_prop(obj, "assetkit_node_extra_json")
    visible = _assetkit_extra_path(extra, "extensions", "KHR_node_visibility", "visible")
    if not isinstance(visible, dict):
        return None
    value = visible.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return None


def _object_uses_parent_source_visibility(obj: bpy.types.Object) -> bool:
    parent = getattr(obj, "parent", None)
    if parent is None:
        return False
    if "assetkit_node_index" not in obj:
        return False
    if not bool(parent.get("assetkit_helper_object", False)):
        return False
    if _object_visibility_extra_value(parent) is not None:
        return True
    animation_data = parent.animation_data
    action = animation_data.action if animation_data else None
    return action is not None and _action_has_visibility_animation(action)


def _object_has_ancestor_source_visibility(obj: bpy.types.Object) -> bool:
    if "assetkit_node_index" not in obj and not bool(obj.get("assetkit_helper_object", False)):
        return False
    parent = getattr(obj, "parent", None)
    while parent is not None:
        if _object_visibility_extra_value(parent) is not None:
            return True
        animation_data = parent.animation_data
        action = animation_data.action if animation_data else None
        if action is not None and _action_has_visibility_animation(action):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _action_has_visibility_animation(action: bpy.types.Action) -> bool:
    for fcurve in _iter_action_fcurves(action):
        if fcurve.data_path in _VISIBILITY_ANIMATION_PATHS:
            return True
    return False


def _is_assetkit_synthetic_helper_object(obj: bpy.types.Object) -> bool:
    if not bool(obj.get("assetkit_helper_object", False)):
        return False
    if obj.name not in {"AssetKit Coordinates", "AssetKitNode"}:
        return False
    if _assetkit_json_prop(obj, "assetkit_node_extra_json") is not None:
        return False
    animation_data = obj.animation_data
    if animation_data and animation_data.action:
        return False
    return True


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
