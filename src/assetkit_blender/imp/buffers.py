from __future__ import annotations

import bpy
from mathutils import Matrix

_CHANNEL_KEYS = (
    "target",
    "target_offset",
    "clip_index",
    "clip_name",
    "value_width",
    "count",
    "interpolation",
    "is_partial",
    "pose_ready",
    "times_f32",
    "values_f32",
    "in_tangents_f32",
    "out_tangents_f32",
)
(
    _TARGET,
    _TARGET_OFFSET,
    _CLIP_INDEX,
    _CLIP_NAME,
    _VALUE_WIDTH,
    _COUNT,
    _INTERPOLATION,
    _IS_PARTIAL,
    _POSE_READY,
    _TIMES_F32,
    _VALUES_F32,
    _IN_TANGENTS_F32,
    _OUT_TANGENTS_F32,
) = range(len(_CHANNEL_KEYS))


def apply_matrix_buffer(
    obj: bpy.types.Object,
    buffer: object,
) -> None:
    matrix = matrix_from_buffer(buffer)
    if matrix is not None:
        obj.matrix_local = matrix


def matrix_from_buffer(buffer: object) -> Matrix | None:
    if not buffer:
        return None

    values = buffer_view(buffer, "f")
    if values is None or len(values) != 16:
        return None

    return matrix_from_values(values, 0)


def matrix_from_values(values: memoryview, offset: int) -> Matrix:
    return Matrix(
        (
            (
                values[offset],
                values[offset + 4],
                values[offset + 8],
                values[offset + 12],
            ),
            (
                values[offset + 1],
                values[offset + 5],
                values[offset + 9],
                values[offset + 13],
            ),
            (
                values[offset + 2],
                values[offset + 6],
                values[offset + 10],
                values[offset + 14],
            ),
            (
                values[offset + 3],
                values[offset + 7],
                values[offset + 11],
                values[offset + 15],
            ),
        )
    )


def buffer_view(buffer: object, fmt: str) -> memoryview | None:
    if not buffer:
        return None

    view = buffer if isinstance(buffer, memoryview) else memoryview(buffer)
    if len(view) == 0:
        return None
    if view.format == fmt and view.ndim == 1:
        return view
    return view.cast(fmt)


def copy_buffer_bytes(
    dst: bytearray,
    offset: int,
    src: object,
    fmt: str,
) -> int:
    view = buffer_view(src, fmt)
    if view is None:
        return 0
    raw             = view.cast("B")
    end             = offset + len(raw)
    dst[offset:end] = raw
    return len(raw)


def channel_get(
    channel: object,
    index: int,
    default: object = None,
) -> object:
    if isinstance(channel, tuple):
        return channel[index] if index < len(channel) else default
    if isinstance(channel, dict):
        return channel.get(_CHANNEL_KEYS[index], default)
    if isinstance(channel, list):
        return channel[index] if index < len(channel) else default
    return default


def channel_int(channel: object, index: int) -> int:
    value = channel_get(channel, index, 0)
    return int(value or 0)


def channel_bool(channel: object, index: int) -> bool:
    return bool(channel_get(channel, index, False))


def channel_buffer(channel: object, index: int) -> object:
    return channel_get(channel, index, b"") or b""


def channel_target(channel: object) -> int:
    return channel_int(channel, _TARGET)


def channel_target_offset(channel: object) -> int:
    return channel_int(channel, _TARGET_OFFSET)


def channel_clip_index(channel: object) -> int:
    return channel_int(channel, _CLIP_INDEX)


def channel_clip_name(channel: object) -> str:
    return str(channel_get(channel, _CLIP_NAME, "") or "")


def channel_value_width(channel: object) -> int:
    return channel_int(channel, _VALUE_WIDTH)


def channel_count(channel: object) -> int:
    return channel_int(channel, _COUNT)


def channel_interpolation(channel: object) -> int:
    return channel_int(channel, _INTERPOLATION)


def channel_is_partial(channel: object) -> bool:
    return channel_bool(channel, _IS_PARTIAL)


def channel_pose_ready(channel: object) -> bool:
    return channel_bool(channel, _POSE_READY)


def channel_times(channel: object) -> object:
    return channel_buffer(channel, _TIMES_F32)


def channel_values(channel: object) -> object:
    return channel_buffer(channel, _VALUES_F32)


def channel_in_tangents(channel: object) -> object:
    return channel_buffer(channel, _IN_TANGENTS_F32)


def channel_out_tangents(channel: object) -> object:
    return channel_buffer(channel, _OUT_TANGENTS_F32)
