#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>
#include <errno.h>
#if defined(_WIN32)
#include <windows.h>
#include <direct.h>
#else
#include <dlfcn.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#include "cglm/struct.h"

#include "ak/assetkit.h"
#include "ak/options.h"
#include "ak/path.h"

struct FListItem {
  struct FListItem *next;
  void             *data;
};
typedef struct FListItem FListItem;

#ifndef PATH_MAX
#  define PATH_MAX 4096
#endif

#define AKB_GEOMETRY_MESH AK_GEOMETRY_MESH
#define AKB_PRIMITIVE_LINES AK_PRIMITIVE_LINES
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
#define AKB_MATERIAL_SPECULAR_GLOSSINESS 6
#define AKB_COORD_RAW 0
#define AKB_COORD_TRANSFORM 1
#define AKB_COORD_ALL 2
#define AKB_SKIN_DEFAULT_JOINTS_PER_VERTEX 4
#define AKB_SKIN_MAX_JOINTS_PER_VERTEX 64
#define AKB_TEXTURE_INFO_MAX 24

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
  AkTree *effect_extra;
  AkbMorphTarget *morph_targets;
  AkMorphPreset *morph_presets;
  AkbLoopFloatAttribute *uv_sets;
  AkbLoopFloatAttribute *color_sets;
  AkbLoopFloatAttribute *point_attrs;
  AkbMaterialVariantMap *material_variants;
  AkbGaussianSplatInfo gsplat;
  AkbTextureInfo texture_infos[AKB_TEXTURE_INFO_MAX];
  AkNode   **skin_joint_sources;
  AkNode    *skin_root_source;
  char     name[512];
  char     object_name[512];
  char     material_name[512];
  char     base_color_texture[1024];
  char     metallic_roughness_texture[1024];
  char     occlusion_texture[1024];
  char     normal_texture[1024];
  char     emissive_texture[1024];
  char     transparent_texture[1024];
  char     specular_texture[1024];
  char     specular_color_texture[1024];
  char     clearcoat_texture[1024];
  char     clearcoat_roughness_texture[1024];
  char     clearcoat_normal_texture[1024];
  char     transmission_texture[1024];
  char     sheen_color_texture[1024];
  char     sheen_roughness_texture[1024];
  char     iridescence_texture[1024];
  char     iridescence_thickness_texture[1024];
  char     volume_thickness_texture[1024];
  char     anisotropy_texture[1024];
  char     diffuse_transmission_texture[1024];
  char     diffuse_transmission_color_texture[1024];
  float   *vertices;
  float   *instance_matrices;
  uint32_t *indices;
  int32_t  *loop_meta;
  int32_t  *loop_starts;
  int32_t  *loop_totals;
  float   *normals;
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
  float    anisotropy;
  float    anisotropy_rotation;
  float    diffuse_transmission;
  float    dispersion;
  float    matrix[16];
  float    coord_matrix[16];
  int32_t  node_index;
  int32_t  skin_root_node_index;
  uint32_t instance_count;
  uint32_t vertex_count;
  uint32_t loop_count;
  uint32_t face_count;
  uint32_t primitive_type;
  uint32_t primitive_mode;
  uint32_t uv_set_count;
  uint32_t color_set_count;
  uint32_t point_attr_count;
  uint32_t texture_info_count;
  uint32_t morph_target_count;
  uint32_t morph_preset_count;
  uint32_t material_variant_count;
  uint32_t material_type;
  uint32_t file_type;
  uint32_t skin_vertex_count;
  uint32_t skin_joint_count;
  uint32_t skin_joint_width;
  uint8_t  has_normals;
  uint8_t  has_uvs;
  uint8_t  has_colors;
  uint8_t  has_tangents;
  uint8_t  has_skin;
  uint8_t  has_sheen;
  uint8_t  double_sided;
  uint8_t  alpha_mode;
  uint8_t  transparent_opaque;
  uint8_t  has_node;
  uint8_t  has_coord_matrix;
  uint8_t  has_gsplat;
  uint8_t  skin_mesh_in_bind_pose;
  uint8_t  borrowed_vertices;
  uint8_t  borrowed_indices;
  uint8_t  zero_copy_flags;
} AkbPrimitive;

typedef struct AkbPrimitiveList {
  AkbPrimitive *items;
  size_t        count;
  size_t        capacity;
} AkbPrimitiveList;

typedef struct AkbSceneNode {
  struct AkbAnimation *animation;
  AkNode   *source;
  AkTree   *camera_extra;
  AkTree   *camera_imager_extra;
  AkTree   *light_extra;
  AkStringArray *layers;
  char     name[512];
  char     camera_name[512];
  char     light_name[512];
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
  AkbSceneNodeList nodes;
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
} AkbSavedOptions;

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
} AkbAnimChannel;

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

static void
akb_shared_doc_retain(AkbSharedDoc *owner) {
  if (owner)
    owner->refcount++;
}

static void
akb_shared_doc_release(AkbSharedDoc *owner) {
  if (!owner)
    return;
  if (--owner->refcount == 0) {
    if (owner->doc)
      ak_free(owner->doc);
    free(owner);
  }
}

static void
akb_primitive_retain_doc(AkbPrimitive *prim, AkbSharedDoc *owner) {
  if (!prim || !owner || prim->doc_owner)
    return;
  akb_shared_doc_retain(owner);
  prim->doc_owner = owner;
}

static AkbAnimation *
akb_animation_retain(AkbAnimation *animation) {
  if (animation)
    animation->refcount++;
  return animation;
}

static void
akb_coord_matrix(AkbCoordContext *coord) {
  float in[3];
  float out[3];
  int i;

  memset(coord->matrix, 0, sizeof(coord->matrix));
  coord->matrix[15] = 1.0f;

  for (i = 0; i < 3; i++) {
    in[0] = 0.0f;
    in[1] = 0.0f;
    in[2] = 0.0f;
    in[i] = 1.0f;
    ak_coordCvtVectorTo(coord->source, in, coord->target, out);
    coord->matrix[(size_t)i * 4]     = out[0];
    coord->matrix[(size_t)i * 4 + 1] = out[1];
    coord->matrix[(size_t)i * 4 + 2] = out[2];
  }
}

static void
akb_coord_ctx_init(AkbCoordContext *coord, AkDoc *doc, const AkbLoadOptions *options) {
  coord->source = doc && doc->coordSys ? doc->coordSys : AK_YUP;
  coord->target = options->target_coord ? options->target_coord : AK_ZUP;
  coord->convert = coord->source != coord->target
                   && !ak_coordOrientationIsEq(coord->source, coord->target);
  coord->conversion = options->coord_conversion;
  akb_coord_matrix(coord);
}

static void
akb_prepare_blender_coords(AkDoc *doc,
                           AkbCoordContext *coord,
                           const AkbLoadOptions *options) {
  akb_coord_ctx_init(coord, doc, options);
}

static AkCoordSys *
akb_coord_from_name(const char *name) {
  if (!name || !name[0])
    return AK_ZUP;
  if (strcmp(name, "Y_UP") == 0)
    return AK_YUP;
  if (strcmp(name, "X_UP") == 0)
    return AK_XUP;
  if (strcmp(name, "Z_UP_LH") == 0)
    return AK_ZUP_LH;
  if (strcmp(name, "Y_UP_LH") == 0)
    return AK_YUP_LH;
  if (strcmp(name, "X_UP_LH") == 0)
    return AK_XUP_LH;
  return AK_ZUP;
}

static uint8_t
akb_conversion_from_name(const char *name) {
  if (!name || !name[0])
    return AKB_COORD_TRANSFORM;
  if (strcmp(name, "RAW") == 0)
    return AKB_COORD_RAW;
  if (strcmp(name, "ALL") == 0)
    return AKB_COORD_ALL;
  return AKB_COORD_TRANSFORM;
}

static void
akb_load_options_default(AkbLoadOptions *options) {
  memset(options, 0, sizeof(*options));
  options->target_coord = AK_ZUP;
  options->scene_index = -1;
  options->coord_conversion = AKB_COORD_TRANSFORM;
  options->triangulate = 1;
  options->gen_normals = 0;
  options->cvt_triangle_strip = 1;
  options->cvt_triangle_fan = 1;
  options->import_lines = 1;
  options->cvt_line_loop = 1;
  options->cvt_line_strip = 1;
  options->use_mmap = 0;
}

static int
akb_load_options_from_dict(AkbLoadOptions *options, PyObject *dict) {
  PyObject *value;

  akb_load_options_default(options);
  if (!dict || dict == Py_None)
    return 1;
  if (!PyDict_Check(dict)) {
    PyErr_SetString(PyExc_TypeError, "AssetKit load options must be a dict");
    return 0;
  }

  value = PyDict_GetItemString(dict, "coordinate_system");
  if (value && PyUnicode_Check(value))
    options->target_coord = akb_coord_from_name(PyUnicode_AsUTF8(value));

  value = PyDict_GetItemString(dict, "coordinate_conversion");
  if (value && PyUnicode_Check(value))
    options->coord_conversion = akb_conversion_from_name(PyUnicode_AsUTF8(value));

  value = PyDict_GetItemString(dict, "scene_index");
  if (value && value != Py_None) {
    long index = PyLong_AsLong(value);
    if (PyErr_Occurred())
      return 0;
    options->scene_index = (int32_t)index;
  }

  value = PyDict_GetItemString(dict, "triangulate");
  if (value)
    options->triangulate = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "generate_normals");
  if (value)
    options->gen_normals = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "convert_triangle_strip");
  if (value)
    options->cvt_triangle_strip = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "convert_triangle_fan");
  if (value)
    options->cvt_triangle_fan = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "import_lines");
  if (value)
    options->import_lines = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "convert_line_loop");
  if (value)
    options->cvt_line_loop = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "convert_line_strip");
  if (value)
    options->cvt_line_strip = PyObject_IsTrue(value) ? 1 : 0;

  value = PyDict_GetItemString(dict, "use_mmap");
  if (value)
    options->use_mmap = PyObject_IsTrue(value) ? 1 : 0;

  return !PyErr_Occurred();
}

static AkCoordCvtType
akb_assetkit_coord_cvt_type(uint8_t conversion) {
  if (conversion == AKB_COORD_RAW)
    return AK_COORD_CVT_DISABLED;
  if (conversion == AKB_COORD_ALL)
    return AK_COORD_CVT_ALL;
  return AK_COORD_CVT_DISABLED;
}

static void
akb_options_apply(const AkbLoadOptions *options, AkbSavedOptions *saved) {
  saved->coord = ak_opt_get(AK_OPT_COORD);
  saved->coord_convert_type = ak_opt_get(AK_OPT_COORD_CONVERT_TYPE);
  saved->triangulate = ak_opt_get(AK_OPT_TRIANGULATE);
  saved->gen_normals = ak_opt_get(AK_OPT_GEN_NORMALS_IF_NEEDED);
  saved->cvt_triangle_strip = ak_opt_get(AK_OPT_CVT_TRIANGLESTRIP);
  saved->cvt_triangle_fan = ak_opt_get(AK_OPT_CVT_TRIANGLEFAN);
  saved->cvt_line_loop = ak_opt_get(AK_OPT_CVT_LINELOOP);
  saved->cvt_line_strip = ak_opt_get(AK_OPT_CVT_LINESTRIP);
  saved->use_mmap = ak_opt_get(AK_OPT_USE_MMAP);

  ak_opt_set(AK_OPT_COORD, (uintptr_t)options->target_coord);
  ak_opt_set(AK_OPT_COORD_CONVERT_TYPE,
             (uintptr_t)akb_assetkit_coord_cvt_type(options->coord_conversion));
  ak_opt_set(AK_OPT_TRIANGULATE, options->triangulate);
  ak_opt_set(AK_OPT_GEN_NORMALS_IF_NEEDED, options->gen_normals);
  ak_opt_set(AK_OPT_CVT_TRIANGLESTRIP, options->cvt_triangle_strip);
  ak_opt_set(AK_OPT_CVT_TRIANGLEFAN, options->cvt_triangle_fan);
  ak_opt_set(AK_OPT_CVT_LINELOOP, options->cvt_line_loop);
  ak_opt_set(AK_OPT_CVT_LINESTRIP, options->cvt_line_strip);
  ak_opt_set(AK_OPT_USE_MMAP, options->use_mmap);
}

static void
akb_options_restore(const AkbSavedOptions *saved) {
  ak_opt_set(AK_OPT_COORD, saved->coord);
  ak_opt_set(AK_OPT_COORD_CONVERT_TYPE, saved->coord_convert_type);
  ak_opt_set(AK_OPT_TRIANGULATE, saved->triangulate);
  ak_opt_set(AK_OPT_GEN_NORMALS_IF_NEEDED, saved->gen_normals);
  ak_opt_set(AK_OPT_CVT_TRIANGLESTRIP, saved->cvt_triangle_strip);
  ak_opt_set(AK_OPT_CVT_TRIANGLEFAN, saved->cvt_triangle_fan);
  ak_opt_set(AK_OPT_CVT_LINELOOP, saved->cvt_line_loop);
  ak_opt_set(AK_OPT_CVT_LINESTRIP, saved->cvt_line_strip);
  ak_opt_set(AK_OPT_USE_MMAP, saved->use_mmap);
}

static void
akb_animation_release(AkbAnimation *animation) {
  size_t i;

  if (!animation)
    return;

  if (--animation->refcount == 0) {
    for (i = 0; i < animation->count; i++) {
      if (!animation->channels[i].borrowed_times)
        free(animation->channels[i].times);
      if (!animation->channels[i].borrowed_values)
        free(animation->channels[i].values);
      if (!animation->channels[i].borrowed_in_tangents)
        free(animation->channels[i].in_tangents);
      if (!animation->channels[i].borrowed_out_tangents)
        free(animation->channels[i].out_tangents);
    }
    free(animation->channels);
    free(animation->baked_values);
    if (animation->baked)
      ak_free(animation->baked);
    akb_shared_doc_release(animation->doc_owner);
    free(animation);
  }
}

static const char *
akb_name(const char *value, const char *fallback) {
  return value && value[0] ? value : fallback;
}

static int
akb_raw_semantic_is(AkInput *input, const char *name) {
  return input && input->semanticRaw && strcmp(input->semanticRaw, name) == 0;
}

static AkInput *
akb_find_input(AkMeshPrimitive *prim,
               AkInputSemantic semantic_a,
               AkInputSemantic semantic_b,
               const char *raw_a,
               const char *raw_b) {
  AkInput *input;

  for (input = prim ? prim->input : NULL; input; input = input->next) {
    if (input->semantic == semantic_a || input->semantic == semantic_b)
      return input;
    if ((raw_a && akb_raw_semantic_is(input, raw_a))
        || (raw_b && akb_raw_semantic_is(input, raw_b)))
      return input;
  }

  return NULL;
}

static AkInput *
akb_find_input_with_accessor(AkMeshPrimitive *prim,
                             AkInputSemantic semantic_a,
                             AkInputSemantic semantic_b,
                             const char *raw_a,
                             const char *raw_b) {
  AkInput *input;

  for (input = prim ? prim->input : NULL; input; input = input->next) {
    if (!input->accessor || input->accessor->count == 0)
      continue;
    if (input->semantic == semantic_a || input->semantic == semantic_b)
      return input;
    if ((raw_a && akb_raw_semantic_is(input, raw_a))
        || (raw_b && akb_raw_semantic_is(input, raw_b)))
      return input;
  }

  return NULL;
}

static void
akb_primitive_free(AkbPrimitive *prim) {
  uint32_t i;

  if (!prim)
    return;
  if (!prim->borrowed_vertices)
    free(prim->vertices);
  free(prim->instance_matrices);
  if (!prim->borrowed_indices)
    free(prim->indices);
  free(prim->loop_meta);
  free(prim->normals);
  for (i = 0; i < prim->uv_set_count; i++)
    if (!prim->uv_sets[i].borrowed)
      free(prim->uv_sets[i].values);
  free(prim->uv_sets);
  for (i = 0; i < prim->color_set_count; i++)
    if (!prim->color_sets[i].borrowed)
      free(prim->color_sets[i].values);
  free(prim->color_sets);
  for (i = 0; i < prim->point_attr_count; i++)
    if (!prim->point_attrs[i].borrowed)
      free(prim->point_attrs[i].values);
  free(prim->point_attrs);
  if (!prim->uv_set_count)
    free(prim->uvs);
  if (!prim->color_set_count)
    free(prim->colors);
  free(prim->tangents);
  free(prim->skin_joints);
  free(prim->skin_joint_nodes);
  free(prim->skin_weights);
  free(prim->skin_inverse_bind_matrices);
  free(prim->skin_joint_sources);
  free(prim->material_variants);
  for (i = 0; i < prim->morph_target_count; i++)
    free(prim->morph_targets[i].positions);
  free(prim->morph_targets);
  akb_animation_release(prim->animation);
  akb_animation_release(prim->morph_animation);
  akb_animation_release(prim->material_animation);
  akb_shared_doc_release(prim->doc_owner);
  memset(prim, 0, sizeof(*prim));
}

static void
akb_scene_node_free(AkbSceneNode *node) {
  if (!node)
    return;
  akb_animation_release(node->animation);
  memset(node, 0, sizeof(*node));
}

static void
akb_list_free(AkbPrimitiveList *list) {
  size_t i;

  if (!list || !list->items)
    return;

  for (i = 0; i < list->count; i++)
    akb_primitive_free(&list->items[i]);
  free(list->items);
  memset(list, 0, sizeof(*list));
}

static void
akb_node_list_free(AkbSceneNodeList *list) {
  size_t i;

  if (!list || !list->items)
    return;

  for (i = 0; i < list->count; i++)
    akb_scene_node_free(&list->items[i]);
  free(list->items);
  memset(list, 0, sizeof(*list));
}

static int
akb_list_push(AkbPrimitiveList *list, AkbPrimitive *prim) {
  AkbPrimitive *new_items;
  size_t new_capacity;

  if (list->count == list->capacity) {
    new_capacity = list->capacity ? list->capacity * 2 : 16;
    new_items = (AkbPrimitive *)realloc(list->items, new_capacity * sizeof(*new_items));
    if (!new_items)
      return 0;
    list->items = new_items;
    list->capacity = new_capacity;
  }

  list->items[list->count++] = *prim;
  memset(prim, 0, sizeof(*prim));
  return 1;
}

static int
akb_node_list_push(AkbSceneNodeList *list, AkbSceneNode *node) {
  AkbSceneNode *new_items;
  size_t new_capacity;

  if (list->count == list->capacity) {
    new_capacity = list->capacity ? list->capacity * 2 : 32;
    new_items = (AkbSceneNode *)realloc(list->items, new_capacity * sizeof(*new_items));
    if (!new_items)
      return 0;
    list->items = new_items;
    list->capacity = new_capacity;
  }

  list->items[list->count++] = *node;
  memset(node, 0, sizeof(*node));
  return 1;
}

static void
akb_list_set_coord_matrix(AkbPrimitiveList *list, const AkbCoordContext *coord) {
  size_t i;

  if (!list || !coord || !coord->convert || coord->conversion != AKB_COORD_TRANSFORM)
    return;

  for (i = 0; i < list->count; i++) {
    memcpy(list->items[i].coord_matrix,
           coord->matrix,
           sizeof(list->items[i].coord_matrix));
    list->items[i].has_coord_matrix = 1;
  }
}

static void
akb_path_join(char *dest, size_t capacity, const char *dir, const char *name) {
  size_t len;

  if (!dest || capacity == 0)
    return;

  if (!dir || !dir[0]) {
    snprintf(dest, capacity, "%s", name ? name : "");
    return;
  }

  len = strlen(dir);
  if (len > 0 && (dir[len - 1] == '/' || dir[len - 1] == '\\'))
    snprintf(dest, capacity, "%s%s", dir, name ? name : "");
  else
    snprintf(dest, capacity, "%s/%s", dir, name ? name : "");
}

static int
akb_mkdir_if_needed(const char *path) {
  if (!path || !path[0])
    return 0;

#if defined(_WIN32)
  if (_mkdir(path) == 0 || errno == EEXIST)
    return 1;
#else
  if (mkdir(path, 0700) == 0 || errno == EEXIST)
    return 1;
#endif

  return 0;
}

static uint64_t
akb_fnv1a64(const unsigned char *data, size_t length) {
  uint64_t hash;
  size_t i;

  hash = UINT64_C(1469598103934665603);
  for (i = 0; i < length; i++) {
    hash ^= data[i];
    hash *= UINT64_C(1099511628211);
  }

  return hash;
}

