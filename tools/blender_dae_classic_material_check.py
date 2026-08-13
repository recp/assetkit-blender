#!/usr/bin/env python3
"""Check that native Blender export preserves COLLADA classic material types.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_classic_material_check.py
"""

from __future__ import annotations

import math
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
from assetkit_blender.assetkit import TextureRefData, native_load_meshes  # noqa: E402
from assetkit_blender.imp import textures as _textures  # noqa: E402
from assetkit_blender.imp.material import core as _materials  # noqa: E402
from assetkit_blender.imp.material import shader as _shader  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


EXPECTED_TYPES = {
    "PhongMaterial": ("phong", 1),
    "BlinnMaterial": ("blinn", 2),
    "LambertMaterial": ("lambert", 3),
    "ConstantMaterial": ("constant", 4),
    "PhongQuarterMaterial": ("phong", 1),
    "PhongZeroMaterial": ("phong", 1),
    "SpecularTextureMaterial": ("phong", 1),
}

EXPECTED_CLASSIC = {
    # name: (canonical exponent, Blender roughness, classic specular level)
    "PhongMaterial": (20.0, math.sqrt(2.0 / 22.0), 0.3),
    "PhongQuarterMaterial": (32.0, math.sqrt(2.0 / 34.0), 0.4),
    "BlinnMaterial": (64.0, math.sqrt(2.0 / 66.0), 0.2),
    "PhongZeroMaterial": (0.0, 1.0, 0.5),
}

DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_images>
    <image id="specular-image"><init_from>{texture}</init_from></image>
  </library_images>
  <library_effects>
    <effect id="phong-effect"><profile_COMMON><technique sid="common"><phong>
      <diffuse><color>0.8 0.2 0.1 1</color></diffuse>
      <specular><color>0.3 0.3 0.3 1</color></specular>
    </phong></technique></profile_COMMON></effect>
    <effect id="blinn-effect"><profile_COMMON><technique sid="common"><blinn>
      <diffuse><color>0.1 0.8 0.2 1</color></diffuse>
      <specular><color>0.2 0.2 0.2 1</color></specular><shininess><float>0.5</float></shininess>
    </blinn></technique></profile_COMMON></effect>
    <effect id="lambert-effect"><profile_COMMON><technique sid="common"><lambert>
      <diffuse><color>0.2 0.1 0.8 1</color></diffuse>
    </lambert></technique></profile_COMMON></effect>
    <effect id="constant-effect"><profile_COMMON><technique sid="common"><constant>
      <emission><color>0.7 0.6 0.2 1</color></emission>
    </constant></technique></profile_COMMON></effect>
    <effect id="phong-quarter-effect"><profile_COMMON><technique sid="common"><phong>
      <diffuse><color>0.6 0.3 0.1 1</color></diffuse>
      <specular><color>0.4 0.4 0.4 1</color></specular><shininess><float>0.25</float></shininess>
    </phong></technique></profile_COMMON></effect>
    <effect id="phong-zero-effect"><profile_COMMON><technique sid="common"><phong>
      <diffuse><color>0.3 0.2 0.7 1</color></diffuse>
      <specular><color>0.5 0.5 0.5 1</color></specular><shininess><float>0</float></shininess>
    </phong></technique></profile_COMMON></effect>
    <effect id="specular-texture-effect"><profile_COMMON>
      <newparam sid="specular-surface"><surface type="2D"><init_from>specular-image</init_from></surface></newparam>
      <newparam sid="specular-sampler"><sampler2D><source>specular-surface</source></sampler2D></newparam>
      <technique sid="common"><phong>
        <diffuse><color>0.4 0.4 0.4 1</color></diffuse>
        <specular><texture texture="specular-sampler" texcoord="TEX0"/></specular>
        <shininess><float>0.5</float></shininess>
      </phong></technique>
    </profile_COMMON></effect>
  </library_effects>
  <library_materials>
    <material id="phong-material" name="PhongMaterial"><instance_effect url="#phong-effect"/></material>
    <material id="blinn-material" name="BlinnMaterial"><instance_effect url="#blinn-effect"/></material>
    <material id="lambert-material" name="LambertMaterial"><instance_effect url="#lambert-effect"/></material>
    <material id="constant-material" name="ConstantMaterial"><instance_effect url="#constant-effect"/></material>
    <material id="phong-quarter-material" name="PhongQuarterMaterial"><instance_effect url="#phong-quarter-effect"/></material>
    <material id="phong-zero-material" name="PhongZeroMaterial"><instance_effect url="#phong-zero-effect"/></material>
    <material id="specular-texture-material" name="SpecularTextureMaterial"><instance_effect url="#specular-texture-effect"/></material>
  </library_materials>
  <library_geometries><geometry id="classic-geometry"><mesh>
    <source id="positions"><float_array id="positions-array" count="63">
      0 0 0 1 0 0 0 1 0
      2 0 0 3 0 0 2 1 0
      4 0 0 5 0 0 4 1 0
      6 0 0 7 0 0 6 1 0
      8 0 0 9 0 0 8 1 0
      10 0 0 11 0 0 10 1 0
      12 0 0 13 0 0 12 1 0
    </float_array><technique_common><accessor source="#positions-array" count="21" stride="3">
      <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
    </accessor></technique_common></source>
    <source id="texcoords"><float_array id="texcoords-array" count="6">0 0 1 0 0 1</float_array>
      <technique_common><accessor source="#texcoords-array" count="3" stride="2">
        <param name="S" type="float"/><param name="T" type="float"/>
      </accessor></technique_common>
    </source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1" material="phong-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
    <triangles count="1" material="blinn-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>3 4 5</p></triangles>
    <triangles count="1" material="lambert-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>6 7 8</p></triangles>
    <triangles count="1" material="constant-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>9 10 11</p></triangles>
    <triangles count="1" material="phong-quarter-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>12 13 14</p></triangles>
    <triangles count="1" material="phong-zero-symbol"><input semantic="VERTEX" source="#vertices" offset="0"/><p>15 16 17</p></triangles>
    <triangles count="1" material="specular-texture-symbol">
      <input semantic="VERTEX" source="#vertices" offset="0"/>
      <input semantic="TEXCOORD" source="#texcoords" offset="1" set="0"/>
      <p>18 0 19 1 20 2</p>
    </triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene"><node id="classic-node" name="ClassicNode">
    <instance_geometry url="#classic-geometry"><bind_material><technique_common>
      <instance_material symbol="phong-symbol" target="#phong-material"/>
      <instance_material symbol="blinn-symbol" target="#blinn-material"/>
      <instance_material symbol="lambert-symbol" target="#lambert-material"/>
      <instance_material symbol="constant-symbol" target="#constant-material"/>
      <instance_material symbol="phong-quarter-symbol" target="#phong-quarter-material"/>
      <instance_material symbol="phong-zero-symbol" target="#phong-zero-material"/>
      <instance_material symbol="specular-texture-symbol" target="#specular-texture-material">
        <bind_vertex_input semantic="TEX0" input_semantic="TEXCOORD" input_set="0"/>
      </instance_material>
    </technique_common></bind_material></instance_geometry>
  </node></visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""

