#!/usr/bin/env python3
"""Exercise AssetKit OBJ export's default Blender-to-Y-up transform."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_WAVEFRONT  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def add_asymmetric_mesh() -> None:
    mesh = bpy.data.meshes.new("DefaultAxisMesh")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.0, 0.0, 3.0),
        ],
        [],
        [(0, 1, 2), (0, 3, 1)],
    )
    mesh.update()
    obj = bpy.data.objects.new("DefaultAxisMesh", mesh)
    bpy.context.collection.objects.link(obj)


def obj_vertices(path: Path) -> list[tuple[float, float, float]]:
    vertices = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("v "):
            continue
        values = line.split()
        vertices.append(tuple(float(value) for value in values[1:4]))
    return vertices


def assert_close(actual: tuple[float, ...], expected: tuple[float, ...]) -> None:
    if len(actual) != len(expected) or any(abs(a - b) > 1.0e-6 for a, b in zip(actual, expected)):
        raise AssertionError(f"OBJ default axis changed: expected {expected}, got {actual}")


def run_checks(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    reset_scene()
    add_asymmetric_mesh()
    path = out_root / "axis_default.obj"
    result = export_scene(bpy.context, path, AK_FILE_TYPE_WAVEFRONT)
    if result < 0:
        raise AssertionError(f"OBJ export failed: {result}")

    actual = obj_vertices(path)
    expected = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, -2.0),
        (0.0, 3.0, 0.0),
    ]
    if len(actual) != len(expected):
        raise AssertionError(f"OBJ exported {len(actual)} vertices, expected {len(expected)}")
    for value, want in zip(actual, expected):
        assert_close(value, want)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(tempfile.mkdtemp(prefix="assetkit-obj-check-")))
    args = parser.parse_args(argv)
    run_checks(args.out)
    print(f"OBJ export checks passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
