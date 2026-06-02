from __future__ import annotations

import ctypes
import ctypes.util
import gc
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

AK_OK = 0
AK_FILE_TYPE_AUTO = 0
AK_FILE_TYPE_WAVEFRONT = 3
AK_FILE_TYPE_STL = 4
AK_GEOMETRY_MESH = 1
AK_PRIMITIVE_LINES = 1
AK_PRIMITIVE_POLYGONS = 2
AK_PRIMITIVE_TRIANGLES = 3
AK_PRIMITIVE_POINTS = 4
AK_INPUT_NORMAL = 13
AK_INPUT_POSITION = 16
AK_INPUT_TEXCOORD = 19
AK_INPUT_UV = 21

AKT_FLOAT = 10
AKT_DOUBLE = 33
AKT_INT = 6
AKT_UINT = 28
AKT_BYTE = 29
AKT_UBYTE = 30
AKT_SHORT = 31
AKT_USHORT = 32
AKT_INT64 = 34
AKT_UINT64 = 35

_PROFILE_ENABLED: bool | None = None
_EMPTY_SEQUENCE: tuple = ()


class AkObject(ctypes.Structure):
    pass


AkObject._fields_ = [
    ("next", ctypes.POINTER(AkObject)),
    ("size", ctypes.c_size_t),
    ("type", ctypes.c_int32),
    ("pData", ctypes.c_void_p),
]


class AkOneWayIterBase(ctypes.Structure):
    _fields_ = [("next", ctypes.c_void_p)]


class AkIndexArray(ctypes.Structure):
    _fields_ = [
        ("count", ctypes.c_size_t),
        ("max", ctypes.c_uint32),
        ("componentType", ctypes.c_int32),
        ("reserved", ctypes.c_uint32),
    ]


class AkBuffer(ctypes.Structure):
    pass


AkBuffer._fields_ = [
    ("next", ctypes.POINTER(AkBuffer)),
    ("name", ctypes.c_char_p),
    ("data", ctypes.c_void_p),
    ("length", ctypes.c_size_t),
]


class AkAccessor(ctypes.Structure):
    pass


AkAccessor._fields_ = [
    ("next", ctypes.POINTER(AkAccessor)),
    ("buffer", ctypes.POINTER(AkBuffer)),
    ("name", ctypes.c_char_p),
    ("min", ctypes.c_void_p),
    ("max", ctypes.c_void_p),
    ("byteOffset", ctypes.c_size_t),
    ("byteStride", ctypes.c_size_t),
    ("byteLength", ctypes.c_size_t),
    ("count", ctypes.c_uint32),
    ("bytesPerComponent", ctypes.c_uint32),
    ("componentSize", ctypes.c_int32),
    ("componentType", ctypes.c_int32),
    ("componentCount", ctypes.c_uint32),
    ("fillByteSize", ctypes.c_size_t),
    ("gpuTarget", ctypes.c_int32),
    ("normalized", ctypes.c_bool),
    ("originalComponentType", ctypes.c_int32),
    ("originallyNormalized", ctypes.c_bool),
]


class AkInput(ctypes.Structure):
    pass


AkInput._fields_ = [
    ("semanticRaw", ctypes.c_char_p),
    ("next", ctypes.POINTER(AkInput)),
    ("accessor", ctypes.POINTER(AkAccessor)),
    ("reserved", ctypes.c_void_p),
    ("index", ctypes.c_uint32),
    ("isIndexed", ctypes.c_bool),
    ("semantic", ctypes.c_int32),
    ("indexOffset", ctypes.c_uint32),
    ("set", ctypes.c_uint32),
]


class AkMeshPrimitive(ctypes.Structure):
    pass


AkMeshPrimitive._fields_ = [
    ("next", ctypes.POINTER(AkMeshPrimitive)),
    ("mesh", ctypes.c_void_p),
    ("bbox", ctypes.c_void_p),
    ("name", ctypes.c_char_p),
    ("bindmaterial", ctypes.c_char_p),
    ("material", ctypes.c_void_p),
    ("materialBindings", ctypes.c_void_p),
    ("input", ctypes.POINTER(AkInput)),
    ("pos", ctypes.POINTER(AkInput)),
    ("indices", ctypes.POINTER(AkIndexArray)),
    ("indexAccessor", ctypes.c_void_p),
    ("extra", ctypes.c_void_p),
    ("udata", ctypes.c_void_p),
    ("type", ctypes.c_int32),
    ("nPolygons", ctypes.c_uint32),
    ("inputCount", ctypes.c_uint32),
    ("center", ctypes.c_float * 3),
    ("indexStride", ctypes.c_uint32),
    ("reserved1", ctypes.c_uint32),
    ("reserved2", ctypes.c_uint32),
    ("reserved3", ctypes.c_void_p),
    ("variantMappings", ctypes.c_void_p),
    ("variantMappingCount", ctypes.c_uint32),
    ("materialBindingCount", ctypes.c_uint32),
    ("gsplat", ctypes.c_void_p),
]


class AkMesh(ctypes.Structure):
    _fields_ = [
        ("geom", ctypes.c_void_p),
        ("convexHullOf", ctypes.c_char_p),
        ("primitive", ctypes.POINTER(AkMeshPrimitive)),
        ("bbox", ctypes.c_void_p),
        ("extra", ctypes.c_void_p),
        ("edith", ctypes.c_void_p),
        ("skins", ctypes.c_void_p),
        ("name", ctypes.c_char_p),
        ("weights", ctypes.c_void_p),
        ("primitiveCount", ctypes.c_uint32),
        ("center", ctypes.c_float * 3),
    ]


class AkGeometry(ctypes.Structure):
    pass


AkGeometry._fields_ = [
    ("next", ctypes.POINTER(AkGeometry)),
    ("name", ctypes.c_char_p),
    ("gdata", ctypes.POINTER(AkObject)),
    ("extra", ctypes.c_void_p),
    ("materialMap", ctypes.c_void_p),
    ("bbox", ctypes.c_void_p),
]


class AkGenericLib(ctypes.Structure):
    _fields_ = [
        ("first", ctypes.c_void_p),
        ("last", ctypes.c_void_p),
        ("count", ctypes.c_uint32),
    ]


class AkGeometryLib(ctypes.Structure):
    _fields_ = [
        ("first", ctypes.POINTER(AkGeometry)),
        ("last", ctypes.POINTER(AkGeometry)),
        ("count", ctypes.c_uint32),
    ]


class AkLibraries(ctypes.Structure):
    _fields_ = [
        ("cameras", AkGenericLib),
        ("lights", AkGenericLib),
        ("materials", AkGenericLib),
        ("geometries", AkGeometryLib),
        ("visualScenes", AkGenericLib),
        ("nodes", AkGenericLib),
        ("animations", AkGenericLib),
        ("buffers", AkGenericLib),
        ("accessors", AkGenericLib),
        ("textures", AkGenericLib),
        ("samplers", AkGenericLib),
        ("images", AkGenericLib),
        ("morphs", AkGenericLib),
        ("skins", AkGenericLib),
    ]


class AkScene(ctypes.Structure):
    _fields_ = [("visualScene", ctypes.c_void_p), ("extra", ctypes.c_void_p)]


class AkMaterialPropertyRegistry(ctypes.Structure):
    _fields_ = [
        ("sets", ctypes.c_void_p),
        ("byId", ctypes.c_void_p),
        ("count", ctypes.c_uint32),
    ]


