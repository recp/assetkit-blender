#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ak/assetkit.h"
#include "ak/options.h"

#define AKB_GEOMETRY_MESH 1
#define AKB_PRIMITIVE_TRIANGLES 3
#define AKB_INPUT_NORMAL 13
#define AKB_INPUT_POSITION 16
#define AKB_INPUT_TEXCOORD 19
#define AKB_INPUT_UV 21
#define AKB_ANIM_TRANSLATION 1
#define AKB_ANIM_ROTATION_QUAT 2
#define AKB_ANIM_SCALE 3
#define AKB_COORD_RAW 0
#define AKB_COORD_TRANSFORM 1
#define AKB_COORD_ALL 2

typedef struct AkbPrimitive {
  struct AkbSharedDoc *doc_owner;
  struct AkbAnimation *animation;
  char     name[512];
  char     object_name[512];
  char     material_name[512];
  char     base_color_texture[1024];
  char     metallic_roughness_texture[1024];
  char     normal_texture[1024];
  char     emissive_texture[1024];
  float   *vertices;
  uint32_t *indices;
  int32_t  *loop_meta;
  int32_t  *loop_starts;
  int32_t  *loop_totals;
  float   *normals;
  float   *uvs;
  float    base_color[4];
  float    emissive_color[3];
  float    metallic;
  float    roughness;
  float    alpha_cutoff;
  float    normal_scale;
  float    matrix[16];
  float    coord_matrix[16];
  int32_t  node_index;
  uint32_t vertex_count;
  uint32_t loop_count;
  uint32_t face_count;
  uint8_t  has_normals;
  uint8_t  has_uvs;
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
  char     name[512];
  float    matrix[16];
  int32_t  parent_index;
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
} AkbLoadOptions;

typedef struct AkbSavedOptions {
  uintptr_t coord;
  uintptr_t coord_convert_type;
  uintptr_t triangulate;
  uintptr_t gen_normals;
  uintptr_t cvt_triangle_strip;
  uintptr_t cvt_triangle_fan;
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
  size_t         count;
  size_t         capacity;
  size_t         refcount;
} AkbAnimation;

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

  ak_opt_set(AK_OPT_COORD, (uintptr_t)options->target_coord);
  ak_opt_set(AK_OPT_COORD_CONVERT_TYPE,
             (uintptr_t)akb_assetkit_coord_cvt_type(options->coord_conversion));
  ak_opt_set(AK_OPT_TRIANGULATE, options->triangulate);
  ak_opt_set(AK_OPT_GEN_NORMALS_IF_NEEDED, options->gen_normals);
  ak_opt_set(AK_OPT_CVT_TRIANGLESTRIP, options->cvt_triangle_strip);
  ak_opt_set(AK_OPT_CVT_TRIANGLEFAN, options->cvt_triangle_fan);
}

