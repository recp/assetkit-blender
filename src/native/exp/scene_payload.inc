static int
akb_export_payload_is_native_mesh(PyObject *payload_obj) {
  PyObject *tag_obj;
  unsigned long tag;
  Py_ssize_t size;

  if (!PyTuple_Check(payload_obj))
    return 0;
  size = PyTuple_Size(payload_obj);
  if (size != 5
      && size != 7
      && size != 8
      && size != 9
      && size != 10
      && size != 11
      && size != 12
      && size != 14
      && size != 15
      && size != 16
      && size != 17
      && size != 18)
    return 0;

  tag_obj = PyTuple_GET_ITEM(payload_obj, 0);
  tag = PyLong_AsUnsignedLong(tag_obj);
  if (PyErr_Occurred()) {
    PyErr_Clear();
    return 0;
  }
  return tag == AKB_EXPORT_NATIVE_MESH_PAYLOAD;
}

static int
akb_export_add_native_mesh_payload_to_node(AkDoc      *doc,
                                           AkNode     *node,
                                           const char *name,
                                           PyObject   *payload_obj,
                                           AkNode    **nodes,
                                           Py_ssize_t  node_count);

static int
akb_export_add_curve_object_to_node(AkDoc      *doc,
                                    AkNode     *node,
                                    const char *name,
                                    PyObject   *payload_obj);

