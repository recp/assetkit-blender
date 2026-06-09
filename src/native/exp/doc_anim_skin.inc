static AkDoc *
akb_export_doc_new(const char *name, AkFileType file_type) {
  AkHeap  *heap;
  AkDoc   *doc;
  AkScene *scene;

  heap = ak_heap_new(NULL, NULL, NULL);
  if (!heap)
    return NULL;

  doc = (AkDoc *)ak_heap_calloc(heap, NULL, sizeof(*doc));
  if (!doc)
    return NULL;

  ak_heap_setdata(heap, doc);

  doc->inf = (AkDocInf *)ak_heap_calloc(heap, doc, sizeof(*doc->inf));
  if (!doc->inf)
    return NULL;
  doc->inf->name          = name && name[0] ? name : "model";
  doc->inf->ftype         = file_type;
  doc->inf->base.coordSys = AK_ZUP;
  doc->coordSys           = AK_ZUP;

  scene = (AkScene *)ak_heap_calloc(heap, doc, sizeof(*scene));
  if (!scene)
    return NULL;
  ak_setypeid(scene, AKT_SCENE);
  scene->name = name && name[0] ? name : "Scene";
  scene->node = (AkNode *)ak_heap_calloc(heap, scene, sizeof(*scene->node));
  if (!scene->node)
    return NULL;
  scene->node->visible = true;
  ak_setypeid(scene->node, AKT_NODE);

  AKB_LIB_APPEND(doc->lib.scenes, scene, next);
  doc->scene = scene;

  return doc;
}

static AkMeshPrimitive *
akb_export_add_primitive(AkDoc      *doc,
                         AkObject   *mesh_obj,
                         AkMesh     *mesh,
                         const void *positions,
                         size_t      positions_len,
                         const void *normals,
                         size_t      normals_len,
                         const void *tangents,
                         size_t      tangents_len,
                         PyObject   *uv_sets_obj,
                         PyObject   *color_sets_obj,
                         const void *indices,
                         size_t      indices_len,
                         const void *joints,
                         size_t      joints_len,
                         const void *weights,
                         size_t      weights_len,
                         uint32_t    vertex_count,
                         AkMaterial *material) {
  AkHeap          *heap;
  AkTriangles     *tri;
  AkMeshPrimitive *prim;
  size_t           index_count;

  if (!doc || !mesh_obj || !mesh || !positions || vertex_count == 0)
    return NULL;
  if (positions_len < (size_t)vertex_count * 3u * sizeof(float))
    return NULL;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return NULL;

  tri = (AkTriangles *)ak_heap_calloc(heap, mesh_obj, sizeof(*tri));
  if (!tri)
    return NULL;

  tri->mode       = AK_TRIANGLES;
  prim            = &tri->base;
  prim->mesh      = mesh;
  prim->type      = AK_PRIMITIVE_TRIANGLES;
  prim->material  = material;

  index_count = 0;
  if (indices) {
    if (indices_len < 3u * sizeof(uint32_t) || indices_len % sizeof(uint32_t) != 0) {
      PyErr_SetString(PyExc_ValueError, "mesh indices must be a uint32 triangle index buffer");
      return NULL;
    }
    index_count = indices_len / sizeof(uint32_t);
    prim->indices = akb_export_indices_from_u32(heap,
                                                prim,
                                                (const uint32_t *)indices,
                                                index_count,
                                                vertex_count);
    if (!prim->indices)
      return NULL;
  }

  prim->nPolygons = (uint32_t)((index_count ? index_count : vertex_count) / 3u);

  if (!akb_export_add_input_buffer(heap,
                                   doc,
                                   prim,
                                   positions,
                                   (size_t)vertex_count * 3u * sizeof(float),
                                   vertex_count,
                                   AK_COMPONENT_SIZE_VEC3,
                                   AKT_FLOAT,
                                   3,
                                   AK_INPUT_POSITION,
                                   "POSITION",
                                   0))
    return NULL;

  if (normals && normals_len >= (size_t)vertex_count * 3u * sizeof(float)) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     normals,
                                     normals_len,
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC3,
                                     AKT_FLOAT,
                                     3,
                                     AK_INPUT_NORMAL,
                                     "NORMAL",
                                     0))
      return NULL;
  }

  if (tangents && tangents_len >= (size_t)vertex_count * 4u * sizeof(float)) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     tangents,
                                     tangents_len,
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_FLOAT,
                                     4,
                                     AK_INPUT_TANGENT,
                                     "TANGENT",
                                     0))
      return NULL;
  }

  if (!akb_export_add_float_input_sequence(heap,
                                           doc,
                                           prim,
                                           uv_sets_obj,
                                           vertex_count,
                                           2,
                                           AK_COMPONENT_SIZE_VEC2,
                                           AK_INPUT_TEXCOORD,
                                           "TEXCOORD"))
    return NULL;

  if (!akb_export_add_float_input_sequence(heap,
                                           doc,
                                           prim,
                                           color_sets_obj,
                                           vertex_count,
                                           4,
                                           AK_COMPONENT_SIZE_VEC4,
                                           AK_INPUT_COLOR,
                                           "COLOR"))
    return NULL;

  if ((joints && !weights) || (!joints && weights)) {
    PyErr_SetString(PyExc_ValueError, "skin joints and weights must be provided together");
    return NULL;
  }

  if (joints && weights) {
    if (!akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     joints,
                                     joints_len,
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
                                     weights,
                                     weights_len,
                                     vertex_count,
                                     AK_COMPONENT_SIZE_VEC4,
                                     AKT_FLOAT,
                                     4,
                                     AK_INPUT_WEIGHT,
                                     "WEIGHTS",
                                     0))
      return NULL;
  }

  return prim;
}

static AkNode *
akb_export_add_node_child(AkDoc       *doc,
                          AkNode      *parent,
                          const char  *name,
                          const float  matrix[16],
                          int          force_trs);

