from __future__ import annotations

LoadOptions = tuple[int, ...]

AKB_LOAD_OPT_COORD_SYSTEM = 0
AKB_LOAD_OPT_COORD_CONVERSION = 1
AKB_LOAD_OPT_SCENE_INDEX = 2
AKB_LOAD_OPT_TRIANGULATE = 3
AKB_LOAD_OPT_GENERATE_NORMALS = 4
AKB_LOAD_OPT_CONVERT_TRIANGLE_STRIP = 5
AKB_LOAD_OPT_CONVERT_TRIANGLE_FAN = 6
AKB_LOAD_OPT_IMPORT_LINES = 7
AKB_LOAD_OPT_CONVERT_LINE_LOOP = 8
AKB_LOAD_OPT_CONVERT_LINE_STRIP = 9
AKB_LOAD_OPT_USE_MMAP = 10
AKB_LOAD_OPT_PRESERVE_EXTRAS = 11
AKB_LOAD_OPT_BUILD_TRIANGLE_EDGES = 12
AKB_LOAD_OPT_GEOMETRY_KEYS = 13
AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS = 14
AKB_LOAD_OPT_TEXTURE_LOADING = 15
AKB_LOAD_OPT_DEFER_CUSTOM_NORMALS = 16
AKB_LOAD_OPT_COUNT = 17

AKB_LOAD_COORD_Z_UP = 0
AKB_LOAD_COORD_Y_UP = 1
AKB_LOAD_COORD_X_UP = 2
AKB_LOAD_COORD_Z_UP_LH = 3
AKB_LOAD_COORD_Y_UP_LH = 4
AKB_LOAD_COORD_X_UP_LH = 5

AKB_LOAD_COORD_RAW = 0
AKB_LOAD_COORD_TRANSFORM = 1
AKB_LOAD_COORD_ALL = 2

AKB_LOAD_TEXTURE_AUTO = 0
AKB_LOAD_TEXTURE_IMMEDIATE = 1
AKB_LOAD_TEXTURE_DEFERRED = 2

AKB_LOAD_DEFER_NORMALS_AUTO = 0
AKB_LOAD_DEFER_NORMALS_NO = 1
AKB_LOAD_DEFER_NORMALS_YES = 2


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
    )