static int
akb_export_add_mesh_object_to_node(AkDoc       *doc,
                                   AkNode      *node,
                                   const char  *name,
                                   PyObject    *payload_obj,
                                   AkNode     **nodes,
                                   Py_ssize_t   node_count) {
  AkHeap          *heap;
  AkGeometry      *geom;
  AkObject        *mesh_obj;
  AkMesh          *mesh;
  AkMeshPrimitive *last_prim;
  AkbExportMorphBuild morph_build;
  PyObject        *primitives_obj;
  PyObject        *morph_animation_obj;
  PyObject        *skin_obj;
  Py_ssize_t       primitive_count;
  Py_ssize_t       i;

  if (!doc || !node || !payload_obj)
    return 0;

  if (akb_export_payload_is_native_mesh(payload_obj))
    return akb_export_add_native_mesh_payload_to_node(doc,
                                                      node,
                                                      name,
                                                      payload_obj,
                                                      nodes,
                                                      node_count);

  primitives_obj = payload_obj;
  morph_animation_obj = Py_None;
  skin_obj = Py_None;
  if (PyTuple_Check(payload_obj)
      && (PyTuple_Size(payload_obj) == 2 || PyTuple_Size(payload_obj) == 3)) {
    primitives_obj = PyTuple_GET_ITEM(payload_obj, 0);
    morph_animation_obj = PyTuple_GET_ITEM(payload_obj, 1);
    if (!primitives_obj)
      return 0;
    if (!morph_animation_obj)
      morph_animation_obj = Py_None;
    if (PyTuple_Size(payload_obj) == 3) {
      skin_obj = PyTuple_GET_ITEM(payload_obj, 2);
      if (!skin_obj)
        skin_obj = Py_None;
    }
  }

  if (!PySequence_Check(primitives_obj)) {
    PyErr_SetString(PyExc_TypeError, "mesh primitive groups must be a sequence");
    return 0;
  }

  primitive_count = PySequence_Size(primitives_obj);
  if (primitive_count < 0)
    return 0;
  if (primitive_count == 0)
    return 1;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  geom = (AkGeometry *)ak_heap_calloc(heap, doc, sizeof(*geom));
  if (!geom)
    return 0;
  geom->name = name && name[0] ? name : NULL;
  ak_setypeid(geom, AKT_GEOMETRY);

  mesh_obj = ak_objAlloc(heap, geom, sizeof(*mesh), AK_GEOMETRY_MESH, true);
  if (!mesh_obj)
    return 0;
  geom->gdata = mesh_obj;
  mesh = (AkMesh *)ak_objGet(mesh_obj);
  mesh->geom = geom;
  mesh->name = name && name[0] ? name : NULL;

  last_prim = NULL;
  memset(&morph_build, 0, sizeof(morph_build));
  for (i = 0; i < primitive_count; i++) {
    PyObject *prim_item;
    PyObject *positions_obj;
    PyObject *normals_obj;
    PyObject *tangents_obj;
    PyObject *uvs_obj;
    PyObject *colors_obj;
    PyObject *indices_obj;
    PyObject *material_obj;
    PyObject *morph_positions_obj;
    PyObject *morph_names_obj;
    PyObject *morph_weights_obj;
    PyObject *joints_obj;
    PyObject *weights_obj;
    Py_ssize_t vertex_count_py;
    Py_buffer positions_view;
    Py_buffer normals_view;
    Py_buffer tangents_view;
    Py_buffer indices_view;
    Py_buffer joints_view;
    Py_buffer weights_view;
    AkMaterial *material;
    AkMeshPrimitive *prim;
    Py_ssize_t prim_item_size;
    int has_normals;
    int has_tangents;
    int has_indices;
    int has_joints;
    int has_weights;

    memset(&positions_view, 0, sizeof(positions_view));
    memset(&normals_view, 0, sizeof(normals_view));
    memset(&tangents_view, 0, sizeof(tangents_view));
    memset(&indices_view, 0, sizeof(indices_view));
    memset(&joints_view, 0, sizeof(joints_view));
    memset(&weights_view, 0, sizeof(weights_view));
    tangents_obj = Py_None;
    colors_obj = Py_None;
    indices_obj = Py_None;
    material_obj = Py_None;
    morph_positions_obj = Py_None;
    morph_names_obj = Py_None;
    morph_weights_obj = Py_None;
    joints_obj = Py_None;
    weights_obj = Py_None;
    material = NULL;

    prim_item = PySequence_GetItem(primitives_obj, i);
    if (!prim_item)
      return 0;

    prim_item_size = PySequence_Size(prim_item);
    if (prim_item_size != 11 && prim_item_size != 13) {
      PyErr_SetString(PyExc_ValueError, "AssetKit export primitive item must have eleven or thirteen fields");
      Py_DECREF(prim_item);
      return 0;
    }

    if (prim_item_size == 13) {
      if (!PyArg_ParseTuple(prim_item,
                            "OOOOOOnOOOOOO",
                            &positions_obj,
                            &normals_obj,
                            &tangents_obj,
                            &uvs_obj,
                            &colors_obj,
                            &indices_obj,
                            &vertex_count_py,
                            &material_obj,
                            &morph_positions_obj,
                            &morph_names_obj,
                            &morph_weights_obj,
                            &joints_obj,
                            &weights_obj)) {
        Py_DECREF(prim_item);
        return 0;
      }
    } else {
      if (!PyArg_ParseTuple(prim_item,
                            "OOOOOOnOOOO",
                            &positions_obj,
                            &normals_obj,
                            &tangents_obj,
                            &uvs_obj,
                            &colors_obj,
                            &indices_obj,
                            &vertex_count_py,
                            &material_obj,
                            &morph_positions_obj,
                            &morph_names_obj,
                            &morph_weights_obj)) {
        Py_DECREF(prim_item);
        return 0;
      }
    }

    has_normals = normals_obj != Py_None;
    has_tangents = tangents_obj != Py_None;
    has_indices = indices_obj != Py_None;
    has_joints = joints_obj != Py_None;
    has_weights = weights_obj != Py_None;
    if (has_joints != has_weights) {
      Py_DECREF(prim_item);
      PyErr_SetString(PyExc_ValueError, "skin joints and weights must be provided together");
      return 0;
    }

    if (vertex_count_py <= 0) {
      Py_DECREF(prim_item);
      continue;
    }

    if (PyObject_GetBuffer(positions_obj, &positions_view, PyBUF_SIMPLE) < 0) {
      Py_DECREF(prim_item);
      return 0;
    }
    if (has_normals && PyObject_GetBuffer(normals_obj, &normals_view, PyBUF_SIMPLE) < 0) {
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }
    if (has_tangents && PyObject_GetBuffer(tangents_obj, &tangents_view, PyBUF_SIMPLE) < 0) {
      if (has_normals)
        PyBuffer_Release(&normals_view);
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }
    if (has_indices && PyObject_GetBuffer(indices_obj, &indices_view, PyBUF_SIMPLE) < 0) {
      if (has_tangents)
        PyBuffer_Release(&tangents_view);
      if (has_normals)
        PyBuffer_Release(&normals_view);
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }

    material = akb_export_material(doc, material_obj);
    if (PyErr_Occurred()) {
      if (has_indices)
        PyBuffer_Release(&indices_view);
      if (has_tangents)
        PyBuffer_Release(&tangents_view);
      if (has_normals)
        PyBuffer_Release(&normals_view);
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }

    if (morph_positions_obj != Py_None) {
      Py_ssize_t morph_target_count;

      morph_target_count = PySequence_Size(morph_positions_obj);
      if (morph_target_count < 0) {
        if (has_indices)
          PyBuffer_Release(&indices_view);
        if (has_tangents)
          PyBuffer_Release(&tangents_view);
        if (has_normals)
          PyBuffer_Release(&normals_view);
        PyBuffer_Release(&positions_view);
        Py_DECREF(prim_item);
        return 0;
      }
      if (morph_target_count > 0) {
        if (morph_target_count > UINT32_MAX) {
          if (has_indices)
            PyBuffer_Release(&indices_view);
          if (has_tangents)
            PyBuffer_Release(&tangents_view);
          if (has_normals)
            PyBuffer_Release(&normals_view);
          PyBuffer_Release(&positions_view);
          Py_DECREF(prim_item);
          PyErr_SetString(PyExc_OverflowError, "too many morph targets");
          return 0;
        }
        if (!morph_build.morph
            && !akb_export_morph_begin(doc,
                                       &morph_build,
                                       morph_names_obj,
                                       morph_weights_obj,
                                       (uint32_t)morph_target_count)) {
          if (has_indices)
            PyBuffer_Release(&indices_view);
          if (has_tangents)
            PyBuffer_Release(&tangents_view);
          if (has_normals)
            PyBuffer_Release(&normals_view);
          PyBuffer_Release(&positions_view);
          Py_DECREF(prim_item);
          return 0;
        }
      }
    }

    if (has_joints && PyObject_GetBuffer(joints_obj, &joints_view, PyBUF_SIMPLE) < 0) {
      if (has_indices)
        PyBuffer_Release(&indices_view);
      if (has_tangents)
        PyBuffer_Release(&tangents_view);
      if (has_normals)
        PyBuffer_Release(&normals_view);
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }
    if (has_weights && PyObject_GetBuffer(weights_obj, &weights_view, PyBUF_SIMPLE) < 0) {
      if (has_joints)
        PyBuffer_Release(&joints_view);
      if (has_indices)
        PyBuffer_Release(&indices_view);
      if (has_tangents)
        PyBuffer_Release(&tangents_view);
      if (has_normals)
        PyBuffer_Release(&normals_view);
      PyBuffer_Release(&positions_view);
      Py_DECREF(prim_item);
      return 0;
    }

    prim = akb_export_add_primitive(
      doc,
      mesh_obj,
      mesh,
      positions_view.buf,
      (size_t)positions_view.len,
      has_normals ? normals_view.buf : NULL,
      has_normals ? (size_t)normals_view.len : 0,
      has_tangents ? tangents_view.buf : NULL,
      has_tangents ? (size_t)tangents_view.len : 0,
      uvs_obj,
      colors_obj,
      has_indices ? indices_view.buf : NULL,
      has_indices ? (size_t)indices_view.len : 0,
      has_joints ? joints_view.buf : NULL,
      has_joints ? (size_t)joints_view.len : 0,
      has_weights ? weights_view.buf : NULL,
      has_weights ? (size_t)weights_view.len : 0,
      (uint32_t)vertex_count_py,
      material);

    if (prim && morph_build.morph) {
      if (!akb_export_morph_add_primitive(doc,
                                          &morph_build,
                                          morph_positions_obj,
                                          (uint32_t)vertex_count_py)) {
        if (has_weights)
          PyBuffer_Release(&weights_view);
        if (has_joints)
          PyBuffer_Release(&joints_view);
        if (has_indices)
          PyBuffer_Release(&indices_view);
        if (has_tangents)
          PyBuffer_Release(&tangents_view);
        if (has_normals)
          PyBuffer_Release(&normals_view);
        PyBuffer_Release(&positions_view);
        Py_DECREF(prim_item);
        return 0;
      }
    }

    if (has_weights)
      PyBuffer_Release(&weights_view);
    if (has_joints)
      PyBuffer_Release(&joints_view);
    if (has_indices)
      PyBuffer_Release(&indices_view);
    if (has_tangents)
      PyBuffer_Release(&tangents_view);
    if (has_normals)
      PyBuffer_Release(&normals_view);
    PyBuffer_Release(&positions_view);
    Py_DECREF(prim_item);

    if (!prim)
      return 0;

    if (last_prim)
      last_prim->next = prim;
    else
      mesh->primitive = prim;
    last_prim = prim;
    mesh->primitiveCount++;
  }

  if (!mesh->primitive)
    return 1;

  AKB_LIB_APPEND(doc->lib.geometries, geom, next);

  {
    AkInstanceGeometry *instGeom;

    instGeom = ak_nodeAttachGeometry(node, geom);
    if (!instGeom)
      return 0;

    if (morph_build.morph) {
      AkInstanceMorph *morpher;

      morpher = (AkInstanceMorph *)ak_heap_calloc(heap, instGeom, sizeof(*morpher));
      if (!morpher)
        return 0;
      ak_setypeid(morpher, AKT_MORPH_INST);
      morpher->morph = morph_build.morph;
      instGeom->morpher = morpher;

      if (morph_animation_obj != Py_None
          && !akb_export_add_morph_weight_animation(doc, morpher, morph_animation_obj))
        return 0;
    }

    if (skin_obj != Py_None
        && !akb_export_add_skin_to_instance(doc,
                                            instGeom,
                                            mesh,
                                            skin_obj,
                                            nodes,
                                            node_count))
      return 0;
  }

  if (morph_build.morph && morph_build.primitiveCount != mesh->primitiveCount) {
    PyErr_SetString(PyExc_ValueError, "morph primitive count must match mesh primitive count");
    return 0;
  }

  return 1;
}

