from __future__ import annotations

from array import array
from collections import deque
import math
import queue
import threading
import time
import traceback

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

from .assetkit import (
    AssetKit,
    AssetKitSceneData,
    MeshPrimitiveData,
    SceneNodeData,
    TextureRefData,
    native_load_meshes,
    native_open_scene_stream,
)

_ANIM_TRANSLATION = 1
_ANIM_ROTATION_QUAT = 2
_ANIM_SCALE = 3
_ANIM_MORPH_WEIGHTS = 4
_INTERPOLATION_LINEAR = 1
_INTERPOLATION_STEP = 6
_PROGRESSIVE_BATCH_SIZE = 128
_PROGRESSIVE_TIME_BUDGET = 0.025
_AUTO_PROGRESSIVE_MESH_COUNT = 128
_AUTO_PROGRESSIVE_NODE_COUNT = 512
_ACTIVE_IMPORT_JOBS: list["_ProgressiveImportJob"] = []


def import_assetkit_file(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
    collection: bpy.types.Collection | None = None,
    focus_mode: str = "NEVER",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    fit_timeline: bool = False,
) -> list[bpy.types.Object]:
    existing_actions = _snapshot_actions(fit_timeline)
    primitives, scene_nodes = _load_assetkit_scene(filepath, library_path, load_options)
    state = _begin_scene_build(primitives, scene_nodes, collection or bpy.context.collection)
    objects = [
        _create_import_object(primitive, state, collection or bpy.context.collection, shading_mode)
        for primitive in primitives
    ]

    _finish_import(
        objects,
        focus_mode,
        scene_was_empty,
        collection or bpy.context.collection,
        focus_camera,
        select_imported,
        set_viewport_shading,
        existing_actions,
    )
    return objects


def import_assetkit_file_progressive(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
    collection: bpy.types.Collection | None = None,
    batch_size: int = _PROGRESSIVE_BATCH_SIZE,
    focus_mode: str = "NEVER",
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    fit_timeline: bool = False,
) -> "_ProgressiveImportJob":
    job = _ProgressiveImportJob(
        filepath,
        library_path,
        load_options,
        collection or bpy.context.collection,
        max(1, batch_size),
        focus_mode,
        scene_was_empty,
        focus_camera,
        select_imported,
        shading_mode,
        set_viewport_shading,
        _snapshot_actions(fit_timeline),
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
    scene_was_empty: bool = False,
    focus_camera: bpy.types.Object | None = None,
    select_imported: bool = False,
    shading_mode: str = "AUTO",
    set_viewport_shading: bool = True,
    fit_timeline: bool = False,
) -> list[bpy.types.Object] | "_ProgressiveImportJob":
    active_collection = collection or bpy.context.collection
    existing_actions = _snapshot_actions(fit_timeline)
    if library_path:
        return import_assetkit_file(
            filepath,
            library_path,
            load_options,
            active_collection,
            focus_mode,
            scene_was_empty,
            focus_camera,
            select_imported,
            shading_mode,
            set_viewport_shading,
            fit_timeline,
        )

    stream = native_open_scene_stream(filepath, load_options)
    if stream is None:
        return import_assetkit_file(
            filepath,
            library_path,
            load_options,
            active_collection,
            focus_mode,
            scene_was_empty,
            focus_camera,
            select_imported,
            shading_mode,
            set_viewport_shading,
            fit_timeline,
        )

    use_progressive = (
        stream.mesh_count >= _AUTO_PROGRESSIVE_MESH_COUNT
        or len(stream.nodes) >= _AUTO_PROGRESSIVE_NODE_COUNT
    )
    if use_progressive:
        job = _ProgressiveImportJob(
            filepath,
            library_path,
            load_options,
            active_collection,
            max(1, batch_size),
            focus_mode,
            scene_was_empty,
            focus_camera,
            select_imported,
            shading_mode,
            set_viewport_shading,
            existing_actions,
            stream=stream,
        )
        job.start()
        return job

    primitives = stream.read_mesh_batch(0, stream.mesh_count)
    state = _begin_scene_build(primitives, stream.nodes, active_collection)
    objects = [_create_import_object(primitive, state, active_collection, shading_mode) for primitive in primitives]
    _finish_import(
        objects,
        focus_mode,
        scene_was_empty,
        active_collection,
        focus_camera,
        select_imported,
        set_viewport_shading,
        existing_actions,
    )
    return objects


def _load_assetkit_scene(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
) -> tuple[list[MeshPrimitiveData], list[SceneNodeData]]:
    loaded = native_load_meshes(filepath, load_options) if not library_path else None
    if loaded is None:
        kit = AssetKit(library_path or None)
        loaded = kit.load_meshes(filepath)

    if isinstance(loaded, AssetKitSceneData):
        return loaded.meshes, loaded.nodes
    return loaded, []


def _begin_scene_build(
    primitives: list[MeshPrimitiveData],
    scene_nodes: list[SceneNodeData],
    collection: bpy.types.Collection,
) -> dict:
    coord_root = _create_coord_root(primitives, collection)
    node_objects = _create_scene_nodes(scene_nodes, coord_root, collection)
    return {
        "coord_root": coord_root,
        "node_objects": node_objects,
        "node_data": {index: node for index, node in enumerate(scene_nodes)},
        "material_cache": {},
        "skin_cache": {},
    }


