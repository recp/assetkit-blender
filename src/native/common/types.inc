#define AKB_GEOMETRY_MESH AK_GEOMETRY_MESH
#define AKB_GEOMETRY_SPLINE AK_GEOMETRY_SPLINE
#define AKB_GEOMETRY_BREP AK_GEOMETRY_BREP
#define AKB_CURVE_POLY 1
#define AKB_CURVE_NURBS 2
#define AKB_PRIMITIVE_LINES AK_PRIMITIVE_LINES
#define AKB_PRIMITIVE_POLYGONS AK_PRIMITIVE_POLYGONS
#define AKB_PRIMITIVE_TRIANGLES AK_PRIMITIVE_TRIANGLES
#define AKB_PRIMITIVE_POINTS AK_PRIMITIVE_POINTS
#define AKB_INPUT_NORMAL 13
#define AKB_INPUT_POSITION 16
#define AKB_INPUT_TANGENT 17
#define AKB_INPUT_TEXCOORD 19
#define AKB_INPUT_TEXTANGENT 20
#define AKB_INPUT_UV 21
#define AKB_ANIM_TRANSLATION 1
#define AKB_ANIM_ROTATION_QUAT 2
#define AKB_ANIM_SCALE 3
#define AKB_ANIM_MORPH_WEIGHTS 4
#define AKB_ANIM_VISIBILITY 5
#define AKB_ANIM_CAMERA_XFOV 6
#define AKB_ANIM_CAMERA_YFOV 7
#define AKB_ANIM_CAMERA_ZNEAR 8
#define AKB_ANIM_CAMERA_ZFAR 9
#define AKB_ANIM_CAMERA_ORTHO_XMAG 10
#define AKB_ANIM_CAMERA_ORTHO_YMAG 11
#define AKB_ANIM_LIGHT_COLOR 12
#define AKB_ANIM_LIGHT_INTENSITY 13
#define AKB_ANIM_LIGHT_RANGE 14
#define AKB_ANIM_LIGHT_SPOT_INNER 15
#define AKB_ANIM_LIGHT_SPOT_OUTER 16
#define AKB_ANIM_MATERIAL_BASE_COLOR 32
#define AKB_ANIM_MATERIAL_METALLIC 33
#define AKB_ANIM_MATERIAL_ROUGHNESS 34
#define AKB_ANIM_MATERIAL_ALPHA_CUTOFF 35
#define AKB_ANIM_MATERIAL_EMISSIVE_COLOR 36
#define AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH 37
#define AKB_ANIM_MATERIAL_NORMAL_SCALE 38
#define AKB_ANIM_MATERIAL_OCCLUSION_STRENGTH 39
#define AKB_ANIM_MATERIAL_SPECULAR 40
#define AKB_ANIM_MATERIAL_SPECULAR_COLOR 41
#define AKB_ANIM_MATERIAL_IOR 42
#define AKB_ANIM_MATERIAL_CLEARCOAT 43
#define AKB_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS 44
#define AKB_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE 45
#define AKB_ANIM_MATERIAL_TRANSMISSION 46
#define AKB_ANIM_MATERIAL_SHEEN_COLOR 47
#define AKB_ANIM_MATERIAL_SHEEN_ROUGHNESS 48
#define AKB_ANIM_MATERIAL_IRIDESCENCE 49
#define AKB_ANIM_MATERIAL_IRIDESCENCE_IOR 50
#define AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM 51
#define AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM 52
#define AKB_ANIM_MATERIAL_VOLUME_THICKNESS 53
#define AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE 54
#define AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR 55
#define AKB_ANIM_MATERIAL_ANISOTROPY 56
#define AKB_ANIM_MATERIAL_ANISOTROPY_ROTATION 57
#define AKB_ANIM_MATERIAL_DISPERSION 58
#define AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION 59
#define AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR 60
#define AKB_ANIM_TEXTURE_TRANSFORM_BASE 1000
#define AKB_ANIM_TEXTURE_TRANSFORM_STRIDE 4
#define AKB_ANIM_TEXTURE_TRANSFORM_OFFSET 0
#define AKB_ANIM_TEXTURE_TRANSFORM_SCALE 1
#define AKB_ANIM_TEXTURE_TRANSFORM_ROTATION 2
#define AKB_MATERIAL_SPECULAR_GLOSSINESS AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS
#define AKB_COORD_RAW 0
#define AKB_COORD_TRANSFORM 1
#define AKB_COORD_ALL 2
#define AKB_LOAD_COORD_Z_UP 0
#define AKB_LOAD_COORD_Y_UP 1
#define AKB_LOAD_COORD_X_UP 2
#define AKB_LOAD_COORD_Z_UP_LH 3
#define AKB_LOAD_COORD_Y_UP_LH 4
#define AKB_LOAD_COORD_X_UP_LH 5
#define AKB_SKIN_DEFAULT_JOINTS_PER_VERTEX 4
#define AKB_SKIN_MAX_JOINTS_PER_VERTEX 64
#define AKB_TEXTURE_INFO_MAX 24
#define AKB_EDGE_BUILD_FACE_LIMIT 256
#define AKB_LARGE_SCENE_PRIMITIVE_THRESHOLD 1024
#define AKB_GEOMETRY_CONTENT_KEY_BYTE_LIMIT (64u * 1024u)
#define AKB_MAT4(value) (*(mat4 *)(void *)(value))
#define AKB_VEC3(value) (*(vec3 *)(void *)(value))
#define AKB_VEC4(value) (*(vec4 *)(void *)(value))
#define AKB_VERSOR(value) (*(versor *)(void *)(value))
#define AKB_EXPORT_ITEM_NODE 0
#define AKB_EXPORT_ITEM_MESH 1
#define AKB_EXPORT_ITEM_CAMERA 2
#define AKB_EXPORT_ITEM_LIGHT 3
#define AKB_EXPORT_ITEM_JOINT 4
#define AKB_EXPORT_ITEM_CURVE 5
#define AKB_EXPORT_NATIVE_MESH_PAYLOAD 0x414B4D46u
#define AKB_EXPORT_NATIVE_CURVE_PAYLOAD 0x414B4356u
#define AKB_EXPORT_MATERIAL_FEATURE_IOR 100
#define AKB_LIB_APPEND(LIB, ITEM, NEXT)                                      \
  do {                                                                       \
    (ITEM)->NEXT = NULL;                                                     \
    if ((LIB).last)                                                          \
      (LIB).last->NEXT = (ITEM);                                             \
    else                                                                     \
      (LIB).first = (ITEM);                                                  \
    (LIB).last = (ITEM);                                                     \
    (LIB).count++;                                                           \
  } while (0)

