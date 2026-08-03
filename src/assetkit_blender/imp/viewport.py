from __future__ import annotations

import math

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


_DEFAULT_LINE_PREVIEW_COLOR = (0.08, 0.08, 0.08, 1.0)


def select_imported_objects(objects: list[bpy.types.Object]) -> None:
    if not objects:
        return

    selection = import_selection_objects(objects)
    clear_selection()
    for obj in selection:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = selection[-1]


def import_selection_objects(
    objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    selection: list[bpy.types.Object] = []
    seen: set[int] = set()
    animated: list[bpy.types.Object] = []
    animated_seen: set[int] = set()

    def append(obj: bpy.types.Object | None) -> None:
        if obj is None or obj.name not in bpy.data.objects:
            return
        key = obj.as_pointer()
        if key in seen:
            return
        seen.add(key)
        selection.append(obj)

    def mark_animated(obj: bpy.types.Object | None) -> None:
        if obj is None or obj.name not in bpy.data.objects:
            return
        anim_data = getattr(obj, "animation_data", None)
        if anim_data is None or getattr(anim_data, "action", None) is None:
            return
        key = obj.as_pointer()
        if key in animated_seen:
            return
        animated_seen.add(key)
        animated.append(obj)

    for obj in objects:
        append(obj)
        mark_animated(obj)

        parent = obj.parent
        while parent is not None:
            mark_animated(parent)
            parent = parent.parent

        for modifier in getattr(obj, "modifiers", ()) or ():
            if getattr(modifier, "type", "") == "ARMATURE":
                mark_animated(getattr(modifier, "object", None))

    for obj in animated:
        append(obj)

    return selection or objects


def clear_selection() -> None:
    try:
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action="DESELECT")
            return
    except Exception:
        pass

    for obj in bpy.context.scene.objects:
        obj.select_set(False)


class SelectionState:
    __slots__ = ("active", "selected")

    def __init__(self) -> None:
        self.selected = list(bpy.context.selected_objects)
        self.active   = bpy.context.view_layer.objects.active

    def restore(self) -> None:
        clear_selection()
        for obj in self.selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if self.active and self.active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = self.active


def temporary_selection(objects: list[bpy.types.Object]) -> SelectionState:
    selection = SelectionState()
    select_imported_objects(objects)
    return selection


def set_viewport_material_preview(clean_overlays: bool = False) -> None:
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D" or not hasattr(space, "shading"):
                    continue
                try:
                    _set_material_preview_shading(space.shading)
                    _set_line_preview_shading(space.shading)
                    if not clean_overlays:
                        continue
                    overlay = getattr(space, "overlay", None)
                    if overlay:
                        _clean_viewport_overlay(overlay)
                except Exception:
                    pass


def _set_material_preview_shading(shading: object) -> None:
    was_material_preview = shading.type == "MATERIAL"
    shading.color_type = "MATERIAL"
    shading.type       = "MATERIAL"
    if was_material_preview:
        return

    # Blender's default material-preview light follows the view. That is
    # convenient while sculpting, but it can make orthogonal faces keep nearly
    # identical lighting while orbiting an imported asset. Keep the studio
    # light in world space so authored normals remain visually meaningful,
    # without replacing a Material Preview setup the user already chose.
    if hasattr(shading, "use_studiolight_view_rotation"):
        shading.use_studiolight_view_rotation = False
    if hasattr(shading, "show_shadows"):
        shading.show_shadows = True


def _set_line_preview_shading(shading: object) -> None:
    if hasattr(shading, "wireframe_color_type"):
        shading.wireframe_color_type = "OBJECT"


def set_line_preview_color(
    obj: bpy.types.Object,
    material: bpy.types.Material | None,
) -> None:
    color = (
        material.diffuse_color
        if material is not None
        else _DEFAULT_LINE_PREVIEW_COLOR
    )
    try:
        # Both RNA properties use Blender's linear color subtype. Assign the
        # four-component view directly: no gamma work or per-edge conversion.
        obj.color = color
    except (AttributeError, TypeError, ValueError):
        obj.color = _DEFAULT_LINE_PREVIEW_COLOR


def _clean_viewport_overlay(overlay: object) -> None:
    if hasattr(overlay, "show_wireframes"):
        overlay.show_wireframes = False
    if hasattr(overlay, "wireframe_opacity"):
        # Polygon wireframes stay hidden, while loose edges remain visible in
        # the owning object's line-material color selected above.
        overlay.wireframe_opacity = 1.0
    if hasattr(overlay, "show_relationship_lines"):
        overlay.show_relationship_lines = False