def _create_import_object(
    primitive: MeshPrimitiveData,
    state: dict,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> bpy.types.Object:
    node_objects = state["node_objects"]
    node_parent = node_objects.get(primitive.node_index)
    parent = node_parent or state["coord_root"]
    use_node_parent = node_parent is not None
    return _create_mesh_object(
        primitive,
        parent,
        node_objects=node_objects,
        node_data=state["node_data"],
        material_cache=state["material_cache"],
        skin_cache=state["skin_cache"],
        apply_transform=not use_node_parent,
        apply_animation=not use_node_parent,
        shading_mode=shading_mode,
        collection=collection,
    )


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
    scene_was_empty: bool,
    collection: bpy.types.Collection,
    focus_camera: bpy.types.Object | None,
    select_imported: bool,
    set_viewport_shading: bool,
    existing_actions: set[bpy.types.Action] | None,
) -> None:
    if select_imported:
        _select_imported_objects(objects)
    _focus_imported_objects(objects, focus_mode, scene_was_empty, collection, focus_camera)
    if set_viewport_shading:
        _set_viewport_material_preview()
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


def _set_viewport_material_preview() -> None:
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D" or not hasattr(space, "shading"):
                    continue
                try:
                    space.shading.type = "MATERIAL"
                except Exception:
                    pass


def _snapshot_actions(enabled: bool) -> set[bpy.types.Action] | None:
    return set(bpy.data.actions) if enabled else None


def _fit_timeline_to_new_actions(existing_actions: set[bpy.types.Action] | None) -> None:
    if existing_actions is None:
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

    scene = bpy.context.scene
    scene.frame_start = int(math.floor(max(0.0, min_frame)))
    scene.frame_end = max(scene.frame_start + 1, int(math.ceil(max_frame)))


def _action_frame_range(action: bpy.types.Action) -> tuple[float, float] | None:
    min_frame: float | None = None
    max_frame: float | None = None
    fcurves = getattr(action, "fcurves", None)
    if fcurves:
        for fcurve in fcurves:
            for key in fcurve.keyframe_points:
                frame = float(key.co.x)
                min_frame = frame if min_frame is None else min(min_frame, frame)
                max_frame = frame if max_frame is None else max(max_frame, frame)

        if min_frame is not None and max_frame is not None:
            return min_frame, max_frame

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

    return None


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


def _object_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector] | None:
    minimum: Vector | None = None
    maximum: Vector | None = None

    for obj in objects:
        if obj.type != "MESH" or not obj.bound_box:
            continue
        matrix = obj.matrix_world
        for corner in obj.bound_box:
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
    radius = max((maximum - minimum).length * 0.5, 0.5)
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
                    _pad_view_distance(space, radius)
            except Exception:
                pass
    if selection:
        selection.restore()


def _set_viewport_clip(space: bpy.types.SpaceView3D, radius: float) -> None:
    clip_end = max(space.clip_end, radius * 24.0, 1000.0)
    space.clip_end = min(clip_end, 10_000_000.0)
    space.clip_start = min(space.clip_start, max(radius / 100_000.0, 0.001))


def _pad_view_distance(space: bpy.types.SpaceView3D, radius: float) -> None:
    region_3d = getattr(space, "region_3d", None)
    if region_3d is None:
        return
    try:
        target = radius * _viewport_distance_factor(radius)
        current = region_3d.view_distance
        if current <= 0.0:
            region_3d.view_distance = target
        elif current < target:
            region_3d.view_distance = target
        elif current > target * 1.15:
            region_3d.view_distance = target * 1.15
    except Exception:
        pass


def _viewport_distance_factor(radius: float) -> float:
    return 2.4 + 2.8 / (1.0 + radius / 8.0)


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
    radius = max(size.length * 0.5, 0.5)
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
        camera.clip_start = min(camera.clip_start, max(radius / 100_000.0, 0.001))
        camera.clip_end = max(camera.clip_end, radius * 24.0)
        return

    near_depth = max(min(positive_depths) - radius * 4.0, max(radius / 100_000.0, 0.001))
    far_depth = max(positive_depths) + radius * 8.0
    camera.clip_start = min(camera.clip_start, near_depth)
    camera.clip_end = max(camera.clip_end, far_depth, radius * 24.0)


