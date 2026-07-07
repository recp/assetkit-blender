static void
akb_import_free(AkbImport *import) {
  if (!import)
    return;
  akb_list_free(&import->primitives);
  akb_curve_list_free(&import->curves);
  akb_node_list_free(&import->nodes);
  akb_arena_free(&import->arena);
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
akb_float_default(float value, float defval) {
  if (value == defval)
    return 1;
  return fabsf(value - defval) <= 1.0e-6f;
}

static PyObject *
akb_float_or_none(float value, float defval) {
  if (akb_float_default(value, defval))
    Py_RETURN_NONE;
  return PyFloat_FromDouble(value);
}

static PyObject *
akb_none(void) {
  Py_RETURN_NONE;
}

static PyObject *
akb_vec3_or_none(const float value[3], float x, float y, float z) {
  if (akb_float_default(value[0], x)
      && akb_float_default(value[1], y)
      && akb_float_default(value[2], z))
    Py_RETURN_NONE;
  return Py_BuildValue("(fff)", value[0], value[1], value[2]);
}

static PyObject *
akb_vec4_or_none(const float value[4], float x, float y, float z, float w) {
  if (akb_float_default(value[0], x)
      && akb_float_default(value[1], y)
      && akb_float_default(value[2], z)
      && akb_float_default(value[3], w))
    Py_RETURN_NONE;
  return Py_BuildValue("(ffff)", value[0], value[1], value[2], value[3]);
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
  AkImageSource *source;
  AkImageBase *base;
  PyObject *dict;
  char path[PATH_MAX];

  dict = PyDict_New();
  if (!dict)
    return NULL;

  source = image ? image->source : NULL;
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
  AKB_IMAGE_SET_OBJ("mime_type", akb_unicode_from_cstr(source ? source->mimeType : NULL));
  AKB_IMAGE_SET_OBJ("type", PyLong_FromLong(base ? (long)base->type : 0));
  AKB_IMAGE_SET_OBJ("embedded",
                    PyBool_FromLong(source && source->buffer && source->buffer->data));
  AKB_IMAGE_SET_OBJ("face", PyLong_FromLong(source ? (long)source->face : 0));
  AKB_IMAGE_SET_OBJ("mip_index", PyLong_FromUnsignedLong(source ? source->mipIndex : 0));
  AKB_IMAGE_SET_OBJ("array_index", PyLong_FromLong(source ? (long)source->arrayIndex : -1));
  AKB_IMAGE_SET_OBJ("depth", PyLong_FromUnsignedLong(source ? source->depth : 0));
  AKB_IMAGE_SET_OBJ("extra", akb_tree_to_py(image ? ak_extra(image) : NULL));

#undef AKB_IMAGE_SET_OBJ

  return dict;
}

static PyObject *
akb_doc_images_to_py(AkDoc *doc) {
  AkImage *item;
  PyObject *list;
  PyObject *image_obj;
  size_t index;

  list = PyList_New(0);
  if (!list)
    return NULL;

  if (!doc)
    return list;

  index = 0;
  for (item = doc->lib.images.first; item; item = item->next) {
    image_obj = akb_image_to_py(doc, item, index++);
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
akb_scene_count(AkDoc *doc) {
  AkScene *scene;
  size_t count = 0;

  if (!doc || !doc->lib.scenes.first)
    return 0;

  for (scene = doc->lib.scenes.first;
       scene;
       scene = scene->next)
    count++;

  return count;
}

static int32_t
akb_scene_index(AkDoc *doc, AkScene *selected) {
  AkScene *scene;
  int32_t index = 0;

  if (!doc || !doc->lib.scenes.first || !selected)
    return -1;

  for (scene = doc->lib.scenes.first;
       scene;
       scene = scene->next, index++) {
    if (scene == selected)
      return index;
  }

  return -1;
}

static PyObject *
akb_scene_names_to_py(AkDoc *doc) {
  AkScene *scene;
  PyObject *list;
  PyObject *item;

  list = PyList_New(0);
  if (!list)
    return NULL;

  if (!doc || !doc->lib.scenes.first)
    return list;

  for (scene = doc->lib.scenes.first;
       scene;
       scene = scene->next) {
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
  AkScene *scene;

  scene = akb_selected_scene(doc, options);

  return akb_py_dict_set_owned(out,
                               "scene_count",
                               PyLong_FromSize_t(akb_scene_count(doc)))
         && akb_py_dict_set_owned(out,
                                  "scene_index",
                                  PyLong_FromLong(akb_scene_index(doc, scene)))
         && akb_py_dict_set_owned(out,
                                  "scene_name",
                                  akb_unicode_from_cstr(scene ? scene->name : NULL))
         && akb_py_dict_set_owned(out,
                                  "scene_names",
                                  akb_scene_names_to_py(doc))
         && akb_py_dict_set_owned(out,
                                  "scene_extra",
                                  akb_tree_to_py(scene ? ak_extra(scene) : NULL));
}

static PyObject *
akb_anim_channels_to_py(AkbAnimation *animation) {
  PyObject *list;
  PyObject *tuple;
  PyObject *value;
  AkbAnimChannel *channel;
  size_t i;

  if (!animation || !animation->count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)animation->count);
  if (!list)
    return NULL;

#define AKB_CH_SET_OBJ(INDEX, OBJ) do {            \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(tuple); Py_DECREF(list); return NULL; } \
    PyTuple_SET_ITEM(tuple, (INDEX), value);        \
  } while (0)

  for (i = 0; i < animation->count; i++) {
    channel = &animation->channels[i];
    tuple = PyTuple_New(AKB_PY_ANIM_FIELD_COUNT);
    if (!tuple) {
      Py_DECREF(list);
      return NULL;
    }

    AKB_CH_SET_OBJ(AKB_PY_ANIM_TARGET, PyLong_FromUnsignedLong(channel->target));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_TARGET_OFFSET, PyLong_FromUnsignedLong(channel->target_offset));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_CLIP_INDEX, PyLong_FromUnsignedLong(channel->clip_index));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_CLIP_NAME, akb_unicode_from_cstr(channel->clip_name));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_VALUE_WIDTH, PyLong_FromUnsignedLong(channel->value_width));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_COUNT, PyLong_FromUnsignedLong(channel->count));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_INTERPOLATION, PyLong_FromUnsignedLong(channel->interpolation));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_IS_PARTIAL, PyBool_FromLong(channel->is_partial));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_POSE_READY, PyBool_FromLong(channel->pose_ready));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_TIMES_F32,
                   akb_memoryview_or_empty(channel->times,
                                           (size_t)channel->count * sizeof(float)));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_VALUES_F32,
                   akb_memoryview_or_empty(channel->values,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_IN_TANGENTS_F32,
                   akb_memoryview_or_empty(channel->in_tangents,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));
    AKB_CH_SET_OBJ(AKB_PY_ANIM_OUT_TANGENTS_F32,
                   akb_memoryview_or_empty(channel->out_tangents,
                                           (size_t)channel->count
                                           * channel->value_width
                                           * sizeof(float)));

    PyList_SET_ITEM(list, (Py_ssize_t)i, tuple);
  }