TEXTURE_DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_images>
    <image id="image"><init_from>{texture}</init_from></image>
  </library_images>
  <library_effects>
    <effect id="texture-effect"><profile_COMMON>
      <newparam sid="surface"><surface type="2D"><init_from>image</init_from></surface></newparam>
      <newparam sid="sampler"><sampler2D><source>surface</source></sampler2D></newparam>
      <technique sid="common"><phong>
        <diffuse><texture texture="sampler" texcoord="TEX0"/></diffuse>
        <specular><color>0.2 0.2 0.2 1</color></specular>
        <shininess><float>8</float></shininess>
      </phong></technique>
    </profile_COMMON></effect>
  </library_effects>
  <library_materials>
    <material id="texture-material" name="TextureMaterial">
      <instance_effect url="#texture-effect"/>
    </material>
  </library_materials>
  <library_geometries><geometry id="texture-geometry"><mesh>
    <source id="positions">
      <float_array id="positions-array" count="9">0 0 0 1 0 0 0 1 0</float_array>
      <technique_common><accessor source="#positions-array" count="3" stride="3">
        <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
      </accessor></technique_common>
    </source>
    <source id="texcoords">
      <float_array id="texcoords-array" count="6">0 0 1 0 0 1</float_array>
      <technique_common><accessor source="#texcoords-array" count="3" stride="2">
        <param name="S" type="float"/><param name="T" type="float"/>
      </accessor></technique_common>
    </source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1" material="texture-symbol">
      <input semantic="VERTEX" source="#vertices" offset="0"/>
      <input semantic="TEXCOORD" source="#texcoords" offset="1" set="0"/>
      <p>0 0 1 1 2 2</p>
    </triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene"><node id="texture-node">
    <instance_geometry url="#texture-geometry"><bind_material><technique_common>
      <instance_material symbol="texture-symbol" target="#texture-material">
        <bind_vertex_input semantic="TEX0" input_semantic="TEXCOORD" input_set="0"/>
      </instance_material>
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


def assert_float_close(label: str, actual: float, expected: float) -> None:
    if not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1.0e-6):
        raise AssertionError(f"{label}: expected {expected:.9f}, got {float(actual):.9f}")


def load_native_scene(path: Path):
    scene = native_load_meshes(
        path,
        make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="RAW",
            texture_loading="DEFERRED",
        ),
    )
    if scene is None or not scene.meshes:
        raise AssertionError(f"native DAE load produced no meshes: {path}")
    return scene


def assert_native_classic_semantics(path: Path, texture_path: Path) -> None:
    scene = load_native_scene(path)
    meshes = {mesh.material_name: mesh for mesh in scene.meshes}

    for name, (exponent, expected_roughness, expected_specular) in EXPECTED_CLASSIC.items():
        mesh = meshes.get(name)
        if mesh is None:
            raise AssertionError(f"native classic check: missing material {name}")
        assert_float_close(f"{name} exponent {exponent:g} roughness", mesh.roughness, expected_roughness)
        assert_float_close(f"{name} classic specular strength", mesh.specular_strength, 1.0)
        assert_float_close(f"{name} classic specular color", max(mesh.specular_color), expected_specular)
        if not _materials._has_specular(mesh):
            raise AssertionError(f"{name}: classic specular color was not recognized")

    texture_mesh = meshes.get("SpecularTextureMaterial")
    if texture_mesh is None:
        raise AssertionError("native classic check: missing SpecularTextureMaterial")
    assert_float_close(
        "classic specular texture roughness",
        texture_mesh.roughness,
        math.sqrt(2.0 / 66.0),
    )
    assert_float_close(
        "classic specular texture strength",
        texture_mesh.specular_strength,
        1.0,
    )
    actual_texture = Path(texture_mesh.specular_color_texture).resolve()
    if actual_texture != texture_path.resolve():
        raise AssertionError(
            f"classic specular texture: expected {texture_path}, got {actual_texture}"
        )
    if not _materials._has_specular(texture_mesh):
        raise AssertionError("classic specular texture was not recognized")


def principled_input(material_name: str, socket_name: str):
    material = bpy.data.materials.get(material_name)
    tree = material.node_tree if material is not None else None
    bsdf = tree.nodes.get("Principled BSDF") if tree is not None else None
    socket = bsdf.inputs.get(socket_name) if bsdf is not None else None
    if socket is None:
        raise AssertionError(f"{material_name}: missing Principled {socket_name} input")
    return socket


