#!/usr/bin/env python3
"""Exercise BeamNG-relevant COLLADA naming and many-color-set round trips.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_beamng_dae_check.py
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_DAE  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


COLOR_SET_COUNT = 40


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_beamng_mesh() -> None:
    reset_scene()
    mesh = bpy.data.meshes.new("body_a800")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        [],
        [(0, 1, 2), (0, 2, 3)],
    )
    mesh.update()

    for set_index in range(COLOR_SET_COUNT):
        attr = mesh.color_attributes.new(
            name=f"beamng_color_{set_index:02d}",
            type="FLOAT_COLOR",
            domain="CORNER",
        )
        value = set_index / (COLOR_SET_COUNT - 1)
        for loop_index, item in enumerate(attr.data):
            item.color = (
                value,
                loop_index / max(1, len(attr.data) - 1),
                1.0 - value,
                1.0,
            )

    material = bpy.data.materials.new("body")
    mesh.materials.append(material)
    obj = bpy.data.objects.new("body_a800", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def inspect_dae(path: Path) -> None:
    root = ET.parse(path).getroot()
    inputs = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "input"
        and element.attrib.get("semantic") == "COLOR"
    ]
    sets = sorted(int(element.attrib["set"]) for element in inputs)
    if sets != list(range(COLOR_SET_COUNT)):
        raise AssertionError(f"COLLADA COLOR sets are incomplete: {sets}")

    geometry_names = {
        element.attrib.get("name") or element.attrib.get("id")
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "geometry"
    }
    if "body_a800" not in geometry_names:
        raise AssertionError(f"BeamNG LOD mesh name was not preserved: {geometry_names}")

    material_names = {
        element.attrib.get("name") or element.attrib.get("id")
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "material"
    }
    if "body" not in material_names:
        raise AssertionError(f"BeamNG material name was not preserved: {material_names}")


def inspect_reimport(path: Path) -> None:
    reset_scene()
    objects = import_assetkit_file(
        os.fspath(path),
        "",
        make_load_options(texture_loading="DEFERRED"),
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
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if len(mesh_objects) != 1:
        raise AssertionError(f"expected one reimported mesh, got {len(mesh_objects)}")
    obj = mesh_objects[0]
    if obj.name != "body_a800":
        raise AssertionError(f"BeamNG object name changed on reimport: {obj.name}")
    if len(obj.data.loop_triangles) != 2:
        obj.data.calc_loop_triangles()
    if len(obj.data.loop_triangles) != 2:
        raise AssertionError("BeamNG test mesh topology changed on reimport")
    if len(obj.data.color_attributes) != COLOR_SET_COUNT:
        raise AssertionError(
            "COLLADA color sets changed on reimport: "
            f"{len(obj.data.color_attributes)} != {COLOR_SET_COUNT}"
        )
    material_names = [material.name if material else None for material in obj.data.materials]
    if not material_names or material_names[0] != "body":
        raise AssertionError(
            f"BeamNG material binding changed on reimport: {material_names}"
        )


def write_mixed_surface_line_dae(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            <?xml version="1.0" encoding="utf-8"?>
            <COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
              <asset><up_axis>Z_UP</up_axis></asset>
              <library_effects>
                <effect id="body-effect"><profile_COMMON><technique sid="common"><lambert>
                  <diffuse><color>0.8 0.8 0.8 1</color></diffuse>
                </lambert></technique></profile_COMMON></effect>
              </library_effects>
              <library_materials>
                <material id="body" name="body"><instance_effect url="#body-effect"/></material>
                <material id="edge" name="edge"><instance_effect url="#body-effect"/></material>
              </library_materials>
              <library_geometries>
                <geometry id="body_a800-geometry" name="body_a800"><mesh>
                  <source id="body_a800-position">
                    <float_array id="body_a800-position-array" count="15">
                      0 0 0  1 0 0  0 1 0  2 0 0  2 1 0
                    </float_array>
                    <technique_common><accessor source="#body_a800-position-array" count="5" stride="3">
                      <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
                    </accessor></technique_common>
                  </source>
                  <vertices id="body_a800-vertices">
                    <input semantic="POSITION" source="#body_a800-position"/>
                  </vertices>
                  <triangles material="body" count="1">
                    <input semantic="VERTEX" source="#body_a800-vertices" offset="0"/>
                    <p>0 1 2</p>
                  </triangles>
                  <lines material="edge" count="1">
                    <input semantic="VERTEX" source="#body_a800-vertices" offset="0"/>
                    <p>3 4</p>
                  </lines>
                </mesh></geometry>
              </library_geometries>
              <library_visual_scenes>
                <visual_scene id="Scene" name="Scene"><node id="body_a800" name="body_a800">
                  <instance_geometry url="#body_a800-geometry">
                    <bind_material><technique_common>
                      <instance_material symbol="body" target="#body"/>
                      <instance_material symbol="edge" target="#edge"/>
                    </technique_common></bind_material>
                  </instance_geometry>
                </node></visual_scene>
              </library_visual_scenes>
              <scene><instance_visual_scene url="#Scene"/></scene>
            </COLLADA>
            """
        ),
        encoding="utf-8",
    )