#undef AKB_CH_SET_OBJ

  return list;
}

static PyObject *
akb_skin_pose_anim_channels_to_py(AkbPrimitive *prim) {
  PyObject *list;
  PyObject *channels;
  uint32_t i;

  if (!prim || !prim->skin_pose_animation_count)
    return PyList_New(0);

  list = PyList_New((Py_ssize_t)prim->skin_pose_animation_count);
  if (!list)
    return NULL;

  for (i = 0; i < prim->skin_pose_animation_count; i++) {
    channels = akb_anim_channels_to_py(prim->skin_pose_animations
                                       ? prim->skin_pose_animations[i]
                                       : NULL);
    if (!channels) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, (Py_ssize_t)i, channels);
  }

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

static int
akb_float_eq(float a, float b) {
  if (a == b)
    return 1;
  return fabsf(a - b) <= 1.0e-6f;
}

static int
akb_vec3_eq(const float v[3], float x, float y, float z) {
  return akb_float_eq(v[0], x)
         && akb_float_eq(v[1], y)
         && akb_float_eq(v[2], z);
}

static int
akb_vec4_eq(const float v[4], float x, float y, float z, float w) {
  return akb_float_eq(v[0], x)
         && akb_float_eq(v[1], y)
         && akb_float_eq(v[2], z)
         && akb_float_eq(v[3], w);
}

static int
akb_primitive_has_simple_material_values(const AkbPrimitive *prim) {
  return prim
         && akb_vec4_eq(prim->transparent_color, 1.0f, 1.0f, 1.0f, 1.0f)
         && akb_vec3_eq(prim->emissive_color, 0.0f, 0.0f, 0.0f)
         && akb_vec3_eq(prim->specular_color, 1.0f, 1.0f, 1.0f)
         && akb_vec3_eq(prim->sheen_color, 0.0f, 0.0f, 0.0f)
         && akb_vec3_eq(prim->volume_attenuation_color, 1.0f, 1.0f, 1.0f)
         && akb_vec3_eq(prim->volume_scatter_color, 0.0f, 0.0f, 0.0f)
         && akb_vec3_eq(prim->diffuse_transmission_color, 1.0f, 1.0f, 1.0f)
         && akb_float_eq(prim->alpha_cutoff, 0.5f)
         && akb_float_eq(prim->transparent_amount, 1.0f)
         && akb_float_eq(prim->normal_scale, 1.0f)
         && akb_float_eq(prim->occlusion_strength, 1.0f)
         && akb_float_eq(prim->emissive_strength, 1.0f)
         && akb_float_eq(prim->specular_strength, 1.0f)
         && akb_float_eq(prim->ior, 1.5f)
         && akb_float_eq(prim->clearcoat, 0.0f)
         && akb_float_eq(prim->clearcoat_roughness, 0.0f)
         && akb_float_eq(prim->clearcoat_normal_scale, 1.0f)
         && akb_float_eq(prim->transmission, 0.0f)
         && akb_float_eq(prim->sheen_roughness, 0.0f)
         && akb_float_eq(prim->iridescence, 0.0f)
         && akb_float_eq(prim->iridescence_ior, 1.3f)
         && akb_float_eq(prim->iridescence_thickness_minimum, 100.0f)
         && akb_float_eq(prim->iridescence_thickness_maximum, 400.0f)
         && akb_float_eq(prim->volume_thickness, 0.0f)
         && akb_float_eq(prim->volume_attenuation_distance, INFINITY)
         && akb_float_eq(prim->volume_scatter_anisotropy, 0.0f)
         && akb_float_eq(prim->anisotropy, 0.0f)
         && akb_float_eq(prim->anisotropy_rotation, 0.0f)
         && akb_float_eq(prim->diffuse_transmission, 0.0f)
         && akb_float_eq(prim->dispersion, 0.0f);
}

static int
akb_primitive_simple_uvs_ok(const AkbPrimitive *prim) {
  if (!prim || !prim->uv_set_count)
    return 1;
  if (prim->uv_set_count != 1 || !prim->uv_sets || !prim->uvs)
    return 0;
  if (prim->uv_sets[0].width != 2)
    return 0;
  if (prim->uv_sets[0].values != prim->uvs)
    return 0;
  return prim->uv_sets[0].name[0] == '\0'
         || strcmp(prim->uv_sets[0].name, "UVMap") == 0;
}

static int
akb_primitive_simple_base_color_texture_ok(const AkbPrimitive *prim) {
  AkbTextureInfo *info;

  if (!prim)
    return 0;
  if (!akb_cstr_has(prim->base_color_texture))
    return prim->texture_info_count == 0;
  if (prim->texture_info_count == 0)
    return 1;
  if (prim->texture_info_count != 1)
    return 0;
  if (!prim->texture_infos)
    return 0;

  info = (AkbTextureInfo *)&prim->texture_infos[0];
  if (strcmp(info->role, "base_color") != 0)
    return 0;
  if (info->has_transform || info->slot != 0 || info->transform_slot > 0)
    return 0;
  if (info->texture_extra || info->texref_extra || info->image_extra || info->sampler_extra)
    return 0;
  return 1;
}

