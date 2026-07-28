from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from pathlib import Path

import bpy

from ..assetkit import AssetKitError, _native_module
from ..enums import (
    AK_DAE_EXPORT_INDEX_SINGLE,
    AK_DAE_EXPORT_VERSION_AUTO,
    AK_GLTF_EXPORT_VERSION_AUTO,
    AK_FILE_TYPE_3MF,
    AK_FILE_TYPE_DAE,
    AK_FILE_TYPE_GLB,
    AK_FILE_TYPE_GLTF,
    AK_FILE_TYPE_PLY,
    AK_FILE_TYPE_STL,
    AK_FILE_TYPE_WAVEFRONT,
    AK_PLY_EXPORT_ASCII,
    AK_PLY_EXPORT_BINARY_LITTLE,
    AK_PLY_EXPORT_COLOR_LINEAR,
    AK_PLY_EXPORT_COLOR_NONE,
    AK_PLY_EXPORT_COLOR_SRGB,
    AK_STL_EXPORT_ASCII,
    AK_STL_EXPORT_BINARY,
    AK_OK,
    AKB_LOAD_COORD_RAW,
    AKB_LOAD_COORD_TRANSFORM,
    AKB_LOAD_COORD_Y_UP,
    AKB_LOAD_COORD_Z_UP,
)

from .common import (
    _export_document_extra,
    _profile_enabled,
    _profile_log,
    suffix_from_file_type,
)
from .images import _ExportImageStore
from .scene import _collect_scene_items
from .visibility import _is_assetkit_synthetic_helper_object

_AKB_NATIVE_MESH_PAYLOAD = 0x414B4D46
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
_ANIMATION_TIMING_SCENE = "SCENE"
_ANIMATION_TIMING_CLIP = "CLIP"

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
_ANIMATION_FRAME_EPSILON = 1.0e-4
_BONE_PROP_LOCATION = 0
_BONE_PROP_ROTATION_AXIS_ANGLE = 1
_BONE_PROP_ROTATION_EULER = 2
_BONE_PROP_ROTATION_QUATERNION = 3
_BONE_PROP_SCALE = 4
_BONE_ROTATION_PATH_INDICES = (
    _BONE_PROP_ROTATION_AXIS_ANGLE,
    _BONE_PROP_ROTATION_EULER,
    _BONE_PROP_ROTATION_QUATERNION,
)
_BONE_TRANSFORM_PROPERTIES = (
    "location",
    "rotation_axis_angle",
    "rotation_euler",
    "rotation_quaternion",
    "scale",
)
_POSE_PLAN_NAME = 0
_POSE_PLAN_PATHS = 1
_POSE_PLAN_FRAMES = 2
_POSE_PLAN_LOC_CURVES = 3
_POSE_PLAN_QUAT_CURVES = 4
_POSE_PLAN_SCALE_CURVES = 5
_POSE_PLAN_LOC_DEFAULTS = 6
_POSE_PLAN_QUAT_DEFAULTS = 7
_POSE_PLAN_SCALE_DEFAULTS = 8
_POSE_PLAN_LOC_INTERP = 9
_POSE_PLAN_ROT_INTERP = 10
_POSE_PLAN_SCALE_INTERP = 11
_POSE_PLAN_REST_MATRIX = 12
_POSE_PLAN_TIMES = 13
_POSE_PLAN_TRANSLATIONS = 14
_POSE_PLAN_ROTATIONS = 15
_POSE_PLAN_SCALES = 16
_POSE_PLAN_PREVIOUS_QUAT = 17
_POSE_PLAN_VALID = 18