def inspect_mixed_surface_line_roundtrip(
    source_path: Path,
    out_path: Path,
    *,
    expect_line_material: bool = True,
) -> None:
    reset_scene()
    objects = import_assetkit_file(
        os.fspath(source_path),
        "",
        make_load_options(texture_loading="DEFERRED"),
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
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if len(mesh_objects) != 1:
        raise AssertionError(
            f"mixed surface/line source split into {len(mesh_objects)} Blender meshes"
        )
    obj = mesh_objects[0]
    loose_edges = [edge for edge in obj.data.edges if edge.is_loose]
    if len(obj.data.polygons) != 1 or len(loose_edges) != 1:
        raise AssertionError(
            "mixed surface/line topology changed during import: "
            f"faces={len(obj.data.polygons)} loose_edges={len(loose_edges)}"
        )
    if "assetkit_mixed_line_material_slot" not in obj:
        raise AssertionError("mixed line material metadata was not retained")
    line_material_slot = int(obj["assetkit_mixed_line_material_slot"])
    if expect_line_material and line_material_slot < 0:
        raise AssertionError("mixed line material binding was not retained")
    if not expect_line_material and line_material_slot != -1:
        raise AssertionError(
            f"material-less mixed line gained a material slot: {line_material_slot}"
        )

    result = export_scene(bpy.context, out_path, AK_FILE_TYPE_DAE)
    if result < 0 or not out_path.is_file():
        raise AssertionError(f"mixed surface/line COLLADA export failed: {result}")
    root = ET.parse(out_path).getroot()
    line_nodes = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "lines"
    ]
    if len(line_nodes) != 1 or line_nodes[0].attrib.get("count") != "1":
        raise AssertionError(
            f"mixed line primitive did not round-trip: count={len(line_nodes)}"
        )

    reset_scene()
    reimported = import_assetkit_file(
        os.fspath(out_path),
        "",
        make_load_options(texture_loading="DEFERRED"),
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
    reimported_meshes = [item for item in reimported if item.type == "MESH"]
    if len(reimported_meshes) != 1:
        raise AssertionError(
            f"mixed surface/line round-trip split into {len(reimported_meshes)} meshes"
        )
    mesh = reimported_meshes[0].data
    if len(mesh.polygons) != 1 or sum(edge.is_loose for edge in mesh.edges) != 1:
        raise AssertionError("mixed surface/line topology changed after round-trip")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(tempfile.mkdtemp(prefix="assetkit-beamng-dae-")),
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    dae_path = args.out / "body_a800.dae"

    make_beamng_mesh()
    result = export_scene(bpy.context, dae_path, AK_FILE_TYPE_DAE)
    if result < 0 or not dae_path.is_file():
        raise AssertionError(f"COLLADA export failed: {result}")
    inspect_dae(dae_path)
    inspect_reimport(dae_path)
    mixed_source_path = args.out / "mixed_surface_line_source.dae"
    mixed_roundtrip_path = args.out / "mixed_surface_line_roundtrip.dae"
    write_mixed_surface_line_dae(mixed_source_path)
    inspect_mixed_surface_line_roundtrip(mixed_source_path, mixed_roundtrip_path)
    material_less_source_path = args.out / "mixed_surface_line_no_material_source.dae"
    material_less_roundtrip_path = args.out / "mixed_surface_line_no_material_roundtrip.dae"
    material_less_source_path.write_text(
        mixed_source_path.read_text(encoding="utf-8").replace(
            '<lines material="edge"',
            "<lines",
            1,
        ),
        encoding="utf-8",
    )
    inspect_mixed_surface_line_roundtrip(
        material_less_source_path,
        material_less_roundtrip_path,
        expect_line_material=False,
    )
    print(
        "BeamNG COLLADA checks passed: "
        f"{dae_path}; mixed surface/line: {mixed_roundtrip_path}; "
        f"material-less line: {material_less_roundtrip_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
