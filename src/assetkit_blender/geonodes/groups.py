"""Reusable groups of built-in nodes; no per-point Python evaluation."""

import bpy

NAMES = {"OBJECT": "AssetKit Object Source", "CROP": "AssetKit Crop Points", "OPACITY": "AssetKit Splat Opacity"}


def get_group(kind):
    for tree in bpy.data.node_groups:
        if tree.get("assetkit_geometry_group") == kind and tree.get("assetkit_geometry_version") == 1:
            return tree
    tree = bpy.data.node_groups.new(NAMES[kind], "GeometryNodeTree")
    tree["assetkit_geometry_group"] = kind
    tree["assetkit_geometry_version"] = 1

    def socket(name, direction, type, default=None):
        value = tree.interface.new_socket(name=name, in_out=direction, socket_type=type)
        if default is not None:
            value.default_value = default
        return value

    socket("Geometry", "OUTPUT", "NodeSocketGeometry")
    source = tree.nodes.new("NodeGroupInput")
    output = tree.nodes.new("NodeGroupOutput")
    source.location = (-600, 0)
    output.location = (600, 0)
    link = tree.links.new
    if kind == "OBJECT":
        socket("Object", "INPUT", "NodeSocketObject")
        info = tree.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "ORIGINAL"
        info.inputs["As Instance"].default_value = True
        link(source.outputs["Object"], info.inputs["Object"])
        link(info.outputs["Geometry"], output.inputs["Geometry"])
        return tree
    socket("Geometry", "INPUT", "NodeSocketGeometry")
    realize = tree.nodes.new("GeometryNodeRealizeInstances")
    realize.location = (-360, 180)
    link(source.outputs["Geometry"], realize.inputs["Geometry"])
    if kind == "CROP":
        socket("Min", "INPUT", "NodeSocketVector", (-1, -1, -1))
        socket("Max", "INPUT", "NodeSocketVector", (1, 1, 1))
        position = tree.nodes.new("GeometryNodeInputPosition")
        clamp = tree.nodes.new("ShaderNodeVectorMath")
        clamp.operation = "MAXIMUM"
        link(position.outputs["Position"], clamp.inputs[0])
        link(source.outputs["Min"], clamp.inputs[1])
        upper = tree.nodes.new("ShaderNodeVectorMath")
        upper.operation = "MINIMUM"
        link(clamp.outputs["Vector"], upper.inputs[0])
        link(source.outputs["Max"], upper.inputs[1])
        distance = tree.nodes.new("ShaderNodeVectorMath")
        distance.operation = "DISTANCE"
        link(position.outputs["Position"], distance.inputs[0])
        link(upper.outputs["Vector"], distance.inputs[1])
        outside = tree.nodes.new("ShaderNodeMath")
        outside.operation = "GREATER_THAN"
        link(distance.outputs["Value"], outside.inputs[0])
        outside.inputs[1].default_value = 0.0
        delete = tree.nodes.new("GeometryNodeDeleteGeometry")
        delete.domain = "POINT"
        link(realize.outputs["Geometry"], delete.inputs["Geometry"])
        link(outside.outputs[0], delete.inputs["Selection"])
        link(delete.outputs["Geometry"], output.inputs["Geometry"])
    elif kind == "OPACITY":
        factor = socket("Opacity", "INPUT", "NodeSocketFloat", 1.0)
        factor.min_value, factor.max_value = 0.0, 1.0
        attr = tree.nodes.new("GeometryNodeInputNamedAttribute")
        attr.data_type = "FLOAT_COLOR"
        attr.inputs["Name"].default_value = "radiance:base"
        separate = tree.nodes.new("FunctionNodeSeparateColor")
        combine = tree.nodes.new("FunctionNodeCombineColor")
        multiply = tree.nodes.new("ShaderNodeMath")
        multiply.operation, multiply.use_clamp = "MULTIPLY", True
        link(attr.outputs["Attribute"], separate.inputs["Color"])
        for name in ("Red", "Green", "Blue"):
            link(separate.outputs[name], combine.inputs[name])
        link(separate.outputs["Alpha"], multiply.inputs[0])
        link(source.outputs["Opacity"], multiply.inputs[1])
        link(multiply.outputs[0], combine.inputs["Alpha"])
        store = tree.nodes.new("GeometryNodeStoreNamedAttribute")
        store.data_type, store.domain = "FLOAT_COLOR", "POINT"
        store.inputs["Name"].default_value = "radiance:base"
        link(realize.outputs["Geometry"], store.inputs["Geometry"])
        link(attr.outputs["Exists"], store.inputs["Selection"])
        link(combine.outputs["Color"], store.inputs["Value"])
        link(store.outputs["Geometry"], output.inputs["Geometry"])
    for index, node in enumerate(n for n in tree.nodes if n not in (source, output, realize)):
        node.location = (-360 + (index % 4) * 210, -120 - (index // 4) * 220)
    return tree