def assert_blender_classic_semantics(texture_path: Path) -> None:
    for name, (exponent, expected_roughness, expected_specular) in EXPECTED_CLASSIC.items():
        roughness = principled_input(name, "Roughness")
        specular = principled_input(name, "Specular IOR Level")
        assert_float_close(f"{name} exponent {exponent:g} Blender roughness", roughness.default_value, expected_roughness)
        assert_float_close(f"{name} Blender classic specular level", specular.default_value, expected_specular)

    tint = principled_input("SpecularTextureMaterial", "Specular Tint")
    if not tint.is_linked:
        raise AssertionError("classic specular texture did not reach Principled Specular Tint")
    nodes = {link.from_node for link in tint.links}
    pending = list(nodes)
    while pending:
        node = pending.pop()
        for socket in node.inputs:
            for link in socket.links:
                if link.from_node not in nodes:
                    nodes.add(link.from_node)
                    pending.append(link.from_node)
    image_nodes = [node for node in nodes if node.type == "TEX_IMAGE" and node.image]
    if len(image_nodes) != 1:
        raise AssertionError(
            f"classic specular texture expected one upstream image, got {len(image_nodes)}"
        )
    actual_texture = Path(bpy.path.abspath(image_nodes[0].image.filepath)).resolve()
    if actual_texture != texture_path.resolve():
        raise AssertionError(
            f"classic specular texture node: expected {texture_path}, got {actual_texture}"
        )


def finish_deferred_materials() -> None:
    while _materials.has_deferred_work():
        _materials._deferred_material_node_timer()
    while _textures.has_deferred_work():
        _textures._deferred_texture_timer()


def assert_deferred_texture_state_clean() -> None:
    if _textures._DEFERRED_TEXTURE_KEYS:
        raise AssertionError("deferred texture keys were not drained")
    if _textures._DEFERRED_TEXTURE_WAITERS:
        raise AssertionError("deferred texture waiters were not released")
    if _textures._DEFERRED_TEXTURE_TIMER_ACTIVE:
        raise AssertionError("deferred texture timer remained active")


def new_principled_material(name: str):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = tree.nodes.get("Principled BSDF") if tree else None
    if tree is None or bsdf is None:
        raise AssertionError(f"failed to create Principled material {name}")
    return material, tree, bsdf


def image_pixels(image) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in image.pixels[:4])


def assert_color_close(label: str, actual, expected) -> None:
    if any(
        abs(float(value) - wanted) > 1.0e-6
        for value, wanted in zip(actual, expected)
    ):
        raise AssertionError(f"{label}: expected {expected}, got {tuple(actual)}")


