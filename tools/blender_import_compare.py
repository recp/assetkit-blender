#!/usr/bin/env python3
"""Compare AssetKit Blender imports with Blender's built-in OBJ/PLY/STL importers.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_import_compare.py -- \
    --root /path/to/blender/tests/files/io_tests --formats obj ply stl --semantic

For benchmark runs:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_import_compare.py -- \
    --bench --runs 5 /path/to/model.obj /path/to/model.ply /path/to/model.stl
"""

from __future__ import annotations

import argparse
import glob
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.assetkit import (  # noqa: E402
    AK_PRIMITIVE_LINES,
    AK_PRIMITIVE_POINTS,
    AK_PRIMITIVE_TRIANGLES,
    native_load_meshes,
)
from assetkit_blender.importer import import_assetkit_file  # noqa: E402


NATIVE_OPTIONS = {
    "coordinate_system": "Z_UP",
    "coordinate_conversion": "TRANSFORM",
    "generate_normals": False,
    "convert_triangle_strip": True,
    "convert_triangle_fan": True,
    "import_lines": True,
    "convert_line_loop": True,
    "convert_line_strip": True,
    "triangulate": True,
}

IMPORT_OPTIONS = {
    "coordinate_system": "Z_UP",
    "coordinate_conversion": "DEFAULT",
    "triangulate": True,
    "generate_normals": False,
    "texture_loading": "DEFERRED",
}


KNOWN_OBJ_DIFFS = {
    "all_curves_as_nurbs.obj",
    "all_objects.obj",
    "all_objects_mat_groups.obj",
    "cube_loose_edges_verts.obj",
    "faces_invalid_or_with_holes.obj",
    "invalid_faces.obj",
    "makehuman.obj",
    "materials.obj",
    "nurbs.obj",
    "nurbs_curves.obj",
    "nurbs_cyclic.obj",
    "nurbs_endpoint.obj",
    "nurbs_manual.obj",
    "polylines.obj",
    "rhino_curve_arc_bezier_deg2.obj",
    "rhino_curve_bezier_deg3_cyclic.obj",
    "rhino_curve_bezier_deg4_rat.obj",
    "rhino_curve_circle_bezier_deg2_cyclic.obj",
    "rhino_curve_uniform_cyclic_deg3.obj",
    "rhino_curve_uniform_cyclic_deg7.obj",
    "suzanne_all_data.obj",
}


@dataclass(slots=True)
class MeshStats:
    meshes: int = 0
    curves: int = 0
    objects: int = 0
    verts: int = 0
    edges: int = 0
    faces: int = 0
    loops: int = 0
    tri_loops: int = 0
    loose_edges: int = 0
    points: int = 0


def purge_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.images,
    ):
        for item in list(datablocks):
            if item.users == 0:
                datablocks.remove(item)