static void
akb_options_restore(const AkbSavedOptions *saved) {
  ak_opt_set(AK_OPT_COORD, saved->coord);
  ak_opt_set(AK_OPT_COORD_CONVERT_TYPE, saved->coord_convert_type);
  ak_opt_set(AK_OPT_TRIANGULATE, saved->triangulate);
  ak_opt_set(AK_OPT_GEN_NORMALS_IF_NEEDED, saved->gen_normals);
  ak_opt_set(AK_OPT_CVT_TRIANGLESTRIP, saved->cvt_triangle_strip);
  ak_opt_set(AK_OPT_CVT_TRIANGLEFAN, saved->cvt_triangle_fan);
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
  if (!prim)
    return;
  if (!prim->borrowed_vertices)
    free(prim->vertices);
  if (!prim->borrowed_indices)
    free(prim->indices);
  free(prim->loop_meta);
  free(prim->normals);
  free(prim->uvs);
  akb_animation_release(prim->animation);
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

static void
akb_extract_material(AkDoc *doc, AkMeshPrimitive *prim, AkbPrimitive *out) {
  AkMaterial *mat;
  AkEffect *effect;
  AkTechniqueFxCommon *cmn;

  out->base_color[0] = 1.0f;
  out->base_color[1] = 1.0f;
  out->base_color[2] = 1.0f;
  out->base_color[3] = 1.0f;
  out->emissive_color[0] = 0.0f;
  out->emissive_color[1] = 0.0f;
  out->emissive_color[2] = 0.0f;
  out->metallic = 1.0f;
  out->roughness = 1.0f;
  out->alpha_cutoff = 0.5f;
  out->normal_scale = 1.0f;

  mat = prim ? prim->material : NULL;
  if (!mat)
    return;

  snprintf(out->material_name, sizeof(out->material_name), "%s", akb_name(mat->name, "AssetKitMaterial"));

  effect = mat->effect ? (AkEffect *)ak_instanceObject(&mat->effect->base) : NULL;
  cmn = effect ? ak_getProfileTechniqueCommon(effect) : NULL;
  if (!cmn)
    return;

  out->double_sided = cmn->doubleSided ? 1 : 0;

  if (cmn->albedo) {
    if (cmn->albedo->color) {
      out->base_color[0] = cmn->albedo->color->vec[0];
      out->base_color[1] = cmn->albedo->color->vec[1];
      out->base_color[2] = cmn->albedo->color->vec[2];
      out->base_color[3] = cmn->albedo->color->vec[3];
    }
    akb_copy_texture_path(doc, cmn->albedo->texture, out->base_color_texture, sizeof(out->base_color_texture));
  }

  if (cmn->metalness) {
    out->metallic = cmn->metalness->intensity;
    akb_copy_texture_path(doc, cmn->metalness->tex, out->metallic_roughness_texture, sizeof(out->metallic_roughness_texture));
  }
  if (cmn->roughness)
    out->roughness = cmn->roughness->intensity;

  if (cmn->normal) {
    out->normal_scale = cmn->normal->scale == 0.0f ? 1.0f : cmn->normal->scale;
    akb_copy_texture_path(doc, cmn->normal->tex, out->normal_texture, sizeof(out->normal_texture));
  }

  if (cmn->emission) {
    if (cmn->emission->color.color) {
      out->emissive_color[0] = cmn->emission->color.color->vec[0] * cmn->emission->strength;
      out->emissive_color[1] = cmn->emission->color.color->vec[1] * cmn->emission->strength;
      out->emissive_color[2] = cmn->emission->color.color->vec[2] * cmn->emission->strength;
    }
    akb_copy_texture_path(doc, cmn->emission->color.texture, out->emissive_texture, sizeof(out->emissive_texture));
  }

  if (cmn->transparent) {
    out->alpha_cutoff = cmn->transparent->cutoff;
    switch (cmn->transparent->opaque) {
      case AK_OPAQUE_BLEND:
        out->alpha_mode = 1;
        break;
      case AK_OPAQUE_MASK:
        out->alpha_mode = 2;
        break;
      default:
        out->alpha_mode = out->base_color[3] < 1.0f ? 1 : 0;
        break;
    }
  } else {
    out->alpha_mode = out->base_color[3] < 1.0f ? 1 : 0;
  }
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
                          const AkbCoordContext *coord) {
  AkbAnimChannel out = {0};
  AkAnimSampler *sampler;
  AkInput *time_input;
  AkInput *value_input;
  float *raw_values;
  uint32_t target_width;
  uint32_t time_count;
  uint32_t value_count;
  uint8_t raw_borrowed;

  sampler = ak_getObjectByUrl(&channel->source);
  if (!sampler)
    return 1;

  time_input = akb_anim_sampler_input(sampler, AK_INPUT_INPUT);
  value_input = akb_anim_sampler_input(sampler, AK_INPUT_OUTPUT);
  if (!time_input || !time_input->accessor || !value_input || !value_input->accessor)
    return 1;

  out.target = (uint32_t)akb_anim_target_kind((AkObject *)target->target,
                                             &target_width);
  if (!out.target)
    return 1;

  out.value_width = value_input->accessor->componentCount
                    ? value_input->accessor->componentCount
                    : target_width;
  if (target->isPartial && out.value_width > 1)
    out.value_width = 1;

  out.times = akb_accessor_float_borrow(time_input->accessor, 1, &time_count);
  if (out.times) {
    out.borrowed_times = 1;
  } else {
    out.times = akb_accessor_float_copy(time_input->accessor, 1, &time_count);
    if (!out.times)
      return 0;
  }

  raw_values = akb_accessor_float_borrow(value_input->accessor,
                                         out.value_width,
                                         &value_count);
  if (raw_values) {
    raw_borrowed = 1;
  } else {
    raw_values = akb_accessor_float_copy(value_input->accessor,
                                         out.value_width,
                                         &value_count);
    raw_borrowed = 0;
    if (!raw_values) {
      if (!out.borrowed_times)
        free(out.times);
      return 0;
    }
  }

  if (value_count < time_count)
    time_count = value_count;

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
                           AkObject **targets,
                           int target_count,
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

      for (i = 0; i < target_count; i++) {
        if (resolved.target == targets[i]) {
          if (!akb_animation_add_channel(animation, channel, &resolved, coord))
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
akb_node_transform_targets(AkNode *node, AkObject **targets, int capacity) {
  AkObject *object;
  int count;

  if (!node || !node->transform)
    return 0;

  count = 0;
  for (object = node->transform->base; object && count < capacity; object = object->next)
    targets[count++] = object;

  for (object = node->transform->item; object && count < capacity; object = object->next)
    targets[count++] = object;

  return count;
}

static AkbAnimation *
akb_animation_new(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  AkNode *node,
                  const AkbCoordContext *coord,
                  int *ok) {
  AkbAnimation *animation;
  AkLibrary *library;
  AkObject *targets[64];
  AkContext context;
  int target_count;

  *ok = 1;
  target_count = akb_node_transform_targets(node, targets, 64);
  if (!target_count)
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
                                    targets,
                                    target_count,
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
  snprintf(out.name, sizeof(out.name), "%s", akb_name(node->name, "AssetKitNode"));
  out.parent_index = parent_index;
  ak_transformCombine(node->transform, out.matrix);
  out.has_transform = 1;
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
                      AkDoc *doc,
                      AkbSharedDoc *doc_owner,
                      AkbAnimation *animation,
                      AkNode *node,
                      int32_t node_index,
                      AkGeometry *geom,
                      AkMesh *mesh,
                      AkMeshPrimitive *prim,
                      uint32_t prim_index) {
  AkbPrimitive out = {0};
  AkInput *pos_input, *normal_input, *uv_input;
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
  akb_extract_material(doc, prim, &out);
  out.animation = akb_animation_retain(animation);

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

  uv_input = akb_find_input(prim, AK_INPUT_TEXCOORD, AK_INPUT_UV, "TEXCOORD", "UV");
  out.uvs = akb_loop_attribute_copy(prim,
                                    uv_input,
                                    raw_indices,
                                    raw_count,
                                    out.indices,
                                    out.loop_count,
                                    2,
                                    1,
                                    &out.has_uvs);

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
                 AkDoc *doc,
                 AkbSharedDoc *doc_owner,
                 AkbAnimation *animation,
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
                               doc,
                               doc_owner,
                               animation,
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
    ok = 1;
    if (!ok)
      return 0;

    geom = (AkGeometry *)ak_instanceObject(&node->geometry->base);
    if (!akb_extract_mesh(list, doc, doc_owner, animation, node, node_index, geom)) {
      akb_animation_release(animation);
      return 0;
    }
    akb_animation_release(animation);
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

  if (import->primitives.count > 0) {
    akb_list_set_coord_matrix(&import->primitives, &coord);
    return 1;
  }

  for (lib = doc->lib.geometries; lib; lib = lib->next) {
    for (geom = (AkGeometry *)lib->chld; geom; geom = (AkGeometry *)geom->base.next) {
      if (!akb_extract_mesh(&import->primitives, doc, doc_owner, NULL, NULL, -1, geom))
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

  AKB_SET_OBJ("name", PyUnicode_FromString(prim->name));
  AKB_SET_OBJ("object_name", PyUnicode_FromString(prim->object_name));
  AKB_SET_OBJ("vertex_count", PyLong_FromUnsignedLong(prim->vertex_count));
  AKB_SET_OBJ("loop_count", PyLong_FromUnsignedLong(prim->loop_count));
  AKB_SET_OBJ("face_count", PyLong_FromUnsignedLong(prim->face_count));
  AKB_SET_OBJ("material_name", PyUnicode_FromString(prim->material_name));
  AKB_SET_OBJ("base_color", Py_BuildValue("(ffff)",
                                          prim->base_color[0],
                                          prim->base_color[1],
                                          prim->base_color[2],
                                          prim->base_color[3]));
  AKB_SET_OBJ("emissive_color", Py_BuildValue("(fff)",
                                             prim->emissive_color[0],
                                             prim->emissive_color[1],
                                             prim->emissive_color[2]));
  AKB_SET_OBJ("metallic", PyFloat_FromDouble(prim->metallic));
  AKB_SET_OBJ("roughness", PyFloat_FromDouble(prim->roughness));
  AKB_SET_OBJ("alpha_cutoff", PyFloat_FromDouble(prim->alpha_cutoff));
  AKB_SET_OBJ("normal_scale", PyFloat_FromDouble(prim->normal_scale));
  AKB_SET_OBJ("alpha_mode", PyLong_FromUnsignedLong(prim->alpha_mode));
  AKB_SET_OBJ("double_sided", PyBool_FromLong(prim->double_sided));
  AKB_SET_OBJ("has_node", PyBool_FromLong(prim->has_node));
  AKB_SET_OBJ("node_index", PyLong_FromLong(prim->node_index));
  AKB_SET_OBJ("zero_copy_flags", PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SET_OBJ("anim_count",
              PyLong_FromUnsignedLong(prim->animation
                                      ? (unsigned long)prim->animation->count
                                      : 0));
  AKB_SET_OBJ("anim_channels", akb_anim_channels_to_py(prim->animation));
  AKB_SET_OBJ("matrix_f32", akb_memoryview_or_empty(prim->matrix, prim->has_node ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ("coord_matrix_f32",
              akb_memoryview_or_empty(prim->coord_matrix,
                                      prim->has_coord_matrix ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ("base_color_texture", PyUnicode_FromString(prim->base_color_texture));
  AKB_SET_OBJ("metallic_roughness_texture", PyUnicode_FromString(prim->metallic_roughness_texture));
  AKB_SET_OBJ("normal_texture", PyUnicode_FromString(prim->normal_texture));
  AKB_SET_OBJ("emissive_texture", PyUnicode_FromString(prim->emissive_texture));
  AKB_SET_OBJ("vertices_f32", akb_memoryview_or_empty(prim->vertices, (size_t)prim->vertex_count * 3 * sizeof(float)));
  AKB_SET_OBJ("indices_u32", akb_memoryview_or_empty(prim->indices, (size_t)prim->loop_count * sizeof(uint32_t)));
  AKB_SET_OBJ("loop_starts_i32", akb_memoryview_or_empty(prim->loop_starts, (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ("loop_totals_i32", akb_memoryview_or_empty(prim->loop_totals, (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ("normals_f32", akb_memoryview_or_empty(prim->normals, prim->has_normals ? (size_t)prim->loop_count * 3 * sizeof(float) : 0));
  AKB_SET_OBJ("uvs_f32", akb_memoryview_or_empty(prim->uvs, prim->has_uvs ? (size_t)prim->loop_count * 2 * sizeof(float) : 0));

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

  AKB_NODE_SET_OBJ("name", PyUnicode_FromString(node->name));
  AKB_NODE_SET_OBJ("parent_index", PyLong_FromLong(node->parent_index));
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

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  Py_BEGIN_ALLOW_THREADS
  akb_options_apply(&options, &saved_options);
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  doc_owner->doc = doc;
  if (result == AK_OK && doc)
    ok = akb_extract_doc(doc, doc_owner, &import, &options);
  else
    ok = 0;
  akb_options_restore(&saved_options);
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

static PyMethodDef akb_methods[] = {
  {"load_meshes", akb_load_meshes, METH_VARARGS, "Load mesh buffers through AssetKit."},
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
