static int
akb_export_skin_mapping(PyObject *mapping_obj,
                        int32_t **table_out,
                        Py_ssize_t *table_len_out) {
  PyObject  *seq;
  Py_ssize_t count;
  int32_t   *table;

  if (!mapping_obj || mapping_obj == Py_None) {
    *table_out = NULL;
    *table_len_out = 0;
    return 1;
  }

  seq = PySequence_Fast(mapping_obj, "skin group mapping must be a sequence");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count <= 0) {
    Py_DECREF(seq);
    *table_out = NULL;
    *table_len_out = 0;
    return 1;
  }

  table = (int32_t *)malloc((size_t)count * sizeof(*table));
  if (!table) {
    Py_DECREF(seq);
    PyErr_NoMemory();
    return 0;
  }

  for (Py_ssize_t i = 0; i < count; i++) {
    long joint = PyLong_AsLong(PySequence_Fast_GET_ITEM(seq, i));
    if (PyErr_Occurred()) {
      free(table);
      Py_DECREF(seq);
      return 0;
    }
    table[i] = joint >= 0 && joint <= UINT16_MAX ? (int32_t)joint : -1;
  }

  Py_DECREF(seq);
  *table_out = table;
  *table_len_out = count;
  return 1;
}

static int
akb_export_skin_group_values(PyObject       *groups_obj,
                             const int32_t *group_to_joint,
                             Py_ssize_t     group_to_joint_len,
                             uint16_t       joints[4],
                             float          weights[4],
                             int           *any_weight) {
  PyObject   *groups_seq;
  Py_ssize_t  group_count;
  uint16_t    best_joints[4] = {0, 0, 0, 0};
  float       best_weights[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float       total;

  for (uint32_t i = 0; i < 4u; i++) {
    joints[i] = 0;
    weights[i] = 0.0f;
  }

  if (!groups_obj || groups_obj == Py_None)
    return 1;

  groups_seq = PySequence_Fast(groups_obj, "vertex groups must be a sequence");
  if (!groups_seq)
    return 0;

  group_count = PySequence_Fast_GET_SIZE(groups_seq);
  for (Py_ssize_t i = 0; i < group_count; i++) {
    PyObject *item;
    PyObject *group_obj;
    PyObject *weight_obj;
    long      group_index;
    int32_t   joint_index;
    double    weight;

    item = PySequence_Fast_GET_ITEM(groups_seq, i);
    group_obj = PyObject_GetAttrString(item, "group");
    weight_obj = PyObject_GetAttrString(item, "weight");
    if (!group_obj || !weight_obj) {
      Py_XDECREF(weight_obj);
      Py_XDECREF(group_obj);
      Py_DECREF(groups_seq);
      return 0;
    }

    group_index = PyLong_AsLong(group_obj);
    weight = PyFloat_AsDouble(weight_obj);
    Py_DECREF(weight_obj);
    Py_DECREF(group_obj);
    if (PyErr_Occurred()) {
      Py_DECREF(groups_seq);
      return 0;
    }

    if (group_index < 0 || group_index >= group_to_joint_len || weight <= 0.0)
      continue;
    joint_index = group_to_joint[group_index];
    if (joint_index < 0)
      continue;

    for (uint32_t slot = 0; slot < 4u; slot++) {
      if ((float)weight > best_weights[slot]
          || ((float)weight == best_weights[slot]
              && (uint16_t)joint_index > best_joints[slot])) {
        for (uint32_t move = 3u; move > slot; move--) {
          best_weights[move] = best_weights[move - 1u];
          best_joints[move] = best_joints[move - 1u];
        }
        best_weights[slot] = (float)weight;
        best_joints[slot] = (uint16_t)joint_index;
        break;
      }
    }
  }
  Py_DECREF(groups_seq);

  total = best_weights[0] + best_weights[1] + best_weights[2] + best_weights[3];
  if (total <= 0.0f)
    return 1;

  for (uint32_t i = 0; i < 4u; i++) {
    joints[i] = best_joints[i];
    weights[i] = best_weights[i] / total;
    if (weights[i] > 0.0f)
      *any_weight = 1;
  }
  return 1;
}

static int
akb_export_skin_cached_vertex(PyObject                 *vertices_obj,
                              Py_ssize_t               vertex_count,
                              uint32_t                 vertex_index,
                              const int32_t           *group_to_joint,
                              Py_ssize_t               group_to_joint_len,
                              AkbExportSkinVertexCache *cache,
                              uint16_t                 joints[4],
                              float                    weights[4]) {
  AkbExportSkinVertexCache *entry;
  PyObject                 *vertex_obj;
  PyObject                 *groups_obj;
  int                       any_weight;

  if (!vertices_obj || !group_to_joint || !cache || vertex_index >= (uint32_t)vertex_count)
    return 0;

  entry = &cache[vertex_index];
  if (!entry->filled) {
    any_weight = 0;
    vertex_obj = PySequence_GetItem(vertices_obj, (Py_ssize_t)vertex_index);
    if (!vertex_obj)
      return 0;

    groups_obj = PyObject_GetAttrString(vertex_obj, "groups");
    Py_DECREF(vertex_obj);
    if (!groups_obj)
      return 0;

    if (!akb_export_skin_group_values(groups_obj,
                                      group_to_joint,
                                      group_to_joint_len,
                                      entry->joints,
                                      entry->weights,
                                      &any_weight)) {
      Py_DECREF(groups_obj);
      return 0;
    }
    Py_DECREF(groups_obj);
    entry->filled = 1;
  }

  memcpy(joints, entry->joints, sizeof(entry->joints));
  memcpy(weights, entry->weights, sizeof(entry->weights));
  return 1;
}

static Py_ssize_t
akb_export_attr_len(PyObject *obj, const char *name) {
  PyObject   *attr;
  Py_ssize_t  len;

  attr = PyObject_GetAttrString(obj, name);
  if (!attr)
    return -1;
  len = PyObject_Length(attr);
  Py_DECREF(attr);
  return len;
}

static PyObject *
akb_export_attr_obj(PyObject *obj, const char *name) {
  PyObject *attr;

  attr = PyObject_GetAttrString(obj, name);
  if (!attr)
    return NULL;
  return attr;
}

static float
akb_export_clamp01_float(float value) {
  if (value < 0.0f)
    return 0.0f;
  if (value > 1.0f)
    return 1.0f;
  return value;
}

static int
akb_export_fast_attr_domain(PyObject *attr,
                            AkbExportFastAttrDomain *domain_out) {
  PyObject    *domain_obj;
  const char  *domain;

  if (!attr || !domain_out)
    return 0;

  domain_obj = PyObject_GetAttrString(attr, "domain");
  if (!domain_obj)
    return 0;
  domain = PyUnicode_AsUTF8(domain_obj);
  if (!domain) {
    Py_DECREF(domain_obj);
    return 0;
  }

  if (strcmp(domain, "CORNER") == 0)
    *domain_out = AKB_EXPORT_FAST_ATTR_CORNER;
  else if (strcmp(domain, "POINT") == 0)
    *domain_out = AKB_EXPORT_FAST_ATTR_POINT;
  else {
    Py_DECREF(domain_obj);
    return 0;
  }

  Py_DECREF(domain_obj);
  return 1;
}

static PyObject *
akb_export_fast_attr_get(PyObject *attrs, const char *name) {
  PyObject *attr;

  if (!attrs || !name)
    Py_RETURN_NONE;

  attr = PyObject_CallMethod(attrs, "get", "s", name);
  if (!attr) {
    PyErr_Clear();
    Py_RETURN_NONE;
  }
  if (!attr)
    Py_RETURN_NONE;
  return attr;
}

static uint64_t
akb_export_hash_bytes(uint64_t h, const void *data, size_t len) {
  const unsigned char *bytes;
  size_t               i;

  bytes = (const unsigned char *)data;
  for (i = 0; i < len; i++) {
    h ^= (uint64_t)bytes[i];
    h *= 1099511628211ull;
  }
  return h;
}

static uint64_t
akb_export_fast_vertex_hash(const float position[3],
                            uint32_t vertex_index,
                            const float normal[3],
                            const float tangent[4],
                            int has_tangents,
                            const float *uv,
                            uint32_t uv_count,
                            const float *color,
                            uint32_t color_count,
                            const uint16_t joints[4],
                            const float weights[4],
                            int has_skin,
                            int has_morph) {
  uint64_t h;

  h = 1469598103934665603ull;
  if (has_morph)
    h = akb_export_hash_bytes(h, &vertex_index, sizeof(vertex_index));
  h = akb_export_hash_bytes(h, position, sizeof(float) * 3u);
  h = akb_export_hash_bytes(h, normal, sizeof(float) * 3u);
  if (has_tangents)
    h = akb_export_hash_bytes(h, tangent, sizeof(float) * 4u);
  h = akb_export_hash_bytes(h, uv, sizeof(float) * (size_t)uv_count * 2u);
  h = akb_export_hash_bytes(h, color, sizeof(float) * (size_t)color_count * 4u);
  if (has_skin) {
    h = akb_export_hash_bytes(h, joints, sizeof(uint16_t) * 4u);
    h = akb_export_hash_bytes(h, weights, sizeof(float) * 4u);
  }
  return h;
}

static int
akb_export_fast_vertex_eq(const AkbExportFastVertex *entry,
                          const float position[3],
                          uint32_t vertex_index,
                          const float normal[3],
                          const float tangent[4],
                          int has_tangents,
                          const float *uv,
                          uint32_t uv_count,
                          const float *color,
                          uint32_t color_count,
                          const uint16_t joints[4],
                          const float weights[4],
                          int has_skin,
                          int has_morph) {
  return entry->used
         && (!has_morph || entry->vertexIndex == vertex_index)
         && memcmp(entry->position, position, sizeof(float) * 3u) == 0
         && memcmp(entry->normal, normal, sizeof(float) * 3u) == 0
         && (!has_tangents || memcmp(entry->tangent, tangent, sizeof(float) * 4u) == 0)
         && memcmp(entry->uv, uv, sizeof(float) * (size_t)uv_count * 2u) == 0
         && memcmp(entry->color, color, sizeof(float) * (size_t)color_count * 4u) == 0
         && (!has_skin
             || (memcmp(entry->joints, joints, sizeof(uint16_t) * 4u) == 0
                 && memcmp(entry->weights, weights, sizeof(float) * 4u) == 0));
}

static void
akb_export_fast_group_free(AkbExportFastGroup *group,
                           uint32_t uv_count,
                           uint32_t color_count,
                           uint32_t morph_count) {
  uint32_t i;

  if (!group)
    return;
  free(group->positions);
  free(group->normals);
  free(group->tangents);
  free(group->joints);
  free(group->weights);
  if (group->morphs) {
    for (i = 0; i < morph_count; i++)
      free(group->morphs[i]);
    free(group->morphs);
  }
  for (i = 0; i < uv_count; i++)
    free(group->uvs[i]);
  for (i = 0; i < color_count; i++)
    free(group->colors[i]);
  free(group->indices);
  free(group->table);
}

static int
akb_export_fast_group_reserve_vertices(AkbExportFastGroup *group,
                                       uint32_t uv_count,
                                       uint32_t color_count,
                                       uint32_t morph_count,
                                       int has_tangents,
                                       int has_skin,
                                       size_t needed) {
  size_t   new_cap;
  float   *new_positions;
  float   *new_normals;
  float   *new_tangents;
  uint16_t *new_joints;
  float   *new_weights;
  uint32_t i;

  if (needed <= group->vertexCap)
    return 1;
  new_cap = group->vertexCap ? group->vertexCap * 2u : 256u;
  while (new_cap < needed)
    new_cap *= 2u;

  new_positions = (float *)realloc(group->positions, new_cap * 3u * sizeof(float));
  if (!new_positions) {
    PyErr_NoMemory();
    return 0;
  }
  group->positions = new_positions;

  new_normals = (float *)realloc(group->normals, new_cap * 3u * sizeof(float));
  if (!new_normals) {
    PyErr_NoMemory();
    return 0;
  }
  group->normals = new_normals;

  if (has_tangents) {
    new_tangents = (float *)realloc(group->tangents, new_cap * 4u * sizeof(float));
    if (!new_tangents) {
      PyErr_NoMemory();
      return 0;
    }
    group->tangents = new_tangents;
  }

  if (has_skin) {
    new_joints = (uint16_t *)realloc(group->joints, new_cap * 4u * sizeof(uint16_t));
    if (!new_joints) {
      PyErr_NoMemory();
      return 0;
    }
    group->joints = new_joints;

    new_weights = (float *)realloc(group->weights, new_cap * 4u * sizeof(float));
    if (!new_weights) {
      PyErr_NoMemory();
      return 0;
    }
    group->weights = new_weights;
  }

  if (morph_count) {
    if (!group->morphs) {
      group->morphs = (float **)calloc(morph_count, sizeof(*group->morphs));
      if (!group->morphs) {
        PyErr_NoMemory();
        return 0;
      }
    }
    for (i = 0; i < morph_count; i++) {
      float *new_morph;

      new_morph = (float *)realloc(group->morphs[i], new_cap * 3u * sizeof(float));
      if (!new_morph) {
        PyErr_NoMemory();
        return 0;
      }
      group->morphs[i] = new_morph;
    }
  }

  for (i = 0; i < uv_count; i++) {
    float *new_uvs;

    new_uvs = (float *)realloc(group->uvs[i], new_cap * 2u * sizeof(float));
    if (!new_uvs) {
      PyErr_NoMemory();
      return 0;
    }
    group->uvs[i] = new_uvs;
  }

  for (i = 0; i < color_count; i++) {
    float *new_colors;

    new_colors = (float *)realloc(group->colors[i], new_cap * 4u * sizeof(float));
    if (!new_colors) {
      PyErr_NoMemory();
      return 0;
    }
    group->colors[i] = new_colors;
  }

  group->vertexCap = new_cap;
  return 1;
}

static int
akb_export_fast_group_reserve_indices(AkbExportFastGroup *group, size_t needed) {
  size_t    new_cap;
  uint32_t *new_indices;

  if (needed <= group->indexCap)
    return 1;
  new_cap = group->indexCap ? group->indexCap * 2u : 768u;
  while (new_cap < needed)
    new_cap *= 2u;
  new_indices = (uint32_t *)realloc(group->indices, new_cap * sizeof(uint32_t));
  if (!new_indices) {
    PyErr_NoMemory();
    return 0;
  }
  group->indices = new_indices;
  group->indexCap = new_cap;
  return 1;
}

static int
akb_export_fast_group_table_reserve(AkbExportFastGroup *group,
                                    uint32_t uv_count,
                                    uint32_t color_count,
                                    uint32_t morph_count,
                                    int has_tangents,
                                    int has_skin,
                                    size_t needed);

static int
akb_export_fast_group_table_insert_existing(AkbExportFastGroup *group,
                                            uint32_t uv_count,
                                            uint32_t color_count,
                                            uint32_t morph_count,
                                            int has_tangents,
                                            int has_skin,
                                            const AkbExportFastVertex *src) {
  uint64_t h;
  size_t   mask;
  size_t   slot;

  h = akb_export_fast_vertex_hash(src->position,
                                  src->vertexIndex,
                                  src->normal,
                                  src->tangent,
                                  has_tangents,
                                  src->uv,
                                  uv_count,
                                  src->color,
                                  color_count,
                                  src->joints,
                                  src->weights,
                                  has_skin,
                                  morph_count > 0);
  mask = group->tableCap - 1u;
  slot = (size_t)h & mask;
  for (;;) {
    AkbExportFastVertex *entry;

    entry = &group->table[slot];
    if (!entry->used) {
      *entry = *src;
      return 1;
    }
    slot = (slot + 1u) & mask;
  }
}

static int
akb_export_fast_group_table_reserve(AkbExportFastGroup *group,
                                    uint32_t uv_count,
                                    uint32_t color_count,
                                    uint32_t morph_count,
                                    int has_tangents,
                                    int has_skin,
                                    size_t needed) {
  AkbExportFastVertex *old_table;
  size_t               old_cap;
  size_t               new_cap;
  size_t               i;

  if (group->tableCap && needed * 2u < group->tableCap)
    return 1;

  old_table = group->table;
  old_cap = group->tableCap;
  new_cap = old_cap ? old_cap * 2u : 1024u;
  while (needed * 2u >= new_cap)
    new_cap *= 2u;

  group->table = (AkbExportFastVertex *)calloc(new_cap, sizeof(*group->table));
  if (!group->table) {
    group->table = old_table;
    PyErr_NoMemory();
    return 0;
  }
  group->tableCap = new_cap;
  group->tableCount = 0;

  if (old_table) {
    for (i = 0; i < old_cap; i++) {
      if (!old_table[i].used)
        continue;
      if (!akb_export_fast_group_table_insert_existing(group,
                                                       uv_count,
                                                       color_count,
                                                       morph_count,
                                                       has_tangents,
                                                       has_skin,
                                                       &old_table[i])) {
        free(old_table);
        return 0;
      }
      group->tableCount++;
    }
    free(old_table);
  }

  return 1;
}

static int
akb_export_fast_group_vertex(AkbExportFastGroup *group,
                             uint32_t uv_count,
                             uint32_t color_count,
                             uint32_t morph_count,
                             int has_tangents,
                             int has_skin,
                             const float *src_positions,
                             float **morph_deltas,
                             uint32_t vertex_index,
                             const float normal[3],
                             const float tangent[4],
                             const uint16_t joints[4],
                             const float weights[4],
                             const float *uv,
                             const float *color,
                             uint32_t *out_index) {
  uint64_t h;
  size_t   mask;
  size_t   slot;
  float    position[3];

  position[0] = src_positions[(size_t)vertex_index * 3u];
  position[1] = src_positions[(size_t)vertex_index * 3u + 1u];
  position[2] = src_positions[(size_t)vertex_index * 3u + 2u];

  if (!akb_export_fast_group_table_reserve(group,
                                           uv_count,
                                           color_count,
                                           morph_count,
                                           has_tangents,
                                           has_skin,
                                           group->tableCount + 1u))
    return 0;

  h = akb_export_fast_vertex_hash(position,
                                  vertex_index,
                                  normal,
                                  tangent,
                                  has_tangents,
                                  uv,
                                  uv_count,
                                  color,
                                  color_count,
                                  joints,
                                  weights,
                                  has_skin,
                                  morph_count > 0);
  mask = group->tableCap - 1u;
  slot = (size_t)h & mask;
  for (;;) {
    AkbExportFastVertex *entry;

    entry = &group->table[slot];
    if (!entry->used)
      break;
    if (akb_export_fast_vertex_eq(entry,
                                  position,
                                  vertex_index,
                                  normal,
                                  tangent,
                                  has_tangents,
                                  uv,
                                  uv_count,
                                  color,
                                  color_count,
                                  joints,
                                  weights,
                                  has_skin,
                                  morph_count > 0)) {
      *out_index = entry->outIndex;
      return 1;
    }
    slot = (slot + 1u) & mask;
  }

  if (group->vertexCount > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "too many exported mesh vertices");
    return 0;
  }
  if (!akb_export_fast_group_reserve_vertices(group,
                                              uv_count,
                                              color_count,
                                              morph_count,
                                              has_tangents,
                                              has_skin,
                                              group->vertexCount + 1u))
    return 0;

  *out_index = (uint32_t)group->vertexCount;
  memcpy(&group->positions[group->vertexCount * 3u], position, sizeof(float) * 3u);
  memcpy(&group->normals[group->vertexCount * 3u], normal, sizeof(float) * 3u);
  if (has_tangents)
    memcpy(&group->tangents[group->vertexCount * 4u], tangent, sizeof(float) * 4u);
  if (has_skin) {
    memcpy(&group->joints[group->vertexCount * 4u], joints, sizeof(uint16_t) * 4u);
    memcpy(&group->weights[group->vertexCount * 4u], weights, sizeof(float) * 4u);
  }
  for (uint32_t i = 0; i < morph_count; i++) {
    if (morph_deltas && morph_deltas[i] && group->morphs && group->morphs[i]) {
      memcpy(&group->morphs[i][group->vertexCount * 3u],
             &morph_deltas[i][(size_t)vertex_index * 3u],
             sizeof(float) * 3u);
    }
  }
  for (uint32_t i = 0; i < uv_count; i++) {
    group->uvs[i][group->vertexCount * 2u] = uv[(size_t)i * 2u];
    group->uvs[i][group->vertexCount * 2u + 1u] = uv[(size_t)i * 2u + 1u];
  }
  for (uint32_t i = 0; i < color_count; i++) {
    memcpy(&group->colors[i][group->vertexCount * 4u],
           &color[(size_t)i * 4u],
           sizeof(float) * 4u);
  }

  group->vertexCount++;
  group->tableCount++;

  group->table[slot].used = 1;
  group->table[slot].vertexIndex = vertex_index;
  group->table[slot].outIndex = *out_index;
  memcpy(group->table[slot].position, position, sizeof(float) * 3u);
  memcpy(group->table[slot].normal, normal, sizeof(float) * 3u);
  if (has_tangents)
    memcpy(group->table[slot].tangent, tangent, sizeof(float) * 4u);
  if (has_skin) {
    memcpy(group->table[slot].joints, joints, sizeof(uint16_t) * 4u);
    memcpy(group->table[slot].weights, weights, sizeof(float) * 4u);
  }
  memcpy(group->table[slot].uv, uv, sizeof(float) * (size_t)uv_count * 2u);
  memcpy(group->table[slot].color, color, sizeof(float) * (size_t)color_count * 4u);

  return 1;
}

