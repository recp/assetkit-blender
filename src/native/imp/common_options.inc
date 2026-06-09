
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

static AkCoordSys *
akb_blender_source_coord(AkDoc *doc) {
  AkFileType ftype;

  if (!doc)
    return AK_YUP;

  ftype = doc->inf ? doc->inf->ftype : AK_FILE_TYPE_AUTO;
  switch (ftype) {
    case AK_FILE_TYPE_WAVEFRONT:
    case AK_FILE_TYPE_STL:
    case AK_FILE_TYPE_PLY:
      return AK_ZUP;
    default:
      break;
  }

  return doc->coordSys ? doc->coordSys : AK_YUP;
}

static void
akb_coord_ctx_init(AkbCoordContext *coord, AkDoc *doc, const AkbLoadOptions *options) {
  coord->source = akb_blender_source_coord(doc);
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
akb_coord_from_id(long id) {
  switch (id) {
    case AKB_LOAD_COORD_Y_UP:
      return AK_YUP;
    case AKB_LOAD_COORD_X_UP:
      return AK_XUP;
    case AKB_LOAD_COORD_Z_UP_LH:
      return AK_ZUP_LH;
    case AKB_LOAD_COORD_Y_UP_LH:
      return AK_YUP_LH;
    case AKB_LOAD_COORD_X_UP_LH:
      return AK_XUP_LH;
    default:
      break;
  }
  return AK_ZUP;
}

static uint8_t
akb_conversion_from_id(long id) {
  if (id == AKB_COORD_RAW)
    return AKB_COORD_RAW;
  if (id == AKB_COORD_ALL)
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
  options->use_mmap = 1;
  options->preserve_extras = 1;
  options->build_triangle_edges = 0;
  options->geometry_keys = 1;
}

static PyObject *
akb_load_option_item(PyObject **items, Py_ssize_t count, Py_ssize_t index) {
  if (index < 0 || index >= count)
    return NULL;
  return items[index];
}

static int
akb_load_option_long(PyObject  **items,
                     Py_ssize_t count,
                     Py_ssize_t index,
                     long      *value) {
  PyObject *item;
  long      val;

  item = akb_load_option_item(items, count, index);
  if (!item || item == Py_None)
    return 1;

  val = PyLong_AsLong(item);
  if (PyErr_Occurred())
    return 0;

  *value = val;
  return 1;
}

static int
akb_load_option_bool(PyObject  **items,
                     Py_ssize_t count,
                     Py_ssize_t index,
                     uint8_t   *value) {
  PyObject *item;
  int       isTrue;

  item = akb_load_option_item(items, count, index);
  if (!item || item == Py_None)
    return 1;

  isTrue = PyObject_IsTrue(item);
  if (isTrue < 0)
    return 0;

  *value = isTrue ? 1 : 0;
  return 1;
}

static int
akb_load_options_from_object(AkbLoadOptions *options, PyObject *obj) {
  PyObject  *seq;
  PyObject **items;
  Py_ssize_t count;
  long       value;

  akb_load_options_default(options);
  if (!obj || obj == Py_None)
    return 1;

  seq = PySequence_Fast(obj, "AssetKit load options must be a tuple or list");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  items = PySequence_Fast_ITEMS(seq);

  value = AKB_LOAD_COORD_Z_UP;
  if (!akb_load_option_long(items, count, AKB_LOAD_OPT_COORD_SYSTEM, &value))
    goto fail;
  options->target_coord = akb_coord_from_id(value);

  value = AKB_COORD_TRANSFORM;
  if (!akb_load_option_long(items, count, AKB_LOAD_OPT_COORD_CONVERSION, &value))
    goto fail;
  options->coord_conversion = akb_conversion_from_id(value);

  value = options->scene_index;
  if (!akb_load_option_long(items, count, AKB_LOAD_OPT_SCENE_INDEX, &value))
    goto fail;
  options->scene_index = (int32_t)value;

  if (!akb_load_option_bool(items, count, AKB_LOAD_OPT_TRIANGULATE, &options->triangulate)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_GENERATE_NORMALS, &options->gen_normals)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_CONVERT_TRIANGLE_STRIP, &options->cvt_triangle_strip)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_CONVERT_TRIANGLE_FAN, &options->cvt_triangle_fan)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_IMPORT_LINES, &options->import_lines)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_CONVERT_LINE_LOOP, &options->cvt_line_loop)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_CONVERT_LINE_STRIP, &options->cvt_line_strip)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_USE_MMAP, &options->use_mmap)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_PRESERVE_EXTRAS, &options->preserve_extras)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_BUILD_TRIANGLE_EDGES, &options->build_triangle_edges)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_GEOMETRY_KEYS, &options->geometry_keys)
      || !akb_load_option_bool(items, count, AKB_LOAD_OPT_GEOMETRY_CONTENT_KEYS, &options->geometry_content_keys))
    goto fail;

  Py_DECREF(seq);
  return 1;