static int
akb_export_set_node_trs_from_matrix(AkNode *node, const float matrix[16]) {
  AkHeap       *heap;
  AkObject     *translate_obj;
  AkObject     *rotation_obj;
  AkObject     *scale_obj;
  AkTranslate  *translate;
  AkQuaternion *rotation;
  AkScale      *scale;
  float         translation_value[3];
  float         scale_value[3];
  versor        rotation_value;

  if (!node)
    return 0;

  if (matrix) {
    akb_mat4_to_trs(matrix, translation_value, rotation_value, scale_value);
    glm_quat_normalize(rotation_value);
  } else {
    translation_value[0] = 0.0f;
    translation_value[1] = 0.0f;
    translation_value[2] = 0.0f;
    scale_value[0] = 1.0f;
    scale_value[1] = 1.0f;
    scale_value[2] = 1.0f;
    glm_quat_identity(rotation_value);
  }

  heap = ak_heap_getheap(node);
  if (!heap)
    return 0;

  if (!node->transform) {
    node->transform = ak_heap_calloc(heap, node, sizeof(*node->transform));
    if (!node->transform)
      return 0;
  }

  translate_obj = ak_objAlloc(heap, node, sizeof(*translate), AKT_TRANSLATE, true);
  rotation_obj  = ak_objAlloc(heap, node, sizeof(*rotation), AKT_QUATERNION, true);
  scale_obj     = ak_objAlloc(heap, node, sizeof(*scale), AKT_SCALE, true);
  if (!translate_obj || !rotation_obj || !scale_obj)
    return 0;

  translate = ak_objGet(translate_obj);
  rotation  = ak_objGet(rotation_obj);
  scale     = ak_objGet(scale_obj);
  memcpy(translate->val, translation_value, sizeof(translation_value));
  memcpy(rotation->val, rotation_value, sizeof(rotation_value));
  memcpy(scale->val, scale_value, sizeof(scale_value));

  translate_obj->next = rotation_obj;
  rotation_obj->next  = scale_obj;
  scale_obj->next     = NULL;
  node->transform->item = translate_obj;

  return 1;
}

static AkObject *
akb_export_node_transform_object(AkNode *node, AkTargetPropertyType target_type) {
  AkObject *obj;
  AkTypeId  type;

  if (!node || !node->transform)
    return NULL;

  switch (target_type) {
    case AK_TARGET_POSITION: type = AKT_TRANSLATE; break;
    case AK_TARGET_QUAT:     type = AKT_QUATERNION; break;
    case AK_TARGET_SCALE:    type = AKT_SCALE; break;
    default:                 return NULL;
  }

  for (obj = node->transform->item; obj; obj = obj->next) {
    if (obj->type == type)
      return obj;
  }

  return NULL;
}

static AkComponentSize
akb_export_anim_component_size(uint32_t component_count) {
  switch (component_count) {
    case 1: return AK_COMPONENT_SIZE_SCALAR;
    case 2: return AK_COMPONENT_SIZE_VEC2;
    case 3: return AK_COMPONENT_SIZE_VEC3;
    case 4: return AK_COMPONENT_SIZE_VEC4;
    default: break;
  }
  return AK_COMPONENT_SIZE_UNKNOWN;
}

static uint32_t
akb_export_anim_target_width(uint32_t target_type) {
  if (target_type == AKB_ANIM_VISIBILITY)
    return 1;

  if (target_type >= AKB_ANIM_TEXTURE_TRANSFORM_BASE) {
    uint32_t prop;

    prop = (target_type - AKB_ANIM_TEXTURE_TRANSFORM_BASE)
           % AKB_ANIM_TEXTURE_TRANSFORM_STRIDE;
    if (prop == AKB_ANIM_TEXTURE_TRANSFORM_OFFSET
        || prop == AKB_ANIM_TEXTURE_TRANSFORM_SCALE)
      return 2;
    if (prop == AKB_ANIM_TEXTURE_TRANSFORM_ROTATION)
      return 1;
    return 0;
  }

  switch (target_type) {
    case AK_TARGET_POSITION:
    case AK_TARGET_SCALE:
      return 3;
    case AK_TARGET_QUAT:
      return 4;
    case AKB_ANIM_MATERIAL_BASE_COLOR:
      return 4;
    case AKB_ANIM_MATERIAL_EMISSIVE_COLOR:
    case AKB_ANIM_MATERIAL_SPECULAR_COLOR:
    case AKB_ANIM_MATERIAL_SHEEN_COLOR:
    case AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR:
    case AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR:
      return 3;
    case AKB_ANIM_MATERIAL_METALLIC:
    case AKB_ANIM_MATERIAL_ROUGHNESS:
    case AKB_ANIM_MATERIAL_ALPHA_CUTOFF:
    case AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH:
    case AKB_ANIM_MATERIAL_NORMAL_SCALE:
    case AKB_ANIM_MATERIAL_OCCLUSION_STRENGTH:
    case AKB_ANIM_MATERIAL_SPECULAR:
    case AKB_ANIM_MATERIAL_IOR:
    case AKB_ANIM_MATERIAL_CLEARCOAT:
    case AKB_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS:
    case AKB_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE:
    case AKB_ANIM_MATERIAL_TRANSMISSION:
    case AKB_ANIM_MATERIAL_SHEEN_ROUGHNESS:
    case AKB_ANIM_MATERIAL_IRIDESCENCE:
    case AKB_ANIM_MATERIAL_IRIDESCENCE_IOR:
    case AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM:
    case AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM:
    case AKB_ANIM_MATERIAL_VOLUME_THICKNESS:
    case AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE:
    case AKB_ANIM_MATERIAL_ANISOTROPY:
    case AKB_ANIM_MATERIAL_ANISOTROPY_ROTATION:
    case AKB_ANIM_MATERIAL_DISPERSION:
    case AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION:
      return 1;
    default:
      break;
  }
  return 0;
}

