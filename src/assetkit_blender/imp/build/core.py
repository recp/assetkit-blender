from __future__ import annotations

from collections import deque
import math
import os
import time

import bpy
from mathutils import Matrix, Vector

from ...assetkit import CurveData, MeshPrimitiveData, SceneNodeData, _profile_enabled, _profile_log
from ...load_options import AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS, LoadOptions
from ..animation import actions as _animation
from .. import profile as _profile_state
from ..animation.actions import _action_frame_range
from ..context import ImportState
from ..material import core as _materials, _create_material, _material_cache_key_for_data
from ..metadata import (
    _assetkit_extra_child,
    _assetkit_extra_float,
    _assetkit_extra_float_array,
    _assetkit_extra_path,
    _assetkit_extra_plain_value,
    _set_assetkit_json_prop,
)
from ..skin import _node_static_world_matrix
from ..viewport import (
    apply_import_placement as _apply_import_placement,
    focus_imported_objects as _focus_imported_objects,
    scene_bounds_from_info as _scene_bounds_from_info,
    select_imported_objects as _select_imported_objects,
    set_viewport_material_preview as _set_viewport_material_preview,
    unique_objects as _unique_objects,
)
from .common import _compact_object_matrix, _mesh_node_parent, _set_parent
from .mesh import _create_grouped_mesh_object, _create_import_object
from .scene import (
    _add_node_ancestors,
    _create_coord_root,
    _create_prototype_collections,
    _create_scene_nodes,
    _mark_skinned_node_animation_skip,
    _required_scene_node_indices,
    _skinned_node_animation_skip_indices,
)
from .visibility import (
    _effective_static_node_visibility_map,
    _node_has_visibility_animation,
    _node_object_visibility_map,
)

_MATERIAL_PREBUILD_PRIMITIVE_LIMIT = 1024
_REQUIRED_NODE_INDICES_AUTO         = object()
_COMPACT_STATIC_INSTANCES_ENV       = "ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES"

