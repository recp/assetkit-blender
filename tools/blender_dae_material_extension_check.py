#!/usr/bin/env python3
"""Exercise supported COLLADA material extensions through Blender.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_material_extension_check.py
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_DAE  # noqa: E402
from assetkit_blender.exp.core import export_scene  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(b"\x00\x80\x80\x80"))
    + png_chunk(b"IEND", b"")
)

DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_images>
    <image id="height-image"><init_from>height.png</init_from></image>
    <image id="normal-image"><init_from>normal.png</init_from></image>
    <image id="specular-image"><init_from>specular.png</init_from></image>
  </library_images>
  <library_effects>
    <effect id="height-effect"><profile_COMMON>
      <newparam sid="height-surface"><surface type="2D"><init_from>height-image</init_from></surface></newparam>
      <newparam sid="height-sampler"><sampler2D><source>height-surface</source></sampler2D></newparam>
      <newparam sid="specular-surface"><surface type="2D"><init_from>specular-image</init_from></surface></newparam>
      <newparam sid="specular-sampler"><sampler2D><source>specular-surface</source></sampler2D></newparam>
      <technique sid="common"><phong>
        <diffuse><color>0.3 0.3 0.3 1</color></diffuse>
        <specular><color>1 1 1 1</color></specular><shininess><float>24</float></shininess>
      </phong><extra><technique profile="OpenCOLLADA3dsMax">
        <specularLevel><texture texture="specular-sampler" texcoord="TEXCOORD0">
          <extra><technique profile="MAX3D"><amount>0.65</amount></technique></extra>
        </texture></specularLevel>
        <bump bumptype="HEIGHTFIELD"><texture texture="height-sampler" texcoord="TEXCOORD0">
          <extra><technique profile="MAX3D"><amount>0.35</amount></technique></extra>
        </texture></bump>
      </technique></extra></technique>
    </profile_COMMON></effect>
    <effect id="normal-effect"><profile_COMMON>
      <newparam sid="normal-surface"><surface type="2D"><init_from>normal-image</init_from></surface></newparam>
      <newparam sid="normal-sampler"><sampler2D><source>normal-surface</source></sampler2D></newparam>
      <technique sid="common"><phong><diffuse><color>0.4 0.4 0.4 1</color></diffuse></phong>
        <extra><technique profile="FCOLLADA"><bump bumptype="NORMALMAP">
          <texture texture="normal-sampler" texcoord="TEXCOORD0"/>
        </bump></technique></extra>
      </technique>
    </profile_COMMON></effect>
  </library_effects>
  <library_materials>
    <material id="height-material" name="HeightMaterial"><instance_effect url="#height-effect"/></material>
    <material id="normal-material" name="NormalMaterial"><instance_effect url="#normal-effect"/></material>
  </library_materials>
  <library_geometries><geometry id="triangle"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array>
      <technique_common><accessor source="#positions-array" count="3" stride="3">
        <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
      </accessor></technique_common></source>
    <source id="uvs"><float_array id="uvs-array" count="6">0 0 1 0 0 1</float_array>
      <technique_common><accessor source="#uvs-array" count="3" stride="2">
        <param name="S" type="float"/><param name="T" type="float"/>
      </accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1" material="material-symbol">
      <input semantic="VERTEX" source="#vertices" offset="0"/>
      <input semantic="TEXCOORD" source="#uvs" offset="1" set="0"/>
      <p>0 0 1 1 2 2</p>
    </triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="height-node" name="HeightNode"><instance_geometry url="#triangle"><bind_material><technique_common>
      <instance_material symbol="material-symbol" target="#height-material">
        <bind_vertex_input semantic="TEXCOORD0" input_semantic="TEXCOORD" input_set="0"/>
      </instance_material>
    </technique_common></bind_material></instance_geometry></node>
    <node id="normal-node" name="NormalNode"><translate>2 0 0</translate><instance_geometry url="#triangle"><bind_material><technique_common>
      <instance_material symbol="material-symbol" target="#normal-material">
        <bind_vertex_input semantic="TEXCOORD0" input_semantic="TEXCOORD" input_set="0"/>
      </instance_material>
    </technique_common></bind_material></instance_geometry></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    for image in list(bpy.data.images):
        bpy.data.images.remove(image)


def import_dae(path: Path) -> None:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="RAW",
        texture_loading="IMMEDIATE",
    )
    imported = import_assetkit_file(
        os.fspath(path),
        load_options=options,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    if not imported:
        raise AssertionError("DAE import produced no objects")


def material_named(name: str) -> bpy.types.Material:
    material = next((mat for mat in bpy.data.materials if name.lower() in mat.name.lower()), None)
    if material is None or material.node_tree is None:
        raise AssertionError(f"missing node material: {name}")
    return material


def assert_material_graphs() -> None:
    height = material_named("HeightMaterial")
    height_nodes = list(height.node_tree.nodes)
    bump = next((node for node in height_nodes if node.type == "BUMP"), None)
    if bump is None or bump.get("assetkit_normal_kind") != "height":
        raise AssertionError("HEIGHTFIELD did not become a tagged Blender Bump node")
    if abs(float(bump.inputs["Strength"].default_value) - 0.35) > 1.0e-5:
        raise AssertionError("HEIGHTFIELD amount was not preserved")
    if any(node.type == "NORMAL_MAP" for node in height_nodes):
        raise AssertionError("HEIGHTFIELD was also interpreted as a tangent normal map")

    level = next(
        (node for node in height_nodes if node.get("assetkit_specular_kind") == "level"),
        None,
    )
    if level is None:
        raise AssertionError("specularLevel did not reach the Blender graph")
    if abs(float(level.get("assetkit_specular_factor", -1.0)) - 0.65) > 1.0e-5:
        raise AssertionError("specularLevel amount was not preserved")

    normal = material_named("NormalMaterial")
    normal_nodes = list(normal.node_tree.nodes)
    normal_map = next((node for node in normal_nodes if node.type == "NORMAL_MAP"), None)
    if normal_map is None or normal_map.get("assetkit_normal_kind") != "normal":
        raise AssertionError("NORMALMAP did not become a tagged Blender Normal Map node")
    if any(node.type == "BUMP" for node in normal_nodes):
        raise AssertionError("NORMALMAP was incorrectly interpreted as height")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="assetkit-dae-material-ext-"))
    source = root / "material_extensions.dae"
    exported = root / "material_extensions_roundtrip.dae"
    source.write_text(DAE, encoding="utf-8")
    for name in ("height.png", "normal.png", "specular.png"):
        (root / name).write_bytes(PNG_1X1)

    reset_scene()
    import_dae(source)
    assert_material_graphs()

    result = export_scene(bpy.context, exported, AK_FILE_TYPE_DAE)
    if result < 0 or not exported.exists():
        raise AssertionError("DAE material extension export failed")
    output = exported.read_text(encoding="utf-8")
    for marker in ('bumptype="HEIGHTFIELD"', 'bumptype="NORMALMAP"', "<specularLevel>"):
        if marker not in output:
            raise AssertionError(f"round-trip DAE is missing {marker}")

    reset_scene()
    import_dae(exported)
    assert_material_graphs()
    print(f"AssetKit DAE material extension round-trip passed: {exported}")


if __name__ == "__main__":
    main()
