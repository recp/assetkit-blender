from __future__ import annotations

from array import array
from collections import deque
from dataclasses import replace
import json
import math
import os
import queue
import threading
import time
import traceback

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Quaternion, Vector

from .assetkit import (
    AK_FILE_TYPE_WAVEFRONT,
    AK_FILE_TYPE_STL,
    AK_PRIMITIVE_LINES,
    AK_PRIMITIVE_POLYGONS,
    AK_PRIMITIVE_POINTS,
    AK_PRIMITIVE_TRIANGLES,
    AssetKit,
    AssetKitSceneData,
    LoopFloatAttributeData,
    MeshPrimitiveData,
    SceneNodeData,
    TextureRefData,
    _profile_enabled,
    _profile_log,
    native_animation_component_constant,
    native_animation_coords,
    native_load_meshes,
    native_fill_i32,
    native_fill_triangle_loop_offsets_ptr,
    native_fill_u8_ptr,
    native_offset_i32,
    native_open_scene_stream,
    native_skin_group_assignments,
    native_write_offset_i32,
)
from .hud import finish_loading_hud, start_loading_hud, update_loading_hud

_ANIM_TRANSLATION = 1
_ANIM_ROTATION_QUAT = 2
_ANIM_SCALE = 3
_ANIM_MORPH_WEIGHTS = 4
_ANIM_VISIBILITY = 5
_ANIM_CAMERA_XFOV = 6
_ANIM_CAMERA_YFOV = 7
_ANIM_CAMERA_ZNEAR = 8
_ANIM_CAMERA_ZFAR = 9
_ANIM_CAMERA_ORTHO_XMAG = 10
_ANIM_CAMERA_ORTHO_YMAG = 11
_ANIM_LIGHT_COLOR = 12
_ANIM_LIGHT_INTENSITY = 13
_ANIM_LIGHT_RANGE = 14
_ANIM_LIGHT_SPOT_INNER = 15
_ANIM_LIGHT_SPOT_OUTER = 16
_ANIM_MATERIAL_BASE_COLOR = 32
_ANIM_MATERIAL_METALLIC = 33
_ANIM_MATERIAL_ROUGHNESS = 34
_ANIM_MATERIAL_ALPHA_CUTOFF = 35
_ANIM_MATERIAL_EMISSIVE_COLOR = 36
_ANIM_MATERIAL_EMISSIVE_STRENGTH = 37
_ANIM_MATERIAL_NORMAL_SCALE = 38
_ANIM_MATERIAL_OCCLUSION_STRENGTH = 39
_ANIM_MATERIAL_SPECULAR = 40
_ANIM_MATERIAL_SPECULAR_COLOR = 41
_ANIM_MATERIAL_IOR = 42
_ANIM_MATERIAL_CLEARCOAT = 43
_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS = 44
_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE = 45
_ANIM_MATERIAL_TRANSMISSION = 46
_ANIM_MATERIAL_SHEEN_COLOR = 47
_ANIM_MATERIAL_SHEEN_ROUGHNESS = 48
_ANIM_MATERIAL_IRIDESCENCE = 49
_ANIM_MATERIAL_IRIDESCENCE_IOR = 50
_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM = 51
_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM = 52
_ANIM_MATERIAL_VOLUME_THICKNESS = 53
_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE = 54
_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR = 55
_ANIM_MATERIAL_ANISOTROPY = 56
_ANIM_MATERIAL_ANISOTROPY_ROTATION = 57
_ANIM_MATERIAL_DISPERSION = 58
_ANIM_MATERIAL_DIFFUSE_TRANSMISSION = 59
_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR = 60
_ANIM_TEXTURE_TRANSFORM_BASE = 1000
_ANIM_TEXTURE_TRANSFORM_STRIDE = 4
_ANIM_TEXTURE_TRANSFORM_OFFSET = 0
_ANIM_TEXTURE_TRANSFORM_SCALE = 1
_ANIM_TEXTURE_TRANSFORM_ROTATION = 2
_ANIM_TEXTURE_TRANSFORM_ROLES = (
    "base_color",
    "metallic_roughness",
    "occlusion",
    "normal",
    "emissive",
    "transparent",
    "specular",
    "specular_color",
    "clearcoat",
    "clearcoat_roughness",
    "clearcoat_normal",
    "transmission",
    "sheen_color",
    "sheen_roughness",
    "iridescence",
    "iridescence_thickness",
    "volume_thickness",
    "anisotropy",
    "diffuse_transmission",
    "diffuse_transmission_color",
)
_MATERIAL_TEXTURE_FIELDS = tuple(f"{role}_texture" for role in _ANIM_TEXTURE_TRANSFORM_ROLES)
_TEXTURE_IMAGE_CACHE: dict[tuple[str, str], object] = {}
_TEXTURE_PATH_CACHE: dict[str, str] = {}
_ACTIVE_TEXTURE_NODE_CACHE: dict[object, object] | None = None
_ACTIVE_SEPARATE_COLOR_CACHE: dict[int, object] | None = None
_ACTIVE_TEXTURE_LOAD_MODE = "IMMEDIATE"
_DEFERRED_TEXTURE_WAITERS: dict[tuple[str, str], list[object]] = {}
_DEFERRED_TEXTURE_KEYS: deque[tuple[str, str]] = deque()
_DEFERRED_TEXTURE_TIMER_ACTIVE = False
_DEFERRED_TEXTURE_TIME_BUDGET = 0.006
_DEFERRED_MATERIAL_NODE_TASKS: deque[tuple[object, ...]] = deque()
_DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = False
_DEFERRED_MATERIAL_NODE_TIME_BUDGET = 0.006
_DEFERRED_MATERIAL_SLOT_TASKS: deque["_DeferredMaterialSpec"] = deque()
_DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE = False
_DEFERRED_MATERIAL_SLOT_TIME_BUDGET = 0.006
_REQUIRED_NODE_INDICES_AUTO = object()
_INTERPOLATION_LINEAR = 1
_INTERPOLATION_HERMITE = 4
_INTERPOLATION_STEP = 6
_AK_MATERIAL_TYPE_PHONG = 1
_AK_MATERIAL_TYPE_BLINN = 2
_AK_MATERIAL_TYPE_LAMBERT = 3
_AK_MATERIAL_TYPE_CONSTANT = 4
_AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS = 6
_AK_MATERIAL_TYPE_PBR = 7
_AK_OPAQUE_A_ONE = 1
_AK_OPAQUE_A_ZERO = 2
_AK_OPAQUE_RGB_ONE = 3
_AK_OPAQUE_RGB_ZERO = 4
_GLTF_SETTINGS_GROUP_NAME = "glTF Material Output"
_GLTF_SETTINGS_SOCKETS = (
    ("Occlusion", 1.0),
    ("Thickness", 0.0),
    ("Dispersion", 0.0),
    ("Iridescence Factor", 0.0),
    ("Iridescence Thickness Minimum", 100.0),
)
_GLTF_SETTINGS_GROUP_CACHE = None
_TEXTURE_WRAP_DEFAULT = 1
_TEXTURE_FILTER_DEFAULT = 0
_TEXTURE_EXTENSION_DEFAULT = "REPEAT"
_TEXTURE_INTERPOLATION_DEFAULT = "Linear"
_PROGRESSIVE_BATCH_SIZE = 128
_PROGRESSIVE_FIRST_BATCH_SIZE = 8
_PROGRESSIVE_TIME_BUDGET = 0.025
_DEFERRED_NORMAL_TIME_BUDGET = 0.006
_ACTIVE_IMPORT_JOBS: list["_ProgressiveImportJob"] = []
_DEFERRED_NORMAL_TASKS: deque[tuple[bpy.types.Mesh, object, object | None, object | None]] = deque()
_DEFERRED_NORMAL_TIMER_ACTIVE = False
_ACTION_CHANNELBAGS: dict[tuple[int, int], tuple[object, object]] = {}
_ACTION_CHANNEL_GROUPS: dict[tuple[int, str], object] = {}
_IMPORT_SHARED_ACTIONS: dict[tuple[int, str, str], bpy.types.Action] = {}
_ACTION_FRAME_RANGES: dict[int, tuple[float, float]] = {}
_KEYFRAME_ENUM_VALUES: dict[tuple[str, str], int] = {}
_KEYFRAME_ENUM_ARRAYS: dict[tuple[int, int], array] = {}
_BOOL_ARRAYS: dict[tuple[int, int], array] = {}
_TRI_LOOP_START_ARRAYS: dict[int, array] = {}
_TRI_LOOP_START_CACHE_LIMIT = 65536
_ACTION_SLOTS_SUPPORTED: bool | None = None
_PROFILE_MATERIAL_STATS: dict[str, float | int] | None = None
_CH_KEYS = (
    "target",
    "target_offset",
    "clip_index",
    "clip_name",
    "value_width",
    "count",
    "interpolation",
    "is_partial",
    "pose_ready",
    "times_f32",
    "values_f32",
    "in_tangents_f32",
    "out_tangents_f32",
)
(
    _CH_TARGET,
    _CH_TARGET_OFFSET,
    _CH_CLIP_INDEX,
    _CH_CLIP_NAME,
    _CH_VALUE_WIDTH,
    _CH_COUNT,
    _CH_INTERPOLATION,
    _CH_IS_PARTIAL,
    _CH_POSE_READY,
    _CH_TIMES_F32,
    _CH_VALUES_F32,
    _CH_IN_TANGENTS_F32,
    _CH_OUT_TANGENTS_F32,
) = range(len(_CH_KEYS))

(
    _S_COORD_ROOT,
    _S_ROOT_OBJECTS,
    _S_NODE_OBJECTS,
    _S_NODE_DATA,
    _S_NODE_VISIBILITY,
    _S_NODE_ANIMATION_SKIP_INDICES,
    _S_MATERIAL_CACHE,
    _S_MESH_CACHE,
    _S_SKIN_CACHE,
    _S_NODE_ANIMATION_DEFERRED,
    _S_SKIN_ANIMATION_DEFERRED,
    _S_DEFERRED_SKIN_ANIMATIONS,
    _S_MESH_CACHE_HITS,
    _S_DEFER_CUSTOM_NORMALS,
    _S_HAS_NODE_VISIBILITY_ANIMATION,
    _S_HAS_NODE_ANIMATION,
    _S_DYNAMIC_SKIN_ANIMATION_SKIP,
    _S_NODE_PARENT_CACHE,
) = range(18)
_SKIN_CACHE_DEFER_BIND_SKINS = object()


class _DeferredMaterialSpec:
    __slots__ = (
        "name",
        "cache",
        "cache_key",
        "path",
        "tex_info",
        "base_color",
        "metallic",
        "roughness",
        "double_sided",
        "classic",
        "normal_path",
        "normal_tex_info",
        "normal_scale",
        "specular",
        "has_specular_tint",
        "specular_color",
        "has_emission",
        "emissive_color",
        "emissive_strength",
        "ior",
        "slots",
    )

    def __init__(
        self,
        name: str,
        cache: dict | None,
        cache_key: object,
        path: str,
        tex_info: TextureRefData | None,
        base_color: tuple[float, float, float, float],
        metallic: float,
        roughness: float,
        double_sided: bool,
        *,
        classic: bool = False,
        normal_path: str = "",
        normal_tex_info: TextureRefData | None = None,
        normal_scale: float = 1.0,
        specular: float = 0.5,
        has_specular_tint: bool = False,
        specular_color: tuple[float, float, float] = (1.0, 1.0, 1.0),
        has_emission: bool = False,
        emissive_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        emissive_strength: float = 0.0,
        ior: float = 1.5,
    ) -> None:
        self.name = name
        self.cache = cache
        self.cache_key = cache_key
        self.path = path
        self.tex_info = tex_info
        self.base_color = base_color
        self.metallic = metallic
        self.roughness = roughness
        self.double_sided = double_sided
        self.classic = classic
        self.normal_path = normal_path
        self.normal_tex_info = normal_tex_info
        self.normal_scale = normal_scale
        self.specular = specular
        self.has_specular_tint = has_specular_tint
        self.specular_color = specular_color
        self.has_emission = has_emission
        self.emissive_color = emissive_color
        self.emissive_strength = emissive_strength
        self.ior = ior
        self.slots: list[tuple[object, object | None, int, bool]] = []


def import_assetkit_file(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
    collection: bpy.types.Collection | None = None,
    focus_mode: str = "NEVER",
    placement_mode: str = "AS_AUTHORED",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    clean_viewport_overlays: bool = True,
    fit_timeline: bool = False,
) -> list[bpy.types.Object]:
    _reset_action_cache()
    _reset_material_profile()
    existing_actions = _snapshot_actions(fit_timeline)
    texture_load_mode = _texture_load_mode(load_options)
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    defer_custom_normals = _defer_custom_normals(load_options, shading_mode)
    total_started_at = time.perf_counter() if profile_detail else 0.0
    load_started_at = total_started_at
    primitives, scene_nodes, doc_extra, scene_extra, scene_info, doc_images = _load_assetkit_scene(
        filepath,
        library_path,
        load_options,
    )
    if profile_detail:
        _profile_log(
            "blocking load "
            f"meshes={len(primitives)} nodes={len(scene_nodes)} "
            f"elapsed={(time.perf_counter() - load_started_at) * 1000.0:.3f}ms"
        )
    scene_started_at = time.perf_counter() if profile_detail else 0.0
    state = _begin_scene_build(
        primitives,
        scene_nodes,
        collection or bpy.context.collection,
        doc_extra,
        scene_extra,
        scene_info,
        doc_images,
        defer_custom_normals=defer_custom_normals,
    )
    if profile_detail:
        _profile_log(
            "blocking begin_scene_build "
            f"nodes={len(scene_nodes)} "
            f"elapsed={(time.perf_counter() - scene_started_at) * 1000.0:.3f}ms"
        )
    objects: list[bpy.types.Object] = []
    build_started_at = time.perf_counter() if profile_detail else 0.0
    import_units = _mesh_import_units(primitives)
    global _ACTIVE_TEXTURE_LOAD_MODE
    previous_texture_load_mode = _ACTIVE_TEXTURE_LOAD_MODE
    _ACTIVE_TEXTURE_LOAD_MODE = texture_load_mode
    try:
        for unit in import_units:
            objects.extend(_create_import_unit(unit, state, collection or bpy.context.collection, shading_mode))
        _apply_deferred_bind_pose_skins(state)
    finally:
        _ACTIVE_TEXTURE_LOAD_MODE = previous_texture_load_mode
    if profile_detail:
        _profile_log(
            "blocking build_objects "
            f"objects={len(objects)} primitives={len(primitives)} units={len(import_units)} "
            f"mesh_cache_hits={int(state[_S_MESH_CACHE_HITS])} "
            f"elapsed={(time.perf_counter() - build_started_at) * 1000.0:.3f}ms"
        )
        _log_material_profile("blocking")

    finish_started_at = time.perf_counter() if profile_detail else 0.0
    _finish_import(
        objects,
        focus_mode,
        placement_mode,
        state[_S_ROOT_OBJECTS],
        scene_was_empty,
        collection or bpy.context.collection,
        focus_camera,
        select_imported,
        set_viewport_shading,
        clean_viewport_overlays,
        existing_actions,
    )
    if profile_detail:
        _profile_log(
            "blocking finish "
            f"elapsed={(time.perf_counter() - finish_started_at) * 1000.0:.3f}ms "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return _import_result_objects(objects, state)


def import_assetkit_file_progressive(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
    collection: bpy.types.Collection | None = None,
    batch_size: int = _PROGRESSIVE_BATCH_SIZE,
    focus_mode: str = "NEVER",
    placement_mode: str = "AS_AUTHORED",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    clean_viewport_overlays: bool = True,
    fit_timeline: bool = False,
) -> "_ProgressiveImportJob":
    _reset_action_cache()
    _reset_material_profile()
    job = _ProgressiveImportJob(
        filepath,
        library_path,
        load_options,
        collection or bpy.context.collection,
        max(1, batch_size),
        focus_mode,
        placement_mode,
        scene_was_empty,
        focus_camera,
        select_imported,
        shading_mode,
        set_viewport_shading,
        clean_viewport_overlays,
        _snapshot_actions(fit_timeline),
        prefer_grouped=True,
    )
    job.start()
    return job


def import_assetkit_file_auto(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
    collection: bpy.types.Collection | None = None,
    batch_size: int = _PROGRESSIVE_BATCH_SIZE,
    focus_mode: str = "NEVER",
    placement_mode: str = "AS_AUTHORED",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    clean_viewport_overlays: bool = True,
    fit_timeline: bool = False,
) -> list[bpy.types.Object] | "_ProgressiveImportJob":
    _reset_action_cache()
    _reset_material_profile()
    active_collection = collection or bpy.context.collection
    job = _ProgressiveImportJob(
        filepath,
        library_path,
        load_options,
        active_collection,
        max(1, batch_size),
        focus_mode,
        placement_mode,
        scene_was_empty,
        focus_camera,
        select_imported,
        shading_mode,
        set_viewport_shading,
        clean_viewport_overlays,
        _snapshot_actions(fit_timeline),
        prefer_grouped=True,
    )
    job.start()
    return job


def _load_assetkit_scene(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
) -> tuple[list[MeshPrimitiveData], list[SceneNodeData], object | None, object | None, dict, list[dict]]:
    loaded = native_load_meshes(filepath, load_options) if not library_path else None
    if loaded is None:
        kit = AssetKit(library_path or None)
        loaded = kit.load_meshes(filepath)

    if isinstance(loaded, AssetKitSceneData):
        return (
            loaded.meshes,
            loaded.nodes,
            loaded.doc_extra,
            loaded.scene_extra,
            _scene_info_from_loaded(loaded),
            list(loaded.images or []),
        )
    return loaded, [], None, None, {}, []


def _reset_material_profile() -> None:
    global _PROFILE_MATERIAL_STATS
    if not _profile_enabled():
        _PROFILE_MATERIAL_STATS = None
        return
    _PROFILE_MATERIAL_STATS = {
        "calls": 0,
        "cache_hits": 0,
        "created": 0,
        "cache_key_ms": 0.0,
        "new_ms": 0.0,
        "simple_ms": 0.0,
        "nodes_ms": 0.0,
        "props_ms": 0.0,
        "settings_ms": 0.0,
        "textures_ms": 0.0,
        "animation_ms": 0.0,
        "total_ms": 0.0,
        "mesh_calls": 0,
        "mesh_alloc_ms": 0.0,
        "mesh_views_ms": 0.0,
        "mesh_topology_ms": 0.0,
        "mesh_uv_ms": 0.0,
        "mesh_color_ms": 0.0,
        "mesh_tangent_ms": 0.0,
        "mesh_update_ms": 0.0,
        "mesh_shading_ms": 0.0,
        "mesh_finish_ms": 0.0,
        "mesh_total_ms": 0.0,
        "finish_calls": 0,
        "finish_bind_shape_ms": 0.0,
        "finish_object_ms": 0.0,
        "finish_material_ms": 0.0,
        "finish_props_ms": 0.0,
        "finish_morph_ms": 0.0,
        "finish_skin_ms": 0.0,
        "finish_animation_ms": 0.0,
        "finish_instancing_ms": 0.0,
        "finish_total_ms": 0.0,
    }


def _record_material_profile(
    *,
    cache_hit: bool,
    cache_key_ms: float,
    new_ms: float,
    simple_ms: float,
    nodes_ms: float,
    props_ms: float,
    settings_ms: float,
    textures_ms: float,
    animation_ms: float,
    total_ms: float,
) -> None:
    stats = _PROFILE_MATERIAL_STATS
    if stats is None:
        return
    stats["calls"] = int(stats["calls"]) + 1
    if cache_hit:
        stats["cache_hits"] = int(stats["cache_hits"]) + 1
    else:
        stats["created"] = int(stats["created"]) + 1
    stats["cache_key_ms"] = float(stats["cache_key_ms"]) + cache_key_ms
    stats["new_ms"] = float(stats["new_ms"]) + new_ms
    stats["simple_ms"] = float(stats["simple_ms"]) + simple_ms
    stats["nodes_ms"] = float(stats["nodes_ms"]) + nodes_ms
    stats["props_ms"] = float(stats["props_ms"]) + props_ms
    stats["settings_ms"] = float(stats["settings_ms"]) + settings_ms
    stats["textures_ms"] = float(stats["textures_ms"]) + textures_ms
    stats["animation_ms"] = float(stats["animation_ms"]) + animation_ms
    stats["total_ms"] = float(stats["total_ms"]) + total_ms


def _log_material_profile(label: str) -> None:
    stats = _PROFILE_MATERIAL_STATS
    if stats is None:
        return
    if int(stats["calls"]):
        _profile_log(
            "material_profile "
            f"{label} calls={int(stats['calls'])} "
            f"created={int(stats['created'])} "
            f"cache_hits={int(stats['cache_hits'])} "
            f"cache_key={float(stats['cache_key_ms']):.3f}ms "
            f"new={float(stats['new_ms']):.3f}ms "
            f"simple={float(stats['simple_ms']):.3f}ms "
            f"nodes={float(stats['nodes_ms']):.3f}ms "
            f"props={float(stats['props_ms']):.3f}ms "
            f"settings={float(stats['settings_ms']):.3f}ms "
            f"textures={float(stats['textures_ms']):.3f}ms "
            f"animation={float(stats['animation_ms']):.3f}ms "
            f"total={float(stats['total_ms']):.3f}ms"
        )
    mesh_calls = int(stats.get("mesh_calls", 0) or 0)
    if mesh_calls:
        _profile_log(
            "mesh_profile "
            f"{label} calls={mesh_calls} "
            f"alloc={float(stats['mesh_alloc_ms']):.3f}ms "
            f"views={float(stats['mesh_views_ms']):.3f}ms "
            f"topology={float(stats['mesh_topology_ms']):.3f}ms "
            f"uv={float(stats['mesh_uv_ms']):.3f}ms "
            f"color={float(stats['mesh_color_ms']):.3f}ms "
            f"tangent={float(stats['mesh_tangent_ms']):.3f}ms "
            f"update={float(stats['mesh_update_ms']):.3f}ms "
            f"shading={float(stats['mesh_shading_ms']):.3f}ms "
            f"finish={float(stats['mesh_finish_ms']):.3f}ms "
            f"total={float(stats['mesh_total_ms']):.3f}ms"
        )
    finish_calls = int(stats.get("finish_calls", 0) or 0)
    if finish_calls:
        _profile_log(
            "finish_profile "
            f"{label} calls={finish_calls} "
            f"bind_shape={float(stats['finish_bind_shape_ms']):.3f}ms "
            f"object={float(stats['finish_object_ms']):.3f}ms "
            f"material={float(stats['finish_material_ms']):.3f}ms "
            f"props={float(stats['finish_props_ms']):.3f}ms "
            f"morph={float(stats['finish_morph_ms']):.3f}ms "
            f"skin={float(stats['finish_skin_ms']):.3f}ms "
            f"animation={float(stats['finish_animation_ms']):.3f}ms "
            f"instancing={float(stats['finish_instancing_ms']):.3f}ms "
            f"total={float(stats['finish_total_ms']):.3f}ms"
        )


def _record_mesh_profile(phases: dict[str, float], total_ms: float) -> None:
    stats = _PROFILE_MATERIAL_STATS
    if stats is None:
        return
    stats["mesh_calls"] = int(stats.get("mesh_calls", 0) or 0) + 1
    for name in (
        "alloc",
        "views",
        "topology",
        "uv",
        "color",
        "tangent",
        "update",
        "shading",
        "finish",
    ):
        key = f"mesh_{name}_ms"
        stats[key] = float(stats.get(key, 0.0) or 0.0) + float(phases.get(name, 0.0))
    stats["mesh_total_ms"] = float(stats.get("mesh_total_ms", 0.0) or 0.0) + total_ms


def _record_finish_profile(
    *,
    bind_shape_ms: float,
    object_ms: float,
    material_ms: float,
    props_ms: float,
    morph_ms: float,
    skin_ms: float,
    animation_ms: float,
    instancing_ms: float,
    total_ms: float,
) -> None:
    stats = _PROFILE_MATERIAL_STATS
    if stats is None:
        return
    stats["finish_calls"] = int(stats.get("finish_calls", 0) or 0) + 1
    stats["finish_bind_shape_ms"] = float(stats.get("finish_bind_shape_ms", 0.0) or 0.0) + bind_shape_ms
    stats["finish_object_ms"] = float(stats.get("finish_object_ms", 0.0) or 0.0) + object_ms
    stats["finish_material_ms"] = float(stats.get("finish_material_ms", 0.0) or 0.0) + material_ms
    stats["finish_props_ms"] = float(stats.get("finish_props_ms", 0.0) or 0.0) + props_ms
    stats["finish_morph_ms"] = float(stats.get("finish_morph_ms", 0.0) or 0.0) + morph_ms
    stats["finish_skin_ms"] = float(stats.get("finish_skin_ms", 0.0) or 0.0) + skin_ms
    stats["finish_animation_ms"] = float(stats.get("finish_animation_ms", 0.0) or 0.0) + animation_ms
    stats["finish_instancing_ms"] = float(stats.get("finish_instancing_ms", 0.0) or 0.0) + instancing_ms
    stats["finish_total_ms"] = float(stats.get("finish_total_ms", 0.0) or 0.0) + total_ms


def _texture_load_mode(load_options: dict | None) -> str:
    mode = str((load_options or {}).get("texture_loading") or "IMMEDIATE").upper()
    if mode == "AUTO":
        return "IMMEDIATE" if bpy.app.background else "DEFERRED"
    if mode == "DEFERRED":
        return "DEFERRED"
    return "IMMEDIATE"


def _defer_custom_normals(load_options: dict | None, shading_mode: str) -> bool:
    if bpy.app.background or str(shading_mode or "AUTO").upper() != "AUTO":
        return False

    value = (load_options or {}).get("defer_custom_normals", "AUTO")
    if isinstance(value, bool):
        return value
    mode = str(value or "AUTO").upper()
    return mode not in {"0", "FALSE", "IMMEDIATE", "NO", "OFF"}


def _effective_shading_mode(data: MeshPrimitiveData, shading_mode: str) -> str:
    mode = str(shading_mode or "AUTO").upper()
    if (
        mode in {"AUTO", "AS_IS"}
        and int(getattr(data, "file_type", 0) or 0) == AK_FILE_TYPE_STL
        and int(getattr(data, "primitive_type", 0) or 0) == AK_PRIMITIVE_TRIANGLES
    ):
        return "FLAT"
    return mode


def _uses_wavefront_smoothing(data: MeshPrimitiveData) -> bool:
    return (
        int(getattr(data, "file_type", 0) or 0) == AK_FILE_TYPE_WAVEFRONT
        and int(getattr(data, "primitive_type", 0) or 0) in (AK_PRIMITIVE_TRIANGLES, AK_PRIMITIVE_POLYGONS)
    )


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


def _scene_info_from_loaded(loaded: object | None) -> dict:
    if not loaded:
        return {}
    return {
        "index": int(getattr(loaded, "scene_index", -1)),
        "count": int(getattr(loaded, "scene_count", 0)),
        "name": str(getattr(loaded, "scene_name", "") or ""),
        "names": list(getattr(loaded, "scene_names", []) or []),
    }


def _begin_scene_build(
    primitives: list[MeshPrimitiveData],
    scene_nodes: list[SceneNodeData],
    collection: bpy.types.Collection,
    doc_extra: object | None = None,
    scene_extra: object | None = None,
    scene_info: dict | None = None,
    doc_images: list[dict] | None = None,
    apply_node_animation: bool = True,
    defer_custom_normals: bool = False,
    dynamic_skin_animation_skip: bool = False,
    create_all_nodes: bool = False,
    required_node_indices: object = _REQUIRED_NODE_INDICES_AUTO,
) -> dict:
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    _set_document_extra_props(collection, doc_extra, scene_extra, scene_info, doc_images)
    doc_ms = (time.perf_counter() - started_at) * 1000.0 if profile_detail else 0.0
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    coord_root = _create_coord_root(primitives, collection)
    coord_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile_detail else 0.0
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    node_visibility_animation = False
    node_animation = False
    node_hidden = False
    for node in scene_nodes:
        if not node.visible:
            node_hidden = True
        if node.anim_count or node.anim_channels:
            node_animation = True
        if _node_has_visibility_animation(node):
            node_visibility_animation = True
    if node_hidden or node_visibility_animation:
        node_visibility = _effective_static_node_visibility_map(scene_nodes)
        node_object_visibility = _node_object_visibility_map(scene_nodes, node_visibility)
    else:
        node_visibility = None
        node_object_visibility = None
    visibility_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile_detail else 0.0
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    node_animation_skip_indices = _skinned_node_animation_skip_indices(primitives)
    if create_all_nodes:
        required_node_indices = None
    elif required_node_indices is _REQUIRED_NODE_INDICES_AUTO:
        required_node_indices = _required_scene_node_indices(primitives, scene_nodes, node_animation_skip_indices)
    elif required_node_indices is not None:
        required_node_indices = set(required_node_indices)
    node_objects = _create_scene_nodes(
        scene_nodes,
        coord_root,
        collection,
        node_object_visibility,
        apply_animation=apply_node_animation,
        skip_animation_nodes=node_animation_skip_indices,
        required_indices=required_node_indices,
    )
    nodes_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile_detail else 0.0
    if profile_detail:
        _profile_log(
            "begin_scene_build_detail "
            f"doc_props={doc_ms:.3f}ms "
            f"coord_root={coord_ms:.3f}ms "
            f"visibility={visibility_ms:.3f}ms "
            f"create_nodes={nodes_ms:.3f}ms "
            f"nodes={len(scene_nodes)} "
            f"created_nodes={len(node_objects)}"
        )
    return {
        _S_COORD_ROOT: coord_root,
        _S_ROOT_OBJECTS: _scene_root_objects(scene_nodes, coord_root, node_objects),
        _S_NODE_OBJECTS: node_objects,
        _S_NODE_DATA: {index: node for index, node in enumerate(scene_nodes)},
        _S_NODE_VISIBILITY: node_visibility,
        _S_NODE_ANIMATION_SKIP_INDICES: node_animation_skip_indices,
        _S_MATERIAL_CACHE: {},
        _S_MESH_CACHE: {},
        _S_SKIN_CACHE: {},
        _S_NODE_ANIMATION_DEFERRED: not apply_node_animation,
        _S_SKIN_ANIMATION_DEFERRED: not apply_node_animation,
        _S_DEFERRED_SKIN_ANIMATIONS: [],
        _S_MESH_CACHE_HITS: 0,
        _S_DEFER_CUSTOM_NORMALS: defer_custom_normals,
        _S_HAS_NODE_VISIBILITY_ANIMATION: node_visibility_animation,
        _S_HAS_NODE_ANIMATION: node_animation,
        _S_DYNAMIC_SKIN_ANIMATION_SKIP: dynamic_skin_animation_skip,
        _S_NODE_PARENT_CACHE: {},
    }


def _set_document_extra_props(
    collection: bpy.types.Collection,
    doc_extra: object | None,
    scene_extra: object | None = None,
    scene_info: dict | None = None,
    doc_images: list[dict] | None = None,
) -> None:
    _set_assetkit_json_prop(collection, "assetkit_document_extra_json", doc_extra)
    _set_assetkit_json_prop(bpy.context.scene, "assetkit_document_extra_json", doc_extra)
    _set_assetkit_json_prop(collection, "assetkit_document_images_json", doc_images)
    _set_assetkit_json_prop(bpy.context.scene, "assetkit_document_images_json", doc_images)
    _set_scene_props(collection, scene_extra, scene_info)
    _set_scene_props(bpy.context.scene, scene_extra, scene_info)
    world = _assetkit_document_world(doc_extra, doc_images)
    if world:
        _set_assetkit_json_prop(world, "assetkit_document_extra_json", doc_extra)
        _set_assetkit_json_prop(world, "assetkit_document_images_json", doc_images)


def _set_scene_props(target, scene_extra: object | None, scene_info: dict | None) -> None:
    info = scene_info or {}
    if not scene_extra and not info:
        return

    _set_assetkit_json_prop(target, "assetkit_scene_extra_json", scene_extra)
    target["assetkit_scene_index"] = int(info.get("index", -1))
    target["assetkit_scene_count"] = int(info.get("count", 0))
    target["assetkit_scene_name"] = str(info.get("name", "") or "")
    _set_assetkit_json_prop(target, "assetkit_scene_names_json", info.get("names"))


def _assetkit_document_world(
    doc_extra: object | None,
    doc_images: list[dict] | None = None,
) -> bpy.types.World | None:
    scene = bpy.context.scene
    world = scene.world
    if world is None and _document_image_based_light(doc_extra):
        world = bpy.data.worlds.new("AssetKit World")
        scene.world = world
    if world:
        _apply_document_image_based_light(world, doc_extra, doc_images)
    return world


def _document_image_based_light(doc_extra: object | None) -> object | None:
    ext = _assetkit_extra_path(doc_extra, "extensions", "EXT_lights_image_based")
    lights = _assetkit_extra_child(ext, "lights")
    if not isinstance(lights, dict):
        return None
    for child in lights.get("children") or ():
        if isinstance(child, dict):
            return child
    return None


def _apply_document_image_based_light(
    world: bpy.types.World,
    doc_extra: object | None,
    doc_images: list[dict] | None = None,
) -> None:
    light = _document_image_based_light(doc_extra)
    if not light:
        return

    intensity = max(0.0, _assetkit_extra_float(_assetkit_extra_child(light, "intensity"), 1.0))
    color = _image_based_light_color(light)
    if not color:
        return

    world.color = color
    world["assetkit_environment_intensity"] = intensity
    world["assetkit_environment_color"] = color
    world["assetkit_environment_type"] = "EXT_lights_image_based"
    _set_image_based_light_props(world, light, doc_images)

    try:
        world.use_nodes = True
    except Exception:
        return

    background = world.node_tree.nodes.get("Background") if world.node_tree else None
    if not background:
        return
    color_socket = background.inputs.get("Color")
    strength_socket = background.inputs.get("Strength")
    if color_socket:
        color_socket.default_value = (*color, 1.0)
    if strength_socket:
        strength_socket.default_value = min(max(intensity, 0.0), 10.0)


def _set_image_based_light_props(
    world: bpy.types.World,
    light: object,
    doc_images: list[dict] | None = None,
) -> None:
    payload = _assetkit_extra_plain_value(light)
    if not isinstance(payload, dict):
        return

    name = payload.get("name")
    if name:
        world["assetkit_environment_name"] = str(name)

    specular_size = payload.get("specularImageSize")
    if specular_size is not None:
        try:
            world["assetkit_environment_specular_image_size"] = int(specular_size)
        except (TypeError, ValueError):
            pass

    rotation = payload.get("rotation")
    if isinstance(rotation, list) and len(rotation) == 4:
        try:
            world["assetkit_environment_rotation_xyzw"] = tuple(float(value) for value in rotation)
        except (TypeError, ValueError):
            pass

    _set_assetkit_json_prop(
        world,
        "assetkit_environment_irradiance_coefficients_json",
        payload.get("irradianceCoefficients"),
    )
    _set_assetkit_json_prop(
        world,
        "assetkit_environment_specular_images_json",
        payload.get("specularImages"),
    )
    _set_assetkit_json_prop(
        world,
        "assetkit_environment_specular_image_paths_json",
        _image_based_light_specular_paths(payload.get("specularImages"), doc_images),
    )


def _image_based_light_specular_paths(
    specular_images: object | None,
    doc_images: list[dict] | None,
) -> list[list[str]] | None:
    if not isinstance(specular_images, list) or not doc_images:
        return None

    paths = []
    for mip in specular_images:
        if not isinstance(mip, list):
            continue
        row = []
        for index in mip:
            try:
                image = doc_images[int(index)]
            except (TypeError, ValueError, IndexError):
                row.append("")
                continue
            row.append(str(image.get("path") or "") if isinstance(image, dict) else "")
        paths.append(row)

    return paths or None


def _image_based_light_color(light: object | None) -> tuple[float, float, float] | None:
    coeffs = _assetkit_extra_child(light, "irradianceCoefficients")
    if not isinstance(coeffs, dict):
        return None

    payload = _assetkit_extra_plain_value(coeffs)
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        try:
            values = tuple(float(value) for value in payload[0][:3])
        except (TypeError, ValueError):
            values = ()
    else:
        first = None
        for child in coeffs.get("children") or ():
            if isinstance(child, dict):
                first = child
                break
        values = _assetkit_extra_float_array(first, 3)
    if len(values) != 3:
        return None
    positives = [max(0.0, float(value)) for value in values]
    scale = max(max(positives), 1.0)
    return tuple(max(0.0, min(value / scale, 1.0)) for value in positives)


def _scene_root_objects(
    scene_nodes: list[SceneNodeData],
    coord_root: bpy.types.Object | None,
    node_objects: dict[int, bpy.types.Object],
) -> list[bpy.types.Object]:
    if coord_root:
        return [coord_root]
    roots = []
    for index, node in enumerate(scene_nodes):
        if node.parent_index < 0 and index in node_objects:
            roots.append(node_objects[index])
    return roots


def _mesh_node_parent(state: dict, node_index: int) -> tuple[bpy.types.Object | None, bool]:
    cache = state.get(_S_NODE_PARENT_CACHE)
    if cache is not None:
        cached = cache.get(node_index)
        if cached is not None:
            return cached

    node_objects = state[_S_NODE_OBJECTS]
    node_parent = node_objects.get(node_index)
    if node_parent is not None:
        result = (node_parent, True)
        if cache is not None:
            cache[node_index] = result
        return result

    node_data = state[_S_NODE_DATA]
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

    result = (state[_S_COORD_ROOT], False)
    if cache is not None:
        cache[node_index] = result
    return result


def _create_import_object(
    primitive: MeshPrimitiveData,
    state: dict,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    node_objects = state[_S_NODE_OBJECTS]
    parent, use_node_parent = _mesh_node_parent(state, int(primitive.node_index))
    defer_animation = bool(state[_S_NODE_ANIMATION_DEFERRED])
    node_visibility_animation = bool(state[_S_HAS_NODE_VISIBILITY_ANIMATION])
    mesh_cache_key = _mesh_data_reuse_key(primitive, shading_mode)
    mesh_cache = state[_S_MESH_CACHE] if mesh_cache_key is not None else None
    if mesh_cache is not None:
        cached_mesh = mesh_cache.get(mesh_cache_key)
        if cached_mesh is not None:
            use_object_material_slot = _has_material_data(primitive)
            state[_S_MESH_CACHE_HITS] += 1
            return _finish_mesh_object(
                cached_mesh,
                primitive,
                parent,
                node_objects=node_objects,
                node_data=state[_S_NODE_DATA],
                node_visibility=state[_S_NODE_VISIBILITY],
                material_cache=state[_S_MATERIAL_CACHE],
                skin_cache=state[_S_SKIN_CACHE],
                apply_transform=not use_node_parent,
                apply_animation=(not use_node_parent and not defer_animation),
                apply_skin_animation=not bool(state[_S_SKIN_ANIMATION_DEFERRED]),
                deferred_skin_animations=state[_S_DEFERRED_SKIN_ANIMATIONS],
                collection=collection,
                object_material_slot=use_object_material_slot,
                node_visibility_animation=node_visibility_animation,
            )

    objects = _create_mesh_object(
        primitive,
        parent,
        node_objects=node_objects,
        node_data=state[_S_NODE_DATA],
        node_visibility=state[_S_NODE_VISIBILITY],
        material_cache=state[_S_MATERIAL_CACHE],
        skin_cache=state[_S_SKIN_CACHE],
        apply_transform=not use_node_parent,
        apply_animation=(not use_node_parent and not defer_animation),
        apply_skin_animation=not bool(state[_S_SKIN_ANIMATION_DEFERRED]),
        deferred_skin_animations=state[_S_DEFERRED_SKIN_ANIMATIONS],
        shading_mode=shading_mode,
        defer_custom_normals=bool(state[_S_DEFER_CUSTOM_NORMALS]),
        collection=collection,
        object_material_slot=False,
        node_visibility_animation=node_visibility_animation,
    )
    if mesh_cache is not None and len(objects) == 1 and isinstance(objects[0].data, bpy.types.Mesh):
        mesh_cache[mesh_cache_key] = objects[0].data
    return objects


def _create_import_unit(
    unit: MeshPrimitiveData | list[MeshPrimitiveData],
    state: dict,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    if state[_S_DYNAMIC_SKIN_ANIMATION_SKIP]:
        _mark_skinned_node_animation_skip(state, unit if isinstance(unit, list) else [unit])
    if isinstance(unit, list):
        return _create_grouped_mesh_object(unit, state, collection, shading_mode)
    return _create_import_object(unit, state, collection, shading_mode)


def _create_grouped_mesh_object(
    primitives: list[MeshPrimitiveData],
    state: dict,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    first = primitives[0]
    node_objects = state[_S_NODE_OBJECTS]
    parent, use_node_parent = _mesh_node_parent(state, int(first.node_index))
    defer_animation = bool(state[_S_NODE_ANIMATION_DEFERRED])
    node_visibility_animation = bool(state[_S_HAS_NODE_VISIBILITY_ANIMATION])

    count_started_at = time.perf_counter() if profile_detail else 0.0
    total_vertex_count = sum(int(primitive.vertex_count) for primitive in primitives)
    total_loop_count = sum(int(primitive.loop_count) for primitive in primitives)
    total_face_count = sum(int(primitive.face_count) for primitive in primitives)
    count_ms = (time.perf_counter() - count_started_at) * 1000.0 if profile_detail else 0.0

    skin_joint_width = max(1, int(first.skin_joint_width or 4))
    vertices = bytearray(total_vertex_count * 3 * 4)
    indices = bytearray(total_loop_count * 4)
    loop_starts = bytearray(total_face_count * 4)
    normals = bytearray(total_loop_count * 3 * 4) if first.normals_f32 else None
    vertex_normals = bytearray(total_vertex_count * 3 * 4) if first.vertex_normals_f32 else None
    tangents = bytearray(total_loop_count * 4 * 4) if first.tangents_f32 else None
    skin_joints = bytearray(total_vertex_count * skin_joint_width * 2) if first.has_skin else None
    skin_weights = bytearray(total_vertex_count * skin_joint_width * 4) if first.has_skin else None
    attr_started_at = time.perf_counter() if profile_detail else 0.0
    uv_sets = _group_loop_float_attrs(primitives, "uv_sets")
    color_sets = _group_loop_float_attrs(primitives, "color_sets")
    has_materials = any(_has_material_data(primitive) for primitive in primitives)
    material_indices = bytearray(total_face_count * 4) if has_materials else b""
    sharp_faces = _group_wavefront_sharp_faces(primitives, total_face_count)
    attr_ms = (time.perf_counter() - attr_started_at) * 1000.0 if profile_detail else 0.0

    assemble_started_at = time.perf_counter() if profile_detail else 0.0
    vertex_offset = 0
    loop_offset = 0
    face_offset = 0
    for slot_index, primitive in enumerate(primitives):
        primitive_vertices = _buffer_view(primitive.vertices_f32, "f")
        primitive_indices = _buffer_view(primitive.indices_u32, "i")
        if primitive_vertices is None or primitive_indices is None:
            return [_create_import_object(primitive, state, collection, shading_mode)[0]]

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
    assemble_ms = (time.perf_counter() - assemble_started_at) * 1000.0 if profile_detail else 0.0

    replace_started_at = time.perf_counter() if profile_detail else 0.0
    data = replace(
        first,
        name=_group_mesh_name(first),
        vertex_count=total_vertex_count,
        loop_count=total_loop_count,
        face_count=total_face_count,
        vertices_f32=vertices,
        indices_u32=indices,
        loop_starts_i32=loop_starts,
        loop_totals_i32=b"",
        normals_f32=normals or b"",
        vertex_normals_f32=vertex_normals or b"",
        tangents_f32=tangents or b"",
        uv_sets=uv_sets,
        color_sets=color_sets,
        skin_joints_u16=skin_joints or b"",
        skin_weights_f32=skin_weights or b"",
        skin_vertex_count=total_vertex_count if first.has_skin else 0,
        sharp_faces_u8=sharp_faces,
    )
    replace_ms = (time.perf_counter() - replace_started_at) * 1000.0 if profile_detail else 0.0

    bulk_started_at = time.perf_counter() if profile_detail else 0.0
    objects = _create_grouped_mesh_object_bulk(
        data,
        primitives,
        material_indices,
        parent,
        node_objects=node_objects,
        node_data=state[_S_NODE_DATA],
        node_visibility=state[_S_NODE_VISIBILITY],
        material_cache=state[_S_MATERIAL_CACHE],
        skin_cache=state[_S_SKIN_CACHE],
        apply_transform=not use_node_parent,
        apply_animation=(not use_node_parent and not defer_animation),
        apply_skin_animation=not bool(state[_S_SKIN_ANIMATION_DEFERRED]),
        deferred_skin_animations=state[_S_DEFERRED_SKIN_ANIMATIONS],
        has_materials=has_materials,
        shading_mode=shading_mode,
        defer_custom_normals=bool(state[_S_DEFER_CUSTOM_NORMALS]),
        collection=collection,
        node_visibility_animation=node_visibility_animation,
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
        grouped.append(replace(first_attr, values_f32=values))
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
    collection: bpy.types.Collection | None = None,
    node_visibility_animation: bool = True,
) -> list[bpy.types.Object]:
    total_started_at = time.perf_counter()
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    phase_started_at = total_started_at
    detail_parts: list[str] = []
    mesh = bpy.data.meshes.new(data.name)
    mesh.vertices.add(data.vertex_count)
    mesh.loops.add(data.loop_count)
    mesh.polygons.add(data.face_count)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"alloc={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")
    if vertices is None or indices is None or loop_starts is None:
        raise RuntimeError("AssetKit native bridge returned incomplete grouped mesh buffers")
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"views={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    _set_mesh_positions(mesh, vertices)
    _set_mesh_loop_vertex_indices(mesh, indices)
    _set_mesh_loop_starts(mesh, loop_starts, int(data.loop_count), int(data.face_count))
    if loop_totals is not None and int(data.loop_count) != int(data.face_count) * 3:
        mesh.polygons.foreach_set("loop_total", _rna_i32_values(loop_totals))
    _set_mesh_material_indices(mesh, material_indices)
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

    if data.tangents_f32:
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

    if has_materials:
        for primitive in primitives:
            if not _try_defer_material_assignment(mesh, obj, primitive, material_cache, False):
                material = _create_material(primitive, material_cache)
                if material:
                    mesh.materials.append(material)
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
        units.append(group if len(group) > 1 else primitive)

    return units


def _mesh_group_key(primitive: MeshPrimitiveData) -> tuple | None:
    if int(primitive.primitive_type) not in (AK_PRIMITIVE_TRIANGLES, AK_PRIMITIVE_POLYGONS):
        return None
    if not primitive.mesh_key or not primitive.vertices_f32 or not primitive.indices_u32:
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
    mesh_key = 0 if int(getattr(primitive, "file_type", 0) or 0) == AK_FILE_TYPE_WAVEFRONT else int(primitive.mesh_key)

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


def _mesh_data_reuse_key(primitive: MeshPrimitiveData, shading_mode: str) -> tuple | None:
    if int(primitive.primitive_type) != AK_PRIMITIVE_TRIANGLES:
        return None
    if not primitive.vertices_f32 or not primitive.indices_u32:
        return None
    if int(primitive.loop_count) != int(primitive.face_count) * 3:
        return None
    if primitive.instance_count or primitive.has_gsplat:
        return None
    if primitive.has_skin or primitive.morph_targets or primitive.morph_anim_channels:
        return None
    if primitive.material_anim_channels or primitive.material_variants:
        return None
    if primitive.point_attr_count:
        return None

    geometry_key = int(getattr(primitive, "geometry_key", 0) or 0)
    mesh_key = int(primitive.mesh_key or 0)
    if geometry_key:
        source_key = (1, geometry_key)
    elif mesh_key:
        source_key = (0, mesh_key, int(primitive.primitive_index))
    else:
        return None

    return (
        source_key,
        int(primitive.primitive_mode),
        int(primitive.vertex_count),
        int(primitive.loop_count),
        int(primitive.face_count),
        bool(primitive.normals_f32),
        bool(primitive.vertex_normals_f32),
        bool(primitive.tangents_f32),
        bool(primitive.smooth_shading) if _uses_wavefront_smoothing(primitive) else False,
        _loop_attr_signature(primitive.uv_sets),
        _loop_attr_signature(primitive.color_sets),
        str(shading_mode or "AUTO").upper(),
    )


def _loop_attr_signature(attrs: list[LoopFloatAttributeData] | None) -> tuple:
    return tuple((attr.name, int(attr.set), int(attr.width)) for attr in (attrs or ()))


def _import_result_objects(mesh_objects: list[bpy.types.Object], state: dict) -> list[bpy.types.Object]:
    if mesh_objects:
        return mesh_objects

    node_objects = state.get(_S_NODE_OBJECTS) or {}
    return [
        obj
        for obj in node_objects.values()
        if getattr(obj, "type", "") in {"CAMERA", "LIGHT"}
    ]


def _select_imported_objects(objects: list[bpy.types.Object]) -> None:
    if not objects:
        return

    _clear_selection()
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]


def _finish_import(
    objects: list[bpy.types.Object],
    focus_mode: str,
    placement_mode: str,
    root_objects: list[bpy.types.Object],
    scene_was_empty: bool,
    collection: bpy.types.Collection,
    focus_camera: bpy.types.Object | None,
    select_imported: bool,
    set_viewport_shading: bool,
    clean_viewport_overlays: bool,
    existing_actions: set[bpy.types.Action] | None,
) -> None:
    _apply_import_placement(objects, placement_mode, root_objects)
    if select_imported:
        _select_imported_objects(objects)
    _focus_imported_objects(objects, focus_mode, scene_was_empty, collection, focus_camera)
    if set_viewport_shading and scene_was_empty:
        _set_viewport_material_preview(clean_viewport_overlays)
    _fit_timeline_to_new_actions(existing_actions)


def _clear_selection() -> None:
    try:
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action="DESELECT")
            return
    except Exception:
        pass

    for obj in bpy.context.scene.objects:
        obj.select_set(False)


class _SelectionState:
    def __init__(self) -> None:
        self.selected = list(bpy.context.selected_objects)
        self.active = bpy.context.view_layer.objects.active

    def restore(self) -> None:
        _clear_selection()
        for obj in self.selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if self.active and self.active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = self.active


def _temporary_selection(objects: list[bpy.types.Object]) -> _SelectionState:
    selection = _SelectionState()
    _select_imported_objects(objects)
    return selection


def _set_viewport_material_preview(clean_overlays: bool = False) -> None:
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D" or not hasattr(space, "shading"):
                    continue
                try:
                    space.shading.color_type = "MATERIAL"
                    space.shading.type = "MATERIAL"
                    if not clean_overlays:
                        continue
                    overlay = getattr(space, "overlay", None)
                    if overlay:
                        if hasattr(overlay, "show_wireframes"):
                            overlay.show_wireframes = False
                        if hasattr(overlay, "wireframe_opacity"):
                            overlay.wireframe_opacity = 0.0
                        if hasattr(overlay, "show_relationship_lines"):
                            overlay.show_relationship_lines = False
                except Exception:
                    pass


def _snapshot_actions(enabled: bool) -> set[bpy.types.Action] | None:
    return set(bpy.data.actions) if enabled else None


def _fit_timeline_to_new_actions(existing_actions: set[bpy.types.Action] | None) -> None:
    if existing_actions is None:
        return

    if _ACTION_FRAME_RANGES:
        min_frame = min(frame_range[0] for frame_range in _ACTION_FRAME_RANGES.values())
        max_frame = max(frame_range[1] for frame_range in _ACTION_FRAME_RANGES.values())
        _set_scene_frame_range(min_frame, max_frame)
        return

    min_frame: float | None = None
    max_frame: float | None = None
    for action in bpy.data.actions:
        if action in existing_actions:
            continue
        frame_range = _action_frame_range(action)
        if frame_range is None:
            continue
        start, end = frame_range
        min_frame = start if min_frame is None else min(min_frame, start)
        max_frame = end if max_frame is None else max(max_frame, end)

    if min_frame is None or max_frame is None:
        return

    _set_scene_frame_range(min_frame, max_frame)


def _set_scene_frame_range(min_frame: float, max_frame: float) -> None:
    scene = bpy.context.scene
    scene.frame_start = int(math.floor(max(0.0, min_frame)))
    scene.frame_end = max(scene.frame_start + 1, int(math.ceil(max_frame)))
    try:
        scene.frame_current = scene.frame_start
    except Exception:
        pass


def _action_frame_range(action: bpy.types.Action) -> tuple[float, float] | None:
    cached = _ACTION_FRAME_RANGES.get(action.as_pointer())
    if cached is not None:
        return cached

    for attr in ("curve_frame_range", "frame_range"):
        value = getattr(action, attr, None)
        if value is None:
            continue
        try:
            start = float(value[0])
            end = float(value[1])
        except (TypeError, ValueError, IndexError):
            continue
        if end > start:
            return start, end

    min_frame: float | None = None
    max_frame: float | None = None
    for fcurve in _iter_action_fcurves(action):
        for key in fcurve.keyframe_points:
            frame = float(key.co.x)
            min_frame = frame if min_frame is None else min(min_frame, frame)
            max_frame = frame if max_frame is None else max(max_frame, frame)

    if min_frame is not None and max_frame is not None:
        return min_frame, max_frame

    return None


def _iter_action_fcurves(action: bpy.types.Action):
    fcurves = getattr(action, "fcurves", None)
    if fcurves:
        yield from fcurves
        return

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except Exception:
                    continue
                yield from getattr(channelbag, "fcurves", []) or []


def _channelbag_for_fcurve(action: bpy.types.Action, fcurve: bpy.types.FCurve):
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for slot in getattr(action, "slots", []) or []:
                try:
                    channelbag = strip.channelbag(slot)
                except Exception:
                    continue
                for candidate in getattr(channelbag, "fcurves", []) or []:
                    if candidate == fcurve:
                        return channelbag
    return None


def _set_fcurve_group(fcurve: bpy.types.FCurve, channelbag, group_name: str) -> None:
    if not group_name or not channelbag:
        return
    try:
        current = getattr(fcurve, "group", None)
        if current is not None and getattr(current, "name", None) == group_name:
            return
    except Exception:
        pass
    try:
        fcurve.group = _channelbag_group(channelbag, group_name)
    except Exception:
        pass


def _new_channelbag_fcurve(channelbag, data_path: str, index: int | None, group_name: str):
    try:
        if index is None:
            return channelbag.fcurves.new(data_path=data_path, group_name=group_name)
        return channelbag.fcurves.new(data_path=data_path, index=index, group_name=group_name)
    except TypeError:
        if index is None:
            fcurve = channelbag.fcurves.new(data_path=data_path)
        else:
            fcurve = channelbag.fcurves.new(data_path=data_path, index=index)
        _set_fcurve_group(fcurve, channelbag, group_name)
        return fcurve


def _channelbag_group(channelbag, group_name: str):
    key = (id(channelbag), group_name)
    group = _ACTION_CHANNEL_GROUPS.get(key)
    if group is not None:
        return group
    if group_name not in channelbag.groups:
        group = channelbag.groups.new(group_name)
    else:
        group = channelbag.groups[group_name]
    _ACTION_CHANNEL_GROUPS[key] = group
    return group


def _focus_imported_objects(
    objects: list[bpy.types.Object],
    focus_mode: str,
    scene_was_empty: bool,
    collection: bpy.types.Collection,
    focus_camera: bpy.types.Object | None,
) -> None:
    if focus_mode == "NEVER":
        return
    if focus_mode == "EMPTY_SCENE" and not scene_was_empty:
        return
    if not objects:
        return

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    bounds = _object_bounds(objects)
    if bounds is None:
        return

    _frame_viewports(bounds, objects)
    if scene_was_empty:
        _frame_camera(bounds, collection, focus_camera)


def _apply_import_placement(
    objects: list[bpy.types.Object],
    placement_mode: str,
    root_objects: list[bpy.types.Object] | None = None,
) -> None:
    if placement_mode == "AS_AUTHORED" or not objects:
        return

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    bounds = _object_bounds(objects)
    if bounds is None:
        return

    minimum, maximum = bounds
    center = (minimum + maximum) * 0.5
    cursor = bpy.context.scene.cursor.location
    if placement_mode == "ORIGIN_GROUND":
        target = Vector((0.0, 0.0, 0.0))
    elif placement_mode == "CURSOR_GROUND":
        target = Vector((cursor.x, cursor.y, cursor.z))
    else:
        return

    offset = Vector((target.x - center.x, target.y - center.y, target.z - minimum.z))
    if offset.length <= 1e-9:
        return

    for root in _placement_roots(objects, root_objects or []):
        try:
            matrix = root.matrix_world.copy()
            matrix.translation += offset
            root.matrix_world = matrix
        except Exception:
            root.location += offset

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _placement_roots(
    objects: list[bpy.types.Object],
    root_objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    roots = [obj for obj in root_objects if obj and obj.name in bpy.data.objects]
    if roots:
        return _unique_objects(roots)

    object_set = set(objects)
    roots = []
    for obj in objects:
        root = obj
        while root.parent and root.parent in object_set:
            root = root.parent
        roots.append(root)
    return _unique_objects(roots)


def _unique_objects(objects: list[bpy.types.Object]) -> list[bpy.types.Object]:
    seen = set()
    unique = []
    for obj in objects:
        key = obj.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        unique.append(obj)
    return unique


def _object_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector] | None:
    minimum: Vector | None = None
    maximum: Vector | None = None
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
    except Exception:
        depsgraph = None

    for obj in objects:
        if obj.type != "MESH" or not obj.bound_box or _is_hidden_for_bounds(obj):
            continue
        eval_obj = obj
        if depsgraph is not None:
            try:
                eval_obj = obj.evaluated_get(depsgraph)
            except Exception:
                eval_obj = obj
        matrix = eval_obj.matrix_world
        for corner in eval_obj.bound_box:
            point = matrix @ Vector(corner)
            if minimum is None:
                minimum = point.copy()
                maximum = point.copy()
            else:
                minimum.x = min(minimum.x, point.x)
                minimum.y = min(minimum.y, point.y)
                minimum.z = min(minimum.z, point.z)
                maximum.x = max(maximum.x, point.x)
                maximum.y = max(maximum.y, point.y)
                maximum.z = max(maximum.z, point.z)

    if minimum is None or maximum is None:
        return None
    return minimum, maximum


def _is_hidden_for_bounds(obj: bpy.types.Object) -> bool:
    current = obj
    while current is not None:
        helper_hidden = bool(current.get("assetkit_helper_hidden"))
        try:
            if current.hide_get() and not helper_hidden:
                return True
        except Exception:
            pass
        if (current.hide_viewport or current.hide_render) and not helper_hidden:
            return True
        current = current.parent
    return False


def _bounds_corners(bounds: tuple[Vector, Vector]) -> list[Vector]:
    minimum, maximum = bounds
    return [
        Vector((x, y, z))
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]


def _frame_viewports(
    bounds: tuple[Vector, Vector],
    objects: list[bpy.types.Object] | None = None,
) -> None:
    window_manager = bpy.context.window_manager
    minimum, maximum = bounds
    radius = max((maximum - minimum).length * 0.5, 1.0e-6)
    selection = _temporary_selection(objects) if objects else None
    for window in getattr(window_manager, "windows", []):
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((item for item in area.regions if item.type == "WINDOW"), None)
            space = next((item for item in area.spaces if item.type == "VIEW_3D"), None)
            if region is None or space is None:
                continue
            _set_viewport_clip(space, radius)
            try:
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    bpy.ops.view3d.view_selected(use_all_regions=False)
                    _set_view_distance(space, bounds, radius)
            except Exception:
                pass
    if selection:
        selection.restore()


def _set_viewport_clip(space: bpy.types.SpaceView3D, radius: float) -> None:
    space.clip_start = _clip_start_for_radius(radius)
    space.clip_end = _clip_end_for_radius(radius)


def _set_view_distance(
    space: bpy.types.SpaceView3D,
    bounds: tuple[Vector, Vector],
    radius: float,
) -> None:
    region_3d = getattr(space, "region_3d", None)
    if region_3d is None:
        return
    try:
        minimum, maximum = bounds
        region_3d.view_location = (minimum + maximum) * 0.5
        target = radius * _viewport_distance_factor(radius)
        current = float(getattr(region_3d, "view_distance", 0.0) or 0.0)
        if current <= 0.0 or current > target * 2.0 or current < target * 0.35:
            region_3d.view_distance = target
    except Exception:
        pass


def _viewport_distance_factor(radius: float) -> float:
    return 1.9 + 2.0 / (1.0 + radius / 8.0)


def _frame_camera(
    bounds: tuple[Vector, Vector],
    collection: bpy.types.Collection,
    camera_obj: bpy.types.Object | None,
) -> None:
    scene = bpy.context.scene
    if camera_obj is None:
        camera = bpy.data.cameras.new("AssetKit Camera")
        camera_obj = bpy.data.objects.new("AssetKit Camera", camera)
        collection.objects.link(camera_obj)
        scene.camera = camera_obj
    elif scene.camera is None:
        scene.camera = camera_obj

    minimum, maximum = bounds
    center = (minimum + maximum) * 0.5
    size = maximum - minimum
    radius = max(size.length * 0.5, 1.0e-6)
    direction = Vector((1.6, -2.2, 1.25)).normalized()

    camera = camera_obj.data
    camera_obj.rotation_euler = (center - (center + direction)).to_track_quat("-Z", "Y").to_euler()
    if camera.type == "ORTHO":
        camera.ortho_scale = max(size.x, size.y, size.z, 1.0) * 1.35
        distance = radius * 3.0
        camera_obj.location = center + direction * distance
    else:
        distance = _camera_fit_distance(camera, direction, center, _bounds_corners(bounds)) * 1.25
        camera_obj.location = center + direction * distance
    _fit_camera_with_blender(camera_obj, bounds)
    _ensure_camera_contains_bounds(scene, camera_obj, bounds)
    _set_camera_clip(camera_obj, bounds, radius)


def _fit_camera_with_blender(
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
) -> None:
    if not hasattr(camera_obj, "camera_fit_coords"):
        return

    coords: list[float] = []
    for corner in _bounds_corners(bounds):
        coords.extend((corner.x, corner.y, corner.z))

    try:
        location, scale = camera_obj.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), coords)
    except Exception:
        return

    camera_obj.location = location
    if camera_obj.data.type == "ORTHO" and scale > 0.0:
        camera_obj.data.ortho_scale = scale * 1.15


