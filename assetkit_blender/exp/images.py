from __future__ import annotations

import os
from array import array
from pathlib import Path

import bmesh
import bpy

from ..assetkit import _native_module


class _ExportImageStore:
    def __init__(self, tmp_dir: Path):
        self._tmp_dir = tmp_dir
        self._cache: dict[int, str | None] = {}
        self._mr_cache: dict[tuple[int, int, int, int, int, int, float, float], str | None] = {}
        self._base_alpha_cache: dict[tuple[int, int, int, int, bool], str | None] = {}
        self._channel_cache: dict[tuple[int, int, int, float], str | None] = {}
        self._rgb_channel_cache: dict[tuple[int, int, float], str | None] = {}
        self._spec_gloss_cache: dict[tuple[int, int, int, int, bytes, float], str | None] = {}
        self._shader_bake_cache: dict[tuple[int, int, int, int, str], str | None] = {}
        self._lighting_bake_cache: dict[tuple[int, int, int, int, str], str | None] = {}
        self._counter = 0

    def path_for(self, image: bpy.types.Image) -> str | None:
        key = int(image.as_pointer())
        if key in self._cache:
            return self._cache[key]

        path = self._source_path(image)
        if path is None:
            path = self._write_temp_image(image)

        self._cache[key] = path
        return path

    def metallic_roughness_path(
        self,
        occlusion_image: bpy.types.Image | None,
        occlusion_channel: int,
        metallic_image: bpy.types.Image | None,
        metallic_channel: int,
        roughness_image: bpy.types.Image | None,
        roughness_channel: int,
        metallic_factor: float,
        roughness_factor: float,
        name: str,
    ) -> str | None:
        if occlusion_image is None and metallic_image is None and roughness_image is None:
            return None

        occ_key = int(occlusion_image.as_pointer()) if occlusion_image else 0
        metal_key = int(metallic_image.as_pointer()) if metallic_image else 0
        rough_key = int(roughness_image.as_pointer()) if roughness_image else 0
        key = (
            occ_key,
            int(occlusion_channel),
            metal_key,
            int(metallic_channel),
            rough_key,
            int(roughness_channel),
            float(metallic_factor),
            float(roughness_factor),
        )
        if key in self._mr_cache:
            return self._mr_cache[key]

        path = self._write_metallic_roughness(
            occlusion_image,
            occlusion_channel,
            metallic_image,
            metallic_channel,
            roughness_image,
            roughness_channel,
            metallic_factor,
            roughness_factor,
            name,
        )
        self._mr_cache[key] = path
        return path

    def base_color_alpha_path(
        self,
        base_image: bpy.types.Image | None,
        base_channel: int,
        alpha_image: bpy.types.Image,
        alpha_channel: int,
        name: str,
        invert_alpha: bool = False,
    ) -> str | None:
        base_key = int(base_image.as_pointer()) if base_image else 0
        alpha_key = int(alpha_image.as_pointer())
        key = (
            base_key,
            int(base_channel),
            alpha_key,
            int(alpha_channel),
            bool(invert_alpha),
        )
        if key in self._base_alpha_cache:
            return self._base_alpha_cache[key]

        path = self._write_base_color_alpha(
            base_image,
            base_channel,
            alpha_image,
            alpha_channel,
            name,
            invert_alpha,
        )
        self._base_alpha_cache[key] = path
        return path

    def channel_path(
        self,
        image: bpy.types.Image,
        source_channel: int,
        target_channel: int,
        name: str,
        fallback: float = 1.0,
    ) -> str | None:
        key = (
            int(image.as_pointer()),
            int(source_channel),
            int(target_channel),
            float(fallback),
        )
        if key in self._channel_cache:
            return self._channel_cache[key]

        path = self._write_channel(image, source_channel, target_channel, name, fallback)
        self._channel_cache[key] = path
        return path

    def rgb_channel_path(
        self,
        image: bpy.types.Image,
        source_channel: int,
        name: str,
        fallback: float = 1.0,
    ) -> str | None:
        key = (
            int(image.as_pointer()),
            int(source_channel),
            float(fallback),
        )
        if key in self._rgb_channel_cache:
            return self._rgb_channel_cache[key]

        path = self._write_rgb_channel(image, source_channel, name, fallback)
        self._rgb_channel_cache[key] = path
        return path

    def specular_glossiness_path(
        self,
        specular_image: bpy.types.Image | None,
        specular_channel: int,
        glossiness_image: bpy.types.Image | None,
        glossiness_channel: int,
        specular_color: bytes,
        glossiness_factor: float,
        name: str,
    ) -> str | None:
        spec_key = int(specular_image.as_pointer()) if specular_image else 0
        gloss_key = int(glossiness_image.as_pointer()) if glossiness_image else 0
        key = (
            spec_key,
            int(specular_channel),
            gloss_key,
            int(glossiness_channel),
            bytes(specular_color),
            float(glossiness_factor),
        )
        if key in self._spec_gloss_cache:
            return self._spec_gloss_cache[key]

        path = self._write_specular_glossiness(
            specular_image,
            specular_channel,
            glossiness_image,
            glossiness_channel,
            specular_color,
            glossiness_factor,
            name,
        )
        self._spec_gloss_cache[key] = path
        return path

    def shader_bake_path(
        self,
        context: bpy.types.Context,
        obj: bpy.types.Object,
        mesh: bpy.types.Mesh,
        material: bpy.types.Material,
        material_index: int,
        size: int,
        name: str,
        uv_name: str = "",
    ) -> str | None:
        if obj.type != "MESH":
            return None
        uv_layers = getattr(mesh, "uv_layers", None) if mesh is not None else None
        if uv_layers is None or len(uv_layers) == 0:
            return None

        size = max(64, min(8192, int(size)))
        key = (
            int(obj.as_pointer()),
            int(mesh.as_pointer()),
            int(material_index),
            int(size),
            str(uv_name or ""),
        )
        if key in self._shader_bake_cache:
            return self._shader_bake_cache[key]

        path = self._write_shader_bake(
            context,
            obj,
            mesh,
            material,
            int(material_index),
            size,
            name,
            str(uv_name or ""),
        )
        self._shader_bake_cache[key] = path
        return path

    def lighting_bake_path(
        self,
        context: bpy.types.Context,
        obj: bpy.types.Object,
        mesh: bpy.types.Mesh,
        material: bpy.types.Material,
        material_index: int,
        size: int,
        name: str,
        uv_name: str = "",
    ) -> str | None:
        if obj.type != "MESH":
            return None
        uv_layers = getattr(mesh, "uv_layers", None) if mesh is not None else None
        if uv_layers is None or len(uv_layers) == 0:
            return None

        size = max(64, min(8192, int(size)))
        key = (
            int(obj.as_pointer()),
            int(mesh.as_pointer()),
            int(material_index),
            int(size),
            str(uv_name or ""),
        )
        if key in self._lighting_bake_cache:
            return self._lighting_bake_cache[key]

        path = self._write_shader_bake(
            context,
            obj,
            mesh,
            material,
            int(material_index),
            size,
            name,
            str(uv_name or ""),
            "COMBINED",
            "lightingBake",
        )
        self._lighting_bake_cache[key] = path
        return path

    def _source_path(self, image: bpy.types.Image) -> str | None:
        if image.is_dirty:
            return None
        if image.source not in {"FILE", "SEQUENCE"} or not image.filepath_raw:
            return None
        path = bpy.path.abspath(image.filepath_raw, library=image.library)
        if not path or not os.path.isfile(path):
            return None
        if image.packed_file is not None:
            # Blender's glTF importer packs file-backed images but keeps
            # filepath_raw. Reuse the source only when the packed size still
            # matches; changed or packed-only images fall back to temp export.
            try:
                if int(image.packed_file.size) != os.path.getsize(path):
                    return None
            except (OSError, TypeError, ValueError):
                return None
        return path

    def _write_temp_image(self, image: bpy.types.Image) -> str | None:
        if image.packed_file is not None:
            packed = image.packed_file.data
            suffix = self._packed_suffix(packed)
            if suffix is not None:
                path = self._next_path(image.name, suffix)
                path.write_bytes(packed)
                return os.fspath(path)

        pixels = self._image_pixels(image)
        if pixels is not None:
            width, height, rgba = pixels
            return self._write_rgba_pixels(image.name, width, height, rgba)

        path = self._next_path(image.name, ".png")
        tmp_image = None
        try:
            tmp_image = image.copy()
            tmp_image.filepath_raw = os.fspath(path)
            tmp_image.file_format = "PNG"
            tmp_image.save()
            return os.fspath(path)
        except Exception:
            return None
        finally:
            if tmp_image is not None:
                bpy.data.images.remove(tmp_image)

    def _write_metallic_roughness(
        self,
        occlusion_image: bpy.types.Image | None,
        occlusion_channel: int,
        metallic_image: bpy.types.Image | None,
        metallic_channel: int,
        roughness_image: bpy.types.Image | None,
        roughness_channel: int,
        metallic_factor: float,
        roughness_factor: float,
        name: str,
    ) -> str | None:
        occ_pixels = self._image_pixels(occlusion_image) if occlusion_image else None
        metal_pixels = self._image_pixels(metallic_image) if metallic_image else None
        rough_pixels = self._image_pixels(roughness_image) if roughness_image else None
        if occlusion_image is not None and occ_pixels is None:
            return None
        if metallic_image is not None and metal_pixels is None:
            return None
        if roughness_image is not None and rough_pixels is None:
            return None

        width = max(
            occ_pixels[0] if occ_pixels else 1,
            metal_pixels[0] if metal_pixels else 1,
            rough_pixels[0] if rough_pixels else 1,
        )
        height = max(
            occ_pixels[1] if occ_pixels else 1,
            metal_pixels[1] if metal_pixels else 1,
            rough_pixels[1] if rough_pixels else 1,
        )
        pixels = _native_pack_metallic_roughness(
            width,
            height,
            occ_pixels,
            occlusion_channel,
            metal_pixels,
            metallic_channel,
            rough_pixels,
            roughness_channel,
            metallic_factor,
            roughness_factor,
        )
        if pixels is not None:
            return self._write_rgba_pixels(f"{name}_metallicRoughness", width, height, pixels)

        pixels = array("f", [0.0]) * (width * height * 4)

        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                pixels[offset] = self._sample_channel(
                    occ_pixels,
                    x,
                    y,
                    width,
                    height,
                    1.0,
                    occlusion_channel,
                )
                pixels[offset + 1] = self._sample_channel(
                    rough_pixels,
                    x,
                    y,
                    width,
                    height,
                    roughness_factor,
                    roughness_channel,
                )
                pixels[offset + 2] = self._sample_channel(
                    metal_pixels,
                    x,
                    y,
                    width,
                    height,
                    metallic_factor,
                    metallic_channel,
                )
                pixels[offset + 3] = 1.0

        return self._write_rgba_pixels(f"{name}_metallicRoughness", width, height, pixels)

    def _write_base_color_alpha(
        self,
        base_image: bpy.types.Image | None,
        base_channel: int,
        alpha_image: bpy.types.Image,
        alpha_channel: int,
        name: str,
        invert_alpha: bool,
    ) -> str | None:
        base_pixels = self._image_pixels(base_image) if base_image else None
        alpha_pixels = self._image_pixels(alpha_image)
        if base_image is not None and base_pixels is None:
            return None
        if alpha_pixels is None:
            return None

        width = max(base_pixels[0] if base_pixels else 1, alpha_pixels[0])
        height = max(base_pixels[1] if base_pixels else 1, alpha_pixels[1])
        pixels = _native_pack_base_color_alpha(
            width,
            height,
            base_pixels,
            base_channel,
            alpha_pixels,
            alpha_channel,
            invert_alpha,
        )
        if pixels is not None:
            return self._write_rgba_pixels(f"{name}_baseColorAlpha", width, height, pixels)

        pixels = array("f", [0.0]) * (width * height * 4)

        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                if base_channel == 0:
                    pixels[offset] = self._sample_channel(base_pixels, x, y, width, height, 1.0, 0)
                    pixels[offset + 1] = self._sample_channel(base_pixels, x, y, width, height, 1.0, 1)
                    pixels[offset + 2] = self._sample_channel(base_pixels, x, y, width, height, 1.0, 2)
                else:
                    value = self._sample_channel(
                        base_pixels,
                        x,
                        y,
                        width,
                        height,
                        1.0,
                        base_channel,
                    )
                    pixels[offset] = value
                    pixels[offset + 1] = value
                    pixels[offset + 2] = value
                alpha_value = self._sample_channel(
                    alpha_pixels,
                    x,
                    y,
                    width,
                    height,
                    1.0,
                    alpha_channel,
                )
                pixels[offset + 3] = 1.0 - alpha_value if invert_alpha else alpha_value

        return self._write_rgba_pixels(f"{name}_baseColorAlpha", width, height, pixels)

    def _write_channel(
        self,
        image: bpy.types.Image,
        source_channel: int,
        target_channel: int,
        name: str,
        fallback: float,
    ) -> str | None:
        image_pixels = self._image_pixels(image)
        if image_pixels is None:
            return None

        width, height, _rgba = image_pixels
        pixels = _native_pack_channel(
            width,
            height,
            image_pixels,
            source_channel,
            target_channel,
            fallback,
        )
        if pixels is not None:
            return self._write_rgba_pixels(f"{name}_channel", width, height, pixels)

        pixels = array("f", [1.0]) * (width * height * 4)
        if target_channel < 0 or target_channel > 3:
            target_channel = 0
        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                pixels[offset + target_channel] = self._sample_channel(
                    image_pixels,
                    x,
                    y,
                    width,
                    height,
                    fallback,
                    source_channel,
                )

        return self._write_rgba_pixels(f"{name}_channel", width, height, pixels)

    def _write_rgb_channel(
        self,
        image: bpy.types.Image,
        source_channel: int,
        name: str,
        fallback: float,
    ) -> str | None:
        image_pixels = self._image_pixels(image)
        if image_pixels is None:
            return None

        width, height, _rgba = image_pixels
        pixels = _native_pack_rgb_channel(
            width,
            height,
            image_pixels,
            source_channel,
            fallback,
        )
        if pixels is not None:
            return self._write_rgba_pixels(f"{name}_rgb", width, height, pixels)

        pixels = array("f", [1.0]) * (width * height * 4)
        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                value = self._sample_channel(
                    image_pixels,
                    x,
                    y,
                    width,
                    height,
                    fallback,
                    source_channel,
                )
                pixels[offset] = value
                pixels[offset + 1] = value
                pixels[offset + 2] = value

        return self._write_rgba_pixels(f"{name}_rgb", width, height, pixels)

    def _write_specular_glossiness(
        self,
        specular_image: bpy.types.Image | None,
        specular_channel: int,
        glossiness_image: bpy.types.Image | None,
        glossiness_channel: int,
        specular_color: bytes,
        glossiness_factor: float,
        name: str,
    ) -> str | None:
        spec_pixels = self._image_pixels(specular_image) if specular_image else None
        gloss_pixels = self._image_pixels(glossiness_image) if glossiness_image else None
        if specular_image is not None and spec_pixels is None:
            return None
        if glossiness_image is not None and gloss_pixels is None:
            return None

        width = max(spec_pixels[0] if spec_pixels else 1, gloss_pixels[0] if gloss_pixels else 1)
        height = max(spec_pixels[1] if spec_pixels else 1, gloss_pixels[1] if gloss_pixels else 1)
        pixels = _native_pack_specular_glossiness(
            width,
            height,
            spec_pixels,
            specular_channel,
            gloss_pixels,
            glossiness_channel,
            specular_color,
            glossiness_factor,
        )
        if pixels is not None:
            return self._write_rgba_pixels(f"{name}_specularGlossiness", width, height, pixels)

        spec = array("f")
        spec.frombytes(specular_color)
        while len(spec) < 4:
            spec.append(1.0)

        pixels = array("f", [1.0]) * (width * height * 4)
        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                if specular_image is None:
                    pixels[offset] = _clamp01(float(spec[0]))
                    pixels[offset + 1] = _clamp01(float(spec[1]))
                    pixels[offset + 2] = _clamp01(float(spec[2]))
                elif specular_channel == 0:
                    pixels[offset] = self._sample_channel(spec_pixels, x, y, width, height, spec[0], 0)
                    pixels[offset + 1] = self._sample_channel(spec_pixels, x, y, width, height, spec[1], 1)
                    pixels[offset + 2] = self._sample_channel(spec_pixels, x, y, width, height, spec[2], 2)
                else:
                    value = self._sample_channel(
                        spec_pixels,
                        x,
                        y,
                        width,
                        height,
                        1.0,
                        specular_channel,
                    )
                    pixels[offset] = value
                    pixels[offset + 1] = value
                    pixels[offset + 2] = value
                pixels[offset + 3] = self._sample_channel(
                    gloss_pixels,
                    x,
                    y,
                    width,
                    height,
                    glossiness_factor,
                    glossiness_channel,
                )

        return self._write_rgba_pixels(f"{name}_specularGlossiness", width, height, pixels)

    def _write_shader_bake(
        self,
        context: bpy.types.Context,
        obj: bpy.types.Object,
        mesh: bpy.types.Mesh,
        material: bpy.types.Material,
        material_index: int,
        size: int,
        name: str,
        uv_name: str,
        bake_type: str = "DIFFUSE",
        output_suffix: str = "shaderBake",
    ) -> str | None:
        scene = context.scene
        view_layer = context.view_layer
        image = None
        temp_nodes = []
        bake_obj = None
        bake_mesh = None
        old_active = view_layer.objects.active
        old_selected = tuple(context.selected_objects)
        old_engine = getattr(scene.render, "engine", None)
        cycles = getattr(scene, "cycles", None)
        old_cycles_samples = getattr(cycles, "samples", None) if cycles is not None else None

        try:
            bake_obj, bake_mesh = self._filtered_material_bake_object(
                context,
                obj,
                mesh,
                material,
                material_index,
                name,
                uv_name,
            )
            if bake_obj is None:
                return None

            image = bpy.data.images.new(
                f"##assetkit-bake:{name}##",
                int(size),
                int(size),
                alpha=True,
                float_buffer=False,
            )
            for slot in getattr(bake_obj, "material_slots", ()) or ():
                material = getattr(slot, "material", None)
                if material is None or not material.use_nodes or material.node_tree is None:
                    continue
                nodes = material.node_tree.nodes
                active_node = getattr(nodes, "active", None)
                selected_nodes = tuple(node for node in nodes if getattr(node, "select", False))
                bake_node = nodes.new("ShaderNodeTexImage")
                bake_node.name = "##assetkit_bake_target##"
                bake_node.label = "AssetKit Bake Target"
                bake_node.image = image
                for node in selected_nodes:
                    node.select = False
                bake_node.select = True
                nodes.active = bake_node
                temp_nodes.append((nodes, bake_node, active_node, selected_nodes))

            if not temp_nodes:
                return None

            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode="OBJECT")
            for selected in old_selected:
                selected.select_set(False)
            bake_obj.select_set(True)
            view_layer.objects.active = bake_obj

            try:
                scene.render.engine = "CYCLES"
            except Exception:
                pass
            if bake_type != "COMBINED" and cycles is not None and old_cycles_samples is not None:
                cycles.samples = min(max(int(old_cycles_samples), 1), 32)

            if bake_type == "COMBINED":
                bpy.ops.object.bake(type="COMBINED", margin=4, use_clear=True)
            else:
                try:
                    bpy.ops.object.bake(
                        type="DIFFUSE",
                        pass_filter={"COLOR"},
                        margin=4,
                        use_clear=True,
                    )
                except TypeError:
                    bpy.ops.object.bake(type="DIFFUSE", margin=4, use_clear=True)

            pixels = self._image_pixels(image)
            if pixels is None:
                return None
            width, height, rgba = pixels
            return self._write_rgba_pixels(f"{name}_{output_suffix}", width, height, rgba)
        except Exception:
            return None
        finally:
            for nodes, bake_node, active_node, selected_nodes in reversed(temp_nodes):
                try:
                    nodes.remove(bake_node)
                except Exception:
                    pass
                try:
                    nodes.active = active_node
                except Exception:
                    pass
                try:
                    for node in selected_nodes:
                        node.select = True
                except Exception:
                    pass
            if image is not None:
                try:
                    bpy.data.images.remove(image)
                except Exception:
                    pass
            if old_cycles_samples is not None and cycles is not None:
                try:
                    cycles.samples = old_cycles_samples
                except Exception:
                    pass
            if old_engine is not None:
                try:
                    scene.render.engine = old_engine
                except Exception:
                    pass
            try:
                if bake_obj is not None:
                    bake_obj.select_set(False)
                for selected in old_selected:
                    selected.select_set(True)
                view_layer.objects.active = old_active
            except Exception:
                pass
            if bake_obj is not None:
                try:
                    bpy.data.objects.remove(bake_obj, do_unlink=True)
                except Exception:
                    pass
            if bake_mesh is not None:
                try:
                    bpy.data.meshes.remove(bake_mesh)
                except Exception:
                    pass

    def _filtered_material_bake_object(
        self,
        context: bpy.types.Context,
        obj: bpy.types.Object,
        mesh: bpy.types.Mesh,
        material: bpy.types.Material,
        material_index: int,
        name: str,
        uv_name: str,
    ) -> tuple[bpy.types.Object | None, bpy.types.Mesh | None]:
        if mesh is None or material is None or material_index < 0:
            return None, None

        polygons = getattr(mesh, "polygons", None)
        if polygons is None or len(polygons) == 0:
            return None, None
        found = False
        for poly in polygons:
            if int(poly.material_index) == material_index:
                found = True
                break
        if not found:
            return None, None

        filtered_mesh = bpy.data.meshes.new(f"##assetkit-bake-mesh:{name}##")
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.faces.ensure_lookup_table()
            delete = [
                face
                for face in bm.faces
                if int(face.material_index) != int(material_index)
            ]
            if len(delete) >= len(bm.faces):
                try:
                    bpy.data.meshes.remove(filtered_mesh)
                except Exception:
                    pass
                return None, None
            if delete:
                bmesh.ops.delete(bm, geom=delete, context="FACES_ONLY")
            for face in bm.faces:
                face.material_index = 0
            bm.to_mesh(filtered_mesh)
        except Exception:
            try:
                bpy.data.meshes.remove(filtered_mesh)
            except Exception:
                pass
            return None, None
        finally:
            bm.free()

        filtered_mesh.update()
        self._set_bake_uv_layer(filtered_mesh, uv_name)
        filtered_mesh.materials.append(material)
        bake_obj = bpy.data.objects.new(f"##assetkit-bake-object:{name}##", filtered_mesh)
        bake_obj.matrix_world = obj.matrix_world.copy()
        bake_obj.hide_render = False
        bake_obj.hide_viewport = False
        try:
            context.collection.objects.link(bake_obj)
        except Exception:
            bpy.context.scene.collection.objects.link(bake_obj)
        return bake_obj, filtered_mesh

    @staticmethod
    def _set_bake_uv_layer(mesh: bpy.types.Mesh, uv_name: str) -> None:
        if not uv_name:
            return
        uv_layers = getattr(mesh, "uv_layers", None)
        if uv_layers is None or len(uv_layers) == 0:
            return
        for index, layer in enumerate(uv_layers):
            if layer.name != uv_name:
                continue
            try:
                uv_layers.active_index = index
            except Exception:
                pass
            try:
                uv_layers.active = layer
            except Exception:
                pass
            try:
                uv_layers.active_render = layer
            except Exception:
                pass
            return

    def _write_rgba_pixels(self, name: str, width: int, height: int, pixels: array) -> str | None:
        path = self._next_path(name, ".png")
        image = None
        try:
            image = bpy.data.images.new(f"##assetkit-export:{name}##", width, height, alpha=True)
            image.pixels.foreach_set(pixels)
            image.update()
            image.filepath_raw = os.fspath(path)
            image.file_format = "PNG"
            image.save()
            return os.fspath(path)
        except Exception:
            return None
        finally:
            if image is not None:
                bpy.data.images.remove(image)

    @staticmethod
    def _image_pixels(image: bpy.types.Image | None) -> tuple[int, int, array] | None:
        if image is None:
            return None
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            return None
        try:
            pixels = array("f", [0.0]) * (width * height * 4)
            image.pixels.foreach_get(pixels)
        except Exception:
            return None
        return width, height, pixels

    @staticmethod
    def _sample_channel(
        image_data: tuple[int, int, array] | None,
        x: int,
        y: int,
        width: int,
        height: int,
        fallback: float,
        channel: int = 0,
    ) -> float:
        if image_data is None:
            return _clamp01(float(fallback))
        if channel < 0 or channel > 3:
            channel = 0
        src_width, src_height, pixels = image_data
        src_x = min(src_width - 1, max(0, (x * src_width) // width))
        src_y = min(src_height - 1, max(0, (y * src_height) // height))
        return _clamp01(float(pixels[(src_y * src_width + src_x) * 4 + channel]))

    def _next_path(self, name: str, suffix: str) -> Path:
        self._counter += 1
        safe = self._safe_name(name) or "image"
        return self._tmp_dir / f"{self._counter:04d}_{safe}{suffix}"

    @staticmethod
    def _packed_suffix(data: bytes) -> str | None:
        if data.startswith(b"\x89PNG"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        return None

    @staticmethod
    def _safe_name(name: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in "._-" else "_"
            for ch in name
        ).strip("._-")


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _native_pack_metallic_roughness(
    width: int,
    height: int,
    occ_pixels: tuple[int, int, array] | None,
    occlusion_channel: int,
    metal_pixels: tuple[int, int, array] | None,
    metallic_channel: int,
    rough_pixels: tuple[int, int, array] | None,
    roughness_channel: int,
    metallic_factor: float,
    roughness_factor: float,
) -> array | None:
    module = _native_module()
    if module is None:
        return None
    helper = getattr(module, "export_pack_metallic_roughness", None)
    if helper is None:
        return None
    return helper(
        int(width),
        int(height),
        occ_pixels,
        int(occlusion_channel),
        metal_pixels,
        int(metallic_channel),
        rough_pixels,
        int(roughness_channel),
        float(metallic_factor),
        float(roughness_factor),
    )


def _native_pack_base_color_alpha(
    width: int,
    height: int,
    base_pixels: tuple[int, int, array] | None,
    base_channel: int,
    alpha_pixels: tuple[int, int, array],
    alpha_channel: int,
    invert_alpha: bool,
) -> array | None:
    module = _native_module()
    if module is None:
        return None
    helper = getattr(module, "export_pack_base_color_alpha", None)
    if helper is None:
        return None
    return helper(
        int(width),
        int(height),
        base_pixels,
        int(base_channel),
        alpha_pixels,
        int(alpha_channel),
        bool(invert_alpha),
    )


def _native_pack_channel(
    width: int,
    height: int,
    image_pixels: tuple[int, int, array],
    source_channel: int,
    target_channel: int,
    fallback: float,
) -> array | None:
    module = _native_module()
    if module is None:
        return None
    helper = getattr(module, "export_pack_channel", None)
    if helper is None:
        return None
    return helper(
        int(width),
        int(height),
        image_pixels,
        int(source_channel),
        int(target_channel),
        float(fallback),
    )


def _native_pack_rgb_channel(
    width: int,
    height: int,
    image_pixels: tuple[int, int, array],
    source_channel: int,
    fallback: float,
) -> array | None:
    module = _native_module()
    if module is None:
        return None
    helper = getattr(module, "export_pack_rgb_channel", None)
    if helper is None:
        return None
    return helper(
        int(width),
        int(height),
        image_pixels,
        int(source_channel),
        float(fallback),
    )


def _native_pack_specular_glossiness(
    width: int,
    height: int,
    spec_pixels: tuple[int, int, array] | None,
    specular_channel: int,
    gloss_pixels: tuple[int, int, array] | None,
    glossiness_channel: int,
    specular_color: bytes,
    glossiness_factor: float,
) -> array | None:
    module = _native_module()
    if module is None:
        return None
    helper = getattr(module, "export_pack_specular_glossiness", None)
    if helper is None:
        return None
    return helper(
        int(width),
        int(height),
        spec_pixels,
        int(specular_channel),
        gloss_pixels,
        int(glossiness_channel),
        specular_color,
        float(glossiness_factor),
    )
