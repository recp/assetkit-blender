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
_APPLY_MODIFIER_FORMATS = {"GLTF", "GLB", "DAE", "OBJ", "STL", "PLY"}

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
    return export_format in _MESH_TRANSFORM_FORMATS


def _on_export_format_changed(self, _context) -> None:
    self.apply_modifiers = _format_default_apply_modifiers(self.export_format)


class ASSETKIT_OT_export_assetkit(bpy.types.Operator, ExportHelper):
    bl_idname = "assetkit.export_assetkit"
    bl_label = "Export AssetKit"
    bl_options = {"REGISTER"}

    filename_ext = ".gltf"
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply",
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
    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply object modifiers before mesh export",
        default=False,
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
            ("AUTO", "Auto", "Use format defaults: glTF/GLB Y-up, OBJ/COLLADA/STL/PLY authored coordinates"),
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
        default=False,
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
        layout.prop(self, "export_format")
        include = layout.box()
        include.label(text="Include")
        include.prop(self, "selected_only")
        if self.export_format not in {"STL", "PLY"}:
            materials = layout.box()
            materials.label(text="Materials")
            materials.prop(self, "material_export_mode")
            if self.material_export_mode != "DIRECT":
                materials.prop(self, "material_bake_size")
        if self.export_format in _MESH_TRANSFORM_FORMATS:
            transform = layout.box()
            transform.label(text="Transform")
            transform.prop(self, "apply_modifiers")
            transform.prop(self, "global_scale")
            transform.prop(self, "use_scene_unit")
            transform.prop(self, "forward_axis")
            transform.prop(self, "up_axis")
        else:
            if self.export_format in _APPLY_MODIFIER_FORMATS:
                mesh = layout.box()
                mesh.label(text="Mesh")
                mesh.prop(self, "apply_modifiers")
            coords = layout.box()
            coords.label(text="Coordinates")
            coords.prop(self, "coordinate_conversion")
            if self.coordinate_conversion == "TRANSFORM":
                coords.prop(self, "coordinate_system")
        if self.export_format == "DAE":
            dae = layout.box()
            dae.label(text="COLLADA")
            dae.prop(self, "dae_version")
            dae.prop(self, "dae_index_mode")
        if self.export_format == "STL":
            stl = layout.box()
            stl.label(text="STL")
            stl.prop(self, "stl_format")
            stl.prop(self, "stl_batch_mode")
        if self.export_format == "PLY":
            ply = layout.box()
            ply.label(text="PLY")
            ply.prop(self, "ply_format")
            ply.prop(self, "ply_export_uv")
            ply.prop(self, "ply_export_normals")
            ply.prop(self, "ply_export_colors")
            ply.prop(self, "ply_export_triangulated_mesh")

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
            if self.export_format in {"DAE", "OBJ", "STL", "PLY"}:
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
                ply_export_uv=self.ply_export_uv,
                ply_export_normals=self.ply_export_normals,
                ply_export_colors=self.ply_export_colors,
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
