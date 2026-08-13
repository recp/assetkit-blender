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
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.enums import AK_FILE_TYPE_DAE, AK_FILE_TYPE_GLTF  # noqa: E402
from assetkit_blender.exp.core import export_scene  # noqa: E402
from assetkit_blender.importer import _object_bounds, import_assetkit_file  # noqa: E402
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
        if not obj.get("assetkit_helper_hidden") or not obj.hide_viewport:
            raise AssertionError(f"transform-only hierarchy object {name} is visible")
    hierarchy_instances = [
        obj
        for obj in bpy.data.objects
        if obj.get("assetkit_instance_node")
    ]
    if len(hierarchy_instances) != 3:
        raise AssertionError(
            f"expected 3 explicit hierarchy instances, got {len(hierarchy_instances)}"
        )
    count, minimum, maximum = _evaluated_mesh_bounds()
    if count != 2:
        raise AssertionError(f"expected 2 full-hierarchy mesh instances, got {count}")
    _assert_close(minimum, [11.0, 12.0, 3.0], "full hierarchy minimum")
    _assert_close(maximum, [22.0, 14.0, 3.0], "full hierarchy maximum")
    print("DAE instance_node hierarchy check passed")


if __name__ == "__main__":
    main()