def _camera_fit_distance(
    camera: bpy.types.Camera,
    direction: Vector,
    center: Vector,
    corners: list[Vector],
) -> float:
    rotation = (-direction).to_track_quat("-Z", "Y").to_matrix().inverted()
    half_angle_x = max(getattr(camera, "angle_x", camera.angle) * 0.5, math.radians(5.0))
    half_angle_y = max(getattr(camera, "angle_y", camera.angle) * 0.5, math.radians(5.0))
    tan_x = max(math.tan(half_angle_x), 0.01)
    tan_y = max(math.tan(half_angle_y), 0.01)
    distance = 0.5

    for corner in corners:
        local = rotation @ (corner - center)
        distance = max(distance, local.z + abs(local.x) / tan_x, local.z + abs(local.y) / tan_y)

    return max(distance, 0.5)


def _ensure_camera_contains_bounds(
    scene: bpy.types.Scene,
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
) -> None:
    camera = camera_obj.data
    corners = _bounds_corners(bounds)
    margin = 0.06

    for _ in range(8):
        try:
            bpy.context.view_layer.update()
            projected = [world_to_camera_view(scene, camera_obj, corner) for corner in corners]
        except Exception:
            return

        if all(margin <= point.x <= 1.0 - margin
               and margin <= point.y <= 1.0 - margin
               and point.z > 0.0
               for point in projected):
            return

        if camera.type == "ORTHO":
            camera.ortho_scale *= 1.2
        else:
            target = sum(corners, Vector()) / len(corners)
            offset = camera_obj.location - target
            if offset.length <= 0.0:
                return
            camera_obj.location = target + offset * 1.2
            camera_obj.rotation_euler = (target - camera_obj.location).to_track_quat("-Z", "Y").to_euler()


def _set_camera_clip(
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
    radius: float,
) -> None:
    camera = camera_obj.data
    forward = camera_obj.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
    depths = [(corner - camera_obj.location).dot(forward) for corner in _bounds_corners(bounds)]
    positive_depths = [depth for depth in depths if depth > 0.0]
    if not positive_depths:
        camera.clip_start = _clip_start_for_radius(radius)
        camera.clip_end = _clip_end_for_radius(radius)
        return

    near_depth = max(min(positive_depths) * 0.25, _clip_start_for_radius(radius))
    far_depth = max(max(positive_depths) + radius * 2.0, _clip_end_for_radius(radius))
    camera.clip_start = min(near_depth, 10_000.0)
    camera.clip_end = min(far_depth, 10_000_000.0)


def _clip_start_for_radius(radius: float) -> float:
    return max(radius / 100_000.0, 0.001)


def _clip_end_for_radius(radius: float) -> float:
    return min(max(radius * 32.0, 1000.0), 10_000_000.0)


class _ProgressiveImportJob:
    def __init__(
        self,
        filepath: str,
        library_path: str,
        load_options: dict | None,
        collection: bpy.types.Collection,
        batch_size: int,
        focus_mode: str,
        placement_mode: str,
        scene_was_empty: bool,
        focus_camera: bpy.types.Object | None,
        select_imported: bool,
        shading_mode: str,
        set_viewport_shading: bool,
        clean_viewport_overlays: bool,
        existing_actions: set[bpy.types.Action] | None,
        stream: object | None = None,
        prefer_grouped: bool = False,
    ) -> None:
        self.filepath = filepath
        self.library_path = library_path
        self.load_options = load_options
        self.collection = collection
        self.batch_size = batch_size
        self.focus_mode = focus_mode
        self.placement_mode = placement_mode
        self.scene_was_empty = scene_was_empty
        self.focus_camera = focus_camera
        self.select_imported = select_imported
        self.shading_mode = shading_mode
        self.set_viewport_shading = set_viewport_shading
        self.clean_viewport_overlays = clean_viewport_overlays
        self.existing_actions = existing_actions
        self.stream = stream
        self.prefer_grouped = prefer_grouped
        self.texture_load_mode = _texture_load_mode(load_options)
        self.defer_custom_normals = _defer_custom_normals(load_options, shading_mode)
        self.scene_nodes: list[SceneNodeData] = []
        self.doc_extra: object | None = getattr(stream, "doc_extra", None)
        self.scene_extra: object | None = getattr(stream, "scene_extra", None)
        self.scene_info: dict = _scene_info_from_loaded(stream)
        self.doc_images: list[dict] = list(getattr(stream, "images", []) or [])
        self.required_node_indices: list[int] | None = getattr(stream, "required_node_indices", None)
        self.mesh_count = 0
        self.pending_primitives: deque[MeshPrimitiveData] = deque()
        self.deferred_primitives: deque[MeshPrimitiveData] = deque()
        self.objects: list[bpy.types.Object] = []
        self.state: dict | None = None
        self.error: BaseException | None = None
        self.error_traceback = ""
        self.producer_done = False
        self.load_started_at = 0.0
        self.build_started_at = 0.0
        self.first_object_at = 0.0
        self.created_count = 0
        self.progress_active = False
        self.profile_detail = _PROFILE_MATERIAL_STATS is not None
        self._queue: queue.SimpleQueue[list[MeshPrimitiveData]] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._produce, name="AssetKit progressive import", daemon=True)

    def start(self) -> None:
        self.load_started_at = time.perf_counter()
        _ACTIVE_IMPORT_JOBS.append(self)
        self._progress_begin()
        self._status_set("AssetKit is importing...")
        start_loading_hud("AssetKit is importing", delay=0.0)
        self._thread.start()
        bpy.app.timers.register(self._timer, first_interval=0.001)

    def _produce(self) -> None:
        try:
            if not self.library_path:
                open_started_at = time.perf_counter() if self.profile_detail else 0.0
                stream = self.stream or native_open_scene_stream(self.filepath, self.load_options)
                if stream is not None:
                    if self.profile_detail:
                        _profile_log(
                            "producer open_scene "
                            f"elapsed={(time.perf_counter() - open_started_at) * 1000.0:.3f}ms "
                            f"meshes={stream.mesh_count} nodes={len(stream.nodes)}"
                        )
                    self.scene_nodes = stream.nodes
                    self.doc_extra = stream.doc_extra
                    self.scene_extra = stream.scene_extra
                    self.doc_images = list(stream.images or [])
                    self.scene_info = _scene_info_from_loaded(stream)
                    self.required_node_indices = stream.required_node_indices
                    self.mesh_count = stream.mesh_count
                    start = 0
                    producer_batch_size = max(self.batch_size * 4, 256)
                    while start < stream.mesh_count:
                        if self.prefer_grouped and stream.mesh_count <= self.batch_size:
                            count = stream.mesh_count
                        elif start == 0:
                            count = min(_PROGRESSIVE_FIRST_BATCH_SIZE, self.batch_size)
                        else:
                            count = producer_batch_size
                        batch_started_at = time.perf_counter() if self.profile_detail else 0.0
                        batch = stream.read_mesh_batch(start, count)
                        if batch:
                            self._queue.put(batch)
                        if self.profile_detail:
                            _profile_log(
                                "producer batch "
                                f"start={start} requested={count} got={len(batch)} "
                                f"elapsed={(time.perf_counter() - batch_started_at) * 1000.0:.3f}ms"
                            )
                        start += count
                    return

            fallback_started_at = time.perf_counter() if self.profile_detail else 0.0
            primitives, scene_nodes, doc_extra, scene_extra, scene_info, doc_images = _load_assetkit_scene(
                self.filepath,
                self.library_path,
                self.load_options,
            )
            if self.profile_detail:
                _profile_log(
                    "producer fallback_load "
                    f"elapsed={(time.perf_counter() - fallback_started_at) * 1000.0:.3f}ms "
                    f"meshes={len(primitives)} nodes={len(scene_nodes)}"
                )
            self.scene_nodes = scene_nodes
            self.doc_extra = doc_extra
            self.scene_extra = scene_extra
            self.scene_info = scene_info
            self.doc_images = doc_images
            self.required_node_indices = None
            self.mesh_count = len(primitives)
            if primitives:
                self._queue.put(primitives)
        except BaseException as exc:
            self.error = exc
            self.error_traceback = traceback.format_exc()
        finally:
            self.producer_done = True

    def _timer(self) -> float | None:
        try:
            return self._step()
        except BaseException:
            print(traceback.format_exc())
            self._finish()
            return None

    def _step(self) -> float | None:
        self._drain_queue()

        if self.error:
            print(self.error_traceback or str(self.error))
            self._finish()
            return None

        if self._waiting_for_grouped_auto_load():
            self._status_set("AssetKit is importing...")
            update_loading_hud("AssetKit is importing")
            return 0.001

        if self.state is None:
            if not self.pending_primitives and not self.deferred_primitives and not self.producer_done:
                self._status_set("AssetKit is importing...")
                update_loading_hud("AssetKit is importing")
                return 0.01
            self.build_started_at = time.perf_counter()
            coord_probe = [self.pending_primitives[0]] if self.pending_primitives else list(self.deferred_primitives)[:1]
            scene_build_started_at = time.perf_counter() if self.profile_detail else 0.0
            self.state = _begin_scene_build(
                coord_probe,
                self.scene_nodes,
                self.collection,
                self.doc_extra,
                self.scene_extra,
                self.scene_info,
                self.doc_images,
                apply_node_animation=False,
                defer_custom_normals=self.defer_custom_normals,
                dynamic_skin_animation_skip=True,
                create_all_nodes=self.required_node_indices is None and not self.producer_done,
                required_node_indices=(
                    self.required_node_indices
                    if self.required_node_indices is not None
                    else _REQUIRED_NODE_INDICES_AUTO
                ),
            )
            if self.profile_detail:
                _profile_log(
                    "begin_scene_build "
                    f"nodes={len(self.scene_nodes)} "
                    f"pending={len(self.pending_primitives)} deferred={len(self.deferred_primitives)} "
                    f"elapsed={(time.perf_counter() - scene_build_started_at) * 1000.0:.3f}ms"
                )
            self._status_set("AssetKit is importing...")
            update_loading_hud("AssetKit is importing")
            if not self.pending_primitives and not self.deferred_primitives and self.producer_done:
                self._finish_success()
                return None

        if self._can_build_grouped_auto_slice():
            self._build_grouped_auto_slice()
            if self.producer_done and not self.pending_primitives and not self.deferred_primitives:
                self._finish_success()
                return None
            self._progress_update()
            return 0.001

        if not self.pending_primitives and self.deferred_primitives and not self.producer_done:
            self._status_set("AssetKit is importing...")
            update_loading_hud("AssetKit is importing")
            self._drain_queue()
            return 0.005

        created_this_step = 0
        slice_started_at = time.perf_counter()
        global _ACTIVE_TEXTURE_LOAD_MODE
        previous_texture_load_mode = _ACTIVE_TEXTURE_LOAD_MODE
        _ACTIVE_TEXTURE_LOAD_MODE = self.texture_load_mode
        try:
            while (self.pending_primitives or self.deferred_primitives) and created_this_step < self.batch_size:
                primitive = (
                    self.pending_primitives.popleft()
                    if self.pending_primitives
                    else self.deferred_primitives.popleft()
                )
                created_objects = _create_import_object(
                    primitive,
                    self.state,
                    self.collection,
                    self.shading_mode,
                )
                self.objects.extend(created_objects)
                self.created_count += 1
                created_this_step += 1
                if self.first_object_at == 0.0:
                    self.first_object_at = time.perf_counter()
                if time.perf_counter() - slice_started_at >= _PROGRESSIVE_TIME_BUDGET:
                    break
        finally:
            _ACTIVE_TEXTURE_LOAD_MODE = previous_texture_load_mode

        if created_this_step and self.profile_detail:
            _profile_log(
                "build_slice "
                f"created={created_this_step} "
                f"pending={len(self.pending_primitives)} deferred={len(self.deferred_primitives)} "
                f"elapsed={(time.perf_counter() - slice_started_at) * 1000.0:.3f}ms"
            )

        self._drain_queue()
        if self.producer_done and not self.pending_primitives and not self.deferred_primitives:
            self._finish_success()
            return None

        self._progress_update()
        return 0.001

    def _drain_queue(self) -> None:
        while True:
            try:
                batch = self._queue.get_nowait()
            except queue.Empty:
                return
            for primitive in batch:
                if primitive.primitive_type in {AK_PRIMITIVE_LINES, AK_PRIMITIVE_POINTS}:
                    self.deferred_primitives.append(primitive)
                else:
                    self.pending_primitives.append(primitive)

    def _waiting_for_grouped_auto_load(self) -> bool:
        return (
            self.prefer_grouped
            and not self.producer_done
            and self.mesh_count > 0
            and self.mesh_count <= self.batch_size
        )

    def _can_build_grouped_auto_slice(self) -> bool:
        return (
            self.prefer_grouped
            and self.producer_done
            and self.mesh_count > 0
            and self.mesh_count <= self.batch_size
            and (self.pending_primitives or self.deferred_primitives)
        )

    def _build_grouped_auto_slice(self) -> None:
        if self.state is None:
            return

        slice_started_at = time.perf_counter()
        primitives = list(self.pending_primitives)
        deferred = list(self.deferred_primitives)
        self.pending_primitives.clear()
        self.deferred_primitives.clear()

        units = _mesh_import_units(primitives)
        if deferred:
            units.extend(deferred)

        created_units = 0
        created_primitives = 0
        global _ACTIVE_TEXTURE_LOAD_MODE
        previous_texture_load_mode = _ACTIVE_TEXTURE_LOAD_MODE
        _ACTIVE_TEXTURE_LOAD_MODE = self.texture_load_mode
        try:
            for unit in units:
                created_objects = _create_import_unit(
                    unit,
                    self.state,
                    self.collection,
                    self.shading_mode,
                )
                self.objects.extend(created_objects)
                created_units += 1
                created_primitives += len(unit) if isinstance(unit, list) else 1
                if self.first_object_at == 0.0 and created_objects:
                    self.first_object_at = time.perf_counter()
        finally:
            _ACTIVE_TEXTURE_LOAD_MODE = previous_texture_load_mode

        self.created_count += created_primitives
        if self.profile_detail:
            _profile_log(
                "build_grouped_auto_slice "
                f"units={created_units} primitives={created_primitives} "
                f"elapsed={(time.perf_counter() - slice_started_at) * 1000.0:.3f}ms"
            )

    def _finish_success(self) -> None:
        _apply_deferred_bind_pose_skins(self.state)
        _apply_deferred_scene_node_animations(self.state)
        _apply_deferred_skin_animations(self.state)
        _finish_import(
            self.objects,
            self.focus_mode,
            self.placement_mode,
            self.state[_S_ROOT_OBJECTS] if self.state else [],
            self.scene_was_empty,
            self.collection,
            self.focus_camera,
            self.select_imported,
            self.set_viewport_shading,
            self.clean_viewport_overlays,
            self.existing_actions,
        )
        finished_at = time.perf_counter()
        load_seconds = self.build_started_at - self.load_started_at
        build_seconds = finished_at - self.build_started_at
        first_object_seconds = self.first_object_at - self.load_started_at if self.first_object_at else 0.0
        if self.profile_detail:
            _profile_log(
                "progressive finish "
                f"objects={len(_import_result_objects(self.objects, self.state or {}))} "
                f"mesh_cache_hits={int(self.state[_S_MESH_CACHE_HITS]) if self.state else 0} "
                f"first_object={first_object_seconds:.3f}s "
                f"load={load_seconds:.3f}s build={build_seconds:.3f}s "
                f"total={finished_at - self.load_started_at:.3f}s"
            )
            _log_material_profile("progressive")
        self._finish()

    def _finish(self) -> None:
        self._progress_end()
        self._status_clear()
        finish_loading_hud()
        if self in _ACTIVE_IMPORT_JOBS:
            _ACTIVE_IMPORT_JOBS.remove(self)

    def _progress_begin(self) -> None:
        if self.progress_active:
            return
        try:
            bpy.context.window_manager.progress_begin(0, max(1, self.mesh_count or len(self.pending_primitives)))
            self.progress_active = True
        except Exception:
            self.progress_active = False

    def _progress_update(self) -> None:
        if not self.progress_active:
            return
        try:
            bpy.context.window_manager.progress_update(self.created_count)
        except Exception:
            self.progress_active = False

    def _progress_end(self) -> None:
        if not self.progress_active:
            return
        try:
            bpy.context.window_manager.progress_end()
        except Exception:
            pass
        self.progress_active = False

    def _status_set(self, text: str) -> None:
        try:
            workspace = bpy.context.workspace
            if workspace:
                workspace.status_text_set(text)
        except Exception:
            pass

    def _status_clear(self) -> None:
        try:
            workspace = bpy.context.workspace
            if workspace:
                workspace.status_text_set(None)
        except Exception:
            pass


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
            collection=collection,
            object_material_slot=object_material_slot,
            node_visibility_animation=node_visibility_animation,
        )

    mesh = bpy.data.meshes.new(data.name)
    mesh.from_pydata(data.vertices, [], data.faces)
    mesh.update(calc_edges=False)

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

    profile_detail = _PROFILE_MATERIAL_STATS is not None
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
    if data.edge_count and data.edges_u32:
        mesh.edges.add(data.edge_count)
    mesh.polygons.add(data.face_count)
    lap_detail("alloc")

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    edges = _buffer_view(data.edges_u32, "i") if data.edge_count and data.edges_u32 else None
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")
    lap_detail("views")

    if vertices is None or indices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete mesh buffers")
    if loop_starts is None:
        loop_starts = _triangle_loop_starts(int(data.loop_count))

    _set_mesh_positions(mesh, vertices)
    _set_mesh_loop_vertex_indices(mesh, indices)
    if edges is not None:
        _set_mesh_edges(mesh, edges)
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

    if data.tangents_f32:
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
    profile_detail = _PROFILE_MATERIAL_STATS is not None
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
        if not _try_defer_material_assignment(mesh, obj, data, material_cache, object_material_slot):
            material = _create_material(data, material_cache)
            if material:
                if object_material_slot:
                    _assign_object_material_slot(obj, material)
                else:
                    mesh.materials.append(material)
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


