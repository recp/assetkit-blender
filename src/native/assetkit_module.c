#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "cglm/struct.h"

#include "ak/assetkit.h"
#include "ak/options.h"

#define AKB_GEOMETRY_MESH 1
#define AKB_PRIMITIVE_TRIANGLES 3
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
#define AKB_COORD_RAW 0
#define AKB_COORD_TRANSFORM 1
#define AKB_COORD_ALL 2
#define AKB_SKIN_JOINTS_PER_VERTEX 4
#define AKB_TEXTURE_INFO_MAX 24

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
} AkbLoopFloatAttribute;

typedef struct AkbTextureInfo {
  char    role[64];
  char    path[1024];
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
  uint32_t variant_index;
} AkbMaterialVariantMap;

typedef struct AkbPrimitive {
  struct AkbSharedDoc *doc_owner;
  struct AkbAnimation *animation;
  struct AkbAnimation *morph_animation;
  AkbMorphTarget *morph_targets;
  AkbLoopFloatAttribute *uv_sets;
  AkbLoopFloatAttribute *color_sets;
  AkbMaterialVariantMap *material_variants;
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
  float   *vertices;
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
  uint32_t vertex_count;
  uint32_t loop_count;
  uint32_t face_count;
  uint32_t uv_set_count;
  uint32_t color_set_count;
  uint32_t texture_info_count;
  uint32_t morph_target_count;
  uint32_t material_variant_count;
  uint32_t material_type;
  uint32_t skin_vertex_count;
  uint32_t skin_joint_count;
  uint32_t skin_joint_width;
  uint8_t  has_normals;
  uint8_t  has_uvs;
  uint8_t  has_colors;
  uint8_t  has_tangents;
  uint8_t  has_skin;
  uint8_t  double_sided;
  uint8_t  alpha_mode;
  uint8_t  has_node;
  uint8_t  has_coord_matrix;
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
  uint8_t     coord_conversion;
  uint8_t     triangulate;
  uint8_t     gen_normals;
  uint8_t     cvt_triangle_strip;
  uint8_t     cvt_triangle_fan;
  uint8_t     use_mmap;
} AkbLoadOptions;

typedef struct AkbSavedOptions {
  uintptr_t coord;
  uintptr_t coord_convert_type;
  uintptr_t triangulate;
  uintptr_t gen_normals;
  uintptr_t cvt_triangle_strip;
  uintptr_t cvt_triangle_fan;
  uintptr_t use_mmap;
} AkbSavedOptions;

typedef struct AkbSharedDoc {
  AkDoc *doc;
  size_t refcount;
} AkbSharedDoc;

