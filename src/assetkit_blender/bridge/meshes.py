from __future__ import annotations

from typing import Iterable

from ..enums import AK_PRIMITIVE_TRIANGLES
from .data import (
    LoopFloatAttributeData,
    MeshPrimitiveData,
    MorphTargetData,
    TextureRefData,
)

_EMPTY_SEQUENCE: tuple = ()

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
    _S_MATERIAL_NAME,
    _S_BASE_COLOR,
    _S_OPACITY,
    _S_ALPHA_MODE,
    _S_ALPHA_CUTOFF,
    _S_TRANSPARENT_AMOUNT,
    _S_TRANSPARENT_COLOR,
    _S_SPECULAR_STRENGTH,
    _S_POINT_ATTR_COUNT,
    _S_POINT_ATTRS,
    _S_TEXTURE_INFOS,
) = range(47)
_S_LEGACY_FIELD_COUNT = _S_GEOMETRY_KEY + 1
_S_FIELD_COUNT = _S_TEXTURE_INFOS + 1

(
    _ST_IMAGE_NAME,
    _ST_SAMPLER_NAME,
    _ST_COLOR_SPACE,
    _ST_CHANNELS,
    _ST_TEXCOORD,
    _ST_COORD_INPUT_NAME,
    _ST_WRAP_S,
    _ST_WRAP_T,
    _ST_WRAP_P,
    _ST_MIN_FILTER,
    _ST_MAG_FILTER,
    _ST_MIP_FILTER,
    _ST_TRANSFORM_SLOT,
) = range(13)


class NativeLoopFloatAttributeData:
    __slots__ = ("_raw",)

    def __init__(self, raw: tuple):
        self._raw = raw

    @property
    def name(self):
        return self._raw[0] or ""

    @property
    def set(self):
        return int(self._raw[1] or 0)

    @property
    def width(self):
        return int(self._raw[2] or 0)

    @property
    def values_f32(self):
        return self._raw[3] or b""


