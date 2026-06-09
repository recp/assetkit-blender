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

static uint64_t
akb_fnv1a64_update(uint64_t hash, const void *data, size_t length) {
  const unsigned char *bytes;
  size_t i;

  if (!data || !length)
    return hash;

  bytes = (const unsigned char *)data;
  for (i = 0; i < length; i++) {
    hash ^= bytes[i];
    hash *= UINT64_C(1099511628211);
  }

  return hash;
}

static uint64_t
akb_fnv1a64_mix_u64(uint64_t hash, uint64_t value) {
  unsigned int i;

  for (i = 0; i < 8; i++) {
    hash ^= (unsigned char)((value >> (i * 8)) & 0xFFu);
    hash *= UINT64_C(1099511628211);
  }

  return hash;
}

static uint64_t
akb_fnv1a64_mix_cstr(uint64_t hash, const char *str, size_t capacity) {
  size_t length = 0;

  if (!str || !capacity)
    return akb_fnv1a64_mix_u64(hash, 0);

  while (length < capacity && str[length])
    length++;

  hash = akb_fnv1a64_mix_u64(hash, (uint64_t)length);
  return akb_fnv1a64_update(hash, str, length);
}

static uint64_t
akb_geometry_key_mix_buffer(uint64_t hash,
                            const void *data,
                            size_t length,
                            int content_key) {
  hash = akb_fnv1a64_mix_u64(hash, (uint64_t)length);
  if (!data || !length)
    return hash;
  if (content_key)
    return akb_fnv1a64_update(hash, data, length);
  return akb_fnv1a64_mix_u64(hash, (uintptr_t)data);
}

static int
akb_geometry_key_add_bytes(size_t *total, size_t bytes) {
  if (!bytes)
    return 1;
  if (*total > SIZE_MAX - bytes)
    return 0;
  *total += bytes;
  return *total <= AKB_GEOMETRY_CONTENT_KEY_BYTE_LIMIT;
}

static int
akb_geometry_key_content_allowed(const AkbPrimitive *prim) {
  size_t total = 0;
  uint32_t i;

  if (!prim)
    return 0;

  if (!akb_geometry_key_add_bytes(&total,
                                  (size_t)prim->vertex_count
                                  * 3
                                  * sizeof(float))
      || !akb_geometry_key_add_bytes(&total,
                                     (size_t)prim->loop_count
                                     * sizeof(uint32_t))
      || !akb_geometry_key_add_bytes(&total,
                                     (size_t)prim->face_count
                                     * sizeof(int32_t) * 2))
    return 0;

  if (prim->has_normals
      && !akb_geometry_key_add_bytes(&total,
                                     (size_t)prim->loop_count
                                     * 3
                                     * sizeof(float)))
    return 0;
  if (prim->has_vertex_normals
      && !akb_geometry_key_add_bytes(&total,
                                     (size_t)prim->vertex_count
                                     * 3
                                     * sizeof(float)))
    return 0;
  if (prim->has_tangents
      && !akb_geometry_key_add_bytes(&total,
                                     (size_t)prim->loop_count
                                     * 4
                                     * sizeof(float)))
    return 0;

  for (i = 0; i < prim->uv_set_count; i++) {
    if (!akb_geometry_key_add_bytes(&total,
                                    (size_t)prim->loop_count
                                    * prim->uv_sets[i].width
                                    * sizeof(float)))
      return 0;
  }

  for (i = 0; i < prim->color_set_count; i++) {
    if (!akb_geometry_key_add_bytes(&total,
                                    (size_t)prim->loop_count
                                    * prim->color_sets[i].width
                                    * sizeof(float)))
      return 0;
  }

  return 1;
}

static uint64_t
akb_geometry_key_loop_attrs(uint64_t hash,
                            const AkbLoopFloatAttribute *attrs,
                            uint32_t count,
                            uint32_t value_count,
                            int content_key) {
  uint32_t i;
  size_t length;

  hash = akb_fnv1a64_mix_u64(hash, count);
  for (i = 0; i < count; i++) {
    hash = akb_fnv1a64_mix_cstr(hash, attrs[i].name, sizeof(attrs[i].name));
    hash = akb_fnv1a64_mix_u64(hash, attrs[i].set);
    hash = akb_fnv1a64_mix_u64(hash, attrs[i].width);
    length = (size_t)value_count * attrs[i].width * sizeof(float);
    hash = akb_geometry_key_mix_buffer(hash, attrs[i].values, length, content_key);
  }

  return hash;
}

