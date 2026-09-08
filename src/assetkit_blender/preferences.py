import bpy


class AssetKitPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or "assetkit_blender"

    assetkit_library: bpy.props.StringProperty(
        name="AssetKit Library",
        subtype="FILE_PATH",
        description="Path to libassetkit shared library",
        default="",
    )

    source_cache_mib: bpy.props.IntProperty(
        name="Geometry Source Cache (MiB)", default=512, min=16, max=32768,
        description="Estimated source-data budget; active sources stay resident even if larger than the budget",
    )

    gaussian_preview: bpy.props.BoolProperty(
        name="Gaussian Preview on Import", default=True,
        description="Preview imported Gaussian point clouds in Solid shading using the GPU",
    )

    gaussian_preview_mib: bpy.props.IntProperty(
        name="Gaussian Preview Budget (MiB)", default=1024, min=64, max=32768,
        description="Memory budget for Gaussian viewport data and working buffers",
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "assetkit_library")
        layout.prop(self, "source_cache_mib")
        layout.prop(self, "gaussian_preview")
        layout.prop(self, "gaussian_preview_mib")