def _try_defer_material_assignment(
    mesh: bpy.types.Mesh,
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    material_cache: dict[object, object] | None,
    object_material_slot: bool,
) -> bool:
    if _ACTIVE_TEXTURE_LOAD_MODE != "DEFERRED":
        return False

    classic_deferred = False
    if _has_material_data(data):
        color_attr = _color_attribute_name(data)
        base_color = _material_base_color(data)
        if _can_use_classic_texture_fast_material(data, color_attr):
            classic_deferred = True
            cache_key = _material_cache_key(data)
        else:
            fast_key = _fast_simple_native_base_color_texture_key(data)
            if fast_key is None:
                fast_key = _fast_base_color_texture_visual_key(data, "")
            if fast_key is not None:
                cache_key = fast_key
                color_attr = ""
                base_color = data.base_color
            elif _can_use_base_color_texture_fast_material(data, color_attr, base_color):
                cache_key = _material_cache_key(data)
            else:
                return False
    else:
        fast_key = _fast_simple_native_base_color_texture_key(data)
        if fast_key is None:
            fast_key = _fast_base_color_texture_visual_key(data, "")
        if fast_key is None:
            return False
        cache_key = fast_key
        color_attr = ""
        base_color = data.base_color

    cached = material_cache.get(cache_key) if material_cache is not None else None
    if isinstance(cached, _DeferredMaterialSpec):
        spec = cached
    elif cached is not None:
        if object_material_slot:
            _assign_object_material_slot(obj, cached)
        else:
            mesh.materials.append(cached)
        return True
    else:
        material_name = data.material_name or f"{data.name}_Material"
        if data.material_name and color_attr:
            material_name = f"{material_name}_{color_attr}"
        if classic_deferred:
            spec = _DeferredMaterialSpec(
                material_name,
                material_cache,
                cache_key,
                data.base_color_texture,
                _texture_info(data, "base_color"),
                base_color,
                0.0,
                _classic_roughness(data.specular_strength),
                _is_double_sided_material(data),
                classic=True,
                normal_path=data.normal_texture,
                normal_tex_info=_texture_info(data, "normal"),
                normal_scale=float(data.normal_scale),
                specular=_classic_specular(data),
                has_specular_tint=_has_specular(data),
                specular_color=tuple(data.specular_color),
                has_emission=_has_emission(data),
                emissive_color=tuple(data.emissive_color),
                emissive_strength=_emission_strength(data),
                ior=_material_ior(data),
            )
        else:
            spec = _DeferredMaterialSpec(
                material_name,
                material_cache,
                cache_key,
                data.base_color_texture,
                _texture_info(data, "base_color"),
                base_color,
                float(data.metallic),
                float(data.roughness),
                _is_double_sided_material(data),
            )
        if material_cache is not None:
            material_cache[cache_key] = spec
        _queue_deferred_material_slot(spec)

    slot_index = -1
    spec.slots.append((mesh, obj if object_material_slot else None, slot_index, object_material_slot))
    return True


def _ensure_object_material_slot(mesh: bpy.types.Mesh) -> int:
    if not mesh.materials:
        mesh.materials.append(None)
    return 0


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
                    _set_render_color_index(mesh)
            elif not _apply_vector_attribute(mesh, name, values, "FLOAT4", "POINT"):
                _apply_split_attribute(mesh, name, values, ("x", "y", "z", "w"), "POINT")


def _is_color_attribute_name(name: str) -> bool:
    return name == "Color" or name.startswith("Color.")


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
    profile_detail = _PROFILE_MATERIAL_STATS is not None

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
            mesh.normals_split_custom_set_from_vertices(vertex_normals)
        elif isinstance(normals, memoryview):
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


def _set_render_color_index(mesh: bpy.types.Mesh) -> None:
    try:
        mesh.color_attributes.render_color_index = 0
    except Exception:
        pass


def _create_scene_nodes(
    nodes: list[SceneNodeData],
    coord_root: bpy.types.Object | None,
    collection: bpy.types.Collection,
    node_visibility: dict[int, bool] | None = None,
    apply_animation: bool = True,
    skip_animation_nodes: set[int] | None = None,
    required_indices: set[int] | None = None,
) -> dict[int, bpy.types.Object]:
    objects: dict[int, bpy.types.Object] = {}
    node_lookup = {index: node for index, node in enumerate(nodes)}
    skip_animation_nodes = skip_animation_nodes or set()
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    create_started_at = time.perf_counter() if profile_detail else 0.0

    for index, node in enumerate(nodes):
        if required_indices is not None and index not in required_indices:
            continue
        obj = _new_scene_node_object(node, index, (node_visibility or {}).get(index, node.visible))
        collection.objects.link(obj)
        objects[index] = obj

    create_ms = (time.perf_counter() - create_started_at) * 1000.0 if profile_detail else 0.0
    bind_started_at = time.perf_counter() if profile_detail else 0.0
    animation_ms = 0.0
    visibility_anim_ms = 0.0
    for index, obj in objects.items():
        node = nodes[index]
        parent = objects.get(node.parent_index) if node.parent_index >= 0 else coord_root
        _set_parent(obj, parent)
        _apply_matrix_buffer(obj, node.matrix_f32)
        has_visibility_animation = _node_has_effective_visibility_animation(index, node_lookup)
        if apply_animation and index not in skip_animation_nodes:
            anim_started_at = time.perf_counter() if profile_detail else 0.0
            _apply_animation(obj, node, skip_visibility=has_visibility_animation)
            if profile_detail:
                animation_ms += (time.perf_counter() - anim_started_at) * 1000.0
            if has_visibility_animation:
                vis_started_at = time.perf_counter() if profile_detail else 0.0
                _apply_effective_node_visibility_animation(obj, index, node_lookup)
                if profile_detail:
                    visibility_anim_ms += (time.perf_counter() - vis_started_at) * 1000.0
        if obj.type == "EMPTY":
            _hide_helper_object(obj)

    if profile_detail:
        _profile_log(
            "create_scene_nodes_detail "
            f"create_link={create_ms:.3f}ms "
            f"parent_matrix_hide={(time.perf_counter() - bind_started_at) * 1000.0:.3f}ms "
            f"animation={animation_ms:.3f}ms "
            f"visibility_animation={visibility_anim_ms:.3f}ms "
            f"nodes={len(nodes)} "
            f"created={len(objects)} "
            f"skip_animation={len(skip_animation_nodes)} "
            f"apply_animation={apply_animation}"
        )
    return objects


def _required_scene_node_indices(
    primitives: list[MeshPrimitiveData],
    nodes: list[SceneNodeData],
    skipped_animation_indices: set[int] | None = None,
) -> set[int] | None:
    if not nodes:
        return None

    required: set[int] = set()
    child_counts = _scene_node_child_counts(nodes)
    primitive_node_indices = {
        int(primitive.node_index)
        for primitive in primitives
        if int(primitive.node_index) >= 0
    }
    skipped_animation_indices = skipped_animation_indices or set()
    for primitive in primitives:
        node_index = int(primitive.node_index)
        if _primitive_node_needs_helper(node_index, nodes, child_counts):
            _add_node_ancestors(required, nodes, node_index)
        else:
            _add_node_parent_ancestors(required, nodes, node_index)

        if primitive.has_skin:
            _add_node_ancestors(required, nodes, int(primitive.skin_root_node_index))
            if not primitive.skin_mesh_in_bind_pose:
                joint_nodes = _buffer_view(primitive.skin_joint_nodes_i32, "i")
                if joint_nodes is not None:
                    count = min(len(joint_nodes), int(primitive.skin_joint_count))
                    for index in range(count):
                        _add_node_ancestors(required, nodes, int(joint_nodes[index]))

    for index, node in enumerate(nodes):
        if _scene_node_payload_can_inline(index, node, primitive_node_indices, child_counts):
            continue
        if _scene_node_requires_standalone_object(node):
            _add_node_ancestors(required, nodes, index)
        elif index not in skipped_animation_indices and (node.anim_count or node.anim_channels):
            _add_node_ancestors(required, nodes, index)

    if len(required) >= len(nodes):
        return None
    return required


def _add_node_ancestors(required: set[int], nodes: list[SceneNodeData], node_index: int) -> None:
    count = len(nodes)
    seen: set[int] = set()
    current = node_index
    while 0 <= current < count and current not in seen:
        seen.add(current)
        required.add(current)
        current = nodes[current].parent_index


def _add_node_parent_ancestors(required: set[int], nodes: list[SceneNodeData], node_index: int) -> None:
    if 0 <= node_index < len(nodes):
        _add_node_ancestors(required, nodes, nodes[node_index].parent_index)


def _scene_node_child_counts(nodes: list[SceneNodeData]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for node in nodes:
        parent_index = int(node.parent_index)
        if parent_index >= 0:
            counts[parent_index] = counts.get(parent_index, 0) + 1
    return counts


def _primitive_node_needs_helper(
    node_index: int,
    nodes: list[SceneNodeData],
    child_counts: dict[int, int],
) -> bool:
    if node_index < 0 or node_index >= len(nodes):
        return False
    if child_counts.get(node_index, 0) > 0:
        return True
    return _scene_node_requires_standalone_object(nodes[node_index])


def _scene_node_requires_standalone_object(node: SceneNodeData) -> bool:
    return bool(
        node.camera_type
        or node.light_type
        or node.layers
        or node.extra
        or node.camera_extra
        or node.camera_imager_extra
        or node.light_extra
    )


def _scene_node_payload_can_inline(
    node_index: int,
    node: SceneNodeData,
    primitive_node_indices: set[int],
    child_counts: dict[int, int],
) -> bool:
    if node_index not in primitive_node_indices:
        return False
    if child_counts.get(node_index, 0) > 0:
        return False
    return not _scene_node_requires_standalone_object(node)


def _scene_node_has_required_payload(node: SceneNodeData) -> bool:
    return bool(
        node.anim_count
        or node.anim_channels
        or _scene_node_requires_standalone_object(node)
    )


def _skinned_node_animation_skip_indices(primitives: list[MeshPrimitiveData]) -> set[int]:
    if not any(primitive.has_skin and primitive.skin_mesh_in_bind_pose for primitive in primitives):
        return set()
    skip: set[int] = set()
    _mark_skinned_node_animation_skip({_S_NODE_ANIMATION_SKIP_INDICES: skip}, primitives)
    return skip


def _mark_skinned_node_animation_skip(state: dict | None, primitives: list[MeshPrimitiveData]) -> None:
    if not state:
        return

    skip = state.get(_S_NODE_ANIMATION_SKIP_INDICES)
    if skip is None:
        skip = set()
        state[_S_NODE_ANIMATION_SKIP_INDICES] = skip
    for primitive in primitives:
        if not primitive.has_skin or not primitive.skin_mesh_in_bind_pose:
            continue

        root_index = int(primitive.skin_root_node_index)
        if root_index >= 0:
            skip.add(root_index)

        joint_nodes = _buffer_view(primitive.skin_joint_nodes_i32, "i")
        if joint_nodes is None:
            continue
        for index in range(min(len(joint_nodes), int(primitive.skin_joint_count))):
            node_index = int(joint_nodes[index])
            if node_index >= 0:
                skip.add(node_index)


def _apply_deferred_scene_node_animations(state: dict | None) -> None:
    if not state or not state.get(_S_NODE_ANIMATION_DEFERRED):
        return
    if not state.get(_S_HAS_NODE_ANIMATION) and not state.get(_S_HAS_NODE_VISIBILITY_ANIMATION):
        state[_S_NODE_ANIMATION_DEFERRED] = False
        return

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    node_objects = state.get(_S_NODE_OBJECTS) or {}
    node_data = state.get(_S_NODE_DATA) or {}
    skip_animation_nodes = state.get(_S_NODE_ANIMATION_SKIP_INDICES) or set()
    animation_ms = 0.0
    visibility_anim_ms = 0.0
    for index, node in node_data.items():
        if index in skip_animation_nodes:
            continue
        obj = node_objects.get(index)
        if not obj:
            continue
        has_visibility_animation = _node_has_effective_visibility_animation(index, node_data)
        anim_started_at = time.perf_counter() if profile_detail else 0.0
        _apply_animation(obj, node, skip_visibility=has_visibility_animation)
        if profile_detail:
            animation_ms += (time.perf_counter() - anim_started_at) * 1000.0
        if has_visibility_animation:
            vis_started_at = time.perf_counter() if profile_detail else 0.0
            _apply_effective_node_visibility_animation(obj, index, node_data)
            if profile_detail:
                visibility_anim_ms += (time.perf_counter() - vis_started_at) * 1000.0

    state[_S_NODE_ANIMATION_DEFERRED] = False
    if profile_detail:
        _profile_log(
            "deferred_scene_node_animations "
            f"nodes={len(node_data)} "
            f"animation={animation_ms:.3f}ms "
            f"visibility_animation={visibility_anim_ms:.3f}ms "
            f"total={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _apply_deferred_bind_pose_skins(state: dict | None) -> None:
    if not state:
        return

    skin_cache = state.get(_S_SKIN_CACHE) or {}
    pending = skin_cache.get(_SKIN_CACHE_DEFER_BIND_SKINS) or []
    if not pending:
        return
    skin_cache[_SKIN_CACHE_DEFER_BIND_SKINS] = []

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    groups: dict[object, list[tuple]] = {}
    for item in pending:
        _obj, data, _joint_names, joint_nodes, _node_objects, node_data, *_rest = item
        key = _bind_pose_skin_group_key(data, joint_nodes, node_data)
        groups.setdefault(key, []).append(item)

    armature_count = _create_bind_pose_skin_armature_groups(list(groups.values()))

    pending.clear()
    if profile_detail:
        _profile_log(
            "deferred_bind_pose_skins "
            f"skins={sum(len(items) for items in groups.values())} "
            f"armatures={armature_count} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _bind_pose_skin_group_key(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
) -> object:
    root_index = int(data.skin_root_node_index)
    if root_index >= 0:
        return root_index
    first_index = int(joint_nodes[0]) if len(joint_nodes) else -1
    first_node = node_data.get(first_index)
    parent_index = int(first_node.parent_index) if first_node else -1
    if parent_index >= 0:
        return ("parent", parent_index)
    count = min(len(joint_nodes), int(data.skin_joint_count))
    return ("skin", tuple(int(joint_nodes[index]) for index in range(count)))


def _create_bind_pose_skin_armature_groups(groups: list[list[tuple]]) -> int:
    groups = [items for items in groups if items]
    if not groups:
        return 0

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at

    def lap_ms() -> float:
        nonlocal phase_started_at
        if not profile_detail:
            return 0.0
        now = time.perf_counter()
        elapsed = (now - phase_started_at) * 1000.0
        phase_started_at = now
        return elapsed

    records = []
    for items in groups:
        (
            first_obj,
            first_data,
            _first_joint_names,
            first_joint_nodes,
            first_node_objects,
            first_node_data,
            collection,
            _first_apply_animation,
            _first_pose_channels,
            _first_deferred_skin_animations,
        ) = items[0]
        armature_data = bpy.data.armatures.new(f"{first_obj.name}_Armature")
        armature = bpy.data.objects.new(f"{first_obj.name}_Armature", armature_data)
        collection.objects.link(armature)
        armature_source = _skin_armature_source(
            first_data,
            first_joint_nodes,
            first_node_objects,
            first_node_data,
        ) or first_obj
        _match_object_space(armature, armature_source)
        bone_node_indices = _bind_pose_group_bone_node_indices(items)
        records.append({
            "items": items,
            "armature": armature,
            "armature_data": armature_data,
            "armature_source": armature_source,
            "node_data": first_node_data,
            "bone_node_indices": bone_node_indices,
            "bone_names_by_node": _bind_pose_group_bone_names(items),
            "rest_matrices_by_node": _skin_rest_matrices_from_assetkit_nodes(
                first_data,
                first_node_data,
                bone_node_indices,
            ),
        })
    create_ms = lap_ms()

    previous_active = bpy.context.view_layer.objects.active
    previous_selection = list(bpy.context.selected_objects)
    if previous_active and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    for obj in previous_selection:
        obj.select_set(False)
    for record in records:
        record["armature"].select_set(True)
    bpy.context.view_layer.objects.active = records[0]["armature"]
    bpy.ops.object.mode_set(mode="EDIT")
    mode_enter_ms = lap_ms()

    total_bones = 0
    for record in records:
        edit_bones = record["armature_data"].edit_bones
        bone_node_indices = record["bone_node_indices"]
        bone_names_by_node = record["bone_names_by_node"]
        rest_matrices_by_node = record["rest_matrices_by_node"]
        node_data = record["node_data"]
        for node_index in bone_node_indices:
            name = bone_names_by_node.get(node_index)
            if not name:
                continue
            bone = edit_bones.new(name)
            matrix = rest_matrices_by_node.get(node_index) or Matrix.Identity(4)
            _set_bone_from_rest_matrix(
                bone,
                matrix,
                _skin_bone_length(node_index, bone_node_indices, node_data, rest_matrices_by_node),
            )
            total_bones += 1
    create_bones_ms = lap_ms()

    for record in records:
        edit_bones = record["armature_data"].edit_bones
        bone_names_by_node = record["bone_names_by_node"]
        node_data = record["node_data"]
        for node_index, name in bone_names_by_node.items():
            parent_joint = None
            parent_index = node_data.get(node_index).parent_index if node_data.get(node_index) else -1
            while parent_index >= 0 and parent_joint is None:
                parent_name = bone_names_by_node.get(parent_index)
                if parent_name:
                    parent_joint = parent_name
                    break
                parent_node = node_data.get(parent_index)
                parent_index = parent_node.parent_index if parent_node else -1
            if parent_joint is not None and parent_joint in edit_bones:
                edit_bones[name].parent = edit_bones[parent_joint]
    parent_bones_ms = lap_ms()

    bpy.ops.object.mode_set(mode="OBJECT")
    mode_exit_ms = lap_ms()

    skin_count = 0
    for record in records:
        armature = record["armature"]
        immediate_items = [item for item in record["items"] if item[7]]
        deferred_items = [item for item in record["items"] if not item[7]]
        if immediate_items:
            root_animation_applied: set[int] = set()
            for _obj, data, _joint_names, _joint_nodes, _node_objects, node_data, _collection, _apply_animation_flag, _pose_channels, _deferred_skin_animations in immediate_items:
                root_index = int(data.skin_root_node_index)
                if root_index in root_animation_applied:
                    continue
                root_node = node_data.get(root_index)
                if root_node:
                    _apply_animation(armature, root_node)
                root_animation_applied.add(root_index)
            joint_names, joint_nodes, node_data, pose_channels = _bind_pose_group_animation_payload(immediate_items)
            _apply_bone_animations(armature, joint_names, joint_nodes, node_data, pose_channels)
        if deferred_items:
            joint_names, joint_nodes, node_data, pose_channels = _bind_pose_group_animation_payload(deferred_items)
            _obj, data, _old_joint_names, _old_joint_nodes, _node_objects, _old_node_data, _collection, _apply_animation_flag, _old_pose_channels, deferred_skin_animations = deferred_items[0]
            include_root = int(data.skin_root_node_index) >= 0
            if deferred_skin_animations is not None:
                deferred_skin_animations.append((armature, data, joint_names, joint_nodes, node_data, pose_channels, include_root))
        skin_count += len(record["items"])
    animation_ms = lap_ms()

    for record in records:
        armature = record["armature"]
        _match_object_space(armature, record["armature_source"])
        _hide_helper_object(armature)
        _hide_bind_pose_skin_helpers(record["items"])
    hide_ms = lap_ms()

    for record in records:
        armature = record["armature"]
        for obj, _data, _joint_names, _joint_nodes, _node_objects, _node_data, _collection, _apply_anim_flag, _pose_channels, _deferred_skin_animations in record["items"]:
            modifier = obj.modifiers.new("AssetKit Skin", "ARMATURE")
            modifier.object = armature
            modifier.use_vertex_groups = True
            _parent_skinned_mesh_to_armature(obj, armature)
    bind_ms = lap_ms()

    for record in records:
        record["armature"].select_set(False)
    for obj in previous_selection:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = previous_active
    cleanup_ms = lap_ms()

    if profile_detail:
        _profile_log(
            "create_bind_pose_skin_armature_groups "
            f"skins={skin_count} armatures={len(records)} bones={total_bones} "
            f"create={create_ms:.3f}ms mode_enter={mode_enter_ms:.3f}ms "
            f"create_bones={create_bones_ms:.3f}ms parent_bones={parent_bones_ms:.3f}ms "
            f"mode_exit={mode_exit_ms:.3f}ms animation={animation_ms:.3f}ms "
            f"hide={hide_ms:.3f}ms bind={bind_ms:.3f}ms cleanup={cleanup_ms:.3f}ms "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return len(records)


def _bind_pose_group_bone_node_indices(items: list[tuple]) -> list[int]:
    indices: list[int] = []
    seen: set[int] = set()
    for _obj, data, _joint_names, joint_nodes, _node_objects, node_data, *_rest in items:
        for node_index in _skin_bone_node_indices(data, joint_nodes, node_data):
            if node_index in seen:
                continue
            seen.add(node_index)
            indices.append(node_index)
    return indices


def _bind_pose_group_bone_names(items: list[tuple]) -> dict[int, str]:
    names: dict[int, str] = {}
    for _obj, _data, joint_names, joint_nodes, _node_objects, _node_data, *_rest in items:
        count = min(len(joint_nodes), len(joint_names))
        for joint_index in range(count):
            node_index = int(joint_nodes[joint_index])
            if node_index >= 0 and node_index not in names:
                names[node_index] = joint_names[joint_index]
    return names


def _bind_pose_group_animation_payload(items: list[tuple]) -> tuple[list[str], list[int], dict[int, SceneNodeData], list[list[dict]]]:
    joint_names_out: list[str] = []
    joint_nodes_out: list[int] = []
    pose_channels_out: list[list[dict]] = []
    seen: set[str] = set()
    node_data_out: dict[int, SceneNodeData] = items[0][5] if items else {}

    for _obj, _data, joint_names, joint_nodes, _node_objects, node_data, *_rest in items:
        node_data_out = node_data
        pose_channels = _rest[2] if len(_rest) > 2 else None
        count = min(len(joint_names), len(joint_nodes))
        for joint_index in range(count):
            name = joint_names[joint_index]
            if name in seen:
                continue
            seen.add(name)
            joint_names_out.append(name)
            joint_nodes_out.append(int(joint_nodes[joint_index]))
            pose_channels_out.append(
                list(pose_channels[joint_index] or [])
                if pose_channels is not None and joint_index < len(pose_channels)
                else []
            )

    return joint_names_out, joint_nodes_out, node_data_out, pose_channels_out


def _hide_bind_pose_skin_helpers(items: list[tuple]) -> None:
    if not items:
        return

    helpers: set[int] = set()
    _first_obj, _first_data, _first_joint_names, _first_joint_nodes, node_objects, node_data, *_rest = items[0]
    children_by_parent: dict[int, list[int]] = {}
    for node_index, node in node_data.items():
        children_by_parent.setdefault(int(node.parent_index), []).append(node_index)

    for _obj, _data, _joint_names, joint_nodes, _node_objects, _node_data, *_item_rest in items:
        for index in range(len(joint_nodes)):
            node_index = int(joint_nodes[index])
            if node_index >= 0:
                helpers.add(node_index)

    stack = list(helpers)
    while stack:
        node_index = stack.pop()
        for child_index in children_by_parent.get(node_index, ()):
            if child_index in helpers:
                continue
            helpers.add(child_index)
            stack.append(child_index)

    for node_index in helpers:
        node = node_objects.get(node_index)
        if node and node.type == "EMPTY":
            _hide_empty_helper_object(node)


def _apply_deferred_skin_animations(state: dict | None) -> None:
    if not state or not state.get(_S_SKIN_ANIMATION_DEFERRED):
        return

    pending = state.get(_S_DEFERRED_SKIN_ANIMATIONS) or []
    if not pending:
        state[_S_SKIN_ANIMATION_DEFERRED] = False
        return

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    skin_count = len(pending)
    for armature, data, joint_names, joint_nodes, node_data, pose_channels_by_joint, include_root in pending:
        if include_root:
            root_node = node_data.get(int(data.skin_root_node_index))
            if root_node:
                _apply_animation(armature, root_node)
        _apply_bone_animations(armature, joint_names, joint_nodes, node_data, pose_channels_by_joint)

    state[_S_SKIN_ANIMATION_DEFERRED] = False
    pending.clear()
    if profile_detail:
        _profile_log(
            "deferred_skin_animations "
            f"skins={skin_count} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _effective_static_node_visibility_map(nodes: list[SceneNodeData]) -> dict[int, bool]:
    visibility: dict[int, bool] = {}
    animated = [_node_has_visibility_animation(node) for node in nodes]
    count = len(nodes)

    for index in range(count):
        if index in visibility:
            continue

        stack: list[int] = []
        seen: set[int] = set()
        current = index
        while 0 <= current < count and current not in visibility and current not in seen:
            seen.add(current)
            stack.append(current)
            current = nodes[current].parent_index

        inherited = visibility.get(current, True) if 0 <= current < count else True
        while stack:
            node_index = stack.pop()
            if not animated[node_index]:
                inherited = inherited and bool(nodes[node_index].visible)
            visibility[node_index] = inherited

    return visibility


def _node_object_visibility_map(
    nodes: list[SceneNodeData],
    static_visibility: dict[int, bool],
) -> dict[int, bool]:
    visibility: dict[int, bool] = {}
    for index, node in enumerate(nodes):
        inherited = static_visibility.get(index, True)
        visibility[index] = inherited and bool(node.visible) if _node_has_visibility_animation(node) else inherited
    return visibility


def _node_has_visibility_animation(node: SceneNodeData) -> bool:
    for channel in node.anim_channels or ():
        if _channel_target(channel) == _ANIM_VISIBILITY:
            return True
    return False


def _node_has_effective_visibility_animation(
    node_index: int,
    node_data: dict[int, SceneNodeData],
) -> bool:
    if node_index < 0 or not node_data:
        return False
    for ancestor_index in _node_ancestor_chain(node_index, node_data):
        node = node_data.get(ancestor_index)
        if node and _node_has_visibility_animation(node):
            return True
    return False


def _apply_effective_node_visibility_animation(
    obj: bpy.types.Object,
    node_index: int,
    node_data: dict[int, SceneNodeData],
) -> None:
    if node_index < 0 or not node_data:
        return

    chain = _node_ancestor_chain(node_index, node_data)
    channels_by_clip = _visibility_channels_by_clip(chain, node_data)
    if not channels_by_clip:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    end_frame = scene.frame_end
    actions: list[bpy.types.Action] = []

    for clip_key, node_channels in channels_by_clip.items():
        channels = [channel for channel_list in node_channels.values() for channel in channel_list]
        key_times = _animation_key_times(channels)
        if not key_times:
            continue
        if key_times[0] > 0.0:
            key_times.insert(0, 0.0)

        action = _visibility_action_for(obj, channels[0])
        actions.append(action)
        _register_action_frame_range(action, key_times[0] * fps, key_times[-1] * fps)
        coords = array("f", [0.0]) * (len(key_times) * 2)
        for key_index, time_value in enumerate(key_times):
            coords[key_index * 2] = time_value * fps
            coords[key_index * 2 + 1] = 0.0 if _effective_visibility_at_time(
                chain,
                node_data,
                node_channels,
                time_value,
            ) else 1.0

        for path in ("hide_viewport", "hide_render"):
            _remove_fcurves(action, path)
            fcurve = _ensure_fcurve(action, obj, path, None, group_name="Visibility")
            _write_fcurve_points(fcurve, coords, "CONSTANT")

        end_frame = max(end_frame, int(key_times[-1] * fps + 0.5))

    for action in actions:
        _stash_animation_action(obj, action)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _node_ancestor_chain(
    node_index: int,
    node_data: dict[int, SceneNodeData],
) -> list[int]:
    chain: list[int] = []
    seen: set[int] = set()
    current = node_index
    while current >= 0 and current in node_data and current not in seen:
        seen.add(current)
        chain.append(current)
        current = node_data[current].parent_index
    chain.reverse()
    return chain


def _visibility_channels_by_clip(
    chain: list[int],
    node_data: dict[int, SceneNodeData],
) -> dict[tuple[int, str], dict[int, list[dict]]]:
    clips: dict[tuple[int, str], dict[int, list[dict]]] = {}
    for node_index in chain:
        node = node_data.get(node_index)
        if not node:
            continue
        for channel in node.anim_channels or ():
            if _channel_target(channel) != _ANIM_VISIBILITY:
                continue
            clip_key = _channel_action_clip(channel)
            clips.setdefault(clip_key, {}).setdefault(node_index, []).append(channel)
    return clips


def _effective_visibility_at_time(
    chain: list[int],
    node_data: dict[int, SceneNodeData],
    channels_by_node: dict[int, list[dict]],
    time_value: float,
) -> bool:
    for node_index in chain:
        node = node_data.get(node_index)
        if not node:
            continue
        channels = channels_by_node.get(node_index)
        if channels:
            visible = _visibility_channels_value(channels, node.visible, time_value)
        else:
            visible = bool(node.visible)
        if not visible:
            return False
    return True


def _visibility_channels_value(
    channels: list[dict],
    fallback: bool,
    time_value: float,
) -> bool:
    value = 1.0 if fallback else 0.0
    for channel in channels:
        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        interpolation = _blender_interpolation(_channel_interpolation(channel))
        value = _sample_anim_scalar(times, values, count, value_width, 0, time_value, interpolation)
    return value >= 0.5


def _visibility_action_for(obj: bpy.types.Object, channel: dict) -> bpy.types.Action:
    action = _existing_action_for_clip(obj, "", channel)
    if action:
        return action

    obj.animation_data_create()
    action = bpy.data.actions.new(_animation_action_name(obj.name, "", channel))
    clip_index, _clip_name = _channel_action_clip(channel)
    if obj.animation_data.action is None or clip_index == 0:
        obj.animation_data.action = action
    return action


def _existing_action_for_clip(
    obj: bpy.types.Object,
    suffix: str,
    channel: dict,
) -> bpy.types.Action | None:
    if not obj.animation_data:
        return None

    name = _animation_action_name(obj.name, suffix, channel)
    active = obj.animation_data.action
    if active and _action_name_matches(active.name, name):
        return active

    for track in obj.animation_data.nla_tracks:
        for strip in track.strips:
            action = strip.action
            if action and _action_name_matches(action.name, name):
                return action
    return None


def _action_name_matches(candidate: str, expected: str) -> bool:
    return candidate == expected or candidate.startswith(f"{expected}.")


def _remove_fcurves(action: bpy.types.Action, data_path: str) -> None:
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:
        return
    for fcurve in list(fcurves):
        if fcurve.data_path == data_path:
            fcurves.remove(fcurve)


def _new_scene_node_object(node: SceneNodeData, index: int, visible: bool) -> bpy.types.Object:
    name = node.name or f"AssetKitNode_{index}"

    if node.camera_type:
        camera = bpy.data.cameras.new(node.camera_name or name)
        _configure_camera(camera, node)
        _set_assetkit_json_prop(camera, "assetkit_camera_extra_json", node.camera_extra)
        _set_assetkit_json_prop(camera, "assetkit_camera_imager_extra_json", node.camera_imager_extra)
        obj = bpy.data.objects.new(name, camera)
        _set_node_visibility(obj, visible)
        _set_assetkit_node_props(obj, node)
        return obj

    if node.light_type:
        light = bpy.data.lights.new(node.light_name or name, _blender_light_type(node.light_type))
        _configure_light(light, node)
        _set_assetkit_json_prop(light, "assetkit_light_extra_json", node.light_extra)
        obj = bpy.data.objects.new(name, light)
        _set_node_visibility(obj, visible)
        _set_assetkit_node_props(obj, node)
        return obj

    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
    _set_node_visibility(obj, visible)
    _set_assetkit_node_props(obj, node)
    return obj


def _set_assetkit_node_props(obj: bpy.types.Object, node: SceneNodeData) -> None:
    _set_assetkit_json_prop(obj, "assetkit_node_extra_json", node.extra)
    _set_assetkit_json_prop(obj, "assetkit_node_layers_json", node.layers)


def _configure_camera(camera: bpy.types.Camera, node: SceneNodeData) -> None:
    values = node.camera_values
    if node.camera_type == 2:
        camera.type = "ORTHO"
        camera.ortho_scale = max(values[0], values[1]) * 2.0 if max(values[0], values[1]) > 0.0 else 1.0
    else:
        camera.type = "PERSP"
        if values[1] > 0.0:
            camera.angle_y = values[1]
        elif values[0] > 0.0:
            camera.angle_x = values[0]
    if values[3] > 0.0:
        camera.clip_start = values[3]
    if values[4] > values[3]:
        camera.clip_end = values[4]


def _blender_light_type(light_type: int) -> str:
    if light_type == 2:
        return "SUN"
    if light_type == 4:
        return "SPOT"
    return "POINT"


def _configure_light(light: bpy.types.Light, node: SceneNodeData) -> None:
    values = node.light_values
    light.color = node.light_color
    if values[0] > 0.0:
        light.energy = values[0]
    if hasattr(light, "cutoff_distance") and values[1] > 0.0:
        light.cutoff_distance = values[1]
    if light.type == "SPOT" and values[3] > 0.0:
        light.spot_size = values[3] * 2.0
        if values[2] > 0.0 and values[3] > values[2]:
            light.spot_blend = max(0.0, min(1.0, 1.0 - values[2] / values[3]))


def _set_node_visibility(obj: bpy.types.Object, visible: bool) -> None:
    hidden = not bool(visible)
    obj.hide_viewport = hidden
    obj.hide_render = hidden


def _hide_helper_object(obj: bpy.types.Object, hide_empty: bool = False) -> None:
    obj["assetkit_helper_object"] = True
    if obj.type == "EMPTY":
        obj.hide_select = False
        obj.empty_display_size = max(0.1, min(obj.empty_display_size, 0.35))
        if hide_empty:
            _hide_empty_helper_object(obj)
        return

    obj.hide_select = True
    action = obj.animation_data.action if obj.animation_data else None
    if action and any(fcurve.data_path in {"hide_viewport", "hide_render"} for fcurve in _iter_action_fcurves(action)):
        return

    obj.hide_viewport = True
    obj.hide_render = True
    obj["assetkit_helper_hidden"] = True


def _hide_empty_helper_object(obj: bpy.types.Object) -> None:
    if obj.get("assetkit_helper_hidden"):
        return
    if not obj.get("assetkit_helper_object"):
        obj["assetkit_helper_object"] = True
    obj.hide_select = True
    obj.hide_viewport = True
    obj.hide_render = True
    obj["assetkit_helper_hidden"] = True


def _create_coord_root(
    primitives: list[MeshPrimitiveData],
    collection: bpy.types.Collection,
) -> bpy.types.Object | None:
    for primitive in primitives:
        matrix = _matrix_from_buffer(primitive.coord_matrix_f32)
        if matrix is None:
            continue

        root = bpy.data.objects.new("AssetKit Coordinates", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.5
        root.matrix_local = matrix
        collection.objects.link(root)
        _hide_helper_object(root)
        return root

    return None


def _set_parent(obj: bpy.types.Object, parent: bpy.types.Object | None) -> None:
    if not parent:
        return

    obj.parent = parent
    obj.matrix_parent_inverse.identity()


def _apply_matrix(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    _apply_matrix_buffer(obj, data.matrix_f32)


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
    obj.matrix_local = original @ _matrix_from_values(matrices, 0)
    obj["assetkit_instance_index"] = 0
    obj["assetkit_instance_count"] = count

    base_name = obj.name
    for index in range(1, count):
        duplicate = obj.copy()
        duplicate.data = obj.data
        duplicate.name = f"{base_name}_Instance_{index:03d}"
        duplicate.matrix_local = original @ _matrix_from_values(matrices, index * 16)
        duplicate["assetkit_instance_index"] = index
        duplicate["assetkit_instance_count"] = count
        collection.objects.link(duplicate)
        objects.append(duplicate)

    return objects


def _apply_matrix_buffer(obj: bpy.types.Object, buffer: object) -> None:
    matrix = _matrix_from_buffer(buffer)
    if matrix is None:
        return

    obj.matrix_local = matrix


def _matrix_from_buffer(buffer: object) -> Matrix | None:
    if not buffer:
        return None

    values = _buffer_view(buffer, "f")
    if values is None or len(values) != 16:
        return None

    return _matrix_from_values(values, 0)


def _matrix_from_values(values: memoryview, offset: int) -> Matrix:
    return Matrix(
        (
            (values[offset], values[offset + 4], values[offset + 8], values[offset + 12]),
            (values[offset + 1], values[offset + 5], values[offset + 9], values[offset + 13]),
            (values[offset + 2], values[offset + 6], values[offset + 10], values[offset + 14]),
            (values[offset + 3], values[offset + 7], values[offset + 11], values[offset + 15]),
        )
    )


def _buffer_view(buffer: object, fmt: str) -> memoryview | None:
    if not buffer:
        return None

    view = buffer if isinstance(buffer, memoryview) else memoryview(buffer)
    if len(view) == 0:
        return None
    if view.format == fmt and view.ndim == 1:
        return view
    return view.cast(fmt)


def _copy_buffer_bytes(dst: bytearray, offset: int, src: object, fmt: str) -> int:
    view = _buffer_view(src, fmt)
    if view is None:
        return 0
    raw = view.cast("B")
    end = offset + len(raw)
    dst[offset:end] = raw
    return len(raw)


def _channel_get(channel: object, index: int, default: object = None) -> object:
    if isinstance(channel, tuple):
        return channel[index] if index < len(channel) else default
    if isinstance(channel, dict):
        return channel.get(_CH_KEYS[index], default)
    if isinstance(channel, list):
        return channel[index] if index < len(channel) else default
    return default


def _channel_int(channel: object, index: int) -> int:
    value = _channel_get(channel, index, 0)
    return int(value or 0)


def _channel_bool(channel: object, index: int) -> bool:
    return bool(_channel_get(channel, index, False))


def _channel_buffer(channel: object, index: int) -> object:
    return _channel_get(channel, index, b"") or b""


def _channel_target(channel: object) -> int:
    return _channel_int(channel, _CH_TARGET)


def _channel_target_offset(channel: object) -> int:
    return _channel_int(channel, _CH_TARGET_OFFSET)


def _channel_clip_index(channel: object) -> int:
    return _channel_int(channel, _CH_CLIP_INDEX)


def _channel_clip_name(channel: object) -> str:
    return str(_channel_get(channel, _CH_CLIP_NAME, "") or "")


def _channel_value_width(channel: object) -> int:
    return _channel_int(channel, _CH_VALUE_WIDTH)


def _channel_count(channel: object) -> int:
    return _channel_int(channel, _CH_COUNT)


def _channel_interpolation(channel: object) -> int:
    return _channel_int(channel, _CH_INTERPOLATION)


def _channel_is_partial(channel: object) -> bool:
    return _channel_bool(channel, _CH_IS_PARTIAL)


def _channel_pose_ready(channel: object) -> bool:
    return _channel_bool(channel, _CH_POSE_READY)


def _channel_times(channel: object) -> object:
    return _channel_buffer(channel, _CH_TIMES_F32)


def _channel_values(channel: object) -> object:
    return _channel_buffer(channel, _CH_VALUES_F32)


def _channel_in_tangents(channel: object) -> object:
    return _channel_buffer(channel, _CH_IN_TANGENTS_F32)


def _channel_out_tangents(channel: object) -> object:
    return _channel_buffer(channel, _CH_OUT_TANGENTS_F32)


def _reset_action_cache() -> None:
    _ACTION_CHANNELBAGS.clear()
    _ACTION_CHANNEL_GROUPS.clear()
    _IMPORT_SHARED_ACTIONS.clear()
    _ACTION_FRAME_RANGES.clear()


def _merge_frame_bounds(
    bounds: tuple[float, float] | None,
    start: float,
    end: float,
) -> tuple[float, float]:
    if bounds is None:
        return float(start), float(end)
    return min(bounds[0], float(start)), max(bounds[1], float(end))


def _channel_frame_bounds(
    channel: object,
    fps: float,
    start_frame: float = 0.0,
) -> tuple[float, float] | None:
    count = _channel_count(channel)
    times = _buffer_view(_channel_times(channel), "f")
    if count <= 0 or times is None:
        return None
    last = min(count, len(times)) - 1
    if last < 0:
        return None
    start = float(start_frame) + float(times[0]) * fps
    end = float(start_frame) + float(times[last]) * fps
    return start, end


def _register_action_frame_range(action: bpy.types.Action, start: float, end: float) -> None:
    if end < start:
        return
    key = action.as_pointer()
    existing = _ACTION_FRAME_RANGES.get(key)
    _ACTION_FRAME_RANGES[key] = _merge_frame_bounds(existing, start, end)


def _register_actions_frame_range(
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    bounds: tuple[float, float] | None,
) -> None:
    if not actions or bounds is None:
        return
    for _owner, action in actions.values():
        _register_action_frame_range(action, bounds[0], bounds[1])


def _apply_animation(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    *,
    skip_visibility: bool = False,
) -> None:
    channels = data.anim_channels or []
    if not channels:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0

    if any(_channel_target(channel) == _ANIM_ROTATION_QUAT for channel in channels):
        obj.rotation_mode = "QUATERNION"

    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    end_frame = scene.frame_end
    frame_bounds: tuple[float, float] | None = None
    converted_targets, cone_end_frame = _apply_light_spot_cone_animations(
        obj,
        channels,
        actions,
        written_fcurves,
        fps,
        start_frame,
    )
    end_frame = max(end_frame, cone_end_frame)

    for channel in channels:
        target = _channel_target(channel)
        if target in converted_targets:
            continue
        if target == _ANIM_VISIBILITY:
            if skip_visibility:
                continue
            action = _animation_action_for(obj, obj, actions, "", channel)
            end_frame = max(end_frame, _apply_visibility_animation_channel(obj, action, channel, fps, start_frame))
            bounds = _channel_frame_bounds(channel, fps, start_frame)
            if bounds is not None:
                frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])
            continue

        owner, path, width, group_name = _anim_channel_target(obj, target)
        if not owner or not path:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        bounds = _channel_frame_bounds(channel, fps, start_frame)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        if target_offset >= width:
            continue

        action = _animation_action_for(obj, owner, actions, "" if owner == obj else "_Data", channel)
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        if not is_partial:
            if _anim_channel_can_use_native_coords(target):
                coords_by_component: list[object | None] = [
                    native_animation_coords(channel, component, fps)
                    for component in range(component_count)
                ]
            else:
                coords_by_component = [None] * component_count

            if any(coords is None for coords in coords_by_component):
                coords_by_component = [array("f", [0.0]) * (count * 2) for _ in range(component_count)]
                for key_index in range(count):
                    frame = start_frame + times[key_index] * fps
                    base = key_index * value_width
                    for component, coords in enumerate(coords_by_component):
                        coords[key_index * 2] = frame
                        coords[key_index * 2 + 1] = _anim_channel_value(
                            obj,
                            target,
                            values[base + component],
                        )

            for component, coords in enumerate(coords_by_component):
                target_index = target_offset + component
                fcurve_index = None if width == 1 else target_index
                write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
                if write_key in written_fcurves:
                    continue
                written_fcurves.add(write_key)
                fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
                _write_fcurve_points(
                    fcurve,
                    coords,
                    interpolation,
                    times=times,
                    fps=fps,
                    in_tangents=in_tangents,
                    out_tangents=out_tangents,
                    value_width=value_width,
                    value_index=component,
                    tangent_value=(
                        lambda value, target=target: _anim_channel_tangent_value(target, value)
                    ),
                )

            end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))
            continue

        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            fcurve_index = None if width == 1 else target_index
            write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
            coords = (
                native_animation_coords(channel, value_index, fps)
                if _anim_channel_can_use_native_coords(target)
                else None
            )
            if coords is None:
                coords = array("f", [0.0]) * (count * 2)
                for key_index in range(count):
                    coords[key_index * 2] = start_frame + times[key_index] * fps
                    coords[key_index * 2 + 1] = _anim_channel_value(
                        obj,
                        target,
                        values[key_index * value_width + value_index],
                    )

            _write_fcurve_points(
                fcurve,
                coords,
                interpolation,
                times=times,
                fps=fps,
                in_tangents=in_tangents,
                out_tangents=out_tangents,
                value_width=value_width,
                value_index=value_index,
                tangent_value=(
                    lambda value, target=target: _anim_channel_tangent_value(target, value)
                ),
            )

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    _stash_animation_actions(actions)
    _register_actions_frame_range(actions, frame_bounds)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _animation_action_for(
    obj: bpy.types.Object,
    owner: bpy.types.ID,
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    suffix: str,
    channel: dict | None = None,
) -> bpy.types.Action:
    clip_index, clip_name = _channel_action_clip(channel)
    key = (owner.as_pointer(), clip_index, suffix)
    cached = actions.get(key)
    if cached:
        return cached[1]

    owner.animation_data_create()
    action = _shared_animation_action(suffix, channel)
    if action is None:
        action = _new_animation_action(_animation_action_name(obj.name, suffix, channel))
    if owner.animation_data.action is None or clip_index == 0:
        owner.animation_data.action = action
        slot = _ensure_action_channelbag(action, owner)[0]
        _set_animation_data_slot(owner, slot)
    actions[key] = (owner, action)
    return action


def _shared_animation_action(suffix: str, channel: dict | None) -> bpy.types.Action | None:
    global _ACTION_SLOTS_SUPPORTED
    if _ACTION_SLOTS_SUPPORTED is False:
        return None

    clip_index, clip_name = _channel_action_clip(channel)
    key = (clip_index, clip_name, suffix)
    action = _IMPORT_SHARED_ACTIONS.get(key)
    if action is not None:
        return action

    action = _new_animation_action(_shared_animation_action_name(suffix, channel))
    if getattr(action, "slots", None) is None or getattr(action, "layers", None) is None:
        _ACTION_SLOTS_SUPPORTED = False
        bpy.data.actions.remove(action)
        return None

    _ACTION_SLOTS_SUPPORTED = True
    _IMPORT_SHARED_ACTIONS[key] = action
    return action


def _new_animation_action(name: str) -> bpy.types.Action:
    action = bpy.data.actions.new(name)
    _ensure_action_layer_strip(action)
    return action


def _ensure_action_layer_strip(action: bpy.types.Action):
    layers = getattr(action, "layers", None)
    if layers is None:
        return None

    if len(layers) == 0:
        try:
            layer = layers.new("layer0")
        except TypeError:
            layer = layers.new(name="layer0")
    else:
        layer = layers[0]

    strips = getattr(layer, "strips", None)
    if strips is None:
        return None
    if len(strips) == 0:
        try:
            return strips.new(type="KEYFRAME")
        except TypeError:
            return strips.new("KEYFRAME")
    return strips[0]


def _ensure_action_channelbag(action: bpy.types.Action, owner: bpy.types.ID):
    key = (action.as_pointer(), owner.as_pointer())
    cached = _ACTION_CHANNELBAGS.get(key)
    if cached:
        return cached

    strip = _ensure_action_layer_strip(action)
    slots = getattr(action, "slots", None)
    if strip is None or slots is None:
        return None, None

    slot = None
    for candidate in slots:
        if (
            getattr(candidate, "target_id_type", "") == owner.id_type
            and getattr(candidate, "name_display", getattr(candidate, "name", "")) == owner.name
        ):
            slot = candidate
            break
    if slot is None:
        try:
            slot = slots.new(owner.id_type, owner.name)
        except TypeError:
            slot = slots.new(id_type=owner.id_type, name=owner.name)

    try:
        channelbag = strip.channelbag(slot)
    except Exception:
        channelbag = None
    if channelbag is None:
        try:
            channelbag = strip.channelbags.new(slot)
        except Exception:
            channelbag = None
    if channelbag is None:
        return slot, None

    _ACTION_CHANNELBAGS[key] = (slot, channelbag)
    return slot, channelbag


def _set_animation_data_slot(owner: bpy.types.ID, slot) -> None:
    animation_data = getattr(owner, "animation_data", None)
    if animation_data is None or not hasattr(animation_data, "action_slot"):
        return
    try:
        animation_data.action_slot = slot
    except Exception:
        pass


def _animation_action_name(base_name: str, suffix: str, channel: dict | None) -> str:
    clip_index, clip_name = _channel_action_clip(channel)
    if clip_name:
        return f"{base_name}_AssetKit_{clip_name}{suffix}"
    if clip_index:
        return f"{base_name}_AssetKit_Animation_{clip_index}{suffix}"
    return f"{base_name}_AssetKit{suffix}"


def _shared_animation_action_name(suffix: str, channel: dict | None) -> str:
    clip_index, clip_name = _channel_action_clip(channel)
    if clip_name:
        return f"AssetKit_{clip_name}{suffix}"
    if clip_index:
        return f"AssetKit_Animation_{clip_index}{suffix}"
    return f"AssetKit{suffix}"


def _channel_action_clip(channel: dict | None) -> tuple[int, str]:
    clip_index = _channel_clip_index(channel)
    clip_name = _safe_action_name(_channel_clip_name(channel))
    if not clip_name:
        clip_index = 0
    return clip_index, clip_name


def _fcurve_write_key(
    owner: bpy.types.ID,
    channel: dict,
    data_path: str,
    index: int | None,
) -> tuple[int, int, str, int]:
    clip_index, _clip_name = _channel_action_clip(channel)
    return (
        owner.as_pointer(),
        clip_index,
        data_path,
        -1 if index is None else int(index),
    )


def _safe_action_name(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in name.strip())
    return out[:96]


def _stash_animation_actions(actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]]) -> None:
    for owner, action in actions.values():
        if not action or _action_frame_range(action) is None:
            continue
        _stash_animation_action(owner, action)