static AkInput *
akb_export_anim_sampler_input(AkHeap         *heap,
                              AkAnimSampler  *sampler,
                              AkAccessor     *acc,
                              AkInputSemantic semantic) {
  AkInput *input;

  if (!heap || !sampler || !acc)
    return NULL;

  input = ak_heap_calloc(heap, sampler, sizeof(*input));
  if (!input)
    return NULL;

  input->accessor = acc;
  input->semantic = semantic;
  input->next     = sampler->input;
  sampler->input  = input;

  if (semantic == AK_INPUT_INPUT)
    sampler->inputInput = input;
  else if (semantic == AK_INPUT_OUTPUT)
    sampler->outputInput = input;

  return input;
}

static int
akb_export_add_transform_animation_channel(AkDoc       *doc,
                                           AkAnimation *animation,
                                           AkNode      *node,
                                           PyObject    *channel_obj) {
  AkHeap *heap;
  PyObject *times_obj;
  PyObject *values_obj;
  Py_buffer times_view;
  Py_buffer values_view;
  AkAnimSampler *sampler;
  AkChannel *channel;
  AkResolvedTarget *resolved;
  AkBuffer *times_buffer;
  AkBuffer *values_buffer;
  AkAccessor *times_accessor;
  AkAccessor *values_accessor;
  void *target_ptr;
  Py_ssize_t count_py;
  size_t times_len;
  size_t values_len;
  size_t value_component_size;
  uint32_t value_width;
  AkTypeId value_component_type;
  AkTargetPropertyType channel_target_type;
  int target_type_int;
  int interpolation_int;
  int ok;

  if (!doc || !animation || !node || !channel_obj)
    return 0;

  memset(&times_view, 0, sizeof(times_view));
  memset(&values_view, 0, sizeof(values_view));

  if (!PyArg_ParseTuple(channel_obj,
                        "iOOni",
                        &target_type_int,
                        &times_obj,
                        &values_obj,
                        &count_py,
                        &interpolation_int))
    return 0;

  if (count_py <= 0 || count_py > UINT32_MAX) {
    PyErr_SetString(PyExc_ValueError, "animation sample count is invalid");
    return 0;
  }

  value_width = akb_export_anim_target_width((AkTargetPropertyType)target_type_int);
  if (value_width == 0) {
    PyErr_SetString(PyExc_ValueError, "unsupported transform animation target");
    return 0;
  }

  if (target_type_int == AKB_ANIM_VISIBILITY) {
    target_ptr = &node->visible;
    channel_target_type = AK_TARGET_BOOL;
    value_component_type = AKT_UBYTE;
    value_component_size = sizeof(uint8_t);
  } else {
    target_ptr = akb_export_node_transform_object(node,
                                                  (AkTargetPropertyType)target_type_int);
    channel_target_type = (AkTargetPropertyType)target_type_int;
    value_component_type = AKT_FLOAT;
    value_component_size = sizeof(float);
    if (!target_ptr) {
      PyErr_SetString(PyExc_ValueError, "animation target transform is missing");
      return 0;
    }
  }

  if (PyObject_GetBuffer(times_obj, &times_view, PyBUF_SIMPLE) < 0)
    return 0;
  if (PyObject_GetBuffer(values_obj, &values_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&times_view);
    return 0;
  }

  times_len  = (size_t)count_py * sizeof(float);
  values_len = (size_t)count_py * value_width * value_component_size;
  if ((size_t)times_view.len < times_len || (size_t)values_view.len < values_len) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    PyErr_SetString(PyExc_ValueError, "animation buffer is smaller than declared sample count");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    return 0;
  }

  ok = 0;
  sampler = ak_heap_calloc(heap, animation, sizeof(*sampler));
  channel = ak_heap_calloc(heap, animation, sizeof(*channel));
  resolved = channel ? ak_heap_calloc(heap, channel, sizeof(*resolved)) : NULL;
  if (!sampler || !channel || !resolved)
    goto done;

  times_buffer = akb_export_buffer(heap, doc, sampler, times_view.buf, times_len);
  values_buffer = akb_export_buffer(heap, doc, sampler, values_view.buf, values_len);
  times_accessor = akb_export_accessor(heap,
                                       doc,
                                       times_buffer,
                                       AK_COMPONENT_SIZE_SCALAR,
                                       AKT_FLOAT,
                                       1,
                                       (uint32_t)count_py);
  values_accessor = akb_export_accessor(heap,
                                        doc,
                                        values_buffer,
                                        akb_export_anim_component_size(value_width),
                                        value_component_type,
                                        value_width,
                                        (uint32_t)count_py);
  if (!times_accessor || !values_accessor)
    goto done;

  if (!akb_export_anim_sampler_input(heap, sampler, times_accessor, AK_INPUT_INPUT)
      || !akb_export_anim_sampler_input(heap, sampler, values_accessor, AK_INPUT_OUTPUT))
    goto done;

  sampler->uniInterpolation = interpolation_int == AK_INTERPOLATION_STEP
                                ? AK_INTERPOLATION_STEP
                                : AK_INTERPOLATION_LINEAR;
  sampler->base.next = (void *)animation->sampler;
  animation->sampler = sampler;

  ak_setypeid(resolved, AKT_RESOLVED_TARGET);
  resolved->target = target_ptr;
  resolved->off = 0;
  resolved->isPartial = false;

  channel->resolvedTarget = resolved;
  channel->targetType = channel_target_type;
  channel->source.ptr = sampler;
  channel->next = animation->channel;
  animation->channel = channel;
  ok = 1;

done:
  PyBuffer_Release(&values_view);
  PyBuffer_Release(&times_view);
  if (!ok && !PyErr_Occurred())
    PyErr_NoMemory();
  return ok;
}