typedef enum AkbLoadOptionField {
  AKB_LOAD_OPT_COORD_SYSTEM = 0,
  AKB_LOAD_OPT_COORD_CONVERSION,
  AKB_LOAD_OPT_SCENE_INDEX,
  AKB_LOAD_OPT_TRIANGULATE,
  AKB_LOAD_OPT_GENERATE_NORMALS,
  AKB_LOAD_OPT_CONVERT_TRIANGLE_STRIP,
  AKB_LOAD_OPT_CONVERT_TRIANGLE_FAN,
  AKB_LOAD_OPT_IMPORT_LINES,
  AKB_LOAD_OPT_CONVERT_LINE_LOOP,
  AKB_LOAD_OPT_CONVERT_LINE_STRIP,
  AKB_LOAD_OPT_USE_MMAP,
  AKB_LOAD_OPT_PRESERVE_EXTRAS,
  AKB_LOAD_OPT_BUILD_TRIANGLE_EDGES,
  AKB_LOAD_OPT_GEOMETRY_KEYS,
  AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS,
  AKB_LOAD_OPT_TEXTURE_LOADING,
  AKB_LOAD_OPT_DEFER_CUSTOM_NORMALS,
  AKB_LOAD_OPT_PRESERVE_TANGENTS,
  AKB_LOAD_OPT_COUNT
} AkbLoadOptionField;

static double
akb_now_ms(void) {
#if defined(_WIN32)
  static LARGE_INTEGER freq;
  LARGE_INTEGER now;

  if (!freq.QuadPart)
    QueryPerformanceFrequency(&freq);
  QueryPerformanceCounter(&now);
  return (double)now.QuadPart * 1000.0 / (double)freq.QuadPart;
#else
  struct timespec ts;

  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
#endif
}

static int
akb_profile_enabled(void) {
  static int cached = -1;
  const char *env = getenv("ASSETKIT_BLENDER_PROFILE");

  if (cached >= 0)
    return cached;

  if (!env || !env[0])
    return cached = 0;

  cached = strcmp(env, "0") != 0
           && strcmp(env, "false") != 0
           && strcmp(env, "FALSE") != 0
           && strcmp(env, "off") != 0
           && strcmp(env, "OFF") != 0;
  return cached;
}

static void
akb_profile_log(const char *fmt, ...) {
  va_list args;

  if (!akb_profile_enabled())
    return;

  fputs("[AssetKit native] ", stderr);
  va_start(args, fmt);
  vfprintf(stderr, fmt, args);
  va_end(args);
  fputc('\n', stderr);
  fflush(stderr);
}