static AkbExportFastGroup *
akb_export_fast_group_for_material(AkbExportFastGroup **groups,
                                   size_t *group_count,
                                   size_t *group_cap,
                                   int material_index) {
  size_t i;

  for (i = 0; i < *group_count; i++) {
    if ((*groups)[i].materialIndex == material_index)
      return &(*groups)[i];
  }

  if (*group_count == *group_cap) {
    size_t new_cap;
    AkbExportFastGroup *new_groups;

    new_cap = *group_cap ? *group_cap * 2u : 4u;
    new_groups = (AkbExportFastGroup *)realloc(*groups, new_cap * sizeof(*new_groups));
    if (!new_groups) {
      PyErr_NoMemory();
      return NULL;
    }
    memset(&new_groups[*group_cap], 0, (new_cap - *group_cap) * sizeof(*new_groups));
    *groups = new_groups;
    *group_cap = new_cap;
  }

  (*groups)[*group_count].materialIndex = material_index;
  return &(*groups)[(*group_count)++];
}

static int
akb_export_fast_read_tangent_attr(PyObject   *attr,
                                  Py_ssize_t  loop_count,
                                  PyObject  **tangent_buf_out,
                                  Py_buffer  *tangent_view_out,
                                  float     **tangents_out) {
  AkbExportFastAttrDomain domain;
  PyObject *data_obj;
  PyObject *buf;

  if (!attr || attr == Py_None)
    return 0;
  if (!akb_export_fast_attr_domain(attr, &domain) || domain != AKB_EXPORT_FAST_ATTR_CORNER) {
    PyErr_Clear();
    return 0;
  }

  data_obj = PyObject_GetAttrString(attr, "data");
  if (!data_obj) {
    PyErr_Clear();
    return 0;
  }
  if (PyObject_Length(data_obj) < loop_count) {
    Py_DECREF(data_obj);
    return 0;
  }

  buf = akb_export_array_new("f", loop_count * 4);
  if (!buf) {
    Py_DECREF(data_obj);
    return -1;
  }
  if (PyObject_GetBuffer(buf, tangent_view_out, PyBUF_SIMPLE) < 0) {
    Py_DECREF(buf);
    Py_DECREF(data_obj);
    return -1;
  }
  if (!akb_export_foreach_get_buffer(data_obj, "vector", buf, "f")) {
    PyBuffer_Release(tangent_view_out);
    memset(tangent_view_out, 0, sizeof(*tangent_view_out));
    Py_DECREF(buf);
    Py_DECREF(data_obj);
    PyErr_Clear();
    return 0;
  }

  Py_DECREF(data_obj);
  *tangent_buf_out = buf;
  *tangents_out = (float *)tangent_view_out->buf;
  return *tangents_out ? 1 : -1;
}

