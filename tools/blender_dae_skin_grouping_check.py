#!/usr/bin/env python3
"""Check that COLLADA skin grouping preserves controller palettes.

Run inside Blender:

  blender --background --factory-startup --python-exit-code 1 \
    --python tools/blender_dae_skin_grouping_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter, defaultdict
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


def _controller_xml(controller_id: str, joint: str, inverse_bind: str) -> str:
    return f"""<controller id="{controller_id}"><skin source="#geom">
      <bind_shape_matrix>{IDENTITY}</bind_shape_matrix>
      <source id="{controller_id}-joints">
        <Name_array id="{controller_id}-joints-array" count="1">{joint}</Name_array>
        <technique_common><accessor source="#{controller_id}-joints-array" count="1" stride="1"><param name="JOINT" type="Name"/></accessor></technique_common>
      </source>
      <source id="{controller_id}-binds">
        <float_array id="{controller_id}-binds-array" count="16">{inverse_bind}</float_array>
        <technique_common><accessor source="#{controller_id}-binds-array" count="1" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common>
      </source>
      <source id="{controller_id}-weights">
        <float_array id="{controller_id}-weights-array" count="1">1</float_array>
        <technique_common><accessor source="#{controller_id}-weights-array" count="1" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common>
      </source>
      <joints><input semantic="JOINT" source="#{controller_id}-joints"/><input semantic="INV_BIND_MATRIX" source="#{controller_id}-binds"/></joints>
      <vertex_weights count="3"><input semantic="JOINT" source="#{controller_id}-joints" offset="0"/><input semantic="WEIGHT" source="#{controller_id}-weights" offset="1"/><vcount>1 1 1</vcount><v>0 0 0 0 0 0</v></vertex_weights>
    </skin></controller>"""


FIXTURE = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>
  <library_geometries><geometry id="geom"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">1 0 0  0 0 0  0 1 0</float_array><technique_common><accessor source="#positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
    <triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 2 1</p></triangles>
  </mesh></geometry></library_geometries>
  <library_controllers>
    {_controller_xml("skinA", "jointA", IDENTITY)}
    {_controller_xml("skinB", "jointB", "1 0 0 -2  0 1 0 0  0 0 1 0  0 0 0 1")}
  </library_controllers>
  <library_animations><animation id="jointB-animation">
    <source id="jointB-animation-input"><float_array id="jointB-animation-input-array" count="2">0 1</float_array><technique_common><accessor source="#jointB-animation-input-array" count="2" stride="1"><param name="TIME" type="float"/></accessor></technique_common></source>
    <source id="jointB-animation-output"><float_array id="jointB-animation-output-array" count="6">2 0 0  4 0 0</float_array><technique_common><accessor source="#jointB-animation-output-array" count="2" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
    <source id="jointB-animation-interpolation"><Name_array id="jointB-animation-interpolation-array" count="2">LINEAR LINEAR</Name_array><technique_common><accessor source="#jointB-animation-interpolation-array" count="2" stride="1"><param name="INTERPOLATION" type="name"/></accessor></technique_common></source>
    <sampler id="jointB-animation-sampler"><input semantic="INPUT" source="#jointB-animation-input"/><input semantic="OUTPUT" source="#jointB-animation-output"/><input semantic="INTERPOLATION" source="#jointB-animation-interpolation"/></sampler>
    <channel source="#jointB-animation-sampler" target="jointB/translation"/>
  </animation></library_animations>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="skeletonRoot"><matrix>{IDENTITY}</matrix>
      <node id="jointA" sid="jointA" name="jointA" type="JOINT"><matrix>{IDENTITY}</matrix></node>
      <node id="jointB" sid="jointB" name="jointB" type="JOINT"><translate sid="translation">2 0 0</translate></node>
    </node>
    <node id="sharedSkinNode"><matrix>{IDENTITY}</matrix><instance_controller url="#skinA"><skeleton>#skeletonRoot</skeleton></instance_controller></node>
    <node id="multipleControllerNode"><matrix>{IDENTITY}</matrix>
      <instance_controller url="#skinA"><skeleton>#skeletonRoot</skeleton></instance_controller>
      <instance_controller url="#skinB"><skeleton>#skeletonRoot</skeleton></instance_controller>
    </node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


INSTANCE_SKELETON_FIXTURE = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>
  <library_geometries><geometry id="geom"><mesh>
    <source id="positions"><float_array id="positions-array" count="9">0 0 0  1 0 0  0 1 0</float_array><technique_common><accessor source="#positions-array" count="3" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
    <vertices id="vertices"><input semantic="POSITION" source="#positions"/></vertices>
    <triangles count="1"><input semantic="VERTEX" source="#vertices" offset="0"/><p>0 1 2</p></triangles>
  </mesh></geometry></library_geometries>
  <library_controllers>{_controller_xml("skinShared", "joint", IDENTITY)}</library_controllers>
  <library_visual_scenes><visual_scene id="Scene">
    <node id="rigA" name="rigA"><translate sid="translation">0 0 0</translate>
      <node id="jointA" sid="joint" name="sharedJoint" type="JOINT"><matrix>{IDENTITY}</matrix></node>
    </node>
    <node id="rigB" name="rigB"><translate sid="translation">100 0 0</translate>
      <node id="jointB" sid="joint" name="sharedJoint" type="JOINT"><matrix>{IDENTITY}</matrix></node>
    </node>
    <node id="meshA" name="meshA"><matrix>{IDENTITY}</matrix><instance_controller url="#skinShared"><skeleton>#rigA</skeleton></instance_controller></node>
    <node id="meshB" name="meshB"><matrix>{IDENTITY}</matrix><instance_controller url="#skinShared"><skeleton>#rigB</skeleton></instance_controller></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>"""


