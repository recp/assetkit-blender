#!/usr/bin/env python3
"""Exercise AssetKit glTF export include/data toggles inside Blender.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_gltf_export_options_check.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_GLTF  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material() -> bpy.types.Material:
    material = bpy.data.materials.new("TexturedMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        raise AssertionError("Principled BSDF node is missing")

    bsdf.inputs["Metallic"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.55

    image = bpy.data.images.new("TinyBaseColor", width=2, height=2)
    image.pixels.foreach_set(
        [
            1.0, 0.0, 0.0, 1.0,
            0.0, 1.0, 0.0, 1.0,
            0.0, 0.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
        ]
    )
    image.update()

    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def make_scene() -> None:
    reset_scene()

    mesh = bpy.data.meshes.new("OptionMesh")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ],
        [],
        [(0, 1, 2), (0, 1, 3)],
    )
    mesh.update()

    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_values = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    for poly in mesh.polygons:
        for corner, loop_index in enumerate(poly.loop_indices):
            uv_layer.data[loop_index].uv = uv_values[corner]

    color_attr = mesh.color_attributes.new(name="Color", type="BYTE_COLOR", domain="CORNER")
    colors = [
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 1.0),
        (0.0, 0.0, 1.0, 1.0),
    ]
    for poly in mesh.polygons:
        for corner, loop_index in enumerate(poly.loop_indices):
            color_attr.data[loop_index].color = colors[corner]

    obj = bpy.data.objects.new("AnimatedMesh", mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(make_material())

    basis = obj.shape_key_add(name="Basis")
    shape = obj.shape_key_add(name="Raised")
    shape.data[2].co.z += 0.25
    basis.value = 0.0
    shape.value = 0.5

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.location = (0.0, 0.0, 0.0)
    obj.keyframe_insert(data_path="location", frame=1)
    obj.location = (1.0, 0.0, 0.0)
    obj.keyframe_insert(data_path="location", frame=10)

    bpy.ops.object.light_add(type="POINT", location=(0.0, -2.0, 2.0))
    bpy.context.object.name = "PointLight"
    bpy.ops.object.camera_add(location=(0.0, -4.0, 2.0), rotation=(1.1, 0.0, 0.0))
    bpy.context.object.name = "Camera"


def export_case(out_root: Path, name: str, **kwargs) -> dict:
    make_scene()
    path = out_root / f"{name}.gltf"
    result = export_scene(bpy.context, path, AK_FILE_TYPE_GLTF, **kwargs)
    if result < 0:
        raise AssertionError(f"export failed for {name}: {result}")
    return json.loads(path.read_text(encoding="utf-8"))


def primitives(data: dict) -> list[dict]:
    out = []
    for mesh in data.get("meshes", []):
        out.extend(mesh.get("primitives", []))
    return out


def first_attributes(data: dict) -> dict:
    prims = primitives(data)
    if not prims:
        raise AssertionError("exported glTF has no primitives")
    return prims[0].get("attributes", {})


def assert_no_light_payload(data: dict) -> None:
    lights = data.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights")
    if lights:
        raise AssertionError("lights were exported while export_lights=False")
    for node in data.get("nodes", []):
        if "camera" in node:
            raise AssertionError("camera node payload was exported while export_cameras=False")
        light_ext = node.get("extensions", {}).get("KHR_lights_punctual")
        if light_ext:
            raise AssertionError("light node payload was exported while export_lights=False")


def run_checks(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    data = export_case(out_root, "default")
    attrs = first_attributes(data)
    if "NORMAL" not in attrs or "TEXCOORD_0" not in attrs or "COLOR_0" not in attrs:
        raise AssertionError(f"default mesh attributes are incomplete: {sorted(attrs)}")
    if not data.get("materials"):
        raise AssertionError("default export did not write materials")
    if not data.get("images") or not data.get("textures"):
        raise AssertionError("default export did not write image textures")
    if not data.get("animations"):
        raise AssertionError("default export did not write transform animations")

    data = export_case(out_root, "no_scene_payloads", export_cameras=False, export_lights=False)
    if data.get("cameras"):
        raise AssertionError("cameras were exported while export_cameras=False")
    assert_no_light_payload(data)

    data = export_case(out_root, "no_materials", export_materials=False)
    if data.get("materials"):
        raise AssertionError("materials were exported while export_materials=False")
    for prim in primitives(data):
        if "material" in prim:
            raise AssertionError("primitive material binding exists while export_materials=False")

    data = export_case(out_root, "no_images", export_images=False)
    if not data.get("materials"):
        raise AssertionError("materials should remain when only export_images=False")
    if data.get("images") or data.get("textures"):
        raise AssertionError("image or texture payloads were exported while export_images=False")

    data = export_case(
        out_root,
        "no_mesh_data",
        export_uv=False,
        export_normals=False,
        export_tangents=False,
        export_vertex_colors=False,
    )
    attrs = first_attributes(data)
    forbidden = [key for key in attrs if key == "NORMAL" or key.startswith(("TEXCOORD", "COLOR"))]
    if forbidden:
        raise AssertionError(f"disabled mesh attributes were exported: {forbidden}")

    data = export_case(out_root, "no_animation", export_animations=False)
    if data.get("animations"):
        raise AssertionError("animations were exported while export_animations=False")

    data = export_case(out_root, "no_shape_keys", export_shape_keys=False)
    for prim in primitives(data):
        if prim.get("targets"):
            raise AssertionError("shape key targets were exported while export_shape_keys=False")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(tempfile.mkdtemp(prefix="assetkit-gltf-options-")))
    args = parser.parse_args(argv)
    run_checks(args.out)
    print(f"glTF export option checks passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