static int
akb_export_fast_read_tangent_split(PyObject   *attrs,
                                   Py_ssize_t  loop_count,
                                   PyObject  **tangent_buf_out,
                                   Py_buffer  *tangent_view_out,
                                   float     **tangents_out) {
  static const char *names[4] = {
    "assetkit_tangent_x",
    "assetkit_tangent_y",
    "assetkit_tangent_z",
    "assetkit_tangent_w"
  };
  PyObject *attrs_obj[4];
  PyObject *data_obj[4];
  PyObject *component_buf[4];
  Py_buffer component_view[4];
  PyObject *tangent_buf;
  float *components[4];
  float *tangents;
  int ok;

  memset(attrs_obj, 0, sizeof(attrs_obj));
  memset(data_obj, 0, sizeof(data_obj));
  memset(component_buf, 0, sizeof(component_buf));
  memset(component_view, 0, sizeof(component_view));
  memset(components, 0, sizeof(components));

  ok = 1;
  for (uint32_t i = 0; i < 4u; i++) {
    AkbExportFastAttrDomain domain;

    attrs_obj[i] = akb_export_fast_attr_get(attrs, names[i]);
    if (!attrs_obj[i] || attrs_obj[i] == Py_None) {
      ok = 0;
      goto done_split;
    }
    if (!akb_export_fast_attr_domain(attrs_obj[i], &domain)
        || domain != AKB_EXPORT_FAST_ATTR_CORNER) {
      PyErr_Clear();
      ok = 0;
      goto done_split;
    }
    data_obj[i] = PyObject_GetAttrString(attrs_obj[i], "data");
    if (!data_obj[i] || PyObject_Length(data_obj[i]) < loop_count) {
      PyErr_Clear();
      ok = 0;
      goto done_split;
    }
    component_buf[i] = akb_export_array_new("f", loop_count);
    if (!component_buf[i]
        || PyObject_GetBuffer(component_buf[i], &component_view[i], PyBUF_SIMPLE) < 0) {
      ok = -1;
      goto done_split;
    }
    components[i] = (float *)component_view[i].buf;
    if (!components[i]
        || !akb_export_foreach_get_buffer(data_obj[i], "value", component_buf[i], "f")) {
      ok = -1;
      goto done_split;
    }
  }

  tangent_buf = akb_export_array_new("f", loop_count * 4);
  if (!tangent_buf || PyObject_GetBuffer(tangent_buf, tangent_view_out, PyBUF_SIMPLE) < 0) {
    Py_XDECREF(tangent_buf);
    ok = -1;
    goto done_split;
  }
  tangents = (float *)tangent_view_out->buf;
  if (!tangents) {
    PyBuffer_Release(tangent_view_out);
    memset(tangent_view_out, 0, sizeof(*tangent_view_out));
    Py_DECREF(tangent_buf);
    ok = -1;
    goto done_split;
  }
  for (Py_ssize_t i = 0; i < loop_count; i++) {
    tangents[(size_t)i * 4u] = components[0][i];
    tangents[(size_t)i * 4u + 1u] = components[1][i];
    tangents[(size_t)i * 4u + 2u] = components[2][i];
    tangents[(size_t)i * 4u + 3u] = components[3][i];
  }
  *tangent_buf_out = tangent_buf;
  *tangents_out = tangents;
  ok = 1;

done_split:
  for (uint32_t i = 0; i < 4u; i++) {
    if (component_view[i].buf)
      PyBuffer_Release(&component_view[i]);
    Py_XDECREF(component_buf[i]);
    Py_XDECREF(data_obj[i]);
    Py_XDECREF(attrs_obj[i]);
  }
  if (ok < 0 && !PyErr_Occurred())
    PyErr_NoMemory();
  return ok;
}

static int
akb_export_fast_read_tangents(PyObject   *mesh,
                              Py_ssize_t  loop_count,
                              PyObject  **tangent_buf_out,
                              Py_buffer  *tangent_view_out,
                              float     **tangents_out,
                              int        *has_tangents_out) {
  PyObject *attrs;
  PyObject *attr;
  int       result;

  *tangent_buf_out = NULL;
  *tangents_out = NULL;
  *has_tangents_out = 0;

  attrs = PyObject_GetAttrString(mesh, "attributes");
  if (!attrs) {
    PyErr_Clear();
    return 1;
  }

  attr = akb_export_fast_attr_get(attrs, "assetkit_tangent");
  result = akb_export_fast_read_tangent_attr(attr,
                                             loop_count,
                                             tangent_buf_out,
                                             tangent_view_out,
                                             tangents_out);
  Py_XDECREF(attr);
  if (result < 0) {
    Py_DECREF(attrs);
    return 0;
  }
  if (result > 0) {
    *has_tangents_out = 1;
    Py_DECREF(attrs);
    return 1;
  }

  result = akb_export_fast_read_tangent_split(attrs,
                                              loop_count,
                                              tangent_buf_out,
                                              tangent_view_out,
                                              tangents_out);
  Py_DECREF(attrs);
  if (result < 0)
    return 0;
  *has_tangents_out = result > 0;
  return 1;
}

