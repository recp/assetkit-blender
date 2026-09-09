import bpy
from bpy_extras.io_utils import ImportHelper

from . import runtime


class AssetKitSourceItem(bpy.types.PropertyGroup):
    pass


class AssetKitGeometrySource(bpy.types.GeometryNodeCustomGroup):
    bl_idname = "AssetKitGeometrySource"
    bl_label = "AssetKit Source"
    bl_description = "Cached file geometry; sequences follow the assigned scene's timeline"
    bl_width_default = 280

    filepath: bpy.props.StringProperty(name="File", subtype="FILE_PATH", update=runtime.changed)
    enabled: bpy.props.BoolProperty(name="Enabled", default=True, update=runtime.changed)
    scene_index: bpy.props.IntProperty(name="Scene Index", default=-1, min=-1,
                                      description="-1: active/default source scene; otherwise a zero-based scene index",
                                      update=runtime.changed)
    node_path: bpy.props.StringProperty(name="Node", description="Empty: all geometry; otherwise source node path, including descendants",
                                       update=runtime.changed)
    source_nodes: bpy.props.CollectionProperty(type=AssetKitSourceItem)
    scene_names: bpy.props.StringProperty(options={"SKIP_SAVE"})
    sequence: bpy.props.BoolProperty(name="Sequence", update=runtime.changed)
    owner_scene: bpy.props.PointerProperty(name="Timeline", type=bpy.types.Scene, update=runtime.changed)
    start_frame: bpy.props.IntProperty(name="Start", default=1, update=runtime.changed)
    first_frame: bpy.props.IntProperty(name="First File", default=1, min=0, update=runtime.changed)
    last_frame: bpy.props.IntProperty(name="Last File", default=250, min=0, update=runtime.changed)
    frame_step: bpy.props.IntProperty(name="Hold Frames", default=1, min=1, update=runtime.changed)
    loop: bpy.props.BoolProperty(name="Loop", update=runtime.changed)
    missing: bpy.props.EnumProperty(name="Missing / Invalid", default="EMPTY", update=runtime.changed,
                                    items=(("EMPTY", "Empty", "Output no geometry and show the error"),
                                           ("HOLD", "Hold Previous", "Keep the last valid source; show the error")))
    status: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def init(self, context):
        tree = bpy.data.node_groups.new("AssetKit Source", "GeometryNodeTree")
        tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        translation = tree.interface.new_socket(name="Translation", in_out="INPUT", socket_type="NodeSocketVector")
        translation.subtype = "TRANSLATION"
        tree.interface.new_socket(name="Rotation", in_out="INPUT", socket_type="NodeSocketRotation")
        scale = tree.interface.new_socket(name="Scale", in_out="INPUT", socket_type="NodeSocketVector")
        scale.default_value = (1, 1, 1)
        source = tree.nodes.new("GeometryNodeCollectionInfo")
        source.name = "Source"
        source.transform_space = "ORIGINAL"
        source.inputs["Separate Children"].default_value = True
        source.inputs["Reset Children"].default_value = False
        inputs = tree.nodes.new("NodeGroupInput")
        inputs.location.y = -180
        transform = tree.nodes.new("GeometryNodeTransform")
        transform.location.x = 240
        tree.links.new(source.outputs["Instances"], transform.inputs["Geometry"])
        for name in ("Translation", "Rotation", "Scale"):
            tree.links.new(inputs.outputs[name], transform.inputs[name])
        output = tree.nodes.new("NodeGroupOutput")
        output.location.x = 480
        tree.links.new(transform.outputs["Geometry"], output.inputs["Geometry"])
        self.node_tree = tree
        self.owner_scene = (context or bpy.context).scene
        runtime.changed(self)

    def copy(self, _node):
        self.node_tree = self.node_tree.copy()
        # A copied source shares cached geometry, not its mutable selection collection.
        if "assetkit_source_selection" in self.node_tree:
            del self.node_tree["assetkit_source_selection"]
        runtime.changed(self)

    def free(self):
        runtime.forget(self)
        tree = self.node_tree
        self.node_tree = None
        if (tree is not None and not tree.use_fake_user
                and not bpy.data.user_map(subset={tree}).get(tree)):
            collection = tree.get("assetkit_source_selection")
            bpy.data.node_groups.remove(tree)
            if collection is not None and collection.users == 0:
                bpy.data.collections.remove(collection)

    def draw_buttons(self, context, layout):
        layout.prop(self, "enabled")
        row = layout.row(align=True)
        row.prop(self, "filepath", text="")
        op = row.operator("assetkit.source_file", text="", icon="FILE_FOLDER")
        op.tree_name, op.node_name = self.id_data.name, self.name
        layout.prop(self, "scene_index")
        if self.scene_names:
            layout.label(text=self.scene_names)
        layout.prop_search(self, "node_path", self, "source_nodes", text="Node")
        layout.label(text="Empty Node: all geometry")
        layout.prop(self, "sequence")
        if self.sequence:
            layout.label(text="File pattern: capture_####.spz")
            layout.prop(self, "owner_scene")
            row = layout.row(align=True)
            row.prop(self, "first_frame")
            row.prop(self, "last_frame")
            row = layout.row(align=True)
            row.prop(self, "start_frame")
            row.prop(self, "frame_step")
            layout.prop(self, "loop")
        layout.prop(self, "missing")
        layout.operator("assetkit.reload_sources", icon="FILE_REFRESH")
        if self.status:
            layout.label(text=self.status)