typedef enum AkbTextureRoleId {
  AKB_TEX_ROLE_BASE_COLOR = 0,
  AKB_TEX_ROLE_METALLIC_ROUGHNESS = 1,
  AKB_TEX_ROLE_OCCLUSION = 2,
  AKB_TEX_ROLE_NORMAL = 3,
  AKB_TEX_ROLE_EMISSIVE = 4,
  AKB_TEX_ROLE_TRANSPARENT = 5,
  AKB_TEX_ROLE_SPECULAR = 6,
  AKB_TEX_ROLE_SPECULAR_COLOR = 7,
  AKB_TEX_ROLE_CLEARCOAT = 8,
  AKB_TEX_ROLE_CLEARCOAT_ROUGHNESS = 9,
  AKB_TEX_ROLE_CLEARCOAT_NORMAL = 10,
  AKB_TEX_ROLE_TRANSMISSION = 11,
  AKB_TEX_ROLE_SHEEN_COLOR = 12,
  AKB_TEX_ROLE_SHEEN_ROUGHNESS = 13,
  AKB_TEX_ROLE_IRIDESCENCE = 14,
  AKB_TEX_ROLE_IRIDESCENCE_THICKNESS = 15,
  AKB_TEX_ROLE_VOLUME_THICKNESS = 16,
  AKB_TEX_ROLE_ANISOTROPY = 17,
  AKB_TEX_ROLE_DIFFUSE_TRANSMISSION = 18,
  AKB_TEX_ROLE_DIFFUSE_TRANSMISSION_COLOR = 19
} AkbTextureRoleId;

typedef struct AkbExportMorphBuild {
  AkMorph        *morph;
  AkMorphTarget **targets;
  AkMorphable   **lastMorphables;
  uint32_t        targetCount;
  uint32_t        primitiveCount;
} AkbExportMorphBuild;

typedef struct AkbKtx2MipLevel {
  uint32_t width;
  uint32_t height;
  uint32_t byte_offset;
  uint32_t byte_length;
} AkbKtx2MipLevel;

typedef struct AkbKtx2DecodedImage {
  uint8_t         *data;
  size_t           data_length;
  uint32_t         width;
  uint32_t         height;
  uint32_t         channels;
  uint32_t         mip_count;
  AkbKtx2MipLevel *mips;
  uint32_t         reserved[2];
} AkbKtx2DecodedImage;

typedef int
(*AkbKtx2DecodeFn)(const uint8_t       *data,
                   size_t               size,
                   AkbKtx2DecodedImage *out);

typedef struct AkbMorphTarget {
  char     name[512];
  float   *positions;
  float    weight;
  uint32_t vertex_count;
} AkbMorphTarget;

typedef struct AkbLoopFloatAttribute {
  char     name[64];
  float   *values;
  uint32_t width;
  uint32_t set;
  uint8_t  borrowed;
} AkbLoopFloatAttribute;

typedef struct AkbTextureInfo {
  AkTree *texture_extra;
  AkTree *texref_extra;
  AkTree *image_extra;
  AkTree *sampler_extra;
  char    role[64];
  char    path[1024];
  char    image_name[512];
  char    sampler_name[512];
  char    color_space[32];
  char    channels[16];
  char    texcoord[64];
  char    coord_input_name[64];
  float   transform_offset[2];
  float   transform_scale[2];
  float   transform_rotation;
  int32_t slot;
  int32_t transform_slot;
  int32_t wrap_s;
  int32_t wrap_t;
  int32_t wrap_p;
  int32_t min_filter;
  int32_t mag_filter;
  int32_t mip_filter;
  uint8_t has_transform;
} AkbTextureInfo;

typedef struct AkbMaterialVariantMap {
  char     variant_name[512];
  char     material_name[512];
  AkMaterial *material;
  uint32_t variant_index;
} AkbMaterialVariantMap;

typedef struct AkbGaussianSplatInfo {
  uint32_t kernel;
  uint32_t color_space;
  uint32_t projection;
  uint32_t sorting_method;
  uint32_t decoded_count;
} AkbGaussianSplatInfo;

