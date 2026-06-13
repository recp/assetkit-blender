from __future__ import annotations

import os

import bpy
from bpy_extras.io_utils import ExportHelper

from ..assetkit import AssetKitError
from ..enums import (
    AK_DAE_EXPORT_INDEX_AUTO,
    AK_DAE_EXPORT_INDEX_MULTI,
    AK_DAE_EXPORT_INDEX_SINGLE,
    AK_DAE_EXPORT_VERSION_1_4,
    AK_DAE_EXPORT_VERSION_1_5,
    AK_DAE_EXPORT_VERSION_AUTO,
)
from ..load_options import _coord_conversion_id, _coord_system_id
from .exporter import EXPORT_FORMATS, export_scene, file_type_from_format, suffix_from_format

_DAE_VERSION_VALUES = {
    "AUTO": AK_DAE_EXPORT_VERSION_AUTO,
    "1_4": AK_DAE_EXPORT_VERSION_1_4,
    "1_5": AK_DAE_EXPORT_VERSION_1_5,
}

_DAE_INDEX_MODE_VALUES = {
    "AUTO": AK_DAE_EXPORT_INDEX_AUTO,
    "MULTI": AK_DAE_EXPORT_INDEX_MULTI,
    "SINGLE": AK_DAE_EXPORT_INDEX_SINGLE,
}

_FORMAT_BY_SUFFIX = {
    suffix.lower(): identifier
    for identifier, _name, _description, _file_type, suffix in EXPORT_FORMATS
}

_MESH_TRANSFORM_FORMATS = {"OBJ", "STL", "PLY"}
_APPLY_MODIFIER_FORMATS = {"GLTF", "GLB", "3MF", "DAE", "OBJ", "STL", "PLY"}
_SCENE_DATA_FORMATS = {"GLTF", "GLB", "DAE"}
_CUSTOM_PROPERTY_FORMATS = {"GLTF", "GLB", "3MF", "DAE"}
_MATERIAL_FORMATS = {"GLTF", "GLB", "3MF", "DAE", "OBJ"}
_MESH_DATA_FORMATS = {"GLTF", "GLB", "3MF", "DAE", "OBJ", "PLY"}
_ANIMATION_FORMATS = {"GLTF", "GLB", "DAE"}

_FORWARD_AXIS_ITEMS = (
    ("X", "X", "Use +X as forward"),
    ("Y", "Y", "Use +Y as forward"),
    ("Z", "Z", "Use +Z as forward"),
    ("-X", "-X", "Use -X as forward"),
    ("-Y", "-Y", "Use -Y as forward"),
    ("-Z", "-Z", "Use -Z as forward"),
)

_UP_AXIS_ITEMS = (
    ("X", "X", "Use +X as up"),
    ("Y", "Y", "Use +Y as up"),
    ("Z", "Z", "Use +Z as up"),
    ("-X", "-X", "Use -X as up"),
    ("-Y", "-Y", "Use -Y as up"),
    ("-Z", "-Z", "Use -Z as up"),
)


def _format_default_apply_modifiers(export_format: str) -> bool:
    return export_format in _APPLY_MODIFIER_FORMATS


def _on_export_format_changed(self, _context) -> None:
    self.apply_modifiers = _format_default_apply_modifiers(self.export_format)


def _draw_panel(layout, panel_id: str, title: str, *, default_closed: bool = True):
    panel = getattr(layout, "panel", None)
    if panel is None:
        box = layout.box()
        box.label(text=title)
        return box

    header, body = panel(panel_id, default_closed=default_closed)
    header.label(text=title)
    return body


def _draw_toggle_panel(
    layout,
    operator,
    panel_id: str,
    prop_name: str,
    title: str,
    *,
    default_closed: bool = True,
):
    panel = getattr(layout, "panel", None)
    if panel is None:
        box = layout.box()
        box.prop(operator, prop_name)
        box.active = bool(getattr(operator, prop_name))
        return box

    header, body = panel(panel_id, default_closed=default_closed)
    header.use_property_split = False
    header.prop(operator, prop_name, text="")
    header.label(text=title)
    if body:
        body.active = bool(getattr(operator, prop_name))
    return body


