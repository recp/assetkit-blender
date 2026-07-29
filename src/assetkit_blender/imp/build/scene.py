from __future__ import annotations

from array import array
import time

import bpy
from mathutils import Matrix

from ...assetkit import CurveData, MeshPrimitiveData, SceneNodeData, _profile_enabled, _profile_log
from .. import profile as _profile_state
from ..buffers import (
    apply_matrix_buffer as _apply_matrix_buffer,
    buffer_view as _buffer_view,
    copy_buffer_bytes as _copy_buffer_bytes,
    matrix_from_buffer as _matrix_from_buffer,
)
from ..context import ImportState
from ..metadata import _set_assetkit_json_prop
from ..animation.object import _apply_animation
from ..objects import (
    _hide_empty_helper_object,
    _hide_helper_object,
    _keep_helper_object_visible,
    _set_node_visibility,
)
from ..skin import (
    _SKIN_CACHE_DEFER_BIND_SKINS,
    _apply_bone_animations,
    _match_skin_armature_space,
    _parent_skinned_mesh_to_armature,
    _set_bone_from_rest_matrix,
    _skin_bone_length,
    _skin_bone_node_indices,
    _skin_rest_matrices_from_assetkit_nodes,
    _remove_temporary_view_layer_link,
    _temporary_view_layer_link,
)
from .common import (
    _blender_natural_name_key,
    _compact_object_matrix,
    _mesh_node_parent,
    _node_import_collection,
    _set_parent,
)
from .visibility import _apply_effective_node_visibility_animation, _node_has_effective_visibility_animation

_AKB_CURVE_NURBS = 2

def _create_prototype_collections(
    nodes: list[SceneNodeData],
) -> dict[int, bpy.types.Collection]:
    prototype_roots = [
        index
        for index, node in enumerate(nodes)
        if int(node.prototype_root_index) == index
    ]
    if not prototype_roots:
        return {}

    collections: dict[int, bpy.types.Collection] = {}
    serial = len(bpy.data.collections)
    width = max(6, len(str(serial + len(prototype_roots))))
    for root_index in prototype_roots:
        while True:
            name = f"AssetKit Prototype {serial:0{width}d}"
            serial += 1
            if bpy.data.collections.get(name) is None:
                break
        prototype = bpy.data.collections.new(name)
        prototype["assetkit_prototype_root_index"] = root_index
        source_name = str(nodes[root_index].name or "")
        if source_name:
            prototype["assetkit_prototype_name"] = source_name
        collections[root_index] = prototype
    return collections


def _create_scene_nodes(
    nodes: list[SceneNodeData],
    coord_root: bpy.types.Object | None,
    collection: bpy.types.Collection,
    prototype_collections: dict[int, bpy.types.Collection],
    deferred_collection_instances: list[tuple],
    node_visibility: dict[int, bool] | None = None,
    apply_animation: bool = True,
    skip_animation_nodes: set[int] | None = None,
    required_indices: set[int] | None = None,
    has_visibility_animation: bool = False,
) -> dict[int, bpy.types.Object]:
    objects: dict[int, bpy.types.Object] = {}
    skip_animation_nodes = skip_animation_nodes or set()
    profile_detail = _profile_state.stats is not None
    create_started_at = time.perf_counter() if profile_detail else 0.0
    fallback_node_count = _fallback_scene_node_count(nodes, required_indices)

    create_indices = [
        index
        for index in range(len(nodes))
        if required_indices is None or index in required_indices
    ]
    create_indices.sort(
        key=lambda index: (
            _blender_natural_name_key(
                _scene_node_object_name(
                    nodes[index],
                    index,
                    fallback_node_count,
                )
            ),
            index,
        )
    )
    for index in create_indices:
        node = nodes[index]
        obj = _new_scene_node_object(
            node,
            index,
            (node_visibility or {}).get(index, node.visible),
            fallback_node_count,
        )
        active_collection = prototype_collections.get(
            int(node.prototype_root_index),
            collection,
        )
        active_collection.objects.link(obj)
        instance_target_index = int(node.instance_target_index)
        if instance_target_index >= 0:
            target_collection = prototype_collections.get(instance_target_index)
            if target_collection is not None:
                obj["assetkit_instance_node"] = True
                obj["assetkit_instance_target_index"] = instance_target_index
                deferred_collection_instances.append((obj, target_collection))
        objects[index] = obj

    create_ms = (time.perf_counter() - create_started_at) * 1000.0 if profile_detail else 0.0
    bind_started_at = time.perf_counter() if profile_detail else 0.0
    animation_ms = 0.0
    visibility_anim_ms = 0.0
    for index, obj in objects.items():
        node = nodes[index]
        if node.parent_index >= 0:
            parent = objects.get(node.parent_index)
        elif int(node.prototype_root_index) >= 0:
            parent = None
        else:
            parent = coord_root
        _set_parent(obj, parent)
        _apply_matrix_buffer(obj, node.matrix_f32)
        instance_target_index = int(node.instance_target_index)
        node_has_visibility_animation = has_visibility_animation and _node_has_effective_visibility_animation(
            index,
            nodes,
        )
        if apply_animation and index not in skip_animation_nodes:
            anim_started_at = time.perf_counter() if profile_detail else 0.0
            _apply_animation(obj, node, skip_visibility=node_has_visibility_animation)
            if profile_detail:
                animation_ms += (time.perf_counter() - anim_started_at) * 1000.0
            if node_has_visibility_animation:
                vis_started_at = time.perf_counter() if profile_detail else 0.0
                _apply_effective_node_visibility_animation(obj, index, nodes)
                if profile_detail:
                    visibility_anim_ms += (time.perf_counter() - vis_started_at) * 1000.0
        if obj.type == "EMPTY" and instance_target_index < 0:
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