static const char *
akb_embedded_image_extension(const unsigned char *data, size_t length, const char *mime) {
  if (mime) {
    if (strstr(mime, "png"))
      return "png";
    if (strstr(mime, "jpeg") || strstr(mime, "jpg"))
      return "jpg";
    if (strstr(mime, "webp"))
      return "webp";
    if (strstr(mime, "ktx2"))
      return "ktx2";
  }

  if (data && length >= 8
      && data[0] == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G')
    return "png";
  if (data && length >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF)
    return "jpg";
  if (data && length >= 12
      && memcmp(data, "RIFF", 4) == 0
      && memcmp(data + 8, "WEBP", 4) == 0)
    return "webp";
  if (data && length >= 12
      && data[0] == 0xAB && data[1] == 'K' && data[2] == 'T' && data[3] == 'X'
      && data[4] == ' ' && data[5] == '2')
    return "ktx2";

  return "bin";
}

static int
akb_file_has_size(const char *path, size_t length) {
#if defined(_WIN32)
  struct _stat st;
  if (_stat(path, &st) != 0)
    return 0;
#else
  struct stat st;
  if (stat(path, &st) != 0)
    return 0;
#endif

  return (size_t)st.st_size == length;
}

static int
akb_write_file_once(const char *path, const unsigned char *data, size_t length) {
  FILE *file;
  size_t written;

  if (akb_file_has_size(path, length))
    return 1;

  file = fopen(path, "wb");
  if (!file)
    return 0;

  written = fwrite(data, 1, length, file);
  if (fclose(file) != 0 || written != length) {
    remove(path);
    return 0;
  }

  return 1;
}

static int
akb_copy_embedded_texture_path(AkImage *image, char *dest, size_t capacity) {
  AkInitFrom *init_from;
  AkBuffer *buff;
  const unsigned char *data;
  const char *tmpdir;
  const char *ext;
  char dir[PATH_MAX];
  char filename[128];
  uint64_t hash;
  size_t length;

  if (!image || !dest || capacity == 0)
    return 0;

  init_from = image->initFrom;
  buff = init_from ? init_from->buff : NULL;
  data = buff ? (const unsigned char *)buff->data : NULL;
  length = buff ? buff->length : 0;
  if (!data || length == 0)
    return 0;

  tmpdir = getenv("TMPDIR");
  if (!tmpdir || !tmpdir[0])
    tmpdir = "/tmp";

  akb_path_join(dir, sizeof(dir), tmpdir, "assetkit_blender");
  if (!akb_mkdir_if_needed(dir))
    return 0;

  hash = akb_fnv1a64(data, length);
  ext = akb_embedded_image_extension(data, length, init_from->buffMime);
  snprintf(filename,
           sizeof(filename),
           "texture_%016llx.%s",
           (unsigned long long)hash,
           ext);
  akb_path_join(dest, capacity, dir, filename);

  if (!akb_write_file_once(dest, data, length)) {
    dest[0] = '\0';
    return 0;
  }

  return 1;
}

static void
akb_copy_image_path(AkDoc *doc, AkImage *image, char *dest, size_t capacity) {
  AkInitFrom *init_from;
  const char *path;
  char resolved[PATH_MAX];

  if (!dest || capacity == 0)
    return;
  dest[0] = '\0';

  if (!image)
    return;

  init_from = image->initFrom;
  if (!init_from)
    return;

  path = init_from->resolvedFullPath ? init_from->resolvedFullPath : init_from->ref;
  if (!path || !path[0]) {
    akb_copy_embedded_texture_path(image, dest, capacity);
    return;
  }

  if (path[0] == '/' || !doc || !doc->inf || !doc->inf->dir) {
    snprintf(dest, capacity, "%s", path);
  } else {
    snprintf(dest, capacity, "%s", ak_fullpath(doc, path, resolved));
  }

}

static void
akb_copy_texture_path(AkDoc *doc, AkTextureRef *texref, char *dest, size_t capacity) {
  AkImage *image;

  if (!dest || capacity == 0)
    return;
  dest[0] = '\0';

  if (!texref || !texref->texture || !(image = texref->texture->image))
    return;

  akb_copy_image_path(doc, image, dest, capacity);
}

static AkbTextureInfo *
akb_texture_info_for_role(AkbPrimitive *out, const char *role) {
  uint32_t i;

  if (!out || !role || !role[0])
    return NULL;

  for (i = 0; i < out->texture_info_count; i++) {
    if (strcmp(out->texture_infos[i].role, role) == 0)
      return &out->texture_infos[i];
  }

  if (out->texture_info_count >= AKB_TEXTURE_INFO_MAX)
    return NULL;

  i = out->texture_info_count++;
  memset(&out->texture_infos[i], 0, sizeof(out->texture_infos[i]));
  snprintf(out->texture_infos[i].role, sizeof(out->texture_infos[i].role), "%s", role);
  return &out->texture_infos[i];
}

static int32_t
akb_texref_slot(AkTextureRef *texref, AkInstanceMaterial *inst_mat) {
  AkBindVertexInput *bvi;
  int32_t slot;

  if (!texref)
    return 0;

  slot = texref->slot;
  if (texref->transform && texref->transform->slot > -1)
    slot = texref->transform->slot;

  if (texref->texcoord && inst_mat) {
    for (bvi = inst_mat->bindVertexInput; bvi; bvi = bvi->next) {
      if (bvi->semantic && strcmp(bvi->semantic, texref->texcoord) == 0) {
        slot = (int32_t)bvi->inputSet;
        break;
      }
    }
  }

  return slot >= 0 ? slot : 0;
}

static const char *
akb_texture_role_color_space(const char *role) {
  if (!role)
    return "Non-Color";

  if (strcmp(role, "base_color") == 0
      || strcmp(role, "emissive") == 0
      || strcmp(role, "specular_color") == 0
      || strcmp(role, "sheen_color") == 0
      || strcmp(role, "diffuse_transmission_color") == 0)
    return "sRGB";

  return "Non-Color";
}

static void
akb_texture_ref_color_space(AkTextureRef *texref,
                            const char *role,
                            char *dest,
                            size_t capacity) {
  AkTextureColorSpace color_space;
  const char *name;

  if (!dest || capacity == 0)
    return;

  color_space = texref ? texref->colorSpace : AK_TEXTURE_COLORSPACE_UNSPECIFIED;
  if (color_space == AK_TEXTURE_COLORSPACE_SRGB)
    name = "sRGB";
  else if (color_space == AK_TEXTURE_COLORSPACE_LINEAR)
    name = "Non-Color";
  else
    name = akb_texture_role_color_space(role);

  snprintf(dest, capacity, "%s", name);
}

static const char *
akb_texture_role_channels(const char *role) {
  if (!role)
    return "";

  if (strcmp(role, "occlusion") == 0
      || strcmp(role, "clearcoat") == 0
      || strcmp(role, "transmission") == 0
      || strcmp(role, "iridescence") == 0)
    return "R";
  if (strcmp(role, "metallic_roughness") == 0)
    return "GB";
  if (strcmp(role, "clearcoat_roughness") == 0
      || strcmp(role, "iridescence_thickness") == 0
      || strcmp(role, "volume_thickness") == 0)
    return "G";
  if (strcmp(role, "specular") == 0
      || strcmp(role, "diffuse_transmission") == 0)
    return "A";
  if (strcmp(role, "base_color") == 0
      || strcmp(role, "emissive") == 0
      || strcmp(role, "normal") == 0
      || strcmp(role, "clearcoat_normal") == 0
      || strcmp(role, "specular_color") == 0
      || strcmp(role, "sheen_color") == 0
      || strcmp(role, "diffuse_transmission_color") == 0)
    return "RGB";
  if (strcmp(role, "anisotropy") == 0)
    return "RGB";

  return "";
}

static void
akb_texture_ref_channels(AkTextureRef *texref,
                         const char *role,
                         char *dest,
                         size_t capacity) {
  AkTextureChannels channels;
  size_t i;

  if (!dest || capacity == 0)
    return;

  channels = texref ? texref->channels : AK_TEXTURE_CHANNEL_NONE;
  if (channels == AK_TEXTURE_CHANNEL_NONE) {
    snprintf(dest, capacity, "%s", akb_texture_role_channels(role));
    return;
  }

  i = 0;
#define AKB_APPEND_CHANNEL(CHANNEL, LETTER) do {      \
    if ((channels & (CHANNEL)) && i + 1 < capacity) { \
      dest[i++] = (LETTER);                           \
    }                                                 \
  } while (0)

  AKB_APPEND_CHANNEL(AK_TEXTURE_CHANNEL_R, 'R');
  AKB_APPEND_CHANNEL(AK_TEXTURE_CHANNEL_G, 'G');
  AKB_APPEND_CHANNEL(AK_TEXTURE_CHANNEL_B, 'B');
  AKB_APPEND_CHANNEL(AK_TEXTURE_CHANNEL_A, 'A');

#undef AKB_APPEND_CHANNEL

  dest[i] = '\0';
}

static void
akb_copy_texture_info(AkDoc *doc,
                      AkTextureRef *texref,
                      AkInstanceMaterial *inst_mat,
                      const char *role,
                      char *dest,
                      size_t capacity,
                      AkbPrimitive *out) {
  AkbTextureInfo *info;
  AkImage *image;
  AkSampler *sampler;
  AkTextureTransform *transform;

  akb_copy_texture_path(doc, texref, dest, capacity);
  if (!dest || !dest[0])
    return;

  info = akb_texture_info_for_role(out, role);
  if (!info)
    return;

  memset(info->path, 0, sizeof(info->path));
  snprintf(info->path, sizeof(info->path), "%s", dest);
  akb_texture_ref_color_space(texref,
                              role,
                              info->color_space,
                              sizeof(info->color_space));
  akb_texture_ref_channels(texref,
                           role,
                           info->channels,
                           sizeof(info->channels));
  info->slot = akb_texref_slot(texref, inst_mat);

  if (texref->texcoord)
    snprintf(info->texcoord, sizeof(info->texcoord), "%s", texref->texcoord);
  if (texref->coordInputName)
    snprintf(info->coord_input_name, sizeof(info->coord_input_name), "%s", texref->coordInputName);

  image = texref->texture ? texref->texture->image : NULL;
  sampler = texref->texture ? texref->texture->sampler : NULL;
  info->texture_extra = texref->texture ? ak_extra(texref->texture) : NULL;
  info->texref_extra = ak_extra(texref);
  info->image_extra = image ? ak_extra(image) : NULL;
  info->sampler_extra = sampler ? ak_extra(sampler) : NULL;
  if (image && image->name)
    snprintf(info->image_name, sizeof(info->image_name), "%s", image->name);
  if (sampler && sampler->name)
    snprintf(info->sampler_name, sizeof(info->sampler_name), "%s", sampler->name);
  info->wrap_s = sampler ? sampler->wrapS : AK_WRAP_MODE_WRAP;
  info->wrap_t = sampler ? sampler->wrapT : AK_WRAP_MODE_WRAP;
  info->wrap_p = sampler ? sampler->wrapP : AK_WRAP_MODE_WRAP;
  info->min_filter = sampler ? sampler->minfilter : AK_MINFILTER_LINEAR;
  info->mag_filter = sampler ? sampler->magfilter : AK_MAGFILTER_LINEAR;
  info->mip_filter = sampler ? sampler->mipfilter : AK_MIPFILTER_LINEAR;

  transform = texref->transform;
  info->transform_offset[0] = 0.0f;
  info->transform_offset[1] = 0.0f;
  info->transform_scale[0] = 1.0f;
  info->transform_scale[1] = 1.0f;
  info->transform_rotation = 0.0f;
  info->transform_slot = -1;
  info->has_transform = 0;
  if (transform) {
    info->transform_offset[0] = transform->offset[0];
    info->transform_offset[1] = transform->offset[1];
    info->transform_scale[0] = transform->scale[0];
    info->transform_scale[1] = transform->scale[1];
    info->transform_rotation = transform->rotation;
    info->transform_slot = transform->slot;
    info->has_transform = 1;
  }
}

static float
akb_clampf(float value, float min_value, float max_value) {
  if (value < min_value)
    return min_value;
  if (value > max_value)
    return max_value;
  return value;
}

static float
akb_luminance3(const float color[3]) {
  return color[0] * 0.2126f + color[1] * 0.7152f + color[2] * 0.0722f;
}

static int
akb_tree_has_name(const AkTreeNode *node, const char *name, unsigned int depth) {
  const AkTreeNode *child;

  if (!node || !name || depth > 64)
    return 0;
  if (node->name && strcmp(node->name, name) == 0)
    return 1;

  for (child = node->chld; child; child = child->next) {
    if (akb_tree_has_name(child, name, depth + 1))
      return 1;
  }

  return 0;
}

static AkEffect *
akb_primitive_effect(AkMeshPrimitive *prim,
                     AkBindMaterial *bind_material,
                     AkMaterial **mat_out,
                     AkInstanceMaterial **inst_mat_out) {
  AkMaterial *mat;
  AkInstanceMaterial *inst_mat;
  AkEffect *effect;

  mat = prim ? prim->material : NULL;
  inst_mat = NULL;
  effect = NULL;

  if (mat) {
    effect = mat->effect ? (AkEffect *)ak_instanceObject(&mat->effect->base) : NULL;
  } else if (bind_material) {
    effect = ak_effectForBindMaterial(bind_material, prim, &inst_mat);
    if (inst_mat)
      mat = (AkMaterial *)ak_instanceObject(&inst_mat->base);
  }

  if (mat_out)
    *mat_out = mat;
  if (inst_mat_out)
    *inst_mat_out = inst_mat;

  return effect;
}

static void
akb_extract_material(AkDoc *doc,
                     AkMeshPrimitive *prim,
                     AkBindMaterial *bind_material,
                     AkbPrimitive *out) {
  AkMaterial *mat;
  AkInstanceMaterial *inst_mat;
  AkEffect *effect;
  AkTechniqueFxCommon *cmn;
  int is_specular_glossiness;

  out->base_color[0] = 1.0f;
  out->base_color[1] = 1.0f;
  out->base_color[2] = 1.0f;
  out->base_color[3] = 1.0f;
  out->transparent_color[0] = 1.0f;
  out->transparent_color[1] = 1.0f;
  out->transparent_color[2] = 1.0f;
  out->transparent_color[3] = 1.0f;
  out->emissive_color[0] = 0.0f;
  out->emissive_color[1] = 0.0f;
  out->emissive_color[2] = 0.0f;
  out->specular_color[0] = 1.0f;
  out->specular_color[1] = 1.0f;
  out->specular_color[2] = 1.0f;
  out->sheen_color[0] = 0.0f;
  out->sheen_color[1] = 0.0f;
  out->sheen_color[2] = 0.0f;
  out->volume_attenuation_color[0] = 1.0f;
  out->volume_attenuation_color[1] = 1.0f;
  out->volume_attenuation_color[2] = 1.0f;
  out->diffuse_transmission_color[0] = 1.0f;
  out->diffuse_transmission_color[1] = 1.0f;
  out->diffuse_transmission_color[2] = 1.0f;
  out->metallic = 1.0f;
  out->roughness = 1.0f;
  out->alpha_cutoff = 0.5f;
  out->transparent_amount = 1.0f;
  out->opacity = 1.0f;
  out->normal_scale = 1.0f;
  out->occlusion_strength = 1.0f;
  out->emissive_strength = 1.0f;
  out->specular_strength = 1.0f;
  out->ior = 1.5f;
  out->clearcoat_normal_scale = 1.0f;
  out->iridescence_ior = 1.3f;
  out->iridescence_thickness_minimum = 100.0f;
  out->iridescence_thickness_maximum = 400.0f;
  out->volume_attenuation_distance = 1000000.0f;

  mat = prim ? prim->material : NULL;
  inst_mat = NULL;
  effect = NULL;

  if (mat) {
    effect = mat->effect ? (AkEffect *)ak_instanceObject(&mat->effect->base) : NULL;
  } else if (bind_material) {
    effect = ak_effectForBindMaterial(bind_material, prim, &inst_mat);
    if (inst_mat)
      mat = (AkMaterial *)ak_instanceObject(&inst_mat->base);
  }

  if (!mat && !effect)
    return;

  if (mat && mat->name) {
    snprintf(out->material_name,
             sizeof(out->material_name),
             "%s",
             akb_name(mat->name, "AssetKitMaterial"));
  } else if (inst_mat && inst_mat->symbol) {
    snprintf(out->material_name,
             sizeof(out->material_name),
             "%s",
             akb_name(inst_mat->symbol, "AssetKitMaterial"));
  }

  cmn = effect ? ak_getProfileTechniqueCommon(effect) : NULL;
  if (mat)
    out->material_extra = ak_extra(mat);
  if (effect)
    out->effect_extra = ak_extra(effect);
  if (!cmn)
    return;

  is_specular_glossiness = akb_tree_has_name(out->material_extra,
                                             "KHR_materials_pbrSpecularGlossiness",
                                             0);
  out->material_type = (uint32_t)cmn->type;
  if (is_specular_glossiness)
    out->material_type = AKB_MATERIAL_SPECULAR_GLOSSINESS;

#define AKB_COPY_TEX(ROLE, TEXREF, DEST) \
  akb_copy_texture_info(doc, (TEXREF), inst_mat, (ROLE), (DEST), sizeof(DEST), out)

  out->double_sided = cmn->doubleSided ? 1 : 0;

  if (cmn->albedo) {
    if (cmn->albedo->color) {
      out->base_color[0] = cmn->albedo->color->vec[0];
      out->base_color[1] = cmn->albedo->color->vec[1];
      out->base_color[2] = cmn->albedo->color->vec[2];
      out->base_color[3] = cmn->albedo->color->vec[3];
    }
    AKB_COPY_TEX("base_color", cmn->albedo->texture, out->base_color_texture);
  }

  if (cmn->metalness) {
    out->metallic = cmn->metalness->intensity;
    AKB_COPY_TEX("metallic_roughness", cmn->metalness->tex, out->metallic_roughness_texture);
  }
  if (cmn->roughness)
    out->roughness = cmn->roughness->intensity;

  if (cmn->normal) {
    out->normal_scale = cmn->normal->scale == 0.0f ? 1.0f : cmn->normal->scale;
    AKB_COPY_TEX("normal", cmn->normal->tex, out->normal_texture);
  }

  if (cmn->occlusion) {
    out->occlusion_strength = cmn->occlusion->strength == 0.0f ? 1.0f : cmn->occlusion->strength;
    AKB_COPY_TEX("occlusion", cmn->occlusion->tex, out->occlusion_texture);
  }

  if (cmn->specular) {
    out->specular_strength = cmn->specular->strength;
    if (cmn->specular->color) {
      if (cmn->specular->color->color) {
        out->specular_color[0] = cmn->specular->color->color->vec[0];
        out->specular_color[1] = cmn->specular->color->color->vec[1];
        out->specular_color[2] = cmn->specular->color->color->vec[2];
      }
      AKB_COPY_TEX("specular_color", cmn->specular->color->texture, out->specular_color_texture);
    }
    AKB_COPY_TEX("specular", cmn->specular->specularTex, out->specular_texture);
  }
  if (is_specular_glossiness) {
    out->metallic = 0.0f;
    out->roughness = 1.0f - akb_clampf(out->specular_strength, 0.0f, 1.0f);
  }

  out->ior = cmn->ior > 0.0f ? cmn->ior : out->ior;

  if (cmn->clearcoat) {
    out->clearcoat = cmn->clearcoat->intensity;
    out->clearcoat_roughness = cmn->clearcoat->roughness;
    out->clearcoat_normal_scale = cmn->clearcoat->normalScale == 0.0f ? 1.0f : cmn->clearcoat->normalScale;
    AKB_COPY_TEX("clearcoat", cmn->clearcoat->texture, out->clearcoat_texture);
    AKB_COPY_TEX("clearcoat_roughness",
                 cmn->clearcoat->roughnessTexture,
                 out->clearcoat_roughness_texture);
    AKB_COPY_TEX("clearcoat_normal",
                 cmn->clearcoat->normalTexture,
                 out->clearcoat_normal_texture);
  }

  if (cmn->transmission) {
    out->transmission = cmn->transmission->factor;
    AKB_COPY_TEX("transmission", cmn->transmission->texture, out->transmission_texture);
  }

  if (cmn->sheen) {
    out->has_sheen = 1;
    out->sheen_roughness = cmn->sheen->roughness;
    if (cmn->sheen->color) {
      if (cmn->sheen->color->color) {
        out->sheen_color[0] = cmn->sheen->color->color->vec[0];
        out->sheen_color[1] = cmn->sheen->color->color->vec[1];
        out->sheen_color[2] = cmn->sheen->color->color->vec[2];
      }
      AKB_COPY_TEX("sheen_color", cmn->sheen->color->texture, out->sheen_color_texture);
    }
    AKB_COPY_TEX("sheen_roughness", cmn->sheen->roughnessTexture, out->sheen_roughness_texture);
  }

  if (cmn->iridescence) {
    out->iridescence = cmn->iridescence->factor;
    out->iridescence_ior = cmn->iridescence->ior > 0.0f
                           ? cmn->iridescence->ior
                           : out->iridescence_ior;
    out->iridescence_thickness_minimum = cmn->iridescence->thicknessMinimum;
    out->iridescence_thickness_maximum = cmn->iridescence->thicknessMaximum;
    AKB_COPY_TEX("iridescence", cmn->iridescence->texture, out->iridescence_texture);
    AKB_COPY_TEX("iridescence_thickness",
                 cmn->iridescence->thicknessTexture,
                 out->iridescence_thickness_texture);
  }

  if (cmn->volume) {
    out->volume_thickness = cmn->volume->thicknessFactor;
    out->volume_attenuation_distance = cmn->volume->attenuationDistance > 0.0f
                                       ? cmn->volume->attenuationDistance
                                       : out->volume_attenuation_distance;
    out->volume_attenuation_color[0] = cmn->volume->attenuationColor.vec[0];
    out->volume_attenuation_color[1] = cmn->volume->attenuationColor.vec[1];
    out->volume_attenuation_color[2] = cmn->volume->attenuationColor.vec[2];
    AKB_COPY_TEX("volume_thickness", cmn->volume->thicknessTexture, out->volume_thickness_texture);
  }

  if (cmn->anisotropy) {
    out->anisotropy = cmn->anisotropy->strength;
    out->anisotropy_rotation = cmn->anisotropy->rotation;
    AKB_COPY_TEX("anisotropy", cmn->anisotropy->texture, out->anisotropy_texture);
  }

  if (cmn->diffuseTransmission) {
    out->diffuse_transmission = cmn->diffuseTransmission->factor;
    if (cmn->diffuseTransmission->color) {
      if (cmn->diffuseTransmission->color->color) {
        out->diffuse_transmission_color[0] = cmn->diffuseTransmission->color->color->vec[0];
        out->diffuse_transmission_color[1] = cmn->diffuseTransmission->color->color->vec[1];
        out->diffuse_transmission_color[2] = cmn->diffuseTransmission->color->color->vec[2];
      }
      AKB_COPY_TEX("diffuse_transmission_color",
                   cmn->diffuseTransmission->color->texture,
                   out->diffuse_transmission_color_texture);
    }
    AKB_COPY_TEX("diffuse_transmission",
                 cmn->diffuseTransmission->texture,
                 out->diffuse_transmission_texture);
  }

  if (cmn->dispersion)
    out->dispersion = cmn->dispersion->dispersion;

  if (cmn->emission) {
    out->emissive_strength = cmn->emission->strength;
    if (cmn->emission->color.color) {
      out->emissive_color[0] = cmn->emission->color.color->vec[0];
      out->emissive_color[1] = cmn->emission->color.color->vec[1];
      out->emissive_color[2] = cmn->emission->color.color->vec[2];
    }
    AKB_COPY_TEX("emissive", cmn->emission->color.texture, out->emissive_texture);
  }

  if (cmn->transparent) {
    float opacity;
    float alpha;
    float luminance;

    out->alpha_cutoff = cmn->transparent->cutoff;
    out->transparent_amount = cmn->transparent->amount;
    out->transparent_opaque = (uint8_t)cmn->transparent->opaque;

    if (cmn->transparent->color) {
      if (cmn->transparent->color->color) {
        out->transparent_color[0] = cmn->transparent->color->color->vec[0];
        out->transparent_color[1] = cmn->transparent->color->color->vec[1];
        out->transparent_color[2] = cmn->transparent->color->color->vec[2];
        out->transparent_color[3] = cmn->transparent->color->color->vec[3];
      }
      AKB_COPY_TEX("transparent", cmn->transparent->color->texture, out->transparent_texture);
    }

    alpha = out->transparent_color[3];
    luminance = akb_luminance3(out->transparent_color);
    opacity = out->base_color[3];

    switch (cmn->transparent->opaque) {
      case AK_OPAQUE_BLEND:
        opacity = out->base_color[3] * out->transparent_amount;
        out->alpha_mode = 1;
        break;
      case AK_OPAQUE_MASK:
        opacity = out->base_color[3] * out->transparent_amount;
        out->alpha_mode = 2;
        break;
      case AK_OPAQUE_A_ONE:
        opacity = alpha * out->transparent_amount;
        out->alpha_mode = opacity < 0.999f || out->transparent_texture[0] ? 1 : 0;
        break;
      case AK_OPAQUE_A_ZERO:
        opacity = 1.0f - alpha * out->transparent_amount;
        out->alpha_mode = opacity < 0.999f || out->transparent_texture[0] ? 1 : 0;
        break;
      case AK_OPAQUE_RGB_ONE:
        opacity = luminance * out->transparent_amount;
        out->alpha_mode = opacity < 0.999f || out->transparent_texture[0] ? 1 : 0;
        break;
      case AK_OPAQUE_RGB_ZERO:
        opacity = 1.0f - luminance * out->transparent_amount;
        out->alpha_mode = opacity < 0.999f || out->transparent_texture[0] ? 1 : 0;
        break;
      default:
        out->alpha_mode = out->base_color[3] < 1.0f ? 1 : 0;
        break;
    }
    out->opacity = akb_clampf(opacity, 0.0f, 1.0f);
    out->base_color[3] = out->opacity;
  } else {
    out->alpha_mode = out->base_color[3] < 1.0f ? 1 : 0;
    out->opacity = out->base_color[3];
  }

#undef AKB_COPY_TEX
}

static const char *
akb_material_variant_name(AkDoc *doc, uint32_t index) {
  AkMaterialVariant *variant;
  uint32_t i;

  variant = doc ? doc->materialVariants : NULL;
  for (i = 0; variant && i < index; i++)
    variant = variant->next;

  return variant ? variant->name : NULL;
}

static int
akb_extract_material_variants(AkDoc *doc, AkMeshPrimitive *prim, AkbPrimitive *out) {
  AkMaterialVariantMapping *mapping;
  AkbMaterialVariantMap *items;
  const char *variant_name;
  const char *material_name;
  uint32_t i;

  if (!doc || !prim || !out || !prim->variantMappings || prim->variantMappingCount == 0)
    return 1;

  items = (AkbMaterialVariantMap *)calloc(prim->variantMappingCount, sizeof(*items));
  if (!items)
    return 0;

  i = 0;
  for (mapping = prim->variantMappings;
       mapping && i < prim->variantMappingCount;
       mapping = mapping->next) {
    items[i].variant_index = mapping->variantIndex;
    items[i].material = mapping->material;
    variant_name = akb_material_variant_name(doc, mapping->variantIndex);
    material_name = mapping->material ? mapping->material->name : NULL;

    if (variant_name && variant_name[0])
      snprintf(items[i].variant_name, sizeof(items[i].variant_name), "%s", variant_name);
    if (material_name && material_name[0])
      snprintf(items[i].material_name, sizeof(items[i].material_name), "%s", material_name);
    i++;
  }

  if (!i) {
    free(items);
    return 1;
  }

  out->material_variants = items;
  out->material_variant_count = i;
  return 1;
}

