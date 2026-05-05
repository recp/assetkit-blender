from __future__ import annotations

from array import array

import bpy
from mathutils import Matrix

from .assetkit import AssetKit, MeshPrimitiveData, native_load_meshes

_ANIM_TRANSLATION = 1
_ANIM_ROTATION_QUAT = 2
_ANIM_SCALE = 3
_INTERPOLATION_LINEAR = 1
_INTERPOLATION_STEP = 6


def import_assetkit_file(filepath: str, library_path: str = "") -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []

    primitives = native_load_meshes(filepath) if not library_path else None
    if primitives is None:
        kit = AssetKit(library_path or None)
        primitives = kit.load_meshes(filepath)

    coord_root = _create_coord_root(primitives)
    for primitive in primitives:
        obj = _create_mesh_object(primitive, coord_root)
        objects.append(obj)

    return objects


def _create_mesh_object(data: MeshPrimitiveData, parent: bpy.types.Object | None = None) -> bpy.types.Object:
    if data.vertices_f32 and data.indices_u32:
        return _create_mesh_object_bulk(data, parent)

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
    _set_parent(obj, parent)
    _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)
    _apply_animation(obj, data)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_mesh_object_bulk(data: MeshPrimitiveData, parent: bpy.types.Object | None = None) -> bpy.types.Object:
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
    _set_parent(obj, parent)
    _apply_matrix(obj, data)
    material = _create_material(data)
    if material:
        mesh.materials.append(material)
    _apply_animation(obj, data)

    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _create_coord_root(primitives: list[MeshPrimitiveData]) -> bpy.types.Object | None:
    for primitive in primitives:
        matrix = _matrix_from_buffer(primitive.coord_matrix_f32)
        if matrix is None:
            continue

        root = bpy.data.objects.new("AssetKit Coordinates", None)
        root.empty_display_type = "ARROWS"
        root.empty_display_size = 0.5
        root.matrix_local = matrix
        bpy.context.collection.objects.link(root)
        return root

    return None


def _set_parent(obj: bpy.types.Object, parent: bpy.types.Object | None) -> None:
    if not parent:
        return

    obj.parent = parent
    obj.matrix_parent_inverse.identity()