def infer_format(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in {"obj", "ply", "stl"}:
        return suffix
    raise ValueError(f"Unsupported importer format for {path!r}")


def iter_corpus_paths(root: str, formats: Iterable[str]) -> list[str]:
    paths: list[str] = []
    for fmt in formats:
        paths.extend(sorted(glob.glob(os.path.join(root, fmt, f"*.{fmt}"))))
    return paths


def blender_stats() -> MeshStats:
    stats = MeshStats()
    for obj in bpy.context.scene.objects:
        stats.objects += 1
        if obj.type == "CURVE" and obj.data:
            stats.curves += 1
            continue
        if obj.type != "MESH" or not obj.data:
            continue
        mesh = obj.data
        stats.meshes += 1
        stats.verts += len(mesh.vertices)
        stats.edges += len(mesh.edges)
        stats.faces += len(mesh.polygons)
        stats.loops += len(mesh.loops)
        if len(mesh.polygons) == 0:
            if len(mesh.edges):
                stats.loose_edges += len(mesh.edges)
            elif len(mesh.vertices):
                stats.points += len(mesh.vertices)
        for poly in mesh.polygons:
            if poly.loop_total >= 3:
                stats.tri_loops += (poly.loop_total - 2) * 3
    return stats


def assetkit_native_stats(path: str) -> MeshStats:
    result = native_load_meshes(path, NATIVE_OPTIONS)
    meshes = list(result.meshes if result else [])
    stats = MeshStats(meshes=len(meshes), objects=len(meshes))
    for mesh in meshes:
        vertex_count = int(mesh.vertex_count or 0)
        loop_count = int(mesh.loop_count or 0)
        face_count = int(mesh.face_count or 0)
        edge_count = int(mesh.edge_count or 0)
        primitive_type = int(mesh.primitive_type or AK_PRIMITIVE_TRIANGLES)

        stats.verts += vertex_count
        stats.edges += edge_count
        stats.faces += face_count
        stats.loops += loop_count
        if face_count > 0:
            stats.tri_loops += loop_count
        elif primitive_type == AK_PRIMITIVE_LINES:
            stats.loose_edges += edge_count or loop_count // 2
        elif primitive_type == AK_PRIMITIVE_POINTS:
            stats.points += loop_count or vertex_count
    return stats


def import_blender_builtin(path: str, fmt: str) -> None:
    if fmt == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif fmt == "ply":
        bpy.ops.wm.ply_import(filepath=path, merge_verts=False, import_attributes=True)
    elif fmt == "stl":
        bpy.ops.wm.stl_import(filepath=path)
    else:
        raise ValueError(f"Unsupported format {fmt!r}")


def import_assetkit(path: str) -> None:
    import_assetkit_file(
        path,
        load_options=IMPORT_OPTIONS,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        shading_mode="AUTO",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
        fit_timeline=False,
    )


def equivalent(fmt: str, assetkit: MeshStats, blender: MeshStats) -> tuple[bool, str]:
    if blender.curves:
        return False, "built-in produced curve/freeform data"
    if assetkit.verts != blender.verts:
        return False, "vertex count differs"
    if assetkit.tri_loops != blender.tri_loops:
        return False, "triangulated loop count differs"
    if assetkit.loose_edges != blender.loose_edges:
        return False, "loose edge count differs"
    if fmt == "ply" and blender.tri_loops == 0 and blender.loose_edges == 0:
        if assetkit.points != blender.points and assetkit.points != blender.verts:
            return False, "point count differs"
    if fmt == "stl" and assetkit.faces != blender.faces:
        return False, "face count differs"
    return True, "ok"


def run_semantic(paths: Iterable[str], fail_on_diff: bool, allow_known_diffs: bool) -> int:
    total = 0
    diff = 0
    known_diff = 0
    errors = 0
    for path in paths:
        fmt = infer_format(path)
        total += 1
        basename = os.path.basename(path)
        try:
            assetkit = assetkit_native_stats(path)
            assetkit_error = ""
        except Exception as exc:  # noqa: BLE001 - diagnostic tool
            assetkit = MeshStats()
            assetkit_error = type(exc).__name__

        purge_scene()
        try:
            import_blender_builtin(path, fmt)
            builtin = blender_stats()
            builtin_error = ""
        except Exception as exc:  # noqa: BLE001 - diagnostic tool
            builtin = MeshStats()
            builtin_error = type(exc).__name__
        purge_scene()

        if assetkit_error or builtin_error:
            ok = bool(assetkit_error and builtin_error)
            reason = "both rejected" if ok else "one importer rejected"
            errors += 0 if ok else 1
        else:
            ok, reason = equivalent(fmt, assetkit, builtin)
        is_known_diff = (
            not ok
            and allow_known_diffs
            and fmt == "obj"
            and basename in KNOWN_OBJ_DIFFS
        )
        if is_known_diff:
            known_diff += 1
        elif not ok:
            diff += 1
        label = "OK" if ok else ("KNOWN_DIFF" if is_known_diff else "DIFF")
        print(
            f"SEMANTIC {label} fmt={fmt} file={basename!r} reason={reason} "
            f"assetkit={assetkit_error or asdict(assetkit)} "
            f"builtin={builtin_error or asdict(builtin)}",
            flush=True,
        )
    print(
        f"SEMANTIC SUMMARY total={total} diff={diff} known_diff={known_diff} errors={errors}",
        flush=True,
    )
    return 1 if fail_on_diff and diff else 0


def time_import(path: str, importer: str) -> tuple[float, MeshStats]:
    purge_scene()
    started = time.perf_counter()
    if importer == "assetkit":
        import_assetkit(path)
    else:
        import_blender_builtin(path, infer_format(path))
    elapsed = (time.perf_counter() - started) * 1000.0
    stats = blender_stats()
    purge_scene()
    return elapsed, stats


def run_bench(paths: Iterable[str], runs: int, warmup: int) -> None:
    for path in paths:
        for importer in ("assetkit", "builtin"):
            samples: list[float] = []
            last_stats = MeshStats()
            for run_index in range(runs):
                elapsed, last_stats = time_import(path, importer)
                samples.append(elapsed)
                print(
                    f"BENCH RUN importer={importer} file={os.path.basename(path)!r} "
                    f"run={run_index + 1} ms={elapsed:.3f} stats={asdict(last_stats)}",
                    flush=True,
                )
            warm_samples = samples[warmup:] if warmup < len(samples) else samples
            print(
                f"BENCH SUMMARY importer={importer} file={os.path.basename(path)!r} "
                f"median={statistics.median(warm_samples):.3f} "
                f"min={min(warm_samples):.3f} runs={runs} warmup={warmup} "
                f"stats={asdict(last_stats)}",
                flush=True,
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Specific OBJ/PLY/STL files to benchmark or compare")
    parser.add_argument("--root", help="Blender io_tests root containing obj/, ply/, stl/ subdirectories")
    parser.add_argument("--formats", nargs="+", choices=("obj", "ply", "stl"), default=("obj", "ply", "stl"))
    parser.add_argument("--semantic", action="store_true", help="Run native semantic comparison")
    parser.add_argument("--bench", action="store_true", help="Run full Blender import benchmark")
    parser.add_argument("--runs", type=int, default=5, help="Benchmark samples per importer")
    parser.add_argument("--warmup", type=int, default=1, help="Samples to drop from benchmark summary")
    parser.add_argument("--fail-on-diff", action="store_true", help="Exit non-zero if semantic diffs are found")
    parser.add_argument(
        "--allow-known-diffs",
        action="store_true",
        help="Treat documented OBJ semantic differences as known while still failing on new diffs",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    paths = list(args.paths)
    if args.root:
        paths.extend(iter_corpus_paths(args.root, args.formats))
    paths = [str(Path(path).expanduser()) for path in paths]

    if not paths:
        raise SystemExit("No input files. Pass paths or --root.")
    if not args.semantic and not args.bench:
        args.semantic = True

    status = 0
    if args.semantic:
        status = max(status, run_semantic(paths, args.fail_on_diff, args.allow_known_diffs))
    if args.bench:
        run_bench(paths, max(1, args.runs), max(0, args.warmup))
    return status


if __name__ == "__main__":
    if "--" in sys.argv:
        tool_argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        tool_argv = sys.argv[1:]
    raise SystemExit(main(tool_argv))