def _stash_animation_action(owner: bpy.types.ID, action: bpy.types.Action) -> None:
    try:
        owner.animation_data_create()
        tracks = owner.animation_data.nla_tracks
    except Exception:
        return

    for track in tracks:
        if any(strip.action == action for strip in track.strips):
            return

    try:
        track = tracks.new(prev=None)
        track.name = action.name
        strip = track.strips.new(action.name, bpy.context.scene.frame_start, action)
    except Exception:
        return

    _set_nla_strip_action_slot(strip, action, owner)
    frame_range = _action_frame_range(action)
    if frame_range is not None:
        strip.action_frame_start = frame_range[0]
        strip.action_frame_end = frame_range[1]
    track.lock = True
    track.mute = True


def _set_nla_strip_action_slot(strip, action: bpy.types.Action, owner: bpy.types.ID) -> None:
    if not hasattr(strip, "action_slot"):
        return

    slot = _ACTION_CHANNELBAGS.get((action.as_pointer(), owner.as_pointer()), (None, None))[0]
    if slot is not None:
        try:
            strip.action_slot = slot
            return
        except Exception:
            pass

    slot = None
    for candidate in getattr(action, "slots", []):
        if getattr(candidate, "target_id_type", "") == owner.id_type:
            slot = candidate
            break
    if slot is None:
        slots = list(getattr(action, "slots", []))
        slot = slots[0] if slots else None
    if slot is None:
        return

    try:
        strip.action_slot = slot
    except Exception:
        pass


def _apply_light_spot_cone_animations(
    obj: bpy.types.Object,
    channels: list[dict],
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    written_fcurves: set[tuple[int, int, str, int]],
    fps: float,
    start_frame: float,
) -> tuple[set[int], int]:
    data = getattr(obj, "data", None)
    if obj.type != "LIGHT" or not data or getattr(data, "type", "") != "SPOT":
        return set(), bpy.context.scene.frame_end
    if not hasattr(data, "spot_size") or not hasattr(data, "spot_blend"):
        return set(), bpy.context.scene.frame_end

    cone_channels = {
        _ANIM_LIGHT_SPOT_INNER: [
            channel for channel in channels
            if _channel_target(channel) == _ANIM_LIGHT_SPOT_INNER
        ],
        _ANIM_LIGHT_SPOT_OUTER: [
            channel for channel in channels
            if _channel_target(channel) == _ANIM_LIGHT_SPOT_OUTER
        ],
    }
    if not cone_channels[_ANIM_LIGHT_SPOT_INNER] and not cone_channels[_ANIM_LIGHT_SPOT_OUTER]:
        return set(), bpy.context.scene.frame_end

    key_times = _animation_key_times(cone_channels[_ANIM_LIGHT_SPOT_INNER] + cone_channels[_ANIM_LIGHT_SPOT_OUTER])
    if not key_times:
        return set(), bpy.context.scene.frame_end

    outer_fallback = max(float(data.spot_size) * 0.5, 1.0e-6)
    inner_fallback = outer_fallback * max(0.0, min(1.0, 1.0 - float(data.spot_blend)))
    first_channel = cone_channels[_ANIM_LIGHT_SPOT_OUTER][0] if cone_channels[_ANIM_LIGHT_SPOT_OUTER] else cone_channels[_ANIM_LIGHT_SPOT_INNER][0]
    action = _animation_action_for(obj, data, actions, "_Data", first_channel)
    interpolation = _merged_animation_interpolation(cone_channels[_ANIM_LIGHT_SPOT_INNER] + cone_channels[_ANIM_LIGHT_SPOT_OUTER])
    converted: set[int] = set()
    _register_action_frame_range(action, start_frame + key_times[0] * fps, start_frame + key_times[-1] * fps)

    if cone_channels[_ANIM_LIGHT_SPOT_OUTER]:
        coords = array("f", [0.0]) * (len(key_times) * 2)
        for key_index, time_value in enumerate(key_times):
            outer = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_OUTER], outer_fallback, time_value)
            coords[key_index * 2] = start_frame + time_value * fps
            coords[key_index * 2 + 1] = max(0.0, float(outer)) * 2.0
        write_key = _fcurve_write_key(data, first_channel, "spot_size", None)
        if write_key not in written_fcurves:
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, data, "spot_size", None, group_name="Light")
            _write_fcurve_points(fcurve, coords, interpolation)
        converted.add(_ANIM_LIGHT_SPOT_OUTER)

    coords = array("f", [0.0]) * (len(key_times) * 2)
    for key_index, time_value in enumerate(key_times):
        inner = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_INNER], inner_fallback, time_value)
        outer = _animation_sample_scalar(cone_channels[_ANIM_LIGHT_SPOT_OUTER], outer_fallback, time_value)
        coords[key_index * 2] = start_frame + time_value * fps
        coords[key_index * 2 + 1] = _spot_blend_from_angles(inner, outer)
    write_key = _fcurve_write_key(data, first_channel, "spot_blend", None)
    if write_key not in written_fcurves:
        written_fcurves.add(write_key)
        fcurve = _ensure_fcurve(action, data, "spot_blend", None, group_name="Light")
        _write_fcurve_points(fcurve, coords, interpolation)
    converted.add(_ANIM_LIGHT_SPOT_INNER)

    return converted, int(start_frame + key_times[-1] * fps + 0.5)


def _spot_blend_from_angles(inner: float, outer: float) -> float:
    outer = max(float(outer), 1.0e-6)
    inner = max(0.0, min(float(inner), outer))
    return max(0.0, min(1.0, 1.0 - inner / outer))


def _animation_key_times(channels: list[dict]) -> list[float]:
    values: set[float] = set()
    for channel in channels:
        count = _channel_count(channel)
        times = _buffer_view(_channel_times(channel), "f")
        if count <= 0 or times is None:
            continue
        for index in range(min(count, len(times))):
            values.add(float(times[index]))
    return sorted(values)


def _merged_animation_interpolation(channels: list[dict]) -> str:
    for channel in channels:
        if _blender_interpolation(_channel_interpolation(channel)) != "CONSTANT":
            return "LINEAR"
    return "CONSTANT"


def _animation_sample_scalar(
    channels: list[dict],
    fallback: float,
    time_value: float,
) -> float:
    values = [float(fallback)]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0]


def _anim_channel_target(
    obj: bpy.types.Object,
    target: int,
) -> tuple[bpy.types.ID | None, str, int, str]:
    path, width = _anim_target_path(target)
    if path:
        return obj, path, width, "Transform"

    data = getattr(obj, "data", None)
    if obj.type == "CAMERA" and data:
        if target == _ANIM_CAMERA_XFOV:
            return data, "angle_x", 1, "Camera"
        if target == _ANIM_CAMERA_YFOV:
            return data, "angle_y", 1, "Camera"
        if target == _ANIM_CAMERA_ZNEAR:
            return data, "clip_start", 1, "Camera"
        if target == _ANIM_CAMERA_ZFAR:
            return data, "clip_end", 1, "Camera"
        if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG}:
            return data, "ortho_scale", 1, "Camera"

    if obj.type == "LIGHT" and data:
        if target == _ANIM_LIGHT_COLOR:
            return data, "color", 3, "Light"
        if target == _ANIM_LIGHT_INTENSITY:
            return data, "energy", 1, "Light"
        if target == _ANIM_LIGHT_RANGE and hasattr(data, "cutoff_distance"):
            return data, "cutoff_distance", 1, "Light"
        if target == _ANIM_LIGHT_SPOT_OUTER and hasattr(data, "spot_size"):
            return data, "spot_size", 1, "Light"
        if target == _ANIM_LIGHT_SPOT_INNER and hasattr(data, "spot_blend"):
            return data, "spot_blend", 1, "Light"

    return None, "", 0, ""


def _anim_channel_value(obj: bpy.types.Object, target: int, value: float) -> float:
    if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG, _ANIM_LIGHT_SPOT_OUTER}:
        return value * 2.0

    if target == _ANIM_LIGHT_SPOT_INNER:
        data = getattr(obj, "data", None)
        outer = getattr(data, "spot_size", 0.0) * 0.5 if data else 0.0
        if outer <= 1.0e-6:
            return 0.0
        return max(0.0, min(1.0, 1.0 - value / outer))

    return value


def _anim_channel_tangent_value(target: int, value: float) -> float:
    if target in {_ANIM_CAMERA_ORTHO_XMAG, _ANIM_CAMERA_ORTHO_YMAG, _ANIM_LIGHT_SPOT_OUTER}:
        return value * 2.0
    return value


def _apply_visibility_animation_channel(
    obj: bpy.types.Object,
    action: bpy.types.Action,
    channel: dict,
    fps: float,
    start_frame: float,
) -> int:
    count = _channel_count(channel)
    value_width = _channel_value_width(channel)
    times = _buffer_view(_channel_times(channel), "f")
    values = _buffer_view(_channel_values(channel), "f")
    if count <= 0 or value_width <= 0 or times is None or values is None:
        return bpy.context.scene.frame_end

    coords = array("f", [0.0]) * (count * 2)
    for key_index in range(count):
        coords[key_index * 2] = start_frame + times[key_index] * fps
        coords[key_index * 2 + 1] = 0.0 if values[key_index * value_width] >= 0.5 else 1.0

    for path in ("hide_viewport", "hide_render"):
        fcurve = _ensure_fcurve(action, obj, path, None, group_name="Visibility")
        _write_fcurve_points(fcurve, coords, "CONSTANT")

    return int(start_frame + times[count - 1] * fps + 0.5)


