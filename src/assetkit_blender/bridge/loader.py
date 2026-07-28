from __future__ import annotations

import gc
import os
import time

from .curves import curves_from_raw as _native_curves_from_raw
from .data import AssetKitSceneData
from .meshes import meshes_from_raw as _native_meshes_from_raw
from .nodes import nodes_from_raw as _native_nodes_from_raw
from .runtime import (
    AssetKitError,
    native_module as _native_module,
    profile_enabled as _profile_enabled,
    profile_log as _profile_log,
)
from .stream import NativeSceneStream


def _native_result_int(result: object, key: str, default: int) -> int:
    if not isinstance(result, dict):
        return default
    value = result.get(key)
    return int(value if value is not None else default)


def native_load_meshes(
    filepath: str | os.PathLike[str],
    options: tuple[int, ...] | None = None,
) -> AssetKitSceneData | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    profile          = _profile_enabled()
    total_started_at = time.perf_counter() if profile else 0.0

    try:
        native_started_at = time.perf_counter() if profile else 0.0
        result            = _assetkit_blender.load_meshes(os.fspath(filepath), options or None)
        native_ms         = (
            (time.perf_counter() - native_started_at) * 1000.0
            if profile
            else 0.0
        )
    except RuntimeError as exc:
        raise AssetKitError(str(exc)) from exc

    raw_meshes = result.get("meshes", []) if isinstance(result, dict) else result
    raw_curves = result.get("curves", []) if isinstance(result, dict) else []
    raw_nodes  = result.get("nodes", []) if isinstance(result, dict) else []

    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()

    try:
        meshes_started_at = time.perf_counter() if profile else 0.0
        meshes            = _native_meshes_from_raw(raw_meshes)
        meshes_ms         = (
            (time.perf_counter() - meshes_started_at) * 1000.0
            if profile
            else 0.0
        )

        nodes_started_at = time.perf_counter() if profile else 0.0
        nodes            = _native_nodes_from_raw(raw_nodes)
        nodes_ms         = (
            (time.perf_counter() - nodes_started_at) * 1000.0
            if profile
            else 0.0
        )

        curves_started_at = time.perf_counter() if profile else 0.0
        curves            = _native_curves_from_raw(raw_curves)
        curves_ms         = (
            (time.perf_counter() - curves_started_at) * 1000.0
            if profile
            else 0.0
        )
    finally:
        if gc_was_enabled:
            gc.enable()

    data = AssetKitSceneData(
        meshes       = meshes,
        nodes        = nodes,
        curves       = curves,
        doc_extra    = result.get("doc_extra") if isinstance(result, dict) else None,
        scene_extra  = result.get("scene_extra") if isinstance(result, dict) else None,
        images       = list(result.get("images") or []) if isinstance(result, dict) else None,
        scene_index  = _native_result_int(result, "scene_index", -1),
        scene_count  = _native_result_int(result, "scene_count", 0),
        scene_name   = str(result.get("scene_name") or "") if isinstance(result, dict) else "",
        scene_names  = list(result.get("scene_names") or []) if isinstance(result, dict) else None,
        scene_bounds = (
            result.get("scene_bounds")
            if isinstance(result, dict)
            else None
        ),
    )

    if profile:
        _profile_log(
            "load_meshes "
            f"native={native_ms:.3f}ms "
            f"mesh_dataclass={meshes_ms:.3f}ms "
            f"node_dataclass={nodes_ms:.3f}ms "
            f"curve_dataclass={curves_ms:.3f}ms "
            f"meshes={len(meshes)} curves={len(curves)} nodes={len(nodes)} "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return data


def native_open_scene_stream(
    filepath: str | os.PathLike[str],
    options: tuple[int, ...] | None = None,
) -> NativeSceneStream | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    profile          = _profile_enabled()
    total_started_at = time.perf_counter() if profile else 0.0

    try:
        native_started_at = time.perf_counter() if profile else 0.0
        result            = _assetkit_blender.open_scene(os.fspath(filepath), options or None)
        native_ms         = (
            (time.perf_counter() - native_started_at) * 1000.0
            if profile
            else 0.0
        )
    except RuntimeError as exc:
        raise AssetKitError(str(exc)) from exc

    nodes_started_at = time.perf_counter() if profile else 0.0
    nodes            = _native_nodes_from_raw(result.get("nodes", []))
    nodes_ms         = (
        (time.perf_counter() - nodes_started_at) * 1000.0
        if profile
        else 0.0
    )

    curves_started_at = time.perf_counter() if profile else 0.0
    curves            = _native_curves_from_raw(result.get("curves", []))
    curves_ms         = (
        (time.perf_counter() - curves_started_at) * 1000.0
        if profile
        else 0.0
    )

    stream = NativeSceneStream(
        module                = _assetkit_blender,
        owner                 = result.get("_owner"),
        mesh_count            = int(result.get("mesh_count") or 0),
        nodes                 = nodes,
        curves                = curves,
        doc_extra             = result.get("doc_extra"),
        scene_extra           = result.get("scene_extra"),
        images                = list(result.get("images") or []),
        required_node_indices = list(result.get("required_node_indices") or []),
        scene_index           = _native_result_int(result, "scene_index", -1),
        scene_count           = _native_result_int(result, "scene_count", 0),
        scene_name            = str(result.get("scene_name") or ""),
        scene_names           = list(result.get("scene_names") or []),
        scene_bounds          = result.get("scene_bounds"),
    )

    if profile:
        _profile_log(
            "open_scene "
            f"native={native_ms:.3f}ms "
            f"node_dataclass={nodes_ms:.3f}ms "
            f"curve_dataclass={curves_ms:.3f}ms "
            f"meshes={stream.mesh_count} curves={len(curves)} nodes={len(nodes)} "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return stream
