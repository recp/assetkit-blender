from __future__ import annotations

import hashlib
from array import array

import bpy
from bpy_extras.io_utils import ImportHelper

from .assetkit import AssetKitError
from .importer import import_assetkit_file, import_assetkit_file_auto, import_assetkit_file_progressive


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
        description="Ask AssetKit to generate missing normals before Blender creates the mesh",
        default=False,
    )
    mesh_shading: bpy.props.EnumProperty(
        name="Shading",
        description="How mesh shading is set after import",
        items=(
            ("AUTO", "Auto", "Use authored normal data when available"),
            ("FLAT", "Flat", "Use flat face shading"),
            ("SMOOTH", "Smooth", "Use smooth shading"),
        ),
        default="AUTO",
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
    convert_line_loop: bpy.props.BoolProperty(
        name="Convert Line Loops",
        description="Convert line loop primitives to Blender line edges",
        default=True,
    )
    convert_line_strip: bpy.props.BoolProperty(
        name="Convert Line Strips",
        description="Convert line strip primitives to Blender line edges",
        default=True,
    )
    build_mode: bpy.props.EnumProperty(
        name="Build Mode",
        description="How Blender objects are created after AssetKit reads the file",
        items=(
            ("AUTO", "Auto", "Use progressive building for large object/node counts"),
            ("BLOCKING", "Blocking", "Build all Blender objects before the import operator returns"),
            ("PROGRESSIVE", "Progressive", "Load AssetKit in the background and build Blender objects in batches"),
        ),
        default="AUTO",
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
    placement: bpy.props.EnumProperty(
        name="Placement",
        description="Move the imported asset after import",
        items=(
            ("AS_AUTHORED", "As Authored", "Keep authored coordinates"),
            ("ORIGIN_GROUND", "Origin Ground", "Center the asset on world origin and place it on the ground plane"),
            ("CURSOR_GROUND", "Cursor Ground", "Center the asset on the 3D cursor and place it on the cursor ground plane"),
        ),
        default="AS_AUTHORED",
    )
    select_imported_objects: bpy.props.BoolProperty(
        name="Select Imported Objects",
        description="Select created mesh objects after import",
        default=False,
    )
    set_viewport_shading: bpy.props.BoolProperty(
        name="Set Viewport Shading",
        description="Switch 3D viewports to material preview after import",
        default=True,
    )
    fit_timeline: bpy.props.BoolProperty(
        name="Fit Timeline",
        description="Fit the timeline to the imported animation range",
        default=True,
    )
    replace_startup_cube: bpy.props.EnumProperty(
        name="Replace Startup",
        description="Remove Blender startup objects before importing",
        items=(
            ("DEFAULT_CUBE", "Default Cube", "Remove the untouched startup cube before import"),
            ("STARTUP_SCENE", "Startup Scene", "Remove the untouched startup cube, camera, and light before import"),
            ("NEVER", "Never", "Keep all existing scene objects"),
        ),
        default="STARTUP_SCENE",
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        load_options = self._load_options()
        if self.replace_startup_cube in {"DEFAULT_CUBE", "STARTUP_SCENE"}:
            _remove_default_cube(context.scene, remove_startup_camera_light=self.replace_startup_cube == "STARTUP_SCENE")
        scene_was_empty = _scene_has_no_content(context.scene)
        focus_camera = context.scene.camera if scene_was_empty else None

        if self.build_mode == "AUTO":
            try:
                result = import_assetkit_file_auto(
                    self.filepath,
                    prefs.assetkit_library,
                    load_options,
                    collection=context.collection,
                    batch_size=self.progressive_batch_size,
                    focus_mode=self.focus_import,
                    placement_mode=self.placement,
                    scene_was_empty=scene_was_empty,
                    focus_camera=focus_camera,
                    select_imported=self.select_imported_objects,
                    shading_mode=self.mesh_shading,
                    set_viewport_shading=self.set_viewport_shading,
                    fit_timeline=self.fit_timeline,
                )
            except AssetKitError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            except OSError as exc:
                self.report({"ERROR"}, f"Could not load AssetKit library: {exc}")
                return {"CANCELLED"}

            if isinstance(result, list):
                if not result:
                    self.report({"WARNING"}, "AssetKit loaded the file but no importable mesh primitives were found")
                else:
                    self.report({"INFO"}, f"Imported {len(result)} mesh object(s) through AssetKit")
            else:
                self.report({"INFO"}, "AssetKit progressive import started")
            return {"FINISHED"}

        if self.build_mode == "PROGRESSIVE":
            import_assetkit_file_progressive(
                self.filepath,
                prefs.assetkit_library,
                load_options,
                collection=context.collection,
                batch_size=self.progressive_batch_size,
                focus_mode=self.focus_import,
                placement_mode=self.placement,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=self.select_imported_objects,
                shading_mode=self.mesh_shading,
                set_viewport_shading=self.set_viewport_shading,
                fit_timeline=self.fit_timeline,
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
                placement_mode=self.placement,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=self.select_imported_objects,
                shading_mode=self.mesh_shading,
                set_viewport_shading=self.set_viewport_shading,
                fit_timeline=self.fit_timeline,
            )
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not load AssetKit library: {exc}")
            return {"CANCELLED"}

        if not objects:
            self.report({"WARNING"}, "AssetKit loaded the file but no importable mesh primitives were found")
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
        mesh_box.prop(self, "convert_line_loop")
        mesh_box.prop(self, "convert_line_strip")

        load_box = layout.box()
        load_box.label(text="Loading")
        load_box.prop(self, "build_mode")
        if self.build_mode in {"AUTO", "PROGRESSIVE"}:
            load_box.prop(self, "progressive_batch_size")

        view_box = layout.box()
        view_box.label(text="View")
        view_box.prop(self, "mesh_shading")
        view_box.prop(self, "focus_import")
        view_box.prop(self, "placement")
        view_box.prop(self, "replace_startup_cube")
        view_checks = view_box.column()
        view_checks.use_property_split = False
        view_checks.prop(self, "select_imported_objects")
        view_checks.prop(self, "set_viewport_shading")
        view_checks.prop(self, "fit_timeline")

    def _load_options(self) -> dict:
        return {
            "coordinate_conversion": self.coordinate_conversion,
            "coordinate_system": self.coordinate_system,
            "triangulate": self.triangulate,
            "generate_normals": self.generate_normals,
            "convert_triangle_strip": self.convert_triangle_strip,
            "convert_triangle_fan": self.convert_triangle_fan,
            "convert_line_loop": self.convert_line_loop,
            "convert_line_strip": self.convert_line_strip,
        }


def _scene_has_no_content(scene: bpy.types.Scene) -> bool:
    content_types = {"ARMATURE", "CURVE", "EMPTY", "FONT", "MESH", "META", "SURFACE"}
    return not any(obj.type in content_types for obj in scene.objects)


def _remove_default_cube(scene: bpy.types.Scene, remove_startup_camera_light: bool = True) -> bool:
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
    if remove_startup_camera_light:
        _remove_startup_camera_light(scene)
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


def _remove_startup_camera_light(scene: bpy.types.Scene) -> None:
    for obj in list(scene.objects):
        if _is_startup_camera(obj) or _is_startup_light(obj):
            data = obj.data
            obj_type = obj.type
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                if obj_type == "CAMERA":
                    bpy.data.cameras.remove(data)
                elif obj_type == "LIGHT":
                    bpy.data.lights.remove(data)


def _is_startup_camera(obj: bpy.types.Object) -> bool:
    if obj.type != "CAMERA" or obj.name != "Camera" or obj.data is None:
        return False
    if obj.animation_data or obj.constraints:
        return False
    return abs(obj.data.lens - 50.0) < 1e-4


def _is_startup_light(obj: bpy.types.Object) -> bool:
    if obj.type != "LIGHT" or obj.name != "Light" or obj.data is None:
        return False
    if obj.animation_data or obj.constraints:
        return False
    return obj.data.type == "POINT"


_MATERIAL_VARIANT_ITEMS_CACHE = ()


def _material_variant_items(self, context):
    del self

    global _MATERIAL_VARIANT_ITEMS_CACHE

    names = _material_variant_names(context)
    items = [("__DEFAULT__", "Default", "Restore default materials")]
    items.extend(
        (
            _material_variant_identifier(name),
            name,
            "Apply this AssetKit material variant",
        )
        for name in names
    )
    _MATERIAL_VARIANT_ITEMS_CACHE = tuple(items)
    return _MATERIAL_VARIANT_ITEMS_CACHE


def _material_variant_name_from_enum(context, identifier: str) -> str:
    if identifier == "__DEFAULT__":
        return ""
    for name in _material_variant_names(context):
        if _material_variant_identifier(name) == identifier:
            return name
    return identifier


def _material_variant_names(context) -> list[str]:
    names = set()
    objects = getattr(context, "scene", None).objects if getattr(context, "scene", None) else []
    for obj in objects:
        count = int(obj.get("assetkit_material_variant_count") or 0)
        for index in range(count):
            name = obj.get(f"assetkit_material_variant_{index}_name")
            if name:
                names.add(str(name))
    return sorted(names)


def _material_variant_identifier(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return f"VARIANT_{digest}"


class ASSETKIT_OT_apply_material_variant(bpy.types.Operator):
    bl_idname = "assetkit.apply_material_variant"
    bl_label = "Apply AssetKit Material Variant"
    bl_options = {"REGISTER", "UNDO"}

    variant: bpy.props.EnumProperty(
        name="Variant",
        description="Material variant to apply",
        items=_material_variant_items,
    )
    variant_name: bpy.props.StringProperty(
        name="Variant",
        description="Material variant name. Leave empty to restore default materials",
        default="",
        options={"HIDDEN"},
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Apply the material variant only to selected objects",
        default=False,
    )

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        variant_name = self.variant_name or _material_variant_name_from_enum(context, self.variant)
        changed = _apply_material_variant(context, variant_name, self.selected_only)
        if changed == 0:
            self.report({"WARNING"}, "No matching AssetKit material variants found")
        else:
            label = variant_name or "default"
            self.report({"INFO"}, f"Applied AssetKit material variant '{label}' to {changed} object(s)")
        return {"FINISHED"}


def _apply_material_variant(context, variant_name: str, selected_only: bool) -> int:
    objects = context.selected_objects if selected_only else context.scene.objects
    changed = 0
    for obj in objects:
        if obj.type != "MESH" or not obj.data:
            continue
        slot = _variant_slot(obj, variant_name)
        if slot is None:
            continue
        _set_material_slot(obj, slot)
        changed += 1
    return changed


def _variant_slot(obj: bpy.types.Object, variant_name: str) -> int | None:
    count = int(obj.get("assetkit_material_variant_count") or 0)
    if count <= 0:
        return None
    if not variant_name:
        return 0
    for index in range(count):
        prefix = f"assetkit_material_variant_{index}"
        if obj.get(f"{prefix}_name") == variant_name:
            slot = obj.get(f"{prefix}_slot")
            return int(slot) if slot is not None else None
    return None


def _set_material_slot(obj: bpy.types.Object, slot: int) -> None:
    obj.active_material_index = max(0, min(slot, max(0, len(obj.data.materials) - 1)))
    if not obj.data.polygons:
        return
    values = array("i", [obj.active_material_index]) * len(obj.data.polygons)
    obj.data.polygons.foreach_set("material_index", values)
    obj.data.update()
