#!/usr/bin/env python3
"""Check COLLADA asset units across AssetKit coordinate-conversion modes.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_unit_check.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <unit meter="{meter}" name="{unit_name}"/>
    <up_axis>{up_axis}</up_axis>
  </asset>
  <library_geometries>
    <geometry id="unit-triangle" name="unit-triangle">
      <mesh>
        <source id="positions">
          <float_array id="positions-array" count="9">
            0 0 0  10 0 0  0 20 0
          </float_array>
          <technique_common>
            <accessor source="#positions-array" count="3" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="vertices">
          <input semantic="POSITION" source="#positions"/>
        </vertices>
        <triangles count="1">
          <input semantic="VERTEX" source="#vertices" offset="0"/>
          <p>0 1 2</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="parent" name="parent">
        <translate>100 200 300</translate>
        <node id="child" name="child">
          <translate>5 6 7</translate>
          <instance_geometry url="#unit-triangle"/>
        </node>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene>
    <instance_visual_scene url="#Scene"/>
  </scene>
</COLLADA>
"""


def _clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _world_bbox(objects: list[bpy.types.Object]) -> tuple[list[float], list[float]]:
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    mesh_count = 0
    for obj in objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mesh_count += 1
        for vertex in obj.data.vertices:
            world = obj.matrix_world @ vertex.co
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world[axis])
                maximum[axis] = max(maximum[axis], world[axis])
    if mesh_count != 1:
        raise AssertionError(f"expected one imported mesh, got {mesh_count}")
    return minimum, maximum


def _assert_close(actual: list[float], expected: list[float], label: str) -> None:
    for value, wanted in zip(actual, expected):
        if not math.isclose(value, wanted, rel_tol=1.0e-6, abs_tol=1.0e-6):
            raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _import_case(
    path: Path,
    conversion: str,
) -> tuple[list[float], list[float], list[bpy.types.Object]]:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion=conversion,
        texture_loading="DEFERRED",
    )
    objects = import_assetkit_file(
        str(path),
        load_options=options,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    bpy.context.view_layer.update()
    return (*_world_bbox(objects), objects)


def _write_fixture(
    directory: Path,
    name: str,
    *,
    meter: str,
    unit_name: str,
    up_axis: str = "Z_UP",
) -> Path:
    path = directory / name
    path.write_text(
        FIXTURE.format(meter=meter, unit_name=unit_name, up_axis=up_axis),
        encoding="utf-8",
    )
    return path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-unit-") as temp_dir:
        directory = Path(temp_dir)
        inch_path = _write_fixture(
            directory,
            "inch-z-up.dae",
            meter="0.0254",
            unit_name="inch",
        )
        centimeter_path = _write_fixture(
            directory,
            "centimeter-y-up.dae",
            meter="0.01",
            unit_name="centimeter",
            up_axis="Y_UP",
        )
        invalid_path = _write_fixture(
            directory,
            "invalid-unit.dae",
            meter="0",
            unit_name="broken",
        )

        minimum, maximum, _ = _import_case(inch_path, "TRANSFORM")
        _assert_close(
            minimum,
            [105.0 * 0.0254, 206.0 * 0.0254, 307.0 * 0.0254],
            "inch transform minimum",
        )
        _assert_close(
            maximum,
            [115.0 * 0.0254, 226.0 * 0.0254, 307.0 * 0.0254],
            "inch transform maximum",
        )
        roots = [
            obj
            for obj in bpy.data.objects
            if obj.get("assetkit_coordinate_root")
        ]
        if len(roots) != 1:
            raise AssertionError(f"expected one unit coordinate root, got {len(roots)}")
        _assert_close(list(roots[0].scale), [0.0254] * 3, "inch root scale")

        _clear_scene()
        minimum, maximum, _ = _import_case(inch_path, "RAW")
        _assert_close(minimum, [105.0, 206.0, 307.0], "raw minimum")
        _assert_close(maximum, [115.0, 226.0, 307.0], "raw maximum")
        if any(obj.get("assetkit_coordinate_root") for obj in bpy.data.objects):
            raise AssertionError("RAW import unexpectedly created a coordinate root")

        _clear_scene()
        minimum, maximum, _ = _import_case(inch_path, "ALL")
        _assert_close(
            minimum,
            [105.0 * 0.0254, 206.0 * 0.0254, 307.0 * 0.0254],
            "all minimum",
        )
        _assert_close(
            maximum,
            [115.0 * 0.0254, 226.0 * 0.0254, 307.0 * 0.0254],
            "all maximum",
        )

        _clear_scene()
        minimum, maximum, _ = _import_case(centimeter_path, "TRANSFORM")
        dimensions = sorted(maximum[i] - minimum[i] for i in range(3))
        _assert_close(dimensions, [0.0, 0.1, 0.2], "Y-up centimeter dimensions")

        _clear_scene()
        minimum, maximum, _ = _import_case(invalid_path, "TRANSFORM")
        _assert_close(minimum, [105.0, 206.0, 307.0], "invalid-unit minimum")
        _assert_close(maximum, [115.0, 226.0, 307.0], "invalid-unit maximum")

    print("DAE asset unit check passed")


if __name__ == "__main__":
    main()