static int
akb_export_add_camera_object_to_node(AkDoc       *doc,
                                     AkNode      *node,
                                     const char  *name,
                                     PyObject    *payload_obj) {
  AkCamera *camera;
  int       projection_type;
  double    yfov;
  double    aspect;
  double    znear;
  double    zfar;
  double    xmag;
  double    ymag;
  PyObject *extra_obj;
  Py_ssize_t payload_size;

  if (!doc || !node)
    return 0;

  extra_obj = Py_None;
  payload_size = PyTuple_Check(payload_obj) ? PyTuple_Size(payload_obj) : -1;
  if (payload_size == 8) {
    if (!PyArg_ParseTuple(payload_obj,
                          "iddddddO",
                          &projection_type,
                          &yfov,
                          &aspect,
                          &znear,
                          &zfar,
                          &xmag,
                          &ymag,
                          &extra_obj))
      return 0;
  } else if (payload_size == 7) {
    if (!PyArg_ParseTuple(payload_obj,
                          "idddddd",
                          &projection_type,
                          &yfov,
                          &aspect,
                          &znear,
                          &zfar,
                          &xmag,
                          &ymag))
      return 0;
  } else {
    PyErr_SetString(PyExc_ValueError, "camera payload must have seven or eight fields");
    return 0;
  }

  if (projection_type == AK_PROJECTION_ORTHOGRAPHIC) {
    camera = ak_camMakeOrthographic(doc,
                                    NULL,
                                    (float)xmag,
                                    (float)ymag,
                                    (float)aspect,
                                    (float)znear,
                                    (float)zfar);
  } else {
    camera = ak_camMakePerspective(doc,
                                   NULL,
                                   (float)yfov,
                                   (float)aspect,
                                   (float)znear,
                                   (float)zfar);
  }
  if (!camera)
    return 0;
  camera->name = name && name[0] ? name : NULL;
  if (!akb_export_apply_object_extra(doc, camera, extra_obj))
    return 0;

  return ak_nodeAttachCamera(node, camera) != NULL;
}

