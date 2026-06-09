#!/usr/bin/env python3
"""Benchmark AssetKit Blender export against Blender's glTF exporter.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_export_benchmark.py -- \
    --runs 5 --compare-blender --format glb \
    /Users/recp/Projects/KhronosGroup/glTF-Sample-Assets/Models/DamagedHelmet/glTF/DamagedHelmet.gltf
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_GLB, AK_FILE_TYPE_GLTF  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402


def purge_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_scene(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=os.fspath(path))
        return
    if suffix in {".gltf", ".glb"}:
        bpy.ops.import_scene.gltf(filepath=os.fspath(path))
        return
    raise ValueError(f"unsupported benchmark input: {path}")


def scene_stats() -> dict[str, int]:
    meshes = 0
    verts = 0
    loops = 0
    tris = 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mesh = obj.data
        meshes += 1
        verts += len(mesh.vertices)
        loops += len(mesh.loops)
        for poly in mesh.polygons:
            if poly.loop_total >= 3:
                tris += poly.loop_total - 2
    return {
        "objects": len(bpy.context.scene.objects),
        "meshes": meshes,
        "verts": verts,
        "loops": loops,
        "tris": tris,
    }


def _linked_resource_path(base: Path, uri: object) -> Path | None:
    if not isinstance(uri, str) or not uri or uri.startswith("data:"):
        return None

    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        candidate = Path(unquote(parsed.path))
    else:
        candidate = base.parent / unquote(parsed.path)
    return candidate if candidate.is_file() else None


def _gltf_file_size(path: Path) -> int:
    try:
        gltf = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return path.stat().st_size

    total = path.stat().st_size
    seen = {path.resolve()}
    for collection in ("buffers", "images"):
        for item in gltf.get(collection, ()) or ():
            resource = _linked_resource_path(path, item.get("uri") if isinstance(item, dict) else None)
            if resource is None:
                continue
            resolved = resource.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            total += resource.stat().st_size
    return total


def file_size(path: Path) -> int:
    if path.is_file():
        if path.suffix.lower() == ".gltf":
            return _gltf_file_size(path)
        return path.stat().st_size
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return 0


def bench_assetkit(out_path: Path, fmt: str) -> None:
    file_type = AK_FILE_TYPE_GLB if fmt == "glb" else AK_FILE_TYPE_GLTF
    export_scene(bpy.context, out_path, file_type)


def bench_blender(out_path: Path, fmt: str) -> None:
    export_format = "GLB" if fmt == "glb" else "GLTF_SEPARATE"
    bpy.ops.export_scene.gltf(
        filepath=os.fspath(out_path),
        export_format=export_format,
        use_selection=False,
    )


def run_one(engine: str, input_path: Path, out_dir: Path, fmt: str, run_index: int) -> dict:
    suffix = ".glb" if fmt == "glb" else ".gltf"
    out_path = out_dir / engine / f"{input_path.stem}-{run_index}{suffix}"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    if engine == "assetkit":
        bench_assetkit(out_path, fmt)
    elif engine == "blender":
        bench_blender(out_path, fmt)
    else:
        raise ValueError(engine)
    elapsed = time.perf_counter() - start

    return {
        "engine": engine,
        "input": os.fspath(input_path),
        "run": run_index,
        "seconds": elapsed,
        "bytes": file_size(out_path),
        "output": os.fspath(out_path),
    }


def summarize(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        key = (row["engine"], row["input"])
        grouped.setdefault(key, []).append(float(row["seconds"]))

    out = []
    for (engine, input_path), values in sorted(grouped.items()):
        out.append({
            "engine": engine,
            "input": input_path,
            "runs": len(values),
            "min_seconds": min(values),
            "median_seconds": statistics.median(values),
            "max_seconds": max(values),
        })
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Input .gltf, .glb or .blend files")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--format", choices=("gltf", "glb"), default="glb")
    parser.add_argument("--compare-blender", action="store_true")
    parser.add_argument("--out", default="", help="Output directory; defaults to a temporary directory")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    out_root = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="akb-export-bench-"))
    engines = ["assetkit"]
    if args.compare_blender:
        engines.append("blender")

    rows = []
    for raw_path in args.paths:
        input_path = Path(raw_path).expanduser().resolve()
        for run_index in range(max(1, args.runs)):
            purge_scene()
            import_scene(input_path)
            stats = scene_stats()
            for engine in engines:
                row = run_one(engine, input_path, out_root, args.format, run_index)
                row.update(stats)
                rows.append(row)
                print(json.dumps(row, sort_keys=True), flush=True)

    for row in summarize(rows):
        print(json.dumps({"summary": row}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    raise SystemExit(main(argv))
