from __future__ import annotations

import math
import os
import time
from collections import deque

import bpy

from ..assetkit import TextureRefData, _profile_log
from . import profile as _profile_state
from .buffers import buffer_view as _buffer_view
from .metadata import _set_assetkit_json_prop, _set_prop_if_nondefault

ACTIVE_LOAD_MODE = "IMMEDIATE"
ACTIVE_NODE_CACHE: dict[object, object] | None = None
ACTIVE_SEPARATE_COLOR_CACHE: dict[int, object] | None = None
ACTIVE_VALIDATED_IMAGE_KEYS: set[tuple[str, str]] | None = None

_TEXTURE_IMAGE_CACHE: dict[tuple[str, str], object] = {}
_TEXTURE_PATH_CACHE: dict[str, str] = {}
_DEFERRED_TEXTURE_WAITERS: dict[tuple[str, str], list[object]] = {}
_DEFERRED_TEXTURE_KEYS: deque[tuple[str, str]] = deque()
_DEFERRED_TEXTURE_TIMER_ACTIVE = False
_DEFERRED_TEXTURE_TIME_BUDGET = 0.006
_TEXTURE_WRAP_DEFAULT = 1
_TEXTURE_FILTER_DEFAULT = 0
_TEXTURE_EXTENSION_DEFAULT = "REPEAT"
_TEXTURE_INTERPOLATION_DEFAULT = "Linear"


def has_deferred_work() -> bool:
    return bool(_DEFERRED_TEXTURE_KEYS)


def _image_texture_node(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    tex_info: TextureRefData | None = None,
):
    stats = _profile_state.stats
    profile_started_at = time.perf_counter() if stats is not None else 0.0
    if stats is not None:
        stats["texture_node_calls"] = int(stats.get("texture_node_calls", 0) or 0) + 1
    colorspace = _texture_color_space(tex_info, colorspace)
    cache_key = _texture_node_cache_key(path, colorspace, tex_info)
    if ACTIVE_NODE_CACHE is not None and cache_key is not None:
        tex = ACTIVE_NODE_CACHE.get(cache_key)
        if _node_is_alive(mat, tex):
            if stats is not None:
                stats["texture_node_cache_hits"] = int(stats.get("texture_node_cache_hits", 0) or 0) + 1
            _append_texture_node_role(tex, tex_info)
            return tex

    defer_image = _should_defer_texture_image(path)
    image = _cached_texture_image(path, colorspace) if defer_image else _load_texture_image(path, colorspace)
    if not image and not defer_image:
        return None

    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    if image:
        tex.image = image
    elif defer_image:
        _queue_deferred_texture_image(tex, path, colorspace)
    if tex_info and tex_info.role:
        tex.label = f"AssetKit {tex_info.role}"
        tex["assetkit_texture_role"] = tex_info.role
        if tex_info.slot:
            tex["assetkit_texture_slot"] = tex_info.slot
        if colorspace:
            tex["assetkit_texture_colorspace"] = colorspace
        if tex_info.image_name:
            tex["assetkit_texture_image_name"] = tex_info.image_name
        if tex_info.sampler_name:
            tex["assetkit_texture_sampler_name"] = tex_info.sampler_name
        if tex_info.channels:
            tex["assetkit_texture_channels"] = tex_info.channels
        _set_texture_sampler_props(tex, tex_info)
        _set_assetkit_json_prop(tex, "assetkit_texture_extra_json", tex_info.texture_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_ref_extra_json", tex_info.texref_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_image_extra_json", tex_info.image_extra)
        _set_assetkit_json_prop(tex, "assetkit_texture_sampler_extra_json", tex_info.sampler_extra)
    _configure_texture_node(mat, tex, tex_info)
    if ACTIVE_NODE_CACHE is not None and cache_key is not None:
        ACTIVE_NODE_CACHE[cache_key] = tex
    if stats is not None:
        stats["texture_node_create_ms"] = (
            float(stats.get("texture_node_create_ms", 0.0) or 0.0)
            + (time.perf_counter() - profile_started_at) * 1000.0
        )
    return tex


