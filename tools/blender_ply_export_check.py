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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_PLY  # noqa: E402
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
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property uchar alpha",
    ):
        if expected not in header:
            raise AssertionError(f"ASCII PLY header missing {expected!r}")
    assert_equal(ply_header_count(ascii_path, "face"), 1, "ASCII attr face count")
    assert_equal(assetkit_import_stats(ascii_path)[2], 1, "AssetKit import of ASCII PLY")

    reset_scene()
    plane = add_plane("SolidPlane")
    mod = plane.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = 0.5
    no_mod_path = out_root / "modifier_off.ply"
    mod_path = out_root / "modifier_on.ply"
    export_scene(bpy.context, no_mod_path, AK_FILE_TYPE_PLY, ply_apply_modifiers=False)
    export_scene(bpy.context, mod_path, AK_FILE_TYPE_PLY, ply_apply_modifiers=True)
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
        ply_global_scale=2.0,
        ply_forward_axis="X",
        ply_up_axis="Z",
    )
    vertices = ascii_vertices(scaled_path)
    expected = [(0.0, 0.0, 0.0), (0.0, -2.0, 0.0), (2.0, 0.0, 0.0)]
    for index, (actual, want) in enumerate(zip(vertices, expected)):
        assert_close_vec(actual, want, f"axis/scale vertex {index}")

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