static int
akb_export_add_transform_animations(AkDoc    *doc,
                                    AkNode   *node,
                                    PyObject *animation_obj) {
  AkHeap *heap;
  AkAnimation *animation;
  PyObject *seq;
  Py_ssize_t count;
  Py_ssize_t i;
  int channel_count;

  if (!doc || !node || !animation_obj || animation_obj == Py_None)
    return 1;

  seq = PySequence_Fast(animation_obj, "animation payload must be a sequence");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count <= 0) {
    Py_DECREF(seq);
    return 1;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    Py_DECREF(seq);
    return 0;
  }

  animation = ak_heap_calloc(heap, doc, sizeof(*animation));
  if (!animation) {
    Py_DECREF(seq);
    PyErr_NoMemory();
    return 0;
  }
  animation->name = node->name;

  channel_count = 0;
  for (i = 0; i < count; i++) {
    PyObject *channel_obj;

    channel_obj = PySequence_Fast_GET_ITEM(seq, i);
    if (!akb_export_add_transform_animation_channel(doc,
                                                    animation,
                                                    node,
                                                    channel_obj)) {
      Py_DECREF(seq);
      return 0;
    }
    channel_count++;
  }

  Py_DECREF(seq);
  if (channel_count > 0)
    AKB_LIB_APPEND(doc->lib.animations, animation, next);

  return 1;
}

static AkTextureTransform *
akb_export_input_texture_transform(AkMaterialInput *input) {
  AkTextureRef *texref;

  texref = ak_materialInputTexture(input);
  return texref ? texref->transform : NULL;
}

static AkTextureTransform *
akb_export_material_feature_texture_transform(AkMaterialFeature *feature,
                                              uint32_t           role) {
  if (!feature)
    return NULL;

  switch (feature->type) {
    case AK_MATERIAL_FEATURE_SPECULAR: {
      AkMaterialSpecularFeature *f = (AkMaterialSpecularFeature *)feature;
      if (role == AKB_TEX_ROLE_SPECULAR)
        return akb_export_input_texture_transform(f->factor);
      if (role == AKB_TEX_ROLE_SPECULAR_COLOR)
        return akb_export_input_texture_transform(f->color);
      break;
    }
    case AK_MATERIAL_FEATURE_CLEARCOAT: {
      AkMaterialClearcoatFeature *f = (AkMaterialClearcoatFeature *)feature;
      if (role == AKB_TEX_ROLE_CLEARCOAT)
        return akb_export_input_texture_transform(f->factor);
      if (role == AKB_TEX_ROLE_CLEARCOAT_ROUGHNESS)
        return akb_export_input_texture_transform(f->roughness);
      if (role == AKB_TEX_ROLE_CLEARCOAT_NORMAL)
        return akb_export_input_texture_transform(f->normal);
      break;
    }
    case AK_MATERIAL_FEATURE_TRANSMISSION: {
      AkMaterialTransmissionFeature *f = (AkMaterialTransmissionFeature *)feature;
      if (role == AKB_TEX_ROLE_TRANSMISSION)
        return akb_export_input_texture_transform(f->factor);
      break;
    }
    case AK_MATERIAL_FEATURE_SHEEN: {
      AkMaterialSheenFeature *f = (AkMaterialSheenFeature *)feature;
      if (role == AKB_TEX_ROLE_SHEEN_COLOR)
        return akb_export_input_texture_transform(f->color);
      if (role == AKB_TEX_ROLE_SHEEN_ROUGHNESS)
        return akb_export_input_texture_transform(f->roughness);
      break;
    }
    case AK_MATERIAL_FEATURE_IRIDESCENCE: {
      AkMaterialIridescenceFeature *f = (AkMaterialIridescenceFeature *)feature;
      if (role == AKB_TEX_ROLE_IRIDESCENCE)
        return akb_export_input_texture_transform(f->factor);
      if (role == AKB_TEX_ROLE_IRIDESCENCE_THICKNESS)
        return akb_export_input_texture_transform(f->thickness);
      break;
    }
    case AK_MATERIAL_FEATURE_VOLUME: {
      AkMaterialVolumeFeature *f = (AkMaterialVolumeFeature *)feature;
      if (role == AKB_TEX_ROLE_VOLUME_THICKNESS)
        return akb_export_input_texture_transform(f->thickness);
      break;
    }
    case AK_MATERIAL_FEATURE_ANISOTROPY: {
      AkMaterialAnisotropyFeature *f = (AkMaterialAnisotropyFeature *)feature;
      if (role == AKB_TEX_ROLE_ANISOTROPY)
        return akb_export_input_texture_transform(f->strength);
      break;
    }
    case AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION: {
      AkMaterialDiffuseTransmissionFeature *f;
      f = (AkMaterialDiffuseTransmissionFeature *)feature;
      if (role == AKB_TEX_ROLE_DIFFUSE_TRANSMISSION)
        return akb_export_input_texture_transform(f->factor);
      if (role == AKB_TEX_ROLE_DIFFUSE_TRANSMISSION_COLOR)
        return akb_export_input_texture_transform(f->color);
      break;
    }
    default:
      break;
  }

  return NULL;
}

static AkTextureTransform *
akb_export_material_texture_transform(AkMaterial *mat, uint32_t role) {
  AkMaterialSurface *surface;
  AkMaterialFeature *feature;
  AkTextureTransform *transform;

  surface = mat ? mat->surface : NULL;
  if (!surface)
    return NULL;

  switch (role) {
    case AKB_TEX_ROLE_BASE_COLOR:
      return akb_export_input_texture_transform(surface->baseColor);
    case AKB_TEX_ROLE_METALLIC_ROUGHNESS:
      transform = akb_export_input_texture_transform(surface->metallic);
      return transform ? transform : akb_export_input_texture_transform(surface->roughness);
    case AKB_TEX_ROLE_OCCLUSION:
      return akb_export_input_texture_transform(surface->occlusion);
    case AKB_TEX_ROLE_NORMAL:
      return akb_export_input_texture_transform(surface->normal);
    case AKB_TEX_ROLE_EMISSIVE:
      return akb_export_input_texture_transform(surface->emissive);
    default:
      break;
  }

  for (feature = surface->features; feature; feature = feature->next) {
    transform = akb_export_material_feature_texture_transform(feature, role);
    if (transform)
      return transform;
  }

  return NULL;
}