static const uint32_t *
akb_indices_data(AkUIntArray *indices, size_t *count_out) {
  *count_out = 0;
  if (!indices || indices->count == 0)
    return NULL;
  *count_out = indices->count;
  return indices->items;
}

static float *
akb_accessor_float_borrow(AkAccessor *acc, uint32_t width, uint32_t *count_out) {
  size_t stride;
  char *base;

  *count_out = 0;
  if (!acc || !acc->buffer || !acc->buffer->data || acc->count == 0)
    return NULL;

  stride = acc->byteStride ? acc->byteStride : acc->fillByteSize;
  if (acc->componentType != AKT_FLOAT
      || acc->componentCount != width
      || stride != (size_t)width * sizeof(float)
      || acc->fillByteSize != (size_t)width * sizeof(float))
    return NULL;

  if (acc->byteOffset + (size_t)acc->count * stride > acc->buffer->length)
    return NULL;

  base = (char *)acc->buffer->data + acc->byteOffset;
  *count_out = acc->count;
  return (float *)base;
}

static float *
akb_accessor_float_copy(AkAccessor *acc, uint32_t width, uint32_t *count_out) {
  float *out;
  float *tmp;
  size_t total;
  size_t written;
  uint32_t comp_count, i, j;

  *count_out = 0;
  if (!acc || acc->count == 0)
    return NULL;

  comp_count = acc->componentCount ? acc->componentCount : width;
  total = (size_t)acc->count * width;
  out = (float *)calloc(total, sizeof(float));
  if (!out)
    return NULL;

  if (comp_count == width) {
    written = ak_accessorAsFloat(acc, out, total);
    if (written == 0) {
      free(out);
      return NULL;
    }
    *count_out = acc->count;
    return out;
  }

  tmp = (float *)calloc((size_t)acc->count * comp_count, sizeof(float));
  if (!tmp) {
    free(out);
    return NULL;
  }

  written = ak_accessorAsFloat(acc, tmp, (size_t)acc->count * comp_count);
  if (written == 0) {
    free(tmp);
    free(out);
    return NULL;
  }

  for (i = 0; i < acc->count; i++) {
    for (j = 0; j < width; j++) {
      if (j < comp_count)
        out[(size_t)i * width + j] = tmp[(size_t)i * comp_count + j];
    }
  }

  free(tmp);
  *count_out = acc->count;
  return out;
}

static float *
akb_instance_attr_values(AkAccessor *acc,
                         uint32_t width,
                         uint32_t expected_count,
                         uint8_t *borrowed) {
  float *values;
  uint32_t count;

  *borrowed = 0;
  values = akb_accessor_float_borrow(acc, width, &count);
  if (values) {
    if (count != expected_count)
      return NULL;
    *borrowed = 1;
    return values;
  }

  values = akb_accessor_float_copy(acc, width, &count);
  if (!values)
    return NULL;
  if (count != expected_count) {
    free(values);
    return NULL;
  }

  return values;
}

static void
akb_trs_to_matrix(const float *translation,
                  const float *rotation,
                  const float *scale,
                  float *dest) {
  CGLM_ALIGN_MAT mat4 matrix;
  CGLM_ALIGN(8) vec3 scale3;
  versor quat;

  if (rotation) {
    quat[0] = rotation[0];
    quat[1] = rotation[1];
    quat[2] = rotation[2];
    quat[3] = rotation[3];
    glm_quat_normalize(quat);
  } else {
    glm_quat_identity(quat);
  }

  glm_quat_mat4(quat, matrix);

  scale3[0] = scale ? scale[0] : 1.0f;
  scale3[1] = scale ? scale[1] : 1.0f;
  scale3[2] = scale ? scale[2] : 1.0f;
  glm_scale(matrix, scale3);

  matrix[3][0] = translation ? translation[0] : 0.0f;
  matrix[3][1] = translation ? translation[1] : 0.0f;
  matrix[3][2] = translation ? translation[2] : 0.0f;
  matrix[3][3] = 1.0f;

  memcpy(dest, matrix, 16 * sizeof(float));
}

static int
akb_extract_instancing(AkbPrimitive *out, AkNode *node) {
  AkInstanceAttribs *instancing;
  float *translations = NULL;
  float *rotations = NULL;
  float *scales = NULL;
  uint32_t i;
  uint8_t borrowed_translations = 0;
  uint8_t borrowed_rotations = 0;
  uint8_t borrowed_scales = 0;

  if (!node || !node->instancing || node->instancing->count == 0)
    return 1;

  instancing = node->instancing;
  if (instancing->translation) {
    translations = akb_instance_attr_values(instancing->translation,
                                            3,
                                            instancing->count,
                                            &borrowed_translations);
    if (!translations)
      return 0;
  }
  if (instancing->rotation) {
    rotations = akb_instance_attr_values(instancing->rotation,
                                         4,
                                         instancing->count,
                                         &borrowed_rotations);
    if (!rotations)
      goto fail;
  }
  if (instancing->scale) {
    scales = akb_instance_attr_values(instancing->scale,
                                      3,
                                      instancing->count,
                                      &borrowed_scales);
    if (!scales)
      goto fail;
  }

  out->instance_matrices = (float *)malloc((size_t)instancing->count * 16 * sizeof(float));
  if (!out->instance_matrices)
    goto fail;

  for (i = 0; i < instancing->count; i++) {
    akb_trs_to_matrix(translations ? translations + (size_t)i * 3 : NULL,
                      rotations ? rotations + (size_t)i * 4 : NULL,
                      scales ? scales + (size_t)i * 3 : NULL,
                      out->instance_matrices + (size_t)i * 16);
  }
  out->instance_count = instancing->count;

  if (translations && !borrowed_translations)
    free(translations);
  if (rotations && !borrowed_rotations)
    free(rotations);
  if (scales && !borrowed_scales)
    free(scales);
  return 1;

fail:
  if (translations && !borrowed_translations)
    free(translations);
  if (rotations && !borrowed_rotations)
    free(rotations);
  if (scales && !borrowed_scales)
    free(scales);
  return 0;
}

static float *
akb_loop_attribute_copy(AkMeshPrimitive *prim,
                        AkInput *input,
                        const uint32_t *raw_indices,
                        size_t raw_count,
                        const uint32_t *vertex_indices,
                        uint32_t loop_count,
                        uint32_t width,
                        int flip_v,
                        uint8_t *has_attr) {
  float *values, *out;
  uint32_t value_count = 0;
  uint32_t stride, offset, i, j, idx;

  *has_attr = 0;
  if (!input || !input->accessor || loop_count == 0)
    return NULL;

  values = akb_accessor_float_copy(input->accessor, width, &value_count);
  if (!values || value_count == 0) {
    free(values);
    return NULL;
  }

  if (value_count == loop_count) {
    if (flip_v && width >= 2) {
      for (i = 0; i < loop_count; i++)
        values[(size_t)i * width + 1] = 1.0f - values[(size_t)i * width + 1];
    }
    *has_attr = 1;
    return values;
  }

  out = (float *)calloc((size_t)loop_count * width, sizeof(float));
  if (!out) {
    free(values);
    return NULL;
  }

  stride = prim->indexStride ? prim->indexStride : 1;
  offset = input->offset;

  for (i = 0; i < loop_count; i++) {
    if (value_count == loop_count) {
      idx = i;
    } else if (raw_indices && ((size_t)i * stride + offset) < raw_count) {
      idx = raw_indices[(size_t)i * stride + offset];
    } else {
      idx = vertex_indices[i];
    }

    if (idx >= value_count)
      continue;

    for (j = 0; j < width; j++)
      out[(size_t)i * width + j] = values[(size_t)idx * width + j];

    if (flip_v && width >= 2)
      out[(size_t)i * width + 1] = 1.0f - out[(size_t)i * width + 1];
  }

  free(values);
  *has_attr = 1;
  return out;
}

static int
akb_input_matches(AkInput *input,
                  AkInputSemantic semantic_a,
                  AkInputSemantic semantic_b,
                  const char *raw_a,
                  const char *raw_b) {
  return input
         && (input->semantic == semantic_a
             || input->semantic == semantic_b
             || (raw_a && akb_raw_semantic_is(input, raw_a))
             || (raw_b && akb_raw_semantic_is(input, raw_b)));
}

static void
akb_fill_missing_components(float *values,
                            uint32_t loop_count,
                            uint32_t width,
                            uint32_t source_width,
                            float default_value) {
  uint32_t i, j;

  if (!values || source_width >= width)
    return;

  for (i = 0; i < loop_count; i++) {
    for (j = source_width; j < width; j++)
      values[(size_t)i * width + j] = default_value;
  }
}

static void
akb_loop_attr_name(AkbLoopFloatAttribute *attr,
                   const char *prefix,
                   uint32_t fallback_index) {
  uint32_t set;

  if (!attr || !prefix)
    return;

  set = attr->set;
  if (strcmp(prefix, "UVMap") == 0) {
    if (set == 0)
      snprintf(attr->name, sizeof(attr->name), "UVMap");
    else
      snprintf(attr->name, sizeof(attr->name), "UVMap.%03u", set);
  } else if (strcmp(prefix, "Color") == 0) {
    if (set == 0)
      snprintf(attr->name, sizeof(attr->name), "Color");
    else
      snprintf(attr->name, sizeof(attr->name), "Color.%03u", set);
  } else {
    snprintf(attr->name, sizeof(attr->name), "%s.%03u", prefix, fallback_index);
  }
}

static int
akb_extract_loop_float_attrs(AkbPrimitive *out,
                             AkMeshPrimitive *prim,
                             const uint32_t *raw_indices,
                             size_t raw_count,
                             const uint32_t *vertex_indices,
                             uint32_t loop_count,
                             AkInputSemantic semantic_a,
                             AkInputSemantic semantic_b,
                             const char *raw_a,
                             const char *raw_b,
                             uint32_t width,
                             int flip_v,
                             float missing_default,
                             const char *name_prefix,
                             AkbLoopFloatAttribute **attrs_out,
                             uint32_t *count_out) {
  AkbLoopFloatAttribute *attrs;
  AkInput *input;
  uint32_t max_count, count;
  uint8_t has_attr;

  (void)out;

  if (!attrs_out || !count_out)
    return 0;

  *attrs_out = NULL;
  *count_out = 0;
  if (!prim || !loop_count)
    return 1;

  max_count = 0;
  for (input = prim->input; input; input = input->next) {
    if (input->accessor
        && akb_input_matches(input, semantic_a, semantic_b, raw_a, raw_b))
      max_count++;
  }

  if (!max_count)
    return 1;

  attrs = (AkbLoopFloatAttribute *)calloc(max_count, sizeof(*attrs));
  if (!attrs)
    return 0;

  count = 0;
  for (input = prim->input; input; input = input->next) {
    if (!input->accessor
        || !akb_input_matches(input, semantic_a, semantic_b, raw_a, raw_b))
      continue;

    has_attr = 0;
    attrs[count].values = akb_loop_attribute_copy(prim,
                                                  input,
                                                  raw_indices,
                                                  raw_count,
                                                  vertex_indices,
                                                  loop_count,
                                                  width,
                                                  flip_v,
                                                  &has_attr);
    if (!attrs[count].values || !has_attr)
      continue;

    attrs[count].width = width;
    attrs[count].set = input->set;
    akb_fill_missing_components(attrs[count].values,
                                loop_count,
                                width,
                                input->accessor->componentCount,
                                missing_default);
    akb_loop_attr_name(&attrs[count], name_prefix, count);
    count++;
  }

  if (!count) {
    free(attrs);
    return 1;
  }

  *attrs_out = attrs;
  *count_out = count;
  return 1;
}

static int
akb_raw_semantic_starts_with(AkInput *input, const char *prefix) {
  size_t len;

  if (!input || !input->semanticRaw || !prefix)
    return 0;

  len = strlen(prefix);
  return strncmp(input->semanticRaw, prefix, len) == 0;
}

static int
akb_point_attr_candidate(AkInput *input, uint32_t primitive_type) {
  if (!input || !input->accessor || input->accessor->count == 0)
    return 0;
  if (input->semantic == AK_INPUT_POSITION)
    return 0;
  if (!input->semanticRaw)
    return 0;

  if (akb_raw_semantic_starts_with(input, "_")
      || akb_raw_semantic_starts_with(input, "KHR_"))
    return 1;

  if (input->semantic == AK_INPUT_COLOR)
    return primitive_type == AKB_PRIMITIVE_POINTS
           || primitive_type == AKB_PRIMITIVE_LINES;
  if (primitive_type != AKB_PRIMITIVE_POINTS
      && primitive_type != AKB_PRIMITIVE_LINES)
    return 0;
  if (primitive_type == AKB_PRIMITIVE_LINES)
    return akb_raw_semantic_starts_with(input, "COLOR");
  if (input->semantic != AK_INPUT_OTHER)
    return 0;

  return akb_raw_semantic_is(input, "OPACITY")
         || akb_raw_semantic_is(input, "SCALE")
         || akb_raw_semantic_is(input, "ROTATION")
         || akb_raw_semantic_starts_with(input, "COLOR");
}

static uint32_t
akb_point_attr_width(AkInput *input) {
  uint32_t width;

  if (!input || !input->accessor)
    return 0;

  if (input->semantic == AK_INPUT_COLOR || akb_raw_semantic_starts_with(input, "COLOR"))
    return 4;

  width = input->accessor->componentCount ? input->accessor->componentCount : 1;
  return width > 4 ? 4 : width;
}

static void
akb_point_attr_name(AkbLoopFloatAttribute *attr, AkInput *input, uint32_t fallback_index) {
  const char *raw;

  if (!attr || !input)
    return;

  raw = input->semanticRaw;
  attr->set = input->set;

  if (input->semantic == AK_INPUT_COLOR || akb_raw_semantic_starts_with(input, "COLOR")) {
    if (input->set == 0)
      snprintf(attr->name, sizeof(attr->name), "Color");
    else
      snprintf(attr->name, sizeof(attr->name), "Color.%03u", input->set);
  } else if (raw && strcmp(raw, "OPACITY") == 0) {
    snprintf(attr->name, sizeof(attr->name), "assetkit_opacity");
  } else if (raw && strcmp(raw, "SCALE") == 0) {
    snprintf(attr->name, sizeof(attr->name), "assetkit_scale");
  } else if (raw && strcmp(raw, "ROTATION") == 0) {
    snprintf(attr->name, sizeof(attr->name), "assetkit_rotation");
  } else if (raw && (raw[0] == '_' || strncmp(raw, "KHR_", 4) == 0)) {
    snprintf(attr->name, sizeof(attr->name), "%s", raw);
  } else if (raw && raw[0]) {
    snprintf(attr->name, sizeof(attr->name), "assetkit_%s", raw);
  } else {
    snprintf(attr->name, sizeof(attr->name), "assetkit_point_attr.%03u", fallback_index);
  }
}

static int
akb_extract_point_float_attrs(AkbPrimitive *out,
                              AkMeshPrimitive *prim,
                              AkbSharedDoc *doc_owner) {
  AkbLoopFloatAttribute *attrs;
  AkInput *input;
  float *values;
  uint32_t max_count, count, value_count, width;
  uint8_t borrowed;

  if (!out || !prim || !out->vertex_count)
    return 1;

  max_count = 0;
  for (input = prim->input; input; input = input->next) {
    if (akb_point_attr_candidate(input, out->primitive_type))
      max_count++;
  }

  if (!max_count)
    return 1;

  attrs = (AkbLoopFloatAttribute *)calloc(max_count, sizeof(*attrs));
  if (!attrs)
    return 0;

  count = 0;
  for (input = prim->input; input; input = input->next) {
    if (!akb_point_attr_candidate(input, out->primitive_type))
      continue;

    width = akb_point_attr_width(input);
    if (!width)
      continue;

    borrowed = 0;
    values = akb_accessor_float_borrow(input->accessor, width, &value_count);
    if (values) {
      borrowed = 1;
    } else {
      values = akb_accessor_float_copy(input->accessor, width, &value_count);
      borrowed = 0;
    }

    if (!values || value_count != out->vertex_count) {
      if (values && !borrowed)
        free(values);
      continue;
    }

    attrs[count].values = values;
    attrs[count].width = width;
    attrs[count].borrowed = borrowed;
    akb_fill_missing_components(attrs[count].values,
                                out->vertex_count,
                                width,
                                input->accessor->componentCount,
                                input->semantic == AK_INPUT_COLOR
                                || akb_raw_semantic_starts_with(input, "COLOR")
                                ? 1.0f
                                : 0.0f);
    akb_point_attr_name(&attrs[count], input, count);
    if (borrowed)
      akb_primitive_retain_doc(out, doc_owner);
    count++;
  }

  if (!count) {
    free(attrs);
    return 1;
  }

  out->point_attrs = attrs;
  out->point_attr_count = count;
  return 1;
}

static AkMorphInspectMorphable *
akb_morphable_at(AkMorphInspectTargetView *view, uint32_t index) {
  AkMorphInspectMorphable *morphable;
  uint32_t i;

  morphable = view ? view->morphable : NULL;
  for (i = 0; morphable && i < index; i++)
    morphable = morphable->next;
  return morphable;
}

static AkInput *
akb_morph_position_input(AkMorphInspectMorphable *morphable) {
  AkMorphInspectInput *input;

  for (input = morphable ? morphable->input : NULL; input; input = input->next) {
    if (input->input && input->input->semantic == AK_INPUT_POSITION)
      return input->input;
  }

  return NULL;
}

static float
akb_morph_initial_weight(AkInstanceMorph *morpher, AkMesh *mesh, uint32_t index) {
  AkMorph *morph;

  if (!morpher || !(morph = morpher->morph))
    return 0.0f;
  if (morpher->overrideWeights && index < morpher->overrideWeights->count)
    return morpher->overrideWeights->items[index];
  if (morph->defaultWeights && index < morph->defaultWeights->count)
    return morph->defaultWeights->items[index];
  if (mesh && mesh->weights && index < mesh->weights->count)
    return mesh->weights->items[index];
  return 0.0f;
}

static int
akb_morph_is_relative(AkMorph *morph) {
  return morph && morph->method == AK_MORPH_METHOD_RELATIVE;
}

static int
akb_morph_copy_positions(AkbMorphTarget *target,
                         const float *base_positions,
                         uint32_t base_count,
                         AkInput *position,
                         int relative) {
  float *source;
  float *dest;
  uint32_t source_count = 0;
  uint32_t i;
  uint8_t source_borrowed;

  if (!target || !base_positions || !position || !position->accessor)
    return 0;

  source = akb_accessor_float_borrow(position->accessor, 3, &source_count);
  if (source) {
    source_borrowed = 1;
  } else {
    source = akb_accessor_float_copy(position->accessor, 3, &source_count);
    source_borrowed = 0;
  }

  if (!source || source_count != base_count) {
    if (!source_borrowed)
      free(source);
    return 0;
  }

  dest = (float *)malloc((size_t)base_count * 3 * sizeof(float));
  if (!dest) {
    if (!source_borrowed)
      free(source);
    return 0;
  }

  if (relative) {
    for (i = 0; i < base_count * 3; i++)
      dest[i] = base_positions[i] + source[i];
  } else {
    memcpy(dest, source, (size_t)base_count * 3 * sizeof(float));
  }

  if (!source_borrowed)
    free(source);

  target->positions = dest;
  target->vertex_count = base_count;
  return 1;
}

static int
akb_extract_morph_targets(AkbPrimitive *out,
                          AkGeometry *geom,
                          AkMesh *mesh,
                          AkMeshPrimitive *prim,
                          uint32_t prim_index,
                          AkInstanceMorph *morpher) {
  AkInputSemantic desired[1] = {AK_INPUT_POSITION};
  AkMorph *morph;
  AkMorphInspectView *view;
  AkMorphInspectTargetView *target_view;
  AkMorphInspectMorphable *morphable;
  AkInput *position;
  AkbMorphTarget *targets;
  uint32_t target_index;
  uint32_t write_index;
  const char *target_name;

  (void)prim;

  if (!out || !geom || !mesh || !morpher || !(morph = morpher->morph)
      || !morph->targetCount || !out->vertices || !out->vertex_count)
    return 1;

  out->morph_presets = morph->presets;
  out->morph_preset_count = morph->presetCount;

  view = morph->inspectResult;
  if (!view) {
    if (ak_morphInspect(geom, morph, desired, 1, false, true) != AK_OK)
      return 1;
    view = morph->inspectResult;
  }
  if (!view || !view->targets)
    return 1;

  targets = (AkbMorphTarget *)calloc(morph->targetCount, sizeof(*targets));
  if (!targets)
    return 0;

  write_index = 0;
  target_index = 0;
  for (target_view = view->targets;
       target_view && target_index < morph->targetCount;
       target_view = target_view->next, target_index++) {
    morphable = akb_morphable_at(target_view, prim_index);
    position = akb_morph_position_input(morphable);
    if (!position)
      continue;

    if (!akb_morph_copy_positions(&targets[write_index],
                                  out->vertices,
                                  out->vertex_count,
                                  position,
                                  akb_morph_is_relative(morph)))
      continue;

    target_name = morph->targetNames && target_index < morph->targetCount
                  ? morph->targetNames[target_index]
                  : NULL;
    if (target_name && target_name[0])
      snprintf(targets[write_index].name, sizeof(targets[write_index].name), "%s", target_name);
    else
      snprintf(targets[write_index].name, sizeof(targets[write_index].name), "AssetKitMorph_%u", target_index);

    targets[write_index].weight = akb_morph_initial_weight(morpher, mesh, target_index);
    write_index++;
  }

  if (!write_index) {
    free(targets);
    return 1;
  }

  out->morph_targets = targets;
  out->morph_target_count = write_index;
  return 1;
}

static int32_t
akb_scene_node_index_for(AkbSceneNodeList *nodes, AkNode *node) {
  const char *target_id;
  const char *source_id;
  size_t i;

  if (!nodes || !node)
    return -1;

  target_id = (const char *)ak_mem_getId(node);
  for (i = 0; i < nodes->count; i++) {
    if (nodes->items[i].source == node)
      return (int32_t)i;
    source_id = (const char *)ak_mem_getId(nodes->items[i].source);
    if (source_id && target_id && strcmp(source_id, target_id) == 0)
      return (int32_t)i;
  }

  return -1;
}

static uint32_t
akb_skin_joint_width(AkSkin *skin) {
  uint32_t width;

  width = skin && skin->nMaxJoints
          ? skin->nMaxJoints
          : AKB_SKIN_DEFAULT_JOINTS_PER_VERTEX;
  if (width > AKB_SKIN_MAX_JOINTS_PER_VERTEX)
    return AKB_SKIN_MAX_JOINTS_PER_VERTEX;
  return width;
}

static int
akb_node_is_skin_joint(AkNode *node, AkNode **joints, size_t count) {
  size_t i;

  if (!node || !joints)
    return 0;

  for (i = 0; i < count; i++) {
    if (joints[i] == node)
      return 1;
  }

  return 0;
}

static AkNode *
akb_skin_armature_root(AkNode *root, AkNode **joints, size_t count) {
  if (root) {
    if (akb_node_is_skin_joint(root, joints, count) && root->parent)
      return root->parent;
    return root;
  }

  if (joints && count && joints[0]) {
    if (joints[0]->parent)
      return joints[0]->parent;
    return joints[0];
  }

  return NULL;
}