def _texture_node_cache_key(path: str, colorspace: str, tex_info: TextureRefData | None) -> object | None:
    if tex_info and (tex_info.texture_extra or tex_info.texref_extra or tex_info.image_extra or tex_info.sampler_extra):
        return None

    try:
        source_path = _texture_abs_path(path)
    except Exception:
        return None

    if tex_info is None:
        return (source_path, colorspace, 0, 1, 1, 1, 0, 0, 0, False)

    transform = None
    if tex_info.has_transform:
        transform = (
            float(tex_info.transform_offset[0]),
            float(tex_info.transform_offset[1]),
            float(tex_info.transform_scale[0]),
            float(tex_info.transform_scale[1]),
            float(tex_info.transform_rotation),
        )

    return (
        source_path,
        colorspace,
        _texture_uv_slot(tex_info),
        int(tex_info.wrap_s),
        int(tex_info.wrap_t),
        int(tex_info.wrap_p),
        int(tex_info.min_filter),
        int(tex_info.mag_filter),
        int(tex_info.mip_filter),
        transform,
    )


def _append_texture_node_role(tex, tex_info: TextureRefData | None) -> None:
    if not tex_info or not tex_info.role:
        return
    try:
        roles = str(tex.get("assetkit_texture_roles") or tex.get("assetkit_texture_role") or "")
        if tex_info.role not in {role for role in roles.split(",") if role}:
            tex["assetkit_texture_roles"] = f"{roles},{tex_info.role}" if roles else tex_info.role
    except Exception:
        pass


def _node_is_alive(mat: bpy.types.Material, node) -> bool:
    if node is None:
        return False
    try:
        return mat.node_tree.nodes.get(node.name) == node
    except ReferenceError:
        return False
    except Exception:
        return False


def _socket_cache_key(socket) -> int:
    try:
        return int(socket.as_pointer())
    except Exception:
        return 0


def _should_defer_texture_image(path: str) -> bool:
    return ACTIVE_LOAD_MODE == "DEFERRED" and bool(path)


def _queue_deferred_texture_image(tex, path: str, colorspace: str, store_props: bool = True) -> None:
    global _DEFERRED_TEXTURE_TIMER_ACTIVE
    key = _texture_image_cache_key(path, colorspace)
    image = _cached_texture_image_by_key(key)
    if image:
        _assign_texture_image(tex, image)
        return

    waiters = _DEFERRED_TEXTURE_WAITERS.get(key)
    if waiters is None:
        _DEFERRED_TEXTURE_WAITERS[key] = [tex]
        _DEFERRED_TEXTURE_KEYS.append(key)
    else:
        waiters.append(tex)

    if store_props:
        try:
            tex["assetkit_texture_pending_path"] = key[0]
            tex["assetkit_texture_pending_colorspace"] = key[1]
        except Exception:
            pass

    if not _DEFERRED_TEXTURE_TIMER_ACTIVE:
        _DEFERRED_TEXTURE_TIMER_ACTIVE = True
        bpy.app.timers.register(_deferred_texture_timer, first_interval=0.001)


def _deferred_texture_timer() -> float | None:
    global _DEFERRED_TEXTURE_TIMER_ACTIVE
    started_at = time.perf_counter()
    while _DEFERRED_TEXTURE_KEYS:
        key = _DEFERRED_TEXTURE_KEYS.popleft()
        waiters = _DEFERRED_TEXTURE_WAITERS.pop(key, [])
        live_waiters = [node for node in waiters if _node_ref_alive(node)]
        if live_waiters:
            image = _load_texture_image_immediate(key[0], key[1])
            if image:
                for node in live_waiters:
                    _assign_texture_image(node, image)
        if time.perf_counter() - started_at >= _DEFERRED_TEXTURE_TIME_BUDGET:
            return 0.001

    _DEFERRED_TEXTURE_TIMER_ACTIVE = False
    return None


def _assign_texture_image(tex, image) -> None:
    if not _node_ref_alive(tex):
        return
    try:
        tex.image = image
        if "assetkit_texture_pending_path" in tex:
            del tex["assetkit_texture_pending_path"]
        if "assetkit_texture_pending_colorspace" in tex:
            del tex["assetkit_texture_pending_colorspace"]
    except Exception:
        pass


def _node_ref_alive(node) -> bool:
    if node is None:
        return False
    try:
        tree = node.id_data
        return tree is not None and tree.nodes.get(node.name) == node
    except ReferenceError:
        return False
    except Exception:
        return False


def _texture_color_space(tex_info: TextureRefData | None, fallback: str) -> str:
    if tex_info and tex_info.color_space:
        return tex_info.color_space
    return fallback


def _load_texture_image(path: str, colorspace: str):
    return _load_texture_image_immediate(path, colorspace)


