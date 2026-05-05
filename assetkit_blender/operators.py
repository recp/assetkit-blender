from __future__ import annotations

import bpy
from bpy_extras.io_utils import ImportHelper

from .assetkit import AssetKitError
from .importer import import_assetkit_file, import_assetkit_file_progressive


class ASSETKIT_OT_import_assetkit(bpy.types.Operator, ImportHelper):
    bl_idname = "assetkit.import_assetkit"
    bl_label = "Import AssetKit"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply",
        options={"HIDDEN"},
    )
    coordinate_conversion: bpy.props.EnumProperty(
        name="Coordinate Mode",
        description="How AssetKit should adapt source coordinates for Blender",
        items=(
            ("TRANSFORM", "Root Transform", "Keep mesh data as authored and add a coordinate root"),
            ("ALL", "Convert Data", "Convert mesh data and node transforms in AssetKit"),
            ("RAW", "Raw", "Do not convert source coordinates"),
        ),
        default="TRANSFORM",
    )
    coordinate_system: bpy.props.EnumProperty(
        name="Target Coordinates",
        description="Target coordinate system for converted imports",
        items=(
            ("Z_UP", "Z Up", "Blender default right-handed Z-up coordinates"),
            ("Y_UP", "Y Up", "Right-handed Y-up coordinates"),
            ("X_UP", "X Up", "Right-handed X-up coordinates"),
            ("Z_UP_LH", "Z Up LH", "Left-handed Z-up coordinates"),
            ("Y_UP_LH", "Y Up LH", "Left-handed Y-up coordinates"),
            ("X_UP_LH", "X Up LH", "Left-handed X-up coordinates"),
        ),
        default="Z_UP",
    )
    triangulate: bpy.props.BoolProperty(
        name="Triangulate",
        description="Convert polygonal mesh primitives to triangles",
        default=True,
    )
    generate_normals: bpy.props.BoolProperty(
        name="Generate Normals",
        description="Generate normals when the source mesh does not provide them",
        default=True,
    )
    convert_triangle_strip: bpy.props.BoolProperty(
        name="Convert Triangle Strips",
        description="Convert triangle strip primitives to triangles",
        default=True,
    )
    convert_triangle_fan: bpy.props.BoolProperty(
        name="Convert Triangle Fans",
        description="Convert triangle fan primitives to triangles",
        default=True,
    )
    build_mode: bpy.props.EnumProperty(
        name="Build Mode",
        description="How Blender objects are created after AssetKit reads the file",
        items=(
            ("BLOCKING", "Blocking", "Build all Blender objects before the import operator returns"),
            ("PROGRESSIVE", "Progressive", "Load AssetKit in the background and build Blender objects in batches"),
        ),
        default="BLOCKING",
    )
    progressive_batch_size: bpy.props.IntProperty(
        name="Batch Size",
        description="Maximum mesh objects to create per progressive import step",
        default=128,
        min=1,
        max=512,
    )
    focus_import: bpy.props.EnumProperty(
        name="Focus Imported",
        description="Frame the imported asset after import",
        items=(
            ("EMPTY_SCENE", "If Scene Empty", "Frame the asset when the scene had no content before import"),
            ("ALWAYS", "Always", "Always frame the imported asset"),
            ("NEVER", "Never", "Do not change the current view"),
        ),
        default="EMPTY_SCENE",
    )
    replace_startup_cube: bpy.props.EnumProperty(
        name="Replace",
        description="Remove Blender's untouched startup cube before importing",
        items=(
            ("DEFAULT_CUBE", "Default Cube", "Remove the untouched startup cube before import"),
            ("NEVER", "Never", "Keep all existing scene objects"),
        ),
        default="DEFAULT_CUBE",
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        load_options = self._load_options()
        if self.replace_startup_cube == "DEFAULT_CUBE":
            _remove_default_cube(context.scene)
        scene_was_empty = _scene_has_no_content(context.scene)
        focus_camera = context.scene.camera if scene_was_empty else None

        if self.build_mode == "PROGRESSIVE":
            import_assetkit_file_progressive(
                self.filepath,
                prefs.assetkit_library,
                load_options,
                collection=context.collection,
                batch_size=self.progressive_batch_size,
                focus_mode=self.focus_import,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
            )
            self.report({"INFO"}, "AssetKit progressive import started")
            return {"FINISHED"}

        try:
            objects = import_assetkit_file(
                self.filepath,
                prefs.assetkit_library,
                load_options,
                collection=context.collection,
                focus_mode=self.focus_import,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
            )
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

    def draw(self, _context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        coord_box = layout.box()
        coord_box.label(text="Coordinates")
        coord_box.prop(self, "coordinate_conversion")
        coord_box.prop(self, "coordinate_system")

        mesh_box = layout.box()
        mesh_box.use_property_split = False
        mesh_box.label(text="Mesh")
        mesh_box.prop(self, "triangulate")
        mesh_box.prop(self, "generate_normals")
        mesh_box.prop(self, "convert_triangle_strip")
        mesh_box.prop(self, "convert_triangle_fan")

        load_box = layout.box()
        load_box.label(text="Loading")
        load_box.prop(self, "build_mode")
        if self.build_mode == "PROGRESSIVE":
            load_box.prop(self, "progressive_batch_size")

        view_box = layout.box()
        view_box.label(text="View")
        view_box.prop(self, "focus_import")
        view_box.prop(self, "replace_startup_cube")

    def _load_options(self) -> dict:
        return {
            "coordinate_conversion": self.coordinate_conversion,
            "coordinate_system": self.coordinate_system,
            "triangulate": self.triangulate,
            "generate_normals": self.generate_normals,
            "convert_triangle_strip": self.convert_triangle_strip,
            "convert_triangle_fan": self.convert_triangle_fan,
        }


def _scene_has_no_content(scene: bpy.types.Scene) -> bool:
    content_types = {"ARMATURE", "CURVE", "EMPTY", "FONT", "MESH", "META", "SURFACE"}
    return not any(obj.type in content_types for obj in scene.objects)


def _remove_default_cube(scene: bpy.types.Scene) -> bool:
    content_types = {"ARMATURE", "CURVE", "EMPTY", "FONT", "MESH", "META", "SURFACE"}
    content = [obj for obj in scene.objects if obj.type in content_types]
    if len(content) != 1:
        return False

    obj = content[0]
    if not _is_startup_cube(obj):
        return False

    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    return True


def _is_startup_cube(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH" or obj.name != "Cube" or obj.data is None:
        return False
    if obj.location.length > 1e-6:
        return False
    if any(abs(value) > 1e-6 for value in obj.rotation_euler):
        return False
    if any(abs(value - 1.0) > 1e-6 for value in obj.scale):
        return False
    if obj.modifiers or obj.animation_data:
        return False
    return len(obj.data.vertices) == 8 and len(obj.data.polygons) == 6
