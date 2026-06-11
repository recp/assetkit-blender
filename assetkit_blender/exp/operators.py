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


class ASSETKIT_OT_export_assetkit(bpy.types.Operator, ExportHelper):
    bl_idname = "assetkit.export_assetkit"
    bl_label = "Export AssetKit"
    bl_options = {"REGISTER"}

    filename_ext = ".gltf"
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae",
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
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=False,
    )
    coordinate_conversion: bpy.props.EnumProperty(
        name="Mode",
        description="Coordinate handling for AssetKit export",
        items=(
            ("AUTO", "Auto", "Use format defaults: glTF/GLB Y-up, COLLADA authored coordinates"),
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

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "export_format")
        layout.prop(self, "selected_only")
        materials = layout.box()
        materials.label(text="Materials")
        materials.prop(self, "material_export_mode")
        if self.material_export_mode != "DIRECT":
            materials.prop(self, "material_bake_size")
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
        if coord_conversion == "AUTO":
            if self.export_format == "DAE":
                coord_conversion = "RAW"
                coord_system = "Z_UP"
            else:
                coord_conversion = "TRANSFORM"
                coord_system = "Y_UP"
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
            )
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not export through AssetKit: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Exported through AssetKit")
        return {"FINISHED"}
