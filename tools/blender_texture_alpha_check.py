"""Exercise Blender image alpha interpretation used by AssetKit imports.

Run inside Blender, for example:

  /Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
    --python tools/blender_texture_alpha_check.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assetkit_blender import importer  # noqa: E402


def main() -> None:
    dds = bpy.data.images.new("AssetKit DDS alpha check", width=1, height=1, alpha=True)
    dds.alpha_mode = "STRAIGHT"
    importer._register_texture_image(dds, "/tmp/assetkit-alpha-check.dds", "sRGB")
    if dds.alpha_mode != "CHANNEL_PACKED":
        raise AssertionError(f"DDS alpha mode is {dds.alpha_mode!r}, expected 'CHANNEL_PACKED'")

    png = bpy.data.images.new("AssetKit PNG alpha check", width=1, height=1, alpha=True)
    png.alpha_mode = "STRAIGHT"
    importer._register_texture_image(png, "/tmp/assetkit-alpha-check.png", "sRGB")
    if png.alpha_mode != "STRAIGHT":
        raise AssertionError(f"non-DDS alpha mode changed to {png.alpha_mode!r}")

    cached = importer._cached_texture_image("/tmp/assetkit-alpha-check.dds", "sRGB")
    if cached is not dds or cached.alpha_mode != "CHANNEL_PACKED":
        raise AssertionError("cached DDS image did not preserve channel-packed alpha")

    print("AssetKit Blender texture alpha checks passed")


if __name__ == "__main__":
    main()