static AkMeshPrimitive *
akb_export_add_native_group_primitive(AkDoc              *doc,
                                      AkObject           *mesh_obj,
                                      AkMesh             *mesh,
                                      AkbExportFastGroup *group,
                                      uint32_t            uv_count,
                                      uint32_t            color_count,
                                      int                 has_tangents,
                                      int                 has_skin,
                                      AkMaterial         *material) {
  AkHeap          *heap;
  AkTriangles     *tri;
  AkMeshPrimitive *prim;
  uint32_t         vertex_count;
  uint32_t         i;

  if (!doc || !mesh_obj || !mesh || !group || !group->positions || group->vertexCount == 0)
    return NULL;
  if (group->vertexCount > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "too many exported mesh vertices");
    return NULL;
  }

  heap = ak_heap_getheap(doc);
  if (!heap)
    return NULL;

  tri = (AkTriangles *)ak_heap_calloc(heap, mesh_obj, sizeof(*tri));
  if (!tri)
    return NULL;

  vertex_count   = (uint32_t)group->vertexCount;
  tri->mode      = AK_TRIANGLES;
  prim           = &tri->base;
  prim->mesh     = mesh;
  prim->type     = AK_PRIMITIVE_TRIANGLES;
  prim->material = material;
  prim->nPolygons = (uint32_t)(group->indexCount / 3u);

  if (group->indices && group->indexCount) {
    prim->indices = akb_export_indices_from_u32(heap,
                                                prim,
                                                group->indices,
                                                group->indexCount,
                                                vertex_count);
    if (!prim->indices)
      return NULL;
  }

  if (!akb_export_add_input_buffer(heap,
                                   doc,
                                   prim,
                                   group->positions,
                                   (size_t)vertex_count * 3u * sizeof(float),
                                   vertex_count,
                                   AK_COMPONENT_SIZE_VEC3,
                                   AKT_FLOAT,
                                   3,
                                   AK_INPUT_POSITION,
                                   "POSITION",
                                   0))
    return NULL;

  if (!akb_export_add_input_buffer(heap,
                                   doc,
                                   prim,
                                   group->normals,
                                   (size_t)vertex_count * 3u * sizeof(float),
                                   vertex_count,
                                   AK_COMPONENT_SIZE_VEC3,
                                   AKT_FLOAT,
                                   3,
                                   AK_INPUT_NORMAL,
                                   "NORMAL",
                                   0))
    return NULL;

  if (has_tangents && group->tangents) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     group->tangents,
                                     (size_t)vertex_count * 4u * sizeof(float),
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_FLOAT,
                                     4,
                                     AK_INPUT_TANGENT,
                                     "TANGENT",
                                     0))
      return NULL;
  }

  if (has_skin && group->joints && group->weights) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     group->joints,
                                     (size_t)vertex_count * 4u * sizeof(uint16_t),
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_USHORT,
                                     4,
                                     AK_INPUT_JOINT,
                                     "JOINTS",
                                     0))
      return NULL;

    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     group->weights,
                                     (size_t)vertex_count * 4u * sizeof(float),
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_FLOAT,
                                     4,
                                     AK_INPUT_WEIGHT,
                                     "WEIGHTS",
                                     0))
      return NULL;
  }

  for (i = 0; i < uv_count; i++) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     group->uvs[i],
                                     (size_t)vertex_count * 2u * sizeof(float),
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC2,
                                     AKT_FLOAT,
                                     2,
                                     AK_INPUT_TEXCOORD,
                                     "TEXCOORD",
                                     i))
      return NULL;
  }

  for (i = 0; i < color_count; i++) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     group->colors[i],
                                     (size_t)vertex_count * 4u * sizeof(float),
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_FLOAT,
                                     4,
                                     AK_INPUT_COLOR,
                                     "COLOR",
                                     i))
      return NULL;
  }

  return prim;
}

static void
akb_export_fast_groups_free(AkbExportFastGroup *groups,
                            size_t              group_count,
                            uint32_t            uv_count,
                            uint32_t            color_count,
                            uint32_t            morph_count) {
  size_t i;

  if (!groups)
    return;
  for (i = 0; i < group_count; i++)
    akb_export_fast_group_free(&groups[i], uv_count, color_count, morph_count);
  free(groups);
}

static AkLineMode
akb_export_line_mode_from_source(uint32_t source_mode) {
  switch (source_mode) {
    case AK_LINE_LOOP:
      return AK_LINE_LOOP;
    case AK_LINE_STRIP:
      return AK_LINE_STRIP;
    case AK_LINES:
    default:
      return AK_LINES;
  }
}

static int
akb_export_add_point_color_inputs(AkHeap          *heap,
                                  AkDoc           *doc,
                                  AkMeshPrimitive *prim,
                                  PyObject        *color_layers_seq,
                                  uint32_t         vertex_count) {
  Py_ssize_t color_count;

  if (!color_layers_seq || color_layers_seq == Py_None)
    return 1;

  color_count = PySequence_Fast_GET_SIZE(color_layers_seq);
  if (color_count < 0)
    return 0;

  for (Py_ssize_t i = 0; i < color_count; i++) {
    PyObject *color_layer;
    PyObject *data_obj;
    PyObject *color_buf;
    Py_buffer color_view;
    float *colors;
    AkbExportFastAttrDomain domain;
    size_t value_count;
    int ok;

    color_layer = PySequence_Fast_GET_ITEM(color_layers_seq, i);
    if (!akb_export_fast_attr_domain(color_layer, &domain)) {
      PyErr_Clear();
      continue;
    }
    if (domain != AKB_EXPORT_FAST_ATTR_POINT)
      continue;

    data_obj = PyObject_GetAttrString(color_layer, "data");
    if (!data_obj)
      return 0;
    if (PyObject_Length(data_obj) < (Py_ssize_t)vertex_count) {
      Py_DECREF(data_obj);
      PyErr_SetString(PyExc_ValueError, "point color attribute is shorter than mesh vertex count");
      return 0;
    }

    memset(&color_view, 0, sizeof(color_view));
    color_buf = akb_export_array_new("f", (Py_ssize_t)vertex_count * 4);
    if (!color_buf || PyObject_GetBuffer(color_buf, &color_view, PyBUF_SIMPLE) < 0) {
      Py_XDECREF(color_buf);
      Py_DECREF(data_obj);
      PyErr_NoMemory();
      return 0;
    }
    colors = (float *)color_view.buf;
    ok = colors && akb_export_foreach_get_buffer(data_obj, "color", color_buf, "f");
    if (ok) {
      value_count = (size_t)vertex_count * 4u;
      for (size_t j = 0; j < value_count; j++)
        colors[j] = akb_export_clamp01_float(colors[j]);
      ok = akb_export_add_input_buffer(heap,
                                       doc,
                                       prim,
                                       colors,
                                       value_count * sizeof(float),
                                       vertex_count,
                                       AK_COMPONENT_SIZE_VEC4,
                                       AKT_FLOAT,
                                       4,
                                       AK_INPUT_COLOR,
                                       "COLOR",
                                       (uint32_t)i);
    }

    PyBuffer_Release(&color_view);
    Py_DECREF(color_buf);
    Py_DECREF(data_obj);
    if (!ok)
      return 0;
  }

  return 1;
}

static int
akb_export_add_point_normal_input(AkHeap          *heap,
                                  AkDoc           *doc,
                                  AkMeshPrimitive *prim,
                                  PyObject        *mesh_py,
                                  uint32_t         vertex_count) {
  PyObject *attrs_obj;
  PyObject *normal_attr;
  PyObject *data_obj;
  PyObject *normal_buf;
  Py_buffer normal_view;
  float *normals;
  AkbExportFastAttrDomain domain;
  int ok;

  attrs_obj = PyObject_GetAttrString(mesh_py, "attributes");
  if (!attrs_obj) {
    PyErr_Clear();
    return 1;
  }

  normal_attr = akb_export_fast_attr_get(attrs_obj, "assetkit_normal");
  Py_DECREF(attrs_obj);
  if (!normal_attr || normal_attr == Py_None) {
    Py_XDECREF(normal_attr);
    return 1;
  }

  ok = 1;
  memset(&normal_view, 0, sizeof(normal_view));
  data_obj = NULL;
  normal_buf = NULL;
  if (!akb_export_fast_attr_domain(normal_attr, &domain)) {
    PyErr_Clear();
    goto done_point_normal;
  }
  if (domain != AKB_EXPORT_FAST_ATTR_POINT)
    goto done_point_normal;

  data_obj = PyObject_GetAttrString(normal_attr, "data");
  if (!data_obj) {
    ok = 0;
    goto done_point_normal;
  }
  if (PyObject_Length(data_obj) < (Py_ssize_t)vertex_count) {
    PyErr_SetString(PyExc_ValueError, "point normal attribute is shorter than mesh vertex count");
    ok = 0;
    goto done_point_normal;
  }

  normal_buf = akb_export_array_new("f", (Py_ssize_t)vertex_count * 3);
  if (!normal_buf || PyObject_GetBuffer(normal_buf, &normal_view, PyBUF_SIMPLE) < 0) {
    PyErr_NoMemory();
    ok = 0;
    goto done_point_normal;
  }
  normals = (float *)normal_view.buf;
  if (!normals
      || !akb_export_foreach_get_buffer(data_obj, "vector", normal_buf, "f")
      || !akb_export_add_input_buffer(heap,
                                      doc,
                                      prim,
                                      normals,
                                      (size_t)vertex_count * 3u * sizeof(float),
                                      vertex_count,
                                      AK_COMPONENT_SIZE_VEC3,
                                      AKT_FLOAT,
                                      3,
                                      AK_INPUT_NORMAL,
                                      "NORMAL",
                                      0))
    ok = 0;

done_point_normal:
  if (normal_view.buf)
    PyBuffer_Release(&normal_view);
  Py_XDECREF(normal_buf);
  Py_XDECREF(data_obj);
  Py_DECREF(normal_attr);
  return ok;
}