class NativeSimpleMeshData:
    __slots__ = ("_raw", "_count", "_point_attrs", "_texture_infos", "_uv_sets")

    vertices = _EMPTY_SEQUENCE
    faces = _EMPTY_SEQUENCE
    normals = _EMPTY_SEQUENCE
    uvs = _EMPTY_SEQUENCE
    loop_vertex_indices = _EMPTY_SEQUENCE
    uvs_f32 = b""
    colors_f32 = b""
    uv_sets = None
    color_sets = None
    point_attrs = None
    texture_infos = None
    morph_targets = None
    morph_presets = None
    material_variants = None
    skin_pose_anim_channels = None
    anim_channels = None
    morph_anim_channels = None
    material_anim_channels = None
    sharp_faces_u8 = b""
    has_gsplat = False
    gsplat_kernel = 0
    gsplat_color_space = 0
    gsplat_projection = 0
    gsplat_sorting_method = 0
    gsplat_decoded_count = 0
    has_skin = False
    anim_count = 0
    morph_target_count = 0
    morph_preset_count = 0
    morph_anim_count = 0
    material_anim_count = 0
    material_variant_count = 0
    primitive_extra = None
    mesh_extra = None
    geometry_extra = None
    material_extra = None
    skin_vertex_count = 0
    skin_joint_count = 0
    skin_joint_width = 0
    uv_set_count = 0
    color_set_count = 0
    point_attr_count = 0
    skin_root_node_index = -1
    material_name = ""
    base_color = (1.0, 1.0, 1.0, 1.0)
    transparent_color = (1.0, 1.0, 1.0, 1.0)
    emissive_color = (0.0, 0.0, 0.0)
    specular_color = (1.0, 1.0, 1.0)
    sheen_color = (0.0, 0.0, 0.0)
    volume_attenuation_color = (1.0, 1.0, 1.0)
    volume_scatter_color = (0.0, 0.0, 0.0)
    diffuse_transmission_color = (1.0, 1.0, 1.0)
    alpha_cutoff = 0.5
    transparent_amount = 1.0
    opacity = 1.0
    normal_scale = 1.0
    occlusion_strength = 1.0
    emissive_strength = 1.0
    specular_strength = 1.0
    ior = 1.5
    clearcoat = 0.0
    clearcoat_roughness = 0.0
    clearcoat_normal_scale = 1.0
    transmission = 0.0
    sheen_roughness = 0.0
    iridescence = 0.0
    iridescence_ior = 1.3
    iridescence_thickness_minimum = 100.0
    iridescence_thickness_maximum = 400.0
    volume_thickness = 0.0
    volume_attenuation_distance = float("inf")
    volume_scatter_anisotropy = 0.0
    anisotropy = 0.0
    anisotropy_rotation = 0.0
    diffuse_transmission = 0.0
    dispersion = 0.0
    alpha_mode = 0
    transparent_inverted = False
    has_sheen = False
    skin_mesh_in_bind_pose = False
    transparent_texture = ""
    metallic_roughness_texture = ""
    occlusion_texture = ""
    normal_texture = ""
    emissive_texture = ""
    specular_texture = ""
    specular_color_texture = ""
    clearcoat_texture = ""
    clearcoat_roughness_texture = ""
    clearcoat_normal_texture = ""
    transmission_texture = ""
    sheen_color_texture = ""
    sheen_roughness_texture = ""
    iridescence_texture = ""
    iridescence_thickness_texture = ""
    volume_thickness_texture = ""
    anisotropy_texture = ""
    diffuse_transmission_texture = ""
    diffuse_transmission_color_texture = ""
    skin_joints_u16 = b""
    skin_weights_f32 = b""
    skin_joint_nodes_i32 = b""
    skin_inverse_bind_matrices_f32 = b""
    skin_bind_shape_matrix_f32 = b""
    simple_native = True

    def __init__(self, raw: tuple):
        self._raw = raw
        self._count = len(raw)
        self._point_attrs = None
        self._texture_infos = None
        self._uv_sets = None

    def _get(self, index: int, default=None):
        return self._raw[index] if index < self._count and self._raw[index] is not None else default

    @property
    def _native_owner(self):
        return self._raw[_S_OWNER]

    @property
    def name(self):
        return self._get(_S_NAME, "AssetKitMesh") or "AssetKitMesh"

    @property
    def object_name(self):
        return self._get(_S_OBJECT_NAME, "") or ""

    @property
    def vertex_count(self):
        return self._get(_S_VERTEX_COUNT, 0) or 0

    @property
    def loop_count(self):
        return self._get(_S_LOOP_COUNT, 0) or 0

    @property
    def face_count(self):
        return self._get(_S_FACE_COUNT, 0) or 0

    @property
    def edge_count(self):
        return self._get(_S_EDGE_COUNT, 0) or 0

    @property
    def primitive_type(self):
        return self._get(_S_PRIMITIVE_TYPE, AK_PRIMITIVE_TRIANGLES) or AK_PRIMITIVE_TRIANGLES

    @property
    def primitive_mode(self):
        return self._get(_S_PRIMITIVE_MODE, 0) or 0

    @property
    def file_type(self):
        return self._get(_S_FILE_TYPE, 0) or 0

    @property
    def mesh_key(self):
        return self._get(_S_MESH_KEY, 0) or 0

    @property
    def primitive_index(self):
        return self._get(_S_PRIMITIVE_INDEX, 0) or 0

    @property
    def zero_copy_flags(self):
        return self._get(_S_ZERO_COPY_FLAGS, 0) or 0

    @property
    def has_node(self):
        return bool(self._get(_S_HAS_NODE, False))

    @property
    def node_index(self):
        return self._get(_S_NODE_INDEX, -1)

    @property
    def matrix_f32(self):
        return self._get(_S_MATRIX_F32, b"") or b""

    @property
    def coord_matrix_f32(self):
        return self._get(_S_COORD_MATRIX_F32, b"") or b""

    @property
    def instance_count(self):
        return self._get(_S_INSTANCE_COUNT, 0) or 0

    @property
    def instance_matrices_f32(self):
        return self._get(_S_INSTANCE_MATRICES_F32, b"") or b""

    @property
    def vertices_f32(self):
        return self._get(_S_VERTICES_F32, b"") or b""

    @property
    def indices_u32(self):
        return self._get(_S_INDICES_U32, b"") or b""

    @property
    def loop_starts_i32(self):
        return self._get(_S_LOOP_STARTS_I32, b"") or b""

    @property
    def loop_totals_i32(self):
        return self._get(_S_LOOP_TOTALS_I32, b"") or b""

    @property
    def normals_f32(self):
        return self._get(_S_NORMALS_F32, b"") or b""

    @property
    def vertex_normals_f32(self):
        return self._get(_S_VERTEX_NORMALS_F32, b"") or b""

    @property
    def tangents_f32(self):
        return self._get(_S_TANGENTS_F32, b"") or b""

    @property
    def geometry_key(self):
        return self._get(_S_GEOMETRY_KEY, 0) or 0

    @property
    def edges_u32(self):
        return self._get(_S_EDGES_U32, b"") or b""

    @property
    def uvs_f32(self):
        return self._get(_S_UVS_F32, b"") or b""

    @property
    def uv_set_count(self):
        return 1 if self.uvs_f32 else 0

    @property
    def uv_sets(self):
        cached = self._uv_sets
        if cached is not None:
            return cached
        values = self.uvs_f32
        cached = (
            (NativeLoopFloatAttributeData(("UVMap", 0, 2, values)),)
            if values
            else ()
        )
        self._uv_sets = cached
        return cached

    @property
    def base_color_texture(self):
        return self._get(_S_BASE_COLOR_TEXTURE, "") or ""

    @property
    def material_type(self):
        return self._get(_S_MATERIAL_TYPE, 0) or 0

    @property
    def material_key(self):
        return self._get(_S_MATERIAL_KEY, 0) or 0

    @property
    def material_name(self):
        return self._get(_S_MATERIAL_NAME, "") or ""

    @property
    def base_color(self):
        return self._get(_S_BASE_COLOR, (1.0, 1.0, 1.0, 1.0)) or (1.0, 1.0, 1.0, 1.0)

    @property
    def opacity(self):
        return self._get(_S_OPACITY, 1.0)

    @property
    def alpha_mode(self):
        return self._get(_S_ALPHA_MODE, 0) or 0

    @property
    def alpha_cutoff(self):
        return self._get(_S_ALPHA_CUTOFF, 0.5)

    @property
    def transparent_amount(self):
        return self._get(_S_TRANSPARENT_AMOUNT, 1.0)

    @property
    def transparent_color(self):
        return self._get(
            _S_TRANSPARENT_COLOR,
            (1.0, 1.0, 1.0, 1.0),
        ) or (1.0, 1.0, 1.0, 1.0)

    @property
    def specular_strength(self):
        return self._get(_S_SPECULAR_STRENGTH, 1.0)

    @property
    def point_attr_count(self):
        return self._get(_S_POINT_ATTR_COUNT, 0) or 0

    @property
    def point_attrs(self):
        cached = self._point_attrs
        if cached is not None:
            return cached
        cached = tuple(
            NativeLoopFloatAttributeData(item)
            for item in (self._get(_S_POINT_ATTRS, ()) or ())
        )
        self._point_attrs = cached
        return cached

    @property
    def texture_infos(self):
        cached = self._texture_infos
        if cached is not None:
            return cached
        raw_infos = self._get(_S_TEXTURE_INFOS, {}) or {}
        if isinstance(raw_infos, tuple):
            cached = _native_simple_texture_info_from_raw(
                self.base_color_texture,
                raw_infos,
            )
        else:
            cached = _native_texture_infos_from_raw(raw_infos)
        self._texture_infos = cached
        return cached

    @property
    def metallic(self):
        return self._get(_S_METALLIC, 1.0)

    @property
    def roughness(self):
        return self._get(_S_ROUGHNESS, 1.0)

    @property
    def double_sided(self):
        return bool(self._get(_S_DOUBLE_SIDED, False))

    @property
    def smooth_shading(self):
        return bool(self._get(_S_SMOOTH_SHADING, False))


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
) = range(133)

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
        return NativeSimpleMeshData(item)

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
    data.material_name = get("material_name") or ""
    data.base_color = tuple(get("base_color") or (1.0, 1.0, 1.0, 1.0))
    opacity = get("opacity")
    data.opacity = float(opacity if opacity is not None else 1.0)
    data.alpha_mode = int(get("alpha_mode") or 0)
    data.material_type = int(get("material_type") or 0)
    data.material_key = int(get("material_key") or 0)
    metallic = get("metallic")
    roughness = get("roughness")
    data.metallic = float(metallic if metallic is not None else 1.0)
    data.roughness = float(roughness if roughness is not None else 1.0)
    data.double_sided = bool(get("double_sided"))
    data.primitive_index = int(get("primitive_index") or 0)
    data.zero_copy_flags = int(get("zero_copy_flags") or 0)
    data.geometry_key = int(get("geometry_key") or 0)
    data.smooth_shading = bool(get("smooth_shading"))
    data.simple_native = True
    data._native_owner = get("_owner")
    return data


