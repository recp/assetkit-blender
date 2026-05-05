from __future__ import annotations

from array import array

import bpy
from mathutils import Matrix

from .assetkit import AssetKit, MeshPrimitiveData, native_load_meshes


def import_assetkit_file(filepath: str, library_path: str = "") -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []

    primitives = native_load_meshes(filepath) if not library_path else None
    if primitives is None:
        kit = AssetKit(library_path or None)
        primitives = kit.load_meshes(filepath)

    for primitive in primitives:
        obj = _create_mesh_object(primitive)
        objects.append(obj)

    return objects


def _create_mesh_object(data: MeshPrimitiveData) -> bpy.types.Object:
    if data.vertices_f32 and data.indices_u32:
        return _create_mesh_object_bulk(data)

    mesh = bpy.data.meshes.new(data.name)
    mesh.from_pydata(data.vertices, [], data.faces)
    mesh.update(calc_edges=True)

    if data.uvs and len(data.uvs) >= len(mesh.loops):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, uv in enumerate(data.uvs[: len(mesh.loops)]):
            uv_layer.data[loop_index].uv = (uv[0], 1.0 - uv[1])

    if data.normals and len(data.normals) >= len(mesh.loops):
        mesh.normals_split_custom_set(data.normals[: len(mesh.loops)])
        for poly in mesh.polygons:
            poly.use_smooth = True

    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_mesh_object_bulk(data: MeshPrimitiveData) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(data.name)

    mesh.vertices.add(data.vertex_count)
    mesh.loops.add(data.loop_count)
    mesh.polygons.add(data.face_count)

    vertices = _buffer_view(data.vertices_f32, "f")
    indices = _buffer_view(data.indices_u32, "i")
    loop_starts = _buffer_view(data.loop_starts_i32, "i")
    loop_totals = _buffer_view(data.loop_totals_i32, "i")

    if vertices is None or indices is None:
        raise RuntimeError("AssetKit native bridge returned incomplete mesh buffers")
    if loop_starts is None or loop_totals is None:
        loop_starts = array("i", range(0, data.loop_count, 3))
        loop_totals = array("i", [3]) * data.face_count

    mesh.vertices.foreach_set("co", vertices)
    mesh.loops.foreach_set("vertex_index", indices)
    mesh.polygons.foreach_set("loop_start", loop_starts)
    mesh.polygons.foreach_set("loop_total", loop_totals)

    if data.uvs_f32:
        uvs = _buffer_view(data.uvs_f32, "f")
        uv_layer = mesh.uv_layers.new(name="UVMap")
        if uvs is not None:
            uv_layer.data.foreach_set("uv", uvs)

    mesh.update(calc_edges=True)

    if data.normals_f32:
        normals = _buffer_view(data.normals_f32, "f")
        try:
            if normals is not None:
                mesh.corner_normals.foreach_set("vector", normals)
                for poly in mesh.polygons:
                    poly.use_smooth = True
        except Exception:
            pass

    obj = bpy.data.objects.new(data.object_name or data.name, mesh)
    _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _apply_matrix(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    if not data.matrix_f32:
        return

    values = _buffer_view(data.matrix_f32, "f")
    if values is None or len(values) != 16:
        return

    obj.matrix_local = Matrix(
        (
            (values[0], values[4], values[8], values[12]),
            (values[1], values[5], values[9], values[13]),
            (values[2], values[6], values[10], values[14]),
            (values[3], values[7], values[11], values[15]),
        )
    )


def _buffer_view(buffer: object, fmt: str) -> memoryview | None:
    if not buffer:
        return None

    view = buffer if isinstance(buffer, memoryview) else memoryview(buffer)
    if len(view) == 0:
        return None
    if view.format == fmt and view.ndim == 1:
        return view
    return view.cast(fmt)


def _create_material(data: MeshPrimitiveData) -> bpy.types.Material | None:
    if not data.material_name:
        return None

    mat = bpy.data.materials.get(data.material_name) or bpy.data.materials.new(data.material_name)
    mat.use_nodes = True
    mat.use_backface_culling = not data.double_sided
    if data.alpha_mode == 1:
        mat.blend_method = "BLEND"
    elif data.alpha_mode == 2:
        mat.blend_method = "CLIP"
        mat.alpha_threshold = data.alpha_cutoff

    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    _set_input(bsdf, "Base Color", data.base_color)
    _set_input(bsdf, "Metallic", data.metallic)
    _set_input(bsdf, "Roughness", data.roughness)
    _set_input(bsdf, "Alpha", data.base_color[3])
    _set_input(bsdf, "Emission Color", (*data.emissive_color, 1.0))

    if data.base_color_texture:
        _link_image(mat, bsdf, data.base_color_texture, "Base Color", colorspace="sRGB")
    if data.metallic_roughness_texture:
        _link_image(mat, bsdf, data.metallic_roughness_texture, "Roughness", colorspace="Non-Color")
    if data.emissive_texture:
        _link_image(mat, bsdf, data.emissive_texture, "Emission Color", colorspace="sRGB")

    return mat


def _set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket:
        socket.default_value = value


def _link_image(mat: bpy.types.Material, target, path: str, input_name: str, colorspace: str) -> None:
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return

    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    socket = target.inputs.get(input_name)
    if socket:
        links.new(tex.outputs["Color"], socket)
