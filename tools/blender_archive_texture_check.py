"""Check that textures embedded beside DAE and glTF archive roots reach Blender.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_archive_texture_check.py
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import time
from zipfile import ZIP_DEFLATED, ZipFile

import bpy


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender import importer  # noqa: E402
from assetkit_blender.imp import textures  # noqa: E402
from assetkit_blender.imp.material import core as materials  # noqa: E402
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


def _write_image(root: Path) -> Path:
    image_path = root / "archive-check.png"
    image = bpy.data.images.new("archive-fixture", width=2, height=2, alpha=True)
    image.pixels = [1.0, 0.25, 0.0, 1.0] * 4
    image.filepath_raw = str(image_path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return image_path


def _write_dae_fixture(root: Path, image_path: Path) -> Path:
    archive_path = root / "archive-texture.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("model.dae", DAE)
        archive.write(image_path, "textures/archive-check.png")
    return archive_path


def _write_gltf_fixture(root: Path, image_path: Path) -> Path:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    texcoords = struct.pack("<6f", 0, 0, 1, 0, 0, 1)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + texcoords + indices
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "mesh.bin", "byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {
                "buffer": 0,
                "byteOffset": len(positions),
                "byteLength": len(texcoords),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(positions) + len(texcoords),
                "byteLength": len(indices),
                "target": 34963,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": 3,
                "type": "VEC2",
            },
            {
                "bufferView": 2,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
            },
        ],
        "images": [{"uri": "textures/archive-check.png"}],
        "textures": [{"source": 0}],
        "materials": [
            {
                "name": "archive-material",
                "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
            }
        ],
        "meshes": [
            {
                "name": "archive-geometry",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "indices": 2,
                        "material": 0,
                    }
                ],
            }
        ],
        "nodes": [{"name": "archive-node", "mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }

    archive_path = root / "generic-gltf.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("nested/deeper/ignored.ply", "not selected")
        archive.writestr("scene/model.gltf", json.dumps(gltf))
        archive.writestr("scene/mesh.bin", binary)
        archive.write(image_path, "scene/textures/archive-check.png")
    return archive_path


def _clear_scene_data() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _finish_deferred_textures() -> None:
    deadline = time.monotonic() + 5.0
    while (
        materials._DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
        or textures._DEFERRED_TEXTURE_TIMER_ACTIVE
    ) and time.monotonic() < deadline:
        if materials._DEFERRED_MATERIAL_NODE_TIMER_ACTIVE:
            materials._deferred_material_node_timer()
        if textures._DEFERRED_TEXTURE_TIMER_ACTIVE:
            textures._deferred_texture_timer()
        time.sleep(0.001)
    if (
        materials._DEFERRED_MATERIAL_NODE_TIMER_ACTIVE
        or textures._DEFERRED_TEXTURE_TIMER_ACTIVE
    ):
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
            f"{archive_path.name} {mode}: expected one assigned image texture node, "
            f"got nodes={len(texture_nodes)} assigned={len(assigned)}"
        )

    image = assigned[0].image
    resolved_path = Path(bpy.path.abspath(image.filepath))
    if not resolved_path.is_file() or resolved_path.stat().st_size == 0:
        raise AssertionError(
            f"{archive_path.name} {mode}: archive texture was not extracted: {resolved_path}"
        )
    if tuple(image.size) != (2, 2):
        raise AssertionError(
            f"{archive_path.name} {mode}: unexpected archive image size {tuple(image.size)}"
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-blender-archive-") as temp_dir:
        root = Path(temp_dir)
        image_path = _write_image(root)
        archives = (
            _write_dae_fixture(root, image_path),
            _write_gltf_fixture(root, image_path),
        )
        for archive_path in archives:
            for mode in ("IMMEDIATE", "DEFERRED"):
                _clear_scene_data()
                _assert_texture(mode, archive_path)

    print("AssetKit Blender archive texture checks passed")


if __name__ == "__main__":
    main()