def _apply_shape_keys(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    targets = data.morph_targets or []
    if not targets:
        return

    vertex_count = len(obj.data.vertices)
    obj.shape_key_add(name="Basis", from_mix=False)
    for index, target in enumerate(targets):
        if target.vertex_count != vertex_count:
            continue
        coords = _buffer_view(target.positions_f32, "f")
        if coords is None or len(coords) != vertex_count * 3:
            continue

        key = obj.shape_key_add(name=target.name or f"AssetKitMorph_{index}", from_mix=False)
        key.data.foreach_set("co", coords)
        key.value = target.weight

    obj.data.update()
    _apply_shape_key_animation(obj, data)


def _apply_shape_key_animation(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    channels = data.morph_anim_channels or []
    shape_keys = obj.data.shape_keys
    if not channels or not shape_keys:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0
    end_frame = scene.frame_end

    shape_keys.animation_data_create()
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    frame_bounds: tuple[float, float] | None = None

    for channel in channels:
        if _channel_target(channel) != _ANIM_MORPH_WEIGHTS:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        bounds = _channel_frame_bounds(channel, fps, start_frame)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        component_count = 1 if is_partial else value_width
        action = _animation_action_for(obj, shape_keys, actions, "_Morph", channel)
        for component in range(component_count):
            key_index = target_offset + component + 1
            if key_index >= len(shape_keys.key_blocks):
                continue

            key = shape_keys.key_blocks[key_index]
            value_index = 0 if is_partial else component
            path = key.path_from_id("value")
            write_key = _fcurve_write_key(shape_keys, channel, path, 0)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, shape_keys, key.path_from_id("value"), 0, group_name="Shape Keys")
            coords = array("f", [0.0]) * (count * 2)
            for frame_index in range(count):
                coords[frame_index * 2] = start_frame + times[frame_index] * fps
                coords[frame_index * 2 + 1] = values[frame_index * value_width + value_index]

            _write_fcurve_points(
                fcurve,
                coords,
                interpolation,
                times=times,
                fps=fps,
                in_tangents=in_tangents,
                out_tangents=out_tangents,
                value_width=value_width,
                value_index=value_index,
            )

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    _stash_animation_actions(actions)
    _register_actions_frame_range(actions, frame_bounds)
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _apply_morph_presets(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    presets = data.morph_presets or []
    shape_keys = obj.data.shape_keys if obj.data else None
    if not presets or not shape_keys or len(shape_keys.key_blocks) <= 1:
        return

    target_count = len(shape_keys.key_blocks) - 1
    written = 0
    for preset in presets:
        name = str(preset.get("name") or f"Preset {written + 1}")
        weights = [float(value) for value in preset.get("weights") or ()]
        if not weights:
            continue

        prefix = f"assetkit_morph_preset_{written}"
        obj[f"{prefix}_name"] = name
        obj[f"{prefix}_weights_json"] = json.dumps(
            weights[:target_count],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        obj[f"{prefix}_target_count"] = min(target_count, len(weights))
        written += 1

    if written:
        obj["assetkit_morph_preset_count"] = written


def _apply_skin(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    collection: bpy.types.Collection,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_animation: bool = True,
    deferred_skin_animations: list | None = None,
) -> None:
    if not data.has_skin or data.skin_vertex_count <= 0 or data.skin_joint_count <= 0:
        return

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    detail_parts: list[str] = []
    joints = _buffer_view(data.skin_joints_u16, "H")
    weights = _buffer_view(data.skin_weights_f32, "f")
    joint_nodes = _buffer_view(data.skin_joint_nodes_i32, "i")
    if joints is None or weights is None or joint_nodes is None:
        return
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"views={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now

    width = max(1, int(data.skin_joint_width or 4))
    vertex_count = min(data.skin_vertex_count, len(obj.data.vertices))
    joint_names = _create_skin_vertex_groups(obj, data, joints, weights, vertex_count, width, joint_nodes, node_objects)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"vertex_groups={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    if data.skin_mesh_in_bind_pose:
        queue = _deferred_bind_pose_skin_queue(skin_cache)
        if queue is not None:
            queue.append((
                obj,
                data,
                joint_names,
                joint_nodes,
                node_objects,
                node_data,
                collection,
                apply_animation,
                data.skin_pose_anim_channels,
                deferred_skin_animations,
            ))
            if profile_detail:
                now = time.perf_counter()
                detail_parts.append(f"defer={(now - phase_started_at) * 1000.0:.3f}ms")
                _profile_log(
                    "apply_skin_detail "
                    f"name={obj.name!r} joints={data.skin_joint_count} verts={vertex_count} "
                    f"total={(now - total_started_at) * 1000.0:.3f}ms "
                    + " ".join(detail_parts)
                )
            return
    cache_key = _skin_cache_key(data, joint_nodes, obj)
    armature = skin_cache.get(cache_key) if skin_cache is not None else None
    if armature is None:
        armature = _create_skin_armature(
            obj,
            data,
            joint_names,
            joint_nodes,
            node_objects,
            node_data,
            collection,
            apply_animation=apply_animation,
            pose_channels_by_joint=data.skin_pose_anim_channels,
            deferred_skin_animations=deferred_skin_animations,
        )
        if armature and skin_cache is not None:
            skin_cache[cache_key] = armature
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"armature={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    if not armature:
        return

    modifier = obj.modifiers.new("AssetKit Skin", "ARMATURE")
    modifier.object = armature
    modifier.use_vertex_groups = True
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"modifier={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    _hide_skin_node_helpers(joint_nodes, node_objects, node_data)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"hide_helpers={(now - phase_started_at) * 1000.0:.3f}ms")
        phase_started_at = now
    if _skin_uses_bind_pose_armature(data):
        _parent_skinned_mesh_to_armature(obj, armature)
    if profile_detail:
        now = time.perf_counter()
        detail_parts.append(f"parent={(now - phase_started_at) * 1000.0:.3f}ms")
        _profile_log(
            "apply_skin_detail "
            f"name={obj.name!r} joints={data.skin_joint_count} verts={vertex_count} "
            f"total={(now - total_started_at) * 1000.0:.3f}ms "
            + " ".join(detail_parts)
        )


def _hide_skin_node_helpers(
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
) -> None:
    node_indices = _skin_helper_node_indices(joint_nodes, node_data)
    for node_index in node_indices:
        node = node_objects.get(node_index)
        if node and node.type == "EMPTY":
            _hide_empty_helper_object(node)


def _skin_helper_node_indices(
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
) -> set[int]:
    helpers = {
        int(joint_nodes[index])
        for index in range(len(joint_nodes))
        if int(joint_nodes[index]) >= 0
    }
    if not helpers:
        return helpers

    children_by_parent: dict[int, list[int]] = {}
    for node_index, node in node_data.items():
        children_by_parent.setdefault(int(node.parent_index), []).append(node_index)

    stack = list(helpers)
    while stack:
        node_index = stack.pop()
        for child_index in children_by_parent.get(node_index, ()):
            if child_index in helpers:
                continue
            helpers.add(child_index)
            stack.append(child_index)

    return helpers


def _apply_skin_bind_shape(mesh: bpy.types.Mesh, data: MeshPrimitiveData) -> None:
    if not data.has_skin:
        return

    matrix = _matrix_from_buffer(data.skin_bind_shape_matrix_f32)
    if matrix is None or _matrix_is_identity(matrix):
        return

    mesh.transform(matrix)
    mesh.update(calc_edges=False)


def _matrix_is_identity(matrix: Matrix, epsilon: float = 1.0e-6) -> bool:
    identity = Matrix.Identity(4)
    for row in range(4):
        for col in range(4):
            if abs(matrix[row][col] - identity[row][col]) > epsilon:
                return False
    return True


def _skin_cache_key(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    obj: bpy.types.Object,
) -> object:
    count = min(len(joint_nodes), int(data.skin_joint_count))
    return (
        id(obj.parent),
        int(data.skin_root_node_index),
        tuple(int(joint_nodes[index]) for index in range(count)),
    )


def _deferred_bind_pose_skin_queue(skin_cache: dict | None) -> list | None:
    if skin_cache is None:
        return None
    queue = skin_cache.get(_SKIN_CACHE_DEFER_BIND_SKINS)
    if queue is None:
        queue = []
        skin_cache[_SKIN_CACHE_DEFER_BIND_SKINS] = queue
    return queue


def _skin_joint_name(
    joint_index: int,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
) -> str:
    node_index = int(joint_nodes[joint_index]) if joint_index < len(joint_nodes) else -1
    node = node_objects.get(node_index)
    if node:
        return node.name
    if node_index >= 0:
        return f"AssetKitJoint_{node_index}"
    return f"AssetKitJoint_{joint_index}"


def _create_skin_vertex_groups(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    joints: memoryview,
    weights: memoryview,
    vertex_count: int,
    width: int,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
) -> list[str]:
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    groups = []
    for joint_index in range(data.skin_joint_count):
        group = obj.vertex_groups.new(name=_skin_joint_name(joint_index, joint_nodes, node_objects))
        groups.append(group)
    if profile_detail:
        now = time.perf_counter()
        create_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    else:
        create_ms = 0.0

    group_count = len(groups)
    fast_assignments = native_skin_group_assignments(joints, weights, vertex_count, width, group_count)
    if fast_assignments:
        add_call_count = 0
        assignment_count = 0
        for joint_index, weight, indices in fast_assignments:
            if 0 <= joint_index < group_count:
                groups[joint_index].add(indices, weight, "REPLACE")
                add_call_count += 1
                assignment_count += len(indices)
        if profile_detail:
            now = time.perf_counter()
            _profile_log(
                "skin_vertex_groups_detail "
                f"name={obj.name!r} joints={group_count} verts={vertex_count} "
                f"assignments={assignment_count} add_calls={add_call_count} "
                f"create={create_ms:.3f}ms collect=0.000ms "
                f"add={(now - phase_started_at) * 1000.0:.3f}ms "
                f"mode=native_rigid total={(now - total_started_at) * 1000.0:.3f}ms"
            )
        return [group.name for group in groups]

    assignments: list[dict[float, list[int]] | None] = [None] * group_count
    assignment_count = 0
    for vertex_index in range(vertex_count):
        base = vertex_index * width
        for slot in range(width):
            weight = weights[base + slot]
            if weight <= 0.0:
                continue
            joint_index = int(joints[base + slot])
            if 0 <= joint_index < group_count:
                group_assignments = assignments[joint_index]
                if group_assignments is None:
                    group_assignments = {}
                    assignments[joint_index] = group_assignments
                group_assignments.setdefault(float(weight), []).append(vertex_index)
                assignment_count += 1
    if profile_detail:
        now = time.perf_counter()
        collect_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    else:
        collect_ms = 0.0

    add_call_count = 0
    for joint_index, group_assignments in enumerate(assignments):
        if not group_assignments:
            continue
        group = groups[joint_index]
        for weight, indices in group_assignments.items():
            group.add(indices, weight, "REPLACE")
            add_call_count += 1
    if profile_detail:
        now = time.perf_counter()
        add_ms = (now - phase_started_at) * 1000.0
        _profile_log(
            "skin_vertex_groups_detail "
            f"name={obj.name!r} joints={group_count} verts={vertex_count} "
            f"assignments={assignment_count} add_calls={add_call_count} "
            f"create={create_ms:.3f}ms collect={collect_ms:.3f}ms "
            f"add={add_ms:.3f}ms total={(now - total_started_at) * 1000.0:.3f}ms"
        )

    return [group.name for group in groups]


def _create_skin_armature(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    collection: bpy.types.Collection,
    apply_animation: bool = True,
    pose_channels_by_joint: list[list[dict]] | None = None,
    deferred_skin_animations: list | None = None,
) -> bpy.types.Object | None:
    if not joint_names:
        return None

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at

    def lap_ms() -> float:
        nonlocal phase_started_at
        if not profile_detail:
            return 0.0
        now = time.perf_counter()
        elapsed = (now - phase_started_at) * 1000.0
        phase_started_at = now
        return elapsed

    armature_data = bpy.data.armatures.new(f"{obj.name}_Armature")
    armature = bpy.data.objects.new(f"{obj.name}_Armature", armature_data)
    collection.objects.link(armature)
    armature_source = _skin_armature_source(data, joint_nodes, node_objects, node_data) or obj
    _match_object_space(armature, armature_source)
    create_ms = lap_ms()

    previous_active = bpy.context.view_layer.objects.active
    previous_selection = list(bpy.context.selected_objects)
    if previous_active and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    mode_enter_ms = lap_ms()

    edit_bones = armature_data.edit_bones
    bone_node_indices = _skin_bone_node_indices(data, joint_nodes, node_data)
    node_to_joint = {
        int(joint_nodes[index]): index
        for index in range(min(len(joint_nodes), len(joint_names)))
        if int(joint_nodes[index]) >= 0
    }
    bone_names_by_node = _skin_bone_names_by_node(bone_node_indices, node_objects, node_to_joint, joint_names)
    rest_matrices_by_node = _skin_rest_matrices_by_node(
        data,
        joint_nodes,
        node_objects,
        node_data,
        armature,
        bone_node_indices,
    )

    for node_index in bone_node_indices:
        name = bone_names_by_node.get(node_index)
        if not name:
            continue
        bone = edit_bones.new(name)
        matrix = rest_matrices_by_node.get(node_index)
        if matrix is None:
            matrix = _node_rest_matrix(node_index, node_objects, armature)
        _set_bone_from_rest_matrix(
            bone,
            matrix,
            _skin_bone_length(node_index, bone_node_indices, node_data, rest_matrices_by_node),
        )
    create_bones_ms = lap_ms()

    for node_index, name in bone_names_by_node.items():
        parent_joint = None
        parent_index = node_data.get(node_index).parent_index if node_data.get(node_index) else -1
        while parent_index >= 0 and parent_joint is None:
            parent_name = bone_names_by_node.get(parent_index)
            if parent_name:
                parent_joint = parent_name
                break
            parent_node = node_data.get(parent_index)
            parent_index = parent_node.parent_index if parent_node else -1
        if parent_joint is not None and parent_joint in edit_bones:
            edit_bones[name].parent = edit_bones[parent_joint]
    parent_bones_ms = lap_ms()

    bpy.ops.object.mode_set(mode="OBJECT")
    mode_exit_ms = lap_ms()
    if _skin_uses_bind_pose_armature(data):
        root_node = node_data.get(int(data.skin_root_node_index))
        if apply_animation:
            if root_node:
                _apply_animation(armature, root_node)
            _apply_bone_animations(armature, joint_names, joint_nodes, node_data, pose_channels_by_joint)
        elif deferred_skin_animations is not None:
            deferred_skin_animations.append((armature, data, joint_names, joint_nodes, node_data, pose_channels_by_joint, True))
    else:
        bound_to_nodes = _bind_bones_to_nodes(armature, bone_names_by_node, node_objects)
        if not bound_to_nodes:
            if apply_animation:
                _apply_bone_animations(armature, joint_names, joint_nodes, node_data, pose_channels_by_joint)
            elif deferred_skin_animations is not None:
                deferred_skin_animations.append((armature, data, joint_names, joint_nodes, node_data, pose_channels_by_joint, False))
    animation_ms = lap_ms()
    if _skin_uses_bind_pose_armature(data):
        _match_object_space(armature, armature_source)
    else:
        _match_object_space(armature, armature_source)
    _hide_helper_object(armature)

    if armature not in previous_selection:
        armature.select_set(False)
    bpy.context.view_layer.objects.active = previous_active
    cleanup_ms = lap_ms()
    if profile_detail:
        _profile_log(
            "create_skin_armature_detail "
            f"name={armature.name!r} joints={len(joint_names)} bones={len(bone_node_indices)} "
            f"create={create_ms:.3f}ms "
            f"mode_enter={mode_enter_ms:.3f}ms "
            f"create_bones={create_bones_ms:.3f}ms "
            f"parent_bones={parent_bones_ms:.3f}ms "
            f"mode_exit={mode_exit_ms:.3f}ms "
            f"animation={animation_ms:.3f}ms "
            f"cleanup={cleanup_ms:.3f}ms "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return armature


def _skin_bone_node_indices(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
) -> list[int]:
    joint_indices = [int(joint_nodes[index]) for index in range(len(joint_nodes)) if int(joint_nodes[index]) >= 0]
    return joint_indices


def _skin_uses_bind_pose_armature(data: MeshPrimitiveData) -> bool:
    return bool(data.skin_mesh_in_bind_pose)


def _skin_armature_source(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
) -> bpy.types.Object | None:
    root_index = int(data.skin_root_node_index)
    if root_index >= 0 and root_index in node_objects:
        return node_objects[root_index]

    if len(joint_nodes) == 0:
        return None

    first_index = int(joint_nodes[0])
    first_node = node_data.get(first_index)
    parent_index = first_node.parent_index if first_node else -1
    if parent_index >= 0 and parent_index in node_objects:
        return node_objects[parent_index]
    return node_objects.get(first_index)


def _parent_skinned_mesh_to_armature(
    obj: bpy.types.Object,
    armature: bpy.types.Object,
) -> None:
    obj.parent = armature
    obj.matrix_parent_inverse.identity()
    obj.matrix_local = Matrix.Identity(4)


def _skin_bone_names_by_node(
    bone_node_indices: list[int],
    node_objects: dict[int, bpy.types.Object],
    node_to_joint: dict[int, int],
    joint_names: list[str],
) -> dict[int, str]:
    names: dict[int, str] = {}
    for node_index in bone_node_indices:
        joint_index = node_to_joint.get(node_index)
        if joint_index is not None and joint_index < len(joint_names):
            names[node_index] = joint_names[joint_index]
            continue
        node = node_objects.get(node_index)
        names[node_index] = node.name if node else f"AssetKitBone_{node_index}"
    return names


def _skin_rest_matrices_by_node(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    armature: bpy.types.Object,
    bone_node_indices: list[int],
) -> dict[int, Matrix]:
    if _skin_uses_bind_pose_armature(data):
        return _skin_rest_matrices_from_assetkit_nodes(data, node_data, bone_node_indices)

    matrices = {node_index: _node_rest_matrix(node_index, node_objects, armature) for node_index in bone_node_indices}
    values = _buffer_view(data.skin_inverse_bind_matrices_f32, "f")
    if values is None or len(values) < len(joint_nodes) * 16:
        return matrices

    coord_matrix = _matrix_from_buffer(data.coord_matrix_f32) or Matrix.Identity(4)
    bind_coord_matrix = coord_matrix
    world_to_armature = armature.matrix_world.inverted_safe()
    for index in range(len(joint_nodes)):
        node_index = int(joint_nodes[index])
        if node_index < 0:
            continue
        inverse_bind = _matrix_from_values(values, index * 16)
        matrices[node_index] = world_to_armature @ (bind_coord_matrix @ inverse_bind.inverted_safe())
    return matrices


def _skin_rest_matrices_from_assetkit_nodes(
    data: MeshPrimitiveData,
    node_data: dict[int, SceneNodeData],
    bone_node_indices: list[int],
) -> dict[int, Matrix]:
    cache: dict[int, Matrix] = {}
    root_index = int(data.skin_root_node_index)
    root_world = _node_static_world_matrix(root_index, node_data, cache) if root_index >= 0 else Matrix.Identity(4)
    root_inverse = root_world.inverted_safe()
    return {
        node_index: root_inverse @ _node_static_world_matrix(node_index, node_data, cache)
        for node_index in bone_node_indices
    }


def _node_static_world_matrix(
    node_index: int,
    node_data: dict[int, SceneNodeData],
    cache: dict[int, Matrix],
) -> Matrix:
    cached = cache.get(node_index)
    if cached is not None:
        return cached

    stack: list[int] = []
    current = node_index
    while current >= 0 and current not in cache:
        stack.append(current)
        node = node_data.get(current)
        current = node.parent_index if node else -1

    matrix = cache.get(current, Matrix.Identity(4))
    for index in reversed(stack):
        node = node_data.get(index)
        local = _matrix_from_buffer(node.matrix_f32) if node else None
        matrix = matrix @ (local or Matrix.Identity(4))
        cache[index] = matrix
    return cache.get(node_index, Matrix.Identity(4))


def _node_rest_matrix(
    node_index: int,
    node_objects: dict[int, bpy.types.Object],
    armature: bpy.types.Object,
) -> Matrix:
    node = node_objects.get(node_index)
    if not node:
        return Matrix.Identity(4)
    return armature.matrix_world.inverted_safe() @ node.matrix_world


def _skin_bone_length(
    node_index: int,
    bone_node_indices: list[int],
    node_data: dict[int, SceneNodeData],
    rest_matrices_by_node: dict[int, Matrix],
) -> float:
    matrix = rest_matrices_by_node.get(node_index)
    if matrix is None:
        return 0.05
    head = matrix.to_translation()
    for child_index in bone_node_indices:
        child = node_data.get(child_index)
        if child and child.parent_index == node_index:
            child_matrix = rest_matrices_by_node.get(child_index)
            if child_matrix:
                length = (child_matrix.to_translation() - head).length
                if length > 1.0e-5:
                    return length
    return 0.05


def _set_bone_from_rest_matrix(
    bone: bpy.types.EditBone,
    matrix: Matrix,
    length: float,
) -> None:
    head = matrix.to_translation()
    basis = matrix.to_3x3()
    direction = basis @ Vector((0.0, 1.0, 0.0))
    roll_axis = basis @ Vector((0.0, 0.0, 1.0))
    if direction.length <= 1.0e-5:
        direction = Vector((0.0, 1.0, 0.0))
    bone.head = head
    bone.tail = head + direction.normalized() * max(length, 0.004)
    if roll_axis.length > 1.0e-5:
        try:
            bone.align_roll(roll_axis.normalized())
        except Exception:
            pass


def _bind_bones_to_nodes(
    armature: bpy.types.Object,
    bone_names_by_node: dict[int, str],
    node_objects: dict[int, bpy.types.Object],
) -> bool:
    bound_any = False
    for node_index, name in bone_names_by_node.items():
        pose_bone = armature.pose.bones.get(name)
        node = node_objects.get(node_index)
        if not pose_bone or not node:
            continue
        constraint = pose_bone.constraints.new(type="COPY_TRANSFORMS")
        constraint.name = "AssetKit Node"
        constraint.target = node
        constraint.target_space = "WORLD"
        constraint.owner_space = "WORLD"
        bound_any = True
    return bound_any


def _match_object_space(target: bpy.types.Object, source: bpy.types.Object) -> None:
    target.parent = source.parent
    target.matrix_parent_inverse.identity()
    target.matrix_world = source.matrix_world.copy()


def _pose_bone_edit_local_matrix(pose_bone: bpy.types.PoseBone) -> Matrix:
    matrix = pose_bone.bone.matrix_local.copy()
    parent = pose_bone.parent
    if parent:
        return parent.bone.matrix_local.inverted_safe() @ matrix
    return matrix


def _bone_anim_sample(
    target: int,
    values: memoryview,
    value_width: int,
    key_index: int,
    edit_translation: Vector,
    edit_rotation_inv: Quaternion,
) -> tuple[float, ...] | None:
    base = key_index * value_width
    if target == _ANIM_TRANSLATION and value_width >= 3:
        translation = Vector((values[base], values[base + 1], values[base + 2]))
        corrected = edit_rotation_inv @ (translation - edit_translation)
        return corrected.x, corrected.y, corrected.z

    if target == _ANIM_ROTATION_QUAT and value_width >= 4:
        rotation = Quaternion((values[base], values[base + 1], values[base + 2], values[base + 3]))
        corrected = edit_rotation_inv @ rotation
        corrected.normalize()
        return corrected.w, corrected.x, corrected.y, corrected.z

    if target == _ANIM_SCALE and value_width >= 3:
        return values[base], values[base + 1], values[base + 2]

    return None


def _bone_default_component_value(target: int, target_index: int) -> float | None:
    if target == _ANIM_TRANSLATION:
        return 0.0
    if target == _ANIM_ROTATION_QUAT:
        return 1.0 if target_index == 0 else 0.0
    if target == _ANIM_SCALE:
        return 1.0
    return None


def _bone_component_is_default(
    channel: object,
    target: int,
    target_index: int,
    value_index: int,
) -> bool:
    if not _channel_pose_ready(channel):
        return False
    default_value = _bone_default_component_value(target, target_index)
    if default_value is None:
        return False
    return native_animation_component_constant(channel, value_index, default_value)


def _anim_channel_can_use_native_coords(target: int) -> bool:
    return target in {_ANIM_TRANSLATION, _ANIM_ROTATION_QUAT, _ANIM_SCALE}


def _apply_bone_animations(
    armature: bpy.types.Object,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
    pose_channels_by_joint: list[list[dict]] | None = None,
) -> None:
    profile_detail = _PROFILE_MATERIAL_STATS is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    animated = False
    channel_count = 0
    for index, name in enumerate(joint_names):
        pose_bone = armature.pose.bones.get(name)
        if pose_bone:
            pose_bone.rotation_mode = "QUATERNION"
        channels = _bone_animation_channels(index, joint_nodes, node_data, pose_channels_by_joint)
        if channels:
            animated = True
            channel_count += len(channels)

    if not animated:
        return
    if profile_detail:
        now = time.perf_counter()
        prep_ms = (now - phase_started_at) * 1000.0
        phase_started_at = now
    else:
        prep_ms = 0.0

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    end_frame = scene.frame_end
    coords_ms = 0.0
    fcurve_ms = 0.0
    write_ms = 0.0
    fallback_ms = 0.0
    skipped_default_fcurves = 0
    frame_bounds: tuple[float, float] | None = None

    for index, name in enumerate(joint_names):
        pose_bone = armature.pose.bones.get(name)
        channels = _bone_animation_channels(index, joint_nodes, node_data, pose_channels_by_joint)
        if not pose_bone or not channels:
            continue

        needs_python_pose = any(not _channel_pose_ready(channel) for channel in channels)
        if needs_python_pose:
            edit_matrix = _pose_bone_edit_local_matrix(pose_bone)
            edit_translation = edit_matrix.to_translation()
            edit_rotation_inv = edit_matrix.to_quaternion().conjugated()
        else:
            edit_translation = Vector((0.0, 0.0, 0.0))
            edit_rotation_inv = Quaternion((1.0, 0.0, 0.0, 0.0))

        for channel in channels:
            target = _channel_target(channel)
            path, width = _anim_target_path(target)
            if not path:
                continue

            count = _channel_count(channel)
            value_width = _channel_value_width(channel)
            target_offset = _channel_target_offset(channel)
            is_partial = _channel_is_partial(channel)
            times = _buffer_view(_channel_times(channel), "f")
            values = _buffer_view(_channel_values(channel), "f")
            if count <= 0 or value_width <= 0 or times is None or values is None:
                continue
            bounds = _channel_frame_bounds(channel, fps)
            if bounds is not None:
                frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])

            interpolation = _blender_interpolation(_channel_interpolation(channel))
            in_tangents, out_tangents = _channel_tangents(channel)
            component_count = 1 if is_partial else min(width - target_offset, value_width)
            data_path = pose_bone.path_from_id(path)
            if not is_partial:
                pose_ready = _channel_pose_ready(channel)
                skip_components = [False] * component_count
                if pose_ready:
                    for component in range(component_count):
                        target_index = target_offset + component
                        if _bone_component_is_default(channel, target, target_index, component):
                            skip_components[component] = True
                            skipped_default_fcurves += 1

                coords_by_component: list[object | None]
                if pose_ready:
                    if profile_detail:
                        coords_started_at = time.perf_counter()
                    coords_by_component = [
                        None
                        if skip_components[component]
                        else native_animation_coords(channel, component, fps)
                        for component in range(component_count)
                    ]
                    if profile_detail:
                        coords_ms += (time.perf_counter() - coords_started_at) * 1000.0
                else:
                    coords_by_component = [None] * component_count

                if any(
                    coords is None and not skip_components[component]
                    for component, coords in enumerate(coords_by_component)
                ):
                    if profile_detail:
                        fallback_started_at = time.perf_counter()
                    coords_by_component = [
                        None if skip_components[component] else array("f", [0.0]) * (count * 2)
                        for component in range(component_count)
                    ]
                    for key_index in range(count):
                        sample = _bone_anim_sample(
                            target,
                            values,
                            value_width,
                            key_index,
                            edit_translation,
                            edit_rotation_inv,
                        )
                        frame = times[key_index] * fps
                        base = key_index * value_width
                        for component, coords in enumerate(coords_by_component):
                            if coords is None:
                                continue
                            target_index = target_offset + component
                            coords[key_index * 2] = frame
                            coords[key_index * 2 + 1] = (
                                sample[target_index]
                                if sample is not None and target_index < len(sample)
                                else values[base + component]
                            )
                    if profile_detail:
                        fallback_ms += (time.perf_counter() - fallback_started_at) * 1000.0

                for component, coords in enumerate(coords_by_component):
                    if coords is None:
                        continue
                    target_index = target_offset + component
                    write_key = _fcurve_write_key(armature, channel, data_path, target_index)
                    if write_key in written_fcurves:
                        continue
                    written_fcurves.add(write_key)
                    action = _animation_action_for(armature, armature, actions, "", channel)
                    if profile_detail:
                        fcurve_started_at = time.perf_counter()
                    fcurve = _ensure_fcurve(action, armature, data_path, target_index, group_name=name)
                    if profile_detail:
                        fcurve_ms += (time.perf_counter() - fcurve_started_at) * 1000.0
                        write_started_at = time.perf_counter()
                    _write_fcurve_points(fcurve, coords, interpolation)
                    if profile_detail:
                        write_ms += (time.perf_counter() - write_started_at) * 1000.0

                end_frame = max(end_frame, int(times[count - 1] * fps + 0.5))
                continue

            for component in range(component_count):
                target_index = target_offset + component
                value_index = 0 if is_partial else component
                if _bone_component_is_default(channel, target, target_index, value_index):
                    skipped_default_fcurves += 1
                    continue
                write_key = _fcurve_write_key(armature, channel, data_path, target_index)
                if write_key in written_fcurves:
                    continue
                written_fcurves.add(write_key)
                action = _animation_action_for(armature, armature, actions, "", channel)
                if profile_detail:
                    fcurve_started_at = time.perf_counter()
                fcurve = _ensure_fcurve(action, armature, data_path, target_index, group_name=name)
                if profile_detail:
                    fcurve_ms += (time.perf_counter() - fcurve_started_at) * 1000.0
                    fallback_started_at = time.perf_counter()
                coords = array("f", [0.0]) * (count * 2)
                for key_index in range(count):
                    coords[key_index * 2] = times[key_index] * fps
                    coords[key_index * 2 + 1] = values[key_index * value_width + value_index]
                if profile_detail:
                    fallback_ms += (time.perf_counter() - fallback_started_at) * 1000.0

                if profile_detail:
                    write_started_at = time.perf_counter()
                _write_fcurve_points(
                    fcurve,
                    coords,
                    interpolation,
                    times=times,
                    fps=fps,
                    in_tangents=None if not is_partial else in_tangents,
                    out_tangents=None if not is_partial else out_tangents,
                    value_width=value_width,
                    value_index=value_index,
                )
                if profile_detail:
                    write_ms += (time.perf_counter() - write_started_at) * 1000.0

            end_frame = max(end_frame, int(times[count - 1] * fps + 0.5))

    if profile_detail:
        before_stash_at = time.perf_counter()
    _stash_animation_actions(actions)
    _register_actions_frame_range(actions, frame_bounds)
    if profile_detail:
        stash_ms = (time.perf_counter() - before_stash_at) * 1000.0
    else:
        stash_ms = 0.0
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame
    if profile_detail:
        _profile_log(
            "apply_bone_animations_detail "
            f"name={armature.name!r} joints={len(joint_names)} channels={channel_count} "
            f"fcurves={len(written_fcurves)} skipped_default={skipped_default_fcurves} "
            f"prep={prep_ms:.3f}ms "
            f"coords={coords_ms:.3f}ms fallback={fallback_ms:.3f}ms "
            f"ensure_fcurve={fcurve_ms:.3f}ms write={write_ms:.3f}ms "
            f"stash={stash_ms:.3f}ms total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )


def _bone_animation_channels(
    joint_index: int,
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
    pose_channels_by_joint: list[list[dict]] | None = None,
) -> list[dict]:
    if pose_channels_by_joint is not None and joint_index < len(pose_channels_by_joint):
        return pose_channels_by_joint[joint_index] or []

    node = node_data.get(int(joint_nodes[joint_index]) if joint_index < len(joint_nodes) else -1)
    return list(node.anim_channels or []) if node else []


def _ensure_fcurve(
    action: bpy.types.Action,
    obj: bpy.types.ID,
    data_path: str,
    index: int | None,
    group_name: str = "Transform",
):
    slot, channelbag = _ensure_action_channelbag(action, obj)
    if channelbag is not None:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        return _new_channelbag_fcurve(channelbag, data_path, index, group_name)

    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        existing = _find_fcurve(fcurves, data_path, index)
        if existing is not None:
            return existing
        if index is None:
            return fcurves.new(data_path=data_path, action_group=group_name)
        return fcurves.new(data_path=data_path, index=index, action_group=group_name)

    ensure = getattr(action, "fcurve_ensure_for_datablock", None)
    if not ensure:
        raise RuntimeError("Blender Action API does not expose fcurve creation")

    try:
        obj.animation_data_create()
        if obj.animation_data.action != action:
            obj.animation_data.action = action
    except Exception:
        pass

    if index is None:
        fcurve = ensure(obj, data_path, group_name=group_name)
    else:
        fcurve = ensure(obj, data_path, index=index, group_name=group_name)
    if len(fcurve.keyframe_points) == 0:
        return fcurve

    channelbag = _channelbag_for_fcurve(action, fcurve)
    if not channelbag:
        return fcurve
    if index is None:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        fcurve = _new_channelbag_fcurve(channelbag, data_path, None, group_name)
    else:
        existing = _find_fcurve(channelbag.fcurves, data_path, index)
        if existing is not None:
            return existing
        fcurve = _new_channelbag_fcurve(channelbag, data_path, index, group_name)
    return fcurve


def _find_fcurve(fcurves, data_path: str, index: int | None):
    try:
        if index is None:
            found = fcurves.find(data_path)
        else:
            found = fcurves.find(data_path, index=index)
        if found is not None:
            return found
    except Exception:
        pass

    for fcurve in fcurves:
        try:
            if fcurve.data_path != data_path:
                continue
            if index is None or int(fcurve.array_index) == int(index):
                return fcurve
        except Exception:
            continue
    return None


def _channel_tangents(channel: dict) -> tuple[object | None, object | None]:
    if _channel_interpolation(channel) != _INTERPOLATION_HERMITE:
        return None, None

    in_tangents = _buffer_view(_channel_in_tangents(channel), "f")
    out_tangents = _buffer_view(_channel_out_tangents(channel), "f")
    if in_tangents is None or out_tangents is None:
        return None, None
    return in_tangents, out_tangents


def _write_fcurve_points(
    fcurve,
    coords,
    interpolation: str,
    *,
    times=None,
    fps: float = 1.0,
    in_tangents=None,
    out_tangents=None,
    value_width: int = 0,
    value_index: int = 0,
    tangent_value=None,
) -> None:
    count = len(coords) // 2
    _clear_fcurve_points(fcurve)
    fcurve.keyframe_points.add(count)
    fcurve.keyframe_points.foreach_set("co", coords)

    use_cubic = (
        interpolation == "BEZIER"
        and times is not None
        and in_tangents is not None
        and out_tangents is not None
        and value_width > 0
        and count > 0
    )

    _foreach_set_keyframe_enum(
        fcurve.keyframe_points,
        "interpolation",
        "BEZIER" if use_cubic else interpolation,
        count,
    )

    if use_cubic:
        _apply_cubic_handles(
            fcurve,
            coords,
            times,
            fps,
            in_tangents,
            out_tangents,
            value_width,
            value_index,
            tangent_value,
        )

    if use_cubic:
        fcurve.update()


def _clear_fcurve_points(fcurve) -> None:
    points = fcurve.keyframe_points
    if not points:
        return
    try:
        points.clear()
        return
    except Exception:
        pass
    while points:
        try:
            points.remove(points[-1], fast=True)
        except TypeError:
            points.remove(points[-1])
        except Exception:
            break


def _foreach_set_keyframe_enum(points, prop: str, value: str, count: int) -> None:
    enum_value = _keyframe_enum_value(prop, value)
    if enum_value is None:
        for point in points:
            setattr(point, prop, value)
        return
    try:
        points.foreach_set(prop, _keyframe_enum_array(enum_value, count))
    except Exception:
        for point in points:
            setattr(point, prop, value)


def _keyframe_enum_array(enum_value: int, count: int) -> array:
    key = (enum_value, count)
    cached = _KEYFRAME_ENUM_ARRAYS.get(key)
    if cached is not None:
        return cached
    typecode = "B" if 0 <= int(enum_value) <= 255 else "i"
    values = array(typecode, [enum_value]) * count
    _KEYFRAME_ENUM_ARRAYS[key] = values
    return values


def _keyframe_enum_value(prop: str, value: str) -> int | None:
    key = (prop, value)
    cached = _KEYFRAME_ENUM_VALUES.get(key)
    if cached is not None:
        return cached
    try:
        enum_value = bpy.types.Keyframe.bl_rna.properties[prop].enum_items[value].value
    except Exception:
        return None
    _KEYFRAME_ENUM_VALUES[key] = enum_value
    return enum_value


def _apply_cubic_handles(
    fcurve,
    coords,
    times,
    fps: float,
    in_tangents,
    out_tangents,
    value_width: int,
    value_index: int,
    tangent_value,
) -> None:
    points = fcurve.keyframe_points
    count = len(points)
    for index, point in enumerate(points):
        frame = coords[index * 2]
        value = coords[index * 2 + 1]
        point.handle_left_type = "FREE"
        point.handle_right_type = "FREE"

        if index > 0:
            dt = max(0.0, float(times[index] - times[index - 1]))
            tangent = _output_tangent(in_tangents[index * value_width + value_index], tangent_value)
            point.handle_left = (frame - (dt * fps) / 3.0, value - (tangent * dt) / 3.0)
        else:
            point.handle_left = (frame, value)

        if index + 1 < count:
            dt = max(0.0, float(times[index + 1] - times[index]))
            tangent = _output_tangent(out_tangents[index * value_width + value_index], tangent_value)
            point.handle_right = (frame + (dt * fps) / 3.0, value + (tangent * dt) / 3.0)
        else:
            point.handle_right = (frame, value)


def _output_tangent(value: float, tangent_value) -> float:
    if tangent_value is None:
        return float(value)
    converted = tangent_value(float(value))
    return float(value) if converted is None else float(converted)


def _anim_target_path(target: int) -> tuple[str, int]:
    if target == _ANIM_TRANSLATION:
        return "location", 3
    if target == _ANIM_ROTATION_QUAT:
        return "rotation_quaternion", 4
    if target == _ANIM_SCALE:
        return "scale", 3
    return "", 0


def _blender_interpolation(interpolation: int) -> str:
    if interpolation == _INTERPOLATION_STEP:
        return "CONSTANT"
    if interpolation == _INTERPOLATION_HERMITE:
        return "BEZIER"
    if interpolation == _INTERPOLATION_LINEAR:
        return "LINEAR"
    return "LINEAR"


def _apply_material_variants(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None = None,
) -> None:
    variants = data.material_variants or []
    if not variants:
        return

    obj["assetkit_material_variant_count"] = len(variants)
    for index, variant in enumerate(variants):
        prefix = f"assetkit_material_variant_{index}"
        obj[f"{prefix}_index"] = int(variant.get("variant_index") or 0)
        obj[f"{prefix}_name"] = variant.get("variant_name") or ""
        obj[f"{prefix}_material"] = variant.get("material_name") or ""
        material = _create_variant_material(data, variant, material_cache)
        if material:
            slot = _ensure_material_slot(obj.data, material)
            obj[f"{prefix}_slot"] = slot


def _ensure_material_slot(mesh: bpy.types.Mesh, material: bpy.types.Material) -> int:
    for index, slot_material in enumerate(mesh.materials):
        if slot_material == material:
            return index
    mesh.materials.append(material)
    return len(mesh.materials) - 1


def _create_variant_material(
    data: MeshPrimitiveData,
    variant: dict,
    material_cache: dict[object, bpy.types.Material] | None,
) -> bpy.types.Material | None:
    raw = variant.get("material")
    if not isinstance(raw, dict):
        return None
    return _create_material(_variant_material_data(data, variant, raw), material_cache)


def _variant_material_data(data: MeshPrimitiveData, variant: dict, raw: dict) -> MeshPrimitiveData:
    values = {
        "material_name": _variant_material_name(data, variant, raw),
        "base_color": tuple(raw.get("base_color") or data.base_color),
        "transparent_color": tuple(raw.get("transparent_color") or data.transparent_color),
        "emissive_color": tuple(raw.get("emissive_color") or data.emissive_color),
        "specular_color": tuple(raw.get("specular_color") or data.specular_color),
        "sheen_color": tuple(raw.get("sheen_color") or data.sheen_color),
        "volume_attenuation_color": tuple(raw.get("volume_attenuation_color") or data.volume_attenuation_color),
        "diffuse_transmission_color": tuple(
            raw.get("diffuse_transmission_color") or data.diffuse_transmission_color
        ),
        "metallic": _raw_float(raw, "metallic", data.metallic),
        "roughness": _raw_float(raw, "roughness", data.roughness),
        "alpha_cutoff": _raw_float(raw, "alpha_cutoff", data.alpha_cutoff),
        "transparent_amount": _raw_float(raw, "transparent_amount", data.transparent_amount),
        "opacity": _raw_float(raw, "opacity", data.opacity),
        "normal_scale": _raw_float(raw, "normal_scale", data.normal_scale),
        "occlusion_strength": _raw_float(raw, "occlusion_strength", data.occlusion_strength),
        "emissive_strength": _raw_float(raw, "emissive_strength", data.emissive_strength),
        "specular_strength": _raw_float(raw, "specular_strength", data.specular_strength),
        "ior": _raw_float(raw, "ior", data.ior),
        "clearcoat": _raw_float(raw, "clearcoat", data.clearcoat),
        "clearcoat_roughness": _raw_float(raw, "clearcoat_roughness", data.clearcoat_roughness),
        "clearcoat_normal_scale": _raw_float(raw, "clearcoat_normal_scale", data.clearcoat_normal_scale),
        "transmission": _raw_float(raw, "transmission", data.transmission),
        "sheen_roughness": _raw_float(raw, "sheen_roughness", data.sheen_roughness),
        "iridescence": _raw_float(raw, "iridescence", data.iridescence),
        "iridescence_ior": _raw_float(raw, "iridescence_ior", data.iridescence_ior),
        "iridescence_thickness_minimum": _raw_float(
            raw,
            "iridescence_thickness_minimum",
            data.iridescence_thickness_minimum,
        ),
        "iridescence_thickness_maximum": _raw_float(
            raw,
            "iridescence_thickness_maximum",
            data.iridescence_thickness_maximum,
        ),
        "volume_thickness": _raw_float(raw, "volume_thickness", data.volume_thickness),
        "volume_attenuation_distance": _raw_float(
            raw,
            "volume_attenuation_distance",
            data.volume_attenuation_distance,
        ),
        "anisotropy": _raw_float(raw, "anisotropy", data.anisotropy),
        "anisotropy_rotation": _raw_float(raw, "anisotropy_rotation", data.anisotropy_rotation),
        "diffuse_transmission": _raw_float(raw, "diffuse_transmission", data.diffuse_transmission),
        "dispersion": _raw_float(raw, "dispersion", data.dispersion),
        "alpha_mode": _raw_int(raw, "alpha_mode", data.alpha_mode),
        "transparent_opaque": _raw_int(raw, "transparent_opaque", data.transparent_opaque),
        "double_sided": bool(raw.get("double_sided", data.double_sided)),
        "has_sheen": bool(raw.get("has_sheen", data.has_sheen)),
        "material_type": _raw_int(raw, "material_type", data.material_type),
        "file_type": _raw_int(raw, "file_type", data.file_type),
        "material_key": _raw_int(raw, "material_key", data.material_key),
        "texture_infos": _variant_texture_infos(data.texture_infos, raw.get("texture_infos") or {}),
        "material_extra": raw.get("material_extra"),
        "source_extra": raw.get("source_extra"),
    }

    for name in _MATERIAL_TEXTURE_FIELDS:
        values[name] = raw.get(name) or getattr(data, name)

    return replace(data, **values)


def _variant_material_name(data: MeshPrimitiveData, variant: dict, raw: dict) -> str:
    name = raw.get("material_name") or variant.get("material_name") or ""
    if name:
        return str(name)

    base = data.material_name or data.name or "AssetKitMaterial"
    suffix = variant.get("variant_name") or f"Variant_{int(variant.get('variant_index') or 0)}"
    return f"{base}_{suffix}"


def _raw_float(raw: dict, key: str, fallback: float) -> float:
    value = raw.get(key)
    return float(value) if value is not None else float(fallback)


def _raw_int(raw: dict, key: str, fallback: int) -> int:
    value = raw.get(key)
    return int(value) if value is not None else int(fallback)


def _raw_texture_infos(raw_infos: dict) -> dict[str, TextureRefData]:
    texture_infos = {}
    for role, info in raw_infos.items():
        texture_infos[str(role)] = TextureRefData(
            role=str(role),
            path=info.get("path") or "",
            image_name=info.get("image_name") or "",
            sampler_name=info.get("sampler_name") or "",
            color_space=info.get("color_space") or "",
            channels=info.get("channels") or "",
            texcoord=info.get("texcoord") or "",
            coord_input_name=info.get("coord_input_name") or "",
            slot=int(info.get("slot") or 0),
            wrap_s=int(info.get("wrap_s") or 1),
            wrap_t=int(info.get("wrap_t") or 1),
            wrap_p=int(info.get("wrap_p") or 1),
            min_filter=int(info.get("min_filter") or 0),
            mag_filter=int(info.get("mag_filter") or 0),
            mip_filter=int(info.get("mip_filter") or 0),
            has_transform=bool(info.get("has_transform")),
            transform_offset=tuple(info.get("transform_offset") or (0.0, 0.0)),
            transform_scale=tuple(info.get("transform_scale") or (1.0, 1.0)),
            transform_rotation=_raw_float(info, "transform_rotation", 0.0),
            transform_slot=int(info.get("transform_slot") if info.get("transform_slot") is not None else -1),
            texture_extra=info.get("texture_extra"),
            texref_extra=info.get("texref_extra"),
            image_extra=info.get("image_extra"),
            sampler_extra=info.get("sampler_extra"),
        )
    return texture_infos


def _variant_texture_infos(
    base_infos: dict[str, TextureRefData] | None,
    raw_infos: dict,
) -> dict[str, TextureRefData]:
    texture_infos = {
        role: replace(info)
        for role, info in (base_infos or {}).items()
    }
    texture_infos.update(_raw_texture_infos(raw_infos))
    return texture_infos


def _apply_assetkit_extra_props(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    obj["assetkit_primitive_type"] = int(data.primitive_type)
    obj["assetkit_primitive_mode"] = int(data.primitive_mode)
    obj["assetkit_vertex_count"] = int(data.vertex_count)
    obj["assetkit_loop_count"] = int(data.loop_count)
    obj["assetkit_face_count"] = int(data.face_count)
    obj["assetkit_node_index"] = int(data.node_index)
    obj["assetkit_zero_copy_flags"] = int(data.zero_copy_flags)
    _set_assetkit_json_prop(obj, "assetkit_primitive_extra_json", data.primitive_extra)
    _set_assetkit_json_prop(obj, "assetkit_mesh_extra_json", data.mesh_extra)
    _set_assetkit_json_prop(obj, "assetkit_geometry_extra_json", data.geometry_extra)
    _apply_gaussian_splat_props(obj, data)


def _apply_gaussian_splat_props(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    if not data.has_gsplat:
        return

    obj["assetkit_gaussian_splat"] = True
    obj["assetkit_gaussian_splat_kernel"] = _gsplat_kernel_name(data.gsplat_kernel)
    obj["assetkit_gaussian_splat_color_space"] = _gsplat_color_space_name(data.gsplat_color_space)
    obj["assetkit_gaussian_splat_projection"] = _gsplat_projection_name(data.gsplat_projection)
    obj["assetkit_gaussian_splat_sorting_method"] = _gsplat_sorting_method_name(
        data.gsplat_sorting_method
    )
    obj["assetkit_gaussian_splat_decoded_count"] = int(data.gsplat_decoded_count)
    obj["assetkit_gaussian_splat_kernel_value"] = int(data.gsplat_kernel)
    obj["assetkit_gaussian_splat_color_space_value"] = int(data.gsplat_color_space)
    obj["assetkit_gaussian_splat_projection_value"] = int(data.gsplat_projection)
    obj["assetkit_gaussian_splat_sorting_method_value"] = int(data.gsplat_sorting_method)


def _gsplat_kernel_name(value: int) -> str:
    return {
        1: "ellipse",
    }.get(int(value), "unknown")


def _gsplat_color_space_name(value: int) -> str:
    return {
        1: "srgb_rec709_display",
        2: "lin_rec709_display",
    }.get(int(value), "unknown")


def _gsplat_projection_name(value: int) -> str:
    return {
        0: "perspective",
        1: "orthographic",
    }.get(int(value), "unknown")


def _gsplat_sorting_method_name(value: int) -> str:
    return {
        0: "camera_distance",
        1: "none",
    }.get(int(value), "unknown")


def _create_material(
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None = None,
) -> bpy.types.Material | None:
    if not _has_material_data(data):
        return None

    profile_detail = _PROFILE_MATERIAL_STATS is not None
    profile_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = profile_started_at
    cache_key_ms = 0.0
    new_ms = 0.0
    simple_ms = 0.0
    nodes_ms = 0.0
    props_ms = 0.0
    settings_ms = 0.0
    textures_ms = 0.0
    animation_ms = 0.0

    def lap_ms() -> float:
        nonlocal phase_started_at
        if not profile_detail:
            return 0.0
        now = time.perf_counter()
        elapsed = (now - phase_started_at) * 1000.0
        phase_started_at = now
        return elapsed

    cache_key = _material_cache_key(data)
    cache_key_ms = lap_ms()
    if material_cache is not None and cache_key in material_cache:
        if profile_detail:
            _record_material_profile(
                cache_hit=True,
                cache_key_ms=cache_key_ms,
                new_ms=0.0,
                simple_ms=0.0,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return material_cache[cache_key]

    color_attr = _color_attribute_name(data)
    material_name = data.material_name or f"{data.name}_Material"
    if data.material_name and color_attr:
        material_name = f"{material_name}_{color_attr}"
    base_color = _material_base_color(data)
    mat = bpy.data.materials.new(material_name)
    mat.diffuse_color = base_color
    new_ms = lap_ms()
    if _can_use_simple_material(data, color_attr):
        _configure_simple_material(mat, data, base_color)
        simple_ms = lap_ms()
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=simple_ms,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    if _can_defer_base_color_texture_material(data, color_attr, base_color):
        _configure_deferred_base_color_texture_material(mat, data, base_color)
        simple_ms = lap_ms()
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=simple_ms,
                nodes_ms=0.0,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    if _can_use_scalar_principled_material(data, color_attr):
        if _configure_scalar_principled_material(mat, data, base_color):
            nodes_ms = lap_ms()
            _set_assetkit_material_props(mat, data)
            _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
            _set_assetkit_json_prop(mat, "assetkit_material_source_extra_json", data.source_extra)
            props_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=props_ms,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    if _can_use_classic_texture_fast_material(data, color_attr):
        if _configure_classic_texture_fast_material(mat, data, base_color):
            nodes_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    if _can_use_base_color_texture_fast_material(data, color_attr, base_color):
        if _configure_base_color_texture_fast_material(mat, data, base_color):
            nodes_ms = lap_ms()
            if material_cache is not None:
                material_cache[cache_key] = mat
            if profile_detail:
                _record_material_profile(
                    cache_hit=False,
                    cache_key_ms=cache_key_ms,
                    new_ms=new_ms,
                    simple_ms=0.0,
                    nodes_ms=nodes_ms,
                    props_ms=0.0,
                    settings_ms=0.0,
                    textures_ms=0.0,
                    animation_ms=0.0,
                    total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
                )
            return mat

    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        if material_cache is not None:
            material_cache[cache_key] = mat
        if profile_detail:
            nodes_ms = lap_ms()
            _record_material_profile(
                cache_hit=False,
                cache_key_ms=cache_key_ms,
                new_ms=new_ms,
                simple_ms=0.0,
                nodes_ms=nodes_ms,
                props_ms=0.0,
                settings_ms=0.0,
                textures_ms=0.0,
                animation_ms=0.0,
                total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
            )
        return mat

    color_target = bsdf
    color_input = "Base Color"
    alpha_socket = bsdf.inputs.get("Alpha")
    if _is_unlit_material(data):
        color_target, alpha_socket = _configure_unlit_shader(mat, data.alpha_mode)
        color_input = "Color"
    else:
        if _is_classic_lit_material(data):
            _set_input(bsdf, "Metallic", 0.0)
            _set_input(bsdf, "Roughness", _classic_roughness(data.specular_strength))
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _classic_specular(data))
        elif _is_specular_glossiness_material(data):
            _set_input(bsdf, "Metallic", 0.0)
            _set_input(bsdf, "Roughness", data.roughness)
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), 0.5)
        else:
            _set_input(bsdf, "Metallic", data.metallic)
            _set_input(bsdf, "Roughness", data.roughness)
            _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _pbr_specular_level(data))
        if _has_emission(data):
            _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))
            _set_first_input(bsdf, ("Emission Strength",), _emission_strength(data))
        if _has_specular(data):
            _set_first_input(bsdf, ("Specular Tint",), (*data.specular_color, 1.0))
        _set_first_input(bsdf, ("IOR",), _material_ior(data))
        if _has_clearcoat(data):
            _set_first_input(bsdf, ("Coat Weight", "Clearcoat"), data.clearcoat)
            _set_first_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), data.clearcoat_roughness)
        if _has_transmission(data):
            _set_first_input(bsdf, ("Transmission Weight", "Transmission"), data.transmission)
        if _has_sheen(data):
            _set_first_input(bsdf, ("Sheen Weight", "Sheen"), 1.0 if data.has_sheen else 0.0)
            _set_first_input(bsdf, ("Sheen Tint",), (*data.sheen_color, 1.0))
            _set_first_input(bsdf, ("Sheen Roughness",), data.sheen_roughness)
        if _has_anisotropy(data):
            _set_first_input(bsdf, ("Anisotropic",), data.anisotropy)
            _set_first_input(bsdf, ("Anisotropic Rotation",), _blender_anisotropy_rotation(data.anisotropy_rotation))
        if _has_iridescence(data):
            _set_first_input(bsdf, ("Thin Film IOR",), data.iridescence_ior)
            _set_first_input(bsdf, ("Thin Film Weight", "Iridescence Weight", "Iridescence"), data.iridescence)
            _set_first_input(bsdf, ("Thin Film Thickness",), data.iridescence_thickness_maximum)
        if data.dispersion:
            _set_first_input(bsdf, ("Dispersion",), data.dispersion)
        if _has_diffuse_transmission(data):
            _set_first_input(bsdf, ("Diffuse Transmission Weight", "Diffuse Transmission"), data.diffuse_transmission)
            _set_first_input(bsdf, ("Diffuse Transmission Color",), (*data.diffuse_transmission_color, 1.0))

    _set_input(color_target, color_input, base_color)
    if alpha_socket:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass
    nodes_ms = lap_ms()

    _set_assetkit_material_props(mat, data)
    _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
    _set_assetkit_json_prop(mat, "assetkit_material_source_extra_json", data.source_extra)
    props_ms = lap_ms()
    settings_node = _ensure_gltf_settings_node(mat, data, bsdf)
    settings_ms = lap_ms()

    global _ACTIVE_SEPARATE_COLOR_CACHE, _ACTIVE_TEXTURE_NODE_CACHE
    previous_texture_node_cache = _ACTIVE_TEXTURE_NODE_CACHE
    previous_separate_color_cache = _ACTIVE_SEPARATE_COLOR_CACHE
    _ACTIVE_TEXTURE_NODE_CACHE = {}
    _ACTIVE_SEPARATE_COLOR_CACHE = {}
    try:
        if data.base_color_texture or color_attr:
            _link_base_color(mat, color_target, data, color_attr, color_input, alpha_socket)
        if data.metallic_roughness_texture:
            _link_metallic_roughness_texture(
                mat,
                bsdf,
                data.metallic_roughness_texture,
                _texture_info(data, "metallic_roughness"),
                metallic_factor=data.metallic,
                roughness_factor=data.roughness,
            )
        if data.occlusion_texture and bsdf == color_target:
            _link_occlusion_texture(mat, bsdf, data, settings_node)
        if data.normal_texture:
            _link_normal_texture(mat, bsdf, data.normal_texture, data.normal_scale, _texture_info(data, "normal"))
        if data.emissive_texture:
            _link_emissive_texture(
                mat,
                bsdf,
                data,
            )
        if data.transparent_texture and alpha_socket:
            _link_transparent_texture(mat, alpha_socket, data)
        if data.specular_texture:
            if int(data.material_type) == _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS:
                _link_specular_glossiness_texture(mat, bsdf, data)
            else:
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.specular_texture,
                    ("Specular IOR Level", "Specular"),
                    colorspace="Non-Color",
                    channel="Alpha",
                    factor=_pbr_specular_level(data),
                    tex_info=_texture_info(data, "specular"),
                )
        if data.specular_color_texture:
            _link_color_texture(
                mat,
                bsdf,
                data.specular_color_texture,
                ("Specular Tint",),
                colorspace="sRGB",
                factor=(*data.specular_color, 1.0),
                tex_info=_texture_info(data, "specular_color"),
            )
        if data.clearcoat_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.clearcoat_texture,
                ("Coat Weight", "Clearcoat"),
                colorspace="Non-Color",
                channel="Red",
                factor=data.clearcoat,
                tex_info=_texture_info(data, "clearcoat"),
            )
        if data.clearcoat_roughness_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.clearcoat_roughness_texture,
                ("Coat Roughness", "Clearcoat Roughness"),
                colorspace="Non-Color",
                channel="Green",
                factor=data.clearcoat_roughness,
                tex_info=_texture_info(data, "clearcoat_roughness"),
            )
        if data.clearcoat_normal_texture:
            _link_normal_texture(
                mat,
                bsdf,
                data.clearcoat_normal_texture,
                data.clearcoat_normal_scale,
                _texture_info(data, "clearcoat_normal"),
                input_name="Coat Normal",
            )
        if data.transmission_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.transmission_texture,
                ("Transmission Weight", "Transmission"),
                colorspace="Non-Color",
                channel="Red",
                factor=data.transmission,
                tex_info=_texture_info(data, "transmission"),
            )
        if data.sheen_color_texture:
            _link_color_texture(
                mat,
                bsdf,
                data.sheen_color_texture,
                ("Sheen Tint",),
                colorspace="sRGB",
                factor=(*data.sheen_color, 1.0),
                tex_info=_texture_info(data, "sheen_color"),
            )
        if data.sheen_roughness_texture:
            _link_factor_texture(
                mat,
                bsdf,
                data.sheen_roughness_texture,
                ("Sheen Roughness",),
                colorspace="Non-Color",
                channel="Alpha",
                factor=data.sheen_roughness,
                tex_info=_texture_info(data, "sheen_roughness"),
            )
        if data.iridescence_thickness_texture:
            _link_range_texture(
                mat,
                bsdf,
                data.iridescence_thickness_texture,
                ("Thin Film Thickness",),
                colorspace="Non-Color",
                channel="Green",
                minimum=data.iridescence_thickness_minimum,
                maximum=data.iridescence_thickness_maximum,
                tex_info=_texture_info(data, "iridescence_thickness"),
            )
        if data.iridescence_texture:
            iridescence_inputs = ("Thin Film Weight", "Iridescence Weight", "Iridescence")
            if _has_input(bsdf, iridescence_inputs):
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.iridescence_texture,
                    iridescence_inputs,
                    colorspace="Non-Color",
                    channel="Red",
                    factor=data.iridescence,
                    tex_info=_texture_info(data, "iridescence"),
                )
            elif settings_node:
                _link_factor_texture(
                    mat,
                    settings_node,
                    data.iridescence_texture,
                    ("Iridescence Factor",),
                    colorspace="Non-Color",
                    channel="Red",
                    factor=data.iridescence,
                    tex_info=_texture_info(data, "iridescence"),
                )
        if data.volume_thickness_texture:
            volume_inputs = ("Volume Thickness", "Thickness")
            if _has_input(bsdf, volume_inputs):
                _link_factor_texture(
                    mat,
                    bsdf,
                    data.volume_thickness_texture,
                    volume_inputs,
                    colorspace="Non-Color",
                    channel="Green",
                    factor=data.volume_thickness,
                    tex_info=_texture_info(data, "volume_thickness"),
                )
            elif settings_node:
                _link_factor_texture(
                    mat,
                    settings_node,
                    data.volume_thickness_texture,
                    ("Thickness",),
                    colorspace="Non-Color",
                    channel="Green",
                    factor=data.volume_thickness,
                    tex_info=_texture_info(data, "volume_thickness"),
                )
        diffuse_transmission_inputs = ("Diffuse Transmission Weight", "Diffuse Transmission")
        if data.anisotropy_texture:
            _link_anisotropy_texture(mat, bsdf, data)
        if data.diffuse_transmission_texture and _has_input(bsdf, diffuse_transmission_inputs):
            _link_factor_texture(
                mat,
                bsdf,
                data.diffuse_transmission_texture,
                diffuse_transmission_inputs,
                colorspace="Non-Color",
                channel="Alpha",
                factor=data.diffuse_transmission,
                tex_info=_texture_info(data, "diffuse_transmission"),
            )
        if data.diffuse_transmission_color_texture and _has_input(bsdf, ("Diffuse Transmission Color",)):
            _link_color_texture(
                mat,
                bsdf,
                data.diffuse_transmission_color_texture,
                ("Diffuse Transmission Color",),
                colorspace="sRGB",
                factor=(*data.diffuse_transmission_color, 1.0),
                tex_info=_texture_info(data, "diffuse_transmission_color"),
            )
        if _has_diffuse_transmission(data) and not _has_input(bsdf, diffuse_transmission_inputs):
            _link_diffuse_transmission_shader(mat, data)
        if data.volume_thickness > 0.0:
            _link_volume_absorption(mat, data)
        if _has_volume_scatter(data):
            _link_volume_scatter(mat, data)
    finally:
        _ACTIVE_TEXTURE_NODE_CACHE = previous_texture_node_cache
        _ACTIVE_SEPARATE_COLOR_CACHE = previous_separate_color_cache
    textures_ms = lap_ms()

    _apply_material_animation(mat, data, bsdf, color_target, color_input, alpha_socket, settings_node)
    animation_ms = lap_ms()

    if material_cache is not None:
        material_cache[cache_key] = mat
    if profile_detail:
        _record_material_profile(
            cache_hit=False,
            cache_key_ms=cache_key_ms,
            new_ms=new_ms,
            simple_ms=0.0,
            nodes_ms=nodes_ms,
            props_ms=props_ms,
            settings_ms=settings_ms,
            textures_ms=textures_ms,
            animation_ms=animation_ms,
            total_ms=(time.perf_counter() - profile_started_at) * 1000.0,
        )
    return mat