typedef struct AkbPrimitive {
  struct AkbSharedDoc *doc_owner;
  struct AkbAnimation *animation;
  struct AkbAnimation *morph_animation;
  struct AkbAnimation *material_animation;
  AkTree *primitive_extra;
  AkTree *mesh_extra;
  AkTree *geometry_extra;
  AkTree *material_extra;
  AkbMorphTarget *morph_targets;
  AkMorphPreset *morph_presets;
  AkbLoopFloatAttribute *uv_sets;
  AkbLoopFloatAttribute *color_sets;
  AkbLoopFloatAttribute *point_attrs;
  AkbMaterialVariantMap *material_variants;
  AkbGaussianSplatInfo gsplat;
  AkbTextureInfo *texture_infos;
  struct AkbAnimation **skin_pose_animations;
  AkNode   **skin_joint_sources;
  AkNode    *skin_root_source;
  const char *name;
  const char *object_name;
  const char *material_name;
  char     *base_color_texture;
  char     *metallic_roughness_texture;
  char     *occlusion_texture;
  char     *normal_texture;
  char     *emissive_texture;
  char     *transparent_texture;
  char     *specular_texture;
  char     *specular_color_texture;
  char     *clearcoat_texture;
  char     *clearcoat_roughness_texture;
  char     *clearcoat_normal_texture;
  char     *transmission_texture;
  char     *sheen_color_texture;
  char     *sheen_roughness_texture;
  char     *iridescence_texture;
  char     *iridescence_thickness_texture;
  char     *volume_thickness_texture;
  char     *anisotropy_texture;
  char     *diffuse_transmission_texture;
  char     *diffuse_transmission_color_texture;
  float   *vertices;
  float   *instance_matrices;
  uint32_t *indices;
  uint32_t *edges;
  int32_t  *loop_meta;
  int32_t  *loop_starts;
  int32_t  *loop_totals;
  float   *normals;
  float   *vertex_normals;
  float   *uvs;
  float   *colors;
  float   *tangents;
  uint16_t *skin_joints;
  int32_t  *skin_joint_nodes;
  float   *skin_weights;
  float   *skin_inverse_bind_matrices;
  float    skin_bind_shape_matrix[16];
  float    base_color[4];
  float    transparent_color[4];
  float    emissive_color[3];
  float    specular_color[3];
  float    sheen_color[3];
  float    volume_attenuation_color[3];
  float    volume_scatter_color[3];
  float    diffuse_transmission_color[3];
  float    metallic;
  float    roughness;
  float    alpha_cutoff;
  float    transparent_amount;
  float    opacity;
  float    normal_scale;
  float    occlusion_strength;
  float    emissive_strength;
  float    specular_strength;
  float    ior;
  float    clearcoat;
  float    clearcoat_roughness;
  float    clearcoat_normal_scale;
  float    transmission;
  float    sheen_roughness;
  float    iridescence;
  float    iridescence_ior;
  float    iridescence_thickness_minimum;
  float    iridescence_thickness_maximum;
  float    volume_thickness;
  float    volume_attenuation_distance;
  float    volume_scatter_anisotropy;
  float    anisotropy;
  float    anisotropy_rotation;
  float    diffuse_transmission;
  float    dispersion;
  float    matrix[16];
  float    coord_matrix[16];
  uintptr_t mesh_key;
  uintptr_t material_key;
  uint64_t geometry_key;
  int32_t  node_index;
  int32_t  skin_root_node_index;
  uint32_t instance_count;
  uint32_t vertex_count;
  uint32_t loop_count;
  uint32_t face_count;
  uint32_t edge_count;
  uint32_t primitive_type;
  uint32_t primitive_mode;
  uint32_t uv_set_count;
  uint32_t color_set_count;
  uint32_t point_attr_count;
  uint32_t texture_info_count;
  uint32_t texture_info_capacity;
  uint32_t skin_pose_animation_count;
  uint32_t morph_target_count;
  uint32_t morph_preset_count;
  uint32_t material_variant_count;
  uint32_t material_type;
  uint32_t file_type;
  uint32_t primitive_index;
  uint32_t skin_vertex_count;
  uint32_t skin_joint_count;
  uint32_t skin_joint_width;
  uint8_t  has_normals;
  uint8_t  has_vertex_normals;
  uint8_t  has_uvs;
  uint8_t  has_colors;
  uint8_t  has_tangents;
  uint8_t  has_skin;
  uint8_t  has_sheen;
  uint8_t  smooth_shading;
  uint8_t  double_sided;
  uint8_t  alpha_mode;
  uint8_t  transparent_inverted;
  uint8_t  has_node;
  uint8_t  has_coord_matrix;
  uint8_t  has_gsplat;
  uint8_t  skin_mesh_in_bind_pose;
  uint8_t  borrowed_vertices;
  uint8_t  borrowed_indices;
  uint8_t  borrowed_edges;
  uint8_t  borrowed_normals;
  uint8_t  borrowed_vertex_normals;
  uint8_t  borrowed_tangents;
  uint8_t  arena_vertices;
  uint8_t  arena_indices;
  uint8_t  arena_edges;
  uint8_t  arena_loop_meta;
  uint8_t  arena_uv_sets;
  uint8_t  arena_color_sets;
  uint8_t  arena_point_attrs;
  uint8_t  arena_instance_matrices;
  uint8_t  arena_skin_joint_nodes;
  uint8_t  arena_skin_inverse_bind_matrices;
  uint8_t  arena_skin_joint_sources;
  uint8_t  zero_copy_flags;
} AkbPrimitive;

typedef struct AkbInputScan {
  AkInput *normal;
  AkInput *tangent;
  AkInput *uv;
  AkInput *color;
  uint32_t uv_count;
  uint32_t color_count;
  uint32_t point_attr_count;
} AkbInputScan;

typedef struct AkbIndexView {
  const void *data;
  size_t      count;
  size_t      item_stride;
  AkTypeId    component_type;
  uint8_t     borrowable_u32;
} AkbIndexView;

typedef struct AkbPrimitiveList {
  AkbPrimitive *items;
  size_t        count;
  size_t        capacity;
  size_t        skin_count;
} AkbPrimitiveList;

typedef struct AkbCurve {
  AkTree     *geometry_extra;
  AkTree     *curve_extra;
  const char *name;
  const char *object_name;
  float      *points;
  float       matrix[16];
  float       coord_matrix[16];
  int32_t     node_index;
  uint32_t    point_count;
  uint32_t    degree;
  uint8_t     kind;
  uint8_t     closed;
  uint8_t     has_node;
  uint8_t     has_coord_matrix;
  uint8_t     arena_points;
} AkbCurve;

