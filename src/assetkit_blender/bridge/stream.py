from __future__ import annotations

import gc
import time

from .data import CurveData, MeshPrimitiveData, SceneNodeData
from .meshes import meshes_from_raw as _native_meshes_from_raw
from .runtime import profile_enabled as _profile_enabled, profile_log as _profile_log


class NativeSceneStream:
    def __init__(
        self,
        module: object,
        owner: object,
        mesh_count: int,
        nodes: list[SceneNodeData],
        curves: list[CurveData] | None = None,
        doc_extra: object | None = None,
        scene_extra: object | None = None,
        images: list[dict] | None = None,
        required_node_indices: list[int] | None = None,
        scene_index: int = -1,
        scene_count: int = 0,
        scene_name: str = "",
        scene_names: list[str] | None = None,
        scene_bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
    ) -> None:
        self._module = module
        self._owner = owner
        self.mesh_count = mesh_count
        self.nodes = nodes
        self.curves = curves or []
        self.doc_extra = doc_extra
        self.scene_extra = scene_extra
        self.images = images or []
        self.required_node_indices = required_node_indices or []
        self.scene_index = scene_index
        self.scene_count = scene_count
        self.scene_name = scene_name
        self.scene_names = scene_names or []
        self.scene_bounds = scene_bounds

    def read_mesh_batch(self, start: int, count: int) -> list[MeshPrimitiveData]:
        profile = _profile_enabled()
        native_started_at = time.perf_counter() if profile else 0.0
        raw_meshes = self._module.read_mesh_batch(self._owner, start, count)
        native_ms = (time.perf_counter() - native_started_at) * 1000.0 if profile else 0.0
        gc_was_enabled = gc.isenabled()
        if gc_was_enabled:
            gc.disable()
        try:
            convert_started_at = time.perf_counter() if profile else 0.0
            meshes = _native_meshes_from_raw(raw_meshes)
            convert_ms = (time.perf_counter() - convert_started_at) * 1000.0 if profile else 0.0
        finally:
            if gc_was_enabled:
                gc.enable()
        if profile:
            _profile_log(
                "read_mesh_batch "
                f"start={start} count={count} returned={len(meshes)} "
                f"native={native_ms:.3f}ms "
                f"mesh_dataclass={convert_ms:.3f}ms"
            )
        return meshes