static int
akb_export_add_point_line_mesh_payload_to_node(AkDoc      *doc,
                                               AkNode     *node,
                                               const char *name,
                                               PyObject   *mesh_py,
                                               PyObject   *materials_seq,
                                               PyObject   *color_layers_seq,
                                               PyObject   *variants_obj,
                                               PyObject   *mesh_extra_obj,
                                               PyObject   *geometry_extra_obj,
                                               PyObject   *primitive_extra_obj,
                                               uint32_t    source_primitive_type,
                                               uint32_t    source_primitive_mode) {
  AkHeap          *heap;
  AkGeometry      *geom;
  AkObject        *mesh_obj;
  AkMesh          *mesh;
  AkMeshPrimitive *prim;
  AkMaterial      *material;
  PyObject        *vertices_obj;
  PyObject        *edges_obj;
  PyObject        *positions_buf;
  PyObject        *edge_indices_buf;
  Py_buffer        positions_view;
  Py_buffer        edge_indices_view;
  float           *positions;
  int32_t         *edge_indices;
  Py_ssize_t       vertex_count_py;
  Py_ssize_t       edge_count_py;
  Py_ssize_t       material_count_py;
  int              material_index;
  int              ok;

  if (!doc || !node || !mesh_py)
    return 0;
  if (source_primitive_type != AKB_PRIMITIVE_POINTS
      && source_primitive_type != AKB_PRIMITIVE_LINES)
    return 1;

  memset(&positions_view, 0, sizeof(positions_view));
  memset(&edge_indices_view, 0, sizeof(edge_indices_view));
  vertices_obj = NULL;
  edges_obj = NULL;
  positions_buf = NULL;
  edge_indices_buf = NULL;
  positions = NULL;
  edge_indices = NULL;
  prim = NULL;
  ok = 1;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  vertices_obj = akb_export_attr_obj(mesh_py, "vertices");
  if (!vertices_obj)
    return 0;
  vertex_count_py = PyObject_Length(vertices_obj);
  if (vertex_count_py <= 0) {
    ok = 1;
    goto done_point_line;
  }
  if (vertex_count_py > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "too many exported mesh vertices");
    ok = 0;
    goto done_point_line;
  }

  edge_count_py = 0;
  if (source_primitive_type == AKB_PRIMITIVE_LINES) {
    edges_obj = akb_export_attr_obj(mesh_py, "edges");
    if (!edges_obj) {
      ok = 0;
      goto done_point_line;
    }
    edge_count_py = PyObject_Length(edges_obj);
    if (edge_count_py <= 0) {
      ok = 1;
      goto done_point_line;
    }
    if (edge_count_py > (Py_ssize_t)(UINT32_MAX / 2u)) {
      PyErr_SetString(PyExc_OverflowError, "too many exported mesh line indices");
      ok = 0;
      goto done_point_line;
    }
  }

  positions_buf = akb_export_array_new("f", vertex_count_py * 3);
  if (!positions_buf || PyObject_GetBuffer(positions_buf, &positions_view, PyBUF_SIMPLE) < 0) {
    PyErr_NoMemory();
    ok = 0;
    goto done_point_line;
  }
  positions = (float *)positions_view.buf;
  if (!positions
      || !akb_export_foreach_get_buffer(vertices_obj, "co", positions_buf, "f")) {
    ok = 0;
    goto done_point_line;
  }

  if (source_primitive_type == AKB_PRIMITIVE_LINES) {
    edge_indices_buf = akb_export_array_new("i", edge_count_py * 2);
    if (!edge_indices_buf
        || PyObject_GetBuffer(edge_indices_buf, &edge_indices_view, PyBUF_SIMPLE) < 0) {
      PyErr_NoMemory();
      ok = 0;
      goto done_point_line;
    }
    edge_indices = (int32_t *)edge_indices_view.buf;
    if (!edge_indices
        || !akb_export_foreach_get_buffer(edges_obj, "vertices", edge_indices_buf, "i")) {
      ok = 0;
      goto done_point_line;
    }
  }

  geom = (AkGeometry *)ak_heap_calloc(heap, doc, sizeof(*geom));
  if (!geom) {
    PyErr_NoMemory();
    ok = 0;
    goto done_point_line;
  }
  geom->name = name && name[0] ? name : NULL;
  ak_setypeid(geom, AKT_GEOMETRY);

  mesh_obj = ak_objAlloc(heap, geom, sizeof(*mesh), AK_GEOMETRY_MESH, true);
  if (!mesh_obj) {
    PyErr_NoMemory();
    ok = 0;
    goto done_point_line;
  }
  geom->gdata = mesh_obj;
  mesh = (AkMesh *)ak_objGet(mesh_obj);
  mesh->geom = geom;
  mesh->name = name && name[0] ? name : NULL;
  if (!akb_export_apply_direct_extra(doc, geom, &mesh->extra, mesh_extra_obj)
      || !akb_export_apply_direct_extra(doc, geom, &geom->extra, geometry_extra_obj)) {
    ok = 0;
    goto done_point_line;
  }

  material_count_py = PySequence_Fast_GET_SIZE(materials_seq);
  material_index = material_count_py > 0 ? 0 : -1;
  material = material_index >= 0
               ? akb_export_material(doc, PySequence_Fast_GET_ITEM(materials_seq, 0))
               : akb_export_material(doc, Py_None);
  if (PyErr_Occurred()) {
    ok = 0;
    goto done_point_line;
  }

  if (source_primitive_type == AKB_PRIMITIVE_LINES) {
    AkLines *lines;

    lines = (AkLines *)ak_heap_calloc(heap, mesh_obj, sizeof(*lines));
    if (!lines) {
      PyErr_NoMemory();
      ok = 0;
      goto done_point_line;
    }
    lines->mode = akb_export_line_mode_from_source(source_primitive_mode);
    prim = &lines->base;
    prim->type = AKB_PRIMITIVE_LINES;
    prim->nPolygons = (uint32_t)edge_count_py;
    prim->indices = akb_export_index_array_from_i32(heap,
                                                    prim,
                                                    edge_indices,
                                                    (size_t)edge_count_py * 2u,
                                                    (uint32_t)vertex_count_py);
    if (!prim->indices) {
      ok = 0;
      goto done_point_line;
    }
  } else {
    prim = (AkMeshPrimitive *)ak_heap_calloc(heap, mesh_obj, sizeof(*prim));
    if (!prim) {
      PyErr_NoMemory();
      ok = 0;
      goto done_point_line;
    }
    prim->type = AKB_PRIMITIVE_POINTS;
    prim->nPolygons = (uint32_t)vertex_count_py;
  }

  prim->mesh = mesh;
  prim->material = material;
  if (!akb_export_add_input_buffer(heap,
                                   doc,
                                   prim,
                                   positions,
                                   (size_t)vertex_count_py * 3u * sizeof(float),
                                   (uint32_t)vertex_count_py,
                                   AK_COMPONENT_SIZE_VEC3,
                                   AKT_FLOAT,
                                   3,
                                   AK_INPUT_POSITION,
                                   "POSITION",
                                   0)
      || !akb_export_add_point_normal_input(heap,
                                            doc,
                                            prim,
                                            mesh_py,
                                            (uint32_t)vertex_count_py)
      || !akb_export_add_point_color_inputs(heap,
                                            doc,
                                            prim,
                                            color_layers_seq,
                                            (uint32_t)vertex_count_py)
      || !akb_export_apply_direct_extra(doc, geom, &prim->extra, primitive_extra_obj)
      || !akb_export_apply_material_variants(doc,
                                             prim,
                                             variants_obj,
                                             material_index,
                                             materials_seq)) {
    ok = 0;
    goto done_point_line;
  }

  mesh->primitive = prim;
  mesh->primitiveCount = 1;
  AKB_LIB_APPEND(doc->lib.geometries, geom, next);
  if (!ak_nodeAttachGeometry(node, geom)) {
    ok = 0;
    goto done_point_line;
  }

done_point_line:
  if (edge_indices_view.buf)
    PyBuffer_Release(&edge_indices_view);
  if (positions_view.buf)
    PyBuffer_Release(&positions_view);
  Py_XDECREF(edge_indices_buf);
  Py_XDECREF(positions_buf);
  Py_XDECREF(edges_obj);
  Py_XDECREF(vertices_obj);
  return ok;
}

