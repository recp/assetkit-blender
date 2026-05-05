from __future__ import annotations

import bpy
from bpy_extras.io_utils import ImportHelper

from .assetkit import AssetKitError
from .importer import import_assetkit_file


class ASSETKIT_OT_import_assetkit(bpy.types.Operator, ImportHelper):
    bl_idname = "assetkit.import_assetkit"
    bl_label = "Import AssetKit"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply",
        options={"HIDDEN"},
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        try:
            objects = import_assetkit_file(self.filepath, prefs.assetkit_library)
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not load AssetKit library: {exc}")
            return {"CANCELLED"}

        if not objects:
            self.report({"WARNING"}, "AssetKit loaded the file but no triangle meshes were imported")
            return {"FINISHED"}

        self.report({"INFO"}, f"Imported {len(objects)} mesh object(s) through AssetKit")
        return {"FINISHED"}
