from __future__ import annotations

import os

import bpy
from bpy_extras.io_utils import ExportHelper

from ..assetkit import AssetKitError
from .exporter import EXPORT_FORMATS, export_scene, file_type_from_format, suffix_from_format


class ASSETKIT_OT_export_assetkit(bpy.types.Operator, ExportHelper):
    bl_idname = "assetkit.export_assetkit"
    bl_label = "Export AssetKit"
    bl_options = {"REGISTER"}

    filename_ext = ".gltf"
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb",
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

    def check(self, _context):
        ext = suffix_from_format(self.export_format)
        root, current_ext = os.path.splitext(self.filepath)
        if current_ext.lower() != ext:
            self.filepath = root + ext
            self.filename_ext = ext
            return True
        return False

    def execute(self, context):
        file_type = file_type_from_format(self.export_format)
        try:
            export_scene(
                context,
                self.filepath,
                file_type,
                selected_only=self.selected_only,
            )
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not export through AssetKit: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, "Exported through AssetKit")
        return {"FINISHED"}
