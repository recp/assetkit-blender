#!/usr/bin/env python3
"""Check that native Blender export preserves COLLADA classic material types.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_classic_material_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
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


EXPECTED_TYPES = {
    "PhongMaterial": ("phong", 1),
    "BlinnMaterial": ("blinn", 2),
    "LambertMaterial": ("lambert", 3),
    "ConstantMaterial": ("constant", 4),
}

DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_effects>
    <effect id="phong-effect"><profile_COMMON><technique sid="common"><phong>
      <diffuse><color>0.8 0.2 0.1 1</color></diffuse>
      <specular><color>0.3 0.3 0.3 1</color></specular><shininess><float>24</float></shininess>
    </phong></technique></profile_COMMON></effect>
    <effect id="blinn-effect"><profile_COMMON><technique sid="common"><blinn>
      <diffuse><color>0.1 0.8 0.2 1</color></diffuse>
      <specular><color>0.2 0.2 0.2 1</color></specular><shininess><float>18</float></shininess>
    </blinn></technique></profile_COMMON></effect>
    <effect id="lambert-effect"><profile_COMMON><technique sid="common"><lambert>
      <diffuse><color>0.2 0.1 0.8 1</color></diffuse>
    </lambert></technique></profile_COMMON></effect>
    <effect id="constant-effect"><profile_COMMON><technique sid="common"><constant>
      <emission><color>0.7 0.6 0.2 1</color></emission>
    </constant></technique></profile_COMMON></effect>
  </library_effects>
  <library_materials>
    <material id="phong-material" name="PhongMaterial"><instance_effect url="#phong-effect"/></material>
    <material id="blinn-material" name="BlinnMaterial"><instance_effect url="#blinn-effect"/></material>
    <material id="lambert-material" name="LambertMaterial"><instance_effect url="#lambert-effect"/></material>
    <material id="constant-material" name="ConstantMaterial"><instance_effect url="#constant-effect"/></material>
  </library_materials>
  <library_geometries><geometry id="classic-geometry"><mesh>
    <source id="positions"><float_array id="positions-array" count="36">
      0 0 0 1 0 0 0 1 0
      2 0 0 3 0 0 2 1 0
      4 0 0 5 0 0 4 1 0
      6 0 0 7 0 0 6 1 0
    </float_array><technique_common><accessor source="#positions-array" count="12" stride="3">
      <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
    </accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1" material="phong-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
    <triangles count="1" material="blinn-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>3 4 5</p></triangles>
    <triangles count="1" material="lambert-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>6 7 8</p></triangles>
    <triangles count="1" material="constant-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>9 10 11</p></triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene"><node id="classic-node" name="ClassicNode">
    <instance_geometry url="#classic-geometry"><bind_material><technique_common>
      <instance_material symbol="phong-symbol" target="#phong-material"/>
      <instance_material symbol="blinn-symbol" target="#blinn-material"/>
      <instance_material symbol="lambert-symbol" target="#lambert-material"/>
      <instance_material symbol="constant-symbol" target="#constant-material"/>
    </technique_common></bind_material></instance_geometry>
  </node></visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_dae(path: Path) -> None:
    imported = import_assetkit_file(
        os.fspath(path),
        load_options=make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="RAW",
            texture_loading="DEFERRED",
        ),
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    if not imported:
        raise AssertionError(f"DAE import produced no objects: {path}")


def assert_blender_types(label: str) -> None:
    for name, (_tag, expected_type) in EXPECTED_TYPES.items():
        material = bpy.data.materials.get(name)
        if material is None:
            raise AssertionError(f"{label}: missing material {name}")
        actual_type = int(material.get("assetkit_material_type", 0))
        if actual_type != expected_type:
            raise AssertionError(
                f"{label}: {name} expected AssetKit type {expected_type}, got {actual_type}"
            )


def output_techniques(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    namespace = root.tag.partition("}")[0].lstrip("{")
    ns = {"c": namespace}
    effects = {
        effect.get("id", ""): effect
        for effect in root.findall("c:library_effects/c:effect", ns)
    }
    result: dict[str, str] = {}
    for material in root.findall("c:library_materials/c:material", ns):
        name = material.get("name", "")
        instance = material.find("c:instance_effect", ns)
        if instance is None:
            continue
        effect = effects.get(instance.get("url", "").lstrip("#"))
        technique = effect.find("c:profile_COMMON/c:technique", ns) if effect is not None else None
        shader = next(iter(technique), None) if technique is not None else None
        if shader is not None:
            result[name] = shader.tag.rsplit("}", 1)[-1]
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-classic-") as temp_dir:
        root = Path(temp_dir)
        source = root / "classic.dae"
        exported = root / "classic-roundtrip.dae"
        source.write_text(DAE, encoding="utf-8")

        reset_scene()
        import_dae(source)
        assert_blender_types("source import")

        result = export_scene(bpy.context, exported, AK_FILE_TYPE_DAE)
        if result < 0 or not exported.is_file():
            raise AssertionError(f"native DAE export failed: {result}")
        techniques = output_techniques(exported)
        for name, (expected_tag, _expected_type) in EXPECTED_TYPES.items():
            actual_tag = techniques.get(name)
            if actual_tag != expected_tag:
                raise AssertionError(
                    f"native export changed {name} from {expected_tag} to {actual_tag}"
                )

        reset_scene()
        import_dae(exported)
        assert_blender_types("round-trip import")

    print("DAE classic material type round-trip passed")


if __name__ == "__main__":
    main()
