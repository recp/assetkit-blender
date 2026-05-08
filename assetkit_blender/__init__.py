bl_info = {
    "name": "AssetKit Blender",
    "author": "Recep Aslantas",
    "version": (0, 1, 1),
    "blender": (4, 2, 0),
    "location": "File > Import > AssetKit",
    "description": "Import 3D assets through AssetKit",
    "category": "Import-Export",
}

import bpy

from .operators import (
    ASSETKIT_OT_apply_material_variant,
    ASSETKIT_OT_apply_morph_preset,
    ASSETKIT_OT_import_assetkit,
)
from .preferences import AssetKitPreferences


class ASSETKIT_MT_file_menu(bpy.types.Menu):
    bl_label = "AssetKit"

    def draw(self, _context):
        self.layout.operator(
            ASSETKIT_OT_import_assetkit.bl_idname,
            text="Import with AssetKit",
        )
        self.layout.operator(
            ASSETKIT_OT_apply_material_variant.bl_idname,
            text="Apply Material Variant",
        )
        self.layout.operator(
            ASSETKIT_OT_apply_morph_preset.bl_idname,
            text="Apply Morph Preset",
        )


classes = (
    AssetKitPreferences,
    ASSETKIT_OT_import_assetkit,
    ASSETKIT_OT_apply_material_variant,
    ASSETKIT_OT_apply_morph_preset,
    ASSETKIT_MT_file_menu,
)


def menu_func_import(self, _context):
    self.layout.operator(
        ASSETKIT_OT_import_assetkit.bl_idname,
        text="AssetKit (.gltf, .glb, .dae, .obj, .stl, .ply)",
    )


def menu_func_assetkit(self, _context):
    self.layout.separator()
    self.layout.menu(ASSETKIT_MT_file_menu.__name__)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.prepend(menu_func_import)
    bpy.types.TOPBAR_MT_file.append(menu_func_assetkit)


def unregister():
    bpy.types.TOPBAR_MT_file.remove(menu_func_assetkit)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
