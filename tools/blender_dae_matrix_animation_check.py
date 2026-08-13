#!/usr/bin/env python3
"""Check whole-matrix COLLADA channels survive native and Blender import.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_dae_matrix_animation_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.imp.animation.actions import _iter_action_fcurves  # noqa: E402
from assetkit_blender.imp.buffers import (  # noqa: E402
    channel_count,
    channel_target,
    channel_value_width,
)
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


_ANIM_TRANSLATION = 1
_ANIM_ROTATION_QUAT = 2
_ANIM_SCALE = 3
_IDENTITY = "1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"

_MATRIX_SAMPLES = f"""
  {_IDENTITY}
  0 -1 0 2  1 0 0 0  0 0 1 0  0 0 0 1
  1 0 0 4  0 1 0 0  0 0 1 0  0 0 0 1
"""

FIXTURE = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
  <library_geometries><geometry id="geom"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">0 0 0  1 0 0  0 1 0</float_array><technique_common><accessor source="#positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
  </mesh></geometry></library_geometries>
  <library_controllers><controller id="skin"><skin source="#geom">
    <bind_shape_matrix>{_IDENTITY}</bind_shape_matrix>
    <source id="skin-joints"><Name_array id="skin-joints-array" count="1">joint</Name_array><technique_common><accessor source="#skin-joints-array" count="1" stride="1"><param name="JOINT" type="Name"/></accessor></technique_common></source>
    <source id="skin-binds"><float_array id="skin-binds-array" count="16">{_IDENTITY}</float_array><technique_common><accessor source="#skin-binds-array" count="1" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source>
    <source id="skin-weights"><float_array id="skin-weights-array" count="1">1</float_array><technique_common><accessor source="#skin-weights-array" count="1" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common></source>
    <joints><input semantic="JOINT" source="#skin-joints"/><input semantic="INV_BIND_MATRIX" source="#skin-binds"/></joints>
    <vertex_weights count="3"><input semantic="JOINT" source="#skin-joints" offset="0"/><input semantic="WEIGHT" source="#skin-weights" offset="1"/><vcount>1 1 1</vcount><v>0 0 0 0 0 0</v></vertex_weights>
  </skin></controller></library_controllers>
  <library_animations><animation id="joint-matrix-animation">
    <source id="joint-matrix-input"><float_array id="joint-matrix-input-array" count="3">0 0.5 1</float_array><technique_common><accessor source="#joint-matrix-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
    <source id="joint-matrix-output"><float_array id="joint-matrix-output-array" count="48">{_MATRIX_SAMPLES}</float_array><technique_common><accessor source="#joint-matrix-output-array" count="3" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source>
    <source id="joint-matrix-interpolation"><Name_array id="joint-matrix-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array><technique_common><accessor source="#joint-matrix-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
    <sampler id="joint-matrix-sampler"><input semantic="INPUT" source="#joint-matrix-input"/><input semantic="OUTPUT" source="#joint-matrix-output"/><input semantic="INTERPOLATION" source="#joint-matrix-interpolation"/></sampler>
    <channel source="#joint-matrix-sampler" target="joint/transform"/>
  </animation></library_animations>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="rig" name="rig"><node id="joint" sid="joint" name="joint" type="JOINT"><matrix sid="transform">{_IDENTITY}</matrix></node></node>
    <node id="skinned" name="skinned"><matrix>{_IDENTITY}</matrix><instance_controller url="#skin"><skeleton>#joint</skeleton></instance_controller></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def _linked_actions() -> set[bpy.types.Action]:
    linked: set[bpy.types.Action] = set()
    for obj in bpy.data.objects:
        animation_data = obj.animation_data
        if animation_data is None:
            continue
        if animation_data.action is not None:
            linked.add(animation_data.action)
        for track in animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action is not None:
                    linked.add(strip.action)
    return linked


def _assert_native_channels(path: Path, options: object) -> None:
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 1:
        count = 0 if loaded is None else len(loaded.meshes)
        raise AssertionError(f"expected one native primitive, got {count}")

    pose_channels = loaded.meshes[0].skin_pose_anim_channels
    if len(pose_channels) != 1:
        raise AssertionError(f"expected one joint channel list, got {len(pose_channels)}")
    channels = list(pose_channels[0] or [])
    targets = {channel_target(channel) for channel in channels}
    if targets != {_ANIM_TRANSLATION, _ANIM_ROTATION_QUAT, _ANIM_SCALE}:
        raise AssertionError(f"whole matrix was not baked to TRS channels: {targets}")
    for channel in channels:
        if channel_count(channel) < 3:
            raise AssertionError("baked matrix channel lost key samples")
        expected_width = 4 if channel_target(channel) == _ANIM_ROTATION_QUAT else 3
        if channel_value_width(channel) != expected_width:
            raise AssertionError(
                f"unexpected baked channel width: {channel_value_width(channel)}"
            )


def _assert_blender_animation(path: Path, options: object) -> None:
    objects = import_assetkit_file(
        os.fspath(path),
        load_options=options,
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=True,
        select_imported=False,
        shading_mode="AUTO",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
        fit_timeline=True,
    )
    meshes = [obj for obj in objects if obj.type == "MESH"]
    armatures = {
        modifier.object
        for obj in meshes
        for modifier in obj.modifiers
        if modifier.type == "ARMATURE" and modifier.object is not None
    }
    if len(armatures) != 1:
        raise AssertionError(f"expected one connected armature, got {len(armatures)}")
    armature = next(iter(armatures))
    if len(armature.pose.bones) != 1:
        raise AssertionError(f"expected one pose bone, got {len(armature.pose.bones)}")
    bone = armature.pose.bones[0]

    actions = [
        action
        for action in bpy.data.actions
        if any(True for _ in _iter_action_fcurves(action))
    ]
    if not actions:
        raise AssertionError("whole-matrix animation produced no Blender Action")
    linked = _linked_actions()
    if any(action not in linked for action in actions):
        raise AssertionError("whole-matrix animation Action is not assigned to the armature")
    data_paths = {
        fcurve.data_path
        for action in actions
        for fcurve in _iter_action_fcurves(action)
    }
    expected_paths = {
        bone.path_from_id("location"),
        bone.path_from_id("rotation_quaternion"),
    }
    if not expected_paths.issubset(data_paths):
        raise AssertionError(f"missing pose Action paths: {data_paths}")
    if bpy.context.scene.frame_start != 0 or bpy.context.scene.frame_end != 24:
        raise AssertionError(
            "timeline did not fit the matrix animation: "
            f"{bpy.context.scene.frame_start}..{bpy.context.scene.frame_end}"
        )

    expected_origins = {
        0: Vector((0.0, 0.0, 0.0)),
        12: Vector((2.0, 0.0, 0.0)),
        24: Vector((4.0, 0.0, 0.0)),
    }
    rotations = {}
    for frame, expected_origin in expected_origins.items():
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        origin = armature.matrix_world @ bone.matrix.translation
        error = (origin - expected_origin).length
        if error > 1.0e-5:
            raise AssertionError(
                f"frame {frame}: origin={tuple(origin)}, expected={tuple(expected_origin)}, "
                f"error={error:.9g}"
            )
        rotations[frame] = bone.matrix.to_quaternion()
    if abs(rotations[0].dot(rotations[12])) > 0.999:
        raise AssertionError("middle matrix rotation was not animated")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-matrix-animation-") as temp_dir:
        path = Path(temp_dir) / "matrix-animation.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        options = make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading="DEFERRED",
        )
        _assert_native_channels(path, options)
        _assert_blender_animation(path, options)

    print("DAE matrix animation check passed")


if __name__ == "__main__":
    main()
