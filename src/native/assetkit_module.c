#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ak/assetkit.h"

#define AKB_GEOMETRY_MESH 1
#define AKB_PRIMITIVE_TRIANGLES 3
#define AKB_INPUT_NORMAL 13
#define AKB_INPUT_POSITION 16
#define AKB_INPUT_TEXCOORD 19
#define AKB_INPUT_UV 21

typedef struct AkbPrimitive {
  struct AkbSharedDoc *doc_owner;
  char     name[512];
  char     object_name[512];
  char     material_name[512];
  char     base_color_texture[1024];
  char     metallic_roughness_texture[1024];
  char     normal_texture[1024];
  char     emissive_texture[1024];
  float   *vertices;
  uint32_t *indices;
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
  uint32_t vertex_count;
  uint32_t loop_count;
  uint32_t face_count;
  uint8_t  has_normals;
  uint8_t  has_uvs;
  uint8_t  double_sided;
  uint8_t  alpha_mode;
  uint8_t  has_node;
  uint8_t  borrowed_vertices;
  uint8_t  borrowed_indices;
  uint8_t  zero_copy_flags;
} AkbPrimitive;

typedef struct AkbPrimitiveList {
  AkbPrimitive *items;
  size_t        count;
  size_t        capacity;
} AkbPrimitiveList;

typedef struct AkbSharedDoc {
  AkDoc *doc;
  size_t refcount;
} AkbSharedDoc;

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
  free(prim->loop_starts);
  free(prim->loop_totals);
  free(prim->normals);
  free(prim->uvs);
  akb_shared_doc_release(prim->doc_owner);
  memset(prim, 0, sizeof(*prim));
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