typedef struct AkbCurveList {
  AkbCurve *items;
  size_t    count;
  size_t    capacity;
} AkbCurveList;

typedef struct AkbPrimitiveReuseEntry {
  AkGeometry      *geom;
  AkMesh          *mesh;
  AkMeshPrimitive *prim;
  AkInstanceGeometry *instance;
  uint32_t        prim_index;
  size_t          source_index;
  uint8_t         occupied;
} AkbPrimitiveReuseEntry;

typedef struct AkbPrimitiveReuseCache {
  AkbPrimitiveReuseEntry *items;
  size_t                  count;
  size_t                  capacity;
  size_t                  hits;
} AkbPrimitiveReuseCache;

typedef struct AkbSceneNode {
  struct AkbAnimation *animation;
  AkNode   *source;
  AkTree   *camera_extra;
  AkTree   *camera_imager_extra;
  AkTree   *light_extra;
  AkStringArray *layers;
  const char *name;
  const char *camera_name;
  const char *light_name;
  float    matrix[16];
  float    camera_values[6];
  float    light_color[3];
  float    light_values[5];
  int32_t  parent_index;
  uint8_t  camera_type;
  uint8_t  light_type;
  uint8_t  has_transform;
  uint8_t  visible;
} AkbSceneNode;

typedef struct AkbSceneNodeList {
  AkbSceneNode *items;
  size_t        count;
  size_t        capacity;
} AkbSceneNodeList;

typedef struct AkbImport {
  AkbPrimitiveList primitives;
  AkbCurveList     curves;
  AkbSceneNodeList nodes;
  AkbArena         arena;
} AkbImport;

typedef struct AkbCoordContext {
  AkCoordSys *source;
  AkCoordSys *target;
  float       matrix[16];
  uint8_t     convert;
  uint8_t     conversion;
} AkbCoordContext;

typedef struct AkbLoadOptions {
  AkCoordSys *target_coord;
  int32_t     scene_index;
  uint8_t     coord_conversion;
  uint8_t     triangulate;
  uint8_t     gen_normals;
  uint8_t     cvt_triangle_strip;
  uint8_t     cvt_triangle_fan;
  uint8_t     import_lines;
  uint8_t     cvt_line_loop;
  uint8_t     cvt_line_strip;
  uint8_t     use_mmap;
  uint8_t     preserve_extras;
  uint8_t     build_triangle_edges;
  uint8_t     geometry_keys;
  uint8_t     geometry_content_keys;
} AkbLoadOptions;

typedef struct AkbSavedOptions {
  uintptr_t coord;
  uintptr_t coord_convert_type;
  uintptr_t triangulate;
  uintptr_t gen_normals;
  uintptr_t cvt_triangle_strip;
  uintptr_t cvt_triangle_fan;
  uintptr_t cvt_line_loop;
  uintptr_t cvt_line_strip;
  uintptr_t use_mmap;
  uintptr_t preserve_extras;
  uintptr_t meshopt_decoder_path;
  uintptr_t draco_decoder_path;
  uintptr_t gsplat_decoder_path;
  uintptr_t ktx2_decoder_path;
} AkbSavedOptions;

typedef struct AkbDecoderPaths {
  char meshopt[PATH_MAX];
  char draco[PATH_MAX];
  char gsplat[PATH_MAX];
  char ktx2[PATH_MAX];
  int  initialized;
} AkbDecoderPaths;

static AkbDecoderPaths AKB_DECODER_PATHS;

typedef struct AkbSharedDoc {
  AkDoc *doc;
  size_t refcount;
} AkbSharedDoc;

typedef struct AkbAnimChannel {
  float      *times;
  float      *values;
  float      *in_tangents;
  float      *out_tangents;
  const char *clip_name;
  uint32_t    count;
  uint32_t    value_width;
  uint32_t    target;
  uint32_t    target_offset;
  uint32_t    clip_index;
  uint8_t     interpolation;
  uint8_t     is_partial;
  uint8_t     borrowed_times;
  uint8_t     borrowed_values;
  uint8_t     borrowed_in_tangents;
  uint8_t     borrowed_out_tangents;
  uint8_t     pose_ready;
} AkbAnimChannel;

typedef enum AkbPyAnimChannelField {
  AKB_PY_ANIM_TARGET = 0,
  AKB_PY_ANIM_TARGET_OFFSET,
  AKB_PY_ANIM_CLIP_INDEX,
  AKB_PY_ANIM_CLIP_NAME,
  AKB_PY_ANIM_VALUE_WIDTH,
  AKB_PY_ANIM_COUNT,
  AKB_PY_ANIM_INTERPOLATION,
  AKB_PY_ANIM_IS_PARTIAL,
  AKB_PY_ANIM_POSE_READY,
  AKB_PY_ANIM_TIMES_F32,
  AKB_PY_ANIM_VALUES_F32,
  AKB_PY_ANIM_IN_TANGENTS_F32,
  AKB_PY_ANIM_OUT_TANGENTS_F32,
  AKB_PY_ANIM_FIELD_COUNT
} AkbPyAnimChannelField;

