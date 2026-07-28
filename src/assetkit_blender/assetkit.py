from __future__ import annotations

from .enums import *  # re-exported for existing add-on imports
from .bridge.abi import (
    AkAccessor,
    AkBuffer,
    AkDoc,
    AkGenericLib,
    AkGeometry,
    AkGeometryLib,
    AkIndexArray,
    AkInput,
    AkLibraries,
    AkMaterialPropertyRegistry,
    AkMesh,
    AkMeshPrimitive,
    AkObject,
    AkOneWayIterBase,
    AkScene,
    AkSceneCamera,
    AkSceneCameraList,
    AkSceneLight,
    AkSceneLightList,
)
from .bridge.curves import NativeCurveData
from .bridge.curves import curves_from_raw as _native_curves_from_raw
from .bridge.data import (
    AssetKitSceneData,
    CurveData,
    LoopFloatAttributeData,
    MeshPrimitiveData,
    MorphTargetData,
    SceneNodeData,
    TextureRefData,
)
from .bridge.legacy import AssetKit, resolve_library_path
from .bridge.loader import native_load_meshes, native_open_scene_stream
from .bridge.meshes import (
    NativeLoopFloatAttributeData,
    NativeSimpleMeshData,
)
from .bridge.meshes import (
    meshes_from_raw as _native_meshes_from_raw,
)
from .bridge.nodes import NativeSceneNodeData
from .bridge.nodes import nodes_from_raw as _native_nodes_from_raw
from .bridge.ops import (
    native_animation_component_constant,
    native_animation_coords,
    native_animation_quat_slerp_coords,
    native_buffer_sequences_equal,
    native_buffers_equal,
    native_fill_i32,
    native_fill_triangle_loop_offsets_ptr,
    native_fill_u8_ptr,
    native_offset_i32,
    native_skin_group_assignments,
    native_write_offset_i32,
)
from .bridge.runtime import (
    AssetKitError,
    probe_file_type,
    warmup_native_module,
)
from .bridge.runtime import (
    native_module as _native_module,
)
from .bridge.runtime import (
    profile_enabled as _profile_enabled,
)
from .bridge.runtime import (
    profile_log as _profile_log,
)
from .bridge.stream import NativeSceneStream