static uint32_t *
akb_indices_copy(AkUIntArray *indices, size_t *count_out) {
  uint32_t *copy;
  size_t count;

  *count_out = 0;
  if (!indices || indices->count == 0)
    return NULL;

  count = indices->count;
  copy = (uint32_t *)malloc(count * sizeof(uint32_t));
  if (!copy)
    return NULL;

  memcpy(copy, indices->items, count * sizeof(uint32_t));
  *count_out = count;
  return copy;
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
  float *tmp, *out;
  size_t total, written;
  uint32_t comp_count, i, j;

  *count_out = 0;
  if (!acc || acc->count == 0)
    return NULL;

  comp_count = acc->componentCount ? acc->componentCount : width;
  total = (size_t)acc->count * comp_count;
  tmp = (float *)calloc(total, sizeof(float));
  if (!tmp)
    return NULL;

  written = ak_accessorAsFloat(acc, tmp, total);
  if (written == 0) {
    free(tmp);
    return NULL;
  }

  out = (float *)calloc((size_t)acc->count * width, sizeof(float));
  if (!out) {
    free(tmp);
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
akb_extract_primitive(AkbPrimitiveList *list,
                      AkDoc *doc,
                      AkbSharedDoc *doc_owner,
                      AkNode *node,
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

  akb_extract_material(doc, prim, &out);

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
  out.loop_starts = (int32_t *)malloc((size_t)out.face_count * sizeof(int32_t));
  out.loop_totals = (int32_t *)malloc((size_t)out.face_count * sizeof(int32_t));
  if ((out.face_count && (!out.loop_starts || !out.loop_totals))) {
    akb_primitive_free(&out);
    return 0;
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
akb_extract_mesh(AkbPrimitiveList *list, AkDoc *doc, AkbSharedDoc *doc_owner, AkNode *node, AkGeometry *geom) {
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
    if (!akb_extract_primitive(list, doc, doc_owner, node, geom, mesh, prim, prim_index))
      return 0;
  }

  return 1;
}

static int
akb_extract_node(AkbPrimitiveList *list, AkDoc *doc, AkbSharedDoc *doc_owner, AkNode *node) {
  AkNode *child;

  if (!node)
    return 1;

  if (node->geometry) {
    AkGeometry *geom = (AkGeometry *)ak_instanceObject(&node->geometry->base);
    if (!akb_extract_mesh(list, doc, doc_owner, node, geom))
      return 0;
  }

  for (child = node->chld; child; child = child->next) {
    if (!akb_extract_node(list, doc, doc_owner, child))
      return 0;
  }

  return 1;
}

static int
akb_extract_scene(AkDoc *doc, AkbSharedDoc *doc_owner, AkbPrimitiveList *list) {
  AkVisualScene *scene;
  AkInstanceBase *inst;

  if (!doc || !doc->scene.visualScene)
    return 1;

  scene = (AkVisualScene *)ak_instanceObject(doc->scene.visualScene);
  if (!scene || !scene->node)
    return 1;

  for (inst = scene->node->node ? &scene->node->node->base : NULL; inst; inst = inst->next) {
    AkNode *node = inst->node ? inst->node : (AkNode *)ak_instanceObject(inst);
    if (!akb_extract_node(list, doc, doc_owner, node))
      return 0;
  }

  return 1;
}

static int
akb_extract_doc(AkDoc *doc, AkbSharedDoc *doc_owner, AkbPrimitiveList *list) {
  AkLibrary *lib;

  if (!akb_extract_scene(doc, doc_owner, list))
    return 0;

  if (list->count > 0)
    return 1;

  for (lib = doc->lib.geometries; lib; lib = lib->next) {
    AkGeometry *geom;

    for (geom = (AkGeometry *)lib->chld; geom; geom = (AkGeometry *)geom->base.next) {
      if (!akb_extract_mesh(list, doc, doc_owner, NULL, geom))
        return 0;
    }
  }

  return 1;
}

static void
akb_primitive_capsule_destructor(PyObject *capsule) {
  AkbPrimitive *prim;

  prim = (AkbPrimitive *)PyCapsule_GetPointer(capsule, "assetkit_blender.AkbPrimitive");
  if (!prim)
    return;

  akb_primitive_free(prim);
  free(prim);
}

static PyObject *
akb_memoryview_or_empty(const void *data, size_t size) {
  if (!data || size == 0)
    return PyBytes_FromStringAndSize(NULL, 0);
  return PyMemoryView_FromMemory((char *)data, (Py_ssize_t)size, PyBUF_READ);
}

static PyObject *
akb_primitive_to_py(AkbPrimitive *prim) {
  PyObject *dict, *owner, *value;

  dict = PyDict_New();
  if (!dict) {
    akb_primitive_free(prim);
    free(prim);
    return NULL;
  }

  owner = PyCapsule_New(prim, "assetkit_blender.AkbPrimitive", akb_primitive_capsule_destructor);
  if (!owner) {
    Py_DECREF(dict);
    akb_primitive_free(prim);
    free(prim);
    return NULL;
  }

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
    Py_DECREF(owner);
    return NULL;
  }
  Py_DECREF(owner);

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
  AKB_SET_OBJ("zero_copy_flags", PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SET_OBJ("matrix_f32", akb_memoryview_or_empty(prim->matrix, prim->has_node ? 16 * sizeof(float) : 0));
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
akb_load_meshes(PyObject *self, PyObject *args) {
  const char *filepath;
  AkDoc *doc = NULL;
  AkbSharedDoc *doc_owner;
  AkResult result;
  AkbPrimitiveList list = {0};
  PyObject *out;
  size_t i;
  int ok;

  (void)self;

  if (!PyArg_ParseTuple(args, "s", &filepath))
    return NULL;

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  Py_BEGIN_ALLOW_THREADS
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  doc_owner->doc = doc;
  if (result == AK_OK && doc)
    ok = akb_extract_doc(doc, doc_owner, &list);
  else
    ok = 0;
  Py_END_ALLOW_THREADS

  if (result != AK_OK || !doc) {
    PyErr_Format(PyExc_RuntimeError, "AssetKit failed to load file: result=%d", result);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (!ok) {
    akb_list_free(&list);
    akb_shared_doc_release(doc_owner);
    PyErr_SetString(PyExc_MemoryError, "AssetKit bridge could not prepare mesh buffers");
    return NULL;
  }

  out = PyList_New((Py_ssize_t)list.count);
  if (!out) {
    akb_list_free(&list);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  for (i = 0; i < list.count; i++) {
    AkbPrimitive *owner = (AkbPrimitive *)malloc(sizeof(*owner));
    PyObject *item;

    if (!owner) {
      Py_DECREF(out);
      akb_list_free(&list);
      akb_shared_doc_release(doc_owner);
      return PyErr_NoMemory();
    }

    *owner = list.items[i];
    memset(&list.items[i], 0, sizeof(list.items[i]));

    item = akb_primitive_to_py(owner);
    if (!item) {
      Py_DECREF(out);
      akb_list_free(&list);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(out, (Py_ssize_t)i, item);
  }

  akb_list_free(&list);
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