typedef enum AkbPySimplePrimitiveField {
  AKB_PY_SIMPLE_OWNER = 0,
  AKB_PY_SIMPLE_NAME,
  AKB_PY_SIMPLE_OBJECT_NAME,
  AKB_PY_SIMPLE_VERTEX_COUNT,
  AKB_PY_SIMPLE_LOOP_COUNT,
  AKB_PY_SIMPLE_FACE_COUNT,
  AKB_PY_SIMPLE_PRIMITIVE_TYPE,
  AKB_PY_SIMPLE_PRIMITIVE_MODE,
  AKB_PY_SIMPLE_FILE_TYPE,
  AKB_PY_SIMPLE_MESH_KEY,
  AKB_PY_SIMPLE_PRIMITIVE_INDEX,
  AKB_PY_SIMPLE_ZERO_COPY_FLAGS,
  AKB_PY_SIMPLE_HAS_NODE,
  AKB_PY_SIMPLE_NODE_INDEX,
  AKB_PY_SIMPLE_MATRIX_F32,
  AKB_PY_SIMPLE_COORD_MATRIX_F32,
  AKB_PY_SIMPLE_INSTANCE_COUNT,
  AKB_PY_SIMPLE_INSTANCE_MATRICES_F32,
  AKB_PY_SIMPLE_VERTICES_F32,
  AKB_PY_SIMPLE_INDICES_U32,
  AKB_PY_SIMPLE_LOOP_STARTS_I32,
  AKB_PY_SIMPLE_LOOP_TOTALS_I32,
  AKB_PY_SIMPLE_NORMALS_F32,
  AKB_PY_SIMPLE_VERTEX_NORMALS_F32,
  AKB_PY_SIMPLE_TANGENTS_F32,
  AKB_PY_SIMPLE_GEOMETRY_KEY,
  AKB_PY_SIMPLE_EDGE_COUNT,
  AKB_PY_SIMPLE_EDGES_U32,
  AKB_PY_SIMPLE_UVS_F32,
  AKB_PY_SIMPLE_BASE_COLOR_TEXTURE,
  AKB_PY_SIMPLE_MATERIAL_TYPE,
  AKB_PY_SIMPLE_MATERIAL_KEY,
  AKB_PY_SIMPLE_METALLIC,
  AKB_PY_SIMPLE_ROUGHNESS,
  AKB_PY_SIMPLE_DOUBLE_SIDED,
  AKB_PY_SIMPLE_SMOOTH_SHADING,
  AKB_PY_SIMPLE_FIELD_COUNT
} AkbPySimplePrimitiveField;

typedef enum AkbPyCurveField {
  AKB_PY_CURVE_OWNER = 0,
  AKB_PY_CURVE_NAME,
  AKB_PY_CURVE_OBJECT_NAME,
  AKB_PY_CURVE_KIND,
  AKB_PY_CURVE_POINT_COUNT,
  AKB_PY_CURVE_DEGREE,
  AKB_PY_CURVE_CLOSED,
  AKB_PY_CURVE_HAS_NODE,
  AKB_PY_CURVE_NODE_INDEX,
  AKB_PY_CURVE_MATRIX_F32,
  AKB_PY_CURVE_COORD_MATRIX_F32,
  AKB_PY_CURVE_POINTS_F32,
  AKB_PY_CURVE_GEOMETRY_EXTRA,
  AKB_PY_CURVE_CURVE_EXTRA,
  AKB_PY_CURVE_FIELD_COUNT
} AkbPyCurveField;

typedef enum AkbPySceneNodeField {
  AKB_PY_NODE_OWNER = 0,
  AKB_PY_NODE_NAME,
  AKB_PY_NODE_PARENT_INDEX,
  AKB_PY_NODE_VISIBLE,
  AKB_PY_NODE_LAYERS,
  AKB_PY_NODE_CAMERA_TYPE,
  AKB_PY_NODE_CAMERA_NAME,
  AKB_PY_NODE_CAMERA_EXTRA,
  AKB_PY_NODE_CAMERA_IMAGER_EXTRA,
  AKB_PY_NODE_CAMERA_VALUES,
  AKB_PY_NODE_LIGHT_TYPE,
  AKB_PY_NODE_LIGHT_NAME,
  AKB_PY_NODE_LIGHT_EXTRA,
  AKB_PY_NODE_LIGHT_COLOR,
  AKB_PY_NODE_LIGHT_VALUES,
  AKB_PY_NODE_MATRIX_F32,
  AKB_PY_NODE_EXTRA,
  AKB_PY_NODE_ANIM_COUNT,
  AKB_PY_NODE_ANIM_CHANNELS,
  AKB_PY_NODE_FIELD_COUNT
} AkbPySceneNodeField;