class ASSETKIT_OT_export_assetkit(bpy.types.Operator, ExportHelper):
    bl_idname = "assetkit.export_assetkit"
    bl_label = "Export AssetKit"
    bl_options = {"REGISTER"}

    filename_ext = ".gltf"
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply;*.3mf",
        options={"HIDDEN"},
    )
    assetkit_last_filepath: bpy.props.StringProperty(
        default="",
        options={"HIDDEN"},
    )
    assetkit_last_export_format: bpy.props.StringProperty(
        default="",
        options={"HIDDEN"},
    )
    export_format: bpy.props.EnumProperty(
        name="Format",
        description="AssetKit export format",
        items=tuple(
            (identifier, name, description)
            for identifier, name, description, _file_type, _suffix in EXPORT_FORMATS
        ),
        default="GLTF",
        update=_on_export_format_changed,
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=False,
    )
    export_visible: bpy.props.BoolProperty(
        name="Visible Objects",
        description="Export visible objects",
        default=True,
    )
    export_renderable: bpy.props.BoolProperty(
        name="Renderable Objects",
        description="Export renderable objects",
        default=True,
    )
    export_cameras: bpy.props.BoolProperty(
        name="Cameras",
        description="Export cameras",
        default=True,
    )
    export_lights: bpy.props.BoolProperty(
        name="Lights",
        description="Export lights",
        default=True,
    )
    export_custom_properties: bpy.props.BoolProperty(
        name="Custom Properties",
        description="Export AssetKit custom property payloads",
        default=True,
    )
    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply object modifiers before mesh export",
        default=True,
    )
    export_uv: bpy.props.BoolProperty(
        name="UVs",
        description="Export mesh UV coordinates",
        default=True,
    )
    export_normals: bpy.props.BoolProperty(
        name="Normals",
        description="Export mesh normals",
        default=True,
    )
    export_tangents: bpy.props.BoolProperty(
        name="Tangents",
        description="Export mesh tangents when available",
        default=True,
    )
    export_vertex_colors: bpy.props.BoolProperty(
        name="Vertex Colors",
        description="Export mesh vertex colors",
        default=True,
    )
    export_attributes: bpy.props.BoolProperty(
        name="Attributes",
        description="Export AssetKit-supported mesh attributes",
        default=True,
    )
    export_materials: bpy.props.BoolProperty(
        name="Materials",
        description="Export materials",
        default=True,
    )
    export_images: bpy.props.BoolProperty(
        name="Images",
        description="Export material image textures",
        default=True,
    )
    export_animations: bpy.props.BoolProperty(
        name="Animations",
        description="Export transform, bone, material, and morph animations",
        default=True,
    )
    export_skins: bpy.props.BoolProperty(
        name="Skinning",
        description="Export armature skinning data",
        default=True,
    )
    export_shape_keys: bpy.props.BoolProperty(
        name="Shape Keys",
        description="Export shape keys as morph targets",
        default=True,
    )
    export_shape_key_normals: bpy.props.BoolProperty(
        name="Shape Key Normals",
        description="Export shape key normals when supported",
        default=True,
    )
    export_shape_key_tangents: bpy.props.BoolProperty(
        name="Shape Key Tangents",
        description="Export shape key tangents when supported",
        default=True,
    )
    export_shape_key_animations: bpy.props.BoolProperty(
        name="Shape Key Animations",
        description="Export shape key weight animations",
        default=True,
    )
    global_scale: bpy.props.FloatProperty(
        name="Scale",
        description="Scale factor for mesh export",
        default=1.0,
        min=0.000001,
        soft_min=0.01,
        soft_max=1000.0,
    )
    use_scene_unit: bpy.props.BoolProperty(
        name="Scene Unit",
        description="Apply the scene unit scale to mesh export",
        default=False,
    )
    forward_axis: bpy.props.EnumProperty(
        name="Forward Axis",
        description="Forward axis for mesh export",
        items=_FORWARD_AXIS_ITEMS,
        default="Y",
    )
    up_axis: bpy.props.EnumProperty(
        name="Up Axis",
        description="Up axis for mesh export",
        items=_UP_AXIS_ITEMS,
        default="Z",
    )
    coordinate_conversion: bpy.props.EnumProperty(
        name="Mode",
        description="Coordinate handling for AssetKit export",
        items=(
            ("AUTO", "Auto", "Use format defaults: glTF/GLB Y-up, 3MF/OBJ/COLLADA/STL/PLY authored coordinates"),
            ("TRANSFORM", "Convert Data", "Export in the selected target coordinate system"),
            ("RAW", "Raw", "Do not change AssetKit document coordinates before export"),
        ),
        default="AUTO",
    )
    coordinate_system: bpy.props.EnumProperty(
        name="Target",
        description="Target up-axis/orientation for converted export",
        items=(
            ("Y_UP", "Y Up", "Export as right-handed Y-up"),
            ("Z_UP", "Z Up", "Export as right-handed Z-up"),
            ("X_UP", "X Up", "Export as right-handed X-up"),
        ),
        default="Y_UP",
    )
    dae_version: bpy.props.EnumProperty(
        name="Version",
        description="COLLADA schema version for DAE export",
        items=(
            ("AUTO", "Auto", "Use AssetKit's lowest compatible COLLADA version"),
            ("1_4", "1.4.1", "Force COLLADA 1.4.1"),
            ("1_5", "1.5.0", "Force COLLADA 1.5.0"),
        ),
        default="AUTO",
    )
    dae_index_mode: bpy.props.EnumProperty(
        name="Indices",
        description="Index layout for COLLADA primitive export",
        items=(
            ("AUTO", "Auto", "Use AssetKit's default DAE index layout"),
            ("MULTI", "Multi-index", "Write native COLLADA-style input offsets"),
            ("SINGLE", "Single-index", "Normalize attributes to one vertex index"),
        ),
        default="SINGLE",
    )
    material_export_mode: bpy.props.EnumProperty(
        name="Shader Graphs",
        description="How unsupported Blender shader graphs are exported",
        items=(
            ("AUTO", "Auto Bake", "Bake only shader graphs that cannot be mapped directly"),
            ("DIRECT", "Direct", "Use direct AssetKit material mapping only"),
            ("BAKE", "Bake All", "Bake material color for every node material"),
        ),
        default="AUTO",
    )
    material_bake_size: bpy.props.EnumProperty(
        name="Bake Size",
        description="Texture size for baked shader fallback",
        items=(
            ("512", "512", "Bake 512 x 512 fallback textures"),
            ("1024", "1024", "Bake 1024 x 1024 fallback textures"),
            ("2048", "2048", "Bake 2048 x 2048 fallback textures"),
        ),
        default="1024",
    )
    stl_format: bpy.props.EnumProperty(
        name="Format",
        description="STL file encoding",
        items=(
            ("BINARY", "Binary", "Export compact binary STL"),
            ("ASCII", "ASCII", "Export text STL"),
        ),
        default="BINARY",
    )
    stl_batch_mode: bpy.props.BoolProperty(
        name="Batch Mode",
        description="Export each mesh object to a separate STL file",
        default=False,
    )
    stl_apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply object modifiers before STL export",
        default=True,
    )
    stl_global_scale: bpy.props.FloatProperty(
        name="Scale",
        description="Scale factor for STL export",
        default=1.0,
        min=0.000001,
        soft_min=0.01,
        soft_max=1000.0,
    )
    stl_use_scene_unit: bpy.props.BoolProperty(
        name="Scene Unit",
        description="Apply the scene unit scale to STL export",
        default=False,
    )
    stl_forward_axis: bpy.props.EnumProperty(
        name="Forward Axis",
        description="Forward axis for STL export",
        items=_FORWARD_AXIS_ITEMS,
        default="Y",
    )
    stl_up_axis: bpy.props.EnumProperty(
        name="Up Axis",
        description="Up axis for STL export",
        items=_UP_AXIS_ITEMS,
        default="Z",
    )
    ply_format: bpy.props.EnumProperty(
        name="Format",
        description="PLY file encoding",
        items=(
            ("BINARY", "Binary", "Export compact binary little-endian PLY"),
            ("ASCII", "ASCII", "Export text PLY"),
        ),
        default="BINARY",
    )
    ply_apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply object modifiers before PLY export",
        default=True,
    )
    ply_global_scale: bpy.props.FloatProperty(
        name="Scale",
        description="Scale factor for PLY export",
        default=1.0,
        min=0.000001,
        soft_min=0.01,
        soft_max=1000.0,
    )
    ply_use_scene_unit: bpy.props.BoolProperty(
        name="Scene Unit",
        description="Apply the scene unit scale to PLY export",
        default=False,
    )
    ply_forward_axis: bpy.props.EnumProperty(
        name="Forward Axis",
        description="Forward axis for PLY export",
        items=_FORWARD_AXIS_ITEMS,
        default="Y",
    )
    ply_up_axis: bpy.props.EnumProperty(
        name="Up Axis",
        description="Up axis for PLY export",
        items=_UP_AXIS_ITEMS,
        default="Z",
    )
    ply_export_uv: bpy.props.BoolProperty(
        name="UV",
        description="Export first PLY UV layer as s/t vertex properties",
        default=True,
    )
    ply_export_normals: bpy.props.BoolProperty(
        name="Normals",
        description="Export PLY normals when available",
        default=True,
    )
    ply_export_colors: bpy.props.EnumProperty(
        name="Colors",
        description="PLY vertex color export mode",
        items=(
            ("SRGB", "sRGB", "Write colors as uchar sRGB values"),
            ("LINEAR", "Linear", "Write colors as uchar linear values"),
            ("NONE", "None", "Do not export vertex colors"),
        ),
        default="SRGB",
    )
    ply_export_triangulated_mesh: bpy.props.BoolProperty(
        name="Triangulated Mesh",
        description="Triangulate polygon faces for PLY export",
        default=False,
    )

    def draw(self, _context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "export_format")

        self._draw_format_settings(layout)
        self._draw_coordinates_settings(layout)
        self._draw_include_settings(layout)
        self._draw_data_settings(layout)
        self._draw_animation_settings(layout)

    def _draw_format_settings(self, layout):
        if self.export_format == "DAE":
            dae = _draw_panel(layout, "ASSETKIT_export_collada", "COLLADA", default_closed=False)
            if dae:
                dae.prop(self, "dae_version")
                dae.prop(self, "dae_index_mode")
        elif self.export_format == "STL":
            stl = _draw_panel(layout, "ASSETKIT_export_stl", "STL", default_closed=False)
            if stl:
                stl.prop(self, "stl_format")
                stl.prop(self, "stl_batch_mode")
        elif self.export_format == "PLY":
            ply = _draw_panel(layout, "ASSETKIT_export_ply", "PLY", default_closed=False)
            if ply:
                ply.prop(self, "ply_format")
                ply.prop(self, "ply_export_triangulated_mesh")

    def _draw_coordinates_settings(self, layout):
        if self.export_format in _MESH_TRANSFORM_FORMATS:
            transform = _draw_panel(layout, "ASSETKIT_export_coordinates", "Coordinates", default_closed=False)
            if transform:
                transform.prop(self, "apply_modifiers")
                transform.prop(self, "global_scale")
                transform.prop(self, "use_scene_unit")
                transform.prop(self, "forward_axis")
                transform.prop(self, "up_axis")
        else:
            coords = _draw_panel(layout, "ASSETKIT_export_coordinates", "Coordinates", default_closed=False)
            if coords:
                coords.prop(self, "coordinate_conversion")
                if self.coordinate_conversion == "TRANSFORM":
                    coords.prop(self, "coordinate_system")
                if self.export_format in _APPLY_MODIFIER_FORMATS:
                    coords.prop(self, "apply_modifiers")

    def _draw_include_settings(self, layout):
        include = _draw_panel(layout, "ASSETKIT_export_include", "Include", default_closed=True)
        if not include:
            return

        limit = include.column(heading="Limit to", align=True)
        limit.prop(self, "selected_only")
        limit.prop(self, "export_visible")
        limit.prop(self, "export_renderable")
        if self.export_format in _SCENE_DATA_FORMATS:
            data = include.column(heading="Scene Data", align=True)
            data.prop(self, "export_cameras")
            data.prop(self, "export_lights")
            data.prop(self, "export_custom_properties")
        elif self.export_format in _CUSTOM_PROPERTY_FORMATS:
            data = include.column(heading="Metadata", align=True)
            data.prop(self, "export_custom_properties")

    def _draw_data_settings(self, layout):
        has_mesh_settings = self.export_format in _MESH_DATA_FORMATS
        has_material_settings = self.export_format not in {"STL", "PLY"}
        has_shape_key_settings = self.export_format in _ANIMATION_FORMATS
        if not has_mesh_settings and not has_material_settings and not has_shape_key_settings:
            return

        data = _draw_panel(layout, "ASSETKIT_export_data", "Data", default_closed=True)
        if not data:
            return

        if has_mesh_settings:
            mesh = _draw_panel(data, "ASSETKIT_export_data_mesh", "Mesh", default_closed=True)
            if mesh:
                mesh.prop(self, "export_uv")
                mesh.prop(self, "export_normals")
                if self.export_format != "PLY":
                    tangent = mesh.column()
                    tangent.active = self.export_normals
                    tangent.prop(self, "export_tangents")
                mesh.prop(self, "export_vertex_colors")
                mesh.prop(self, "export_attributes")

        if has_material_settings:
            materials = _draw_toggle_panel(
                data,
                self,
                "ASSETKIT_export_data_materials",
                "export_materials",
                "Materials",
                default_closed=True,
            )
            if materials:
                materials.prop(self, "export_images")
                materials.prop(self, "material_export_mode")
                if self.material_export_mode != "DIRECT":
                    materials.prop(self, "material_bake_size")

        if has_shape_key_settings:
            skinning = _draw_panel(data, "ASSETKIT_export_data_skinning", "Skinning", default_closed=True)
            if skinning:
                skinning.prop(self, "export_skins")

            shape_keys = _draw_toggle_panel(
                data,
                self,
                "ASSETKIT_export_data_shape_keys",
                "export_shape_keys",
                "Shape Keys",
                default_closed=True,
            )
            if shape_keys:
                shape_keys.prop(self, "export_shape_key_normals")
                tangent = shape_keys.column()
                tangent.active = self.export_shape_key_normals
                tangent.prop(self, "export_shape_key_tangents")

    def _draw_animation_settings(self, layout):
        if self.export_format in _ANIMATION_FORMATS:
            animation = _draw_toggle_panel(
                layout,
                self,
                "ASSETKIT_export_animation",
                "export_animations",
                "Animation",
                default_closed=True,
            )
            if animation and self.export_shape_keys:
                animation.prop(self, "export_shape_key_animations")

    def check(self, _context):
        path_changed = self.filepath != self.assetkit_last_filepath
        format_changed = (
            bool(self.assetkit_last_export_format)
            and self.export_format != self.assetkit_last_export_format
        )
        root, current_ext = os.path.splitext(self.filepath)
        ext_format = _FORMAT_BY_SUFFIX.get(current_ext.lower())
        changed = False

        if path_changed and not format_changed and ext_format:
            if self.export_format != ext_format:
                self.export_format = ext_format
                changed = True

        ext = suffix_from_format(self.export_format)
        root, current_ext = os.path.splitext(self.filepath)
        if current_ext.lower() != ext:
            self.filepath = root + ext
            changed = True

        if self.filename_ext != ext:
            self.filename_ext = ext
            changed = True

        self.assetkit_last_filepath = self.filepath
        self.assetkit_last_export_format = self.export_format
        return changed

    def execute(self, context):
        file_type = file_type_from_format(self.export_format)
        coord_conversion = self.coordinate_conversion
        coord_system = self.coordinate_system
        if self.export_format in _MESH_TRANSFORM_FORMATS:
            if self.forward_axis.lstrip("-") == self.up_axis.lstrip("-"):
                self.report({"ERROR"}, "Forward and up axes must be different")
                return {"CANCELLED"}
            coord_conversion = "RAW"
            coord_system = "Z_UP"
        elif coord_conversion == "AUTO":
            if self.export_format in {"3MF", "DAE", "OBJ", "STL", "PLY"}:
                coord_conversion = "RAW"
                coord_system = "Z_UP"
            else:
                coord_conversion = "TRANSFORM"
                coord_system = "Y_UP"
        use_apply_modifiers = self.export_format in _APPLY_MODIFIER_FORMATS
        use_mesh_transform = self.export_format in _MESH_TRANSFORM_FORMATS
        try:
            export_scene(
                context,
                self.filepath,
                file_type,
                selected_only=self.selected_only,
                dae_version=_DAE_VERSION_VALUES.get(self.dae_version, AK_DAE_EXPORT_VERSION_AUTO),
                dae_index_mode=_DAE_INDEX_MODE_VALUES.get(
                    self.dae_index_mode,
                    AK_DAE_EXPORT_INDEX_AUTO,
                ),
                coordinate_system=_coord_system_id(coord_system),
                coordinate_conversion=_coord_conversion_id(coord_conversion),
                material_export_mode=self.material_export_mode,
                material_bake_size=int(self.material_bake_size),
                export_visible=self.export_visible,
                export_renderable=self.export_renderable,
                export_cameras=self.export_cameras if self.export_format in _SCENE_DATA_FORMATS else False,
                export_lights=self.export_lights if self.export_format in _SCENE_DATA_FORMATS else False,
                export_custom_properties=(
                    self.export_custom_properties if self.export_format in _CUSTOM_PROPERTY_FORMATS else True
                ),
                export_uv=self.export_uv if self.export_format in _MESH_DATA_FORMATS else True,
                export_normals=self.export_normals if self.export_format in _MESH_DATA_FORMATS else True,
                export_tangents=self.export_tangents if self.export_format in _MESH_DATA_FORMATS else True,
                export_vertex_colors=self.export_vertex_colors if self.export_format in _MESH_DATA_FORMATS else True,
                export_attributes=self.export_attributes if self.export_format in _MESH_DATA_FORMATS else True,
                export_materials=self.export_materials if self.export_format in _MATERIAL_FORMATS else True,
                export_images=self.export_images if self.export_format in _MATERIAL_FORMATS else True,
                export_animations=self.export_animations if self.export_format in _ANIMATION_FORMATS else True,
                export_skins=self.export_skins if self.export_format in _ANIMATION_FORMATS else True,
                export_shape_keys=self.export_shape_keys if self.export_format in _ANIMATION_FORMATS else True,
                export_shape_key_normals=(
                    self.export_shape_key_normals if self.export_format in _ANIMATION_FORMATS else True
                ),
                export_shape_key_tangents=(
                    self.export_shape_key_tangents if self.export_format in _ANIMATION_FORMATS else True
                ),
                export_shape_key_animations=(
                    self.export_shape_key_animations if self.export_format in _ANIMATION_FORMATS else True
                ),
                apply_modifiers=self.apply_modifiers if use_apply_modifiers else None,
                global_scale=self.global_scale if use_mesh_transform else None,
                use_scene_unit=self.use_scene_unit if use_mesh_transform else None,
                forward_axis=self.forward_axis if use_mesh_transform else None,
                up_axis=self.up_axis if use_mesh_transform else None,
                stl_format=self.stl_format,
                stl_batch_mode=self.stl_batch_mode,
                stl_apply_modifiers=self.stl_apply_modifiers,
                stl_global_scale=self.stl_global_scale,
                stl_use_scene_unit=self.stl_use_scene_unit,
                stl_forward_axis=self.stl_forward_axis,
                stl_up_axis=self.stl_up_axis,
                ply_format=self.ply_format,
                ply_apply_modifiers=self.ply_apply_modifiers,
                ply_global_scale=self.ply_global_scale,
                ply_use_scene_unit=self.ply_use_scene_unit,
                ply_forward_axis=self.ply_forward_axis,
                ply_up_axis=self.ply_up_axis,
                ply_export_uv=self.export_uv if self.export_format == "PLY" else self.ply_export_uv,
                ply_export_normals=self.export_normals if self.export_format == "PLY" else self.ply_export_normals,
                ply_export_colors=(
                    "SRGB" if self.export_format == "PLY" and self.export_vertex_colors else self.ply_export_colors
                ),
                ply_export_triangulated_mesh=self.ply_export_triangulated_mesh,
            )
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not export through AssetKit: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Exported through AssetKit")
        return {"FINISHED"}