class _ProgressiveImportJob:
    def __init__(
        self,
        filepath: str,
        library_path: str,
        load_options: dict | None,
        collection: bpy.types.Collection,
        batch_size: int,
        focus_mode: str,
        scene_was_empty: bool,
        focus_camera: bpy.types.Object | None,
        select_imported: bool,
        shading_mode: str,
        set_viewport_shading: bool,
        existing_actions: set[bpy.types.Action] | None,
        stream: object | None = None,
    ) -> None:
        self.filepath = filepath
        self.library_path = library_path
        self.load_options = load_options
        self.collection = collection
        self.batch_size = batch_size
        self.focus_mode = focus_mode
        self.scene_was_empty = scene_was_empty
        self.focus_camera = focus_camera
        self.select_imported = select_imported
        self.shading_mode = shading_mode
        self.set_viewport_shading = set_viewport_shading
        self.existing_actions = existing_actions
        self.stream = stream
        self.scene_nodes: list[SceneNodeData] = []
        self.mesh_count = 0
        self.pending_primitives: deque[MeshPrimitiveData] = deque()
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
        self._queue: queue.SimpleQueue[list[MeshPrimitiveData]] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._produce, name="AssetKit progressive import", daemon=True)

    def start(self) -> None:
        self.load_started_at = time.perf_counter()
        _ACTIVE_IMPORT_JOBS.append(self)
        self._thread.start()
        bpy.app.timers.register(self._timer, first_interval=0.001)

    def _produce(self) -> None:
        try:
            if not self.library_path:
                stream = self.stream or native_open_scene_stream(self.filepath, self.load_options)
                if stream is not None:
                    self.scene_nodes = stream.nodes
                    self.mesh_count = stream.mesh_count
                    start = 0
                    producer_batch_size = max(self.batch_size * 4, 256)
                    while start < stream.mesh_count:
                        count = self.batch_size if start == 0 else producer_batch_size
                        batch = stream.read_mesh_batch(start, count)
                        if batch:
                            self._queue.put(batch)
                        start += count
                    return

            primitives, scene_nodes = _load_assetkit_scene(self.filepath, self.library_path, self.load_options)
            self.scene_nodes = scene_nodes
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

        if self.state is None:
            if not self.pending_primitives and not self.producer_done:
                return 0.01
            self.build_started_at = time.perf_counter()
            coord_probe = [self.pending_primitives[0]] if self.pending_primitives else []
            self.state = _begin_scene_build(coord_probe, self.scene_nodes, self.collection)
            self._progress_begin()
            if not self.pending_primitives and self.producer_done:
                self._finish()
                return None

        created_this_step = 0
        slice_started_at = time.perf_counter()
        while self.pending_primitives and created_this_step < self.batch_size:
            obj = _create_import_object(
                self.pending_primitives.popleft(),
                self.state,
                self.collection,
                self.shading_mode,
            )
            self.objects.append(obj)
            self.created_count += 1
            created_this_step += 1
            if self.first_object_at == 0.0:
                self.first_object_at = time.perf_counter()
            if time.perf_counter() - slice_started_at >= _PROGRESSIVE_TIME_BUDGET:
                break

        self._drain_queue()
        if self.producer_done and not self.pending_primitives:
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
            self.pending_primitives.extend(batch)

    def _finish_success(self) -> None:
        _finish_import(
            self.objects,
            self.focus_mode,
            self.scene_was_empty,
            self.collection,
            self.focus_camera,
            self.select_imported,
            self.set_viewport_shading,
            self.existing_actions,
        )
        finished_at = time.perf_counter()
        load_seconds = self.build_started_at - self.load_started_at
        build_seconds = finished_at - self.build_started_at
        first_object_seconds = self.first_object_at - self.load_started_at if self.first_object_at else 0.0
        print(
            "AssetKit progressive import finished: "
            f"{len(self.objects)} mesh object(s), "
            f"first_object={first_object_seconds:.3f}s, "
            f"load={load_seconds:.3f}s, build={build_seconds:.3f}s, total={finished_at - self.load_started_at:.3f}s"
        )
        self._finish()

    def _finish(self) -> None:
        self._progress_end()
        if self in _ACTIVE_IMPORT_JOBS:
            _ACTIVE_IMPORT_JOBS.remove(self)

    def _progress_begin(self) -> None:
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


