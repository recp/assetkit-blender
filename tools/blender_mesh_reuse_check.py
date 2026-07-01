#!/usr/bin/env python3
"""Exercise AssetKit Blender mesh-data reuse for repeated source glTF meshes.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_mesh_reuse_check.py
"""

from __future__ import annotations

import argparse
import array
import json
import os
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def write_reused_mesh_gltf(out_dir: Path, grid_size: int = 65) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "reused_mesh"
    gltf_path = out_dir / f"{stem}.gltf"
    bin_path = out_dir / f"{stem}.bin"

    positions = array.array("f")
    for y in range(grid_size):
        fy = float(y) / float(grid_size - 1)
        for x in range(grid_size):
            fx = float(x) / float(grid_size - 1)
            positions.extend((fx, fy, 0.0))

    indices = array.array("I")
    for y in range(grid_size - 1):
        row = y * grid_size
        next_row = row + grid_size
        for x in range(grid_size - 1):
            a = row + x
            b = a + 1
            c = next_row + x
            d = c + 1
            indices.extend((a, c, b, b, c, d))

    if positions.itemsize != 4 or indices.itemsize != 4:
        raise AssertionError(
            f"unexpected array item sizes: f={positions.itemsize}, I={indices.itemsize}"
        )

    if sys.byteorder != "little":
        positions.byteswap()
        indices.byteswap()

    position_byte_length = len(positions) * positions.itemsize
    index_byte_offset = position_byte_length
    index_byte_length = len(indices) * indices.itemsize
    buffer_byte_length = position_byte_length + index_byte_length
    vertex_count = grid_size * grid_size
    index_count = len(indices)

    with bin_path.open("wb") as out:
        positions.tofile(out)
        indices.tofile(out)

    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": bin_path.name, "byteLength": buffer_byte_length}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": position_byte_length,
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": index_byte_offset,
                "byteLength": index_byte_length,
                "target": 34963,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": vertex_count,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5125,
                "count": index_count,
                "type": "SCALAR",
            },
        ],
        "meshes": [
            {
                "name": "SharedGridMesh",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4,
                    }
                ],
            }
        ],
        "nodes": [
            {"name": "ReuseNodeA", "mesh": 0},
            {"name": "ReuseNodeB", "mesh": 0, "translation": [2.0, 0.0, 0.0]},
        ],
        "scenes": [{"nodes": [0, 1]}],
        "scene": 0,
    }
    gltf_path.write_text(json.dumps(gltf, separators=(",", ":")), encoding="utf-8")
    return gltf_path


def import_asset(path: Path, *, geometry_content_keys: bool) -> list[bpy.types.Object]:
    return import_assetkit_file(
        os.fspath(path),
        "",
        make_load_options(
            texture_loading="DEFERRED",
            geometry_content_keys=geometry_content_keys,
        ),
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


def assert_mesh_reuse(
    gltf_path: Path,
    *,
    label: str,
    geometry_content_keys: bool,
) -> dict:
    reset_scene()
    imported = import_asset(gltf_path, geometry_content_keys=geometry_content_keys)
    mesh_objects = [obj for obj in imported if getattr(obj, "type", None) == "MESH"]
    if len(mesh_objects) != 2:
        raise AssertionError(f"expected 2 imported mesh objects, got {len(mesh_objects)}")

    mesh_ids = {obj.data.as_pointer() for obj in mesh_objects}
    if len(mesh_ids) != 1:
        details = [(obj.name, obj.data.name, obj.data.as_pointer()) for obj in mesh_objects]
        raise AssertionError(f"repeated source mesh did not reuse Blender Mesh data: {details}")

    mesh = mesh_objects[0].data
    if len(mesh.vertices) <= 0 or len(mesh.polygons) <= 0:
        raise AssertionError("imported mesh has no geometry")

    return {
        "label": label,
        "source": os.fspath(gltf_path),
        "objects": [obj.name for obj in mesh_objects],
        "mesh_data": mesh.name,
        "unique_mesh_data": len(mesh_ids),
        "vertices": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "loops": len(mesh.loops),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(tempfile.mkdtemp(prefix="assetkit-mesh-reuse-")),
        help="Directory for the generated glTF fixture.",
    )
    args = parser.parse_args(argv)
    gltf_path = write_reused_mesh_gltf(args.out.expanduser().resolve())
    result = {
        "runs": [
            assert_mesh_reuse(
                gltf_path,
                label="default",
                geometry_content_keys=False,
            ),
            assert_mesh_reuse(
                gltf_path,
                label="content_key_limit",
                geometry_content_keys=True,
            ),
        ]
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"mesh reuse check passed: {gltf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
