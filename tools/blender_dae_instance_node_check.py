#!/usr/bin/env python3
"""Check compact COLLADA instance_node import with nested prototypes.

Run inside Blender:

  blender --background --factory-startup \
    --python tools/blender_dae_instance_node_check.py
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_DAE, AK_FILE_TYPE_GLTF  # noqa: E402
from assetkit_blender.exp.core import export_scene  # noqa: E402
from assetkit_blender.importer import (  # noqa: E402
    _object_bounds,
    import_assetkit_file,
    import_assetkit_file_progressive,
)
from assetkit_blender.imp.build.scene import (  # noqa: E402
    _apply_deferred_collection_instances,
    _realize_full_hierarchy_instances,
)
from assetkit_blender.load_options import make_load_options  # noqa: E402
from assetkit_blender.operators import ASSETKIT_OT_import_assetkit  # noqa: E402


FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <unit meter="1" name="meter"/>
    <up_axis>Z_UP</up_axis>
  </asset>
  <library_geometries>
    <geometry id="triangle" name="Shared Triangle">
      <mesh>
        <source id="positions">
          <float_array id="positions-array" count="9">0 0 0  1 0 0  0 2 0</float_array>
          <technique_common>
            <accessor source="#positions-array" count="3" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="vertices">
          <input semantic="POSITION" source="#positions"/>
        </vertices>
        <triangles count="1">
          <input semantic="VERTEX" source="#vertices" offset="0"/>
          <p>0 1 2</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_nodes>
    <node id="leaf" name="Leaf">
      <translate>1 2 3</translate>
      <instance_geometry url="#triangle"/>
    </node>
    <node id="nested" name="Nested">
      <translate>0 10 0</translate>
      <instance_node url="#leaf"/>
    </node>
  </library_nodes>
  <library_visual_scenes>
    <visual_scene id="Scene" name="Scene">
      <node id="instance-a" name="Instance A">
        <translate>10 0 0</translate>
        <instance_node url="#nested"/>
      </node>
      <node id="instance-b" name="Instance B">
        <translate>20 0 0</translate>
        <instance_node url="#nested"/>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <scene>
    <instance_visual_scene url="#Scene"/>
  </scene>
</COLLADA>
"""


ANIMATED_FIXTURE = FIXTURE.replace(
    "<translate>1 2 3</translate>",
    '<translate sid="translate">1 2 3</translate>',
).replace(
    "  <library_visual_scenes>",
    """  <library_animations>
    <animation id="leaf-translate-animation">
      <source id="leaf-translate-input">
        <float_array id="leaf-translate-input-array" count="2">0 1</float_array>
        <technique_common>
          <accessor source="#leaf-translate-input-array" count="2" stride="1">
            <param name="TIME" type="float"/>
          </accessor>
        </technique_common>
      </source>
      <source id="leaf-translate-output">
        <float_array id="leaf-translate-output-array" count="2">1 5</float_array>
        <technique_common>
          <accessor source="#leaf-translate-output-array" count="2" stride="1">
            <param name="X" type="float"/>
          </accessor>
        </technique_common>
      </source>
      <source id="leaf-translate-interpolation">
        <Name_array id="leaf-translate-interpolation-array" count="2">LINEAR LINEAR</Name_array>
        <technique_common>
          <accessor source="#leaf-translate-interpolation-array" count="2" stride="1">
            <param name="INTERPOLATION" type="Name"/>
          </accessor>
        </technique_common>
      </source>
      <sampler id="leaf-translate-sampler">
        <input semantic="INPUT" source="#leaf-translate-input"/>
        <input semantic="OUTPUT" source="#leaf-translate-output"/>
        <input semantic="INTERPOLATION" source="#leaf-translate-interpolation"/>
      </sampler>
      <channel source="#leaf-translate-sampler" target="leaf/translate.X"/>
    </animation>
  </library_animations>
  <library_visual_scenes>""",
)


def _assert_close(actual: list[float], expected: list[float], label: str) -> None:
    for value, wanted in zip(actual, expected):
        if not math.isclose(value, wanted, rel_tol=1.0e-6, abs_tol=1.0e-6):
            raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _evaluated_mesh_bounds() -> tuple[int, list[float], list[float]]:
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    count = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for instance in depsgraph.object_instances:
        obj = instance.object
        if (
            obj.type != "MESH"
            or obj.data is None
            or len(obj.data.polygons) == 0
        ):
            continue
        count += 1
        for vertex in obj.data.vertices:
            world = instance.matrix_world @ Vector(vertex.co)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world[axis])
                maximum[axis] = max(maximum[axis], world[axis])
    return count, minimum, maximum