static int
akb_export_add_light_object_to_node(AkDoc       *doc,
                                    AkNode      *node,
                                    const char  *name,
                                    PyObject    *payload_obj) {
  AkLight   *light;
  PyObject  *color_obj;
  Py_buffer  color_view;
  int        light_type;
  double     intensity;
  double     range;
  double     inner;
  double     outer;
  double     falloff;
  PyObject  *extra_obj;
  Py_ssize_t payload_size;

  if (!doc || !node)
    return 0;

  memset(&color_view, 0, sizeof(color_view));
  extra_obj = Py_None;
  payload_size = PyTuple_Check(payload_obj) ? PyTuple_Size(payload_obj) : -1;
  if (payload_size == 8) {
    if (!PyArg_ParseTuple(payload_obj,
                          "iOdddddO",
                          &light_type,
                          &color_obj,
                          &intensity,
                          &range,
                          &inner,
                          &outer,
                          &falloff,
                          &extra_obj))
      return 0;
  } else if (payload_size == 7) {
    if (!PyArg_ParseTuple(payload_obj,
                          "iOddddd",
                          &light_type,
                          &color_obj,
                          &intensity,
                          &range,
                          &inner,
                          &outer,
                          &falloff))
      return 0;
  } else {
    PyErr_SetString(PyExc_ValueError, "light payload must have seven or eight fields");
    return 0;
  }

  if (PyObject_GetBuffer(color_obj, &color_view, PyBUF_SIMPLE) < 0)
    return 0;
  if (color_view.len < (Py_ssize_t)(3u * sizeof(float))) {
    PyBuffer_Release(&color_view);
    PyErr_SetString(PyExc_ValueError, "light color buffer must hold three float values");
    return 0;
  }

  light = ak_lightMake(doc, NULL, (AkLightType)light_type);
  if (!light) {
    PyBuffer_Release(&color_view);
    return 0;
  }
  light->name = name && name[0] ? name : NULL;

  if (light->data) {
    const float *color;

    color = (const float *)color_view.buf;
    light->data->color.rgba.R = color[0];
    light->data->color.rgba.G = color[1];
    light->data->color.rgba.B = color[2];
    light->data->color.rgba.A = 1.0f;
    light->data->intensity = (float)intensity;
    light->data->range = (float)range;

    if (light->data->type == AK_LIGHT_TYPE_SPOT) {
      AkSpotLight *spot;

      spot = (AkSpotLight *)light->data;
      spot->innerConeAngle = (float)inner;
      spot->outerConeAngle = (float)outer;
      spot->coneFalloffExponent = (float)falloff;
    }
  }

  PyBuffer_Release(&color_view);
  if (!akb_export_apply_object_extra(doc, light, extra_obj))
    return 0;

  return ak_nodeAttachLight(node, light) != NULL;
}

