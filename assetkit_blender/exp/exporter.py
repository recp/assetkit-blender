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
from .animation import (
    animation_action_slot,
    animation_channel_with_clip,
    animation_channels_with_clip,
)
from .images import _ExportImageStore
from .materials import _material_bake_required, _material_tuple

EXPORT_FORMATS = (
    ("GLTF", "glTF", "Export .gltf with external .bin/resources", AK_FILE_TYPE_GLTF, ".gltf"),
    ("GLB", "GLB", "Export binary .glb", AK_FILE_TYPE_GLB, ".glb"),
    ("3MF", "3MF (.3mf)", "Export 3D Manufacturing Format package", AK_FILE_TYPE_3MF, ".3mf"),
    ("DAE", "COLLADA (.dae)", "Export COLLADA .dae", AK_FILE_TYPE_DAE, ".dae"),
    ("OBJ", "Wavefront OBJ (.obj)", "Export Wavefront OBJ .obj/.mtl", AK_FILE_TYPE_WAVEFRONT, ".obj"),
    ("STL", "STL (.stl)", "Export STL triangle mesh", AK_FILE_TYPE_STL, ".stl"),
    ("PLY", "PLY (.ply)", "Export Polygon File Format mesh", AK_FILE_TYPE_PLY, ".ply"),
)

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
        stl_export_format=stl_export_format,
        stl_scale=static_scale,
        stl_forward_axis=static_forward_axis,
        stl_up_axis=static_up_axis,
        ply_export_format=ply_export_format,
        ply_export_normals=bool(ply_export_normals) and bool(export_normals),
        ply_export_uv=bool(ply_export_uv) and bool(export_uv),
        ply_export_color_mode=ply_color_mode if export_vertex_colors else AK_PLY_EXPORT_COLOR_NONE,
        ply_export_triangulated=bool(ply_export_triangulated_mesh),
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
            stl_export_format=stl_export_format,
            stl_scale=stl_scale,
            stl_forward_axis=stl_forward_axis,
            stl_up_axis=stl_up_axis,
            ply_export_format=ply_export_format,
            ply_export_normals=ply_export_normals,
            ply_export_uv=ply_export_uv,
            ply_export_color_mode=ply_export_color_mode,
            ply_export_triangulated=ply_export_triangulated,
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
            _matrix_bytes(_object_world_matrix(obj, depsgraph)),
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
            fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(animation_data))) if action else ()
            pose = getattr(armature, "pose", None)
            if pose is None:
                continue
            for pose_bone in getattr(pose, "bones", []) or []:
                constraints = getattr(pose_bone, "constraints", None)
                if not fcurves and (constraints is None or len(constraints) == 0):
                    continue
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

    fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(animation_data)))
    if not fcurves:
        return None, False

    parent = obj.parent if obj.parent in included else None
    sample_transform = _transform_fcurves_need_sampling(fcurves, {
        "location": "location",
        "rotation_axis_angle": "rotation_axis_angle",
        "rotation_euler": "rotation_euler",
        "rotation_quaternion": "rotation_quaternion",
        "scale": "scale",
    })
    visibility_channel = _object_visibility_animation_channel(context.scene, obj, fcurves)
    direct = (
        _object_transform_animation_direct(context, obj, action, fcurves)
        if parent is obj.parent and not sample_transform
        else None
    )
    if direct is not None:
        channels = list(direct)
        if visibility_channel:
            channels.append(visibility_channel)
        return (animation_channels_with_clip(channels, action) if channels else None), False

    frames = _action_transform_keyframes(action, fcurves)
    if sample_transform:
        frames = _expanded_integer_sample_frames(frames)
    if len(frames) < 2:
        return (
            (animation_channel_with_clip(visibility_channel, action),)
            if visibility_channel else None
        ), False

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
            _action_interpolation(action, _LOCATION_ANIMATION_PATHS, fcurves),
        ))
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times.tobytes(),
            rotations.tobytes(),
            count,
            _action_interpolation(action, _ROTATION_ANIMATION_PATHS, fcurves),
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times.tobytes(),
            scales.tobytes(),
            count,
            _action_interpolation(action, _SCALE_ANIMATION_PATHS, fcurves),
        ))
    if visibility_channel:
        channels.append(visibility_channel)

    return (animation_channels_with_clip(channels, action) if channels else None), changed_frame