static uint64_t
akb_primitive_geometry_key(const AkbPrimitive *prim, int content_key) {
  uint64_t hash;
  size_t length;

  if (!prim
      || (prim->primitive_type != AKB_PRIMITIVE_TRIANGLES
          && prim->primitive_type != AKB_PRIMITIVE_POLYGONS)
      || !prim->vertices
      || !prim->indices
      || prim->loop_count != prim->face_count * 3
      || prim->has_skin
      || prim->has_gsplat
      || prim->instance_count
      || prim->point_attr_count
      || prim->morph_target_count
      || prim->morph_preset_count
      || prim->material_variant_count
      || (prim->animation && prim->animation->count)
      || (prim->morph_animation && prim->morph_animation->count)
      || (prim->material_animation && prim->material_animation->count))
    return 0;

  content_key = content_key && akb_geometry_key_content_allowed(prim);
  hash = UINT64_C(1469598103934665603);
  hash = akb_fnv1a64_mix_u64(hash, prim->primitive_type);
  hash = akb_fnv1a64_mix_u64(hash, prim->primitive_mode);
  hash = akb_fnv1a64_mix_u64(hash, prim->vertex_count);
  hash = akb_fnv1a64_mix_u64(hash, prim->loop_count);
  hash = akb_fnv1a64_mix_u64(hash, prim->face_count);
  length = (size_t)prim->vertex_count * 3 * sizeof(float);
  hash = akb_geometry_key_mix_buffer(hash, prim->vertices, length, content_key);
  length = (size_t)prim->loop_count * sizeof(uint32_t);
  hash = akb_geometry_key_mix_buffer(hash, prim->indices, length, content_key);
  hash = akb_fnv1a64_mix_u64(hash, prim->has_normals);
  length = prim->has_normals ? (size_t)prim->loop_count * 3 * sizeof(float) : 0;
  hash = akb_geometry_key_mix_buffer(hash, prim->normals, length, content_key);
  hash = akb_fnv1a64_mix_u64(hash, prim->has_vertex_normals);
  length = prim->has_vertex_normals ? (size_t)prim->vertex_count * 3 * sizeof(float) : 0;
  hash = akb_geometry_key_mix_buffer(hash, prim->vertex_normals, length, content_key);
  hash = akb_fnv1a64_mix_u64(hash, prim->has_tangents);
  length = prim->has_tangents ? (size_t)prim->loop_count * 4 * sizeof(float) : 0;
  hash = akb_geometry_key_mix_buffer(hash, prim->tangents, length, content_key);
  hash = akb_geometry_key_loop_attrs(hash,
                                     prim->uv_sets,
                                     prim->uv_set_count,
                                     prim->loop_count,
                                     content_key);
  hash = akb_geometry_key_loop_attrs(hash,
                                     prim->color_sets,
                                     prim->color_set_count,
                                     prim->loop_count,
                                     content_key);

  return hash ? hash : UINT64_C(1);
}

static uint64_t
akb_edge_key(uint32_t a, uint32_t b) {
  uint32_t lo;
  uint32_t hi;

  if (a < b) {
    lo = a;
    hi = b;
  } else {
    lo = b;
    hi = a;
  }

  return ((uint64_t)lo << 32) | (uint64_t)hi;
}

static int
akb_edge_key_cmp(const void *a, const void *b) {
  uint64_t av = *(const uint64_t *)a;
  uint64_t bv = *(const uint64_t *)b;

  return (av > bv) - (av < bv);
}