class ASSETKIT_OT_source_file(bpy.types.Operator, ImportHelper):
    bl_idname = "assetkit.source_file"
    bl_label = "Choose AssetKit Source"
    bl_options = {"UNDO", "INTERNAL"}
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(default="*.gltf;*.glb;*.dae;*.obj;*.stl;*.ply;*.spz;*.lgsc;*.3mf;*.zip", options={"HIDDEN"})
    tree_name: bpy.props.StringProperty(options={"HIDDEN"})
    node_name: bpy.props.StringProperty(options={"HIDDEN"})

    def execute(self, _context):
        tree = bpy.data.node_groups.get(self.tree_name)
        node = tree.nodes.get(self.node_name) if tree else None
        if node is None or node.bl_idname != "AssetKitGeometrySource":
            return {"CANCELLED"}
        node.filepath = self.filepath
        runtime.flush()
        return {"FINISHED"}


class ASSETKIT_OT_reload_sources(bpy.types.Operator):
    bl_idname = "assetkit.reload_sources"
    bl_label = "Reload Sources"
    bl_description = "Reload shared file sources and their external geometry buffers"

    def execute(self, _context):
        runtime.reload_sources()
        return {"FINISHED"}


class ASSETKIT_OT_add_geometry_group(bpy.types.Operator):
    bl_idname = "assetkit.add_geometry_group"
    bl_label = "Add AssetKit Geometry Group"
    bl_options = {"REGISTER", "UNDO"}
    kind: bpy.props.EnumProperty(items=(("OBJECT", "Object Source", "Use an existing Blender object"),
                                        ("CROP", "Crop Points", "Keep points inside an axis-aligned box"),
                                        ("OPACITY", "Splat Opacity", "Multiply Gaussian opacity without changing radiance")))

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and space.type == "NODE_EDITOR" and space.tree_type == "GeometryNodeTree" and space.edit_tree

    def execute(self, context):
        from .groups import get_group
        node = context.space_data.edit_tree.nodes.new("GeometryNodeGroup")
        node.node_tree = get_group(self.kind)
        node.location = context.space_data.cursor_location
        if self.kind == "OBJECT" and context.active_object:
            # Do not create an Object Info dependency cycle on the modifier owner.
            source = next((obj for obj in context.selected_objects if obj != context.active_object), None)
            node.inputs["Object"].default_value = source
        return {"FINISHED"}


class ASSETKIT_MT_geometry_nodes(bpy.types.Menu):
    bl_label = "AssetKit"

    def draw(self, _context):
        op = self.layout.operator("node.add_node", text="File / Sequence Source")
        op.type, op.use_transform = "AssetKitGeometrySource", True
        for kind, title in (("OBJECT", "Object Source"), ("CROP", "Crop Points"), ("OPACITY", "Splat Opacity")):
            self.layout.operator("assetkit.add_geometry_group", text=title).kind = kind


def menu(self, context):
    if context.space_data and context.space_data.tree_type == "GeometryNodeTree":
        self.layout.menu("ASSETKIT_MT_geometry_nodes")
        self.layout.separator()


def menu_import(self, context):
    if context.space_data and context.space_data.tree_type == "GeometryNodeTree":
        op = self.layout.operator("node.add_node", text="AssetKit File / Sequence")
        op.type, op.use_transform = "AssetKitGeometrySource", True
        self.layout.separator()


CLASSES = (AssetKitSourceItem, AssetKitGeometrySource, ASSETKIT_OT_source_file,
           ASSETKIT_OT_reload_sources, ASSETKIT_OT_add_geometry_group, ASSETKIT_MT_geometry_nodes)
