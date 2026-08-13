#!/usr/bin/env python3
"""Check COLLADA light attenuation survives Blender import and export.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_dae_light_check.py
"""

from __future__ import annotations

import json
import math
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


DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
  <library_lights>
    <light id="constant-light" name="ConstantLight"><technique_common><spot>
      <color>1 0 0</color><constant_attenuation>1</constant_attenuation>
      <linear_attenuation>0</linear_attenuation><quadratic_attenuation>0</quadratic_attenuation>
      <falloff_angle>40</falloff_angle><falloff_exponent>3</falloff_exponent>
    </spot></technique_common></light>
    <light id="linear-light" name="LinearLight"><technique_common><point>
      <color>0 1 0</color><constant_attenuation>0.25</constant_attenuation>
      <linear_attenuation>0.5</linear_attenuation><quadratic_attenuation>0</quadratic_attenuation>
    </point></technique_common></light>
    <light id="quadratic-light" name="QuadraticLight"><technique_common><point>
      <color>0 0 1</color><constant_attenuation>0.125</constant_attenuation>
      <linear_attenuation>0.25</linear_attenuation><quadratic_attenuation>0.75</quadratic_attenuation>
    </point></technique_common></light>
  </library_lights>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="constant-node" name="ConstantNode"><translate>0 0 2</translate><scale>25 25 25</scale><instance_light url="#constant-light"/></node>
    <node id="linear-node" name="LinearNode"><translate>2 0 2</translate><instance_light url="#linear-light"/></node>
    <node id="quadratic-node" name="QuadraticNode"><translate>-2 0 2</translate><instance_light url="#quadratic-light"/></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""

EXPECTED = {
    (1.0, 0.0, 0.0): (0.0, (1.0, 0.0, 0.0)),
    (0.0, 1.0, 0.0): (1.0, (0.25, 0.5, 0.0)),
    (0.0, 0.0, 1.0): (2.0, (0.125, 0.25, 0.75)),
}

GLTF = {
    "asset": {"version": "2.0"},
    "extensionsUsed": ["KHR_lights_punctual"],
    "extensions": {
        "KHR_lights_punctual": {
            "lights": [{"name": "GLTFPoint", "type": "point", "intensity": 10.0}]
        }
    },
    "scene": 0,
    "scenes": [{"nodes": [0]}],
    "nodes": [{"extensions": {"KHR_lights_punctual": {"light": 0}}}],
}


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)


