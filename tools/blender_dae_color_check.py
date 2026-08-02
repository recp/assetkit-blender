#!/usr/bin/env python3
"""Check that Blender receives AssetKit's canonical colors unchanged.

AssetKit converts SceneKit-authored COLLADA constants to linear-sRGB at the
format boundary. This integration check uses the already-linear expected value
and must fail if the Blender bridge applies a second decode.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_color_check.py
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


DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <contributor><authoring_tool>{authoring_tool}</authoring_tool></contributor>
    <unit meter="1" name="meter"/><up_axis>Z_UP</up_axis>
  </asset>
  <library_effects>
    <effect id="paint-effect"><profile_COMMON><technique sid="common"><phong>
      <diffuse><color>0.4 0.0980392 0 1</color></diffuse>
      <specular><color>0 0 0 1</color></specular>
      <shininess><float>0</float></shininess>
    </phong></technique></profile_COMMON></effect>
  </library_effects>
  <library_materials>
    <material id="paint" name="paint"><instance_effect url="#paint-effect"/></material>
  </library_materials>
  <library_geometries><geometry id="triangle" name="triangle"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array>
      <technique_common><accessor source="#positions-array" count="3" stride="3">
        <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
      </accessor></technique_common>
    </source>
    <source id="colors"><float_array id="colors-array" count="12">0.4 0.0980392 0 1 0.4 0.0980392 0 1 0.4 0.0980392 0 1</float_array>
      <technique_common><accessor source="#colors-array" count="3" stride="4">
        <param name="R" type="float"/><param name="G" type="float"/><param name="B" type="float"/><param name="A" type="float"/>
      </accessor></technique_common>
    </source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1" material="paint-symbol">
      <input semantic="VERTEX" source="#vertices" offset="0"/>
      <input semantic="COLOR" source="#colors" offset="1" set="0"/><p>0 0 1 1 2 2</p>
    </triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene" name="Scene"><node id="node" name="node">
    <instance_geometry url="#triangle"><bind_material><technique_common>
      <instance_material symbol="paint-symbol" target="#paint"/>
    </technique_common></bind_material></instance_geometry>
  </node></visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def _import_colors(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="RAW",
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
    mesh_objects = [obj for obj in objects if obj.type == "MESH" and obj.data]
    if len(mesh_objects) != 1:
        raise AssertionError(f"expected one mesh object, got {len(mesh_objects)}")
    materials = mesh_objects[0].data.materials
    if len(materials) != 1 or materials[0] is None:
        raise AssertionError("expected one imported material")
    material = materials[0]
    if not material.use_nodes or material.node_tree is None:
        raise AssertionError("expected a node material")
    bsdf = next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if bsdf is None:
        raise AssertionError("expected a Principled BSDF")
    socket = bsdf.inputs.get("Base Color")
    if socket is None:
        raise AssertionError("expected a Base Color input")
    color_attribute = mesh_objects[0].data.color_attributes.get("Color")
    if color_attribute is None or not color_attribute.data:
        raise AssertionError("expected a Color corner attribute")
    return (
        tuple(float(component) for component in socket.default_value),
        tuple(float(component) for component in color_attribute.data[0].color),
    )


def _assert_color(actual: tuple[float, ...], expected: tuple[float, ...], label: str) -> None:
    if len(actual) != len(expected):
        raise AssertionError(f"{label}: component count changed")
    for got, wanted in zip(actual, expected):
        if not math.isclose(got, wanted, rel_tol=1.0e-5, abs_tol=1.0e-5):
            raise AssertionError(f"{label}: expected {expected}, got {actual}")


def main() -> None:
    source = (0.4, 0.0980392, 0.0, 1.0)
    scenekit_linear = (0.13286832, 0.009721215, 0.0, 1.0)
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-color-") as temp_dir:
        directory = Path(temp_dir)
        scenekit_path = directory / "scenekit.dae"
        generic_path = directory / "generic.dae"
        scenekit_path.write_text(
            DAE.format(authoring_tool="SceneKit Collada Exporter v1.0"),
            encoding="utf-8",
        )
        generic_path.write_text(
            DAE.format(authoring_tool="Blender 4.5"),
            encoding="utf-8",
        )

        material_color, vertex_color = _import_colors(scenekit_path)
        _assert_color(material_color, scenekit_linear, "SceneKit DAE material")
        _assert_color(vertex_color, scenekit_linear, "SceneKit DAE vertex")

        bpy.ops.wm.read_factory_settings(use_empty=True)
        material_color, vertex_color = _import_colors(generic_path)
        _assert_color(material_color, source, "generic DAE material")
        _assert_color(vertex_color, source, "generic DAE vertex")

    print("DAE color-space check passed")


if __name__ == "__main__":
    main()