def _evaluated_mesh_origin_x() -> list[float]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return sorted(
        float(instance.matrix_world.translation.x)
        for instance in depsgraph.object_instances
        if (
            instance.object.type == "MESH"
            and instance.object.data is not None
            and len(instance.object.data.polygons) > 0
        )
    )


def _add_object_reference_bundle(
    owner: bpy.types.Object,
    target: bpy.types.Object,
) -> None:
    owner["assetkit_cross_reference"] = target
    constraint = owner.constraints.new("COPY_LOCATION")
    constraint.name = "Hierarchy Cross Constraint"
    constraint.target = target
    constraint.influence = 0.0
    owner["assetkit_cross_driven_value"] = 0.0
    target["assetkit_cross_source_value"] = 3.0
    driver_curve = owner.driver_add('["assetkit_cross_driven_value"]')
    driver = driver_curve.driver
    driver.type = "SCRIPTED"
    driver.expression = "source_value"
    variable = driver.variables.new()
    variable.name = "source_value"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id = target
    variable.targets[0].data_path = '["assetkit_cross_source_value"]'


def _realized_occurrence_root(obj: bpy.types.Object) -> bpy.types.Object | None:
    current = obj
    while current.parent is not None:
        if current.get("assetkit_instance_realized"):
            return current
        current = current.parent
    return current if current.get("assetkit_instance_realized") else None