static int
akb_extract_skin(AkbPrimitive *out,
                 AkbSceneNodeList *nodes,
                 AkMeshPrimitive *prim,
                 uint32_t prim_index,
                 AkInstanceSkin *skinner) {
  AkSkin *skin;
  AkNode *root;
  AkNode **joints;
  AkNode **joint_sources;
  uint16_t *joint_indices;
  int32_t *joint_nodes;
  float *weights;
  float *inverse_bind_matrices;
  size_t filled_count;
  uint32_t joint_width;
  size_t i;

  if (!out || !prim || !skinner || !(skin = skinner->skin)
      || !skin->nJoints || !out->vertex_count)
    return 1;

  joint_width = akb_skin_joint_width(skin);
  joint_indices = (uint16_t *)calloc((size_t)out->vertex_count
                                     * joint_width,
                                     sizeof(*joint_indices));
  weights = (float *)calloc((size_t)out->vertex_count
                            * joint_width,
                            sizeof(*weights));
  if (!joint_indices || !weights) {
    free(joint_indices);
    free(weights);
    return 0;
  }

  filled_count = ak_skinFillWeights(skin,
                                    prim,
                                    prim_index,
                                    joint_width,
                                    joint_indices,
                                    weights);
  if (!filled_count) {
    free(joint_indices);
    free(weights);
    return 1;
  }

  joint_nodes = (int32_t *)malloc((size_t)skin->nJoints * sizeof(*joint_nodes));
  joint_sources = (AkNode **)malloc((size_t)skin->nJoints * sizeof(*joint_sources));
  if (!joint_nodes || !joint_sources) {
    free(joint_sources);
    free(joint_nodes);
    free(joint_indices);
    free(weights);
    return 0;
  }

  joints = skinner->overrideJoints ? skinner->overrideJoints : skin->joints;
  for (i = 0; i < skin->nJoints; i++) {
    joint_sources[i] = joints ? joints[i] : NULL;
    joint_nodes[i] = joint_sources[i]
                     ? akb_scene_node_index_for(nodes, joint_sources[i])
                     : -1;
  }

  inverse_bind_matrices = NULL;
  if (skin->invBindPoses) {
    inverse_bind_matrices = (float *)malloc((size_t)skin->nJoints
                                            * 16
                                            * sizeof(*inverse_bind_matrices));
    if (!inverse_bind_matrices) {
      free(joint_nodes);
      free(joint_sources);
      free(joint_indices);
      free(weights);
      return 0;
    }
    memcpy(inverse_bind_matrices,
           skin->invBindPoses,
           (size_t)skin->nJoints * 16 * sizeof(*inverse_bind_matrices));
  }

  out->skin_joints = joint_indices;
  out->skin_weights = weights;
  out->skin_joint_nodes = joint_nodes;
  out->skin_joint_sources = joint_sources;
  out->skin_inverse_bind_matrices = inverse_bind_matrices;
  memcpy(out->skin_bind_shape_matrix,
         skin->bindShapeMatrix,
         sizeof(out->skin_bind_shape_matrix));
  root = akb_skin_armature_root(skin->skeleton, joint_sources, skin->nJoints);
  out->skin_root_source = root;
  out->skin_root_node_index = akb_scene_node_index_for(nodes, root);
  out->skin_vertex_count = (uint32_t)filled_count;
  out->skin_joint_count = (uint32_t)skin->nJoints;
  out->skin_joint_width = joint_width;
  out->has_skin = 1;
  return 1;
}

static void
akb_mat4_identity(float m[16]) {
  memset(m, 0, 16 * sizeof(float));
  m[0] = 1.0f;
  m[5] = 1.0f;
  m[10] = 1.0f;
  m[15] = 1.0f;
}

static void
akb_mat4_mul(const float a[16], const float b[16], float out[16]) {
  float r[16];
  int col, row;

  for (col = 0; col < 4; col++) {
    for (row = 0; row < 4; row++) {
      r[col * 4 + row] = a[row]      * b[col * 4]
                       + a[4 + row]  * b[col * 4 + 1]
                       + a[8 + row]  * b[col * 4 + 2]
                       + a[12 + row] * b[col * 4 + 3];
    }
  }

  memcpy(out, r, sizeof(r));
}

static void
akb_mat4_inv(const float m[16], float out[16]) {
  CGLM_ALIGN_MAT mat4 in;
  CGLM_ALIGN_MAT mat4 inv;

  memcpy(in, m, 16 * sizeof(float));
  glm_mat4_inv(in, inv);
  memcpy(out, inv, 16 * sizeof(float));
}

static void
akb_node_world_matrix(AkNode *node, float out[16]) {
  if (!node) {
    akb_mat4_identity(out);
    return;
  }

  ak_transformCombineWorld(node, out);
}

static int
akb_ensure_owned_vertices(AkbPrimitive *out) {
  float *copy;

  if (!out || !out->vertices || !out->vertex_count || !out->borrowed_vertices)
    return 1;

  copy = (float *)malloc((size_t)out->vertex_count * 3 * sizeof(*copy));
  if (!copy)
    return 0;

  memcpy(copy, out->vertices, (size_t)out->vertex_count * 3 * sizeof(*copy));
  out->vertices = copy;
  out->borrowed_vertices = 0;
  out->zero_copy_flags &= (uint8_t)~1u;
  return 1;
}

static void
akb_mat4_mul_point3(const float m[16], float v[3]) {
  float x = v[0];
  float y = v[1];
  float z = v[2];
  float w;

  v[0] = m[0] * x + m[4] * y + m[8]  * z + m[12];
  v[1] = m[1] * x + m[5] * y + m[9]  * z + m[13];
  v[2] = m[2] * x + m[6] * y + m[10] * z + m[14];
  w    = m[3] * x + m[7] * y + m[11] * z + m[15];
  if (w != 0.0f && w != 1.0f) {
    v[0] /= w;
    v[1] /= w;
    v[2] /= w;
  }
}

static void
akb_mat4_mul_vec3_normalize(const float m[16], float v[3]) {
  float x = v[0];
  float y = v[1];
  float z = v[2];
  float len;

  v[0] = m[0] * x + m[4] * y + m[8]  * z;
  v[1] = m[1] * x + m[5] * y + m[9]  * z;
  v[2] = m[2] * x + m[6] * y + m[10] * z;

  len = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (len > 1.0e-8f) {
    v[0] /= len;
    v[1] /= len;
    v[2] /= len;
  }
}

static void
akb_skin_vertex_matrix(const AkbPrimitive *out,
                       const float *joint_mats,
                       uint32_t vertex_index,
                       float matrix[16]) {
  uint32_t slot, index;
  uint32_t i;
  float weight, weight_sum;

  memset(matrix, 0, 16 * sizeof(float));
  weight_sum = 0.0f;

  for (slot = 0; slot < out->skin_joint_width; slot++) {
    index = out->skin_joints[(size_t)vertex_index * out->skin_joint_width + slot];
    weight = out->skin_weights[(size_t)vertex_index * out->skin_joint_width + slot];
    if (weight <= 0.0f || index >= out->skin_joint_count)
      continue;

    for (i = 0; i < 16; i++)
      matrix[i] += joint_mats[(size_t)index * 16 + i] * weight;
    weight_sum += weight;
  }

  if (weight_sum > 1.0e-8f) {
    weight = 1.0f / weight_sum;
    for (slot = 0; slot < 16; slot++)
      matrix[slot] *= weight;
  } else {
    memcpy(matrix, joint_mats, 16 * sizeof(float));
  }
}

static int
akb_skin_bind_pose_joint_matrices(AkbPrimitive *out, float **joint_mats_out) {
  float *joint_mats;
  float root_world[16];
  float root_inv[16];
  float bind_world[16];
  float bind_arma[16];
  uint32_t i;

  if (!out || !out->skin_joint_count || !joint_mats_out)
    return 0;

  joint_mats = (float *)malloc((size_t)out->skin_joint_count * 16 * sizeof(*joint_mats));
  if (!joint_mats)
    return 0;

  akb_node_world_matrix(out->skin_root_source, root_world);
  akb_mat4_inv(root_world, root_inv);

  for (i = 0; i < out->skin_joint_count; i++) {
    if (out->skin_inverse_bind_matrices) {
      if (out->skin_joint_sources && out->skin_joint_sources[i])
        akb_node_world_matrix(out->skin_joint_sources[i], bind_world);
      else
        akb_mat4_inv(out->skin_inverse_bind_matrices + (size_t)i * 16, bind_world);
      akb_mat4_mul(root_inv, bind_world, bind_arma);
      akb_mat4_mul(bind_arma,
                   out->skin_inverse_bind_matrices + (size_t)i * 16,
                   joint_mats + (size_t)i * 16);
    } else {
      akb_node_world_matrix(out->skin_joint_sources ? out->skin_joint_sources[i] : NULL,
                            bind_world);
      akb_mat4_mul(root_inv, bind_world, joint_mats + (size_t)i * 16);
    }
  }

  *joint_mats_out = joint_mats;
  return 1;
}

static void
akb_skin_bind_pose_apply_loop_vectors(AkbPrimitive *out, const float *vertex_mats) {
  uint32_t loop_index;
  uint32_t vertex_index;

  if (!out || !vertex_mats || !out->indices)
    return;

  if (out->normals) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      akb_mat4_mul_vec3_normalize(vertex_mats + (size_t)vertex_index * 16,
                                  out->normals + (size_t)loop_index * 3);
    }
  }

  if (out->tangents) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      akb_mat4_mul_vec3_normalize(vertex_mats + (size_t)vertex_index * 16,
                                  out->tangents + (size_t)loop_index * 4);
    }
  }
}

static int
akb_skin_into_bind_pose(AkbPrimitive *out) {
  float *joint_mats;
  float *vertex_mats;
  AkbMorphTarget *target;
  uint32_t vertex_index;
  uint32_t target_index;

  if (!out || !out->has_skin)
    return 1;
  if (!out->skin_joints || !out->skin_weights || !out->skin_joint_count
      || !out->skin_joint_width || out->skin_vertex_count != out->vertex_count
      || !out->skin_inverse_bind_matrices || !out->skin_joint_sources
      || !out->skin_root_source)
    return 1;

  if (!akb_ensure_owned_vertices(out))
    return 0;
  if (!akb_skin_bind_pose_joint_matrices(out, &joint_mats))
    return 0;

  vertex_mats = (float *)malloc((size_t)out->vertex_count * 16 * sizeof(*vertex_mats));
  if (!vertex_mats) {
    free(joint_mats);
    return 0;
  }

  for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
    akb_skin_vertex_matrix(out,
                           joint_mats,
                           vertex_index,
                           vertex_mats + (size_t)vertex_index * 16);
    akb_mat4_mul_point3(vertex_mats + (size_t)vertex_index * 16,
                        out->vertices + (size_t)vertex_index * 3);
  }

  for (target_index = 0; target_index < out->morph_target_count; target_index++) {
    target = &out->morph_targets[target_index];
    if (!target->positions || target->vertex_count != out->vertex_count)
      continue;
    for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
      akb_mat4_mul_point3(vertex_mats + (size_t)vertex_index * 16,
                          target->positions + (size_t)vertex_index * 3);
    }
  }

  akb_skin_bind_pose_apply_loop_vectors(out, vertex_mats);

  out->skin_mesh_in_bind_pose = 1;
  free(vertex_mats);
  free(joint_mats);
  return 1;
}

static void
akb_resolve_skin_joint_nodes(AkbPrimitiveList *list, AkbSceneNodeList *nodes) {
  AkbPrimitive *prim;
  uint32_t i;
  size_t j;

  if (!list || !nodes)
    return;

  for (j = 0; j < list->count; j++) {
    prim = &list->items[j];
    if (!prim->has_skin || !prim->skin_joint_sources || !prim->skin_joint_nodes)
      continue;

    for (i = 0; i < prim->skin_joint_count; i++) {
      prim->skin_joint_nodes[i] = akb_scene_node_index_for(nodes,
                                                           prim->skin_joint_sources[i]);
    }
    prim->skin_root_node_index = akb_scene_node_index_for(nodes,
                                                          prim->skin_root_source);
  }
}

static AkInput *
akb_anim_sampler_input(AkAnimSampler *sampler, AkInputSemantic semantic) {
  AkInput *input;

  if (!sampler)
    return NULL;

  if (semantic == AK_INPUT_INPUT && sampler->inputInput)
    return sampler->inputInput;
  if (semantic == AK_INPUT_OUTPUT && sampler->outputInput)
    return sampler->outputInput;

  for (input = sampler->input; input; input = input->next) {
    if (input->semantic == semantic)
      return input;
  }

  return NULL;
}

static int
akb_anim_target_kind(AkObject *target, uint32_t *width) {
  if (!target)
    return 0;

  switch ((AkTypeId)target->type) {
    case AKT_TRANSLATE:
      *width = 3;
      return AKB_ANIM_TRANSLATION;
    case AKT_QUATERNION:
      *width = 4;
      return AKB_ANIM_ROTATION_QUAT;
    case AKT_SCALE:
      *width = 3;
      return AKB_ANIM_SCALE;
    default:
      break;
  }

  return 0;
}

static int
akb_anim_binding_push(AkbAnimBinding *bindings,
                      int capacity,
                      int count,
                      void *target,
                      uint32_t kind,
                      uint32_t width) {
  if (!target || !kind || !width || count >= capacity)
    return count;
  bindings[count].target = target;
  bindings[count].kind = kind;
  bindings[count].width = width;
  return count + 1;
}

static int
akb_animation_push(AkbAnimation *animation, AkbAnimChannel *channel) {
  AkbAnimChannel *channels;
  size_t capacity;

  if (animation->count == animation->capacity) {
    capacity = animation->capacity ? animation->capacity * 2 : 8;
    channels = (AkbAnimChannel *)realloc(animation->channels,
                                         capacity * sizeof(*channels));
    if (!channels)
      return 0;
    animation->channels = channels;
    animation->capacity = capacity;
  }

  animation->channels[animation->count++] = *channel;
  memset(channel, 0, sizeof(*channel));
  return 1;
}

static int
akb_animation_extract_cubic_values(float **values_io,
                                   float **in_tangents_out,
                                   float **out_tangents_out,
                                   uint32_t *value_count_io,
                                   uint8_t *borrowed_io,
                                   uint32_t time_count,
                                   uint32_t read_width,
                                   uint32_t value_width) {
  float *src;
  float *values;
  float *in_tangents;
  float *out_tangents;
  uint32_t sample_width;
  uint32_t expected_count;
  uint32_t compact_count;
  uint32_t i;

  if (!values_io || !*values_io || !in_tangents_out || !out_tangents_out
      || !value_count_io || !borrowed_io
      || !time_count || !read_width || !value_width)
    return 1;

  sample_width = (read_width == 1 && value_width > 1) ? value_width : read_width;
  expected_count = time_count * 3;
  if (read_width == 1 && value_width > 1)
    expected_count *= value_width;

  if (*value_count_io != expected_count)
    return 1;

  compact_count = time_count * sample_width;
  src = *values_io;
  values = (float *)malloc((size_t)compact_count * sizeof(float));
  in_tangents = (float *)malloc((size_t)compact_count * sizeof(float));
  out_tangents = (float *)malloc((size_t)compact_count * sizeof(float));
  if (!values || !in_tangents || !out_tangents) {
    free(values);
    free(in_tangents);
    free(out_tangents);
    return 0;
  }

  for (i = 0; i < time_count; i++) {
    memcpy(&in_tangents[(size_t)i * sample_width],
           &src[((size_t)i * 3) * sample_width],
           (size_t)sample_width * sizeof(float));
    memcpy(&values[(size_t)i * sample_width],
           &src[((size_t)i * 3 + 1) * sample_width],
           (size_t)sample_width * sizeof(float));
    memcpy(&out_tangents[(size_t)i * sample_width],
           &src[((size_t)i * 3 + 2) * sample_width],
           (size_t)sample_width * sizeof(float));
  }

  if (!*borrowed_io)
    free(src);

  *values_io = values;
  *in_tangents_out = in_tangents;
  *out_tangents_out = out_tangents;
  *borrowed_io = 0;
  *value_count_io = (read_width == 1 && value_width > 1)
                    ? compact_count
                    : time_count;
  return 1;
}

static void
akb_animation_copy_quat_sample(float *dst,
                               const float *src,
                               float sign) {
  dst[0] = sign * src[3];
  dst[1] = sign * src[0];
  dst[2] = sign * src[1];
  dst[3] = sign * src[2];
}

static int
akb_animation_convert_values(AkbAnimChannel *out,
                             float *raw_values,
                             uint32_t raw_count,
                             uint8_t raw_borrowed,
                             const AkbCoordContext *coord) {
  float *values;
  float *in_tangents;
  float *out_tangents;
  float *raw_in_tangents;
  float *raw_out_tangents;
  float dot;
  float sign;
  uint32_t i;

  (void)coord;

  if (out->target != AKB_ANIM_ROTATION_QUAT || out->is_partial) {
    if (out->target == AKB_ANIM_ROTATION_QUAT && out->is_partial) {
      switch (out->target_offset) {
        case 0: out->target_offset = 1; break;
        case 1: out->target_offset = 2; break;
        case 2: out->target_offset = 3; break;
        case 3: out->target_offset = 0; break;
        default: break;
      }
    }
    out->values = raw_values;
    out->borrowed_values = raw_borrowed;
    return 1;
  }

  values = (float *)malloc((size_t)raw_count * 4 * sizeof(float));
  in_tangents = out->in_tangents
                ? (float *)malloc((size_t)raw_count * 4 * sizeof(float))
                : NULL;
  out_tangents = out->out_tangents
                 ? (float *)malloc((size_t)raw_count * 4 * sizeof(float))
                 : NULL;
  if (!values) {
    if (!raw_borrowed)
      free(raw_values);
    if (!out->borrowed_in_tangents)
      free(out->in_tangents);
    if (!out->borrowed_out_tangents)
      free(out->out_tangents);
    out->in_tangents = NULL;
    out->out_tangents = NULL;
    return 0;
  }
  if ((out->in_tangents && !in_tangents)
      || (out->out_tangents && !out_tangents)) {
    free(values);
    free(in_tangents);
    free(out_tangents);
    if (!raw_borrowed)
      free(raw_values);
    if (!out->borrowed_in_tangents)
      free(out->in_tangents);
    if (!out->borrowed_out_tangents)
      free(out->out_tangents);
    out->in_tangents = NULL;
    out->out_tangents = NULL;
    return 0;
  }

  raw_in_tangents = out->in_tangents;
  raw_out_tangents = out->out_tangents;
  for (i = 0; i < raw_count; i++) {
    akb_animation_copy_quat_sample(&values[(size_t)i * 4],
                                   &raw_values[(size_t)i * out->value_width],
                                   1.0f);

    sign = 1.0f;
    if (i > 0) {
      dot = values[(size_t)i * 4] * values[(size_t)(i - 1) * 4]
            + values[(size_t)i * 4 + 1] * values[(size_t)(i - 1) * 4 + 1]
            + values[(size_t)i * 4 + 2] * values[(size_t)(i - 1) * 4 + 2]
            + values[(size_t)i * 4 + 3] * values[(size_t)(i - 1) * 4 + 3];
      if (dot < 0.0f) {
        sign = -1.0f;
        values[(size_t)i * 4]     = -values[(size_t)i * 4];
        values[(size_t)i * 4 + 1] = -values[(size_t)i * 4 + 1];
        values[(size_t)i * 4 + 2] = -values[(size_t)i * 4 + 2];
        values[(size_t)i * 4 + 3] = -values[(size_t)i * 4 + 3];
      }
    }

    if (raw_in_tangents) {
      akb_animation_copy_quat_sample(&in_tangents[(size_t)i * 4],
                                     &raw_in_tangents[(size_t)i * out->value_width],
                                     sign);
    }
    if (raw_out_tangents) {
      akb_animation_copy_quat_sample(&out_tangents[(size_t)i * 4],
                                     &raw_out_tangents[(size_t)i * out->value_width],
                                     sign);
    }
  }
  out->value_width = 4;

  if (!raw_borrowed)
    free(raw_values);
  if (!out->borrowed_in_tangents)
    free(raw_in_tangents);
  if (!out->borrowed_out_tangents)
    free(raw_out_tangents);
  out->values = values;
  out->borrowed_values = 0;
  out->in_tangents = in_tangents;
  out->out_tangents = out_tangents;
  out->borrowed_in_tangents = 0;
  out->borrowed_out_tangents = 0;
  return 1;
}

static int
akb_animation_add_channel(AkbAnimation *animation,
                          AkChannel *channel,
                          AkResolvedTarget *target,
                          const AkbAnimBinding *binding,
                          const AkbCoordContext *coord,
                          uint32_t clip_index,
                          const char *clip_name) {
  AkbAnimChannel out = {0};
  AkAnimSampler *sampler;
  AkInput *time_input;
  AkInput *value_input;
  float *raw_values;
  uint32_t time_count;
  uint32_t value_count;
  uint32_t read_width;
  uint32_t logical_value_count;
  uint8_t raw_borrowed;

  sampler = ak_getObjectByUrl(&channel->source);
  if (!sampler)
    return 1;

  time_input = akb_anim_sampler_input(sampler, AK_INPUT_INPUT);
  value_input = akb_anim_sampler_input(sampler, AK_INPUT_OUTPUT);
  if (!time_input || !time_input->accessor || !value_input || !value_input->accessor)
    return 1;

  out.target = binding->kind;
  if (!out.target)
    return 1;
  out.clip_index = clip_index;
  out.clip_name = clip_name;

  out.value_width = value_input->accessor->componentCount
                    ? value_input->accessor->componentCount
                    : binding->width;
  if (target->isPartial && out.value_width > 1)
    out.value_width = 1;
  read_width = out.value_width;

  if (binding->kind == AKB_ANIM_MORPH_WEIGHTS && !target->isPartial) {
    out.value_width = binding->width;
    read_width = value_input->accessor->componentCount
                 ? value_input->accessor->componentCount
                 : 1;
    if (read_width != out.value_width)
      read_width = 1;
  }

  out.times = akb_accessor_float_borrow(time_input->accessor, 1, &time_count);
  if (out.times) {
    out.borrowed_times = 1;
  } else {
    out.times = akb_accessor_float_copy(time_input->accessor, 1, &time_count);
    if (!out.times)
      return 0;
  }

  raw_values = akb_accessor_float_borrow(value_input->accessor,
                                         read_width,
                                         &value_count);
  if (raw_values) {
    raw_borrowed = 1;
  } else {
    raw_values = akb_accessor_float_copy(value_input->accessor,
                                         read_width,
                                         &value_count);
    raw_borrowed = 0;
    if (!raw_values) {
      if (!out.borrowed_times)
        free(out.times);
      return 0;
    }
  }

  if (sampler->uniInterpolation == AK_INTERPOLATION_HERMITE
      && !akb_animation_extract_cubic_values(&raw_values,
                                             &out.in_tangents,
                                             &out.out_tangents,
                                             &value_count,
                                             &raw_borrowed,
                                             time_count,
                                             read_width,
                                             out.value_width)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!raw_borrowed)
      free(raw_values);
    return 0;
  }

  logical_value_count = value_count;
  if (binding->kind == AKB_ANIM_MORPH_WEIGHTS
      && !target->isPartial
      && read_width == 1
      && out.value_width > 1)
    logical_value_count = value_count / out.value_width;

  if (logical_value_count < time_count)
    time_count = logical_value_count;

  out.count = time_count;
  out.target_offset = target->isPartial ? target->off : 0;
  out.is_partial = target->isPartial ? 1 : 0;
  out.interpolation = (uint8_t)sampler->uniInterpolation;

  if (!akb_animation_convert_values(&out,
                                    raw_values,
                                    value_count,
                                    raw_borrowed,
                                    coord)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 0;
  }

  if (!out.count) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 1;
  }

  if (!akb_animation_push(animation, &out)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 0;
  }

  return 1;
}