def _create_mesh_object(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    shading_mode: str = "AUTO",
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    if data.vertices_f32 and data.indices_u32:
        return _create_mesh_object_bulk(
            data,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            material_cache=material_cache,
            skin_cache=skin_cache,
            apply_transform=apply_transform,
            apply_animation=apply_animation,
            shading_mode=shading_mode,
            collection=collection,
        )

    mesh = bpy.data.meshes.new(data.name)
    mesh.from_pydata(data.vertices, [], data.faces)
    mesh.update(calc_edges=True)

    if data.uvs and len(data.uvs) >= len(mesh.loops):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, uv in enumerate(data.uvs[: len(mesh.loops)]):
            uv_layer.data[loop_index].uv = (uv[0], 1.0 - uv[1])

    _apply_shading(mesh, shading_mode, data.normals[: len(mesh.loops)] if data.normals else None)

    active_collection = collection or bpy.context.collection
    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if apply_transform:
        _apply_matrix(obj, data)
    active_collection.objects.link(obj)
    material = _create_material(data, material_cache)
    if material:
        mesh.materials.append(material)
    _apply_material_variants(obj, data)
    _apply_shape_keys(obj, data)
    _apply_skin(obj, data, node_objects or {}, node_data or {}, active_collection, skin_cache)
    if apply_animation:
        _apply_animation(obj, data)

    return obj


def _create_mesh_object_bulk(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    material_cache: dict[object, bpy.types.Material] | None = None,
    skin_cache: dict[object, bpy.types.Object] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
    shading_mode: str = "AUTO",
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(data.name)

    mesh.vertices.add(data.vertex_count)
    mesh.loops.add(data.loop_count)
    mesh.polygons.add(data.face_count)

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")

    if vertices is None or indices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete mesh buffers")
    if loop_starts is None or loop_totals is None:
        loop_starts = array("i", range(0, data.loop_count, 3))
        loop_totals = array("i", [3]) * data.face_count

    mesh.vertices.foreach_set("co", vertices)
    mesh.loops.foreach_set("vertex_index", indices)
    mesh.polygons.foreach_set("loop_start", loop_starts)
    mesh.polygons.foreach_set("loop_total", loop_totals)

    if data.uv_sets:
        for index, attr in enumerate(data.uv_sets):
            uvs = _buffer_view(attr.values_f32, "f")
            uv_layer = mesh.uv_layers.new(name=attr.name or ("UVMap" if index == 0 else f"UVMap.{index:03d}"))
            if uvs is not None:
                uv_layer.data.foreach_set("uv", uvs)
    elif data.uvs_f32:
        uvs = _buffer_view(data.uvs_f32, "f")
        uv_layer = mesh.uv_layers.new(name="UVMap")
        if uvs is not None:
            uv_layer.data.foreach_set("uv", uvs)

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
    elif data.colors_f32:
        colors = _buffer_view(data.colors_f32, "f")
        if colors is not None:
            color_attr = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
            color_attr.data.foreach_set("color", colors)

    if data.tangents_f32:
        tangents = _buffer_view(data.tangents_f32, "f")
        if tangents is not None:
            tangent_attr = mesh.attributes.new(name="assetkit_tangent", type="FLOAT_COLOR", domain="CORNER")
            tangent_attr.data.foreach_set("color", tangents)

    mesh.update(calc_edges=True)

    _apply_shading(mesh, shading_mode, _buffer_view(data.normals_f32, "f") if data.normals_f32 else None)

    active_collection = collection or bpy.context.collection
    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if apply_transform:
        _apply_matrix(obj, data)
    active_collection.objects.link(obj)
    material = _create_material(data, material_cache)
    if material:
        mesh.materials.append(material)
    _apply_material_variants(obj, data)
    _apply_shape_keys(obj, data)
    _apply_skin(obj, data, node_objects or {}, node_data or {}, active_collection, skin_cache)
    if apply_animation:
        _apply_animation(obj, data)

    return obj


def _apply_shading(
    mesh: bpy.types.Mesh,
    mode: str,
    normals: object | None,
) -> None:
    if mode == "FLAT":
        _set_mesh_smooth(mesh, False)
        return
    if mode == "SMOOTH":
        _set_mesh_smooth(mesh, True)
        return

    if not normals:
        _set_mesh_smooth(mesh, False)
        return

    try:
        if isinstance(normals, memoryview):
            mesh.corner_normals.foreach_set("vector", normals)
        else:
            mesh.normals_split_custom_set(normals)
        _set_mesh_smooth(mesh, True)
    except Exception:
        _set_mesh_smooth(mesh, True)


def _set_mesh_smooth(mesh: bpy.types.Mesh, smooth: bool) -> None:
    if not mesh.polygons:
        return

    values = array("b", [1 if smooth else 0]) * len(mesh.polygons)
    try:
        mesh.polygons.foreach_set("use_smooth", values)
    except Exception:
        for poly in mesh.polygons:
            poly.use_smooth = smooth


def _create_scene_nodes(
    nodes: list[SceneNodeData],
    coord_root: bpy.types.Object | None,
    collection: bpy.types.Collection,
) -> dict[int, bpy.types.Object]:
    objects: dict[int, bpy.types.Object] = {}

    for index, node in enumerate(nodes):
        obj = _new_scene_node_object(node, index)
        collection.objects.link(obj)
        objects[index] = obj

    for index, node in enumerate(nodes):
        obj = objects[index]
        parent = objects.get(node.parent_index) if node.parent_index >= 0 else coord_root
        _set_parent(obj, parent)
        _apply_matrix_buffer(obj, node.matrix_f32)
        _apply_animation(obj, node)

    return objects


def _new_scene_node_object(node: SceneNodeData, index: int) -> bpy.types.Object:
    name = node.name or f"AssetKitNode_{index}"

    if node.camera_type:
        camera = bpy.data.cameras.new(node.camera_name or name)
        _configure_camera(camera, node)
        return bpy.data.objects.new(name, camera)

    if node.light_type:
        light = bpy.data.lights.new(node.light_name or name, _blender_light_type(node.light_type))
        _configure_light(light, node)
        return bpy.data.objects.new(name, light)

    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.35
    return obj


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
        return root

    return None


def _set_parent(obj: bpy.types.Object, parent: bpy.types.Object | None) -> None:
    if not parent:
        return

    obj.parent = parent
    obj.matrix_parent_inverse.identity()


def _apply_matrix(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    _apply_matrix_buffer(obj, data.matrix_f32)


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


def _apply_animation(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    channels = data.anim_channels or []
    if not channels:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0

    if any(int(channel.get("target") or 0) == _ANIM_ROTATION_QUAT for channel in channels):
        obj.rotation_mode = "QUATERNION"

    obj.animation_data_create()
    action = bpy.data.actions.new(f"{obj.name}_AssetKit")
    obj.animation_data.action = action
    end_frame = scene.frame_end

    for channel in channels:
        target = int(channel.get("target") or 0)
        path, width = _anim_target_path(target)
        if not path:
            continue

        count = int(channel.get("count") or 0)
        value_width = int(channel.get("value_width") or 0)
        target_offset = int(channel.get("target_offset") or 0)
        is_partial = bool(channel.get("is_partial"))
        times = _buffer_view(channel.get("times_f32") or b"", "f")
        values = _buffer_view(channel.get("values_f32") or b"", "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue

        interpolation = _blender_interpolation(int(channel.get("interpolation") or 0))
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            fcurve = _ensure_fcurve(action, obj, path, target_index)
            coords = array("f", [0.0]) * (count * 2)
            for key_index in range(count):
                coords[key_index * 2] = start_frame + times[key_index] * fps
                coords[key_index * 2 + 1] = values[key_index * value_width + value_index]

            fcurve.keyframe_points.add(count)
            fcurve.keyframe_points.foreach_set("co", coords)
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation
            fcurve.update()

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


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
    action = bpy.data.actions.new(f"{obj.name}_AssetKit_Morph")
    shape_keys.animation_data.action = action

    for channel in channels:
        if int(channel.get("target") or 0) != _ANIM_MORPH_WEIGHTS:
            continue

        count = int(channel.get("count") or 0)
        value_width = int(channel.get("value_width") or 0)
        target_offset = int(channel.get("target_offset") or 0)
        is_partial = bool(channel.get("is_partial"))
        times = _buffer_view(channel.get("times_f32") or b"", "f")
        values = _buffer_view(channel.get("values_f32") or b"", "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue

        interpolation = _blender_interpolation(int(channel.get("interpolation") or 0))
        component_count = 1 if is_partial else value_width
        for component in range(component_count):
            key_index = target_offset + component + 1
            if key_index >= len(shape_keys.key_blocks):
                continue

            key = shape_keys.key_blocks[key_index]
            value_index = 0 if is_partial else component
            fcurve = _ensure_fcurve(action, shape_keys, key.path_from_id("value"), 0, group_name="Shape Keys")
            coords = array("f", [0.0]) * (count * 2)
            for frame_index in range(count):
                coords[frame_index * 2] = start_frame + times[frame_index] * fps
                coords[frame_index * 2 + 1] = values[frame_index * value_width + value_index]

            fcurve.keyframe_points.add(count)
            fcurve.keyframe_points.foreach_set("co", coords)
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation
            fcurve.update()

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _apply_skin(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    collection: bpy.types.Collection,
    skin_cache: dict[object, bpy.types.Object] | None = None,
) -> None:
    if not data.has_skin or data.skin_vertex_count <= 0 or data.skin_joint_count <= 0:
        return

    joints = _buffer_view(data.skin_joints_u16, "H")
    weights = _buffer_view(data.skin_weights_f32, "f")
    joint_nodes = _buffer_view(data.skin_joint_nodes_i32, "i")
    if joints is None or weights is None or joint_nodes is None:
        return

    width = max(1, int(data.skin_joint_width or 4))
    vertex_count = min(data.skin_vertex_count, len(obj.data.vertices))
    joint_names = _create_skin_vertex_groups(obj, data, joints, weights, vertex_count, width, joint_nodes, node_objects)
    cache_key = _skin_cache_key(data, joint_nodes, obj)
    armature = skin_cache.get(cache_key) if skin_cache is not None else None
    if armature is None:
        armature = _create_skin_armature(obj, data, joint_names, joint_nodes, node_objects, node_data, collection)
        if armature and skin_cache is not None:
            skin_cache[cache_key] = armature
    if not armature:
        return

    modifier = obj.modifiers.new("AssetKit Skin", "ARMATURE")
    modifier.object = armature
    modifier.use_vertex_groups = True


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
    groups = []
    for joint_index in range(data.skin_joint_count):
        node_index = int(joint_nodes[joint_index]) if joint_index < len(joint_nodes) else -1
        node = node_objects.get(node_index)
        group = obj.vertex_groups.new(name=node.name if node else f"AssetKitJoint_{joint_index}")
        groups.append(group)

    group_count = len(groups)
    for vertex_index in range(vertex_count):
        base = vertex_index * width
        for slot in range(width):
            weight = weights[base + slot]
            if weight <= 0.0:
                continue
            joint_index = int(joints[base + slot])
            if 0 <= joint_index < group_count:
                groups[joint_index].add((vertex_index,), weight, "REPLACE")

    return [group.name for group in groups]


def _create_skin_armature(
    obj: bpy.types.Object,
    data: MeshPrimitiveData,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    collection: bpy.types.Collection,
) -> bpy.types.Object | None:
    if not joint_names:
        return None

    armature_data = bpy.data.armatures.new(f"{obj.name}_Armature")
    armature = bpy.data.objects.new(f"{obj.name}_Armature", armature_data)
    collection.objects.link(armature)
    _match_object_space(armature, obj)

    previous_active = bpy.context.view_layer.objects.active
    previous_selection = list(bpy.context.selected_objects)
    if previous_active and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = armature_data.edit_bones
    rest_matrices = _joint_rest_matrices(data, joint_nodes, armature)
    positions = (
        [matrix.to_translation() for matrix in rest_matrices]
        if rest_matrices
        else _joint_positions(joint_nodes, node_objects, armature)
    )
    node_to_joint = {
        int(joint_nodes[index]): index
        for index in range(min(len(joint_nodes), len(joint_names)))
        if int(joint_nodes[index]) >= 0
    }

    for index, name in enumerate(joint_names):
        bone = edit_bones.new(name)
        if rest_matrices:
            _set_bone_from_rest_matrix(
                bone,
                rest_matrices[index],
                _joint_length(index, joint_nodes, node_objects, node_to_joint, positions),
            )
        else:
            head = positions[index]
            tail = _joint_tail(index, joint_nodes, node_objects, node_to_joint, positions)
            bone.head = head
            bone.tail = tail

    for index, name in enumerate(joint_names):
        node_index = int(joint_nodes[index]) if index < len(joint_nodes) else -1
        node = node_objects.get(node_index)
        parent = node.parent if node else None
        parent_joint = None
        while parent and parent_joint is None:
            for candidate_node_index, candidate_joint in node_to_joint.items():
                if node_objects.get(candidate_node_index) == parent:
                    parent_joint = candidate_joint
                    break
            parent = parent.parent
        if parent_joint is not None and parent_joint < len(joint_names):
            edit_bones[name].parent = edit_bones[joint_names[parent_joint]]

    bpy.ops.object.mode_set(mode="OBJECT")
    if not _bind_pose_bones_to_nodes(armature, joint_names, joint_nodes, node_objects):
        _apply_bone_animations(armature, joint_names, joint_nodes, node_data)
    _match_object_space(armature, obj)

    bpy.ops.object.select_all(action="DESELECT")
    for selected in previous_selection:
        selected.select_set(True)
    bpy.context.view_layer.objects.active = previous_active
    return armature


def _joint_rest_matrices(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    armature: bpy.types.Object,
) -> list[Matrix]:
    values = _buffer_view(data.skin_inverse_bind_matrices_f32, "f")
    if values is None or len(values) < len(joint_nodes) * 16:
        return []

    coord_matrix = _matrix_from_buffer(data.coord_matrix_f32) or Matrix.Identity(4)
    world_to_armature = armature.matrix_world.inverted_safe()
    matrices = []
    for index in range(len(joint_nodes)):
        inverse_bind = _matrix_from_values(values, index * 16)
        bind_world = coord_matrix @ inverse_bind.inverted_safe()
        matrices.append(world_to_armature @ bind_world)
    return matrices


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


def _bind_pose_bones_to_nodes(
    armature: bpy.types.Object,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
) -> bool:
    bound_any = False
    for index, name in enumerate(joint_names):
        pose_bone = armature.pose.bones.get(name)
        node = node_objects.get(int(joint_nodes[index]) if index < len(joint_nodes) else -1)
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
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _joint_positions(
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    armature: bpy.types.Object,
) -> list[Vector]:
    positions = []
    world_to_armature = armature.matrix_world.inverted_safe()
    for index in range(len(joint_nodes)):
        node = node_objects.get(int(joint_nodes[index]))
        if node:
            positions.append(world_to_armature @ node.matrix_world.to_translation())
        else:
            positions.append(Vector((0.0, float(index) * 0.05, 0.0)))
    return positions


def _joint_length(
    joint_index: int,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_to_joint: dict[int, int],
    positions: list[Vector],
) -> float:
    head = positions[joint_index]
    node = node_objects.get(int(joint_nodes[joint_index])) if joint_index < len(joint_nodes) else None
    if node:
        length: float | None = None
        for child_node_index, child_joint_index in node_to_joint.items():
            child = node_objects.get(child_node_index)
            if child and child.parent == node and child_joint_index < len(positions):
                child_length = (positions[child_joint_index] - head).length
                if child_length > 1.0e-5:
                    length = child_length if length is None else min(length, child_length)
        if length is not None:
            return length
    return 0.05


def _joint_tail(
    joint_index: int,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_to_joint: dict[int, int],
    positions: list[Vector],
) -> Vector:
    node = node_objects.get(int(joint_nodes[joint_index])) if joint_index < len(joint_nodes) else None
    if node:
        for child_node_index, child_joint_index in node_to_joint.items():
            child = node_objects.get(child_node_index)
            if child and child.parent == node and child_joint_index < len(positions):
                tail = positions[child_joint_index]
                if (tail - positions[joint_index]).length > 1.0e-5:
                    return tail
    return positions[joint_index] + Vector((0.0, 0.05, 0.0))


def _apply_bone_animations(
    armature: bpy.types.Object,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
) -> None:
    animated = False
    for index, name in enumerate(joint_names):
        pose_bone = armature.pose.bones.get(name)
        if pose_bone:
            pose_bone.rotation_mode = "QUATERNION"
        node = node_data.get(int(joint_nodes[index]) if index < len(joint_nodes) else -1)
        if node and node.anim_channels:
            animated = True

    if not animated:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    action = bpy.data.actions.new(f"{armature.name}_AssetKit")
    armature.animation_data_create()
    armature.animation_data.action = action
    end_frame = scene.frame_end

    for index, name in enumerate(joint_names):
        pose_bone = armature.pose.bones.get(name)
        node = node_data.get(int(joint_nodes[index]) if index < len(joint_nodes) else -1)
        if not pose_bone or not node or not node.anim_channels:
            continue

        for channel in node.anim_channels:
            target = int(channel.get("target") or 0)
            path, width = _anim_target_path(target)
            if not path:
                continue

            count = int(channel.get("count") or 0)
            value_width = int(channel.get("value_width") or 0)
            target_offset = int(channel.get("target_offset") or 0)
            is_partial = bool(channel.get("is_partial"))
            times = _buffer_view(channel.get("times_f32") or b"", "f")
            values = _buffer_view(channel.get("values_f32") or b"", "f")
            if count <= 0 or value_width <= 0 or times is None or values is None:
                continue

            interpolation = _blender_interpolation(int(channel.get("interpolation") or 0))
            component_count = 1 if is_partial else min(width - target_offset, value_width)
            data_path = pose_bone.path_from_id(path)
            for component in range(component_count):
                target_index = target_offset + component
                value_index = 0 if is_partial else component
                fcurve = _ensure_fcurve(action, armature, data_path, target_index, group_name=name)
                coords = array("f", [0.0]) * (count * 2)
                for key_index in range(count):
                    coords[key_index * 2] = times[key_index] * fps
                    coords[key_index * 2 + 1] = values[key_index * value_width + value_index]

                fcurve.keyframe_points.add(count)
                fcurve.keyframe_points.foreach_set("co", coords)
                for point in fcurve.keyframe_points:
                    point.interpolation = interpolation
                fcurve.update()

            end_frame = max(end_frame, int(times[count - 1] * fps + 0.5))

    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _ensure_fcurve(
    action: bpy.types.Action,
    obj: bpy.types.ID,
    data_path: str,
    index: int,
    group_name: str = "Transform",
):
    ensure = getattr(action, "fcurve_ensure_for_datablock", None)
    if ensure:
        return ensure(obj, data_path, index=index, group_name=group_name)
    return action.fcurves.new(data_path=data_path, index=index, action_group=group_name)


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
    if interpolation == _INTERPOLATION_LINEAR:
        return "LINEAR"
    return "LINEAR"


def _apply_material_variants(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    variants = data.material_variants or []
    if not variants:
        return

    obj["assetkit_material_variant_count"] = len(variants)
    for index, variant in enumerate(variants):
        prefix = f"assetkit_material_variant_{index}"
        obj[f"{prefix}_index"] = int(variant.get("variant_index") or 0)
        obj[f"{prefix}_name"] = variant.get("variant_name") or ""
        obj[f"{prefix}_material"] = variant.get("material_name") or ""


def _create_material(
    data: MeshPrimitiveData,
    material_cache: dict[object, bpy.types.Material] | None = None,
) -> bpy.types.Material | None:
    if not _has_material_data(data):
        return None

    cache_key = _material_cache_key(data)
    if material_cache is not None and cache_key in material_cache:
        return material_cache[cache_key]

    material_name = data.material_name or f"{data.name}_Material"
    mat = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    mat.use_nodes = True
    mat.use_backface_culling = not data.double_sided
    if data.alpha_mode == 1:
        mat.blend_method = "BLEND"
    elif data.alpha_mode == 2:
        mat.blend_method = "CLIP"
        mat.alpha_threshold = data.alpha_cutoff

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        if material_cache is not None:
            material_cache[cache_key] = mat
        return mat

    _set_input(bsdf, "Base Color", data.base_color)
    _set_input(bsdf, "Metallic", data.metallic)
    _set_input(bsdf, "Roughness", data.roughness)
    _set_input(bsdf, "Alpha", data.opacity)
    _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))
    _set_first_input(bsdf, ("Specular IOR Level", "Specular"), data.specular_strength)
    _set_first_input(bsdf, ("Specular Tint",), (*data.specular_color, 1.0))
    _set_first_input(bsdf, ("IOR",), data.ior)
    _set_first_input(bsdf, ("Coat Weight", "Clearcoat"), data.clearcoat)
    _set_first_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), data.clearcoat_roughness)
    _set_first_input(bsdf, ("Transmission Weight", "Transmission"), data.transmission)
    _set_first_input(bsdf, ("Sheen Weight", "Sheen"), max(data.sheen_color))
    _set_first_input(bsdf, ("Sheen Tint",), (*data.sheen_color, 1.0))
    _set_first_input(bsdf, ("Sheen Roughness",), data.sheen_roughness)
    _set_first_input(bsdf, ("Anisotropic",), data.anisotropy)
    _set_first_input(bsdf, ("Anisotropic Rotation",), data.anisotropy_rotation)
    _set_first_input(bsdf, ("Thin Film IOR",), data.iridescence_ior)
    if data.iridescence or data.iridescence_thickness_texture:
        _set_first_input(bsdf, ("Thin Film Thickness",), data.iridescence_thickness_maximum)

    _set_assetkit_material_props(mat, data)

    if data.base_color_texture:
        _link_base_color_texture(mat, bsdf, data)
    if data.metallic_roughness_texture:
        _link_metallic_roughness_texture(
            mat,
            bsdf,
            data.metallic_roughness_texture,
            _texture_info(data, "metallic_roughness"),
        )
    if data.occlusion_texture:
        _link_image_first(
            mat,
            bsdf,
            data.occlusion_texture,
            ("Ambient Occlusion", "Occlusion"),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "occlusion"),
        )
    if data.normal_texture:
        _link_normal_texture(mat, bsdf, data.normal_texture, data.normal_scale, _texture_info(data, "normal"))
    if data.emissive_texture:
        _link_image(
            mat,
            bsdf,
            data.emissive_texture,
            "Emission Color",
            colorspace="sRGB",
            tex_info=_texture_info(data, "emissive"),
        )
    if data.transparent_texture:
        _link_alpha_texture(mat, bsdf, data.transparent_texture, _texture_info(data, "transparent"))
    if data.specular_texture:
        _link_image_first(
            mat,
            bsdf,
            data.specular_texture,
            ("Specular IOR Level", "Specular"),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "specular"),
        )
    if data.specular_color_texture:
        _link_image_first(
            mat,
            bsdf,
            data.specular_color_texture,
            ("Specular Tint",),
            colorspace="sRGB",
            tex_info=_texture_info(data, "specular_color"),
        )
    if data.clearcoat_texture:
        _link_image_first(
            mat,
            bsdf,
            data.clearcoat_texture,
            ("Coat Weight", "Clearcoat"),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "clearcoat"),
        )
    if data.clearcoat_roughness_texture:
        _link_image_first(
            mat,
            bsdf,
            data.clearcoat_roughness_texture,
            ("Coat Roughness", "Clearcoat Roughness"),
            colorspace="Non-Color",
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
        _link_image_first(
            mat,
            bsdf,
            data.transmission_texture,
            ("Transmission Weight", "Transmission"),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "transmission"),
        )
    if data.sheen_color_texture:
        _link_image_first(
            mat,
            bsdf,
            data.sheen_color_texture,
            ("Sheen Tint",),
            colorspace="sRGB",
            tex_info=_texture_info(data, "sheen_color"),
        )
    if data.sheen_roughness_texture:
        _link_image_first(
            mat,
            bsdf,
            data.sheen_roughness_texture,
            ("Sheen Roughness",),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "sheen_roughness"),
        )
    if data.iridescence_thickness_texture:
        _link_image_first(
            mat,
            bsdf,
            data.iridescence_thickness_texture,
            ("Thin Film Thickness",),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "iridescence_thickness"),
        )
    if data.anisotropy_texture:
        _link_image_first(
            mat,
            bsdf,
            data.anisotropy_texture,
            ("Anisotropic",),
            colorspace="Non-Color",
            tex_info=_texture_info(data, "anisotropy"),
        )

    if material_cache is not None:
        material_cache[cache_key] = mat
    return mat


