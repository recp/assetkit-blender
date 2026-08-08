#!/usr/bin/env python3
"""Print object/material details for selected face-counts after AssetKit import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def _texture_nodes(material: bpy.types.Material | None) -> list[dict[str, object]]:
    if material is None or material.node_tree is None:
        return []
    result = []
    for node in material.node_tree.nodes:
        if node.type != "TEX_IMAGE":
            continue
        image = node.image
        result.append(
            {
                "node": node.name,
                "image": image.name if image else None,
                "filepath": image.filepath if image else None,
                "colorspace": image.colorspace_settings.name if image else None,
            }
        )
    return result


def _object_record(obj: bpy.types.Object) -> dict[str, object]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    bounds_min = [min(float(corner[axis]) for corner in corners) for axis in range(3)]
    bounds_max = [max(float(corner[axis]) for corner in corners) for axis in range(3)]
    slots = []
    counts = [0] * len(obj.material_slots)
    for polygon in obj.data.polygons:
        if 0 <= polygon.material_index < len(counts):
            counts[polygon.material_index] += 1
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        bsdf = material.node_tree.nodes.get("Principled BSDF") if material and material.node_tree else None
        base = bsdf.inputs.get("Base Color") if bsdf else None
        slots.append(
            {
                "index": index,
                "faces": counts[index],
                "link": slot.link,
                "name": material.name if material else None,
                "base_color": [round(float(value), 6) for value in base.default_value] if base else None,
                "textures": _texture_nodes(material),
                "backface_culling": bool(material.use_backface_culling) if material else None,
            }
        )
    normal_sum = Vector((0.0, 0.0, 0.0))
    for polygon in obj.data.polygons:
        normal_sum += (obj.matrix_world.to_3x3() @ polygon.normal) * polygon.area
    return {
        "name": obj.name,
        "data": obj.data.name,
        "vertices": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "bounds_min": [round(value, 6) for value in bounds_min],
        "bounds_max": [round(value, 6) for value in bounds_max],
        "bounds_center": [round((lo + hi) * 0.5, 6) for lo, hi in zip(bounds_min, bounds_max)],
        "materials": slots,
        "normal_sum": [round(float(value), 6) for value in normal_sum],
        "properties": {
            key: obj[key]
            for key in obj.keys()
            if isinstance(obj[key], (str, int, float, bool))
        },
    }


def main(paths: list[str]) -> int:
    if not paths:
        raise SystemExit("Pass asset paths after --")
    face_counts = {56, 120, 152, 387, 438, 774}
    for path in paths:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        options = make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading="IMMEDIATE",
        )
        result = import_assetkit_file(
            path,
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
        if result is False:
            raise RuntimeError(f"AssetKit could not import {path}")
        bpy.context.view_layer.update()
        mesh_objects = [
            obj
            for obj in bpy.context.scene.objects
            if obj.type == "MESH" and obj.data and obj.data.polygons
        ]
        scene_top = max((obj.matrix_world @ Vector(corner)).z for obj in mesh_objects for corner in obj.bound_box)
        records = [
            _object_record(obj)
            for obj in mesh_objects
            if len(obj.data.polygons) in face_counts
            or max((obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box) >= scene_top - 0.6
        ]
        records.sort(key=lambda item: (int(item["faces"]), item["bounds_center"], item["name"]))
        print("ASSETKIT_MATERIAL_PROBE " + json.dumps({"path": path, "objects": records}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    raise SystemExit(main(args))
