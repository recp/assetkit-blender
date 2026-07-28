from __future__ import annotations


def is_color_attribute_name(name: str) -> bool:
    return name == "Color" or name.startswith("Color.")