def export_scene(
    context: bpy.types.Context,
    filepath: str | os.PathLike[str],
    file_type: int,
    *,
    selected_only: bool = False,
    gltf_version: int = AK_GLTF_EXPORT_VERSION_AUTO,
    dae_version: int = AK_DAE_EXPORT_VERSION_AUTO,
    dae_index_mode: int = AK_DAE_EXPORT_INDEX_SINGLE,
    coordinate_system: int | None = None,
    coordinate_conversion: int | None = None,
    material_export_mode: str = "AUTO",
    material_bake_size: int = 1024,
    lighting_bake_mode: str = "OFF",
    export_visible: bool = True,
    export_renderable: bool = True,
    export_cameras: bool = True,
    export_lights: bool = True,
    export_custom_properties: bool = True,
    export_uv: bool = True,
    export_normals: bool = True,
    export_tangents: bool = True,
    export_vertex_colors: bool = True,
    export_attributes: bool = True,
    export_materials: bool = True,
    export_images: bool = True,
    export_animations: bool = True,
    export_skins: bool = True,
    export_shape_keys: bool = True,
    export_shape_key_normals: bool = True,
    export_shape_key_tangents: bool = True,
    export_shape_key_animations: bool = True,
    animation_bake_mode: str = "OFF",
    animation_timing: str = _ANIMATION_TIMING_CLIP,
    apply_modifiers: bool | None = None,
    global_scale: float | None = None,
    use_scene_unit: bool | None = None,
    forward_axis: str | None = None,
    up_axis: str | None = None,
    stl_format: str = "BINARY",
    stl_batch_mode: bool = False,
    stl_global_scale: float | None = None,
    stl_use_scene_unit: bool | None = None,
    stl_forward_axis: str | None = None,
    stl_up_axis: str | None = None,
    stl_apply_modifiers: bool | None = None,
    ply_format: str = "BINARY",
    ply_apply_modifiers: bool | None = None,
    ply_global_scale: float | None = None,
    ply_use_scene_unit: bool | None = None,
    ply_forward_axis: str | None = None,
    ply_up_axis: str | None = None,
    ply_export_uv: bool = True,
    ply_export_normals: bool = True,
    ply_export_colors: str = "SRGB",
    ply_export_triangulated_mesh: bool = False,
    three_mf_compression_level: int = 1,
) -> int:
    module = _native_module()
    if module is None:
        raise AssetKitError("AssetKit native Blender bridge is not available")

    path = Path(filepath)
    suffix = suffix_from_file_type(file_type)
    if path.suffix.lower() != suffix:
        path = path.with_suffix(suffix)
    material_export_mode = _material_export_mode_id(material_export_mode)
    lighting_bake_mode = _lighting_bake_mode_id(lighting_bake_mode)
    animation_bake_mode = _animation_bake_mode_id(animation_bake_mode)
    animation_timing = _animation_timing_id(animation_timing)
    if file_type in _NO_MATERIAL_FORMATS or not export_materials:
        material_export_mode = "NONE"
        lighting_bake_mode = "OFF"
    elif file_type == AK_FILE_TYPE_3MF:
        lighting_bake_mode = "OFF"
    elif not export_images:
        material_export_mode = "DIRECT"
        lighting_bake_mode = "OFF"
    if (
        file_type not in _ANIMATED_SCENE_FORMATS
        or not export_animations
        or not export_shape_keys
        or not export_shape_key_animations
    ):
        animation_bake_mode = "OFF"
    material_bake_size = _material_bake_size(material_bake_size)
    stl_export_format = _stl_export_format_id(stl_format)
    mesh_apply_modifiers = _resolve_apply_modifiers(
        file_type,
        apply_modifiers,
        stl_apply_modifiers,
        ply_apply_modifiers,
    )
    stl_scale_value = _resolve_format_float(global_scale, stl_global_scale, 1.0)
    stl_scene_unit = _resolve_format_bool(use_scene_unit, stl_use_scene_unit, False)
    stl_forward = _resolve_format_text(forward_axis, stl_forward_axis, "Y")
    stl_up = _resolve_format_text(up_axis, stl_up_axis, "Z")
    stl_scale = _static_mesh_effective_scale(
        context,
        file_type,
        stl_scale_value,
        stl_scene_unit,
    )
    ply_export_format = _ply_export_format_id(ply_format)
    ply_color_mode = _ply_export_color_mode_id(ply_export_colors)
    three_mf_compression_level = max(0, min(12, int(three_mf_compression_level)))
    ply_scale_value = _resolve_format_float(global_scale, ply_global_scale, 1.0)
    ply_scene_unit = _resolve_format_bool(use_scene_unit, ply_use_scene_unit, False)
    ply_forward = _resolve_format_text(forward_axis, ply_forward_axis, "Y")
    ply_up = _resolve_format_text(up_axis, ply_up_axis, "Z")
    ply_scale = _static_mesh_effective_scale(
        context,
        file_type,
        ply_scale_value,
        ply_scene_unit,
    )

    if file_type == AK_FILE_TYPE_STL and stl_batch_mode:
        return _export_stl_batch_scene(
            module,
            context,
            path,
            selected_only=selected_only,
            gltf_version=gltf_version,
            dae_version=dae_version,
            dae_index_mode=dae_index_mode,
            coordinate_system=coordinate_system,
            coordinate_conversion=coordinate_conversion,
            material_export_mode=material_export_mode,
            material_bake_size=material_bake_size,
            lighting_bake_mode=lighting_bake_mode,
            export_visible=bool(export_visible),
            export_renderable=bool(export_renderable),
            export_cameras=bool(export_cameras),
            export_lights=bool(export_lights),
            export_custom_properties=bool(export_custom_properties),
            export_uv=bool(export_uv),
            export_normals=bool(export_normals),
            export_tangents=bool(export_tangents),
            export_vertex_colors=bool(export_vertex_colors),
            export_attributes=bool(export_attributes),
            export_materials=bool(export_materials),
            export_images=bool(export_images),
            export_animations=bool(export_animations),
            export_skins=bool(export_skins),
            export_shape_keys=bool(export_shape_keys),
            export_shape_key_normals=bool(export_shape_key_normals),
            export_shape_key_tangents=bool(export_shape_key_tangents),
            export_shape_key_animations=bool(export_shape_key_animations),
            animation_timing=animation_timing,
            stl_export_format=stl_export_format,
            stl_scale=stl_scale,
            stl_forward_axis=stl_forward,
            stl_up_axis=stl_up,
            ply_export_format=AK_PLY_EXPORT_BINARY_LITTLE,
            ply_export_normals=False,
            ply_export_uv=False,
            ply_export_color_mode=AK_PLY_EXPORT_COLOR_NONE,
            ply_export_triangulated=False,
            apply_modifiers=bool(mesh_apply_modifiers),
        )

    static_scale = ply_scale if file_type == AK_FILE_TYPE_PLY else stl_scale
    static_forward_axis = ply_forward if file_type == AK_FILE_TYPE_PLY else stl_forward
    static_up_axis = ply_up if file_type == AK_FILE_TYPE_PLY else stl_up

    return _export_scene_once(
        module,
        context,
        path,
        file_type,
        selected_only=selected_only,
        object_filter=None,
        gltf_version=gltf_version,
        dae_version=dae_version,
        dae_index_mode=dae_index_mode,
        coordinate_system=coordinate_system,
        coordinate_conversion=coordinate_conversion,
        material_export_mode=material_export_mode,
        material_bake_size=material_bake_size,
        lighting_bake_mode=lighting_bake_mode,
        export_visible=bool(export_visible),
        export_renderable=bool(export_renderable),
        export_cameras=bool(export_cameras),
        export_lights=bool(export_lights),
        export_custom_properties=bool(export_custom_properties),
        export_uv=bool(export_uv),
        export_normals=bool(export_normals),
        export_tangents=bool(export_tangents),
        export_vertex_colors=bool(export_vertex_colors),
        export_attributes=bool(export_attributes),
        export_materials=bool(export_materials),
        export_images=bool(export_images),
        export_animations=bool(export_animations),
        export_skins=bool(export_skins),
        export_shape_keys=bool(export_shape_keys),
        export_shape_key_normals=bool(export_shape_key_normals),
        export_shape_key_tangents=bool(export_shape_key_tangents),
        export_shape_key_animations=bool(export_shape_key_animations),
        animation_bake_mode=animation_bake_mode,
        animation_timing=animation_timing,
        stl_export_format=stl_export_format,
        stl_scale=static_scale,
        stl_forward_axis=static_forward_axis,
        stl_up_axis=static_up_axis,
        ply_export_format=ply_export_format,
        ply_export_normals=bool(ply_export_normals) and bool(export_normals),
        ply_export_uv=bool(ply_export_uv) and bool(export_uv),
        ply_export_color_mode=ply_color_mode if export_vertex_colors else AK_PLY_EXPORT_COLOR_NONE,
        ply_export_triangulated=bool(ply_export_triangulated_mesh),
        three_mf_compression_level=three_mf_compression_level,
        apply_modifiers=bool(mesh_apply_modifiers),
    )


