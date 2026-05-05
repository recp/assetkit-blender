from __future__ import annotations

import ctypes
import ctypes.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

AK_OK = 0
AK_FILE_TYPE_AUTO = 0
AK_GEOMETRY_MESH = 1
AK_PRIMITIVE_TRIANGLES = 3
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


class AkUIntArray(ctypes.Structure):
    _fields_ = [("count", ctypes.c_size_t)]


class AkBuffer(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("length", ctypes.c_size_t),
    ]


class AkAccessor(ctypes.Structure):
    _fields_ = [
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
    ("index", ctypes.c_uint32),
    ("isIndexed", ctypes.c_bool),
    ("semantic", ctypes.c_int32),
    ("offset", ctypes.c_uint32),
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
    ("input", ctypes.POINTER(AkInput)),
    ("pos", ctypes.POINTER(AkInput)),
    ("indices", ctypes.POINTER(AkUIntArray)),
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
    ("base", AkOneWayIterBase),
    ("name", ctypes.c_char_p),
    ("gdata", ctypes.POINTER(AkObject)),
    ("extra", ctypes.c_void_p),
    ("materialMap", ctypes.c_void_p),
    ("bbox", ctypes.c_void_p),
]


class AkLibrary(ctypes.Structure):
    pass


AkLibrary._fields_ = [
    ("next", ctypes.POINTER(AkLibrary)),
    ("name", ctypes.c_char_p),
    ("extra", ctypes.c_void_p),
    ("chld", ctypes.c_void_p),
    ("count", ctypes.c_uint64),
]


class AkLibraries(ctypes.Structure):
    _fields_ = [
        ("cameras", ctypes.c_void_p),
        ("lights", ctypes.c_void_p),
        ("effects", ctypes.c_void_p),
        ("libimages", ctypes.c_void_p),
        ("materials", ctypes.c_void_p),
        ("geometries", ctypes.POINTER(AkLibrary)),
        ("controllers", ctypes.c_void_p),
        ("visualScenes", ctypes.c_void_p),
        ("nodes", ctypes.c_void_p),
        ("animations", ctypes.c_void_p),
        ("buffers", ctypes.c_void_p),
        ("accessors", ctypes.c_void_p),
        ("textures", ctypes.c_void_p),
        ("samplers", ctypes.c_void_p),
        ("images", ctypes.c_void_p),
        ("morphs", ctypes.c_void_p),
        ("skins", ctypes.c_void_p),
    ]


class AkScene(ctypes.Structure):
    _fields_ = [("visualScene", ctypes.c_void_p), ("extra", ctypes.c_void_p)]


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
    ]


@dataclass
class MorphTargetData:
    name: str
    weight: float = 0.0
    vertex_count: int = 0
    positions_f32: object = b""


@dataclass
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
    vertices_f32: object = b""
    indices_u32: object = b""
    loop_starts_i32: object = b""
    loop_totals_i32: object = b""
    normals_f32: object = b""
    uvs_f32: object = b""
    skin_joints_u16: object = b""
    skin_weights_f32: object = b""
    skin_joint_nodes_i32: object = b""
    skin_inverse_bind_matrices_f32: object = b""
    anim_channels: list[dict] | None = None
    morph_targets: list[MorphTargetData] | None = None
    morph_anim_channels: list[dict] | None = None
    object_name: str = ""
    matrix_f32: object = b""
    coord_matrix_f32: object = b""
    node_index: int = -1
    has_node: bool = False
    has_skin: bool = False
    anim_count: int = 0
    morph_target_count: int = 0
    morph_anim_count: int = 0
    skin_vertex_count: int = 0
    skin_joint_count: int = 0
    skin_joint_width: int = 0
    skin_root_node_index: int = -1
    material_name: str = ""
    base_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    emissive_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metallic: float = 1.0
    roughness: float = 1.0
    alpha_cutoff: float = 0.5
    normal_scale: float = 1.0
    alpha_mode: int = 0
    double_sided: bool = False
    zero_copy_flags: int = 0
    base_color_texture: str = ""
    metallic_roughness_texture: str = ""
    normal_texture: str = ""
    emissive_texture: str = ""
    _native_owner: object | None = None


@dataclass
class SceneNodeData:
    name: str
    parent_index: int = -1
    matrix_f32: object = b""
    anim_channels: list[dict] | None = None
    anim_count: int = 0
    camera_type: int = 0
    camera_name: str = ""
    camera_values: tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    light_type: int = 0
    light_name: str = ""
    light_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    light_values: tuple[float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0)
    _native_owner: object | None = None


@dataclass
class AssetKitSceneData:
    meshes: list[MeshPrimitiveData]
    nodes: list[SceneNodeData]


class AssetKitError(RuntimeError):
    pass


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
        lib = doc.lib.geometries
        while lib:
            geom_ptr = ctypes.cast(lib.contents.chld, ctypes.POINTER(AkGeometry))
            while geom_ptr:
                geom = geom_ptr.contents
                gdata = geom.gdata
                if gdata and gdata.contents.type == AK_GEOMETRY_MESH:
                    mesh_ptr = ctypes.cast(gdata.contents.pData, ctypes.POINTER(AkMesh))
                    yield from self._mesh_primitives(geom, mesh_ptr.contents)
                geom_ptr = ctypes.cast(geom.base.next, ctypes.POINTER(AkGeometry))
            lib = lib.contents.next

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
        raw_indices = self._indices(prim.indices)
        if raw_indices:
            stride = max(1, int(prim.indexStride or 1))
            pos_offset = int(pos_input.contents.offset or 0)
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
            offset = int(inp.contents.offset or 0)
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

    @staticmethod
    def _indices(indices: ctypes.POINTER(AkUIntArray)) -> list[int]:
        if not indices:
            return []
        count = int(indices.contents.count)
        if count <= 0:
            return []
        data_addr = ctypes.addressof(indices.contents) + ctypes.sizeof(ctypes.c_size_t)
        array_type = ctypes.c_uint32 * count
        return list(ctypes.cast(data_addr, ctypes.POINTER(array_type)).contents)


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