static int
akb_export_material_anim_target(AkMaterial             *mat,
                                uint32_t                target,
                                void                  **ptr,
                                uint32_t               *off,
                                AkTargetPropertyType   *target_type,
                                uint32_t               *width) {
  uint32_t role;
  uint32_t prop;
  AkTextureTransform *transform;
  AkMaterialSurface *surface;

  if (!mat || !ptr || !off || !target_type || !width)
    return 0;

  surface = mat->surface;

#define AKB_MAT_ANIM_INPUT(INPUT, TYPE, WIDTH) do {                          \
    if (!(INPUT))                                                             \
      return 0;                                                               \
    *ptr = &(INPUT)->value[0];                                                \
    *off = target;                                                            \
    *target_type = (TYPE);                                                    \
    *width = (WIDTH);                                                         \
    return 1;                                                                \
  } while (0)

#define AKB_MAT_ANIM_FLOAT(FIELD) do {                                        \
    *ptr = &(FIELD);                                                          \
    *off = target;                                                            \
    *target_type = AK_TARGET_FLOAT;                                           \
    *width = 1;                                                               \
    return 1;                                                                \
  } while (0)

#define AKB_MAT_ANIM_COLOR(FIELD, WIDTH) do {                                 \
    *ptr = (FIELD).vec;                                                       \
    *off = target;                                                            \
    *target_type = AK_TARGET_COLOR;                                           \
    *width = (WIDTH);                                                         \
    return 1;                                                                \
  } while (0)

  if (target == AKB_ANIM_MATERIAL_BASE_COLOR) {
    if (!surface || !surface->baseColor)
      return 0;
    *ptr = surface->baseColor;
    *off = target;
    *target_type = AK_TARGET_COLOR;
    *width = 4;
    return 1;
  }

  if (!surface)
    return 0;

  switch (target) {
    case AKB_ANIM_MATERIAL_METALLIC:
      AKB_MAT_ANIM_INPUT(surface->metallic, AK_TARGET_FLOAT, 1);
    case AKB_ANIM_MATERIAL_ROUGHNESS:
      AKB_MAT_ANIM_INPUT(surface->roughness, AK_TARGET_FLOAT, 1);
    case AKB_ANIM_MATERIAL_ALPHA_CUTOFF:
      AKB_MAT_ANIM_FLOAT(surface->alphaCutoff);
    case AKB_ANIM_MATERIAL_EMISSIVE_COLOR:
      AKB_MAT_ANIM_INPUT(surface->emissive, AK_TARGET_COLOR, 3);
    case AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH:
      AKB_MAT_ANIM_FLOAT(surface->emissiveStrength);
    case AKB_ANIM_MATERIAL_NORMAL_SCALE:
      AKB_MAT_ANIM_INPUT(surface->normal, AK_TARGET_FLOAT, 1);
    case AKB_ANIM_MATERIAL_OCCLUSION_STRENGTH:
      AKB_MAT_ANIM_INPUT(surface->occlusion, AK_TARGET_FLOAT, 1);
    case AKB_ANIM_MATERIAL_IOR:
      AKB_MAT_ANIM_FLOAT(surface->ior);
    case AKB_ANIM_MATERIAL_SPECULAR: {
      AkMaterialSpecularFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR);
      AKB_MAT_ANIM_INPUT(f ? f->factor : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_SPECULAR_COLOR: {
      AkMaterialSpecularFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR);
      AKB_MAT_ANIM_INPUT(f ? f->color : NULL, AK_TARGET_COLOR, 3);
    }
    case AKB_ANIM_MATERIAL_CLEARCOAT: {
      AkMaterialClearcoatFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLEARCOAT);
      AKB_MAT_ANIM_INPUT(f ? f->factor : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS: {
      AkMaterialClearcoatFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLEARCOAT);
      AKB_MAT_ANIM_INPUT(f ? f->roughness : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE: {
      AkMaterialClearcoatFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLEARCOAT);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->normalScale);
    }
    case AKB_ANIM_MATERIAL_TRANSMISSION: {
      AkMaterialTransmissionFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_TRANSMISSION);
      AKB_MAT_ANIM_INPUT(f ? f->factor : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_SHEEN_COLOR: {
      AkMaterialSheenFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SHEEN);
      AKB_MAT_ANIM_INPUT(f ? f->color : NULL, AK_TARGET_COLOR, 3);
    }
    case AKB_ANIM_MATERIAL_SHEEN_ROUGHNESS: {
      AkMaterialSheenFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SHEEN);
      AKB_MAT_ANIM_INPUT(f ? f->roughness : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_IRIDESCENCE: {
      AkMaterialIridescenceFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
      AKB_MAT_ANIM_INPUT(f ? f->factor : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_IRIDESCENCE_IOR: {
      AkMaterialIridescenceFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->ior);
    }
    case AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM: {
      AkMaterialIridescenceFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->thicknessMinimum);
    }
    case AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM: {
      AkMaterialIridescenceFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->thicknessMaximum);
    }
    case AKB_ANIM_MATERIAL_VOLUME_THICKNESS: {
      AkMaterialVolumeFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_VOLUME);
      AKB_MAT_ANIM_INPUT(f ? f->thickness : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE: {
      AkMaterialVolumeFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_VOLUME);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->attenuationDistance);
    }
    case AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR: {
      AkMaterialVolumeFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_VOLUME);
      if (!f)
        return 0;
      AKB_MAT_ANIM_COLOR(f->attenuationColor, 3);
    }
    case AKB_ANIM_MATERIAL_ANISOTROPY: {
      AkMaterialAnisotropyFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_ANISOTROPY);
      AKB_MAT_ANIM_INPUT(f ? f->strength : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_ANISOTROPY_ROTATION: {
      AkMaterialAnisotropyFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_ANISOTROPY);
      AKB_MAT_ANIM_INPUT(f ? f->rotation : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_DISPERSION: {
      AkMaterialDispersionFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DISPERSION);
      if (!f)
        return 0;
      AKB_MAT_ANIM_FLOAT(f->dispersion);
    }
    case AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION: {
      AkMaterialDiffuseTransmissionFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION);
      AKB_MAT_ANIM_INPUT(f ? f->factor : NULL, AK_TARGET_FLOAT, 1);
    }
    case AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR: {
      AkMaterialDiffuseTransmissionFeature *f;
      f = (void *)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION);
      AKB_MAT_ANIM_INPUT(f ? f->color : NULL, AK_TARGET_COLOR, 3);
    }
    default:
      break;
  }

  if (target < AKB_ANIM_TEXTURE_TRANSFORM_BASE)
    return 0;

  role = (target - AKB_ANIM_TEXTURE_TRANSFORM_BASE)
         / AKB_ANIM_TEXTURE_TRANSFORM_STRIDE;
  prop = (target - AKB_ANIM_TEXTURE_TRANSFORM_BASE)
         % AKB_ANIM_TEXTURE_TRANSFORM_STRIDE;
  if (prop != AKB_ANIM_TEXTURE_TRANSFORM_OFFSET
      && prop != AKB_ANIM_TEXTURE_TRANSFORM_SCALE
      && prop != AKB_ANIM_TEXTURE_TRANSFORM_ROTATION)
    return 0;

  transform = akb_export_material_texture_transform(mat, role);
  if (!transform)
    return 0;

  *ptr = transform;
  *off = prop;
  *target_type = prop == AKB_ANIM_TEXTURE_TRANSFORM_ROTATION
                 ? AK_TARGET_FLOAT
                 : AK_TARGET_VEC2;
  *width = prop == AKB_ANIM_TEXTURE_TRANSFORM_ROTATION ? 1u : 2u;
  return 1;