static void
akb_build_triangle_edges(AkbArena *arena, AkbPrimitive *prim) {
  uint64_t keys[AKB_EDGE_BUILD_FACE_LIMIT * 3];
  uint64_t previous;
  uint64_t key;
  size_t count = 0;
  size_t unique_count = 0;
  size_t i;
  size_t out_index;
  uint32_t a, b, c;

  if (!prim
      || prim->primitive_type != AKB_PRIMITIVE_TRIANGLES
      || !prim->indices
      || !prim->face_count
      || prim->face_count > AKB_EDGE_BUILD_FACE_LIMIT
      || prim->loop_count < prim->face_count * 3)
    return;

  for (i = 0; i < (size_t)prim->face_count; i++) {
    a = prim->indices[i * 3 + 0];
    b = prim->indices[i * 3 + 1];
    c = prim->indices[i * 3 + 2];

    if (a != b)
      keys[count++] = akb_edge_key(a, b);
    if (b != c)
      keys[count++] = akb_edge_key(b, c);
    if (c != a)
      keys[count++] = akb_edge_key(c, a);
  }

  if (!count) {
    return;
  }

  qsort(keys, count, sizeof(*keys), akb_edge_key_cmp);
  previous = UINT64_MAX;
  for (i = 0; i < count; i++) {
    if (keys[i] != previous) {
      unique_count++;
      previous = keys[i];
    }
  }

  if (!unique_count || unique_count > UINT32_MAX) {
    return;
  }

  prim->edges = (uint32_t *)akb_owned_alloc(arena,
                                            unique_count * 2 * sizeof(uint32_t),
                                            sizeof(uint32_t),
                                            &prim->arena_edges);
  if (!prim->edges) {
    return;
  }

  out_index = 0;
  previous = UINT64_MAX;
  for (i = 0; i < count; i++) {
    key = keys[i];
    if (key == previous)
      continue;
    prim->edges[out_index * 2 + 0] = (uint32_t)(key >> 32);
    prim->edges[out_index * 2 + 1] = (uint32_t)(key & UINT32_C(0xFFFFFFFF));
    out_index++;
    previous = key;
  }

  prim->edge_count = (uint32_t)out_index;
}

static size_t
akb_hash_capacity_for(size_t count) {
  size_t cap;

  if (!count || count > (SIZE_MAX / 4))
    return 0;

  cap = 64;
  while (cap < count * 2) {
    if (cap > SIZE_MAX / 2)
      return 0;
    cap <<= 1;
  }
  return cap;
}

static uint32_t
akb_stl_float_bits(float value) {
  uint32_t bits;

  memcpy(&bits, &value, sizeof(bits));
  return bits;
}

static uint32_t
akb_stl_rotl32(uint32_t value, unsigned shift) {
  return (value << shift) | (value >> (32u - shift));
}

static uint32_t
akb_stl_hash3_u32(uint32_t a, uint32_t b, uint32_t c) {
  uint32_t value;

  value = a ^ akb_stl_rotl32(b, 11u) ^ akb_stl_rotl32(c, 22u);
  value ^= value >> 16;
  return value;
}

static uint32_t
akb_stl_position_hash(const float *pos) {
  return akb_stl_hash3_u32(akb_stl_float_bits(pos[0]),
                           akb_stl_float_bits(pos[1]),
                           akb_stl_float_bits(pos[2]));
}

static int
akb_stl_position_equal(const float *a, const float *b) {
  return memcmp(a, b, sizeof(float) * 3) == 0;
}

static int
akb_stl_position_intern(float *vertices,
                        uint32_t *table,
                        size_t table_cap,
                        uint32_t *count,
                        const float *pos,
                        uint32_t *index_out) {
  uint32_t hash;
  size_t mask, slot;
  uint32_t packed, index;

  hash = akb_stl_position_hash(pos);
  mask = table_cap - 1;
  slot = (size_t)hash & mask;
  for (;;) {
    packed = table[slot];
    if (!packed) {
      index = (*count)++;
      vertices[(size_t)index * 3 + 0] = pos[0];
      vertices[(size_t)index * 3 + 1] = pos[1];
      vertices[(size_t)index * 3 + 2] = pos[2];
      table[slot] = index + 1;
      *index_out = index;
      return 1;
    }

    index = packed - 1;
    if (akb_stl_position_equal(vertices + (size_t)index * 3, pos)) {
      *index_out = index;
      return 1;
    }
    slot = (slot + 1) & mask;
  }
}