fail:
  Py_DECREF(seq);
  return 0;
}

static AkCoordCvtType
akb_assetkit_coord_cvt_type(uint8_t conversion) {
  if (conversion == AKB_COORD_RAW)
    return AK_COORD_CVT_DISABLED;
  if (conversion == AKB_COORD_ALL)
    return AK_COORD_CVT_ALL;
  return AK_COORD_CVT_DISABLED;
}

static const char *
akb_sibling_decoder_path(char *dst, size_t dst_size, const char *filename) {
  char modpath[PATH_MAX];
  char *sep;
  char *sep2;
  size_t dir_len;
  size_t file_len;

  if (!dst || dst_size == 0 || !filename)
    return NULL;

#if defined(_WIN32)
  {
    HMODULE module = NULL;
    DWORD len;

    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
                            | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            (LPCSTR)&akb_sibling_decoder_path,
                            &module))
      return NULL;

    len = GetModuleFileNameA(module, modpath, sizeof(modpath));
    if (len == 0 || len >= sizeof(modpath))
      return NULL;
  }
#else
  {
    Dl_info info;
    int len;

    if (!dladdr((const void *)&akb_sibling_decoder_path, &info)
        || !info.dli_fname)
      return NULL;

    len = snprintf(modpath, sizeof(modpath), "%s", info.dli_fname);
    if (len <= 0 || (size_t)len >= sizeof(modpath))
      return NULL;
  }
#endif

  sep = strrchr(modpath, '/');
  sep2 = strrchr(modpath, '\\');
  if (!sep || (sep2 && sep2 > sep))
    sep = sep2;
  if (!sep)
    return NULL;

  dir_len = (size_t)(sep - modpath) + 1;
  file_len = strlen(filename);
  if (dir_len + file_len >= dst_size)
    return NULL;

  memcpy(dst, modpath, dir_len);
  memcpy(dst + dir_len, filename, file_len + 1);

#if defined(_WIN32)
  return GetFileAttributesA(dst) != INVALID_FILE_ATTRIBUTES ? dst : NULL;
#else
  return access(dst, R_OK) == 0 ? dst : NULL;
#endif
}

static void
akb_decoder_paths_init(void) {
  if (AKB_DECODER_PATHS.initialized)
    return;

#if defined(_WIN32)
  akb_sibling_decoder_path(AKB_DECODER_PATHS.meshopt,
                           sizeof(AKB_DECODER_PATHS.meshopt),
                           "assetkit_meshoptimizer.dll");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.draco,
                           sizeof(AKB_DECODER_PATHS.draco),
                           "assetkit_draco.dll");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.gsplat,
                           sizeof(AKB_DECODER_PATHS.gsplat),
                           "assetkit_spz.dll");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.ktx2,
                           sizeof(AKB_DECODER_PATHS.ktx2),
                           "assetkit_ktx2.dll");
#elif defined(__APPLE__)
  akb_sibling_decoder_path(AKB_DECODER_PATHS.meshopt,
                           sizeof(AKB_DECODER_PATHS.meshopt),
                           "libassetkit_meshoptimizer.dylib");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.draco,
                           sizeof(AKB_DECODER_PATHS.draco),
                           "libassetkit_draco.dylib");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.gsplat,
                           sizeof(AKB_DECODER_PATHS.gsplat),
                           "libassetkit_spz.dylib");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.ktx2,
                           sizeof(AKB_DECODER_PATHS.ktx2),
                           "libassetkit_ktx2.dylib");