def focus_imported_objects(
    objects: list[bpy.types.Object],
    focus_mode: str,
    scene_was_empty: bool,
    collection: bpy.types.Collection,
    focus_camera: bpy.types.Object | None,
    authored_bounds: tuple[Vector, Vector] | None = None,
) -> None:
    if focus_mode == "NEVER":
        return
    if focus_mode == "EMPTY_SCENE" and not scene_was_empty:
        return
    if not objects:
        return

    bounds = authored_bounds
    if bounds is None:
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        bounds = object_bounds(objects)
    if bounds is None:
        return

    frame_viewports(bounds, objects)
    if scene_was_empty and focus_camera is not None:
        frame_camera(bounds, collection, focus_camera)


def apply_import_placement(
    objects: list[bpy.types.Object],
    placement_mode: str,
    root_objects: list[bpy.types.Object] | None = None,
    authored_bounds: tuple[Vector, Vector] | None = None,
) -> tuple[Vector, Vector] | None:
    if placement_mode == "AS_AUTHORED" or not objects:
        return authored_bounds

    bounds = authored_bounds
    if bounds is None:
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        bounds = object_bounds(objects)
    if bounds is None:
        return None

    minimum, maximum = bounds
    center           = (minimum + maximum) * 0.5
    cursor           = bpy.context.scene.cursor.location
    if placement_mode == "ORIGIN_GROUND":
        target = Vector((0.0, 0.0, 0.0))
    elif placement_mode == "CURSOR_GROUND":
        target = Vector((cursor.x, cursor.y, cursor.z))
    else:
        return bounds

    offset = Vector(
        (
            target.x - center.x,
            target.y - center.y,
            target.z - minimum.z,
        )
    )
    if offset.length <= 1e-9:
        return bounds

    for root in placement_roots(objects, root_objects or []):
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
    return minimum + offset, maximum + offset


def scene_bounds_from_info(
    scene_info: dict | None,
) -> tuple[Vector, Vector] | None:
    value = (scene_info or {}).get("bounds")
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        minimum_values = tuple(float(component) for component in value[0])
        maximum_values = tuple(float(component) for component in value[1])
    except (TypeError, ValueError):
        return None
    if len(minimum_values) != 3 or len(maximum_values) != 3:
        return None
    if not all(
        math.isfinite(component)
        for component in (*minimum_values, *maximum_values)
    ):
        return None
    if any(
        minimum_values[axis] > maximum_values[axis]
        for axis in range(3)
    ):
        return None
    return Vector(minimum_values), Vector(maximum_values)