def _export_scene_once(
    module,
    context: bpy.types.Context,
    path: Path,
    file_type: int,
    *,
    selected_only: bool,
    object_filter: set[bpy.types.Object] | None,
    gltf_version: int,
    dae_version: int,
    dae_index_mode: int,
    coordinate_system: int | None,
    coordinate_conversion: int | None,
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
    stl_export_format: int,
    stl_scale: float,
    stl_forward_axis: str,
    stl_up_axis: str,
    ply_export_format: int,
    ply_export_normals: bool,
    ply_export_uv: bool,
    ply_export_color_mode: int,
    ply_export_triangulated: bool,
    three_mf_compression_level: int,
    apply_modifiers: bool,
) -> int:

    profile = _profile_enabled()
    started_at = time.perf_counter() if profile else 0.0
    with tempfile.TemporaryDirectory(prefix="akb-export-images-") as image_tmp:
        image_store = _ExportImageStore(Path(image_tmp))
        material_cache: dict[tuple, tuple | None] = {}
        mesh_payload_cache: dict[tuple[int, tuple[int, ...]], tuple | None] = {}
        mesh_cleanup = []
        collect_started_at = time.perf_counter() if profile else 0.0
        items = _collect_scene_items(
            context,
            file_type=file_type,
            selected_only=selected_only,
            object_filter=object_filter,
            image_store=image_store,
            material_cache=material_cache,
            mesh_payload_cache=mesh_payload_cache,
            mesh_cleanup=mesh_cleanup,
            material_export_mode=material_export_mode,
            material_bake_size=material_bake_size,
            lighting_bake_mode=lighting_bake_mode,
            export_visible=export_visible,
            export_renderable=export_renderable,
            export_cameras=export_cameras,
            export_lights=export_lights,
            export_custom_properties=export_custom_properties,
            export_uv=export_uv,
            export_normals=export_normals,
            export_tangents=export_tangents,
            export_vertex_colors=export_vertex_colors,
            export_attributes=export_attributes,
            export_materials=export_materials,
            export_images=export_images,
            export_animations=export_animations,
            export_skins=export_skins,
            export_shape_keys=export_shape_keys,
            export_shape_key_normals=export_shape_key_normals,
            export_shape_key_tangents=export_shape_key_tangents,
            export_shape_key_animations=export_shape_key_animations,
            animation_bake_mode=animation_bake_mode,
            animation_timing=animation_timing,
            apply_modifiers=apply_modifiers,
            ply_export_normals=bool(ply_export_normals),
            ply_export_uv=bool(ply_export_uv),
            ply_export_colors=ply_export_color_mode != AK_PLY_EXPORT_COLOR_NONE,
            ply_export_triangulated=bool(ply_export_triangulated),
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
            doc_extra = _export_document_extra(context) if export_custom_properties else None
            export_coord_system = (
                AKB_LOAD_COORD_Z_UP
                if coordinate_system is None and file_type in _RAW_Z_UP_FORMATS
                else AKB_LOAD_COORD_Y_UP
                if coordinate_system is None
                else int(coordinate_system)
            )
            export_coord_conversion = (
                AKB_LOAD_COORD_RAW
                if coordinate_conversion is None and file_type in _RAW_Z_UP_FORMATS
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
                int(gltf_version),
                int(dae_version),
                int(dae_index_mode),
                export_coord_system,
                export_coord_conversion,
                stl_export_format,
                int(ply_export_format),
                int(bool(ply_export_normals)),
                int(bool(ply_export_uv)),
                int(ply_export_color_mode),
                int(bool(ply_export_triangulated)),
                int(three_mf_compression_level),
                _assetkit_blender_authoring_tool(),
                float(stl_scale),
                str(stl_forward_axis or "Y"),
                str(stl_up_axis or "Z"),
            ))
            if profile:
                _profile_log(
                    f"native_export elapsed={(time.perf_counter() - native_started_at) * 1000.0:.3f}ms"
                )
        finally:
            cleanup_started_at = time.perf_counter() if profile else 0.0
            for cleanup_item in mesh_cleanup:
                if isinstance(cleanup_item, tuple) and cleanup_item and cleanup_item[0] == "mesh":
                    bpy.data.meshes.remove(cleanup_item[1])
                else:
                    cleanup_item.to_mesh_clear()
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


