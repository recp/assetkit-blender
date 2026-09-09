"""Point/Gaussian attribute groups for Blender builds without a native splat type."""

BASE = "radiance:base"
BACKUP = "assetkit:radiance_base"
COLOR_SPACE = "assetkit:color_space"


def build(tree, kind, socket, source, output):
    link = tree.links.new
    socket("Geometry", "INPUT", "NodeSocketGeometry")
    geometry = source.outputs["Geometry"]

    def attribute(name, data_type):
        node = tree.nodes.new("GeometryNodeInputNamedAttribute")
        node.data_type = data_type
        node.inputs["Name"].default_value = name
        return node

    def store(name, data_type, value, selection=None):
        nonlocal geometry
        node = tree.nodes.new("GeometryNodeStoreNamedAttribute")
        node.data_type, node.domain = data_type, "POINT"
        node.inputs["Name"].default_value = name
        link(geometry, node.inputs["Geometry"])
        link(value, node.inputs["Value"])
        if selection is not None:
            link(selection, node.inputs["Selection"])
        geometry = node.outputs["Geometry"]

    base = attribute(BASE, "FLOAT_COLOR")
    if kind == "TO_POINTS":
        store(BACKUP, "FLOAT_COLOR", base.outputs["Attribute"], base.outputs["Exists"])
        remove = tree.nodes.new("GeometryNodeRemoveAttribute")
        remove.inputs["Name"].default_value = BASE
        link(geometry, remove.inputs["Geometry"])
        radius = socket("Radius", "INPUT", "NodeSocketFloat", 0.01)
        radius.min_value = 0
        points = tree.nodes.new("GeometryNodeSetPointRadius")
        link(remove.outputs["Geometry"], points.inputs["Points"])
        link(source.outputs["Radius"], points.inputs["Radius"])
        geometry = points.outputs["Points"]
    else:
        socket("Color", "INPUT", "NodeSocketColor", (0.5, 0.5, 0.5, 1))
        opacity = socket("Opacity", "INPUT", "NodeSocketFloat", 1.0)
        opacity.min_value, opacity.max_value = 0.0, 1.0
        socket("Scale", "INPUT", "NodeSocketVector", (0.01, 0.01, 0.01))
        socket("Rotation", "INPUT", "NodeSocketRotation")

        def fallback(existing, default, input_type):
            switch = tree.nodes.new("GeometryNodeSwitch")
            switch.input_type = input_type
            link(existing.outputs["Exists"], switch.inputs["Switch"])
            link(existing.outputs["Attribute"], switch.inputs["True"])
            link(default, switch.inputs["False"])
            return switch.outputs["Output"]

        # Color sockets are scene-linear. Encode only the DC coefficient;
        # preserve authored radiance and higher SH bands when already present.
        dc = tree.nodes.new("ShaderNodeVectorMath")
        dc.operation = "SUBTRACT"
        link(source.outputs["Color"], dc.inputs[0])
        dc.inputs[1].default_value = (0.5,) * 3
        scale = tree.nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        link(dc.outputs["Vector"], scale.inputs[0])
        scale.inputs["Scale"].default_value = 1.0 / 0.28209479177387814
        rgb = tree.nodes.new("ShaderNodeSeparateXYZ")
        link(scale.outputs["Vector"], rgb.inputs["Vector"])
        color = tree.nodes.new("FunctionNodeCombineColor")
        for axis, channel in zip("XYZ", ("Red", "Green", "Blue")):
            link(rgb.outputs[axis], color.inputs[channel])
        link(source.outputs["Opacity"], color.inputs["Alpha"])
        backup = attribute(BACKUP, "FLOAT_COLOR")
        value = fallback(base, fallback(backup, color.outputs["Color"], "RGBA"), "RGBA")

        existing = tree.nodes.new("FunctionNodeBooleanMath")
        existing.operation = "NOR"
        link(base.outputs["Exists"], existing.inputs[0])
        link(backup.outputs["Exists"], existing.inputs[1])
        linear = tree.nodes.new("FunctionNodeInputInt")
        linear.integer = 2
        store(COLOR_SPACE, "INT", linear.outputs[0], existing.outputs[0])
        store(BASE, "FLOAT_COLOR", value)
        for name, input_type, data_type in (("Scale", "VECTOR", "FLOAT_VECTOR"),
                                             ("Rotation", "ROTATION", "QUATERNION")):
            attr = attribute(name.lower(), data_type)
            store(name.lower(), data_type, fallback(attr, source.outputs[name], input_type))
    link(geometry, output.inputs["Geometry"])
    for index, node in enumerate(n for n in tree.nodes if n not in (source, output)):
        node.location = (-360 + (index % 4) * 210, -120 - (index // 4) * 220)