static int
akb_export_add_native_mesh_payload_to_node(AkDoc      *doc,
                                           AkNode     *node,
                                           const char *name,
                                           PyObject   *payload_obj,
                                           AkNode    **nodes,
                                           Py_ssize_t  node_count) {
  PyObject *mesh_py;
  PyObject *uv_layers_obj;
  PyObject *color_layers_obj;
  PyObject *materials_obj;
  PyObject *skin_mapping_obj;
  PyObject *skin_obj;
  PyObject *morph_obj;
  PyObject *variants_obj;
  PyObject *mesh_extra_obj;
  PyObject *geometry_extra_obj;
  PyObject *primitive_extra_obj;
  PyObject *morph_basis_obj;
  PyObject *morph_targets_obj;
  PyObject *morph_names_obj;
  PyObject *morph_weights_obj;
  PyObject *morph_animation_obj;
  PyObject *uv_layers_seq;
  PyObject *color_layers_seq;
  PyObject *materials_seq;
  PyObject *morph_targets_seq;
  PyObject *vertices_obj;
  PyObject *loops_obj;
  PyObject *loop_tris_obj;
  PyObject *corner_normals_obj;
  PyObject *morph_basis_data_obj;
  PyObject **morph_data_objs;
  PyObject *uv_data_objs[AKB_EXPORT_FAST_UV_MAX];
  PyObject *color_data_objs[AKB_EXPORT_FAST_COLOR_MAX];
  PyObject *positions_buf;
  PyObject *normals_buf;
  PyObject *tangents_buf;
  PyObject *loop_vertices_buf;
  PyObject *tri_loops_buf;
  PyObject *tri_materials_buf;
  PyObject **morph_bufs;
  PyObject *uv_bufs[AKB_EXPORT_FAST_UV_MAX];
  PyObject *color_bufs[AKB_EXPORT_FAST_COLOR_MAX];
  Py_buffer positions_view;
  Py_buffer normals_view;
  Py_buffer tangents_view;
  Py_buffer loop_vertices_view;
  Py_buffer tri_loops_view;
  Py_buffer tri_materials_view;
  Py_buffer *morph_views;
  Py_buffer uv_views[AKB_EXPORT_FAST_UV_MAX];
  Py_buffer color_views[AKB_EXPORT_FAST_COLOR_MAX];
  float *positions;
  float *normals;
  float *tangents;
  int32_t *group_to_joint;
  Py_ssize_t group_to_joint_len;
  AkbExportSkinVertexCache *skin_cache;
  float **morph_deltas;
  float *uvs[AKB_EXPORT_FAST_UV_MAX];
  float *colors[AKB_EXPORT_FAST_COLOR_MAX];
  int32_t *loop_vertices;
  int32_t *tri_loops;
  int32_t *tri_materials;
  AkbExportFastAttrDomain color_domains[AKB_EXPORT_FAST_COLOR_MAX];
  Py_ssize_t vertex_count;
  Py_ssize_t loop_count;
  Py_ssize_t tri_count;
  Py_ssize_t uv_count_py;
  Py_ssize_t color_count_py;
  Py_ssize_t material_count_py;
  uint32_t uv_count;
  uint32_t color_count;
  uint32_t morph_count;
  Py_ssize_t payload_size;
  AkHeap *heap;
  AkGeometry *geom;
  AkObject *mesh_obj;
  AkMesh *mesh;
  AkMeshPrimitive *last_prim;
  AkbExportMorphBuild morph_build;
  AkbExportFastGroup *groups;
  size_t group_count;
  size_t invalid_group_index;
  uint32_t source_primitive_type;
  uint32_t source_primitive_mode;
  int has_tangents;
  int has_skin;
  int has_morph;
  int flip_uv_v;
  int ok;

  if (!doc || !node || !payload_obj)
    return 0;
  flip_uv_v = doc->inf
              && (doc->inf->ftype == AK_FILE_TYPE_GLTF
                  || doc->inf->ftype == AK_FILE_TYPE_GLB);

  mesh_py = PyTuple_GET_ITEM(payload_obj, 1);
  uv_layers_obj = PyTuple_GET_ITEM(payload_obj, 2);
  color_layers_obj = PyTuple_GET_ITEM(payload_obj, 3);
  materials_obj = PyTuple_GET_ITEM(payload_obj, 4);
  payload_size = PyTuple_Size(payload_obj);
  skin_mapping_obj = Py_None;
  skin_obj = Py_None;
  morph_obj = Py_None;
  variants_obj = Py_None;
  mesh_extra_obj = Py_None;
  geometry_extra_obj = Py_None;
  primitive_extra_obj = Py_None;
  source_primitive_type = 0;
  source_primitive_mode = 0;
  if (payload_size >= 7) {
    skin_mapping_obj = PyTuple_GET_ITEM(payload_obj, 5);
    skin_obj = PyTuple_GET_ITEM(payload_obj, 6);
  }
  if (payload_size >= 8)
    morph_obj = PyTuple_GET_ITEM(payload_obj, 7);
  if (payload_size >= 9)
    variants_obj = PyTuple_GET_ITEM(payload_obj, 8);
  if (payload_size >= 10)
    mesh_extra_obj = PyTuple_GET_ITEM(payload_obj, 9);
  if (payload_size >= 11)
    geometry_extra_obj = PyTuple_GET_ITEM(payload_obj, 10);
  if (payload_size >= 12)
    primitive_extra_obj = PyTuple_GET_ITEM(payload_obj, 11);
  if (payload_size >= 14) {
    unsigned long value;

    value = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(payload_obj, 12));
    if (PyErr_Occurred()) {
      PyErr_Clear();
      value = 0;
    }
    source_primitive_type = (uint32_t)value;

    value = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(payload_obj, 13));
    if (PyErr_Occurred()) {
      PyErr_Clear();
      value = 0;
    }
    source_primitive_mode = (uint32_t)value;
  }
  has_skin = skin_mapping_obj != Py_None && skin_obj != Py_None;
  has_morph = morph_obj != Py_None;

  if (PyObject_CallMethod(mesh_py, "calc_loop_triangles", NULL) == NULL)
    return 0;

  uv_layers_seq = PySequence_Fast(uv_layers_obj, "uv layers must be a sequence");
  color_layers_seq = PySequence_Fast(color_layers_obj, "color layers must be a sequence");
  materials_seq = PySequence_Fast(materials_obj, "material payloads must be a sequence");
  morph_targets_seq = NULL;
  morph_basis_obj = Py_None;
  morph_targets_obj = Py_None;
  morph_names_obj = Py_None;
  morph_weights_obj = Py_None;
  morph_animation_obj = Py_None;
  morph_basis_data_obj = NULL;
  group_to_joint = NULL;
  group_to_joint_len = 0;
  skin_cache = NULL;
  if (!uv_layers_seq || !color_layers_seq || !materials_seq) {
    Py_XDECREF(uv_layers_seq);
    Py_XDECREF(color_layers_seq);
    Py_XDECREF(materials_seq);
    return 0;
  }

  morph_count = 0;
  if (has_morph) {
    if (!PyArg_ParseTuple(morph_obj,
                          "OOOOO",
                          &morph_basis_obj,
                          &morph_targets_obj,
                          &morph_names_obj,
                          &morph_weights_obj,
                          &morph_animation_obj)) {
      Py_DECREF(uv_layers_seq);
      Py_DECREF(color_layers_seq);
      Py_DECREF(materials_seq);
      return 0;
    }
    morph_targets_seq = PySequence_Fast(morph_targets_obj,
                                        "morph targets must be a sequence");
    if (!morph_targets_seq) {
      Py_DECREF(uv_layers_seq);
      Py_DECREF(color_layers_seq);
      Py_DECREF(materials_seq);
      return 0;
    }
    if (PySequence_Fast_GET_SIZE(morph_targets_seq) > UINT32_MAX) {
      Py_DECREF(morph_targets_seq);
      Py_DECREF(uv_layers_seq);
      Py_DECREF(color_layers_seq);
      Py_DECREF(materials_seq);
      PyErr_SetString(PyExc_OverflowError, "too many morph targets");
      return 0;
    }
    morph_count = (uint32_t)PySequence_Fast_GET_SIZE(morph_targets_seq);
    has_morph = morph_count > 0;
    if (!has_morph) {
      Py_DECREF(morph_targets_seq);
      morph_targets_seq = NULL;
    }
  }

  uv_count_py = PySequence_Fast_GET_SIZE(uv_layers_seq);
  color_count_py = PySequence_Fast_GET_SIZE(color_layers_seq);
  material_count_py = PySequence_Fast_GET_SIZE(materials_seq);
  if (uv_count_py < 0 || uv_count_py > (Py_ssize_t)AKB_EXPORT_FAST_UV_MAX
      || color_count_py < 0 || color_count_py > (Py_ssize_t)AKB_EXPORT_FAST_COLOR_MAX) {
    Py_XDECREF(morph_targets_seq);
    Py_DECREF(uv_layers_seq);
    Py_DECREF(color_layers_seq);
    Py_DECREF(materials_seq);
    return 0;
  }
  uv_count = (uint32_t)uv_count_py;
  color_count = (uint32_t)color_count_py;
  if (material_count_py < 0 || material_count_py > INT_MAX) {
    Py_XDECREF(morph_targets_seq);
    Py_DECREF(uv_layers_seq);
    Py_DECREF(color_layers_seq);
    Py_DECREF(materials_seq);
    PyErr_SetString(PyExc_OverflowError, "too many material slots");
    return 0;
  }

  vertices_obj = akb_export_attr_obj(mesh_py, "vertices");
  loops_obj = akb_export_attr_obj(mesh_py, "loops");
  loop_tris_obj = akb_export_attr_obj(mesh_py, "loop_triangles");
  corner_normals_obj = akb_export_attr_obj(mesh_py, "corner_normals");
  if (!vertices_obj || !loops_obj || !loop_tris_obj || !corner_normals_obj) {
    Py_XDECREF(vertices_obj);
    Py_XDECREF(loops_obj);
    Py_XDECREF(loop_tris_obj);
    Py_XDECREF(corner_normals_obj);
    Py_XDECREF(morph_targets_seq);
    Py_DECREF(uv_layers_seq);
    Py_DECREF(color_layers_seq);
    Py_DECREF(materials_seq);
    return 0;
  }

  vertex_count = PyObject_Length(vertices_obj);
  loop_count = PyObject_Length(loops_obj);
  tri_count = PyObject_Length(loop_tris_obj);
  if (vertex_count <= 0 || loop_count <= 0 || tri_count <= 0) {
    int point_line_ok;

    point_line_ok = 1;
    if (vertex_count > 0
        && (source_primitive_type == AKB_PRIMITIVE_POINTS
            || source_primitive_type == AKB_PRIMITIVE_LINES)) {
      if (has_skin || has_morph) {
        PyErr_SetString(PyExc_ValueError, "point and line mesh export does not support skin or morph payloads");
        point_line_ok = 0;
      } else {
        point_line_ok = akb_export_add_point_line_mesh_payload_to_node(doc,
                                                                       node,
                                                                       name,
                                                                       mesh_py,
                                                                       materials_seq,
                                                                       color_layers_seq,
                                                                       variants_obj,
                                                                       mesh_extra_obj,
                                                                       geometry_extra_obj,
                                                                       primitive_extra_obj,
                                                                       source_primitive_type,
                                                                       source_primitive_mode);
      }
    }
    Py_DECREF(vertices_obj);
    Py_DECREF(loops_obj);
    Py_DECREF(loop_tris_obj);
    Py_DECREF(corner_normals_obj);
    Py_XDECREF(morph_targets_seq);
    Py_DECREF(uv_layers_seq);
    Py_DECREF(color_layers_seq);
    Py_DECREF(materials_seq);
    return point_line_ok;
  }

  memset(&positions_view, 0, sizeof(positions_view));
  memset(&normals_view, 0, sizeof(normals_view));
  memset(&tangents_view, 0, sizeof(tangents_view));
  memset(&loop_vertices_view, 0, sizeof(loop_vertices_view));
  memset(&tri_loops_view, 0, sizeof(tri_loops_view));
  memset(&tri_materials_view, 0, sizeof(tri_materials_view));
  memset(uv_data_objs, 0, sizeof(uv_data_objs));
  memset(color_data_objs, 0, sizeof(color_data_objs));
  memset(uv_bufs, 0, sizeof(uv_bufs));
  memset(color_bufs, 0, sizeof(color_bufs));
  memset(uv_views, 0, sizeof(uv_views));
  memset(color_views, 0, sizeof(color_views));
  memset(uvs, 0, sizeof(uvs));
  memset(colors, 0, sizeof(colors));
  memset(color_domains, 0, sizeof(color_domains));
  positions_buf = akb_export_array_new("f", vertex_count * 3);
  normals_buf = akb_export_array_new("f", loop_count * 3);
  tangents_buf = NULL;
  loop_vertices_buf = akb_export_array_new("i", loop_count);
  tri_loops_buf = akb_export_array_new("i", tri_count * 3);
  tri_materials_buf = akb_export_array_new("i", tri_count);
  morph_deltas = NULL;
  morph_bufs = NULL;
  morph_views = NULL;
  morph_data_objs = NULL;
  if (has_morph) {
    morph_deltas = (float **)calloc((size_t)morph_count, sizeof(*morph_deltas));
    morph_bufs = (PyObject **)calloc((size_t)morph_count, sizeof(*morph_bufs));
    morph_views = (Py_buffer *)calloc((size_t)morph_count, sizeof(*morph_views));
    morph_data_objs = (PyObject **)calloc((size_t)morph_count, sizeof(*morph_data_objs));
  }
  groups = NULL;
  group_count = 0;
  invalid_group_index = 0;
  memset(&morph_build, 0, sizeof(morph_build));
  ok = 1;

  if (!positions_buf || !normals_buf || !loop_vertices_buf || !tri_loops_buf || !tri_materials_buf
      || (has_morph && (!morph_deltas || !morph_bufs || !morph_views || !morph_data_objs))) {
    PyErr_NoMemory();
    ok = 0;
    goto done_native;
  }
  if (PyObject_GetBuffer(positions_buf, &positions_view, PyBUF_SIMPLE) < 0
      || PyObject_GetBuffer(normals_buf, &normals_view, PyBUF_SIMPLE) < 0
      || PyObject_GetBuffer(loop_vertices_buf, &loop_vertices_view, PyBUF_SIMPLE) < 0
      || PyObject_GetBuffer(tri_loops_buf, &tri_loops_view, PyBUF_SIMPLE) < 0
      || PyObject_GetBuffer(tri_materials_buf, &tri_materials_view, PyBUF_SIMPLE) < 0) {
    ok = 0;
    goto done_native;
  }

  positions = (float *)positions_view.buf;
  normals = (float *)normals_view.buf;
  tangents = NULL;
  loop_vertices = (int32_t *)loop_vertices_view.buf;
  tri_loops = (int32_t *)tri_loops_view.buf;
  tri_materials = (int32_t *)tri_materials_view.buf;
  if (!positions || !normals || !loop_vertices || !tri_loops || !tri_materials) {
    PyErr_NoMemory();
    ok = 0;
    goto done_native;
  }

  group_count = (size_t)material_count_py + 1u;
  invalid_group_index = (size_t)material_count_py;
  groups = (AkbExportFastGroup *)calloc(group_count, sizeof(*groups));
  if (!groups) {
    PyErr_NoMemory();
    ok = 0;
    goto done_native;
  }
  for (size_t i = 0; i < (size_t)material_count_py; i++)
    groups[i].materialIndex = (int)i;
  groups[invalid_group_index].materialIndex = -1;

  if (has_skin) {
    if (!akb_export_skin_mapping(skin_mapping_obj, &group_to_joint, &group_to_joint_len)) {
      ok = 0;
      goto done_native;
    }
    if (!group_to_joint || group_to_joint_len <= 0) {
      PyErr_SetString(PyExc_ValueError, "skin group mapping is empty");
      ok = 0;
      goto done_native;
    }
    skin_cache = (AkbExportSkinVertexCache *)calloc((size_t)vertex_count, sizeof(*skin_cache));
    if (!skin_cache) {
      PyErr_NoMemory();
      ok = 0;
      goto done_native;
    }
  }

  for (uint32_t i = 0; i < uv_count; i++) {
    PyObject *uv_layer;

    uv_layer = PySequence_Fast_GET_ITEM(uv_layers_seq, (Py_ssize_t)i);
    uv_data_objs[i] = PyObject_GetAttrString(uv_layer, "data");
    if (!uv_data_objs[i]) {
      ok = 0;
      goto done_native;
    }
    if (PyObject_Length(uv_data_objs[i]) < loop_count) {
      PyErr_SetString(PyExc_ValueError, "uv layer is shorter than mesh loop count");
      ok = 0;
      goto done_native;
    }
    uv_bufs[i] = akb_export_array_new("f", loop_count * 2);
    if (!uv_bufs[i] || PyObject_GetBuffer(uv_bufs[i], &uv_views[i], PyBUF_SIMPLE) < 0) {
      PyErr_NoMemory();
      ok = 0;
      goto done_native;
    }
    uvs[i] = (float *)uv_views[i].buf;
    if (!uvs[i]) {
      PyErr_NoMemory();
      ok = 0;
      goto done_native;
    }
  }

  for (uint32_t i = 0; i < color_count; i++) {
    PyObject *color_layer;
    Py_ssize_t expected_count;

    color_layer = PySequence_Fast_GET_ITEM(color_layers_seq, (Py_ssize_t)i);
    if (!akb_export_fast_attr_domain(color_layer, &color_domains[i])) {
      PyErr_SetString(PyExc_ValueError, "color attribute must use POINT or CORNER domain");
      ok = 0;
      goto done_native;
    }
    expected_count = color_domains[i] == AKB_EXPORT_FAST_ATTR_CORNER ? loop_count : vertex_count;
    color_data_objs[i] = PyObject_GetAttrString(color_layer, "data");
    if (!color_data_objs[i]) {
      ok = 0;
      goto done_native;
    }
    if (PyObject_Length(color_data_objs[i]) < expected_count) {
      PyErr_SetString(PyExc_ValueError, "color attribute is shorter than its mesh domain");
      ok = 0;
      goto done_native;
    }
    color_bufs[i] = akb_export_array_new("f", expected_count * 4);
    if (!color_bufs[i] || PyObject_GetBuffer(color_bufs[i], &color_views[i], PyBUF_SIMPLE) < 0) {
      PyErr_NoMemory();
      ok = 0;
      goto done_native;
    }
    colors[i] = (float *)color_views[i].buf;
    if (!colors[i]) {
      PyErr_NoMemory();
      ok = 0;
      goto done_native;
    }
  }

  if (has_morph) {
    morph_basis_data_obj = PyObject_GetAttrString(morph_basis_obj, "data");
    if (!morph_basis_data_obj || PyObject_Length(morph_basis_data_obj) < vertex_count) {
      PyErr_SetString(PyExc_ValueError, "morph basis is shorter than mesh vertex count");
      ok = 0;
      goto done_native;
    }
    ok = akb_export_foreach_get_buffer(morph_basis_data_obj, "co", positions_buf, "f");
  } else {
    ok = akb_export_foreach_get_buffer(vertices_obj, "co", positions_buf, "f");
  }
  ok = ok
       && akb_export_foreach_get_buffer(loops_obj, "vertex_index", loop_vertices_buf, "i")
       && akb_export_foreach_get_buffer(loop_tris_obj, "loops", tri_loops_buf, "i")
       && akb_export_foreach_get_buffer(loop_tris_obj, "material_index", tri_materials_buf, "i")
       && akb_export_foreach_get_buffer(corner_normals_obj, "vector", normals_buf, "f");
  if (!ok)
    goto done_native;

  if (has_morph) {
    for (uint32_t i = 0; i < morph_count; i++) {
      PyObject *target_obj;

      target_obj = PySequence_Fast_GET_ITEM(morph_targets_seq, (Py_ssize_t)i);
      morph_data_objs[i] = PyObject_GetAttrString(target_obj, "data");
      if (!morph_data_objs[i] || PyObject_Length(morph_data_objs[i]) < vertex_count) {
        PyErr_SetString(PyExc_ValueError, "morph target is shorter than mesh vertex count");
        ok = 0;
        goto done_native;
      }
      morph_bufs[i] = akb_export_array_new("f", vertex_count * 3);
      if (!morph_bufs[i] || PyObject_GetBuffer(morph_bufs[i], &morph_views[i], PyBUF_SIMPLE) < 0) {
        PyErr_NoMemory();
        ok = 0;
        goto done_native;
      }
      morph_deltas[i] = (float *)morph_views[i].buf;
      if (!morph_deltas[i]
          || !akb_export_foreach_get_buffer(morph_data_objs[i], "co", morph_bufs[i], "f")) {
        ok = 0;
        goto done_native;
      }
      for (Py_ssize_t value_index = 0; value_index < vertex_count * 3; value_index++)
        morph_deltas[i][value_index] -= positions[value_index];
    }
  }

  for (uint32_t i = 0; i < uv_count; i++) {
    if (!akb_export_foreach_get_buffer(uv_data_objs[i], "uv", uv_bufs[i], "f")) {
      ok = 0;
      goto done_native;
    }
  }

  for (uint32_t i = 0; i < color_count; i++) {
    if (!akb_export_foreach_get_buffer(color_data_objs[i], "color", color_bufs[i], "f")) {
      ok = 0;
      goto done_native;
    }
  }

  if (!akb_export_fast_read_tangents(mesh_py,
                                     loop_count,
                                     &tangents_buf,
                                     &tangents_view,
                                     &tangents,
                                     &has_tangents)) {
    ok = 0;
    goto done_native;
  }

  for (Py_ssize_t tri_index = 0; tri_index < tri_count && ok; tri_index++) {
    AkbExportFastGroup *group;
    int material_index;

    material_index = tri_materials[tri_index];
    if (material_index >= 0 && material_index < material_count_py)
      group = &groups[material_index];
    else
      group = &groups[invalid_group_index];

    for (uint32_t corner = 0; corner < 3u; corner++) {
      int32_t  loop_index_i;
      uint32_t loop_index;
      int32_t  vertex_index_i;
      uint32_t vertex_index;
      float    normal[3];
      float    tangent[4];
      uint16_t joints[4];
      float    weights[4];
      float    uv[AKB_EXPORT_FAST_UV_MAX * 2u];
      float    color[AKB_EXPORT_FAST_COLOR_MAX * 4u];
      uint32_t out_index;

      loop_index_i = tri_loops[(size_t)tri_index * 3u + corner];
      if (loop_index_i < 0 || loop_index_i >= loop_count) {
        PyErr_SetString(PyExc_ValueError, "loop triangle references a missing mesh loop");
        ok = 0;
        break;
      }
      loop_index = (uint32_t)loop_index_i;
      vertex_index_i = loop_vertices[loop_index];
      if (vertex_index_i < 0 || vertex_index_i >= vertex_count) {
        PyErr_SetString(PyExc_ValueError, "mesh loop references a missing vertex");
        ok = 0;
        break;
      }
      vertex_index = (uint32_t)vertex_index_i;

      normal[0] = normals[(size_t)loop_index * 3u];
      normal[1] = normals[(size_t)loop_index * 3u + 1u];
      normal[2] = normals[(size_t)loop_index * 3u + 2u];
      if (normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2] <= 0.00000001f) {
        normal[0] = 0.0f;
        normal[1] = 0.0f;
        normal[2] = 1.0f;
      }

      for (uint32_t i = 0; i < uv_count; i++) {
        uv[i * 2u] = uvs[i][(size_t)loop_index * 2u];
        uv[i * 2u + 1u] = flip_uv_v
                           ? 1.0f - uvs[i][(size_t)loop_index * 2u + 1u]
                           : uvs[i][(size_t)loop_index * 2u + 1u];
      }

      if (has_tangents) {
        tangent[0] = tangents[(size_t)loop_index * 4u];
        tangent[1] = tangents[(size_t)loop_index * 4u + 1u];
        tangent[2] = tangents[(size_t)loop_index * 4u + 2u];
        tangent[3] = tangents[(size_t)loop_index * 4u + 3u];
      } else {
        tangent[0] = 0.0f;
        tangent[1] = 0.0f;
        tangent[2] = 0.0f;
        tangent[3] = 1.0f;
      }

      if (has_skin) {
        if (!akb_export_skin_cached_vertex(vertices_obj,
                                           vertex_count,
                                           vertex_index,
                                           group_to_joint,
                                           group_to_joint_len,
                                           skin_cache,
                                           joints,
                                           weights)) {
          ok = 0;
          break;
        }
      }

      for (uint32_t i = 0; i < color_count; i++) {
        size_t color_index;

        color_index = color_domains[i] == AKB_EXPORT_FAST_ATTR_CORNER
                        ? (size_t)loop_index
                        : (size_t)vertex_index;
        color[i * 4u] = akb_export_clamp01_float(colors[i][color_index * 4u]);
        color[i * 4u + 1u] = akb_export_clamp01_float(colors[i][color_index * 4u + 1u]);
        color[i * 4u + 2u] = akb_export_clamp01_float(colors[i][color_index * 4u + 2u]);
        color[i * 4u + 3u] = akb_export_clamp01_float(colors[i][color_index * 4u + 3u]);
      }

      if (!akb_export_fast_group_vertex(group,
                                        uv_count,
                                        color_count,
                                        morph_count,
                                        has_tangents,
                                        has_skin,
                                        positions,
                                        morph_deltas,
                                        vertex_index,
                                        normal,
                                        tangent,
                                        joints,
                                        weights,
                                        uv,
                                        color,
                                        &out_index)
          || !akb_export_fast_group_reserve_indices(group, group->indexCount + 1u)) {
        ok = 0;
        break;
      }
      group->indices[group->indexCount++] = out_index;
    }
  }

  if (!ok || group_count == 0)
    goto done_native;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    ok = 0;
    goto done_native;
  }

  geom = (AkGeometry *)ak_heap_calloc(heap, doc, sizeof(*geom));
  if (!geom) {
    ok = 0;
    goto done_native;
  }
  geom->name = name && name[0] ? name : NULL;
  ak_setypeid(geom, AKT_GEOMETRY);

  mesh_obj = ak_objAlloc(heap, geom, sizeof(*mesh), AK_GEOMETRY_MESH, true);
  if (!mesh_obj) {
    ok = 0;
    goto done_native;
  }
  geom->gdata = mesh_obj;
  mesh = (AkMesh *)ak_objGet(mesh_obj);
  mesh->geom = geom;
  mesh->name = name && name[0] ? name : NULL;
  if (!akb_export_apply_direct_extra(doc, geom, &mesh->extra, mesh_extra_obj)
      || !akb_export_apply_direct_extra(doc, geom, &geom->extra, geometry_extra_obj)) {
    ok = 0;
    goto done_native;
  }
  last_prim = NULL;

  if (has_morph
      && !akb_export_morph_begin(doc,
                                 &morph_build,
                                 morph_names_obj,
                                 morph_weights_obj,
                                 morph_count)) {
    ok = 0;
    goto done_native;
  }

  for (size_t group_index = 0; group_index < group_count; group_index++) {
    AkbExportFastGroup *group;
    AkMaterial *material;
    PyObject *material_obj;
    AkMeshPrimitive *prim;

    group = &groups[group_index];
    if (!group->vertexCount)
      continue;

    if (group->materialIndex >= 0
        && group->materialIndex < PySequence_Fast_GET_SIZE(materials_seq))
      material_obj = PySequence_Fast_GET_ITEM(materials_seq, group->materialIndex);
    else
      material_obj = Py_None;

    material = akb_export_material(doc, material_obj);
    if (PyErr_Occurred()) {
      ok = 0;
      goto done_native;
    }

    prim = akb_export_add_native_group_primitive(doc,
                                                 mesh_obj,
                                                 mesh,
                                                 group,
                                                 uv_count,
                                                 color_count,
                                                 has_tangents,
                                                 has_skin,
                                                 material);
    if (!prim) {
      ok = 0;
      goto done_native;
    }
    if (!akb_export_apply_direct_extra(doc, geom, &prim->extra, primitive_extra_obj)) {
      ok = 0;
      goto done_native;
    }

    if (!akb_export_apply_material_variants(doc,
                                            prim,
                                            variants_obj,
                                            group->materialIndex,
                                            materials_seq)) {
      ok = 0;
      goto done_native;
    }

    if (has_morph
        && !akb_export_morph_add_primitive_buffers(doc,
                                                   &morph_build,
                                                   group->morphs,
                                                   morph_count,
                                                   (uint32_t)group->vertexCount)) {
      ok = 0;
      goto done_native;
    }

    if (last_prim)
      last_prim->next = prim;
    else
      mesh->primitive = prim;
    last_prim = prim;
    mesh->primitiveCount++;
  }

  if (!mesh->primitive) {
    ok = 1;
    goto done_native;
  }

  AKB_LIB_APPEND(doc->lib.geometries, geom, next);
  {
    AkInstanceGeometry *instGeom;

    instGeom = ak_nodeAttachGeometry(node, geom);
    if (!instGeom) {
      ok = 0;
      goto done_native;
    }
    if (has_skin
        && !akb_export_add_skin_to_instance(doc,
                                            instGeom,
                                            mesh,
                                            skin_obj,
                                            nodes,
                                            node_count))
      ok = 0;

    if (ok && has_morph) {
      AkInstanceMorph *morpher;

      morpher = (AkInstanceMorph *)ak_heap_calloc(heap, instGeom, sizeof(*morpher));
      if (!morpher) {
        ok = 0;
        goto done_native;
      }
      ak_setypeid(morpher, AKT_MORPH_INST);
      morpher->morph = morph_build.morph;
      instGeom->morpher = morpher;

      if (morph_animation_obj != Py_None
          && !akb_export_add_morph_weight_animation(doc, morpher, morph_animation_obj))
        ok = 0;
    }
  }

  if (ok && has_morph && morph_build.primitiveCount != mesh->primitiveCount) {
    PyErr_SetString(PyExc_ValueError, "morph primitive count must match mesh primitive count");
    ok = 0;
  }