static void
akb_stl_sort_triangle(uint32_t key[3]) {
  uint32_t tmp;

  if (key[0] > key[1]) {
    tmp = key[0];
    key[0] = key[1];
    key[1] = tmp;
  }
  if (key[1] > key[2]) {
    tmp = key[1];
    key[1] = key[2];
    key[2] = tmp;
  }
  if (key[0] > key[1]) {
    tmp = key[0];
    key[0] = key[1];
    key[1] = tmp;
  }
}

static uint32_t
akb_stl_triangle_hash(const uint32_t key[3]) {
  return akb_stl_hash3_u32(key[0], key[1], key[2]);
}

static int
akb_stl_triangle_key_equal(const uint32_t *keys, uint32_t index, const uint32_t key[3]) {
  const uint32_t *stored = keys + (size_t)index * 3;

  return stored[0] == key[0] && stored[1] == key[1] && stored[2] == key[2];
}

static int
akb_stl_triangle_seen(uint32_t *table,
                      uint32_t *keys,
                      size_t table_cap,
                      uint32_t *count,
                      const uint32_t key[3]) {
  uint32_t hash;
  size_t mask, slot;
  uint32_t packed, index;

  hash = akb_stl_triangle_hash(key);
  mask = table_cap - 1;
  slot = (size_t)hash & mask;
  for (;;) {
    packed = table[slot];
    if (!packed) {
      index = (*count)++;
      keys[(size_t)index * 3 + 0] = key[0];
      keys[(size_t)index * 3 + 1] = key[1];
      keys[(size_t)index * 3 + 2] = key[2];
      table[slot] = index + 1;
      return 0;
    }

    index = packed - 1;
    if (akb_stl_triangle_key_equal(keys, index, key))
      return 1;
    slot = (slot + 1) & mask;
  }
}

static int
akb_stl_compact_loop_float(float **values_io,
                           uint8_t *borrowed_io,
                           const uint32_t *loop_remap,
                           uint32_t loop_count,
                           uint32_t width) {
  float *old_values, *new_values;
  uint32_t i;

  if (!values_io || !*values_io || !loop_remap || !loop_count || !width)
    return 1;

  old_values = *values_io;
  new_values = (float *)malloc((size_t)loop_count * width * sizeof(*new_values));
  if (!new_values)
    return 0;

  for (i = 0; i < loop_count; i++) {
    memcpy(new_values + (size_t)i * width,
           old_values + (size_t)loop_remap[i] * width,
           (size_t)width * sizeof(*new_values));
  }

  if (!borrowed_io || !*borrowed_io)
    free(old_values);
  *values_io = new_values;
  if (borrowed_io)
    *borrowed_io = 0;
  return 1;
}

static int
akb_stl_compact_loop_attrs(AkbLoopFloatAttribute *attrs,
                           uint32_t count,
                           const uint32_t *loop_remap,
                           uint32_t loop_count) {
  uint32_t i;

  for (i = 0; i < count; i++) {
    if (!akb_stl_compact_loop_float(&attrs[i].values,
                                    &attrs[i].borrowed,
                                    loop_remap,
                                    loop_count,
                                    attrs[i].width))
      return 0;
  }
  return 1;
}

static void
akb_stl_drop_vertex_normals(AkbPrimitive *prim) {
  if (!prim || !prim->vertex_normals)
    return;
  if (!prim->borrowed_vertex_normals)
    free(prim->vertex_normals);
  prim->vertex_normals = NULL;
  prim->borrowed_vertex_normals = 0;
  prim->has_vertex_normals = 0;
}

static int
akb_stl_needs_loop_remap(const AkbPrimitive *prim) {
  return prim
         && (prim->normals
             || prim->tangents
             || prim->uv_set_count
             || prim->color_set_count);
}

static int
akb_stl_already_position_indexed(const AkbPrimitive *prim) {
  return prim
         && prim->file_type == AK_FILE_TYPE_STL
         && prim->primitive_type == AKB_PRIMITIVE_TRIANGLES
         && prim->vertices
         && prim->indices
         && prim->vertex_count
         && prim->loop_count
         && prim->face_count
         && prim->loop_count == prim->face_count * 3
         && prim->vertex_count < prim->loop_count
         && !prim->normals
         && !prim->vertex_normals
         && !prim->tangents
         && !prim->uv_set_count
         && !prim->color_set_count;
}

