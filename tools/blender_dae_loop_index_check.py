#!/usr/bin/env python3
"""Check that DAE loop attributes honor non-identity multi-indices.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_loop_index_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from array import array
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.importer import _apply_shading, import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <unit meter="1" name="meter"/>
    <up_axis>Z_UP</up_axis>
  </asset>
  <library_geometries>
    <geometry id="indexed-attrs" name="indexed-attrs">
      <mesh>
        <source id="positions">
          <float_array id="positions-array" count="18">
            0 0 0  1 0 0  1 1 0  0 1 0  2 0 0  2 1 0
          </float_array>
          <technique_common>
            <accessor source="#positions-array" count="6" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="normals">
          <float_array id="normals-array" count="18">
            1 0 0  0 1 0  0 0 1  -1 0 0  0 -1 0  0 0 -1
          </float_array>
          <technique_common>
            <accessor source="#normals-array" count="6" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="uvs">
          <float_array id="uvs-array" count="12">
            0.01 0.11  0.02 0.12  0.03 0.13
            0.04 0.14  0.05 0.15  0.06 0.16
          </float_array>
          <technique_common>
            <accessor source="#uvs-array" count="6" stride="2">
              <param name="S" type="float"/>
              <param name="T" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="vertices">
          <input semantic="POSITION" source="#positions"/>
        </vertices>
        <triangles count="2">
          <input semantic="VERTEX" source="#vertices" offset="0"/>
          <input semantic="NORMAL" source="#normals" offset="1"/>
          <input semantic="TEXCOORD" source="#uvs" offset="2" set="0"/>
          <p>
            0 5 5  1 4 4  2 3 3
            3 2 2  4 1 1  5 0 0
          </p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="indexed-attrs-node" name="indexed-attrs-node">
        <instance_geometry url="#indexed-attrs"/>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene>
    <instance_visual_scene url="#Scene"/>
  </scene>
</COLLADA>
"""


def float_values(buffer: object) -> list[float]:
    view = memoryview(buffer)
    if view.format != "f":
        view = view.cast("f")
    return list(view)


def assert_blender_custom_normals(
    mesh: bpy.types.Mesh,
    expected_normals: list[tuple[float, float, float]],
    expected_domain: str,
) -> None:
    custom_normal = mesh.attributes.get("custom_normal")
    if custom_normal is None:
        raise AssertionError("missing free custom_normal attribute")
    if custom_normal.domain != expected_domain or custom_normal.data_type != "FLOAT_VECTOR":
        raise AssertionError(
            "unexpected custom_normal layout: "
            f"{custom_normal.domain}/{custom_normal.data_type}"
        )

    blender_normal_values = array("f", [0.0]) * (len(mesh.loops) * 3)
    mesh.corner_normals.foreach_get("vector", blender_normal_values)
    blender_normals = list(
        zip(
            blender_normal_values[0::3],
            blender_normal_values[1::3],
            blender_normal_values[2::3],
        )
    )
    for actual, expected in zip(blender_normals, expected_normals):
        if any(abs(a - e) > 1e-6 for a, e in zip(actual, expected)):
            raise AssertionError(f"Blender custom normals differ: {blender_normals}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-index-") as temp_dir:
        path = Path(temp_dir) / "indexed-attrs.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        options = make_load_options(texture_loading="DEFERRED")
        loaded = native_load_meshes(
            os.fspath(path),
            options,
        )
        objects = import_assetkit_file(
            os.fspath(path),
            load_options=options,
            collection=bpy.context.collection,
            focus_mode="NEVER",
            placement_mode="AS_AUTHORED",
            select_imported=False,
            shading_mode="AUTO",
            set_viewport_shading=False,
            clean_viewport_overlays=False,
        )

    if loaded is None or len(loaded.meshes) != 1:
        raise AssertionError("expected exactly one native mesh")

    mesh = loaded.meshes[0]
    uvs = float_values(mesh.uvs_f32)
    normals = float_values(mesh.normals_f32)
    vertex_normals = float_values(mesh.vertex_normals_f32)
    expected_u = [0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
    actual_u = uvs[0::2]
    if len(actual_u) != len(expected_u):
        raise AssertionError(f"unexpected UV count: {len(actual_u)}")
    for actual, expected in zip(actual_u, expected_u):
        if abs(actual - expected) > 1e-6:
            raise AssertionError(f"UV multi-index ignored: {actual_u}")

    expected_normals = [
        (0.0, 0.0, -1.0),
        (0.0, -1.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
    ]
    normal_values = normals or vertex_normals
    actual_normals = list(
        zip(normal_values[0::3], normal_values[1::3], normal_values[2::3])
    )
    if actual_normals != expected_normals:
        raise AssertionError(f"normal multi-index ignored: {actual_normals}")

    imported_meshes = [
        obj.data for obj in objects if obj.type == "MESH" and obj.data is not None
    ]
    if len(imported_meshes) != 1:
        raise AssertionError(f"expected one imported Blender mesh, got {len(imported_meshes)}")

    imported_mesh = imported_meshes[0]
    assert_blender_custom_normals(imported_mesh, expected_normals, "POINT")

    corner_mesh = bpy.data.meshes.new("indexed-corner-normal-check")
    corner_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2), (0, 2, 3)],
    )
    corner_values = array("f", (component for normal in expected_normals for component in normal))
    if not _apply_shading(corner_mesh, "AUTO", memoryview(corner_values)):
        raise AssertionError("failed to apply corner custom normals")
    assert_blender_custom_normals(corner_mesh, expected_normals, "CORNER")

    print("DAE indexed loop attribute check passed")


if __name__ == "__main__":
    main()