def _export_stl_batch_scene(
    module,
    context: bpy.types.Context,
    path: Path,
    *,
    selected_only: bool,
    gltf_version: int,
    dae_version: int,
    dae_index_mode: int,
    coordinate_system: int | None,
    coordinate_conversion: int | None,
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
    animation_timing: str,
    stl_export_format: int,
    stl_scale: float,
    stl_forward_axis: str,
    stl_up_axis: str,
    ply_export_format: int,
    ply_export_normals: bool,
    ply_export_uv: bool,
    ply_export_color_mode: int,
    ply_export_triangulated: bool,
    apply_modifiers: bool,
) -> int:
    objects = _stl_batch_objects(context, selected_only)
    if not objects:
        raise AssetKitError("No exportable scene objects found")

    used: set[str] = set()
    for obj in objects:
        batch_path = _stl_batch_path(path, obj.name, used)
        _export_scene_once(
            module,
            context,
            batch_path,
            AK_FILE_TYPE_STL,
            selected_only=False,
            object_filter={obj},
            gltf_version=gltf_version,
            dae_version=dae_version,
            dae_index_mode=dae_index_mode,
            coordinate_system=coordinate_system,
            coordinate_conversion=coordinate_conversion,
            material_export_mode=material_export_mode,
            material_bake_size=material_bake_size,
            lighting_bake_mode=lighting_bake_mode,
            export_visible=export_visible,
            export_renderable=export_renderable,
            export_cameras=export_cameras,
            export_lights=export_lights,
            export_custom_properties=export_custom_properties,
            export_uv=export_uv,
            export_normals=export_normals,
            export_tangents=export_tangents,
            export_vertex_colors=export_vertex_colors,
            export_attributes=export_attributes,
            export_materials=export_materials,
            export_images=export_images,
            export_animations=export_animations,
            export_skins=export_skins,
            export_shape_keys=export_shape_keys,
            export_shape_key_normals=export_shape_key_normals,
            export_shape_key_tangents=export_shape_key_tangents,
            export_shape_key_animations=export_shape_key_animations,
            animation_bake_mode="OFF",
            animation_timing=animation_timing,
            stl_export_format=stl_export_format,
            stl_scale=stl_scale,
            stl_forward_axis=stl_forward_axis,
            stl_up_axis=stl_up_axis,
            ply_export_format=ply_export_format,
            ply_export_normals=ply_export_normals,
            ply_export_uv=ply_export_uv,
            ply_export_color_mode=ply_export_color_mode,
            ply_export_triangulated=ply_export_triangulated,
            three_mf_compression_level=1,
            apply_modifiers=apply_modifiers,
        )
    return AK_OK