typedef struct AkbAnimChannel {
  float    *times;
  float    *values;
  uint32_t  count;
  uint32_t  value_width;
  uint32_t  target;
  uint32_t  target_offset;
  uint8_t   interpolation;
  uint8_t   is_partial;
  uint8_t   borrowed_times;
  uint8_t   borrowed_values;
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
  options->coord_conversion = AKB_COORD_TRANSFORM;
  options->triangulate = 1;
  options->gen_normals = 1;
  options->cvt_triangle_strip = 1;
  options->cvt_triangle_fan = 1;
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
  saved->use_mmap = ak_opt_get(AK_OPT_USE_MMAP);

  ak_opt_set(AK_OPT_COORD, (uintptr_t)options->target_coord);
  ak_opt_set(AK_OPT_COORD_CONVERT_TYPE,
             (uintptr_t)akb_assetkit_coord_cvt_type(options->coord_conversion));
  ak_opt_set(AK_OPT_TRIANGULATE, options->triangulate);
  ak_opt_set(AK_OPT_GEN_NORMALS_IF_NEEDED, options->gen_normals);
  ak_opt_set(AK_OPT_CVT_TRIANGLESTRIP, options->cvt_triangle_strip);
  ak_opt_set(AK_OPT_CVT_TRIANGLEFAN, options->cvt_triangle_fan);
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

static void
akb_primitive_free(AkbPrimitive *prim) {
  uint32_t i;

  if (!prim)
    return;
  if (!prim->borrowed_vertices)
    free(prim->vertices);
  if (!prim->borrowed_indices)
    free(prim->indices);
  free(prim->loop_meta);
  free(prim->normals);
  for (i = 0; i < prim->uv_set_count; i++)
    free(prim->uv_sets[i].values);
  free(prim->uv_sets);
  for (i = 0; i < prim->color_set_count; i++)
    free(prim->color_sets[i].values);
  free(prim->color_sets);
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
akb_copy_texture_path(AkDoc *doc, AkTextureRef *texref, char *dest, size_t capacity) {
  AkImage *image;
  AkInitFrom *init_from;
  const char *path;

  if (!dest || capacity == 0)
    return;
  dest[0] = '\0';

  if (!texref || !texref->texture || !(image = texref->texture->image))
    return;

  init_from = image->initFrom;
  if (!init_from)
    return;

  path = init_from->resolvedFullPath ? init_from->resolvedFullPath : init_from->ref;
  if (!path || !path[0])
    return;

  if (path[0] == '/' || !doc || !doc->inf || !doc->inf->dir)
    snprintf(dest, capacity, "%s", path);
  else
    snprintf(dest, capacity, "%s/%s", doc->inf->dir, path);
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

static void
akb_copy_texture_info(AkDoc *doc,
                      AkTextureRef *texref,
                      AkInstanceMaterial *inst_mat,
                      const char *role,
                      char *dest,
                      size_t capacity,
                      AkbPrimitive *out) {
  AkbTextureInfo *info;
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
  info->slot = akb_texref_slot(texref, inst_mat);

  if (texref->texcoord)
    snprintf(info->texcoord, sizeof(info->texcoord), "%s", texref->texcoord);
  if (texref->coordInputName)
    snprintf(info->coord_input_name, sizeof(info->coord_input_name), "%s", texref->coordInputName);

  sampler = texref->texture ? texref->texture->sampler : NULL;
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

static void
akb_extract_material(AkDoc *doc,
                     AkMeshPrimitive *prim,
                     AkBindMaterial *bind_material,
                     AkbPrimitive *out) {
  AkMaterial *mat;
  AkInstanceMaterial *inst_mat;
  AkEffect *effect;
  AkTechniqueFxCommon *cmn;

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
  if (!cmn)
    return;

  out->material_type = (uint32_t)cmn->type;

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
                   out->diffuse_transmission_texture);
    }
    AKB_COPY_TEX("diffuse_transmission",
                 cmn->diffuseTransmission->texture,
                 out->diffuse_transmission_texture);
  }

  if (cmn->dispersion)
    out->dispersion = cmn->dispersion->dispersion;

  if (cmn->emission) {
    if (cmn->emission->color.color) {
      out->emissive_color[0] = cmn->emission->color.color->vec[0] * cmn->emission->strength;
      out->emissive_color[1] = cmn->emission->color.color->vec[1] * cmn->emission->strength;
      out->emissive_color[2] = cmn->emission->color.color->vec[2] * cmn->emission->strength;
    }
    AKB_COPY_TEX("emissive", cmn->emission->color.texture, out->emissive_texture);
  }

  if (cmn->transparent) {
    float opacity;
    float alpha;
    float luminance;

    out->alpha_cutoff = cmn->transparent->cutoff;
    out->transparent_amount = cmn->transparent->amount;

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

static int
akb_extract_skin(AkbPrimitive *out,
                 AkbSceneNodeList *nodes,
                 AkMeshPrimitive *prim,
                 uint32_t prim_index,
                 AkInstanceSkin *skinner) {
  AkSkin *skin;
  AkNode **joints;
  AkNode **joint_sources;
  uint16_t *joint_indices;
  int32_t *joint_nodes;
  float *weights;
  float *inverse_bind_matrices;
  size_t filled_count;
  size_t i;

  if (!out || !prim || !skinner || !(skin = skinner->skin)
      || !skin->nJoints || !out->vertex_count)
    return 1;

  joint_indices = (uint16_t *)calloc((size_t)out->vertex_count
                                     * AKB_SKIN_JOINTS_PER_VERTEX,
                                     sizeof(*joint_indices));
  weights = (float *)calloc((size_t)out->vertex_count
                            * AKB_SKIN_JOINTS_PER_VERTEX,
                            sizeof(*weights));
  if (!joint_indices || !weights) {
    free(joint_indices);
    free(weights);
    return 0;
  }

  filled_count = ak_skinFillWeights(skin,
                                    prim,
                                    prim_index,
                                    AKB_SKIN_JOINTS_PER_VERTEX,
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
  out->skin_root_source = skin->skeleton;
  out->skin_root_node_index = akb_scene_node_index_for(nodes, skin->skeleton);
  out->skin_vertex_count = (uint32_t)filled_count;
  out->skin_joint_count = (uint32_t)skin->nJoints;
  out->skin_joint_width = AKB_SKIN_JOINTS_PER_VERTEX;
  out->has_skin = 1;
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
akb_animation_convert_values(AkbAnimChannel *out,
                             float *raw_values,
                             uint32_t raw_count,
                             uint8_t raw_borrowed,
                             const AkbCoordContext *coord) {
  float *values;
  float dot;
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
  if (!values) {
    if (!raw_borrowed)
      free(raw_values);
    return 0;
  }

  for (i = 0; i < raw_count; i++) {
    values[(size_t)i * 4]     = raw_values[(size_t)i * out->value_width + 3];
    values[(size_t)i * 4 + 1] = raw_values[(size_t)i * out->value_width];
    values[(size_t)i * 4 + 2] = raw_values[(size_t)i * out->value_width + 1];
    values[(size_t)i * 4 + 3] = raw_values[(size_t)i * out->value_width + 2];

    if (i > 0) {
      dot = values[(size_t)i * 4] * values[(size_t)(i - 1) * 4]
            + values[(size_t)i * 4 + 1] * values[(size_t)(i - 1) * 4 + 1]
            + values[(size_t)i * 4 + 2] * values[(size_t)(i - 1) * 4 + 2]
            + values[(size_t)i * 4 + 3] * values[(size_t)(i - 1) * 4 + 3];
      if (dot < 0.0f) {
        values[(size_t)i * 4]     = -values[(size_t)i * 4];
        values[(size_t)i * 4 + 1] = -values[(size_t)i * 4 + 1];
        values[(size_t)i * 4 + 2] = -values[(size_t)i * 4 + 2];
        values[(size_t)i * 4 + 3] = -values[(size_t)i * 4 + 3];
      }
    }
  }
  out->value_width = 4;

  if (!raw_borrowed)
    free(raw_values);
  out->values = values;
  out->borrowed_values = 0;
  return 1;
}

static int
akb_animation_add_channel(AkbAnimation *animation,
                          AkChannel *channel,
                          AkResolvedTarget *target,
                          const AkbAnimBinding *binding,
                          const AkbCoordContext *coord) {
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
    return 0;
  }

  if (!out.count) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    return 1;
  }

  if (!akb_animation_push(animation, &out)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
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
  AkAnimation *stack[256];
  AkAnimation *next;
  AkChannel *channel;
  AkResolvedTarget resolved;
  int top;
  int i;

  top = 0;
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
                                         coord))
            return 0;
          break;
        }
      }
    }

    if (source->animation) {
      next = (AkAnimation *)source->base.next;
      if (next && top < 256)
        stack[top++] = next;
      source = source->animation;
    } else if (source->base.next) {
      source = (AkAnimation *)source->base.next;
    } else if (top > 0) {
      source = stack[--top];
    } else {
      source = NULL;
    }
  }

  return 1;
}

