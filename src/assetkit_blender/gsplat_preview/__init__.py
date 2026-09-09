"""Optional Solid-viewport preview; the imported point cloud remains editable."""

import bpy
from bpy.app.handlers import persistent


ENABLED = 'assetkit_gaussian_preview'
DISPLAY = 'assetkit_gaussian_previous_display'
_handler = None
_renderer = None
_signature = None
_revision = 0
_error = ''
_enabled = set()
_cloud_views = {}


class _PointCloudView:
    # GeometrySet owns the temporary PointCloud exposed by Blender's Python API.
    __slots__ = ('geometry', 'data')

    def __init__(self, geometry, data):
        self.geometry, self.data = geometry, data

    def __getattr__(self, name):
        return getattr(self.data, name)


def pointcloud(obj, cache=None):
    if obj is None or obj.type not in {'MESH', 'POINTCLOUD', 'CURVE', 'CURVES', 'FONT', 'SURFACE', 'VOLUME'}:
        return None
    if not obj.is_evaluated and not obj.modifiers:
        return obj.data if obj.type == 'POINTCLOUD' else None
    if not obj.is_evaluated:
        obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    key = (obj.as_pointer(), _revision)
    if cache is not None and key in cache:
        return cache[key]
    geometry = obj.evaluated_geometry()
    data = geometry.pointcloud
    result = _PointCloudView(geometry, data) if data is not None else None
    if cache is not None:
        cache[key] = result
    return result


def is_splat_cloud(cloud):
    return (cloud is not None and 'radiance:base' in cloud.attributes
            and 'scale' in cloud.attributes and 'rotation' in cloud.attributes)


def is_splat(obj):
    return is_splat_cloud(pointcloud(obj))


def is_native(obj):
    return getattr(pointcloud(obj), 'type', '') == 'GAUSSIAN_SPLAT'


def clear(geometry=True):
    global _renderer, _signature
    _renderer = None
    _signature = None
    if geometry:
        _cloud_views.clear()


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def enable(obj, enabled=True):
    global _error
    if enabled and (not is_splat(obj) or is_native(obj)):
        return
    if obj.library is not None and obj.override_library is None:
        raise ValueError('Make a local object or library override to enable Gaussian preview')
    if enabled:
        if DISPLAY not in obj:
            obj[DISPLAY] = obj.display_type
        # WIRE still draws every point as a square in Blender's overlay pass.
        obj.display_type = 'BOUNDS'
    elif DISPLAY in obj:
        obj.display_type = obj[DISPLAY]
        del obj[DISPLAY]
    obj[ENABLED] = enabled
    if enabled:
        _enabled.add(obj.as_pointer())
    else:
        _enabled.discard(obj.as_pointer())
    _error = ''
    clear()
    redraw()