static int
akb_animation_collect_walk(AkbAnimation *animation,
                           AkAnimation *source,
                           AkContext *context,
                           const AkbAnimBinding *bindings,
                           int binding_count,
                           const AkbCoordContext *coord) {
  struct AkbAnimationStackItem {
    AkAnimation *source;
    uint32_t index;
    const char *name;
  } stack[256];
  AkAnimation *next;
  AkChannel *channel;
  AkResolvedTarget resolved;
  const char *clip_name;
  uint32_t clip_index;
  int top;
  int i;

  top = 0;
  clip_index = 0;
  clip_name = source ? source->name : NULL;
  while (source) {
    for (channel = source->channel; channel; channel = channel->next) {
      resolved = ak_channelTarget(context, channel);
      if (!resolved.target)
        continue;

      for (i = 0; i < binding_count; i++) {
        if (resolved.target == bindings[i].target) {
          if (!akb_animation_add_channel(animation,
                                         channel,
                                         &resolved,
                                         &bindings[i],
                                         coord,
                                         clip_index,
                                         clip_name))
            return 0;
          break;
        }
      }
    }

    if (source->animation) {
      next = (AkAnimation *)source->base.next;
      if (next && top < 256) {
        stack[top].source = next;
        stack[top].index = clip_index + 1;
        stack[top].name = next->name;
        top++;
      }
      source = source->animation;
    } else if (source->base.next) {
      source = (AkAnimation *)source->base.next;
      clip_index++;
      clip_name = source->name;
    } else if (top > 0) {
      top--;
      source = stack[top].source;
      clip_index = stack[top].index;
      clip_name = stack[top].name;
    } else {
      source = NULL;
    }
  }

  return 1;
}

static AkbAnimation *
akb_animation_new_for_bindings(AkDoc *doc,
                               AkbSharedDoc *doc_owner,
                               const AkbAnimBinding *bindings,
                               int binding_count,
                               const AkbCoordContext *coord,
                               int *ok) {
  AkbAnimation *animation;
  AkLibrary *library;
  AkContext context;

  *ok = 1;
  if (!doc || !bindings || binding_count <= 0)
    return NULL;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  memset(&context, 0, sizeof(context));
  context.doc = doc;

  for (library = doc->lib.animations; library; library = library->next) {
    if (!akb_animation_collect_walk(animation,
                                    (AkAnimation *)library->chld,
                                    &context,
                                    bindings,
                                    binding_count,
                                    coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static int
akb_node_visibility_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  if (!node)
    return 0;

  return akb_anim_binding_push(bindings,
                               capacity,
                               0,
                               &node->visible,
                               AKB_ANIM_VISIBILITY,
                               1);
}

static int
akb_node_transform_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  AkObject *object;
  uint32_t kind;
  uint32_t width;
  int count;

  count = akb_node_visibility_bindings(node, bindings, capacity);
  if (!node)
    return 0;
  if (!node->transform)
    return count;

  for (object = node->transform->base; object; object = object->next) {
    kind = (uint32_t)akb_anim_target_kind(object, &width);
    count = akb_anim_binding_push(bindings, capacity, count, object, kind, width);
  }

  for (object = node->transform->item; object; object = object->next) {
    kind = (uint32_t)akb_anim_target_kind(object, &width);
    count = akb_anim_binding_push(bindings, capacity, count, object, kind, width);
  }

  return count;
}

static int
akb_node_camera_bindings(AkNode *node,
                         AkbAnimBinding *bindings,
                         int capacity,
                         int count) {
  AkCamera *camera;
  AkProjection *projection;

  if (!node || !node->camera)
    return count;

  camera = (AkCamera *)ak_instanceObject(node->camera);
  if (!camera || !camera->optics || !(projection = camera->optics->tcommon))
    return count;

  if (projection->type == AK_PROJECTION_PERSPECTIVE) {
    AkPerspective *persp;

    persp = (AkPerspective *)projection;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->xfov,
                                  AKB_ANIM_CAMERA_XFOV,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->yfov,
                                  AKB_ANIM_CAMERA_YFOV,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->znear,
                                  AKB_ANIM_CAMERA_ZNEAR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->zfar,
                                  AKB_ANIM_CAMERA_ZFAR,
                                  1);
  } else if (projection->type == AK_PROJECTION_ORTHOGRAPHIC) {
    AkOrthographic *ortho;

    ortho = (AkOrthographic *)projection;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->xmag,
                                  AKB_ANIM_CAMERA_ORTHO_XMAG,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->ymag,
                                  AKB_ANIM_CAMERA_ORTHO_YMAG,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->znear,
                                  AKB_ANIM_CAMERA_ZNEAR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->zfar,
                                  AKB_ANIM_CAMERA_ZFAR,
                                  1);
  }

  return count;
}

static int
akb_node_light_bindings(AkNode *node,
                        AkbAnimBinding *bindings,
                        int capacity,
                        int count) {
  AkLight *light;
  AkLightBase *base;

  if (!node || !node->light)
    return count;

  light = (AkLight *)ak_instanceObject(node->light);
  if (!light || !(base = light->tcommon))
    return count;

  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                base->color.vec,
                                AKB_ANIM_LIGHT_COLOR,
                                3);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &base->intensity,
                                AKB_ANIM_LIGHT_INTENSITY,
                                1);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &base->range,
                                AKB_ANIM_LIGHT_RANGE,
                                1);

  if (base->type == AK_LIGHT_TYPE_SPOT) {
    AkSpotLight *spot;

    spot = (AkSpotLight *)base;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &spot->innerConeAngle,
                                  AKB_ANIM_LIGHT_SPOT_INNER,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &spot->outerConeAngle,
                                  AKB_ANIM_LIGHT_SPOT_OUTER,
                                  1);
  }

  return count;
}

static int
akb_node_scene_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  int count;

  count = akb_node_transform_bindings(node, bindings, capacity);
  count = akb_node_camera_bindings(node, bindings, capacity, count);
  count = akb_node_light_bindings(node, bindings, capacity, count);

  return count;
}

static int
akb_texture_transform_binding_push(AkbAnimBinding *bindings,
                                   int capacity,
                                   int count,
                                   AkTextureRef *texref,
                                   uint32_t role_id) {
  AkTextureTransform *transform;
  uint32_t base;

  if (!texref || !(transform = texref->transform))
    return count;

  base = AKB_ANIM_TEXTURE_TRANSFORM_BASE
         + role_id * AKB_ANIM_TEXTURE_TRANSFORM_STRIDE;
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                transform->offset,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_OFFSET,
                                2);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                transform->scale,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_SCALE,
                                2);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &transform->rotation,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_ROTATION,
                                1);

  return count;
}

static int
akb_material_bindings(AkTechniqueFxCommon *cmn, AkbAnimBinding *bindings, int capacity) {
  int count;

  count = 0;
  if (!cmn)
    return 0;

  if (cmn->albedo) {
    if (cmn->albedo->color)
      count = akb_anim_binding_push(bindings,
                                    capacity,
                                    count,
                                    cmn->albedo->color->vec,
                                    AKB_ANIM_MATERIAL_BASE_COLOR,
                                    4);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->albedo->texture,
                                               AKB_TEX_ROLE_BASE_COLOR);
  }
  if (cmn->metalness) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->metalness->intensity,
                                  AKB_ANIM_MATERIAL_METALLIC,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->metalness->tex,
                                               AKB_TEX_ROLE_METALLIC_ROUGHNESS);
  }
  if (cmn->roughness) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->roughness->intensity,
                                  AKB_ANIM_MATERIAL_ROUGHNESS,
                                  1);
    if (!cmn->metalness || cmn->roughness->tex != cmn->metalness->tex)
      count = akb_texture_transform_binding_push(bindings,
                                                 capacity,
                                                 count,
                                                 cmn->roughness->tex,
                                                 AKB_TEX_ROLE_METALLIC_ROUGHNESS);
  }
  if (cmn->transparent) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->transparent->cutoff,
                                  AKB_ANIM_MATERIAL_ALPHA_CUTOFF,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->transparent->color
                                               ? cmn->transparent->color->texture
                                               : NULL,
                                               AKB_TEX_ROLE_TRANSPARENT);
  }
  if (cmn->emission) {
    if (cmn->emission->color.color)
      count = akb_anim_binding_push(bindings,
                                    capacity,
                                    count,
                                    cmn->emission->color.color->vec,
                                    AKB_ANIM_MATERIAL_EMISSIVE_COLOR,
                                    3);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->emission->strength,
                                  AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->emission->color.texture,
                                               AKB_TEX_ROLE_EMISSIVE);
  }
  if (cmn->normal) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->normal->scale,
                                  AKB_ANIM_MATERIAL_NORMAL_SCALE,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->normal->tex,
                                               AKB_TEX_ROLE_NORMAL);
  }
  if (cmn->occlusion) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->occlusion->strength,
                                  AKB_ANIM_MATERIAL_OCCLUSION_STRENGTH,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->occlusion->tex,
                                               AKB_TEX_ROLE_OCCLUSION);
  }
  if (cmn->specular) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->specular->strength,
                                  AKB_ANIM_MATERIAL_SPECULAR,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->specular->specularTex,
                                               AKB_TEX_ROLE_SPECULAR);
    if (cmn->specular->color && cmn->specular->color->color)
      count = akb_anim_binding_push(bindings,
                                    capacity,
                                    count,
                                    cmn->specular->color->color->vec,
                                    AKB_ANIM_MATERIAL_SPECULAR_COLOR,
                                    3);
    if (cmn->specular->color)
      count = akb_texture_transform_binding_push(bindings,
                                                 capacity,
                                                 count,
                                                 cmn->specular->color->texture,
                                                 AKB_TEX_ROLE_SPECULAR_COLOR);
  }
  if (cmn->ior > 0.0f)
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->ior,
                                  AKB_ANIM_MATERIAL_IOR,
                                  1);
  if (cmn->clearcoat) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->clearcoat->intensity,
                                  AKB_ANIM_MATERIAL_CLEARCOAT,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->clearcoat->roughness,
                                  AKB_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->clearcoat->normalScale,
                                  AKB_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->clearcoat->texture,
                                               AKB_TEX_ROLE_CLEARCOAT);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->clearcoat->roughnessTexture,
                                               AKB_TEX_ROLE_CLEARCOAT_ROUGHNESS);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->clearcoat->normalTexture,
                                               AKB_TEX_ROLE_CLEARCOAT_NORMAL);
  }
  if (cmn->transmission) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->transmission->factor,
                                  AKB_ANIM_MATERIAL_TRANSMISSION,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->transmission->texture,
                                               AKB_TEX_ROLE_TRANSMISSION);
  }
  if (cmn->sheen) {
    if (cmn->sheen->color && cmn->sheen->color->color)
      count = akb_anim_binding_push(bindings,
                                    capacity,
                                    count,
                                    cmn->sheen->color->color->vec,
                                    AKB_ANIM_MATERIAL_SHEEN_COLOR,
                                    3);
    if (cmn->sheen->color)
      count = akb_texture_transform_binding_push(bindings,
                                                 capacity,
                                                 count,
                                                 cmn->sheen->color->texture,
                                                 AKB_TEX_ROLE_SHEEN_COLOR);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->sheen->roughness,
                                  AKB_ANIM_MATERIAL_SHEEN_ROUGHNESS,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->sheen->roughnessTexture,
                                               AKB_TEX_ROLE_SHEEN_ROUGHNESS);
  }
  if (cmn->iridescence) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->iridescence->factor,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->iridescence->ior,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_IOR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->iridescence->thicknessMinimum,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->iridescence->thicknessMaximum,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->iridescence->texture,
                                               AKB_TEX_ROLE_IRIDESCENCE);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->iridescence->thicknessTexture,
                                               AKB_TEX_ROLE_IRIDESCENCE_THICKNESS);
  }
  if (cmn->volume) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->volume->thicknessFactor,
                                  AKB_ANIM_MATERIAL_VOLUME_THICKNESS,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->volume->attenuationDistance,
                                  AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  cmn->volume->attenuationColor.vec,
                                  AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR,
                                  3);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->volume->thicknessTexture,
                                               AKB_TEX_ROLE_VOLUME_THICKNESS);
  }
  if (cmn->anisotropy) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->anisotropy->strength,
                                  AKB_ANIM_MATERIAL_ANISOTROPY,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->anisotropy->rotation,
                                  AKB_ANIM_MATERIAL_ANISOTROPY_ROTATION,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->anisotropy->texture,
                                               AKB_TEX_ROLE_ANISOTROPY);
  }
  if (cmn->dispersion)
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->dispersion->dispersion,
                                  AKB_ANIM_MATERIAL_DISPERSION,
                                  1);
  if (cmn->diffuseTransmission) {
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &cmn->diffuseTransmission->factor,
                                  AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION,
                                  1);
    if (cmn->diffuseTransmission->color && cmn->diffuseTransmission->color->color)
      count = akb_anim_binding_push(bindings,
                                    capacity,
                                    count,
                                    cmn->diffuseTransmission->color->color->vec,
                                    AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR,
                                    3);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               cmn->diffuseTransmission->texture,
                                               AKB_TEX_ROLE_DIFFUSE_TRANSMISSION);
    if (cmn->diffuseTransmission->color)
      count = akb_texture_transform_binding_push(bindings,
                                                 capacity,
                                                 count,
                                                 cmn->diffuseTransmission->color->texture,
                                                 AKB_TEX_ROLE_DIFFUSE_TRANSMISSION_COLOR);
  }

  return count;
}

static AkbAnimation *
akb_material_animation_new(AkDoc *doc,
                           AkbSharedDoc *doc_owner,
                           AkMeshPrimitive *prim,
                           AkBindMaterial *bind_material,
                           const AkbCoordContext *coord,
                           int *ok) {
  AkEffect *effect;
  AkTechniqueFxCommon *cmn;
  AkbAnimBinding bindings[64];
  int binding_count;

  *ok = 1;
  effect = akb_primitive_effect(prim, bind_material, NULL, NULL);
  cmn = effect ? ak_getProfileTechniqueCommon(effect) : NULL;
  binding_count = akb_material_bindings(cmn, bindings, 64);

  return akb_animation_new_for_bindings(doc,
                                        doc_owner,
                                        bindings,
                                        binding_count,
                                        coord,
                                        ok);
}

static int
akb_node_has_rotate(AkNode *node) {
  AkObject *object;

  if (!node || !node->transform)
    return 0;

  for (object = node->transform->base; object; object = object->next) {
    if ((AkTypeId)object->type == AKT_ROTATE)
      return 1;
  }

  for (object = node->transform->item; object; object = object->next) {
    if ((AkTypeId)object->type == AKT_ROTATE)
      return 1;
  }

  return 0;
}

static void
akb_baked_matrix_to_trs(const float m[16],
                        float *translation,
                        float *rotation,
                        float *scale,
                        const float *previous_rotation) {
  CGLM_ALIGN_MAT mat4 matrix;
  CGLM_ALIGN_MAT mat4 rotation_matrix;
  CGLM_ALIGN(16) vec4 translation4;
  CGLM_ALIGN(16) vec4 rotation_wxyz;
  CGLM_ALIGN(16) vec4 previous_wxyz;
  CGLM_ALIGN(8) vec3 scale3;
  versor rotation_xyzw;

  memcpy(matrix, m, sizeof(matrix));
  glm_decompose(matrix, translation4, rotation_matrix, scale3);
  glm_mat4_quat(rotation_matrix, rotation_xyzw);
  glm_quat_normalize(rotation_xyzw);

  translation[0] = translation4[0];
  translation[1] = translation4[1];
  translation[2] = translation4[2];
  scale[0] = scale3[0];
  scale[1] = scale3[1];
  scale[2] = scale3[2];

  rotation_wxyz[0] = rotation_xyzw[3];
  rotation_wxyz[1] = rotation_xyzw[0];
  rotation_wxyz[2] = rotation_xyzw[1];
  rotation_wxyz[3] = rotation_xyzw[2];

  if (previous_rotation) {
    memcpy(previous_wxyz, previous_rotation, sizeof(previous_wxyz));
    if (glm_vec4_dot(rotation_wxyz, previous_wxyz) < 0.0f)
      glm_vec4_negate(rotation_wxyz);
  }

  memcpy(rotation, rotation_wxyz, sizeof(rotation_wxyz));
}

