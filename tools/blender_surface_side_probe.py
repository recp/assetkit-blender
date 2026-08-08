#!/usr/bin/env python3
"""Summarize coincident top-surface sides after an AssetKit import."""

from __future__ import annotations

from collections import Counter
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


def _material_key(obj: bpy.types.Object, material_index: int) -> str:
    if material_index < 0 or material_index >= len(obj.material_slots):
        return "material:none"
    material = obj.material_slots[material_index].material
    if material is None:
        return "material:none"
    if material.node_tree:
        images = sorted(
            {
                Path(node.image.filepath).name
                for node in material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image and node.image.filepath
            }
        )
        if images:
            return "image:" + ",".join(images)
        surface = material.node_tree.nodes.get("Principled BSDF")
        if surface:
            color = surface.inputs["Base Color"].default_value
            return "base:" + ",".join(f"{float(value):.3f}" for value in color)
    color = material.diffuse_color
    return "diffuse:" + ",".join(f"{float(value):.3f}" for value in color)


def _triangle_color_key(obj: bpy.types.Object, loop_indices: tuple[int, int, int]) -> str | None:
    attribute = obj.data.color_attributes.get("Color")
    if attribute is None or attribute.domain != "CORNER":
        return None
    samples = [attribute.data[index].color for index in loop_indices]
    color = [
        sum(float(sample[channel]) for sample in samples) / len(samples)
        for channel in range(4)
    ]
    return "color:" + ",".join(f"{value:.3f}" for value in color)


def _load(path: str) -> None:
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


def _probe(path: str) -> dict[str, object]:
    _load(path)
    objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.data and obj.data.polygons
    ]
    scene_top = max(
        float((obj.matrix_world @ vertex.co).z)
        for obj in objects
        for vertex in obj.data.vertices
    )
    triangles: dict[
        tuple[tuple[float, float, float], ...],
        list[tuple[str, str, str]],
    ] = {}
    side_counts: Counter[tuple[str, str]] = Counter()
    normal_alignment: Counter[tuple[str, str]] = Counter()
    for obj in objects:
        obj.data.calc_loop_triangles()
        for triangle in obj.data.loop_triangles:
            points = [
                obj.matrix_world @ obj.data.vertices[index].co
                for index in triangle.vertices
            ]
            center_z = sum(float(point.z) for point in points) / 3.0
            if center_z < scene_top - 1.0:
                continue
            normal = (points[1] - points[0]).cross(points[2] - points[0])
            direction = "up" if normal.z >= 0.0 else "down"
            appearance = _triangle_color_key(obj, tuple(triangle.loops))
            if appearance is None:
                appearance = _material_key(obj, triangle.material_index)
            side_counts[(direction, appearance)] += 1
            if triangle.loops:
                stored = sum(
                    (obj.data.loops[index].normal for index in triangle.loops),
                    Vector((0.0, 0.0, 0.0)),
                )
                stored = obj.matrix_world.to_3x3().inverted().transposed() @ stored
                relation = "aligned" if stored.dot(normal) >= 0.0 else "opposed"
                normal_alignment[(direction, relation)] += 1
            key = tuple(sorted(
                tuple(round(float(value), 5) for value in point)
                for point in points
            ))
            triangles.setdefault(key, []).append((direction, appearance, obj.name))

    patterns: Counter[tuple[tuple[str, str], ...]] = Counter()
    examples: dict[tuple[tuple[str, str], ...], tuple[tuple[float, float, float], ...]] = {}
    for key, entries in triangles.items():
        if len(entries) < 2:
            continue
        pattern = tuple(sorted((direction, appearance) for direction, appearance, _ in entries))
        patterns[pattern] += 1
        examples.setdefault(pattern, key)

    return {
        "path": path,
        "objects": len(objects),
        "scene_top": round(scene_top, 6),
        "top_triangles": sum(side_counts.values()),
        "side_counts": [
            {"side": side, "appearance": appearance, "triangles": count}
            for (side, appearance), count in side_counts.most_common(30)
        ],
        "normal_alignment": [
            {"side": side, "relation": relation, "triangles": count}
            for (side, relation), count in normal_alignment.most_common()
        ],
        "duplicate_keys": sum(1 for entries in triangles.values() if len(entries) > 1),
        "duplicate_patterns": [
            {
                "entries": [
                    {"side": side, "appearance": appearance}
                    for side, appearance in pattern
                ],
                "triangles": count,
                "example": examples[pattern],
            }
            for pattern, count in patterns.most_common(30)
        ],
    }


def main(paths: list[str]) -> int:
    if not paths:
        raise SystemExit("Pass asset paths after --")
    for path in paths:
        print("ASSETKIT_SURFACE_SIDE " + json.dumps(_probe(path), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    raise SystemExit(main(args))
