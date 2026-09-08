from __future__ import annotations

import bpy
import numpy as np

from .buffers import buffer_view


def create_pointcloud(data):
    """Build a point cloud using Blender's Gaussian attribute layout."""
    points = bpy.data.pointclouds.new(data.name)
    if not hasattr(points, "resize"):
        bpy.data.pointclouds.remove(points)
        return None

    try:
        count = data.vertex_count
        points.resize(count)
        positions = buffer_view(data.vertices_f32, "f")
        if positions is None:
            raise RuntimeError("AssetKit returned no Gaussian positions")
        points.attributes["position"].data.foreach_set("vector", positions)

        attrs = {attr.name: attr for attr in data.point_attrs or []}

        def values(name, width):
            attr = attrs.get(name)
            source = buffer_view(attr.values_f32, "f") if attr else None
            if source is None or attr.width != width or len(source) != count * width:
                raise RuntimeError(f"AssetKit returned an invalid Gaussian attribute: {name}")
            return np.frombuffer(source, dtype=np.float32).reshape(count, width)

        scales = values("scale", 3)
        scale_attr = points.attributes.new("scale", "FLOAT_VECTOR", "POINT")
        scale_attr.data.foreach_set("vector", scales.ravel())

        # AssetKit uses xyzw, Blender's quaternion attribute uses wxyz.
        rotations = np.ascontiguousarray(values("rotation", 4)[:, [3, 0, 1, 2]])
        rotation_attr = points.attributes.new("rotation", "QUATERNION", "POINT")
        rotation_attr.data.foreach_set("value", rotations.ravel())

        base = np.empty((count, 4), dtype=np.float32)
        base[:, :3] = values("radiance:dc", 3)
        base[:, 3] = values("opacity", 1)[:, 0]
        base_attr = points.attributes.new("radiance:base", "FLOAT_COLOR", "POINT")
        base_attr.data.foreach_set("color", base.ravel())

        for index in range((data.gsplat_sh_degree + 1) ** 2 - 1):
            name = f"radiance:sh_{index}"
            attr = points.attributes.new(name, "FLOAT_VECTOR", "POINT")
            attr.data.foreach_set("vector", values(name, 3).ravel())

        native_type = points.bl_rna.properties.get("type")
        if native_type and "GAUSSIAN_SPLAT" in native_type.enum_items:
            points.type = "GAUSSIAN_SPLAT"
        else:
            # Earlier Blender releases display ordinary points. Keep their
            # radius usable without modifying the Gaussian scale attribute.
            radius = points.attributes.new("radius", "FLOAT", "POINT")
            radius.data.foreach_set("value", np.max(scales, axis=1))
        points["assetkit_gaussian_splat_antialiased"] = bool(data.gsplat_antialiased)
        points["assetkit_gaussian_splat_sh_degree"] = int(data.gsplat_sh_degree)
        points["assetkit_gaussian_splat_color_space"] = int(data.gsplat_color_space)
        points.update_tag()
        return points
    except Exception:
        bpy.data.pointclouds.remove(points)
        raise