def assert_deferred_texture_topology_fallbacks(root: Path) -> None:
    reset_scene()
    previous_mode = _textures.ACTIVE_LOAD_MODE
    _textures.ACTIVE_LOAD_MODE = "DEFERRED"
    try:
        missing_path = root / "early-missing.png"
        early_material, early_tree, early_bsdf = new_principled_material("EarlyMissing")
        expected_base = (0.2, 0.4, 0.6, 1.0)
        early_base = early_bsdf.inputs["Base Color"]
        early_base.default_value = expected_base
        early_tex = _textures._image_texture_node(
            early_material,
            str(missing_path),
            "sRGB",
            TextureRefData(role="base_color", path=str(missing_path)),
        )
        if early_tex is not None:
            output = _shader._multiply_color_factor(
                early_material,
                early_tex.outputs.get("Color"),
                expected_base,
                "Base Color Factor",
            )
            early_tree.links.new(output, early_base)
        if early_base.is_linked:
            raise AssertionError("early missing texture built a Base Color helper branch")
        if any(node.type == "TEX_IMAGE" for node in early_tree.nodes):
            raise AssertionError("early missing texture built an image node")
        assert_color_close("early missing authored Base Color", early_base.default_value, expected_base)
        assert_deferred_texture_state_clean()

        corrupt_path = root / "late-failure.ktx2"
        corrupt_path.write_bytes(b"not a valid KTX2 payload")

        base_materials = []
        for index, factor in enumerate(
            ((0.2, 0.4, 0.6, 1.0), (0.8, 0.3, 0.1, 1.0))
        ):
            material, tree, bsdf = new_principled_material(f"LateBase{index}")
            base = bsdf.inputs["Base Color"]
            base.default_value = factor
            tex = _textures._image_texture_node(
                material,
                str(corrupt_path),
                "sRGB",
                TextureRefData(role="base_color", path=str(corrupt_path)),
            )
            if tex is None:
                raise AssertionError("existing late-failure texture was not deferred")
            output = _shader._multiply_color_factor(
                material,
                tex.outputs.get("Color"),
                factor,
                "Base Color Factor",
            )
            tree.links.new(output, base)
            base_materials.append((material, tex, base, factor))

        dead_material, _dead_tree, _dead_bsdf = new_principled_material("DeletedWaiter")
        dead_tex = _textures._image_texture_node(
            dead_material,
            str(corrupt_path),
            "sRGB",
            TextureRefData(role="base_color", path=str(corrupt_path)),
        )
        if dead_tex is None:
            raise AssertionError("deleted waiter was not queued")
        bpy.data.materials.remove(dead_material)

        packed_material, _packed_tree, packed_bsdf = new_principled_material("LatePacked")
        packed_roughness = 0.35
        packed_metallic = 0.65
        packed_bsdf.inputs["Roughness"].default_value = packed_roughness
        packed_bsdf.inputs["Metallic"].default_value = packed_metallic
        _shader._link_metallic_roughness_texture(
            packed_material,
            packed_bsdf,
            str(corrupt_path),
            TextureRefData(role="metallic_roughness", path=str(corrupt_path)),
            metallic_factor=packed_metallic,
            roughness_factor=packed_roughness,
        )
        packed_tex = next(
            (node for node in packed_material.node_tree.nodes if node.type == "TEX_IMAGE"),
            None,
        )
        if packed_tex is None:
            raise AssertionError("packed texture topology was not built")

        normal_material, _normal_tree, normal_bsdf = new_principled_material("LateNormal")
        _shader._link_normal_texture(
            normal_material,
            normal_bsdf,
            str(corrupt_path),
            0.75,
            TextureRefData(role="normal", path=str(corrupt_path)),
        )
        normal_tex = next(
            (node for node in normal_material.node_tree.nodes if node.type == "TEX_IMAGE"),
            None,
        )
        if normal_tex is None:
            raise AssertionError("normal texture topology was not built")

        waiter_sizes = sorted(
            len(waiters) for waiters in _textures._DEFERRED_TEXTURE_WAITERS.values()
        )
        if waiter_sizes != [2, 3]:
            raise AssertionError(
                f"deferred waiter coalescing expected [2, 3], got {waiter_sizes}"
            )
        finish_deferred_materials()
        assert_deferred_texture_state_clean()

        first_fallback = base_materials[0][1].image
        second_fallback = base_materials[1][1].image
        if first_fallback is None or first_fallback != second_fallback:
            raise AssertionError("same-key color waiters did not share a fallback image")
        if first_fallback.get("assetkit_missing_texture_fallback") != "COLOR":
            raise AssertionError("late color failure did not receive the color fallback")
        assert_color_close(
            "late color neutral image",
            image_pixels(first_fallback),
            (1.0, 1.0, 1.0, 1.0),
        )
        for _material, _tex, base, factor in base_materials:
            if not base.is_linked:
                raise AssertionError("late color fallback lost its Base Color topology")
            factor_inputs = _shader._color_multiply_inputs(base.links[0].from_node)
            if factor_inputs is None:
                raise AssertionError("late color fallback lost its factor helper")
            assert_color_close(
                "late Base Color factor",
                factor_inputs[1].default_value,
                factor,
            )
            assert_color_close("late authored Base Color", base.default_value, factor)

        if packed_tex.image is None:
            raise AssertionError("packed late failure did not receive a fallback image")
        if packed_tex.image.get("assetkit_missing_texture_fallback") != "COLOR":
            raise AssertionError("packed late failure did not receive the color fallback")
        assert_color_close(
            "packed neutral image",
            image_pixels(packed_tex.image),
            (1.0, 1.0, 1.0, 1.0),
        )
        roughness = packed_bsdf.inputs["Roughness"]
        metallic = packed_bsdf.inputs["Metallic"]
        if not roughness.is_linked or not metallic.is_linked:
            raise AssertionError("packed fallback lost metallic/roughness topology")
        if abs(float(roughness.links[0].from_node.inputs[1].default_value) - packed_roughness) > 1.0e-6:
            raise AssertionError("packed fallback changed the authored roughness factor")
        if abs(float(metallic.links[0].from_node.inputs[1].default_value) - packed_metallic) > 1.0e-6:
            raise AssertionError("packed fallback changed the authored metallic factor")

        if normal_tex.image is None:
            raise AssertionError("normal late failure did not receive a fallback image")
        if normal_tex.image.get("assetkit_missing_texture_fallback") != "NORMAL":
            raise AssertionError("normal late failure did not receive the normal fallback")
        assert_color_close(
            "normal neutral image",
            image_pixels(normal_tex.image),
            (0.5, 0.5, 1.0, 1.0),
        )
        if not normal_bsdf.inputs["Normal"].is_linked:
            raise AssertionError("normal fallback lost its normal-map topology")
    finally:
        _textures.ACTIVE_LOAD_MODE = previous_mode


