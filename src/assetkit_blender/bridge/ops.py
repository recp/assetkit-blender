from __future__ import annotations

from .runtime import native_module as _native_module


def native_animation_coords(channel: object, component: int, fps: float) -> memoryview | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        coords = _assetkit_blender.anim_coords(channel, int(component), float(fps))
    except Exception:
        return None
    if not coords:
        return None
    return memoryview(coords).cast("f")


def native_animation_quat_slerp_coords(channel: object, component: int, fps: float) -> memoryview | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        coords = _assetkit_blender.anim_quat_slerp_coords(channel, int(component), float(fps))
    except Exception:
        return None
    if not coords:
        return None
    return memoryview(coords).cast("f")


def native_animation_component_constant(
    channel: object,
    component: int,
    expected: float,
    epsilon: float = 1.0e-6,
) -> bool:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return False

    try:
        return bool(
            _assetkit_blender.anim_component_constant(
                channel,
                int(component),
                float(expected),
                float(epsilon),
            )
        )
    except Exception:
        return False


def native_offset_i32(buffer: object, offset: int) -> memoryview | None:
    if not buffer:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        shifted = _assetkit_blender.offset_i32(buffer, int(offset))
    except Exception:
        return None
    if not shifted:
        return None
    return memoryview(shifted).cast("i")


def native_buffers_equal(left: object, right: object) -> bool | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return bool(_assetkit_blender.buffers_equal(left, right))
    except Exception:
        return None


def native_buffer_sequences_equal(left: object, right: object) -> bool | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return bool(_assetkit_blender.buffer_sequences_equal(left, right))
    except Exception:
        return None


def native_write_offset_i32(dst: object, byte_offset: int, buffer: object, offset: int) -> int | None:
    if not dst or not buffer:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return int(_assetkit_blender.write_offset_i32(dst, int(byte_offset), buffer, int(offset)))
    except Exception:
        return None


def native_fill_i32(dst: object, byte_offset: int, value: int, count: int) -> int | None:
    if not dst or count <= 0:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return int(_assetkit_blender.fill_i32(dst, int(byte_offset), int(value), int(count)))
    except Exception:
        return None


def native_fill_triangle_loop_offsets_ptr(address: int, face_count: int) -> int | None:
    if address <= 0 or face_count <= 0:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return int(_assetkit_blender.fill_triangle_loop_offsets_ptr(int(address), int(face_count)))
    except Exception:
        return None


def native_fill_u8_ptr(address: int, value: int, count: int) -> int | None:
    if address <= 0 or count <= 0 or value < 0 or value > 255:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        return int(_assetkit_blender.fill_u8_ptr(int(address), int(value), int(count)))
    except Exception:
        return None


def native_skin_group_assignments(
    joints: object,
    weights: object,
    vertex_count: int,
    width: int,
    joint_count: int,
) -> list[tuple[int, float, memoryview]] | None:
    if not joints or not weights or vertex_count <= 0 or width <= 0 or joint_count <= 0:
        return None
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    try:
        packed = _assetkit_blender.skin_group_assignments(
            joints,
            weights,
            int(vertex_count),
            int(width),
            int(joint_count),
        )
    except Exception:
        return None
    if not packed:
        return None

    groups: list[tuple[int, float, memoryview]] = []
    for joint_index, weight, indices in packed:
        if not indices:
            continue
        groups.append((int(joint_index), float(weight), memoryview(indices).cast("i")))
    return groups or None