static int
akb_export_add_gpu_instancing(AkDoc *doc, AkNode *node, PyObject *instancing_obj) {
  PyObject *matrices_obj;
  Py_buffer matrices_view;
  AkHeap *heap;
  AkGpuInstancing *instancing;
  float *translations;
  float *rotations;
  float *scales;
  Py_ssize_t count_py;
  size_t count;
  size_t required;
  int has_translation;
  int has_rotation;
  int has_scale;
  int ok;

  if (!doc || !node || !instancing_obj || instancing_obj == Py_None)
    return 1;

  memset(&matrices_view, 0, sizeof(matrices_view));
  if (!PyArg_ParseTuple(instancing_obj, "On", &matrices_obj, &count_py))
    return 0;
  if (count_py <= 1 || count_py > UINT32_MAX)
    return 1;

  count = (size_t)count_py;
  if (count > SIZE_MAX / (16u * sizeof(float))) {
    PyErr_SetString(PyExc_OverflowError, "instancing matrix payload is too large");
    return 0;
  }
  required = count * 16u * sizeof(float);
  if (PyObject_GetBuffer(matrices_obj, &matrices_view, PyBUF_SIMPLE) < 0)
    return 0;
  if ((size_t)matrices_view.len < required) {
    PyBuffer_Release(&matrices_view);
    PyErr_SetString(PyExc_ValueError, "instancing matrix buffer is smaller than declared count");
    return 0;
  }

  translations = (float *)malloc(count * 3u * sizeof(float));
  rotations    = (float *)malloc(count * 4u * sizeof(float));
  scales       = (float *)malloc(count * 3u * sizeof(float));
  if (!translations || !rotations || !scales) {
    free(scales);
    free(rotations);
    free(translations);
    PyBuffer_Release(&matrices_view);
    PyErr_NoMemory();
    return 0;
  }

  has_translation = 0;
  has_rotation = 0;
  has_scale = 0;
  for (size_t i = 0; i < count; i++) {
    const float *matrix;
    float *translation;
    float *rotation;
    float *scale;

    matrix = (const float *)matrices_view.buf + i * 16u;
    translation = translations + i * 3u;
    rotation = rotations + i * 4u;
    scale = scales + i * 3u;
    akb_mat4_to_trs(matrix, translation, AKB_VERSOR(rotation), scale);
    glm_quat_normalize(AKB_VERSOR(rotation));

    if (fabsf(translation[0]) > 1.0e-6f
        || fabsf(translation[1]) > 1.0e-6f
        || fabsf(translation[2]) > 1.0e-6f)
      has_translation = 1;
    if (fabsf(rotation[0]) > 1.0e-6f
        || fabsf(rotation[1]) > 1.0e-6f
        || fabsf(rotation[2]) > 1.0e-6f
        || fabsf(rotation[3] - 1.0f) > 1.0e-6f)
      has_rotation = 1;
    if (fabsf(scale[0] - 1.0f) > 1.0e-6f
        || fabsf(scale[1] - 1.0f) > 1.0e-6f
        || fabsf(scale[2] - 1.0f) > 1.0e-6f)
      has_scale = 1;
  }

  ok = 1;
  if (!has_translation && !has_rotation && !has_scale)
    goto done;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    ok = 0;
    goto done;
  }

  instancing = (AkGpuInstancing *)ak_heap_calloc(heap, node, sizeof(*instancing));
  if (!instancing) {
    ok = 0;
    goto done;
  }
  instancing->count = (uint32_t)count;

  if (has_translation) {
    AkBuffer *buff;

    buff = akb_export_buffer(heap, doc, instancing, translations, count * 3u * sizeof(float));
    instancing->translation = akb_export_accessor(heap,
                                                  doc,
                                                  buff,
                                                  AK_COMPONENT_SIZE_VEC3,
                                                  AKT_FLOAT,
                                                  3,
                                                  (uint32_t)count);
    if (!instancing->translation) {
      ok = 0;
      goto done;
    }
  }

  if (has_rotation) {
    AkBuffer *buff;

    buff = akb_export_buffer(heap, doc, instancing, rotations, count * 4u * sizeof(float));
    instancing->rotation = akb_export_accessor(heap,
                                               doc,
                                               buff,
                                               AK_COMPONENT_SIZE_VEC4,
                                               AKT_FLOAT,
                                               4,
                                               (uint32_t)count);
    if (!instancing->rotation) {
      ok = 0;
      goto done;
    }
  }

  if (has_scale) {
    AkBuffer *buff;

    buff = akb_export_buffer(heap, doc, instancing, scales, count * 3u * sizeof(float));
    instancing->scale = akb_export_accessor(heap,
                                            doc,
                                            buff,
                                            AK_COMPONENT_SIZE_VEC3,
                                            AKT_FLOAT,
                                            3,
                                            (uint32_t)count);
    if (!instancing->scale) {
      ok = 0;
      goto done;
    }
  }

  node->gpuInstancing = instancing;

