from __future__ import annotations

import gc
import os
import threading
import time
from functools import wraps

import bpy

from .assetkit import (
    AssetKit,
    AssetKitSceneData,
    CurveData,
    MeshPrimitiveData,
    SceneNodeData,
    _profile_log,
    native_load_meshes,
)
from .imp import profile as _profile_state, textures as _textures
from .imp.animation import actions as _animation
from .imp.animation.actions import (
    _new_import_animation_scope,
    _reset_action_cache,
)
from .imp.build import (
    common as _build_common,
    _apply_deferred_bind_pose_skins,
    _apply_deferred_collection_instances,
    _begin_scene_build,
    _can_defer_scene_nodes,
    _compact_content_key_options,
    _create_curve_objects,
    _create_import_unit,
    _finish_compact_static_instances,
    _finish_deferred_scene_nodes,
    _finish_import,
    _import_result_objects,
    _mesh_import_units,
    _prebuild_material_cache,
    _scene_has_timeline_content,
    _scene_info_from_loaded,
    _snapshot_actions,
    _snapshot_scene_frame_range,
    _sort_mesh_import_units_for_blender,
)
from .imp.material import (
    core as _materials,
    _reset_material_template_cache,
)
from .imp.mesh import (
    _apply_shading,  # noqa: F401 - compatibility re-export
    _drain_deferred_staging_work,
)
from .imp.profile import (
    _log_material_profile,
    _reset_material_profile,
)
from .imp.viewport import (
    object_bounds as _object_bounds,  # noqa: F401 - compatibility re-export
)
from .load_options import (
    AKB_LOAD_DEFER_NORMALS_AUTO,
    AKB_LOAD_DEFER_NORMALS_NO,
    AKB_LOAD_DEFER_NORMALS_YES,
    AKB_LOAD_OPT_DEFER_CUSTOM_NORMALS,
    AKB_LOAD_OPT_PRESERVE_TANGENTS,
    AKB_LOAD_OPT_SCENE_BOUNDS,
    AKB_LOAD_OPT_TEXTURE_LOADING,
    AKB_LOAD_TEXTURE_AUTO,
    AKB_LOAD_TEXTURE_DEFERRED,
    AKB_LOAD_TEXTURE_IMMEDIATE,
    LoadOptions,
)

_MATERIAL_TEMPLATE_CLONE_PRIMITIVE_LIMIT = 1024
_PROGRESSIVE_BATCH_SIZE = 128
_PROGRESSIVE_TIME_BUDGET = 0.016
_PROGRESSIVE_LARGE_SCENE_UNIT_THRESHOLD = 1024
_PROGRESSIVE_LOAD_POLL_INTERVAL = 0.020
_ACTIVE_IMPORT_JOBS: list[object] = []
_SUSPEND_GC_DURING_BLOCKING_IMPORT = True


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000.0