def _assetkit_blender_authoring_tool() -> str:
    root_name = __package__[:-4] if __package__.endswith(".exp") else __package__
    root_mod = sys.modules.get(root_name)
    version_text = getattr(root_mod, "__version__", "") if root_mod is not None else ""
    if version_text:
        return f"AssetKit Blender v{version_text}"
    info = getattr(root_mod, "bl_info", {}) if root_mod is not None else {}
    version = info.get("version") if isinstance(info, dict) else None
    if isinstance(version, tuple) and version:
        return "AssetKit Blender v" + ".".join(str(part) for part in version)
    return "AssetKit Blender"


def _material_export_mode_id(value: str | None) -> str:
    mode = (value or "AUTO").upper()
    if mode not in {"DIRECT", "AUTO", "BAKE", "NONE"}:
        return "AUTO"
    return mode


def _lighting_bake_mode_id(value: str | None) -> str:
    mode = (value or "OFF").upper()
    if mode in {"FINAL", "FINAL_COLOR", "ON", "TRUE"}:
        return "FINAL"
    return "OFF"


def _animation_bake_mode_id(value: str | None) -> str:
    mode = (value or "OFF").upper()
    if mode in {"EVALUATED_MESH", "MESH", "GEOMETRY_NODES", "GN"}:
        return "EVALUATED_MESH"
    return "OFF"


def _animation_timing_id(value: str | None) -> str:
    mode = (value or _ANIMATION_TIMING_CLIP).upper()
    if mode in {"SCENE", "TIMELINE", "GLOBAL"}:
        return _ANIMATION_TIMING_SCENE
    return _ANIMATION_TIMING_CLIP


