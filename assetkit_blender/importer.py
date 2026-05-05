from __future__ import annotations

from array import array

import bpy
from mathutils import Matrix, Vector

from .assetkit import AssetKit, AssetKitSceneData, MeshPrimitiveData, SceneNodeData, native_load_meshes

_ANIM_TRANSLATION = 1
_ANIM_ROTATION_QUAT = 2
_ANIM_SCALE = 3
_ANIM_MORPH_WEIGHTS = 4
_INTERPOLATION_LINEAR = 1
_INTERPOLATION_STEP = 6


def import_assetkit_file(
    filepath: str,
    library_path: str = "",
    load_options: dict | None = None,
) -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []

    loaded = native_load_meshes(filepath, load_options) if not library_path else None
    if loaded is None:
        kit = AssetKit(library_path or None)
        loaded = kit.load_meshes(filepath)

    if isinstance(loaded, AssetKitSceneData):
        primitives = loaded.meshes
        scene_nodes = loaded.nodes
    else:
        primitives = loaded
        scene_nodes = []

    coord_root = _create_coord_root(primitives)
    node_objects = _create_scene_nodes(scene_nodes, coord_root)
    node_data = {index: node for index, node in enumerate(scene_nodes)}
    for primitive in primitives:
        node_parent = node_objects.get(primitive.node_index)
        parent = node_parent or coord_root
        use_node_parent = node_parent is not None
        obj = _create_mesh_object(
            primitive,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            apply_transform=not use_node_parent,
            apply_animation=not use_node_parent,
        )
        objects.append(obj)

    return objects


def _create_mesh_object(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
) -> bpy.types.Object:
    if data.vertices_f32 and data.indices_u32:
        return _create_mesh_object_bulk(
            data,
            parent,
            node_objects=node_objects,
            node_data=node_data,
            apply_transform=apply_transform,
            apply_animation=apply_animation,
        )

    mesh = bpy.data.meshes.new(data.name)
    mesh.from_pydata(data.vertices, [], data.faces)
    mesh.update(calc_edges=True)

    if data.uvs and len(data.uvs) >= len(mesh.loops):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, uv in enumerate(data.uvs[: len(mesh.loops)]):
            uv_layer.data[loop_index].uv = (uv[0], 1.0 - uv[1])

    if data.normals and len(data.normals) >= len(mesh.loops):
        mesh.normals_split_custom_set(data.normals[: len(mesh.loops)])
        for poly in mesh.polygons:
            poly.use_smooth = True

    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if apply_transform:
        _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)
    _apply_shape_keys(obj, data)
    _apply_skin(obj, data, node_objects or {}, node_data or {})
    if apply_animation:
        _apply_animation(obj, data)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_mesh_object_bulk(
    data: MeshPrimitiveData,
    parent: bpy.types.Object | None = None,
    *,
    node_objects: dict[int, bpy.types.Object] | None = None,
    node_data: dict[int, SceneNodeData] | None = None,
    apply_transform: bool = True,
    apply_animation: bool = True,
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

    if data.uvs_f32:
        uvs = _buffer_view(data.uvs_f32, "f")
        uv_layer = mesh.uv_layers.new(name="UVMap")
        if uvs is not None:
            uv_layer.data.foreach_set("uv", uvs)

    if data.colors_f32:
        colors = _buffer_view(data.colors_f32, "f")
        if colors is not None:
            color_attr = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
            color_attr.data.foreach_set("color", colors)

    mesh.update(calc_edges=True)

    if data.normals_f32:
        normals = _buffer_view(data.normals_f32, "f")
        try:
            if normals is not None:
                mesh.corner_normals.foreach_set("vector", normals)
                for poly in mesh.polygons:
                    poly.use_smooth = True
        except Exception:
            pass

    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _set_parent(obj, parent)
    if apply_transform:
        _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)
    _apply_shape_keys(obj, data)
    _apply_skin(obj, data, node_objects or {}, node_data or {})
    if apply_animation:
        _apply_animation(obj, data)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_scene_nodes(
    nodes: list[SceneNodeData],
    coord_root: bpy.types.Object | None,
) -> dict[int, bpy.types.Object]:
    objects: dict[int, bpy.types.Object] = {}

    for index, node in enumerate(nodes):
        obj = _new_scene_node_object(node, index)
        bpy.context.collection.objects.link(obj)
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