def _pose_bone_transform_animation(
    context: bpy.types.Context,
    armature: bpy.types.Object,
    bone_name: str,
    action: bpy.types.Action | None,
    fcurves: tuple | None = None,
) -> tuple[tuple | None, bool]:
    paths = _pose_bone_paths(armature, bone_name)
    if not paths:
        return None, False

    pose = getattr(armature, "pose", None)
    pose_bone = pose.bones.get(bone_name) if pose else None
    if fcurves is None:
        fcurves = (
            tuple(_iter_action_fcurves(action, animation_action_slot(getattr(armature, "animation_data", None))))
            if action is not None else ()
        )
    # Pose-bone fcurves store deltas over the rest pose, while exported node
    # channels need absolute local transforms. Sample the evaluated matrix so
    # rest rotations and imported axis wrappers are preserved.
    direct = None
    if direct is not None:
        return (direct if direct else None), False

    frames = (
        _action_keyframes_for_paths(action, set(paths.values()), fcurves)
        if action is not None and fcurves
        else ()
    )
    if action is not None and fcurves and _transform_fcurves_need_sampling(fcurves, paths):
        frames = _expanded_integer_sample_frames(frames)
    if len(frames) < 2 and pose_bone is not None:
        frames = _pose_bone_constraint_keyframes(pose_bone)
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
    loc_interp = (
        _action_interpolation(action, set(paths[prop] for prop in ("location",) if prop in paths), fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    rot_interp = (
        _action_interpolation(action, {
            paths[prop] for prop in ("rotation_axis_angle", "rotation_euler", "rotation_quaternion")
            if prop in paths
        }, fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    scale_interp = (
        _action_interpolation(action, set(paths[prop] for prop in ("scale",) if prop in paths), fcurves)
        if action is not None and fcurves else AK_INTERPOLATION_LINEAR
    )
    if _float_samples_changed(translations, 3):
        channels.append((
            AK_TARGET_POSITION,
            times.tobytes(),
            translations.tobytes(),
            count,
            loc_interp,
        ))
    if _float_samples_changed(rotations, 4):
        channels.append((
            AK_TARGET_QUAT,
            times.tobytes(),
            rotations.tobytes(),
            count,
            rot_interp,
        ))
    if _float_samples_changed(scales, 3):
        channels.append((
            AK_TARGET_SCALE,
            times.tobytes(),
            scales.tobytes(),
            count,
            scale_interp,
        ))

    return (animation_channels_with_clip(channels, action) if channels else None), changed_frame


def _object_transform_animation_direct(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    action: bpy.types.Action,
    fcurves: tuple | None = None,
) -> tuple | None:
    if fcurves is None:
        fcurves = tuple(_iter_action_fcurves(action, animation_action_slot(getattr(obj, "animation_data", None))))
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


def _action_transform_keyframes(action: bpy.types.Action, fcurves: tuple | None = None) -> tuple[float, ...]:
    frames: set[float] = set()
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in _TRANSFORM_ANIMATION_PATHS:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _expanded_integer_sample_frames(frames: tuple[float, ...]) -> tuple[float, ...]:
    if len(frames) < 2:
        return frames

    start = math.floor(frames[0])
    end = math.ceil(frames[-1])
    if end <= start:
        return _dedupe_animation_frames(frames)

    sampled = [float(frame) for frame in range(start, end + 1)]
    for frame in frames:
        value = _canonical_animation_frame(frame)
        nearest = round(value)
        if start <= nearest <= end and abs(value - nearest) <= _ANIMATION_FRAME_EPSILON:
            continue
        sampled.append(value)
    return _dedupe_animation_frames(tuple(sorted(sampled)))


def _canonical_animation_frame(frame: float) -> float:
    value = float(frame)
    nearest = round(value)
    if abs(value - nearest) <= _ANIMATION_FRAME_EPSILON:
        return float(nearest)
    return value


def _dedupe_animation_frames(frames: tuple[float, ...]) -> tuple[float, ...]:
    if len(frames) < 2:
        return frames

    out: list[float] = []
    previous: float | None = None
    for frame in frames:
        value = _canonical_animation_frame(frame)
        if previous is not None and abs(value - previous) <= _ANIMATION_FRAME_EPSILON:
            continue
        out.append(value)
        previous = value
    return tuple(out)


def _transform_fcurves_need_sampling(fcurves: tuple, paths: dict[str, str]) -> bool:
    if not fcurves:
        return False

    transform_paths = {path for path in paths.values() if path}
    rotation_paths = {
        paths[prop]
        for prop in ("rotation_axis_angle", "rotation_euler", "rotation_quaternion")
        if prop in paths and paths[prop]
    }
    if not transform_paths:
        return False

    for fcurve in fcurves:
        path = fcurve.data_path
        if path not in transform_paths:
            continue

        is_rotation = path in rotation_paths
        for key in fcurve.keyframe_points:
            interpolation = key.interpolation
            if interpolation not in {"CONSTANT", "LINEAR"}:
                return True
            if is_rotation and interpolation != "CONSTANT":
                return True
    return False


def _action_keyframes_for_paths(
    action: bpy.types.Action,
    paths: set[str],
    fcurves: tuple | None = None,
) -> tuple[float, ...]:
    frames: set[float] = set()
    if not paths:
        return ()
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            frames.add(float(key.co.x))
    return tuple(sorted(frames))


def _action_interpolation(
    action: bpy.types.Action,
    paths: set[str],
    fcurves: tuple | None = None,
) -> int:
    if not paths:
        return AK_INTERPOLATION_LINEAR
    found = False
    for fcurve in (fcurves if fcurves is not None else _iter_action_fcurves(action)):
        if fcurve.data_path not in paths:
            continue
        for key in fcurve.keyframe_points:
            found = True
            if key.interpolation != "CONSTANT":
                return AK_INTERPOLATION_LINEAR
    return AK_INTERPOLATION_STEP if found else AK_INTERPOLATION_LINEAR


def _iter_action_fcurves(action: bpy.types.Action, slot=None):
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None and len(fcurves) > 0:
        yield from fcurves
        return

    action_slots = tuple(getattr(action, "slots", []) or ())
    if slot is not None:
        slots = (slot,)
    elif len(action_slots) == 1:
        slots = action_slots
    else:
        return
    if not slots:
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for current_slot in slots:
                try:
                    channelbag = strip.channelbag(current_slot)
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


def _pose_bone_constraint_keyframes(pose_bone) -> tuple[float, ...]:
    frames: set[float] = set()
    for constraint in getattr(pose_bone, "constraints", []) or []:
        target = getattr(constraint, "target", None)
        if target is not None:
            _collect_object_animation_keyframes(target, frames)
    return tuple(sorted(frames))


def _collect_object_animation_keyframes(obj: bpy.types.Object, frames: set[float]) -> None:
    seen: set[int] = set()
    while obj is not None:
        key = int(obj.as_pointer())
        if key in seen:
            return
        seen.add(key)

        animation_data = obj.animation_data
        action = animation_data.action if animation_data else None
        if action is not None:
            for fcurve in _iter_action_fcurves(action, animation_action_slot(animation_data)):
                for point in fcurve.keyframe_points:
                    frames.add(float(point.co.x))

        obj = obj.parent


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
        inverse_bind_matrices.tobytes(),
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

    if is_static_mesh:
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

    if export_shape_keys and animation_bake_mode == "EVALUATED_MESH":
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
        times.tobytes(),
        values.tobytes(),
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
    return action is not None and _action_has_visibility_animation(action, animation_action_slot(animation_data))


def _object_has_ancestor_source_visibility(obj: bpy.types.Object) -> bool:
    if "assetkit_node_index" not in obj and not bool(obj.get("assetkit_helper_object", False)):
        return False
    parent = getattr(obj, "parent", None)
    while parent is not None:
        if _object_visibility_extra_value(parent) is not None:
            return True
        animation_data = parent.animation_data
        action = animation_data.action if animation_data else None
        if action is not None and _action_has_visibility_animation(action, animation_action_slot(animation_data)):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _action_has_visibility_animation(action: bpy.types.Action, slot=None) -> bool:
    for fcurve in _iter_action_fcurves(action, slot):
        if fcurve.data_path in _VISIBILITY_ANIMATION_PATHS:
            return True
    return False


def _is_assetkit_synthetic_helper_object(obj: bpy.types.Object) -> bool:
    if not bool(obj.get("assetkit_helper_object", False)):
        return False
    if (
        not bool(obj.get("assetkit_coordinate_root", False))
        and obj.name not in {"AssetKit Root", "AssetKit Coordinate Root", "AssetKit Coordinates"}
    ):
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
