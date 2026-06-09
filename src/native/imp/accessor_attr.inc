static int
akb_index_view_init(AkMeshPrimitive *prim, AkbIndexView *view) {
  AkAccessor *acc;
  AkIndexArray *indices;
  size_t item_size;
  size_t stride;
  const uint8_t *data;

  if (!view)
    return 0;

  memset(view, 0, sizeof(*view));
  if (!prim)
    return 0;

  indices = prim->indices;
  if (indices && indices->count) {
    item_size = ak_indexComponentSize(indices->componentType);
    if (!item_size)
      return 0;

    view->data = indices->items;
    view->count = indices->count;
    view->item_stride = item_size;
    view->component_type = indices->componentType;
    view->borrowable_u32 = indices->componentType == AKT_UINT;
    return 1;
  }

  acc = prim->indexAccessor;
  if (!acc || !acc->buffer || !acc->buffer->data || acc->count == 0)
    return 0;

  item_size = ak_indexComponentSize(acc->componentType);
  if (!item_size)
    return 0;

  stride = acc->byteStride ? acc->byteStride : acc->bytesPerComponent;
  if (stride < item_size)
    return 0;
  if (acc->byteOffset > acc->buffer->length
      || (size_t)acc->count > (SIZE_MAX - item_size) / stride
      || acc->byteOffset + ((size_t)acc->count - 1) * stride + item_size
         > acc->buffer->length)
    return 0;

  data = (const uint8_t *)acc->buffer->data + acc->byteOffset;
  view->data = data;
  view->count = acc->count;
  view->item_stride = stride;
  view->component_type = acc->componentType;
  view->borrowable_u32 = acc->componentType == AKT_UINT
                         && stride == sizeof(uint32_t)
                         && ((uintptr_t)data % sizeof(uint32_t)) == 0;
  return 1;
}

static const uint32_t *
akb_index_view_u32_ptr(const AkbIndexView *view) {
  if (!view
      || !view->data
      || !view->borrowable_u32
      || view->component_type != AKT_UINT
      || view->item_stride != sizeof(uint32_t))
    return NULL;

  return (const uint32_t *)view->data;
}

static inline uint32_t
akb_index_view_get(const AkbIndexView *view, size_t index) {
  const uint8_t *ptr;
  uint16_t u16;
  uint32_t u32;

  if (!view || !view->data || index >= view->count)
    return 0;

  ptr = (const uint8_t *)view->data + index * view->item_stride;
  switch (view->component_type) {
    case AKT_UBYTE:
      return *ptr;
    case AKT_USHORT:
      memcpy(&u16, ptr, sizeof(u16));
      return u16;
    case AKT_UINT:
      memcpy(&u32, ptr, sizeof(u32));
      return u32;
    default:
      return 0;
  }
}