def _suspend_gc_during_import_call(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        gc_was_enabled = gc.isenabled()
        suspend = _SUSPEND_GC_DURING_BLOCKING_IMPORT and gc_was_enabled
        if suspend:
            gc.disable()
        try:
            return func(*args, **kwargs)
        finally:
            if suspend:
                gc.enable()

    return wrapped


@_suspend_gc_during_import_call
def import_assetkit_file(
    filepath: str,
    library_path: str = "",
    load_options: LoadOptions | None = None,
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
    shading_mode = str(shading_mode or "AUTO").upper()
    _reset_action_cache()
    _reset_material_template_cache()
    _reset_material_profile()

    _animation.ACTIVE_SCOPE = _new_import_animation_scope(filepath)

    load_options               = _compact_content_key_options(load_options)
    load_options               = _scene_bounds_options(
        load_options,
        focus_mode,
        placement_mode,
        scene_was_empty,
    )
    existing_actions           = _snapshot_actions(fit_timeline)
    existing_frame_range       = _snapshot_scene_frame_range(fit_timeline)
    scene_had_timeline_content = _scene_has_timeline_content(bpy.context.scene) if fit_timeline else False
    texture_load_mode          = _texture_load_mode(load_options)
    profile_detail             = _profile_state.stats is not None
    defer_custom_normals       = _defer_custom_normals(load_options, shading_mode)
    preserve_tangents          = _preserve_tangents(load_options)
    total_started_at           = time.perf_counter() if profile_detail else 0.0
    load_started_at            = total_started_at

    primitives, curves, scene_nodes, doc_extra, scene_extra, scene_info, doc_images = _load_assetkit_scene(
        filepath,
        library_path,
        load_options,
    )

    if profile_detail:
        _profile_log(
            "blocking load "
            f"meshes={len(primitives)} curves={len(curves)} nodes={len(scene_nodes)} "
            f"elapsed={_elapsed_ms(load_started_at):.3f}ms"
        )

    destination_collection = collection or bpy.context.collection
    staging_collection     = (
        _new_progressive_staging_collection()
        if len(primitives) >= _PROGRESSIVE_LARGE_SCENE_UNIT_THRESHOLD
        else None
    )
    build_collection       = staging_collection or destination_collection
    scene_started_at       = time.perf_counter() if profile_detail else 0.0

    state                  = _begin_scene_build(
        primitives,
        scene_nodes,
        build_collection,
        doc_extra,
        scene_extra,
        scene_info,
        doc_images,
        curves=curves,
        defer_custom_normals=defer_custom_normals,
        preserve_tangents=preserve_tangents,
        defer_scene_nodes=(
            staging_collection is not None
            and _can_defer_scene_nodes(primitives, curves)
        ),
    )

    if profile_detail:
        _profile_log(
            "blocking begin_scene_build "
            f"nodes={len(scene_nodes)} "
            f"elapsed={_elapsed_ms(scene_started_at):.3f}ms"
        )

    objects: list[bpy.types.Object] = []
    build_started_at               = time.perf_counter() if profile_detail else 0.0
    phase_started_at               = build_started_at
    import_units                   = _mesh_import_units(primitives)
    import_units_ms                = _elapsed_ms(phase_started_at) if profile_detail else 0.0

    phase_started_at = time.perf_counter() if profile_detail else 0.0
    _sort_mesh_import_units_for_blender(import_units)
    sort_units_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

    previous_texture_load_mode         = _textures.ACTIVE_LOAD_MODE
    previous_validated_image_keys      = _textures.ACTIVE_VALIDATED_IMAGE_KEYS
    previous_validated_template_keys   = _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS
    previous_material_template_cloning = _materials.ACTIVE_TEMPLATE_CLONING
    previous_prebuilt_materials        = _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID

    _textures.ACTIVE_LOAD_MODE         = texture_load_mode
    _textures.ACTIVE_VALIDATED_IMAGE_KEYS = set()
    _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS = set()
    _materials.ACTIVE_TEMPLATE_CLONING = (
        len(primitives) <= _MATERIAL_TEMPLATE_CLONE_PRIMITIVE_LIMIT
    )

    try:
        phase_started_at = time.perf_counter() if profile_detail else 0.0
        _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID = _prebuild_material_cache(
            primitives,
            state.material_cache,
            texture_load_mode,
        )
        prebuild_materials_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        objects.extend(_create_curve_objects(curves, state, build_collection))
        curves_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        unit_profile = (
            {
                "group_hit":   [0, 0.0],
                "group_miss":  [0, 0.0],
                "single_hit":  [0, 0.0],
                "single_miss": [0, 0.0],
            }
            if profile_detail
            else None
        )

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        for unit in import_units:
            if profile_detail:
                unit_started_at   = time.perf_counter()
                cache_hits_before = int(state.mesh_cache_hits)

            objects.extend(_create_import_unit(unit, state, build_collection, shading_mode))

            if profile_detail:
                cache_hit = int(state.mesh_cache_hits) != cache_hits_before
                kind      = "group" if isinstance(unit, list) else "single"
                bucket    = unit_profile[f"{kind}_{'hit' if cache_hit else 'miss'}"]

                bucket[0] += 1
                bucket[1] += _elapsed_ms(unit_started_at)

        create_units_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        _finish_deferred_scene_nodes(state, objects)
        finish_nodes_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        _finish_compact_static_instances(state)
        compact_instances_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        _apply_deferred_collection_instances(state)
        collection_instances_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        _apply_deferred_bind_pose_skins(state)
        bind_pose_skins_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

        phase_started_at = time.perf_counter() if profile_detail else 0.0
        if staging_collection is not None:
            _drain_deferred_staging_work()
            _publish_progressive_staging_collection(
                destination_collection,
                staging_collection,
            )
        publish_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0
    finally:
        _textures.ACTIVE_LOAD_MODE                    = previous_texture_load_mode
        _textures.ACTIVE_VALIDATED_IMAGE_KEYS         = previous_validated_image_keys
        _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS     = previous_validated_template_keys
        _materials.ACTIVE_TEMPLATE_CLONING            = previous_material_template_cloning
        _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID = previous_prebuilt_materials

        _reset_material_template_cache()

    if profile_detail:
        _profile_log(
            "blocking build_objects "
            f"objects={len(objects)} primitives={len(primitives)} units={len(import_units)} "
            f"mesh_cache_hits={int(state.mesh_cache_hits)} "
            f"elapsed={_elapsed_ms(build_started_at):.3f}ms"
        )
        _profile_log(
            "blocking build_objects_detail "
            f"import_units={import_units_ms:.3f}ms "
            f"sort_units={sort_units_ms:.3f}ms "
            f"prebuild_materials={prebuild_materials_ms:.3f}ms "
            f"curves={curves_ms:.3f}ms "
            f"create_units={create_units_ms:.3f}ms "
            f"finish_nodes={finish_nodes_ms:.3f}ms "
            f"compact_instances={compact_instances_ms:.3f}ms "
            f"collection_instances={collection_instances_ms:.3f}ms "
            f"bind_pose_skins={bind_pose_skins_ms:.3f}ms "
            f"publish={publish_ms:.3f}ms"
        )
        _profile_log(
            "blocking create_units_detail "
            + " ".join(
                f"{name}_calls={values[0]} {name}={values[1]:.3f}ms"
                for name, values in unit_profile.items()
            )
        )
        _log_material_profile("blocking")

    result            = _import_result_objects(objects, state)
    finish_started_at = time.perf_counter() if profile_detail else 0.0

    _finish_import(
        result,
        focus_mode,
        placement_mode,
        state.root_objects,
        scene_was_empty,
        staging_collection or destination_collection,
        focus_camera,
        select_imported,
        set_viewport_shading,
        clean_viewport_overlays,
        existing_actions,
        existing_frame_range,
        scene_had_timeline_content,
        (
            state.scene_bounds
            if state.compact_instance_plan is not None
            else None
        ),
    )
    if profile_detail:
        _profile_log(
            "blocking finish "
            f"elapsed={_elapsed_ms(finish_started_at):.3f}ms "
            f"total={_elapsed_ms(total_started_at):.3f}ms"
        )

    _animation.ACTIVE_SCOPE = ""
    return result


def _new_progressive_staging_collection() -> bpy.types.Collection:
    staging = bpy.data.collections.new("AssetKit Import")
    staging["assetkit_progressive_staging"] = True
    return staging


def _publish_progressive_staging_collection(
    destination: bpy.types.Collection,
    staging: bpy.types.Collection,
) -> None:
    if destination.children.get(staging.name) is None:
        destination.children.link(staging)
    try:
        del staging["assetkit_progressive_staging"]
    except Exception:
        pass


def import_assetkit_file_progressive(
    filepath: str,
    library_path: str = "",
    load_options: LoadOptions | None = None,
    collection: bpy.types.Collection | None = None,
    batch_size: int = _PROGRESSIVE_BATCH_SIZE,
    time_budget: float = _PROGRESSIVE_TIME_BUDGET,
    focus_mode: str = "NEVER",
    placement_mode: str = "AS_AUTHORED",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    clean_viewport_overlays: bool = True,
    fit_timeline: bool = False,
    on_complete=None,
    on_error=None,
) -> object:
    job = _ProgressiveImportJob(
        filepath,
        library_path,
        load_options,
        collection or bpy.context.collection,
        max(1, int(batch_size)),
        max(0.001, float(time_budget)),
        focus_mode,
        placement_mode,
        scene_was_empty,
        focus_camera,
        select_imported,
        shading_mode,
        set_viewport_shading,
        clean_viewport_overlays,
        fit_timeline,
        on_complete,
        on_error,
    )
    _ACTIVE_IMPORT_JOBS.append(job)
    job.start()
    return job


class _ProgressiveImportJob:
    def __init__(
        self,
        filepath: str,
        library_path: str,
        load_options: LoadOptions | None,
        collection: bpy.types.Collection,
        batch_size: int,
        time_budget: float,
        focus_mode: str,
        placement_mode: str,
        scene_was_empty: bool,
        focus_camera: bpy.types.Object | None,
        select_imported: bool,
        shading_mode: str,
        set_viewport_shading: bool,
        clean_viewport_overlays: bool,
        fit_timeline: bool,
        on_complete,
        on_error,
    ) -> None:
        self.filepath                = filepath
        self.library_path            = library_path
        self.load_options            = _scene_bounds_options(
            _compact_content_key_options(load_options),
            focus_mode,
            placement_mode,
            scene_was_empty,
        )
        self.collection              = collection
        self.batch_size              = batch_size
        self.time_budget             = time_budget
        self.focus_mode              = focus_mode
        self.placement_mode          = placement_mode
        self.scene_was_empty         = scene_was_empty
        self.focus_camera            = focus_camera
        self.select_imported         = select_imported
        self.shading_mode            = str(shading_mode or "AUTO").upper()
        self.set_viewport_shading    = set_viewport_shading
        self.clean_viewport_overlays = clean_viewport_overlays
        self.fit_timeline            = fit_timeline
        self.on_complete             = on_complete
        self.on_error                = on_error

        self.prepared                  = False
        self.build_all_at_once         = False
        self.load_started              = False
        self.done                      = False
        self.failed                    = False
        self.texture_load_mode         = "IMMEDIATE"
        self.material_template_cloning = True
        self.prebuilt_materials        = None
        self.animation_scope           = ""
        self.existing_actions          = None
        self.existing_frame_range      = None
        self.scene_had_timeline_content = False
        self.defer_custom_normals       = False
        self.preserve_tangents           = False

        self.loaded_scene = None
        self.load_error   = None
        self.state        = None

        self.staging_collection: bpy.types.Collection | None = None
        self.import_units                                       = []
        self.unit_index                                         = 0
        self.objects: list[bpy.types.Object]                    = []
        self.started_at                                         = 0.0

    def start(self) -> None:
        bpy.app.timers.register(self._timer, first_interval=0.001)

    def _timer(self) -> float | None:
        previous = self._push_globals()

        try:
            if not self.load_started:
                self._start_load()

                if self.load_error is not None:
                    self._finish_error(self.load_error)
                    return None

                if self.loaded_scene is not None:
                    return 0.0

                return _PROGRESSIVE_LOAD_POLL_INTERVAL

            if self.load_error is not None:
                self._finish_error(self.load_error)
                return None

            if self.loaded_scene is None:
                return _PROGRESSIVE_LOAD_POLL_INTERVAL

            if not self.prepared:
                self._prepare_loaded()
                return 0.0

            self._build_step()

            if self.unit_index < len(self.import_units):
                return 0.0

            self._finish_success()
            return None
        except Exception as exc:
            self._finish_error(exc)
            return None
        finally:
            self._pop_globals(previous)

    def _push_globals(self) -> tuple:
        previous = (
            _textures.ACTIVE_LOAD_MODE,
            _textures.ACTIVE_VALIDATED_IMAGE_KEYS,
            _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS,
            _materials.ACTIVE_TEMPLATE_CLONING,
            _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID,
            _animation.ACTIVE_SCOPE,
        )

        _textures.ACTIVE_LOAD_MODE                    = self.texture_load_mode
        _textures.ACTIVE_VALIDATED_IMAGE_KEYS         = set()
        _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS     = set()
        _materials.ACTIVE_TEMPLATE_CLONING            = self.material_template_cloning
        _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID = self.prebuilt_materials

        if self.animation_scope:
            _animation.ACTIVE_SCOPE = self.animation_scope

        return previous

    def _pop_globals(self, previous: tuple) -> None:
        (
            texture_load_mode,
            validated_image_keys,
            validated_template_keys,
            material_template_cloning,
            prebuilt_materials,
            animation_scope,
        ) = previous

        _textures.ACTIVE_LOAD_MODE                      = texture_load_mode
        _textures.ACTIVE_VALIDATED_IMAGE_KEYS           = validated_image_keys
        _materials.ACTIVE_VALIDATED_TEMPLATE_KEYS       = validated_template_keys
        _materials.ACTIVE_TEMPLATE_CLONING              = material_template_cloning
        _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID   = prebuilt_materials
        _animation.ACTIVE_SCOPE                         = animation_scope

    def _start_load(self) -> None:
        self.started_at = time.perf_counter()

        _reset_action_cache()
        _reset_material_template_cache()
        _reset_material_profile()

        self.animation_scope            = _new_import_animation_scope(self.filepath)
        _animation.ACTIVE_SCOPE         = self.animation_scope
        self.existing_actions           = _snapshot_actions(self.fit_timeline)
        self.existing_frame_range       = _snapshot_scene_frame_range(self.fit_timeline)
        self.scene_had_timeline_content = (
            _scene_has_timeline_content(bpy.context.scene) if self.fit_timeline else False
        )
        self.texture_load_mode           = _texture_load_mode(self.load_options)
        self.defer_custom_normals        = _defer_custom_normals(self.load_options, self.shading_mode)
        self.preserve_tangents            = _preserve_tangents(self.load_options)
        self.load_started                 = True

        if os.path.splitext(self.filepath)[1].lower() in {
            ".dae",
            ".zae",
            ".kmz",
        }:
            # COLLADA parsing is native and short enough to run in this timer
            # callback. Keeping it on the main Blender thread avoids a
            # first-load priority inversion when the Python worker hands the
            # completed scene back through a frequently polled GIL.
            self._load_worker()
        else:
            worker = threading.Thread(
                target=self._load_worker,
                name="AssetKitImportLoad",
                daemon=True,
            )
            worker.start()

    def _load_worker(self) -> None:
        profile_detail  = _profile_state.stats is not None
        load_started_at = time.perf_counter() if profile_detail else 0.0

        try:
            loaded_scene = _load_assetkit_scene(self.filepath, self.library_path, self.load_options)
        except Exception as exc:
            self.load_error = exc
            return

        if profile_detail:
            primitives, curves, scene_nodes, _doc_extra, _scene_extra, _scene_info, _doc_images = loaded_scene
            _profile_log(
                "progressive load "
                f"meshes={len(primitives)} curves={len(curves)} nodes={len(scene_nodes)} "
                f"elapsed={_elapsed_ms(load_started_at):.3f}ms"
            )

        self.loaded_scene = loaded_scene

    def _prepare_loaded(self) -> None:
        if self.loaded_scene is None:
            return

        (
            primitives,
            curves,
            scene_nodes,
            doc_extra,
            scene_extra,
            scene_info,
            doc_images,
        ) = self.loaded_scene

        # Keep progressive construction outside the active scene. Linking every
        # partial batch makes Blender redraw and re-evaluate an increasingly
        # large scene between timer callbacks; collection instances make that
        # cost grow especially quickly. Publish the completed import once.
        self.staging_collection = _new_progressive_staging_collection()
        self.state = _begin_scene_build(
            primitives,
            scene_nodes,
            self.staging_collection,
            doc_extra,
            scene_extra,
            scene_info,
            doc_images,
            curves=curves,
            defer_custom_normals=self.defer_custom_normals,
            preserve_tangents=self.preserve_tangents,
            defer_scene_nodes=(
                len(primitives) >= _PROGRESSIVE_LARGE_SCENE_UNIT_THRESHOLD
                and _can_defer_scene_nodes(primitives, curves)
            ),
        )
        self.import_units = _mesh_import_units(primitives)
        _sort_mesh_import_units_for_blender(self.import_units)

        if len(self.import_units) >= _PROGRESSIVE_LARGE_SCENE_UNIT_THRESHOLD:
            self.build_all_at_once = True

        self.material_template_cloning = len(primitives) <= _MATERIAL_TEMPLATE_CLONE_PRIMITIVE_LIMIT
        self.prebuilt_materials        = None

        _textures.ACTIVE_LOAD_MODE                    = self.texture_load_mode
        _materials.ACTIVE_TEMPLATE_CLONING            = self.material_template_cloning
        _build_common.ACTIVE_PREBUILT_MATERIALS_BY_ID = self.prebuilt_materials

        self.objects.extend(_create_curve_objects(curves, self.state, self.staging_collection))
        self.prepared = True

    @_suspend_gc_during_import_call
    def _build_step(self) -> None:
        if self.state is None:
            return

        started_at = time.perf_counter()
        processed  = 0

        while self.unit_index < len(self.import_units):
            unit = self.import_units[self.unit_index]

            self.objects.extend(
                _create_import_unit(
                    unit,
                    self.state,
                    self.staging_collection or self.collection,
                    self.shading_mode,
                )
            )
            self.unit_index += 1
            processed += 1

            if self.build_all_at_once:
                continue

            if processed >= self.batch_size:
                break

            if time.perf_counter() - started_at >= self.time_budget:
                break

    def _finish_success(self) -> None:
        if self.done:
            return

        self.done = True
        result: list[bpy.types.Object] = []

        if self.state is not None:
            profile_detail  = _profile_state.stats is not None
            phase_started_at = time.perf_counter() if profile_detail else 0.0

            _finish_deferred_scene_nodes(self.state, self.objects)
            node_finish_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

            phase_started_at = time.perf_counter() if profile_detail else 0.0
            _finish_compact_static_instances(self.state)
            _apply_deferred_collection_instances(self.state)
            instances_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

            phase_started_at = time.perf_counter() if profile_detail else 0.0
            _apply_deferred_bind_pose_skins(self.state)
            skins_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

            staging = self.staging_collection
            if staging is not None:
                phase_started_at = time.perf_counter() if profile_detail else 0.0

                if self.build_all_at_once:
                    _drain_deferred_staging_work()

                deferred_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0

                phase_started_at = time.perf_counter() if profile_detail else 0.0
                _publish_progressive_staging_collection(self.collection, staging)
                publish_ms = _elapsed_ms(phase_started_at) if profile_detail else 0.0
            else:
                deferred_ms = 0.0
                publish_ms  = 0.0

            _reset_material_template_cache()

            result           = _import_result_objects(self.objects, self.state)
            phase_started_at = time.perf_counter() if profile_detail else 0.0

            _finish_import(
                result,
                self.focus_mode,
                self.placement_mode,
                self.state.root_objects,
                self.scene_was_empty,
                staging or self.collection,
                self.focus_camera,
                self.select_imported,
                self.set_viewport_shading,
                self.clean_viewport_overlays,
                self.existing_actions,
                self.existing_frame_range,
                self.scene_had_timeline_content,
                (
                    self.state.scene_bounds
                    if self.state.compact_instance_plan is not None
                    else None
                ),
            )
            if profile_detail:
                _profile_log(
                    "progressive_finish_detail "
                    f"scene_nodes={node_finish_ms:.3f}ms "
                    f"instances={instances_ms:.3f}ms skins={skins_ms:.3f}ms "
                    f"deferred={deferred_ms:.3f}ms publish={publish_ms:.3f}ms "
                    f"finish_import={_elapsed_ms(phase_started_at):.3f}ms"
                )

        if _profile_state.stats is not None:
            _profile_log(
                "progressive finish "
                f"objects={len(result)} units={len(self.import_units)} "
                f"elapsed={_elapsed_ms(self.started_at):.3f}ms"
            )
            _log_material_profile("progressive")

        _animation.ACTIVE_SCOPE = ""
        _remove_active_import_job(self)

        if self.on_complete:
            self.on_complete(result)

    def _finish_error(self, exc: Exception) -> None:
        self.failed = True
        self.done   = True

        _reset_material_template_cache()

        _animation.ACTIVE_SCOPE = ""
        _remove_active_import_job(self)

        if self.on_error:
            self.on_error(exc)
        else:
            raise exc


def _remove_active_import_job(job: object) -> None:
    try:
        _ACTIVE_IMPORT_JOBS.remove(job)
    except ValueError:
        pass


def _load_assetkit_scene(
    filepath: str,
    library_path: str = "",
    load_options: LoadOptions | None = None,
) -> tuple[
    list[MeshPrimitiveData],
    list[CurveData],
    list[SceneNodeData],
    object | None,
    object | None,
    dict,
    list[dict],
]:
    loaded = native_load_meshes(filepath, load_options) if not library_path else None
    if loaded is None:
        kit = AssetKit(library_path or None)
        loaded = kit.load_meshes(filepath)

    if isinstance(loaded, AssetKitSceneData):
        return (
            loaded.meshes,
            list(loaded.curves or []),
            loaded.nodes,
            loaded.doc_extra,
            loaded.scene_extra,
            _scene_info_from_loaded(loaded),
            list(loaded.images or []),
        )
    return loaded, [], [], None, None, {}, []


def _scene_bounds_options(
    options: LoadOptions | None,
    focus_mode: str,
    placement_mode: str,
    scene_was_empty: bool,
) -> LoadOptions | None:
    if options is None:
        return None

    focus = str(focus_mode or "NEVER").upper()
    placement = str(placement_mode or "AS_AUTHORED").upper()
    needs_focus_bounds = focus != "NEVER" and (
        focus != "EMPTY_SCENE" or scene_was_empty
    )
    needs_bounds = needs_focus_bounds or placement != "AS_AUTHORED"

    values = list(options)
    if len(values) < AKB_LOAD_OPT_SCENE_BOUNDS:
        return options
    if len(values) == AKB_LOAD_OPT_SCENE_BOUNDS:
        values.append(int(needs_bounds))
    else:
        values[AKB_LOAD_OPT_SCENE_BOUNDS] = int(needs_bounds)
    return tuple(values)


def _load_option_int(load_options: LoadOptions | None, index: int, default: int) -> int:
    if not load_options or index >= len(load_options):
        return default
    return int(load_options[index])


def _texture_load_mode(load_options: LoadOptions | None) -> str:
    mode = _load_option_int(load_options, AKB_LOAD_OPT_TEXTURE_LOADING, AKB_LOAD_TEXTURE_IMMEDIATE)
    if mode == AKB_LOAD_TEXTURE_AUTO:
        return "IMMEDIATE" if bpy.app.background else "DEFERRED"
    if mode == AKB_LOAD_TEXTURE_DEFERRED:
        return "DEFERRED"
    return "IMMEDIATE"


def _defer_custom_normals(load_options: LoadOptions | None, shading_mode: str) -> bool:
    if bpy.app.background or str(shading_mode or "AUTO").upper() != "AUTO":
        return False

    mode = _load_option_int(load_options,
                            AKB_LOAD_OPT_DEFER_CUSTOM_NORMALS,
                            AKB_LOAD_DEFER_NORMALS_AUTO)
    if mode == AKB_LOAD_DEFER_NORMALS_NO:
        return False
    if mode == AKB_LOAD_DEFER_NORMALS_YES:
        return True
    return True


def _preserve_tangents(load_options: LoadOptions | None) -> bool:
    return bool(_load_option_int(load_options, AKB_LOAD_OPT_PRESERVE_TANGENTS, 0))
