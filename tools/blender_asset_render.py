#!/usr/bin/env python3
"""Import an asset through the current source tree and render a repeatable preview."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "src"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from assetkit_blender.importer import import_assetkit_file  # noqa: E402
from assetkit_blender.load_options import make_load_options  # noqa: E402


def _look_at(obj: bpy.types.Object, point: Vector) -> None:
    obj.rotation_euler = (point - obj.location).to_track_quat("-Z", "Y").to_euler()


def _scene_bounds() -> tuple[Vector, Vector]:
    bpy.context.view_layer.update()
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    points = [
        obj.matrix_world @ obj.data.vertices[vertex_index].co
        for obj in objects
        for vertex_index in {
            vertex_index
            for polygon in obj.data.polygons
            for vertex_index in polygon.vertices
        }
    ]
    if not points:
        points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    return (
        Vector(tuple(min(point[axis] for point in points) for axis in range(3))),
        Vector(tuple(max(point[axis] for point in points) for axis in range(3))),
    )


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("usage: blender_asset_render.py -- INPUT OUTPUT.png")
    source, output = args
    bpy.ops.wm.read_factory_settings(use_empty=True)
    options = make_load_options(
        coordinate_system="Z_UP",
        coordinate_conversion="TRANSFORM",
        generate_normals=False,
        texture_loading="IMMEDIATE",
    )
    result = import_assetkit_file(
        source,
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
        raise RuntimeError(f"AssetKit could not import {source}")

    if os.environ.get("ASSETKIT_FORCE_OPAQUE") == "1":
        for material in bpy.data.materials:
            if hasattr(material, "surface_render_method"):
                material.surface_render_method = "DITHERED"
            material.diffuse_color[3] = 1.0
            material.use_backface_culling = True
            if material.node_tree:
                surface = material.node_tree.nodes.get("Principled BSDF")
                if surface and "Alpha" in surface.inputs:
                    for link in list(surface.inputs["Alpha"].links):
                        material.node_tree.links.remove(link)
                    surface.inputs["Alpha"].default_value = 1.0

    if os.environ.get("ASSETKIT_FORCE_ATTRIBUTE") == "1":
        for material in bpy.data.materials:
            if not material.node_tree:
                continue
            surface = material.node_tree.nodes.get("Principled BSDF")
            if not surface:
                continue
            for link in list(surface.inputs["Base Color"].links):
                material.node_tree.links.remove(link)
            attribute = material.node_tree.nodes.new("ShaderNodeAttribute")
            attribute.attribute_name = "Color"
            material.node_tree.links.new(attribute.outputs["Color"], surface.inputs["Base Color"])

    if os.environ.get("ASSETKIT_DELETE_WHITE_FACES") == "1":
        for obj in [item for item in bpy.context.scene.objects if item.type == "MESH"]:
            attribute = obj.data.color_attributes.get("Color")
            if attribute is None or attribute.domain != "CORNER":
                continue
            white_faces = {
                polygon.index
                for polygon in obj.data.polygons
                if polygon.loop_total > 0
                and all(
                    min(attribute.data[index].color[:3]) > 0.9
                    for index in polygon.loop_indices
                )
            }
            if not white_faces:
                continue
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            mesh.faces.ensure_lookup_table()
            bmesh.ops.delete(
                mesh,
                geom=[mesh.faces[index] for index in white_faces],
                context="FACES",
            )
            mesh.to_mesh(obj.data)
            mesh.free()

    if os.environ.get("ASSETKIT_FORCE_RED_COLOR") == "1":
        for obj in [item for item in bpy.context.scene.objects if item.type == "MESH"]:
            attribute = obj.data.color_attributes.get("Color")
            if attribute is None:
                continue
            for item in attribute.data:
                item.color = (0.35, 0.08, 0.025, 1.0)

    bounds_min, bounds_max = _scene_bounds()
    print(f"ASSETKIT_RENDER_BOUNDS min={tuple(bounds_min)} max={tuple(bounds_max)}", flush=True)
    center = (bounds_min + bounds_max) * 0.5
    size = bounds_max - bounds_min
    radius = max(float(size.length) * 0.5, 0.001)

    camera_data = bpy.data.cameras.new("AssetKit Diagnostic Camera")
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    bpy.context.scene.collection.objects.link(camera)
    direction = Vector((1.15, -1.35, 0.85)).normalized()
    camera.location = center + direction * radius * 2.35
    camera_data.lens = 52.0
    camera_data.clip_start = max(radius * 0.0001, 0.001)
    camera_data.clip_end = radius * 20.0
    _look_at(camera, center)
    bpy.context.scene.camera = camera

    key_data = bpy.data.lights.new("AssetKit Key", "AREA")
    key_data.energy = 1300.0
    key_data.shape = "DISK"
    key_data.size = radius * 1.2
    key = bpy.data.objects.new(key_data.name, key_data)
    bpy.context.scene.collection.objects.link(key)
    key.location = center + Vector((-0.7, -0.9, 1.6)).normalized() * radius * 2.0
    _look_at(key, center)

    fill_data = bpy.data.lights.new("AssetKit Fill", "AREA")
    fill_data.energy = 700.0
    fill_data.size = radius * 1.5
    fill = bpy.data.objects.new(fill_data.name, fill_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.location = center + Vector((1.0, 0.5, 0.8)).normalized() * radius * 2.0
    _look_at(fill, center)

    world = bpy.context.scene.world or bpy.data.worlds.new("AssetKit World")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.055, 0.055, 0.055, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.65

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(Path(output).resolve())
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.resolution_percentage = 100
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