done_native:
  akb_export_fast_groups_free(groups, group_count, uv_count, color_count, morph_count);
  Py_XDECREF(morph_basis_data_obj);
  if (morph_data_objs) {
    for (uint32_t i = 0; i < morph_count; i++)
      Py_XDECREF(morph_data_objs[i]);
  }
  if (morph_views) {
    for (uint32_t i = 0; i < morph_count; i++) {
      if (morph_views[i].buf)
        PyBuffer_Release(&morph_views[i]);
    }
  }
  if (morph_bufs) {
    for (uint32_t i = 0; i < morph_count; i++)
      Py_XDECREF(morph_bufs[i]);
  }
  free(morph_data_objs);
  free(morph_views);
  free(morph_bufs);
  free(morph_deltas);
  for (uint32_t i = 0; i < uv_count; i++)
    Py_XDECREF(uv_data_objs[i]);
  for (uint32_t i = 0; i < uv_count; i++) {
    if (uv_views[i].buf)
      PyBuffer_Release(&uv_views[i]);
  }
  for (uint32_t i = 0; i < uv_count; i++)
    Py_XDECREF(uv_bufs[i]);
  for (uint32_t i = 0; i < color_count; i++)
    Py_XDECREF(color_data_objs[i]);
  for (uint32_t i = 0; i < color_count; i++) {
    if (color_views[i].buf)
      PyBuffer_Release(&color_views[i]);
  }
  for (uint32_t i = 0; i < color_count; i++)
    Py_XDECREF(color_bufs[i]);
  if (tri_materials_view.buf)
    PyBuffer_Release(&tri_materials_view);
  if (tri_loops_view.buf)
    PyBuffer_Release(&tri_loops_view);
  if (loop_vertices_view.buf)
    PyBuffer_Release(&loop_vertices_view);
  if (tangents_view.buf)
    PyBuffer_Release(&tangents_view);
  if (normals_view.buf)
    PyBuffer_Release(&normals_view);
  if (positions_view.buf)
    PyBuffer_Release(&positions_view);
  Py_XDECREF(positions_buf);
  Py_XDECREF(normals_buf);
  Py_XDECREF(tangents_buf);
  Py_XDECREF(loop_vertices_buf);
  Py_XDECREF(tri_loops_buf);
  Py_XDECREF(tri_materials_buf);
  free(skin_cache);
  free(group_to_joint);
  Py_XDECREF(morph_targets_seq);
  Py_DECREF(vertices_obj);
  Py_DECREF(loops_obj);
  Py_DECREF(loop_tris_obj);
  Py_DECREF(corner_normals_obj);
  Py_DECREF(uv_layers_seq);
  Py_DECREF(color_layers_seq);
  Py_DECREF(materials_seq);

  return ok;
}
