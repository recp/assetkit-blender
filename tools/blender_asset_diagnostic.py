#!/usr/bin/env python3
"""Import assets through AssetKit and print compact scene/material diagnostics.

Run inside Blender, for example:

  blender --background --factory-startup \
    --python tools/blender_asset_diagnostic.py -- /path/to/model.3mf
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
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


def _vector(values: Vector) -> list[float]:
    return [round(float(value), 6) for value in values]


def _material_summary() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for material in bpy.data.materials:
        surface = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
        base = surface.inputs.get("Base Color") if surface else None
        metallic = surface.inputs.get("Metallic") if surface else None
        roughness = surface.inputs.get("Roughness") if surface else None
        alpha = surface.inputs.get("Alpha") if surface else None
        result.append(
            {
                "name": material.name,
                "base_color": list(base.default_value) if base else None,
                "metallic": float(metallic.default_value) if metallic else None,
                "roughness": float(roughness.default_value) if roughness else None,
                "alpha": float(alpha.default_value) if alpha else None,
                "use_backface_culling": bool(material.use_backface_culling),
                "surface_render_method": getattr(material, "surface_render_method", None),
            }
        )
    return result


def _mesh_material_summary(obj: bpy.types.Object) -> list[dict[str, object]]:
    slot_count = max(len(obj.data.materials), len(obj.material_slots))
    polygon_counts = [0] * slot_count
    for polygon in obj.data.polygons:
        if 0 <= polygon.material_index < len(polygon_counts):
            polygon_counts[polygon.material_index] += 1
    result: list[dict[str, object]] = []
    for index in range(slot_count):
        slot = obj.material_slots[index] if index < len(obj.material_slots) else None
        material = slot.material if slot is not None else None
        mesh_material = obj.data.materials[index] if index < len(obj.data.materials) else None
        surface = (
            material.node_tree.nodes.get("Principled BSDF")
            if material and material.node_tree
            else None
        )
        base = surface.inputs.get("Base Color") if surface else None
        base_links = []
        if base:
            for link in base.links:
                source = link.from_node
                base_links.append(
                    {
                        "node": source.name,
                        "type": source.bl_idname,
                        "layer_name": getattr(source, "layer_name", None),
                        "attribute_name": getattr(source, "attribute_name", None),
                    }
                )
        result.append(
            {
                "slot": index,
                "name": material.name if material else None,
                "link": slot.link if slot is not None else None,
                "mesh_name": mesh_material.name if mesh_material else None,
                "faces": polygon_counts[index],
                "base_color": [round(float(value), 6) for value in base.default_value]
                if base else None,
                "base_links": base_links,
                "use_backface_culling": bool(material.use_backface_culling)
                if material else None,
            }
        )
    return result


def _uv_summary(obj: bpy.types.Object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for layer in obj.data.uv_layers:
        values = [item.uv for item in layer.data]
        result.append(
            {
                "name": layer.name,
                "count": len(values),
                "min": [
                    round(min(float(value[axis]) for value in values), 6)
                    for axis in range(2)
                ] if values else None,
                "max": [
                    round(max(float(value[axis]) for value in values), 6)
                    for axis in range(2)
                ] if values else None,
            }
        )
    return result


def _color_summary(obj: bpy.types.Object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for attribute in obj.data.color_attributes:
        values = [tuple(float(channel) for channel in item.color) for item in attribute.data]
        result.append(
            {
                "name": attribute.name,
                "domain": attribute.domain,
                "data_type": attribute.data_type,
                "count": len(values),
                "min": [
                    round(min(value[channel] for value in values), 6)
                    for channel in range(4)
                ] if values else None,
                "max": [
                    round(max(value[channel] for value in values), 6)
                    for channel in range(4)
                ] if values else None,
                "first": [round(channel, 6) for channel in values[0]] if values else None,
            }
        )
    return result


def _top_surface_color_summary(obj: bpy.types.Object) -> list[dict[str, object]]:
    attribute = obj.data.color_attributes.get("Color")
    if attribute is None or attribute.domain != "CORNER" or not obj.data.polygons:
        return []
    world_top = max((obj.matrix_world @ vertex.co).z for vertex in obj.data.vertices)
    counts: Counter[tuple[float, float, float, float]] = Counter()
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        normal = obj.matrix_world.to_3x3() @ polygon.normal
        if center.z < world_top - 1.0 or normal.z <= 0.25:
            continue
        for loop_index in polygon.loop_indices:
            color = attribute.data[loop_index].color
            counts[tuple(round(float(channel), 3) for channel in color)] += 1
    return [
        {"color": list(color), "count": count}
        for color, count in counts.most_common(20)
    ]


def _top_surface_overlap_summary(obj: bpy.types.Object) -> dict[str, object]:
    attribute = obj.data.color_attributes.get("Color")
    if attribute is None or attribute.domain != "CORNER" or not obj.data.polygons:
        return {}

    world_top = max((obj.matrix_world @ vertex.co).z for vertex in obj.data.vertices)
    color_by_normal: dict[str, Counter[tuple[float, float, float, float]]] = {
        "up": Counter(),
        "down": Counter(),
    }
    triangles: dict[
        tuple[tuple[float, float, float], ...],
        list[tuple[str, tuple[float, float, float, float]]],
    ] = {}
    for polygon in obj.data.polygons:
        center = obj.matrix_world @ polygon.center
        if center.z < world_top - 1.0:
            continue
        normal = obj.matrix_world.to_3x3() @ polygon.normal
        direction = "up" if normal.z >= 0.0 else "down"
        samples = [attribute.data[index].color for index in polygon.loop_indices]
        color = tuple(
            round(sum(float(sample[channel]) for sample in samples) / len(samples), 3)
            for channel in range(4)
        )
        color_by_normal[direction][color] += 1
        if len(polygon.vertices) != 3:
            continue
        key = tuple(sorted(
            tuple(round(float(value), 5) for value in obj.matrix_world @ obj.data.vertices[index].co)
            for index in polygon.vertices
        ))
        triangles.setdefault(key, []).append((direction, color))

    overlap_patterns: Counter[tuple[tuple[str, tuple[float, float, float, float]], ...]] = Counter()
    duplicate_triangles = 0
    for entries in triangles.values():
        if len(entries) < 2:
            continue
        duplicate_triangles += 1
        overlap_patterns[tuple(sorted(entries))] += 1

    return {
        "colors_by_normal": {
            direction: [
                {"color": list(color), "faces": count}
                for color, count in counts.most_common(12)
            ]
            for direction, counts in color_by_normal.items()
        },
        "duplicate_triangle_keys": duplicate_triangles,
        "duplicate_patterns": [
            {
                "entries": [
                    {"normal": direction, "color": list(color)}
                    for direction, color in pattern
                ],
                "triangles": count,
            }
            for pattern, count in overlap_patterns.most_common(20)
        ],
    }


def _polygon_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector] | None:
    used_vertices = {
        vertex_index
        for polygon in obj.data.polygons
        for vertex_index in polygon.vertices
    }
    if not used_vertices:
        return None
    positions = [obj.matrix_world @ obj.data.vertices[index].co for index in used_vertices]
    return (
        Vector((min(position[axis] for position in positions) for axis in range(3))),
        Vector((max(position[axis] for position in positions) for axis in range(3))),
    )


def _scene_summary(path: str) -> dict[str, object]:
    bpy.context.view_layer.update()
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.data]
    surface_objects = [obj for obj in mesh_objects if obj.data.polygons]
    nonsurface_objects = [obj for obj in mesh_objects if not obj.data.polygons]
    bounds_min = Vector((math.inf, math.inf, math.inf))
    bounds_max = Vector((-math.inf, -math.inf, -math.inf))
    surface_bounds_min = Vector((math.inf, math.inf, math.inf))
    surface_bounds_max = Vector((-math.inf, -math.inf, -math.inf))
    objects: list[dict[str, object]] = []
    color_attributes = 0

    for obj in mesh_objects:
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        obj_min = Vector((min(c[i] for c in corners) for i in range(3)))
        obj_max = Vector((max(c[i] for c in corners) for i in range(3)))
        polygon_bounds = _polygon_bounds(obj)
        for axis in range(3):
            bounds_min[axis] = min(bounds_min[axis], obj_min[axis])
            bounds_max[axis] = max(bounds_max[axis], obj_max[axis])
            if polygon_bounds:
                surface_bounds_min[axis] = min(surface_bounds_min[axis], polygon_bounds[0][axis])
                surface_bounds_max[axis] = max(surface_bounds_max[axis], polygon_bounds[1][axis])
        color_attributes += len(obj.data.color_attributes)
        objects.append(
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "faces": len(obj.data.polygons),
                "materials": len(obj.data.materials),
                "material_slots": _mesh_material_summary(obj),
                "uv_layers": _uv_summary(obj),
                "color_attributes": [attr.name for attr in obj.data.color_attributes],
                "render_color_index": int(obj.data.color_attributes.render_color_index),
                "color_attribute_summary": _color_summary(obj),
                "top_surface_colors": _top_surface_color_summary(obj),
                "top_surface_overlaps": _top_surface_overlap_summary(obj),
                "bounds_min": _vector(obj_min),
                "bounds_max": _vector(obj_max),
                "polygon_bounds_min": _vector(polygon_bounds[0]) if polygon_bounds else None,
                "polygon_bounds_max": _vector(polygon_bounds[1]) if polygon_bounds else None,
            }
        )

    size = bounds_max - bounds_min if mesh_objects else Vector((0.0, 0.0, 0.0))
    center = (bounds_min + bounds_max) * 0.5 if mesh_objects else Vector((0.0, 0.0, 0.0))
    surface_size = (
        surface_bounds_max - surface_bounds_min
        if surface_objects
        else Vector((0.0, 0.0, 0.0))
    )
    objects.sort(key=lambda item: int(item["vertices"]), reverse=True)
    surface_items = [item for item in objects if int(item["faces"]) > 0]
    surface_object_signatures = [
        {
            "name": item["name"],
            "vertices": item["vertices"],
            "faces": item["faces"],
            "bounds_min": item["bounds_min"],
            "bounds_max": item["bounds_max"],
            "polygon_bounds_min": item["polygon_bounds_min"],
            "polygon_bounds_max": item["polygon_bounds_max"],
            "bounds_center": [
                round(
                    (float(item["bounds_min"][axis]) + float(item["bounds_max"][axis]))
                    * 0.5,
                    6,
                )
                for axis in range(3)
            ],
            "bounds_size": [
                round(
                    float(item["bounds_max"][axis]) - float(item["bounds_min"][axis]),
                    6,
                )
                for axis in range(3)
            ],
        }
        for item in surface_items
    ]
    centers = [
        tuple((float(item["bounds_min"][axis]) + float(item["bounds_max"][axis])) * 0.5
              for axis in range(3))
        for item in surface_items
    ]
    median_center = tuple(
        statistics.median(center[axis] for center in centers)
        for axis in range(3)
    ) if centers else (0.0, 0.0, 0.0)
    spatial_outliers = sorted(
        (
            {
                "name": item["name"],
                "center": _vector(Vector(item_center)),
                "distance_from_median": round(math.dist(item_center, median_center), 6),
                "vertices": item["vertices"],
                "faces": item["faces"],
            }
            for item, item_center in zip(surface_items, centers)
        ),
        key=lambda item: float(item["distance_from_median"]),
        reverse=True,
    )
    high_surface_threshold = float(surface_bounds_max[2]) - 1.5 if surface_objects else math.inf
    high_light_objects = [
        item
        for item in surface_items
        if float(item["bounds_max"][2]) >= high_surface_threshold
        and not item["color_attribute_summary"]
        and not item["uv_layers"]
        and any(
            slot["faces"]
            and slot["base_color"]
            and min(slot["base_color"][:3]) >= 0.8
            for slot in item["material_slots"]
        )
    ]
    return {
        "path": path,
        "objects": len(bpy.context.scene.objects),
        "mesh_objects": len(mesh_objects),
        "vertices": sum(len(obj.data.vertices) for obj in mesh_objects),
        "faces": sum(len(obj.data.polygons) for obj in mesh_objects),
        "color_attributes": color_attributes,
        "bounds_min": _vector(bounds_min) if mesh_objects else None,
        "bounds_max": _vector(bounds_max) if mesh_objects else None,
        "bounds_size": _vector(size),
        "bounds_center": _vector(center),
        "surface_bounds_min": _vector(surface_bounds_min) if surface_objects else None,
        "surface_bounds_max": _vector(surface_bounds_max) if surface_objects else None,
        "surface_bounds_size": _vector(surface_size),
        "surface_object_signatures": surface_object_signatures,
        "largest_objects": objects[:12],
        "top_surface_objects": sorted(
            surface_items,
            key=lambda item: float(item["bounds_max"][2]),
            reverse=True,
        )[:12],
        "high_light_objects": sorted(
            high_light_objects,
            key=lambda item: float(item["bounds_max"][2]),
            reverse=True,
        ),
        "object_center_median": _vector(Vector(median_center)),
        "spatial_outliers": spatial_outliers[:12],
        "nonsurface_objects": [
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "edges": len(obj.data.edges),
                "object_color": [round(float(value), 6) for value in obj.color],
                "mixed_line_material_slot": int(
                    obj.get("assetkit_mixed_line_material_slot", -1)
                ),
                "material_slots": _mesh_material_summary(obj),
            }
            for obj in nonsurface_objects[:24]
        ],
        "materials": _material_summary(),
    }


def main(paths: list[str]) -> int:
    if not paths:
        raise SystemExit("Pass one or more asset paths after --")

    for path in paths:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        options = make_load_options(
            coordinate_system="Z_UP",
            coordinate_conversion="TRANSFORM",
            generate_normals=False,
            texture_loading=os.environ.get("ASSETKIT_DIAGNOSTIC_TEXTURE_LOADING", "DEFERRED"),
        )
        import_assetkit_file(
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
        print("ASSETKIT_DIAGNOSTIC " + json.dumps(_scene_summary(path), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    raise SystemExit(main(args))
