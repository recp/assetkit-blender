#!/usr/bin/env python3
"""Check Gaussian PLY/SPZ import in Blender, including point attributes.

blender --background --factory-startup --python tools/blender_gsplat_import_check.py -- --spz capture.spz
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1] / "src")
    parser.add_argument("--spz", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    sys.path.insert(0, str(args.package_root))

    from assetkit_blender.assetkit import native_load_meshes
    from assetkit_blender.importer import import_assetkit_file

    def check(path):
        source = native_load_meshes(str(path))
        assert source is not None and len(source.meshes) == 1
        primitive = source.meshes[0]
        assert primitive.has_gsplat
        objects = import_assetkit_file(str(path), set_viewport_shading=False)
        clouds = [obj for obj in objects if obj.type == "POINTCLOUD"]
        assert len(clouds) == 1, [(obj.name, obj.type) for obj in objects]
        cloud = clouds[0].data
        count = primitive.vertex_count
        assert len(cloud.points) == count
        assert cloud["assetkit_gaussian_splat_sh_degree"] == primitive.gsplat_sh_degree
        assert cloud["assetkit_gaussian_splat_antialiased"] == primitive.gsplat_antialiased
        source_attrs = {attr.name: np.frombuffer(attr.values_f32, dtype=np.float32).reshape(count, attr.width)
                        for attr in primitive.point_attrs}

        def values(name, width, field):
            result = np.empty(count * width, dtype=np.float32)
            cloud.attributes[name].data.foreach_get(field, result)
            assert np.isfinite(result).all()
            return result.reshape(count, width)

        np.testing.assert_allclose(values("position", 3, "vector"),
                                   np.frombuffer(primitive.vertices_f32, dtype=np.float32).reshape(count, 3))
        np.testing.assert_allclose(values("scale", 3, "vector"), source_attrs["scale"])
        np.testing.assert_allclose(values("rotation", 4, "value"), source_attrs["rotation"][:, [3, 0, 1, 2]])
        base = values("radiance:base", 4, "color")
        np.testing.assert_allclose(base[:, :3], source_attrs["radiance:dc"])
        np.testing.assert_allclose(base[:, 3:], source_attrs["opacity"])
        for i in range((primitive.gsplat_sh_degree + 1) ** 2 - 1):
            name = f"radiance:sh_{i}"
            np.testing.assert_allclose(values(name, 3, "vector"), source_attrs[name])
        prop = cloud.bl_rna.properties.get("type")
        if prop and "GAUSSIAN_SPLAT" in prop.enum_items:
            assert cloud.type == "GAUSSIAN_SPLAT"
        print(f"Gaussian import OK: {path.name}, {count} splats, SH {primitive.gsplat_sh_degree}")
        return cloud

    with tempfile.TemporaryDirectory(prefix="assetkit-blender-splat-") as directory:
        path = Path(directory) / "gaussian.ply"
        fields = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2",
                  "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
        fields += [f"f_rest_{i}" for i in range(72)]
        row = [1, 2, 3, 0, 0, 0, -2, 0, 2, 0, 0, math.log(2), 0, 1, 0, 0, 0] + list(range(72))
        path.write_text("ply\nformat ascii 1.0\nelement vertex 1\n"
                        + "".join(f"property float {name}\n" for name in fields)
                        + "end_header\n" + " ".join(map(str, row)) + "\n")
        cloud = check(path)
        assert cloud["assetkit_gaussian_splat_sh_degree"] == 4
        assert "radiance:sh_23" in cloud.attributes
    if args.spz:
        check(args.spz)


if __name__ == "__main__":
    main()
