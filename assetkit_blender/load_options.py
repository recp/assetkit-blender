from __future__ import annotations

from .enums import (
    AKB_LOAD_COORD_ALL,
    AKB_LOAD_COORD_RAW,
    AKB_LOAD_COORD_TRANSFORM,
    AKB_LOAD_COORD_X_UP,
    AKB_LOAD_COORD_X_UP_LH,
    AKB_LOAD_COORD_Y_UP,
    AKB_LOAD_COORD_Y_UP_LH,
    AKB_LOAD_COORD_Z_UP,
    AKB_LOAD_COORD_Z_UP_LH,
    AKB_LOAD_DEFER_NORMALS_AUTO,
    AKB_LOAD_DEFER_NORMALS_NO,
    AKB_LOAD_DEFER_NORMALS_YES,
    AKB_LOAD_OPT_BUILD_TRIANGLE_EDGES,
    AKB_LOAD_OPT_CONVERT_LINE_LOOP,
    AKB_LOAD_OPT_CONVERT_LINE_STRIP,
    AKB_LOAD_OPT_CONVERT_TRIANGLE_FAN,
    AKB_LOAD_OPT_CONVERT_TRIANGLE_STRIP,
    AKB_LOAD_OPT_COORD_CONVERSION,
    AKB_LOAD_OPT_COORD_SYSTEM,
    AKB_LOAD_OPT_COUNT,
    AKB_LOAD_OPT_DEFER_CUSTOM_NORMALS,
    AKB_LOAD_OPT_GENERATE_NORMALS,
    AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS,
    AKB_LOAD_OPT_GEOMETRY_KEYS,
    AKB_LOAD_OPT_IMPORT_LINES,
    AKB_LOAD_OPT_PRESERVE_EXTRAS,
    AKB_LOAD_OPT_PRESERVE_TANGENTS,
    AKB_LOAD_OPT_SCENE_INDEX,
    AKB_LOAD_OPT_TEXTURE_LOADING,
    AKB_LOAD_OPT_TRIANGULATE,
    AKB_LOAD_OPT_USE_MMAP,
    AKB_LOAD_TEXTURE_AUTO,
    AKB_LOAD_TEXTURE_DEFERRED,
    AKB_LOAD_TEXTURE_IMMEDIATE,
)

LoadOptions = tuple[int, ...]


def _coord_system_id(value: str) -> int:
    if value == "Y_UP":
        return AKB_LOAD_COORD_Y_UP
    if value == "X_UP":
        return AKB_LOAD_COORD_X_UP
    if value == "Z_UP_LH":
        return AKB_LOAD_COORD_Z_UP_LH
    if value == "Y_UP_LH":
        return AKB_LOAD_COORD_Y_UP_LH
    if value == "X_UP_LH":
        return AKB_LOAD_COORD_X_UP_LH
    return AKB_LOAD_COORD_Z_UP


def _coord_conversion_id(value: str) -> int:
    if value == "RAW":
        return AKB_LOAD_COORD_RAW
    if value == "ALL":
        return AKB_LOAD_COORD_ALL
    return AKB_LOAD_COORD_TRANSFORM


def _texture_mode_id(value: str) -> int:
    if value == "DEFERRED":
        return AKB_LOAD_TEXTURE_DEFERRED
    if value == "IMMEDIATE":
        return AKB_LOAD_TEXTURE_IMMEDIATE
    return AKB_LOAD_TEXTURE_AUTO


def _defer_normals_id(value: object = "AUTO") -> int:
    if isinstance(value, bool):
        return AKB_LOAD_DEFER_NORMALS_YES if value else AKB_LOAD_DEFER_NORMALS_NO
    text = str(value or "AUTO").upper()
    if text in {"0", "FALSE", "IMMEDIATE", "NO", "OFF"}:
        return AKB_LOAD_DEFER_NORMALS_NO
    if text in {"1", "TRUE", "DEFERRED", "YES", "ON"}:
        return AKB_LOAD_DEFER_NORMALS_YES
    return AKB_LOAD_DEFER_NORMALS_AUTO


def make_load_options(
    *,
    coordinate_conversion: str = "TRANSFORM",
    coordinate_system: str = "Z_UP",
    scene_index: int = -1,
    triangulate: bool = True,
    generate_normals: bool = False,
    convert_triangle_strip: bool = True,
    convert_triangle_fan: bool = True,
    import_lines: bool = True,
    convert_line_loop: bool = True,
    convert_line_strip: bool = True,
    use_mmap: bool = True,
    preserve_extras: bool = True,
    build_triangle_edges: bool = False,
    geometry_keys: bool = True,
    geometry_content_keys: bool = False,
    texture_loading: str = "IMMEDIATE",
    defer_custom_normals: object = "AUTO",
    preserve_tangents: bool = False,
) -> LoadOptions:
    return (
        _coord_system_id(coordinate_system),
        _coord_conversion_id(coordinate_conversion),
        int(scene_index),
        int(bool(triangulate)),
        int(bool(generate_normals)),
        int(bool(convert_triangle_strip)),
        int(bool(convert_triangle_fan)),
        int(bool(import_lines)),
        int(bool(convert_line_loop)),
        int(bool(convert_line_strip)),
        int(bool(use_mmap)),
        int(bool(preserve_extras)),
        int(bool(build_triangle_edges)),
        int(bool(geometry_keys)),
        int(bool(geometry_content_keys)),
        _texture_mode_id(texture_loading),
        _defer_normals_id(defer_custom_normals),
        int(bool(preserve_tangents)),
    )