#else
  akb_sibling_decoder_path(AKB_DECODER_PATHS.meshopt,
                           sizeof(AKB_DECODER_PATHS.meshopt),
                           "libassetkit_meshoptimizer.so");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.draco,
                           sizeof(AKB_DECODER_PATHS.draco),
                           "libassetkit_draco.so");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.gsplat,
                           sizeof(AKB_DECODER_PATHS.gsplat),
                           "libassetkit_spz.so");
  akb_sibling_decoder_path(AKB_DECODER_PATHS.ktx2,
                           sizeof(AKB_DECODER_PATHS.ktx2),
                           "libassetkit_ktx2.so");
#endif

  AKB_DECODER_PATHS.initialized = 1;
}

static void
akb_set_decoder_path_if_empty(AkOption option, const char *path) {
  if (path && path[0] && !ak_opt_get(option))
    ak_opt_set(option, (uintptr_t)path);
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
  saved->preserve_extras = ak_opt_get(AK_OPT_PRESERVE_EXTRAS);
  saved->meshopt_decoder_path = ak_opt_get(AK_OPT_GLTF_MESHOPT_DECODER_PATH);
  saved->draco_decoder_path = ak_opt_get(AK_OPT_GLTF_DRACO_DECODER_PATH);
  saved->gsplat_decoder_path = ak_opt_get(AK_OPT_GLTF_GSPLAT_DECODER_PATH);
  saved->ktx2_decoder_path = ak_opt_get(AK_OPT_GLTF_KTX2_DECODER_PATH);

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
  ak_opt_set(AK_OPT_PRESERVE_EXTRAS, options->preserve_extras);

  akb_decoder_paths_init();
  akb_set_decoder_path_if_empty(AK_OPT_GLTF_MESHOPT_DECODER_PATH,
                                AKB_DECODER_PATHS.meshopt);
  akb_set_decoder_path_if_empty(AK_OPT_GLTF_DRACO_DECODER_PATH,
                                AKB_DECODER_PATHS.draco);
  akb_set_decoder_path_if_empty(AK_OPT_GLTF_GSPLAT_DECODER_PATH,
                                AKB_DECODER_PATHS.gsplat);
  akb_set_decoder_path_if_empty(AK_OPT_GLTF_KTX2_DECODER_PATH,
                                AKB_DECODER_PATHS.ktx2);
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
  ak_opt_set(AK_OPT_PRESERVE_EXTRAS, saved->preserve_extras);
  ak_opt_set(AK_OPT_GLTF_MESHOPT_DECODER_PATH, saved->meshopt_decoder_path);
  ak_opt_set(AK_OPT_GLTF_DRACO_DECODER_PATH, saved->draco_decoder_path);
  ak_opt_set(AK_OPT_GLTF_GSPLAT_DECODER_PATH, saved->gsplat_decoder_path);
  ak_opt_set(AK_OPT_GLTF_KTX2_DECODER_PATH, saved->ktx2_decoder_path);
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

static void
akb_anim_channel_free(AkbAnimChannel *channel) {
  if (!channel)
    return;

  if (!channel->borrowed_times)
    free(channel->times);
  if (!channel->borrowed_values)
    free(channel->values);
  if (!channel->borrowed_in_tangents)
    free(channel->in_tangents);
  if (!channel->borrowed_out_tangents)
    free(channel->out_tangents);
  memset(channel, 0, sizeof(*channel));
}

static const char *
akb_name(const char *value, const char *fallback) {
  return value && value[0] ? value : fallback;
}

static const char *
akb_arena_format_name_u32(AkbArena *arena, const char *base, uint32_t index) {
  char *buf;
  int len;

  base = akb_name(base, "AssetKit");
  len = snprintf(NULL, 0, "%s_%u", base, index);
  if (len < 0)
    return NULL;

  buf = (char *)akb_arena_alloc(arena, (size_t)len + 1u, 1);
  if (!buf)
    return NULL;

  snprintf(buf, (size_t)len + 1u, "%s_%u", base, index);
  return buf;
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
  if (!prim->borrowed_vertices && !prim->arena_vertices)
    free(prim->vertices);
  if (!prim->arena_instance_matrices)
    free(prim->instance_matrices);
  if (!prim->borrowed_indices && !prim->arena_indices)
    free(prim->indices);
  if (!prim->borrowed_edges && !prim->arena_edges)
    free(prim->edges);
  if (!prim->arena_loop_meta)
    free(prim->loop_meta);
  if (!prim->borrowed_normals)
    free(prim->normals);
  if (!prim->borrowed_vertex_normals)
    free(prim->vertex_normals);
  for (i = 0; i < prim->uv_set_count; i++)
    if (!prim->uv_sets[i].borrowed)
      free(prim->uv_sets[i].values);
  if (!prim->arena_uv_sets)
    free(prim->uv_sets);
  for (i = 0; i < prim->color_set_count; i++)
    if (!prim->color_sets[i].borrowed)
      free(prim->color_sets[i].values);
  if (!prim->arena_color_sets)
    free(prim->color_sets);
  for (i = 0; i < prim->point_attr_count; i++)
    if (!prim->point_attrs[i].borrowed)
      free(prim->point_attrs[i].values);
  if (!prim->arena_point_attrs)
    free(prim->point_attrs);
  if (!prim->uv_set_count)
    free(prim->uvs);
  if (!prim->color_set_count)
    free(prim->colors);
  if (!prim->borrowed_tangents)
    free(prim->tangents);
  free(prim->skin_joints);
  if (!prim->arena_skin_joint_nodes)
    free(prim->skin_joint_nodes);
  free(prim->skin_weights);
  if (!prim->arena_skin_inverse_bind_matrices)
    free(prim->skin_inverse_bind_matrices);
  if (!prim->arena_skin_joint_sources)
    free(prim->skin_joint_sources);
  for (i = 0; i < prim->skin_pose_animation_count; i++)
    akb_animation_release(prim->skin_pose_animations[i]);
  free(prim->skin_pose_animations);
  free(prim->material_variants);
  free(prim->texture_infos);
  free(prim->base_color_texture);
  free(prim->metallic_roughness_texture);
  free(prim->occlusion_texture);
  free(prim->normal_texture);
  free(prim->emissive_texture);
  free(prim->transparent_texture);
  free(prim->specular_texture);
  free(prim->specular_color_texture);
  free(prim->clearcoat_texture);
  free(prim->clearcoat_roughness_texture);
  free(prim->clearcoat_normal_texture);
  free(prim->transmission_texture);
  free(prim->sheen_color_texture);
  free(prim->sheen_roughness_texture);
  free(prim->iridescence_texture);
  free(prim->iridescence_thickness_texture);
  free(prim->volume_thickness_texture);
  free(prim->anisotropy_texture);
  free(prim->diffuse_transmission_texture);
  free(prim->diffuse_transmission_color_texture);
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
akb_list_reserve(AkbPrimitiveList *list, size_t capacity) {
  AkbPrimitive *new_items;

  if (!list || capacity <= list->capacity)
    return 1;
  if (capacity > SIZE_MAX / sizeof(*new_items))
    return 0;

  new_items = (AkbPrimitive *)realloc(list->items, capacity * sizeof(*new_items));
  if (!new_items)
    return 0;

  list->items = new_items;
  list->capacity = capacity;
  return 1;
}

static int
akb_node_list_reserve(AkbSceneNodeList *list, size_t capacity) {
  AkbSceneNode *new_items;

  if (!list || capacity <= list->capacity)
    return 1;
  if (capacity > SIZE_MAX / sizeof(*new_items))
    return 0;

  new_items = (AkbSceneNode *)realloc(list->items, capacity * sizeof(*new_items));
  if (!new_items)
    return 0;

  list->items = new_items;
  list->capacity = capacity;
  return 1;
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

  if (prim->has_skin)
    list->skin_count++;
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
akb_set_primitive_coord_matrix(AkbPrimitive *prim, const AkbCoordContext *coord) {
  if (!prim || !coord)
    return;
  memcpy(prim->coord_matrix, coord->matrix, sizeof(prim->coord_matrix));
  prim->has_coord_matrix = 1;
}

static void
akb_list_set_coord_matrix(AkbPrimitiveList *list, const AkbCoordContext *coord, int include_skin_primitives) {
  size_t i;

  (void)include_skin_primitives;

  if (!list || !coord || !coord->convert || coord->conversion != AKB_COORD_TRANSFORM)
    return;

  for (i = 0; i < list->count; i++)
    akb_set_primitive_coord_matrix(&list->items[i], coord);
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