typedef enum AkbPyPrimitiveField {
  AKB_PY_PRIM_OWNER = 0,
  AKB_PY_PRIM_NAME,
  AKB_PY_PRIM_OBJECT_NAME,
  AKB_PY_PRIM_VERTEX_COUNT,
  AKB_PY_PRIM_LOOP_COUNT,
  AKB_PY_PRIM_FACE_COUNT,
  AKB_PY_PRIM_PRIMITIVE_TYPE,
  AKB_PY_PRIM_PRIMITIVE_MODE,
  AKB_PY_PRIM_MATERIAL_NAME,
  AKB_PY_PRIM_BASE_COLOR,
  AKB_PY_PRIM_TRANSPARENT_COLOR,
  AKB_PY_PRIM_EMISSIVE_COLOR,
  AKB_PY_PRIM_SPECULAR_COLOR,
  AKB_PY_PRIM_SHEEN_COLOR,
  AKB_PY_PRIM_VOLUME_ATTENUATION_COLOR,
  AKB_PY_PRIM_VOLUME_SCATTER_COLOR,
  AKB_PY_PRIM_DIFFUSE_TRANSMISSION_COLOR,
  AKB_PY_PRIM_METALLIC,
  AKB_PY_PRIM_ROUGHNESS,
  AKB_PY_PRIM_ALPHA_CUTOFF,
  AKB_PY_PRIM_TRANSPARENT_AMOUNT,
  AKB_PY_PRIM_OPACITY,
  AKB_PY_PRIM_NORMAL_SCALE,
  AKB_PY_PRIM_OCCLUSION_STRENGTH,
  AKB_PY_PRIM_EMISSIVE_STRENGTH,
  AKB_PY_PRIM_SPECULAR_STRENGTH,
  AKB_PY_PRIM_IOR,
  AKB_PY_PRIM_CLEARCOAT,
  AKB_PY_PRIM_CLEARCOAT_ROUGHNESS,
  AKB_PY_PRIM_CLEARCOAT_NORMAL_SCALE,
  AKB_PY_PRIM_TRANSMISSION,
  AKB_PY_PRIM_SHEEN_ROUGHNESS,
  AKB_PY_PRIM_IRIDESCENCE,
  AKB_PY_PRIM_IRIDESCENCE_IOR,
  AKB_PY_PRIM_IRIDESCENCE_THICKNESS_MINIMUM,
  AKB_PY_PRIM_IRIDESCENCE_THICKNESS_MAXIMUM,
  AKB_PY_PRIM_VOLUME_THICKNESS,
  AKB_PY_PRIM_VOLUME_ATTENUATION_DISTANCE,
  AKB_PY_PRIM_VOLUME_SCATTER_ANISOTROPY,
  AKB_PY_PRIM_ANISOTROPY,
  AKB_PY_PRIM_ANISOTROPY_ROTATION,
  AKB_PY_PRIM_DIFFUSE_TRANSMISSION,
  AKB_PY_PRIM_DISPERSION,
  AKB_PY_PRIM_ALPHA_MODE,
  AKB_PY_PRIM_TRANSPARENT_INVERTED,
  AKB_PY_PRIM_DOUBLE_SIDED,
  AKB_PY_PRIM_MATERIAL_TYPE,
  AKB_PY_PRIM_FILE_TYPE,
  AKB_PY_PRIM_MESH_KEY,
  AKB_PY_PRIM_MATERIAL_KEY,
  AKB_PY_PRIM_PRIMITIVE_INDEX,
  AKB_PY_PRIM_HAS_NODE,
  AKB_PY_PRIM_NODE_INDEX,
  AKB_PY_PRIM_INSTANCE_COUNT,
  AKB_PY_PRIM_HAS_GSPLAT,
  AKB_PY_PRIM_GSPLAT_KERNEL,
  AKB_PY_PRIM_GSPLAT_COLOR_SPACE,
  AKB_PY_PRIM_GSPLAT_PROJECTION,
  AKB_PY_PRIM_GSPLAT_SORTING_METHOD,
  AKB_PY_PRIM_GSPLAT_DECODED_COUNT,
  AKB_PY_PRIM_HAS_SKIN,
  AKB_PY_PRIM_HAS_SHEEN,
  AKB_PY_PRIM_SKIN_VERTEX_COUNT,
  AKB_PY_PRIM_SKIN_JOINT_COUNT,
  AKB_PY_PRIM_SKIN_JOINT_WIDTH,
  AKB_PY_PRIM_SKIN_ROOT_NODE_INDEX,
  AKB_PY_PRIM_SKIN_MESH_IN_BIND_POSE,
  AKB_PY_PRIM_SKIN_POSE_ANIM_CHANNELS,
  AKB_PY_PRIM_ZERO_COPY_FLAGS,
  AKB_PY_PRIM_UV_SET_COUNT,
  AKB_PY_PRIM_COLOR_SET_COUNT,
  AKB_PY_PRIM_POINT_ATTR_COUNT,
  AKB_PY_PRIM_ANIM_COUNT,
  AKB_PY_PRIM_ANIM_CHANNELS,
  AKB_PY_PRIM_MORPH_TARGET_COUNT,
  AKB_PY_PRIM_MORPH_TARGETS,
  AKB_PY_PRIM_MORPH_PRESET_COUNT,
  AKB_PY_PRIM_MORPH_PRESETS,
  AKB_PY_PRIM_MORPH_ANIM_COUNT,
  AKB_PY_PRIM_MORPH_ANIM_CHANNELS,
  AKB_PY_PRIM_MATERIAL_ANIM_COUNT,
  AKB_PY_PRIM_MATERIAL_ANIM_CHANNELS,
  AKB_PY_PRIM_UV_SETS,
  AKB_PY_PRIM_COLOR_SETS,
  AKB_PY_PRIM_POINT_ATTRS,
  AKB_PY_PRIM_TEXTURE_INFOS,
  AKB_PY_PRIM_PRIMITIVE_EXTRA,
  AKB_PY_PRIM_MESH_EXTRA,
  AKB_PY_PRIM_GEOMETRY_EXTRA,
  AKB_PY_PRIM_MATERIAL_EXTRA,
  AKB_PY_PRIM_MATERIAL_VARIANT_COUNT,
  AKB_PY_PRIM_MATERIAL_VARIANTS,
  AKB_PY_PRIM_MATRIX_F32,
  AKB_PY_PRIM_COORD_MATRIX_F32,
  AKB_PY_PRIM_INSTANCE_MATRICES_F32,
  AKB_PY_PRIM_BASE_COLOR_TEXTURE,
  AKB_PY_PRIM_METALLIC_ROUGHNESS_TEXTURE,
  AKB_PY_PRIM_OCCLUSION_TEXTURE,
  AKB_PY_PRIM_NORMAL_TEXTURE,
  AKB_PY_PRIM_EMISSIVE_TEXTURE,
  AKB_PY_PRIM_TRANSPARENT_TEXTURE,
  AKB_PY_PRIM_SPECULAR_TEXTURE,
  AKB_PY_PRIM_SPECULAR_COLOR_TEXTURE,
  AKB_PY_PRIM_CLEARCOAT_TEXTURE,
  AKB_PY_PRIM_CLEARCOAT_ROUGHNESS_TEXTURE,
  AKB_PY_PRIM_CLEARCOAT_NORMAL_TEXTURE,
  AKB_PY_PRIM_TRANSMISSION_TEXTURE,
  AKB_PY_PRIM_SHEEN_COLOR_TEXTURE,
  AKB_PY_PRIM_SHEEN_ROUGHNESS_TEXTURE,
  AKB_PY_PRIM_IRIDESCENCE_TEXTURE,
  AKB_PY_PRIM_IRIDESCENCE_THICKNESS_TEXTURE,
  AKB_PY_PRIM_VOLUME_THICKNESS_TEXTURE,
  AKB_PY_PRIM_ANISOTROPY_TEXTURE,
  AKB_PY_PRIM_DIFFUSE_TRANSMISSION_TEXTURE,
  AKB_PY_PRIM_DIFFUSE_TRANSMISSION_COLOR_TEXTURE,
  AKB_PY_PRIM_VERTICES_F32,
  AKB_PY_PRIM_INDICES_U32,
  AKB_PY_PRIM_LOOP_STARTS_I32,
  AKB_PY_PRIM_LOOP_TOTALS_I32,
  AKB_PY_PRIM_NORMALS_F32,
  AKB_PY_PRIM_VERTEX_NORMALS_F32,
  AKB_PY_PRIM_UVS_F32,
  AKB_PY_PRIM_COLORS_F32,
  AKB_PY_PRIM_TANGENTS_F32,
  AKB_PY_PRIM_SKIN_JOINTS_U16,
  AKB_PY_PRIM_SKIN_WEIGHTS_F32,
  AKB_PY_PRIM_SKIN_JOINT_NODES_I32,
  AKB_PY_PRIM_SKIN_INVERSE_BIND_MATRICES_F32,
  AKB_PY_PRIM_SKIN_BIND_SHAPE_MATRIX_F32,
  AKB_PY_PRIM_GEOMETRY_KEY,
  AKB_PY_PRIM_EDGE_COUNT,
  AKB_PY_PRIM_EDGES_U32,
  AKB_PY_PRIM_SMOOTH_SHADING,
  AKB_PY_PRIM_FIELD_COUNT
} AkbPyPrimitiveField;

typedef struct AkbAnimation {
  AkbSharedDoc  *doc_owner;
  AkbAnimChannel *channels;
  AkBakedAnimation *baked;
  float         *baked_values;
  size_t         count;
  size_t         capacity;
  size_t         refcount;
} AkbAnimation;

typedef struct AkbAnimBinding {
  void    *target;
  uint32_t kind;
  uint32_t width;
} AkbAnimBinding;

typedef struct AkbResolvedAnimChannel {
  AkChannel        *channel;
  AkResolvedTarget resolved;
  const char      *clip_name;
  uint32_t         clip_index;
} AkbResolvedAnimChannel;

typedef struct AkbAnimationIndex {
  AkbResolvedAnimChannel *items;
  size_t                  count;
  size_t                  capacity;
} AkbAnimationIndex;