def _can_use_simple_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if data.material_anim_channels:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return False
    if data.texture_infos:
        return False
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return False
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return False
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return False
    if float(data.volume_thickness) > 0.0 or float(data.dispersion) != 0.0:
        return False
    return True


def _can_use_scalar_principled_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if data.material_anim_channels:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return False
    if data.texture_infos:
        return False
    if float(data.volume_thickness) > 0.0 or _has_volume_scatter(data):
        return False
    return True


def _can_use_base_color_texture_fast_material(
    data: MeshPrimitiveData,
    color_attr: str,
    base_color: tuple[float, float, float, float],
) -> bool:
    if color_attr or not data.base_color_texture:
        return False
    if data.material_anim_channels:
        return False
    if data.material_extra or data.source_extra or data.material_variants:
        return False
    if _is_unlit_material(data) or _is_classic_lit_material(data) or _is_specular_glossiness_material(data):
        return False
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS if name != "base_color_texture"):
        return False
    texture_infos = data.texture_infos or {}
    if any(role != "base_color" for role in texture_infos):
        return False
    tex_info = _texture_info(data, "base_color")
    if tex_info is not None:
        if tex_info.has_transform or _texture_uv_slot(tex_info) != 0:
            return False
        if tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra:
            return False
    if not _tuple_close(base_color, (1.0, 1.0, 1.0, 1.0)):
        return False
    if data.alpha_mode or abs(float(data.opacity) - 1.0) > 1e-6:
        return False
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return False
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return False
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return False
    return float(data.volume_thickness) <= 0.0 and float(data.dispersion) == 0.0


def _can_use_classic_texture_fast_material(data: MeshPrimitiveData, color_attr: str) -> bool:
    if color_attr:
        return False
    if not _is_classic_lit_material(data):
        return False
    if data.material_anim_channels or data.material_extra or data.source_extra or data.material_variants:
        return False
    if not data.base_color_texture and not data.normal_texture:
        return False
    if (
        data.metallic_roughness_texture
        or data.occlusion_texture
        or data.emissive_texture
        or data.transparent_texture
        or data.specular_texture
        or data.specular_color_texture
        or data.clearcoat_texture
        or data.clearcoat_roughness_texture
        or data.clearcoat_normal_texture
        or data.transmission_texture
        or data.sheen_color_texture
        or data.sheen_roughness_texture
        or data.iridescence_texture
        or data.iridescence_thickness_texture
        or data.volume_thickness_texture
        or data.anisotropy_texture
        or data.diffuse_transmission_texture
        or data.diffuse_transmission_color_texture
    ):
        return False
    if (
        data.alpha_mode
        or data.transparent_opaque
        or abs(float(data.opacity) - 1.0) > 1e-6
        or abs(float(data.transparent_amount) - 1.0) > 1e-6
        or abs(float(data.occlusion_strength) - 1.0) > 1e-6
        or abs(float(data.emissive_strength) - 1.0) > 1e-6
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
        or abs(float(data.transmission)) > 1e-6
        or abs(float(data.sheen_roughness)) > 1e-6
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.volume_thickness)) > 1e-6
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
        or abs(float(data.diffuse_transmission)) > 1e-6
        or abs(float(data.dispersion)) > 1e-6
        or data.has_sheen
    ):
        return False

    texture_infos = data.texture_infos or {}
    if any(role not in {"base_color", "normal"} for role in texture_infos):
        return False
    for role in ("base_color", "normal"):
        tex_info = _texture_info(data, role)
        if tex_info is None:
            continue
        if tex_info.has_transform or _texture_uv_slot(tex_info) != 0:
            return False
        if tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra:
            return False
    return True


def _can_defer_base_color_texture_material(
    data: MeshPrimitiveData,
    color_attr: str,
    base_color: tuple[float, float, float, float],
) -> bool:
    return (
        _ACTIVE_TEXTURE_LOAD_MODE == "DEFERRED"
        and _can_use_base_color_texture_fast_material(data, color_attr, base_color)
    )


def _configure_deferred_base_color_texture_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> None:
    mat.diffuse_color = base_color
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)
    _set_material_scalar(mat, "metallic", data.metallic)
    _set_material_scalar(mat, "roughness", data.roughness)
    _set_material_scalar(mat, "specular_intensity", _pbr_specular_level(data))
    try:
        mat["assetkit_deferred_material_nodes"] = True
        mat["assetkit_deferred_base_color_texture"] = data.base_color_texture
    except Exception:
        pass
    _queue_deferred_material_nodes(
        mat,
        data.base_color_texture,
        _texture_info(data, "base_color"),
        base_color,
        float(data.metallic),
        float(data.roughness),
        _is_double_sided_material(data),
    )


def _queue_deferred_material_slot(spec: _DeferredMaterialSpec) -> None:
    global _DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE
    _DEFERRED_MATERIAL_SLOT_TASKS.append(spec)
    if not _DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE:
        _DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_material_slot_timer, first_interval=0.001)


def _deferred_material_slot_timer() -> float | None:
    global _DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE
    started_at = time.perf_counter()
    processed = 0
    profile_detail = _PROFILE_MATERIAL_STATS is not None

    while _DEFERRED_MATERIAL_SLOT_TASKS:
        spec = _DEFERRED_MATERIAL_SLOT_TASKS.popleft()
        try:
            _apply_deferred_material_slot(spec)
            processed += 1
        except Exception:
            pass
        if time.perf_counter() - started_at >= _DEFERRED_MATERIAL_SLOT_TIME_BUDGET:
            if profile_detail and processed:
                _profile_log(
                    "deferred_material_slots "
                    f"materials={processed} remaining={len(_DEFERRED_MATERIAL_SLOT_TASKS)} "
                    f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
                )
            return 0.001

    _DEFERRED_MATERIAL_SLOT_TIMER_ACTIVE = False
    if profile_detail and processed:
        _profile_log(
            "deferred_material_slots "
            f"materials={processed} remaining=0 "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return None


def _apply_deferred_material_slot(spec: _DeferredMaterialSpec) -> None:
    if not spec.slots:
        return

    mat = bpy.data.materials.new(spec.name)
    mat.diffuse_color = spec.base_color
    mat.use_backface_culling = not spec.double_sided
    _set_material_scalar(mat, "metallic", spec.metallic)
    _set_material_scalar(mat, "roughness", spec.roughness)
    _set_material_scalar(mat, "specular_intensity", spec.specular if spec.classic else 0.5)
    try:
        mat["assetkit_deferred_material_nodes"] = True
        mat["assetkit_deferred_base_color_texture"] = spec.path
    except Exception:
        pass

    cache = spec.cache
    if cache is not None:
        cache[spec.cache_key] = mat

    for mesh, obj, slot_index, object_material_slot in spec.slots:
        try:
            if not _mesh_ref_alive(mesh):
                continue
            if object_material_slot and obj is not None and _object_ref_alive(obj):
                if slot_index < 0:
                    slot_index = _ensure_object_material_slot(mesh)
                elif slot_index >= len(mesh.materials):
                    continue
                slot = obj.material_slots[slot_index]
                slot.link = "OBJECT"
                slot.material = mat
            else:
                if slot_index < 0:
                    mesh.materials.append(mat)
                elif slot_index < len(mesh.materials):
                    mesh.materials[slot_index] = mat
        except Exception:
            continue

    if spec.classic:
        _queue_deferred_classic_material_nodes(
            mat,
            spec.path,
            spec.tex_info,
            spec.normal_path,
            spec.normal_tex_info,
            spec.base_color,
            spec.roughness,
            spec.specular,
            spec.has_specular_tint,
            spec.specular_color,
            spec.has_emission,
            spec.emissive_color,
            spec.emissive_strength,
            spec.ior,
            spec.normal_scale,
            spec.double_sided,
        )
    else:
        _queue_deferred_material_nodes(
            mat,
            spec.path,
            spec.tex_info,
            spec.base_color,
            spec.metallic,
            spec.roughness,
            spec.double_sided,
        )


def _mesh_ref_alive(mesh: bpy.types.Mesh) -> bool:
    try:
        return bpy.data.meshes.get(mesh.name) is mesh
    except Exception:
        return False


def _object_ref_alive(obj: bpy.types.Object) -> bool:
    try:
        return bpy.data.objects.get(obj.name) is obj
    except Exception:
        return False


def _configure_base_color_texture_fast_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    bsdf_inputs = bsdf.inputs
    if abs(float(data.metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = data.metallic
    if abs(float(data.roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = data.roughness

    tex_info = _texture_info(data, "base_color")
    colorspace = _texture_color_space(tex_info, "sRGB")
    path = data.base_color_texture
    image = _cached_texture_image(path, colorspace) if _should_defer_texture_image(path) else _load_texture_image(path, colorspace)
    if not image and not _should_defer_texture_image(path):
        return False

    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)

    color_socket = bsdf_inputs.get("Base Color")
    color_output = tex.outputs.get("Color")
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    return True


def _new_fast_image_texture_node(tree, path: str, tex_info: TextureRefData | None, colorspace: str):
    if not path:
        return None
    image = _cached_texture_image(path, colorspace) if _should_defer_texture_image(path) else _load_texture_image(path, colorspace)
    if not image and not _should_defer_texture_image(path):
        return None

    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)
    return tex


def _configure_classic_texture_fast_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Roughness", _classic_roughness(data.specular_strength))
    _set_first_input(bsdf, ("Specular IOR Level", "Specular"), _classic_specular(data))
    if _has_emission(data):
        _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))
        _set_first_input(bsdf, ("Emission Strength",), _emission_strength(data))
    if _has_specular(data):
        _set_first_input(bsdf, ("Specular Tint",), (*data.specular_color, 1.0))
    _set_first_input(bsdf, ("IOR",), _material_ior(data))

    base_info = _texture_info(data, "base_color")
    base_tex = _new_fast_image_texture_node(
        tree,
        data.base_color_texture,
        base_info,
        _texture_color_space(base_info, "sRGB"),
    )
    if base_tex and color_socket:
        color_output = base_tex.outputs.get("Color")
        if color_output:
            tree.links.new(color_output, color_socket)

    normal_info = _texture_info(data, "normal")
    normal_tex = _new_fast_image_texture_node(
        tree,
        data.normal_texture,
        normal_info,
        _texture_color_space(normal_info, "Non-Color"),
    )
    normal_socket = bsdf_inputs.get("Normal")
    if normal_tex and normal_socket:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        if abs(float(data.normal_scale) - 1.0) > 1e-6:
            scale = normal_map.inputs.get("Strength")
            if scale:
                scale.default_value = data.normal_scale
        color_output = normal_tex.outputs.get("Color")
        color_input = normal_map.inputs.get("Color")
        normal_output = normal_map.outputs.get("Normal")
        if color_output and color_input:
            tree.links.new(color_output, color_input)
        if normal_output:
            tree.links.new(normal_output, normal_socket)
    return True


def _configure_scalar_principled_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> bool:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)

    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return False

    diffuse_transmission_inputs = ("Diffuse Transmission Weight", "Diffuse Transmission")
    if _has_diffuse_transmission(data) and not _has_input(bsdf, diffuse_transmission_inputs):
        return False
    if float(data.dispersion) != 0.0 and not _has_input(bsdf, ("Dispersion",)):
        return False

    inputs = bsdf.inputs

    def set_input(name: str, value) -> None:
        socket = inputs.get(name)
        if socket:
            try:
                socket.default_value = value
            except TypeError:
                pass

    def set_first(names: tuple[str, ...], value) -> None:
        for name in names:
            socket = inputs.get(name)
            if socket:
                try:
                    socket.default_value = value
                except TypeError:
                    pass
                return

    set_input("Base Color", base_color)
    set_input("Metallic", data.metallic)
    set_input("Roughness", data.roughness)
    set_first(("Specular IOR Level", "Specular"), _pbr_specular_level(data))
    set_first(("IOR",), _material_ior(data))

    alpha_socket = inputs.get("Alpha")
    if alpha_socket:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass

    if _has_emission(data):
        set_input("Emission Color", (*data.emissive_color, 1.0))
        set_first(("Emission Strength",), _emission_strength(data))
    if _has_specular(data):
        set_first(("Specular Tint",), (*data.specular_color, 1.0))
    if _has_clearcoat(data):
        set_first(("Coat Weight", "Clearcoat"), data.clearcoat)
        set_first(("Coat Roughness", "Clearcoat Roughness"), data.clearcoat_roughness)
    if _has_transmission(data):
        set_first(("Transmission Weight", "Transmission"), data.transmission)
    if _has_sheen(data):
        set_first(("Sheen Weight", "Sheen"), 1.0 if data.has_sheen else 0.0)
        set_first(("Sheen Tint",), (*data.sheen_color, 1.0))
        set_first(("Sheen Roughness",), data.sheen_roughness)
    if _has_anisotropy(data):
        set_first(("Anisotropic",), data.anisotropy)
        set_first(("Anisotropic Rotation",), _blender_anisotropy_rotation(data.anisotropy_rotation))
    if _has_iridescence(data):
        set_first(("Thin Film IOR",), data.iridescence_ior)
        set_first(("Thin Film Weight", "Iridescence Weight", "Iridescence"), data.iridescence)
        set_first(("Thin Film Thickness",), data.iridescence_thickness_maximum)
    if data.dispersion:
        set_first(("Dispersion",), data.dispersion)
    if _has_diffuse_transmission(data):
        set_first(diffuse_transmission_inputs, data.diffuse_transmission)
        set_first(("Diffuse Transmission Color",), (*data.diffuse_transmission_color, 1.0))

    return True


def _queue_deferred_material_nodes(
    mat: bpy.types.Material,
    path: str,
    tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
    double_sided: bool,
) -> None:
    if not path:
        return

    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    _DEFERRED_MATERIAL_NODE_TASKS.append(
        (mat, path, tex_info, base_color, metallic, roughness, double_sided)
    )
    if not _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE:
        _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_material_node_timer, first_interval=0.001)


def _queue_deferred_classic_material_nodes(
    mat: bpy.types.Material,
    base_path: str,
    base_tex_info: TextureRefData | None,
    normal_path: str,
    normal_tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    roughness: float,
    specular: float,
    has_specular_tint: bool,
    specular_color: tuple[float, float, float],
    has_emission: bool,
    emissive_color: tuple[float, float, float],
    emissive_strength: float,
    ior: float,
    normal_scale: float,
    double_sided: bool,
) -> None:
    if not base_path and not normal_path:
        return

    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    _DEFERRED_MATERIAL_NODE_TASKS.append(
        (
            "classic",
            mat,
            base_path,
            base_tex_info,
            normal_path,
            normal_tex_info,
            base_color,
            roughness,
            specular,
            has_specular_tint,
            specular_color,
            has_emission,
            emissive_color,
            emissive_strength,
            ior,
            normal_scale,
            double_sided,
        )
    )
    if not _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE:
        _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_material_node_timer, first_interval=0.001)


def _deferred_material_node_timer() -> float | None:
    global _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
    started_at = time.perf_counter()
    processed = 0
    profile_detail = _PROFILE_MATERIAL_STATS is not None

    while _DEFERRED_MATERIAL_NODE_TASKS:
        task = _DEFERRED_MATERIAL_NODE_TASKS.popleft()
        mat = task[1] if task and task[0] == "classic" else task[0]
        try:
            if _material_ref_alive(mat):
                if task and task[0] == "classic":
                    _apply_deferred_classic_texture_material(*task[1:])
                else:
                    _apply_deferred_base_color_texture_material(*task)
                processed += 1
        except Exception:
            pass
        if time.perf_counter() - started_at >= _DEFERRED_MATERIAL_NODE_TIME_BUDGET:
            if profile_detail and processed:
                _profile_log(
                    "deferred_material_nodes "
                    f"materials={processed} remaining={len(_DEFERRED_MATERIAL_NODE_TASKS)} "
                    f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
                )
            return 0.001

    _DEFERRED_MATERIAL_NODE_TIMER_ACTIVE = False
    if profile_detail and processed:
        _profile_log(
            "deferred_material_nodes "
            f"materials={processed} remaining=0 "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return None


def _material_ref_alive(mat: bpy.types.Material) -> bool:
    try:
        return bpy.data.materials.get(mat.name) is mat
    except Exception:
        return False


def _apply_deferred_base_color_texture_material(
    mat: bpy.types.Material,
    path: str,
    tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    metallic: float,
    roughness: float,
    double_sided: bool,
) -> None:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    if abs(float(metallic)) > 1e-6:
        socket = bsdf_inputs.get("Metallic")
        if socket:
            socket.default_value = metallic
    if abs(float(roughness) - 0.5) > 1e-6:
        socket = bsdf_inputs.get("Roughness")
        if socket:
            socket.default_value = roughness

    colorspace = _texture_color_space(tex_info, "sRGB")
    image = _cached_texture_image(path, colorspace)
    tex = tree.nodes.new("ShaderNodeTexImage")
    extension = _texture_extension(tex_info)
    if extension != _TEXTURE_EXTENSION_DEFAULT:
        tex.extension = extension
    interpolation = _texture_interpolation(tex_info)
    if interpolation != _TEXTURE_INTERPOLATION_DEFAULT:
        tex.interpolation = interpolation
    if image:
        tex.image = image
    else:
        _queue_deferred_texture_image(tex, path, colorspace, store_props=False)

    color_output = tex.outputs.get("Color")
    if color_socket and color_output:
        tree.links.new(color_output, color_socket)
    try:
        mat["assetkit_deferred_material_nodes"] = False
    except Exception:
        pass


def _apply_deferred_classic_texture_material(
    mat: bpy.types.Material,
    base_path: str,
    base_tex_info: TextureRefData | None,
    normal_path: str,
    normal_tex_info: TextureRefData | None,
    base_color: tuple[float, float, float, float],
    roughness: float,
    specular: float,
    has_specular_tint: bool,
    specular_color: tuple[float, float, float],
    has_emission: bool,
    emissive_color: tuple[float, float, float],
    emissive_strength: float,
    ior: float,
    normal_scale: float,
    double_sided: bool,
) -> None:
    mat.diffuse_color = base_color
    mat.use_nodes = True
    mat.use_backface_culling = not double_sided
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if not tree or not bsdf:
        return

    bsdf_inputs = bsdf.inputs
    color_socket = bsdf_inputs.get("Base Color")
    if color_socket:
        color_socket.default_value = base_color
    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Roughness", roughness)
    _set_first_input(bsdf, ("Specular IOR Level", "Specular"), specular)
    if has_emission:
        _set_input(bsdf, "Emission Color", (*emissive_color, 1.0))
        _set_first_input(bsdf, ("Emission Strength",), emissive_strength)
    if has_specular_tint:
        _set_first_input(bsdf, ("Specular Tint",), (*specular_color, 1.0))
    _set_first_input(bsdf, ("IOR",), ior)

    base_tex = _new_fast_image_texture_node(
        tree,
        base_path,
        base_tex_info,
        _texture_color_space(base_tex_info, "sRGB"),
    )
    if base_tex and color_socket:
        color_output = base_tex.outputs.get("Color")
        if color_output:
            tree.links.new(color_output, color_socket)

    normal_tex = _new_fast_image_texture_node(
        tree,
        normal_path,
        normal_tex_info,
        _texture_color_space(normal_tex_info, "Non-Color"),
    )
    normal_socket = bsdf_inputs.get("Normal")
    if normal_tex and normal_socket:
        normal_map = tree.nodes.new("ShaderNodeNormalMap")
        if abs(float(normal_scale) - 1.0) > 1e-6:
            scale = normal_map.inputs.get("Strength")
            if scale:
                scale.default_value = normal_scale
        color_output = normal_tex.outputs.get("Color")
        color_input = normal_map.inputs.get("Color")
        normal_output = normal_map.outputs.get("Normal")
        if color_output and color_input:
            tree.links.new(color_output, color_input)
        if normal_output:
            tree.links.new(normal_output, normal_socket)
    try:
        mat["assetkit_deferred_material_nodes"] = False
    except Exception:
        pass


def _configure_simple_material(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    base_color: tuple[float, float, float, float],
) -> None:
    mat.use_backface_culling = not _is_double_sided_material(data)
    _set_material_alpha_mode(mat, data)
    if _has_nondefault_assetkit_material_props(data):
        _set_assetkit_material_props(mat, data)
    _set_assetkit_json_prop(mat, "assetkit_material_extra_json", _material_extra_for_custom_prop(data))
    _set_assetkit_json_prop(mat, "assetkit_material_source_extra_json", data.source_extra)
    if not getattr(mat, "use_nodes", False):
        _set_material_scalar(mat, "metallic", data.metallic)
        _set_material_scalar(mat, "roughness", data.roughness)
        _set_material_scalar(mat, "specular_intensity", _pbr_specular_level(data))
        return
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return
    _set_input(bsdf, "Base Color", base_color)
    if abs(float(data.metallic)) > 1e-6:
        _set_input(bsdf, "Metallic", data.metallic)
    if abs(float(data.roughness) - 0.5) > 1e-6:
        _set_input(bsdf, "Roughness", data.roughness)
    specular_level = _pbr_specular_level(data)
    if abs(float(specular_level) - 0.5) > 1e-6:
        _set_first_input(bsdf, ("Specular IOR Level", "Specular"), specular_level)
    alpha_socket = bsdf.inputs.get("Alpha") if abs(float(data.opacity) - 1.0) > 1e-6 else None
    if alpha_socket is not None:
        try:
            alpha_socket.default_value = data.opacity
        except TypeError:
            pass


def _set_material_scalar(mat: bpy.types.Material, attr: str, value: float) -> None:
    if not hasattr(mat, attr):
        return
    try:
        setattr(mat, attr, float(value))
    except TypeError:
        pass


def _has_nondefault_assetkit_material_props(data: MeshPrimitiveData) -> bool:
    if any(getattr(data, name) for name in _MATERIAL_TEXTURE_FIELDS):
        return True
    if data.texture_infos:
        return True
    if _has_emission(data) or _has_specular(data) or _has_clearcoat(data):
        return True
    if _has_transmission(data) or _has_sheen(data) or _has_anisotropy(data) or _has_iridescence(data):
        return True
    if _has_diffuse_transmission(data) or _has_volume_scatter(data):
        return True
    return (
        float(data.volume_thickness) > 0.0
        or float(data.dispersion) != 0.0
        or int(data.transparent_opaque) != 0
        or abs(float(data.opacity) - 1.0) > 1.0e-6
        or not _tuple_close(data.transparent_color, (1.0, 1.0, 1.0, 1.0))
    )


def _apply_material_animation(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    bsdf,
    color_target,
    color_input: str,
    alpha_socket,
    settings_node=None,
) -> None:
    channels = data.material_anim_channels or []
    if not channels:
        return
    if mat.get("assetkit_material_animation_applied"):
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]] = {}
    written_fcurves: set[tuple[int, int, str, int]] = set()
    end_frame = scene.frame_end
    frame_bounds: tuple[float, float] | None = None
    converted_texture_location_roles, tex_end_frame = _apply_texture_transform_location_animations(
        mat,
        data,
        actions,
        written_fcurves,
        channels,
        fps,
    )
    end_frame = max(end_frame, tex_end_frame)

    for channel in channels:
        target = _channel_target(channel)
        tex_role = _texture_anim_role(target)
        bounds = _channel_frame_bounds(channel, fps)
        if bounds is not None:
            frame_bounds = _merge_frame_bounds(frame_bounds, bounds[0], bounds[1])
        if (
            tex_role in converted_texture_location_roles
            and _texture_anim_prop(target) == _ANIM_TEXTURE_TRANSFORM_OFFSET
        ):
            continue
        width = _material_anim_width(target)
        if width <= 0:
            continue

        count = _channel_count(channel)
        value_width = _channel_value_width(channel)
        target_offset = _channel_target_offset(channel)
        is_partial = _channel_is_partial(channel)
        times = _buffer_view(_channel_times(channel), "f")
        values = _buffer_view(_channel_values(channel), "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue
        if target_offset >= width:
            continue

        interpolation = _blender_interpolation(_channel_interpolation(channel))
        in_tangents, out_tangents = _channel_tangents(channel)
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            owner, path, fcurve_index, group_name = _material_anim_channel_target(
                mat,
                bsdf,
                color_target,
                color_input,
                alpha_socket,
                settings_node,
                target,
                target_index,
            )
            if not owner or not path:
                continue

            action = _animation_action_for(mat, owner, actions, "" if owner == mat else "_Nodes", channel)
            write_key = _fcurve_write_key(owner, channel, path, fcurve_index)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, owner, path, fcurve_index, group_name=group_name)
            coords = array("f", [0.0]) * (count * 2)
            for key_index in range(count):
                coords[key_index * 2] = times[key_index] * fps
                value = values[key_index * value_width + value_index]
                coords[key_index * 2 + 1] = _material_anim_output_value(data, target, value)

            _write_fcurve_points(
                fcurve,
                coords,
                interpolation,
                times=times,
                fps=fps,
                in_tangents=in_tangents,
                out_tangents=out_tangents,
                value_width=value_width,
                value_index=value_index,
                tangent_value=(
                    lambda value, target=target, data=data: _material_anim_output_tangent(
                        data,
                        target,
                        value,
                    )
                ),
            )

        end_frame = max(end_frame, int(times[count - 1] * fps + 0.5))

    _stash_animation_actions(actions)
    _register_actions_frame_range(actions, frame_bounds)
    if actions:
        mat["assetkit_material_animation_applied"] = True
    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _material_anim_width(target: int) -> int:
    tex_prop = _texture_anim_prop(target)
    if tex_prop in {_ANIM_TEXTURE_TRANSFORM_OFFSET, _ANIM_TEXTURE_TRANSFORM_SCALE}:
        return 2
    if tex_prop == _ANIM_TEXTURE_TRANSFORM_ROTATION:
        return 1

    if target in {
        _ANIM_MATERIAL_BASE_COLOR,
    }:
        return 4
    if target in {
        _ANIM_MATERIAL_EMISSIVE_COLOR,
        _ANIM_MATERIAL_SPECULAR_COLOR,
        _ANIM_MATERIAL_SHEEN_COLOR,
        _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR,
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR,
    }:
        return 3
    if target in {
        _ANIM_MATERIAL_METALLIC,
        _ANIM_MATERIAL_ROUGHNESS,
        _ANIM_MATERIAL_ALPHA_CUTOFF,
        _ANIM_MATERIAL_EMISSIVE_STRENGTH,
        _ANIM_MATERIAL_NORMAL_SCALE,
        _ANIM_MATERIAL_OCCLUSION_STRENGTH,
        _ANIM_MATERIAL_SPECULAR,
        _ANIM_MATERIAL_IOR,
        _ANIM_MATERIAL_CLEARCOAT,
        _ANIM_MATERIAL_CLEARCOAT_ROUGHNESS,
        _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE,
        _ANIM_MATERIAL_TRANSMISSION,
        _ANIM_MATERIAL_SHEEN_ROUGHNESS,
        _ANIM_MATERIAL_IRIDESCENCE,
        _ANIM_MATERIAL_IRIDESCENCE_IOR,
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM,
        _ANIM_MATERIAL_VOLUME_THICKNESS,
        _ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE,
        _ANIM_MATERIAL_ANISOTROPY,
        _ANIM_MATERIAL_ANISOTROPY_ROTATION,
        _ANIM_MATERIAL_DISPERSION,
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION,
    }:
        return 1
    return 0


def _apply_texture_transform_location_animations(
    mat: bpy.types.Material,
    data: MeshPrimitiveData,
    actions: dict[tuple[int, int, str], tuple[bpy.types.ID, bpy.types.Action]],
    written_fcurves: set[tuple[int, int, str, int]],
    channels: list[dict],
    fps: float,
) -> tuple[set[str], int]:
    by_role: dict[str, dict[int, list[dict]]] = {}
    for channel in channels:
        target = _channel_target(channel)
        role = _texture_anim_role(target)
        prop = _texture_anim_prop(target)
        if role and prop in {
            _ANIM_TEXTURE_TRANSFORM_OFFSET,
            _ANIM_TEXTURE_TRANSFORM_SCALE,
            _ANIM_TEXTURE_TRANSFORM_ROTATION,
        }:
            by_role.setdefault(role, {}).setdefault(prop, []).append(channel)

    converted_roles: set[str] = set()
    end_frame = bpy.context.scene.frame_end

    for role, prop_channels in by_role.items():
        tex_info = _texture_info(data, role)
        mapping = _texture_mapping_node(mat, role)
        if not tex_info or not mapping:
            continue
        socket = mapping.inputs.get("Location")
        if not socket:
            continue

        key_times = _texture_transform_key_times(prop_channels)
        if not key_times:
            continue

        path = socket.path_from_id("default_value")
        action = _animation_action_for(mat, mat.node_tree, actions, "_Nodes", _first_texture_transform_channel(prop_channels))
        interpolation = _texture_transform_location_interpolation(prop_channels)

        coords = [array("f", [0.0]) * (len(key_times) * 2) for _ in range(2)]
        for key_index, time_value in enumerate(key_times):
            offset = _texture_transform_sample_vec2(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_OFFSET, []),
                tex_info.transform_offset,
                time_value,
            )
            scale = _texture_transform_sample_vec2(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_SCALE, []),
                tex_info.transform_scale,
                time_value,
            )
            rotation = _texture_transform_sample_scalar(
                prop_channels.get(_ANIM_TEXTURE_TRANSFORM_ROTATION, []),
                float(tex_info.transform_rotation),
                time_value,
            )
            blender_offset, _, _ = _texture_transform_values_gltf_to_blender(offset, rotation, scale)
            frame = time_value * fps
            for component in range(2):
                coords[component][key_index * 2] = frame
                coords[component][key_index * 2 + 1] = blender_offset[component]

        first_channel = _first_texture_transform_channel(prop_channels)
        for component in range(2):
            write_key = _fcurve_write_key(mat.node_tree, first_channel, path, component)
            if write_key in written_fcurves:
                continue
            written_fcurves.add(write_key)
            fcurve = _ensure_fcurve(action, mat.node_tree, path, component, group_name="Texture Transform")
            _write_fcurve_points(fcurve, coords[component], interpolation)

        converted_roles.add(role)
        end_frame = max(end_frame, int(key_times[-1] * fps + 0.5))

    return converted_roles, end_frame


def _first_texture_transform_channel(prop_channels: dict[int, list[dict]]) -> dict:
    for prop in (
        _ANIM_TEXTURE_TRANSFORM_OFFSET,
        _ANIM_TEXTURE_TRANSFORM_SCALE,
        _ANIM_TEXTURE_TRANSFORM_ROTATION,
    ):
        channels = prop_channels.get(prop) or []
        if channels:
            return channels[0]
    return {}


def _texture_transform_key_times(prop_channels: dict[int, list[dict]]) -> list[float]:
    values: set[float] = set()
    for channels in prop_channels.values():
        for channel in channels:
            count = _channel_count(channel)
            times = _buffer_view(_channel_times(channel), "f")
            if count <= 0 or times is None:
                continue
            for index in range(min(count, len(times))):
                values.add(float(times[index]))
    return sorted(values)


def _texture_transform_location_interpolation(prop_channels: dict[int, list[dict]]) -> str:
    interpolation = "CONSTANT"
    for channels in prop_channels.values():
        for channel in channels:
            if _blender_interpolation(_channel_interpolation(channel)) != "CONSTANT":
                return "LINEAR"
    return interpolation


def _texture_transform_sample_vec2(
    channels: list[dict],
    fallback: tuple[float, float],
    time_value: float,
) -> tuple[float, float]:
    values = [float(fallback[0]), float(fallback[1])]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0], values[1]


def _texture_transform_sample_scalar(
    channels: list[dict],
    fallback: float,
    time_value: float,
) -> float:
    values = [float(fallback)]
    for channel in channels:
        _texture_transform_sample_into(values, channel, time_value)
    return values[0]