static int
akb_index_view_copy_u32(const AkbIndexView *view,
                        uint32_t *dst,
                        uint32_t loop_count,
                        uint32_t index_stride,
                        uint32_t index_offset,
                        uint32_t addend) {
  const uint8_t *src8;
  const uint16_t *src16;
  const uint32_t *src32;
  size_t src_index;
  size_t i;
  uint16_t u16;
  uint32_t u32;

  if (!view || !view->data || !dst || index_stride == 0 || index_offset >= index_stride)
    return 0;

  if ((size_t)loop_count > (SIZE_MAX - index_offset) / index_stride)
    return 0;
  if ((size_t)(loop_count ? loop_count - 1 : 0) * index_stride + index_offset
      >= view->count)
    return 0;

  if (view->component_type == AKT_UBYTE && view->item_stride == sizeof(uint8_t)) {
    src8 = (const uint8_t *)view->data + index_offset;
    for (i = 0; i < loop_count; i++)
      dst[i] = (uint32_t)src8[i * index_stride] + addend;
    return 1;
  }

  if (view->component_type == AKT_USHORT
      && view->item_stride == sizeof(uint16_t)
      && ((uintptr_t)view->data % sizeof(uint16_t)) == 0) {
    src16 = (const uint16_t *)view->data + index_offset;
    for (i = 0; i < loop_count; i++)
      dst[i] = (uint32_t)src16[i * index_stride] + addend;
    return 1;
  }

  if (view->component_type == AKT_UINT
      && view->item_stride == sizeof(uint32_t)
      && ((uintptr_t)view->data % sizeof(uint32_t)) == 0) {
    src32 = (const uint32_t *)view->data + index_offset;
    for (i = 0; i < loop_count; i++)
      dst[i] = src32[i * index_stride] + addend;
    return 1;
  }

  switch (view->component_type) {
    case AKT_UBYTE:
      for (i = 0; i < loop_count; i++) {
        src_index = i * index_stride + index_offset;
        dst[i] = (uint32_t)*((const uint8_t *)view->data
                             + src_index * view->item_stride)
                 + addend;
      }
      return 1;
    case AKT_USHORT:
      for (i = 0; i < loop_count; i++) {
        src_index = i * index_stride + index_offset;
        memcpy(&u16,
               (const uint8_t *)view->data + src_index * view->item_stride,
               sizeof(u16));
        dst[i] = (uint32_t)u16 + addend;
      }
      return 1;
    case AKT_UINT:
      for (i = 0; i < loop_count; i++) {
        src_index = i * index_stride + index_offset;
        memcpy(&u32,
               (const uint8_t *)view->data + src_index * view->item_stride,
               sizeof(u32));
        dst[i] = u32 + addend;
      }
      return 1;
    default:
      return 0;
  }
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
akb_accessor_float_copy_with_default(AkAccessor *acc,
                                     uint32_t width,
                                     float missing_default,
                                     uint32_t *count_out) {
  float *out;
  float *tmp;
  size_t total;
  size_t written;
  uint32_t comp_count, copy_count, i, j;

  *count_out = 0;
  if (!acc || acc->count == 0)
    return NULL;

  comp_count = acc->componentCount ? acc->componentCount : width;
  total = (size_t)acc->count * width;
  out = (float *)malloc(total * sizeof(float));
  if (!out)
    return NULL;

  if (acc->buffer
      && acc->buffer->data
      && acc->componentType == AKT_FLOAT
      && !acc->normalized
      && acc->bytesPerComponent == sizeof(float)
      && acc->fillByteSize >= (size_t)comp_count * sizeof(float)) {
    size_t stride;
    size_t copy_bytes;
    char *src;

    copy_count = comp_count < width ? comp_count : width;
    copy_bytes = (size_t)copy_count * sizeof(float);
    stride = acc->byteStride ? acc->byteStride : acc->fillByteSize;
    if (copy_bytes > 0
        && stride >= (size_t)comp_count * sizeof(float)
        && acc->byteOffset + (size_t)(acc->count - 1) * stride + copy_bytes
           <= acc->buffer->length) {
      src = (char *)acc->buffer->data + acc->byteOffset;
      if (copy_count == width && stride == copy_bytes) {
        memcpy(out, src, total * sizeof(float));
      } else {
        for (i = 0; i < acc->count; i++) {
          memcpy(out + (size_t)i * width, src + (size_t)i * stride, copy_bytes);
          for (j = copy_count; j < width; j++)
            out[(size_t)i * width + j] = missing_default;
        }
      }
      *count_out = acc->count;
      return out;
    }
  }

  if (comp_count == width) {
    written = ak_accessorAsFloat(acc, out, total);
    if (written == 0) {
      free(out);
      return NULL;
    }
    *count_out = acc->count;
    return out;
  }

  tmp = (float *)malloc((size_t)acc->count * comp_count * sizeof(float));
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

  copy_count = comp_count < width ? comp_count : width;
  for (i = 0; i < acc->count; i++) {
    memcpy(out + (size_t)i * width,
           tmp + (size_t)i * comp_count,
           (size_t)copy_count * sizeof(float));
    for (j = copy_count; j < width; j++)
      out[(size_t)i * width + j] = missing_default;
  }

  free(tmp);
  *count_out = acc->count;
  return out;
}

static float *
akb_accessor_float_copy(AkAccessor *acc, uint32_t width, uint32_t *count_out) {
  return akb_accessor_float_copy_with_default(acc, width, 0.0f, count_out);
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
akb_extract_instancing(AkbArena *arena, AkbPrimitive *out, AkNode *node) {
  AkGpuInstancing *instancing;
  float *translations = NULL;
  float *rotations = NULL;
  float *scales = NULL;
  uint32_t i;
  uint8_t borrowed_translations = 0;
  uint8_t borrowed_rotations = 0;
  uint8_t borrowed_scales = 0;

  if (!node || !node->gpuInstancing || node->gpuInstancing->count == 0)
    return 1;

  instancing = node->gpuInstancing;
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

  out->instance_matrices = (float *)akb_owned_alloc(arena,
                                                    (size_t)instancing->count
                                                    * 16
                                                    * sizeof(float),
                                                    sizeof(float),
                                                    &out->arena_instance_matrices);
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
akb_loop_attribute_copy(AkbArena *arena,
                        AkMeshPrimitive *prim,
                        AkInput *input,
                        const AkbIndexView *index_view,
                        const uint32_t *vertex_indices,
                        uint32_t loop_count,
                        uint32_t width,
                        int flip_v,
                        uint8_t *has_attr,
                        uint8_t *arena_values) {
  float *values, *out;
  uint32_t value_count = 0;
  uint32_t stride, offset, i, j, idx;
  size_t src_index;
  uint8_t borrowed_values = 0;

  *has_attr = 0;
  if (arena_values)
    *arena_values = 0;
  if (!input || !input->accessor || loop_count == 0)
    return NULL;

  values = akb_accessor_float_borrow(input->accessor, width, &value_count);
  if (values) {
    if (value_count == loop_count && (!flip_v || width < 2)) {
      if (arena_values)
        *arena_values = 1;
      *has_attr = 1;
      return values;
    }
    if (value_count != loop_count) {
      borrowed_values = 1;
    } else {
      values = akb_accessor_float_copy(input->accessor, width, &value_count);
    }
  } else {
    values = akb_accessor_float_copy(input->accessor, width, &value_count);
  }
  if (!values || value_count == 0) {
    if (!borrowed_values)
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

  out = (float *)akb_owned_alloc(arena,
                                 (size_t)loop_count * width * sizeof(float),
                                 sizeof(float),
                                 arena_values);
  if (!out) {
    if (!borrowed_values)
      free(values);
    return NULL;
  }

  stride = prim->indexStride ? prim->indexStride : 1;
  offset = input->indexOffset;

#define AKB_LOOP_ATTR_INDEX(LOOP_INDEX)                                  \
  do {                                                                   \
    src_index = (size_t)(LOOP_INDEX) * stride + offset;                  \
    idx = index_view && src_index < index_view->count                    \
          ? akb_index_view_get(index_view, src_index)                    \
          : vertex_indices[LOOP_INDEX];                                  \
  } while (0)

  if (width == 2) {
    float *dst;
    const float *src;

    for (i = 0; i < loop_count; i++) {
      AKB_LOOP_ATTR_INDEX(i);
      dst = out + (size_t)i * 2;
      if (idx >= value_count) {
        dst[0] = 0.0f;
        dst[1] = 0.0f;
        continue;
      }
      src = values + (size_t)idx * 2;
      dst[0] = src[0];
      dst[1] = flip_v ? 1.0f - src[1] : src[1];
    }
  } else if (width == 3) {
    float *dst;
    const float *src;

    for (i = 0; i < loop_count; i++) {
      AKB_LOOP_ATTR_INDEX(i);
      dst = out + (size_t)i * 3;
      if (idx >= value_count) {
        dst[0] = 0.0f;
        dst[1] = 0.0f;
        dst[2] = 0.0f;
        continue;
      }
      src = values + (size_t)idx * 3;
      dst[0] = src[0];
      dst[1] = src[1];
      dst[2] = src[2];
    }
  } else if (width == 4) {
    float *dst;
    const float *src;

    for (i = 0; i < loop_count; i++) {
      AKB_LOOP_ATTR_INDEX(i);
      dst = out + (size_t)i * 4;
      if (idx >= value_count) {
        dst[0] = 0.0f;
        dst[1] = 0.0f;
        dst[2] = 0.0f;
        dst[3] = 0.0f;
        continue;
      }
      src = values + (size_t)idx * 4;
      dst[0] = src[0];
      dst[1] = src[1];
      dst[2] = src[2];
      dst[3] = src[3];
    }
  } else {
    for (i = 0; i < loop_count; i++) {
      AKB_LOOP_ATTR_INDEX(i);
      if (idx >= value_count) {
        for (j = 0; j < width; j++)
          out[(size_t)i * width + j] = 0.0f;
        continue;
      }

      for (j = 0; j < width; j++)
        out[(size_t)i * width + j] = values[(size_t)idx * width + j];

      if (flip_v && width >= 2)
        out[(size_t)i * width + 1] = 1.0f - out[(size_t)i * width + 1];
    }
  }

#undef AKB_LOOP_ATTR_INDEX

  if (!borrowed_values)
    free(values);
  *has_attr = 1;
  return out;
}

static void
akb_try_extract_vertex_normals(AkbPrimitive *out,
                               AkInput *normal_input,
                               AkInput *pos_input,
                               AkbSharedDoc *doc_owner,
                               const AkNode *node) {
  uint32_t normal_count = 0;

  if (!out
      || !normal_input
      || !normal_input->accessor
      || !pos_input
      || !pos_input->accessor
      || (node && node->geometry && node->geometry->skinner))
    return;

  if (normal_input->indexOffset != pos_input->indexOffset)
    return;

  out->vertex_normals = akb_accessor_float_borrow(normal_input->accessor,
                                                  3,
                                                  &normal_count);
  if (out->vertex_normals) {
    out->borrowed_vertex_normals = 1;
    out->zero_copy_flags |= 4;
    akb_primitive_retain_doc(out, doc_owner);
  } else {
    out->vertex_normals = akb_accessor_float_copy(normal_input->accessor,
                                                  3,
                                                  &normal_count);
  }

  if (!out->vertex_normals)
    return;

  if (normal_count == out->vertex_count) {
    out->has_vertex_normals = 1;
    return;
  }

  if (!out->borrowed_vertex_normals)
    free(out->vertex_normals);
  out->vertex_normals = NULL;
  out->borrowed_vertex_normals = 0;
  out->zero_copy_flags &= (uint8_t)~4u;
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

static int
akb_raw_semantic_starts_with(AkInput *input, const char *prefix);

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

static float
akb_unit_clamp(float value) {
  if (value < 0.0f)
    return 0.0f;
  if (value > 1.0f)
    return 1.0f;
  return value;
}

static float
akb_color_normalize_factor(AkAccessor *acc) {
  AkTypeId source_type;

  if (!acc || acc->normalized || acc->originallyNormalized)
    return 1.0f;

  source_type = acc->originalComponentType
                  ? acc->originalComponentType
                  : acc->componentType;
  switch (source_type) {
    case AKT_UBYTE:
      return 1.0f / 255.0f;
    case AKT_BYTE:
      return 1.0f / 127.0f;
    case AKT_USHORT:
      return 1.0f / 65535.0f;
    case AKT_SHORT:
      return 1.0f / 32767.0f;
    case AKT_UINT:
      return 1.0f / 4294967295.0f;
    case AKT_INT:
      return 1.0f / 2147483647.0f;
    default:
      return 1.0f;
  }
}

static int
akb_color_values_need_normalization(const float *values,
                                    uint32_t loop_count,
                                    uint32_t width,
                                    uint32_t source_width) {
  uint32_t comps, i, j;

  if (!values || !loop_count || !width)
    return 0;

  comps = source_width ? source_width : width;
  if (comps > width)
    comps = width;
  if (!comps)
    return 0;

  for (i = 0; i < loop_count; i++) {
    for (j = 0; j < comps; j++) {
      float value = values[(size_t)i * width + j];
      if (!isfinite(value) || value < 0.0f || value > 1.0f)
        return 1;
    }
  }

  return 0;
}

static void
akb_normalize_color_values(float *values,
                           uint32_t loop_count,
                           uint32_t width,
                           uint32_t source_width,
                           AkAccessor *acc) {
  float factor;
  uint32_t comps, i, j;

  if (!values || !loop_count || !width)
    return;

  factor = akb_color_normalize_factor(acc);
  if (factor == 1.0f)
    return;

  comps = source_width ? source_width : width;
  if (comps > width)
    comps = width;
  if (!comps || !akb_color_values_need_normalization(values, loop_count, width, comps))
    return;

  for (i = 0; i < loop_count; i++) {
    for (j = 0; j < comps; j++)
      values[(size_t)i * width + j] = akb_unit_clamp(values[(size_t)i * width + j] * factor);
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
akb_blender_flip_uv_v(const AkDoc *doc) {
  if (!doc || !doc->inf)
    return 1;

  /*
   * AssetKit flips image pixels for formats whose source texture convention
   * needs it. Blender loads the source image itself, so keep those UVs as-is
   * and only flip formats that AssetKit would not flip on image load.
   */
  return !doc->inf->flipImage;
}

static int
akb_extract_loop_float_attrs(AkbArena *arena,
                             AkbPrimitive *out,
                             AkMeshPrimitive *prim,
                             const AkbIndexView *index_view,
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
                             uint32_t *count_out,
                             uint8_t *arena_attrs_out) {
  AkbLoopFloatAttribute *attrs;
  AkInput *input;
  uint32_t max_count, count;
  uint8_t has_attr;
  uint8_t arena_values;

  (void)out;

  if (!attrs_out || !count_out)
    return 0;

  *attrs_out = NULL;
  *count_out = 0;
  if (arena_attrs_out)
    *arena_attrs_out = 0;
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

  attrs = (AkbLoopFloatAttribute *)akb_owned_alloc(arena,
                                                   max_count * sizeof(*attrs),
                                                   sizeof(*attrs),
                                                   arena_attrs_out);
  if (!attrs)
    return 0;
  memset(attrs, 0, max_count * sizeof(*attrs));

  count = 0;
  for (input = prim->input; input; input = input->next) {
    if (!input->accessor
        || !akb_input_matches(input, semantic_a, semantic_b, raw_a, raw_b))
      continue;

    has_attr = 0;
    arena_values = 0;
    attrs[count].values = akb_loop_attribute_copy(arena,
                                                  prim,
                                                  input,
                                                  index_view,
                                                  vertex_indices,
                                                  loop_count,
                                                  width,
                                                  flip_v,
                                                  &has_attr,
                                                  &arena_values);
    if (!attrs[count].values || !has_attr)
      continue;

    attrs[count].width = width;
    attrs[count].set = input->set;
    attrs[count].borrowed = arena_values;
    akb_fill_missing_components(attrs[count].values,
                                loop_count,
                                width,
                                input->accessor->componentCount,
                                missing_default);
    if (input->semantic == AK_INPUT_COLOR || akb_raw_semantic_starts_with(input, "COLOR"))
      akb_normalize_color_values(attrs[count].values,
                                 loop_count,
                                 width,
                                 input->accessor->componentCount,
                                 input->accessor);
    akb_loop_attr_name(&attrs[count], name_prefix, count);
    count++;
  }

  if (!count) {
    if (!arena_attrs_out || !*arena_attrs_out)
      free(attrs);
    return 1;
  }

  *attrs_out = attrs;
  *count_out = count;
  return 1;
}

static int
akb_extract_one_loop_float_attr(AkbArena *arena,
                                AkMeshPrimitive *prim,
                                AkInput *input,
                                const AkbIndexView *index_view,
                                const uint32_t *vertex_indices,
                                uint32_t loop_count,
                                uint32_t width,
                                int flip_v,
                                float missing_default,
                                const char *name_prefix,
                                AkbLoopFloatAttribute **attrs_out,
                                uint32_t *count_out,
                                uint8_t *arena_attrs_out) {
  AkbLoopFloatAttribute *attrs;
  uint8_t has_attr;
  uint8_t arena_values;

  if (!attrs_out || !count_out)
    return 0;

  *attrs_out = NULL;
  *count_out = 0;
  if (arena_attrs_out)
    *arena_attrs_out = 0;
  if (!input || !input->accessor || !loop_count)
    return 1;

  attrs = (AkbLoopFloatAttribute *)akb_owned_alloc(arena,
                                                   sizeof(*attrs),
                                                   sizeof(*attrs),
                                                   arena_attrs_out);
  if (!attrs)
    return 0;
  memset(attrs, 0, sizeof(*attrs));

  has_attr = 0;
  arena_values = 0;
  attrs[0].values = akb_loop_attribute_copy(arena,
                                            prim,
                                            input,
                                            index_view,
                                            vertex_indices,
                                            loop_count,
                                            width,
                                            flip_v,
                                            &has_attr,
                                            &arena_values);
  if (!attrs[0].values || !has_attr) {
    if (!arena_attrs_out || !*arena_attrs_out)
      free(attrs);
    return 1;
  }

  attrs[0].width = width;
  attrs[0].set = input->set;
  attrs[0].borrowed = arena_values;
  akb_fill_missing_components(attrs[0].values,
                              loop_count,
                              width,
                              input->accessor->componentCount,
                              missing_default);
  if (input->semantic == AK_INPUT_COLOR || akb_raw_semantic_starts_with(input, "COLOR"))
    akb_normalize_color_values(attrs[0].values,
                               loop_count,
                               width,
                               input->accessor->componentCount,
                               input->accessor);
  akb_loop_attr_name(attrs, name_prefix, 0);

  *attrs_out = attrs;
  *count_out = 1;
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
  if (input->semantic == AK_INPUT_NORMAL)
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

static void
akb_scan_inputs(AkMeshPrimitive *prim, uint32_t primitive_type, AkbInputScan *scan) {
  AkInput *input;

  memset(scan, 0, sizeof(*scan));
  if (!prim)
    return;

  for (input = prim->input; input; input = input->next) {
    if (!input->accessor || input->accessor->count == 0)
      continue;

    if (akb_input_matches(input, AK_INPUT_NORMAL, AK_INPUT_NORMAL, "NORMAL", NULL)) {
      if (!scan->normal)
        scan->normal = input;
      if (akb_point_attr_candidate(input, primitive_type))
        scan->point_attr_count++;
      continue;
    }

    if (!scan->tangent
        && akb_input_matches(input,
                             AK_INPUT_TANGENT,
                             AK_INPUT_TEXTANGENT,
                             "TANGENT",
                             "TEXTANGENT")) {
      scan->tangent = input;
      continue;
    }

    if (akb_input_matches(input, AK_INPUT_TEXCOORD, AK_INPUT_UV, "TEXCOORD", "UV")) {
      if (!scan->uv)
        scan->uv = input;
      scan->uv_count++;
      continue;
    }

    if (akb_input_matches(input, AK_INPUT_COLOR, AK_INPUT_COLOR, "COLOR", NULL)) {
      if (!scan->color)
        scan->color = input;
      scan->color_count++;
      continue;
    }

    if (akb_point_attr_candidate(input, primitive_type))
      scan->point_attr_count++;
  }
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
  } else if (input->semantic == AK_INPUT_NORMAL) {
    snprintf(attr->name, sizeof(attr->name), "assetkit_normal");
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
  float missing_default;
  uint32_t max_count, count, value_count, width;
  uint8_t borrowed;
  uint8_t is_color;

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
    is_color = input->semantic == AK_INPUT_COLOR
               || akb_raw_semantic_starts_with(input, "COLOR");
    missing_default = is_color ? 1.0f : 0.0f;
    values = akb_accessor_float_borrow(input->accessor, width, &value_count);
    if (values) {
      borrowed = 1;
    } else {
      values = akb_accessor_float_copy_with_default(input->accessor,
                                                    width,
                                                    missing_default,
                                                    &value_count);
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
    if (borrowed)
      akb_fill_missing_components(attrs[count].values,
                                  out->vertex_count,
                                  width,
                                  input->accessor->componentCount,
                                  missing_default);
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

