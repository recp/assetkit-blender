#!/usr/bin/env python3
"""Measure AssetKit import completion and first foreground viewport redraw.

Run with a foreground Blender instance so material preview and GPU upload are
included:

  /Applications/Blender.app/Contents/MacOS/Blender --factory-startup \
    --python tools/blender_interactive_import_profile.py -- \
    /path/to/model.dae --texture-loading DEFERRED
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assetkit_blender import importer as assetkit_importer  # noqa: E402
from assetkit_blender.assetkit import probe_file_type  # noqa: E402
from assetkit_blender.enums import AK_FILE_TYPE_COLLADA  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Asset file to import")
    parser.add_argument(
        "--texture-loading",
        choices=("IMMEDIATE", "DEFERRED"),
        default="DEFERRED",
    )
    parser.add_argument(
        "--shading",
        choices=("AUTO", "SMOOTH", "FLAT", "AS_IS"),
        default="AS_IS",
    )
    parser.add_argument(
        "--build-mode",
        choices=("AUTO", "PROGRESSIVE", "BLOCKING"),
        default="AUTO",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args(argv)


class InteractiveProfile:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.path = Path(args.path).expanduser().resolve()
        self.started_at = 0.0
        self.imported_at = 0.0
        self.objects = []
        self.finished = False

    def start(self) -> None:
        if not self.path.is_file():
            raise SystemExit(f"Missing input: {self.path}")

        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        options = make_load_options(texture_loading=self.args.texture_loading)
        self.started_at = time.perf_counter()
        use_blocking = self.args.build_mode == "BLOCKING" or (
            self.args.build_mode == "AUTO"
            and probe_file_type(self.path) == AK_FILE_TYPE_COLLADA
        )
        if use_blocking:
            try:
                self.on_complete(
                    assetkit_importer.import_assetkit_file(
                        os.fspath(self.path),
                        "",
                        options,
                        collection=bpy.context.collection,
                        focus_mode="EMPTY_SCENE",
                        placement_mode="AS_AUTHORED",
                        scene_was_empty=True,
                        select_imported=False,
                        shading_mode=self.args.shading,
                        set_viewport_shading=True,
                        clean_viewport_overlays=True,
                        fit_timeline=False,
                    )
                )
            except Exception as exc:
                self.on_error(exc)
                return
        else:
            assetkit_importer.import_assetkit_file_progressive(
                os.fspath(self.path),
                "",
                options,
                collection=bpy.context.collection,
                batch_size=128,
                focus_mode="EMPTY_SCENE",
                placement_mode="AS_AUTHORED",
                scene_was_empty=True,
                select_imported=False,
                shading_mode=self.args.shading,
                set_viewport_shading=True,
                clean_viewport_overlays=True,
                fit_timeline=False,
                on_complete=self.on_complete,
                on_error=self.on_error,
            )
        bpy.app.timers.register(self.poll, first_interval=0.020)

    def on_complete(self, objects) -> None:
        self.objects = list(objects or ())
        self.imported_at = time.perf_counter()

    def on_error(self, exc: Exception) -> None:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), flush=True)
        self.finished = True
        bpy.app.timers.register(self.quit, first_interval=0.01)

    def poll(self) -> float | None:
        if self.finished:
            return None
        now = time.perf_counter()
        if now - self.started_at > max(1.0, float(self.args.timeout)):
            print(json.dumps({"error": "interactive import timeout"}, sort_keys=True), flush=True)
            self.finished = True
            bpy.app.timers.register(self.quit, first_interval=0.01)
            return None
        if not self.imported_at:
            return 0.020

        pending_materials = len(assetkit_importer._DEFERRED_MATERIAL_NODE_TASKS)
        pending_textures = len(assetkit_importer._DEFERRED_TEXTURE_KEYS)
        pending_normals = len(assetkit_importer._DEFERRED_NORMAL_TASKS)
        if pending_materials or pending_textures or pending_normals:
            return 0.020

        redraw_started_at = time.perf_counter()
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        try:
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
        except Exception:
            pass
        ready_at = time.perf_counter()

        texture_nodes = 0
        assigned_texture_nodes = 0
        dds_images = 0
        dds_channel_packed = 0
        bbr_metal_path = ""
        for material in bpy.data.materials:
            if not material.node_tree:
                continue
            for node in material.node_tree.nodes:
                if node.type != "TEX_IMAGE":
                    continue
                texture_nodes += 1
                if node.image is not None:
                    assigned_texture_nodes += 1
        for image in bpy.data.images:
            path = image.get("assetkit_source_path") or image.filepath
            if str(path or "").lower().endswith(".dds"):
                dds_images += 1
                if image.alpha_mode == "CHANNEL_PACKED":
                    dds_channel_packed += 1
                if Path(str(path)).name == "bbr_metal-2048.dds":
                    bbr_metal_path = str(path)

        print(
            json.dumps(
                {
                    "file": os.fspath(self.path),
                    "texture_loading": self.args.texture_loading,
                    "build_mode": self.args.build_mode,
                    "objects": len(self.objects),
                    "meshes": len(bpy.data.meshes),
                    "materials": len(bpy.data.materials),
                    "images": len(bpy.data.images),
                    "dds_images": dds_images,
                    "dds_channel_packed": dds_channel_packed,
                    "bbr_metal_path": bbr_metal_path,
                    "texture_nodes": texture_nodes,
                    "assigned_texture_nodes": assigned_texture_nodes,
                    "missing_texture_nodes": texture_nodes - assigned_texture_nodes,
                    "import_complete_ms": (self.imported_at - self.started_at) * 1000.0,
                    "viewport_ready_ms": (ready_at - self.started_at) * 1000.0,
                    "forced_redraw_ms": (ready_at - redraw_started_at) * 1000.0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        self.finished = True
        bpy.app.timers.register(self.quit, first_interval=0.05)
        return None

    @staticmethod
    def quit() -> None:
        bpy.ops.wm.quit_blender()
        return None


def main(argv: list[str]) -> None:
    profile = InteractiveProfile(parse_args(argv))
    bpy.app.timers.register(profile.start, first_interval=0.01)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