def _stl_export_format_id(value: str | None) -> int:
    if value == "ASCII":
        return AK_STL_EXPORT_ASCII
    return AK_STL_EXPORT_BINARY


def _ply_export_format_id(value: str | None) -> int:
    if value == "ASCII":
        return AK_PLY_EXPORT_ASCII
    return AK_PLY_EXPORT_BINARY_LITTLE


def _ply_export_color_mode_id(value: str | None) -> int:
    mode = (value or "SRGB").upper()
    if mode == "NONE":
        return AK_PLY_EXPORT_COLOR_NONE
    if mode == "LINEAR":
        return AK_PLY_EXPORT_COLOR_LINEAR
    return AK_PLY_EXPORT_COLOR_SRGB


def _resolve_apply_modifiers(
    file_type: int,
    value: bool | None,
    stl_value: bool | None,
    ply_value: bool | None,
) -> bool:
    if value is not None:
        return bool(value)
    if file_type == AK_FILE_TYPE_STL and stl_value is not None:
        return bool(stl_value)
    if file_type == AK_FILE_TYPE_PLY and ply_value is not None:
        return bool(ply_value)
    return file_type in _STATIC_SCENE_MESH_FORMATS


def _resolve_format_bool(value: bool | None, legacy_value: bool | None, default: bool) -> bool:
    if value is not None:
        return bool(value)
    if legacy_value is not None:
        return bool(legacy_value)
    return bool(default)


def _resolve_format_float(value: float | None, legacy_value: float | None, default: float) -> float:
    if value is not None:
        return value
    if legacy_value is not None:
        return legacy_value
    return default


def _resolve_format_text(value: str | None, legacy_value: str | None, default: str) -> str:
    if value:
        return str(value)
    if legacy_value:
        return str(legacy_value)
    return default


def _static_mesh_effective_scale(
    context: bpy.types.Context,
    file_type: int,
    global_scale: float,
    use_scene_unit: bool,
) -> float:
    if file_type not in _STATIC_SCALE_FORMATS:
        return 1.0

    try:
        scale = float(global_scale)
    except (TypeError, ValueError):
        scale = 1.0
    if not math.isfinite(scale) or scale <= 0.0:
        scale = 1.0

    if use_scene_unit:
        unit_settings = getattr(getattr(context, "scene", None), "unit_settings", None)
        try:
            unit_scale = float(getattr(unit_settings, "scale_length", 1.0) or 1.0)
        except (TypeError, ValueError):
            unit_scale = 1.0
        if math.isfinite(unit_scale) and unit_scale > 0.0:
            scale *= unit_scale

    return scale


def _stl_batch_objects(context: bpy.types.Context, selected_only: bool) -> list[bpy.types.Object]:
    selected = set(context.selected_objects) if selected_only else None
    objects: list[bpy.types.Object] = []
    for obj in context.scene.objects:
        if obj.type != "MESH":
            continue
        if _is_assetkit_synthetic_helper_object(obj):
            continue
        if obj.hide_get(view_layer=context.view_layer):
            continue
        if selected is not None and obj not in selected:
            continue
        objects.append(obj)
    return objects


def _stl_batch_path(path: Path, object_name: str, used: set[str]) -> Path:
    safe_name = _safe_filename_fragment(object_name) or "Object"
    stem = path.stem or "untitled"
    suffix = path.suffix or ".stl"

    index = 0
    while True:
        extra = "" if index == 0 else f"_{index:03d}"
        candidate = path.with_name(f"{stem}_{safe_name}{extra}{suffix}")
        key = os.path.normcase(os.path.abspath(os.fspath(candidate)))
        if key not in used:
            used.add(key)
            return candidate
        index += 1


def _safe_filename_fragment(value: str) -> str:
    text = str(value or "").strip()
    out = []
    for char in text:
        if char in {"/", "\\", ":", "\0"} or ord(char) < 32:
            out.append("_")
        else:
            out.append(char)
    return "".join(out).strip(" .")


def _material_bake_size(value: int | str | None) -> int:
    try:
        size = int(value or 1024)
    except (TypeError, ValueError):
        return 1024
    if size <= 0:
        return 1024
    if size < 64:
        return 64
    if size > 8192:
        return 8192
    return size