#undef AKB_MAT_ANIM_COLOR
#undef AKB_MAT_ANIM_FLOAT
#undef AKB_MAT_ANIM_INPUT
}

static int
akb_export_add_material_animation_channel(AkDoc       *doc,
                                          AkAnimation *animation,
                                          AkMaterial  *mat,
                                          PyObject    *channel_obj) {
  AkHeap *heap;
  PyObject *times_obj;
  PyObject *values_obj;
  Py_buffer times_view;
  Py_buffer values_view;
  AkAnimSampler *sampler;
  AkChannel *channel;
  AkResolvedTarget *resolved;
  AkBuffer *times_buffer;
  AkBuffer *values_buffer;
  AkAccessor *times_accessor;
  AkAccessor *values_accessor;
  void *target_ptr;
  Py_ssize_t count_py;
  size_t times_len;
  size_t values_len;
  uint32_t target_off;
  uint32_t value_width;
  AkTargetPropertyType target_type;
  int target_int;
  int interpolation_int;
  int ok;

  if (!doc || !animation || !mat || !mat->surface || !channel_obj)
    return 0;

  memset(&times_view, 0, sizeof(times_view));
  memset(&values_view, 0, sizeof(values_view));

  if (!PyArg_ParseTuple(channel_obj,
                        "iOOni",
                        &target_int,
                        &times_obj,
                        &values_obj,
                        &count_py,
                        &interpolation_int))
    return 0;

  if (!akb_export_material_anim_target(mat,
                                       (uint32_t)target_int,
                                       &target_ptr,
                                       &target_off,
                                       &target_type,
                                       &value_width)) {
    PyErr_Format(PyExc_ValueError,
                 "unsupported material animation target: %d",
                 target_int);
    return 0;
  }

  if (count_py <= 0 || count_py > UINT32_MAX) {
    PyErr_SetString(PyExc_ValueError, "material animation sample count is invalid");
    return 0;
  }

  if (PyObject_GetBuffer(times_obj, &times_view, PyBUF_SIMPLE) < 0)
    return 0;
  if (PyObject_GetBuffer(values_obj, &values_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&times_view);
    return 0;
  }

  times_len  = (size_t)count_py * sizeof(float);
  values_len = (size_t)count_py * value_width * sizeof(float);
  if ((size_t)times_view.len < times_len || (size_t)values_view.len < values_len) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    PyErr_SetString(PyExc_ValueError, "material animation buffer is smaller than declared sample count");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    return 0;
  }

  ok = 0;
  sampler = ak_heap_calloc(heap, animation, sizeof(*sampler));
  channel = ak_heap_calloc(heap, animation, sizeof(*channel));
  resolved = channel ? ak_heap_calloc(heap, channel, sizeof(*resolved)) : NULL;
  if (!sampler || !channel || !resolved)
    goto done;

  times_buffer = akb_export_buffer(heap, doc, sampler, times_view.buf, times_len);
  values_buffer = akb_export_buffer(heap, doc, sampler, values_view.buf, values_len);
  times_accessor = akb_export_accessor(heap,
                                       doc,
                                       times_buffer,
                                       AK_COMPONENT_SIZE_SCALAR,
                                       AKT_FLOAT,
                                       1,
                                       (uint32_t)count_py);
  values_accessor = akb_export_accessor(heap,
                                        doc,
                                        values_buffer,
                                        akb_export_anim_component_size(value_width),
                                        AKT_FLOAT,
                                        value_width,
                                        (uint32_t)count_py);
  if (!times_accessor || !values_accessor)
    goto done;

  if (!akb_export_anim_sampler_input(heap, sampler, times_accessor, AK_INPUT_INPUT)
      || !akb_export_anim_sampler_input(heap, sampler, values_accessor, AK_INPUT_OUTPUT))
    goto done;

  sampler->uniInterpolation = interpolation_int == AK_INTERPOLATION_STEP
                                ? AK_INTERPOLATION_STEP
                                : AK_INTERPOLATION_LINEAR;
  sampler->base.next = (void *)animation->sampler;
  animation->sampler = sampler;

  ak_setypeid(resolved, AKT_RESOLVED_TARGET);
  resolved->target = target_ptr;
  resolved->off = target_off;
  resolved->isPartial = false;

  channel->resolvedTarget = resolved;
  channel->targetType = target_type;
  channel->source.ptr = sampler;
  channel->next = animation->channel;
  animation->channel = channel;
  ok = 1;