static int
akb_optimize_stl_triangle_mesh(AkbPrimitive *prim) {
  float *vertices;
  uint32_t *indices;
  uint32_t *vertex_table;
  uint32_t *triangle_table;
  uint32_t *triangle_keys;
  uint32_t *loop_remap;
  size_t vertex_table_cap, triangle_table_cap;
  uint32_t old_vertex_count, old_loop_count, old_face_count;
  uint32_t vertex_count, loop_count, triangle_count;
  uint32_t face_index, corner;
  int need_loop_remap;
  int profile;
  double started_at, alloc_at, scan_at, compact_at;

  if (!prim
      || prim->file_type != AK_FILE_TYPE_STL
      || prim->primitive_type != AKB_PRIMITIVE_TRIANGLES
      || !prim->vertices
      || !prim->indices
      || !prim->vertex_count
      || !prim->loop_count
      || !prim->face_count
      || prim->loop_count != prim->face_count * 3)
    return 1;

  if (akb_stl_already_position_indexed(prim))
    return 1;

  old_vertex_count = prim->vertex_count;
  old_loop_count = prim->loop_count;
  old_face_count = prim->face_count;
  vertex_table_cap = akb_hash_capacity_for(old_loop_count);
  triangle_table_cap = akb_hash_capacity_for(old_face_count);
  if (!vertex_table_cap || !triangle_table_cap)
    return 1;

  need_loop_remap = akb_stl_needs_loop_remap(prim);
  profile = akb_profile_enabled();
  started_at = profile ? akb_now_ms() : 0.0;
  vertices = (float *)malloc((size_t)old_vertex_count * 3 * sizeof(*vertices));
  indices = (uint32_t *)malloc((size_t)old_loop_count * sizeof(*indices));
  vertex_table = (uint32_t *)calloc(vertex_table_cap, sizeof(*vertex_table));
  triangle_table = (uint32_t *)calloc(triangle_table_cap, sizeof(*triangle_table));
  triangle_keys = (uint32_t *)malloc((size_t)old_face_count * 3 * sizeof(*triangle_keys));
  loop_remap = need_loop_remap
                 ? (uint32_t *)malloc((size_t)old_loop_count * sizeof(*loop_remap))
                 : NULL;
  if (!vertices
      || !indices
      || !vertex_table
      || !triangle_table
      || !triangle_keys
      || (need_loop_remap && !loop_remap)) {
    free(vertices);
    free(indices);
    free(vertex_table);
    free(triangle_table);
    free(triangle_keys);
    free(loop_remap);
    return 1;
  }
  alloc_at = profile ? akb_now_ms() : 0.0;

  vertex_count = 0;
  loop_count = 0;
  triangle_count = 0;
  for (face_index = 0; face_index < old_face_count; face_index++) {
    uint32_t new_indices[3];
    uint32_t triangle_key[3];

    for (corner = 0; corner < 3; corner++) {
      uint32_t src_loop = face_index * 3 + corner;
      uint32_t src_index = prim->indices[src_loop];
      const float *pos;

      if (src_index >= old_vertex_count) {
        free(vertices);
        free(indices);
        free(vertex_table);
        free(triangle_table);
        free(triangle_keys);
        free(loop_remap);
        return 1;
      }

      pos = prim->vertices + (size_t)src_index * 3;
      if (!akb_stl_position_intern(vertices,
                                   vertex_table,
                                   vertex_table_cap,
                                   &vertex_count,
                                   pos,
                                   &new_indices[corner])) {
        free(vertices);
        free(indices);
        free(vertex_table);
        free(triangle_table);
        free(triangle_keys);
        free(loop_remap);
        return 1;
      }
    }

    if (new_indices[0] == new_indices[1]
        || new_indices[0] == new_indices[2]
        || new_indices[1] == new_indices[2])
      continue;

    triangle_key[0] = new_indices[0];
    triangle_key[1] = new_indices[1];
    triangle_key[2] = new_indices[2];
    akb_stl_sort_triangle(triangle_key);
    if (akb_stl_triangle_seen(triangle_table,
                              triangle_keys,
                              triangle_table_cap,
                              &triangle_count,
                              triangle_key))
      continue;

    for (corner = 0; corner < 3; corner++) {
      indices[loop_count] = new_indices[corner];
      if (loop_remap)
        loop_remap[loop_count] = face_index * 3 + corner;
      loop_count++;
    }
  }
  scan_at = profile ? akb_now_ms() : 0.0;

  free(vertex_table);
  free(triangle_table);
  free(triangle_keys);

  if (!loop_count || !vertex_count) {
    free(vertices);
    free(indices);
    free(loop_remap);
    return 1;
  }

  if (loop_remap && loop_count != old_loop_count) {
    if (!akb_stl_compact_loop_float(&prim->normals,
                                    &prim->borrowed_normals,
                                    loop_remap,
                                    loop_count,
                                    3)
        || !akb_stl_compact_loop_float(&prim->tangents,
                                       &prim->borrowed_tangents,
                                       loop_remap,
                                       loop_count,
                                       4)
        || !akb_stl_compact_loop_attrs(prim->uv_sets,
                                       prim->uv_set_count,
                                       loop_remap,
                                       loop_count)
        || !akb_stl_compact_loop_attrs(prim->color_sets,
                                       prim->color_set_count,
                                       loop_remap,
                                       loop_count)) {
      free(vertices);
      free(indices);
      free(loop_remap);
      return 0;
    }
    if (prim->uv_set_count)
      prim->uvs = prim->uv_sets[0].values;
    if (prim->color_set_count)
      prim->colors = prim->color_sets[0].values;
  }
  compact_at = profile ? akb_now_ms() : 0.0;

  free(loop_remap);

  if (!prim->borrowed_vertices && !prim->arena_vertices)
    free(prim->vertices);
  if (!prim->borrowed_indices && !prim->arena_indices)
    free(prim->indices);

  prim->vertices = vertices;
  prim->indices = indices;
  prim->vertex_count = vertex_count;
  prim->loop_count = loop_count;
  prim->face_count = loop_count / 3;
  prim->borrowed_vertices = 0;
  prim->borrowed_indices = 0;
  prim->arena_vertices = 0;
  prim->arena_indices = 0;
  prim->zero_copy_flags &= (uint8_t)~3u;
  akb_stl_drop_vertex_normals(prim);
  if (profile) {
    akb_profile_log("stl_position_dedup old_vertices=%u old_faces=%u old_loops=%u vertices=%u faces=%u loops=%u alloc=%.3fms scan=%.3fms compact=%.3fms total=%.3fms loop_remap=%d",
                    old_vertex_count,
                    old_face_count,
                    old_loop_count,
                    vertex_count,
                    prim->face_count,
                    loop_count,
                    alloc_at - started_at,
                    scan_at - alloc_at,
                    compact_at - scan_at,
                    akb_now_ms() - started_at,
                    need_loop_remap);
  }
  return 1;
}