done:
  free(scales);
  free(rotations);
  free(translations);
  PyBuffer_Release(&matrices_view);
  if (!ok && !PyErr_Occurred())
    PyErr_NoMemory();
  return ok;
}

typedef struct AkbExportSceneItem {
  PyObject *payload;
  PyObject *animation;
  PyObject *instancing;
  PyObject *nodeExtra;
  int       kind;
  int       has_animation;
} AkbExportSceneItem;

typedef struct AkbExportGeometryCacheEntry {
  PyObject   *payload;
  AkGeometry *geometry;
} AkbExportGeometryCacheEntry;

typedef struct AkbExportGeometryCache {
  AkbExportGeometryCacheEntry *entries;
  size_t                       mask;
} AkbExportGeometryCache;

static int
akb_export_mesh_payload_reusable(PyObject *payload_obj) {
  Py_ssize_t size;
  PyObject  *skin_mapping_obj;
  PyObject  *skin_obj;
  PyObject  *morph_obj;

  if (!akb_export_payload_is_native_mesh(payload_obj))
    return 0;

  size = PyTuple_Size(payload_obj);
  if (size < 0)
    return 0;

  skin_mapping_obj = size >= 7 ? PyTuple_GET_ITEM(payload_obj, 5) : Py_None;
  skin_obj = size >= 7 ? PyTuple_GET_ITEM(payload_obj, 6) : Py_None;
  morph_obj = size >= 8 ? PyTuple_GET_ITEM(payload_obj, 7) : Py_None;
  if ((size >= 10 && PyTuple_GET_ITEM(payload_obj, 9) != Py_None)
      || (size >= 11 && PyTuple_GET_ITEM(payload_obj, 10) != Py_None)
      || (size >= 12 && PyTuple_GET_ITEM(payload_obj, 11) != Py_None))
    return 0;

  return skin_mapping_obj == Py_None && skin_obj == Py_None && morph_obj == Py_None;
}

static AkGeometry *
akb_export_node_geometry(AkNode *node) {
  if (!node || !node->geometry)
    return NULL;
  return (AkGeometry *)ak_instanceObject(&node->geometry->base);
}

