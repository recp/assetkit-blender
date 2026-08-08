#!/usr/bin/env python3
"""Exercise AssetKit PLY export parity inside Blender.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_ply_export_check.py
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_PLY  # noqa: E402
from assetkit_blender.exp.images import _ExportImageStore  # noqa: E402
from assetkit_blender.exp.material.core import _material_tuple  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def add_cube(name: str, location=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    return obj


def add_plane(name: str) -> bpy.types.Object:
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    return obj


def add_triangle(name: str, with_attrs: bool = False) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()

    if with_attrs:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uvs = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
        for poly in mesh.polygons:
            for corner, loop_index in enumerate(poly.loop_indices):
                uv_layer.data[loop_index].uv = uvs[corner]

        color_attr = mesh.color_attributes.new(name="Color", type="BYTE_COLOR", domain="CORNER")
        colors = [
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
        ]
        for poly in mesh.polygons:
            for corner, loop_index in enumerate(poly.loop_indices):
                color_attr.data[loop_index].color = colors[corner]

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_close_vec(actual, expected, label: str, eps: float = 1.0e-5) -> None:
    if len(actual) != len(expected) or any(abs(a - b) > eps for a, b in zip(actual, expected)):
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def ply_header(path: Path) -> str:
    data = path.read_bytes()
    marker = b"end_header\n"
    end = data.find(marker)
    if end < 0:
        raise AssertionError(f"{path} has no PLY end_header")
    return data[: end + len(marker)].decode("ascii", errors="replace")


def ply_header_count(path: Path, element: str) -> int:
    header = ply_header(path)
    match = re.search(rf"^element {re.escape(element)} (\d+)$", header, re.MULTILINE)
    if not match:
        raise AssertionError(f"{path} has no element {element}")
    return int(match.group(1))


def ascii_vertices(path: Path) -> list[tuple[float, float, float]]:
    text = path.read_text(encoding="ascii", errors="replace")
    _header, body = text.split("end_header\n", 1)
    out = []
    for line in body.splitlines()[: ply_header_count(path, "vertex")]:
        parts = line.split()
        if len(parts) < 3:
            raise AssertionError(f"invalid PLY vertex row: {line!r}")
        out.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return out


def ascii_vertex_rows(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="ascii", errors="replace")
    _header, body = text.split("end_header\n", 1)
    return [line.split() for line in body.splitlines()[: ply_header_count(path, "vertex")]]


def mesh_stats() -> tuple[int, int, int]:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    return (
        len(meshes),
        sum(len(obj.data.vertices) for obj in meshes),
        sum(len(obj.data.polygons) for obj in meshes),
    )


def native_import_stats(path: Path) -> tuple[int, int, int]:
    reset_scene()
    bpy.ops.wm.ply_import(filepath=os.fspath(path))
    return mesh_stats()


def assetkit_import_stats(path: Path) -> tuple[int, int, int]:
    reset_scene()
    import_assetkit_file(
        os.fspath(path),
        "",
        make_load_options(
            coordinate_conversion="RAW",
            coordinate_system="Z_UP",
            triangulate=True,
            texture_loading="DEFERRED",
        ),
        collection=bpy.context.collection,
        shading_mode="AUTO",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    return mesh_stats()


def run_checks(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    reset_scene()
    for index in range(100):
        add_cube(f"Cube_{index:03d}", (float(index) * 3.0, 0.0, 0.0))
    hidden = add_cube("HiddenCube", (400.0, 0.0, 0.0))
    hidden.hide_set(True)
    all_path = out_root / "hundred.ply"
    export_scene(bpy.context, all_path, AK_FILE_TYPE_PLY)
    assert_equal(ply_header_count(all_path, "face"), 600, "100 visible cubes export")
    assert_equal(native_import_stats(all_path)[2], 600, "native import of 100-cube PLY")

    triangulated_path = out_root / "hundred_triangulated.ply"
    export_scene(bpy.context, triangulated_path, AK_FILE_TYPE_PLY, ply_export_triangulated_mesh=True)
    assert_equal(ply_header_count(triangulated_path, "face"), 1200, "triangulated 100 visible cubes export")

    reset_scene()
    cubes = [add_cube(f"Sel_{index}", (float(index) * 3.0, 0.0, 0.0)) for index in range(5)]
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    cubes[1].select_set(True)
    cubes[3].select_set(True)
    bpy.context.view_layer.objects.active = cubes[1]
    selected_path = out_root / "selected.ply"
    export_scene(bpy.context, selected_path, AK_FILE_TYPE_PLY, selected_only=True)
    assert_equal(ply_header_count(selected_path, "face"), 12, "selected-only export")

    reset_scene()
    mixed_mesh = bpy.data.meshes.new("MixedFaceLineMesh")
    mixed_mesh.from_pydata(
        [(0.0, 0.0, 0.0),
         (1.0, 0.0, 0.0),
         (0.0, 1.0, 0.0),
         (2.0, 0.0, 0.0),
         (2.0, 1.0, 0.0)],
        [(3, 4)],
        [(0, 1, 2)],
    )
    mixed_mesh.materials.append(bpy.data.materials.new("Surface"))
    mixed_mesh.materials.append(bpy.data.materials.new("Edge"))
    mixed = bpy.data.objects.new("MixedFaceLine", mixed_mesh)
    mixed["assetkit_mixed_line_material_slot"] = 1
    mixed["assetkit_mixed_line_mode"] = 1
    bpy.context.collection.objects.link(mixed)
    mixed_path = out_root / "mixed_face_line.ply"
    export_scene(
        bpy.context,
        mixed_path,
        AK_FILE_TYPE_PLY,
        ply_bake_textures=False,
    )
    assert_equal(ply_header_count(mixed_path, "face"), 1,
                 "mixed PLY face count")
    assert_equal(ply_header_count(mixed_path, "edge"), 1,
                 "mixed PLY loose-edge count")

    reset_scene()
    add_triangle("AsciiTriangle", with_attrs=True)
    ascii_path = out_root / "ascii_attrs.ply"
    export_scene(
        bpy.context,
        ascii_path,
        AK_FILE_TYPE_PLY,
        ply_format="ASCII",
        ply_export_colors="LINEAR",
    )
    header = ply_header(ascii_path)
    if "format ascii 1.0" not in header:
        raise AssertionError("ASCII PLY header missing format")
    for expected in (
        "property float s",
        "property float t",
        "property float red",
        "property float green",
        "property float blue",
        "property float alpha",
    ):
        if expected not in header:
            raise AssertionError(f"ASCII PLY header missing {expected!r}")
    assert_equal(ply_header_count(ascii_path, "face"), 1, "ASCII attr face count")
    assert_equal(assetkit_import_stats(ascii_path)[2], 1, "AssetKit import of ASCII PLY")

    bake_option_path = out_root / "bake_option.ply"
    export_scene(
        bpy.context,
        bake_option_path,
        AK_FILE_TYPE_PLY,
        ply_bake_textures=True,
    )
    if ply_header_count(bake_option_path, "face") < 1:
        raise AssertionError("texture-bake option export has no faces")

    reset_scene()
    gamma_triangle = add_triangle("GammaTriangle")
    gamma_uv = gamma_triangle.data.uv_layers.new(name="UVMap")
    gamma_coords = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    for polygon in gamma_triangle.data.polygons:
        for corner, loop_index in enumerate(polygon.loop_indices):
            gamma_uv.data[loop_index].uv = gamma_coords[corner]
    gamma_image = bpy.data.images.new("GammaHalf", width=1, height=1)
    gamma_image.colorspace_settings.name = "Non-Color"
    gamma_image.pixels = (0.5, 0.5, 0.5, 1.0)
    gamma_image.filepath_raw = os.fspath(out_root / "gamma_half.png")
    gamma_image.file_format = "PNG"
    gamma_image.save()
    bpy.data.images.remove(gamma_image)
    gamma_image = bpy.data.images.load(os.fspath(out_root / "gamma_half.png"),
                                       check_existing=False)
    gamma_image.colorspace_settings.name = "sRGB"
    gamma_material = bpy.data.materials.new("GammaMaterial")
    gamma_material.use_nodes = True
    gamma_nodes = gamma_material.node_tree.nodes
    gamma_bsdf = gamma_nodes.get("Principled BSDF")
    if gamma_bsdf is None:
        raise AssertionError("Principled BSDF node is missing")
    gamma_texture = gamma_nodes.new("ShaderNodeTexImage")
    gamma_texture.image = gamma_image
    gamma_bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    gamma_material.node_tree.links.new(gamma_texture.outputs["Color"],
                                       gamma_bsdf.inputs["Base Color"])
    gamma_triangle.data.materials.append(gamma_material)
    gamma_store = _ExportImageStore(out_root / "gamma_payload")
    gamma_payload = _material_tuple(
        gamma_material,
        gamma_store,
        {"UVMap": 0},
        24.0,
        context=bpy.context,
        obj=gamma_triangle,
        mesh=gamma_triangle.data,
        material_index=0,
        file_type=AK_FILE_TYPE_PLY,
        material_export_mode="DIRECT",
        material_bake_size=1024,
        lighting_bake_mode="OFF",
        export_images=True,
    )
    factor_material = bpy.data.materials.new("LinearFactorMaterial")
    factor_material.use_nodes = True
    factor_bsdf = factor_material.node_tree.nodes.get("Principled BSDF")
    if factor_bsdf is None:
        raise AssertionError("factor Principled BSDF node is missing")
    factor_bsdf.inputs["Base Color"].default_value = (0.5, 0.25, 0.75, 0.4)
    factor_bsdf.inputs["Alpha"].default_value = 0.4
    factor_payload = _material_tuple(
        factor_material,
        gamma_store,
        {},
        24.0,
        file_type=AK_FILE_TYPE_PLY,
        material_export_mode="DIRECT",
        material_bake_size=1024,
        lighting_bake_mode="OFF",
        export_images=True,
    )
    gamma_factor = tuple(float(value) for value in factor_payload[1])
    expected_factor = (0.5, 0.25, 0.75, 0.4)
    if any(abs(actual - expected) > 1.0e-6
           for actual, expected in zip(gamma_factor, expected_factor)):
        raise AssertionError(
            f"Blender linear material factor changed at the bridge: {gamma_factor!r}"
        )
    if not gamma_payload[7]:
        raise AssertionError("sRGB regression material has no base-color texture")
    gamma_pixels = gamma_payload[-1]
    if gamma_pixels is None:
        raise AssertionError("sRGB regression material has no pixel payload")
    if gamma_pixels[3] is not True:
        raise AssertionError("sRGB regression image was not classified as encoded sRGB")
    if any(abs(float(value) - (128.0 / 255.0)) > 1.0e-5
           for value in gamma_pixels[2][:3]):
        raise AssertionError(f"unexpected Blender sRGB pixel payload: {gamma_pixels[2][:3]!r}")
    gamma_path = out_root / "srgb_texture_bake.ply"
    export_scene(
        bpy.context,
        gamma_path,
        AK_FILE_TYPE_PLY,
        ply_format="ASCII",
        ply_export_normals=False,
        ply_export_uv=False,
        ply_bake_textures=True,
        material_export_mode="DIRECT",
    )
    gamma_rows = ascii_vertex_rows(gamma_path)
    if not gamma_rows:
        raise AssertionError("sRGB texture bake exported no vertices")
    for row in gamma_rows:
        rgb = tuple(map(int, row[3:6]))
        if any(abs(channel - 128) > 1 for channel in rgb):
            raise AssertionError(
                f"sRGB texture texel was gamma-encoded twice: {rgb!r}"
            )

    reset_scene()
    add_triangle("SrgbTriangle", with_attrs=True)
    srgb_path = out_root / "srgb_attrs.ply"
    export_scene(
        bpy.context,
        srgb_path,
        AK_FILE_TYPE_PLY,
        ply_format="ASCII",
        ply_export_colors="SRGB",
    )
    srgb_header = ply_header(srgb_path)
    for expected in (
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property uchar alpha",
    ):
        if expected not in srgb_header:
            raise AssertionError(f"sRGB PLY header missing {expected!r}")

    reset_scene()
    plane = add_plane("SolidPlane")
    mod = plane.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = 0.5
    no_mod_path = out_root / "modifier_off.ply"
    mod_path = out_root / "modifier_on.ply"
    export_scene(bpy.context, no_mod_path, AK_FILE_TYPE_PLY, ply_apply_modifiers=False)
    export_scene(bpy.context, mod_path, AK_FILE_TYPE_PLY, apply_modifiers=True)
    no_mod_faces = ply_header_count(no_mod_path, "face")
    mod_faces = ply_header_count(mod_path, "face")
    assert_equal(no_mod_faces, 1, "modifier-off plane polygon")
    if mod_faces <= no_mod_faces:
        raise AssertionError(f"modifier-on should add faces, got {mod_faces} <= {no_mod_faces}")

    reset_scene()
    add_triangle("AxisTriangle")
    scaled_path = out_root / "axis_scaled.ply"
    export_scene(
        bpy.context,
        scaled_path,
        AK_FILE_TYPE_PLY,
        ply_format="ASCII",
        global_scale=2.0,
        forward_axis="X",
        up_axis="Z",
    )
    vertices = ascii_vertices(scaled_path)
    expected = [(0.0, 0.0, 0.0), (0.0, -2.0, 0.0), (2.0, 0.0, 0.0)]
    for index, (actual, want) in enumerate(zip(vertices, expected)):
        assert_close_vec(actual, want, f"axis/scale vertex {index}")

    reset_scene()
    add_triangle("DefaultAxisTriangle")
    default_axis_path = out_root / "axis_default.ply"
    export_scene(
        bpy.context,
        default_axis_path,
        AK_FILE_TYPE_PLY,
        ply_format="ASCII",
        ply_bake_textures=False,
    )
    default_vertices = ascii_vertices(default_axis_path)
    default_expected = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)]
    for index, (actual, want) in enumerate(zip(default_vertices, default_expected)):
        assert_close_vec(actual, want, f"default Y-up axis vertex {index}")

    axes = ("X", "Y", "Z", "-X", "-Y", "-Z")
    native_axis = {
        "-X": "NEGATIVE_X",
        "-Y": "NEGATIVE_Y",
        "-Z": "NEGATIVE_Z",
    }
    for forward_axis in axes:
        for up_axis in axes:
            if forward_axis.lstrip("-") == up_axis.lstrip("-"):
                continue
            stem = f"axis_{forward_axis.replace('-', 'neg')}_{up_axis.replace('-', 'neg')}"
            assetkit_path = out_root / f"{stem}_assetkit.ply"
            native_path = out_root / f"{stem}_native.ply"
            export_scene(
                bpy.context,
                assetkit_path,
                AK_FILE_TYPE_PLY,
                ply_format="ASCII",
                global_scale=2.0,
                forward_axis=forward_axis,
                up_axis=up_axis,
            )
            bpy.ops.wm.ply_export(
                filepath=os.fspath(native_path),
                ascii_format=True,
                export_selected_objects=False,
                global_scale=2.0,
                apply_modifiers=True,
                forward_axis=native_axis.get(forward_axis, forward_axis),
                up_axis=native_axis.get(up_axis, up_axis),
                export_uv=True,
                export_normals=False,
                export_colors="SRGB",
                export_attributes=True,
                export_triangulated_mesh=False,
            )
            assetkit_vertices = ascii_vertices(assetkit_path)
            native_vertices = ascii_vertices(native_path)
            assert_equal(len(assetkit_vertices), len(native_vertices), f"{stem} vertex count")
            for index, (actual, want) in enumerate(zip(assetkit_vertices, native_vertices)):
                assert_close_vec(actual, want, f"{stem} vertex {index}")

    print(f"PLY export checks passed: {out_root}")


def run_benchmark(out_root: Path, runs: int, cube_count: int) -> None:
    if runs <= 0:
        return

    reset_scene()
    for index in range(cube_count):
        add_cube(f"Bench_{index:03d}", (float(index) * 3.0, 0.0, 0.0))

    assetkit_times = []
    native_times = []
    for index in range(runs + 1):
        assetkit_path = out_root / f"bench_assetkit_{index}.ply"
        native_path = out_root / f"bench_native_{index}.ply"

        started_at = time.perf_counter()
        export_scene(bpy.context, assetkit_path, AK_FILE_TYPE_PLY)
        assetkit_elapsed = (time.perf_counter() - started_at) * 1000.0

        started_at = time.perf_counter()
        bpy.ops.wm.ply_export(
            filepath=os.fspath(native_path),
            ascii_format=False,
            export_selected_objects=False,
            global_scale=1.0,
            apply_modifiers=True,
            forward_axis="Y",
            up_axis="Z",
            export_uv=True,
            export_normals=False,
            export_colors="SRGB",
            export_attributes=True,
            export_triangulated_mesh=False,
        )
        native_elapsed = (time.perf_counter() - started_at) * 1000.0

        assert_equal(ply_header_count(assetkit_path, "face"), cube_count * 6, "benchmark AssetKit faces")
        assert_equal(ply_header_count(native_path, "face"), cube_count * 6, "benchmark native cube polygon faces")

        if index > 0:
            assetkit_times.append(assetkit_elapsed)
            native_times.append(native_elapsed)

    assetkit_median = statistics.median(assetkit_times)
    native_median = statistics.median(native_times)
    ratio = native_median / assetkit_median if assetkit_median > 0.0 else 0.0
    print(
        "PLY export benchmark "
        f"cubes={cube_count} runs={runs} "
        f"assetkit_median_ms={assetkit_median:.3f} "
        f"native_median_ms={native_median:.3f} "
        f"native_over_assetkit={ratio:.2f}x"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="", help="Output directory; defaults to a temp directory")
    parser.add_argument("--bench-runs", type=int, default=0, help="Run optional native-vs-AssetKit PLY export benchmark")
    parser.add_argument("--bench-cubes", type=int, default=100, help="Cube count for optional PLY export benchmark")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    out_root = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="assetkit-ply-check-"))
    run_checks(out_root)
    run_benchmark(out_root, args.bench_runs, args.bench_cubes)
    return 0


if __name__ == "__main__":
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    raise SystemExit(main(argv))