static AkbAnimation *
akb_animation_new_baked(AkDoc *doc,
                        AkbSharedDoc *doc_owner,
                        AkNode *node,
                        int *ok) {
  AkbAnimation *animation;
  AkBakedAnimation *baked;
  AkbAnimChannel channel;
  float *translations;
  float *rotations;
  float *scales;
  uint32_t i;

  baked = ak_nodeBakeAnimation(doc, node);
  if (!baked || !baked->count || !baked->times || !baked->matrices) {
    if (baked)
      ak_free(baked);
    return NULL;
  }

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    ak_free(baked);
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  animation->baked = baked;
  akb_shared_doc_retain(doc_owner);

  animation->baked_values = (float *)malloc((size_t)baked->count * 10 * sizeof(float));
  if (!animation->baked_values) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  translations = animation->baked_values;
  rotations = translations + (size_t)baked->count * 3;
  scales = rotations + (size_t)baked->count * 4;

  for (i = 0; i < baked->count; i++) {
    akb_baked_matrix_to_trs(baked->matrices + (size_t)i * 16,
                            translations + (size_t)i * 3,
                            rotations + (size_t)i * 4,
                            scales + (size_t)i * 3,
                            i > 0 ? rotations + (size_t)(i - 1) * 4 : NULL);
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_TRANSLATION;
  channel.value_width = 3;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = translations;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;

  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_ROTATION_QUAT;
  channel.value_width = 4;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = rotations;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;
  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_SCALE;
  channel.value_width = 3;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = scales;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;
  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  return animation;
}

static AkbAnimation *
akb_animation_new(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  AkNode *node,
                  const AkbCoordContext *coord,
                  int *ok) {
  AkbAnimation *animation;
  AkLibrary *library;
  AkbAnimBinding bindings[64];
  AkContext context;
  int binding_count;
  int needs_bake;

  *ok = 1;
  needs_bake = ak_nodeNeedsBaking(node) || akb_node_has_rotate(node);

  if (needs_bake) {
    animation = akb_animation_new_baked(doc, doc_owner, node, ok);
    if (!animation || !*ok)
      return animation;
    binding_count = akb_node_visibility_bindings(node, bindings, 64);
    binding_count = akb_node_camera_bindings(node, bindings, 64, binding_count);
    binding_count = akb_node_light_bindings(node, bindings, 64, binding_count);
  } else {
    binding_count = akb_node_scene_bindings(node, bindings, 64);
  }

  if (!binding_count) {
    if (needs_bake)
      return animation;
    animation = akb_animation_new_baked(doc, doc_owner, node, ok);
    return animation;
  }

  if (!needs_bake) {
    animation = (AkbAnimation *)calloc(1, sizeof(*animation));
    if (!animation) {
      *ok = 0;
      return NULL;
    }

    animation->refcount = 1;
    animation->doc_owner = doc_owner;
    akb_shared_doc_retain(doc_owner);
  }

  memset(&context, 0, sizeof(context));
  context.doc = doc;

  for (library = doc->lib.animations; library; library = library->next) {
    if (!akb_animation_collect_walk(animation,
                                    (AkAnimation *)library->chld,
                                    &context,
                                    bindings,
                                    binding_count,
                                    coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static AkbAnimation *
akb_morph_animation_new(AkDoc *doc,
                        AkbSharedDoc *doc_owner,
                        AkInstanceMorph *morpher,
                        const AkbCoordContext *coord,
                        int *ok) {
  AkbAnimation *animation;
  AkbAnimBinding binding = {0};
  AkLibrary *library;
  AkContext context;

  *ok = 1;
  if (!morpher || !morpher->morph || !morpher->morph->targetCount)
    return NULL;

  binding.target = morpher;
  binding.kind = AKB_ANIM_MORPH_WEIGHTS;
  binding.width = morpher->morph->targetCount;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  memset(&context, 0, sizeof(context));
  context.doc = doc;

  for (library = doc->lib.animations; library; library = library->next) {
    if (!akb_animation_collect_walk(animation,
                                    (AkAnimation *)library->chld,
                                    &context,
                                    &binding,
                                    1,
                                    coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static void
akb_extract_node_camera(AkbSceneNode *out, AkNode *node) {
  AkCamera *camera;
  AkProjection *projection;

  if (!out || !node || !node->camera)
    return;

  camera = (AkCamera *)ak_instanceObject(node->camera);
  if (!camera || !camera->optics || !camera->optics->tcommon)
    return;

  projection = camera->optics->tcommon;
  out->camera_extra = ak_extra(camera);
  out->camera_imager_extra = camera->imager ? ak_extra(camera->imager) : NULL;
  out->camera_type = (uint8_t)projection->type + 1;
  snprintf(out->camera_name,
           sizeof(out->camera_name),
           "%s",
           akb_name(camera->name, out->name));

  if (projection->type == AK_PROJECTION_PERSPECTIVE) {
    AkPerspective *persp;

    persp = (AkPerspective *)projection;
    out->camera_values[0] = persp->xfov;
    out->camera_values[1] = persp->yfov;
    out->camera_values[2] = persp->aspectRatio;
    out->camera_values[3] = persp->znear;
    out->camera_values[4] = persp->zfar;
  } else if (projection->type == AK_PROJECTION_ORTHOGRAPHIC) {
    AkOrthographic *ortho;

    ortho = (AkOrthographic *)projection;
    out->camera_values[0] = ortho->xmag;
    out->camera_values[1] = ortho->ymag;
    out->camera_values[2] = ortho->aspectRatio;
    out->camera_values[3] = ortho->znear;
    out->camera_values[4] = ortho->zfar;
  }
}

static void
akb_extract_node_light(AkbSceneNode *out, AkNode *node) {
  AkLight *light;
  AkLightBase *base;

  if (!out || !node || !node->light)
    return;

  light = (AkLight *)ak_instanceObject(node->light);
  if (!light || !light->tcommon)
    return;

  base = light->tcommon;
  out->light_extra = ak_extra(light);
  out->light_type = (uint8_t)base->type;
  snprintf(out->light_name,
           sizeof(out->light_name),
           "%s",
           akb_name(light->name, out->name));
  out->light_color[0] = base->color.rgba.R;
  out->light_color[1] = base->color.rgba.G;
  out->light_color[2] = base->color.rgba.B;
  out->light_values[0] = base->intensity;
  out->light_values[1] = base->range;

  if (base->type == AK_LIGHT_TYPE_SPOT) {
    AkSpotLight *spot;

    spot = (AkSpotLight *)base;
    out->light_values[2] = spot->innerConeAngle;
    out->light_values[3] = spot->outerConeAngle ? spot->outerConeAngle : spot->falloffAngle;
    out->light_values[4] = spot->falloffExp;
  }
}

static int
akb_extract_scene_node(AkbSceneNodeList *nodes,
                       AkDoc *doc,
                       AkbSharedDoc *doc_owner,
                       AkNode *node,
                       const AkbCoordContext *coord,
                       int32_t parent_index,
                       int32_t *node_index) {
  AkbSceneNode out = {0};
  int ok;

  if (!nodes || !node || !node_index)
    return 0;

  *node_index = (int32_t)nodes->count;
  out.source = node;
  snprintf(out.name, sizeof(out.name), "%s", akb_name(node->name, "AssetKitNode"));
  out.parent_index = parent_index;
  out.visible = node->visible ? 1 : 0;
  out.layers = node->layer;
  ak_transformCombine(node->transform, out.matrix);
  out.has_transform = 1;
  akb_extract_node_camera(&out, node);
  akb_extract_node_light(&out, node);
  out.animation = akb_animation_new(doc, doc_owner, node, coord, &ok);
  if (!ok) {
    akb_scene_node_free(&out);
    return 0;
  }

  if (!akb_node_list_push(nodes, &out)) {
    akb_scene_node_free(&out);
    return 0;
  }

  return 1;
}

static int
akb_primitive_supported(AkMeshPrimitive *prim, const AkbLoadOptions *options) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
    case AKB_PRIMITIVE_POINTS:
      return 1;
    case AKB_PRIMITIVE_LINES:
      return options ? options->import_lines : 1;
    default:
      return 0;
  }
}

static uint32_t
akb_primitive_mode(AkMeshPrimitive *prim) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
      return (uint32_t)((AkTriangles *)prim)->mode;
    case AKB_PRIMITIVE_LINES:
      return (uint32_t)((AkLines *)prim)->mode;
    default:
      return 0;
  }
}

static uint32_t
akb_primitive_index_width(AkMeshPrimitive *prim) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
      return ((AkTriangles *)prim)->mode == 0
             || ((AkTriangles *)prim)->mode == AK_TRIANGLES
             ? 3
             : 0;
    case AKB_PRIMITIVE_LINES:
      return ((AkLines *)prim)->mode == 0
             || ((AkLines *)prim)->mode == AK_LINES
             ? 2
             : 0;
    case AKB_PRIMITIVE_POINTS:
      return 1;
    default:
      return 0;
  }
}

static int
akb_extract_primitive(AkbPrimitiveList *list,
                      AkbSceneNodeList *nodes,
                      AkDoc *doc,
                      AkbSharedDoc *doc_owner,
                      AkbAnimation *animation,
                      AkbAnimation *morph_animation,
                      AkNode *node,
                      int32_t node_index,
                      AkGeometry *geom,
                      AkMesh *mesh,
                      AkMeshPrimitive *prim,
                      uint32_t prim_index) {
  AkbPrimitive out = {0};
  AkInput *pos_input, *normal_input, *tangent_input;
  const uint32_t *raw_indices = NULL;
  size_t raw_count = 0;
  uint32_t pos_count = 0;
  uint32_t stride, pos_offset;
  uint32_t i;
  uint32_t index_width;
  int ok;
  const char *base_name;

  index_width = akb_primitive_index_width(prim);
  if (!index_width)
    return 1;

  pos_input = prim->pos && prim->pos->accessor && prim->pos->accessor->count > 0
              ? prim->pos
              : akb_find_input_with_accessor(prim,
                                             AK_INPUT_POSITION,
                                             AK_INPUT_POSITION,
                                             "POSITION",
                                             NULL);
  if (!pos_input || !pos_input->accessor || pos_input->accessor->count == 0)
    return 1;

  out.node_index = node_index;
  out.file_type = doc && doc->inf ? (uint32_t)doc->inf->ftype : 0;
  out.primitive_type = (uint32_t)prim->type;
  out.primitive_mode = akb_primitive_mode(prim);
  out.primitive_extra = ak_extra(prim);
  out.mesh_extra = ak_extra(mesh);
  out.geometry_extra = ak_extra(geom);
  if (prim->gsplat) {
    out.has_gsplat = 1;
    out.gsplat.kernel = (uint32_t)prim->gsplat->kernel;
    out.gsplat.color_space = (uint32_t)prim->gsplat->colorSpace;
    out.gsplat.projection = (uint32_t)prim->gsplat->projection;
    out.gsplat.sorting_method = (uint32_t)prim->gsplat->sortingMethod;
    out.gsplat.decoded_count = prim->gsplat->decodedCount;
  }
  akb_extract_material(doc,
                       prim,
                       node && node->geometry ? node->geometry->bindMaterial : NULL,
                       &out);
  out.material_animation = akb_material_animation_new(doc,
                                                      doc_owner,
                                                      prim,
                                                      node && node->geometry
                                                      ? node->geometry->bindMaterial
                                                      : NULL,
                                                      NULL,
                                                      &ok);
  if (!ok) {
    akb_primitive_free(&out);
    return 0;
  }
  if (!akb_extract_material_variants(doc, prim, &out)) {
    akb_primitive_free(&out);
    return 0;
  }
  out.animation = akb_animation_retain(animation);
  out.morph_animation = akb_animation_retain(morph_animation);
  if (!akb_extract_instancing(&out, node)) {
    akb_primitive_free(&out);
    return 0;
  }

  if (node) {
    snprintf(out.object_name, sizeof(out.object_name), "%s", akb_name(node->name, "AssetKitObject"));
    ak_transformCombine(node->transform, out.matrix);
    out.has_node = 1;
  }

  out.vertices = akb_accessor_float_borrow(pos_input->accessor, 3, &pos_count);
  if (out.vertices) {
    out.borrowed_vertices = 1;
    out.zero_copy_flags |= 1;
    akb_primitive_retain_doc(&out, doc_owner);
  } else {
    out.vertices = akb_accessor_float_copy(pos_input->accessor, 3, &pos_count);
    if (!out.vertices)
      return 0;
  }
  out.vertex_count = pos_count;

  raw_indices = akb_indices_data(prim->indices, &raw_count);

  if (raw_indices) {
    stride = prim->indexStride ? prim->indexStride : 1;
    pos_offset = pos_input->offset;
    out.loop_count = (uint32_t)(raw_count / stride);
    if (stride == 1 && pos_offset == 0) {
      out.indices = (uint32_t *)raw_indices;
      out.borrowed_indices = 1;
      out.zero_copy_flags |= 2;
      akb_primitive_retain_doc(&out, doc_owner);
    } else {
      out.indices = (uint32_t *)malloc((size_t)out.loop_count * sizeof(uint32_t));
      if (!out.indices) {
        akb_primitive_free(&out);
        return 0;
      }

      for (i = 0; i < out.loop_count; i++)
        out.indices[i] = raw_indices[(size_t)i * stride + pos_offset];
    }
  } else {
    out.loop_count = out.vertex_count;
    out.indices = (uint32_t *)malloc((size_t)out.loop_count * sizeof(uint32_t));
    if (!out.indices) {
      akb_primitive_free(&out);
      return 0;
    }

    for (i = 0; i < out.loop_count; i++)
      out.indices[i] = i;
  }

  out.loop_count = (out.loop_count / index_width) * index_width;
  out.face_count = out.primitive_type == AKB_PRIMITIVE_TRIANGLES
                   ? out.loop_count / index_width
                   : 0;
  if (out.face_count) {
    out.loop_meta = (int32_t *)malloc((size_t)out.face_count * 2 * sizeof(int32_t));
    if (!out.loop_meta) {
      akb_primitive_free(&out);
      return 0;
    }
    out.loop_starts = out.loop_meta;
    out.loop_totals = out.loop_meta + out.face_count;
  }

  for (i = 0; i < out.face_count; i++) {
    out.loop_starts[i] = (int32_t)(i * 3);
    out.loop_totals[i] = 3;
  }

  if (!akb_extract_point_float_attrs(&out, prim, doc_owner)) {
    akb_primitive_free(&out);
    return 0;
  }

  if (out.primitive_type == AKB_PRIMITIVE_TRIANGLES) {
    normal_input = akb_find_input(prim, AK_INPUT_NORMAL, AK_INPUT_NORMAL, "NORMAL", NULL);
    out.normals = akb_loop_attribute_copy(prim,
                                          normal_input,
                                          raw_indices,
                                          raw_count,
                                          out.indices,
                                          out.loop_count,
                                          3,
                                          0,
                                          &out.has_normals);

    if (!akb_extract_loop_float_attrs(&out,
                                      prim,
                                      raw_indices,
                                      raw_count,
                                      out.indices,
                                      out.loop_count,
                                      AK_INPUT_TEXCOORD,
                                      AK_INPUT_UV,
                                      "TEXCOORD",
                                      "UV",
                                      2,
                                      1,
                                      0.0f,
                                      "UVMap",
                                      &out.uv_sets,
                                      &out.uv_set_count)) {
      akb_primitive_free(&out);
      return 0;
    }
    if (out.uv_set_count) {
      out.uvs = out.uv_sets[0].values;
      out.has_uvs = 1;
    }

    if (!akb_extract_loop_float_attrs(&out,
                                      prim,
                                      raw_indices,
                                      raw_count,
                                      out.indices,
                                      out.loop_count,
                                      AK_INPUT_COLOR,
                                      AK_INPUT_COLOR,
                                      "COLOR",
                                      NULL,
                                      4,
                                      0,
                                      1.0f,
                                      "Color",
                                      &out.color_sets,
                                      &out.color_set_count)) {
      akb_primitive_free(&out);
      return 0;
    }
    if (out.color_set_count) {
      out.colors = out.color_sets[0].values;
      out.has_colors = 1;
    }

    tangent_input = akb_find_input(prim,
                                   AK_INPUT_TANGENT,
                                   AK_INPUT_TEXTANGENT,
                                   "TANGENT",
                                   "TEXTANGENT");
    out.tangents = akb_loop_attribute_copy(prim,
                                           tangent_input,
                                           raw_indices,
                                           raw_count,
                                           out.indices,
                                           out.loop_count,
                                           4,
                                           0,
                                           &out.has_tangents);
    if (out.tangents && tangent_input && tangent_input->accessor)
      akb_fill_missing_components(out.tangents,
                                  out.loop_count,
                                  4,
                                  tangent_input->accessor->componentCount,
                                  1.0f);

    if (node && node->geometry && node->geometry->morpher) {
      if (!akb_extract_morph_targets(&out,
                                     geom,
                                     mesh,
                                     prim,
                                     prim_index,
                                     node->geometry->morpher)) {
        akb_primitive_free(&out);
        return 0;
      }
    }

    if (node && node->geometry && node->geometry->skinner) {
      if (!akb_extract_skin(&out,
                            nodes,
                            prim,
                            prim_index,
                            node->geometry->skinner)) {
        akb_primitive_free(&out);
        return 0;
      }
      if (node->geometry->skinner->skin
          && node->geometry->skinner->skin->joints
          && !node->geometry->skinner->overrideJoints
          && !akb_skin_into_bind_pose(&out)) {
        akb_primitive_free(&out);
        return 0;
      }
    }
  }

  base_name = akb_name(mesh->name, akb_name(geom->name, "AssetKitMesh"));
  if (mesh->primitiveCount > 1)
    snprintf(out.name, sizeof(out.name), "%s_%u", base_name, prim_index);
  else
    snprintf(out.name, sizeof(out.name), "%s", base_name);

  if (!akb_list_push(list, &out)) {
    akb_primitive_free(&out);
    return 0;
  }

  return 1;
}

static int
akb_extract_mesh(AkbPrimitiveList *list,
                 AkbSceneNodeList *nodes,
                 AkDoc *doc,
                 AkbSharedDoc *doc_owner,
                 AkbAnimation *animation,
                 AkbAnimation *morph_animation,
                 AkNode *node,
                 int32_t node_index,
                 AkGeometry *geom,
                 const AkbLoadOptions *options) {
  AkObject *gdata;
  AkMesh *mesh;
  AkMeshPrimitive *prim;
  uint32_t prim_index = 0;

  if (!geom || !(gdata = geom->gdata) || gdata->type != AKB_GEOMETRY_MESH)
    return 1;

  mesh = (AkMesh *)ak_objGet(gdata);
  if (!mesh)
    return 1;

  for (prim = mesh->primitive; prim; prim = prim->next, prim_index++) {
    if (!akb_primitive_supported(prim, options))
      continue;
    if (!akb_extract_primitive(list,
                               nodes,
                               doc,
                               doc_owner,
                               animation,
                               morph_animation,
                               node,
                               node_index,
                               geom,
                               mesh,
                               prim,
                               prim_index))
      return 0;
  }

  return 1;
}

static int
akb_extract_node(AkbPrimitiveList *list,
                 AkbSceneNodeList *nodes,
                 AkDoc *doc,
                 AkbSharedDoc *doc_owner,
                 AkNode *node,
                 const AkbCoordContext *coord,
                 const AkbLoadOptions *options,
                 int32_t parent_index) {
  AkNode *child;
  AkNode *inst_node;
  AkGeometry *geom;
  AkInstanceBase *inst;
  AkbAnimation *animation;
  AkbAnimation *morph_animation;
  int32_t node_index;
  int ok;

  if (!node)
    return 1;

  if (!akb_extract_scene_node(nodes,
                              doc,
                              doc_owner,
                              node,
                              coord,
                              parent_index,
                              &node_index))
    return 0;

  if (node->geometry) {
    animation = akb_animation_retain(nodes->items[node_index].animation);
    morph_animation = NULL;
    ok = 1;
    if (node->geometry->morpher) {
      morph_animation = akb_morph_animation_new(doc,
                                                doc_owner,
                                                node->geometry->morpher,
                                                coord,
                                                &ok);
    }
    if (!ok) {
      akb_animation_release(animation);
      akb_animation_release(morph_animation);
      return 0;
    }

    geom = (AkGeometry *)ak_instanceObject(&node->geometry->base);
    if (!akb_extract_mesh(list,
                          nodes,
                          doc,
                          doc_owner,
                          animation,
                          morph_animation,
                          node,
                          node_index,
                          geom,
                          options)) {
      akb_animation_release(animation);
      akb_animation_release(morph_animation);
      return 0;
    }
    akb_animation_release(animation);
    akb_animation_release(morph_animation);
  }

  for (child = node->chld; child; child = child->next) {
    if (!akb_extract_node(list, nodes, doc, doc_owner, child, coord, options, node_index))
      return 0;
  }

  for (inst = node->node ? &node->node->base : NULL; inst; inst = inst->next) {
    inst_node = (AkNode *)ak_instanceObject(inst);
    if (!inst_node || inst_node == node)
      continue;
    if (!akb_extract_node(list, nodes, doc, doc_owner, inst_node, coord, options, node_index))
      return 0;
  }

  return 1;
}

static AkVisualScene *
akb_default_visual_scene(AkDoc *doc) {
  if (!doc || !doc->scene.visualScene)
    return NULL;
  return (AkVisualScene *)ak_instanceObject(doc->scene.visualScene);
}

static AkVisualScene *
akb_visual_scene_by_index(AkDoc *doc, int32_t scene_index) {
  AkVisualScene *scene;
  int32_t index;

  if (!doc || scene_index < 0 || !doc->lib.visualScenes)
    return NULL;

  for (scene = (AkVisualScene *)doc->lib.visualScenes->chld, index = 0;
       scene;
       scene = (AkVisualScene *)scene->base.next, index++) {
    if (index == scene_index)
      return scene;
  }

  return NULL;
}

static AkVisualScene *
akb_selected_visual_scene(AkDoc *doc, const AkbLoadOptions *options) {
  AkVisualScene *scene;

  scene = options ? akb_visual_scene_by_index(doc, options->scene_index) : NULL;
  return scene ? scene : akb_default_visual_scene(doc);
}

static int
akb_extract_scene(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  AkbPrimitiveList *list,
                  AkbSceneNodeList *nodes,
                  const AkbCoordContext *coord,
                  const AkbLoadOptions *options) {
  AkVisualScene *scene;
  AkInstanceBase *inst;
  AkNode *node;

  if (!doc)
    return 1;

  scene = akb_selected_visual_scene(doc, options);
  if (!scene || !scene->node)
    return 1;

  if (scene->node->node) {
    for (inst = &scene->node->node->base; inst; inst = inst->next) {
      node = inst->node ? inst->node : (AkNode *)ak_instanceObject(inst);
      if (!akb_extract_node(list, nodes, doc, doc_owner, node, coord, options, -1))
        return 0;
    }
  } else {
    for (node = scene->node; node; node = node->next) {
      if (!akb_extract_node(list, nodes, doc, doc_owner, node, coord, options, -1))
        return 0;
    }
  }

  return 1;
}

static int
akb_extract_doc(AkDoc *doc,
                AkbSharedDoc *doc_owner,
                AkbImport *import,
                const AkbLoadOptions *options) {
  AkbCoordContext coord;
  AkLibrary *lib;
  AkGeometry *geom;

  akb_prepare_blender_coords(doc, &coord, options);

  if (!akb_extract_scene(doc,
                         doc_owner,
                         &import->primitives,
                         &import->nodes,
                         &coord,
                         options))
    return 0;

  akb_resolve_skin_joint_nodes(&import->primitives, &import->nodes);

  if (import->primitives.count > 0) {
    akb_list_set_coord_matrix(&import->primitives, &coord);
    return 1;
  }

  for (lib = doc->lib.geometries; lib; lib = lib->next) {
    for (geom = (AkGeometry *)lib->chld; geom; geom = (AkGeometry *)geom->base.next) {
      if (!akb_extract_mesh(&import->primitives,
                            &import->nodes,
                            doc,
                            doc_owner,
                            NULL,
                            NULL,
                            NULL,
                            -1,
                            geom,
                            options))
        return 0;
    }
  }

  akb_list_set_coord_matrix(&import->primitives, &coord);
  return 1;
}

static void
akb_import_free(AkbImport *import) {
  if (!import)
    return;
  akb_list_free(&import->primitives);
  akb_node_list_free(&import->nodes);
}

static void
akb_import_capsule_destructor(PyObject *capsule) {
  AkbImport *import;

  import = (AkbImport *)PyCapsule_GetPointer(capsule, "assetkit_blender.AkbImport");
  if (!import)
    return;

  akb_import_free(import);
  free(import);
}

static PyObject *
akb_memoryview_or_empty(const void *data, size_t size) {
  if (!data || size == 0)
    return PyBytes_FromStringAndSize(NULL, 0);
  return PyMemoryView_FromMemory((char *)data, (Py_ssize_t)size, PyBUF_READ);
}

static PyObject *
akb_unicode_from_cstr(const char *value) {
  PyObject *out;
  size_t len;

  if (!value)
    return PyUnicode_FromString("");

  len = strlen(value);
  out = PyUnicode_DecodeUTF8(value, (Py_ssize_t)len, "strict");
  if (out)
    return out;

  PyErr_Clear();
  out = PyUnicode_DecodeLatin1(value, (Py_ssize_t)len, "strict");
  if (out)
    return out;

  PyErr_Clear();
  return PyUnicode_DecodeUTF8(value, (Py_ssize_t)len, "replace");
}

static int
akb_py_dict_set_owned(PyObject *dict, const char *key, PyObject *value) {
  int ok;

  if (!value)
    return 0;
  ok = PyDict_SetItemString(dict, key, value) == 0;
  Py_DECREF(value);
  return ok;
}

static PyObject *
akb_tree_to_py_rec(const AkTreeNode *node, unsigned int depth) {
  const AkTreeNodeAttr *attr;
  const AkTreeNode *child;
  PyObject *dict;
  PyObject *attrs;
  PyObject *children;
  PyObject *item;

  if (!node || depth > 64)
    Py_RETURN_NONE;

  dict = PyDict_New();
  if (!dict)
    return NULL;

  if (!akb_py_dict_set_owned(dict, "name", akb_unicode_from_cstr(node->name))) {
    Py_DECREF(dict);
    return NULL;
  }
  if (!akb_py_dict_set_owned(dict, "value", akb_unicode_from_cstr(node->val))) {
    Py_DECREF(dict);
    return NULL;
  }

  attrs = PyDict_New();
  if (!attrs) {
    Py_DECREF(dict);
    return NULL;
  }
  for (attr = node->attribs; attr; attr = attr->next) {
    if (!attr->name)
      continue;
    item = akb_unicode_from_cstr(attr->val);
    if (!item) {
      Py_DECREF(attrs);
      Py_DECREF(dict);
      return NULL;
    }
    if (PyDict_SetItemString(attrs, attr->name, item) < 0) {
      Py_DECREF(item);
      Py_DECREF(attrs);
      Py_DECREF(dict);
      return NULL;
    }
    Py_DECREF(item);
  }
  if (PyDict_SetItemString(dict, "attributes", attrs) < 0) {
    Py_DECREF(attrs);
    Py_DECREF(dict);
    return NULL;
  }
  Py_DECREF(attrs);

  children = PyList_New(0);
  if (!children) {
    Py_DECREF(dict);
    return NULL;
  }
  for (child = node->chld; child; child = child->next) {
    item = akb_tree_to_py_rec(child, depth + 1);
    if (!item || PyList_Append(children, item) < 0) {
      Py_XDECREF(item);
      Py_DECREF(children);
      Py_DECREF(dict);
      return NULL;
    }
    Py_DECREF(item);
  }
  if (PyDict_SetItemString(dict, "children", children) < 0) {
    Py_DECREF(children);
    Py_DECREF(dict);
    return NULL;
  }
  Py_DECREF(children);

  return dict;
}

static PyObject *
akb_tree_to_py(const AkTree *tree) {
  if (!tree)
    Py_RETURN_NONE;
  return akb_tree_to_py_rec(tree, 0);
}

static PyObject *
akb_image_to_py(AkDoc *doc, AkImage *image, size_t index) {
  AkInitFrom *init_from;
  AkImageBase *base;
  PyObject *dict;
  char path[PATH_MAX];

  dict = PyDict_New();
  if (!dict)
    return NULL;

  init_from = image ? image->initFrom : NULL;
  base = image ? image->image : NULL;
  akb_copy_image_path(doc, image, path, sizeof(path));

#define AKB_IMAGE_SET_OBJ(KEY, VALUE) do {        \
    if (!akb_py_dict_set_owned(dict, (KEY), (VALUE))) { \
      Py_DECREF(dict);                            \
      return NULL;                                \
    }                                             \
  } while (0)

  AKB_IMAGE_SET_OBJ("index", PyLong_FromSize_t(index));
  AKB_IMAGE_SET_OBJ("name", akb_unicode_from_cstr(image ? image->name : NULL));
  AKB_IMAGE_SET_OBJ("path", akb_unicode_from_cstr(path));
  AKB_IMAGE_SET_OBJ("mime_type", akb_unicode_from_cstr(init_from ? init_from->buffMime : NULL));
  AKB_IMAGE_SET_OBJ("type", PyLong_FromLong(base ? (long)base->type : 0));
  AKB_IMAGE_SET_OBJ("embedded",
                    PyBool_FromLong(init_from && init_from->buff && init_from->buff->data));
  AKB_IMAGE_SET_OBJ("face", PyLong_FromLong(init_from ? (long)init_from->face : 0));
  AKB_IMAGE_SET_OBJ("mip_index", PyLong_FromUnsignedLong(init_from ? init_from->mipIndex : 0));
  AKB_IMAGE_SET_OBJ("array_index", PyLong_FromLong(init_from ? (long)init_from->arrayIndex : -1));
  AKB_IMAGE_SET_OBJ("depth", PyLong_FromUnsignedLong(init_from ? init_from->depth : 0));
  AKB_IMAGE_SET_OBJ("extra", akb_tree_to_py(image ? ak_extra(image) : NULL));

#undef AKB_IMAGE_SET_OBJ

  return dict;
}

static PyObject *
akb_doc_images_to_py(AkDoc *doc) {
  FListItem *item;
  PyObject *list;
  PyObject *image_obj;
  size_t index;

  list = PyList_New(0);
  if (!list)
    return NULL;

  if (!doc)
    return list;

  index = 0;
  for (item = doc->lib.images; item; item = item->next) {
    image_obj = akb_image_to_py(doc, (AkImage *)item->data, index++);
    if (!image_obj || PyList_Append(list, image_obj) < 0) {
      Py_XDECREF(image_obj);
      Py_DECREF(list);
      return NULL;
    }
    Py_DECREF(image_obj);
  }

  return list;
}

static size_t
akb_visual_scene_count(AkDoc *doc) {
  AkVisualScene *scene;
  size_t count = 0;

  if (!doc || !doc->lib.visualScenes)
    return 0;

  for (scene = (AkVisualScene *)doc->lib.visualScenes->chld;
       scene;
       scene = (AkVisualScene *)scene->base.next)
    count++;

  return count;
}

static int32_t
akb_visual_scene_index(AkDoc *doc, AkVisualScene *selected) {
  AkVisualScene *scene;
  int32_t index = 0;

  if (!doc || !doc->lib.visualScenes || !selected)
    return -1;

  for (scene = (AkVisualScene *)doc->lib.visualScenes->chld;
       scene;
       scene = (AkVisualScene *)scene->base.next, index++) {
    if (scene == selected)
      return index;
  }

  return -1;
}

static PyObject *
akb_visual_scene_names_to_py(AkDoc *doc) {
  AkVisualScene *scene;
  PyObject *list;
  PyObject *item;

  list = PyList_New(0);
  if (!list)
    return NULL;

  if (!doc || !doc->lib.visualScenes)
    return list;

  for (scene = (AkVisualScene *)doc->lib.visualScenes->chld;
       scene;
       scene = (AkVisualScene *)scene->base.next) {
    item = akb_unicode_from_cstr(scene->name);
    if (!item || PyList_Append(list, item) < 0) {
      Py_XDECREF(item);
      Py_DECREF(list);
      return NULL;
    }
    Py_DECREF(item);
  }

  return list;
}

static int
akb_set_scene_info(PyObject *out, AkDoc *doc, const AkbLoadOptions *options) {
  AkVisualScene *scene;

  scene = akb_selected_visual_scene(doc, options);

  return akb_py_dict_set_owned(out,
                               "scene_count",
                               PyLong_FromSize_t(akb_visual_scene_count(doc)))
         && akb_py_dict_set_owned(out,
                                  "scene_index",
                                  PyLong_FromLong(akb_visual_scene_index(doc, scene)))
         && akb_py_dict_set_owned(out,
                                  "scene_name",
                                  akb_unicode_from_cstr(scene ? scene->name : NULL))
         && akb_py_dict_set_owned(out,
                                  "scene_names",
                                  akb_visual_scene_names_to_py(doc))
         && akb_py_dict_set_owned(out,
                                  "scene_extra",
                                  akb_tree_to_py(scene ? ak_extra(scene) : NULL));
}

static PyObject *
akb_anim_channels_to_py(AkbAnimation *animation) {
  PyObject *list;
  PyObject *dict;
  PyObject *value;
  AkbAnimChannel *channel;
  size_t i;

  if (!animation || !animation->count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)animation->count);
  if (!list)
    return NULL;

#define AKB_CH_SET_OBJ(KEY, OBJ) do {              \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(dict); Py_DECREF(list); return NULL; } \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                            \
      Py_DECREF(dict);                             \
      Py_DECREF(list);                             \
      return NULL;                                 \
    }                                              \
    Py_DECREF(value);                              \
  } while (0)

  for (i = 0; i < animation->count; i++) {
    channel = &animation->channels[i];
    dict = PyDict_New();
    if (!dict) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_CH_SET_OBJ("target", PyLong_FromUnsignedLong(channel->target));
    AKB_CH_SET_OBJ("target_offset", PyLong_FromUnsignedLong(channel->target_offset));
    AKB_CH_SET_OBJ("clip_index", PyLong_FromUnsignedLong(channel->clip_index));
    AKB_CH_SET_OBJ("clip_name", akb_unicode_from_cstr(channel->clip_name));
    AKB_CH_SET_OBJ("value_width", PyLong_FromUnsignedLong(channel->value_width));
    AKB_CH_SET_OBJ("count", PyLong_FromUnsignedLong(channel->count));
    AKB_CH_SET_OBJ("interpolation", PyLong_FromUnsignedLong(channel->interpolation));
    AKB_CH_SET_OBJ("is_partial", PyBool_FromLong(channel->is_partial));
    AKB_CH_SET_OBJ("times_f32",
                   akb_memoryview_or_empty(channel->times,
                                           (size_t)channel->count * sizeof(float)));
    AKB_CH_SET_OBJ("values_f32",
                   akb_memoryview_or_empty(channel->values,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));
    AKB_CH_SET_OBJ("in_tangents_f32",
                   akb_memoryview_or_empty(channel->in_tangents,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));
    AKB_CH_SET_OBJ("out_tangents_f32",
                   akb_memoryview_or_empty(channel->out_tangents,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));

    PyList_SET_ITEM(list, (Py_ssize_t)i, dict);
  }