def _texture_transform_sample_into(values: list[float], channel: dict, time_value: float) -> None:
    count = _channel_count(channel)
    value_width = _channel_value_width(channel)
    target_offset = _channel_target_offset(channel)
    is_partial = _channel_is_partial(channel)
    times = _buffer_view(_channel_times(channel), "f")
    raw_values = _buffer_view(_channel_values(channel), "f")
    if count <= 0 or value_width <= 0 or times is None or raw_values is None:
        return

    width = len(values)
    if target_offset >= width:
        return
    component_count = 1 if is_partial else min(width - target_offset, value_width)
    interpolation = _blender_interpolation(_channel_interpolation(channel))
    for component in range(component_count):
        target_index = target_offset + component
        value_index = 0 if is_partial else component
        values[target_index] = _sample_anim_scalar(times, raw_values, count, value_width, value_index, time_value, interpolation)


def _sample_anim_scalar(
    times: memoryview,
    values: memoryview,
    count: int,
    value_width: int,
    value_index: int,
    time_value: float,
    interpolation: str,
) -> float:
    if count <= 1 or time_value <= float(times[0]):
        return float(values[value_index])

    last = min(count, len(times)) - 1
    if time_value >= float(times[last]):
        return float(values[last * value_width + value_index])

    prev = 0
    for index in range(1, last + 1):
        if time_value <= float(times[index]):
            prev = index - 1
            next_index = index
            break
    else:
        return float(values[last * value_width + value_index])

    prev_value = float(values[prev * value_width + value_index])
    if interpolation == "CONSTANT":
        return prev_value

    next_time = float(times[next_index])
    prev_time = float(times[prev])
    if next_time <= prev_time:
        return prev_value
    next_value = float(values[next_index * value_width + value_index])
    factor = (time_value - prev_time) / (next_time - prev_time)
    return prev_value + (next_value - prev_value) * factor


def _material_anim_channel_target(
    mat: bpy.types.Material,
    bsdf,
    color_target,
    color_input: str,
    alpha_socket,
    settings_node,
    target: int,
    target_index: int,
) -> tuple[bpy.types.ID | None, str, int | None, str]:
    tex_role = _texture_anim_role(target)
    tex_prop = _texture_anim_prop(target)
    if tex_role:
        mapping = _texture_mapping_node(mat, tex_role)
        if mapping:
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_OFFSET:
                socket = mapping.inputs.get("Location")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), target_index, "Texture Transform"
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_SCALE:
                socket = mapping.inputs.get("Scale")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), target_index, "Texture Transform"
            if tex_prop == _ANIM_TEXTURE_TRANSFORM_ROTATION:
                socket = mapping.inputs.get("Rotation")
                if socket:
                    return mat.node_tree, socket.path_from_id("default_value"), 2, "Texture Transform"

    if target == _ANIM_MATERIAL_BASE_COLOR:
        socket = alpha_socket if target_index == 3 and alpha_socket else _first_input(color_target, (color_input,))
        if not socket:
            return None, "", None, ""
        index = None if socket == alpha_socket else target_index
        return mat.node_tree, socket.path_from_id("default_value"), index, "Material"

    if target == _ANIM_MATERIAL_NORMAL_SCALE:
        node = _normal_map_node(mat, "normal")
        socket = _first_input(node, ("Strength",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Normal"

    if target == _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE:
        node = _normal_map_node(mat, "clearcoat_normal")
        socket = _first_input(node, ("Strength",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Normal"

    socket_target = {
        _ANIM_MATERIAL_METALLIC: ("Metallic",),
        _ANIM_MATERIAL_ROUGHNESS: ("Roughness",),
        _ANIM_MATERIAL_EMISSIVE_STRENGTH: ("Emission Strength",),
        _ANIM_MATERIAL_SPECULAR: ("Specular IOR Level", "Specular"),
        _ANIM_MATERIAL_IOR: ("IOR",),
        _ANIM_MATERIAL_CLEARCOAT: ("Coat Weight", "Clearcoat"),
        _ANIM_MATERIAL_CLEARCOAT_ROUGHNESS: ("Coat Roughness", "Clearcoat Roughness"),
        _ANIM_MATERIAL_TRANSMISSION: ("Transmission Weight", "Transmission"),
        _ANIM_MATERIAL_SHEEN_ROUGHNESS: ("Sheen Roughness",),
        _ANIM_MATERIAL_ANISOTROPY: ("Anisotropic",),
        _ANIM_MATERIAL_ANISOTROPY_ROTATION: ("Anisotropic Rotation",),
        _ANIM_MATERIAL_IRIDESCENCE: ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        _ANIM_MATERIAL_IRIDESCENCE_IOR: ("Thin Film IOR",),
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM: ("Thin Film Thickness",),
        _ANIM_MATERIAL_VOLUME_THICKNESS: ("Volume Thickness",),
        _ANIM_MATERIAL_DISPERSION: ("Dispersion",),
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION: ("Diffuse Transmission Weight", "Diffuse Transmission"),
    }.get(target)
    if socket_target:
        socket = _first_input(bsdf, socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Material"

    color_socket_target = {
        _ANIM_MATERIAL_EMISSIVE_COLOR: ("Emission Color",),
        _ANIM_MATERIAL_SPECULAR_COLOR: ("Specular Tint",),
        _ANIM_MATERIAL_SHEEN_COLOR: ("Sheen Tint",),
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR: ("Diffuse Transmission Color",),
    }.get(target)
    if color_socket_target:
        socket = _first_input(bsdf, color_socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Material"

    if target == _ANIM_MATERIAL_ALPHA_CUTOFF:
        return mat, "alpha_threshold", None, "Material"

    if target == _ANIM_MATERIAL_DIFFUSE_TRANSMISSION:
        node = _assetkit_node(mat, "assetkit_diffuse_transmission_node", "mix")
        socket = _first_input(node, ("Fac",))
        if socket and not socket.is_linked:
            return mat.node_tree, socket.path_from_id("default_value"), None, "Diffuse Transmission"

    if target == _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR:
        node = _assetkit_node(mat, "assetkit_diffuse_transmission_node", "translucent")
        socket = _first_input(node, ("Color",))
        if socket and not socket.is_linked:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Diffuse Transmission"

    if target == _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR:
        node = _assetkit_node(mat, "assetkit_volume_node", "absorption")
        socket = _first_input(node, ("Color",))
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), target_index, "Volume"

    settings_socket_target = {
        _ANIM_MATERIAL_OCCLUSION_STRENGTH: ("Occlusion",),
        _ANIM_MATERIAL_IRIDESCENCE: ("Iridescence Factor",),
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM: ("Iridescence Thickness Minimum",),
        _ANIM_MATERIAL_VOLUME_THICKNESS: ("Thickness",),
        _ANIM_MATERIAL_DISPERSION: ("Dispersion",),
    }.get(target)
    if settings_socket_target:
        socket = _first_input(settings_node, settings_socket_target)
        if socket:
            return mat.node_tree, socket.path_from_id("default_value"), None, "glTF Material Output"

    prop = _material_anim_custom_prop(target)
    if prop:
        if prop not in mat:
            mat[prop] = (0.0, 0.0, 0.0) if _material_anim_width(target) > 1 else 0.0
        return mat, f'["{prop}"]', None if _material_anim_width(target) == 1 else target_index, "AssetKit"

    return None, "", None, ""


def _material_anim_output_value(data: MeshPrimitiveData, target: int, value: float) -> float:
    if target == _ANIM_MATERIAL_SPECULAR and _uses_pbr_specular_level(data):
        return float(value) * 0.5
    if target == _ANIM_MATERIAL_ANISOTROPY_ROTATION:
        return _blender_anisotropy_rotation(value)
    return float(value)


def _material_anim_output_tangent(data: MeshPrimitiveData, target: int, value: float) -> float:
    if target == _ANIM_MATERIAL_SPECULAR and _uses_pbr_specular_level(data):
        return float(value) * 0.5
    if target == _ANIM_MATERIAL_ANISOTROPY_ROTATION:
        return float(value) / (2.0 * math.pi)
    return float(value)


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


def _texture_anim_role(target: int) -> str:
    if target < _ANIM_TEXTURE_TRANSFORM_BASE:
        return ""
    offset = target - _ANIM_TEXTURE_TRANSFORM_BASE
    role_index = offset // _ANIM_TEXTURE_TRANSFORM_STRIDE
    if role_index < 0 or role_index >= len(_ANIM_TEXTURE_TRANSFORM_ROLES):
        return ""
    return _ANIM_TEXTURE_TRANSFORM_ROLES[role_index]


def _texture_anim_prop(target: int) -> int:
    if target < _ANIM_TEXTURE_TRANSFORM_BASE:
        return -1
    return (target - _ANIM_TEXTURE_TRANSFORM_BASE) % _ANIM_TEXTURE_TRANSFORM_STRIDE


def _texture_mapping_node(mat: bpy.types.Material, role: str):
    node_tree = mat.node_tree
    if not node_tree or not role:
        return None
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeMapping" and node.get("assetkit_texture_role") == role:
            return node
    return None


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


def _material_anim_custom_prop(target: int) -> str:
    return {
        _ANIM_MATERIAL_NORMAL_SCALE: "assetkit_normal_scale",
        _ANIM_MATERIAL_OCCLUSION_STRENGTH: "assetkit_occlusion_strength",
        _ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE: "assetkit_clearcoat_normal_scale",
        _ANIM_MATERIAL_IRIDESCENCE: "assetkit_iridescence",
        _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM: "assetkit_iridescence_thickness_minimum",
        _ANIM_MATERIAL_VOLUME_THICKNESS: "assetkit_volume_thickness",
        _ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE: "assetkit_volume_attenuation_distance",
        _ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR: "assetkit_volume_attenuation_color",
        _ANIM_MATERIAL_DISPERSION: "assetkit_dispersion",
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION: "assetkit_diffuse_transmission",
        _ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR: "assetkit_diffuse_transmission_color",
    }.get(target, "")


def _has_material_data(data: MeshPrimitiveData) -> bool:
    if (
        not data.material_name
        and not data.material_key
        and not data.material_type
        and not data.alpha_mode
        and not data.transparent_opaque
        and not data.texture_infos
        and not data.color_sets
        and not data.base_color_texture
        and not data.metallic_roughness_texture
        and not data.occlusion_texture
        and not data.normal_texture
        and not data.emissive_texture
        and not data.transparent_texture
        and not data.specular_texture
        and not data.specular_color_texture
        and not data.clearcoat_texture
        and not data.clearcoat_roughness_texture
        and not data.clearcoat_normal_texture
        and not data.transmission_texture
        and not data.sheen_color_texture
        and not data.sheen_roughness_texture
        and not data.iridescence_texture
        and not data.iridescence_thickness_texture
        and not data.volume_thickness_texture
        and not data.anisotropy_texture
        and not data.diffuse_transmission_texture
        and not data.diffuse_transmission_color_texture
    ):
        return False
    if data.material_name:
        return True
    if _color_attribute_name(data):
        return True
    return _material_cache_key(data) != _default_material_cache_key()


def _material_base_color(data: MeshPrimitiveData) -> tuple[float, float, float, float]:
    if _uses_transparent_as_surface_color(data):
        return (
            float(data.transparent_color[0]),
            float(data.transparent_color[1]),
            float(data.transparent_color[2]),
            float(data.base_color[3]),
        )
    return data.base_color


def _uses_transparent_as_surface_color(data: MeshPrimitiveData) -> bool:
    if data.base_color_texture or data.transparent_texture:
        return False
    if not _is_default_rgb(data.base_color):
        return False
    if _is_default_rgb(data.transparent_color):
        return False
    return True


def _is_default_rgb(values: tuple[float, ...]) -> bool:
    return len(values) >= 3 and all(abs(float(value) - 1.0) <= 1e-6 for value in values[:3])


def _is_unlit_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) == _AK_MATERIAL_TYPE_CONSTANT


def _is_classic_lit_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) in {
        _AK_MATERIAL_TYPE_PHONG,
        _AK_MATERIAL_TYPE_BLINN,
        _AK_MATERIAL_TYPE_LAMBERT,
    }


def _is_specular_glossiness_material(data: MeshPrimitiveData) -> bool:
    return int(data.material_type) == _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS


def _classic_roughness(shininess: float) -> float:
    value = max(float(shininess), 0.0)
    if value <= 0.0:
        return 1.0
    return max(0.0, min(1.0, math.sqrt(2.0 / (value + 2.0))))


def _classic_specular(data: MeshPrimitiveData) -> float:
    if int(data.material_type) == _AK_MATERIAL_TYPE_LAMBERT:
        return 0.0
    return max(0.0, min(1.0, max(float(v) for v in data.specular_color)))


def _uses_pbr_specular_level(data: MeshPrimitiveData) -> bool:
    return not _is_classic_lit_material(data) and not _is_specular_glossiness_material(data)


def _pbr_specular_level(data: MeshPrimitiveData) -> float:
    return 0.5 * max(0.0, float(data.specular_strength))


def _blender_anisotropy_rotation(rotation: float) -> float:
    return float(rotation) / (2.0 * math.pi)


def _material_ior(data: MeshPrimitiveData) -> float:
    if _is_specular_glossiness_material(data):
        return 1000.0
    return data.ior


def _is_double_sided_material(data: MeshPrimitiveData) -> bool:
    return bool(data.double_sided)


def _set_transparency_overlap(mat: bpy.types.Material, enabled: bool) -> None:
    if hasattr(mat, "use_transparency_overlap"):
        mat.use_transparency_overlap = enabled
    elif hasattr(mat, "show_transparent_back"):
        mat.show_transparent_back = enabled


def _set_material_alpha_mode(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    alpha_mode = int(data.alpha_mode)
    if alpha_mode == 0:
        if getattr(mat, "blend_method", "OPAQUE") != "OPAQUE":
            mat.blend_method = "OPAQUE"
    elif alpha_mode == 1:
        if _prefers_hashed_transparency(data):
            _set_material_enum(mat, "blend_method", "HASHED", "BLEND")
            _set_material_enum(mat, "surface_render_method", "DITHERED")
        else:
            mat.blend_method = "BLEND"
            _set_material_enum(mat, "surface_render_method", "BLENDED")
        _set_transparency_overlap(mat, False)
    elif alpha_mode == 2:
        mat.blend_method = "CLIP"
        _set_material_enum(mat, "surface_render_method", "DITHERED")
        mat.alpha_threshold = data.alpha_cutoff
        _set_transparency_overlap(mat, False)


def _prefers_hashed_transparency(data: MeshPrimitiveData) -> bool:
    if not data.transparent_texture and not _uses_transparent_as_surface_color(data):
        return False
    return int(data.transparent_opaque) in {
        _AK_OPAQUE_A_ZERO,
        _AK_OPAQUE_RGB_ZERO,
    }


def _set_material_enum(mat: bpy.types.Material, attr: str, *values: str) -> bool:
    if not hasattr(mat, attr):
        return False
    prop = mat.bl_rna.properties.get(attr)
    enum_values = {item.identifier for item in prop.enum_items} if prop else set()
    for value in values:
        if not enum_values or value in enum_values:
            try:
                setattr(mat, attr, value)
                return True
            except TypeError:
                continue
    return False


def _has_emission(data: MeshPrimitiveData) -> bool:
    if data.emissive_texture:
        return True
    return any(abs(float(value)) > 1e-6 for value in data.emissive_color)


def _has_specular(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.specular_texture)
        or bool(data.specular_color_texture)
        or abs(float(data.specular_strength) - 1.0) > 1e-6
        or not _is_default_rgb(data.specular_color)
    )


def _has_clearcoat(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.clearcoat_texture)
        or bool(data.clearcoat_roughness_texture)
        or bool(data.clearcoat_normal_texture)
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
    )


def _has_transmission(data: MeshPrimitiveData) -> bool:
    return bool(data.transmission_texture) or abs(float(data.transmission)) > 1e-6


def _has_sheen(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.has_sheen)
        or bool(data.sheen_color_texture)
        or bool(data.sheen_roughness_texture)
        or any(abs(float(value)) > 1e-6 for value in data.sheen_color)
        or abs(float(data.sheen_roughness)) > 1e-6
    )


def _has_anisotropy(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.anisotropy_texture)
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
    )


def _has_iridescence(data: MeshPrimitiveData) -> bool:
    return (
        bool(data.iridescence_texture)
        or bool(data.iridescence_thickness_texture)
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.iridescence_ior) - 1.3) > 1e-6
        or abs(float(data.iridescence_thickness_minimum) - 100.0) > 1e-6
        or abs(float(data.iridescence_thickness_maximum) - 400.0) > 1e-6
    )


def _emission_strength(data: MeshPrimitiveData) -> float:
    return float(data.emissive_strength) if _has_emission(data) else 0.0


def _material_cache_key(data: MeshPrimitiveData) -> object:
    color_attr = _color_attribute_name(data)
    native_key = int(getattr(data, "material_key", 0) or 0)
    if native_key and _preserve_native_material_identity(data):
        return ("native", int(data.file_type), native_key, color_attr)
    visual_key = _fast_visual_material_cache_key(data, color_attr)
    if visual_key is not None:
        return visual_key
    return (
        "props",
        data.material_name,
        color_attr,
        _round_tuple(data.base_color),
        _round_tuple(data.emissive_color),
        _round_tuple(data.specular_color),
        _round_tuple(data.sheen_color),
        _round_tuple(data.transparent_color),
        _round_tuple(data.volume_attenuation_color),
        _round_tuple(data.diffuse_transmission_color),
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        round(float(data.opacity), 6),
        round(float(data.alpha_cutoff), 6),
        round(float(data.transparent_amount), 6),
        round(float(data.normal_scale), 6),
        round(float(data.occlusion_strength), 6),
        round(float(data.emissive_strength), 6),
        round(float(data.specular_strength), 6),
        round(float(data.ior), 6),
        round(float(data.clearcoat), 6),
        round(float(data.clearcoat_roughness), 6),
        round(float(data.clearcoat_normal_scale), 6),
        round(float(data.transmission), 6),
        round(float(data.sheen_roughness), 6),
        round(float(data.iridescence), 6),
        round(float(data.iridescence_ior), 6),
        round(float(data.iridescence_thickness_minimum), 6),
        round(float(data.iridescence_thickness_maximum), 6),
        round(float(data.volume_thickness), 6),
        round(float(data.volume_attenuation_distance), 6),
        round(float(data.anisotropy), 6),
        round(float(data.anisotropy_rotation), 6),
        round(float(data.diffuse_transmission), 6),
        round(float(data.dispersion), 6),
        int(data.alpha_mode),
        int(data.transparent_opaque),
        _is_double_sided_material(data),
        bool(data.has_sheen),
        int(data.material_type),
        int(data.file_type),
        data.base_color_texture,
        data.metallic_roughness_texture,
        data.occlusion_texture,
        data.normal_texture,
        data.emissive_texture,
        data.transparent_texture,
        data.specular_texture,
        data.specular_color_texture,
        data.clearcoat_texture,
        data.clearcoat_roughness_texture,
        data.clearcoat_normal_texture,
        data.transmission_texture,
        data.sheen_color_texture,
        data.sheen_roughness_texture,
        data.iridescence_texture,
        data.iridescence_thickness_texture,
        data.volume_thickness_texture,
        data.anisotropy_texture,
        data.diffuse_transmission_texture,
        data.diffuse_transmission_color_texture,
        _texture_infos_cache_key(data.texture_infos),
        _json_cache_key(data.material_extra),
        _json_cache_key(data.source_extra),
    )


def _preserve_native_material_identity(data: MeshPrimitiveData) -> bool:
    return bool(
        data.material_name
        or data.material_extra
        or data.source_extra
        or data.material_anim_channels
        or data.material_variants
    )


def _fast_visual_material_cache_key(data: MeshPrimitiveData, color_attr: str) -> object | None:
    key = _fast_simple_native_base_color_texture_key(data)
    if key is not None and not color_attr:
        return key
    key = _fast_base_color_texture_visual_key(data, color_attr)
    if key is not None:
        return key
    return None


def _fast_simple_native_base_color_texture_key(data: MeshPrimitiveData) -> object | None:
    if not getattr(data, "simple_native", False) or not data.base_color_texture:
        return None
    return (
        "visual-base-color-texture",
        int(data.file_type),
        int(data.material_type),
        data.base_color_texture,
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        bool(data.double_sided),
    )


def _fast_base_color_texture_visual_key(data: MeshPrimitiveData, color_attr: str) -> object | None:
    if color_attr or not data.base_color_texture:
        return None
    if _preserve_native_material_identity(data):
        return None
    if data.texture_infos or data.color_sets or data.colors_f32 or data.point_attrs:
        return None

    material_type = int(data.material_type)
    if material_type in {
        _AK_MATERIAL_TYPE_PHONG,
        _AK_MATERIAL_TYPE_BLINN,
        _AK_MATERIAL_TYPE_LAMBERT,
        _AK_MATERIAL_TYPE_CONSTANT,
        _AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS,
    }:
        return None
    if (
        data.metallic_roughness_texture
        or data.occlusion_texture
        or data.normal_texture
        or data.emissive_texture
        or data.transparent_texture
        or data.specular_texture
        or data.specular_color_texture
        or data.clearcoat_texture
        or data.clearcoat_roughness_texture
        or data.clearcoat_normal_texture
        or data.transmission_texture
        or data.sheen_color_texture
        or data.sheen_roughness_texture
        or data.iridescence_texture
        or data.iridescence_thickness_texture
        or data.volume_thickness_texture
        or data.anisotropy_texture
        or data.diffuse_transmission_texture
        or data.diffuse_transmission_color_texture
    ):
        return None
    if (
        data.alpha_mode
        or data.transparent_opaque
        or abs(float(data.opacity) - 1.0) > 1e-6
        or abs(float(data.transparent_amount) - 1.0) > 1e-6
        or abs(float(data.normal_scale) - 1.0) > 1e-6
        or abs(float(data.occlusion_strength) - 1.0) > 1e-6
        or abs(float(data.emissive_strength) - 1.0) > 1e-6
        or abs(float(data.specular_strength) - 1.0) > 1e-6
        or abs(float(data.ior) - 1.5) > 1e-6
        or abs(float(data.clearcoat)) > 1e-6
        or abs(float(data.clearcoat_roughness)) > 1e-6
        or abs(float(data.clearcoat_normal_scale) - 1.0) > 1e-6
        or abs(float(data.transmission)) > 1e-6
        or abs(float(data.sheen_roughness)) > 1e-6
        or abs(float(data.iridescence)) > 1e-6
        or abs(float(data.iridescence_ior) - 1.3) > 1e-6
        or abs(float(data.iridescence_thickness_minimum) - 100.0) > 1e-6
        or abs(float(data.iridescence_thickness_maximum) - 400.0) > 1e-6
        or abs(float(data.volume_thickness)) > 1e-6
        or abs(float(data.anisotropy)) > 1e-6
        or abs(float(data.anisotropy_rotation)) > 1e-6
        or abs(float(data.diffuse_transmission)) > 1e-6
        or abs(float(data.dispersion)) > 1e-6
        or data.has_sheen
    ):
        return None
    if (
        not _tuple_close(data.base_color, (1.0, 1.0, 1.0, 1.0))
        or not _tuple_close(data.emissive_color, (0.0, 0.0, 0.0))
        or not _tuple_close(data.specular_color, (1.0, 1.0, 1.0))
        or not _tuple_close(data.sheen_color, (0.0, 0.0, 0.0))
        or not _tuple_close(data.transparent_color, (1.0, 1.0, 1.0, 1.0))
        or not _tuple_close(data.volume_attenuation_color, (1.0, 1.0, 1.0))
        or not _tuple_close(data.diffuse_transmission_color, (1.0, 1.0, 1.0))
    ):
        return None

    return (
        "visual-base-color-texture",
        int(data.file_type),
        int(data.material_type),
        data.base_color_texture,
        round(float(data.metallic), 6),
        round(float(data.roughness), 6),
        bool(data.double_sided),
    )


def _default_material_cache_key() -> object:
    return (
        "props",
        "",
        "",
        (1.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0),
        (1.0, 1.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        (1.0, 1.0, 1.0),
        1.0,
        1.0,
        1.0,
        0.5,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.5,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.3,
        100.0,
        400.0,
        0.0,
        math.inf,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        False,
        False,
        0,
        0,
        *(("",) * 20),
        (),
        "",
        "",
    )


def _round_tuple(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(float(value), 6) for value in values)


def _texture_infos_cache_key(texture_infos: dict[str, TextureRefData] | None) -> tuple:
    if not texture_infos:
        return ()

    items = []
    for role, info in sorted(texture_infos.items()):
        items.append(
            (
                role,
                info.path,
                info.image_name,
                info.sampler_name,
                info.color_space,
                info.channels,
                info.texcoord,
                info.coord_input_name,
                int(info.slot),
                int(info.wrap_s),
                int(info.wrap_t),
                int(info.wrap_p),
                int(info.min_filter),
                int(info.mag_filter),
                int(info.mip_filter),
                bool(info.has_transform),
                _round_tuple(info.transform_offset),
                _round_tuple(info.transform_scale),
                round(float(info.transform_rotation), 6),
                int(info.transform_slot),
                _json_cache_key(info.texture_extra),
                _json_cache_key(info.texref_extra),
                _json_cache_key(info.image_extra),
                _json_cache_key(info.sampler_extra),
            )
        )
    return tuple(items)


def _json_cache_key(value: object | None) -> str:
    if not value:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)


def _color_attribute_name(data: MeshPrimitiveData) -> str:
    if data.color_sets:
        return data.color_sets[0].name or "Color"
    for attr in data.point_attrs or ():
        name = attr.name or ""
        if _is_color_attribute_name(name):
            return name
    if data.colors_f32:
        return "Color"
    return ""


def _configure_unlit_shader(
    mat: bpy.types.Material,
    alpha_mode: int,
):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")

    surface = output.inputs.get("Surface")
    if surface:
        for link in list(surface.links):
            links.remove(link)

    emission = nodes.new("ShaderNodeEmission")
    if not surface:
        return emission, None

    if alpha_mode:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(transparent.outputs.get("BSDF"), mix.inputs[1])
        links.new(emission.outputs.get("Emission"), mix.inputs[2])
        links.new(mix.outputs.get("Shader"), surface)
        return emission, mix.inputs.get("Fac")

    links.new(emission.outputs.get("Emission"), surface)
    return emission, None


def _set_assetkit_material_props(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    props = {
        "assetkit_iridescence": data.iridescence,
        "assetkit_iridescence_ior": data.iridescence_ior,
        "assetkit_iridescence_thickness_minimum": data.iridescence_thickness_minimum,
        "assetkit_iridescence_thickness_maximum": data.iridescence_thickness_maximum,
        "assetkit_volume_thickness": data.volume_thickness,
        "assetkit_volume_attenuation_color": data.volume_attenuation_color,
        "assetkit_volume_attenuation_distance": data.volume_attenuation_distance,
        "assetkit_anisotropy": data.anisotropy,
        "assetkit_anisotropy_rotation": data.anisotropy_rotation,
        "assetkit_diffuse_transmission": data.diffuse_transmission,
        "assetkit_diffuse_transmission_color": data.diffuse_transmission_color,
        "assetkit_dispersion": data.dispersion,
        "assetkit_transparent_color": data.transparent_color,
        "assetkit_transparent_amount": data.transparent_amount,
        "assetkit_opacity": data.opacity,
        "assetkit_transparent_opaque": data.transparent_opaque,
        "assetkit_normal_scale": data.normal_scale,
        "assetkit_occlusion_strength": data.occlusion_strength,
        "assetkit_emissive_strength": data.emissive_strength,
        "assetkit_clearcoat_normal_scale": data.clearcoat_normal_scale,
        "assetkit_material_type": data.material_type,
        "assetkit_file_type": data.file_type,
        "assetkit_iridescence_texture": data.iridescence_texture,
        "assetkit_iridescence_thickness_texture": data.iridescence_thickness_texture,
        "assetkit_volume_thickness_texture": data.volume_thickness_texture,
        "assetkit_anisotropy_texture": data.anisotropy_texture,
        "assetkit_diffuse_transmission_texture": data.diffuse_transmission_texture,
        "assetkit_diffuse_transmission_color_texture": data.diffuse_transmission_color_texture,
        "assetkit_transparent_texture": data.transparent_texture,
    }
    scatter_color = _volume_scatter_color(data)
    if scatter_color:
        props["assetkit_volume_scatter_multiscatter_color"] = scatter_color
    for key, value in props.items():
        if _is_default_material_prop(key, value):
            continue
        mat[key] = value

    for role, info in (data.texture_infos or {}).items():
        prefix = f"assetkit_texture_{role}"
        _set_prop_if_nondefault(mat, f"{prefix}_slot", int(info.slot), 0)
        if info.image_name:
            mat[f"{prefix}_image_name"] = info.image_name
        if info.sampler_name:
            mat[f"{prefix}_sampler_name"] = info.sampler_name
        if info.color_space:
            mat[f"{prefix}_color_space"] = info.color_space
        if info.channels:
            mat[f"{prefix}_channels"] = info.channels
        if info.texcoord:
            mat[f"{prefix}_texcoord"] = info.texcoord
        if info.coord_input_name:
            mat[f"{prefix}_coord_input_name"] = info.coord_input_name
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_s", int(info.wrap_s), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_t", int(info.wrap_t), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_wrap_p", int(info.wrap_p), _TEXTURE_WRAP_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_min_filter", int(info.min_filter), _TEXTURE_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_mag_filter", int(info.mag_filter), _TEXTURE_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_mip_filter", int(info.mip_filter), _TEXTURE_FILTER_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_extension", _texture_extension(info), _TEXTURE_EXTENSION_DEFAULT)
        _set_prop_if_nondefault(mat, f"{prefix}_interpolation", _texture_interpolation(info), _TEXTURE_INTERPOLATION_DEFAULT)
        _set_assetkit_json_prop(mat, f"{prefix}_texture_extra_json", info.texture_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_texref_extra_json", info.texref_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_image_extra_json", info.image_extra)
        _set_assetkit_json_prop(mat, f"{prefix}_sampler_extra_json", info.sampler_extra)
        if info.has_transform:
            mat[f"{prefix}_transform_offset"] = info.transform_offset
            mat[f"{prefix}_transform_scale"] = info.transform_scale
            mat[f"{prefix}_transform_rotation"] = info.transform_rotation


def _set_prop_if_nondefault(target, key: str, value, default) -> None:
    if value == default:
        return
    target[key] = value


_MATERIAL_PROP_DEFAULTS = {
    "assetkit_iridescence": 0.0,
    "assetkit_iridescence_ior": 1.3,
    "assetkit_iridescence_thickness_minimum": 100.0,
    "assetkit_iridescence_thickness_maximum": 400.0,
    "assetkit_volume_thickness": 0.0,
    "assetkit_volume_attenuation_color": (1.0, 1.0, 1.0),
    "assetkit_volume_attenuation_distance": math.inf,
    "assetkit_anisotropy": 0.0,
    "assetkit_anisotropy_rotation": 0.0,
    "assetkit_diffuse_transmission": 0.0,
    "assetkit_diffuse_transmission_color": (1.0, 1.0, 1.0),
    "assetkit_dispersion": 0.0,
    "assetkit_transparent_color": (1.0, 1.0, 1.0, 1.0),
    "assetkit_transparent_amount": 1.0,
    "assetkit_opacity": 1.0,
    "assetkit_transparent_opaque": 0,
    "assetkit_normal_scale": 1.0,
    "assetkit_occlusion_strength": 1.0,
    "assetkit_emissive_strength": 1.0,
    "assetkit_clearcoat_normal_scale": 1.0,
}


def _is_default_material_prop(key: str, value) -> bool:
    if value == "":
        return True
    if key in {"assetkit_material_type", "assetkit_file_type"}:
        return False
    default = _MATERIAL_PROP_DEFAULTS.get(key)
    if default is None:
        return value == 0.0
    if isinstance(default, tuple):
        return _tuple_close(value, default)
    try:
        if float(value) == float(default):
            return True
        return abs(float(value) - float(default)) <= 1.0e-6
    except (TypeError, ValueError):
        return value == default


def _tuple_close(value, default: tuple[float, ...]) -> bool:
    try:
        values = tuple(value)
    except TypeError:
        return False
    if len(values) != len(default):
        return False
    return all(abs(float(item) - float(expected)) <= 1.0e-6 for item, expected in zip(values, default))


def _ensure_gltf_settings_node(mat: bpy.types.Material, data: MeshPrimitiveData, bsdf=None):
    if not _needs_gltf_settings_node(data, bsdf):
        return None

    group = _ensure_gltf_settings_group()
    if not group:
        return None

    node = mat.node_tree.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    node.label = _GLTF_SETTINGS_GROUP_NAME
    node.location = (-220, -520)

    if not data.occlusion_texture:
        _set_input_if_nondefault(node, "Occlusion", data.occlusion_strength, 1.0)
    if not data.volume_thickness_texture:
        _set_input_if_nondefault(node, "Thickness", data.volume_thickness, 0.0)
    _set_input_if_nondefault(node, "Dispersion", data.dispersion, 0.0)
    if not data.iridescence_texture:
        _set_input_if_nondefault(node, "Iridescence Factor", data.iridescence, 0.0)
    if not data.iridescence_thickness_texture:
        _set_input_if_nondefault(
            node,
            "Iridescence Thickness Minimum",
            data.iridescence_thickness_minimum,
            100.0,
        )
    return node


def _needs_gltf_settings_node(data: MeshPrimitiveData, bsdf=None) -> bool:
    if data.occlusion_texture:
        return True

    if float(data.dispersion) != 0.0:
        return not _has_input(bsdf, ("Dispersion",))

    if float(data.volume_thickness) > 0.0 or data.volume_thickness_texture:
        if not _has_input(bsdf, ("Volume Thickness", "Thickness")):
            return True

    if (
        float(data.iridescence) != 0.0
        or data.iridescence_texture
        or float(data.iridescence_thickness_minimum) != 100.0
    ):
        if data.iridescence_texture and not _has_input(
            bsdf,
            ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        ):
            return True
        if data.iridescence_thickness_texture and not _has_input(bsdf, ("Thin Film Thickness",)):
            return True

    return _has_material_settings_animation_needing_node(data, bsdf)


def _has_material_settings_animation_needing_node(data: MeshPrimitiveData, bsdf=None) -> bool:
    for channel in data.material_anim_channels or ():
        target = _channel_target(channel)
        if target == _ANIM_MATERIAL_OCCLUSION_STRENGTH:
            return True
        if target == _ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM:
            continue
        if target == _ANIM_MATERIAL_IRIDESCENCE and not _has_input(
            bsdf,
            ("Thin Film Weight", "Iridescence Weight", "Iridescence"),
        ):
            return True
        if target == _ANIM_MATERIAL_VOLUME_THICKNESS and not _has_input(bsdf, ("Volume Thickness", "Thickness")):
            return True
        if target == _ANIM_MATERIAL_DISPERSION and not _has_input(bsdf, ("Dispersion",)):
            return True
    return False


def _ensure_gltf_settings_group():
    global _GLTF_SETTINGS_GROUP_CACHE

    group = _GLTF_SETTINGS_GROUP_CACHE
    if group is not None:
        try:
            if bpy.data.node_groups.get(group.name) == group:
                return group
        except ReferenceError:
            pass

    group = bpy.data.node_groups.get(_GLTF_SETTINGS_GROUP_NAME)
    if group is None:
        group = bpy.data.node_groups.new(_GLTF_SETTINGS_GROUP_NAME, "ShaderNodeTree")
        group.nodes.new("NodeGroupInput").location = (-200, 0)
        group.nodes.new("NodeGroupOutput")

    if not group.get("assetkit_sockets_ready"):
        for name, default in _GLTF_SETTINGS_SOCKETS:
            _ensure_gltf_settings_socket(group, name, default)
        group["assetkit_sockets_ready"] = True
    _GLTF_SETTINGS_GROUP_CACHE = group
    return group


def _ensure_gltf_settings_socket(group, name: str, default: float) -> None:
    if _has_gltf_settings_socket(group, name):
        return

    socket = None
    interface = getattr(group, "interface", None)
    if interface is not None:
        try:
            socket = interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
        except TypeError:
            socket = interface.new_socket(name, socket_type="NodeSocketFloat")
        except Exception:
            socket = None

    if socket is None:
        try:
            socket = group.inputs.new("NodeSocketFloat", name)
        except Exception:
            socket = None

    if socket is not None:
        try:
            socket.default_value = default
        except Exception:
            pass


def _has_gltf_settings_socket(group, name: str) -> bool:
    for socket in getattr(group, "inputs", ()) or ():
        if socket.name == name:
            return True

    interface = getattr(group, "interface", None)
    for item in getattr(interface, "items_tree", ()) if interface is not None else ():
        if getattr(item, "item_type", "") == "SOCKET" and item.name == name:
            if getattr(item, "in_out", "INPUT") == "INPUT":
                return True
    return False


def _set_assetkit_json_prop(target, key: str, value: object | None) -> None:
    if not value:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return
    if payload and payload != "null":
        target[key] = payload


def _material_extra_extension(data: MeshPrimitiveData, name: str) -> object | None:
    extensions = _assetkit_extra_path(data.material_extra, "extensions")
    return _assetkit_extra_path(extensions, name)


_MAPPED_MATERIAL_EXTRA_EXTENSIONS = {
    "KHR_materials_anisotropy",
    "KHR_materials_clearcoat",
    "KHR_materials_diffuse_transmission",
    "KHR_materials_dispersion",
    "KHR_materials_emissive_strength",
    "KHR_materials_ior",
    "KHR_materials_iridescence",
    "KHR_materials_pbrSpecularGlossiness",
    "KHR_materials_sheen",
    "KHR_materials_specular",
    "KHR_materials_transmission",
    "KHR_materials_unlit",
    "KHR_materials_volume",
    "KHR_materials_volume_scatter",
    "ADOBE_materials_clearcoat_specular",
    "ADOBE_materials_clearcoat_tint",
    "ADOBE_materials_thin_transparency",
}


def _material_extra_for_custom_prop(data: MeshPrimitiveData) -> object | None:
    extra = data.material_extra
    if not isinstance(extra, dict):
        return extra

    children = _assetkit_extra_children(extra)
    if len(children) != 1 or children[0].get("name") != "extensions":
        return extra

    extensions = _assetkit_extra_children(children[0])
    if not extensions:
        return extra
    if all(str(ext.get("name") or "") in _MAPPED_MATERIAL_EXTRA_EXTENSIONS for ext in extensions):
        return None
    return extra


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
    for child in _assetkit_extra_children(value):
        if child.get("name") == name:
            return child
    return None


def _assetkit_extra_children(value: object | None) -> list[dict]:
    if not isinstance(value, dict):
        return []
    return [child for child in (value.get("children") or ()) if isinstance(child, dict)]


def _assetkit_extra_float(value: object | None, default: float = 0.0) -> float:
    if not isinstance(value, dict):
        return default
    try:
        return float(value.get("value"))
    except (TypeError, ValueError):
        return default


def _assetkit_extra_float_array(value: object | None, limit: int) -> tuple[float, ...]:
    if not isinstance(value, dict):
        return ()
    items = []
    for child in value.get("children") or ():
        items.append(_assetkit_extra_float(child))
        if len(items) >= limit:
            break
    return tuple(items)


def _assetkit_extra_plain_value(value: object | None) -> object | None:
    if not isinstance(value, dict):
        return None

    attrs = value.get("attributes") if isinstance(value.get("attributes"), dict) else {}
    node_type = attrs.get("type")
    children = [child for child in (value.get("children") or ()) if isinstance(child, dict)]

    if node_type == "array":
        return [_assetkit_extra_plain_value(child) for child in children]

    if node_type == "object" or children:
        out = {}
        for child in children:
            key = str(child.get("name") or "item")
            child_value = _assetkit_extra_plain_value(child)
            if key in out:
                current = out[key]
                if not isinstance(current, list):
                    out[key] = [current]
                out[key].append(child_value)
            else:
                out[key] = child_value
        return out

    return _assetkit_extra_plain_scalar(value.get("value"))


def _assetkit_extra_plain_scalar(value: object | None) -> object | None:
    if value is None:
        return None

    text = str(value)
    if text == "":
        return ""
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None

    try:
        if "." not in text and "e" not in text and "E" not in text:
            return int(text)
        return float(text)
    except ValueError:
        return text


def _texture_info(data: MeshPrimitiveData, role: str) -> TextureRefData | None:
    return (data.texture_infos or {}).get(role)


def _set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket:
        try:
            socket.default_value = value
        except TypeError:
            pass


def _set_input_if_nondefault(node, name: str, value: float, default: float) -> None:
    if abs(float(value) - float(default)) <= 1.0e-6:
        return
    _set_input(node, name, value)


def _set_first_input(node, names: tuple[str, ...], value) -> None:
    for name in names:
        socket = node.inputs.get(name)
        if socket:
            try:
                socket.default_value = value
            except TypeError:
                pass
            return


def _link_image(
    mat: bpy.types.Material,
    target,
    path: str,
    input_name: str,
    colorspace: str,
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return

    socket = target.inputs.get(input_name)
    if socket:
        mat.node_tree.links.new(tex.outputs["Color"], socket)


def _link_image_first(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return

    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(tex.outputs["Color"], socket)
            return


def _link_factor_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    channel: str,
    factor: float = 1.0,
    tex_info: TextureRefData | None = None,
) -> None:
    output = _factor_texture_output(mat, path, colorspace, channel, factor, tex_info)
    if not output:
        return
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return


def _factor_texture_output(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    channel: str,
    factor: float = 1.0,
    tex_info: TextureRefData | None = None,
):
    channel = _texture_channel_name(tex_info, channel)
    output = _image_texture_channel(mat, path, colorspace, channel, tex_info)
    if not output:
        return None
    if factor != 1.0:
        output = _multiply_value_factor(mat, output, factor, f"{channel} Factor")
    return output


def _link_specular_glossiness_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "specular")
    gloss_info = replace(tex_info, color_space="") if tex_info else None
    _link_color_texture(
        mat,
        bsdf,
        data.specular_texture,
        ("Specular Tint",),
        colorspace="sRGB",
        factor=(*data.specular_color, 1.0),
        tex_info=tex_info,
    )

    output = _image_texture_channel(mat, data.specular_texture, "Non-Color", "Alpha", gloss_info)
    if not output:
        return
    if data.specular_strength != 1.0:
        output = _multiply_value_factor(mat, output, data.specular_strength, "Glossiness Factor")
    output = _one_minus_value(mat, output, "Glossiness to Roughness")
    socket = bsdf.inputs.get("Roughness")
    if socket:
        mat.node_tree.links.new(output, socket)


def _link_range_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    channel: str,
    minimum: float,
    maximum: float,
    tex_info: TextureRefData | None = None,
) -> None:
    channel = _texture_channel_name(tex_info, channel)
    output = _image_texture_channel(mat, path, colorspace, channel, tex_info)
    if not output:
        return
    extent = float(maximum) - float(minimum)
    if extent != 1.0:
        output = _multiply_value_factor(mat, output, extent, f"{channel} Range")
    if minimum != 0.0:
        output = _add_value_factor(mat, output, float(minimum), f"{channel} Offset")
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return


