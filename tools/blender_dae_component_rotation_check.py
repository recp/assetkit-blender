#!/usr/bin/env python3
"""Check COLLADA component rotations are composed before pose animation output.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_dae_component_rotation_check.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.imp.buffers import (  # noqa: E402
    channel_clip_index,
    channel_count,
    channel_target,
    channel_value_width,
)
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


_ANIM_ROTATION_QUAT = 2
_IDENTITY = "1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"


def _scalar_animation(animation_id: str, target: str, values: str) -> str:
    output_param = "ANGLE" if target.endswith(".ANGLE") else "X"
    return f"""<animation id="{animation_id}">
      <source id="{animation_id}-input">
        <float_array id="{animation_id}-input-array" count="3">0 0.5 1</float_array>
        <technique_common><accessor source="#{animation_id}-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common>
      </source>
      <source id="{animation_id}-output">
        <float_array id="{animation_id}-output-array" count="3">{values}</float_array>
        <technique_common><accessor source="#{animation_id}-output-array" count="3" stride="1"><param name="{output_param}" type="float"/></accessor></technique_common>
      </source>
      <source id="{animation_id}-interpolation">
        <Name_array id="{animation_id}-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array>
        <technique_common><accessor source="#{animation_id}-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common>
      </source>
      <sampler id="{animation_id}-sampler">
        <input semantic="INPUT" source="#{animation_id}-input"/>
        <input semantic="OUTPUT" source="#{animation_id}-output"/>
        <input semantic="INTERPOLATION" source="#{animation_id}-interpolation"/>
      </sampler>
      <channel source="#{animation_id}-sampler" target="{target}"/>
    </animation>"""


def _axis_angle_animation() -> str:
    animation_id = "child-axis-animation"
    return f"""<animation id="{animation_id}">
      <source id="{animation_id}-input">
        <float_array id="{animation_id}-input-array" count="3">0 0.5 1</float_array>
        <technique_common><accessor source="#{animation_id}-input-array" count="3" stride="1"><param name="TIME" type="float"/></accessor></technique_common>
      </source>
      <source id="{animation_id}-output">
        <float_array id="{animation_id}-output-array" count="12">0 0 1 0  0 0 1 45  0 0 1 0</float_array>
        <technique_common><accessor source="#{animation_id}-output-array" count="3" stride="4"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/><param name="ANGLE" type="float"/></accessor></technique_common>
      </source>
      <source id="{animation_id}-interpolation">
        <Name_array id="{animation_id}-interpolation-array" count="3">LINEAR LINEAR LINEAR</Name_array>
        <technique_common><accessor source="#{animation_id}-interpolation-array" count="3" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common>
      </source>
      <sampler id="{animation_id}-sampler">
        <input semantic="INPUT" source="#{animation_id}-input"/>
        <input semantic="OUTPUT" source="#{animation_id}-output"/>
        <input semantic="INTERPOLATION" source="#{animation_id}-interpolation"/>
      </sampler>
      <channel source="#{animation_id}-sampler" target="child/axis"/>
    </animation>"""


FIXTURE = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>
  <library_geometries><geometry id="geom"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">3 1 3.5  3.25 1 3.5  3 1.25 3.5</float_array><technique_common><accessor source="#positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
  </mesh></geometry></library_geometries>
  <library_controllers><controller id="skin"><skin source="#geom">
    <bind_shape_matrix>{_IDENTITY}</bind_shape_matrix>
    <source id="skin-joints">
      <Name_array id="skin-joints-array" count="3">root child tip</Name_array>
      <technique_common><accessor source="#skin-joints-array" count="3" stride="1"><param name="JOINT" type="Name"/></accessor></technique_common>
    </source>
    <source id="skin-binds">
      <float_array id="skin-binds-array" count="48">
        {_IDENTITY}
        1 0 0 -1  0 1 0 -2  0 0 1 -3  0 0 0 1
        1 0 0 -3  0 1 0 -1  0 0 1 -3.5  0 0 0 1
      </float_array>
      <technique_common><accessor source="#skin-binds-array" count="3" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common>
    </source>
    <source id="skin-weights">
      <float_array id="skin-weights-array" count="1">1</float_array>
      <technique_common><accessor source="#skin-weights-array" count="1" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common>
    </source>
    <joints><input semantic="JOINT" source="#skin-joints"/><input semantic="INV_BIND_MATRIX" source="#skin-binds"/></joints>
    <vertex_weights count="3"><input semantic="JOINT" source="#skin-joints" offset="0"/><input semantic="WEIGHT" source="#skin-weights" offset="1"/><vcount>1 1 1</vcount><v>2 0 2 0 2 0</v></vertex_weights>
  </skin></controller></library_controllers>
  <library_animations>
    {_scalar_animation("root-x-animation", "root/rotateX.ANGLE", "0 30 0")}
    {_scalar_animation("root-y-animation", "root/rotateY.ANGLE", "0 -40 0")}
    {_scalar_animation("root-z-animation", "root/rotateZ.ANGLE", "0 60 0")}
    {_scalar_animation("mid-x-animation", "mid/translation.X", "0 10 0")}
    {_scalar_animation("mid-rx-animation", "mid/rotateX.ANGLE", "0 20 0")}
    {_scalar_animation("mid-ry-animation", "mid/rotateY.ANGLE", "0 15 0")}
    {_scalar_animation("mid-rz-animation", "mid/rotateZ.ANGLE", "0 -25 0")}
    {_axis_angle_animation()}
  </library_animations>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="root" sid="root" name="root" type="JOINT">
      <rotate sid="rotateX">1 0 0 0</rotate>
      <rotate sid="rotateY">0 1 0 0</rotate>
      <rotate sid="rotateZ">0 0 1 0</rotate>
      <node id="mid" sid="mid" name="mid">
        <translate sid="translation">0 0 0</translate>
        <rotate sid="rotateX">1 0 0 0</rotate>
        <rotate sid="rotateY">0 1 0 0</rotate>
        <rotate sid="rotateZ">0 0 1 0</rotate>
        <node id="child" sid="child" name="child" type="JOINT">
          <translate sid="translation">1 2 3</translate>
          <rotate sid="axis">0 0 1 0</rotate>
          <node id="tip" sid="tip" name="tip" type="JOINT"><translate sid="translation">2 -1 0.5</translate></node>
        </node>
      </node>
    </node>
    <node id="skinned"><matrix>{_IDENTITY}</matrix><instance_controller url="#skin"><skeleton>#root</skeleton></instance_controller></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def _rotation_channels(channels: list[object]) -> list[object]:
    return [channel for channel in channels if channel_target(channel) == _ANIM_ROTATION_QUAT]


def _assert_native_channels(path: Path, options: object) -> None:
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 1:
        count = 0 if loaded is None else len(loaded.meshes)
        raise AssertionError(f"expected one native primitive, got {count}")

    primitive = loaded.meshes[0]
    pose_channels = primitive.skin_pose_anim_channels
    if len(pose_channels) != 3:
        raise AssertionError(f"expected three joint channel lists, got {len(pose_channels)}")

    for joint_index, label in ((0, "component root"), (1, "full child channel")):
        rotations = _rotation_channels(pose_channels[joint_index])
        if len(rotations) != 1:
            raise AssertionError(
                f"{label}: expected one composed quaternion channel, got {len(rotations)}"
            )
        channel = rotations[0]
        if channel_value_width(channel) != 4 or channel_count(channel) < 3:
            raise AssertionError(
                f"{label}: unexpected quaternion layout "
                f"width={channel_value_width(channel)} count={channel_count(channel)}"
            )
        if channel_clip_index(channel) != 0:
            raise AssertionError(f"{label}: implicit COLLADA clip was split")

    mid_nodes = [node for node in loaded.nodes if node.name == "mid"]
    if len(mid_nodes) != 1:
        raise AssertionError(f"expected one intermediate node, got {len(mid_nodes)}")
    mid_rotations = _rotation_channels(list(mid_nodes[0].anim_channels or []))
    if len(mid_rotations) != 1 or channel_value_width(mid_rotations[0]) != 4:
        raise AssertionError(
            "intermediate component rotations were not composed into one quaternion"
        )


def _joint_origin(armature: bpy.types.Object, bone: bpy.types.PoseBone) -> Vector:
    return armature.matrix_world @ bone.matrix.translation


def _assert_close(label: str, actual: Vector, expected: Vector) -> None:
    error = (actual - expected).length
    if error > 1.0e-5:
        raise AssertionError(
            f"{label}: got {tuple(round(value, 7) for value in actual)}, "
            f"expected {tuple(round(value, 7) for value in expected)}, error={error:.9g}"
        )


def _literal_joint_origins(frame: int) -> tuple[Vector, Vector]:
    if frame == 12:
        root = (
            Matrix.Rotation(math.radians(30.0), 4, "X")
            @ Matrix.Rotation(math.radians(-40.0), 4, "Y")
            @ Matrix.Rotation(math.radians(60.0), 4, "Z")
        )
        child_rotation = Matrix.Rotation(math.radians(45.0), 4, "Z")
        mid_translation = Vector((10.0, 0.0, 0.0))
        mid_rotation = (
            Matrix.Rotation(math.radians(20.0), 4, "X")
            @ Matrix.Rotation(math.radians(15.0), 4, "Y")
            @ Matrix.Rotation(math.radians(-25.0), 4, "Z")
        )
    else:
        root = Matrix.Identity(4)
        child_rotation = Matrix.Identity(4)
        mid_translation = Vector((0.0, 0.0, 0.0))
        mid_rotation = Matrix.Identity(4)

    child = root @ (mid_translation + mid_rotation @ Vector((1.0, 2.0, 3.0)))
    tip = root @ (
        mid_translation
        + mid_rotation
        @ (
            Vector((1.0, 2.0, 3.0))
            + child_rotation @ Vector((2.0, -1.0, 0.5))
        )
    )
    return child, tip


def _assert_blender_pose(path: Path, options: object) -> None:
    objects = import_assetkit_file(
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
    if len(armature.pose.bones) != 4:
        raise AssertionError(
            "expected animated non-joint ancestor to be preserved as a fourth bone, "
            f"got {len(armature.pose.bones)}: "
            f"{[(bone.name, bone.parent.name if bone.parent else None) for bone in armature.pose.bones]}"
        )
    roots = [bone for bone in armature.pose.bones if bone.parent is None]
    if len(roots) != 1 or len(roots[0].children) != 1:
        raise AssertionError("unexpected root/helper hierarchy")
    root = roots[0]
    mid = root.children[0]
    if len(mid.children) != 1 or len(mid.children[0].children) != 1:
        raise AssertionError("unexpected helper/child/tip hierarchy")
    child = mid.children[0]
    tip = child.children[0]
    if not root.bone.use_deform or mid.bone.use_deform or not child.bone.use_deform or not tip.bone.use_deform:
        raise AssertionError(
            "only authored skin joints may be deform bones: "
            f"{[(bone.name, bone.bone.use_deform) for bone in armature.pose.bones]}"
        )

    for frame in (0, 12, 24):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        expected_child, expected_tip = _literal_joint_origins(frame)
        _assert_close(f"frame {frame} child", _joint_origin(armature, child), expected_child)
        _assert_close(f"frame {frame} tip", _joint_origin(armature, tip), expected_tip)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-component-rotation-") as temp_dir:
        path = Path(temp_dir) / "component-rotation.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        options = make_load_options(
            coordinate_system="Y_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading="DEFERRED",
        )
        _assert_native_channels(path, options)
        _assert_blender_pose(path, options)

    print("DAE component rotation check passed")


if __name__ == "__main__":
    main()