def _apply_matrix(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    matrix = _matrix_from_buffer(data.matrix_f32)
    if matrix is None:
        return

    obj.matrix_local = matrix


def _matrix_from_buffer(buffer: object) -> Matrix | None:
    if not buffer:
        return None

    values = _buffer_view(buffer, "f")
    if values is None or len(values) != 16:
        return None

    return Matrix(
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


def _apply_animation(obj: bpy.types.Object, data: MeshPrimitiveData) -> None:
    channels = data.anim_channels or []
    if not channels:
        return

    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    start_frame = 0.0

    if any(int(channel.get("target") or 0) == _ANIM_ROTATION_QUAT for channel in channels):
        obj.rotation_mode = "QUATERNION"

    obj.animation_data_create()
    action = bpy.data.actions.new(f"{obj.name}_AssetKit")
    obj.animation_data.action = action
    end_frame = scene.frame_end

    for channel in channels:
        target = int(channel.get("target") or 0)
        path, width = _anim_target_path(target)
        if not path:
            continue

        count = int(channel.get("count") or 0)
        value_width = int(channel.get("value_width") or 0)
        target_offset = int(channel.get("target_offset") or 0)
        is_partial = bool(channel.get("is_partial"))
        times = _buffer_view(channel.get("times_f32") or b"", "f")
        values = _buffer_view(channel.get("values_f32") or b"", "f")
        if count <= 0 or value_width <= 0 or times is None or values is None:
            continue

        interpolation = _blender_interpolation(int(channel.get("interpolation") or 0))
        component_count = 1 if is_partial else min(width - target_offset, value_width)
        for component in range(component_count):
            target_index = target_offset + component
            value_index = 0 if is_partial else component
            fcurve = _ensure_fcurve(action, obj, path, target_index)
            coords = array("f", [0.0]) * (count * 2)
            for key_index in range(count):
                coords[key_index * 2] = start_frame + times[key_index] * fps
                coords[key_index * 2 + 1] = values[key_index * value_width + value_index]

            fcurve.keyframe_points.add(count)
            fcurve.keyframe_points.foreach_set("co", coords)
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation
            fcurve.update()

        end_frame = max(end_frame, int(start_frame + times[count - 1] * fps + 0.5))

    if end_frame > scene.frame_end:
        scene.frame_end = end_frame


def _ensure_fcurve(action: bpy.types.Action, obj: bpy.types.Object, data_path: str, index: int):
    ensure = getattr(action, "fcurve_ensure_for_datablock", None)
    if ensure:
        return ensure(obj, data_path, index=index, group_name="Transform")
    return action.fcurves.new(data_path=data_path, index=index, action_group="Transform")


def _anim_target_path(target: int) -> tuple[str, int]:
    if target == _ANIM_TRANSLATION:
        return "location", 3
    if target == _ANIM_ROTATION_QUAT:
        return "rotation_quaternion", 4
    if target == _ANIM_SCALE:
        return "scale", 3
    return "", 0


def _blender_interpolation(interpolation: int) -> str:
    if interpolation == _INTERPOLATION_STEP:
        return "CONSTANT"
    if interpolation == _INTERPOLATION_LINEAR:
        return "LINEAR"
    return "LINEAR"


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
        _link_base_color_texture(mat, bsdf, data)
    if data.metallic_roughness_texture:
        _link_metallic_roughness_texture(mat, bsdf, data.metallic_roughness_texture)
    if data.normal_texture:
        _link_normal_texture(mat, bsdf, data.normal_texture, data.normal_scale)
    if data.emissive_texture:
        _link_image(mat, bsdf, data.emissive_texture, "Emission Color", colorspace="sRGB")

    return mat


def _set_input(node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket:
        socket.default_value = value


def _link_image(mat: bpy.types.Material, target, path: str, input_name: str, colorspace: str) -> None:
    tex = _image_texture_node(mat, path, colorspace)
    if not tex:
        return

    socket = target.inputs.get(input_name)
    if socket:
        mat.node_tree.links.new(tex.outputs["Color"], socket)


def _link_base_color_texture(mat: bpy.types.Material, bsdf, data: MeshPrimitiveData) -> None:
    tex = _image_texture_node(mat, data.base_color_texture, "sRGB")
    if not tex:
        return

    links = mat.node_tree.links
    base_color = bsdf.inputs.get("Base Color")
    alpha = bsdf.inputs.get("Alpha")
    if base_color:
        links.new(tex.outputs["Color"], base_color)
    if data.alpha_mode and alpha and "Alpha" in tex.outputs:
        links.new(tex.outputs["Alpha"], alpha)


def _link_metallic_roughness_texture(mat: bpy.types.Material, bsdf, path: str) -> None:
    tex = _image_texture_node(mat, path, "Non-Color")
    if not tex:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    separate = nodes.new("ShaderNodeSeparateColor")
    links.new(tex.outputs["Color"], separate.inputs["Color"])

    roughness = bsdf.inputs.get("Roughness")
    metallic = bsdf.inputs.get("Metallic")
    if roughness:
        links.new(separate.outputs["Green"], roughness)
    if metallic:
        links.new(separate.outputs["Blue"], metallic)


def _link_normal_texture(mat: bpy.types.Material, bsdf, path: str, strength: float) -> None:
    tex = _image_texture_node(mat, path, "Non-Color")
    if not tex:
        return

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    normal_map = nodes.new("ShaderNodeNormalMap")
    normal_map.inputs["Strength"].default_value = strength
    links.new(tex.outputs["Color"], normal_map.inputs["Color"])
    normal = bsdf.inputs.get("Normal")
    if normal:
        links.new(normal_map.outputs["Normal"], normal)


def _image_texture_node(mat: bpy.types.Material, path: str, colorspace: str):
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except RuntimeError:
        return None

    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass

    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    return tex