#undef AKB_CH_SET_OBJ

  return list;
}

static PyObject *
akb_loop_float_attrs_to_py(AkbLoopFloatAttribute *attrs, uint32_t count, uint32_t loop_count) {
  PyObject *list;
  PyObject *dict;
  PyObject *value;
  uint32_t i;

  if (!attrs || !count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)count);
  if (!list)
    return NULL;

#define AKB_ATTR_SET_OBJ(KEY, OBJ) do {           \
    value = (OBJ);                                \
    if (!value) { Py_DECREF(dict); Py_DECREF(list); return NULL; } \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                           \
      Py_DECREF(dict);                            \
      Py_DECREF(list);                            \
      return NULL;                                \
    }                                             \
    Py_DECREF(value);                             \
  } while (0)

  for (i = 0; i < count; i++) {
    dict = PyDict_New();
    if (!dict) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_ATTR_SET_OBJ("name", akb_unicode_from_cstr(attrs[i].name));
    AKB_ATTR_SET_OBJ("set", PyLong_FromUnsignedLong(attrs[i].set));
    AKB_ATTR_SET_OBJ("width", PyLong_FromUnsignedLong(attrs[i].width));
    AKB_ATTR_SET_OBJ("values_f32",
                     akb_memoryview_or_empty(attrs[i].values,
                                             attrs[i].values
                                             ? (size_t)loop_count
                                               * attrs[i].width
                                               * sizeof(float)
                                             : 0));

    PyList_SET_ITEM(list, (Py_ssize_t)i, dict);
  }

#undef AKB_ATTR_SET_OBJ

  return list;
}

static PyObject *
akb_texture_infos_to_py(AkbTextureInfo *infos, uint32_t count) {
  PyObject *dict;
  PyObject *item;
  PyObject *value;
  uint32_t i;

  dict = PyDict_New();
  if (!dict)
    return NULL;

#define AKB_TEX_SET_OBJ(KEY, OBJ) do {            \
    value = (OBJ);                                \
    if (!value) { Py_DECREF(item); Py_DECREF(dict); return NULL; } \
    if (PyDict_SetItemString(item, (KEY), value) < 0) { \
      Py_DECREF(value);                           \
      Py_DECREF(item);                            \
      Py_DECREF(dict);                            \
      return NULL;                                \
    }                                             \
    Py_DECREF(value);                             \
  } while (0)

  for (i = 0; i < count; i++) {
    item = PyDict_New();
    if (!item) {
      Py_DECREF(dict);
      return NULL;
    }

    AKB_TEX_SET_OBJ("path", akb_unicode_from_cstr(infos[i].path));
    AKB_TEX_SET_OBJ("image_name", akb_unicode_from_cstr(infos[i].image_name));
    AKB_TEX_SET_OBJ("sampler_name", akb_unicode_from_cstr(infos[i].sampler_name));
    AKB_TEX_SET_OBJ("color_space", akb_unicode_from_cstr(infos[i].color_space));
    AKB_TEX_SET_OBJ("channels", akb_unicode_from_cstr(infos[i].channels));
    AKB_TEX_SET_OBJ("texcoord", akb_unicode_from_cstr(infos[i].texcoord));
    AKB_TEX_SET_OBJ("coord_input_name", akb_unicode_from_cstr(infos[i].coord_input_name));
    AKB_TEX_SET_OBJ("slot", PyLong_FromLong(infos[i].slot));
    AKB_TEX_SET_OBJ("wrap_s", PyLong_FromLong(infos[i].wrap_s));
    AKB_TEX_SET_OBJ("wrap_t", PyLong_FromLong(infos[i].wrap_t));
    AKB_TEX_SET_OBJ("wrap_p", PyLong_FromLong(infos[i].wrap_p));
    AKB_TEX_SET_OBJ("min_filter", PyLong_FromLong(infos[i].min_filter));
    AKB_TEX_SET_OBJ("mag_filter", PyLong_FromLong(infos[i].mag_filter));
    AKB_TEX_SET_OBJ("mip_filter", PyLong_FromLong(infos[i].mip_filter));
    AKB_TEX_SET_OBJ("texture_extra", akb_tree_to_py(infos[i].texture_extra));
    AKB_TEX_SET_OBJ("texref_extra", akb_tree_to_py(infos[i].texref_extra));
    AKB_TEX_SET_OBJ("image_extra", akb_tree_to_py(infos[i].image_extra));
    AKB_TEX_SET_OBJ("sampler_extra", akb_tree_to_py(infos[i].sampler_extra));
    AKB_TEX_SET_OBJ("has_transform", PyBool_FromLong(infos[i].has_transform));
    AKB_TEX_SET_OBJ("transform_offset", Py_BuildValue("(ff)",
                                                      infos[i].transform_offset[0],
                                                      infos[i].transform_offset[1]));
    AKB_TEX_SET_OBJ("transform_scale", Py_BuildValue("(ff)",
                                                     infos[i].transform_scale[0],
                                                     infos[i].transform_scale[1]));
    AKB_TEX_SET_OBJ("transform_rotation",
                    PyFloat_FromDouble(infos[i].transform_rotation));
    AKB_TEX_SET_OBJ("transform_slot", PyLong_FromLong(infos[i].transform_slot));

    if (PyDict_SetItemString(dict, infos[i].role, item) < 0) {
      Py_DECREF(item);
      Py_DECREF(dict);
      return NULL;
    }
    Py_DECREF(item);
  }

#undef AKB_TEX_SET_OBJ

  return dict;
}

static PyObject *
akb_primitive_to_py(AkbPrimitive *prim, PyObject *owner);

static PyObject *
akb_material_variants_to_py(AkbPrimitive *prim, PyObject *owner) {
  PyObject *list;
  PyObject *dict;
  PyObject *value;
  AkMeshPrimitive material_prim;
  AkbPrimitive material_data;
  uint32_t i;

  if (!prim->material_variants || !prim->material_variant_count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)prim->material_variant_count);
  if (!list)
    return NULL;

#define AKB_VARIANT_SET_OBJ(KEY, OBJ) do {        \
    value = (OBJ);                                \
    if (!value) { Py_DECREF(dict); Py_DECREF(list); return NULL; } \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                           \
      Py_DECREF(dict);                            \
      Py_DECREF(list);                            \
      return NULL;                                \
    }                                             \
    Py_DECREF(value);                             \
  } while (0)

  for (i = 0; i < prim->material_variant_count; i++) {
    dict = PyDict_New();
    if (!dict) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_VARIANT_SET_OBJ("variant_index",
                        PyLong_FromUnsignedLong(prim->material_variants[i].variant_index));
    AKB_VARIANT_SET_OBJ("variant_name",
                        akb_unicode_from_cstr(prim->material_variants[i].variant_name));
    AKB_VARIANT_SET_OBJ("material_name",
                        akb_unicode_from_cstr(prim->material_variants[i].material_name));
    if (prim->material_variants[i].material) {
      memset(&material_prim, 0, sizeof(material_prim));
      memset(&material_data, 0, sizeof(material_data));
      material_prim.material = prim->material_variants[i].material;
      material_data.file_type = prim->file_type;
      akb_extract_material(prim->doc_owner ? prim->doc_owner->doc : NULL,
                           &material_prim,
                           NULL,
                           &material_data);
      AKB_VARIANT_SET_OBJ("material", akb_primitive_to_py(&material_data, owner));
    }

    PyList_SET_ITEM(list, (Py_ssize_t)i, dict);
  }

#undef AKB_VARIANT_SET_OBJ

  return list;
}

static PyObject *
akb_morph_targets_to_py(AkbPrimitive *prim) {
  PyObject *list;
  PyObject *dict;
  PyObject *value;
  AkbMorphTarget *target;
  uint32_t i;

  if (!prim || !prim->morph_target_count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)prim->morph_target_count);
  if (!list)
    return NULL;

#define AKB_MT_SET_OBJ(KEY, OBJ) do {              \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(dict); Py_DECREF(list); return NULL; } \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                            \
      Py_DECREF(dict);                             \
      Py_DECREF(list);                             \
      return NULL;                                 \
    }                                              \
    Py_DECREF(value);                              \
  } while (0)

  for (i = 0; i < prim->morph_target_count; i++) {
    target = &prim->morph_targets[i];
    dict = PyDict_New();
    if (!dict) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_MT_SET_OBJ("name", akb_unicode_from_cstr(target->name));
    AKB_MT_SET_OBJ("weight", PyFloat_FromDouble(target->weight));
    AKB_MT_SET_OBJ("vertex_count", PyLong_FromUnsignedLong(target->vertex_count));
    AKB_MT_SET_OBJ("positions_f32",
                   akb_memoryview_or_empty(target->positions,
                                           (size_t)target->vertex_count
                                           * 3
                                           * sizeof(float)));

    PyList_SET_ITEM(list, (Py_ssize_t)i, dict);
  }

#undef AKB_MT_SET_OBJ

  return list;
}

static PyObject *
akb_float_array_to_py(const float *values, uint32_t count) {
  PyObject *list;
  PyObject *item;
  uint32_t i;

  list = PyList_New((Py_ssize_t)count);
  if (!list)
    return NULL;

  for (i = 0; i < count; i++) {
    item = PyFloat_FromDouble(values ? values[i] : 0.0f);
    if (!item) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, (Py_ssize_t)i, item);
  }

  return list;
}

static PyObject *
akb_morph_presets_to_py(AkbPrimitive *prim) {
  AkMorphPreset *preset;
  PyObject *list;
  PyObject *dict;
  PyObject *value;
  uint32_t i;

  if (!prim || !prim->morph_presets || !prim->morph_preset_count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)prim->morph_preset_count);
  if (!list)
    return NULL;

#define AKB_MP_SET_OBJ(KEY, OBJ) do {              \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(dict); Py_DECREF(list); return NULL; } \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                            \
      Py_DECREF(dict);                             \
      Py_DECREF(list);                             \
      return NULL;                                 \
    }                                              \
    Py_DECREF(value);                              \
  } while (0)

  for (i = 0; i < prim->morph_preset_count; i++) {
    preset = &prim->morph_presets[i];
    dict = PyDict_New();
    if (!dict) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_MP_SET_OBJ("name", akb_unicode_from_cstr(preset->name));
    AKB_MP_SET_OBJ("weight_count",
                   PyLong_FromUnsignedLong(preset->weights
                                           ? preset->weights->count
                                           : 0));
    AKB_MP_SET_OBJ("weights",
                   akb_float_array_to_py(preset->weights
                                         ? preset->weights->items
                                         : NULL,
                                         preset->weights
                                         ? preset->weights->count
                                         : 0));

    PyList_SET_ITEM(list, (Py_ssize_t)i, dict);
  }

#undef AKB_MP_SET_OBJ

  return list;
}