done:
  PyBuffer_Release(&values_view);
  PyBuffer_Release(&times_view);
  if (!ok && !PyErr_Occurred())
    PyErr_NoMemory();
  return ok;
}

static int
akb_export_add_material_animations(AkDoc      *doc,
                                   AkMaterial *mat,
                                   PyObject   *animation_obj) {
  AkHeap *heap;
  AkAnimation *animation;
  PyObject *seq;
  Py_ssize_t count;
  Py_ssize_t i;
  int channel_count;

  if (!doc || !mat || !animation_obj || animation_obj == Py_None)
    return 1;

  seq = PySequence_Fast(animation_obj, "material animation payload must be a sequence");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count <= 0) {
    Py_DECREF(seq);
    return 1;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    Py_DECREF(seq);
    return 0;
  }

  animation = ak_heap_calloc(heap, doc, sizeof(*animation));
  if (!animation) {
    Py_DECREF(seq);
    PyErr_NoMemory();
    return 0;
  }
  animation->name = mat->name;

  channel_count = 0;
  for (i = 0; i < count; i++) {
    PyObject *channel_obj;

    channel_obj = PySequence_Fast_GET_ITEM(seq, i);
    if (!akb_export_add_material_animation_channel(doc,
                                                   animation,
                                                   mat,
                                                   channel_obj)) {
      Py_DECREF(seq);
      return 0;
    }
    channel_count++;
  }

  Py_DECREF(seq);
  if (channel_count > 0)
    AKB_LIB_APPEND(doc->lib.animations, animation, next);

  return 1;
}

static int
akb_export_add_morph_weight_animation(AkDoc           *doc,
                                      AkInstanceMorph *morpher,
                                      PyObject        *animation_obj) {
  AkHeap *heap;
  PyObject *times_obj;
  PyObject *values_obj;
  Py_buffer times_view;
  Py_buffer values_view;
  AkAnimation *animation;
  AkAnimSampler *sampler;
  AkChannel *channel;
  AkResolvedTarget *resolved;
  AkBuffer *times_buffer;
  AkBuffer *values_buffer;
  AkAccessor *times_accessor;
  AkAccessor *values_accessor;
  Py_ssize_t count_py;
  Py_ssize_t target_count_py;
  size_t sample_count;
  size_t target_count;
  size_t times_len;
  size_t values_count;
  size_t values_len;
  int interpolation_int;
  int ok;

  if (!doc || !morpher || !morpher->morph
      || !animation_obj || animation_obj == Py_None)
    return 1;

  memset(&times_view, 0, sizeof(times_view));
  memset(&values_view, 0, sizeof(values_view));

  if (!PyArg_ParseTuple(animation_obj,
                        "OOnni",
                        &times_obj,
                        &values_obj,
                        &count_py,
                        &target_count_py,
                        &interpolation_int))
    return 0;

  if (count_py <= 0 || target_count_py <= 0
      || count_py > UINT32_MAX
      || target_count_py > UINT32_MAX
      || (uint32_t)target_count_py != morpher->morph->targetCount) {
    PyErr_SetString(PyExc_ValueError, "morph weight animation dimensions are invalid");
    return 0;
  }

  sample_count = (size_t)count_py;
  target_count = (size_t)target_count_py;
  if (sample_count > SIZE_MAX / target_count
      || sample_count * target_count > SIZE_MAX / sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "morph weight animation is too large");
    return 0;
  }
  values_count = sample_count * target_count;
  times_len = sample_count * sizeof(float);
  values_len = values_count * sizeof(float);

  if (PyObject_GetBuffer(times_obj, &times_view, PyBUF_SIMPLE) < 0)
    return 0;
  if (PyObject_GetBuffer(values_obj, &values_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&times_view);
    return 0;
  }
  if ((size_t)times_view.len < times_len || (size_t)values_view.len < values_len) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    PyErr_SetString(PyExc_ValueError, "morph weight animation buffer is too small");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    return 0;
  }

  ok = 0;
  animation = ak_heap_calloc(heap, doc, sizeof(*animation));
  sampler = animation ? ak_heap_calloc(heap, animation, sizeof(*sampler)) : NULL;
  channel = animation ? ak_heap_calloc(heap, animation, sizeof(*channel)) : NULL;
  resolved = channel ? ak_heap_calloc(heap, channel, sizeof(*resolved)) : NULL;
  if (!animation || !sampler || !channel || !resolved)
    goto done;

  times_buffer = akb_export_buffer(heap, doc, sampler, times_view.buf, times_len);
  values_buffer = akb_export_buffer(heap, doc, sampler, values_view.buf, values_len);
  times_accessor = akb_export_accessor(heap,
                                       doc,
                                       times_buffer,
                                       AK_COMPONENT_SIZE_SCALAR,
                                       AKT_FLOAT,
                                       1,
                                       (uint32_t)sample_count);
  values_accessor = akb_export_accessor(heap,
                                        doc,
                                        values_buffer,
                                        AK_COMPONENT_SIZE_SCALAR,
                                        AKT_FLOAT,
                                        1,
                                        (uint32_t)values_count);
  if (!times_accessor || !values_accessor)
    goto done;

  if (!akb_export_anim_sampler_input(heap, sampler, times_accessor, AK_INPUT_INPUT)
      || !akb_export_anim_sampler_input(heap, sampler, values_accessor, AK_INPUT_OUTPUT))
    goto done;

  sampler->uniInterpolation = interpolation_int == AK_INTERPOLATION_STEP
                                ? AK_INTERPOLATION_STEP
                                : AK_INTERPOLATION_LINEAR;
  sampler->base.next = (void *)animation->sampler;
  animation->sampler = sampler;

  ak_setypeid(resolved, AKT_RESOLVED_TARGET);
  resolved->target = morpher;
  resolved->off = 0;
  resolved->isPartial = false;

  channel->resolvedTarget = resolved;
  channel->targetType = AK_TARGET_WEIGHTS;
  channel->source.ptr = sampler;
  channel->next = animation->channel;
  animation->channel = channel;

  AKB_LIB_APPEND(doc->lib.animations, animation, next);
  ok = 1;