class AkDoc(ctypes.Structure):
    _fields_ = [
        ("inf", ctypes.c_void_p),
        ("coordSys", ctypes.c_void_p),
        ("unit", ctypes.c_void_p),
        ("extra", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
        ("userData", ctypes.c_void_p),
        ("loadMillis", ctypes.c_float),
        ("lib", AkLibraries),
        ("scene", AkScene),
        ("materialVariants", ctypes.c_void_p),
        ("materialVariantCount", ctypes.c_uint32),
        ("materialProperties", AkMaterialPropertyRegistry),
    ]


@dataclass(slots=True)
class MorphTargetData:
    name: str
    weight: float = 0.0
    vertex_count: int = 0
    positions_f32: object = b""


@dataclass(slots=True)
class LoopFloatAttributeData:
    name: str
    set: int = 0
    width: int = 0
    values_f32: object = b""


@dataclass(slots=True)
class TextureRefData:
    role: str = ""
    path: str = ""
    image_name: str = ""
    sampler_name: str = ""
    color_space: str = ""
    channels: str = ""
    texcoord: str = ""
    coord_input_name: str = ""
    slot: int = 0
    wrap_s: int = 1
    wrap_t: int = 1
    wrap_p: int = 1
    min_filter: int = 0
    mag_filter: int = 0
    mip_filter: int = 0
    has_transform: bool = False
    transform_offset: tuple[float, float] = (0.0, 0.0)
    transform_scale: tuple[float, float] = (1.0, 1.0)
    transform_rotation: float = 0.0
    transform_slot: int = -1
    texture_extra: object | None = None
    texref_extra: object | None = None
    image_extra: object | None = None
    sampler_extra: object | None = None


@dataclass(slots=True)
class MeshPrimitiveData:
    name: str
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int]]
    normals: list[tuple[float, float, float]]
    uvs: list[tuple[float, float]]
    loop_vertex_indices: list[int]
    vertex_count: int = 0
    loop_count: int = 0
    face_count: int = 0
    edge_count: int = 0
    primitive_type: int = AK_PRIMITIVE_TRIANGLES
    primitive_mode: int = 0
    vertices_f32: object = b""
    indices_u32: object = b""
    edges_u32: object = b""
    loop_starts_i32: object = b""
    loop_totals_i32: object = b""
    normals_f32: object = b""
    vertex_normals_f32: object = b""
    uvs_f32: object = b""
    colors_f32: object = b""
    tangents_f32: object = b""
    skin_joints_u16: object = b""
    skin_weights_f32: object = b""
    skin_joint_nodes_i32: object = b""
    skin_inverse_bind_matrices_f32: object = b""
    skin_bind_shape_matrix_f32: object = b""
    skin_pose_anim_channels: list[list[object]] | None = None
    anim_channels: list[object] | None = None
    uv_sets: list[LoopFloatAttributeData] | None = None
    color_sets: list[LoopFloatAttributeData] | None = None
    point_attrs: list[LoopFloatAttributeData] | None = None
    texture_infos: dict[str, TextureRefData] | None = None
    morph_targets: list[MorphTargetData] | None = None
    morph_presets: list[dict] | None = None
    material_variants: list[dict] | None = None
    morph_anim_channels: list[object] | None = None
    material_anim_channels: list[object] | None = None
    smooth_shading: bool = False
    sharp_faces_u8: object = b""
    object_name: str = ""
    matrix_f32: object = b""
    coord_matrix_f32: object = b""
    instance_matrices_f32: object = b""
    node_index: int = -1
    instance_count: int = 0
    has_node: bool = False
    has_gsplat: bool = False
    gsplat_kernel: int = 0
    gsplat_color_space: int = 0
    gsplat_projection: int = 0
    gsplat_sorting_method: int = 0
    gsplat_decoded_count: int = 0
    has_skin: bool = False
    anim_count: int = 0
    morph_target_count: int = 0
    morph_preset_count: int = 0
    morph_anim_count: int = 0
    material_anim_count: int = 0
    material_variant_count: int = 0
    primitive_extra: object | None = None
    mesh_extra: object | None = None
    geometry_extra: object | None = None
    material_extra: object | None = None
    source_extra: object | None = None
    skin_vertex_count: int = 0
    skin_joint_count: int = 0
    skin_joint_width: int = 0
    uv_set_count: int = 0
    color_set_count: int = 0
    point_attr_count: int = 0
    skin_root_node_index: int = -1
    material_name: str = ""
    base_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    transparent_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    emissive_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    specular_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    sheen_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    volume_attenuation_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    volume_scatter_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    diffuse_transmission_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    metallic: float = 1.0
    roughness: float = 1.0
    alpha_cutoff: float = 0.5
    transparent_amount: float = 1.0
    opacity: float = 1.0
    normal_scale: float = 1.0
    occlusion_strength: float = 1.0
    emissive_strength: float = 1.0
    specular_strength: float = 1.0
    ior: float = 1.5
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.0
    clearcoat_normal_scale: float = 1.0
    transmission: float = 0.0
    sheen_roughness: float = 0.0
    iridescence: float = 0.0
    iridescence_ior: float = 1.3
    iridescence_thickness_minimum: float = 100.0
    iridescence_thickness_maximum: float = 400.0
    volume_thickness: float = 0.0
    volume_attenuation_distance: float = float("inf")
    volume_scatter_anisotropy: float = 0.0
    anisotropy: float = 0.0
    anisotropy_rotation: float = 0.0
    diffuse_transmission: float = 0.0
    dispersion: float = 0.0
    alpha_mode: int = 0
    transparent_inverted: bool = False
    double_sided: bool = False
    has_sheen: bool = False
    skin_mesh_in_bind_pose: bool = False
    material_type: int = 0
    file_type: int = 0
    mesh_key: int = 0
    material_key: int = 0
    geometry_key: int = 0
    primitive_index: int = 0
    zero_copy_flags: int = 0
    simple_native: bool = False
    base_color_texture: str = ""
    metallic_roughness_texture: str = ""
    occlusion_texture: str = ""
    normal_texture: str = ""
    emissive_texture: str = ""
    transparent_texture: str = ""
    specular_texture: str = ""
    specular_color_texture: str = ""
    clearcoat_texture: str = ""
    clearcoat_roughness_texture: str = ""
    clearcoat_normal_texture: str = ""
    transmission_texture: str = ""
    sheen_color_texture: str = ""
    sheen_roughness_texture: str = ""
    iridescence_texture: str = ""
    iridescence_thickness_texture: str = ""
    volume_thickness_texture: str = ""
    anisotropy_texture: str = ""
    diffuse_transmission_texture: str = ""
    diffuse_transmission_color_texture: str = ""
    _native_owner: object | None = None


@dataclass(slots=True)
class SceneNodeData:
    name: str
    parent_index: int = -1
    matrix_f32: object = b""
    anim_channels: list[object] | None = None
    anim_count: int = 0
    visible: bool = True
    layers: list[str] | None = None
    camera_type: int = 0
    camera_name: str = ""
    camera_values: tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    camera_extra: object | None = None
    camera_imager_extra: object | None = None
    light_type: int = 0
    light_name: str = ""
    light_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    light_values: tuple[float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0)
    light_extra: object | None = None
    extra: object | None = None
    _native_owner: object | None = None


@dataclass(slots=True)
class AssetKitSceneData:
    meshes: list[MeshPrimitiveData]
    nodes: list[SceneNodeData]
    doc_extra: object | None = None
    scene_extra: object | None = None
    images: list[dict] | None = None
    scene_index: int = -1
    scene_count: int = 0
    scene_name: str = ""
    scene_names: list[str] | None = None


class AssetKitError(RuntimeError):
    pass


_NATIVE_MODULE = None
_NATIVE_MODULE_FAILED = False


def _native_module():
    global _NATIVE_MODULE, _NATIVE_MODULE_FAILED
    if _NATIVE_MODULE is not None:
        return _NATIVE_MODULE
    if _NATIVE_MODULE_FAILED:
        return None
    try:
        from . import _assetkit_blender
    except ImportError:
        _NATIVE_MODULE_FAILED = True
        return None
    _NATIVE_MODULE = _assetkit_blender
    return _NATIVE_MODULE