def _has_material_data(data: MeshPrimitiveData) -> bool:
    if data.material_name:
        return True
    return _material_cache_key(data) != _default_material_cache_key()


def _material_cache_key(data: MeshPrimitiveData) -> object:
    if data.material_name:
        return ("name", data.material_name)
    return (
        "props",
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
        bool(data.double_sided),
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
    )


def _default_material_cache_key() -> object:
    return (
        "props",
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
        1000000.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        False,
        *(("",) * 19),
    )


def _round_tuple(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(float(value), 6) for value in values)


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
        "assetkit_iridescence_texture": data.iridescence_texture,
        "assetkit_iridescence_thickness_texture": data.iridescence_thickness_texture,
        "assetkit_volume_thickness_texture": data.volume_thickness_texture,
        "assetkit_anisotropy_texture": data.anisotropy_texture,
        "assetkit_diffuse_transmission_texture": data.diffuse_transmission_texture,
        "assetkit_transparent_texture": data.transparent_texture,
    }
    for key, value in props.items():
        if value == "" or value == 0.0:
            continue
        mat[key] = value

    for role, info in (data.texture_infos or {}).items():
        prefix = f"assetkit_texture_{role}"
        mat[f"{prefix}_slot"] = info.slot
        if info.texcoord:
            mat[f"{prefix}_texcoord"] = info.texcoord
        if info.coord_input_name:
            mat[f"{prefix}_coord_input_name"] = info.coord_input_name
        mat[f"{prefix}_wrap_s"] = info.wrap_s
        mat[f"{prefix}_wrap_t"] = info.wrap_t
        mat[f"{prefix}_min_filter"] = info.min_filter
        mat[f"{prefix}_mag_filter"] = info.mag_filter
        if info.has_transform:
            mat[f"{prefix}_transform_offset"] = info.transform_offset
            mat[f"{prefix}_transform_scale"] = info.transform_scale
            mat[f"{prefix}_transform_rotation"] = info.transform_rotation