def _load_texture_image_immediate(path: str, colorspace: str):
    source_path = _texture_abs_path(path)
    stats = _profile_state.stats
    started_at = time.perf_counter() if stats is not None else 0.0
    image = _find_texture_image(source_path, colorspace)
    if stats is not None:
        stats["texture_image_find_ms"] = (
            float(stats.get("texture_image_find_ms", 0.0) or 0.0)
            + (time.perf_counter() - started_at) * 1000.0
        )
    if image:
        if stats is not None:
            stats["texture_image_cache_hits"] = int(stats.get("texture_image_cache_hits", 0) or 0) + 1
        return image

    if _is_ktx2_path(path):
        image = _decode_ktx2_image(source_path, colorspace)
        if image:
            return image

    if not _is_ktx2_path(path):
        ref_started_at = time.perf_counter() if stats is not None else 0.0
        image = _create_texture_image_file_reference(source_path, colorspace)
        if stats is not None:
            stats["texture_image_ref_ms"] = (
                float(stats.get("texture_image_ref_ms", 0.0) or 0.0)
                + (time.perf_counter() - ref_started_at) * 1000.0
            )
        if image:
            if stats is not None:
                stats["texture_image_refs"] = int(stats.get("texture_image_refs", 0) or 0) + 1
            return image

    image = None
    load_started_at = time.perf_counter() if stats is not None else 0.0
    try:
        image = bpy.data.images.load(source_path, check_existing=False)
    except RuntimeError:
        image = None
    if stats is not None:
        stats["texture_image_load_ms"] = (
            float(stats.get("texture_image_load_ms", 0.0) or 0.0)
            + (time.perf_counter() - load_started_at) * 1000.0
        )

    if image:
        register_started_at = time.perf_counter() if stats is not None else 0.0
        _register_texture_image(image, source_path, colorspace)
        if stats is not None:
            stats["texture_image_register_ms"] = (
                float(stats.get("texture_image_register_ms", 0.0) or 0.0)
                + (time.perf_counter() - register_started_at) * 1000.0
            )
            stats["texture_image_loads"] = int(stats.get("texture_image_loads", 0) or 0) + 1
        return image

    if image and _is_ktx2_path(path):
        try:
            bpy.data.images.remove(image)
        except Exception:
            pass

    if _is_ktx2_path(path):
        image = _decode_ktx2_image(source_path, colorspace)
        if image:
            return image

    return None


def _create_texture_image_file_reference(source_path: str, colorspace: str):
    if not os.path.isfile(source_path):
        return None

    image = None
    try:
        image = bpy.data.images.new(os.path.basename(source_path) or "Texture", width=1, height=1, alpha=True)
        image.source = "FILE"
        image.filepath_raw = source_path
        _register_texture_image(image, source_path, colorspace)
        image["assetkit_lazy_file_reference"] = True
        return image
    except Exception:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass
        return None


def _find_texture_image(path: str, colorspace: str):
    key = _texture_image_cache_key(path, colorspace)
    cached = _cached_texture_image_by_key(key)
    if cached is not None:
        return cached

    source_path = key[0]
    for image in bpy.data.images:
        image_path = image.get("assetkit_source_path") or image.filepath
        if not image_path:
            continue
        try:
            image_path = bpy.path.abspath(image_path)
        except Exception:
            pass
        if os.path.abspath(os.fspath(image_path)) != source_path:
            continue
        if _image_colorspace(image) != colorspace:
            continue
        _register_texture_image(image, source_path, colorspace)
        return image
    return None


def _cached_texture_image(path: str, colorspace: str):
    return _cached_texture_image_by_key(_texture_image_cache_key(path, colorspace))


def _cached_texture_image_by_key(key: tuple[str, str]):
    cached = _TEXTURE_IMAGE_CACHE.get(key)
    if cached is not None:
        if ACTIVE_VALIDATED_IMAGE_KEYS is not None and key in ACTIVE_VALIDATED_IMAGE_KEYS:
            return cached
        try:
            if bpy.data.images.get(cached.name) == cached:
                if _image_colorspace(cached) == key[1]:
                    _set_image_alpha_mode(cached, key[0])
                    if ACTIVE_VALIDATED_IMAGE_KEYS is not None:
                        ACTIVE_VALIDATED_IMAGE_KEYS.add(key)
                    return cached
        except ReferenceError:
            pass
        _TEXTURE_IMAGE_CACHE.pop(key, None)
    return None


