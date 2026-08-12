#!/usr/bin/env python3
"""Check COLLADA bind-shape ordering and tolerant skin-weight handling.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_dae_skin_bind_shape_check.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.assetkit import native_load_meshes  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


IDENTITY = "1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"
ROTATE_Z_90 = "0 -1 0 0  1 0 0 0  0 0 1 0  0 0 0 1"
SCALE_X_2 = "2 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"
REFLECT_X = "-1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"
SHEAR_X_BY_Y = "1 1 0 0  0 1 0 0  0 0 1 0  0 0 0 1"
SINGULAR = "0 0 0 0  0 0 0 0  0 0 0 0  0 0 0 0"
NAN_DIAGONAL = "0e39 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1"


@dataclass(frozen=True)
class SkinCase:
    name: str
    positions: str
    bind_shape: str
    joint_names: tuple[str, ...]
    inverse_binds: str
    weights: str
    vcount: str
    influences: str
    skeleton_nodes: str
    skeleton_ref: str
    expected_local: tuple[tuple[float, float, float], ...]
    expected_world: tuple[tuple[float, float, float], ...]
    invalid_vertex: int | None = None
    expect_native_bind_pose: bool = True
    expected_bone_count: int | None = None
    expected_weight_rows: tuple[tuple[float, ...], ...] | None = None
    expected_unweighted_vertices: tuple[int, ...] = ()
    skeleton_root_matrix: str = IDENTITY


CASES = (
    SkinCase(
        name="noncommuting-bind-shape",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=ROTATE_Z_90,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        # J * IB * BSM * v, with J = translate(+2 X) and BSM = rotate(+90 Z).
        expected_local=((2.0, 1.0, 0.0), (2.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        expected_world=((2.0, 0.0, 1.0), (2.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
    ),
    SkinCase(
        name="identity-bind-shape-control",
        positions="1 2 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("rootJoint", "childJoint"),
        inverse_binds=(
            "1 0 0 -5  0 1 0 0  0 0 1 0  0 0 0 1  "
            "1 0 0 -5  0 1 0 -3  0 0 1 0  0 0 0 1"
        ),
        weights="1",
        vcount="1 1 1",
        influences="1 0  1 0  1 0",
        skeleton_nodes=(
            '<node id="rootJoint" sid="rootJoint" name="rootJoint" type="JOINT">'
            "<matrix>1 0 0 5  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            '<node id="childJoint" sid="childJoint" name="childJoint" type="JOINT">'
            "<matrix>1 0 0 0  0 1 0 3  0 0 1 0  0 0 0 1</matrix>"
            "</node></node>"
        ),
        skeleton_ref="rootJoint",
        expected_local=((1.0, 2.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 2.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ),
    SkinCase(
        name="invalid-influence-control",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        weights="0.25 0.25 1",
        vcount="2 1 1",
        # Vertex 0 has duplicate valid weights that normalize to one. Vertex 2
        # has a positive, representable, but out-of-palette joint index.
        influences="0 0  0 1  0 2  7 2",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        expected_local=((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        invalid_vertex=2,
    ),
    SkinCase(
        name="invalid-weight-token-alignment",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        # The whole invalid token must occupy one array element so the later
        # valid weight stays aligned with vertex 2.
        weights="-1 NaN 2",
        vcount="1 1 1",
        influences="0 0  0 1  0 2",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (2.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (2.0, 0.0, 1.0)),
        expected_weight_rows=((0.0,), (0.0,), (1.0,)),
        expected_unweighted_vertices=(0, 1),
    ),
    SkinCase(
        name="duplicate-weight-overflow",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        # Each token is finite in float32, but their duplicate-joint sum is
        # not. The retained influence must still normalize to one.
        weights="3e38 3e38 1",
        vcount="2 1 1",
        influences="0 0  0 1  0 2  0 2",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        expected_local=((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0)),
        expected_world=((3.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 0.0, 1.0)),
        expected_weight_rows=((1.0, 0.0), (1.0, 0.0), (1.0, 0.0)),
    ),
    SkinCase(
        name="singular-inverse-bind-fallback",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        inverse_binds=SINGULAR,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        # Invalid IBM falls back to inverse(joint bind-world), preserving the
        # authored mesh instead of collapsing it to the origin.
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ),
    SkinCase(
        name="singular-inverse-bind-nonidentity-root",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        inverse_binds=SINGULAR,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        # The fallback inverse bind must be derived in world space (+7 X),
        # then baked in the translated armature-root space (+5 X).
        skeleton_ref="skeletonRoot",
        expected_local=((-4.0, 0.0, 0.0), (-5.0, 0.0, 0.0), (-5.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        skeleton_root_matrix="1 0 0 5  0 1 0 0  0 0 1 0  0 0 0 1",
    ),
    SkinCase(
        name="nan-inverse-bind-fallback",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("joint1",),
        # 0 * 10^39 parses to NaN without relying on non-standard NaN text.
        inverse_binds=NAN_DIAGONAL,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            "<matrix>1 0 0 2  0 1 0 0  0 0 1 0  0 0 0 1</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ),
    SkinCase(
        name="nonfinite-bind-shape-skip",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=NAN_DIAGONAL,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            f"<matrix>{IDENTITY}</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        # A non-finite bind shape is not safe to apply in either native or
        # Python fallback code. Preserve the finite source mesh instead.
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        expect_native_bind_pose=False,
    ),
    SkinCase(
        name="singular-bind-shape-control",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=SINGULAR,
        joint_names=("joint1",),
        inverse_binds=IDENTITY,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes=(
            '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
            f"<matrix>{IDENTITY}</matrix>"
            "</node>"
        ),
        skeleton_ref="skeletonRoot",
        # Unlike an inverse bind, bind_shape_matrix need not be invertible.
        # A finite zero matrix is an authored (collapsing) transform.
        expected_local=((0.0, 0.0, 0.0),) * 3,
        expected_world=((0.0, 0.0, 0.0),) * 3,
    ),
    SkinCase(
        name="unresolved-valid-inverse-bind",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("missingJoint",),
        inverse_binds="1 0 0 -2  0 1 0 0  0 0 1 0  0 0 0 1",
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes="",
        skeleton_ref="skeletonRoot",
        # A valid inverse bind reconstructs the missing joint bind matrix, so
        # native baking remains finite even though Blender cannot create a bone.
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        expected_bone_count=0,
    ),
    SkinCase(
        name="unresolved-singular-inverse-bind-skip",
        positions="1 0 0  0 0 0  0 1 0",
        bind_shape=IDENTITY,
        joint_names=("missingJoint",),
        inverse_binds=SINGULAR,
        weights="1",
        vcount="1 1 1",
        influences="0 0  0 0  0 0",
        skeleton_nodes="",
        skeleton_ref="skeletonRoot",
        expected_local=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        expected_world=((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        expect_native_bind_pose=False,
        expected_bone_count=0,
    ),
)


FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <contributor><authoring_tool>AssetKit Blender skin regression check</authoring_tool></contributor>
    <unit name="meter" meter="1"/><up_axis>Y_UP</up_axis>
  </asset>
  <library_geometries>
    <geometry id="geom" name="SkinTriangle"><mesh>
      <source id="geom-positions">
        <float_array id="geom-positions-array" count="9">{positions}</float_array>
        <technique_common><accessor source="#geom-positions-array" count="3" stride="3">
          <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
        </accessor></technique_common>
      </source>
      <vertices id="geom-vertices"><input semantic="POSITION" source="#geom-positions"/></vertices>
      <triangles count="1"><input semantic="VERTEX" source="#geom-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
  </library_geometries>
  <library_controllers>
    <controller id="skin" name="Skin"><skin source="#geom">
      <bind_shape_matrix>{bind_shape}</bind_shape_matrix>
      <source id="skin-joints">
        <Name_array id="skin-joints-array" count="{joint_count}">{joint_names}</Name_array>
        <technique_common><accessor source="#skin-joints-array" count="{joint_count}" stride="1">
          <param name="JOINT" type="Name"/>
        </accessor></technique_common>
      </source>
      <source id="skin-bindposes">
        <float_array id="skin-bindposes-array" count="{bind_float_count}">{inverse_binds}</float_array>
        <technique_common><accessor source="#skin-bindposes-array" count="{joint_count}" stride="16">
          <param name="TRANSFORM" type="float4x4"/>
        </accessor></technique_common>
      </source>
      <source id="skin-weights">
        <float_array id="skin-weights-array" count="{weight_count}">{weights}</float_array>
        <technique_common><accessor source="#skin-weights-array" count="{weight_count}" stride="1">
          <param name="WEIGHT" type="float"/>
        </accessor></technique_common>
      </source>
      <joints>
        <input semantic="JOINT" source="#skin-joints"/>
        <input semantic="INV_BIND_MATRIX" source="#skin-bindposes"/>
      </joints>
      <vertex_weights count="3">
        <input semantic="JOINT" source="#skin-joints" offset="0"/>
        <input semantic="WEIGHT" source="#skin-weights" offset="1"/>
        <vcount>{vcount}</vcount><v>{influences}</v>
      </vertex_weights>
    </skin></controller>
  </library_controllers>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="skeletonRoot" name="skeletonRoot" type="NODE">
        <matrix>{skeleton_root_matrix}</matrix>{skeleton_nodes}
      </node>
      <node id="meshNode" name="meshNode" type="NODE">
        <matrix>{identity}</matrix>
        <instance_controller url="#skin"><skeleton>#{skeleton_ref}</skeleton></instance_controller>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""

NORMAL_SOURCES = """      <source id="geom-normals">
        <float_array id="geom-normals-array" count="9">{normals}</float_array>
        <technique_common><accessor source="#geom-normals-array" count="3" stride="3">
          <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
        </accessor></technique_common>
      </source>
      <source id="geom-tangents">
        <float_array id="geom-tangents-array" count="9">{tangents}</float_array>
        <technique_common><accessor source="#geom-tangents-array" count="3" stride="3">
          <param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/>
        </accessor></technique_common>
      </source>
