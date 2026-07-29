from __future__ import annotations

import time
from array import array

import bpy
from mathutils import Matrix, Quaternion, Vector

from ..assetkit import (
    MeshPrimitiveData,
    SceneNodeData,
    _profile_log,
    native_animation_component_constant,
    native_animation_coords,
    native_animation_quat_slerp_coords,
    native_skin_group_assignments,
)
from . import profile as _profile_state
from .animation.actions import (
    _animation_action_for,
    _blender_interpolation,
    _channel_frame_bounds,
    _channel_tangents,
    _ensure_fcurve,
    _fcurve_write_key,
    _merge_frame_bounds,
    _register_actions_frame_range,
    _stash_animation_actions,
    _write_fcurve_points,
)
from .animation.object import (
    _ANIM_ROTATION_QUAT,
    _ANIM_SCALE,
    _ANIM_TRANSLATION,
    _anim_target_path,
    _apply_animation,
)
from .buffers import (
    buffer_view as _buffer_view,
    channel_count as _channel_count,
    channel_interpolation as _channel_interpolation,
    channel_is_partial as _channel_is_partial,
    channel_pose_ready as _channel_pose_ready,
    channel_target as _channel_target,
    channel_target_offset as _channel_target_offset,
    channel_times as _channel_times,
    channel_value_width as _channel_value_width,
    channel_values as _channel_values,
    matrix_from_buffer as _matrix_from_buffer,
    matrix_from_values as _matrix_from_values,
)
from .objects import _hide_empty_helper_object, _keep_helper_object_visible

_SKIN_CACHE_DEFER_BIND_SKINS = object()


def _temporary_view_layer_link(
    obj: bpy.types.Object,
) -> bpy.types.Collection | None:
    if obj.name in bpy.context.view_layer.objects:
        return None

    layer_collection = bpy.context.view_layer.active_layer_collection
    collection       = bpy.context.collection
    if layer_collection is not None:
        collection = layer_collection.collection
    if collection.objects.get(obj.name) is not None:
        return None

    collection.objects.link(obj)
    return collection


def _remove_temporary_view_layer_link(
    obj: bpy.types.Object,
    collection: bpy.types.Collection | None,
) -> None:
    if collection is not None and collection.objects.get(obj.name) is not None:
        collection.objects.unlink(obj)


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

    profile_detail = _profile_state.stats is not None
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
        pending = _deferred_bind_pose_skin_items(skin_cache)
        if pending is not None:
            pending.append((
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


def _deferred_bind_pose_skin_items(skin_cache: dict | None) -> list | None:
    if skin_cache is None:
        return None
    pending = skin_cache.get(_SKIN_CACHE_DEFER_BIND_SKINS)
    if pending is None:
        pending = []
        skin_cache[_SKIN_CACHE_DEFER_BIND_SKINS] = pending
    return pending


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
        return f"AssetKit Joint {node_index}"
    return f"AssetKit Joint {joint_index}"


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
    profile_detail = _profile_state.stats is not None
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

    profile_detail = _profile_state.stats is not None
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
    _match_skin_armature_space(
        armature,
        data,
        joint_nodes,
        node_objects,
        node_data,
        obj,
    )
    create_ms = lap_ms()

    # Progressive imports build in an unpublished staging collection. Blender
    # requires an armature in the active ViewLayer before entering Edit Mode,
    # so expose only this object until bone creation is complete.
    temporary_view_collection = _temporary_view_layer_link(armature)

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
    _match_skin_armature_space(
        armature,
        data,
        joint_nodes,
        node_objects,
        node_data,
        obj,
    )
    _keep_helper_object_visible(armature)

    if armature not in previous_selection:
        armature.select_set(False)
    bpy.context.view_layer.objects.active = previous_active
    _remove_temporary_view_layer_link(armature, temporary_view_collection)
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


def _skin_armature_source_index(
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
) -> int:
    root_index = int(data.skin_root_node_index)
    if root_index >= 0:
        return root_index

    if len(joint_nodes) == 0:
        return -1

    first_index = int(joint_nodes[0])
    first_node = node_data.get(first_index)
    parent_index = first_node.parent_index if first_node else -1
    return parent_index if parent_index >= 0 else first_index


def _match_skin_armature_space(
    target: bpy.types.Object,
    data: MeshPrimitiveData,
    joint_nodes: memoryview,
    node_objects: dict[int, bpy.types.Object],
    node_data: dict[int, SceneNodeData],
    fallback: bpy.types.Object,
) -> None:
    source_index = _skin_armature_source_index(data, joint_nodes, node_data)
    source = node_objects.get(source_index) or fallback
    source_data = node_data.get(source_index)
    local_matrix = _matrix_from_buffer(source_data.matrix_f32) if source_data else None

    target.parent = source.parent
    target.matrix_parent_inverse.identity()
    if local_matrix is not None:
        target.matrix_local = local_matrix
        return

    _match_object_space(target, source)


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
        names[node_index] = node.name if node else f"AssetKit Bone {node_index}"
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


def _apply_bone_animations(
    armature: bpy.types.Object,
    joint_names: list[str],
    joint_nodes: memoryview,
    node_data: dict[int, SceneNodeData],
    pose_channels_by_joint: list[list[dict]] | None = None,
) -> None:
    profile_detail = _profile_state.stats is not None
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
                        else (
                            native_animation_quat_slerp_coords(channel, component, fps)
                            if target == _ANIM_ROTATION_QUAT
                            and interpolation == "LINEAR"
                            and component_count == 4
                            and value_width == 4
                            else native_animation_coords(channel, component, fps)
                        )
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

    _register_actions_frame_range(actions, frame_bounds)
    if profile_detail:
        before_stash_at = time.perf_counter()
    _stash_animation_actions(actions)
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