static int
akb_primitive_is_simple_py(const AkbPrimitive *prim) {
  return prim
         && akb_primitive_has_simple_material_values(prim)
         && akb_primitive_simple_uvs_ok(prim)
         && akb_primitive_simple_base_color_texture_ok(prim)
         && !prim->color_set_count
         && !prim->point_attr_count
         && !prim->has_skin
         && !prim->has_gsplat
         && !prim->has_sheen
         && !prim->transparent_inverted
         && !prim->primitive_extra
         && !prim->mesh_extra
         && !prim->geometry_extra
         && !prim->material_extra
         && !prim->material_variant_count
         && !prim->morph_target_count
         && !prim->morph_preset_count
         && !(prim->animation && prim->animation->count)
         && !(prim->morph_animation && prim->morph_animation->count)
         && !(prim->material_animation && prim->material_animation->count)
         && !akb_cstr_has(prim->metallic_roughness_texture)
         && !akb_cstr_has(prim->occlusion_texture)
         && !akb_cstr_has(prim->normal_texture)
         && !akb_cstr_has(prim->emissive_texture)
         && !akb_cstr_has(prim->transparent_texture)
         && !akb_cstr_has(prim->specular_texture)
         && !akb_cstr_has(prim->specular_color_texture)
         && !akb_cstr_has(prim->clearcoat_texture)
         && !akb_cstr_has(prim->clearcoat_roughness_texture)
         && !akb_cstr_has(prim->clearcoat_normal_texture)
         && !akb_cstr_has(prim->transmission_texture)
         && !akb_cstr_has(prim->sheen_color_texture)
         && !akb_cstr_has(prim->sheen_roughness_texture)
         && !akb_cstr_has(prim->iridescence_texture)
         && !akb_cstr_has(prim->iridescence_thickness_texture)
         && !akb_cstr_has(prim->volume_thickness_texture)
         && !akb_cstr_has(prim->anisotropy_texture)
         && !akb_cstr_has(prim->diffuse_transmission_texture)
         && !akb_cstr_has(prim->diffuse_transmission_color_texture);
}

static PyObject *
akb_primitive_simple_to_py(AkbPrimitive *prim, PyObject *owner) {
  PyObject *tuple;
  PyObject *value;

  tuple = PyTuple_New(AKB_PY_SIMPLE_FIELD_COUNT);
  if (!tuple)
    return NULL;

#define AKB_SIMPLE_SET(INDEX, OBJ) do {                   \
    value = (OBJ);                                        \
    if (!value) { Py_DECREF(tuple); return NULL; }        \
    PyTuple_SET_ITEM(tuple, (INDEX), value);              \
  } while (0)

  Py_INCREF(owner);
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_OWNER, owner);
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_NAME, akb_unicode_from_cstr(prim->name));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_OBJECT_NAME, akb_unicode_from_cstr(prim->object_name));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_VERTEX_COUNT, PyLong_FromUnsignedLong(prim->vertex_count));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_LOOP_COUNT, PyLong_FromUnsignedLong(prim->loop_count));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_FACE_COUNT, PyLong_FromUnsignedLong(prim->face_count));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_PRIMITIVE_TYPE, PyLong_FromUnsignedLong(prim->primitive_type));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_PRIMITIVE_MODE, PyLong_FromUnsignedLong(prim->primitive_mode));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_FILE_TYPE, PyLong_FromUnsignedLong(prim->file_type));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_MESH_KEY,
                 PyLong_FromUnsignedLongLong((unsigned long long)prim->mesh_key));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_PRIMITIVE_INDEX,
                 PyLong_FromUnsignedLong(prim->primitive_index));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_ZERO_COPY_FLAGS,
                 PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_HAS_NODE, PyBool_FromLong(prim->has_node));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_NODE_INDEX, PyLong_FromLong(prim->node_index));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_MATRIX_F32,
                 akb_memoryview_or_empty(prim->matrix,
                                         prim->has_node ? 16 * sizeof(float) : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_COORD_MATRIX_F32,
                 akb_memoryview_or_empty(prim->coord_matrix,
                                         prim->has_coord_matrix ? 16 * sizeof(float) : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_INSTANCE_COUNT,
                 PyLong_FromUnsignedLong(prim->instance_count));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_INSTANCE_MATRICES_F32,
                 akb_memoryview_or_empty(prim->instance_matrices,
                                         prim->instance_count
                                         ? (size_t)prim->instance_count
                                           * 16
                                           * sizeof(float)
                                         : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_VERTICES_F32,
                 akb_memoryview_or_empty(prim->vertices,
                                         (size_t)prim->vertex_count * 3 * sizeof(float)));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_INDICES_U32,
                 akb_memoryview_or_empty(prim->indices,
                                         (size_t)prim->loop_count * sizeof(uint32_t)));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_LOOP_STARTS_I32,
                 akb_memoryview_or_empty(prim->loop_starts,
                                         (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_LOOP_TOTALS_I32,
                 akb_memoryview_or_empty(prim->loop_totals,
                                         (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_NORMALS_F32,
                 akb_memoryview_or_empty(prim->normals,
                                         prim->has_normals
                                         ? (size_t)prim->loop_count
                                           * 3
                                           * sizeof(float)
                                         : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_VERTEX_NORMALS_F32,
                 akb_memoryview_or_empty(prim->vertex_normals,
                                         prim->has_vertex_normals
                                         ? (size_t)prim->vertex_count
                                           * 3
                                           * sizeof(float)
                                         : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_TANGENTS_F32,
                 akb_memoryview_or_empty(prim->tangents,
                                         prim->has_tangents
                                         ? (size_t)prim->loop_count
                                           * 4
                                           * sizeof(float)
                                         : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_GEOMETRY_KEY,
                 PyLong_FromUnsignedLongLong((unsigned long long)prim->geometry_key));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_EDGE_COUNT, PyLong_FromUnsignedLong(prim->edge_count));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_EDGES_U32,
                 akb_memoryview_or_empty(prim->edges,
                                         (size_t)prim->edge_count * 2 * sizeof(uint32_t)));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_UVS_F32,
                 akb_memoryview_or_empty(prim->uvs,
                                         prim->has_uvs
                                         ? (size_t)prim->loop_count
                                           * 2
                                           * sizeof(float)
                                         : 0));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_BASE_COLOR_TEXTURE,
                 akb_unicode_from_cstr(prim->base_color_texture));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_MATERIAL_TYPE,
                 PyLong_FromUnsignedLong(prim->material_type));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_MATERIAL_KEY,
                 PyLong_FromUnsignedLongLong((unsigned long long)prim->material_key));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_METALLIC, PyFloat_FromDouble(prim->metallic));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_ROUGHNESS, PyFloat_FromDouble(prim->roughness));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_DOUBLE_SIDED, PyBool_FromLong(prim->double_sided));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_SMOOTH_SHADING, PyBool_FromLong(prim->smooth_shading));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_MATERIAL_NAME,
                 akb_unicode_from_cstr(prim->material_name));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_BASE_COLOR,
                 akb_vec4_or_none(prim->base_color, 1.0f, 1.0f, 1.0f, 1.0f));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_OPACITY, akb_float_or_none(prim->opacity, 1.0f));
  AKB_SIMPLE_SET(AKB_PY_SIMPLE_ALPHA_MODE,
                 prim->alpha_mode
                 ? PyLong_FromUnsignedLong(prim->alpha_mode)
                 : akb_none());