"""

NORMAL_RIGID_CASE = SkinCase(
    name="nonuniform-bind-shape-vectors",
    # The source triangle's geometric normal is normalize(1, 1, 0).
    positions="0 0 0  0 0 1  1 -1 0",
    bind_shape=SCALE_X_2,
    joint_names=("joint1",),
    inverse_binds=IDENTITY,
    weights="1",
    vcount="1 1 1",
    influences="0 0  0 0  0 0",
    skeleton_nodes=(
        '<node id="joint1" sid="joint1" name="joint1" type="JOINT">'
        f"<matrix>{IDENTITY}</matrix>"
        "</node>"
    ),
    skeleton_ref="skeletonRoot",
    expected_local=((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (2.0, -1.0, 0.0)),
    expected_world=((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), (2.0, 0.0, -1.0)),
)

NORMAL_BLENDED_CASE = SkinCase(
    name="nonuniform-bind-shape-vectors-blended",
    positions=NORMAL_RIGID_CASE.positions,
    bind_shape=SCALE_X_2,
    joint_names=("joint1",),
    inverse_binds=IDENTITY,
    weights="0.5",
    vcount="2 2 2",
    # Duplicate positive slots deliberately force the general blended-matrix
    # path while retaining the same effective transform as the rigid control.
    influences="0 0 0 0  0 0 0 0  0 0 0 0",
    skeleton_nodes=NORMAL_RIGID_CASE.skeleton_nodes,
    skeleton_ref="skeletonRoot",
    expected_local=NORMAL_RIGID_CASE.expected_local,
    expected_world=NORMAL_RIGID_CASE.expected_world,
)

NORMAL_SHEAR_CASE = SkinCase(
    name="sheared-bind-shape-vectors",
    positions=NORMAL_RIGID_CASE.positions,
    bind_shape=SHEAR_X_BY_Y,
    joint_names=("joint1",),
    inverse_binds=IDENTITY,
    weights="1",
    vcount="1 1 1",
    influences="0 0  0 0  0 0",
    skeleton_nodes=NORMAL_RIGID_CASE.skeleton_nodes,
    skeleton_ref="skeletonRoot",
    expected_local=((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
    expected_world=((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
)

NORMAL_REFLECTION_CASE = SkinCase(
    name="reflected-bind-shape-vectors",
    positions=NORMAL_RIGID_CASE.positions,
    bind_shape=REFLECT_X,
    joint_names=("joint1",),
    inverse_binds=IDENTITY,
    weights="1",
    vcount="1 1 1",
    influences="0 0  0 0  0 0",
    skeleton_nodes=NORMAL_RIGID_CASE.skeleton_nodes,
    skeleton_ref="skeletonRoot",
    expected_local=((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, -1.0, 0.0)),
    expected_world=((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, -1.0, 0.0)),
)

NORMAL_CASES = (
    NORMAL_RIGID_CASE,
    NORMAL_BLENDED_CASE,
    NORMAL_SHEAR_CASE,
    NORMAL_REFLECTION_CASE,
)
NORMAL_EXPECTED_VECTORS = {
    NORMAL_RIGID_CASE.name: (
        (0.4472136, 0.8944272, 0.0),
        (0.8944272, -0.4472136, 0.0, 1.0),
    ),
    NORMAL_BLENDED_CASE.name: (
        (0.4472136, 0.8944272, 0.0),
        (0.8944272, -0.4472136, 0.0, 1.0),
    ),
    NORMAL_SHEAR_CASE.name: (
        (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0, 1.0),
    ),
    NORMAL_REFLECTION_CASE.name: (
        (-0.7071068, 0.7071068, 0.0),
        (-0.7071068, -0.7071068, 0.0, -1.0),
    ),
}


def _fixture_text(case: SkinCase) -> str:
    return FIXTURE.format(
        positions=case.positions,
        bind_shape=case.bind_shape,
        joint_count=len(case.joint_names),
        joint_names=" ".join(case.joint_names),
        bind_float_count=16 * len(case.joint_names),
        inverse_binds=case.inverse_binds,
        weight_count=len(case.weights.split()),
        weights=case.weights,
        vcount=case.vcount,
        influences=case.influences,
        identity=IDENTITY,
        skeleton_root_matrix=case.skeleton_root_matrix,
        skeleton_nodes=case.skeleton_nodes,
        skeleton_ref=case.skeleton_ref,
    )


def _normal_fixture_text(case: SkinCase) -> str:
    text = _fixture_text(case)
    vertex_marker = (
        '      <vertices id="geom-vertices"><input semantic="POSITION" '
        'source="#geom-positions"/></vertices>\n'
    )
    triangle_marker = (
        '      <triangles count="1"><input semantic="VERTEX" '
        'source="#geom-vertices" offset="0"/><p>0 1 2</p></triangles>'
    )
    sources = NORMAL_SOURCES.format(
        normals="0.70710678 0.70710678 0  " * 3,
        tangents="0.70710678 -0.70710678 0  " * 3,
    )
    triangle = (
        '      <triangles count="1">'
        '<input semantic="VERTEX" source="#geom-vertices" offset="0"/>'
        '<input semantic="NORMAL" source="#geom-normals" offset="1"/>'
        '<input semantic="TEXTANGENT" source="#geom-tangents" offset="2"/>'
        '<p>0 0 0  1 1 1  2 2 2</p></triangles>'
    )
    if vertex_marker not in text or triangle_marker not in text:
        raise AssertionError("normal fixture markers no longer match the base fixture")
    return text.replace(vertex_marker, sources + vertex_marker).replace(
        triangle_marker, triangle
    )


def _float_values(buffer: object) -> list[float]:
    if not buffer:
        return []
    return [float(value) for value in memoryview(buffer).cast("B").cast("f")]


def _points(values: list[float]) -> list[tuple[float, float, float]]:
    return list(zip(values[0::3], values[1::3], values[2::3]))


def _assert_points_close(
    actual: list[tuple[float, float, float]],
    expected: tuple[tuple[float, float, float], ...],
    label: str,
) -> None:
    if len(actual) != len(expected):
        raise AssertionError(
            f"{label}: expected {len(expected)} points, got {len(actual)}"
        )
    for index, (point, wanted) in enumerate(zip(actual, expected)):
        for component, expected_component in zip(point, wanted):
            if not math.isclose(
                component, expected_component, rel_tol=1.0e-6, abs_tol=1.0e-6
            ):
                raise AssertionError(
                    f"{label}[{index}]: expected {wanted}, got {point}"
                )


def _assert_vector_close(
    actual: tuple[float, ...], expected: tuple[float, ...], label: str
) -> None:
    if len(actual) != len(expected):
        raise AssertionError(
            f"{label}: expected {len(expected)} components, got {len(actual)}"
        )
    for component, expected_component in zip(actual, expected):
        if not math.isclose(
            component, expected_component, rel_tol=1.0e-6, abs_tol=1.0e-6
        ):
            raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _object_points(
    obj: bpy.types.Object, *, evaluated: bool
) -> list[tuple[float, float, float]]:
    if not evaluated:
        return [tuple(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices]

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = obj.evaluated_get(depsgraph)
    mesh = evaluated_obj.to_mesh()
    try:
        return [
            tuple(evaluated_obj.matrix_world @ vertex.co) for vertex in mesh.vertices
        ]
    finally:
        evaluated_obj.to_mesh_clear()


def _check_weight_rows(case: SkinCase, data: object) -> None:
    width = int(data.skin_joint_width)
    joints = [
        int(value) for value in memoryview(data.skin_joints_u16).cast("B").cast("H")
    ]
    weights = _float_values(data.skin_weights_f32)
    if case.expected_weight_rows is not None:
        rows = [
            tuple(weights[index * width : (index + 1) * width])
            for index in range(int(data.skin_vertex_count))
        ]
        if len(rows) != len(case.expected_weight_rows):
            raise AssertionError(
                f"{case.name}: expected {len(case.expected_weight_rows)} weight rows, got {len(rows)}"
            )
        for index, (row, expected) in enumerate(
            zip(rows, case.expected_weight_rows)
        ):
            _assert_vector_close(row, expected, f"{case.name} weight row {index}")

    if case.invalid_vertex is None:
        return

    valid_row = weights[:width]
    invalid_base = case.invalid_vertex * width
    invalid_row = weights[invalid_base : invalid_base + width]
    invalid_joints = joints[invalid_base : invalid_base + width]
    if not math.isclose(sum(valid_row), 1.0, rel_tol=1.0e-6, abs_tol=1.0e-6):
        raise AssertionError(
            f"{case.name}: valid weights were not normalized: {valid_row}"
        )
    if not any(
        weight > 0.0 and joint >= data.skin_joint_count
        for joint, weight in zip(invalid_joints, invalid_row)
    ):
        raise AssertionError(
            f"{case.name}: fixture did not retain its invalid influence: {list(zip(invalid_joints, invalid_row))}"
        )


def _check_case(path: Path, case: SkinCase) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="DEFERRED",
    )
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 1:
        raise AssertionError(f"{case.name}: expected one native mesh")

    data = loaded.meshes[0]
    if not data.has_skin:
        raise AssertionError(f"{case.name}: native skin data was dropped")
    if bool(data.skin_mesh_in_bind_pose) != case.expect_native_bind_pose:
        raise AssertionError(
            f"{case.name}: expected native bind-pose bake "
            f"{case.expect_native_bind_pose}, got {data.skin_mesh_in_bind_pose}"
        )
    native_points = _points(_float_values(data.vertices_f32))
    if not all(math.isfinite(component) for point in native_points for component in point):
        raise AssertionError(f"{case.name}: native vertices contain non-finite values: {native_points}")
    _assert_points_close(
        native_points,
        case.expected_local,
        f"{case.name} native/local",
    )
    _check_weight_rows(case, data)

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
    bpy.context.view_layer.update()
    meshes = [obj for obj in objects if obj.type == "MESH" and obj.data is not None]
    if len(meshes) != 1:
        raise AssertionError(
            f"{case.name}: expected one Blender mesh, got {len(meshes)}"
        )
    obj = meshes[0]
    _assert_points_close(
        [tuple(vertex.co) for vertex in obj.data.vertices],
        case.expected_local,
        f"{case.name} Blender/local",
    )
    _assert_points_close(
        _object_points(obj, evaluated=False),
        case.expected_world,
        f"{case.name} Blender/world",
    )

    armature_modifiers = [
        modifier for modifier in obj.modifiers if modifier.type == "ARMATURE"
    ]
    if len(armature_modifiers) != 1 or armature_modifiers[0].object is None:
        raise AssertionError(f"{case.name}: expected one connected armature modifier")
    armature = armature_modifiers[0].object
    if len(obj.vertex_groups) != len(case.joint_names):
        raise AssertionError(
            f"{case.name}: expected {len(case.joint_names)} vertex groups, "
            f"got {len(obj.vertex_groups)}"
        )
    expected_bones = (
        len(case.joint_names)
        if case.expected_bone_count is None
        else case.expected_bone_count
    )
    if len(armature.data.bones) != expected_bones:
        raise AssertionError(
            f"{case.name}: expected {expected_bones} armature bones, "
            f"got {len(armature.data.bones)}"
        )
    if expected_bones == len(case.joint_names):
        missing_bones = [
            group.name for group in obj.vertex_groups if armature.data.bones.get(group.name) is None
        ]
        if missing_bones:
            raise AssertionError(
                f"{case.name}: vertex groups have no matching bones: {missing_bones}"
            )
    for vertex in obj.data.vertices:
        for membership in vertex.groups:
            if not math.isfinite(membership.weight):
                raise AssertionError(
                    f"{case.name}: vertex {vertex.index} has non-finite group weight"
                )
    for pose_position in ("POSE", "REST"):
        armature.data.pose_position = pose_position
        bpy.context.view_layer.update()
        _assert_points_close(
            _object_points(obj, evaluated=True),
            case.expected_world,
            f"{case.name} Blender/{pose_position.lower()}",
        )

    unweighted_vertices = set(case.expected_unweighted_vertices)
    if case.invalid_vertex is not None:
        unweighted_vertices.add(case.invalid_vertex)
    for vertex_index in sorted(unweighted_vertices):
        if obj.data.vertices[vertex_index].groups:
            memberships = [
                group.group for group in obj.data.vertices[vertex_index].groups
            ]
            raise AssertionError(
                f"{case.name}: invalid influence reached Blender groups: {memberships}"
            )


def _check_bind_pose_vectors(path: Path, case: SkinCase) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    options = make_load_options(
        coordinate_system="Y_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="DEFERRED",
        defer_custom_normals=False,
        preserve_tangents=True,
    )
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 1:
        raise AssertionError(f"{case.name}: expected one native mesh")

    data = loaded.meshes[0]
    if not data.skin_mesh_in_bind_pose:
        raise AssertionError(f"{case.name}: native bind-pose bake was skipped")
    expected_normal, expected_tangent = NORMAL_EXPECTED_VECTORS[case.name]
    normals = _points(_float_values(data.normals_f32))
    tangents = _float_values(data.tangents_f32)
    if len(normals) != 3 or len(tangents) != 12:
        raise AssertionError(
            f"{case.name}: missing native normal/tangent data"
        )
    for index, normal in enumerate(normals):
        _assert_vector_close(normal, expected_normal, f"native normal {index}")
    for index in range(3):
        tangent = tuple(tangents[index * 4 : index * 4 + 4])
        _assert_vector_close(tangent, expected_tangent, f"native tangent {index}")

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
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    if len(mesh_objects) != 1:
        raise AssertionError(
            f"{case.name}: expected one Blender mesh, got {len(mesh_objects)}"
        )
    mesh = mesh_objects[0].data
    mesh.update()
    for index, normal in enumerate(mesh.corner_normals):
        _assert_vector_close(
            tuple(normal.vector), expected_normal, f"Blender normal {index}"
        )

    tangent_attribute = mesh.attributes.get("assetkit_tangent")
    if tangent_attribute is not None:
        tangent = tuple(tangent_attribute.data[0].vector)
    else:
        components = []
        for suffix in ("x", "y", "z", "w"):
            component = mesh.attributes.get(f"assetkit_tangent_{suffix}")
            if component is None:
                raise AssertionError(
                    f"{case.name}: Blender tangent attribute was dropped"
                )
            components.append(float(component.data[0].value))
        tangent = tuple(components)
    _assert_vector_close(tangent, expected_tangent, "Blender tangent")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-skin-") as temp_dir:
        directory = Path(temp_dir)
        for case in CASES:
            path = directory / f"{case.name}.dae"
            path.write_text(_fixture_text(case), encoding="utf-8")
            _check_case(path, case)

        for case in NORMAL_CASES:
            normal_path = directory / f"{case.name}.dae"
            normal_path.write_text(_normal_fixture_text(case), encoding="utf-8")
            _check_bind_pose_vectors(normal_path, case)

    print("DAE skin bind-shape check passed")


if __name__ == "__main__":
    main()