def main() -> None:
    bpy.utils.register_class(ASSETKIT_OT_import_assetkit)
    try:
        hierarchy_property = bpy.ops.assetkit.import_assetkit.get_rna_type().properties[
            "hierarchy_mode"
        ]
        if hierarchy_property.default != "FULL":
            raise AssertionError(
                "interactive imports must preserve the full source hierarchy by default"
            )
    finally:
        bpy.utils.unregister_class(ASSETKIT_OT_import_assetkit)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    with tempfile.TemporaryDirectory(prefix="assetkit-dae-instance-node-") as temp_dir:
        path = Path(temp_dir) / "nested-instance-node.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        imported = import_assetkit_file(
            str(path),
            load_options=make_load_options(
                coordinate_system="Z_UP",
                coordinate_conversion="TRANSFORM",
                texture_loading="DEFERRED",
            ),
            collection=bpy.context.collection,
            focus_mode="NEVER",
            placement_mode="AS_AUTHORED",
            select_imported=False,
            set_viewport_shading=False,
            clean_viewport_overlays=False,
        )
        bpy.context.view_layer.update()

    prototypes = [
        collection
        for collection in bpy.data.collections
        if collection.get("assetkit_prototype_root_index") is not None
    ]
    instancers = [
        obj
        for obj in bpy.data.objects
        if obj.get("assetkit_instance_node")
    ]
    batches = [
        obj
        for obj in bpy.data.objects
        if obj.get("assetkit_compact_instance_batch")
    ]
    imported_batches = [
        obj
        for obj in imported
        if obj.get("assetkit_compact_instance_batch")
    ]
    if len(prototypes) != 2:
        raise AssertionError(f"expected 2 prototype collections, got {len(prototypes)}")
    surface_meshes = [mesh for mesh in bpy.data.meshes if len(mesh.polygons) > 0]
    batch_carriers = [
        mesh
        for mesh in bpy.data.meshes
        if mesh.get("assetkit_compact_instance_batch")
        or any(
            obj.data == mesh and obj.get("assetkit_compact_instance_batch")
            for obj in bpy.data.objects
        )
    ]
    if len(surface_meshes) != 1:
        raise AssertionError(
            f"expected 1 source surface mesh datablock, got {len(surface_meshes)}"
        )
    if len(batch_carriers) != 1:
        raise AssertionError(
            f"expected 1 compact point-carrier mesh, got {len(batch_carriers)}"
        )
    if len(instancers) != 1:
        raise AssertionError(
            f"expected 1 residual nested collection instancer, got {len(instancers)}"
        )
    if len(batches) != 1 or int(batches[0].get("assetkit_instance_count", 0)) != 2:
        raise AssertionError(
            "expected one compact batch containing the 2 top-level instances"
        )
    if len(imported_batches) != 1:
        raise AssertionError(
            f"expected the top-level batch in imported roots, got {len(imported_batches)}"
        )

    count, minimum, maximum = _evaluated_mesh_bounds()
    if count != 2:
        raise AssertionError(f"expected 2 evaluated mesh instances, got {count}")
    _assert_close(minimum, [11.0, 12.0, 3.0], "evaluated minimum")
    _assert_close(maximum, [22.0, 14.0, 3.0], "evaluated maximum")
    imported_bounds = _object_bounds(imported)
    if imported_bounds is None:
        raise AssertionError("expected imported collection instances to have bounds")
    _assert_close(list(imported_bounds[0]), [11.0, 12.0, 3.0], "imported minimum")
    _assert_close(list(imported_bounds[1]), [22.0, 14.0, 3.0], "imported maximum")

    with tempfile.TemporaryDirectory(prefix="assetkit-dae-instance-export-") as temp_dir:
        output_paths = []
        for file_type, suffix in (
            (AK_FILE_TYPE_GLTF, "gltf"),
            (AK_FILE_TYPE_DAE, "dae"),
        ):
            for apply_modifiers in (False, True):
                mode = "apply" if apply_modifiers else "raw"
                output = Path(temp_dir) / f"instance-{mode}.{suffix}"
                result = export_scene(
                    bpy.context,
                    output,
                    file_type,
                    apply_modifiers=apply_modifiers,
                )
                if result < 0 or not output.is_file():
                    raise AssertionError(
                        f"compact instance {suffix} export failed "
                        f"with apply_modifiers={apply_modifiers}"
                    )
                output_paths.append(output)

        previous_mode = os.environ.get("ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES")
        os.environ["ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES"] = "0"
        try:
            for output in output_paths:
                bpy.ops.wm.read_factory_settings(use_empty=True)
                import_assetkit_file(
                    str(output),
                    load_options=make_load_options(
                        coordinate_system="Z_UP",
                        coordinate_conversion="TRANSFORM",
                        texture_loading="DEFERRED",
                    ),
                    collection=bpy.context.collection,
                    focus_mode="NEVER",
                    placement_mode="AS_AUTHORED",
                    select_imported=False,
                    set_viewport_shading=False,
                    clean_viewport_overlays=False,
                )
                bpy.context.view_layer.update()
                count, minimum, maximum = _evaluated_mesh_bounds()
                if count != 2:
                    raise AssertionError(
                        f"{output.name}: expected 2 reimported mesh instances, got {count}"
                    )
                _assert_close(minimum, [11.0, 12.0, 3.0], f"{output.name} minimum")
                _assert_close(maximum, [22.0, 14.0, 3.0], f"{output.name} maximum")
        finally:
            if previous_mode is None:
                os.environ.pop("ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES", None)
            else:
                os.environ["ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES"] = previous_mode

    with tempfile.TemporaryDirectory(prefix="assetkit-dae-full-hierarchy-") as temp_dir:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path = Path(temp_dir) / "nested-instance-node.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        import_assetkit_file(
            str(path),
            load_options=make_load_options(
                coordinate_system="Z_UP",
                coordinate_conversion="TRANSFORM",
                texture_loading="DEFERRED",
            ),
            collection=bpy.context.collection,
            focus_mode="NEVER",
            placement_mode="AS_AUTHORED",
            select_imported=False,
            set_viewport_shading=False,
            clean_viewport_overlays=False,
            preserve_hierarchy=True,
        )
        bpy.context.view_layer.update()

    if any(
        obj.get("assetkit_compact_instance_batch")
        for obj in bpy.data.objects
    ):
        raise AssertionError("full hierarchy import unexpectedly created a compact batch")
    for name in ("Instance A", "Instance B"):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.parent is None or obj.parent.name != "AssetKit Node":
            raise AssertionError(f"missing authored hierarchy object {name}")
        if obj.get("assetkit_helper_hidden") or obj.hide_viewport or obj.hide_get():
            raise AssertionError(f"authored hierarchy object {name} is unexpectedly hidden")
    active_objects = list(bpy.context.view_layer.objects)
    collection_instances = [
        obj
        for obj in active_objects
        if obj.instance_type == "COLLECTION"
    ]
    if collection_instances:
        raise AssertionError(
            "full hierarchy import left non-expandable collection instances: "
            + ", ".join(obj.name for obj in collection_instances)
        )
    realized_roots = [
        obj
        for obj in active_objects
        if obj.get("assetkit_instance_realized")
    ]
    if len(realized_roots) != 2:
        raise AssertionError(
            f"expected 2 realized top-level instances, got {len(realized_roots)}"
        )
    active_surface_meshes = [
        obj
        for obj in active_objects
        if obj.type == "MESH" and len(obj.data.polygons) > 0
    ]
    if len(active_surface_meshes) != 2:
        raise AssertionError(
            f"expected 2 editable mesh objects, got {len(active_surface_meshes)}"
        )
    if len({obj.data.as_pointer() for obj in active_surface_meshes}) != 1:
        raise AssertionError("full hierarchy duplicated rather than shared mesh data")
    for obj in active_surface_meshes:
        if obj.parent is None:
            raise AssertionError(f"editable mesh {obj.name} is missing its source parent")
    count, minimum, maximum = _evaluated_mesh_bounds()
    if count != 2:
        raise AssertionError(f"expected 2 full-hierarchy mesh instances, got {count}")
    _assert_close(minimum, [11.0, 12.0, 3.0], "full hierarchy minimum")
    _assert_close(maximum, [22.0, 14.0, 3.0], "full hierarchy maximum")

    with tempfile.TemporaryDirectory(
        prefix="assetkit-dae-animated-full-hierarchy-"
    ) as temp_dir:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path = Path(temp_dir) / "animated-instance-node.dae"
        path.write_text(ANIMATED_FIXTURE, encoding="utf-8")
        import_assetkit_file(
            str(path),
            load_options=make_load_options(
                coordinate_system="Z_UP",
                coordinate_conversion="TRANSFORM",
                texture_loading="DEFERRED",
            ),
            collection=bpy.context.collection,
            focus_mode="NEVER",
            placement_mode="AS_AUTHORED",
            select_imported=False,
            set_viewport_shading=False,
            clean_viewport_overlays=False,
            preserve_hierarchy=True,
        )
        bpy.context.view_layer.update()

    if any(
        obj.instance_type == "COLLECTION"
        for obj in bpy.context.view_layer.objects
    ):
        raise AssertionError(
            "animated full hierarchy left non-editable collection instances"
        )
    for frame, expected in (
        (0, [11.0, 21.0]),
        (12, [13.0, 23.0]),
        (24, [15.0, 25.0]),
    ):
        bpy.context.scene.frame_set(frame)
        actual = _evaluated_mesh_origin_x()
        if len(actual) != 2:
            raise AssertionError(
                f"animated full hierarchy frame {frame}: "
                f"expected 2 meshes, got {len(actual)}"
            )
        _assert_close(actual, expected, f"animated full hierarchy frame {frame}")

    prototype = bpy.data.collections.new("Hierarchy Skin Prototype")
    armature_data = bpy.data.armatures.new("Hierarchy Skin Armature")
    armature = bpy.data.objects.new("Hierarchy Skin Armature", armature_data)
    mesh_data = bpy.data.meshes.new("Hierarchy Skin Mesh")
    mesh_data.vertices.add(1)
    mesh = bpy.data.objects.new("Hierarchy Skin Mesh", mesh_data)
    mesh.shape_key_add(name="Basis")
    morph = mesh.shape_key_add(name="Hierarchy Morph")
    morph.data[0].co.x = 1.0
    morph.value = 0.0
    morph.keyframe_insert(data_path="value", frame=0)
    morph.value = 1.0
    morph.keyframe_insert(data_path="value", frame=24)
    morph.value = 0.0
    modifier = mesh.modifiers.new("Hierarchy Skin", "ARMATURE")
    modifier.object = armature
    mesh.parent = armature
    constraint_target = bpy.data.objects.new("Hierarchy Constraint Target", None)
    constraint_target["assetkit_test_role"] = "constraint_target"
    constraint = mesh.constraints.new("COPY_LOCATION")
    constraint.name = "Hierarchy Constraint"
    constraint.target = constraint_target
    constraint.influence = 0.0
    armature["assetkit_test_role"] = "animated_armature"
    armature["assetkit_object_reference"] = constraint_target
    armature["assetkit_driven_value"] = 0.0
    driver_curve = armature.driver_add('["assetkit_driven_value"]')
    driver = driver_curve.driver
    driver.type = "SCRIPTED"
    driver.expression = "source_value"
    variable = driver.variables.new()
    variable.name = "source_value"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id = constraint_target
    variable.targets[0].data_path = '["assetkit_driver_value"]'
    constraint_target["assetkit_driver_value"] = 3.0
    armature.location.x = 0.0
    armature.keyframe_insert(data_path="location", index=0, frame=0)
    armature.location.x = 2.0
    armature.keyframe_insert(data_path="location", index=0, frame=24)
    armature.location.x = 0.0
    bpy.context.scene.frame_set(0)
    prototype.objects.link(armature)
    prototype.objects.link(mesh)
    prototype.objects.link(constraint_target)
    prototype.instance_offset.x = 2.0
    instances = []
    for label, x in (("A", 2.0), ("B", 12.0)):
        instance = bpy.data.objects.new(f"Hierarchy Skin Instance {label}", None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = prototype
        instance["assetkit_instance_node"] = True
        instance.location.x = x
        bpy.context.scene.collection.objects.link(instance)
        instances.append(instance)
    bpy.context.view_layer.update()
    state = SimpleNamespace(
        preserve_hierarchy=True,
        node_data={
            index: SimpleNamespace(prototype_root_index=-1)
            for index in range(len(instances))
        },
        node_objects=dict(enumerate(instances)),
        realized_instance_objects=[],
    )
    _realize_full_hierarchy_instances(state)
    bpy.context.view_layer.update()
    active_objects = list(bpy.context.view_layer.objects)
    realized_armatures = [obj for obj in active_objects if obj.data == armature_data]
    realized_meshes = [obj for obj in active_objects if obj.data == mesh_data]
    if len(realized_armatures) != 2 or len(realized_meshes) != 2:
        raise AssertionError("full hierarchy did not realize both skinned prototypes")
    realized_constraint_targets = [
        obj
        for obj in active_objects
        if obj.get("assetkit_test_role") == "constraint_target"
    ]
    if len(realized_constraint_targets) != 2:
        raise AssertionError(
            "full hierarchy did not realize both constraint targets"
        )
    for realized_mesh in realized_meshes:
        realized_armature = realized_mesh.parent
        if realized_armature not in realized_armatures:
            raise AssertionError(
                "full hierarchy did not preserve the skin object hierarchy"
            )
        realized_modifier = realized_mesh.modifiers.get("Hierarchy Skin")
        if realized_modifier is None or realized_modifier.object is not realized_armature:
            raise AssertionError(
                "full hierarchy did not remap the skin armature reference"
            )
        realized_constraint = realized_mesh.constraints.get("Hierarchy Constraint")
        realized_constraint_target = (
            realized_constraint.target
            if realized_constraint is not None
            else None
        )
        if (
            realized_constraint_target not in realized_constraint_targets
            or realized_constraint_target.parent is not realized_armature.parent
        ):
            raise AssertionError(
                "full hierarchy did not remap the per-instance constraint target"
            )
        if (
            realized_armature.get("assetkit_object_reference")
            is not realized_constraint_target
        ):
            raise AssertionError(
                "full hierarchy did not remap the per-instance object ID property"
            )
        if (
            realized_armature.animation_data is None
            or realized_armature.animation_data.action is None
        ):
            raise AssertionError("full hierarchy discarded object transform animation")
        realized_drivers = [
            curve
            for curve in realized_armature.animation_data.drivers
            if curve.data_path == '["assetkit_driven_value"]'
        ]
        if len(realized_drivers) != 1:
            raise AssertionError("full hierarchy discarded the object driver")
        realized_driver_target = (
            realized_drivers[0].driver.variables[0].targets[0].id
        )
        if realized_driver_target is not realized_constraint_target:
            raise AssertionError(
                "full hierarchy did not remap the per-instance object driver target"
            )
    shape_keys = realized_meshes[0].data.shape_keys
    realized_morph = (
        shape_keys.key_blocks.get("Hierarchy Morph")
        if shape_keys is not None
        else None
    )
    if (
        realized_morph is None
        or shape_keys.animation_data is None
        or shape_keys.animation_data.action is None
    ):
        raise AssertionError("full hierarchy discarded the shared morph animation")
    for frame, expected_x in ((0, 0.0), (12, 1.0), (24, 2.0)):
        bpy.context.scene.frame_set(frame)
        actual_world_x = sorted(
            float(realized_armature.matrix_world.translation.x)
            for realized_armature in realized_armatures
        )
        _assert_close(
            actual_world_x,
            [expected_x, expected_x + 10.0],
            f"full hierarchy armature animation frame {frame}",
        )
        expected_morph = expected_x * 0.5
        if not math.isclose(
            float(realized_morph.value),
            expected_morph,
            rel_tol=1.0e-6,
            abs_tol=1.0e-6,
        ):
            raise AssertionError(
                f"full hierarchy morph animation frame {frame}: "
                f"expected {expected_morph}, got {realized_morph.value}"
            )

    inner_prototype = bpy.data.collections.new("Hierarchy Inner Prototype")
    inner_target = bpy.data.objects.new("Hierarchy Inner Target", None)
    inner_target["assetkit_cross_role"] = "inner_target"
    inner_referrer = bpy.data.objects.new("Hierarchy Inner Referrer", None)
    inner_referrer["assetkit_cross_role"] = "inner_referrer"
    inner_prototype.objects.link(inner_target)
    inner_prototype.objects.link(inner_referrer)

    outer_prototype = bpy.data.collections.new("Hierarchy Outer Prototype")
    outer_target = bpy.data.objects.new("Hierarchy Outer Target", None)
    outer_target["assetkit_cross_role"] = "outer_target"
    outer_referrer = bpy.data.objects.new("Hierarchy Outer Referrer", None)
    outer_referrer["assetkit_cross_role"] = "outer_referrer"
    nested_instancer = bpy.data.objects.new("Hierarchy Nested Instance", None)
    nested_instancer.instance_type = "COLLECTION"
    nested_instancer.instance_collection = inner_prototype
    nested_instancer["assetkit_instance_node"] = True
    outer_prototype.objects.link(outer_target)
    outer_prototype.objects.link(outer_referrer)
    outer_prototype.objects.link(nested_instancer)

    _add_object_reference_bundle(outer_referrer, inner_target)
    _add_object_reference_bundle(inner_referrer, outer_target)

    outer_instances = []
    for label, x in (("A", 0.0), ("B", 20.0)):
        instance = bpy.data.objects.new(f"Hierarchy Outer Instance {label}", None)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = outer_prototype
        instance["assetkit_instance_node"] = True
        instance.location.x = x
        bpy.context.scene.collection.objects.link(instance)
        outer_instances.append(instance)
    bpy.context.view_layer.update()
    cross_level_state = SimpleNamespace(
        preserve_hierarchy=True,
        node_data={
            index: SimpleNamespace(prototype_root_index=-1)
            for index in range(len(outer_instances))
        },
        node_objects=dict(enumerate(outer_instances)),
        realized_instance_objects=[],
    )
    _realize_full_hierarchy_instances(cross_level_state)
    bpy.context.view_layer.update()

    cross_objects_by_role: dict[str, list[bpy.types.Object]] = {}
    for obj in bpy.context.view_layer.objects:
        role = obj.get("assetkit_cross_role")
        if role:
            cross_objects_by_role.setdefault(str(role), []).append(obj)
    expected_roles = {
        "outer_target",
        "outer_referrer",
        "inner_target",
        "inner_referrer",
    }
    for role in expected_roles:
        count = len(cross_objects_by_role.get(role, []))
        if count != 2:
            raise AssertionError(
                f"full hierarchy expected 2 realized {role} objects, got {count}"
            )

    targets_by_role_and_root = {
        (
            role,
            _realized_occurrence_root(obj).as_pointer(),
        ): obj
        for role in ("outer_target", "inner_target")
        for obj in cross_objects_by_role[role]
    }
    for owner_role, target_role in (
        ("outer_referrer", "inner_target"),
        ("inner_referrer", "outer_target"),
    ):
        for owner in cross_objects_by_role[owner_role]:
            occurrence_root = _realized_occurrence_root(owner)
            if occurrence_root is None:
                raise AssertionError(
                    f"full hierarchy {owner_role} is missing its occurrence root"
                )
            expected_target = targets_by_role_and_root.get(
                (target_role, occurrence_root.as_pointer())
            )
            if expected_target is None:
                raise AssertionError(
                    f"full hierarchy {owner_role} has no occurrence-local {target_role}"
                )
            if owner.get("assetkit_cross_reference") is not expected_target:
                raise AssertionError(
                    f"full hierarchy did not remap {owner_role} ID property "
                    f"to its occurrence-local {target_role}"
                )
            constraint = owner.constraints.get("Hierarchy Cross Constraint")
            if constraint is None or constraint.target is not expected_target:
                raise AssertionError(
                    f"full hierarchy did not remap {owner_role} constraint "
                    f"to its occurrence-local {target_role}"
                )
            drivers = [
                curve
                for curve in owner.animation_data.drivers
                if curve.data_path == '["assetkit_cross_driven_value"]'
            ] if owner.animation_data is not None else []
            if len(drivers) != 1:
                raise AssertionError(
                    f"full hierarchy discarded the {owner_role} driver"
                )
            driver_target = drivers[0].driver.variables[0].targets[0].id
            if driver_target is not expected_target:
                raise AssertionError(
                    f"full hierarchy did not remap {owner_role} driver "
                    f"to its occurrence-local {target_role}"
                )

    repeated_inner = bpy.data.collections.new("Hierarchy Repeated Inner")
    repeated_target = bpy.data.objects.new("Hierarchy Repeated Target", None)
    repeated_inner.objects.link(repeated_target)
    repeated_outer = bpy.data.collections.new("Hierarchy Repeated Outer")
    ambiguous_owner = bpy.data.objects.new("Hierarchy Ambiguous Owner", None)
    repeated_outer.objects.link(ambiguous_owner)
    _add_object_reference_bundle(ambiguous_owner, repeated_target)
    repeated_nested = []
    for label in ("A", "B"):
        nested = bpy.data.objects.new(f"Hierarchy Repeated Nested {label}", None)
        nested.instance_type = "COLLECTION"
        nested.instance_collection = repeated_inner
        nested["assetkit_instance_node"] = True
        repeated_outer.objects.link(nested)
        repeated_nested.append(nested)
    ambiguous_root = bpy.data.objects.new("Hierarchy Ambiguous Root", None)
    ambiguous_root.instance_type = "COLLECTION"
    ambiguous_root.instance_collection = repeated_outer
    ambiguous_root["assetkit_instance_node"] = True
    bpy.context.scene.collection.objects.link(ambiguous_root)
    bpy.context.view_layer.update()
    ambiguous_state = SimpleNamespace(
        preserve_hierarchy=True,
        node_data={0: SimpleNamespace(prototype_root_index=-1)},
        node_objects={0: ambiguous_root},
        realized_instance_objects=[],
    )
    objects_before_ambiguity = {
        obj.as_pointer()
        for obj in bpy.data.objects
    }
    try:
        _realize_full_hierarchy_instances(ambiguous_state)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "full hierarchy accepted an ambiguous repeated-descendant reference"
        )
    objects_after_ambiguity = {
        obj.as_pointer()
        for obj in bpy.data.objects
    }
    if objects_after_ambiguity != objects_before_ambiguity:
        raise AssertionError(
            "ambiguous repeated-descendant rollback leaked realized object copies"
        )
    if (
        ambiguous_root.instance_type != "COLLECTION"
        or ambiguous_root.instance_collection is not repeated_outer
        or ambiguous_root.get("assetkit_instance_realized")
        or ambiguous_state.realized_instance_objects
    ):
        raise AssertionError(
            "ambiguous repeated-descendant rollback mutated the root instance"
        )
    if any(
        nested.instance_type != "COLLECTION"
        or nested.instance_collection is not repeated_inner
        for nested in repeated_nested
    ):
        raise AssertionError(
            "ambiguous repeated-descendant rollback mutated a nested source instance"
        )
    ambiguous_constraint = ambiguous_owner.constraints.get(
        "Hierarchy Cross Constraint"
    )
    ambiguous_drivers = [
        curve
        for curve in ambiguous_owner.animation_data.drivers
        if curve.data_path == '["assetkit_cross_driven_value"]'
    ] if ambiguous_owner.animation_data is not None else []
    if (
        ambiguous_owner.get("assetkit_cross_reference") is not repeated_target
        or ambiguous_constraint is None
        or ambiguous_constraint.target is not repeated_target
        or len(ambiguous_drivers) != 1
        or ambiguous_drivers[0].driver.variables[0].targets[0].id
        is not repeated_target
    ):
        raise AssertionError(
            "ambiguous repeated-descendant rollback mutated source references"
        )

    cycle_a = bpy.data.collections.new("Hierarchy Cycle A")
    cycle_b = bpy.data.collections.new("Hierarchy Cycle B")
    cycle_a_to_b = bpy.data.objects.new("Hierarchy Cycle A to B", None)
    cycle_a.objects.link(cycle_a_to_b)
    cycle_b_to_a = bpy.data.objects.new("Hierarchy Cycle B to A", None)
    cycle_b.objects.link(cycle_b_to_a)
    cycle_instance = bpy.data.objects.new("Hierarchy Cycle Instance", None)
    cycle_instance["assetkit_instance_node"] = True
    bpy.context.scene.collection.objects.link(cycle_instance)
    deferred_cycle_state = SimpleNamespace(
        deferred_collection_instances=[
            (cycle_a_to_b, cycle_b),
            (cycle_b_to_a, cycle_a),
            (cycle_instance, cycle_a),
        ],
    )
    objects_before_cycle = {
        obj.as_pointer()
        for obj in bpy.data.objects
    }
    try:
        _apply_deferred_collection_instances(deferred_cycle_state)
    except RuntimeError:
        pass
    else:
        raise AssertionError("deferred instances accepted a cyclic hierarchy")
    objects_after_cycle = {
        obj.as_pointer()
        for obj in bpy.data.objects
    }
    if objects_after_cycle != objects_before_cycle:
        raise AssertionError("cyclic hierarchy preflight left partial object copies")
    if (
        cycle_instance.instance_type != "NONE"
        or cycle_instance.instance_collection is not None
        or cycle_a_to_b.instance_type != "NONE"
        or cycle_a_to_b.instance_collection is not None
        or cycle_b_to_a.instance_type != "NONE"
        or cycle_b_to_a.instance_collection is not None
        or len(deferred_cycle_state.deferred_collection_instances) != 3
    ):
        raise AssertionError("cyclic hierarchy preflight assigned a deferred instance")

    with tempfile.TemporaryDirectory(prefix="assetkit-dae-progressive-hierarchy-") as temp_dir:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path = Path(temp_dir) / "nested-instance-node.dae"
        path.write_text(FIXTURE, encoding="utf-8")
        completed = []
        errors = []
        job = import_assetkit_file_progressive(
            str(path),
            load_options=make_load_options(
                coordinate_system="Z_UP",
                coordinate_conversion="TRANSFORM",
                texture_loading="DEFERRED",
            ),
            collection=bpy.context.collection,
            focus_mode="NEVER",
            placement_mode="AS_AUTHORED",
            select_imported=False,
            set_viewport_shading=False,
            clean_viewport_overlays=False,
            preserve_hierarchy=True,
            on_complete=completed.append,
            on_error=errors.append,
        )
        try:
            if bpy.app.timers.is_registered(job._timer):
                bpy.app.timers.unregister(job._timer)
        except ValueError:
            pass
        deadline = time.monotonic() + 10.0
        while not job.done and time.monotonic() < deadline:
            job._timer()
        if not job.done or errors or not completed:
            raise AssertionError(
                f"progressive full hierarchy failed: done={job.done} errors={errors}"
            )
        bpy.context.view_layer.update()
        active_objects = list(bpy.context.view_layer.objects)
        import_collection = bpy.data.collections.get(path.stem)
        if (
            import_collection is None
            or bpy.context.scene.collection.children.get(path.stem) is not import_collection
            or bpy.data.collections.get("AssetKit Import") is not None
        ):
            raise AssertionError(
                "progressive import did not publish the source filename collection"
            )
        if any(obj.instance_type == "COLLECTION" for obj in active_objects):
            raise AssertionError("progressive full hierarchy left collection instances")
        if len([obj for obj in active_objects if obj.type == "MESH"]) != 2:
            raise AssertionError("progressive full hierarchy did not expose two meshes")
        blend_path = Path(temp_dir) / "full-hierarchy.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        bpy.context.view_layer.update()
        active_objects = list(bpy.context.view_layer.objects)
        if bpy.context.scene.collection.children.get(path.stem) is None:
            raise AssertionError("saved full hierarchy lost its source filename collection")
        if any(obj.instance_type == "COLLECTION" for obj in active_objects):
            raise AssertionError("saved full hierarchy restored collection instances")
        if len([obj for obj in active_objects if obj.type == "MESH"]) != 2:
            raise AssertionError("saved full hierarchy lost editable meshes")
    print("DAE instance_node hierarchy check passed")


if __name__ == "__main__":
    main()