def native_load_meshes(
    filepath: str | os.PathLike[str],
    options: dict | None = None,
) -> AssetKitSceneData | None:
    try:
        from . import _assetkit_blender
    except ImportError:
        return None

    result = _assetkit_blender.load_meshes(os.fspath(filepath), options or None)
    raw_meshes = result.get("meshes", []) if isinstance(result, dict) else result
    raw_nodes = result.get("nodes", []) if isinstance(result, dict) else []

    nodes = []
    for item in raw_nodes:
        nodes.append(
            SceneNodeData(
                name=item.get("name") or "AssetKitNode",
                parent_index=int(item.get("parent_index") if item.get("parent_index") is not None else -1),
                matrix_f32=item.get("matrix_f32") or b"",
                anim_channels=item.get("anim_channels") or [],
                anim_count=int(item.get("anim_count") or 0),
                camera_type=int(item.get("camera_type") or 0),
                camera_name=item.get("camera_name") or "",
                camera_values=tuple(item.get("camera_values") or (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
                light_type=int(item.get("light_type") or 0),
                light_name=item.get("light_name") or "",
                light_color=tuple(item.get("light_color") or (1.0, 1.0, 1.0)),
                light_values=tuple(item.get("light_values") or (0.0, 0.0, 0.0, 0.0, 0.0)),
                _native_owner=item.get("_owner"),
            )
        )

    meshes = []
    for item in raw_meshes:
        morph_targets = []
        for target in item.get("morph_targets") or []:
            morph_targets.append(
                MorphTargetData(
                    name=target.get("name") or "AssetKitMorph",
                    weight=float(target.get("weight") if target.get("weight") is not None else 0.0),
                    vertex_count=int(target.get("vertex_count") or 0),
                    positions_f32=target.get("positions_f32") or b"",
                )
            )

        meshes.append(
            MeshPrimitiveData(
                name=item.get("name") or "AssetKitMesh",
                vertices=[],
                faces=[],
                normals=[],
                uvs=[],
                loop_vertex_indices=[],
                vertex_count=int(item.get("vertex_count") or 0),
                loop_count=int(item.get("loop_count") or 0),
                face_count=int(item.get("face_count") or 0),
                vertices_f32=item.get("vertices_f32") or b"",
                indices_u32=item.get("indices_u32") or b"",
                loop_starts_i32=item.get("loop_starts_i32") or b"",
                loop_totals_i32=item.get("loop_totals_i32") or b"",
                normals_f32=item.get("normals_f32") or b"",
                uvs_f32=item.get("uvs_f32") or b"",
                skin_joints_u16=item.get("skin_joints_u16") or b"",
                skin_weights_f32=item.get("skin_weights_f32") or b"",
                skin_joint_nodes_i32=item.get("skin_joint_nodes_i32") or b"",
                skin_inverse_bind_matrices_f32=item.get("skin_inverse_bind_matrices_f32") or b"",
                anim_channels=item.get("anim_channels") or [],
                morph_targets=morph_targets,
                morph_anim_channels=item.get("morph_anim_channels") or [],
                object_name=item.get("object_name") or "",
                matrix_f32=item.get("matrix_f32") or b"",
                coord_matrix_f32=item.get("coord_matrix_f32") or b"",
                node_index=int(item.get("node_index") if item.get("node_index") is not None else -1),
                has_node=bool(item.get("has_node")),
                has_skin=bool(item.get("has_skin")),
                anim_count=int(item.get("anim_count") or 0),
                morph_target_count=int(item.get("morph_target_count") or 0),
                morph_anim_count=int(item.get("morph_anim_count") or 0),
                skin_vertex_count=int(item.get("skin_vertex_count") or 0),
                skin_joint_count=int(item.get("skin_joint_count") or 0),
                skin_joint_width=int(item.get("skin_joint_width") or 0),
                skin_root_node_index=int(item.get("skin_root_node_index") if item.get("skin_root_node_index") is not None else -1),
                material_name=item.get("material_name") or "",
                base_color=tuple(item.get("base_color") or (1.0, 1.0, 1.0, 1.0)),
                emissive_color=tuple(item.get("emissive_color") or (0.0, 0.0, 0.0)),
                metallic=float(item.get("metallic") if item.get("metallic") is not None else 1.0),
                roughness=float(item.get("roughness") if item.get("roughness") is not None else 1.0),
                alpha_cutoff=float(item.get("alpha_cutoff") if item.get("alpha_cutoff") is not None else 0.5),
                normal_scale=float(item.get("normal_scale") if item.get("normal_scale") is not None else 1.0),
                alpha_mode=int(item.get("alpha_mode") or 0),
                double_sided=bool(item.get("double_sided")),
                zero_copy_flags=int(item.get("zero_copy_flags") or 0),
                base_color_texture=item.get("base_color_texture") or "",
                metallic_roughness_texture=item.get("metallic_roughness_texture") or "",
                normal_texture=item.get("normal_texture") or "",
                emissive_texture=item.get("emissive_texture") or "",
                _native_owner=item.get("_owner"),
            )
        )
    return AssetKitSceneData(meshes=meshes, nodes=nodes)