static int
akb_node_transform_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  AkObject *object;
  uint32_t kind;
  uint32_t width;
  int count;

  if (!node || !node->transform)
    return 0;

  count = 0;
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

  *ok = 1;
  if (ak_nodeNeedsBaking(node) || akb_node_has_rotate(node))
    return akb_animation_new_baked(doc, doc_owner, node, ok);

  binding_count = akb_node_transform_bindings(node, bindings, 64);
  if (!binding_count) {
    animation = akb_animation_new_baked(doc, doc_owner, node, ok);
    return animation;
  }

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
  const char *base_name;

  pos_input = prim->pos ? prim->pos
                        : akb_find_input(prim, AK_INPUT_POSITION, AK_INPUT_POSITION, "POSITION", NULL);
  if (!pos_input || !pos_input->accessor)
    return 1;

  out.node_index = node_index;
  akb_extract_material(doc,
                       prim,
                       node && node->geometry ? node->geometry->bindMaterial : NULL,
                       &out);
  if (!akb_extract_material_variants(doc, prim, &out)) {
    akb_primitive_free(&out);
    return 0;
  }
  out.animation = akb_animation_retain(animation);
  out.morph_animation = akb_animation_retain(morph_animation);

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

  out.loop_count = (out.loop_count / 3) * 3;
  out.face_count = out.loop_count / 3;
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
                 AkGeometry *geom) {
  AkObject *gdata;
  AkMesh *mesh;
  AkMeshPrimitive *prim;
  uint32_t prim_index = 0;

  if (!geom || !(gdata = geom->gdata) || gdata->type != AKB_GEOMETRY_MESH)
    return 1;

  mesh = (AkMesh *)ak_objGet(gdata);
  for (prim = mesh->primitive; prim; prim = prim->next, prim_index++) {
    if (prim->type != AKB_PRIMITIVE_TRIANGLES)
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
                          geom)) {
      akb_animation_release(animation);
      akb_animation_release(morph_animation);
      return 0;
    }
    akb_animation_release(animation);
    akb_animation_release(morph_animation);
  }

  for (child = node->chld; child; child = child->next) {
    if (!akb_extract_node(list, nodes, doc, doc_owner, child, coord, node_index))
      return 0;
  }

  for (inst = node->node ? &node->node->base : NULL; inst; inst = inst->next) {
    inst_node = (AkNode *)ak_instanceObject(inst);
    if (!inst_node || inst_node == node)
      continue;
    if (!akb_extract_node(list, nodes, doc, doc_owner, inst_node, coord, node_index))
      return 0;
  }

  return 1;
}