def _native_texture_infos_from_raw(
    raw_infos: dict[str, dict],
) -> dict[str, TextureRefData]:
    texture_infos = {}
    for role, info in raw_infos.items():
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
            transform_slot=int(
                info.get("transform_slot")
                if info.get("transform_slot") is not None
                else -1
            ),
            texture_extra=info.get("texture_extra"),
            texref_extra=info.get("texref_extra"),
            image_extra=info.get("image_extra"),
            sampler_extra=info.get("sampler_extra"),
        )
    return texture_infos


def _native_simple_texture_info_from_raw(
    path: str,
    raw_info: tuple,
) -> dict[str, TextureRefData]:
    if not raw_info:
        return {}
    info = TextureRefData(
        role="base_color",
        path=path or "",
        image_name=raw_info[_ST_IMAGE_NAME] or "",
        sampler_name=raw_info[_ST_SAMPLER_NAME] or "",
        color_space=raw_info[_ST_COLOR_SPACE] or "",
        channels=raw_info[_ST_CHANNELS] or "",
        texcoord=raw_info[_ST_TEXCOORD] or "",
        coord_input_name=raw_info[_ST_COORD_INPUT_NAME] or "",
        slot=0,
        wrap_s=int(
            raw_info[_ST_WRAP_S] if raw_info[_ST_WRAP_S] is not None else 1
        ),
        wrap_t=int(
            raw_info[_ST_WRAP_T] if raw_info[_ST_WRAP_T] is not None else 1
        ),
        wrap_p=int(
            raw_info[_ST_WRAP_P] if raw_info[_ST_WRAP_P] is not None else 1
        ),
        min_filter=int(raw_info[_ST_MIN_FILTER] or 0),
        mag_filter=int(raw_info[_ST_MAG_FILTER] or 0),
        mip_filter=int(raw_info[_ST_MIP_FILTER] or 0),
        has_transform=False,
        transform_slot=int(
            raw_info[_ST_TRANSFORM_SLOT]
            if raw_info[_ST_TRANSFORM_SLOT] is not None
            else -1
        ),
    )
    return {"base_color": info}


def meshes_from_raw(raw_meshes: Iterable[dict]) -> list[MeshPrimitiveData]:
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

        texture_infos = _native_texture_infos_from_raw(
            get(_M_TEXTURE_INFOS) or {}
        )

        morph_targets = []
        for target in get(_M_MORPH_TARGETS) or []:
            morph_targets.append(
                MorphTargetData(
                    name=target.get("name") or "",
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