static size_t
akb_export_next_pow2_size(size_t value) {
  size_t out;

  out = 1u;
  while (out < value && out <= (SIZE_MAX >> 1u))
    out <<= 1u;
  return out;
}

static int
akb_export_geometry_cache_init(AkbExportGeometryCache *cache, Py_ssize_t item_count) {
  size_t capacity;

  if (!cache)
    return 0;
  cache->entries = NULL;
  cache->mask = 0;
  if (item_count <= 0)
    return 1;

  capacity = akb_export_next_pow2_size((size_t)item_count * 2u);
  if (capacity < 16u)
    capacity = 16u;
  cache->entries = (AkbExportGeometryCacheEntry *)calloc(capacity,
                                                         sizeof(*cache->entries));
  if (!cache->entries)
    return 0;
  cache->mask = capacity - 1u;
  return 1;
}

static void
akb_export_geometry_cache_free(AkbExportGeometryCache *cache) {
  if (!cache)
    return;
  free(cache->entries);
  cache->entries = NULL;
  cache->mask = 0;
}

static size_t
akb_export_geometry_cache_index(const AkbExportGeometryCache *cache,
                                PyObject                     *payload_obj) {
  uintptr_t ptr;

  ptr = (uintptr_t)payload_obj;
  return (size_t)((ptr >> 4u) ^ (ptr >> 12u)) & cache->mask;
}

static AkGeometry *
akb_export_geometry_cache_get(const AkbExportGeometryCache *cache,
                              PyObject                     *payload_obj) {
  size_t index;

  if (!cache || !cache->entries || !payload_obj || payload_obj == Py_None
      || !akb_export_mesh_payload_reusable(payload_obj))
    return NULL;

  index = akb_export_geometry_cache_index(cache, payload_obj);
  for (;;) {
    AkbExportGeometryCacheEntry *entry;

    entry = &cache->entries[index];
    if (!entry->payload)
      return NULL;
    if (entry->payload == payload_obj)
      return entry->geometry;
    index = (index + 1u) & cache->mask;
  }
}

static int
akb_export_geometry_cache_put(AkbExportGeometryCache *cache,
                              PyObject               *payload_obj,
                              AkGeometry             *geometry) {
  size_t index;

  if (!cache || !cache->entries || !payload_obj || !geometry
      || !akb_export_mesh_payload_reusable(payload_obj))
    return 0;

  index = akb_export_geometry_cache_index(cache, payload_obj);
  for (;;) {
    AkbExportGeometryCacheEntry *entry;

    entry = &cache->entries[index];
    if (!entry->payload || entry->payload == payload_obj) {
      entry->payload = payload_obj;
      entry->geometry = geometry;
      return 1;
    }
    index = (index + 1u) & cache->mask;
  }
}

static int
akb_export_attach_cached_geometry(AkNode *node, AkGeometry *geometry) {
  if (!node || !geometry)
    return 0;
  return ak_nodeAttachGeometry(node, geometry) != NULL;
}

static void
akb_export_scene_items_free(AkbExportSceneItem *items, Py_ssize_t count) {
  Py_ssize_t i;

  if (!items)
    return;

  for (i = 0; i < count; i++) {
    Py_XDECREF(items[i].payload);
    Py_XDECREF(items[i].animation);
    Py_XDECREF(items[i].instancing);
    Py_XDECREF(items[i].nodeExtra);
  }
  free(items);
}

static char *
akb_export_tree_strdup_py(AkHeap *heap, void *parent, PyObject *obj) {
  PyObject   *str_obj;
  const char *str;
  Py_ssize_t  len;
  char       *out;

  if (!obj || obj == Py_None)
    return NULL;

  str_obj = PyUnicode_Check(obj) ? obj : PyObject_Str(obj);
  if (!str_obj)
    return NULL;
  if (str_obj == obj)
    Py_INCREF(str_obj);

  str = PyUnicode_AsUTF8AndSize(str_obj, &len);
  if (!str) {
    Py_DECREF(str_obj);
    return NULL;
  }

  out = ak_heap_strndup(heap, parent, str, (size_t)len);
  Py_DECREF(str_obj);
  return out;
}