static int
akb_optimize_obj_position_mesh(AkbPrimitive *prim) {
  float *vertices;
  float *loop_normals;
  uint32_t *indices;
  uint32_t *vertex_table;
  size_t vertex_table_cap;
  uint32_t old_vertex_count, old_loop_count;
  uint32_t vertex_count;
  uint32_t loop_index;
  int make_loop_normals;
  int profile;
  double started_at, alloc_at, scan_at;

  if (!prim
      || prim->file_type != AK_FILE_TYPE_WAVEFRONT
      || (prim->primitive_type != AKB_PRIMITIVE_TRIANGLES
          && prim->primitive_type != AKB_PRIMITIVE_POLYGONS)
      || !prim->vertices
      || !prim->indices
      || !prim->vertex_count
      || !prim->loop_count
      || !prim->face_count
      || prim->point_attr_count
      || prim->has_skin
      || prim->morph_target_count)
    return 1;

  old_vertex_count = prim->vertex_count;
  old_loop_count = prim->loop_count;
  vertex_table_cap = akb_hash_capacity_for(old_loop_count);
  if (!vertex_table_cap)
    return 1;

  make_loop_normals = prim->has_vertex_normals
                      && prim->vertex_normals
                      && !prim->has_normals;
  profile = akb_profile_enabled();
  started_at = profile ? akb_now_ms() : 0.0;

  vertices = (float *)malloc((size_t)old_vertex_count * 3 * sizeof(*vertices));
  indices = (uint32_t *)malloc((size_t)old_loop_count * sizeof(*indices));
  vertex_table = (uint32_t *)calloc(vertex_table_cap, sizeof(*vertex_table));
  loop_normals = make_loop_normals
                   ? (float *)malloc((size_t)old_loop_count * 3 * sizeof(*loop_normals))
                   : NULL;
  if (!vertices
      || !indices
      || !vertex_table
      || (make_loop_normals && !loop_normals)) {
    free(vertices);
    free(indices);
    free(vertex_table);
    free(loop_normals);
    return 1;
  }
  alloc_at = profile ? akb_now_ms() : 0.0;

  vertex_count = 0;
  for (loop_index = 0; loop_index < old_loop_count; loop_index++) {
    uint32_t src_index;
    const float *pos;
    uint32_t new_index;

    src_index = prim->indices[loop_index];
    if (src_index >= old_vertex_count) {
      free(vertices);
      free(indices);
      free(vertex_table);
      free(loop_normals);
      return 1;
    }

    pos = prim->vertices + (size_t)src_index * 3;
    if (!akb_stl_position_intern(vertices,
                                 vertex_table,
                                 vertex_table_cap,
                                 &vertex_count,
                                 pos,
                                 &new_index)) {
      free(vertices);
      free(indices);
      free(vertex_table);
      free(loop_normals);
      return 1;
    }
    indices[loop_index] = new_index;

    if (loop_normals) {
      memcpy(loop_normals + (size_t)loop_index * 3,
             prim->vertex_normals + (size_t)src_index * 3,
             sizeof(*loop_normals) * 3);
    }
  }
  scan_at = profile ? akb_now_ms() : 0.0;

  free(vertex_table);
  if (vertex_count >= old_vertex_count) {
    free(vertices);
    free(indices);
    if (loop_normals) {
      if (prim->normals && !prim->borrowed_normals)
        free(prim->normals);
      prim->normals = loop_normals;
      prim->has_normals = 1;
      prim->borrowed_normals = 0;
      akb_stl_drop_vertex_normals(prim);
      if (profile) {
        akb_profile_log("obj_loop_normals vertices=%u faces=%u loops=%u total=%.3fms",
                        old_vertex_count,
                        prim->face_count,
                        prim->loop_count,
                        akb_now_ms() - started_at);
      }
    } else {
      free(loop_normals);
    }
    return 1;
  }

  if (!prim->borrowed_vertices && !prim->arena_vertices)
    free(prim->vertices);
  if (!prim->borrowed_indices && !prim->arena_indices)
    free(prim->indices);

  prim->vertices = vertices;
  prim->indices = indices;
  prim->vertex_count = vertex_count;
  prim->borrowed_vertices = 0;
  prim->borrowed_indices = 0;
  prim->arena_vertices = 0;
  prim->arena_indices = 0;
  prim->zero_copy_flags &= (uint8_t)~3u;

  if (loop_normals) {
    if (prim->normals && !prim->borrowed_normals)
      free(prim->normals);
    prim->normals = loop_normals;
    prim->has_normals = 1;
    prim->borrowed_normals = 0;
    akb_stl_drop_vertex_normals(prim);
  }

  if (profile) {
    akb_profile_log("obj_position_dedup old_vertices=%u vertices=%u faces=%u loops=%u alloc=%.3fms scan=%.3fms total=%.3fms loop_normals=%d",
                    old_vertex_count,
                    vertex_count,
                    prim->face_count,
                    prim->loop_count,
                    alloc_at - started_at,
                    scan_at - alloc_at,
                    akb_now_ms() - started_at,
                    make_loop_normals);
  }
  return 1;
}

static void
akb_finalize_primitive_buffers(AkbArena *arena,
                               AkbPrimitive *prim,
                               const AkbLoadOptions *options) {
  if (!prim)
    return;

  akb_optimize_stl_triangle_mesh(prim);
  akb_optimize_obj_position_mesh(prim);

  if (!options || options->build_triangle_edges)
    akb_build_triangle_edges(arena, prim);
  if (!options || options->geometry_keys)
    prim->geometry_key = akb_primitive_geometry_key(prim,
                                                   options
                                                   ? options->geometry_content_keys
                                                   : 0);
}

