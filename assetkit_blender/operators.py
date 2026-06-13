from __future__ import annotations

import hashlib
import json
import os
from array import array

import bpy
from bpy_extras.io_utils import ImportHelper

from .assetkit import AssetKitError
from .hud import finish_loading_hud, start_loading_hud, update_loading_hud
from .load_options import LoadOptions, make_load_options
from .importer import import_assetkit_file, import_assetkit_file_auto, import_assetkit_file_progressive

_DEFERRED_BLOCKING_DELAY = 0.016
_DEFERRED_ASYNC_DELAY = 0.016
_DEFERRED_FAST_BLOCKING_DELAY = 0.001
_FAST_BLOCKING_EXTENSIONS = {".obj", ".ply", ".stl"}
_FAST_BLOCKING_MAX_BYTES = 8 * 1024 * 1024


class ASSETKIT_OT_import_assetkit(bpy.types.Operator, ImportHelper):
    bl_idname = "assetkit.import_assetkit"
    bl_label = "Import AssetKit"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply;*.3mf",
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
        default=False,
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
            ("AS_IS", "As Is", "Leave Blender mesh shading untouched"),
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
    import_lines: bpy.props.BoolProperty(
        name="Import Lines",
        description="Import authored line primitives as Blender edge meshes",
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
            ("AUTO", "Auto", "Keep Blender responsive and stream objects with an adaptive first batch"),
            ("BLOCKING", "Blocking", "Close the file browser first, then build all Blender objects synchronously"),
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
    texture_loading: bpy.props.EnumProperty(
        name="Textures",
        description="When texture image files are loaded into Blender",
        items=(
            ("AUTO", "Auto", "Defer image file loading in the UI so geometry appears first"),
            ("IMMEDIATE", "Immediate", "Load texture image files during import"),
            ("DEFERRED", "Deferred", "Defer simple texture materials and image loading so geometry appears first"),
        ),
        default="AUTO",
    )
    scene_index: bpy.props.IntProperty(
        name="Scene Index",
        description="AssetKit visual scene index to import. Use -1 for the authored default scene",
        default=-1,
        min=-1,
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
    clean_viewport_overlays: bpy.props.BoolProperty(
        name="Clean Viewport Overlays",
        description="Hide wireframe and relationship overlays after importing into an empty scene",
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
        addon = context.preferences.addons.get(__package__)
        assetkit_library = addon.preferences.assetkit_library if addon else ""
        load_options = self._load_options()
        if self.replace_startup_cube in {"DEFAULT_CUBE", "STARTUP_SCENE"}:
            _remove_default_cube(context.scene, remove_startup_camera_light=self.replace_startup_cube == "STARTUP_SCENE")
        scene_was_empty = _scene_has_no_content(context.scene)
        focus_camera = context.scene.camera if scene_was_empty else None

        if self.build_mode == "AUTO" and _auto_should_import_blocking(self.filepath):
            if _should_defer_blocking_import(context):
                _schedule_blocking_import(
                    self.filepath,
                    assetkit_library,
                    load_options,
                    context.collection,
                    self.focus_import,
                    self.placement,
                    scene_was_empty,
                    focus_camera,
                    self.select_imported_objects,
                    self.mesh_shading,
                    self.set_viewport_shading,
                    self.clean_viewport_overlays,
                    self.fit_timeline,
                    delay=_DEFERRED_FAST_BLOCKING_DELAY,
                )
                self.report({"INFO"}, "AssetKit import scheduled")
                return {"FINISHED"}

            try:
                objects = import_assetkit_file(
                    self.filepath,
                    assetkit_library,
                    load_options,
                    collection=context.collection,
                    focus_mode=self.focus_import,
                    placement_mode=self.placement,
                    scene_was_empty=scene_was_empty,
                    focus_camera=focus_camera,
                    select_imported=self.select_imported_objects,
                    shading_mode=self.mesh_shading,
                    set_viewport_shading=self.set_viewport_shading,
                    clean_viewport_overlays=self.clean_viewport_overlays,
                    fit_timeline=self.fit_timeline,
                )
            except AssetKitError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            except OSError as exc:
                self.report({"ERROR"}, f"Could not load AssetKit library: {exc}")
                return {"CANCELLED"}

            if not objects:
                self.report({"WARNING"}, "AssetKit loaded the file but no importable objects were found")
            else:
                self.report({"INFO"}, f"Imported {len(objects)} object(s) through AssetKit")
            return {"FINISHED"}

        if self.build_mode == "AUTO":
            if _should_defer_async_import(context):
                _schedule_auto_import(
                    self.filepath,
                    assetkit_library,
                    load_options,
                    context.collection,
                    self.progressive_batch_size,
                    self.focus_import,
                    self.placement,
                    scene_was_empty,
                    focus_camera,
                    self.select_imported_objects,
                    self.mesh_shading,
                    self.set_viewport_shading,
                    self.clean_viewport_overlays,
                    self.fit_timeline,
                )
                self.report({"INFO"}, "AssetKit import scheduled")
                return {"FINISHED"}

            try:
                result = import_assetkit_file_auto(
                    self.filepath,
                    assetkit_library,
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
                    clean_viewport_overlays=self.clean_viewport_overlays,
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
                    self.report({"WARNING"}, "AssetKit loaded the file but no importable objects were found")
                else:
                    self.report({"INFO"}, f"Imported {len(result)} object(s) through AssetKit")
            else:
                self.report({"INFO"}, "AssetKit progressive import started")
            return {"FINISHED"}

        if self.build_mode == "PROGRESSIVE":
            if _should_defer_async_import(context):
                _schedule_progressive_import(
                    self.filepath,
                    assetkit_library,
                    load_options,
                    context.collection,
                    self.progressive_batch_size,
                    self.focus_import,
                    self.placement,
                    scene_was_empty,
                    focus_camera,
                    self.select_imported_objects,
                    self.mesh_shading,
                    self.set_viewport_shading,
                    self.clean_viewport_overlays,
                    self.fit_timeline,
                )
                self.report({"INFO"}, "AssetKit progressive import scheduled")
                return {"FINISHED"}

            import_assetkit_file_progressive(
                self.filepath,
                assetkit_library,
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
                clean_viewport_overlays=self.clean_viewport_overlays,
                fit_timeline=self.fit_timeline,
            )
            self.report({"INFO"}, "AssetKit progressive import started")
            return {"FINISHED"}

        if _should_defer_blocking_import(context):
            _schedule_blocking_import(
                self.filepath,
                assetkit_library,
                load_options,
                context.collection,
                self.focus_import,
                self.placement,
                scene_was_empty,
                focus_camera,
                self.select_imported_objects,
                self.mesh_shading,
                self.set_viewport_shading,
                self.clean_viewport_overlays,
                self.fit_timeline,
            )
            self.report({"INFO"}, "AssetKit import scheduled")
            return {"FINISHED"}

        try:
            objects = import_assetkit_file(
                self.filepath,
                assetkit_library,
                load_options,
                collection=context.collection,
                focus_mode=self.focus_import,
                placement_mode=self.placement,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=self.select_imported_objects,
                shading_mode=self.mesh_shading,
                set_viewport_shading=self.set_viewport_shading,
                clean_viewport_overlays=self.clean_viewport_overlays,
                fit_timeline=self.fit_timeline,
            )
        except AssetKitError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except OSError as exc:
            self.report({"ERROR"}, f"Could not load AssetKit library: {exc}")
            return {"CANCELLED"}

        if not objects:
            self.report({"WARNING"}, "AssetKit loaded the file but no importable objects were found")
            return {"FINISHED"}

        self.report({"INFO"}, f"Imported {len(objects)} object(s) through AssetKit")
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
        mesh_box.separator()
        mesh_box.prop(self, "import_lines")
        line_box = mesh_box.column()
        line_box.enabled = self.import_lines
        line_box.prop(self, "convert_line_loop")
        line_box.prop(self, "convert_line_strip")

        load_box = layout.box()
        load_box.label(text="Loading")
        load_box.prop(self, "scene_index")
        load_box.prop(self, "build_mode")
        if self.build_mode in {"AUTO", "PROGRESSIVE"}:
            load_box.prop(self, "progressive_batch_size")
        load_box.prop(self, "texture_loading")

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
        clean_row = view_checks.row()
        clean_row.enabled = self.set_viewport_shading
        clean_row.prop(self, "clean_viewport_overlays")
        view_checks.prop(self, "fit_timeline")

    def _load_options(self) -> LoadOptions:
        return make_load_options(
            coordinate_conversion=self.coordinate_conversion,
            coordinate_system=self.coordinate_system,
            scene_index=self.scene_index,
            triangulate=self.triangulate,
            generate_normals=self.generate_normals,
            convert_triangle_strip=self.convert_triangle_strip,
            convert_triangle_fan=self.convert_triangle_fan,
            import_lines=self.import_lines,
            convert_line_loop=self.convert_line_loop,
            convert_line_strip=self.convert_line_strip,
            texture_loading=self.texture_loading,
            preserve_extras=True,
        )


def _scene_has_no_content(scene: bpy.types.Scene) -> bool:
    content_types = {"ARMATURE", "CURVE", "EMPTY", "FONT", "MESH", "META", "SURFACE"}
    return not any(obj.type in content_types for obj in scene.objects)


def _should_defer_blocking_import(context) -> bool:
    return not bpy.app.background


def _should_defer_async_import(context) -> bool:
    return not bpy.app.background


def _auto_should_import_blocking(filepath: str) -> bool:
    if os.path.splitext(filepath or "")[1].lower() not in _FAST_BLOCKING_EXTENSIONS:
        return False
    try:
        return os.path.getsize(filepath) <= _FAST_BLOCKING_MAX_BYTES
    except OSError:
        return True


def _schedule_auto_import(
    filepath: str,
    assetkit_library: str,
    load_options: LoadOptions,
    collection: bpy.types.Collection,
    batch_size: int,
    focus_mode: str,
    placement_mode: str,
    scene_was_empty: bool,
    focus_camera: bpy.types.Object | None,
    select_imported: bool,
    shading_mode: str,
    set_viewport_shading: bool,
    clean_viewport_overlays: bool,
    fit_timeline: bool,
) -> None:
    def run_import() -> None:
        _set_status("AssetKit is importing...")
        update_loading_hud("AssetKit is importing")
        try:
            import_assetkit_file_auto(
                filepath,
                assetkit_library,
                load_options,
                collection=collection,
                batch_size=batch_size,
                focus_mode=focus_mode,
                placement_mode=placement_mode,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=select_imported,
                shading_mode=shading_mode,
                set_viewport_shading=set_viewport_shading,
                clean_viewport_overlays=clean_viewport_overlays,
                fit_timeline=fit_timeline,
            )
        except (AssetKitError, OSError) as exc:
            print(f"AssetKit import failed: {exc}")
            _show_import_error(str(exc))
            _set_status(None)
            finish_loading_hud()
        return None

    start_loading_hud("AssetKit is importing", delay=0.0)
    _set_status("AssetKit is importing...")
    bpy.app.timers.register(run_import, first_interval=_DEFERRED_ASYNC_DELAY)


def _schedule_progressive_import(
    filepath: str,
    assetkit_library: str,
    load_options: LoadOptions,
    collection: bpy.types.Collection,
    batch_size: int,
    focus_mode: str,
    placement_mode: str,
    scene_was_empty: bool,
    focus_camera: bpy.types.Object | None,
    select_imported: bool,
    shading_mode: str,
    set_viewport_shading: bool,
    clean_viewport_overlays: bool,
    fit_timeline: bool,
) -> None:
    def run_import() -> None:
        _set_status("AssetKit is importing...")
        update_loading_hud("AssetKit is importing")
        try:
            import_assetkit_file_progressive(
                filepath,
                assetkit_library,
                load_options,
                collection=collection,
                batch_size=batch_size,
                focus_mode=focus_mode,
                placement_mode=placement_mode,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=select_imported,
                shading_mode=shading_mode,
                set_viewport_shading=set_viewport_shading,
                clean_viewport_overlays=clean_viewport_overlays,
                fit_timeline=fit_timeline,
            )
        except (AssetKitError, OSError) as exc:
            print(f"AssetKit import failed: {exc}")
            _show_import_error(str(exc))
            _set_status(None)
            finish_loading_hud()
        return None

    start_loading_hud("AssetKit is importing", delay=0.0)
    _set_status("AssetKit is importing...")
    bpy.app.timers.register(run_import, first_interval=_DEFERRED_ASYNC_DELAY)


def _schedule_blocking_import(
    filepath: str,
    assetkit_library: str,
    load_options: LoadOptions,
    collection: bpy.types.Collection,
    focus_mode: str,
    placement_mode: str,
    scene_was_empty: bool,
    focus_camera: bpy.types.Object | None,
    select_imported: bool,
    shading_mode: str,
    set_viewport_shading: bool,
    clean_viewport_overlays: bool,
    fit_timeline: bool,
    delay: float = _DEFERRED_BLOCKING_DELAY,
) -> None:
    def run_import() -> None:
        _set_status("AssetKit is importing...")
        update_loading_hud("AssetKit is importing")
        try:
            objects = import_assetkit_file(
                filepath,
                assetkit_library,
                load_options,
                collection=collection,
                focus_mode=focus_mode,
                placement_mode=placement_mode,
                scene_was_empty=scene_was_empty,
                focus_camera=focus_camera,
                select_imported=select_imported,
                shading_mode=shading_mode,
                set_viewport_shading=set_viewport_shading,
                clean_viewport_overlays=clean_viewport_overlays,
                fit_timeline=fit_timeline,
            )
        except (AssetKitError, OSError) as exc:
            print(f"AssetKit import failed: {exc}")
            _show_import_error(str(exc))
        finally:
            _set_status(None)
            finish_loading_hud()
        return None

    start_loading_hud("AssetKit is importing", delay=0.0)
    _set_status("AssetKit is importing...")
    bpy.app.timers.register(run_import, first_interval=delay)


def _set_status(text: str | None) -> None:
    try:
        workspace = bpy.context.workspace
        if workspace:
            workspace.status_text_set(text)
    except Exception:
        pass


def _show_import_error(message: str) -> None:
    def draw(self, _context):
        self.layout.label(text=message)

    try:
        bpy.context.window_manager.popup_menu(draw, title="AssetKit Import Error", icon="ERROR")
    except Exception:
        pass


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


_MORPH_PRESET_ITEMS_CACHE = ()


def _morph_preset_items(self, context):
    del self

    global _MORPH_PRESET_ITEMS_CACHE

    names = _morph_preset_names(context)
    items = [("__RESET__", "Reset", "Set all AssetKit morph weights to zero")]
    items.extend(
        (
            _morph_preset_identifier(name),
            name,
            "Apply this AssetKit morph preset",
        )
        for name in names
    )
    _MORPH_PRESET_ITEMS_CACHE = tuple(items)
    return _MORPH_PRESET_ITEMS_CACHE


def _morph_preset_name_from_enum(context, identifier: str) -> str:
    if identifier == "__RESET__":
        return ""
    for name in _morph_preset_names(context):
        if _morph_preset_identifier(name) == identifier:
            return name
    return identifier


def _morph_preset_names(context) -> list[str]:
    names = set()
    objects = getattr(context, "scene", None).objects if getattr(context, "scene", None) else []
    for obj in objects:
        count = int(obj.get("assetkit_morph_preset_count") or 0)
        for index in range(count):
            name = obj.get(f"assetkit_morph_preset_{index}_name")
            if name:
                names.add(str(name))
    return sorted(names)


def _morph_preset_identifier(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return f"MORPH_PRESET_{digest}"


class ASSETKIT_OT_apply_morph_preset(bpy.types.Operator):
    bl_idname = "assetkit.apply_morph_preset"
    bl_label = "Apply AssetKit Morph Preset"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(
        name="Preset",
        description="Morph preset to apply",
        items=_morph_preset_items,
    )
    preset_name: bpy.props.StringProperty(
        name="Preset",
        description="Morph preset name. Leave empty to reset morph weights",
        default="",
        options={"HIDDEN"},
    )
    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description="Apply the morph preset only to selected objects",
        default=False,
    )

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        preset_name = self.preset_name or _morph_preset_name_from_enum(context, self.preset)
        changed = _apply_morph_preset(context, preset_name, self.selected_only)
        if changed == 0:
            self.report({"WARNING"}, "No matching AssetKit morph presets found")
        else:
            label = preset_name or "reset"
            self.report({"INFO"}, f"Applied AssetKit morph preset '{label}' to {changed} object(s)")
        return {"FINISHED"}


def _apply_morph_preset(context, preset_name: str, selected_only: bool) -> int:
    objects = context.selected_objects if selected_only else context.scene.objects
    changed = 0
    for obj in objects:
        if obj.type != "MESH" or not obj.data or not obj.data.shape_keys:
            continue
        weights = _morph_preset_weights(obj, preset_name)
        if weights is None:
            continue
        _set_shape_key_weights(obj, weights)
        changed += 1
    return changed


def _morph_preset_weights(obj: bpy.types.Object, preset_name: str) -> list[float] | None:
    key_count = max(0, len(obj.data.shape_keys.key_blocks) - 1) if obj.data.shape_keys else 0
    if key_count <= 0:
        return None
    if not preset_name:
        return [0.0] * key_count

    count = int(obj.get("assetkit_morph_preset_count") or 0)
    for index in range(count):
        prefix = f"assetkit_morph_preset_{index}"
        if obj.get(f"{prefix}_name") != preset_name:
            continue
        try:
            raw = json.loads(obj.get(f"{prefix}_weights_json") or "[]")
        except (TypeError, ValueError):
            return None
        weights = [float(value) for value in raw[:key_count]]
        if len(weights) < key_count:
            weights.extend([0.0] * (key_count - len(weights)))
        return weights
    return None


def _set_shape_key_weights(obj: bpy.types.Object, weights: list[float]) -> None:
    shape_keys = obj.data.shape_keys
    for index, value in enumerate(weights, start=1):
        if index >= len(shape_keys.key_blocks):
            break
        shape_keys.key_blocks[index].value = value
