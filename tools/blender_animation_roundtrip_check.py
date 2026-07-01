#!/usr/bin/env python3
"""Exercise AssetKit Blender animation glTF -> DAE -> reimport regressions.

Run with:
  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_animation_roundtrip_check.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for search_path in (REPO_ROOT, TOOLS_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from assetkit_blender.enums import AK_FILE_TYPE_DAE  # noqa: E402
from assetkit_blender.exp.exporter import export_scene  # noqa: E402
from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


DEFAULT_ASSET_CACHE = REPO_ROOT / "benchmark-assets" / "import-suite"
DEFAULT_SAMPLE_ROOT = Path(
    os.environ.get(
        "ASSETKIT_GLTF_SAMPLE_ASSETS",
        "/Users/recp/Projects/KhronosGroup/glTF-Sample-Assets",
    )
)
ANIMATION_ASSETS = (
    (
        "BoxAnimated",
        Path("Models/BoxAnimated/glTF/BoxAnimated.gltf"),
        Path("gltf/BoxAnimated/glTF/BoxAnimated.gltf"),
        "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/BoxAnimated/glTF/BoxAnimated.gltf",
        (
            (
                Path("gltf/BoxAnimated/glTF/BoxAnimated0.bin"),
                "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/BoxAnimated/glTF/BoxAnimated0.bin",
            ),
        ),
    ),
    (
        "CesiumMan",
        Path("Models/CesiumMan/glTF/CesiumMan.gltf"),
        Path("gltf/CesiumMan/glTF/CesiumMan.gltf"),
        "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/glTF/CesiumMan.gltf",
        (
            (
                Path("gltf/CesiumMan/glTF/CesiumMan_data.bin"),
                "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/glTF/CesiumMan_data.bin",
            ),
            (
                Path("gltf/CesiumMan/glTF/CesiumMan_img0.jpg"),
                "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/glTF/CesiumMan_img0.jpg",
            ),
        ),
    ),
)


def download_file(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".download")
    with urlopen(url, timeout=120) as response, tmp_path.open("wb") as out_file:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out_file.write(chunk)
    tmp_path.replace(out_path)


def animation_asset_paths(sample_root: Path, asset_cache: Path) -> list[Path]:
    out: list[Path] = []
    for name, sample_rel, cache_rel, url, resources in ANIMATION_ASSETS:
        sample_path = sample_root / sample_rel
        if sample_path.is_file():
            out.append(sample_path)
            continue

        cache_path = asset_cache / cache_rel
        if not cache_path.exists() or cache_path.stat().st_size == 0:
            print(f"Downloading {name}: {url}", flush=True)
            download_file(url, cache_path)
        for resource_rel, resource_url in resources:
            resource_path = asset_cache / resource_rel
            if not resource_path.exists() or resource_path.stat().st_size == 0:
                print(f"Downloading {name} resource: {resource_url}", flush=True)
                download_file(resource_url, resource_path)
        out.append(cache_path)
    return out


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_asset(path: Path, *, scene_was_empty: bool) -> list[bpy.types.Object]:
    return import_assetkit_file(
        os.fspath(path),
        "",
        make_load_options(texture_loading="IMMEDIATE"),
        collection=bpy.context.collection,
        focus_mode="NEVER",
        placement_mode="AS_AUTHORED",
        scene_was_empty=scene_was_empty,
        select_imported=False,
        shading_mode="AUTO",
        set_viewport_shading=False,
        clean_viewport_overlays=False,
        fit_timeline=True,
    )


def export_dae(path: Path, *, animation_timing: str = "CLIP") -> None:
    result = export_scene(
        bpy.context,
        path,
        AK_FILE_TYPE_DAE,
        export_animations=True,
        export_skins=True,
        export_shape_keys=True,
        export_shape_key_animations=True,
        animation_timing=animation_timing,
    )
    if result < 0 or not path.exists() or path.stat().st_size == 0:
        raise AssertionError(f"DAE export failed: {path}")


def iter_action_fcurves(action: bpy.types.Action):
    seen: set[int] = set()
    direct = getattr(action, "fcurves", None)
    if direct is not None:
        for fcurve in direct:
            key = fcurve.as_pointer()
            if key not in seen:
                seen.add(key)
                yield fcurve

    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for channelbag in getattr(strip, "channelbags", []) or []:
                for fcurve in getattr(channelbag, "fcurves", []) or []:
                    key = fcurve.as_pointer()
                    if key not in seen:
                        seen.add(key)
                        yield fcurve


def iter_animation_owners():
    for collection_name in ("objects", "materials", "meshes", "armatures", "cameras", "lights"):
        for owner in getattr(bpy.data, collection_name, []) or []:
            yield owner
            shape_keys = getattr(owner, "shape_keys", None)
            if shape_keys is not None:
                yield shape_keys


def linked_actions() -> set[bpy.types.Action]:
    actions: set[bpy.types.Action] = set()
    for owner in iter_animation_owners():
        anim_data = getattr(owner, "animation_data", None)
        if anim_data is None:
            continue
        action = getattr(anim_data, "action", None)
        if action is not None:
            actions.add(action)
        for track in getattr(anim_data, "nla_tracks", []) or []:
            for strip in getattr(track, "strips", []) or []:
                action = getattr(strip, "action", None)
                if action is not None:
                    actions.add(action)
    return actions


def action_summary(action: bpy.types.Action) -> dict:
    fcurves = tuple(iter_action_fcurves(action))
    frames = [
        float(point.co.x)
        for fcurve in fcurves
        for point in getattr(fcurve, "keyframe_points", []) or []
    ]
    paths = sorted({fcurve.data_path for fcurve in fcurves})
    return {
        "name": action.name,
        "users": int(action.users),
        "fcurves": len(fcurves),
        "channels": len(paths),
        "start": min(frames) if frames else None,
        "end": max(frames) if frames else None,
        "clip": action.get("assetkit_animation_clip_name", ""),
        "export_clip": action.get("assetkit_animation_clip_export_name", ""),
    }


def offset_linked_action_keyframes(frame_offset: float) -> None:
    for action in linked_actions():
        for fcurve in iter_action_fcurves(action):
            for point in getattr(fcurve, "keyframe_points", []) or []:
                point.co.x += frame_offset
                point.handle_left.x += frame_offset
                point.handle_right.x += frame_offset
            fcurve.update()


def assert_export_normalized_clip_start(summary: dict, source_offset: float) -> None:
    starts = [
        float(row["start"])
        for row in summary["actions"]
        if row["start"] is not None
    ]
    if not starts:
        raise AssertionError(f"{summary['label']}: no action start frames found")
    if min(starts) >= source_offset - 1.0:
        raise AssertionError(
            f"{summary['label']}: exported actions kept scene offset {source_offset}: "
            f"starts={starts}"
        )


def scene_animation_summary(label: str) -> dict:
    actions = [action for action in bpy.data.actions if any(True for _ in iter_action_fcurves(action))]
    linked = linked_actions()
    action_rows = [action_summary(action) for action in actions]
    unlinked = [action.name for action in actions if action not in linked and action.users <= 0]
    return {
        "label": label,
        "objects": len(bpy.context.scene.objects),
        "frame_start": int(bpy.context.scene.frame_start),
        "frame_end": int(bpy.context.scene.frame_end),
        "actions": action_rows,
        "action_count": len(action_rows),
        "fcurve_count": sum(row["fcurves"] for row in action_rows),
        "channel_count": sum(row["channels"] for row in action_rows),
        "unlinked_actions": unlinked,
    }


def assert_animation_summary(summary: dict) -> None:
    if summary["objects"] <= 0:
        raise AssertionError(f"{summary['label']}: import produced no objects")
    if summary["action_count"] <= 0:
        raise AssertionError(f"{summary['label']}: import produced no actions")
    if summary["fcurve_count"] <= 0 or summary["channel_count"] <= 0:
        raise AssertionError(f"{summary['label']}: actions have no visible fcurves")
    if summary["frame_end"] <= summary["frame_start"]:
        raise AssertionError(f"{summary['label']}: timeline did not fit animation")
    if summary["unlinked_actions"]:
        raise AssertionError(f"{summary['label']}: unlinked actions: {summary['unlinked_actions']}")


def roundtrip_asset(source_path: Path, out_dir: Path) -> dict:
    stem = source_path.stem
    dae_path = out_dir / f"{stem}.dae"

    reset_scene()
    import_asset(source_path, scene_was_empty=True)
    imported_summary = scene_animation_summary(f"{stem}:gltf")
    assert_animation_summary(imported_summary)
    offset_linked_action_keyframes(120.0)
    export_dae(dae_path)

    reset_scene()
    import_asset(dae_path, scene_was_empty=True)
    reimported_summary = scene_animation_summary(f"{stem}:dae")
    assert_animation_summary(reimported_summary)
    assert_export_normalized_clip_start(reimported_summary, 120.0)

    return {
        "asset": stem,
        "source": os.fspath(source_path),
        "dae": os.fspath(dae_path),
        "imported": imported_summary,
        "reimported": reimported_summary,
    }


def assert_multi_import_preserves_timeline(dae_paths: list[Path]) -> dict:
    if len(dae_paths) < 2:
        raise AssertionError("multi-import check needs at least two DAE files")

    reset_scene()
    import_asset(dae_paths[0], scene_was_empty=True)
    first_summary = scene_animation_summary(f"{dae_paths[0].stem}:first")
    assert_animation_summary(first_summary)

    preserved_end = max(int(bpy.context.scene.frame_end), 240)
    bpy.context.scene.frame_end = preserved_end
    before_second = int(bpy.context.scene.frame_end)
    actions_before_second = set(bpy.data.actions)
    import_asset(dae_paths[1], scene_was_empty=False)
    after_second = int(bpy.context.scene.frame_end)
    second_summary = scene_animation_summary(f"{dae_paths[1].stem}:second")
    assert_animation_summary(second_summary)

    if after_second < before_second:
        raise AssertionError(
            f"second import shortened timeline: before={before_second}, after={after_second}"
        )

    new_second_actions = [
        action_summary(action)
        for action in bpy.data.actions
        if action not in actions_before_second and any(True for _ in iter_action_fcurves(action))
    ]
    if not new_second_actions:
        raise AssertionError("second import produced no new visible actions")

    offset_actions = [
        row
        for row in new_second_actions
        if row["start"] is not None and row["start"] >= before_second
    ]
    if offset_actions:
        raise AssertionError(
            "second import actions were offset to the existing timeline end: "
            f"before={before_second}, actions={offset_actions}"
        )

    return {
        "first": os.fspath(dae_paths[0]),
        "second": os.fspath(dae_paths[1]),
        "before_second": before_second,
        "after_second": after_second,
        "new_second_actions": new_second_actions,
        "summary": second_summary,
    }


def run_checks(sample_root: Path, asset_cache: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    source_paths = animation_asset_paths(sample_root, asset_cache)
    roundtrips = [roundtrip_asset(path, out_dir) for path in source_paths]
    multi_import = assert_multi_import_preserves_timeline(
        [Path(row["dae"]) for row in roundtrips]
    )
    return {
        "assets": [Path(path).name for path in source_paths],
        "sample_root": os.fspath(sample_root),
        "out": os.fspath(out_dir),
        "roundtrips": roundtrips,
        "multi_import": multi_import,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-cache",
        type=Path,
        default=DEFAULT_ASSET_CACHE,
        help=f"Download cache. Defaults to {DEFAULT_ASSET_CACHE}",
    )
    parser.add_argument(
        "--sample-root",
        type=Path,
        default=DEFAULT_SAMPLE_ROOT,
        help=(
            "glTF-Sample-Assets root. Uses BoxAnimated/CesiumMan .gltf files "
            "when present; falls back to cached GLB files otherwise."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(tempfile.mkdtemp(prefix="assetkit-animation-roundtrip-")),
        help="Directory for exported DAE files.",
    )
    args = parser.parse_args(argv)
    result = run_checks(
        args.sample_root.expanduser().resolve(),
        args.asset_cache.expanduser().resolve(),
        args.out.expanduser().resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"animation round-trip checks passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
