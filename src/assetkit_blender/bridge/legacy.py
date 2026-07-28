from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Iterator, Optional

from ..enums import (
    AK_FILE_TYPE_AUTO,
    AK_GEOMETRY_MESH,
    AK_INPUT_NORMAL,
    AK_INPUT_POSITION,
    AK_INPUT_TEXCOORD,
    AK_INPUT_UV,
    AK_OK,
    AK_PRIMITIVE_TRIANGLES,
    AKT_BYTE,
    AKT_DOUBLE,
    AKT_FLOAT,
    AKT_INT,
    AKT_INT64,
    AKT_SHORT,
    AKT_UBYTE,
    AKT_UINT,
    AKT_UINT64,
    AKT_USHORT,
)
from .abi import (
    AkAccessor,
    AkDoc,
    AkGeometry,
    AkIndexArray,
    AkInput,
    AkMesh,
    AkMeshPrimitive,
)
from .data import MeshPrimitiveData
from .runtime import AssetKitError


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
        data_addr = ctypes.addressof(item) + AkIndexArray.padding.offset + ctypes.sizeof(ctypes.c_uint32)
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
    package_root = Path(__file__).resolve().parents[2]
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
