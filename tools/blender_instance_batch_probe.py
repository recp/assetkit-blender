"""Compare Blender object instances with a matrix-attribute Geometry Nodes batch.

Run with:
  blender --background --factory-startup --python tools/blender_instance_batch_probe.py -- objects 7966 0
  blender --background --factory-startup --python tools/blender_instance_batch_probe.py -- batch 7966 0
"""

from __future__ import annotations

import json
import math
import sys
import time

import bpy
from mathutils import Matrix, Vector


def _arguments() -> tuple[str, int, int]:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    mode = args[0] if args else "batch"
    count = int(args[1]) if len(args) > 1 else 7_966
    depth = int(args[2]) if len(args) > 2 else 0
    if mode not in {"objects", "batch"}:
        raise ValueError("mode must be 'objects' or 'batch'")
    return mode, count, depth


def _prototype_collection(depth: int) -> tuple[bpy.types.Collection, Matrix]:
    mesh = bpy.data.meshes.new("PrototypeMesh")
    mesh.from_pydata(
        [
            (-0.5, -0.5, -0.5),
            (0.5, -0.5, -0.5),
            (0.5, 0.5, -0.5),
            (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5),
            (0.5, -0.5, 0.5),
            (0.5, 0.5, 0.5),
            (-0.5, 0.5, 0.5),
        ],
        [],
        [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (4, 0, 3, 7),
        ],
    )
    obj = bpy.data.objects.new("Prototype", mesh)
    obj.matrix_world = Matrix.Identity(4)
    collection = bpy.data.collections.new("PrototypeCollection")
    collection.objects.link(obj)
    prototype_matrix = obj.matrix_world.copy()

    for level in range(depth):
        parent = bpy.data.collections.new(f"PrototypeCollection_{level:02d}")
        instance = bpy.data.objects.new(f"PrototypeNested_{level:02d}", None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = collection
        local = (
            Matrix.Translation((0.15 * (level + 1), -0.07 * level, 0.03 * level))
            @ Matrix.Rotation(0.025 * (level + 1), 4, "Z")
        )
        instance.matrix_world = local
        parent.objects.link(instance)
        collection = parent
        prototype_matrix = local @ prototype_matrix
    return collection, prototype_matrix


def _matrix(index: int) -> Matrix:
    columns = 128
    x = float(index % columns) * 1.25
    y = float(index // columns) * 1.25
    z = float(index % 7) * 0.03
    angle = float(index % 31) * (math.pi / 62.0)
    scale = 0.8 + float(index % 5) * 0.05
    return (
        Matrix.Translation((x, y, z))
        @ Matrix.Rotation(angle, 4, "Z")
        @ Matrix.Diagonal((scale, scale, scale, 1.0))
    )


def _build_objects(
    staging: bpy.types.Collection,
    prototype: bpy.types.Collection,
    count: int,
) -> None:
    for index in range(count):
        obj = bpy.data.objects.new(f"Instance_{index:06d}", None)
        obj.instance_type = "COLLECTION"
        obj.instance_collection = prototype
        obj.matrix_world = _matrix(index)
        staging.objects.link(obj)


def _batch_node_group(
    prototype: bpy.types.Collection,
) -> bpy.types.GeometryNodeTree:
    group = bpy.data.node_groups.new("AssetKitInstanceBatch", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    group_input = group.nodes.new("NodeGroupInput")
    group_output = group.nodes.new("NodeGroupOutput")
    collection_info = group.nodes.new("GeometryNodeCollectionInfo")
    collection_info.inputs["Collection"].default_value = prototype
    instance_on_points = group.nodes.new("GeometryNodeInstanceOnPoints")
    matrix_attribute = group.nodes.new("GeometryNodeInputNamedAttribute")
    matrix_attribute.data_type = "FLOAT4X4"
    matrix_attribute.inputs["Name"].default_value = "assetkit_instance_matrix"
    set_transform = group.nodes.new("GeometryNodeSetInstanceTransform")

    group.links.new(group_input.outputs["Geometry"], instance_on_points.inputs["Points"])
    group.links.new(collection_info.outputs["Instances"], instance_on_points.inputs["Instance"])
    group.links.new(instance_on_points.outputs["Instances"], set_transform.inputs["Instances"])
    group.links.new(matrix_attribute.outputs["Attribute"], set_transform.inputs["Transform"])
    group.links.new(set_transform.outputs["Instances"], group_output.inputs["Geometry"])
    return group


def _build_batch(
    staging: bpy.types.Collection,
    prototype: bpy.types.Collection,
    count: int,
) -> None:
    mesh = bpy.data.meshes.new("AssetKitInstancePoints")
    mesh.vertices.add(count)
    mesh.vertices.foreach_set("co", [0.0] * (count * 3))

    attribute = mesh.attributes.new(
        "assetkit_instance_matrix",
        type="FLOAT4X4",
        domain="POINT",
    )
    matrices = [
        value
        for index in range(count)
        for row in _matrix(index).transposed()
        for value in row
    ]
    attribute.data.foreach_set("value", matrices)

    obj = bpy.data.objects.new("AssetKitInstanceBatch", mesh)
    staging.objects.link(obj)
    modifier = obj.modifiers.new("AssetKitInstanceBatch", "NODES")
    modifier.node_group = _batch_node_group(prototype)


def main() -> None:
    mode, count, depth = _arguments()
    scene = bpy.context.scene
    root = scene.collection
    for child in list(root.children):
        root.children.unlink(child)

    prototype, prototype_matrix = _prototype_collection(depth)
    staging = bpy.data.collections.new("Staging")

    build_start = time.perf_counter()
    if mode == "objects":
        _build_objects(staging, prototype, count)
    else:
        _build_batch(staging, prototype, count)
    build_ms = (time.perf_counter() - build_start) * 1_000.0

    publish_start = time.perf_counter()
    root.children.link(staging)
    publish_ms = (time.perf_counter() - publish_start) * 1_000.0

    update_start = time.perf_counter()
    bpy.context.view_layer.update()
    update_ms = (time.perf_counter() - update_start) * 1_000.0

    validation_start = time.perf_counter()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_instances = 0
    expected_by_translation = {
        tuple(
            round(value, 2)
            for value in (_matrix(index) @ prototype_matrix).translation
        ): _matrix(index) @ prototype_matrix
        for index in range(count)
    }
    matched_instances = 0
    max_matrix_error = 0.0
    for item in depsgraph.object_instances:
        evaluated_instances += 1
        if not item.is_instance:
            continue
        if item.object.type != "MESH" or item.object.name != "Prototype":
            continue
        matrix = item.matrix_world
        expected = expected_by_translation.get(
            tuple(round(value, 2) for value in matrix.translation)
        )
        if expected is None:
            continue
        matched_instances += 1
        max_matrix_error = max(
            max_matrix_error,
            max(
                abs(float(matrix[row][column]) - float(expected[row][column]))
                for row in range(4)
                for column in range(4)
            ),
        )
    batch_object = bpy.data.objects.get("AssetKitInstanceBatch")
    evaluated_bounds = None
    if batch_object is not None:
        evaluated = batch_object.evaluated_get(depsgraph)
        corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
        evaluated_bounds = [
            [min(point[axis] for point in corners) for axis in range(3)],
            [max(point[axis] for point in corners) for axis in range(3)],
        ]
    validation_ms = (time.perf_counter() - validation_start) * 1_000.0

    print(
        "ASSETKIT_INSTANCE_BATCH_PROBE="
        + json.dumps(
            {
                "mode": mode,
                "count": count,
                "prototype_depth": depth,
                "build_ms": build_ms,
                "publish_ms": publish_ms,
                "view_layer_update_ms": update_ms,
                "validation_ms": validation_ms,
                "evaluated_instances": evaluated_instances,
                "matched_instances": matched_instances,
                "max_matrix_error": max_matrix_error,
                "evaluated_bounds": evaluated_bounds,
                "objects": len(bpy.data.objects),
                "collections": len(bpy.data.collections),
                "meshes": len(bpy.data.meshes),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
