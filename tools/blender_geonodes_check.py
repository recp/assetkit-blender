#!/usr/bin/env python3
"""Exercise file sources and sequence caching in a factory-startup Blender."""

import argparse
import json
import math
import os
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy
import addon_utils


def ply(path, x):
    fields = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
              "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    row = [x, 0, 0, -2, 0, 2, 0, 0, math.log(2), 0, 1, 0, 0, 0]
    path.write_text("ply\nformat ascii 1.0\nelement vertex 1\n"
                    + "".join(f"property float {name}\n" for name in fields)
                    + "end_header\n" + " ".join(map(str, row)) + "\n")


def gltf(path):
    payload = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    path.with_suffix(".bin").write_bytes(payload)
    path.write_text(json.dumps({
        "asset": {"version": "2.0"}, "scene": 0,
        "scenes": [{"name": "Main", "nodes": [0]}, {"name": "Other", "nodes": [3]}],
        "nodes": [{"name": "Root", "translation": [10, 0, 0], "children": [1, 2]},
                  {"name": "Left", "mesh": 0, "translation": [1, 0, 0]},
                  {"name": "Right", "mesh": 0, "translation": [2, 0, 0]},
                  {"name": "Other", "mesh": 0, "translation": [30, 0, 0]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [0, 0, 0], "max": [1, 1, 0]}],
        "bufferViews": [{"buffer": 0, "byteLength": len(payload)}],
        "buffers": [{"uri": path.with_suffix(".bin").name, "byteLength": len(payload)}],
    }))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--spz", type=Path)
    parser.add_argument("--lgsc", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    sys.path.insert(0, str(args.package_root))
    import assetkit_blender
    from assetkit_blender.geonodes import cache as cache_module
    from assetkit_blender.geonodes import runtime
    from assetkit_blender.geonodes.cache import CACHE, OWNER, PATH, sequence_path
    from assetkit_blender.geonodes.groups import get_group
    from assetkit_blender.geonodes.nodes import menu, menu_import

    assert addon_utils.enable("assetkit_blender", default_set=False) is not None
    assert bpy.app.timers.is_registered(runtime.rebuild)
    bpy.app.timers.unregister(runtime.rebuild)
    runtime.rebuild()
    assert bpy.types.NODE_MT_add.draw._draw_funcs.count(menu) == 1
    assert bpy.types.NODE_MT_add.draw._draw_funcs[0] is menu
    assert bpy.types.NODE_MT_category_import.draw._draw_funcs.count(menu_import) == 1
    assert bpy.types.NODE_MT_category_import.draw._draw_funcs[0] is menu_import

    class MenuLayout:
        def __init__(self):
            self.items = []

        def separator(self):
            self.items.append("separator")

        def menu(self, name):
            self.items.append(name)

        def operator(self, name, **kwargs):
            props = SimpleNamespace()
            self.items.append((name, kwargs, props))
            return props

    layout = MenuLayout()
    context = SimpleNamespace(space_data=SimpleNamespace(tree_type="GeometryNodeTree"))
    menu(SimpleNamespace(layout=layout), context)
    assert layout.items == ["ASSETKIT_MT_geometry_nodes", "separator"]
    layout.items.clear()
    menu_import(SimpleNamespace(layout=layout), context)
    assert layout.items[1] == "separator"
    operator, labels, props = layout.items[0]
    assert operator == "node.add_node" and labels["text"] == "AssetKit File / Sequence"
    assert props.type == "AssetKitGeometrySource" and props.use_transform
    context.space_data.tree_type = "ShaderNodeTree"
    menu(SimpleNamespace(layout=layout), context)
    menu_import(SimpleNamespace(layout=layout), context)
    assert len(layout.items) == 2
    print("Add / Input Import menu registration and node target OK")
    initial_lock = bpy.context.scene.render.use_lock_interface
    bpy.context.scene["assetkit_scene_name"] = "User Scene"
    bpy.context.scene.world["assetkit_document_extra_json"] = "User World"
    assert runtime.frame_changed not in bpy.app.handlers.frame_change_pre
    tree = bpy.data.node_groups.new("Source Check", "GeometryNodeTree")
    tree.use_fake_user = True

    def source(path, valid=True):
        node = tree.nodes.new("AssetKitGeometrySource")
        node.filepath = str(path)
        runtime.flush()
        if valid:
            assert "No geometry" not in node.status, node.status
        return node

    def collection(node):
        return node.node_tree.nodes["Source"].inputs["Collection"].default_value

    def clear():
        for node in tuple(tree.nodes):
            tree.nodes.remove(node)
        CACHE.trim(0)

    def evaluated_mesh(node, group=None, values=None, points=False):
        graph = bpy.data.node_groups.new("Source Evaluation", "GeometryNodeTree")
        graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        src = graph.nodes.new("GeometryNodeGroup")
        src.node_tree = node.node_tree
        previous = src.outputs["Geometry"]
        if group:
            operation = graph.nodes.new("GeometryNodeGroup")
            operation.node_tree = get_group(group)
            graph.links.new(previous, operation.inputs["Geometry"])
            for name, value in (values or {}).items():
                operation.inputs[name].default_value = value
            previous = operation.outputs["Geometry"]
        realize = graph.nodes.new("GeometryNodeRealizeInstances")
        graph.links.new(previous, realize.inputs["Geometry"])
        previous = realize.outputs["Geometry"]
        if points:
            convert = graph.nodes.new("GeometryNodePointsToVertices")
            graph.links.new(previous, convert.inputs["Points"])
            previous = convert.outputs["Mesh"]
        output = graph.nodes.new("NodeGroupOutput")
        graph.links.new(previous, output.inputs["Geometry"])
        mesh = bpy.data.meshes.new("Source Evaluation")
        obj = bpy.data.objects.new("Source Evaluation", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.modifiers.new("Source", "NODES").node_group = graph
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        result = evaluated.to_mesh()
        positions = [tuple(vertex.co) for vertex in result.vertices]
        base = result.attributes.get("radiance:base")
        colors = [tuple(value.color) for value in base.data] if base else []
        evaluated.to_mesh_clear()
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        bpy.data.node_groups.remove(graph)
        return positions, colors

    try:
        for kind in ("OBJECT", "CROP", "OPACITY"):
            group = get_group(kind)
            assert group == get_group(kind)
            print("Group OK:", group.name)
        with tempfile.TemporaryDirectory(prefix="assetkit-source-files-") as directory:
            folder = Path(directory)
            for frame in range(1, 4):
                ply(folder / f"capture_{frame:04d}.ply", frame)
            a = source(folder / "capture_0001.ply")
            assert len(collection(a).objects) == 1
            assert next(iter(collection(a).objects)).type == "POINTCLOUD"
            count = CACHE.loads
            b = source(folder / "capture_0001.ply")
            assert collection(a) == collection(b)
            assert CACHE.loads == count
            for _ in range(10):
                runtime.changed(a)
                runtime.flush()
            assert CACHE.loads == count
            print("Static sharing / no repeated decode OK")
            positions, original = evaluated_mesh(a, points=True)
            assert len(positions) == 1, positions
            original_position = positions[0]
            assert original, "Radiance attribute lost during evaluation"
            _, faded = evaluated_mesh(a, "OPACITY", {"Opacity": 0.25}, points=True)
            assert faded[0][:3] == original[0][:3], (faded, original)
            assert abs(faded[0][3] - original[0][3] * 0.25) < 1e-6
            removed, _ = evaluated_mesh(a, "CROP", {"Min": (20, 20, 20), "Max": (30, 30, 30)}, points=True)
            assert not removed, removed
            assert CACHE.loads == count
            print("Actual node evaluation / opacity / crop OK")

            a.filepath = str(folder / "capture_####.ply")
            a.sequence = True
            assert runtime.frame_changed in bpy.app.handlers.frame_change_pre
            a.first_frame, a.last_frame = 1, 3
            runtime.flush()
            bpy.context.scene.frame_set(2)
            second = collection(a)
            assert CACHE.loads == count + 1
            assert second != collection(b)
            bpy.context.scene.frame_set(1)
            assert collection(a) == collection(b)
            bpy.context.scene.frame_set(2)
            assert collection(a) == second
            assert CACHE.loads == count + 1
            assert sequence_path("a_##.spz", 0, 1, 1, 3, 1, True) == "a_03.spz"
            assert sequence_path("a_##.spz", 6, 1, 1, 3, 2, False) == "a_03.spz"
            print("Sequence frame mapping / cache reuse OK")

            a.last_frame = 4
            runtime.flush()
            bpy.context.scene.frame_set(4)
            assert collection(a) is None and "No geometry" in a.status
            a.missing = "HOLD"
            bpy.context.scene.frame_set(2)
            bpy.context.scene.frame_set(4)
            assert collection(a) == second and "Holding" in a.status
            bpy.context.scene.frame_set(2)
            assert "Holding" not in a.status, a.status
            bpy.context.scene.frame_set(4)
            a.missing = "EMPTY"
            runtime.flush()
            assert collection(a) is None
            print("Missing frame empty / hold OK")

            path = folder / "scene.gltf"
            gltf(path)
            c = source(path)
            assert len(collection(c).objects) == 2
            positions, _ = evaluated_mesh(c)
            assert len(positions) == 6, positions
            assert abs(min(p[0] for p in positions) - 11) < 1e-5, positions
            assert abs(max(p[0] for p in positions) - 13) < 1e-5, positions
            assert "Main" in c.scene_names and "Other" in c.scene_names
            paths = [item.name for item in c.source_nodes]
            c.node_path = next(path for path in paths if "Left" in path)
            before = CACHE.loads
            runtime.flush()
            assert len(collection(c).objects) == 1
            assert CACHE.loads == before
            assert "Left" in next(iter(collection(c).objects)).get(PATH)
            c.node_path = "/absent"
            runtime.flush()
            assert collection(c) is None
            c.node_path = ""
            c.scene_index = 1
            runtime.flush()
            assert len(collection(c).objects) == 1
            assert "Other" in next(iter(collection(c).objects)).get(PATH)
            c.scene_index = 99
            runtime.flush()
            assert collection(c) is None and "out of range" in c.status, c.status
            c.scene_index = 0
            c.node_path = next(path for path in paths if "Root" in path and "Left" not in path and "Right" not in path)
            runtime.flush()
            assert len(collection(c).objects) == 2
            assert bpy.context.scene["assetkit_scene_name"] == "User Scene"
            assert bpy.context.scene.world["assetkit_document_extra_json"] == "User World"
            print("Multi-object scene / node selection / alternate scene OK")

            clone = tree.copy()
            runtime.flush()
            cloned = next(node for node in clone.nodes if node.filepath == c.filepath)
            assert collection(cloned) != collection(c)
            cloned.node_path = next(path for path in paths if "Left" in path)
            runtime.flush()
            assert len(collection(cloned).objects) == 1 and len(collection(c).objects) == 2
            for node in tuple(clone.nodes):
                clone.nodes.remove(node)
            bpy.data.node_groups.remove(clone)
            print("Copied nodes keep independent selections OK")

            changed = folder / "capture_0001.ply"
            previous = collection(b)
            before = CACHE.loads
            stamp = changed.stat().st_mtime_ns
            ply(changed, 10)
            os.utime(changed, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
            runtime.changed(b)
            runtime.flush()
            assert collection(b) != previous and CACHE.loads == before + 1
            positions, _ = evaluated_mesh(b, points=True)
            assert abs(positions[0][0] - original_position[0] * 10) < 1e-5, positions
            print("Changed source fingerprint / fresh geometry OK")

            bad = folder / "invalid.ply"
            bad.write_text("not a PLY file\n")
            attempts = []
            original_load = cache_module.load

            def counted_load(key):
                attempts.append(key)
                return original_load(key)

            cache_module.load = counted_load
            try:
                invalid = [source(bad, valid=False), source(bad, valid=False)]
            finally:
                cache_module.load = original_load
            assert len(attempts) == 1, attempts
            assert all(collection(node) is None for node in invalid)
            for node in invalid:
                tree.nodes.remove(node)
            print("Invalid sources share failure cache OK")

            borrowed_entry = CACHE.get(cache_module.fingerprint(str(folder / "capture_0003.ply"), -1))
            borrowed_data = next(iter(borrowed_entry.collection.objects)).data
            borrowed_object = bpy.data.objects.new("User Copy", borrowed_data)
            bpy.context.scene.collection.objects.link(borrowed_object)
            CACHE.trim(0)
            assert len(borrowed_object.data.points) == 1
            bpy.data.objects.remove(borrowed_object, do_unlink=True)
            cache_module._dispose(borrowed_entry.ids)
            print("User-referenced data survives cache eviction OK")

            if args.spz:
                source(args.spz)
            if args.lgsc:
                source(args.lgsc)

            before = CACHE.loads
            path.with_suffix(".bin").write_bytes(struct.pack("<9f", 5, 0, 0, 6, 0, 0, 5, 1, 0))
            runtime.reload_sources()
            assert CACHE.loads > before
            positions, _ = evaluated_mesh(c)
            assert abs(min(p[0] for p in positions) - 16) < 1e-5, positions
            print("Explicit reload OK")
            runtime.render_start(bpy.context.scene)
            assert bpy.context.scene.render.use_lock_interface
            runtime.render_end(bpy.context.scene)

            # Rebuild runtime state like load/undo: restored IDs must be reused.
            before = CACHE.loads
            runtime.rebuild()
            runtime.flush()
            assert CACHE.loads == before
            print("Runtime restore / handler lifecycle OK")

            a.missing = "EMPTY"
            bpy.context.scene.frame_set(1)
            blend_path = folder / "sources.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
            before = CACHE.loads
            bpy.ops.wm.open_mainfile(filepath=str(blend_path))
            tree = bpy.data.node_groups["Source Check"]
            a = next(node for node in tree.nodes if node.sequence)
            b = next(node for node in tree.nodes if node.filepath.endswith("capture_0001.ply"))
            runtime.flush()
            assert CACHE.loads == before, (CACHE.loads, before)
            assert collection(a) == collection(b)
            print("Actual .blend save / reopen without decode OK")

            scene = bpy.context.scene
            scene.render.engine = "BLENDER_WORKBENCH"
            scene.render.resolution_x = scene.render.resolution_y = 8
            scene.render.resolution_percentage = 100
            scene.render.filepath = str(folder / "render_")
            scene.frame_start, scene.frame_end = 1, 2
            graph = bpy.data.node_groups.new("Render Source", "GeometryNodeTree")
            graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
            src = graph.nodes.new("GeometryNodeGroup")
            src.node_tree = a.node_tree
            output = graph.nodes.new("NodeGroupOutput")
            graph.links.new(src.outputs["Geometry"], output.inputs["Geometry"])
            mesh = bpy.data.meshes.new("Render Source")
            host = bpy.data.objects.new("Render Source", mesh)
            scene.collection.objects.link(host)
            host.modifiers.new("Source", "NODES").node_group = graph
            rendered = []

            def rendered_frame(render_scene, *_args):
                rendered.append((render_scene.frame_current, collection(a).name))

            bpy.app.handlers.render_write.append(rendered_frame)
            before = CACHE.loads
            try:
                bpy.ops.render.render(animation=True)
            finally:
                bpy.app.handlers.render_write.remove(rendered_frame)
                bpy.data.objects.remove(host, do_unlink=True)
                bpy.data.meshes.remove(mesh)
                bpy.data.node_groups.remove(graph)
            assert (folder / "render_0001.png").is_file()
            assert (folder / "render_0002.png").is_file()
            assert len(rendered) == 2, rendered
            assert all(f"capture_{frame:04d}.ply" in name for frame, name in rendered), rendered
            assert CACHE.loads <= before + 1, (CACHE.loads, before)
            print("Actual two-frame render / sequence update OK")

            # Current geometry is pinned even when larger than the cache budget.
            active = collection(a)
            CACHE.trim(1)
            assert active in [entry.collection for entry in CACHE.entries.values()]
            assert all(entry.collection.users for entry in CACHE.entries.values())
            print("Budget eviction / active frame pinning OK")
            clear()
            assert not CACHE.entries, [(key, entry.collection.users) for key, entry in CACHE.entries.items()]
            leaked = [(name, item.name) for name in ("collections", "objects", "pointclouds", "meshes")
                      for item in getattr(bpy.data, name) if item.get(OWNER)]
            assert not leaked, leaked
            assert runtime.frame_changed not in bpy.app.handlers.frame_change_pre
            assert bpy.context.scene.render.use_lock_interface == initial_lock
            print("Cache disposal / no owned geometry leaks OK")
    finally:
        clear()
        bpy.data.node_groups.remove(tree)
        addon_utils.disable("assetkit_blender", default_set=False)
        assert not bpy.app.timers.is_registered(runtime.rebuild)
        assert menu not in bpy.types.NODE_MT_add.draw._draw_funcs
        assert menu_import not in bpy.types.NODE_MT_category_import.draw._draw_funcs
    print("AssetKit Geometry Nodes checks passed")


if __name__ == "__main__":
    main()