def _texture_info(data: MeshPrimitiveData, role: str) -> TextureRefData | None:
    return (data.texture_infos or {}).get(role)


def _set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket:
        try:
            socket.default_value = value
        except TypeError:
            pass


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


def _link_base_color_texture(mat: bpy.types.Material, bsdf, data: MeshPrimitiveData) -> None:
    tex = _image_texture_node(mat, data.base_color_texture, "sRGB", _texture_info(data, "base_color"))
    if not tex:
        return

    links = mat.node_tree.links
    base_color = bsdf.inputs.get("Base Color")
    alpha = bsdf.inputs.get("Alpha")
    if base_color:
        links.new(tex.outputs["Color"], base_color)
    if data.alpha_mode and alpha and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], alpha)


def _link_alpha_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    tex_info: TextureRefData | None = None,
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color", tex_info)
    if not tex:
        return

    alpha = bsdf.inputs.get("Alpha")
    if not alpha:
        return

    output = tex.outputs.get("Alpha") or tex.outputs.get("Color")
    if output:
        mat.node_tree.links.new(output, alpha)


def _link_metallic_roughness_texture(
    mat: bpy.types.Material,
    bsdf,
    path: str,
    tex_info: TextureRefData | None = None,
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
        links.new(separate.outputs["Green"], roughness)
    if metallic:
        links.new(separate.outputs["Blue"], metallic)


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
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None

    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass

    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    _configure_texture_node(mat, tex, tex_info)
    return tex


def _configure_texture_node(mat: bpy.types.Material, tex, tex_info: TextureRefData | None) -> None:
    if not tex_info:
        return

    tex.extension = _texture_extension(tex_info)
    tex.interpolation = _texture_interpolation(tex_info)

    needs_uv_node = tex_info.slot > 0 or tex_info.has_transform
    if not needs_uv_node:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = _uv_layer_name(tex_info.slot)
    vector_output = uv.outputs.get("UV")

    if tex_info.has_transform:
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Location"].default_value[0] = tex_info.transform_offset[0]
        mapping.inputs["Location"].default_value[1] = tex_info.transform_offset[1]
        mapping.inputs["Rotation"].default_value[2] = tex_info.transform_rotation
        mapping.inputs["Scale"].default_value[0] = tex_info.transform_scale[0]
        mapping.inputs["Scale"].default_value[1] = tex_info.transform_scale[1]
        if vector_output:
            links.new(vector_output, mapping.inputs["Vector"])
        vector_output = mapping.outputs.get("Vector")

    if vector_output:
        links.new(vector_output, tex.inputs["Vector"])


def _uv_layer_name(slot: int) -> str:
    return "UVMap" if slot <= 0 else f"UVMap.{slot:03d}"


def _texture_extension(tex_info: TextureRefData) -> str:
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


def _texture_interpolation(tex_info: TextureRefData) -> str:
    if tex_info.mag_filter == 1 or tex_info.min_filter == 1:
        return "Closest"
    return "Linear"