static PyObject *
akb_primitive_to_py(AkbPrimitive *prim, PyObject *owner) {
  PyObject *dict;
  PyObject *value;

  dict = PyDict_New();
  if (!dict)
    return NULL;

#define AKB_SET_OBJ(KEY, OBJ) do {                 \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(dict); return NULL; }  \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                            \
      Py_DECREF(dict);                             \
      return NULL;                                 \
    }                                              \
    Py_DECREF(value);                              \
  } while (0)

  if (PyDict_SetItemString(dict, "_owner", owner) < 0) {
    Py_DECREF(dict);
    return NULL;
  }

  AKB_SET_OBJ("name", akb_unicode_from_cstr(prim->name));
  AKB_SET_OBJ("object_name", akb_unicode_from_cstr(prim->object_name));
  AKB_SET_OBJ("vertex_count", PyLong_FromUnsignedLong(prim->vertex_count));
  AKB_SET_OBJ("loop_count", PyLong_FromUnsignedLong(prim->loop_count));
  AKB_SET_OBJ("face_count", PyLong_FromUnsignedLong(prim->face_count));
  AKB_SET_OBJ("primitive_type", PyLong_FromUnsignedLong(prim->primitive_type));
  AKB_SET_OBJ("primitive_mode", PyLong_FromUnsignedLong(prim->primitive_mode));
  AKB_SET_OBJ("material_name", akb_unicode_from_cstr(prim->material_name));
  AKB_SET_OBJ("base_color", Py_BuildValue("(ffff)",
                                          prim->base_color[0],
                                          prim->base_color[1],
                                          prim->base_color[2],
                                          prim->base_color[3]));
  AKB_SET_OBJ("transparent_color", Py_BuildValue("(ffff)",
                                                 prim->transparent_color[0],
                                                 prim->transparent_color[1],
                                                 prim->transparent_color[2],
                                                 prim->transparent_color[3]));
  AKB_SET_OBJ("emissive_color", Py_BuildValue("(fff)",
                                             prim->emissive_color[0],
                                             prim->emissive_color[1],
                                             prim->emissive_color[2]));
  AKB_SET_OBJ("specular_color", Py_BuildValue("(fff)",
                                             prim->specular_color[0],
                                             prim->specular_color[1],
                                             prim->specular_color[2]));
  AKB_SET_OBJ("sheen_color", Py_BuildValue("(fff)",
                                          prim->sheen_color[0],
                                          prim->sheen_color[1],
                                          prim->sheen_color[2]));
  AKB_SET_OBJ("volume_attenuation_color", Py_BuildValue("(fff)",
                                                        prim->volume_attenuation_color[0],
                                                        prim->volume_attenuation_color[1],
                                                        prim->volume_attenuation_color[2]));
  AKB_SET_OBJ("diffuse_transmission_color", Py_BuildValue("(fff)",
                                                          prim->diffuse_transmission_color[0],
                                                          prim->diffuse_transmission_color[1],
                                                          prim->diffuse_transmission_color[2]));
  AKB_SET_OBJ("metallic", PyFloat_FromDouble(prim->metallic));
  AKB_SET_OBJ("roughness", PyFloat_FromDouble(prim->roughness));
  AKB_SET_OBJ("alpha_cutoff", PyFloat_FromDouble(prim->alpha_cutoff));
  AKB_SET_OBJ("transparent_amount", PyFloat_FromDouble(prim->transparent_amount));
  AKB_SET_OBJ("opacity", PyFloat_FromDouble(prim->opacity));
  AKB_SET_OBJ("normal_scale", PyFloat_FromDouble(prim->normal_scale));
  AKB_SET_OBJ("occlusion_strength", PyFloat_FromDouble(prim->occlusion_strength));
  AKB_SET_OBJ("emissive_strength", PyFloat_FromDouble(prim->emissive_strength));
  AKB_SET_OBJ("specular_strength", PyFloat_FromDouble(prim->specular_strength));
  AKB_SET_OBJ("ior", PyFloat_FromDouble(prim->ior));
  AKB_SET_OBJ("clearcoat", PyFloat_FromDouble(prim->clearcoat));
  AKB_SET_OBJ("clearcoat_roughness", PyFloat_FromDouble(prim->clearcoat_roughness));
  AKB_SET_OBJ("clearcoat_normal_scale", PyFloat_FromDouble(prim->clearcoat_normal_scale));
  AKB_SET_OBJ("transmission", PyFloat_FromDouble(prim->transmission));
  AKB_SET_OBJ("sheen_roughness", PyFloat_FromDouble(prim->sheen_roughness));
  AKB_SET_OBJ("iridescence", PyFloat_FromDouble(prim->iridescence));
  AKB_SET_OBJ("iridescence_ior", PyFloat_FromDouble(prim->iridescence_ior));
  AKB_SET_OBJ("iridescence_thickness_minimum",
              PyFloat_FromDouble(prim->iridescence_thickness_minimum));
  AKB_SET_OBJ("iridescence_thickness_maximum",
              PyFloat_FromDouble(prim->iridescence_thickness_maximum));
  AKB_SET_OBJ("volume_thickness", PyFloat_FromDouble(prim->volume_thickness));
  AKB_SET_OBJ("volume_attenuation_distance",
              PyFloat_FromDouble(prim->volume_attenuation_distance));
  AKB_SET_OBJ("anisotropy", PyFloat_FromDouble(prim->anisotropy));
  AKB_SET_OBJ("anisotropy_rotation", PyFloat_FromDouble(prim->anisotropy_rotation));
  AKB_SET_OBJ("diffuse_transmission", PyFloat_FromDouble(prim->diffuse_transmission));
  AKB_SET_OBJ("dispersion", PyFloat_FromDouble(prim->dispersion));
  AKB_SET_OBJ("alpha_mode", PyLong_FromUnsignedLong(prim->alpha_mode));
  AKB_SET_OBJ("transparent_opaque", PyLong_FromUnsignedLong(prim->transparent_opaque));
  AKB_SET_OBJ("double_sided", PyBool_FromLong(prim->double_sided));
  AKB_SET_OBJ("material_type", PyLong_FromUnsignedLong(prim->material_type));
  AKB_SET_OBJ("file_type", PyLong_FromUnsignedLong(prim->file_type));
  AKB_SET_OBJ("has_node", PyBool_FromLong(prim->has_node));
  AKB_SET_OBJ("node_index", PyLong_FromLong(prim->node_index));
  AKB_SET_OBJ("instance_count", PyLong_FromUnsignedLong(prim->instance_count));
  AKB_SET_OBJ("has_gsplat", PyBool_FromLong(prim->has_gsplat));
  AKB_SET_OBJ("gsplat_kernel", PyLong_FromUnsignedLong(prim->gsplat.kernel));
  AKB_SET_OBJ("gsplat_color_space", PyLong_FromUnsignedLong(prim->gsplat.color_space));
  AKB_SET_OBJ("gsplat_projection", PyLong_FromUnsignedLong(prim->gsplat.projection));
  AKB_SET_OBJ("gsplat_sorting_method", PyLong_FromUnsignedLong(prim->gsplat.sorting_method));
  AKB_SET_OBJ("gsplat_decoded_count", PyLong_FromUnsignedLong(prim->gsplat.decoded_count));
  AKB_SET_OBJ("has_skin", PyBool_FromLong(prim->has_skin));
  AKB_SET_OBJ("has_sheen", PyBool_FromLong(prim->has_sheen));
  AKB_SET_OBJ("skin_vertex_count", PyLong_FromUnsignedLong(prim->skin_vertex_count));
  AKB_SET_OBJ("skin_joint_count", PyLong_FromUnsignedLong(prim->skin_joint_count));
  AKB_SET_OBJ("skin_joint_width", PyLong_FromUnsignedLong(prim->skin_joint_width));
  AKB_SET_OBJ("skin_root_node_index", PyLong_FromLong(prim->skin_root_node_index));
  AKB_SET_OBJ("skin_mesh_in_bind_pose", PyBool_FromLong(prim->skin_mesh_in_bind_pose));
  AKB_SET_OBJ("zero_copy_flags", PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SET_OBJ("uv_set_count", PyLong_FromUnsignedLong(prim->uv_set_count));
  AKB_SET_OBJ("color_set_count", PyLong_FromUnsignedLong(prim->color_set_count));
  AKB_SET_OBJ("point_attr_count", PyLong_FromUnsignedLong(prim->point_attr_count));
  AKB_SET_OBJ("anim_count",
              PyLong_FromUnsignedLong(prim->animation
                                      ? (unsigned long)prim->animation->count
                                      : 0));
  AKB_SET_OBJ("anim_channels", akb_anim_channels_to_py(prim->animation));
  AKB_SET_OBJ("morph_target_count", PyLong_FromUnsignedLong(prim->morph_target_count));
  AKB_SET_OBJ("morph_targets", akb_morph_targets_to_py(prim));
  AKB_SET_OBJ("morph_preset_count", PyLong_FromUnsignedLong(prim->morph_preset_count));
  AKB_SET_OBJ("morph_presets", akb_morph_presets_to_py(prim));
  AKB_SET_OBJ("morph_anim_count",
              PyLong_FromUnsignedLong(prim->morph_animation
                                      ? (unsigned long)prim->morph_animation->count
                                      : 0));
  AKB_SET_OBJ("morph_anim_channels", akb_anim_channels_to_py(prim->morph_animation));
  AKB_SET_OBJ("material_anim_count",
              PyLong_FromUnsignedLong(prim->material_animation
                                      ? (unsigned long)prim->material_animation->count
                                      : 0));
  AKB_SET_OBJ("material_anim_channels", akb_anim_channels_to_py(prim->material_animation));
  AKB_SET_OBJ("uv_sets", akb_loop_float_attrs_to_py(prim->uv_sets,
                                                    prim->uv_set_count,
                                                    prim->loop_count));
  AKB_SET_OBJ("color_sets", akb_loop_float_attrs_to_py(prim->color_sets,
                                                       prim->color_set_count,
                                                       prim->loop_count));
  AKB_SET_OBJ("point_attrs", akb_loop_float_attrs_to_py(prim->point_attrs,
                                                        prim->point_attr_count,
                                                        prim->vertex_count));
  AKB_SET_OBJ("texture_infos", akb_texture_infos_to_py(prim->texture_infos,
                                                       prim->texture_info_count));
  AKB_SET_OBJ("primitive_extra", akb_tree_to_py(prim->primitive_extra));
  AKB_SET_OBJ("mesh_extra", akb_tree_to_py(prim->mesh_extra));
  AKB_SET_OBJ("geometry_extra", akb_tree_to_py(prim->geometry_extra));
  AKB_SET_OBJ("material_extra", akb_tree_to_py(prim->material_extra));
  AKB_SET_OBJ("effect_extra", akb_tree_to_py(prim->effect_extra));
  AKB_SET_OBJ("material_variant_count",
              PyLong_FromUnsignedLong(prim->material_variant_count));
  AKB_SET_OBJ("material_variants", akb_material_variants_to_py(prim, owner));
  AKB_SET_OBJ("matrix_f32", akb_memoryview_or_empty(prim->matrix, prim->has_node ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ("coord_matrix_f32",
              akb_memoryview_or_empty(prim->coord_matrix,
                                      prim->has_coord_matrix ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ("instance_matrices_f32",
              akb_memoryview_or_empty(prim->instance_matrices,
                                      prim->instance_count
                                      ? (size_t)prim->instance_count
                                        * 16
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ("base_color_texture", akb_unicode_from_cstr(prim->base_color_texture));
  AKB_SET_OBJ("metallic_roughness_texture", akb_unicode_from_cstr(prim->metallic_roughness_texture));
  AKB_SET_OBJ("occlusion_texture", akb_unicode_from_cstr(prim->occlusion_texture));
  AKB_SET_OBJ("normal_texture", akb_unicode_from_cstr(prim->normal_texture));
  AKB_SET_OBJ("emissive_texture", akb_unicode_from_cstr(prim->emissive_texture));
  AKB_SET_OBJ("transparent_texture", akb_unicode_from_cstr(prim->transparent_texture));
  AKB_SET_OBJ("specular_texture", akb_unicode_from_cstr(prim->specular_texture));
  AKB_SET_OBJ("specular_color_texture", akb_unicode_from_cstr(prim->specular_color_texture));
  AKB_SET_OBJ("clearcoat_texture", akb_unicode_from_cstr(prim->clearcoat_texture));
  AKB_SET_OBJ("clearcoat_roughness_texture", akb_unicode_from_cstr(prim->clearcoat_roughness_texture));
  AKB_SET_OBJ("clearcoat_normal_texture", akb_unicode_from_cstr(prim->clearcoat_normal_texture));
  AKB_SET_OBJ("transmission_texture", akb_unicode_from_cstr(prim->transmission_texture));
  AKB_SET_OBJ("sheen_color_texture", akb_unicode_from_cstr(prim->sheen_color_texture));
  AKB_SET_OBJ("sheen_roughness_texture", akb_unicode_from_cstr(prim->sheen_roughness_texture));
  AKB_SET_OBJ("iridescence_texture", akb_unicode_from_cstr(prim->iridescence_texture));
  AKB_SET_OBJ("iridescence_thickness_texture",
              akb_unicode_from_cstr(prim->iridescence_thickness_texture));
  AKB_SET_OBJ("volume_thickness_texture", akb_unicode_from_cstr(prim->volume_thickness_texture));
  AKB_SET_OBJ("anisotropy_texture", akb_unicode_from_cstr(prim->anisotropy_texture));
  AKB_SET_OBJ("diffuse_transmission_texture",
              akb_unicode_from_cstr(prim->diffuse_transmission_texture));
  AKB_SET_OBJ("diffuse_transmission_color_texture",
              akb_unicode_from_cstr(prim->diffuse_transmission_color_texture));
  AKB_SET_OBJ("vertices_f32", akb_memoryview_or_empty(prim->vertices, (size_t)prim->vertex_count * 3 * sizeof(float)));
  AKB_SET_OBJ("indices_u32", akb_memoryview_or_empty(prim->indices, (size_t)prim->loop_count * sizeof(uint32_t)));
  AKB_SET_OBJ("loop_starts_i32", akb_memoryview_or_empty(prim->loop_starts, (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ("loop_totals_i32", akb_memoryview_or_empty(prim->loop_totals, (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ("normals_f32", akb_memoryview_or_empty(prim->normals, prim->has_normals ? (size_t)prim->loop_count * 3 * sizeof(float) : 0));
  AKB_SET_OBJ("uvs_f32", akb_memoryview_or_empty(prim->uvs, prim->has_uvs ? (size_t)prim->loop_count * 2 * sizeof(float) : 0));
  AKB_SET_OBJ("colors_f32", akb_memoryview_or_empty(prim->colors, prim->has_colors ? (size_t)prim->loop_count * 4 * sizeof(float) : 0));
  AKB_SET_OBJ("tangents_f32",
              akb_memoryview_or_empty(prim->tangents,
                                      prim->has_tangents
                                      ? (size_t)prim->loop_count
                                        * 4
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ("skin_joints_u16",
              akb_memoryview_or_empty(prim->skin_joints,
                                      prim->has_skin
                                      ? (size_t)prim->skin_vertex_count
                                        * prim->skin_joint_width
                                        * sizeof(uint16_t)
                                      : 0));
  AKB_SET_OBJ("skin_weights_f32",
              akb_memoryview_or_empty(prim->skin_weights,
                                      prim->has_skin
                                      ? (size_t)prim->skin_vertex_count
                                        * prim->skin_joint_width
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ("skin_joint_nodes_i32",
              akb_memoryview_or_empty(prim->skin_joint_nodes,
                                      prim->has_skin
                                      ? (size_t)prim->skin_joint_count
                                        * sizeof(int32_t)
                                      : 0));
  AKB_SET_OBJ("skin_inverse_bind_matrices_f32",
              akb_memoryview_or_empty(prim->skin_inverse_bind_matrices,
                                      prim->has_skin && prim->skin_inverse_bind_matrices
                                      ? (size_t)prim->skin_joint_count
                                        * 16
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ("skin_bind_shape_matrix_f32",
              akb_memoryview_or_empty(prim->skin_bind_shape_matrix,
                                      prim->has_skin ? 16 * sizeof(float) : 0));

#undef AKB_SET_OBJ

  return dict;
}

static PyObject *
akb_string_array_to_py(AkStringArray *array) {
  PyObject *list;
  PyObject *item;
  size_t i;

  if (!array || !array->count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)array->count);
  if (!list)
    return NULL;

  for (i = 0; i < array->count; i++) {
    item = akb_unicode_from_cstr(array->items[i]);
    if (!item) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, (Py_ssize_t)i, item);
  }

  return list;
}

static PyObject *
akb_scene_node_to_py(AkbSceneNode *node, PyObject *owner) {
  PyObject *dict;
  PyObject *value;

  dict = PyDict_New();
  if (!dict)
    return NULL;

#define AKB_NODE_SET_OBJ(KEY, OBJ) do {            \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(dict); return NULL; }  \
    if (PyDict_SetItemString(dict, (KEY), value) < 0) { \
      Py_DECREF(value);                            \
      Py_DECREF(dict);                             \
      return NULL;                                 \
    }                                              \
    Py_DECREF(value);                              \
  } while (0)

  if (PyDict_SetItemString(dict, "_owner", owner) < 0) {
    Py_DECREF(dict);
    return NULL;
  }

  AKB_NODE_SET_OBJ("name", akb_unicode_from_cstr(node->name));
  AKB_NODE_SET_OBJ("parent_index", PyLong_FromLong(node->parent_index));
  AKB_NODE_SET_OBJ("visible", PyBool_FromLong(node->visible));
  AKB_NODE_SET_OBJ("layers", akb_string_array_to_py(node->layers));
  AKB_NODE_SET_OBJ("camera_type", PyLong_FromUnsignedLong(node->camera_type));
  AKB_NODE_SET_OBJ("camera_name", akb_unicode_from_cstr(node->camera_name));
  AKB_NODE_SET_OBJ("camera_extra", akb_tree_to_py(node->camera_extra));
  AKB_NODE_SET_OBJ("camera_imager_extra", akb_tree_to_py(node->camera_imager_extra));
  AKB_NODE_SET_OBJ("camera_values", Py_BuildValue("(ffffff)",
                                                  node->camera_values[0],
                                                  node->camera_values[1],
                                                  node->camera_values[2],
                                                  node->camera_values[3],
                                                  node->camera_values[4],
                                                  node->camera_values[5]));
  AKB_NODE_SET_OBJ("light_type", PyLong_FromUnsignedLong(node->light_type));
  AKB_NODE_SET_OBJ("light_name", akb_unicode_from_cstr(node->light_name));
  AKB_NODE_SET_OBJ("light_extra", akb_tree_to_py(node->light_extra));
  AKB_NODE_SET_OBJ("light_color", Py_BuildValue("(fff)",
                                                node->light_color[0],
                                                node->light_color[1],
                                                node->light_color[2]));
  AKB_NODE_SET_OBJ("light_values", Py_BuildValue("(fffff)",
                                                 node->light_values[0],
                                                 node->light_values[1],
                                                 node->light_values[2],
                                                 node->light_values[3],
                                                 node->light_values[4]));
  AKB_NODE_SET_OBJ("matrix_f32",
                   akb_memoryview_or_empty(node->matrix,
                                           node->has_transform ? 16 * sizeof(float) : 0));
  AKB_NODE_SET_OBJ("extra", akb_tree_to_py(node->source ? ak_extra(node->source) : NULL));
  AKB_NODE_SET_OBJ("anim_count",
                   PyLong_FromUnsignedLong(node->animation
                                           ? (unsigned long)node->animation->count
                                           : 0));
  AKB_NODE_SET_OBJ("anim_channels", akb_anim_channels_to_py(node->animation));

#undef AKB_NODE_SET_OBJ

  return dict;
}

static PyThread_type_lock akb_load_lock;

static int
akb_load_lock_ensure(void) {
  if (akb_load_lock)
    return 1;

  akb_load_lock = PyThread_allocate_lock();
  if (akb_load_lock)
    return 1;

  PyErr_SetString(PyExc_RuntimeError, "AssetKit bridge could not create load lock");
  return 0;
}

static PyObject *
akb_load_meshes(PyObject *self, PyObject *args) {
  const char *filepath;
  AkDoc *doc = NULL;
  AkbLoadOptions options;
  AkbSavedOptions saved_options;
  AkbSharedDoc *doc_owner;
  AkResult result;
  AkbImport import = {0};
  AkbImport *owner_import;
  PyObject *options_obj = NULL;
  PyObject *out;
  PyObject *mesh_list;
  PyObject *node_list;
  PyObject *owner;
  PyObject *item;
  size_t i;
  int ok;

  (void)self;

  if (!PyArg_ParseTuple(args, "s|O", &filepath, &options_obj))
    return NULL;

  if (!akb_load_options_from_dict(&options, options_obj))
    return NULL;
  if (!akb_load_lock_ensure())
    return NULL;

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  Py_BEGIN_ALLOW_THREADS
  PyThread_acquire_lock(akb_load_lock, WAIT_LOCK);
  akb_options_apply(&options, &saved_options);
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  doc_owner->doc = doc;
  if (result == AK_OK && doc)
    ok = akb_extract_doc(doc, doc_owner, &import, &options);
  else
    ok = 0;
  akb_options_restore(&saved_options);
  PyThread_release_lock(akb_load_lock);
  Py_END_ALLOW_THREADS

  if (result != AK_OK || !doc) {
    PyErr_Format(PyExc_RuntimeError, "AssetKit failed to load file: result=%d", result);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (!ok) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    PyErr_SetString(PyExc_MemoryError, "AssetKit bridge could not prepare mesh buffers");
    return NULL;
  }

  out = PyDict_New();
  if (!out) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  mesh_list = PyList_New((Py_ssize_t)import.primitives.count);
  node_list = PyList_New((Py_ssize_t)import.nodes.count);
  if (!mesh_list || !node_list) {
    Py_XDECREF(mesh_list);
    Py_XDECREF(node_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  owner_import = (AkbImport *)malloc(sizeof(*owner_import));
  if (!owner_import) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return PyErr_NoMemory();
  }

  *owner_import = import;
  memset(&import, 0, sizeof(import));

  owner = PyCapsule_New(owner_import,
                        "assetkit_blender.AkbImport",
                        akb_import_capsule_destructor);
  if (!owner) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    akb_import_free(owner_import);
    free(owner_import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  for (i = 0; i < owner_import->primitives.count; i++) {
    item = akb_primitive_to_py(&owner_import->primitives.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(mesh_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(mesh_list, (Py_ssize_t)i, item);
  }

  for (i = 0; i < owner_import->nodes.count; i++) {
    item = akb_scene_node_to_py(&owner_import->nodes.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(mesh_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(node_list, (Py_ssize_t)i, item);
  }

  if (PyDict_SetItemString(out, "meshes", mesh_list) < 0
      || PyDict_SetItemString(out, "nodes", node_list) < 0) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  item = akb_tree_to_py(ak_extra(doc));
  if (!item || PyDict_SetItemString(out, "doc_extra", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  item = akb_doc_images_to_py(doc);
  if (!item || PyDict_SetItemString(out, "images", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  if (!akb_set_scene_info(out, doc, &options)) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  Py_DECREF(node_list);
  Py_DECREF(mesh_list);
  Py_DECREF(owner);
  akb_shared_doc_release(doc_owner);
  return out;
}

static PyObject *
akb_open_scene(PyObject *self, PyObject *args) {
  const char *filepath;
  AkDoc *doc = NULL;
  AkbLoadOptions options;
  AkbSavedOptions saved_options;
  AkbSharedDoc *doc_owner;
  AkResult result;
  AkbImport import = {0};
  AkbImport *owner_import;
  PyObject *options_obj = NULL;
  PyObject *out;
  PyObject *node_list;
  PyObject *owner;
  PyObject *item;
  size_t i;
  int ok;

  (void)self;

  if (!PyArg_ParseTuple(args, "s|O", &filepath, &options_obj))
    return NULL;

  if (!akb_load_options_from_dict(&options, options_obj))
    return NULL;
  if (!akb_load_lock_ensure())
    return NULL;

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  Py_BEGIN_ALLOW_THREADS
  PyThread_acquire_lock(akb_load_lock, WAIT_LOCK);
  akb_options_apply(&options, &saved_options);
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  doc_owner->doc = doc;
  if (result == AK_OK && doc)
    ok = akb_extract_doc(doc, doc_owner, &import, &options);
  else
    ok = 0;
  akb_options_restore(&saved_options);
  PyThread_release_lock(akb_load_lock);
  Py_END_ALLOW_THREADS

  if (result != AK_OK || !doc) {
    PyErr_Format(PyExc_RuntimeError, "AssetKit failed to load file: result=%d", result);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (!ok) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    PyErr_SetString(PyExc_MemoryError, "AssetKit bridge could not prepare mesh buffers");
    return NULL;
  }

  out = PyDict_New();
  if (!out) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  node_list = PyList_New((Py_ssize_t)import.nodes.count);
  if (!node_list) {
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  owner_import = (AkbImport *)malloc(sizeof(*owner_import));
  if (!owner_import) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return PyErr_NoMemory();
  }

  *owner_import = import;
  memset(&import, 0, sizeof(import));

  owner = PyCapsule_New(owner_import,
                        "assetkit_blender.AkbImport",
                        akb_import_capsule_destructor);
  if (!owner) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    akb_import_free(owner_import);
    free(owner_import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  for (i = 0; i < owner_import->nodes.count; i++) {
    item = akb_scene_node_to_py(&owner_import->nodes.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(node_list, (Py_ssize_t)i, item);
  }

  item = PyLong_FromSize_t(owner_import->primitives.count);
  if (!item) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (PyDict_SetItemString(out, "_owner", owner) < 0
      || PyDict_SetItemString(out, "nodes", node_list) < 0
      || PyDict_SetItemString(out, "mesh_count", item) < 0) {
    Py_DECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  item = akb_tree_to_py(ak_extra(doc));
  if (!item || PyDict_SetItemString(out, "doc_extra", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  item = akb_doc_images_to_py(doc);
  if (!item || PyDict_SetItemString(out, "images", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  if (!akb_set_scene_info(out, doc, &options)) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  Py_DECREF(node_list);
  Py_DECREF(owner);
  akb_shared_doc_release(doc_owner);
  return out;
}

static PyObject *
akb_read_mesh_batch(PyObject *self, PyObject *args) {
  AkbImport *import;
  PyObject *owner;
  PyObject *item;
  PyObject *list;
  Py_ssize_t start;
  Py_ssize_t count;
  Py_ssize_t available;
  Py_ssize_t i;

  (void)self;

  if (!PyArg_ParseTuple(args, "Onn", &owner, &start, &count))
    return NULL;

  if (start < 0 || count < 0) {
    PyErr_SetString(PyExc_ValueError, "AssetKit mesh batch range must be non-negative");
    return NULL;
  }

  import = (AkbImport *)PyCapsule_GetPointer(owner, "assetkit_blender.AkbImport");
  if (!import)
    return NULL;

  if ((size_t)start >= import->primitives.count || count == 0)
    return PyList_New(0);

  available = (Py_ssize_t)(import->primitives.count - (size_t)start);
  if (count > available)
    count = available;

  list = PyList_New(count);
  if (!list)
    return NULL;

  for (i = 0; i < count; i++) {
    item = akb_primitive_to_py(&import->primitives.items[start + i], owner);
    if (!item) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, i, item);
  }

  return list;
}

static int
akb_read_file_bytes(const char *path, uint8_t **bytes, size_t *size) {
  FILE *file;
  long length;
  size_t read_size;
  uint8_t *data;

  *bytes = NULL;
  *size = 0;

  file = fopen(path, "rb");
  if (!file)
    return 0;
  if (fseek(file, 0, SEEK_END) != 0) {
    fclose(file);
    return 0;
  }
  length = ftell(file);
  if (length <= 0) {
    fclose(file);
    return 0;
  }
  if (fseek(file, 0, SEEK_SET) != 0) {
    fclose(file);
    return 0;
  }

  data = (uint8_t *)malloc((size_t)length);
  if (!data) {
    fclose(file);
    return 0;
  }

  read_size = fread(data, 1, (size_t)length, file);
  fclose(file);
  if (read_size != (size_t)length) {
    free(data);
    return 0;
  }

  *bytes = data;
  *size = read_size;
  return 1;
}

static void *
akb_ktx2_dlopen(const char *path) {
#if defined(_WIN32)
  return (void *)LoadLibraryA(path);
#else
  return dlopen(path, RTLD_NOW);
#endif
}

static void *
akb_ktx2_symbol(void *library, const char *name) {
#if defined(_WIN32)
  return library ? (void *)GetProcAddress((HMODULE)library, name) : NULL;
#else
  return library ? dlsym(library, name) : NULL;
#endif
}

static AkbKtx2DecodeFn
akb_ktx2_decoder(void) {
  static void *library = NULL;
  static AkbKtx2DecodeFn decode = NULL;
  static int tried = 0;
  const char *env_path;

  if (tried)
    return decode;
  tried = 1;

  env_path = getenv("ASSETKIT_KTX2_DECODER_PATH");
  if (env_path && env_path[0])
    library = akb_ktx2_dlopen(env_path);

#if defined(__APPLE__)
  if (!library)
    library = akb_ktx2_dlopen("@loader_path/libassetkit_ktx2.dylib");
  if (!library)
    library = akb_ktx2_dlopen("@rpath/libassetkit_ktx2.dylib");
  if (!library)
    library = akb_ktx2_dlopen("libassetkit_ktx2.dylib");
#elif defined(_WIN32)
  if (!library)
    library = akb_ktx2_dlopen("assetkit_ktx2.dll");
#else
  if (!library)
    library = akb_ktx2_dlopen("$ORIGIN/libassetkit_ktx2.so");
  if (!library)
    library = akb_ktx2_dlopen("libassetkit_ktx2.so");
#endif

  decode = (AkbKtx2DecodeFn)akb_ktx2_symbol(library, "assetkit_ktx2_decode");
  return decode;
}

static PyObject *
akb_decode_ktx2(PyObject *self, PyObject *args) {
  AkbKtx2DecodeFn decode;
  AkbKtx2DecodedImage image;
  PyObject *out;
  PyObject *pixels;
  PyObject *width_obj;
  PyObject *height_obj;
  uint8_t *file_bytes;
  size_t file_size;
  size_t pixel_count;
  size_t i;
  float *pixel_floats;
  const char *path;
  int result;

  (void)self;

  if (!PyArg_ParseTuple(args, "s", &path))
    return NULL;

  decode = akb_ktx2_decoder();
  if (!decode) {
    PyErr_SetString(PyExc_RuntimeError, "AssetKit KTX2 decoder library was not found");
    return NULL;
  }

  if (!akb_read_file_bytes(path, &file_bytes, &file_size)) {
    PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    return NULL;
  }

  memset(&image, 0, sizeof(image));
  result = decode(file_bytes, file_size, &image);
  free(file_bytes);
  if (result != 0 || !image.data || !image.width || !image.height || image.channels != 4) {
    free(image.data);
    free(image.mips);
    PyErr_Format(PyExc_RuntimeError, "AssetKit KTX2 decode failed: result=%d", result);
    return NULL;
  }

  if ((size_t)image.width > SIZE_MAX / (size_t)image.height / 4 / sizeof(float)) {
    free(image.data);
    free(image.mips);
    PyErr_SetString(PyExc_OverflowError, "KTX2 image is too large");
    return NULL;
  }

  pixel_count = (size_t)image.width * (size_t)image.height * 4;
  pixels = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(pixel_count * sizeof(float)));
  if (!pixels) {
    free(image.data);
    free(image.mips);
    return NULL;
  }

  pixel_floats = (float *)PyBytes_AS_STRING(pixels);
  for (i = 0; i < pixel_count; i++)
    pixel_floats[i] = (float)image.data[i] * (1.0f / 255.0f);

  free(image.data);
  free(image.mips);

  out = PyDict_New();
  if (!out) {
    Py_DECREF(pixels);
    return NULL;
  }

  width_obj = PyLong_FromUnsignedLong(image.width);
  height_obj = PyLong_FromUnsignedLong(image.height);
  if (!width_obj || !height_obj
      || PyDict_SetItemString(out, "width", width_obj) < 0
      || PyDict_SetItemString(out, "height", height_obj) < 0
      || PyDict_SetItemString(out, "pixels_f32", pixels) < 0) {
    Py_XDECREF(width_obj);
    Py_XDECREF(height_obj);
    Py_DECREF(pixels);
    Py_DECREF(out);
    return NULL;
  }

  Py_DECREF(width_obj);
  Py_DECREF(height_obj);
  Py_DECREF(pixels);
  return out;
}

static PyMethodDef akb_methods[] = {
  {"load_meshes", akb_load_meshes, METH_VARARGS, "Load mesh buffers through AssetKit."},
  {"open_scene", akb_open_scene, METH_VARARGS, "Open an AssetKit scene for batched mesh reads."},
  {"read_mesh_batch", akb_read_mesh_batch, METH_VARARGS, "Read a batch of mesh buffers from an open AssetKit scene."},
  {"decode_ktx2", akb_decode_ktx2, METH_VARARGS, "Decode a KTX2 texture to float RGBA pixels."},
  {NULL, NULL, 0, NULL}
};

static struct PyModuleDef akb_module = {
  PyModuleDef_HEAD_INIT,
  "_assetkit_blender",
  "Native AssetKit bridge for Blender.",
  -1,
  akb_methods
};

PyMODINIT_FUNC
PyInit__assetkit_blender(void) {
  return PyModule_Create(&akb_module);
}