class AssetKit:
    def __init__(self, library_path: str | os.PathLike[str] | None = None):
        self.library_path = resolve_library_path(library_path)
        self.lib = ctypes.CDLL(str(self.library_path))
        self._bind()

    def _bind(self) -> None:
        self.lib.ak_load.argtypes = [ctypes.POINTER(ctypes.POINTER(AkDoc)), ctypes.c_char_p, ctypes.c_int]
        self.lib.ak_load.restype = ctypes.c_int32
        self.lib.ak_free.argtypes = [ctypes.c_void_p]
        self.lib.ak_free.restype = None
        self.lib.ak_accessorAsFloat.argtypes = [
            ctypes.POINTER(AkAccessor),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
        ]
        self.lib.ak_accessorAsFloat.restype = ctypes.c_size_t

    def load_meshes(self, filepath: str | os.PathLike[str]) -> list[MeshPrimitiveData]:
        doc = ctypes.POINTER(AkDoc)()
        result = self.lib.ak_load(ctypes.byref(doc), os.fsencode(filepath), AK_FILE_TYPE_AUTO)
        if result != AK_OK or not doc:
            raise AssetKitError(f"AssetKit failed to load file: result={result}")

        try:
            return list(self._iter_meshes(doc.contents))
        finally:
            self.lib.ak_free(ctypes.cast(doc, ctypes.c_void_p))

    def _iter_meshes(self, doc: AkDoc) -> Iterator[MeshPrimitiveData]:
        geom_ptr = doc.lib.geometries.first
        while geom_ptr:
            geom = geom_ptr.contents
            gdata = geom.gdata
            if gdata and gdata.contents.type == AK_GEOMETRY_MESH:
                mesh_ptr = ctypes.cast(gdata.contents.pData, ctypes.POINTER(AkMesh))
                yield from self._mesh_primitives(geom, mesh_ptr.contents)
            geom_ptr = geom.next

    def _mesh_primitives(self, geom: AkGeometry, mesh: AkMesh) -> Iterator[MeshPrimitiveData]:
        prim_ptr = mesh.primitive
        prim_index = 0
        while prim_ptr:
            prim = prim_ptr.contents
            if prim.type == AK_PRIMITIVE_TRIANGLES:
                data = self._primitive_data(geom, mesh, prim, prim_index)
                if data.vertices and data.faces:
                    yield data
            prim_ptr = prim.next
            prim_index += 1

    def _primitive_data(
        self,
        geom: AkGeometry,
        mesh: AkMesh,
        prim: AkMeshPrimitive,
        prim_index: int,
    ) -> MeshPrimitiveData:
        pos_input = prim.pos or self._find_input(prim, {AK_INPUT_POSITION}, {"POSITION"})
        if not pos_input or not pos_input.contents.accessor:
            return MeshPrimitiveData("", [], [], [], [], [])

        positions = self._accessor_tuples(pos_input.contents.accessor, 3)
        raw_indices = self._primitive_indices(prim)
        if raw_indices:
            stride = max(1, int(prim.indexStride or 1))
            pos_offset = int(pos_input.contents.indexOffset or 0)
            vertex_indices = [raw_indices[i + pos_offset] for i in range(0, len(raw_indices), stride)]
        else:
            vertex_indices = list(range(len(positions)))

        tri_count = len(vertex_indices) // 3
        faces = [
            (vertex_indices[i], vertex_indices[i + 1], vertex_indices[i + 2])
            for i in range(0, tri_count * 3, 3)
        ]

        normal_input = self._find_input(prim, {AK_INPUT_NORMAL}, {"NORMAL"})
        normals = self._loop_attribute(prim, normal_input, raw_indices, vertex_indices, 3)

        uv_input = self._find_input(prim, {AK_INPUT_TEXCOORD, AK_INPUT_UV}, {"TEXCOORD", "UV"})
        uvs = self._loop_attribute(prim, uv_input, raw_indices, vertex_indices, 2)

        base_name = _decode(mesh.name) or _decode(geom.name) or "AssetKitMesh"
        name = f"{base_name}_{prim_index}" if mesh.primitiveCount > 1 else base_name
        return MeshPrimitiveData(name, positions, faces, normals, uvs, vertex_indices[: tri_count * 3])

    def _find_input(
        self,
        prim: AkMeshPrimitive,
        semantics: set[int],
        raw_names: set[str],
    ) -> Optional[ctypes.POINTER(AkInput)]:
        inp = prim.input
        while inp:
            item = inp.contents
            raw = _decode(item.semanticRaw).upper()
            if item.semantic in semantics or raw in raw_names:
                return inp
            inp = item.next
        return None

    def _accessor_tuples(self, accessor: ctypes.POINTER(AkAccessor), width: int) -> list[tuple]:
        acc = accessor.contents
        count = int(acc.count)
        comp_count = int(acc.componentCount or width)
        total = count * comp_count
        if total <= 0:
            return []
        out = (ctypes.c_float * total)()
        written = int(self.lib.ak_accessorAsFloat(accessor, out, total))
        if written == 0:
            values = self._read_accessor_fallback(acc, comp_count)
        else:
            values = [float(out[i]) for i in range(min(written, total))]
        tuples = []
        for i in range(count):
            start = i * comp_count
            row = values[start : start + comp_count]
            if len(row) >= width:
                tuples.append(tuple(row[:width]))
        return tuples

    def _loop_attribute(
        self,
        prim: AkMeshPrimitive,
        inp: Optional[ctypes.POINTER(AkInput)],
        raw_indices: list[int],
        vertex_indices: list[int],
        width: int,
    ) -> list[tuple]:
        if not inp or not inp.contents.accessor:
            return []
        values = self._accessor_tuples(inp.contents.accessor, width)
        if not values:
            return []

        loop_count = (len(vertex_indices) // 3) * 3
        if raw_indices:
            stride = max(1, int(prim.indexStride or 1))
            offset = int(inp.contents.indexOffset or 0)
            attr_indices = [raw_indices[i + offset] for i in range(0, len(raw_indices), stride)]
        else:
            attr_indices = vertex_indices

        if len(values) == loop_count:
            return values[:loop_count]
        return [values[i] if 0 <= i < len(values) else tuple([0.0] * width) for i in attr_indices[:loop_count]]

    def _read_accessor_fallback(self, acc: AkAccessor, comp_count: int) -> list[float]:
        if not acc.buffer or not acc.buffer.contents.data:
            return []
        type_map = {
            AKT_FLOAT: ctypes.c_float,
            AKT_DOUBLE: ctypes.c_double,
            AKT_INT: ctypes.c_int32,
            AKT_UINT: ctypes.c_uint32,
            AKT_BYTE: ctypes.c_int8,
            AKT_UBYTE: ctypes.c_uint8,
            AKT_SHORT: ctypes.c_int16,
            AKT_USHORT: ctypes.c_uint16,
            AKT_INT64: ctypes.c_int64,
            AKT_UINT64: ctypes.c_uint64,
        }
        c_type = type_map.get(int(acc.componentType))
        if c_type is None:
            return []
        stride = int(acc.byteStride or (ctypes.sizeof(c_type) * comp_count))
        base = int(acc.buffer.contents.data) + int(acc.byteOffset)
        values: list[float] = []
        for row in range(int(acc.count)):
            row_addr = base + row * stride
            for col in range(comp_count):
                addr = row_addr + col * ctypes.sizeof(c_type)
                values.append(float(ctypes.cast(addr, ctypes.POINTER(c_type)).contents.value))
        return values

    def _primitive_indices(self, prim: AkMeshPrimitive) -> list[int]:
        if prim.indices:
            return self._index_data(prim.indices)
        if prim.indexAccessor:
            return self._accessor_indices(ctypes.cast(prim.indexAccessor, ctypes.POINTER(AkAccessor)))
        return []

    @staticmethod
    def _index_data(indices: ctypes.POINTER(AkIndexArray)) -> list[int]:
        if not indices:
            return []
        item = indices.contents
        count = int(item.count)
        if count <= 0:
            return []
        type_map = {
            AKT_UBYTE: ctypes.c_uint8,
            AKT_USHORT: ctypes.c_uint16,
            AKT_UINT: ctypes.c_uint32,
        }
        c_type = type_map.get(int(item.componentType))
        if c_type is None:
            return []
        data_addr = ctypes.addressof(item) + AkIndexArray.reserved.offset + ctypes.sizeof(ctypes.c_uint32)
        array_type = c_type * count
        return [int(v) for v in ctypes.cast(data_addr, ctypes.POINTER(array_type)).contents]

    @staticmethod
    def _accessor_indices(accessor: ctypes.POINTER(AkAccessor)) -> list[int]:
        if not accessor:
            return []
        acc = accessor.contents
        if not acc.buffer or not acc.buffer.contents.data or acc.count <= 0:
            return []
        type_map = {
            AKT_UBYTE: ctypes.c_uint8,
            AKT_USHORT: ctypes.c_uint16,
            AKT_UINT: ctypes.c_uint32,
        }
        c_type = type_map.get(int(acc.componentType))
        if c_type is None:
            return []
        count = int(acc.count)
        stride = int(acc.byteStride or acc.bytesPerComponent or ctypes.sizeof(c_type))
        base = int(acc.buffer.contents.data) + int(acc.byteOffset)
        if stride == ctypes.sizeof(c_type):
            array_type = c_type * count
            return [int(v) for v in ctypes.cast(base, ctypes.POINTER(array_type)).contents]
        out: list[int] = []
        for row in range(count):
            addr = base + row * stride
            out.append(int(ctypes.cast(addr, ctypes.POINTER(c_type)).contents.value))
        return out


def resolve_library_path(configured_path: str | os.PathLike[str] | None = None) -> Path:
    candidates: list[str] = []
    if configured_path:
        candidates.append(os.fspath(configured_path))
    env_path = os.environ.get("ASSETKIT_LIBRARY_PATH")
    if env_path:
        candidates.append(env_path)

    names = ("libassetkit.dylib", "libassetkit.so", "assetkit.dll")
    package_root = Path(__file__).resolve().parent.parent
    roots = []
    for env_name in ("ASSETKIT_ROOT", "ASSETKIT_BLENDER_ASSETKIT_ROOT"):
        env_root = os.environ.get(env_name)
        if env_root:
            roots.append(Path(env_root))
    roots.extend((package_root.parent / "assetkit", package_root / "deps" / "assetkit"))
    for root in roots:
        for base in (root / "build", root / "build" / "src", root / "build" / "Release", root / "lib"):
            candidates.extend(str(base / name) for name in names)

    found = ctypes.util.find_library("assetkit")
    if found:
        candidates.append(found)

    for candidate in candidates:
        if candidate and (Path(candidate).exists() or os.path.isabs(candidate) is False):
            return Path(candidate)

    raise AssetKitError(
        "AssetKit shared library was not found. Set the add-on preference or ASSETKIT_LIBRARY_PATH."
    )


def _decode(value: bytes | None) -> str:
    if not value:
        return ""
    return value.decode("utf-8", "replace")


def _profile_enabled() -> bool:
    global _PROFILE_ENABLED

    if _PROFILE_ENABLED is not None:
        return _PROFILE_ENABLED

    value = os.environ.get("ASSETKIT_BLENDER_PROFILE")
    if value is None or value == "":
        _PROFILE_ENABLED = False
    else:
        _PROFILE_ENABLED = value.lower() not in {"0", "false", "off", "no"}
    return _PROFILE_ENABLED


def _profile_log(message: str) -> None:
    if _profile_enabled():
        print(f"[AssetKit python] {message}", flush=True)


def native_load_meshes(
    filepath: str | os.PathLike[str],
    options: dict | None = None,
) -> AssetKitSceneData | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    profile = _profile_enabled()
    total_started_at = time.perf_counter() if profile else 0.0
    try:
        native_started_at = time.perf_counter() if profile else 0.0
        result = _assetkit_blender.load_meshes(os.fspath(filepath), options or None)
        native_ms = (time.perf_counter() - native_started_at) * 1000.0 if profile else 0.0
    except RuntimeError as exc:
        raise AssetKitError(str(exc)) from exc
    raw_meshes = result.get("meshes", []) if isinstance(result, dict) else result
    raw_nodes = result.get("nodes", []) if isinstance(result, dict) else []

    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        meshes_started_at = time.perf_counter() if profile else 0.0
        meshes = _native_meshes_from_raw(raw_meshes)
        meshes_ms = (time.perf_counter() - meshes_started_at) * 1000.0 if profile else 0.0
        nodes_started_at = time.perf_counter() if profile else 0.0
        nodes = _native_nodes_from_raw(raw_nodes)
        nodes_ms = (time.perf_counter() - nodes_started_at) * 1000.0 if profile else 0.0
    finally:
        if gc_was_enabled:
            gc.enable()
    data = AssetKitSceneData(
        meshes=meshes,
        nodes=nodes,
        doc_extra=result.get("doc_extra") if isinstance(result, dict) else None,
        scene_extra=result.get("scene_extra") if isinstance(result, dict) else None,
        images=list(result.get("images") or []) if isinstance(result, dict) else None,
        scene_index=_native_result_int(result, "scene_index", -1),
        scene_count=_native_result_int(result, "scene_count", 0),
        scene_name=str(result.get("scene_name") or "") if isinstance(result, dict) else "",
        scene_names=list(result.get("scene_names") or []) if isinstance(result, dict) else None,
    )
    if profile:
        _profile_log(
            "load_meshes "
            f"native={native_ms:.3f}ms "
            f"mesh_dataclass={meshes_ms:.3f}ms "
            f"node_dataclass={nodes_ms:.3f}ms "
            f"meshes={len(meshes)} nodes={len(nodes)} "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return data


def native_open_scene_stream(
    filepath: str | os.PathLike[str],
    options: dict | None = None,
) -> NativeSceneStream | None:
    _assetkit_blender = _native_module()
    if _assetkit_blender is None:
        return None

    profile = _profile_enabled()
    total_started_at = time.perf_counter() if profile else 0.0
    try:
        native_started_at = time.perf_counter() if profile else 0.0
        result = _assetkit_blender.open_scene(os.fspath(filepath), options or None)
        native_ms = (time.perf_counter() - native_started_at) * 1000.0 if profile else 0.0
    except RuntimeError as exc:
        raise AssetKitError(str(exc)) from exc
    nodes_started_at = time.perf_counter() if profile else 0.0
    nodes = _native_nodes_from_raw(result.get("nodes", []))
    nodes_ms = (time.perf_counter() - nodes_started_at) * 1000.0 if profile else 0.0
    stream = NativeSceneStream(
        _assetkit_blender,
        result.get("_owner"),
        int(result.get("mesh_count") or 0),
        nodes,
        result.get("doc_extra"),
        result.get("scene_extra"),
        list(result.get("images") or []),
        list(result.get("required_node_indices") or []),
        _native_result_int(result, "scene_index", -1),
        _native_result_int(result, "scene_count", 0),
        str(result.get("scene_name") or ""),
        list(result.get("scene_names") or []),
    )
    if profile:
        _profile_log(
            "open_scene "
            f"native={native_ms:.3f}ms "
            f"node_dataclass={nodes_ms:.3f}ms "
            f"meshes={stream.mesh_count} nodes={len(nodes)} "
            f"total={(time.perf_counter() - total_started_at) * 1000.0:.3f}ms"
        )
    return stream


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


class NativeSceneStream:
    def __init__(
        self,
        module: object,
        owner: object,
        mesh_count: int,
        nodes: list[SceneNodeData],
        doc_extra: object | None = None,
        scene_extra: object | None = None,
        images: list[dict] | None = None,
        required_node_indices: list[int] | None = None,
        scene_index: int = -1,
        scene_count: int = 0,
        scene_name: str = "",
        scene_names: list[str] | None = None,
    ) -> None:
        self._module = module
        self._owner = owner
        self.mesh_count = mesh_count
        self.nodes = nodes
        self.doc_extra = doc_extra
        self.scene_extra = scene_extra
        self.images = images or []
        self.required_node_indices = required_node_indices or []
        self.scene_index = scene_index
        self.scene_count = scene_count
        self.scene_name = scene_name
        self.scene_names = scene_names or []

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


def _native_result_int(result: object, key: str, default: int) -> int:
    if not isinstance(result, dict):
        return default
    value = result.get(key)
    return int(value if value is not None else default)


(
    _N_OWNER,
    _N_NAME,
    _N_PARENT_INDEX,
    _N_VISIBLE,
    _N_LAYERS,
    _N_CAMERA_TYPE,
    _N_CAMERA_NAME,
    _N_CAMERA_EXTRA,
    _N_CAMERA_IMAGER_EXTRA,
    _N_CAMERA_VALUES,
    _N_LIGHT_TYPE,
    _N_LIGHT_NAME,
    _N_LIGHT_EXTRA,
    _N_LIGHT_COLOR,
    _N_LIGHT_VALUES,
    _N_MATRIX_F32,
    _N_EXTRA,
    _N_ANIM_COUNT,
    _N_ANIM_CHANNELS,
) = range(19)


def _native_nodes_from_raw(raw_nodes: Iterable[dict]) -> list[SceneNodeData]:
    nodes = []
    for item in raw_nodes:
        if isinstance(item, tuple) and len(item) >= 19:
            extra = item[_N_EXTRA]
            visible = _extra_bool(extra, ("extensions", "KHR_node_visibility", "visible")) if extra else None
            if visible is None:
                visible = bool(item[_N_VISIBLE])
            nodes.append(
                SceneNodeData(
                    name=item[_N_NAME] or "AssetKitNode",
                    parent_index=int(item[_N_PARENT_INDEX] if item[_N_PARENT_INDEX] is not None else -1),
                    matrix_f32=item[_N_MATRIX_F32] or b"",
                    anim_channels=item[_N_ANIM_CHANNELS] or [],
                    anim_count=int(item[_N_ANIM_COUNT] or 0),
                    visible=visible,
                    layers=item[_N_LAYERS] or [],
                    camera_type=int(item[_N_CAMERA_TYPE] or 0),
                    camera_name=item[_N_CAMERA_NAME] or "",
                    camera_values=item[_N_CAMERA_VALUES] or (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                    camera_extra=item[_N_CAMERA_EXTRA],
                    camera_imager_extra=item[_N_CAMERA_IMAGER_EXTRA],
                    light_type=int(item[_N_LIGHT_TYPE] or 0),
                    light_name=item[_N_LIGHT_NAME] or "",
                    light_color=item[_N_LIGHT_COLOR] or (1.0, 1.0, 1.0),
                    light_values=item[_N_LIGHT_VALUES] or (0.0, 0.0, 0.0, 0.0, 0.0),
                    light_extra=item[_N_LIGHT_EXTRA],
                    extra=extra,
                    _native_owner=item[_N_OWNER],
                )
            )
            continue

        extra = item.get("extra")
        visible = _extra_bool(extra, ("extensions", "KHR_node_visibility", "visible")) if extra else None
        if visible is None:
            visible = bool(item.get("visible", True))
        nodes.append(
            SceneNodeData(
                name=item.get("name") or "AssetKitNode",
                parent_index=int(item.get("parent_index") if item.get("parent_index") is not None else -1),
                matrix_f32=item.get("matrix_f32") or b"",
                anim_channels=item.get("anim_channels") or [],
                anim_count=int(item.get("anim_count") or 0),
                visible=visible,
                layers=list(item.get("layers") or []),
                camera_type=int(item.get("camera_type") or 0),
                camera_name=item.get("camera_name") or "",
                camera_values=tuple(item.get("camera_values") or (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
                camera_extra=item.get("camera_extra"),
                camera_imager_extra=item.get("camera_imager_extra"),
                light_type=int(item.get("light_type") or 0),
                light_name=item.get("light_name") or "",
                light_color=tuple(item.get("light_color") or (1.0, 1.0, 1.0)),
                light_values=tuple(item.get("light_values") or (0.0, 0.0, 0.0, 0.0, 0.0)),
                light_extra=item.get("light_extra"),
                extra=extra,
                _native_owner=item.get("_owner"),
            )
        )
    return nodes


def _extra_bool(extra: object, path: tuple[str, ...]) -> bool | None:
    node = _extra_child_path(extra, path)
    if not isinstance(node, dict):
        return None

    value = str(node.get("value") or "").strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    return None


def _extra_child_path(extra: object, path: tuple[str, ...]) -> object | None:
    node = extra
    for name in path:
        if not isinstance(node, dict):
            return None
        node = next(
            (
                child
                for child in node.get("children") or []
                if isinstance(child, dict) and child.get("name") == name
            ),
            None,
        )
    return node


_NATIVE_SIMPLE_MESH_COMPLEX_KEYS = (
    "uv_sets",
    "color_sets",
    "point_attrs",
    "texture_infos",
    "morph_targets",
    "morph_presets",
    "material_variants",
    "skin_pose_anim_channels",
    "anim_channels",
    "morph_anim_channels",
    "material_anim_channels",
    "primitive_extra",
    "mesh_extra",
    "geometry_extra",
    "material_extra",
    "source_extra",
    "has_skin",
    "has_gsplat",
    "material_key",
    "material_name",
    "base_color_texture",
    "metallic_roughness_texture",
    "occlusion_texture",
    "normal_texture",
    "emissive_texture",
    "transparent_texture",
    "specular_texture",
    "specular_color_texture",
    "clearcoat_texture",
    "clearcoat_roughness_texture",
    "clearcoat_normal_texture",
    "transmission_texture",
    "sheen_color_texture",
    "sheen_roughness_texture",
    "iridescence_texture",
    "iridescence_thickness_texture",
    "volume_thickness_texture",
    "anisotropy_texture",
    "diffuse_transmission_texture",
    "diffuse_transmission_color_texture",
)

(
    _S_OWNER,
    _S_NAME,
    _S_OBJECT_NAME,
    _S_VERTEX_COUNT,
    _S_LOOP_COUNT,
    _S_FACE_COUNT,
    _S_PRIMITIVE_TYPE,
    _S_PRIMITIVE_MODE,
    _S_FILE_TYPE,
    _S_MESH_KEY,
    _S_PRIMITIVE_INDEX,
    _S_ZERO_COPY_FLAGS,
    _S_HAS_NODE,
    _S_NODE_INDEX,
    _S_MATRIX_F32,
    _S_COORD_MATRIX_F32,
    _S_INSTANCE_COUNT,
    _S_INSTANCE_MATRICES_F32,
    _S_VERTICES_F32,
    _S_INDICES_U32,
    _S_LOOP_STARTS_I32,
    _S_LOOP_TOTALS_I32,
    _S_NORMALS_F32,
    _S_VERTEX_NORMALS_F32,
    _S_TANGENTS_F32,
    _S_GEOMETRY_KEY,
    _S_EDGE_COUNT,
    _S_EDGES_U32,
    _S_UVS_F32,
    _S_BASE_COLOR_TEXTURE,
    _S_MATERIAL_TYPE,
    _S_MATERIAL_KEY,
    _S_METALLIC,
    _S_ROUGHNESS,
    _S_DOUBLE_SIDED,
    _S_SMOOTH_SHADING,
) = range(36)
_S_LEGACY_FIELD_COUNT = _S_GEOMETRY_KEY + 1
_S_FIELD_COUNT = _S_SMOOTH_SHADING + 1

(
    _M_OWNER,
    _M_NAME,
    _M_OBJECT_NAME,
    _M_VERTEX_COUNT,
    _M_LOOP_COUNT,
    _M_FACE_COUNT,
    _M_PRIMITIVE_TYPE,
    _M_PRIMITIVE_MODE,
    _M_MATERIAL_NAME,
    _M_BASE_COLOR,
    _M_TRANSPARENT_COLOR,
    _M_EMISSIVE_COLOR,
    _M_SPECULAR_COLOR,
    _M_SHEEN_COLOR,
    _M_VOLUME_ATTENUATION_COLOR,
    _M_VOLUME_SCATTER_COLOR,
    _M_DIFFUSE_TRANSMISSION_COLOR,
    _M_METALLIC,
    _M_ROUGHNESS,
    _M_ALPHA_CUTOFF,
    _M_TRANSPARENT_AMOUNT,
    _M_OPACITY,
    _M_NORMAL_SCALE,
    _M_OCCLUSION_STRENGTH,
    _M_EMISSIVE_STRENGTH,
    _M_SPECULAR_STRENGTH,
    _M_IOR,
    _M_CLEARCOAT,
    _M_CLEARCOAT_ROUGHNESS,
    _M_CLEARCOAT_NORMAL_SCALE,
    _M_TRANSMISSION,
    _M_SHEEN_ROUGHNESS,
    _M_IRIDESCENCE,
    _M_IRIDESCENCE_IOR,
    _M_IRIDESCENCE_THICKNESS_MINIMUM,
    _M_IRIDESCENCE_THICKNESS_MAXIMUM,
    _M_VOLUME_THICKNESS,
    _M_VOLUME_ATTENUATION_DISTANCE,
    _M_VOLUME_SCATTER_ANISOTROPY,
    _M_ANISOTROPY,
    _M_ANISOTROPY_ROTATION,
    _M_DIFFUSE_TRANSMISSION,
    _M_DISPERSION,
    _M_ALPHA_MODE,
    _M_TRANSPARENT_INVERTED,
    _M_DOUBLE_SIDED,
    _M_MATERIAL_TYPE,
    _M_FILE_TYPE,
    _M_MESH_KEY,
    _M_MATERIAL_KEY,
    _M_PRIMITIVE_INDEX,
    _M_HAS_NODE,
    _M_NODE_INDEX,
    _M_INSTANCE_COUNT,
    _M_HAS_GSPLAT,
    _M_GSPLAT_KERNEL,
    _M_GSPLAT_COLOR_SPACE,
    _M_GSPLAT_PROJECTION,
    _M_GSPLAT_SORTING_METHOD,
    _M_GSPLAT_DECODED_COUNT,
    _M_HAS_SKIN,
    _M_HAS_SHEEN,
    _M_SKIN_VERTEX_COUNT,
    _M_SKIN_JOINT_COUNT,
    _M_SKIN_JOINT_WIDTH,
    _M_SKIN_ROOT_NODE_INDEX,
    _M_SKIN_MESH_IN_BIND_POSE,
    _M_SKIN_POSE_ANIM_CHANNELS,
    _M_ZERO_COPY_FLAGS,
    _M_UV_SET_COUNT,
    _M_COLOR_SET_COUNT,
    _M_POINT_ATTR_COUNT,
    _M_ANIM_COUNT,
    _M_ANIM_CHANNELS,
    _M_MORPH_TARGET_COUNT,
    _M_MORPH_TARGETS,
    _M_MORPH_PRESET_COUNT,
    _M_MORPH_PRESETS,
    _M_MORPH_ANIM_COUNT,
    _M_MORPH_ANIM_CHANNELS,
    _M_MATERIAL_ANIM_COUNT,
    _M_MATERIAL_ANIM_CHANNELS,
    _M_UV_SETS,
    _M_COLOR_SETS,
    _M_POINT_ATTRS,
    _M_TEXTURE_INFOS,
    _M_PRIMITIVE_EXTRA,
    _M_MESH_EXTRA,
    _M_GEOMETRY_EXTRA,
    _M_MATERIAL_EXTRA,
    _M_SOURCE_EXTRA,
    _M_MATERIAL_VARIANT_COUNT,
    _M_MATERIAL_VARIANTS,
    _M_MATRIX_F32,
    _M_COORD_MATRIX_F32,
    _M_INSTANCE_MATRICES_F32,
    _M_BASE_COLOR_TEXTURE,
    _M_METALLIC_ROUGHNESS_TEXTURE,
    _M_OCCLUSION_TEXTURE,
    _M_NORMAL_TEXTURE,
    _M_EMISSIVE_TEXTURE,
    _M_TRANSPARENT_TEXTURE,
    _M_SPECULAR_TEXTURE,
    _M_SPECULAR_COLOR_TEXTURE,
    _M_CLEARCOAT_TEXTURE,
    _M_CLEARCOAT_ROUGHNESS_TEXTURE,
    _M_CLEARCOAT_NORMAL_TEXTURE,
    _M_TRANSMISSION_TEXTURE,
    _M_SHEEN_COLOR_TEXTURE,
    _M_SHEEN_ROUGHNESS_TEXTURE,
    _M_IRIDESCENCE_TEXTURE,
    _M_IRIDESCENCE_THICKNESS_TEXTURE,
    _M_VOLUME_THICKNESS_TEXTURE,
    _M_ANISOTROPY_TEXTURE,
    _M_DIFFUSE_TRANSMISSION_TEXTURE,
    _M_DIFFUSE_TRANSMISSION_COLOR_TEXTURE,
    _M_VERTICES_F32,
    _M_INDICES_U32,
    _M_LOOP_STARTS_I32,
    _M_LOOP_TOTALS_I32,
    _M_NORMALS_F32,
    _M_VERTEX_NORMALS_F32,
    _M_UVS_F32,
    _M_COLORS_F32,
    _M_TANGENTS_F32,
    _M_SKIN_JOINTS_U16,
    _M_SKIN_WEIGHTS_F32,
    _M_SKIN_JOINT_NODES_I32,
    _M_SKIN_INVERSE_BIND_MATRICES_F32,
    _M_SKIN_BIND_SHAPE_MATRIX_F32,
    _M_GEOMETRY_KEY,
    _M_EDGE_COUNT,
    _M_EDGES_U32,
    _M_SMOOTH_SHADING,
) = range(134)

_M_FIELD_NAMES = (
    "_owner",
    "name",
    "object_name",
    "vertex_count",
    "loop_count",
    "face_count",
    "primitive_type",
    "primitive_mode",
    "material_name",
    "base_color",
    "transparent_color",
    "emissive_color",
    "specular_color",
    "sheen_color",
    "volume_attenuation_color",
    "volume_scatter_color",
    "diffuse_transmission_color",
    "metallic",
    "roughness",
    "alpha_cutoff",
    "transparent_amount",
    "opacity",
    "normal_scale",
    "occlusion_strength",
    "emissive_strength",
    "specular_strength",
    "ior",
    "clearcoat",
    "clearcoat_roughness",
    "clearcoat_normal_scale",
    "transmission",
    "sheen_roughness",
    "iridescence",
    "iridescence_ior",
    "iridescence_thickness_minimum",
    "iridescence_thickness_maximum",
    "volume_thickness",
    "volume_attenuation_distance",
    "volume_scatter_anisotropy",
    "anisotropy",
    "anisotropy_rotation",
    "diffuse_transmission",
    "dispersion",
    "alpha_mode",
    "transparent_inverted",
    "double_sided",
    "material_type",
    "file_type",
    "mesh_key",
    "material_key",
    "primitive_index",
    "has_node",
    "node_index",
    "instance_count",
    "has_gsplat",
    "gsplat_kernel",
    "gsplat_color_space",
    "gsplat_projection",
    "gsplat_sorting_method",
    "gsplat_decoded_count",
    "has_skin",
    "has_sheen",
    "skin_vertex_count",
    "skin_joint_count",
    "skin_joint_width",
    "skin_root_node_index",
    "skin_mesh_in_bind_pose",
    "skin_pose_anim_channels",
    "zero_copy_flags",
    "uv_set_count",
    "color_set_count",
    "point_attr_count",
    "anim_count",
    "anim_channels",
    "morph_target_count",
    "morph_targets",
    "morph_preset_count",
    "morph_presets",
    "morph_anim_count",
    "morph_anim_channels",
    "material_anim_count",
    "material_anim_channels",
    "uv_sets",
    "color_sets",
    "point_attrs",
    "texture_infos",
    "primitive_extra",
    "mesh_extra",
    "geometry_extra",
    "material_extra",
    "source_extra",
    "material_variant_count",
    "material_variants",
    "matrix_f32",
    "coord_matrix_f32",
    "instance_matrices_f32",
    "base_color_texture",
    "metallic_roughness_texture",
    "occlusion_texture",
    "normal_texture",
    "emissive_texture",
    "transparent_texture",
    "specular_texture",
    "specular_color_texture",
    "clearcoat_texture",
    "clearcoat_roughness_texture",
    "clearcoat_normal_texture",
    "transmission_texture",
    "sheen_color_texture",
    "sheen_roughness_texture",
    "iridescence_texture",
    "iridescence_thickness_texture",
    "volume_thickness_texture",
    "anisotropy_texture",
    "diffuse_transmission_texture",
    "diffuse_transmission_color_texture",
    "vertices_f32",
    "indices_u32",
    "loop_starts_i32",
    "loop_totals_i32",
    "normals_f32",
    "vertex_normals_f32",
    "uvs_f32",
    "colors_f32",
    "tangents_f32",
    "skin_joints_u16",
    "skin_weights_f32",
    "skin_joint_nodes_i32",
    "skin_inverse_bind_matrices_f32",
    "skin_bind_shape_matrix_f32",
    "geometry_key",
    "edge_count",
    "edges_u32",
    "smooth_shading",
)


def _native_mesh_field_getter(item):
    if isinstance(item, tuple):
        if len(item) >= len(_M_FIELD_NAMES):
            return item.__getitem__
        count = len(item)
        return lambda index: item[index] if index < count else None
    names = _M_FIELD_NAMES
    return lambda index: item.get(names[index])


def _native_mesh_is_simple(item: object) -> bool:
    if isinstance(item, tuple):
        return _S_LEGACY_FIELD_COUNT <= len(item) <= _S_FIELD_COUNT
    if not isinstance(item, dict):
        return False
    if "material_name" not in item and "uv_sets" not in item:
        return True
    for key in _NATIVE_SIMPLE_MESH_COMPLEX_KEYS:
        if item.get(key):
            return False
    return True


def _native_simple_mesh_from_raw(item: dict | tuple) -> MeshPrimitiveData:
    if isinstance(item, tuple):
        count = len(item)
        data = MeshPrimitiveData(
            item[_S_NAME] or "AssetKitMesh",
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
        )
        data.vertex_count = int(item[_S_VERTEX_COUNT] or 0)
        data.loop_count = int(item[_S_LOOP_COUNT] or 0)
        data.face_count = int(item[_S_FACE_COUNT] or 0)
        data.edge_count = int(item[_S_EDGE_COUNT] or 0) if count > _S_EDGE_COUNT else 0
        data.primitive_type = int(item[_S_PRIMITIVE_TYPE] or AK_PRIMITIVE_TRIANGLES)
        data.primitive_mode = int(item[_S_PRIMITIVE_MODE] or 0)
        data.vertices_f32 = item[_S_VERTICES_F32] or b""
        data.indices_u32 = item[_S_INDICES_U32] or b""
        data.edges_u32 = (item[_S_EDGES_U32] or b"") if count > _S_EDGES_U32 else b""
        data.loop_starts_i32 = item[_S_LOOP_STARTS_I32] or b""
        data.loop_totals_i32 = item[_S_LOOP_TOTALS_I32] or b""
        data.normals_f32 = item[_S_NORMALS_F32] or b""
        data.vertex_normals_f32 = item[_S_VERTEX_NORMALS_F32] or b""
        data.tangents_f32 = item[_S_TANGENTS_F32] or b""
        data.uvs_f32 = (item[_S_UVS_F32] or b"") if count > _S_UVS_F32 else b""
        data.object_name = item[_S_OBJECT_NAME] or ""
        data.matrix_f32 = item[_S_MATRIX_F32] or b""
        data.coord_matrix_f32 = item[_S_COORD_MATRIX_F32] or b""
        data.instance_matrices_f32 = item[_S_INSTANCE_MATRICES_F32] or b""
        data.node_index = int(item[_S_NODE_INDEX] if item[_S_NODE_INDEX] is not None else -1)
        data.instance_count = int(item[_S_INSTANCE_COUNT] or 0)
        data.has_node = bool(item[_S_HAS_NODE])
        data.file_type = int(item[_S_FILE_TYPE] or 0)
        data.mesh_key = int(item[_S_MESH_KEY] or 0)
        data.primitive_index = int(item[_S_PRIMITIVE_INDEX] or 0)
        data.zero_copy_flags = int(item[_S_ZERO_COPY_FLAGS] or 0)
        data.geometry_key = int(item[_S_GEOMETRY_KEY] or 0)
        data.base_color_texture = (item[_S_BASE_COLOR_TEXTURE] or "") if count > _S_BASE_COLOR_TEXTURE else ""
        if count > _S_MATERIAL_TYPE:
            data.material_type = int(item[_S_MATERIAL_TYPE] or 0)
        if count > _S_MATERIAL_KEY:
            data.material_key = int(item[_S_MATERIAL_KEY] or 0)
        if count > _S_METALLIC:
            data.metallic = float(item[_S_METALLIC] if item[_S_METALLIC] is not None else 1.0)
        if count > _S_ROUGHNESS:
            data.roughness = float(item[_S_ROUGHNESS] if item[_S_ROUGHNESS] is not None else 1.0)
        if count > _S_DOUBLE_SIDED:
            data.double_sided = bool(item[_S_DOUBLE_SIDED])
        if count > _S_SMOOTH_SHADING:
            data.smooth_shading = bool(item[_S_SMOOTH_SHADING])
        data.simple_native = True
        data._native_owner = item[_S_OWNER]
        return data

    get = item.get
    data = MeshPrimitiveData(
        get("name") or "AssetKitMesh",
        _EMPTY_SEQUENCE,
        _EMPTY_SEQUENCE,
        _EMPTY_SEQUENCE,
        _EMPTY_SEQUENCE,
        _EMPTY_SEQUENCE,
    )
    data.vertex_count = int(get("vertex_count") or 0)
    data.loop_count = int(get("loop_count") or 0)
    data.face_count = int(get("face_count") or 0)
    data.edge_count = int(get("edge_count") or 0)
    data.primitive_type = int(get("primitive_type") or AK_PRIMITIVE_TRIANGLES)
    data.primitive_mode = int(get("primitive_mode") or 0)
    data.vertices_f32 = get("vertices_f32") or b""
    data.indices_u32 = get("indices_u32") or b""
    data.edges_u32 = get("edges_u32") or b""
    data.loop_starts_i32 = get("loop_starts_i32") or b""
    data.loop_totals_i32 = get("loop_totals_i32") or b""
    data.normals_f32 = get("normals_f32") or b""
    data.vertex_normals_f32 = get("vertex_normals_f32") or b""
    data.uvs_f32 = get("uvs_f32") or b""
    data.colors_f32 = get("colors_f32") or b""
    data.tangents_f32 = get("tangents_f32") or b""
    data.object_name = get("object_name") or ""
    data.matrix_f32 = get("matrix_f32") or b""
    data.coord_matrix_f32 = get("coord_matrix_f32") or b""
    data.instance_matrices_f32 = get("instance_matrices_f32") or b""
    node_index = get("node_index")
    data.node_index = int(node_index if node_index is not None else -1)
    data.instance_count = int(get("instance_count") or 0)
    data.has_node = bool(get("has_node"))
    data.file_type = int(get("file_type") or 0)
    data.mesh_key = int(get("mesh_key") or 0)
    data.primitive_index = int(get("primitive_index") or 0)
    data.zero_copy_flags = int(get("zero_copy_flags") or 0)
    data.geometry_key = int(get("geometry_key") or 0)
    data.smooth_shading = bool(get("smooth_shading"))
    data.simple_native = True
    data._native_owner = get("_owner")
    return data


def _native_meshes_from_raw(raw_meshes: Iterable[dict]) -> list[MeshPrimitiveData]:
    meshes = []
    for item in raw_meshes:
        if _native_mesh_is_simple(item):
            meshes.append(_native_simple_mesh_from_raw(item))
            continue

        get = _native_mesh_field_getter(item)
        uv_sets = []
        for attr in get(_M_UV_SETS) or []:
            uv_sets.append(
                LoopFloatAttributeData(
                    name=attr.get("name") or "UVMap",
                    set=int(attr.get("set") or 0),
                    width=int(attr.get("width") or 0),
                    values_f32=attr.get("values_f32") or b"",
                )
            )

        color_sets = []
        for attr in get(_M_COLOR_SETS) or []:
            color_sets.append(
                LoopFloatAttributeData(
                    name=attr.get("name") or "Color",
                    set=int(attr.get("set") or 0),
                    width=int(attr.get("width") or 0),
                    values_f32=attr.get("values_f32") or b"",
                )
            )

        point_attrs = []
        for attr in get(_M_POINT_ATTRS) or []:
            point_attrs.append(
                LoopFloatAttributeData(
                    name=attr.get("name") or "assetkit_point_attr",
                    set=int(attr.get("set") or 0),
                    width=int(attr.get("width") or 0),
                    values_f32=attr.get("values_f32") or b"",
                )
            )

        texture_infos = {}
        for role, info in (get(_M_TEXTURE_INFOS) or {}).items():
            texture_infos[str(role)] = TextureRefData(
                role=str(role),
                path=info.get("path") or "",
                image_name=info.get("image_name") or "",
                sampler_name=info.get("sampler_name") or "",
                color_space=info.get("color_space") or "",
                channels=info.get("channels") or "",
                texcoord=info.get("texcoord") or "",
                coord_input_name=info.get("coord_input_name") or "",
                slot=int(info.get("slot") or 0),
                wrap_s=int(info.get("wrap_s") or 1),
                wrap_t=int(info.get("wrap_t") or 1),
                wrap_p=int(info.get("wrap_p") or 1),
                min_filter=int(info.get("min_filter") or 0),
                mag_filter=int(info.get("mag_filter") or 0),
                mip_filter=int(info.get("mip_filter") or 0),
                has_transform=bool(info.get("has_transform")),
                transform_offset=tuple(info.get("transform_offset") or (0.0, 0.0)),
                transform_scale=tuple(info.get("transform_scale") or (1.0, 1.0)),
                transform_rotation=float(
                    info.get("transform_rotation")
                    if info.get("transform_rotation") is not None
                    else 0.0
                ),
                transform_slot=int(info.get("transform_slot") if info.get("transform_slot") is not None else -1),
                texture_extra=info.get("texture_extra"),
                texref_extra=info.get("texref_extra"),
                image_extra=info.get("image_extra"),
                sampler_extra=info.get("sampler_extra"),
            )

        morph_targets = []
        for target in get(_M_MORPH_TARGETS) or []:
            morph_targets.append(
                MorphTargetData(
                    name=target.get("name") or "AssetKitMorph",
                    weight=float(target.get("weight") if target.get("weight") is not None else 0.0),
                    vertex_count=int(target.get("vertex_count") or 0),
                    positions_f32=target.get("positions_f32") or b"",
                )
            )

        data = MeshPrimitiveData(
            get(_M_NAME) or "AssetKitMesh",
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
            _EMPTY_SEQUENCE,
        )
        data.vertex_count = int(get(_M_VERTEX_COUNT) or 0)
        data.loop_count = int(get(_M_LOOP_COUNT) or 0)
        data.face_count = int(get(_M_FACE_COUNT) or 0)
        data.edge_count = int(get(_M_EDGE_COUNT) or 0)
        data.primitive_type = int(get(_M_PRIMITIVE_TYPE) or AK_PRIMITIVE_TRIANGLES)
        data.primitive_mode = int(get(_M_PRIMITIVE_MODE) or 0)
        data.vertices_f32 = get(_M_VERTICES_F32) or b""
        data.indices_u32 = get(_M_INDICES_U32) or b""
        data.edges_u32 = get(_M_EDGES_U32) or b""
        data.loop_starts_i32 = get(_M_LOOP_STARTS_I32) or b""
        data.loop_totals_i32 = get(_M_LOOP_TOTALS_I32) or b""
        data.normals_f32 = get(_M_NORMALS_F32) or b""
        data.vertex_normals_f32 = get(_M_VERTEX_NORMALS_F32) or b""
        data.uvs_f32 = get(_M_UVS_F32) or b""
        data.colors_f32 = get(_M_COLORS_F32) or b""
        data.tangents_f32 = get(_M_TANGENTS_F32) or b""
        data.skin_joints_u16 = get(_M_SKIN_JOINTS_U16) or b""
        data.skin_weights_f32 = get(_M_SKIN_WEIGHTS_F32) or b""
        data.skin_joint_nodes_i32 = get(_M_SKIN_JOINT_NODES_I32) or b""
        data.skin_inverse_bind_matrices_f32 = get(_M_SKIN_INVERSE_BIND_MATRICES_F32) or b""
        data.skin_bind_shape_matrix_f32 = get(_M_SKIN_BIND_SHAPE_MATRIX_F32) or b""
        data.skin_pose_anim_channels = get(_M_SKIN_POSE_ANIM_CHANNELS) or []
        data.anim_channels = get(_M_ANIM_CHANNELS) or []
        data.uv_sets = uv_sets
        data.color_sets = color_sets
        data.point_attrs = point_attrs
        data.texture_infos = texture_infos
        data.morph_targets = morph_targets
        data.morph_presets = get(_M_MORPH_PRESETS) or []
        data.material_variants = get(_M_MATERIAL_VARIANTS) or []
        data.morph_anim_channels = get(_M_MORPH_ANIM_CHANNELS) or []
        data.material_anim_channels = get(_M_MATERIAL_ANIM_CHANNELS) or []
        data.object_name = get(_M_OBJECT_NAME) or ""
        data.matrix_f32 = get(_M_MATRIX_F32) or b""
        data.coord_matrix_f32 = get(_M_COORD_MATRIX_F32) or b""
        data.instance_matrices_f32 = get(_M_INSTANCE_MATRICES_F32) or b""
        node_index = get(_M_NODE_INDEX)
        data.node_index = int(node_index if node_index is not None else -1)
        data.instance_count = int(get(_M_INSTANCE_COUNT) or 0)
        data.has_node = bool(get(_M_HAS_NODE))
        data.has_gsplat = bool(get(_M_HAS_GSPLAT))
        data.gsplat_kernel = int(get(_M_GSPLAT_KERNEL) or 0)
        data.gsplat_color_space = int(get(_M_GSPLAT_COLOR_SPACE) or 0)
        data.gsplat_projection = int(get(_M_GSPLAT_PROJECTION) or 0)
        data.gsplat_sorting_method = int(get(_M_GSPLAT_SORTING_METHOD) or 0)
        data.gsplat_decoded_count = int(get(_M_GSPLAT_DECODED_COUNT) or 0)
        data.has_skin = bool(get(_M_HAS_SKIN))
        data.anim_count = int(get(_M_ANIM_COUNT) or 0)
        data.morph_target_count = int(get(_M_MORPH_TARGET_COUNT) or 0)
        data.morph_preset_count = int(get(_M_MORPH_PRESET_COUNT) or 0)
        data.morph_anim_count = int(get(_M_MORPH_ANIM_COUNT) or 0)
        data.material_anim_count = int(get(_M_MATERIAL_ANIM_COUNT) or 0)
        data.material_variant_count = int(get(_M_MATERIAL_VARIANT_COUNT) or 0)
        data.primitive_extra = get(_M_PRIMITIVE_EXTRA)
        data.mesh_extra = get(_M_MESH_EXTRA)
        data.geometry_extra = get(_M_GEOMETRY_EXTRA)
        data.material_extra = get(_M_MATERIAL_EXTRA)
        data.source_extra = get(_M_SOURCE_EXTRA)
        data.skin_vertex_count = int(get(_M_SKIN_VERTEX_COUNT) or 0)
        data.skin_joint_count = int(get(_M_SKIN_JOINT_COUNT) or 0)
        data.skin_joint_width = int(get(_M_SKIN_JOINT_WIDTH) or 0)
        data.uv_set_count = int(get(_M_UV_SET_COUNT) or 0)
        data.color_set_count = int(get(_M_COLOR_SET_COUNT) or 0)
        data.point_attr_count = int(get(_M_POINT_ATTR_COUNT) or 0)
        skin_root_node_index = get(_M_SKIN_ROOT_NODE_INDEX)
        data.skin_root_node_index = int(skin_root_node_index if skin_root_node_index is not None else -1)
        data.material_name = get(_M_MATERIAL_NAME) or ""
        data.base_color = tuple(get(_M_BASE_COLOR) or (1.0, 1.0, 1.0, 1.0))
        data.transparent_color = tuple(get(_M_TRANSPARENT_COLOR) or (1.0, 1.0, 1.0, 1.0))
        data.emissive_color = tuple(get(_M_EMISSIVE_COLOR) or (0.0, 0.0, 0.0))
        data.specular_color = tuple(get(_M_SPECULAR_COLOR) or (1.0, 1.0, 1.0))
        data.sheen_color = tuple(get(_M_SHEEN_COLOR) or (0.0, 0.0, 0.0))
        data.volume_attenuation_color = tuple(get(_M_VOLUME_ATTENUATION_COLOR) or (1.0, 1.0, 1.0))
        data.volume_scatter_color = tuple(get(_M_VOLUME_SCATTER_COLOR) or (0.0, 0.0, 0.0))
        data.diffuse_transmission_color = tuple(get(_M_DIFFUSE_TRANSMISSION_COLOR) or (1.0, 1.0, 1.0))
        metallic = get(_M_METALLIC)
        roughness = get(_M_ROUGHNESS)
        alpha_cutoff = get(_M_ALPHA_CUTOFF)
        transparent_amount = get(_M_TRANSPARENT_AMOUNT)
        opacity = get(_M_OPACITY)
        normal_scale = get(_M_NORMAL_SCALE)
        occlusion_strength = get(_M_OCCLUSION_STRENGTH)
        emissive_strength = get(_M_EMISSIVE_STRENGTH)
        specular_strength = get(_M_SPECULAR_STRENGTH)
        ior = get(_M_IOR)
        clearcoat = get(_M_CLEARCOAT)
        clearcoat_roughness = get(_M_CLEARCOAT_ROUGHNESS)
        clearcoat_normal_scale = get(_M_CLEARCOAT_NORMAL_SCALE)
        transmission = get(_M_TRANSMISSION)
        sheen_roughness = get(_M_SHEEN_ROUGHNESS)
        iridescence = get(_M_IRIDESCENCE)
        iridescence_ior = get(_M_IRIDESCENCE_IOR)
        iridescence_thickness_minimum = get(_M_IRIDESCENCE_THICKNESS_MINIMUM)
        iridescence_thickness_maximum = get(_M_IRIDESCENCE_THICKNESS_MAXIMUM)
        volume_thickness = get(_M_VOLUME_THICKNESS)
        volume_attenuation_distance = get(_M_VOLUME_ATTENUATION_DISTANCE)
        volume_scatter_anisotropy = get(_M_VOLUME_SCATTER_ANISOTROPY)
        anisotropy = get(_M_ANISOTROPY)
        anisotropy_rotation = get(_M_ANISOTROPY_ROTATION)
        diffuse_transmission = get(_M_DIFFUSE_TRANSMISSION)
        dispersion = get(_M_DISPERSION)
        data.metallic = float(metallic if metallic is not None else 1.0)
        data.roughness = float(roughness if roughness is not None else 1.0)
        data.alpha_cutoff = float(alpha_cutoff if alpha_cutoff is not None else 0.5)
        data.transparent_amount = float(transparent_amount if transparent_amount is not None else 1.0)
        data.opacity = float(opacity if opacity is not None else 1.0)
        data.normal_scale = float(normal_scale if normal_scale is not None else 1.0)
        data.occlusion_strength = float(occlusion_strength if occlusion_strength is not None else 1.0)
        data.emissive_strength = float(emissive_strength if emissive_strength is not None else 1.0)
        data.specular_strength = float(specular_strength if specular_strength is not None else 1.0)
        data.ior = float(ior if ior is not None else 1.5)
        data.clearcoat = float(clearcoat if clearcoat is not None else 0.0)
        data.clearcoat_roughness = float(clearcoat_roughness if clearcoat_roughness is not None else 0.0)
        data.clearcoat_normal_scale = float(clearcoat_normal_scale if clearcoat_normal_scale is not None else 1.0)
        data.transmission = float(transmission if transmission is not None else 0.0)
        data.sheen_roughness = float(sheen_roughness if sheen_roughness is not None else 0.0)
        data.iridescence = float(iridescence if iridescence is not None else 0.0)
        data.iridescence_ior = float(iridescence_ior if iridescence_ior is not None else 1.3)
        data.iridescence_thickness_minimum = float(
            iridescence_thickness_minimum if iridescence_thickness_minimum is not None else 100.0
        )
        data.iridescence_thickness_maximum = float(
            iridescence_thickness_maximum if iridescence_thickness_maximum is not None else 400.0
        )
        data.volume_thickness = float(volume_thickness if volume_thickness is not None else 0.0)
        data.volume_attenuation_distance = float(
            volume_attenuation_distance if volume_attenuation_distance is not None else float("inf")
        )
        data.volume_scatter_anisotropy = float(
            volume_scatter_anisotropy if volume_scatter_anisotropy is not None else 0.0
        )
        data.anisotropy = float(anisotropy if anisotropy is not None else 0.0)
        data.anisotropy_rotation = float(anisotropy_rotation if anisotropy_rotation is not None else 0.0)
        data.diffuse_transmission = float(diffuse_transmission if diffuse_transmission is not None else 0.0)
        data.dispersion = float(dispersion if dispersion is not None else 0.0)
        data.alpha_mode = int(get(_M_ALPHA_MODE) or 0)
        data.transparent_inverted = bool(get(_M_TRANSPARENT_INVERTED))
        data.double_sided = bool(get(_M_DOUBLE_SIDED))
        data.has_sheen = bool(get(_M_HAS_SHEEN))
        data.skin_mesh_in_bind_pose = bool(get(_M_SKIN_MESH_IN_BIND_POSE))
        data.material_type = int(get(_M_MATERIAL_TYPE) or 0)
        data.file_type = int(get(_M_FILE_TYPE) or 0)
        data.mesh_key = int(get(_M_MESH_KEY) or 0)
        data.material_key = int(get(_M_MATERIAL_KEY) or 0)
        data.primitive_index = int(get(_M_PRIMITIVE_INDEX) or 0)
        data.zero_copy_flags = int(get(_M_ZERO_COPY_FLAGS) or 0)
        data.geometry_key = int(get(_M_GEOMETRY_KEY) or 0)
        data.smooth_shading = bool(get(_M_SMOOTH_SHADING))
        data.base_color_texture = get(_M_BASE_COLOR_TEXTURE) or ""
        data.metallic_roughness_texture = get(_M_METALLIC_ROUGHNESS_TEXTURE) or ""
        data.occlusion_texture = get(_M_OCCLUSION_TEXTURE) or ""
        data.normal_texture = get(_M_NORMAL_TEXTURE) or ""
        data.emissive_texture = get(_M_EMISSIVE_TEXTURE) or ""
        data.transparent_texture = get(_M_TRANSPARENT_TEXTURE) or ""
        data.specular_texture = get(_M_SPECULAR_TEXTURE) or ""
        data.specular_color_texture = get(_M_SPECULAR_COLOR_TEXTURE) or ""
        data.clearcoat_texture = get(_M_CLEARCOAT_TEXTURE) or ""
        data.clearcoat_roughness_texture = get(_M_CLEARCOAT_ROUGHNESS_TEXTURE) or ""
        data.clearcoat_normal_texture = get(_M_CLEARCOAT_NORMAL_TEXTURE) or ""
        data.transmission_texture = get(_M_TRANSMISSION_TEXTURE) or ""
        data.sheen_color_texture = get(_M_SHEEN_COLOR_TEXTURE) or ""
        data.sheen_roughness_texture = get(_M_SHEEN_ROUGHNESS_TEXTURE) or ""
        data.iridescence_texture = get(_M_IRIDESCENCE_TEXTURE) or ""
        data.iridescence_thickness_texture = get(_M_IRIDESCENCE_THICKNESS_TEXTURE) or ""
        data.volume_thickness_texture = get(_M_VOLUME_THICKNESS_TEXTURE) or ""
        data.anisotropy_texture = get(_M_ANISOTROPY_TEXTURE) or ""
        data.diffuse_transmission_texture = get(_M_DIFFUSE_TRANSMISSION_TEXTURE) or ""
        data.diffuse_transmission_color_texture = get(_M_DIFFUSE_TRANSMISSION_COLOR_TEXTURE) or ""
        data._native_owner = get(_M_OWNER)
        meshes.append(data)
    return meshes