done:
  PyBuffer_Release(&values_view);
  PyBuffer_Release(&times_view);
  if (!ok && !PyErr_Occurred())
    PyErr_NoMemory();
  return ok;
}

static AkNode *
akb_export_add_node_child(AkDoc       *doc,
                          AkNode      *parent,
                          const char  *name,
                          const float  matrix[16],
                          int          force_trs) {
  AkNode *node;

  if (!doc || !doc->scene || !doc->scene->node)
    return NULL;

  node = ak_nodeMake(doc, parent ? parent : doc->scene->node, NULL);
  if (!node)
    return NULL;
  node->name = name && name[0] ? name : NULL;
  AKB_LIB_APPEND(doc->lib.nodes, node, docNext);
  if (force_trs) {
    if (!akb_export_set_node_trs_from_matrix(node, matrix))
      return NULL;
  } else if (matrix) {
    ak_nodeSetTransformMatrix(node, matrix);
  }

  return node;
}

static int
akb_export_add_skin_to_instance(AkDoc              *doc,
                                AkInstanceGeometry *instGeom,
                                AkMesh             *mesh,
                                PyObject           *skin_obj,
                                AkNode            **nodes,
                                Py_ssize_t          node_count) {
  AkHeap *heap;
  AkSkin *skin;
  AkInstanceSkin *skinner;
  PyObject *joint_indices_obj;
  PyObject *ibm_obj;
  PyObject *joint_indices_seq;
  Py_buffer ibm_view;
  Py_ssize_t joint_count;
  Py_ssize_t skeleton_index;
  Py_ssize_t i;
  size_t ibm_len;

  if (!doc || !instGeom || !mesh || !nodes)
    return 0;
  if (!skin_obj || skin_obj == Py_None)
    return 1;

  joint_indices_obj = NULL;
  ibm_obj = NULL;
  skeleton_index = -1;
  memset(&ibm_view, 0, sizeof(ibm_view));

  if (!PyArg_ParseTuple(skin_obj,
                        "OOn",
                        &joint_indices_obj,
                        &ibm_obj,
                        &skeleton_index))
    return 0;

  joint_indices_seq = PySequence_Fast(joint_indices_obj, "skin joints must be a sequence");
  if (!joint_indices_seq)
    return 0;

  joint_count = PySequence_Fast_GET_SIZE(joint_indices_seq);
  if (joint_count <= 0 || joint_count > UINT32_MAX) {
    Py_DECREF(joint_indices_seq);
    PyErr_SetString(PyExc_ValueError, "skin joint count is invalid");
    return 0;
  }

  if (PyObject_GetBuffer(ibm_obj, &ibm_view, PyBUF_SIMPLE) < 0) {
    Py_DECREF(joint_indices_seq);
    return 0;
  }

  ibm_len = (size_t)joint_count * sizeof(AkFloat4x4);
  if ((size_t)ibm_view.len < ibm_len) {
    PyBuffer_Release(&ibm_view);
    Py_DECREF(joint_indices_seq);
    PyErr_SetString(PyExc_ValueError, "skin inverse bind matrix buffer is too small");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyBuffer_Release(&ibm_view);
    Py_DECREF(joint_indices_seq);
    return 0;
  }

  skin = (AkSkin *)ak_heap_calloc(heap, doc, sizeof(*skin));
  if (!skin) {
    PyBuffer_Release(&ibm_view);
    Py_DECREF(joint_indices_seq);
    PyErr_NoMemory();
    return 0;
  }

  skin->joints = (AkNode **)ak_heap_calloc(heap,
                                           skin,
                                           sizeof(*skin->joints) * (size_t)joint_count);
  skin->invBindPoses = (AkFloat4x4 *)ak_heap_alloc(heap, skin, ibm_len);
  if (!skin->joints || !skin->invBindPoses) {
    PyBuffer_Release(&ibm_view);
    Py_DECREF(joint_indices_seq);
    PyErr_NoMemory();
    return 0;
  }

  for (i = 0; i < joint_count; i++) {
    PyObject   *index_obj;
    Py_ssize_t  node_index;

    index_obj = PySequence_Fast_GET_ITEM(joint_indices_seq, i);
    node_index = PyLong_AsSsize_t(index_obj);
    if (PyErr_Occurred()) {
      PyBuffer_Release(&ibm_view);
      Py_DECREF(joint_indices_seq);
      return 0;
    }
    if (node_index < 0 || node_index >= node_count || !nodes[node_index]) {
      PyBuffer_Release(&ibm_view);
      Py_DECREF(joint_indices_seq);
      PyErr_SetString(PyExc_ValueError, "skin joint index must reference a scene node");
      return 0;
    }
    skin->joints[i] = nodes[node_index];
  }

  memcpy(skin->invBindPoses, ibm_view.buf, ibm_len);
  PyBuffer_Release(&ibm_view);
  Py_DECREF(joint_indices_seq);

  if (skeleton_index >= 0 && skeleton_index < node_count)
    skin->skeleton = nodes[skeleton_index];
  else
    skin->skeleton = skin->joints[0];

  skin->nJoints = (size_t)joint_count;
  skin->nPrims = mesh->primitiveCount;
  skin->nMaxJoints = 4;
  glm_mat4_identity(skin->bindShapeMatrix);
  ak_setypeid(skin, AKT_SKIN);
  AKB_LIB_APPEND(doc->lib.skins, skin, next);

  skinner = (AkInstanceSkin *)ak_heap_calloc(heap, instGeom, sizeof(*skinner));
  if (!skinner) {
    PyErr_NoMemory();
    return 0;
  }
  skinner->skin = skin;
  instGeom->skinner = skinner;

  return 1;
}