def assert_texture_fallback(path: Path, *, expect_image: bool) -> None:
    reset_scene()
    import_dae(path)
    finish_deferred_materials()

    material = bpy.data.materials.get("TextureMaterial")
    if material is None or material.node_tree is None:
        raise AssertionError("missing deferred texture material")
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    base_color = bsdf.inputs.get("Base Color") if bsdf else None
    texture_nodes = [
        node for node in material.node_tree.nodes if node.type == "TEX_IMAGE"
    ]

    if expect_image:
        if not base_color or not base_color.is_linked:
            raise AssertionError("valid deferred texture is not linked to Base Color")
        if len(texture_nodes) != 1 or texture_nodes[0].image is None:
            raise AssertionError("valid deferred texture image was not loaded")
        if texture_nodes[0].interpolation != "Closest":
            raise AssertionError(
                "COLLADA sampler NONE expected Closest interpolation, got "
                f"{texture_nodes[0].interpolation}"
            )
        return

    if base_color is None or base_color.is_linked:
        raise AssertionError("missing deferred texture left Base Color linked to black")
    if texture_nodes:
        raise AssertionError("missing deferred texture left an empty image node")
    expected = (1.0, 1.0, 1.0, 1.0)
    if any(
        abs(float(actual) - wanted) > 1.0e-6
        for actual, wanted in zip(base_color.default_value, expected)
    ):
        raise AssertionError(
            f"missing deferred texture fallback expected {expected}, got {tuple(base_color.default_value)}"
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
        missing_texture = root / "missing-texture.dae"
        present_texture = root / "present-texture.dae"
        texture_path = root / "texture.png"
        source.write_text(DAE.format(texture=texture_path.name), encoding="utf-8")
        missing_texture.write_text(
            TEXTURE_DAE.format(texture="missing.png"),
            encoding="utf-8",
        )

        image = bpy.data.images.new("TextureFixture", width=1, height=1, alpha=True)
        image.pixels = (0.25, 0.5, 0.75, 1.0)
        image.filepath_raw = str(texture_path)
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)
        present_texture.write_text(
            TEXTURE_DAE.format(texture=texture_path.name),
            encoding="utf-8",
        )

        assert_native_classic_semantics(source, texture_path)

        reset_scene()
        import_dae(source)
        finish_deferred_materials()
        assert_blender_types("source import")
        assert_blender_classic_semantics(texture_path)
        assert_deferred_texture_state_clean()

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

        assert_texture_fallback(missing_texture, expect_image=False)
        assert_texture_fallback(present_texture, expect_image=True)
        assert_deferred_texture_topology_fallbacks(root)

    print("DAE classic material and missing texture fallback checks passed")


if __name__ == "__main__":
    main()