def solid_view(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.shading.type = 'SOLID'


def enable_imported(objects):
    if bpy.app.background or _handler is None:
        return
    addon = bpy.context.preferences.addons.get(__package__.rsplit('.', 1)[0])
    if addon and not addon.preferences.gaussian_preview:
        return
    clouds = [obj for obj in objects if is_splat(obj) and not is_native(obj)]
    if not clouds:
        return
    for obj in clouds:
        enable(obj)
    solid_view(bpy.context)


def _draw():
    global _renderer, _signature, _error
    context = bpy.context
    space = context.space_data
    if (not _enabled or _error or not context.region_data or space.type != 'VIEW_3D'
            or space.shading.type not in {'SOLID', 'WIREFRAME'}
            or not space.show_object_viewport_pointcloud):
        return
    try:
        entries, signature = [], []
        for key in tuple(_cloud_views):
            if key[1] != _revision:
                del _cloud_views[key]
        graph = context.evaluated_depsgraph_get()
        for instance in graph.object_instances:
            obj = instance.object
            original = obj.original
            owner = instance.parent.original if instance.is_instance and instance.parent else original
            if not instance.show_self or not (original.get(ENABLED) or owner.get(ENABLED)):
                continue
            if not instance.is_instance and not original.visible_get(viewport=space):
                continue
            cloud = pointcloud(obj, _cloud_views)
            if not is_splat_cloud(cloud) or getattr(cloud, 'type', '') == 'GAUSSIAN_SPLAT':
                if not instance.is_instance and DISPLAY in original:
                    previous = original[DISPLAY]
                    if original.display_type != previous:
                        original.display_type = previous
                continue
            if not instance.is_instance and DISPLAY in original and original.display_type != 'BOUNDS':
                original.display_type = 'BOUNDS'
            matrix = instance.matrix_world.copy()
            entries.append((cloud, matrix))
            signature.append((original.as_pointer(), cloud.as_pointer(), len(cloud.points)))
        if not entries:
            clear(geometry=False)
            return
        signature = (_revision, tuple(signature))
        if signature != _signature:
            from .renderer import Renderer
            addon = context.preferences.addons.get(__package__.rsplit('.', 1)[0])
            budget = getattr(addon.preferences, 'gaussian_preview_mib', 1024) if addon else 1024
            clear(geometry=False)
            _renderer = Renderer(entries, budget * 1024 * 1024)
            _signature = signature
        else:
            _renderer.update_transforms(entries)
        region = context.region_data
        _renderer.draw(region.view_matrix, region.window_matrix,
                       (context.region.width, context.region.height), context.region.as_pointer())
    except Exception as exc:
        _error = str(exc)
        clear()
        # Do not leave an invisible object or retry a failed shader every redraw.
        _restore()
        print('AssetKit Gaussian preview:', _error)


@persistent
def _changed(_scene, graph):
    global _revision
    if not _enabled:
        return
    for update in graph.updates:
        item = update.id
        if ((isinstance(item, bpy.types.PointCloud) and 'radiance:base' in item.attributes)
                or (isinstance(item, bpy.types.Object) and update.is_updated_geometry
                    and (item.get(ENABLED) or item.type == 'POINTCLOUD'))):
            _revision += 1
            break


@persistent
def _reset(*_args):
    global _error
    clear()
    _error = ''
    _enabled.clear()


@persistent
def _restore(*_args):
    for obj in bpy.data.objects:
        if DISPLAY in obj and (obj.library is None or obj.override_library is not None):
            obj.display_type = obj[DISPLAY]


@persistent
def _resume(*_args):
    global _error
    clear()
    _error = ''
    _enabled.clear()
    for obj in bpy.data.objects:
        if (obj.get(ENABLED) and is_splat(obj) and not is_native(obj)
                and (obj.library is None or obj.override_library is not None)):
            _enabled.add(obj.as_pointer())
            if DISPLAY not in obj:
                obj[DISPLAY] = obj.display_type
            if not bpy.app.background:
                obj.display_type = 'BOUNDS'


class ASSETKIT_OT_gaussian_preview(bpy.types.Operator):
    bl_idname = 'assetkit.gaussian_preview'
    bl_label = 'Gaussian Preview'
    bl_description = 'Toggle the GPU Gaussian preview in Solid shading; does not affect F12 rendering'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return ((is_splat(context.object) or context.object and DISPLAY in context.object)
                and context.object.mode == 'OBJECT'
                and not is_native(context.object))

    def execute(self, context):
        active = bool(context.object.get(ENABLED)) and not _error
        try:
            for obj in context.selected_objects or [context.object]:
                enable(obj, not active)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if not active:
            solid_view(context)
        return {'FINISHED'}


class ASSETKIT_OT_edit_gaussian_points(bpy.types.Operator):
    bl_idname = 'assetkit.edit_gaussian_points'
    bl_label = 'Edit Points'
    bl_description = 'Disable the custom preview and edit the original points using Blender selection tools'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return (is_splat(obj) and obj.type == 'POINTCLOUD' and obj.mode == 'OBJECT' and obj.is_editable
                and obj.data.is_editable and bpy.ops.object.mode_set.poll())

    def execute(self, context):
        enabled = [obj for obj in context.selected_objects
                   if is_splat(obj) and obj.get(ENABLED) and not is_native(obj)]
        try:
            for obj in enabled:
                enable(obj, False)
            if bpy.ops.object.mode_set(mode='EDIT') != {'FINISHED'}:
                raise ValueError('Point editing is unavailable for this object')
        except (RuntimeError, ValueError) as exc:
            for obj in enabled:
                enable(obj)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class ASSETKIT_OT_separate_gaussian_points(bpy.types.Operator):
    bl_idname = 'assetkit.separate_gaussian_points'
    bl_label = 'Separate Selected'
    bl_description = 'Separate selected points with Blender, preserving Gaussian color space and antialiasing metadata'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not is_splat(context.object) or context.object.mode != 'EDIT':
            return False
        if len(context.objects_in_mode) != 1:
            cls.poll_message_set('Edit one cloud at a time to separate Gaussian points')
            return False
        return bpy.ops.pointcloud.separate.poll()

    def execute(self, context):
        cloud = context.object.data
        metadata = {name: value for name, value in cloud.items()
                    if name.startswith('assetkit_gaussian_splat_')}
        before = {data.as_pointer() for data in bpy.data.pointclouds}
        result = bpy.ops.pointcloud.separate()
        if result == {'FINISHED'}:
            # Blender copies point attributes, but not the PointCloud's ID properties.
            for data in bpy.data.pointclouds:
                if data.as_pointer() not in before:
                    for name, value in metadata.items():
                        data[name] = value
            clear()
            redraw()
        return result


class ASSETKIT_PT_gaussian_preview(bpy.types.Panel):
    bl_label = 'Gaussian Preview'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AssetKit'

    @classmethod
    def poll(cls, context):
        return is_splat(context.object) or context.object and DISPLAY in context.object

    def draw(self, context):
        layout = self.layout
        if context.object.mode == 'EDIT':
            layout.operator(ASSETKIT_OT_separate_gaussian_points.bl_idname)
            layout.operator('object.mode_set', text='Finish Editing').mode = 'OBJECT'
            if not is_native(context.object):
                layout.label(text='Enable Preview again after editing')
            return
        layout.operator(ASSETKIT_OT_edit_gaussian_points.bl_idname)
        if is_native(context.object):
            layout.label(text='Native Gaussian point cloud')
            return
        active = bool(context.object.get(ENABLED))
        layout.operator(ASSETKIT_OT_gaussian_preview.bl_idname,
                        text='Retry Preview' if _error else ('Disable Preview' if active else 'Enable Preview'),
                        depress=active and not _error)
        if _error:
            box = layout.box()
            box.alert = True
            box.label(text=_error, icon='ERROR')
        if active and context.space_data.shading.type not in {'SOLID', 'WIREFRAME'}:
            layout.label(text='Switch to Solid shading to preview', icon='INFO')
        layout.label(text='Viewport only; not an F12 renderer')


CLASSES = (ASSETKIT_OT_gaussian_preview, ASSETKIT_OT_edit_gaussian_points,
           ASSETKIT_OT_separate_gaussian_points, ASSETKIT_PT_gaussian_preview)
HANDLERS = (('depsgraph_update_post', _changed), ('load_pre', _reset),
            ('undo_post', _resume), ('redo_post', _resume), ('load_post', _resume),
            ('save_pre', _restore), ('save_post', _resume))


def register():
    global _handler
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for name, callback in HANDLERS:
        getattr(bpy.app.handlers, name).append(callback)
    if not bpy.app.background:
        _handler = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')
    bpy.app.timers.register(_resume, first_interval=0.0)


def unregister():
    global _handler
    if bpy.app.timers.is_registered(_resume):
        bpy.app.timers.unregister(_resume)
    _restore()
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
        _handler = None
    for name, callback in HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback in handlers:
            handlers.remove(callback)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _reset()
