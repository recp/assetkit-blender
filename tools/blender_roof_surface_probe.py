#!/usr/bin/env python3
"""Compare roof face orientation and coincident geometry across round trips."""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


ROOF_IMAGE_HASH = "06b5d6e10e5cb1b3"


def _image_hash(material: bpy.types.Material | None) -> str | None:
    if material is None or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        path = Path(bpy.path.abspath(node.image.filepath))
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            return None
    return None


def _face_key(obj: bpy.types.Object, polygon: bpy.types.MeshPolygon):
    positions = []
    for vertex_index in polygon.vertices:
        position = obj.matrix_world @ obj.data.vertices[vertex_index].co
        positions.append(tuple(round(float(axis), 4) for axis in position))
    return tuple(sorted(positions))


def _collect(path: str) -> dict[str, object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="IMMEDIATE",
    )
    if import_assetkit_file(
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
    ) is False:
        raise RuntimeError(f"AssetKit could not import {path}")
    bpy.context.view_layer.update()

    roof_faces: dict[tuple, list[dict[str, object]]] = defaultdict(list)
    all_faces: dict[tuple, list[dict[str, object]]] = defaultdict(list)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for polygon in obj.data.polygons:
            material = None
            if polygon.material_index < len(obj.material_slots):
                material = obj.material_slots[polygon.material_index].material
            image_hash = _image_hash(material)
            normal = (normal_matrix @ polygon.normal).normalized()
            item = {
                "object": obj.name,
                "material": material.name if material else None,
                "image": image_hash,
                "normal": tuple(round(float(axis), 6) for axis in normal),
                "area": round(float(polygon.area), 6),
            }
            key = _face_key(obj, polygon)
            all_faces[key].append(item)
            if image_hash == ROOF_IMAGE_HASH:
                roof_faces[key].append(item)

    return {
        "path": path,
        "roof": roof_faces,
        "coincident": {
            key: faces for key, faces in all_faces.items() if len(faces) > 1
        },
    }


def _dot(a, b) -> float:
    return sum(left * right for left, right in zip(a, b))


def _compare(reference: dict[str, object], candidate: dict[str, object]):
    common = set(reference["roof"]) & set(candidate["roof"])
    dots = []
    for key in common:
        left_faces = reference["roof"][key]
        right_faces = candidate["roof"][key]
        if len(left_faces) != len(right_faces):
            continue
        best = None
        for permutation in itertools.permutations(right_faces):
            candidate_dots = [
                _dot(left["normal"], right["normal"])
                for left, right in zip(left_faces, permutation)
            ]
            if best is None or sum(candidate_dots) > sum(best):
                best = candidate_dots
        dots.extend(best or [])
    return {
        "reference": reference["path"],
        "candidate": candidate["path"],
        "reference_roof_faces": sum(map(len, reference["roof"].values())),
        "candidate_roof_faces": sum(map(len, candidate["roof"].values())),
        "matched_face_keys": len(common),
        "normal_dot_min": round(min(dots), 6) if dots else None,
        "normal_dot_max": round(max(dots), 6) if dots else None,
        "normal_dot_below_0999": sum(dot < 0.999 for dot in dots),
        "reference_coincident_keys": len(reference["coincident"]),
        "candidate_coincident_keys": len(candidate["coincident"]),
    }


def main(paths: list[str]) -> int:
    if len(paths) < 2:
        raise SystemExit("Pass a reference asset and candidates after --")
    records = [_collect(path) for path in paths]
    for candidate in records[1:]:
        print("ASSETKIT_ROOF_COMPARE " + json.dumps(_compare(records[0], candidate)))
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    raise SystemExit(main(args))