def _i32_values(buffer: object) -> tuple[int, ...]:
    return tuple(memoryview(buffer).cast("B").cast("i")) if buffer else ()


def _evaluated_centroid_x(obj: bpy.types.Object) -> float:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return sum(float((evaluated.matrix_world @ vertex.co).x) for vertex in mesh.vertices) / len(mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def _assert_instance_skeleton_roots(path: Path, options: object) -> None:
    path.write_text(INSTANCE_SKELETON_FIXTURE, encoding="utf-8")
    loaded = native_load_meshes(os.fspath(path), options)
    if loaded is None or len(loaded.meshes) != 2:
        raise AssertionError("failed to load two instance-specific skeleton roots")
    roots = {
        loaded.nodes[int(primitive.skin_root_node_index)].name
        for primitive in loaded.meshes
        if int(primitive.skin_root_node_index) >= 0
    }
    joint_palette_indices = {
        tuple(_i32_values(primitive.skin_joint_nodes_i32))
        for primitive in loaded.meshes
    }
    joint_palettes = {
        tuple(loaded.nodes[index].name for index in indices)
        for indices in joint_palette_indices
    }
    if (
        roots != {"rigA", "rigB"}
        or len(joint_palette_indices) != 2
        or joint_palettes != {("sharedJoint",)}
    ):
        raise AssertionError(
            "instance_controller skeleton override was shared: "
            f"roots={roots}, joint_indices={joint_palette_indices}, joints={joint_palettes}"
        )

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
    if len(meshes) != 2 or len(armatures) != 2:
        raise AssertionError(
            f"distinct skeleton instances were grouped: meshes={len(meshes)}, armatures={len(armatures)}"
        )
    root_x = sorted(round(float(armature.matrix_world.translation.x), 5) for armature in armatures)
    if root_x != [0.0, 100.0]:
        raise AssertionError(f"armatures used the wrong instance roots: {root_x}")
    expected_names = {
        f"sharedJoint [AssetKit {indices[0]}]"
        for indices in joint_palette_indices
    }
    group_names = {
        group.name
        for mesh in meshes
        for group in mesh.vertex_groups
    }
    bone_names = {
        bone.name
        for armature in armatures
        for bone in armature.data.bones
    }
    if group_names != expected_names or bone_names != expected_names:
        raise AssertionError(
            "duplicate authored joint names were not mapped deterministically: "
            f"expected={expected_names}, groups={group_names}, bones={bone_names}"
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-skin-grouping-") as temp_dir:
        path = Path(temp_dir) / "skin-grouping.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        options = make_load_options(
            coordinate_system="Y_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading="DEFERRED",
        )

        loaded = native_load_meshes(os.fspath(path), options)
        if loaded is None or len(loaded.meshes) != 6:
            count = 0 if loaded is None else len(loaded.meshes)
            raise AssertionError(f"expected six native primitives, got {count}")

        native_runs: dict[tuple[int, tuple[int, ...]], list] = defaultdict(list)
        for primitive in loaded.meshes:
            if not primitive.has_skin or primitive.skin_joint_count != 1:
                raise AssertionError("native primitive lost its one-joint skin")
            native_runs[
                (int(primitive.node_index), _i32_values(primitive.skin_joint_nodes_i32))
            ].append(primitive)
        if len(native_runs) != 3 or sorted(map(len, native_runs.values())) != [2, 2, 2]:
            raise AssertionError(
                f"expected three two-primitive controller runs, got {native_runs}"
            )

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
        meshes = [obj for obj in objects if obj.type == "MESH" and obj.data]
        if len(meshes) != 3:
            raise AssertionError(
                f"distinct controller palettes were grouped: expected 3 meshes, got {len(meshes)}"
            )

        group_counts = Counter()
        armatures = []
        for obj in meshes:
            if len(obj.data.vertices) != 6 or len(obj.data.polygons) != 2:
                raise AssertionError(
                    f"{obj.name}: same-controller primitives were not grouped correctly"
                )
            if len(obj.vertex_groups) != 1:
                raise AssertionError(f"{obj.name}: expected one controller vertex group")
            group_counts[obj.vertex_groups[0].name] += 1
            modifiers = [
                modifier
                for modifier in obj.modifiers
                if modifier.type == "ARMATURE" and modifier.object is not None
            ]
            if len(modifiers) != 1:
                raise AssertionError(f"{obj.name}: expected one connected armature")
            armatures.append(modifiers[0].object)

        if sorted(group_counts.values()) != [1, 2]:
            raise AssertionError(
                f"shared controller or distinct palette was lost: {group_counts}"
            )
        if set(group_counts) != {"jointA", "jointB"}:
            raise AssertionError(
                f"authored joint names were not preserved: {set(group_counts)}"
            )
        if len({armature.as_pointer() for armature in armatures}) != 1:
            raise AssertionError("skins with the same skeleton root did not share an armature")
        bone_names = {bone.name for bone in armatures[0].data.bones}
        if bone_names != set(group_counts):
            raise AssertionError(
                f"armature palette mismatch: bones={bone_names}, groups={set(group_counts)}"
            )
        bone_lengths = [float(bone.length) for bone in armatures[0].data.bones]
        if (
            not bone_lengths
            or max(bone_lengths) > 0.050001
            or max(bone_lengths) - min(bone_lengths) > 1.0e-6
        ):
            raise AssertionError(
                f"rig display bone lengths were not uniformly bounded: {bone_lengths}"
            )

        bpy.context.scene.frame_set(0)
        bpy.context.view_layer.update()
        start_centroids = [_evaluated_centroid_x(obj) for obj in meshes]
        bpy.context.scene.frame_set(24)
        bpy.context.view_layer.update()
        end_centroids = [_evaluated_centroid_x(obj) for obj in meshes]
        deltas = sorted(round(end - start, 5) for start, end in zip(start_centroids, end_centroids))
        if deltas != [0.0, 0.0, 2.0]:
            raise AssertionError(
                f"controller animation affected the wrong grouped meshes: {deltas}"
            )

        _assert_instance_skeleton_roots(
            Path(temp_dir) / "instance-skeleton-roots.dae",
            options,
        )

    print("DAE skin grouping check passed")


if __name__ == "__main__":
    main()
