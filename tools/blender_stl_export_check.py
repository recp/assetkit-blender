#!/usr/bin/env python3
"""Exercise AssetKit STL export parity inside Blender.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_stl_export_check.py
"""

from __future__ import annotations

import argparse
import os
import statistics
import struct
import sys
import tempfile
import time
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_STL  # noqa: E402
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


def add_triangle(name: str) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def binary_triangle_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 84:
        raise AssertionError(f"{path} is too small for binary STL")
    return struct.unpack_from("<I", data, 80)[0]


def ascii_triangle_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("solid"):
        raise AssertionError(f"{path} does not start with solid")
    return text.count("facet normal")


def first_binary_triangle_vertices(path: Path) -> list[tuple[float, float, float]]:
    data = path.read_bytes()
    if binary_triangle_count(path) < 1:
        raise AssertionError(f"{path} has no triangles")
    offset = 84 + 12
    values = struct.unpack_from("<9f", data, offset)
    return [tuple(values[i:i + 3]) for i in range(0, 9, 3)]


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_close_vec(actual, expected, label: str, eps: float = 1.0e-5) -> None:
    if len(actual) != len(expected) or any(abs(a - b) > eps for a, b in zip(actual, expected)):
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def mesh_polygon_count() -> int:
    return sum(len(obj.data.polygons) for obj in bpy.context.scene.objects if obj.type == "MESH")


def native_import_count(path: Path) -> tuple[int, int]:
    reset_scene()
    bpy.ops.wm.stl_import(filepath=os.fspath(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    return len(meshes), mesh_polygon_count()


def assetkit_import_count(path: Path) -> tuple[int, int]:
    reset_scene()
    objects = import_assetkit_file(
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
    meshes = [obj for obj in objects if obj.type == "MESH"]
    return len(meshes), mesh_polygon_count()


def run_checks(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    reset_scene()
    for index in range(100):
        add_cube(f"Cube_{index:03d}", (float(index) * 3.0, 0.0, 0.0))
    hidden = add_cube("HiddenCube", (400.0, 0.0, 0.0))
    hidden.hide_set(True)
    all_path = out_root / "hundred.stl"
    export_scene(bpy.context, all_path, AK_FILE_TYPE_STL)
    assert_equal(binary_triangle_count(all_path), 1200, "100 visible cubes export")
    assert_equal(native_import_count(all_path), (1, 1200), "native import of 100-cube STL")

    reset_scene()
    cubes = [add_cube(f"Sel_{index}", (float(index) * 3.0, 0.0, 0.0)) for index in range(5)]
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    cubes[1].select_set(True)
    cubes[3].select_set(True)
    bpy.context.view_layer.objects.active = cubes[1]
    selected_path = out_root / "selected.stl"
    export_scene(bpy.context, selected_path, AK_FILE_TYPE_STL, selected_only=True)
    assert_equal(binary_triangle_count(selected_path), 24, "selected-only export")

    reset_scene()
    for index in range(3):
        add_cube(f"Batch_{index}", (float(index) * 3.0, 0.0, 0.0))
    batch_path = out_root / "batch/model.stl"
    export_scene(bpy.context, batch_path, AK_FILE_TYPE_STL, stl_batch_mode=True)
    batch_files = sorted(batch_path.parent.glob("model_*.stl"))
    assert_equal(len(batch_files), 3, "batch file count")
    assert_equal([binary_triangle_count(path) for path in batch_files], [12, 12, 12], "batch triangle counts")

    reset_scene()
    add_cube("AsciiCube")
    ascii_path = out_root / "ascii.stl"
    export_scene(bpy.context, ascii_path, AK_FILE_TYPE_STL, stl_format="ASCII")
    assert_equal(ascii_triangle_count(ascii_path), 12, "ascii facet count")
    assert_equal(assetkit_import_count(ascii_path), (1, 12), "AssetKit import of ASCII STL")

    reset_scene()
    plane = add_plane("SolidPlane")
    mod = plane.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = 0.5
    no_mod_path = out_root / "modifier_off.stl"
    mod_path = out_root / "modifier_on.stl"
    export_scene(bpy.context, no_mod_path, AK_FILE_TYPE_STL, stl_apply_modifiers=False)
    export_scene(bpy.context, mod_path, AK_FILE_TYPE_STL, apply_modifiers=True)
    no_mod_count = binary_triangle_count(no_mod_path)
    mod_count = binary_triangle_count(mod_path)
    assert_equal(no_mod_count, 2, "modifier-off plane triangles")
    if mod_count <= no_mod_count:
        raise AssertionError(f"modifier-on should add triangles, got {mod_count} <= {no_mod_count}")

    reset_scene()
    add_triangle("AxisTriangle")
    scaled_path = out_root / "axis_scaled.stl"
    export_scene(
        bpy.context,
        scaled_path,
        AK_FILE_TYPE_STL,
        global_scale=2.0,
        forward_axis="X",
        up_axis="Z",
    )
    vertices = first_binary_triangle_vertices(scaled_path)
    expected = [(0.0, 0.0, 0.0), (0.0, -2.0, 0.0), (2.0, 0.0, 0.0)]
    for index, (actual, want) in enumerate(zip(vertices, expected)):
        assert_close_vec(actual, want, f"axis/scale vertex {index}")

    print(f"STL export checks passed: {out_root}")


def run_benchmark(out_root: Path, runs: int, cube_count: int) -> None:
    if runs <= 0:
        return

    reset_scene()
    for index in range(cube_count):
        add_cube(f"Bench_{index:03d}", (float(index) * 3.0, 0.0, 0.0))

    assetkit_times = []
    native_times = []
    for index in range(runs + 1):
        assetkit_path = out_root / f"bench_assetkit_{index}.stl"
        native_path = out_root / f"bench_native_{index}.stl"

        started_at = time.perf_counter()
        export_scene(bpy.context, assetkit_path, AK_FILE_TYPE_STL)
        assetkit_elapsed = (time.perf_counter() - started_at) * 1000.0

        started_at = time.perf_counter()
        bpy.ops.wm.stl_export(
            filepath=os.fspath(native_path),
            ascii_format=False,
            export_selected_objects=False,
            global_scale=1.0,
            use_scene_unit=False,
            forward_axis="Y",
            up_axis="Z",
            apply_modifiers=True,
        )
        native_elapsed = (time.perf_counter() - started_at) * 1000.0

        assert_equal(binary_triangle_count(assetkit_path), cube_count * 12, "benchmark AssetKit triangles")
        assert_equal(binary_triangle_count(native_path), cube_count * 12, "benchmark native triangles")

        if index > 0:
            assetkit_times.append(assetkit_elapsed)
            native_times.append(native_elapsed)

    assetkit_median = statistics.median(assetkit_times)
    native_median = statistics.median(native_times)
    ratio = native_median / assetkit_median if assetkit_median > 0.0 else 0.0
    print(
        "STL export benchmark "
        f"cubes={cube_count} runs={runs} "
        f"assetkit_median_ms={assetkit_median:.3f} "
        f"native_median_ms={native_median:.3f} "
        f"native_over_assetkit={ratio:.2f}x"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="", help="Output directory; defaults to a temp directory")
    parser.add_argument("--bench-runs", type=int, default=0, help="Run optional native-vs-AssetKit STL export benchmark")
    parser.add_argument("--bench-cubes", type=int, default=100, help="Cube count for optional STL export benchmark")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    out_root = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="assetkit-stl-check-"))
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