static int
akb_extract_scene(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  AkbPrimitiveList *list,
                  AkbSceneNodeList *nodes,
                  const AkbCoordContext *coord) {
  AkVisualScene *scene;
  AkInstanceBase *inst;
  AkNode *node;

  if (!doc || !doc->scene.visualScene)
    return 1;

  scene = (AkVisualScene *)ak_instanceObject(doc->scene.visualScene);
  if (!scene || !scene->node)
    return 1;

  if (scene->node->node) {
    for (inst = &scene->node->node->base; inst; inst = inst->next) {
      node = inst->node ? inst->node : (AkNode *)ak_instanceObject(inst);
      if (!akb_extract_node(list, nodes, doc, doc_owner, node, coord, -1))
        return 0;
    }
  } else {
    for (node = scene->node; node; node = node->next) {
      if (!akb_extract_node(list, nodes, doc, doc_owner, node, coord, -1))
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
                         &coord))
    return 0;

  akb_resolve_skin_joint_nodes(&import->primitives, &import->nodes);

  if (import->primitives.count > 0) {
    akb_list_set_coord_matrix(&import->primitives, &coord);
    return 1;
  }

  for (lib = doc->lib.geometries; lib; lib = lib->next) {
    for (geom = (AkGeometry *)lib->chld; geom; geom = (AkGeometry *)geom->base.next) {
      if (!akb_extract_mesh(&import->primitives, &import->nodes, doc, doc_owner, NULL, NULL, NULL, -1, geom))
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
    AKB_TEX_SET_OBJ("texcoord", akb_unicode_from_cstr(infos[i].texcoord));
    AKB_TEX_SET_OBJ("coord_input_name", akb_unicode_from_cstr(infos[i].coord_input_name));
    AKB_TEX_SET_OBJ("slot", PyLong_FromLong(infos[i].slot));
    AKB_TEX_SET_OBJ("wrap_s", PyLong_FromLong(infos[i].wrap_s));
    AKB_TEX_SET_OBJ("wrap_t", PyLong_FromLong(infos[i].wrap_t));
    AKB_TEX_SET_OBJ("wrap_p", PyLong_FromLong(infos[i].wrap_p));
    AKB_TEX_SET_OBJ("min_filter", PyLong_FromLong(infos[i].min_filter));
    AKB_TEX_SET_OBJ("mag_filter", PyLong_FromLong(infos[i].mag_filter));
    AKB_TEX_SET_OBJ("mip_filter", PyLong_FromLong(infos[i].mip_filter));
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
akb_material_variants_to_py(AkbPrimitive *prim) {
  PyObject *list;
  PyObject *dict;
  PyObject *value;
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
  AKB_SET_OBJ("double_sided", PyBool_FromLong(prim->double_sided));
  AKB_SET_OBJ("material_type", PyLong_FromUnsignedLong(prim->material_type));
  AKB_SET_OBJ("has_node", PyBool_FromLong(prim->has_node));
  AKB_SET_OBJ("node_index", PyLong_FromLong(prim->node_index));
  AKB_SET_OBJ("has_skin", PyBool_FromLong(prim->has_skin));
  AKB_SET_OBJ("skin_vertex_count", PyLong_FromUnsignedLong(prim->skin_vertex_count));
  AKB_SET_OBJ("skin_joint_count", PyLong_FromUnsignedLong(prim->skin_joint_count));
  AKB_SET_OBJ("skin_joint_width", PyLong_FromUnsignedLong(prim->skin_joint_width));
  AKB_SET_OBJ("skin_root_node_index", PyLong_FromLong(prim->skin_root_node_index));
  AKB_SET_OBJ("zero_copy_flags", PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SET_OBJ("uv_set_count", PyLong_FromUnsignedLong(prim->uv_set_count));
  AKB_SET_OBJ("color_set_count", PyLong_FromUnsignedLong(prim->color_set_count));
  AKB_SET_OBJ("anim_count",
              PyLong_FromUnsignedLong(prim->animation
                                      ? (unsigned long)prim->animation->count
                                      : 0));
  AKB_SET_OBJ("anim_channels", akb_anim_channels_to_py(prim->animation));
  AKB_SET_OBJ("morph_target_count", PyLong_FromUnsignedLong(prim->morph_target_count));
  AKB_SET_OBJ("morph_targets", akb_morph_targets_to_py(prim));
  AKB_SET_OBJ("morph_anim_count",
              PyLong_FromUnsignedLong(prim->morph_animation
                                      ? (unsigned long)prim->morph_animation->count
                                      : 0));
  AKB_SET_OBJ("morph_anim_channels", akb_anim_channels_to_py(prim->morph_animation));
  AKB_SET_OBJ("uv_sets", akb_loop_float_attrs_to_py(prim->uv_sets,
                                                    prim->uv_set_count,
                                                    prim->loop_count));
  AKB_SET_OBJ("color_sets", akb_loop_float_attrs_to_py(prim->color_sets,
                                                       prim->color_set_count,
                                                       prim->loop_count));
  AKB_SET_OBJ("texture_infos", akb_texture_infos_to_py(prim->texture_infos,
                                                       prim->texture_info_count));
  AKB_SET_OBJ("material_variant_count",
              PyLong_FromUnsignedLong(prim->material_variant_count));
  AKB_SET_OBJ("material_variants", akb_material_variants_to_py(prim));
  AKB_SET_OBJ("matrix_f32", akb_memoryview_or_empty(prim->matrix, prim->has_node ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ("coord_matrix_f32",
              akb_memoryview_or_empty(prim->coord_matrix,
                                      prim->has_coord_matrix ? 16 * sizeof(float) : 0));
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

#undef AKB_SET_OBJ

  return dict;
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
  AKB_NODE_SET_OBJ("camera_type", PyLong_FromUnsignedLong(node->camera_type));
  AKB_NODE_SET_OBJ("camera_name", akb_unicode_from_cstr(node->camera_name));
  AKB_NODE_SET_OBJ("camera_values", Py_BuildValue("(ffffff)",
                                                  node->camera_values[0],
                                                  node->camera_values[1],
                                                  node->camera_values[2],
                                                  node->camera_values[3],
                                                  node->camera_values[4],
                                                  node->camera_values[5]));
  AKB_NODE_SET_OBJ("light_type", PyLong_FromUnsignedLong(node->light_type));
  AKB_NODE_SET_OBJ("light_name", akb_unicode_from_cstr(node->light_name));
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

static PyMethodDef akb_methods[] = {
  {"load_meshes", akb_load_meshes, METH_VARARGS, "Load mesh buffers through AssetKit."},
  {"open_scene", akb_open_scene, METH_VARARGS, "Open an AssetKit scene for batched mesh reads."},
  {"read_mesh_batch", akb_read_mesh_batch, METH_VARARGS, "Read a batch of mesh buffers from an open AssetKit scene."},
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