def _scene_info_from_loaded(loaded: object | None) -> dict:
    if not loaded:
        return {}
    return {
        "index": int(getattr(loaded, "scene_index", -1)),
        "count": int(getattr(loaded, "scene_count", 0)),
        "name": str(getattr(loaded, "scene_name", "") or ""),
        "names": list(getattr(loaded, "scene_names", []) or []),
        "bounds": getattr(loaded, "scene_bounds", None),
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
    curves: list[CurveData] | None = None,
    preserve_tangents: bool = False,
    defer_scene_nodes: bool = False,
) -> ImportState:
    profile_detail = _profile_state.stats is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    _set_document_extra_props(collection, doc_extra, scene_extra, scene_info, doc_images)
    doc_ms = (time.perf_counter() - started_at) * 1000.0 if profile_detail else 0.0
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    coord_root = _create_coord_root(primitives, collection, curves)
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
    compact_instance_plan = (
        None
        if create_all_nodes
        else _compact_static_instance_plan(primitives, curves, scene_nodes)
    )
    if compact_instance_plan is not None:
        compact_instance_plan["collection"] = collection
        required_node_indices = compact_instance_plan["required_indices"]
        defer_scene_nodes = False
    elif create_all_nodes:
        required_node_indices = None
    elif required_node_indices is _REQUIRED_NODE_INDICES_AUTO:
        required_node_indices = _required_scene_node_indices(primitives, scene_nodes, node_animation_skip_indices, curves)
    elif required_node_indices is not None:
        required_node_indices = set(required_node_indices)
    prototype_collections = _create_prototype_collections(scene_nodes)
    deferred_collection_instances: list[tuple] = []
    deferred_scene_node_build = None
    if defer_scene_nodes:
        node_objects = {}
        deferred_scene_node_build = {
            "nodes": scene_nodes,
            "coord_root": coord_root,
            "collection": collection,
            "prototype_collections": prototype_collections,
            "deferred_collection_instances": deferred_collection_instances,
            "node_visibility": node_object_visibility,
            "apply_animation": apply_node_animation,
            "skip_animation_nodes": node_animation_skip_indices,
            "required_indices": required_node_indices,
            "has_visibility_animation": node_visibility_animation,
            "hide_helper_empties": create_all_nodes,
        }
    else:
        node_objects = _create_scene_nodes(
            scene_nodes,
            coord_root,
            collection,
            prototype_collections,
            deferred_collection_instances,
            node_object_visibility,
            apply_animation=apply_node_animation,
            skip_animation_nodes=node_animation_skip_indices,
            required_indices=required_node_indices,
            has_visibility_animation=node_visibility_animation,
            hide_helper_empties=create_all_nodes,
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
    return ImportState(
        coord_root                     = coord_root,
        root_objects                   = _scene_root_objects(scene_nodes, coord_root, node_objects),
        node_objects                   = node_objects,
        node_data                      = {index: node for index, node in enumerate(scene_nodes)},
        node_visibility                = node_visibility,
        node_animation_skip_indices    = node_animation_skip_indices,
        material_cache                 = {},
        mesh_cache                     = {},
        skin_cache                     = {},
        node_animation_deferred        = not apply_node_animation,
        skin_animation_deferred        = not apply_node_animation,
        deferred_skin_animations       = [],
        mesh_cache_hits                = 0,
        defer_custom_normals           = defer_custom_normals,
        has_node_visibility_animation  = node_visibility_animation,
        has_node_animation             = node_animation,
        dynamic_skin_animation_skip    = dynamic_skin_animation_skip,
        node_parent_cache              = {},
        preserve_tangents              = preserve_tangents,
        prototype_collections          = prototype_collections,
        deferred_collection_instances = deferred_collection_instances,
        preserve_hierarchy             = create_all_nodes,
        realized_instance_objects      = [],
        deferred_scene_node_build      = deferred_scene_node_build,
        compact_instance_plan          = compact_instance_plan,
        compact_instance_objects       = [],
        scene_bounds                   = _scene_bounds_from_info(scene_info),
    )


def _set_document_extra_props(
    collection: bpy.types.Collection,
    doc_extra: object | None,
    scene_extra: object | None = None,
    scene_info: dict | None = None,
    doc_images: list[dict] | None = None,
) -> None:
    for target in (collection, bpy.context.scene, getattr(bpy.context.scene, "world", None)):
        _clear_assetkit_props(
            target,
            (
                "assetkit_document_extra_json",
                "assetkit_document_images_json",
                "assetkit_scene_extra_json",
                "assetkit_scene_index",
                "assetkit_scene_count",
                "assetkit_scene_name",
                "assetkit_scene_names_json",
            ),
        )
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


def _clear_assetkit_props(target, keys: tuple[str, ...]) -> None:
    if target is None:
        return
    for key in keys:
        try:
            if key in target:
                del target[key]
        except Exception:
            pass


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
        if (
            node.parent_index < 0
            and int(node.prototype_root_index) < 0
            and index in node_objects
        ):
            roots.append(node_objects[index])
    return roots


def _can_defer_scene_nodes(
    primitives: list[MeshPrimitiveData],
    curves: list[CurveData] | None,
) -> bool:
    if curves:
        return False
    return not any(
        primitive.has_skin or primitive.instance_count
        for primitive in primitives
    )


def _compact_static_instances_enabled() -> bool:
    value = str(os.environ.get(_COMPACT_STATIC_INSTANCES_ENV, "") or "").strip().lower()
    if not value or value == "auto":
        return True
    return value in {"1", "true", "yes", "on", "flat", "shallow"}


def _compact_content_key_options(
    options: LoadOptions | None,
) -> LoadOptions | None:
    if not _compact_static_instances_enabled() or options is None:
        return options
    if len(options) <= AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS:
        return options
    if options[AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS]:
        return options
    values = list(options)
    values[AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS] = 1
    return tuple(values)


def _compact_static_instance_plan(
    primitives: list[MeshPrimitiveData],
    curves: list[CurveData] | None,
    nodes: list[SceneNodeData],
) -> dict | None:
    started_at = time.perf_counter() if _profile_enabled() else 0.0
    if not _compact_static_instances_enabled() or not nodes or curves:
        return None
    if not hasattr(bpy.types, "GeometryNodeSetInstanceTransform"):
        return None
    if any(
        primitive.has_skin or primitive.instance_count
        for primitive in primitives
    ):
        return None
    if any(
        not node.visible or node.anim_count or node.anim_channels
        for node in nodes
    ):
        return None

    instance_indices = [
        index
        for index, node in enumerate(nodes)
        if int(node.instance_target_index) >= 0
    ]
    if not instance_indices:
        return None

    node_data = {index: node for index, node in enumerate(nodes)}
    matrix_cache: dict[int, Matrix] = {}
    flat_matrix_buffers = {}
    for index, node in node_data.items():
        matrix_buffer = getattr(node, "world_matrix_f32", b"")
        flat_matrix_buffers[index] = (
            matrix_buffer
            if matrix_buffer
            else _node_static_world_matrix(index, node_data, matrix_cache)
        )

    prototype_targets: dict[int, set[int]] = {}
    grouped_indices: dict[tuple[int, int], list[int]] = {}
    for index in instance_indices:
        node = nodes[index]
        owner = int(node.prototype_root_index)
        target = int(node.instance_target_index)
        grouped_indices.setdefault((owner, target), []).append(index)
        prototype_targets.setdefault(owner, set()).add(target)

    edges = list(grouped_indices)
    selected_edges: set[tuple[int, int]] = set()
    compact_mode = str(
        os.environ.get(_COMPACT_STATIC_INSTANCES_ENV, "") or ""
    ).strip().lower()
    single_batch_layer = compact_mode == "shallow"

    adjacency: dict[int, list[int]] = {}
    for owner, target in edges:
        adjacency.setdefault(owner, []).append(target)
    reachable = {-1}
    pending = [-1]
    while pending:
        owner = pending.pop()
        for target in adjacency.get(owner, ()):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    indegree = {node: 0 for node in reachable}
    for owner in reachable:
        for target in adjacency.get(owner, ()):
            if target in indegree:
                indegree[target] += 1
    ready = deque(node for node, degree in indegree.items() if degree == 0)
    topological_order: list[int] = []
    while ready:
        owner = ready.popleft()
        topological_order.append(owner)
        for target in adjacency.get(owner, ()):
            if target not in indegree:
                continue
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    graph_is_acyclic = len(topological_order) == len(reachable)
    prototype_depth = {-1: 0}
    if graph_is_acyclic:
        for owner in topological_order:
            owner_depth = prototype_depth.get(owner, 0)
            for target in adjacency.get(owner, ()):
                prototype_depth[target] = max(
                    prototype_depth.get(target, 0),
                    owner_depth + 1,
                )

    def selection_is_safe() -> bool:
        if not graph_is_acyclic:
            return False
        no_batch_depth = {-1: 0}
        batch_depth: dict[int, int] = {}
        batch_layers = {-1: 0}
        for owner in topological_order:
            for target in adjacency.get(owner, ()):
                source_layers = batch_layers.get(owner)
                if source_layers is not None:
                    target_layers = source_layers + int(
                        (owner, target) in selected_edges
                    )
                    if target_layers > batch_layers.get(target, -1):
                        batch_layers[target] = target_layers
                if (owner, target) in selected_edges:
                    source = max(
                        no_batch_depth.get(owner, -1),
                        batch_depth.get(owner, -1),
                    )
                    if source >= 0 and source + 3 > batch_depth.get(target, -1):
                        batch_depth[target] = source + 3
                else:
                    source = no_batch_depth.get(owner)
                    if source is not None and source + 1 > no_batch_depth.get(target, -1):
                        no_batch_depth[target] = source + 1
                    source = batch_depth.get(owner)
                    if source is not None and source + 1 > batch_depth.get(target, -1):
                        batch_depth[target] = source + 1
        return (
            max(batch_depth.values(), default=0) <= 7
            and (
                not single_batch_layer
                or max(batch_layers.values(), default=0) <= 1
            )
        )

    flat_validation_mode = compact_mode == "flat"
    candidates = (
        []
        if flat_validation_mode
        else sorted(
            (
                (len(indices), owner, target)
                for (owner, target), indices in grouped_indices.items()
                if len(indices) >= 2
            ),
            reverse=True,
        )
    )
    for _count, owner, target in candidates:
        edge = (owner, target)
        selected_edges.add(edge)
        if not selection_is_safe():
            selected_edges.remove(edge)

    batches = []
    batched_indices: set[int] = set()
    for owner, target in selected_edges:
        indices = grouped_indices[(owner, target)]
        batches.append((owner, target, indices))
        batched_indices.update(indices)

    if not batches and not flat_validation_mode:
        return None
    required_indices: set[int] = set()
    for index, node in enumerate(nodes):
        if int(node.instance_target_index) >= 0:
            continue
        if (
            node.camera_type
            or node.light_type
            or node.layers
            or node.extra
            or node.camera_extra
            or node.camera_imager_extra
            or node.light_extra
        ):
            _add_node_ancestors(required_indices, nodes, index)
    plan = {
        "matrix_buffers": flat_matrix_buffers,
        "object_matrices": {},
        "batches": batches,
        "residual_indices": [
            index for index in instance_indices if index not in batched_indices
        ],
        "node_groups": {},
        "owner_layers": {
            owner: prototype_depth.get(owner, 0)
            for owner, _target in selected_edges
        },
        "collection": None,
        "required_indices": required_indices,
    }
    if _profile_enabled():
        _profile_log(
            "compact_static_instance_plan "
            f"nodes={len(nodes)} batches={len(batches)} "
            f"batched={len(batched_indices)} residual={len(instance_indices) - len(batched_indices)} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return plan


def _finish_deferred_scene_nodes(
    state: ImportState,
    mesh_objects: list[bpy.types.Object],
) -> None:
    deferred_build = state.deferred_scene_node_build
    if deferred_build is None:
        return

    profile_detail = _profile_state.stats is not None
    total_started_at = time.perf_counter() if profile_detail else 0.0
    phase_started_at = total_started_at
    nodes = deferred_build["nodes"]
    node_objects = _create_scene_nodes(
        nodes,
        deferred_build["coord_root"],
        deferred_build["collection"],
        deferred_build["prototype_collections"],
        deferred_build["deferred_collection_instances"],
        deferred_build["node_visibility"],
        apply_animation=deferred_build["apply_animation"],
        skip_animation_nodes=deferred_build["skip_animation_nodes"],
        required_indices=deferred_build["required_indices"],
        has_visibility_animation=deferred_build["has_visibility_animation"],
        hide_helper_empties=deferred_build["hide_helper_empties"],
    )
    create_nodes_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile_detail else 0.0
    state.node_objects = node_objects
    state.root_objects = _scene_root_objects(
        nodes,
        state.coord_root,
        node_objects,
    )
    state.deferred_scene_node_build = None
    parent_cache = state.node_parent_cache
    if parent_cache is not None:
        parent_cache.clear()

    phase_started_at = time.perf_counter() if profile_detail else 0.0
    for obj in mesh_objects:
        try:
            node_index = int(obj.get("assetkit_node_index", -1))
        except Exception:
            continue
        if node_index < 0:
            continue
        parent, _use_node_parent = _mesh_node_parent(state, node_index)
        if parent is not None and obj.parent is not parent:
            _set_parent(obj, parent)
    parent_ms = (time.perf_counter() - phase_started_at) * 1000.0 if profile_detail else 0.0
    if profile_detail:
        _profile_log(
            "finish_deferred_scene_nodes "
            f"mesh_objects={len(mesh_objects)} node_objects={len(node_objects)} "
            f"create_nodes={create_nodes_ms:.3f}ms parent={parent_ms:.3f}ms "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )


def _prebuild_material_cache(
    primitives: list[MeshPrimitiveData],
    material_cache: dict[object, bpy.types.Material],
    texture_load_mode: str,
) -> dict[int, bpy.types.Material | None] | None:
    if texture_load_mode == "DEFERRED" or len(primitives) <= _MATERIAL_PREBUILD_PRIMITIVE_LIMIT:
        return None

    profile_detail = _profile_state.stats is not None
    started_at = time.perf_counter() if profile_detail else 0.0
    prebuilt: dict[int, bpy.types.Material | None] = {}
    created = 0
    skipped = 0
    for primitive in primitives:
        cache_key = _material_cache_key_for_data(primitive)
        if cache_key is _materials.NO_MATERIAL_CACHE_KEY:
            prebuilt[id(primitive)] = None
            skipped += 1
            continue
        if cache_key in material_cache:
            prebuilt[id(primitive)] = material_cache[cache_key]
            skipped += 1
            continue
        material = _create_material(primitive, material_cache, cache_key=cache_key)
        prebuilt[id(primitive)] = material
        if material is not None:
            created += 1
        else:
            skipped += 1

    if profile_detail and (created or skipped):
        _profile_log(
            "prebuild_material_cache "
            f"created={created} skipped={skipped} cached={len(material_cache)} "
            f"elapsed={(time.perf_counter() - started_at) * 1000.0:.3f}ms"
        )
    return prebuilt


def _create_import_unit(
    unit: MeshPrimitiveData | list[MeshPrimitiveData],
    state: ImportState,
    collection: bpy.types.Collection,
    shading_mode: str = "AUTO",
) -> list[bpy.types.Object]:
    if state.dynamic_skin_animation_skip:
        _mark_skinned_node_animation_skip(state, unit if isinstance(unit, list) else [unit])
    if isinstance(unit, list):
        objects = _create_grouped_mesh_object(unit, state, collection, shading_mode)
        node_index = int(unit[0].node_index) if unit else -1
    else:
        objects = _create_import_object(unit, state, collection, shading_mode)
        node_index = int(unit.node_index)
    _apply_compact_node_matrix(objects, state, node_index)
    return objects


def _apply_compact_node_matrix(
    objects: list[bpy.types.Object],
    state: ImportState,
    node_index: int,
) -> None:
    plan = state.compact_instance_plan
    if plan is None or node_index < 0:
        return
    matrix = _compact_object_matrix(plan, node_index)
    if matrix is None:
        return
    for obj in objects:
        obj.matrix_local = matrix


def _import_result_objects(mesh_objects: list[bpy.types.Object], state: ImportState) -> list[bpy.types.Object]:
    prototype_object_pointers = {
        obj.as_pointer()
        for collection in (state.prototype_collections or {}).values()
        for obj in collection.objects
    }
    node_objects = state.node_objects or {}
    node_data = state.node_data or {}
    result = [
        obj
        for obj in mesh_objects
        if obj.as_pointer() not in prototype_object_pointers
    ]
    result.extend(
        obj
        for index, obj in node_objects.items()
        if int(getattr(node_data.get(index), "prototype_root_index", -1)) < 0
        and int(getattr(node_data.get(index), "instance_target_index", -1)) >= 0
    )
    result.extend(
        obj
        for index, obj in node_objects.items()
        if int(getattr(node_data.get(index), "prototype_root_index", -1)) < 0
        and getattr(obj, "type", "") in {"CAMERA", "LIGHT"}
    )
    result.extend(
        obj
        for obj in (state.compact_instance_objects or ())
        if obj.as_pointer() not in prototype_object_pointers
    )
    result.extend(state.realized_instance_objects or ())
    return _unique_objects(result)


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
    existing_frame_range: tuple[float, float] | None,
    scene_had_timeline_content: bool,
    authored_bounds: tuple[Vector, Vector] | None = None,
) -> None:
    profile_detail = _profile_state.stats is not None
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    bounds = _apply_import_placement(
        objects,
        placement_mode,
        root_objects,
        authored_bounds,
    )
    placement_ms = (
        (time.perf_counter() - phase_started_at) * 1000.0
        if profile_detail
        else 0.0
    )
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    if select_imported:
        _select_imported_objects(objects)
    selection_ms = (
        (time.perf_counter() - phase_started_at) * 1000.0
        if profile_detail
        else 0.0
    )
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    _focus_imported_objects(
        objects,
        focus_mode,
        scene_was_empty,
        collection,
        focus_camera,
        bounds,
    )
    focus_ms = (
        (time.perf_counter() - phase_started_at) * 1000.0
        if profile_detail
        else 0.0
    )
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    if set_viewport_shading and scene_was_empty:
        _set_viewport_material_preview(clean_viewport_overlays)
    shading_ms = (
        (time.perf_counter() - phase_started_at) * 1000.0
        if profile_detail
        else 0.0
    )
    phase_started_at = time.perf_counter() if profile_detail else 0.0
    _fit_timeline_to_new_actions(
        existing_actions,
        existing_frame_range,
        preserve_existing_scene=(not scene_was_empty and scene_had_timeline_content),
    )
    if profile_detail:
        _profile_log(
            "finish_import_detail "
            f"precomputed_bounds={authored_bounds is not None} "
            f"placement={placement_ms:.3f}ms selection={selection_ms:.3f}ms "
            f"focus={focus_ms:.3f}ms shading={shading_ms:.3f}ms "
            f"timeline={(time.perf_counter() - phase_started_at) * 1000.0:.3f}ms"
        )


def _snapshot_actions(enabled: bool) -> set[bpy.types.Action] | None:
    return set(bpy.data.actions) if enabled else None


def _snapshot_scene_frame_range(enabled: bool) -> tuple[float, float] | None:
    if not enabled:
        return None
    scene = bpy.context.scene
    return float(scene.frame_start), float(scene.frame_end)


def _scene_has_timeline_content(scene: bpy.types.Scene) -> bool:
    return any(True for _obj in scene.objects)


def _fit_timeline_to_new_actions(
    existing_actions: set[bpy.types.Action] | None,
    existing_frame_range: tuple[float, float] | None,
    preserve_existing_scene: bool = False,
) -> None:
    if existing_actions is None:
        return

    preserve_existing = preserve_existing_scene or bool(existing_actions)
    if _animation.ACTION_FRAME_RANGES:
        min_frame = min(frame_range[0] for frame_range in _animation.ACTION_FRAME_RANGES.values())
        max_frame = max(frame_range[1] for frame_range in _animation.ACTION_FRAME_RANGES.values())
        min_frame, max_frame = _set_scene_frame_range(
            min_frame,
            max_frame,
            preserve_existing=preserve_existing,
            existing_frame_range=existing_frame_range,
        )
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

    min_frame, max_frame = _set_scene_frame_range(
        min_frame,
        max_frame,
        preserve_existing=preserve_existing,
        existing_frame_range=existing_frame_range,
    )


def _set_scene_frame_range(
    min_frame: float,
    max_frame: float,
    preserve_existing: bool = False,
    existing_frame_range: tuple[float, float] | None = None,
) -> tuple[float, float]:
    scene = bpy.context.scene
    if preserve_existing:
        existing_start, existing_end = (
            existing_frame_range
            if existing_frame_range is not None
            else (float(scene.frame_start), float(scene.frame_end))
        )
        min_frame = min(existing_start, min_frame)
        max_frame = max(existing_end, max_frame)

    scene.frame_start = int(math.floor(max(0.0, min_frame)))
    scene.frame_end = max(scene.frame_start + 1, int(math.ceil(max_frame)))
    try:
        scene.frame_current = scene.frame_start
    except Exception:
        pass
    return float(scene.frame_start), float(scene.frame_end)