def _create_coord_root(primitives: list[MeshPrimitiveData]) -> bpy.types.Object | None:
    for primitive in primitives:
        matrix = _matrix_from_buffer(primitive.coord_matrix_f32)
        if matrix is None:
            continue

        root = bpy.data.objects.new("AssetKit Coordinates", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.5
        root.matrix_local = matrix
        bpy.context.collection.objects.link(root)
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

    return Matrix(
        (
            (values[0], values[4], values[8], values[12]),
            (values[1], values[5], values[9], values[13]),
            (values[2], values[6], values[10], values[14]),
            (values[3], values[7], values[11], values[15]),
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
    armature = _create_skin_armature(obj, joint_names, joint_nodes, node_objects, node_data)
    if not armature:
        return

    modifier = obj.modifiers.new("AssetKit Skin", "ARMATURE")
    modifier.object = armature
    modifier.use_vertex_groups = True


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
    joint_names: list[str],
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
) -> bpy.types.Object | None:
    if not joint_names:
        return None

    armature_data = bpy.data.armatures.new(f"{obj.name}_Armature")
    armature = bpy.data.objects.new(f"{obj.name}_Armature", armature_data)
    bpy.context.collection.objects.link(armature)

    previous_active = bpy.context.view_layer.objects.active
    previous_selection = list(bpy.context.selected_objects)
    if previous_active and previous_active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = armature_data.edit_bones
    positions = _joint_positions(joint_nodes, node_objects)
    node_to_joint = {
        int(joint_nodes[index]): index
        for index in range(min(len(joint_nodes), len(joint_names)))
        if int(joint_nodes[index]) >= 0
    }

    for index, name in enumerate(joint_names):
        bone = edit_bones.new(name)
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
    _apply_bone_animations(armature, joint_names, joint_nodes, node_data)

    bpy.ops.object.select_all(action="DESELECT")
    for selected in previous_selection:
        selected.select_set(True)
    bpy.context.view_layer.objects.active = previous_active
    return armature


def _joint_positions(joint_nodes: memoryview, node_objects: dict[int, bpy.types.Object]) -> list[Vector]:
    positions = []
    for index in range(len(joint_nodes)):
        node = node_objects.get(int(joint_nodes[index]))
        if node:
            positions.append(node.matrix_world.to_translation())
        else:
            positions.append(Vector((0.0, float(index) * 0.05, 0.0)))
    return positions


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


def _create_material(data: MeshPrimitiveData) -> bpy.types.Material | None:
    if not data.material_name:
        return None

    mat = bpy.data.materials.get(data.material_name) or bpy.data.materials.new(data.material_name)
    mat.use_nodes = True
    mat.use_backface_culling = not data.double_sided
    if data.alpha_mode == 1:
        mat.blend_method = "BLEND"
    elif data.alpha_mode == 2:
        mat.blend_method = "CLIP"
        mat.alpha_threshold = data.alpha_cutoff

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    _set_input(bsdf, "Base Color", data.base_color)
    _set_input(bsdf, "Metallic", data.metallic)
    _set_input(bsdf, "Roughness", data.roughness)
    _set_input(bsdf, "Alpha", data.base_color[3])
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

    if data.base_color_texture:
        _link_base_color_texture(mat, bsdf, data)
    if data.metallic_roughness_texture:
        _link_metallic_roughness_texture(mat, bsdf, data.metallic_roughness_texture)
    if data.occlusion_texture:
        _link_image_first(mat, bsdf, data.occlusion_texture, ("Ambient Occlusion", "Occlusion"), colorspace="Non-Color")
    if data.normal_texture:
        _link_normal_texture(mat, bsdf, data.normal_texture, data.normal_scale)
    if data.emissive_texture:
        _link_image(mat, bsdf, data.emissive_texture, "Emission Color", colorspace="sRGB")
    if data.specular_texture:
        _link_image_first(mat, bsdf, data.specular_texture, ("Specular IOR Level", "Specular"), colorspace="Non-Color")
    if data.specular_color_texture:
        _link_image_first(mat, bsdf, data.specular_color_texture, ("Specular Tint",), colorspace="sRGB")
    if data.clearcoat_texture:
        _link_image_first(mat, bsdf, data.clearcoat_texture, ("Coat Weight", "Clearcoat"), colorspace="Non-Color")
    if data.clearcoat_roughness_texture:
        _link_image_first(mat, bsdf, data.clearcoat_roughness_texture, ("Coat Roughness", "Clearcoat Roughness"), colorspace="Non-Color")
    if data.clearcoat_normal_texture:
        _link_normal_texture(mat, bsdf, data.clearcoat_normal_texture, data.clearcoat_normal_scale, input_name="Coat Normal")
    if data.transmission_texture:
        _link_image_first(mat, bsdf, data.transmission_texture, ("Transmission Weight", "Transmission"), colorspace="Non-Color")
    if data.sheen_color_texture:
        _link_image_first(mat, bsdf, data.sheen_color_texture, ("Sheen Tint",), colorspace="sRGB")
    if data.sheen_roughness_texture:
        _link_image_first(mat, bsdf, data.sheen_roughness_texture, ("Sheen Roughness",), colorspace="Non-Color")

    return mat


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


def _link_image(mat: bpy.types.Material, target, path: str, input_name: str, colorspace: str) -> None:
    tex = _image_texture_node(mat, path, colorspace)
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
) -> None:
    tex = _image_texture_node(mat, path, colorspace)
    if not tex:
        return

    for input_name in input_names:
        socket = target.inputs.get(input_name)
        if socket:
            mat.node_tree.links.new(tex.outputs["Color"], socket)
            return


def _link_base_color_texture(mat: bpy.types.Material, bsdf, data: MeshPrimitiveData) -> None:
    tex = _image_texture_node(mat, data.base_color_texture, "sRGB")
    if not tex:
        return

    links = mat.node_tree.links
    base_color = bsdf.inputs.get("Base Color")
    alpha = bsdf.inputs.get("Alpha")
    if base_color:
        links.new(tex.outputs["Color"], base_color)
    if data.alpha_mode and alpha and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], alpha)


def _link_metallic_roughness_texture(mat: bpy.types.Material, bsdf, path: str) -> None:
    tex = _image_texture_node(mat, path, "Non-Color")
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
    input_name: str = "Normal",
) -> None:
    tex = _image_texture_node(mat, path, "Non-Color")
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


def _image_texture_node(mat: bpy.types.Material, path: str, colorspace: str):
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
    return tex
