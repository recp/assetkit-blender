#!/usr/bin/env python3
"""Benchmark AssetKit imports against Blender's built-in importers.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_import_benchmark.py -- \
    --runs 5 --warmup 1 --markdown \
    /path/to/model.glb /path/to/model.dae
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


SUPPORTED_FORMATS = {"gltf", "glb", "dae", "obj", "ply", "stl"}


@dataclass(slots=True)
class SceneStats:
    objects: int = 0
    meshes: int = 0
    curves: int = 0
    cameras: int = 0
    lights: int = 0
    materials: int = 0
    images: int = 0
    actions: int = 0
    verts: int = 0
    edges: int = 0
    faces: int = 0
    loops: int = 0
    tris: int = 0


def purge_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def infer_format(path: Path) -> str:
    fmt = path.suffix.lower().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported benchmark input: {path}")
    return fmt


def file_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return 0


def scene_stats() -> SceneStats:
    stats = SceneStats(
        objects=len(bpy.context.scene.objects),
        materials=len(bpy.data.materials),
        images=len(bpy.data.images),
        actions=len(bpy.data.actions),
    )
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.data is not None:
            mesh = obj.data
            stats.meshes += 1
            stats.verts += len(mesh.vertices)
            stats.edges += len(mesh.edges)
            stats.faces += len(mesh.polygons)
            stats.loops += len(mesh.loops)
            for poly in mesh.polygons:
                if poly.loop_total >= 3:
                    stats.tris += poly.loop_total - 2
        elif obj.type == "CURVE":
            stats.curves += 1
        elif obj.type == "CAMERA":
            stats.cameras += 1
        elif obj.type == "LIGHT":
            stats.lights += 1
    return stats


def import_assetkit(path: Path, texture_loading: str, triangulate: bool) -> None:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        convert_triangle_strip=True,
        convert_triangle_fan=True,
        import_lines=True,
        convert_line_loop=True,
        convert_line_strip=True,
        triangulate=triangulate,
        generate_normals=False,
        texture_loading=texture_loading,
    )
    import_assetkit_file(
        os.fspath(path),
        "",
        options,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        shading_mode="AUTO",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
        fit_timeline=True,
    )


def import_builtin(path: Path) -> None:
    fmt = infer_format(path)
    filepath = os.fspath(path)
    if fmt in {"gltf", "glb"}:
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif fmt == "dae":
        bpy.ops.wm.collada_import(filepath=filepath)
    elif fmt == "obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    elif fmt == "ply":
        bpy.ops.wm.ply_import(filepath=filepath, merge_verts=False, import_attributes=True)
    elif fmt == "stl":
        bpy.ops.wm.stl_import(filepath=filepath)
    else:
        raise ValueError(f"unsupported built-in format: {fmt}")


def time_import(path: Path, engine: str, texture_loading: str, triangulate: bool, verbose_importers: bool) -> dict:
    purge_scene()
    started_at = time.perf_counter()
    error = ""
    try:
        if verbose_importers:
            if engine == "assetkit":
                import_assetkit(path, texture_loading, triangulate)
            elif engine == "builtin":
                import_builtin(path)
            else:
                raise ValueError(engine)
        else:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                if engine == "assetkit":
                    import_assetkit(path, texture_loading, triangulate)
                elif engine == "builtin":
                    import_builtin(path)
                else:
                    raise ValueError(engine)
    except Exception as exc:  # noqa: BLE001 - benchmark tool should report importer failures
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    stats = scene_stats()
    purge_scene()
    row = {
        "engine": engine,
        "file": os.fspath(path),
        "format": infer_format(path),
        "bytes": file_size(path),
        "ms": elapsed_ms,
        "error": error,
    }
    row.update(asdict(stats))
    return row


def summarize(rows: list[dict], warmup: int) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["file"], row["engine"]), []).append(row)

    summaries: list[dict] = []
    for (file_path, engine), group in sorted(grouped.items()):
        valid = [row for row in group if not row["error"]]
        measured = valid[warmup:] if warmup < len(valid) else valid
        if not measured:
            summaries.append({
                "file": file_path,
                "engine": engine,
                "runs": len(group),
                "successful_runs": len(valid),
                "error": group[-1]["error"] if group else "no samples",
            })
            continue
        timings = [float(row["ms"]) for row in measured]
        sample = measured[-1]
        summaries.append({
            "file": file_path,
            "engine": engine,
            "runs": len(group),
            "successful_runs": len(valid),
            "measured_runs": len(measured),
            "min_ms": min(timings),
            "median_ms": statistics.median(timings),
            "max_ms": max(timings),
            "objects": sample["objects"],
            "meshes": sample["meshes"],
            "materials": sample["materials"],
            "images": sample["images"],
            "verts": sample["verts"],
            "tris": sample["tris"],
            "error": "",
        })
    return summaries


def comparison_rows(summaries: list[dict]) -> list[dict]:
    by_file: dict[str, dict[str, dict]] = {}
    for row in summaries:
        by_file.setdefault(row["file"], {})[row["engine"]] = row

    rows = []
    for file_path, engines in sorted(by_file.items()):
        assetkit = engines.get("assetkit")
        builtin = engines.get("builtin")
        if not assetkit or not builtin or assetkit.get("error") or builtin.get("error"):
            continue
        assetkit_ms = float(assetkit["median_ms"])
        builtin_ms = float(builtin["median_ms"])
        rows.append({
            "file": file_path,
            "assetkit_median_ms": assetkit_ms,
            "builtin_median_ms": builtin_ms,
            "builtin_over_assetkit": builtin_ms / assetkit_ms if assetkit_ms > 0.0 else 0.0,
            "objects_assetkit": assetkit["objects"],
            "objects_builtin": builtin["objects"],
            "tris_assetkit": assetkit["tris"],
            "tris_builtin": builtin["tris"],
        })
    return rows


def print_markdown(summaries: list[dict]) -> None:
    comparisons = comparison_rows(summaries)
    if not comparisons:
        return
    print("\n| File | AssetKit median | Blender median | Blender / AssetKit | Tris AssetKit | Tris Blender |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for row in comparisons:
        name = Path(row["file"]).name
        print(
            f"| {name} | "
            f"{row['assetkit_median_ms']:.1f} ms | "
            f"{row['builtin_median_ms']:.1f} ms | "
            f"{row['builtin_over_assetkit']:.2f}x | "
            f"{row['tris_assetkit']} | "
            f"{row['tris_builtin']} |"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Input .gltf, .glb, .dae, .obj, .ply, or .stl files")
    parser.add_argument("--runs", type=int, default=5, help="Samples per importer")
    parser.add_argument("--warmup", type=int, default=1, help="Successful samples to drop from summaries")
    parser.add_argument("--engines", nargs="+", choices=("assetkit", "builtin"), default=("assetkit", "builtin"))
    parser.add_argument(
        "--assetkit-textures",
        choices=("AUTO", "IMMEDIATE", "DEFERRED"),
        default="IMMEDIATE",
        help="AssetKit texture loading mode. IMMEDIATE is the fairest default for full import timing.",
    )
    parser.add_argument("--triangulate", action="store_true", help="Triangulate AssetKit imports")
    parser.add_argument("--jsonl", default="", help="Optional path to write raw run rows and summaries")
    parser.add_argument("--markdown", action="store_true", help="Print a markdown comparison table")
    parser.add_argument("--verbose-importers", action="store_true", help="Show importer diagnostic output")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    paths = [Path(path).expanduser().resolve() for path in args.paths]
    runs = max(1, args.runs)
    warmup = max(0, args.warmup)
    rows: list[dict] = []

    jsonl_file = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None
    try:
        for path in paths:
            if not path.exists():
                raise SystemExit(f"missing input: {path}")
            infer_format(path)
            for run_index in range(runs):
                engines = list(args.engines)
                if run_index % 2 == 1:
                    engines.reverse()
                for engine in engines:
                    row = time_import(path, engine, args.assetkit_textures, args.triangulate, args.verbose_importers)
                    row["run"] = run_index + 1
                    rows.append(row)
                    print(json.dumps({"run": row}, sort_keys=True), flush=True)
                    if jsonl_file:
                        print(json.dumps({"run": row}, sort_keys=True), file=jsonl_file, flush=True)

        summaries = summarize(rows, warmup)
        for row in summaries:
            print(json.dumps({"summary": row}, sort_keys=True), flush=True)
            if jsonl_file:
                print(json.dumps({"summary": row}, sort_keys=True), file=jsonl_file, flush=True)

        for row in comparison_rows(summaries):
            print(json.dumps({"comparison": row}, sort_keys=True), flush=True)
            if jsonl_file:
                print(json.dumps({"comparison": row}, sort_keys=True), file=jsonl_file, flush=True)

        if args.markdown:
            print_markdown(summaries)
    finally:
        if jsonl_file:
            jsonl_file.close()
    return 0


if __name__ == "__main__":
    if "--" in sys.argv:
        tool_argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        tool_argv = sys.argv[1:]
    raise SystemExit(main(tool_argv))