def _link_color_texture(
    mat: bpy.types.Material,
    target,
    path: str,
    input_names: tuple[str, ...],
    colorspace: str,
    factor: tuple[float, float, float, float],
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return
    output = _multiply_color_factor(mat, tex.outputs.get("Color"), factor, "Color Factor")
    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(output, socket)
            return


def _link_base_color(
    mat: bpy.types.Material,
    target,
    data: MeshPrimitiveData,
    color_attr: str,
    color_input: str = "Base Color",
    alpha_socket=None,
) -> None:
    color_output = None
    alpha_output = None

    if data.base_color_texture:
        tex = _image_texture_node(mat, data.base_color_texture, "sRGB", _texture_info(data, "base_color"))
        if tex:
            color_output = tex.outputs.get("Color")
            alpha_output = tex.outputs.get("Alpha") if data.alpha_mode else None

    if color_attr:
        vertex_color = _vertex_color_node(mat, color_attr)
        if vertex_color:
            color_output = _multiply_color_outputs(
                mat,
                color_output,
                vertex_color.outputs.get("Color"),
                "Vertex Color",
            )
            if data.alpha_mode:
                alpha_output = _multiply_value_outputs(
                    mat,
                    alpha_output,
                    vertex_color.outputs.get("Alpha"),
                    "Vertex Alpha",
                )

    if color_output:
        color_output = _multiply_color_factor(mat, color_output, data.base_color, "Base Color Factor")
    if data.alpha_mode and alpha_output:
        alpha_output = _multiply_value_factor(mat, alpha_output, data.opacity, "Base Alpha Factor")

    base_color = target.inputs.get(color_input)
    if base_color and color_output:
        mat.node_tree.links.new(color_output, base_color)
    if data.alpha_mode and alpha_socket and alpha_output:
        mat.node_tree.links.new(alpha_output, alpha_socket)


def _link_occlusion_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
    settings_node=None,
) -> None:
    tex = _image_texture_node(mat, data.occlusion_texture, "Non-Color", _texture_info(data, "occlusion"))
    if not tex:
        return

    ao_output = _separate_color_channel(
        mat,
        tex.outputs.get("Color"),
        _texture_channel_name(_texture_info(data, "occlusion"), "Red"),
    )
    strength = max(0.0, min(1.0, float(data.occlusion_strength)))
    if strength != 1.0:
        ao_output = _multiply_value_factor(mat, ao_output, strength, "Occlusion Strength")
        ao_output = _add_value_factor(mat, ao_output, 1.0 - strength, "Occlusion Base")
    if settings_node and ao_output:
        socket = settings_node.inputs.get("Occlusion")
        if socket:
            mat.node_tree.links.new(ao_output, socket)


def _link_emissive_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    emission = bsdf.inputs.get("Emission Color")
    if not emission:
        return

    tex = _image_texture_node(mat, data.emissive_texture, "sRGB", _texture_info(data, "emissive"))
    if not tex:
        return

    color_output = _multiply_color_factor(
        mat,
        tex.outputs.get("Color"),
        (*data.emissive_color, 1.0),
        "Emissive Factor",
    )
    if color_output:
        mat.node_tree.links.new(color_output, emission)


def _link_volume_absorption(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output or "Volume" not in output.inputs:
        return

    try:
        volume = nodes.new("ShaderNodeVolumeAbsorption")
    except Exception:
        return
    volume.label = "AssetKit Volume Absorption"
    volume["assetkit_volume_node"] = "absorption"

    color = volume.inputs.get("Color")
    if color:
        color.default_value = (*data.volume_attenuation_color, 1.0)

    density = volume.inputs.get("Density")
    if density:
        distance = float(data.volume_attenuation_distance)
        density.default_value = 1.0 / distance if distance > 0.0 else 0.0

    volume_output = volume.outputs.get("Volume")
    if volume_output:
        links.new(volume_output, output.inputs["Volume"])


def _has_volume_scatter(data: MeshPrimitiveData) -> bool:
    return bool(_volume_scatter_color(data))


def _volume_scatter_color(data: MeshPrimitiveData) -> tuple[float, float, float] | None:
    ext = _material_extra_extension(data, "KHR_materials_volume_scatter")
    color = _assetkit_extra_float_array(_assetkit_extra_child(ext, "multiscatterColorFactor"), 3)
    if len(color) != 3:
        return None
    return tuple(max(0.0, min(1.0, float(value))) for value in color)


def _link_volume_scatter(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    color = _volume_scatter_color(data)
    if not color:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output or "Volume" not in output.inputs:
        return

    try:
        scatter = nodes.new("ShaderNodeVolumeScatter")
    except Exception:
        return
    scatter.label = "AssetKit Volume Scatter"
    scatter["assetkit_volume_node"] = "scatter"

    color_socket = scatter.inputs.get("Color")
    if color_socket:
        color_socket.default_value = (*color, 1.0)

    density = scatter.inputs.get("Density")
    if density:
        distance = float(data.volume_attenuation_distance)
        if distance > 0.0 and math.isfinite(distance):
            density.default_value = min(1.0 / distance, 1.0)
        else:
            density.default_value = max(0.0, min(float(data.volume_thickness), 1.0))

    volume_output = scatter.outputs.get("Volume")
    volume_input = output.inputs.get("Volume")
    if not volume_output or not volume_input:
        return

    previous = volume_input.links[0].from_socket if volume_input.links else None
    if previous is None:
        links.new(volume_output, volume_input)
        return

    try:
        add = nodes.new("ShaderNodeAddShader")
    except Exception:
        return
    add.label = "AssetKit Volume"
    for link in list(volume_input.links):
        links.remove(link)
    links.new(previous, add.inputs[0])
    links.new(volume_output, add.inputs[1])
    links.new(add.outputs.get("Shader"), volume_input)


def _vertex_color_node(mat: bpy.types.Material, name: str):
    nodes = mat.node_tree.nodes
    try:
        node = nodes.new("ShaderNodeVertexColor")
        node.layer_name = name
    except Exception:
        try:
            node = nodes.new("ShaderNodeAttribute")
            node.attribute_name = name
        except Exception:
            return None
    return node


def _multiply_color_outputs(
    mat: bpy.types.Material,
    output_a,
    output_b,
    label: str,
):
    if output_a is None:
        return output_b
    if output_b is None:
        return output_a

    node = _new_color_multiply_node(mat, label)
    if not node:
        return output_a

    inputs = _color_multiply_inputs(node)
    output = _color_multiply_output(node)
    if not inputs or output is None:
        return output_a

    mat.node_tree.links.new(output_a, inputs[0])
    mat.node_tree.links.new(output_b, inputs[1])
    return output


def _multiply_color_factor(
    mat: bpy.types.Material,
    output,
    factor: tuple[float, float, float, float],
    label: str,
):
    color = tuple(float(value) for value in factor[:3])
    if color == (1.0, 1.0, 1.0):
        return output

    node = _new_color_multiply_node(mat, label)
    if not node:
        return output

    inputs = _color_multiply_inputs(node)
    result = _color_multiply_output(node)
    if not inputs or result is None:
        return output

    mat.node_tree.links.new(output, inputs[0])
    try:
        inputs[1].default_value = (*color, 1.0)
    except TypeError:
        pass
    return result


def _new_color_multiply_node(mat: bpy.types.Material, label: str):
    nodes = mat.node_tree.nodes
    try:
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = "MULTIPLY"
        node.inputs["Fac"].default_value = 1.0
    except Exception:
        try:
            node = nodes.new("ShaderNodeMix")
            node.data_type = "RGBA"
            node.blend_type = "MULTIPLY"
            node.inputs["Factor"].default_value = 1.0
        except Exception:
            return None
    node.label = label
    return node


def _color_multiply_inputs(node) -> tuple[object, object] | None:
    if "Color1" in node.inputs and "Color2" in node.inputs:
        return node.inputs["Color1"], node.inputs["Color2"]
    if len(node.inputs) >= 8:
        return node.inputs[6], node.inputs[7]
    return None


def _color_multiply_output(node):
    if "Color" in node.outputs:
        return node.outputs["Color"]
    if len(node.outputs) >= 3:
        return node.outputs[2]
    return None


def _multiply_value_outputs(
    mat: bpy.types.Material,
    output_a,
    output_b,
    label: str,
):
    if output_a is None:
        return output_b
    if output_b is None:
        return output_a

    node = _new_value_multiply_node(mat, label)
    if not node:
        return output_a

    mat.node_tree.links.new(output_a, node.inputs[0])
    mat.node_tree.links.new(output_b, node.inputs[1])
    return node.outputs[0]


def _multiply_value_factor(
    mat: bpy.types.Material,
    output,
    factor: float,
    label: str,
):
    if factor == 1.0:
        return output

    node = _new_value_multiply_node(mat, label)
    if not node:
        return output

    mat.node_tree.links.new(output, node.inputs[0])
    node.inputs[1].default_value = factor
    return node.outputs[0]


def _add_value_factor(
    mat: bpy.types.Material,
    output,
    value: float,
    label: str,
):
    if value == 0.0:
        return output

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return output
    node.label = label
    node.operation = "ADD"
    mat.node_tree.links.new(output, node.inputs[0])
    node.inputs[1].default_value = value
    return node.outputs[0]


def _one_minus_value(mat: bpy.types.Material, output, label: str):
    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return output
    node.label = label
    node.operation = "SUBTRACT"
    node.inputs[0].default_value = 1.0
    mat.node_tree.links.new(output, node.inputs[1])
    return node.outputs[0]


def _mix_color_factor(
    mat: bpy.types.Material,
    output,
    base: tuple[float, float, float],
    factor: float,
    label: str,
):
    if output is None:
        return None

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMixRGB")
        node.blend_type = "MIX"
        node.inputs["Fac"].default_value = factor
        node.inputs["Color1"].default_value = (*base, 1.0)
        mat.node_tree.links.new(output, node.inputs["Color2"])
        node.label = label
        return node.outputs["Color"]
    except Exception:
        pass

    try:
        node = mat.node_tree.nodes.new("ShaderNodeMix")
    except Exception:
        return output
    node.data_type = "RGBA"
    node.blend_type = "MIX"
    node.inputs["Factor"].default_value = factor
    node.inputs[6].default_value = (*base, 1.0)
    node.label = label
    mat.node_tree.links.new(output, node.inputs[7])
    return node.outputs[2]


def _new_value_multiply_node(mat: bpy.types.Material, label: str):
    try:
        node = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return None
    node.label = label
    node.operation = "MULTIPLY"
    return node


def _link_base_color_texture(mat: bpy.types.Material, bsdf, data: MeshPrimitiveData) -> None:
    _link_base_color(mat, bsdf, data, "")


def _link_transparent_texture(
    mat: bpy.types.Material,
    alpha_socket,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "transparent")
    tex = _image_texture_node(mat, data.transparent_texture, "Non-Color", tex_info)
    if not tex:
        return

    opaque = int(data.transparent_opaque)
    channel = _texture_channel_name(tex_info, "")
    if channel:
        if channel == "Alpha":
            output = tex.outputs.get("Alpha") or _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent Alpha")
        else:
            output = _separate_color_channel(mat, tex.outputs.get("Color"), channel)
    elif opaque in {_AK_OPAQUE_RGB_ONE, _AK_OPAQUE_RGB_ZERO}:
        output = _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent RGB")
    else:
        output = tex.outputs.get("Alpha") or _rgb_to_luminance(mat, tex.outputs.get("Color"), "Transparent Alpha")

    if not output:
        return

    if float(data.transparent_amount) != 1.0:
        output = _multiply_value_factor(mat, output, data.transparent_amount, "Transparent Amount")

    if opaque in {_AK_OPAQUE_A_ZERO, _AK_OPAQUE_RGB_ZERO}:
        output = _one_minus_value(mat, output, "Transparent Invert")

    _replace_socket_link(mat, alpha_socket, output)


def _has_diffuse_transmission(data: MeshPrimitiveData) -> bool:
    return (
        float(data.diffuse_transmission) > 0.0
        or bool(data.diffuse_transmission_texture)
        or bool(data.diffuse_transmission_color_texture)
    )


def _link_diffuse_transmission_shader(mat: bpy.types.Material, data: MeshPrimitiveData) -> None:
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    output = nodes.get("Material Output")
    if not output:
        return
    surface = output.inputs.get("Surface")
    if not surface:
        return

    previous = surface.links[0].from_socket if surface.links else None
    if previous is None:
        bsdf = nodes.get("Principled BSDF")
        previous = bsdf.outputs.get("BSDF") if bsdf else None
    if previous is None:
        return

    try:
        translucent = nodes.new("ShaderNodeBsdfTranslucent")
        mix = nodes.new("ShaderNodeMixShader")
    except Exception:
        return
    translucent.label = "AssetKit Diffuse Transmission"
    translucent["assetkit_diffuse_transmission_node"] = "translucent"
    mix.label = "AssetKit Diffuse Transmission"
    mix["assetkit_diffuse_transmission_node"] = "mix"

    color_socket = translucent.inputs.get("Color")
    if color_socket:
        color_socket.default_value = (*data.diffuse_transmission_color, 1.0)
        if data.diffuse_transmission_color_texture:
            _link_color_texture(
                mat,
                translucent,
                data.diffuse_transmission_color_texture,
                ("Color",),
                colorspace="sRGB",
                factor=(*data.diffuse_transmission_color, 1.0),
                tex_info=_texture_info(data, "diffuse_transmission_color"),
            )

    factor_output = None
    if data.diffuse_transmission_texture:
        factor_output = _factor_texture_output(
            mat,
            data.diffuse_transmission_texture,
            "Non-Color",
            "Alpha",
            data.diffuse_transmission,
            _texture_info(data, "diffuse_transmission"),
        )
    factor = mix.inputs.get("Fac")
    if factor_output and factor:
        links.new(factor_output, factor)
    elif factor:
        factor.default_value = max(0.0, min(1.0, float(data.diffuse_transmission)))

    for link in list(surface.links):
        links.remove(link)
    links.new(previous, mix.inputs[1])
    links.new(translucent.outputs.get("BSDF"), mix.inputs[2])
    links.new(mix.outputs.get("Shader"), surface)


def _link_anisotropy_texture(
    mat: bpy.types.Material,
    bsdf,
    data: MeshPrimitiveData,
) -> None:
    tex_info = _texture_info(data, "anisotropy")
    tex = _image_texture_node(mat, data.anisotropy_texture, "Non-Color", tex_info)
    if not tex:
        return

    separate = _separate_color_node(mat, tex.outputs["Color"])
    if not separate:
        return

    strength = separate.outputs.get("Blue")
    if strength:
        if data.anisotropy != 1.0:
            strength = _multiply_value_factor(mat, strength, data.anisotropy, "Anisotropy Factor")
        socket = bsdf.inputs.get("Anisotropic")
        if socket:
            mat.node_tree.links.new(strength, socket)

    rotation = _anisotropy_rotation_output(mat, separate, data.anisotropy_rotation)
    socket = bsdf.inputs.get("Anisotropic Rotation")
    if rotation and socket:
        mat.node_tree.links.new(rotation, socket)

    tangent = bsdf.inputs.get("Tangent")
    if tangent:
        try:
            tangent_node = mat.node_tree.nodes.new("ShaderNodeTangent")
            tangent_node.direction_type = "UV_MAP"
            tangent_node.uv_map = _uv_layer_name(tex_info.slot if tex_info else 0)
            mat.node_tree.links.new(tangent_node.outputs["Tangent"], tangent)
        except Exception:
            pass


def _anisotropy_rotation_output(
    mat: bpy.types.Material,
    separate,
    factor_rotation: float,
):
    red = separate.outputs.get("Red")
    green = separate.outputs.get("Green")
    if not red or not green:
        return None

    x = _add_value_factor(mat, _multiply_value_factor(mat, red, 2.0, "Anisotropy X Scale"), -1.0, "Anisotropy X Bias")
    y = _add_value_factor(mat, _multiply_value_factor(mat, green, 2.0, "Anisotropy Y Scale"), -1.0, "Anisotropy Y Bias")

    try:
        atan = mat.node_tree.nodes.new("ShaderNodeMath")
    except Exception:
        return None
    atan.label = "Anisotropy Rotation"
    atan.operation = "ARCTAN2"
    mat.node_tree.links.new(y, atan.inputs[0])
    mat.node_tree.links.new(x, atan.inputs[1])
    output = atan.outputs[0]

    if factor_rotation != 0.0:
        output = _add_value_factor(mat, output, factor_rotation, "Anisotropy Rotation Factor")

    return _multiply_value_factor(mat, output, 1.0 / (2.0 * math.pi), "Anisotropy Rotation Units")


def _replace_socket_link(mat: bpy.types.Material, socket, output) -> None:
    if not socket or not output:
        return
    for link in list(socket.links):
        mat.node_tree.links.remove(link)
    mat.node_tree.links.new(output, socket)


def _rgb_to_luminance(mat: bpy.types.Material, output, label: str):
    if output is None:
        return None
    try:
        node = mat.node_tree.nodes.new("ShaderNodeRGBToBW")
    except Exception:
        return output
    node.label = label
    mat.node_tree.links.new(output, node.inputs["Color"])
    return node.outputs["Val"]


def _link_metallic_roughness_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    tex_info: TextureRefData | None = None,
    metallic_factor: float = 1.0,
    roughness_factor: float = 1.0,
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color", tex_info)
    if not tex:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    separate = nodes.new("ShaderNodeSeparateColor")
    links.new(tex.outputs["Color"], separate.inputs["Color"])

    roughness = bsdf.inputs.get("Roughness")
    metallic = bsdf.inputs.get("Metallic")
    if roughness:
        roughness_output = separate.outputs["Green"]
        if roughness_factor != 1.0:
            roughness_output = _multiply_value_factor(mat, roughness_output, roughness_factor, "Roughness Factor")
        links.new(roughness_output, roughness)
    if metallic:
        metallic_output = separate.outputs["Blue"]
        if metallic_factor != 1.0:
            metallic_output = _multiply_value_factor(mat, metallic_output, metallic_factor, "Metallic Factor")
        links.new(metallic_output, metallic)


def _link_normal_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    strength: float,
    tex_info: TextureRefData | None = None,
    input_name: str = "Normal",
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color", tex_info)
    if not tex:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.label = f"AssetKit {(tex_info.role if tex_info else input_name)}"
    if tex_info and tex_info.role:
        normal_map["assetkit_normal_role"] = tex_info.role
    normal_map.inputs["Strength"].default_value = strength
    links.new(tex.outputs["Color"], normal_map.inputs["Color"])
    normal = bsdf.inputs.get(input_name)
    if normal:
        links.new(normal_map.outputs["Normal"], normal)


def _image_texture_node(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    tex_info: TextureRefData | None = None,
):
    colorspace = _texture_color_space(tex_info, colorspace)
    cache_key = _texture_node_cache_key(path, colorspace, tex_info)
    if _ACTIVE_TEXTURE_NODE_CACHE is not None and cache_key is not None:
        tex = _ACTIVE_TEXTURE_NODE_CACHE.get(cache_key)
        if _node_is_alive(mat, tex):
            _append_texture_node_role(tex, tex_info)
            return tex

    defer_image = _should_defer_texture_image(path)
    image = _cached_texture_image(path, colorspace) if defer_image else _load_texture_image(path, colorspace)
    if not image and not defer_image:
        return None

    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    if image:
        tex.image = image
    elif defer_image:
        _queue_deferred_texture_image(tex, path, colorspace)
    if tex_info and tex_info.role:
        tex.label = f"AssetKit {tex_info.role}"
        tex["assetkit_texture_role"] = tex_info.role
        if tex_info.slot:
            tex["assetkit_texture_slot"] = tex_info.slot
        if colorspace:
            tex["assetkit_texture_colorspace"] = colorspace
        if tex_info.image_name:
            tex["assetkit_texture_image_name"] = tex_info.image_name
        if tex_info.sampler_name:
            tex["assetkit_texture_sampler_name"] = tex_info.sampler_name
        if tex_info.channels:
            tex["assetkit_texture_channels"] = tex_info.channels
        _set_texture_sampler_props(tex, tex_info)
        _set_assetkit_json_prop(tex, "assetkit_texture_extra_json", tex_info.texture_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_ref_extra_json", tex_info.texref_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_image_extra_json", tex_info.image_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_sampler_extra_json", tex_info.sampler_extra)
    _configure_texture_node(mat, tex, tex_info)
    if _ACTIVE_TEXTURE_NODE_CACHE is not None and cache_key is not None:
        _ACTIVE_TEXTURE_NODE_CACHE[cache_key] = tex
    return tex


def _texture_node_cache_key(path: str, colorspace: str, tex_info: TextureRefData | None) -> object | None:
    if tex_info and (tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra):
        return None

    try:
        source_path = _texture_abs_path(path)
    except Exception:
        return None

    if tex_info is None:
        return (source_path, colorspace, 0, 1, 1, 0, 0, 0, False)

    transform = None
    if tex_info.has_transform:
        transform = (
            float(tex_info.transform_offset[0]),
            float(tex_info.transform_offset[1]),
            float(tex_info.transform_scale[0]),
            float(tex_info.transform_scale[1]),
            float(tex_info.transform_rotation),
        )

    return (
        source_path,
        colorspace,
        _texture_uv_slot(tex_info),
        int(tex_info.wrap_s),
        int(tex_info.wrap_t),
        int(tex_info.min_filter),
        int(tex_info.mag_filter),
        int(tex_info.mip_filter),
        transform,
    )


def _append_texture_node_role(tex, tex_info: TextureRefData | None) -> None:
    if not tex_info or not tex_info.role:
        return
    try:
        roles = str(tex.get("assetkit_texture_roles") or tex.get("assetkit_texture_role") or "")
        if tex_info.role not in {role for role in roles.split(",") if role}:
            tex["assetkit_texture_roles"] = f"{roles},{tex_info.role}" if roles else tex_info.role
    except Exception:
        pass


def _node_is_alive(mat: bpy.types.Material, node) -> bool:
    if node is None:
        return False
    try:
        return mat.node_tree.nodes.get(node.name) == node
    except ReferenceError:
        return False
    except Exception:
        return False


def _socket_cache_key(socket) -> int:
    try:
        return int(socket.as_pointer())
    except Exception:
        return 0


def _should_defer_texture_image(path: str) -> bool:
    return _ACTIVE_TEXTURE_LOAD_MODE == "DEFERRED" and bool(path)


def _queue_deferred_texture_image(tex, path: str, colorspace: str, store_props: bool = True) -> None:
    global _DEFERRED_TEXTURE_TIMER_ACTIVE
    key = _texture_image_cache_key(path, colorspace)
    image = _cached_texture_image_by_key(key)
    if image:
        _assign_texture_image(tex, image)
        return

    waiters = _DEFERRED_TEXTURE_WAITERS.get(key)
    if waiters is None:
        _DEFERRED_TEXTURE_WAITERS[key] = [tex]
        _DEFERRED_TEXTURE_KEYS.append(key)
    else:
        waiters.append(tex)

    if store_props:
        try:
            tex["assetkit_texture_pending_path"] = key[0]
            tex["assetkit_texture_pending_colorspace"] = key[1]
        except Exception:
            pass

    if not _DEFERRED_TEXTURE_TIMER_ACTIVE:
        _DEFERRED_TEXTURE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_texture_timer, first_interval=0.001)


def _deferred_texture_timer() -> float | None:
    global _DEFERRED_TEXTURE_TIMER_ACTIVE
    started_at = time.perf_counter()
    while _DEFERRED_TEXTURE_KEYS:
        key = _DEFERRED_TEXTURE_KEYS.popleft()
        waiters = _DEFERRED_TEXTURE_WAITERS.pop(key, [])
        live_waiters = [node for node in waiters if _node_ref_alive(node)]
        if live_waiters:
            image = _load_texture_image_immediate(key[0], key[1])
            if image:
                for node in live_waiters:
                    _assign_texture_image(node, image)
        if time.perf_counter() - started_at >= _DEFERRED_TEXTURE_TIME_BUDGET:
            return 0.001

    _DEFERRED_TEXTURE_TIMER_ACTIVE = False
    return None


def _assign_texture_image(tex, image) -> None:
    if not _node_ref_alive(tex):
        return
    try:
        tex.image = image
        if "assetkit_texture_pending_path" in tex:
            del tex["assetkit_texture_pending_path"]
        if "assetkit_texture_pending_colorspace" in tex:
            del tex["assetkit_texture_pending_colorspace"]
    except Exception:
        pass


def _node_ref_alive(node) -> bool:
    if node is None:
        return False
    try:
        tree = node.id_data
        return tree is not None and tree.nodes.get(node.name) == node
    except ReferenceError:
        return False
    except Exception:
        return False


def _texture_color_space(tex_info: TextureRefData | None, fallback: str) -> str:
    if tex_info and tex_info.color_space:
        return tex_info.color_space
    return fallback


def _load_texture_image(path: str, colorspace: str):
    return _load_texture_image_immediate(path, colorspace)


def _load_texture_image_immediate(path: str, colorspace: str):
    source_path = _texture_abs_path(path)
    image = _find_texture_image(source_path, colorspace)
    if image:
        return image

    if _is_ktx2_path(path):
        image = _decode_ktx2_image(source_path, colorspace)
        if image:
            return image

    image = None
    try:
        image = bpy.data.images.load(source_path, check_existing=False)
    except RuntimeError:
        image = None

    if image:
        _register_texture_image(image, source_path, colorspace)
        return image

    if image and _is_ktx2_path(path):
        try:
            bpy.data.images.remove(image)
        except Exception:
            pass

    if _is_ktx2_path(path):
        image = _decode_ktx2_image(source_path, colorspace)
        if image:
            return image

    return None


def _find_texture_image(path: str, colorspace: str):
    key = _texture_image_cache_key(path, colorspace)
    cached = _cached_texture_image_by_key(key)
    if cached is not None:
        return cached

    source_path = key[0]
    for image in bpy.data.images:
        image_path = image.get("assetkit_source_path") or image.filepath
        if not image_path:
            continue
        try:
            image_path = bpy.path.abspath(image_path)
        except Exception:
            pass
        if os.path.abspath(os.fspath(image_path)) != source_path:
            continue
        if _image_colorspace(image) != colorspace:
            continue
        image["assetkit_source_path"] = source_path
        image["assetkit_colorspace"] = colorspace
        _TEXTURE_IMAGE_CACHE[key] = image
        return image
    return None


def _cached_texture_image(path: str, colorspace: str):
    return _cached_texture_image_by_key(_texture_image_cache_key(path, colorspace))


def _cached_texture_image_by_key(key: tuple[str, str]):
    cached = _TEXTURE_IMAGE_CACHE.get(key)
    if cached is not None:
        try:
            if bpy.data.images.get(cached.name) == cached:
                if _image_colorspace(cached) == key[1]:
                    return cached
        except ReferenceError:
            pass
        _TEXTURE_IMAGE_CACHE.pop(key, None)
    return None


def _register_texture_image(image, path: str, colorspace: str) -> None:
    source_path, normalized_colorspace = _texture_image_cache_key(path, colorspace)
    image["assetkit_source_path"] = source_path
    image["assetkit_colorspace"] = colorspace
    _set_image_colorspace(image, colorspace)
    _TEXTURE_IMAGE_CACHE[(source_path, normalized_colorspace)] = image


def _texture_image_cache_key(path: str, colorspace: str) -> tuple[str, str]:
    return _texture_abs_path(path), str(colorspace or "")


def _texture_abs_path(path: str) -> str:
    source = os.fspath(path)
    cached = _TEXTURE_PATH_CACHE.get(source)
    if cached is not None:
        return cached
    cached = os.path.abspath(source)
    _TEXTURE_PATH_CACHE[source] = cached
    return cached


def _image_colorspace(image) -> str:
    stored = image.get("assetkit_colorspace")
    if stored:
        return str(stored)
    try:
        return image.colorspace_settings.name
    except Exception:
        return ""


def _image_has_size(image) -> bool:
    try:
        return int(image.size[0]) > 0 and int(image.size[1]) > 0
    except Exception:
        return False


def _set_image_colorspace(image, colorspace: str) -> None:
    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass


def _is_ktx2_path(path: str) -> bool:
    return os.fspath(path).lower().endswith(".ktx2")


def _decode_ktx2_image(path: str, colorspace: str):
    source_path = _texture_abs_path(path)
    image = _find_texture_image(source_path, colorspace)
    if image:
        return image

    try:
        from . import _assetkit_blender
    except Exception:
        return None

    try:
        decoded = _assetkit_blender.decode_ktx2(source_path)
    except Exception as exc:
        if _PROFILE_MATERIAL_STATS is not None:
            _profile_log(f"KTX2 decode skipped path={path!r} error={exc}")
        return None

    width = int(decoded.get("width") or 0)
    height = int(decoded.get("height") or 0)
    pixels = _buffer_view(decoded.get("pixels_f32") or b"", "f")
    if width <= 0 or height <= 0 or pixels is None or len(pixels) != width * height * 4:
        return None

    name = os.path.basename(source_path)
    image = bpy.data.images.new(name, width=width, height=height, alpha=True, float_buffer=False)
    image.pixels.foreach_set(pixels)
    image.filepath = source_path
    image["assetkit_decoded_texture"] = True
    _register_texture_image(image, source_path, colorspace)
    image.update()
    return image


def _image_texture_channel(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    channel: str,
    tex_info: TextureRefData | None = None,
):
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return None
    channel = _texture_channel_name(tex_info, channel)
    if channel == "Alpha":
        return tex.outputs.get("Alpha") or tex.outputs.get("Color")
    if channel == "Color":
        return tex.outputs.get("Color")

    return _separate_color_channel(mat, tex.outputs.get("Color"), channel)


def _texture_channel_name(tex_info: TextureRefData | None, fallback: str) -> str:
    letters = _texture_channel_letters(tex_info)
    if len(letters) != 1:
        return fallback
    return {
        "R": "Red",
        "G": "Green",
        "B": "Blue",
        "A": "Alpha",
    }.get(letters[0], fallback)


def _texture_channel_letters(tex_info: TextureRefData | None) -> tuple[str, ...]:
    if not tex_info or not tex_info.channels:
        return ()
    seen = []
    for letter in str(tex_info.channels).upper():
        if letter in {"R", "G", "B", "A"} and letter not in seen:
            seen.append(letter)
    return tuple(seen)


def _separate_color_channel(
    mat: bpy.types.Material,
    color_output,
    channel: str,
):
    if color_output is None:
        return None

    separate = _separate_color_node(mat, color_output)
    if separate:
        return separate.outputs.get(channel)
    return color_output


def _separate_color_node(mat: bpy.types.Material, color_output):
    global _ACTIVE_SEPARATE_COLOR_CACHE
    cache_key = _socket_cache_key(color_output)
    if _ACTIVE_SEPARATE_COLOR_CACHE is not None and cache_key:
        separate = _ACTIVE_SEPARATE_COLOR_CACHE.get(cache_key)
        if _node_is_alive(mat, separate):
            return separate

    try:
        separate = mat.node_tree.nodes.new("ShaderNodeSeparateColor")
        mat.node_tree.links.new(color_output, separate.inputs["Color"])
    except Exception:
        return None

    if _ACTIVE_SEPARATE_COLOR_CACHE is not None and cache_key:
        _ACTIVE_SEPARATE_COLOR_CACHE[cache_key] = separate
    return separate


def _configure_texture_node(mat: bpy.types.Material, tex, tex_info: TextureRefData | None) -> None:
    if not tex_info:
        return

    tex.extension = _texture_extension(tex_info)
    tex.interpolation = _texture_interpolation(tex_info)

    uv_slot = _texture_uv_slot(tex_info)
    needs_uv_node = uv_slot > 0 or tex_info.has_transform
    if not needs_uv_node:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = _uv_layer_name(uv_slot)
    vector_output = uv.outputs.get("UV")

    if tex_info.has_transform:
        offset, rotation, scale = _texture_transform_gltf_to_blender(tex_info)
        mapping = nodes.new("ShaderNodeMapping")
        mapping.label = f"AssetKit {tex_info.role} Transform"
        mapping["assetkit_texture_role"] = tex_info.role
        if hasattr(mapping, "vector_type"):
            mapping.vector_type = "POINT"
        mapping.inputs["Location"].default_value[0] = offset[0]
        mapping.inputs["Location"].default_value[1] = offset[1]
        mapping.inputs["Rotation"].default_value[2] = rotation
        mapping.inputs["Scale"].default_value[0] = scale[0]
        mapping.inputs["Scale"].default_value[1] = scale[1]
        if vector_output:
            links.new(vector_output, mapping.inputs["Vector"])
        vector_output = mapping.outputs.get("Vector")

    if vector_output:
        links.new(vector_output, tex.inputs["Vector"])


def _texture_uv_slot(tex_info: TextureRefData) -> int:
    if tex_info.has_transform and tex_info.transform_slot >= 0:
        return tex_info.transform_slot
    return tex_info.slot


def _texture_transform_gltf_to_blender(
    tex_info: TextureRefData,
) -> tuple[tuple[float, float], float, tuple[float, float]]:
    return _texture_transform_values_gltf_to_blender(
        tex_info.transform_offset,
        float(tex_info.transform_rotation),
        tex_info.transform_scale,
    )


def _texture_transform_values_gltf_to_blender(
    offset: tuple[float, float],
    rotation: float,
    scale: tuple[float, float],
) -> tuple[tuple[float, float], float, tuple[float, float]]:
    return (
        (
            float(offset[0]) + float(scale[1]) * math.sin(rotation),
            1.0 - float(offset[1]) - float(scale[1]) * math.cos(rotation),
        ),
        rotation,
        (float(scale[0]), float(scale[1])),
    )


def _uv_layer_name(slot: int) -> str:
    return "UVMap" if slot <= 0 else f"UVMap.{slot:03d}"


def _texture_extension(tex_info: TextureRefData | None) -> str:
    if tex_info is None:
        return _TEXTURE_EXTENSION_DEFAULT
    wrap_s = tex_info.wrap_s
    wrap_t = tex_info.wrap_t
    if wrap_s != wrap_t:
        return "REPEAT"
    if wrap_s == 2 or wrap_s == 5:
        return "MIRROR"
    if wrap_s == 3:
        return "EXTEND"
    if wrap_s == 4:
        return "CLIP"
    return "REPEAT"


def _texture_interpolation(tex_info: TextureRefData | None) -> str:
    if tex_info is None:
        return _TEXTURE_INTERPOLATION_DEFAULT
    if tex_info.mag_filter == 1 or tex_info.min_filter in {1, 4, 5}:
        return "Closest"
    return "Linear"


def _set_texture_sampler_props(tex, tex_info: TextureRefData) -> None:
    extension = _texture_extension(tex_info)
    interpolation = _texture_interpolation(tex_info)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_s", int(tex_info.wrap_s), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_t", int(tex_info.wrap_t), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_p", int(tex_info.wrap_p), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_min_filter", int(tex_info.min_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_mag_filter", int(tex_info.mag_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_mip_filter", int(tex_info.mip_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_extension", extension, _TEXTURE_EXTENSION_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_interpolation", interpolation, _TEXTURE_INTERPOLATION_DEFAULT)