#undef AKB_SIMPLE_SET

  return tuple;
}

static PyObject *
akb_curve_to_py(AkbCurve *curve, PyObject *owner) {
  PyObject *tuple;
  PyObject *value;

  tuple = PyTuple_New(AKB_PY_CURVE_FIELD_COUNT);
  if (!tuple)
    return NULL;

#define AKB_CURVE_SET(INDEX, OBJ) do {                    \
    value = (OBJ);                                        \
    if (!value) { Py_DECREF(tuple); return NULL; }        \
    PyTuple_SET_ITEM(tuple, (INDEX), value);              \
  } while (0)

  Py_INCREF(owner);
  AKB_CURVE_SET(AKB_PY_CURVE_OWNER, owner);
  AKB_CURVE_SET(AKB_PY_CURVE_NAME, akb_unicode_from_cstr(curve->name));
  AKB_CURVE_SET(AKB_PY_CURVE_OBJECT_NAME, akb_unicode_from_cstr(curve->object_name));
  AKB_CURVE_SET(AKB_PY_CURVE_KIND, PyLong_FromUnsignedLong(curve->kind));
  AKB_CURVE_SET(AKB_PY_CURVE_POINT_COUNT, PyLong_FromUnsignedLong(curve->point_count));
  AKB_CURVE_SET(AKB_PY_CURVE_DEGREE, PyLong_FromUnsignedLong(curve->degree));
  AKB_CURVE_SET(AKB_PY_CURVE_CLOSED, PyBool_FromLong(curve->closed));
  AKB_CURVE_SET(AKB_PY_CURVE_HAS_NODE, PyBool_FromLong(curve->has_node));
  AKB_CURVE_SET(AKB_PY_CURVE_NODE_INDEX, PyLong_FromLong(curve->node_index));
  AKB_CURVE_SET(AKB_PY_CURVE_MATRIX_F32,
                akb_memoryview_or_empty(curve->matrix,
                                        curve->has_node ? 16 * sizeof(float) : 0));
  AKB_CURVE_SET(AKB_PY_CURVE_COORD_MATRIX_F32,
                akb_memoryview_or_empty(curve->coord_matrix,
                                        curve->has_coord_matrix ? 16 * sizeof(float) : 0));
  AKB_CURVE_SET(AKB_PY_CURVE_POINTS_F32,
                akb_memoryview_or_empty(curve->points,
                                        (size_t)curve->point_count * 4 * sizeof(float)));
  AKB_CURVE_SET(AKB_PY_CURVE_GEOMETRY_EXTRA, akb_tree_to_py(curve->geometry_extra));
  AKB_CURVE_SET(AKB_PY_CURVE_CURVE_EXTRA, akb_tree_to_py(curve->curve_extra));

#undef AKB_CURVE_SET

  return tuple;
}

static PyObject *
akb_curve_list_to_py(AkbImport *import, PyObject *owner) {
  PyObject *list;
  PyObject *item;
  size_t i;

  list = PyList_New((Py_ssize_t)(import ? import->curves.count : 0));
  if (!list)
    return NULL;

  if (!import)
    return list;

  for (i = 0; i < import->curves.count; i++) {
    item = akb_curve_to_py(&import->curves.items[i], owner);
    if (!item) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, (Py_ssize_t)i, item);
  }

  return list;
}

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
                           NULL,
                           &material_prim,
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
  PyObject *tuple;
  PyObject *value;

  if (akb_primitive_is_simple_py(prim))
    return akb_primitive_simple_to_py(prim, owner);

  tuple = PyTuple_New(AKB_PY_PRIM_FIELD_COUNT);
  if (!tuple)
    return NULL;