def import_dae(path: Path) -> None:
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="DEFERRED",
    )
    import_assetkit_file(
        str(path),
        load_options=options,
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


def assert_close(actual: float, expected: float, message: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=1.0e-6, abs_tol=1.0e-6):
        raise AssertionError(f"{message}: expected {expected}, got {actual}")


def assert_lights() -> None:
    lights = {
        tuple(round(float(value), 6) for value in light.color): light
        for light in bpy.data.lights
    }
    if set(lights) != set(EXPECTED):
        raise AssertionError(f"unexpected light colors: {sorted(lights)}")

    for color, (exponent, attenuation) in EXPECTED.items():
        light = lights[color]
        assert_close(light.energy, 1000.0, f"{color} preview energy")
        assert_close(
            light["assetkit_light_attenuation_falloff_exponent"],
            exponent,
            f"{color} falloff exponent",
        )
        for suffix, expected in zip(("constant", "linear", "quadratic"), attenuation):
            assert_close(
                light[f"assetkit_light_attenuation_{suffix}"],
                expected,
                f"{color} attenuation {suffix}",
            )
        assert_close(light["assetkit_light_source_intensity"], 1.0, f"{color} source intensity")

    constant = lights[(1.0, 0.0, 0.0)]
    assert_close(math.degrees(constant.spot_size), 80.0, "COLLADA half-angle to Blender full cone")
    assert_close(constant.spot_blend, 1.0, "zero inner cone maps to a fully soft Blender spot")
    assert_close(constant["assetkit_light_cone_falloff_exponent"], 3.0, "spot cone exponent")
    falloff = constant.node_tree.nodes.get("AssetKit Light Falloff") if constant.node_tree else None
    emission = next((node for node in constant.node_tree.nodes if node.type == "EMISSION"), None)
    if falloff is None or emission is None or not emission.inputs["Strength"].is_linked:
        raise AssertionError("constant spot has no authored Cycles falloff")
    link = emission.inputs["Strength"].links[0]
    if link.from_node != falloff or link.from_socket.name != "Constant":
        raise AssertionError(f"constant spot expected Constant falloff, got {link.from_socket.name}")
    assert_close(falloff.inputs["Strength"].default_value, 1.0, "constant falloff strength")

    for color, coefficients in (
        ((0.0, 1.0, 0.0), (0.25, 0.5, 0.0)),
        ((0.0, 0.0, 1.0), (0.125, 0.25, 0.75)),
    ):
        light = lights[color]
        tree = light.node_tree
        if tree is None:
            raise AssertionError(f"{color} has no authored mixed attenuation graph")
        reciprocal = tree.nodes.get("AssetKit Attenuation Reciprocal")
        emission = next((node for node in tree.nodes if node.type == "EMISSION"), None)
        if reciprocal is None or emission is None or not emission.inputs["Strength"].is_linked:
            raise AssertionError(f"{color} mixed attenuation is not linked")
        if emission.inputs["Strength"].links[0].from_node != reciprocal:
            raise AssertionError(f"{color} emission is not driven by attenuation reciprocal")
        constant_value, linear_value, quadratic_value = coefficients
        constant_node = tree.nodes.get("AssetKit Attenuation Constant")
        assert_close(constant_node.outputs[0].default_value, constant_value, f"{color} graph constant")
        for name, expected in (("Linear", linear_value), ("Quadratic", quadratic_value)):
            term = tree.nodes.get(f"AssetKit Attenuation {name} Term")
            if expected > 0.0:
                if term is None:
                    raise AssertionError(f"{color} graph has no {name} term")
                assert_close(term.inputs[0].default_value, expected, f"{color} graph {name}")
            elif term is not None:
                raise AssertionError(f"{color} graph has unexpected {name} term")


def assert_exported(path: Path) -> None:
    root = ET.parse(path).getroot()
    namespace = root.tag.partition("}")[0].lstrip("{")
    ns = {"c": namespace}
    by_color = {}
    for light in root.findall("c:library_lights/c:light", ns):
        common = light.find("c:technique_common", ns)
        profile = next(iter(common), None) if common is not None else None
        if profile is None:
            continue
        color = tuple(float(value) for value in (profile.findtext("c:color", namespaces=ns) or "").split())
        by_color[color] = profile
    if set(by_color) != set(EXPECTED):
        raise AssertionError(f"exported light colors changed: {sorted(by_color)}")

    for color, (_exponent, attenuation) in EXPECTED.items():
        profile = by_color[color]
        actual = tuple(
            float(profile.findtext(f"c:{tag}", namespaces=ns) or "nan")
            for tag in ("constant_attenuation", "linear_attenuation", "quadratic_attenuation")
        )
        for got, wanted in zip(actual, attenuation):
            assert_close(got, wanted, f"exported attenuation for {color}")
    spot = by_color[(1.0, 0.0, 0.0)]
    assert_close(float(spot.findtext("c:falloff_angle", namespaces=ns) or "nan"), 40.0, "spot angle")
    assert_close(float(spot.findtext("c:falloff_exponent", namespaces=ns) or "nan"), 3.0, "spot exponent")


def assert_gltf_light() -> None:
    if len(bpy.data.lights) != 1:
        raise AssertionError(f"expected one glTF light, got {len(bpy.data.lights)}")
    light = bpy.data.lights[0]
    if light.type != "POINT":
        raise AssertionError(f"expected glTF point light, got {light.type}")
    assert_close(light.energy, 10.0, "glTF point intensity")
    assert_close(light["assetkit_light_source_intensity"], 10.0, "glTF source intensity")
    assert_close(
        light["assetkit_light_attenuation_falloff_exponent"],
        2.0,
        "glTF inverse-square falloff exponent",
    )
    for suffix, expected in (("constant", 0.0), ("linear", 0.0), ("quadratic", 1.0)):
        assert_close(
            light[f"assetkit_light_attenuation_{suffix}"],
            expected,
            f"glTF attenuation {suffix}",
        )
    falloff = light.node_tree.nodes.get("AssetKit Light Falloff") if light.node_tree else None
    if falloff is not None:
        raise AssertionError("glTF point light should use Blender's native inverse-square falloff")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-light-") as temp_dir:
        source = Path(temp_dir) / "lights.dae"
        exported = Path(temp_dir) / "lights-roundtrip.dae"
        source.write_text(DAE, encoding="utf-8")
        reset_scene()
        import_dae(source)
        assert_lights()
        result = export_scene(bpy.context, exported, AK_FILE_TYPE_DAE)
        if result < 0 or not exported.is_file():
            raise AssertionError(f"DAE light export failed: {result}")
        assert_exported(exported)

        reset_scene()
        import_dae(exported)
        assert_lights()

        gltf = Path(temp_dir) / "point-light.gltf"
        gltf.write_text(json.dumps(GLTF, separators=(",", ":")), encoding="utf-8")
        reset_scene()
        import_dae(gltf)
        assert_gltf_light()

    print("DAE light attenuation check passed")


if __name__ == "__main__":
    main()