static int
akb_export_tree_append_attr(AkHeap *heap,
                            AkTreeNode *node,
                            PyObject *key_obj,
                            PyObject *val_obj,
                            AkTreeNodeAttr ***tail) {
  AkTreeNodeAttr *attr;

  attr = (AkTreeNodeAttr *)ak_heap_calloc(heap, node, sizeof(*attr));
  if (!attr)
    return 0;

  attr->name = akb_export_tree_strdup_py(heap, attr, key_obj);
  attr->val  = akb_export_tree_strdup_py(heap, attr, val_obj);
  if (!attr->name) {
    PyErr_SetString(PyExc_ValueError, "AssetKit extra attribute name is required");
    return 0;
  }

  **tail = attr;
  *tail = &attr->next;
  node->attrc++;
  return 1;
}

static AkTreeNode *
akb_export_tree_from_py(AkHeap *heap, void *parent, PyObject *obj) {
  PyObject       *name_obj;
  PyObject       *value_obj;
  PyObject       *attrs_obj;
  PyObject       *children_obj;
  PyObject       *seq;
  AkTreeNode     *node;
  AkTreeNode     *prev_child;
  AkTreeNodeAttr **attr_tail;
  Py_ssize_t      pos;
  Py_ssize_t      i;
  Py_ssize_t      count;
  PyObject       *key;
  PyObject       *val;

  if (!obj || obj == Py_None)
    return NULL;
  if (!PyDict_Check(obj)) {
    PyErr_SetString(PyExc_TypeError, "AssetKit extra tree node must be a dict");
    return NULL;
  }

  node = (AkTreeNode *)ak_heap_calloc(heap, parent, sizeof(*node));
  if (!node)
    return NULL;

  name_obj = PyDict_GetItemString(obj, "name");
  node->name = akb_export_tree_strdup_py(heap, node, name_obj);
  if (!node->name)
    node->name = ak_heap_strdup(heap, node, "item");

  value_obj = PyDict_GetItemString(obj, "value");
  node->val = akb_export_tree_strdup_py(heap, node, value_obj);

  attrs_obj = PyDict_GetItemString(obj, "attributes");
  if (attrs_obj && attrs_obj != Py_None) {
    if (!PyDict_Check(attrs_obj)) {
      PyErr_SetString(PyExc_TypeError, "AssetKit extra attributes must be a dict");
      return NULL;
    }

    attr_tail = &node->attribs;
    pos = 0;
    while (PyDict_Next(attrs_obj, &pos, &key, &val)) {
      if (!akb_export_tree_append_attr(heap, node, key, val, &attr_tail))
        return NULL;
    }
  }

  children_obj = PyDict_GetItemString(obj, "children");
  if (!children_obj || children_obj == Py_None)
    return node;

  seq = PySequence_Fast(children_obj, "AssetKit extra children must be a sequence");
  if (!seq)
    return NULL;

  prev_child = NULL;
  count = PySequence_Fast_GET_SIZE(seq);
  for (i = 0; i < count; i++) {
    AkTreeNode *child;

    child = akb_export_tree_from_py(heap,
                                    node,
                                    PySequence_Fast_GET_ITEM(seq, i));
    if (!child) {
      Py_DECREF(seq);
      return NULL;
    }

    child->parent = node;
    child->prev = prev_child;
    if (prev_child)
      prev_child->next = child;
    else
      node->chld = child;
    prev_child = child;
    node->chldc++;
  }

  Py_DECREF(seq);
  return node;
}

static int
akb_export_apply_doc_extra(AkDoc *doc, PyObject *extra_obj) {
  AkHeap *heap;
  AkTree *extra;

  if (!extra_obj || extra_obj == Py_None)
    return 1;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  extra = akb_export_tree_from_py(heap, doc, extra_obj);
  if (!extra)
    return 0;

  ak_extra_set(doc, extra);
  return 1;
}

static int
akb_export_apply_object_extra(AkDoc *doc, void *obj, PyObject *extra_obj) {
  AkHeap *heap;
  AkTree *extra;

  if (!extra_obj || extra_obj == Py_None)
    return 1;
  if (!doc || !obj)
    return 0;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  extra = akb_export_tree_from_py(heap, obj, extra_obj);
  if (!extra)
    return 0;

  ak_extra_set(obj, extra);
  return 1;
}

static int
akb_export_apply_direct_extra(AkDoc    *doc,
                              void     *parent,
                              AkTree  **slot,
                              PyObject *extra_obj) {
  AkHeap *heap;
  AkTree *extra;

  if (!extra_obj || extra_obj == Py_None)
    return 1;
  if (!doc || !slot)
    return 0;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  extra = akb_export_tree_from_py(heap, parent ? parent : doc, extra_obj);
  if (!extra)
    return 0;

  *slot = extra;
  return 1;
}
