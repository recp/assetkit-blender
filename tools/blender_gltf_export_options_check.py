#!/usr/bin/env python3
"""Exercise AssetKit glTF export include/data toggles inside Blender.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_gltf_export_options_check.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_GLTF  # noqa: E402
from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402

_AK_MINFILTER_UNSPECIFIED = 6
_AK_MAGFILTER_UNSPECIFIED = 2
_AK_MIPFILTER_UNSPECIFIED = 3
_UNSPECIFIED_FILTERS = (
    _AK_MINFILTER_UNSPECIFIED,
    _AK_MAGFILTER_UNSPECIFIED,
    _AK_MIPFILTER_UNSPECIFIED,
)


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def assert_absent_sampler_filters_stay_unspecified(root: Path) -> None:
    image_name = "unspecified-sampler.png"
    (root / image_name).write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = {
        "asset": {"version": "2.0"},
        "images": [{"uri": image_name}],
        "samplers": [{}],
        "textures": [{"sampler": 0, "source": 0}],
        "materials": [{
            "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}
        }],
        "buffers": [{
            "byteLength": 36,
            "uri": "data:application/octet-stream;base64,"
                   + base64.b64encode(
                       b"\x00\x00\x00\x00" * 9
                   ).decode("ascii"),
        }],
        "bufferViews": [{"buffer": 0, "byteLength": 36}],
        "accessors": [{
            "bufferView": 0,
            "componentType": 5126,
            "count": 3,
            "type": "VEC3",
        }],
        "meshes": [{
            "primitives": [{"attributes": {"POSITION": 0}, "material": 0}]
        }],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    path = root / "unspecified-sampler.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = native_load_meshes(
        os.fspath(path),
        make_load_options(
            coordinate_system="Y_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading="DEFERRED",
        ),
    )
    if loaded is None or not loaded.meshes:
        raise AssertionError("failed to load absent-filter sampler fixture")
    info = (loaded.meshes[0].texture_infos or {}).get("base_color")
    if info is None or (info.min_filter, info.mag_filter, info.mip_filter) != _UNSPECIFIED_FILTERS:
        raise AssertionError(
            "absent glTF sampler filters became authored values: "
            f"{None if info is None else (info.min_filter, info.mag_filter, info.mip_filter)}"
        )

    reset_scene()
    imported = import_assetkit_file(
        os.fspath(path),
        load_options=make_load_options(texture_loading="IMMEDIATE"),
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    if not imported:
        raise AssertionError("absent-filter fixture did not import into Blender")
    image_nodes = [
        node
        for material in bpy.data.materials
        if material.node_tree
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE"
    ]
    filter_keys = (
        "assetkit_texture_min_filter",
        "assetkit_texture_mag_filter",
        "assetkit_texture_mip_filter",
    )
    if len(image_nodes) != 1 or tuple(
        int(image_nodes[0].get(key, -1)) for key in filter_keys
    ) != _UNSPECIFIED_FILTERS:
        raise AssertionError("Blender did not retain UNSPECIFIED sampler metadata")

    exported_path = root / "unspecified-sampler-roundtrip.gltf"
    result = export_scene(bpy.context, exported_path, AK_FILE_TYPE_GLTF)
    if result < 0:
        raise AssertionError(f"absent-filter round-trip export failed: {result}")
    exported = json.loads(exported_path.read_text(encoding="utf-8"))
    for sampler in exported.get("samplers", []):
        if "minFilter" in sampler or "magFilter" in sampler:
            raise AssertionError(f"absent filters became explicit on round-trip: {sampler}")


def make_material() -> bpy.types.Material:
    material = bpy.data.materials.new("TexturedMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        raise AssertionError("Principled BSDF node is missing")

    bsdf.inputs["Metallic"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["IOR"].default_value = 1.0

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


def make_unlit_line_scene() -> tuple[float, float, float, float]:
    reset_scene()
    expected = (0.25, 0.125, 0.0625, 1.0)

    mesh = bpy.data.meshes.new("UnlitLineMesh")
    mesh.from_pydata([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1)], [])
    mesh.update()

    material = bpy.data.materials.new("UnlitLineMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    output = nodes.get("Material Output")
    if output is None:
        raise AssertionError("Material Output node is missing")
    surface = output.inputs.get("Surface")
    if surface is None:
        raise AssertionError("Material Output surface socket is missing")
    for link in list(surface.links):
        material.node_tree.links.remove(link)
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = expected
    material.node_tree.links.new(emission.outputs["Emission"], surface)

    obj = bpy.data.objects.new("UnlitLine", mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(material)
    return expected


def export_case(out_root: Path, name: str, **kwargs) -> dict:
    make_scene()
    path = out_root / f"{name}.gltf"
    result = export_scene(bpy.context, path, AK_FILE_TYPE_GLTF, **kwargs)
    if result < 0:
        raise AssertionError(f"export failed for {name}: {result}")
    return json.loads(path.read_text(encoding="utf-8"))


def export_unlit_line_case(out_root: Path) -> tuple[dict, tuple[float, float, float, float]]:
    expected = make_unlit_line_scene()
    path = out_root / "unlit_line.gltf"
    result = export_scene(bpy.context, path, AK_FILE_TYPE_GLTF)
    if result < 0:
        raise AssertionError(f"unlit line export failed: {result}")
    return json.loads(path.read_text(encoding="utf-8")), expected


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


def assert_ior_roundtrip(path: Path, texture_loading: str) -> None:
    reset_scene()
    imported = import_assetkit_file(
        str(path),
        load_options=make_load_options(texture_loading=texture_loading),
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    if not imported:
        raise AssertionError(f"IOR round-trip import returned no objects in {texture_loading} mode")

    materials = [
        material
        for material in bpy.data.materials
        if not bool(material.get("assetkit_internal_template", False))
    ]
    if len(materials) != 1:
        raise AssertionError(f"IOR round-trip produced {len(materials)} materials in {texture_loading} mode")

    material = materials[0]
    bsdf = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    socket = bsdf.inputs.get("IOR") if bsdf else None
    if socket is None or abs(float(socket.default_value) - 1.0) > 1.0e-6:
        raise AssertionError(f"IOR socket changed in {texture_loading} mode")
    if abs(float(material.get("assetkit_ior", 1.5)) - 1.0) > 1.0e-6:
        raise AssertionError(f"assetkit_ior changed in {texture_loading} mode")


def run_checks(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    assert_absent_sampler_filters_stay_unspecified(out_root)

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
    ior = data["materials"][0].get("extensions", {}).get("KHR_materials_ior", {}).get("ior")
    if ior != 1.0:
        raise AssertionError(f"default export changed IOR: {ior!r}")
    for texture_loading in ("IMMEDIATE", "DEFERRED"):
        assert_ior_roundtrip(out_root / "default.gltf", texture_loading)

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

    data, expected = export_unlit_line_case(out_root)
    line_primitives = [prim for prim in primitives(data) if prim.get("mode") == 1]
    if len(line_primitives) != 1:
        raise AssertionError(f"unlit line export wrote {len(line_primitives)} line primitives")
    materials = data.get("materials") or []
    if len(materials) != 1:
        raise AssertionError(f"unlit line export wrote {len(materials)} materials")
    material = materials[0]
    if "KHR_materials_unlit" not in material.get("extensions", {}):
        raise AssertionError("unlit line material lost KHR_materials_unlit")
    actual = material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
    if actual is None or any(abs(float(a) - float(b)) > 1.0e-6 for a, b in zip(actual, expected)):
        raise AssertionError(f"unlit line color changed: expected {expected}, got {actual}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(tempfile.mkdtemp(prefix="assetkit-gltf-options-")))
    args = parser.parse_args(argv)
    run_checks(args.out)
    print(f"glTF export option checks passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