def _register_texture_image(image, path: str, colorspace: str) -> None:
    source_path, normalized_colorspace = _texture_image_cache_key(path, colorspace)
    image["assetkit_source_path"] = source_path
    image["assetkit_colorspace"] = colorspace
    _set_image_colorspace(image, colorspace)
    _set_image_alpha_mode(image, source_path)
    _TEXTURE_IMAGE_CACHE[(source_path, normalized_colorspace)] = image
    if ACTIVE_VALIDATED_IMAGE_KEYS is not None:
        ACTIVE_VALIDATED_IMAGE_KEYS.add((source_path, normalized_colorspace))


def _texture_image_cache_key(path: str, colorspace: str) -> tuple[str, str]:
    return _texture_abs_path(path), str(colorspace or "")


def _texture_abs_path(path: str) -> str:
    source = os.fspath(path)
    cached = _TEXTURE_PATH_CACHE.get(source)
    if cached is not None:
        return cached
    cached = os.path.abspath(source)
    _TEXTURE_PATH_CACHE[source] = cached
    return cached


def _image_colorspace(image) -> str:
    stored = image.get("assetkit_colorspace")
    if stored:
        return str(stored)
    try:
        return image.colorspace_settings.name
    except Exception:
        return ""


def _image_has_size(image) -> bool:
    try:
        return int(image.size[0]) > 0 and int(image.size[1]) > 0
    except Exception:
        return False


def _set_image_colorspace(image, colorspace: str) -> None:
    try:
        image.colorspace_settings.name = colorspace
    except TypeError:
        pass


def _set_image_alpha_mode(image, path: str) -> None:
    if not os.fspath(path).lower().endswith(".dds"):
        return
    try:
        image.alpha_mode = "CHANNEL_PACKED"
    except (TypeError, ValueError):
        pass


def _is_ktx2_path(path: str) -> bool:
    return os.fspath(path).lower().endswith(".ktx2")


def _decode_ktx2_image(path: str, colorspace: str):
    source_path = _texture_abs_path(path)
    image = _find_texture_image(source_path, colorspace)
    if image:
        return image

    try:
        from .. import _assetkit_blender
    except Exception:
        return None

    try:
        decoded = _assetkit_blender.decode_ktx2(source_path)
    except Exception as exc:
        if _profile_state.stats is not None:
            _profile_log(f"KTX2 decode skipped path={path!r} error={exc}")
        return None

    width = int(decoded.get("width") or 0)
    height = int(decoded.get("height") or 0)
    pixels = _buffer_view(decoded.get("pixels_f32") or b"", "f")
    if width <= 0 or height <= 0 or pixels is None or len(pixels) != width * height * 4:
        return None

    name = os.path.basename(source_path)
    image = bpy.data.images.new(name, width=width, height=height, alpha=True, float_buffer=False)
    image.pixels.foreach_set(pixels)
    image.filepath = source_path
    image["assetkit_decoded_texture"] = True
    _register_texture_image(image, source_path, colorspace)
    image.update()
    return image


def _image_texture_channel(
    mat: bpy.types.Material,
    path: str,
    colorspace: str,
    channel: str,
    tex_info: TextureRefData | None = None,
):
    tex = _image_texture_node(mat, path, colorspace, tex_info)
    if not tex:
        return None
    channel = _texture_channel_name(tex_info, channel)
    if channel == "Alpha":
        return tex.outputs.get("Alpha") or tex.outputs.get("Color")
    if channel == "Color":
        return tex.outputs.get("Color")

    return _separate_color_channel(mat, tex.outputs.get("Color"), channel)


def _texture_channel_name(tex_info: TextureRefData | None, fallback: str) -> str:
    letters = _texture_channel_letters(tex_info)
    if len(letters) != 1:
        return fallback
    return {
        "R": "Red",
        "G": "Green",
        "B": "Blue",
        "A": "Alpha",
    }.get(letters[0], fallback)


def _texture_channel_letters(tex_info: TextureRefData | None) -> tuple[str, ...]:
    if not tex_info or not tex_info.channels:
        return ()
    seen = []
    for letter in str(tex_info.channels).upper():
        if letter in {"R", "G", "B", "A"} and letter not in seen:
            seen.append(letter)
    return tuple(seen)


def _separate_color_channel(
    mat: bpy.types.Material,
    color_output,
    channel: str,
):
    if color_output is None:
        return None

    separate = _separate_color_node(mat, color_output)
    if separate:
        return separate.outputs.get(channel)
    return color_output


