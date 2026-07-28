from __future__ import annotations

import ctypes


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
        ("padding", ctypes.c_uint32),
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
    ("flags", ctypes.c_uint32),
    ("indexStride", ctypes.c_uint32),
    ("reserved", ctypes.c_void_p),
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


class AkScene(ctypes.Structure):
    pass


class AkSceneCamera(ctypes.Structure):
    pass


AkSceneCamera._fields_ = [
    ("next", ctypes.POINTER(AkSceneCamera)),
    ("camera", ctypes.c_void_p),
    ("firstInstance", ctypes.c_void_p),
    ("useCount", ctypes.c_uint32),
]


class AkSceneLight(ctypes.Structure):
    pass


AkSceneLight._fields_ = [
    ("next", ctypes.POINTER(AkSceneLight)),
    ("light", ctypes.c_void_p),
    ("firstInstance", ctypes.c_void_p),
    ("useCount", ctypes.c_uint32),
]


class AkSceneCameraList(ctypes.Structure):
    _fields_ = [
        ("first", ctypes.POINTER(AkSceneCamera)),
        ("last", ctypes.POINTER(AkSceneCamera)),
        ("count", ctypes.c_uint32),
        ("useCount", ctypes.c_uint32),
    ]


class AkSceneLightList(ctypes.Structure):
    _fields_ = [
        ("first", ctypes.POINTER(AkSceneLight)),
        ("last", ctypes.POINTER(AkSceneLight)),
        ("count", ctypes.c_uint32),
        ("useCount", ctypes.c_uint32),
    ]


AkScene._fields_ = [
    ("next", ctypes.POINTER(AkScene)),
    ("name", ctypes.c_char_p),
    ("node", ctypes.c_void_p),
    ("firstCamNode", ctypes.c_void_p),
    ("cameras", AkSceneCameraList),
    ("lights", AkSceneLightList),
    ("bbox", ctypes.c_void_p),
    ("extra", ctypes.c_void_p),
]


class AkLibraries(ctypes.Structure):
    _fields_ = [
        ("cameras", AkGenericLib),
        ("lights", AkGenericLib),
        ("materials", AkGenericLib),
        ("geometries", AkGeometryLib),
        ("scenes", AkGenericLib),
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
        ("scene", ctypes.POINTER(AkScene)),
        ("materialVariants", ctypes.c_void_p),
        ("materialVariantCount", ctypes.c_uint32),
        ("materialProperties", AkMaterialPropertyRegistry),
    ]
