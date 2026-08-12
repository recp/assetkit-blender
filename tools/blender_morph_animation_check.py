#!/usr/bin/env python3
"""Check morph slot stability and COLLADA controller animation fan-out.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_morph_animation_check.py
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.imp.buffers import (  # noqa: E402
    buffer_view,
    channel_clip_index,
    channel_clip_name,
    channel_count,
    channel_times,
    channel_target_offset,
    channel_value_width,
    channel_values,
)
from assetkit_blender.imp.animation.actions import _iter_action_fcurves  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


DAE_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>
  <library_geometries>
    <geometry id="base"><mesh>
      <source id="base-positions"><float_array id="base-positions-array" count="9">0 0 0  1 0 0  0 1 0</float_array><technique_common><accessor source="#base-positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
      <vertices id="base-vertices"><input semantic="POSITION" source="#base-positions"/></vertices>
      <triangles count="1"><input semantic="VERTEX" source="#base-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
    <geometry id="raised"><mesh>
      <source id="raised-positions"><float_array id="raised-positions-array" count="9">0 0 1  1 0 1  0 1 1</float_array><technique_common><accessor source="#raised-positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
      <vertices id="raised-vertices"><input semantic="POSITION" source="#raised-positions"/></vertices>
      <triangles count="1"><input semantic="VERTEX" source="#raised-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
    <geometry id="raised2"><mesh>
      <source id="raised2-positions"><float_array id="raised2-positions-array" count="9">0 0 2  1 0 2  0 1 2</float_array><technique_common><accessor source="#raised2-positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
      <vertices id="raised2-vertices"><input semantic="POSITION" source="#raised2-positions"/></vertices>
      <triangles count="1"><input semantic="VERTEX" source="#raised2-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
  </library_geometries>
  <library_controllers><controller id="morph"><morph method="NORMALIZED" source="#base">
    <source id="morph-targets"><IDREF_array id="morph-targets-array" count="2">raised raised2</IDREF_array><technique_common><accessor source="#morph-targets-array" count="2"><param name="MORPH_TARGET" type="IDREF"/></accessor></technique_common></source>
    <source id="morph-weights"><float_array id="morph-weights-array" count="2">0 0</float_array><technique_common><accessor source="#morph-weights-array" count="2"><param name="MORPH_WEIGHT" type="float"/></accessor></technique_common></source>
    <targets><input semantic="MORPH_TARGET" source="#morph-targets"/><input semantic="MORPH_WEIGHT" source="#morph-weights"/></targets>
  </morph></controller></library_controllers>
  <library_animations>
    <animation id="weight-animation">
      <source id="weight-input"><float_array id="weight-input-array" count="3">0 .5 1</float_array><technique_common><accessor source="#weight-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="weight-output"><float_array id="weight-output-array" count="3">0 10 20</float_array><technique_common><accessor source="#weight-output-array" count="3" stride="1"><param name="VALUE" type="float"/></accessor></technique_common></source>
      <source id="weight-interpolation"><Name_array id="weight-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array><technique_common><accessor source="#weight-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <sampler id="weight-sampler"><input semantic="INPUT" source="#weight-input"/><input semantic="OUTPUT" source="#weight-output"/><input semantic="INTERPOLATION" source="#weight-interpolation"/></sampler>
      <channel source="#weight-sampler" target="morph-weights(0)"/>
    </animation>
    <animation id="weight2-animation">
      <source id="weight2-input"><float_array id="weight2-input-array" count="3">0 .5 1</float_array><technique_common><accessor source="#weight2-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="weight2-output"><float_array id="weight2-output-array" count="3">0 20 40</float_array><technique_common><accessor source="#weight2-output-array" count="3" stride="1"><param name="VALUE" type="float"/></accessor></technique_common></source>
      <source id="weight2-interpolation"><Name_array id="weight2-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array><technique_common><accessor source="#weight2-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <sampler id="weight2-sampler"><input semantic="INPUT" source="#weight2-input"/><input semantic="OUTPUT" source="#weight2-output"/><input semantic="INTERPOLATION" source="#weight2-interpolation"/></sampler>
      <channel source="#weight2-sampler" target="morph-weights(1)"/>
    </animation>
    <animation id="property-animation">
      <source id="property-input"><float_array id="property-input-array" count="3">0 .5 1</float_array><technique_common><accessor source="#property-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="property-output"><float_array id="property-output-array" count="3">0 10 20</float_array><technique_common><accessor source="#property-output-array" count="3" stride="1"><param name="X" type="float"/></accessor></technique_common></source>
      <source id="property-interpolation"><Name_array id="property-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array><technique_common><accessor source="#property-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <sampler id="property-sampler"><input semantic="INPUT" source="#property-input"/><input semantic="OUTPUT" source="#property-output"/><input semantic="INTERPOLATION" source="#property-interpolation"/></sampler>
      <channel source="#property-sampler" target="property/translation.X"/>
    </animation>
    <animation id="mixed-animation">
      <source id="mixed-input"><float_array id="mixed-input-array" count="3">0 .5 1</float_array><technique_common><accessor source="#mixed-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="mixed-output"><float_array id="mixed-output-array" count="3">0 10 20</float_array><technique_common><accessor source="#mixed-output-array" count="3" stride="1"><param name="X" type="float"/></accessor></technique_common></source>
      <source id="mixed-interpolation"><Name_array id="mixed-interpolation-array" count="3">STEP LINEAR LINEAR</Name_array><technique_common><accessor source="#mixed-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <sampler id="mixed-sampler"><input semantic="INPUT" source="#mixed-input"/><input semantic="OUTPUT" source="#mixed-output"/><input semantic="INTERPOLATION" source="#mixed-interpolation"/></sampler>
      <channel source="#mixed-sampler" target="mixed/translation.X"/>
    </animation>
    <animation id="curve-animation">
      <source id="curve-input"><float_array id="curve-input-array" count="2">0 1</float_array><technique_common><accessor source="#curve-input-array" count="2" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="curve-output"><float_array id="curve-output-array" count="2">0 1</float_array><technique_common><accessor source="#curve-output-array" count="2" stride="1"><param name="X" type="float"/></accessor></technique_common></source>
      <source id="curve-interpolation"><Name_array id="curve-interpolation-array" count="2">BEZIER BEZIER</Name_array><technique_common><accessor source="#curve-interpolation-array" count="2" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <source id="curve-in-tangent"><float_array id="curve-in-tangent-array" count="4">0 0  .666666667 1</float_array><technique_common><accessor source="#curve-in-tangent-array" count="2" stride="2"><param name="TIME" type="float"/><param name="VALUE" type="float"/></accessor></technique_common></source>
      <source id="curve-out-tangent"><float_array id="curve-out-tangent-array" count="4">.333333333 1  1 1</float_array><technique_common><accessor source="#curve-out-tangent-array" count="2" stride="2"><param name="TIME" type="float"/><param name="VALUE" type="float"/></accessor></technique_common></source>
      <sampler id="curve-sampler"><input semantic="INPUT" source="#curve-input"/><input semantic="OUTPUT" source="#curve-output"/><input semantic="INTERPOLATION" source="#curve-interpolation"/><input semantic="IN_TANGENT" source="#curve-in-tangent"/><input semantic="OUT_TANGENT" source="#curve-out-tangent"/></sampler>
      <channel source="#curve-sampler" target="curve/translation.X"/>
    </animation>
    <animation id="move-animation">
      <source id="move-input"><float_array id="move-input-array" count="2">0 1</float_array><technique_common><accessor source="#move-input-array" count="2" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
      <source id="move-output"><float_array id="move-output-array" count="2">0 3</float_array><technique_common><accessor source="#move-output-array" count="2" stride="1"><param name="X" type="float"/></accessor></technique_common></source>
      <source id="move-interpolation"><Name_array id="move-interpolation-array" count="2">LINEAR LINEAR</Name_array><technique_common><accessor source="#move-interpolation-array" count="2" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
      <sampler id="move-sampler"><input semantic="INPUT" source="#move-input"/><input semantic="OUTPUT" source="#move-output"/><input semantic="INTERPOLATION" source="#move-interpolation"/></sampler>
      <channel source="#move-sampler" target="mover/translation.X"/>
    </animation>
  </library_animations>
  <library_animation_clips><animation_clip id="WeightClip" name="WeightClip" start=".25" end=".75"><instance_animation url="#weight-animation"/><instance_animation url="#weight2-animation"/><instance_animation url="#property-animation"/><instance_animation url="#mixed-animation"/><instance_animation url="#curve-animation"/></animation_clip></library_animation_clips>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="instanceA" name="instanceA"><instance_controller url="#morph"/></node>
    <node id="instanceB" name="instanceB"><translate>2 0 0</translate><instance_controller url="#morph"/></node>
    <node id="property" name="property"><translate sid="translation">0 0 0</translate></node>
    <node id="mixed" name="mixed"><translate sid="translation">0 0 0</translate></node>
    <node id="curve" name="curve"><translate sid="translation">0 0 0</translate></node>
    <node id="mover" name="mover"><translate sid="translation">0 0 0</translate></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def _options():
    return make_load_options(
        coordinate_system="Y_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="DEFERRED",
    )


def _import(path: Path, options: object) -> list[bpy.types.Object]:
    return import_assetkit_file(
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


def _assert_channel_sample(
    channel: object,
    time: float,
    expected: float,
    label: str,
    component: int = 0,
) -> None:
    count = channel_count(channel)
    width = channel_value_width(channel)
    times = buffer_view(channel_times(channel), "f")
    values = buffer_view(channel_values(channel), "f")
    if times is None or values is None or count <= 0:
        raise AssertionError(f"{label}: missing native channel samples")
    if abs(float(times[0])) > 1.0e-6 or abs(float(times[count - 1]) - 0.5) > 1.0e-6:
        raise AssertionError(f"{label}: explicit clip was not normalized to [0, .5]")
    best = min(range(count), key=lambda index: abs(float(times[index]) - time))
    if abs(float(times[best]) - time) > 1.0e-5:
        raise AssertionError(f"{label}: no exact sample at clip-local time {time}")
    if component < 0 or component >= width:
        raise AssertionError(f"{label}: component {component} outside width {width}")
    actual = float(values[best * width + component])
    if abs(actual - expected) > 4.0e-4:
        raise AssertionError(f"{label}: value {actual} at {time}, expected {expected}")


def _action_curve(action: bpy.types.Action | None, data_path: str, array_index: int = 0):
    if action is None:
        return None
    for curve in _iter_action_fcurves(action):
        if curve.data_path == data_path and int(curve.array_index) == array_index:
            return curve
    return None


def _assert_mixed_step_channel(channel: object) -> None:
    count = channel_count(channel)
    times = buffer_view(channel_times(channel), "f")
    values = buffer_view(channel_values(channel), "f")
    if times is None or values is None or count < 3:
        raise AssertionError("mixed STEP channel is missing dense samples")
    exact = min(range(count), key=lambda index: abs(float(times[index]) - 0.25))
    before = max((index for index in range(count) if float(times[index]) < 0.25), default=-1)
    if before < 0 or abs(float(values[before])) > 4.0e-4:
        raise AssertionError("mixed STEP channel lost the left-limit value")
    if abs(float(times[exact]) - 0.25) > 1.0e-6 or abs(float(values[exact]) - 10.0) > 4.0e-4:
        raise AssertionError("mixed STEP channel lost the exact-key right value")
    _assert_channel_sample(channel, 0.5, 15.0, "mixed STEP endpoint")


def _assert_dae_fanout(path: Path, options: object) -> None:
    path.write_text(DAE_FIXTURE, encoding="utf-8")
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None:
        raise AssertionError("failed to load COLLADA morph fixture")
    primitives = [primitive for primitive in loaded.meshes if primitive.morph_targets]
    if len(primitives) != 2:
        raise AssertionError(f"expected two morph instances, got {len(primitives)}")
    for primitive in primitives:
        channels = list(primitive.morph_anim_channels or [])
        if len(channels) != 2:
            raise AssertionError("morph animation did not fan out to every instance")
        if any(
            channel_clip_index(channel) != 0
            or channel_clip_name(channel) != "WeightClip"
            for channel in channels
        ):
            raise AssertionError("explicit morph clip membership was lost")
        by_offset = {channel_target_offset(channel): channel for channel in channels}
        if set(by_offset) != {0, 1}:
            raise AssertionError("explicit morph channels did not preserve both target slots")
        for time, value in ((0.0, 5.0), (0.25, 10.0), (0.5, 15.0)):
            _assert_channel_sample(by_offset[0], time, value, "morph")
        for time, value in ((0.0, 10.0), (0.25, 20.0), (0.5, 30.0)):
            _assert_channel_sample(by_offset[1], time, value, "morph slot 2")

    property_node = next((node for node in loaded.nodes if node.name == "property"), None)
    property_channels = list(property_node.anim_channels or []) if property_node else []
    if len(property_channels) != 1 or channel_clip_index(property_channels[0]) != 0:
        raise AssertionError("explicit property clip membership was lost")
    for time, value in ((0.0, 5.0), (0.25, 10.0), (0.5, 15.0)):
        _assert_channel_sample(property_channels[0], time, value, "property")

    mixed_node = next((node for node in loaded.nodes if node.name == "mixed"), None)
    mixed_channels = list(mixed_node.anim_channels or []) if mixed_node else []
    if len(mixed_channels) != 1 or channel_clip_index(mixed_channels[0]) != 0:
        raise AssertionError("explicit mixed STEP clip membership was lost")
    _assert_mixed_step_channel(mixed_channels[0])

    curve_node = next((node for node in loaded.nodes if node.name == "curve"), None)
    curve_channels = list(curve_node.anim_channels or []) if curve_node else []
    if len(curve_channels) != 1 or channel_clip_index(curve_channels[0]) != 0:
        raise AssertionError("explicit Bezier clip membership was lost")
    _assert_channel_sample(curve_channels[0], 0.0, 0.578125, "Bezier boundary")

    mover = next((node for node in loaded.nodes if node.name == "mover"), None)
    mover_channels = list(mover.anim_channels or []) if mover else []
    if len(mover_channels) != 1 or channel_clip_index(mover_channels[0]) != 1:
        raise AssertionError("unreferenced animation was not kept in a separate implicit clip")

    objects = _import(path, options)
    meshes = [obj for obj in objects if obj.type == "MESH" and obj.data.shape_keys]
    if len(meshes) != 2:
        raise AssertionError(f"expected two Blender morph meshes, got {len(meshes)}")
    for obj in meshes:
        keys = obj.data.shape_keys
        action = keys.animation_data.action if keys.animation_data else None
        if action is None or action.get("assetkit_animation_clip_name") != "WeightClip":
            raise AssertionError(f"{obj.name}: explicit morph action was not attached")
        curves = list(_iter_action_fcurves(action))
        if len(curves) != 2:
            raise AssertionError(f"{obj.name}: expected two morph FCurves, got {len(curves)}")
        curves.sort(key=lambda curve: curve.data_path)
        expected_samples = (
            ((0.0, 5.0), (6.0, 10.0), (12.0, 15.0)),
            ((0.0, 10.0), (6.0, 20.0), (12.0, 30.0)),
        )
        for curve, samples in zip(curves, expected_samples):
            for frame, expected in samples:
                actual = float(curve.evaluate(frame))
                if abs(actual - expected) > 4.0e-4:
                    raise AssertionError(
                        f"{obj.name} frame {frame}: morph curve {actual}, expected {expected}"
                    )

    object_by_name = {obj.name: obj for obj in bpy.context.collection.all_objects}
    for name, samples in {
        "property": ((0.0, 5.0), (6.0, 10.0), (12.0, 15.0)),
        "mixed": ((0.0, 0.0), (5.99, 0.0), (6.0, 10.0), (12.0, 15.0)),
        "curve": ((0.0, 0.578125),),
    }.items():
        obj = object_by_name.get(name)
        action = obj.animation_data.action if obj and obj.animation_data else None
        if action is None or action.get("assetkit_animation_clip_name") != "WeightClip":
            raise AssertionError(f"{name}: explicit property action was not attached")
        fcurve = _action_curve(action, "location", 0)
        if fcurve is None:
            raise AssertionError(f"{name}: missing location.X FCurve")
        for frame, expected in samples:
            actual = float(fcurve.evaluate(frame))
            if abs(actual - expected) > 4.0e-4:
                raise AssertionError(
                    f"{name} frame {frame}: property curve {actual}, expected {expected}"
                )


def _gltf_slot_fixture(path: Path) -> None:
    parts = [
        (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        (0.0,) * 9,
        (0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0),
        (0.25, 0.75, 1.0, 0.0),
    ]
    blob = b""
    views = []
    for values in parts:
        raw = struct.pack("<" + "f" * len(values), *values)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)})
        blob += raw
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{
            "byteLength": len(blob),
            "uri": "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii"),
        }],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 3, "componentType": 5126, "count": 2, "type": "SCALAR"},
            {"bufferView": 4, "componentType": 5126, "count": 4, "type": "SCALAR"},
        ],
        "meshes": [{
            "name": "two_slots",
            "weights": [0.25, 0.75],
            "extras": {"targetNames": ["normalOnly", "positionOnly"]},
            "primitives": [{
                "attributes": {"POSITION": 0},
                "targets": [{"NORMAL": 1}, {"POSITION": 2}],
                "mode": 4,
            }],
        }],
        "nodes": [{"name": "morphNode", "mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "animations": [{
            "name": "weights",
            "samplers": [{"input": 3, "output": 4, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"node": 0, "path": "weights"}}],
        }],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def _assert_morph_slots(path: Path, options: object) -> None:
    _gltf_slot_fixture(path)
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 1:
        raise AssertionError("failed to load morph slot fixture")
    primitive = loaded.meshes[0]
    targets = list(primitive.morph_targets or [])
    if primitive.morph_target_count != 2 or [target.name for target in targets] != [
        "normalOnly",
        "positionOnly",
    ]:
        raise AssertionError("native morph target slots were compacted or renamed")

    obj = next(obj for obj in _import(path, options) if obj.type == "MESH")
    keys = obj.data.shape_keys.key_blocks
    if [key.name for key in keys] != ["Basis", "normalOnly", "positionOnly"]:
        raise AssertionError(f"Blender shape-key slots shifted: {[key.name for key in keys]}")
    expected = {
        0: ((0.25, 0.75), 0.75),
        24: ((1.0, 0.0), 0.0),
    }
    for frame, (weights, expected_z) in expected.items():
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        actual_weights = (float(keys[1].value), float(keys[2].value))
        if any(abs(a - b) > 1.0e-6 for a, b in zip(actual_weights, weights)):
            raise AssertionError(f"frame {frame}: shifted morph weights {actual_weights}")
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            if any(abs(float(vertex.co.z) - expected_z) > 1.0e-6 for vertex in mesh.vertices):
                raise AssertionError(f"frame {frame}: wrong evaluated morph slot")
        finally:
            evaluated.to_mesh_clear()


def main() -> None:
    options = _options()
    with tempfile.TemporaryDirectory(prefix="assetkit-morph-animation-") as temp_dir:
        temp = Path(temp_dir)
        _assert_dae_fanout(temp / "morph-fanout.dae", options)
        _assert_morph_slots(temp / "morph-slots.gltf", options)
    print("Morph animation check passed")


if __name__ == "__main__":
    main()