#define AKB_SET_OBJ(INDEX, OBJ) do {               \
    value = (OBJ);                                 \
    if (!value) { Py_DECREF(tuple); return NULL; } \
    PyTuple_SET_ITEM(tuple, (INDEX), value);       \
  } while (0)

  Py_INCREF(owner);
  AKB_SET_OBJ(AKB_PY_PRIM_OWNER, owner);
  AKB_SET_OBJ(AKB_PY_PRIM_NAME, akb_unicode_from_cstr(prim->name));
  AKB_SET_OBJ(AKB_PY_PRIM_OBJECT_NAME, akb_unicode_from_cstr(prim->object_name));
  AKB_SET_OBJ(AKB_PY_PRIM_VERTEX_COUNT, PyLong_FromUnsignedLong(prim->vertex_count));
  AKB_SET_OBJ(AKB_PY_PRIM_LOOP_COUNT, PyLong_FromUnsignedLong(prim->loop_count));
  AKB_SET_OBJ(AKB_PY_PRIM_FACE_COUNT, PyLong_FromUnsignedLong(prim->face_count));
  AKB_SET_OBJ(AKB_PY_PRIM_PRIMITIVE_TYPE, PyLong_FromUnsignedLong(prim->primitive_type));
  AKB_SET_OBJ(AKB_PY_PRIM_PRIMITIVE_MODE, PyLong_FromUnsignedLong(prim->primitive_mode));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_NAME, akb_unicode_from_cstr(prim->material_name));
  AKB_SET_OBJ(AKB_PY_PRIM_BASE_COLOR,
              akb_vec4_or_none(prim->base_color, 1.0f, 1.0f, 1.0f, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSPARENT_COLOR,
              akb_vec4_or_none(prim->transparent_color, 1.0f, 1.0f, 1.0f, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_EMISSIVE_COLOR,
              akb_vec3_or_none(prim->emissive_color, 0.0f, 0.0f, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_SPECULAR_COLOR,
              akb_vec3_or_none(prim->specular_color, 1.0f, 1.0f, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_SHEEN_COLOR,
              akb_vec3_or_none(prim->sheen_color, 0.0f, 0.0f, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_ATTENUATION_COLOR,
              akb_vec3_or_none(prim->volume_attenuation_color, 1.0f, 1.0f, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_SCATTER_COLOR,
              akb_vec3_or_none(prim->volume_scatter_color, 0.0f, 0.0f, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_DIFFUSE_TRANSMISSION_COLOR,
              akb_vec3_or_none(prim->diffuse_transmission_color, 1.0f, 1.0f, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_METALLIC, akb_float_or_none(prim->metallic, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_ROUGHNESS, akb_float_or_none(prim->roughness, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_ALPHA_CUTOFF, akb_float_or_none(prim->alpha_cutoff, 0.5f));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSPARENT_AMOUNT, akb_float_or_none(prim->transparent_amount, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_OPACITY, akb_float_or_none(prim->opacity, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_NORMAL_SCALE, akb_float_or_none(prim->normal_scale, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_OCCLUSION_STRENGTH, akb_float_or_none(prim->occlusion_strength, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_EMISSIVE_STRENGTH, akb_float_or_none(prim->emissive_strength, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_SPECULAR_STRENGTH, akb_float_or_none(prim->specular_strength, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_IOR, akb_float_or_none(prim->ior, 1.5f));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT, akb_float_or_none(prim->clearcoat, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT_ROUGHNESS, akb_float_or_none(prim->clearcoat_roughness, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT_NORMAL_SCALE, akb_float_or_none(prim->clearcoat_normal_scale, 1.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSMISSION, akb_float_or_none(prim->transmission, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_SHEEN_ROUGHNESS, akb_float_or_none(prim->sheen_roughness, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE, akb_float_or_none(prim->iridescence, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE_IOR, akb_float_or_none(prim->iridescence_ior, 1.3f));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE_THICKNESS_MINIMUM,
              akb_float_or_none(prim->iridescence_thickness_minimum, 100.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE_THICKNESS_MAXIMUM,
              akb_float_or_none(prim->iridescence_thickness_maximum, 400.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_THICKNESS, akb_float_or_none(prim->volume_thickness, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_ATTENUATION_DISTANCE,
              akb_float_or_none(prim->volume_attenuation_distance, INFINITY));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_SCATTER_ANISOTROPY,
              akb_float_or_none(prim->volume_scatter_anisotropy, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_ANISOTROPY, akb_float_or_none(prim->anisotropy, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_ANISOTROPY_ROTATION, akb_float_or_none(prim->anisotropy_rotation, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_DIFFUSE_TRANSMISSION, akb_float_or_none(prim->diffuse_transmission, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_DISPERSION, akb_float_or_none(prim->dispersion, 0.0f));
  AKB_SET_OBJ(AKB_PY_PRIM_ALPHA_MODE, PyLong_FromUnsignedLong(prim->alpha_mode));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSPARENT_INVERTED, PyBool_FromLong(prim->transparent_inverted));
  AKB_SET_OBJ(AKB_PY_PRIM_DOUBLE_SIDED, PyBool_FromLong(prim->double_sided));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_TYPE, PyLong_FromUnsignedLong(prim->material_type));
  AKB_SET_OBJ(AKB_PY_PRIM_FILE_TYPE, PyLong_FromUnsignedLong(prim->file_type));
  AKB_SET_OBJ(AKB_PY_PRIM_MESH_KEY,
              PyLong_FromUnsignedLongLong((unsigned long long)prim->mesh_key));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_KEY,
              PyLong_FromUnsignedLongLong((unsigned long long)prim->material_key));
  AKB_SET_OBJ(AKB_PY_PRIM_PRIMITIVE_INDEX, PyLong_FromUnsignedLong(prim->primitive_index));
  AKB_SET_OBJ(AKB_PY_PRIM_HAS_NODE, PyBool_FromLong(prim->has_node));
  AKB_SET_OBJ(AKB_PY_PRIM_NODE_INDEX, PyLong_FromLong(prim->node_index));
  AKB_SET_OBJ(AKB_PY_PRIM_INSTANCE_COUNT, PyLong_FromUnsignedLong(prim->instance_count));
  AKB_SET_OBJ(AKB_PY_PRIM_HAS_GSPLAT, PyBool_FromLong(prim->has_gsplat));
  AKB_SET_OBJ(AKB_PY_PRIM_GSPLAT_KERNEL, PyLong_FromUnsignedLong(prim->gsplat.kernel));
  AKB_SET_OBJ(AKB_PY_PRIM_GSPLAT_COLOR_SPACE, PyLong_FromUnsignedLong(prim->gsplat.color_space));
  AKB_SET_OBJ(AKB_PY_PRIM_GSPLAT_PROJECTION, PyLong_FromUnsignedLong(prim->gsplat.projection));
  AKB_SET_OBJ(AKB_PY_PRIM_GSPLAT_SORTING_METHOD,
              PyLong_FromUnsignedLong(prim->gsplat.sorting_method));
  AKB_SET_OBJ(AKB_PY_PRIM_GSPLAT_DECODED_COUNT,
              PyLong_FromUnsignedLong(prim->gsplat.decoded_count));
  AKB_SET_OBJ(AKB_PY_PRIM_HAS_SKIN, PyBool_FromLong(prim->has_skin));
  AKB_SET_OBJ(AKB_PY_PRIM_HAS_SHEEN, PyBool_FromLong(prim->has_sheen));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_VERTEX_COUNT, PyLong_FromUnsignedLong(prim->skin_vertex_count));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_JOINT_COUNT, PyLong_FromUnsignedLong(prim->skin_joint_count));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_JOINT_WIDTH, PyLong_FromUnsignedLong(prim->skin_joint_width));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_ROOT_NODE_INDEX, PyLong_FromLong(prim->skin_root_node_index));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_MESH_IN_BIND_POSE,
              PyBool_FromLong(prim->skin_mesh_in_bind_pose));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_POSE_ANIM_CHANNELS, akb_skin_pose_anim_channels_to_py(prim));
  AKB_SET_OBJ(AKB_PY_PRIM_ZERO_COPY_FLAGS, PyLong_FromUnsignedLong(prim->zero_copy_flags));
  AKB_SET_OBJ(AKB_PY_PRIM_UV_SET_COUNT, PyLong_FromUnsignedLong(prim->uv_set_count));
  AKB_SET_OBJ(AKB_PY_PRIM_COLOR_SET_COUNT, PyLong_FromUnsignedLong(prim->color_set_count));
  AKB_SET_OBJ(AKB_PY_PRIM_POINT_ATTR_COUNT, PyLong_FromUnsignedLong(prim->point_attr_count));
  AKB_SET_OBJ(AKB_PY_PRIM_ANIM_COUNT,
              PyLong_FromUnsignedLong(prim->animation
                                      ? (unsigned long)prim->animation->count
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_ANIM_CHANNELS, akb_anim_channels_to_py(prim->animation));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_TARGET_COUNT,
              PyLong_FromUnsignedLong(prim->morph_target_count));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_TARGETS, akb_morph_targets_to_py(prim));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_PRESET_COUNT,
              PyLong_FromUnsignedLong(prim->morph_preset_count));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_PRESETS, akb_morph_presets_to_py(prim));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_ANIM_COUNT,
              PyLong_FromUnsignedLong(prim->morph_animation
                                      ? (unsigned long)prim->morph_animation->count
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_MORPH_ANIM_CHANNELS, akb_anim_channels_to_py(prim->morph_animation));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_ANIM_COUNT,
              PyLong_FromUnsignedLong(prim->material_animation
                                      ? (unsigned long)prim->material_animation->count
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_ANIM_CHANNELS,
              akb_anim_channels_to_py(prim->material_animation));
  AKB_SET_OBJ(AKB_PY_PRIM_UV_SETS, akb_loop_float_attrs_to_py(prim->uv_sets,
                                                    prim->uv_set_count,
                                                    prim->loop_count));
  AKB_SET_OBJ(AKB_PY_PRIM_COLOR_SETS, akb_loop_float_attrs_to_py(prim->color_sets,
                                                       prim->color_set_count,
                                                       prim->loop_count));
  AKB_SET_OBJ(AKB_PY_PRIM_POINT_ATTRS, akb_loop_float_attrs_to_py(prim->point_attrs,
                                                        prim->point_attr_count,
                                                        prim->vertex_count));
  AKB_SET_OBJ(AKB_PY_PRIM_TEXTURE_INFOS, akb_texture_infos_to_py(prim->texture_infos,
                                                       prim->texture_info_count));
  AKB_SET_OBJ(AKB_PY_PRIM_PRIMITIVE_EXTRA, akb_tree_to_py(prim->primitive_extra));
  AKB_SET_OBJ(AKB_PY_PRIM_MESH_EXTRA, akb_tree_to_py(prim->mesh_extra));
  AKB_SET_OBJ(AKB_PY_PRIM_GEOMETRY_EXTRA, akb_tree_to_py(prim->geometry_extra));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_EXTRA, akb_tree_to_py(prim->material_extra));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_VARIANT_COUNT,
              PyLong_FromUnsignedLong(prim->material_variant_count));
  AKB_SET_OBJ(AKB_PY_PRIM_MATERIAL_VARIANTS, akb_material_variants_to_py(prim, owner));
  AKB_SET_OBJ(AKB_PY_PRIM_MATRIX_F32,
              akb_memoryview_or_empty(prim->matrix, prim->has_node ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_COORD_MATRIX_F32,
              akb_memoryview_or_empty(prim->coord_matrix,
                                      prim->has_coord_matrix ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_INSTANCE_MATRICES_F32,
              akb_memoryview_or_empty(prim->instance_matrices,
                                      prim->instance_count
                                      ? (size_t)prim->instance_count
                                        * 16
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_BASE_COLOR_TEXTURE, akb_unicode_from_cstr(prim->base_color_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_METALLIC_ROUGHNESS_TEXTURE,
              akb_unicode_from_cstr(prim->metallic_roughness_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_OCCLUSION_TEXTURE, akb_unicode_from_cstr(prim->occlusion_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_NORMAL_TEXTURE, akb_unicode_from_cstr(prim->normal_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_EMISSIVE_TEXTURE, akb_unicode_from_cstr(prim->emissive_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSPARENT_TEXTURE,
              akb_unicode_from_cstr(prim->transparent_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_SPECULAR_TEXTURE, akb_unicode_from_cstr(prim->specular_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_SPECULAR_COLOR_TEXTURE,
              akb_unicode_from_cstr(prim->specular_color_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT_TEXTURE, akb_unicode_from_cstr(prim->clearcoat_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT_ROUGHNESS_TEXTURE,
              akb_unicode_from_cstr(prim->clearcoat_roughness_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_CLEARCOAT_NORMAL_TEXTURE,
              akb_unicode_from_cstr(prim->clearcoat_normal_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_TRANSMISSION_TEXTURE,
              akb_unicode_from_cstr(prim->transmission_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_SHEEN_COLOR_TEXTURE,
              akb_unicode_from_cstr(prim->sheen_color_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_SHEEN_ROUGHNESS_TEXTURE,
              akb_unicode_from_cstr(prim->sheen_roughness_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE_TEXTURE,
              akb_unicode_from_cstr(prim->iridescence_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_IRIDESCENCE_THICKNESS_TEXTURE,
              akb_unicode_from_cstr(prim->iridescence_thickness_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_VOLUME_THICKNESS_TEXTURE,
              akb_unicode_from_cstr(prim->volume_thickness_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_ANISOTROPY_TEXTURE, akb_unicode_from_cstr(prim->anisotropy_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_DIFFUSE_TRANSMISSION_TEXTURE,
              akb_unicode_from_cstr(prim->diffuse_transmission_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_DIFFUSE_TRANSMISSION_COLOR_TEXTURE,
              akb_unicode_from_cstr(prim->diffuse_transmission_color_texture));
  AKB_SET_OBJ(AKB_PY_PRIM_VERTICES_F32,
              akb_memoryview_or_empty(prim->vertices,
                                      (size_t)prim->vertex_count * 3 * sizeof(float)));
  AKB_SET_OBJ(AKB_PY_PRIM_INDICES_U32,
              akb_memoryview_or_empty(prim->indices,
                                      (size_t)prim->loop_count * sizeof(uint32_t)));
  AKB_SET_OBJ(AKB_PY_PRIM_LOOP_STARTS_I32,
              akb_memoryview_or_empty(prim->loop_starts,
                                      (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ(AKB_PY_PRIM_LOOP_TOTALS_I32,
              akb_memoryview_or_empty(prim->loop_totals,
                                      (size_t)prim->face_count * sizeof(int32_t)));
  AKB_SET_OBJ(AKB_PY_PRIM_NORMALS_F32,
              akb_memoryview_or_empty(prim->normals,
                                      prim->has_normals
                                      ? (size_t)prim->loop_count * 3 * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_VERTEX_NORMALS_F32,
              akb_memoryview_or_empty(prim->vertex_normals,
                                      prim->has_vertex_normals
                                      ? (size_t)prim->vertex_count * 3 * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_UVS_F32,
              akb_memoryview_or_empty(prim->uvs,
                                      prim->has_uvs
                                      ? (size_t)prim->loop_count * 2 * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_COLORS_F32,
              akb_memoryview_or_empty(prim->colors,
                                      prim->has_colors
                                      ? (size_t)prim->loop_count * 4 * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_TANGENTS_F32,
              akb_memoryview_or_empty(prim->tangents,
                                      prim->has_tangents
                                      ? (size_t)prim->loop_count
                                        * 4
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_JOINTS_U16,
              akb_memoryview_or_empty(prim->skin_joints,
                                      prim->has_skin
                                      ? (size_t)prim->skin_vertex_count
                                        * prim->skin_joint_width
                                        * sizeof(uint16_t)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_WEIGHTS_F32,
              akb_memoryview_or_empty(prim->skin_weights,
                                      prim->has_skin
                                      ? (size_t)prim->skin_vertex_count
                                        * prim->skin_joint_width
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_JOINT_NODES_I32,
              akb_memoryview_or_empty(prim->skin_joint_nodes,
                                      prim->has_skin
                                      ? (size_t)prim->skin_joint_count
                                        * sizeof(int32_t)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_INVERSE_BIND_MATRICES_F32,
              akb_memoryview_or_empty(prim->skin_inverse_bind_matrices,
                                      prim->has_skin && prim->skin_inverse_bind_matrices
                                      ? (size_t)prim->skin_joint_count
                                        * 16
                                        * sizeof(float)
                                      : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_SKIN_BIND_SHAPE_MATRIX_F32,
              akb_memoryview_or_empty(prim->skin_bind_shape_matrix,
                                      prim->has_skin ? 16 * sizeof(float) : 0));
  AKB_SET_OBJ(AKB_PY_PRIM_GEOMETRY_KEY,
              PyLong_FromUnsignedLongLong((unsigned long long)prim->geometry_key));
  AKB_SET_OBJ(AKB_PY_PRIM_EDGE_COUNT, PyLong_FromUnsignedLong(prim->edge_count));
  AKB_SET_OBJ(AKB_PY_PRIM_EDGES_U32,
              akb_memoryview_or_empty(prim->edges,
                                      (size_t)prim->edge_count * 2 * sizeof(uint32_t)));
  AKB_SET_OBJ(AKB_PY_PRIM_SMOOTH_SHADING, PyBool_FromLong(prim->smooth_shading));

#undef AKB_SET_OBJ

  return tuple;
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
  PyObject *tuple;
  PyObject *value;

  tuple = PyTuple_New(AKB_PY_NODE_FIELD_COUNT);
  if (!tuple)
    return NULL;

#define AKB_NODE_SET_OBJ(INDEX, OBJ) do {           \
    value = (OBJ);                                  \
    if (!value) { Py_DECREF(tuple); return NULL; }  \
    PyTuple_SET_ITEM(tuple, (INDEX), value);        \
  } while (0)

  Py_INCREF(owner);
  PyTuple_SET_ITEM(tuple, AKB_PY_NODE_OWNER, owner);
  AKB_NODE_SET_OBJ(AKB_PY_NODE_NAME,
                   node->name ? akb_unicode_from_cstr(node->name) : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_PARENT_INDEX, PyLong_FromLong(node->parent_index));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_VISIBLE, PyBool_FromLong(node->visible));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LAYERS,
                   node->layers && node->layers->count
                   ? akb_string_array_to_py(node->layers)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_CAMERA_TYPE, PyLong_FromUnsignedLong(node->camera_type));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_CAMERA_NAME,
                   node->camera_type
                   ? akb_unicode_from_cstr(node->camera_name)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_CAMERA_EXTRA,
                   node->camera_type && node->camera_extra
                   ? akb_tree_to_py(node->camera_extra)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_CAMERA_IMAGER_EXTRA,
                   node->camera_type && node->camera_imager_extra
                   ? akb_tree_to_py(node->camera_imager_extra)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_CAMERA_VALUES,
                   node->camera_type
                   ? Py_BuildValue("(ffffff)",
                                   node->camera_values[0],
                                   node->camera_values[1],
                                   node->camera_values[2],
                                   node->camera_values[3],
                                   node->camera_values[4],
                                   node->camera_values[5])
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LIGHT_TYPE, PyLong_FromUnsignedLong(node->light_type));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LIGHT_NAME,
                   node->light_type
                   ? akb_unicode_from_cstr(node->light_name)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LIGHT_EXTRA,
                   node->light_type && node->light_extra
                   ? akb_tree_to_py(node->light_extra)
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LIGHT_COLOR,
                   node->light_type
                   ? Py_BuildValue("(fff)",
                                   node->light_color[0],
                                   node->light_color[1],
                                   node->light_color[2])
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_LIGHT_VALUES,
                   node->light_type
                   ? Py_BuildValue("(fffff)",
                                   node->light_values[0],
                                   node->light_values[1],
                                   node->light_values[2],
                                   node->light_values[3],
                                   node->light_values[4])
                   : akb_none());
  AKB_NODE_SET_OBJ(AKB_PY_NODE_MATRIX_F32,
                   akb_memoryview_or_empty(node->matrix,
                                           node->has_transform ? 16 * sizeof(float) : 0));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_EXTRA, akb_tree_to_py(node->source ? ak_extra(node->source) : NULL));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_ANIM_COUNT,
                   PyLong_FromUnsignedLong(node->animation
                                           ? (unsigned long)node->animation->count
                                           : 0));
  AKB_NODE_SET_OBJ(AKB_PY_NODE_ANIM_CHANNELS, akb_anim_channels_to_py(node->animation));

#undef AKB_NODE_SET_OBJ

  return tuple;
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

static int
akb_scene_node_requires_object(const AkbSceneNode *node) {
  return node
         && (node->camera_type
             || node->light_type
             || node->camera_extra
             || node->camera_imager_extra
             || node->light_extra
             || (node->layers && node->layers->count)
             || (node->source && ak_extra(node->source)));
}

static void
akb_required_node_add_ancestors(uint8_t                *required,
                                const AkbSceneNodeList *nodes,
                                int32_t                 node_index) {
  size_t  count;
  int32_t current;
  int32_t remaining;

  if (!required || !nodes)
    return;

  count     = nodes->count;
  current   = node_index;
  remaining = (int32_t)count;
  while (current >= 0 && (size_t)current < count && remaining-- > 0) {
    required[current] = 1;
    current = nodes->items[current].parent_index;
  }
}

static void
akb_required_node_add_parent_ancestors(uint8_t                *required,
                                       const AkbSceneNodeList *nodes,
                                       int32_t                 node_index) {
  if (!nodes || node_index < 0 || (size_t)node_index >= nodes->count)
    return;

  akb_required_node_add_ancestors(required,
                                  nodes,
                                  nodes->items[node_index].parent_index);
}

static PyObject *
akb_required_node_indices_to_py(const AkbImport *import) {
  const AkbPrimitive *prim;
  const AkbCurve *curve;
  const AkbSceneNode *node;
  const AkbSceneNodeList *nodes;
  PyObject *list;
  PyObject *item;
  uint32_t *child_counts;
  uint8_t  *required;
  uint8_t  *primitive_nodes;
  uint8_t  *skip_animation;
  size_t    node_count;
  size_t    required_count;
  size_t    i;
  uint32_t  joint_count;
  int32_t   node_index;
  int32_t   parent_index;

  nodes = import ? &import->nodes : NULL;
  if (!nodes || nodes->count == 0)
    return PyList_New(0);

  node_count = nodes->count;
  child_counts = (uint32_t *)calloc(node_count, sizeof(*child_counts));
  required = (uint8_t *)calloc(node_count, sizeof(*required));
  primitive_nodes = (uint8_t *)calloc(node_count, sizeof(*primitive_nodes));
  skip_animation = (uint8_t *)calloc(node_count, sizeof(*skip_animation));
  if (!child_counts || !required || !primitive_nodes || !skip_animation) {
    free(skip_animation);
    free(primitive_nodes);
    free(required);
    free(child_counts);
    return PyErr_NoMemory();
  }

  for (i = 0; i < node_count; i++) {
    parent_index = nodes->items[i].parent_index;
    if (parent_index >= 0 && (size_t)parent_index < node_count)
      child_counts[parent_index]++;
  }

  for (i = 0; i < import->primitives.count; i++) {
    prim = &import->primitives.items[i];
    node_index = prim->node_index;
    if (node_index >= 0 && (size_t)node_index < node_count)
      primitive_nodes[node_index] = 1;

    if (!prim->has_skin || !prim->skin_mesh_in_bind_pose)
      continue;

    node_index = prim->skin_root_node_index;
    if (node_index >= 0 && (size_t)node_index < node_count)
      skip_animation[node_index] = 1;

    if (!prim->skin_joint_nodes)
      continue;

    joint_count = prim->skin_joint_count;
    for (uint32_t j = 0; j < joint_count; j++) {
      node_index = prim->skin_joint_nodes[j];
      if (node_index >= 0 && (size_t)node_index < node_count)
        skip_animation[node_index] = 1;
    }
  }

  for (i = 0; i < import->curves.count; i++) {
    curve = &import->curves.items[i];
    node_index = curve->node_index;
    if (node_index >= 0 && (size_t)node_index < node_count)
      primitive_nodes[node_index] = 1;
  }

  for (i = 0; i < import->primitives.count; i++) {
    prim = &import->primitives.items[i];
    node_index = prim->node_index;
    if (node_index >= 0
        && (size_t)node_index < node_count
        && (child_counts[node_index]
            || akb_scene_node_requires_object(&nodes->items[node_index]))) {
      akb_required_node_add_ancestors(required, nodes, node_index);
    } else {
      akb_required_node_add_parent_ancestors(required, nodes, node_index);
    }

    if (!prim->has_skin)
      continue;

    akb_required_node_add_ancestors(required,
                                    nodes,
                                    prim->skin_root_node_index);
    if (!prim->skin_mesh_in_bind_pose
        && prim->skin_joint_nodes
        && prim->skin_joint_count > 0) {
      joint_count = prim->skin_joint_count;
      for (uint32_t j = 0; j < joint_count; j++)
        akb_required_node_add_ancestors(required, nodes, prim->skin_joint_nodes[j]);
    }
  }

  for (i = 0; i < import->curves.count; i++) {
    curve = &import->curves.items[i];
    node_index = curve->node_index;
    if (node_index >= 0
        && (size_t)node_index < node_count
        && (child_counts[node_index]
            || akb_scene_node_requires_object(&nodes->items[node_index]))) {
      akb_required_node_add_ancestors(required, nodes, node_index);
    } else {
      akb_required_node_add_parent_ancestors(required, nodes, node_index);
    }
  }

  for (i = 0; i < node_count; i++) {
    node = &nodes->items[i];
    if (primitive_nodes[i]
        && !child_counts[i]
        && !akb_scene_node_requires_object(node)) {
      continue;
    }
    if (akb_scene_node_requires_object(node)
        || (!skip_animation[i]
            && node->animation
            && node->animation->count > 0)) {
      akb_required_node_add_ancestors(required, nodes, (int32_t)i);
    }
  }

  required_count = 0;
  for (i = 0; i < node_count; i++) {
    if (required[i])
      required_count++;
  }

  list = PyList_New((Py_ssize_t)required_count);
  if (!list) {
    free(skip_animation);
    free(primitive_nodes);
    free(required);
    free(child_counts);
    return NULL;
  }

  required_count = 0;
  for (i = 0; i < node_count; i++) {
    if (!required[i])
      continue;
    item = PyLong_FromSize_t(i);
    if (!item) {
      Py_DECREF(list);
      free(skip_animation);
      free(primitive_nodes);
      free(required);
      free(child_counts);
      return NULL;
    }
    PyList_SET_ITEM(list, (Py_ssize_t)required_count++, item);
  }

  free(skip_animation);
  free(primitive_nodes);
  free(required);
  free(child_counts);
  return list;
}
