import bpy


class AssetKitPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or "assetkit_blender"

    assetkit_library: bpy.props.StringProperty(
        name="AssetKit Library",
        subtype="FILE_PATH",
        description="Path to libassetkit shared library",
        default="",
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "assetkit_library")
