from __future__ import annotations

import importlib
import os
from pathlib import Path

from ..enums import (
    AK_FILE_TYPE_3MF,
    AK_FILE_TYPE_AUTO,
    AK_FILE_TYPE_COLLADA,
    AK_FILE_TYPE_GLB,
    AK_FILE_TYPE_GLTF,
    AK_FILE_TYPE_PLY,
    AK_FILE_TYPE_STL,
    AK_FILE_TYPE_WAVEFRONT,
)

_NATIVE_MODULE        = None
_NATIVE_MODULE_FAILED = False
_PROFILE_ENABLED      = None


class AssetKitError(RuntimeError):
    pass


def native_module():
    global _NATIVE_MODULE, _NATIVE_MODULE_FAILED

    if _NATIVE_MODULE is not None:
        return _NATIVE_MODULE
    if _NATIVE_MODULE_FAILED:
        return None

    try:
        from .. import _assetkit_blender
    except ImportError:
        try:
            _assetkit_blender = importlib.import_module("_assetkit_blender")
        except ImportError:
            _NATIVE_MODULE_FAILED = True
            return None

    _NATIVE_MODULE = _assetkit_blender
    return _NATIVE_MODULE


def warmup_native_module() -> None:
    native_module()


def probe_file_type(filepath: str | os.PathLike[str]) -> int:
    native = native_module()
    if native is not None and hasattr(native, "probe_file_type"):
        try:
            return int(native.probe_file_type(os.fspath(filepath)))
        except RuntimeError:
            pass

    suffix = Path(filepath).suffix.lower()
    return {
        ".dae":  AK_FILE_TYPE_COLLADA,
        ".zae":  AK_FILE_TYPE_COLLADA,
        ".kmz":  AK_FILE_TYPE_COLLADA,
        ".gltf": AK_FILE_TYPE_GLTF,
        ".glb":  AK_FILE_TYPE_GLB,
        ".obj":  AK_FILE_TYPE_WAVEFRONT,
        ".stl":  AK_FILE_TYPE_STL,
        ".ply":  AK_FILE_TYPE_PLY,
        ".3mf":  AK_FILE_TYPE_3MF,
    }.get(suffix, AK_FILE_TYPE_AUTO)


def profile_enabled() -> bool:
    global _PROFILE_ENABLED

    if _PROFILE_ENABLED is not None:
        return _PROFILE_ENABLED

    value = os.environ.get("ASSETKIT_BLENDER_PROFILE")
    if value is None or value == "":
        _PROFILE_ENABLED = False
    else:
        _PROFILE_ENABLED = value.lower() not in {"0", "false", "off", "no"}
    return _PROFILE_ENABLED


def profile_log(message: str) -> None:
    if profile_enabled():
        print(f"[AssetKit python] {message}", flush=True)