def placement_roots(
    objects: list[bpy.types.Object],
    root_objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    roots = [
        obj
        for obj in root_objects
        if obj and obj.name in bpy.data.objects
    ]
    if roots:
        return unique_objects(roots)

    object_set = set(objects)
    roots      = []
    for obj in objects:
        root = obj
        while root.parent and root.parent in object_set:
            root = root.parent
        roots.append(root)
    return unique_objects(roots)


def unique_objects(
    objects: list[bpy.types.Object],
) -> list[bpy.types.Object]:
    seen   = set()
    unique = []
    for obj in objects:
        key = obj.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        unique.append(obj)
    return unique


def object_bounds(
    objects: list[bpy.types.Object],
) -> tuple[Vector, Vector] | None:
    minimum: Vector | None = None
    maximum: Vector | None = None

    def extend_corners(corners, matrix) -> None:
        nonlocal minimum, maximum
        for corner in corners:
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

    collection_cache: dict[int, tuple[Vector, Vector] | None] = {}
    collection_stack: set[int] = set()
    compact_batch_pointers = {
        obj.as_pointer()
        for obj in objects
        if obj.get("assetkit_compact_instance_batch")
    }

    def collection_bounds(
        collection: bpy.types.Collection,
    ) -> tuple[Vector, Vector] | None:
        key = collection.as_pointer()
        if key in collection_cache:
            return collection_cache[key]
        if key in collection_stack:
            return None
        collection_stack.add(key)
        local_minimum: Vector | None = None
        local_maximum: Vector | None = None

        def extend_local(corners, matrix) -> None:
            nonlocal local_minimum, local_maximum
            for corner in corners:
                point = matrix @ Vector(corner)
                if local_minimum is None:
                    local_minimum = point.copy()
                    local_maximum = point.copy()
                else:
                    local_minimum.x = min(local_minimum.x, point.x)
                    local_minimum.y = min(local_minimum.y, point.y)
                    local_minimum.z = min(local_minimum.z, point.z)
                    local_maximum.x = max(local_maximum.x, point.x)
                    local_maximum.y = max(local_maximum.y, point.y)
                    local_maximum.z = max(local_maximum.z, point.z)

        for obj in collection.objects:
            if is_hidden_for_bounds(obj):
                continue
            if obj.type == "MESH" and obj.bound_box:
                extend_local(obj.bound_box, obj.matrix_world)
            target = getattr(obj, "instance_collection", None)
            if (
                getattr(obj, "instance_type", "NONE") == "COLLECTION"
                and target is not None
            ):
                nested = collection_bounds(target)
                if nested is not None:
                    extend_local(bounds_corners(nested), obj.matrix_world)

        collection_stack.remove(key)
        result = (
            (local_minimum, local_maximum)
            if local_minimum is not None and local_maximum is not None
            else None
        )
        collection_cache[key] = result
        return result

    for obj in objects:
        if is_hidden_for_bounds(obj):
            continue
        if (
            obj.type == "MESH"
            and obj.bound_box
            and not obj.get("assetkit_compact_instance_batch")
        ):
            extend_corners(obj.bound_box, obj.matrix_world)
        target = getattr(obj, "instance_collection", None)
        if (
            getattr(obj, "instance_type", "NONE") == "COLLECTION"
            and target is not None
        ):
            nested = collection_bounds(target)
            if nested is not None:
                extend_corners(bounds_corners(nested), obj.matrix_world)

    if compact_batch_pointers:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for instance in depsgraph.object_instances:
            parent = instance.parent
            if parent is None:
                continue
            original_parent = parent.original
            if original_parent.as_pointer() not in compact_batch_pointers:
                continue
            evaluated = instance.object
            if (
                evaluated.type != "MESH"
                or evaluated.data is None
                or len(evaluated.data.polygons) == 0
                or not evaluated.bound_box
            ):
                continue
            extend_corners(evaluated.bound_box, instance.matrix_world)

    if minimum is None or maximum is None:
        return None
    return minimum, maximum


def is_hidden_for_bounds(obj: bpy.types.Object) -> bool:
    current = obj
    while current is not None:
        helper_hidden = bool(current.get("assetkit_helper_hidden"))
        try:
            if current.hide_get() and not helper_hidden:
                return True
        except Exception:
            pass
        if (
            (current.hide_viewport or current.hide_render)
            and not helper_hidden
        ):
            return True
        current = current.parent
    return False


def bounds_corners(
    bounds: tuple[Vector, Vector],
) -> list[Vector]:
    minimum, maximum = bounds
    return [
        Vector((x, y, z))
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]


def frame_viewports(
    bounds: tuple[Vector, Vector],
    objects: list[bpy.types.Object] | None = None,
) -> None:
    del objects
    window_manager   = bpy.context.window_manager
    minimum, maximum = bounds
    radius           = max((maximum - minimum).length * 0.5, 1.0e-6)
    for window in getattr(window_manager, "windows", []):
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = next(
                (
                    item
                    for item in area.spaces
                    if item.type == "VIEW_3D"
                ),
                None,
            )
            if space is None:
                continue
            set_viewport_clip(space, radius)
            set_view_distance(space, bounds, radius)


def set_viewport_clip(
    space: bpy.types.SpaceView3D,
    radius: float,
) -> None:
    space.clip_start = clip_start_for_radius(radius)
    space.clip_end   = clip_end_for_radius(radius)


def set_view_distance(
    space: bpy.types.SpaceView3D,
    bounds: tuple[Vector, Vector],
    radius: float,
) -> None:
    region_3d = getattr(space, "region_3d", None)
    if region_3d is None:
        return
    try:
        minimum, maximum        = bounds
        region_3d.view_location = (minimum + maximum) * 0.5
        target                  = radius * viewport_distance_factor(radius)
        # A focus request is an explicit framing operation. Reusing a previous
        # view distance within a broad tolerance made the same asset open at
        # different zoom levels depending on the user's last manual dolly.
        region_3d.view_distance = target
    except Exception:
        pass


def viewport_distance_factor(radius: float) -> float:
    return 1.9 + 2.0 / (1.0 + radius / 8.0)


def frame_camera(
    bounds: tuple[Vector, Vector],
    collection: bpy.types.Collection,
    camera_obj: bpy.types.Object | None,
) -> None:
    del collection
    scene = bpy.context.scene
    if camera_obj is None:
        return
    if scene.camera is None:
        scene.camera = camera_obj

    minimum, maximum = bounds
    center           = (minimum + maximum) * 0.5
    size             = maximum - minimum
    radius           = max(size.length * 0.5, 1.0e-6)
    direction        = Vector((1.6, -2.2, 1.25)).normalized()

    camera                    = camera_obj.data
    camera_obj.rotation_euler = (
        center - (center + direction)
    ).to_track_quat("-Z", "Y").to_euler()
    if camera.type == "ORTHO":
        camera.ortho_scale = max(
            size.x,
            size.y,
            size.z,
            1.0,
        ) * 1.35
        distance            = radius * 3.0
        camera_obj.location = center + direction * distance
    else:
        distance = camera_fit_distance(
            camera,
            direction,
            center,
            bounds_corners(bounds),
        ) * 1.25
        camera_obj.location = center + direction * distance
    fit_camera_with_blender(camera_obj, bounds)
    ensure_camera_contains_bounds(scene, camera_obj, bounds)
    set_camera_clip(camera_obj, bounds, radius)


def fit_camera_with_blender(
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
) -> None:
    if not hasattr(camera_obj, "camera_fit_coords"):
        return

    coords: list[float] = []
    for corner in bounds_corners(bounds):
        coords.extend((corner.x, corner.y, corner.z))

    try:
        location, scale = camera_obj.camera_fit_coords(
            bpy.context.evaluated_depsgraph_get(),
            coords,
        )
    except Exception:
        return

    camera_obj.location = location
    if camera_obj.data.type == "ORTHO" and scale > 0.0:
        camera_obj.data.ortho_scale = scale * 1.15


def camera_fit_distance(
    camera: bpy.types.Camera,
    direction: Vector,
    center: Vector,
    corners: list[Vector],
) -> float:
    rotation     = (-direction).to_track_quat("-Z", "Y").to_matrix().inverted()
    half_angle_x = max(
        getattr(camera, "angle_x", camera.angle) * 0.5,
        math.radians(5.0),
    )
    half_angle_y = max(
        getattr(camera, "angle_y", camera.angle) * 0.5,
        math.radians(5.0),
    )
    tan_x    = max(math.tan(half_angle_x), 0.01)
    tan_y    = max(math.tan(half_angle_y), 0.01)
    distance = 0.5

    for corner in corners:
        local    = rotation @ (corner - center)
        distance = max(
            distance,
            local.z + abs(local.x) / tan_x,
            local.z + abs(local.y) / tan_y,
        )

    return max(distance, 0.5)


def ensure_camera_contains_bounds(
    scene: bpy.types.Scene,
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
) -> None:
    camera  = camera_obj.data
    corners = bounds_corners(bounds)
    margin  = 0.06

    for _ in range(8):
        try:
            bpy.context.view_layer.update()
            projected = [
                world_to_camera_view(scene, camera_obj, corner)
                for corner in corners
            ]
        except Exception:
            return

        if all(
            margin <= point.x <= 1.0 - margin
            and margin <= point.y <= 1.0 - margin
            and point.z > 0.0
            for point in projected
        ):
            return

        if camera.type == "ORTHO":
            camera.ortho_scale *= 1.2
        else:
            target = sum(corners, Vector()) / len(corners)
            offset = camera_obj.location - target
            if offset.length <= 0.0:
                return
            camera_obj.location = target + offset * 1.2
            camera_obj.rotation_euler = (
                target - camera_obj.location
            ).to_track_quat("-Z", "Y").to_euler()


def set_camera_clip(
    camera_obj: bpy.types.Object,
    bounds: tuple[Vector, Vector],
    radius: float,
) -> None:
    camera  = camera_obj.data
    forward = (
        camera_obj.matrix_world.to_quaternion()
        @ Vector((0.0, 0.0, -1.0))
    )
    depths = [
        (corner - camera_obj.location).dot(forward)
        for corner in bounds_corners(bounds)
    ]
    positive_depths = [
        depth
        for depth in depths
        if depth > 0.0
    ]
    if not positive_depths:
        camera.clip_start = clip_start_for_radius(radius)
        camera.clip_end   = clip_end_for_radius(radius)
        return

    near_depth = max(
        min(positive_depths) * 0.25,
        clip_start_for_radius(radius),
    )
    far_depth  = max(
        max(positive_depths) + radius * 2.0,
        clip_end_for_radius(radius),
    )
    camera.clip_start = min(near_depth, 10_000.0)
    camera.clip_end   = min(far_depth, 10_000_000.0)


def clip_start_for_radius(radius: float) -> float:
    # Keep enough near-plane precision for coplanar authored line primitives.
    # An excessively small near clip makes Blender's native loose-edge overlay
    # alternate with the underlying surface and appear dashed at a distance.
    return max(radius / 1_000.0, 0.001)


def clip_end_for_radius(radius: float) -> float:
    return min(max(radius * 32.0, 1000.0), 10_000_000.0)
