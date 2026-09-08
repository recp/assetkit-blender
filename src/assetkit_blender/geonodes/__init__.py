import bpy

from . import runtime
from .nodes import CLASSES, menu, menu_import


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.prepend(menu)
    if import_menu := getattr(bpy.types, "NODE_MT_category_import", None):
        import_menu.prepend(menu_import)
    runtime.register()


def unregister():
    runtime.unregister()
    bpy.types.NODE_MT_add.remove(menu)
    if import_menu := getattr(bpy.types, "NODE_MT_category_import", None):
        import_menu.remove(menu_import)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
