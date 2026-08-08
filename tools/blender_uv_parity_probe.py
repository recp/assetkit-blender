#!/usr/bin/env python3
"""Compare world-position to UV mappings across AssetKit round trips."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def _image_key(image: bpy.types.Image | None) -> str | None:
    if image is None:
        return None
    path = Path(bpy.path.abspath(image.filepath))
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return f"missing:{path.name}"


def _material_image(material: bpy.types.Material | None) -> bpy.types.Image | None:
    if material is None or material.node_tree is None:
        return None
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    base = bsdf.inputs.get("Base Color") if bsdf else None
    if base and base.is_linked:
        node = base.links[0].from_node
        if node.type == "TEX_IMAGE":
            return node.image
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            return node.image
    return None


def _round_position(value: Vector) -> tuple[float, float, float]:
    return tuple(round(float(axis), 4) for axis in value)


def _round_uv(uv: Vector) -> tuple[float, float]:
    return round(float(uv.x), 5), round(float(uv.y), 5)


def _face_signature(
    corners: list[tuple[tuple[float, float, float], tuple[float, float]]],
) -> tuple[tuple[tuple[float, float, float], tuple[float, float]], ...]:
    """Canonicalize a face without losing each position-to-UV pairing."""
    return tuple(sorted(corners))


def _collect(path: str) -> dict[str, object]:
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

    groups: dict[str, dict[str, object]] = {}
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.data is None or not obj.data.polygons:
            continue
        uv_layer = obj.data.uv_layers.active
        if uv_layer is None:
            continue
        for polygon in obj.data.polygons:
            if polygon.material_index >= len(obj.material_slots):
                continue
            material = obj.material_slots[polygon.material_index].material
            image = _material_image(material)
            key = _image_key(image)
            if key is None:
                continue
            group = groups.setdefault(
                key,
                {
                    "image_names": set(),
                    "objects": set(),
                    "corners": defaultdict(set),
                    "_faces": Counter(),
                    "_position_faces": Counter(),
                    "face_count": 0,
                },
            )
            group["image_names"].add(Path(bpy.path.abspath(image.filepath)).name)
            group["objects"].add(obj.name)
            group["face_count"] += 1
            corners = group["corners"]
            face_corners = []
            for loop_index in polygon.loop_indices:
                loop = obj.data.loops[loop_index]
                position = obj.matrix_world @ obj.data.vertices[loop.vertex_index].co
                rounded_position = _round_position(position)
                rounded_uv = _round_uv(uv_layer.data[loop_index].uv)
                corners[rounded_position].add(rounded_uv)
                face_corners.append((rounded_position, rounded_uv))
            group["_faces"][_face_signature(face_corners)] += 1
            group["_position_faces"][tuple(sorted(position for position, _ in face_corners))] += 1

    serializable = {}
    for key, group in groups.items():
        corners = group["corners"]
        pairs = sorted((position, uv) for position, uvs in corners.items() for uv in uvs)
        serializable[key] = {
            "image_names": sorted(group["image_names"]),
            "objects": sorted(group["objects"]),
            "face_count": group["face_count"],
            "position_count": len(corners),
            "pair_count": len(pairs),
            "uv_min": [min(pair[1][axis] for pair in pairs) for axis in range(2)],
            "uv_max": [max(pair[1][axis] for pair in pairs) for axis in range(2)],
            "pairs": pairs,
            "_faces": group["_faces"],
            "_position_faces": group["_position_faces"],
        }
    return {"path": path, "groups": serializable}


def _transform_uv(uv: tuple[float, float], mode: str) -> tuple[float, float]:
    u, v = uv
    if "u" in mode:
        u = 1.0 - u
    if "v" in mode:
        v = 1.0 - v
    return round(u, 6), round(v, 6)


def _compare(reference: dict[str, object], candidate: dict[str, object]) -> list[dict[str, object]]:
    comparisons = []
    for key in sorted(set(reference["groups"]) & set(candidate["groups"])):
        left = reference["groups"][key]
        right = candidate["groups"][key]
        left_pairs = {(tuple(position), tuple(uv)) for position, uv in left["pairs"]}
        right_pairs = {(tuple(position), tuple(uv)) for position, uv in right["pairs"]}
        modes = {}
        face_modes = {}
        for mode in ("identity", "u", "v", "uv"):
            transformed = {
                (position, _transform_uv(uv, mode))
                for position, uv in right_pairs
            }
            modes[mode] = len(left_pairs & transformed)
            transformed_faces = Counter()
            for face, count in right["_faces"].items():
                transformed_face = _face_signature(
                    [(position, _transform_uv(uv, mode)) for position, uv in face]
                )
                transformed_faces[transformed_face] += count
            face_modes[mode] = sum((left["_faces"] & transformed_faces).values())
        common_position_faces = sum(
            (left["_position_faces"] & right["_position_faces"]).values()
        )
        comparisons.append(
            {
                "image": key,
                "reference_names": left["image_names"],
                "candidate_names": right["image_names"],
                "reference_pairs": len(left_pairs),
                "candidate_pairs": len(right_pairs),
                "matches": modes,
                "best": max(modes, key=modes.get),
                "reference_faces": sum(left["_faces"].values()),
                "candidate_faces": sum(right["_faces"].values()),
                "common_position_faces": common_position_faces,
                "face_matches": face_modes,
                "face_best": max(face_modes, key=face_modes.get),
            }
        )
    return comparisons


def main(paths: list[str]) -> int:
    if len(paths) < 2:
        raise SystemExit("Pass a reference asset and one or more candidates after --")
    records = [_collect(path) for path in paths]
    reference = records[0]
    for record in records:
        compact = {
            "path": record["path"],
            "groups": {
                key: {
                    field: value
                    for field, value in group.items()
                    if field != "pairs" and not field.startswith("_")
                }
                for key, group in record["groups"].items()
            },
        }
        print("ASSETKIT_UV_GROUPS " + json.dumps(compact, sort_keys=True), flush=True)
    for candidate in records[1:]:
        print(
            "ASSETKIT_UV_COMPARE "
            + json.dumps(
                {
                    "reference": reference["path"],
                    "candidate": candidate["path"],
                    "groups": _compare(reference, candidate),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    raise SystemExit(main(args))
