#!/usr/bin/env python3
"""Check Gaussian conversion groups and coordinate/scale parity in standard Blender."""

import math
import base64
import json
from pathlib import Path
import sys
import struct
import tempfile
import time

import addon_utils
import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from assetkit_blender.geonodes.groups import get_group
from assetkit_blender.geonodes import runtime
from assetkit_blender.geonodes.cache import CACHE
from assetkit_blender.gsplat_preview import pointcloud, is_splat, enable, DISPLAY
from assetkit_blender.importer import import_assetkit_file, import_assetkit_file_progressive
from assetkit_blender.load_options import make_load_options


def values(cloud, name, width, field, dtype=np.float32):
    array = np.empty(len(cloud.points) * width, dtype=dtype)
    cloud.attributes[name].data.foreach_get(field, array)
    return array.reshape(-1, width)


def main():
    assert addon_utils.enable("assetkit_blender", default_set=False)
    mesh = bpy.data.meshes.new("Point source")
    mesh.from_pydata([(1, 2, 3), (4, 5, 6)], [], [])
    obj = bpy.data.objects.new("Point source", mesh)
    bpy.context.scene.collection.objects.link(obj)
    tree = bpy.data.node_groups.new("Conversion check", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    inp = tree.nodes.new("NodeGroupInput")
    out = tree.nodes.new("NodeGroupOutput")
    points = tree.nodes.new("GeometryNodeMeshToPoints")
    points.mode = "VERTICES"
    tree.links.new(inp.outputs["Geometry"], points.inputs["Mesh"])
    splats = tree.nodes.new("GeometryNodeGroup")
    splats.node_tree = get_group("TO_GAUSSIANS")
    splats.inputs["Color"].default_value = (0.02, 0.3, 0.8, 1)
    splats.inputs["Opacity"].default_value = 0.4
    splats.inputs["Scale"].default_value = (0.01, 0.02, 0.03)
    splats.inputs["Rotation"].default_value = (0, 0, math.pi / 2)
    tree.links.new(points.outputs["Points"], splats.inputs["Geometry"])
    tree.links.new(splats.outputs["Geometry"], out.inputs["Geometry"])
    obj.modifiers.new("Gaussian", "NODES").node_group = tree
    bpy.context.view_layer.update()
    assert is_splat(obj), "Mesh hosts with evaluated point clouds must be previewable"
    cloud = pointcloud(obj)
    base = values(cloud, "radiance:base", 4, "color")
    expected = (np.array([0.02, 0.3, 0.8]) - 0.5) / 0.28209479177387814
    np.testing.assert_allclose(base[:, :3], np.tile(expected, (2, 1)), atol=2e-7)
    np.testing.assert_allclose(base[:, 3], 0.4)
    np.testing.assert_array_equal(values(cloud, "assetkit:color_space", 1, "value", np.int32), 2)
    scales = values(cloud, "scale", 3, "vector")
    rotations = values(cloud, "rotation", 4, "value")
    np.testing.assert_allclose(scales, [[0.01, 0.02, 0.03]] * 2)
    np.testing.assert_allclose(rotations, [[math.sqrt(0.5), 0, 0, math.sqrt(0.5)]] * 2, atol=1e-6)

    ordinary = tree.nodes.new("GeometryNodeGroup")
    ordinary.node_tree = get_group("TO_POINTS")
    tree.links.new(splats.outputs["Geometry"], ordinary.inputs["Geometry"])
    tree.links.new(ordinary.outputs["Geometry"], out.inputs["Geometry"])
    bpy.context.view_layer.update()
    assert not is_splat(obj)
    np.testing.assert_array_equal(values(pointcloud(obj), "assetkit:radiance_base", 4, "color"), base)
    restored = tree.nodes.new("GeometryNodeGroup")
    restored.node_tree = get_group("TO_GAUSSIANS")
    tree.links.new(ordinary.outputs["Geometry"], restored.inputs["Geometry"])
    tree.links.new(restored.outputs["Geometry"], out.inputs["Geometry"])
    bpy.context.view_layer.update()
    cloud = pointcloud(obj)
    np.testing.assert_array_equal(values(cloud, "radiance:base", 4, "color"), base)
    np.testing.assert_array_equal(values(cloud, "scale", 3, "vector"), scales)
    np.testing.assert_array_equal(values(cloud, "rotation", 4, "value"), rotations)
    enable(obj)
    assert obj.display_type == "BOUNDS"
    enable(obj, False)
    assert DISPLAY not in obj
    print("Point/Gaussian groups, linear color, quaternion, restoration and evaluated host OK")

    # Exercise the same options through blocking, progressive and source-node paths.
    with tempfile.TemporaryDirectory(prefix="assetkit-import-options-") as directory:
        path = Path(directory) / "points.ply"
        path.write_text("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\n"
                        "property float z\nend_header\n1 2 3\n")
        def positions(objects):
            bpy.context.view_layer.update()
            return [tuple(obj.matrix_world @ vertex.co) for obj in objects if obj.type == "MESH"
                    for vertex in obj.data.vertices]

        for mode, coords in (("TRANSFORM", "Z_UP"), ("ALL", "Y_UP"), ("RAW", "Z_UP")):
            options = make_load_options(coordinate_conversion=mode, coordinate_system=coords)
            normal = import_assetkit_file(str(path), load_options=options, set_viewport_shading=False)
            scaled = import_assetkit_file(str(path), load_options=options, global_scale=3,
                                         set_viewport_shading=False)
            expected = np.array(positions(normal)) * 3
            assert expected.shape == (1, 3)
            np.testing.assert_allclose(positions(scaled), expected)
            completed, errors = [], []
            job = import_assetkit_file_progressive(str(path), load_options=options, global_scale=3,
                    set_viewport_shading=False, on_complete=completed.append, on_error=errors.append)
            if bpy.app.timers.is_registered(job._timer):
                bpy.app.timers.unregister(job._timer)
            deadline = time.monotonic() + 30
            while not job.done and time.monotonic() < deadline:
                job._timer()
                time.sleep(0.001)
            assert job.done and not errors, errors
            np.testing.assert_allclose(positions(completed[0]), expected)

            source = tree.nodes.new("AssetKitGeometrySource")
            source.coordinate_conversion, source.coordinate_system = mode, coords
            source.filepath = str(path)
            runtime.flush()
            count = CACHE.loads
            collection = source.node_tree.nodes["Source"].inputs["Collection"].default_value
            assert collection is not None, source.status
            source.inputs["Global Scale"].default_value = 3
            realize = tree.nodes.new("GeometryNodeRealizeInstances")
            tree.links.new(source.outputs["Geometry"], realize.inputs["Geometry"])
            tree.links.new(realize.outputs["Geometry"], out.inputs["Geometry"])
            bpy.context.view_layer.update()
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            result = evaluated.to_mesh()
            np.testing.assert_allclose([tuple(v.co) for v in result.vertices], expected)
            evaluated.to_mesh_clear()
            runtime.flush()
            assert CACHE.loads == count
            print("Import options parity OK:", mode, coords)

        payload = struct.pack("<17f", 0, 0, 0, 1, 0, 0, 0, 1, 0,
                              0, 1, 1, 0, 0, 2, 0, 0)
        path = Path(directory) / "animated.gltf"
        path.write_text(json.dumps({
            "asset": {"version": "2.0"}, "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"translation": [5, 0, 0], "children": [1, 2]},
                      {"mesh": 0, "translation": [1, 0, 0]}, {"mesh": 0, "translation": [-1, 0, 0]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "buffers": [{"byteLength": len(payload),
                         "uri": "data:application/octet-stream;base64," + base64.b64encode(payload).decode()}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36},
                            {"buffer": 0, "byteOffset": 36, "byteLength": 8},
                            {"buffer": 0, "byteOffset": 44, "byteLength": 24}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                           "min": [0, 0, 0], "max": [1, 1, 0]},
                          {"bufferView": 1, "componentType": 5126, "count": 2, "type": "SCALAR",
                           "min": [0], "max": [1]},
                          {"bufferView": 2, "componentType": 5126, "count": 2, "type": "VEC3"}],
            "animations": [{"samplers": [{"input": 1, "output": 2, "interpolation": "LINEAR"}],
                            "channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}]}],
        }))
        normal = import_assetkit_file(str(path), preserve_hierarchy=True, set_viewport_shading=False)
        scaled = import_assetkit_file(str(path), preserve_hierarchy=True, global_scale=3,
                                     set_viewport_shading=False)
        first = None
        for frame in (1, 7, 25):
            bpy.context.scene.frame_set(frame)
            current = np.array(positions(normal))
            assert current.shape == (6, 3)
            np.testing.assert_allclose(positions(scaled), current * 3, atol=1e-5)
            if first is None:
                first = current.copy()
        assert not np.array_equal(first, current), "Animation must actually move"
        print("Global scale preserves hierarchy, shared geometry and animated transforms OK")


main()
