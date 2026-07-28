"""Profile and validate an AssetKit DAE import in background Blender.

The optional compact path is selected with:
  ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES=1 blender ... -- model.dae
"""

from __future__ import annotations

import json
import hashlib
import os
import pickle
import struct
import sys
import time
import zlib
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if not args:
        raise SystemExit("expected a DAE path after --")
    path = Path(args[0]).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"missing DAE: {path}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    started_at = time.perf_counter()
    imported = import_assetkit_file(
        os.fspath(path),
        load_options=make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="TRANSFORM",
            texture_loading="DEFERRED",
        ),
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        select_imported=False,
        shading_mode="AS_IS",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
        fit_timeline=False,
    )
    imported_at = time.perf_counter()

    update_started_at = time.perf_counter()
    bpy.context.view_layer.update()
    updated_at = time.perf_counter()

    evaluated_faces = 0
    evaluated_mesh_instances = 0
    evaluated_surface_instances = 0
    transform_sums = [0.0] * 16
    transform_compensation = [0.0] * 16
    transform_multisets = {
        1: [0, 0],
        10: [0, 0],
        100: [0, 0],
        1_000: [0, 0],
    }
    matrix_multisets = {
        1: [0, 0],
        10: [0, 0],
        100: [0, 0],
        1_000: [0, 0],
    }
    counter_path = os.environ.get("ASSETKIT_TRANSFORM_COUNTER_PATH")
    record_path = os.environ.get("ASSETKIT_TRANSFORM_RECORD_PATH")
    transform_records = bytearray() if record_path else None
    transform_record_names = {} if record_path else None
    transform_counters = (
        {scale: Counter() for scale in transform_multisets}
        if counter_path
        else None
    )
    geometry_multiset = [0, 0]
    digest_mask = (1 << 128) - 1
    world_minimum = [float("inf")] * 3
    world_maximum = [float("-inf")] * 3
    trace_object_name = os.environ.get("ASSETKIT_TRACE_OBJECT_NAME")
    traced_instances = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluation_started_at = time.perf_counter()
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type != "MESH" or obj.data is None:
            continue
        if (
            trace_object_name
            and obj.original.name == trace_object_name
            and len(traced_instances) < 32
        ):
            parent = instance.parent
            parent_original = parent.original if parent is not None else None
            traced_instances.append(
                {
                    "persistent_id": list(instance.persistent_id),
                    "parent": parent_original.name if parent_original else None,
                    "parent_source_node_index": int(
                        parent_original.get("assetkit_source_node_index", -1)
                    )
                    if parent_original
                    else -1,
                    "parent_batch_target": int(
                        parent_original.get("assetkit_instance_target_index", -1)
                    )
                    if parent_original
                    else -1,
                    "translation": [
                        float(instance.matrix_world[row][3]) for row in range(3)
                    ],
                }
            )
        evaluated_mesh_instances += 1
        face_count = len(obj.data.polygons)
        evaluated_faces += face_count
        if face_count <= 0:
            continue
        evaluated_surface_instances += 1
        mesh_name_hash = zlib.crc32(obj.data.name.encode("utf-8")) & 0xFFFFFFFF
        weight = (
            1.0
            + float(face_count)
            + float(len(obj.data.vertices)) * 1.0e-4
            + float(mesh_name_hash) * 1.0e-12
        )
        matrix = instance.matrix_world
        for row in range(4):
            for column in range(4):
                offset = row * 4 + column
                value = float(matrix[row][column]) * weight
                corrected = value - transform_compensation[offset]
                updated = transform_sums[offset] + corrected
                transform_compensation[offset] = (
                    updated - transform_sums[offset]
                ) - corrected
                transform_sums[offset] = updated
        matrix_values = [
            float(matrix[row][column])
            for row in range(4)
            for column in range(4)
        ]
        mesh_identity = (
            f"{obj.data.name}\0{len(obj.data.vertices)}\0{face_count}\0"
        ).encode("utf-8")
        geometry_digest = int.from_bytes(
            hashlib.blake2b(mesh_identity, digest_size=16).digest(),
            "little",
        )
        if transform_records is not None:
            transform_records.extend(
                struct.pack(
                    "<16s16f",
                    geometry_digest.to_bytes(16, "little"),
                    *matrix_values,
                )
            )
            transform_record_names[geometry_digest.to_bytes(16, "little").hex()] = {
                "name": obj.data.name,
                "object_name": obj.original.name,
                "source_node_index": int(
                    obj.original.get("assetkit_node_index", -1)
                ),
                "vertices": len(obj.data.vertices),
                "faces": face_count,
            }
        geometry_multiset[0] = (geometry_multiset[0] + geometry_digest) & digest_mask
        geometry_multiset[1] ^= geometry_digest
        for scale, multiset in transform_multisets.items():
            quantized = struct.pack(
                "<16q",
                *(round(value * scale) for value in matrix_values),
            )
            matrix_digest = int.from_bytes(
                hashlib.blake2b(quantized, digest_size=16).digest(),
                "little",
            )
            matrix_multiset = matrix_multisets[scale]
            matrix_multiset[0] = (
                matrix_multiset[0] + matrix_digest
            ) & digest_mask
            matrix_multiset[1] ^= matrix_digest
            digest = int.from_bytes(
                hashlib.blake2b(
                    mesh_identity + quantized,
                    digest_size=16,
                ).digest(),
                "little",
            )
            multiset[0] = (multiset[0] + digest) & digest_mask
            multiset[1] ^= digest
            if transform_counters is not None:
                transform_counters[scale][digest] += 1
        for corner in obj.bound_box:
            world = matrix @ Vector(corner)
            for axis in range(3):
                world_minimum[axis] = min(world_minimum[axis], float(world[axis]))
                world_maximum[axis] = max(world_maximum[axis], float(world[axis]))
    evaluated_at = time.perf_counter()

    batches = [
        obj for obj in bpy.data.objects if obj.get("assetkit_compact_instance_batch")
    ]
    residual_instances = [
        obj
        for obj in bpy.data.objects
        if obj.get("assetkit_instance_node")
        and not obj.get("assetkit_compact_instance_batch")
    ]
    traced_prototype_objects = []
    trace_prototype_root = os.environ.get("ASSETKIT_TRACE_PROTOTYPE_ROOT")
    if trace_prototype_root:
        root_index = int(trace_prototype_root)
        prototype = next(
            (
                collection
                for collection in bpy.data.collections
                if int(collection.get("assetkit_prototype_root_index", -1))
                == root_index
            ),
            None,
        )
        if prototype is not None:
            for obj in prototype.objects:
                target = int(obj.get("assetkit_instance_target_index", -1))
                if target < 0:
                    continue
                if obj.get("assetkit_compact_instance_batch"):
                    source_attr = obj.data.attributes.get(
                        "assetkit_source_node_index"
                    )
                    matrix_attr = obj.data.attributes.get(
                        "assetkit_instance_matrix"
                    )
                    source_indices = [0] * (
                        len(source_attr.data) if source_attr else 0
                    )
                    if source_attr is not None and source_indices:
                        source_attr.data.foreach_get("value", source_indices)
                    matrix_values = [0.0] * (
                        len(matrix_attr.data) * 16 if matrix_attr else 0
                    )
                    if matrix_attr is not None and matrix_values:
                        matrix_attr.data.foreach_get("value", matrix_values)
                    traced_prototype_objects.append(
                        {
                            "name": obj.name,
                            "target": target,
                            "batch": True,
                            "source_node_indices": source_indices[:32],
                            "matrices": [
                                matrix_values[offset : offset + 16]
                                for offset in range(
                                    0,
                                    min(len(matrix_values), 32 * 16),
                                    16,
                                )
                            ],
                        }
                    )
                elif len(traced_prototype_objects) < 32:
                    traced_prototype_objects.append(
                        {
                            "name": obj.name,
                            "target": target,
                            "batch": False,
                            "source_node_index": int(
                                obj.get("assetkit_source_node_index", -1)
                            ),
                            "matrix": [
                                float(obj.matrix_local[row][column])
                                for row in range(4)
                                for column in range(4)
                            ],
                        }
                    )
    if counter_path and transform_counters is not None:
        with open(counter_path, "wb") as stream:
            pickle.dump(transform_counters, stream, protocol=pickle.HIGHEST_PROTOCOL)
    if record_path and transform_records is not None:
        with open(record_path, "wb") as stream:
            stream.write(transform_records)
        with open(record_path + ".json", "w", encoding="utf-8") as stream:
            json.dump(transform_record_names, stream, sort_keys=True)
    print(
        "ASSETKIT_DAE_COMPACT_PROFILE="
        + json.dumps(
            {
                "compact_enabled": str(
                    os.environ.get("ASSETKIT_BLENDER_COMPACT_STATIC_INSTANCES", "")
                ).lower()
                not in {"0", "false", "no", "off", "legacy"},
                "import_ms": (imported_at - started_at) * 1_000.0,
                "view_layer_update_ms": (updated_at - update_started_at) * 1_000.0,
                "evaluation_scan_ms": (evaluated_at - evaluation_started_at) * 1_000.0,
                "imported_objects": len(imported),
                "objects": len(bpy.data.objects),
                "meshes": len(bpy.data.meshes),
                "materials": len(bpy.data.materials),
                "compact_batches": len(batches),
                "compact_instances": sum(
                    int(obj.get("assetkit_instance_count", 0)) for obj in batches
                ),
                "residual_instances": len(residual_instances),
                "evaluated_mesh_instances": evaluated_mesh_instances,
                "evaluated_surface_instances": evaluated_surface_instances,
                "evaluated_faces": evaluated_faces,
                "transform_checksum": [
                    round(value, 5) for value in transform_sums
                ],
                "transform_multiset": {
                    f"{1.0 / scale:.3f}": (
                        f"{values[0]:032x}:{values[1]:032x}"
                    )
                    for scale, values in transform_multisets.items()
                },
                "matrix_multiset": {
                    f"{1.0 / scale:.3f}": (
                        f"{values[0]:032x}:{values[1]:032x}"
                    )
                    for scale, values in matrix_multisets.items()
                },
                "geometry_multiset": (
                    f"{geometry_multiset[0]:032x}:{geometry_multiset[1]:032x}"
                ),
                "world_bounds": [
                    [round(value, 5) for value in world_minimum],
                    [round(value, 5) for value in world_maximum],
                ],
                "traced_instances": traced_instances,
                "traced_prototype_objects": traced_prototype_objects,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
