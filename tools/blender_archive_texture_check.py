"""Check that textures embedded beside a DAE inside an archive reach Blender.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_archive_texture_check.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
from zipfile import ZIP_DEFLATED, ZipFile

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assetkit_blender import importer  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><up_axis>Z_UP</up_axis></asset>
  <library_images>
    <image id="archive-image" name="archive-image">
      <init_from>textures/archive-check.png</init_from>
    </image>
  </library_images>
  <library_effects>
    <effect id="archive-effect">
      <profile_COMMON>
        <newparam sid="archive-surface">
          <surface type="2D"><init_from>archive-image</init_from></surface>
        </newparam>
        <newparam sid="archive-sampler">
          <sampler2D><source>archive-surface</source></sampler2D>
        </newparam>
        <technique sid="common">
          <lambert>
            <diffuse><texture texture="archive-sampler" texcoord="UVMap"/></diffuse>
          </lambert>
        </technique>
      </profile_COMMON>
    </effect>
  </library_effects>
  <library_materials>
    <material id="archive-material" name="archive-material">
      <instance_effect url="#archive-effect"/>
    </material>
  </library_materials>
  <library_geometries>
    <geometry id="archive-geometry" name="archive-geometry">
      <mesh>
        <source id="archive-positions">
          <float_array id="archive-positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array>
          <technique_common>
            <accessor source="#archive-positions-array" count="3" stride="3">
              <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="archive-uvs">
          <float_array id="archive-uvs-array" count="6">0 0 1 0 0 1</float_array>
          <technique_common>
            <accessor source="#archive-uvs-array" count="3" stride="2">
              <param name="S" type="float"/><param name="T" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="archive-vertices">
          <input semantic="POSITION" source="#archive-positions"/>
        </vertices>
        <triangles material="archive-symbol" count="1">
          <input semantic="VERTEX" source="#archive-vertices" offset="0"/>
          <input semantic="TEXCOORD" source="#archive-uvs" offset="1" set="0"/>
          <p>0 0 1 1 2 2</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_visual_scenes>
    <visual_scene id="archive-scene" name="archive-scene">
      <node id="archive-node" name="archive-node">
        <instance_geometry url="#archive-geometry">
          <bind_material>
            <technique_common>
              <instance_material symbol="archive-symbol" target="#archive-material">
                <bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/>
              </instance_material>
            </technique_common>
          </bind_material>
        </instance_geometry>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#archive-scene"/></scene>
</COLLADA>
"""


def _write_fixture(root: Path) -> Path:
    image_path = root / "archive-check.png"
    image = bpy.data.images.new("archive-fixture", width=2, height=2, alpha=True)
    image.pixels = [1.0, 0.25, 0.0, 1.0] * 4
    image.filepath_raw = str(image_path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)

    archive_path = root / "archive-texture.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("model.dae", DAE)
        archive.write(image_path, "textures/archive-check.png")
    return archive_path


def _clear_scene_data() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _finish_deferred_textures() -> None:
    deadline = time.monotonic() + 5.0
    while importer._DEFERRED_TEXTURE_TIMER_ACTIVE and time.monotonic() < deadline:
        importer._deferred_texture_timer()
        time.sleep(0.001)
    if importer._DEFERRED_TEXTURE_TIMER_ACTIVE:
        raise AssertionError("deferred archive texture load did not settle")


def _assert_texture(mode: str, archive_path: Path) -> None:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        import_lines=True,
        texture_loading=mode,
    )
    importer.import_assetkit_file(
        str(archive_path),
        "",
        options,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        set_viewport_shading=False,
        clean_viewport_overlays=False,
    )
    if mode == "DEFERRED":
        _finish_deferred_textures()

    texture_nodes = [
        node
        for material in bpy.data.materials
        if material.node_tree
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE"
    ]
    assigned = [node for node in texture_nodes if node.image is not None]
    if len(texture_nodes) != 1 or len(assigned) != 1:
        raise AssertionError(
            f"{mode}: expected one assigned image texture node, "
            f"got nodes={len(texture_nodes)} assigned={len(assigned)}"
        )

    image = assigned[0].image
    resolved_path = Path(bpy.path.abspath(image.filepath))
    if not resolved_path.is_file() or resolved_path.stat().st_size == 0:
        raise AssertionError(f"{mode}: archive texture was not extracted: {resolved_path}")
    if tuple(image.size) != (2, 2):
        raise AssertionError(f"{mode}: unexpected archive image size {tuple(image.size)}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-blender-archive-") as temp_dir:
        archive_path = _write_fixture(Path(temp_dir))
        for mode in ("IMMEDIATE", "DEFERRED"):
            _clear_scene_data()
            _assert_texture(mode, archive_path)

    print("AssetKit Blender archive texture checks passed")


if __name__ == "__main__":
    main()
