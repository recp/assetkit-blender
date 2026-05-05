bl_info = {
    "name": "AssetIO Blender",
    "author": "Recep Aslantas",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Import > AssetKit",
    "description": "Import 3D assets through AssetKit",
    "category": "Import-Export",
}

import bpy

from .operators import ASSETIO_OT_import_assetkit
from .preferences import AssetIOPreferences


class ASSETIO_MT_file_menu(bpy.types.Menu):
    bl_label = "AssetIO"

    def draw(self, _context):
        self.layout.operator(
            ASSETIO_OT_import_assetkit.bl_idname,
            text="Import with AssetKit",
        )


classes = (
    AssetIOPreferences,
    ASSETIO_OT_import_assetkit,
    ASSETIO_MT_file_menu,
)


def menu_func_import(self, _context):
    self.layout.operator(
        ASSETIO_OT_import_assetkit.bl_idname,
        text="AssetKit",
    )


def menu_func_assetio(self, _context):
    self.layout.separator()
    self.layout.menu(ASSETIO_MT_file_menu.__name__)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.prepend(menu_func_import)
    bpy.types.TOPBAR_MT_file.append(menu_func_assetio)


def unregister():
    bpy.types.TOPBAR_MT_file.remove(menu_func_assetio)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