def _apply_deferred_collection_instances(state: ImportState | None) -> None:
    if not state:
        return
    pending = state.deferred_collection_instances or []
    for obj, target_collection in pending:
        obj.instance_type = "COLLECTION"
        obj.instance_collection = target_collection
    pending.clear()


def _finish_compact_static_instances(state: ImportState | None) -> None:
    if not state:
        return
    plan = state.compact_instance_plan
    if plan is None or plan.get("finished"):
        return
    started_at = time.perf_counter() if _profile_enabled() else 0.0

    nodes = state.node_data or {}
    prototype_collections = state.prototype_collections or {}
    default_collection = plan["collection"]
    coord_root = state.coord_root
    created = state.compact_instance_objects

    batch_started_at = time.perf_counter() if _profile_enabled() else 0.0
    batches_by_owner: dict[int, list[tuple[int, list[int]]]] = {}
    for owner, target, node_indices in plan["batches"]:
        if prototype_collections.get(target) is not None:
            batches_by_owner.setdefault(owner, []).append((target, node_indices))

    owners_by_layer: dict[int, list[int]] = {}
    owner_layers = plan.get("owner_layers") or {}
    for owner in batches_by_owner:
        owners_by_layer.setdefault(int(owner_layers.get(owner, 0)), []).append(owner)

    for layer, owners in owners_by_layer.items():
        owners.sort()
        catalog = bpy.data.collections.new(
            f"AssetKit Instance Catalog {layer}"
        )
        targets = sorted(
            {
                target
                for owner in owners
                for target, _node_indices in batches_by_owner[owner]
            }
        )
        target_slots = {target: slot for slot, target in enumerate(targets)}
        for target in targets:
            target_collection = prototype_collections[target]
            entry = bpy.data.objects.new(
                f"AssetKit Instance Target {target}",
                None,
            )
            entry.instance_type = "COLLECTION"
            entry.instance_collection = target_collection
            catalog.objects.link(entry)

        node_group = _compact_instance_node_group(layer, catalog)
        plan["node_groups"][layer] = node_group
        for owner in owners:
            active_collection = (
                prototype_collections.get(owner, default_collection)
                if owner >= 0
                else default_collection
            )
            owner_batches = batches_by_owner[owner]
            owner_batches.sort(key=lambda item: item[0])
            node_indices = [
                node_index
                for _target, indices in owner_batches
                for node_index in indices
            ]
            target_indices = [
                target_slots[target]
                for target, indices in owner_batches
                for _node_index in indices
            ]
            obj = _create_compact_instance_batch_object(
                owner,
                node_indices,
                target_indices,
                plan["matrix_buffers"],
                active_collection,
                node_group,
                len(target_slots),
            )
            if owner < 0:
                _set_parent(obj, coord_root)
            created.append(obj)
    batch_ms = (
        (time.perf_counter() - batch_started_at) * 1000.0
        if _profile_enabled()
        else 0.0
    )

    residual_started_at = time.perf_counter() if _profile_enabled() else 0.0
    for node_index in plan["residual_indices"]:
        node = nodes.get(node_index)
        if node is None:
            continue
        owner = int(node.prototype_root_index)
        target = int(node.instance_target_index)
        target_collection = prototype_collections.get(target)
        if target_collection is None:
            continue
        active_collection = (
            prototype_collections.get(owner, default_collection)
            if owner >= 0
            else default_collection
        )
        obj = bpy.data.objects.new(
            node.name or f"AssetKit Instance {node_index}",
            None,
        )
        obj.instance_type = "COLLECTION"
        obj.instance_collection = target_collection
        obj["assetkit_instance_node"] = True
        obj["assetkit_instance_target_index"] = target
        obj["assetkit_source_node_index"] = node_index
        active_collection.objects.link(obj)
        if owner < 0:
            _set_parent(obj, coord_root)
        matrix = _compact_object_matrix(plan, node_index)
        if matrix is not None:
            obj.matrix_local = matrix
        created.append(obj)
    residual_ms = (
        (time.perf_counter() - residual_started_at) * 1000.0
        if _profile_enabled()
        else 0.0
    )

    plan["finished"] = True
    if _profile_enabled():
        _profile_log(
            "finish_compact_static_instances "
            f"batches={len(plan['batches'])} "
            f"residual={len(plan['residual_indices'])} "
            f"created={len(created)} "
            f"batch={batch_ms:.3f}ms residual={residual_ms:.3f}ms "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _create_compact_instance_batch_object(
    owner: int,
    node_indices: list[int],
    target_indices: list[int],
    node_matrices: dict[int, object],
    active_collection: bpy.types.Collection,
    node_group: bpy.types.GeometryNodeTree,
    target_count: int,
) -> bpy.types.Object:
    count = len(node_indices)
    mesh = bpy.data.meshes.new(f"AssetKit Instance Batch {owner}")
    mesh.vertices.add(count)

    matrix_values = bytearray(count * 16 * 4)
    source_indices = array("i", node_indices)
    for matrix_index, node_index in enumerate(node_indices):
        matrix = node_matrices[node_index]
        if isinstance(matrix, Matrix):
            values = array(
                "f",
                (
                    value
                    for row in matrix.transposed()
                    for value in row
                ),
            )
        else:
            values = _buffer_view(matrix, "f")
        if values is None or len(values) != 16:
            raise RuntimeError("AssetKit compact instance matrix is incomplete")
        _copy_buffer_bytes(matrix_values, matrix_index * 16 * 4, values, "f")
    matrix_attribute = mesh.attributes.new(
        "assetkit_instance_matrix",
        type="FLOAT4X4",
        domain="POINT",
    )
    matrix_attribute.data.foreach_set("value", memoryview(matrix_values).cast("f"))
    source_attribute = mesh.attributes.new(
        "assetkit_source_node_index",
        type="INT",
        domain="POINT",
    )
    source_attribute.data.foreach_set("value", source_indices)
    target_attribute = mesh.attributes.new(
        "assetkit_instance_target_slot",
        type="INT",
        domain="POINT",
    )
    target_attribute.data.foreach_set("value", target_indices)
    mesh.update(calc_edges=False)

    obj = bpy.data.objects.new(f"AssetKit Instance Batch {owner}", mesh)
    obj["assetkit_compact_instance_batch"] = True
    obj["assetkit_instance_owner_index"] = owner
    obj["assetkit_instance_target_count"] = target_count
    obj["assetkit_instance_count"] = count
    active_collection.objects.link(obj)

    modifier = obj.modifiers.new("AssetKit Instances", "NODES")
    modifier.node_group = node_group
    return obj


def _compact_instance_node_group(
    layer: int,
    catalog: bpy.types.Collection,
) -> bpy.types.GeometryNodeTree:
    group = bpy.data.node_groups.new(
        f"AssetKit Instance Layer {layer}",
        "GeometryNodeTree",
    )
    group.interface.new_socket(
        name="Geometry",
        in_out="INPUT",
        socket_type="NodeSocketGeometry",
    )
    group.interface.new_socket(
        name="Geometry",
        in_out="OUTPUT",
        socket_type="NodeSocketGeometry",
    )

    group_input = group.nodes.new("NodeGroupInput")
    group_output = group.nodes.new("NodeGroupOutput")
    collection_info = group.nodes.new("GeometryNodeCollectionInfo")
    collection_info.inputs["Collection"].default_value = catalog
    collection_info.inputs["Separate Children"].default_value = True
    collection_info.inputs["Reset Children"].default_value = True
    instance_on_points = group.nodes.new("GeometryNodeInstanceOnPoints")
    instance_on_points.inputs["Pick Instance"].default_value = True
    target_attribute = group.nodes.new("GeometryNodeInputNamedAttribute")
    target_attribute.data_type = "INT"
    target_attribute.inputs["Name"].default_value = "assetkit_instance_target_slot"
    matrix_attribute = group.nodes.new("GeometryNodeInputNamedAttribute")
    matrix_attribute.data_type = "FLOAT4X4"
    matrix_attribute.inputs["Name"].default_value = "assetkit_instance_matrix"
    set_transform = group.nodes.new("GeometryNodeSetInstanceTransform")

    group.links.new(group_input.outputs["Geometry"], instance_on_points.inputs["Points"])
    group.links.new(collection_info.outputs["Instances"], instance_on_points.inputs["Instance"])
    group.links.new(target_attribute.outputs["Attribute"], instance_on_points.inputs["Instance Index"])
    group.links.new(instance_on_points.outputs["Instances"], set_transform.inputs["Instances"])
    group.links.new(matrix_attribute.outputs["Attribute"], set_transform.inputs["Transform"])
    group.links.new(set_transform.outputs["Instances"], group_output.inputs["Geometry"])
    return group


def _required_scene_node_indices(
    primitives: list[MeshPrimitiveData],
    nodes: list[SceneNodeData],
    skipped_animation_indices: set[int] | None = None,
    curves: list[CurveData] | None = None,
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
    if curves:
        primitive_node_indices.update(
            int(curve.node_index)
            for curve in curves
            if int(curve.node_index) >= 0
        )
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

    for curve in curves or ():
        node_index = int(curve.node_index)
        if _primitive_node_needs_helper(node_index, nodes, child_counts):
            _add_node_ancestors(required, nodes, node_index)
        else:
            _add_node_parent_ancestors(required, nodes, node_index)

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
        or int(node.instance_target_index) >= 0
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
    _collect_skinned_node_animation_skip(skip, primitives)
    return skip


def _mark_skinned_node_animation_skip(
    state: ImportState | None,
    primitives: list[MeshPrimitiveData],
) -> None:
    if not state:
        return

    _collect_skinned_node_animation_skip(state.node_animation_skip_indices, primitives)


def _collect_skinned_node_animation_skip(
    skip: set[int],
    primitives: list[MeshPrimitiveData],
) -> None:
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


def _apply_deferred_scene_node_animations(state: ImportState | None) -> None:
    if not state or not state.node_animation_deferred:
        return
    if not state.has_node_animation and not state.has_node_visibility_animation:
        state.node_animation_deferred = False
        return

    profile_detail = _profile_state.stats is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    node_objects = state.node_objects or {}
    node_data = state.node_data or {}
    skip_animation_nodes = state.node_animation_skip_indices or set()
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

    state.node_animation_deferred = False
    if profile_detail:
        _profile_log(
            "deferred_scene_node_animations "
            f"nodes={len(node_data)} "
            f"animation={animation_ms:.3f}ms "
            f"visibility_animation={visibility_anim_ms:.3f}ms "
            f"total={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _apply_deferred_bind_pose_skins(state: ImportState | None) -> None:
    if not state:
        return

    skin_cache = state.skin_cache or {}
    pending = skin_cache.get(_SKIN_CACHE_DEFER_BIND_SKINS) or []
    if not pending:
        return
    skin_cache[_SKIN_CACHE_DEFER_BIND_SKINS] = []

    profile_detail = _profile_state.stats is not None
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
        _match_skin_armature_space(
            armature,
            first_data,
            first_joint_nodes,
            first_node_objects,
            first_node_data,
            first_obj,
        )
        bone_node_indices = _bind_pose_group_bone_node_indices(items)
        records.append({
            "items": items,
            "armature": armature,
            "armature_data": armature_data,
            "node_data": first_node_data,
            "bone_node_indices": bone_node_indices,
            "bone_names_by_node": _bind_pose_group_bone_names(items),
            "rest_matrices_by_node": _skin_rest_matrices_from_assetkit_nodes(
                first_data,
                first_node_data,
                bone_node_indices,
            ),
            "temporary_view_collection": _temporary_view_layer_link(armature),
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
        (
            first_obj,
            first_data,
            _first_joint_names,
            first_joint_nodes,
            first_node_objects,
            first_node_data,
            *_first_rest,
        ) = record["items"][0]
        _match_skin_armature_space(
            armature,
            first_data,
            first_joint_nodes,
            first_node_objects,
            first_node_data,
            first_obj,
        )
        _keep_helper_object_visible(armature)
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
        armature = record["armature"]
        armature.select_set(False)
        _remove_temporary_view_layer_link(
            armature,
            record["temporary_view_collection"],
        )
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


def _apply_deferred_skin_animations(state: ImportState | None) -> None:
    if not state or not state.skin_animation_deferred:
        return

    pending = state.deferred_skin_animations or []
    if not pending:
        state.skin_animation_deferred = False
        return

    profile_detail = _profile_state.stats is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    skin_count = len(pending)
    for armature, data, joint_names, joint_nodes, node_data, pose_channels_by_joint, include_root in pending:
        if include_root:
            root_node = node_data.get(int(data.skin_root_node_index))
            if root_node:
                _apply_animation(armature, root_node)
        _apply_bone_animations(armature, joint_names, joint_nodes, node_data, pose_channels_by_joint)

    state.skin_animation_deferred = False
    pending.clear()
    if profile_detail:
        _profile_log(
            "deferred_skin_animations "
            f"skins={skin_count} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )


def _fallback_scene_node_count(nodes: list[SceneNodeData], required_indices: set[int] | None) -> int:
    if required_indices is None:
        return sum(1 for node in nodes if not node.name)
    return sum(1 for index, node in enumerate(nodes) if index in required_indices and not node.name)


def _new_scene_node_object(
    node: SceneNodeData,
    index: int,
    visible: bool,
    fallback_node_count: int,
) -> bpy.types.Object:
    name = _scene_node_object_name(node, index, fallback_node_count)

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
    obj.empty_display_size = 0.0001
    _set_node_visibility(obj, visible)
    _set_assetkit_node_props(obj, node)
    return obj


def _scene_node_object_name(
    node: SceneNodeData,
    index: int,
    fallback_node_count: int,
) -> str:
    return node.name or (
        "AssetKit Node"
        if fallback_node_count == 1 or index == 0
        else f"AssetKit Node {index}"
    )


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


def _create_coord_root(
    primitives: list[MeshPrimitiveData],
    collection: bpy.types.Collection,
    curves: list[CurveData] | None = None,
) -> bpy.types.Object | None:
    for primitive in primitives:
        matrix = _matrix_from_buffer(primitive.coord_matrix_f32)
        if matrix is None:
            continue

        root = bpy.data.objects.new("AssetKit Root", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.0001
        root.matrix_local = matrix
        root["assetkit_helper_object"] = True
        root["assetkit_coordinate_root"] = True
        collection.objects.link(root)
        return root

    for curve in curves or ():
        matrix = _matrix_from_buffer(curve.coord_matrix_f32)
        if matrix is None:
            continue

        root = bpy.data.objects.new("AssetKit Root", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.0001
        root.matrix_local = matrix
        root["assetkit_helper_object"] = True
        root["assetkit_coordinate_root"] = True
        collection.objects.link(root)
        return root

    return None


def _create_curve_objects(
    curves: list[CurveData],
    state: ImportState,
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []
    for curve in curves:
        obj = _create_curve_object(curve, state, collection)
        if obj is not None:
            objects.append(obj)
    return objects


def _create_curve_object(
    curve: CurveData,
    state: ImportState,
    collection: bpy.types.Collection,
) -> bpy.types.Object | None:
    point_count = int(curve.point_count)
    points = _buffer_view(curve.points_f32, "f")
    if point_count <= 0 or points is None or len(points) < point_count * 4:
        return None

    curve_data = bpy.data.curves.new(curve.name or "AssetKit Curve", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 12

    spline_type = "NURBS" if int(curve.kind) == _AKB_CURVE_NURBS else "POLY"
    spline = curve_data.splines.new(spline_type)
    spline.points.add(point_count - 1)
    spline.points.foreach_set("co", points)
    spline.use_cyclic_u = bool(curve.closed)
    if spline_type == "NURBS":
        try:
            spline.order_u = max(2, min(point_count, int(curve.degree) + 1))
            spline.use_endpoint_u = True
        except Exception:
            pass

    obj = bpy.data.objects.new(curve.object_name or curve.name or "AssetKit Curve", curve_data)
    node_index = int(curve.node_index)
    active_collection = _node_import_collection(state, node_index, collection)
    active_collection.objects.link(obj)
    parent, use_node_parent = _mesh_node_parent(state, node_index)
    _set_parent(obj, parent)
    if not use_node_parent:
        _apply_matrix_buffer(obj, curve.matrix_f32)
    _set_assetkit_json_prop(obj, "assetkit_geometry_extra_json", curve.geometry_extra)
    _set_assetkit_json_prop(obj, "assetkit_curve_extra_json", curve.curve_extra)
    obj["assetkit_curve_kind"] = int(curve.kind)
    obj["assetkit_curve_degree"] = int(curve.degree)
    obj["assetkit_curve_closed"] = bool(curve.closed)
    return obj