def _separate_color_node(mat: bpy.types.Material, color_output):
    global ACTIVE_SEPARATE_COLOR_CACHE
    cache_key = _socket_cache_key(color_output)
    if ACTIVE_SEPARATE_COLOR_CACHE is not None and cache_key:
        separate = ACTIVE_SEPARATE_COLOR_CACHE.get(cache_key)
        if _node_is_alive(mat, separate):
            return separate

    try:
        separate = mat.node_tree.nodes.new("ShaderNodeSeparateColor")
        mat.node_tree.links.new(color_output, separate.inputs["Color"])
    except Exception:
        return None

    if ACTIVE_SEPARATE_COLOR_CACHE is not None and cache_key:
        ACTIVE_SEPARATE_COLOR_CACHE[cache_key] = separate
    return separate


def _configure_texture_node(mat: bpy.types.Material, tex, tex_info: TextureRefData | None) -> None:
    if not tex_info:
        return

    tex.extension = _texture_extension(tex_info)
    tex.interpolation = _texture_interpolation(tex_info)

    uv_slot = _texture_uv_slot(tex_info)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = _uv_layer_name(uv_slot)
    vector_output = uv.outputs.get("UV")

    if tex_info.has_transform:
        offset, rotation, scale = _texture_transform_gltf_to_blender(tex_info)
        mapping = nodes.new("ShaderNodeMapping")
        mapping.label = f"AssetKit {tex_info.role} Transform"
        mapping["assetkit_texture_role"] = tex_info.role
        if hasattr(mapping, "vector_type"):
            mapping.vector_type = "POINT"
        mapping.inputs["Location"].default_value[0] = offset[0]
        mapping.inputs["Location"].default_value[1] = offset[1]
        mapping.inputs["Rotation"].default_value[2] = rotation
        mapping.inputs["Scale"].default_value[0] = scale[0]
        mapping.inputs["Scale"].default_value[1] = scale[1]
        if vector_output:
            links.new(vector_output, mapping.inputs["Vector"])
        vector_output = mapping.outputs.get("Vector")

    if vector_output:
        links.new(vector_output, tex.inputs["Vector"])


def _texture_uv_slot(tex_info: TextureRefData) -> int:
    if tex_info.has_transform and tex_info.transform_slot >= 0:
        return tex_info.transform_slot
    return tex_info.slot


def _texture_transform_gltf_to_blender(
    tex_info: TextureRefData,
) -> tuple[tuple[float, float], float, tuple[float, float]]:
    return _texture_transform_values_gltf_to_blender(
        tex_info.transform_offset,
        float(tex_info.transform_rotation),
        tex_info.transform_scale,
    )


def _texture_transform_values_gltf_to_blender(
    offset: tuple[float, float],
    rotation: float,
    scale: tuple[float, float],
) -> tuple[tuple[float, float], float, tuple[float, float]]:
    return (
        (
            float(offset[0]) + float(scale[1]) * math.sin(rotation),
            1.0 - float(offset[1]) - float(scale[1]) * math.cos(rotation),
        ),
        rotation,
        (float(scale[0]), float(scale[1])),
    )


def _uv_layer_name(slot: int) -> str:
    return "UVMap" if slot <= 0 else f"UVMap.{slot:03d}"


def _texture_extension(tex_info: TextureRefData | None) -> str:
    if tex_info is None:
        return _TEXTURE_EXTENSION_DEFAULT
    wrap_s = tex_info.wrap_s
    wrap_t = tex_info.wrap_t
    if wrap_s != wrap_t:
        return "REPEAT"
    if wrap_s == 2 or wrap_s == 5:
        return "MIRROR"
    if wrap_s == 3:
        return "EXTEND"
    if wrap_s == 4:
        return "CLIP"
    return "REPEAT"


def _texture_interpolation(tex_info: TextureRefData | None) -> str:
    if tex_info is None:
        return _TEXTURE_INTERPOLATION_DEFAULT
    if tex_info.mag_filter == 1 or tex_info.min_filter in {1, 4, 5}:
        return "Closest"
    return "Linear"


def _set_texture_sampler_props(tex, tex_info: TextureRefData) -> None:
    extension = _texture_extension(tex_info)
    interpolation = _texture_interpolation(tex_info)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_s", int(tex_info.wrap_s), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_t", int(tex_info.wrap_t), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_wrap_p", int(tex_info.wrap_p), _TEXTURE_WRAP_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_min_filter", int(tex_info.min_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_mag_filter", int(tex_info.mag_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_mip_filter", int(tex_info.mip_filter), _TEXTURE_FILTER_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_extension", extension, _TEXTURE_EXTENSION_DEFAULT)
    _set_prop_if_nondefault(tex, "assetkit_texture_interpolation", interpolation, _TEXTURE_INTERPOLATION_DEFAULT)
