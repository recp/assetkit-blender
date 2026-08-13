from __future__ import annotations

from dataclasses import dataclass

from ..enums import AK_PRIMITIVE_TRIANGLES


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
    min_filter: int = 6
    mag_filter: int = 2
    mip_filter: int = 3
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
    skin_vertex_count: int = 0
    skin_joint_count: int = 0
    skin_joint_width: int = 0
    uv_set_count: int = 0
    color_set_count: int = 0
    point_attr_count: int = 0
    skin_root_node_index: int = -1
    material_name: str = ""
    base_color: tuple[float, float, float, float] = (
        1.0,
        1.0,
        1.0,
        1.0,
    )
    transparent_color: tuple[float, float, float, float] = (
        1.0,
        1.0,
        1.0,
        1.0,
    )
    emissive_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    specular_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    sheen_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    volume_attenuation_color: tuple[float, float, float] = (
        1.0,
        1.0,
        1.0,
    )
    volume_scatter_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    diffuse_transmission_color: tuple[float, float, float] = (
        1.0,
        1.0,
        1.0,
    )
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
class CurveData:
    name: str = "AssetKit Curve"
    object_name: str = ""
    kind: int = 1
    point_count: int = 0
    degree: int = 1
    closed: bool = False
    has_node: bool = False
    node_index: int = -1
    matrix_f32: object = b""
    coord_matrix_f32: object = b""
    points_f32: object = b""
    geometry_extra: object | None = None
    curve_extra: object | None = None
    _native_owner: object | None = None


@dataclass(slots=True)
class SceneNodeData:
    name: str
    parent_index: int = -1
    prototype_root_index: int = -1
    instance_target_index: int = -1
    matrix_f32: object = b""
    world_matrix_f32: object = b""
    anim_channels: list[object] | None = None
    anim_count: int = 0
    visible: bool = True
    layers: list[str] | None = None
    camera_type: int = 0
    camera_name: str = ""
    camera_values: tuple[float, float, float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    )
    camera_extra: object | None = None
    camera_imager_extra: object | None = None
    light_type: int = 0
    light_name: str = ""
    light_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    light_values: tuple[float, ...] = (
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        2.0,
        1.0,
        0.0,
        0.0,
        0.0,
    )
    light_extra: object | None = None
    extra: object | None = None
    _native_owner: object | None = None


@dataclass(slots=True)
class AssetKitSceneData:
    meshes: list[MeshPrimitiveData]
    nodes: list[SceneNodeData]
    curves: list[CurveData] | None = None
    doc_extra: object | None = None
    scene_extra: object | None = None
    images: list[dict] | None = None
    scene_index: int = -1
    scene_count: int = 0
    scene_name: str = ""
    scene_names: list[str] | None = None
    scene_bounds: (
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
        ]
        | None
    ) = None
