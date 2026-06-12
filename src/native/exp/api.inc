static int
akb_export_axis_vector(const char *axis, float out[3]) {
  float sign;
  char  name;

  if (!axis || !axis[0])
    axis = "Y";

  sign = 1.0f;
  if (axis[0] == '-') {
    sign = -1.0f;
    axis++;
  }

  name = axis[0];
  if ((name != 'X' && name != 'Y' && name != 'Z') || axis[1] != '\0')
    return 0;

  out[0] = 0.0f;
  out[1] = 0.0f;
  out[2] = 0.0f;
  out[name == 'X' ? 0 : name == 'Y' ? 1 : 2] = sign;
  return 1;
}

static int
akb_export_static_mesh_axis_matrix(float        scale,
                                   const char  *forward_axis,
                                   const char  *up_axis,
                                   float        matrix[16]) {
  float forward[3];
  float up[3];
  float right[3];

  if (!isfinite(scale) || scale <= 0.0f)
    scale = 1.0f;

  if (!akb_export_axis_vector(forward_axis, forward)
      || !akb_export_axis_vector(up_axis, up))
    return 0;
  if ((forward[0] != 0.0f && up[0] != 0.0f)
      || (forward[1] != 0.0f && up[1] != 0.0f)
      || (forward[2] != 0.0f && up[2] != 0.0f))
    return 0;

  glm_vec3_cross(forward, up, right);
  glm_mat4_identity(AKB_MAT4(matrix));

  matrix[0]  = right[0] * scale;
  matrix[1]  = right[1] * scale;
  matrix[2]  = right[2] * scale;

  matrix[4]  = forward[0] * scale;
  matrix[5]  = forward[1] * scale;
  matrix[6]  = forward[2] * scale;

  matrix[8]  = up[0] * scale;
  matrix[9]  = up[1] * scale;
  matrix[10] = up[2] * scale;
  return 1;
}

static PyObject *
akb_export_scene(PyObject *self, PyObject *args) {
  const char *out_dir;
  const char *name;
  int file_type_int;
  PyObject *items_obj;
  PyObject *doc_extra_obj;
  uintptr_t saved_dae_version;
  uintptr_t saved_dae_index_mode;
  uintptr_t saved_stl_export_format;
  uintptr_t saved_ply_export_format;
  uintptr_t saved_ply_export_normals;
  uintptr_t saved_ply_export_uv;
  uintptr_t saved_ply_export_color_mode;
  uintptr_t saved_ply_export_triangulated;
  uintptr_t saved_authoring_tool;
  const char *authoring_tool_fragment;
  const char *stl_forward_axis;
  const char *stl_up_axis;
  char authoring_tool[256];
  Py_ssize_t item_count;
  Py_ssize_t i;
  AkDoc *doc;
  AkNode **nodes;
  AkbExportSceneItem *scene_items;
  AkbExportGeometryCache geometry_cache;
  AkResult result;
  double total_started_at;
  double phase_started_at;
  double item_ms;
  double payload_ms;
  double coord_ms;
  double core_export_ms;
  int profile;
  int ok;
  int dae_version;
  int dae_index_mode;
  int stl_export_format;
  int ply_export_format;
  int ply_export_normals;
  int ply_export_uv;
  int ply_export_color_mode;
  int ply_export_triangulated;
  int export_coord_system_id;
  int export_coord_conversion_id;
  int set_dae_options;
  int set_stl_options;
  int set_ply_options;
  int set_authoring_tool;
  double stl_global_scale;
  AkCoordSys *export_coord;
  uint8_t export_coord_conversion;
  float stl_root_matrix[16];

  (void)self;
  memset(&geometry_cache, 0, sizeof(geometry_cache));

  doc_extra_obj = Py_None;
  dae_version = AK_DAE_EXPORT_VERSION_AUTO;
  dae_index_mode = AK_DAE_EXPORT_INDEX_AUTO;
  stl_export_format = AK_STL_EXPORT_BINARY;
  ply_export_format = AK_PLY_EXPORT_BINARY_LITTLE;
  ply_export_normals = 0;
  ply_export_uv = 1;
  ply_export_color_mode = AK_PLY_EXPORT_COLOR_SRGB;
  ply_export_triangulated = 0;
  export_coord_system_id = AKB_LOAD_COORD_Y_UP;
  export_coord_conversion_id = AKB_COORD_TRANSFORM;
  authoring_tool_fragment = NULL;
  stl_global_scale = 1.0;
  stl_forward_axis = "Y";
  stl_up_axis = "Z";
  if (!PyArg_ParseTuple(args,
                        "sisO|Oiiiiiiiiiisdss",
                        &out_dir,
                        &file_type_int,
                        &name,
                        &items_obj,
                        &doc_extra_obj,
                        &dae_version,
                        &dae_index_mode,
                        &export_coord_system_id,
                        &export_coord_conversion_id,
                        &stl_export_format,
                        &ply_export_format,
                        &ply_export_normals,
                        &ply_export_uv,
                        &ply_export_color_mode,
                        &ply_export_triangulated,
                        &authoring_tool_fragment,
                        &stl_global_scale,
                        &stl_forward_axis,
                        &stl_up_axis))
    return NULL;
  if (!PySequence_Check(items_obj)) {
    PyErr_SetString(PyExc_TypeError, "scene items must be a sequence");
    return NULL;
  }

  item_count = PySequence_Size(items_obj);
  if (item_count < 0)
    return NULL;

  profile = akb_profile_enabled();
  total_started_at = phase_started_at = profile ? akb_now_ms() : 0.0;
  item_ms = payload_ms = coord_ms = core_export_ms = 0.0;

  doc = akb_export_doc_new(name, (AkFileType)file_type_int);
  if (!doc)
    return PyErr_NoMemory();
  if (!akb_export_apply_doc_extra(doc, doc_extra_obj)) {
    ak_free(doc);
    if (!PyErr_Occurred())
      PyErr_SetString(PyExc_RuntimeError, "AssetKit Blender export bridge could not attach document extras");
    return NULL;
  }

  nodes = calloc((size_t)item_count, sizeof(*nodes));
  if (!nodes) {
    ak_free(doc);
    return PyErr_NoMemory();
  }
  scene_items = calloc((size_t)item_count, sizeof(*scene_items));
  if (!scene_items) {
    free(nodes);
    ak_free(doc);
    return PyErr_NoMemory();
  }
  if (!akb_export_geometry_cache_init(&geometry_cache, item_count)) {
    akb_export_scene_items_free(scene_items, item_count);
    free(nodes);
    ak_free(doc);
    return PyErr_NoMemory();
  }

  ok = 1;
  for (i = 0; i < item_count && ok; i++) {
    PyObject *item;
    Py_ssize_t item_size;
    const char *item_name;
    PyObject *matrix_obj;
    Py_buffer matrix_view;
    PyObject *payload_obj;
    PyObject *animation_obj;
    PyObject *instancing_obj;
    PyObject *node_extra_obj;
    PyObject *visible_obj;
    Py_ssize_t parent_index;
    AkNode *parent_node;
    AkNode *node;
    Py_ssize_t animation_count;
    int has_matrix;
    int has_animation;
    int visible;
    int kind;

    memset(&matrix_view, 0, sizeof(matrix_view));

    item = PySequence_GetItem(items_obj, i);
    if (!item) {
      ok = 0;
      break;
    }

    item_size = PySequence_Size(item);
    if (item_size != 6 && item_size != 7 && item_size != 8 && item_size != 9) {
      PyErr_SetString(PyExc_ValueError, "AssetKit export scene item must have six, seven, eight or nine fields");
      Py_DECREF(item);
      ok = 0;
      break;
    }

    instancing_obj = Py_None;
    node_extra_obj = Py_None;
    visible_obj = Py_True;
    if (item_size == 6) {
      if (!PyArg_ParseTuple(item,
                            "isOnOO",
                            &kind,
                            &item_name,
                            &matrix_obj,
                            &parent_index,
                            &payload_obj,
                            &animation_obj)) {
        Py_DECREF(item);
        ok = 0;
        break;
      }
    } else if (item_size == 7) {
      if (!PyArg_ParseTuple(item,
                            "isOnOOO",
                            &kind,
                            &item_name,
                            &matrix_obj,
                            &parent_index,
                            &payload_obj,
                            &animation_obj,
                            &instancing_obj)) {
        Py_DECREF(item);
        ok = 0;
        break;
      }
    } else if (item_size == 8) {
      if (!PyArg_ParseTuple(item,
                            "isOnOOOO",
                            &kind,
                            &item_name,
                            &matrix_obj,
                            &parent_index,
                            &payload_obj,
                            &animation_obj,
                            &instancing_obj,
                            &node_extra_obj)) {
        Py_DECREF(item);
        ok = 0;
        break;
      }
    } else {
      if (!PyArg_ParseTuple(item,
                            "isOnOOOOO",
                            &kind,
                            &item_name,
                            &matrix_obj,
                            &parent_index,
                            &payload_obj,
                            &animation_obj,
                            &instancing_obj,
                            &node_extra_obj,
                            &visible_obj)) {
        Py_DECREF(item);
        ok = 0;
        break;
      }
    }

    visible = PyObject_IsTrue(visible_obj);
    if (visible < 0) {
      Py_DECREF(item);
      ok = 0;
      break;
    }

    if (parent_index >= 0) {
      if (parent_index >= i || !nodes[parent_index]) {
        Py_DECREF(item);
        PyErr_SetString(PyExc_ValueError, "AssetKit export parent index must reference an earlier node");
        ok = 0;
        break;
      }
      parent_node = nodes[parent_index];
    } else {
      parent_node = doc->scene->node;
    }

    has_matrix = matrix_obj != Py_None;
    has_animation = 0;
    if (animation_obj != Py_None) {
      if (!PySequence_Check(animation_obj)) {
        Py_DECREF(item);
        PyErr_SetString(PyExc_TypeError, "animation payload must be a sequence");
        ok = 0;
        break;
      }
      animation_count = PySequence_Size(animation_obj);
      if (animation_count < 0) {
        Py_DECREF(item);
        ok = 0;
        break;
      }
      has_animation = animation_count > 0;
    }

    if (has_matrix && PyObject_GetBuffer(matrix_obj, &matrix_view, PyBUF_SIMPLE) < 0) {
      Py_DECREF(item);
      ok = 0;
      break;
    }

    node = akb_export_add_node_child(
      doc,
      parent_node,
      item_name,
      has_matrix && matrix_view.len >= (Py_ssize_t)(sizeof(float) * 16u)
        ? (const float *)matrix_view.buf
        : NULL,
      has_animation);

    if (!node) {
      ok = 0;
    } else if (kind != AKB_EXPORT_ITEM_NODE
               && kind != AKB_EXPORT_ITEM_MESH
               && kind != AKB_EXPORT_ITEM_CAMERA
               && kind != AKB_EXPORT_ITEM_LIGHT
               && kind != AKB_EXPORT_ITEM_JOINT
               && kind != AKB_EXPORT_ITEM_CURVE) {
      PyErr_SetString(PyExc_ValueError, "unknown AssetKit export scene item kind");
      ok = 0;
    } else {
      node->visible = visible != 0;
      if (kind == AKB_EXPORT_ITEM_JOINT)
        node->nodeType = AK_NODE_TYPE_JOINT;
      scene_items[i].kind = kind;
      scene_items[i].has_animation = has_animation;
      scene_items[i].payload = payload_obj;
      scene_items[i].animation = animation_obj;
      scene_items[i].instancing = instancing_obj;
      scene_items[i].nodeExtra = node_extra_obj;
      Py_INCREF(payload_obj);
      Py_INCREF(animation_obj);
      Py_INCREF(instancing_obj);
      Py_INCREF(node_extra_obj);
      if (!akb_export_apply_object_extra(doc, node, node_extra_obj))
        ok = 0;
      if (ok && !akb_export_add_gpu_instancing(doc, node, instancing_obj))
        ok = 0;
    }

    if (ok)
      nodes[i] = node;
    if (has_matrix)
      PyBuffer_Release(&matrix_view);
    Py_DECREF(item);
  }

  if (profile) {
    item_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  for (i = 0; i < item_count && ok; i++) {
    AkNode *node;

    node = nodes[i];
    if (!node)
      continue;

    switch (scene_items[i].kind) {
      case AKB_EXPORT_ITEM_NODE:
      case AKB_EXPORT_ITEM_JOINT:
        break;
      case AKB_EXPORT_ITEM_MESH:
      {
        AkGeometry *cached_geometry;

        cached_geometry = akb_export_geometry_cache_get(&geometry_cache,
                                                        scene_items[i].payload);
        if (cached_geometry) {
          ok = akb_export_attach_cached_geometry(node, cached_geometry);
        } else {
          ok = akb_export_add_mesh_object_to_node(doc,
                                                  node,
                                                  node->name,
                                                  scene_items[i].payload,
                                                  nodes,
                                                  item_count);
          if (ok && akb_export_mesh_payload_reusable(scene_items[i].payload)) {
            AkGeometry *geometry;

            geometry = akb_export_node_geometry(node);
            if (!geometry
                || !akb_export_geometry_cache_put(&geometry_cache,
                                                  scene_items[i].payload,
                                                  geometry))
              ok = 0;
          }
        }
        break;
      }
      case AKB_EXPORT_ITEM_CAMERA:
        ok = akb_export_add_camera_object_to_node(doc,
                                                  node,
                                                  node->name,
                                                  scene_items[i].payload);
        break;
      case AKB_EXPORT_ITEM_LIGHT:
        ok = akb_export_add_light_object_to_node(doc,
                                                 node,
                                                 node->name,
                                                 scene_items[i].payload);
        break;
      case AKB_EXPORT_ITEM_CURVE:
        ok = akb_export_add_curve_object_to_node(doc,
                                                 node,
                                                 node->name,
                                                 scene_items[i].payload);
        break;
      default:
        PyErr_SetString(PyExc_ValueError, "unknown AssetKit export scene item kind");
        ok = 0;
        break;
    }

    if (ok && scene_items[i].has_animation)
      ok = akb_export_add_transform_animations(doc,
                                               node,
                                               scene_items[i].animation);
  }

  if (profile) {
    payload_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  akb_export_scene_items_free(scene_items, item_count);
  scene_items = NULL;
  akb_export_geometry_cache_free(&geometry_cache);

  if (!ok) {
    free(nodes);
    ak_free(doc);
    if (!PyErr_Occurred())
      PyErr_SetString(PyExc_RuntimeError, "AssetKit Blender export bridge could not build document");
    return NULL;
  }

  free(nodes);

  if ((file_type_int == AK_FILE_TYPE_STL
       || file_type_int == AK_FILE_TYPE_PLY
       || file_type_int == AK_FILE_TYPE_WAVEFRONT)
      && (stl_global_scale != 1.0
          || strcmp(stl_forward_axis ? stl_forward_axis : "Y", "Y") != 0
          || strcmp(stl_up_axis ? stl_up_axis : "Z", "Z") != 0)) {
    if (!akb_export_static_mesh_axis_matrix((float)stl_global_scale,
                                            stl_forward_axis,
                                            stl_up_axis,
                                            stl_root_matrix)) {
      ak_free(doc);
      PyErr_SetString(PyExc_ValueError, "invalid mesh forward/up axis options");
      return NULL;
    }
    ak_nodeSetTransformMatrix(doc->scene->node, stl_root_matrix);
  }

  Py_BEGIN_ALLOW_THREADS
  export_coord = akb_coord_from_id(export_coord_system_id);
  export_coord_conversion = akb_conversion_from_id(export_coord_conversion_id);
  if (export_coord_conversion != AKB_COORD_RAW
      && export_coord
      && doc->coordSys != export_coord) {
    ak_changeCoordSys(doc, export_coord);
  }
  if (profile) {
    coord_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }
  set_dae_options = file_type_int == AK_FILE_TYPE_COLLADA;
  if (set_dae_options) {
    saved_dae_version = ak_opt_get(AK_OPT_DAE_EXPORT_VERSION);
    saved_dae_index_mode = ak_opt_get(AK_OPT_DAE_EXPORT_INDEX_MODE);
    ak_opt_set(AK_OPT_DAE_EXPORT_VERSION, (uintptr_t)dae_version);
    ak_opt_set(AK_OPT_DAE_EXPORT_INDEX_MODE, (uintptr_t)dae_index_mode);
  }
  set_stl_options = file_type_int == AK_FILE_TYPE_STL;
  if (set_stl_options) {
    saved_stl_export_format = ak_opt_get(AK_OPT_STL_EXPORT_FORMAT);
    ak_opt_set(AK_OPT_STL_EXPORT_FORMAT, (uintptr_t)stl_export_format);
  }
  set_ply_options = file_type_int == AK_FILE_TYPE_PLY;
  if (set_ply_options) {
    saved_ply_export_format = ak_opt_get(AK_OPT_PLY_EXPORT_FORMAT);
    saved_ply_export_normals = ak_opt_get(AK_OPT_PLY_EXPORT_NORMALS);
    saved_ply_export_uv = ak_opt_get(AK_OPT_PLY_EXPORT_UV);
    saved_ply_export_color_mode = ak_opt_get(AK_OPT_PLY_EXPORT_COLOR_MODE);
    saved_ply_export_triangulated = ak_opt_get(AK_OPT_PLY_EXPORT_TRIANGULATED);
    ak_opt_set(AK_OPT_PLY_EXPORT_FORMAT, (uintptr_t)ply_export_format);
    ak_opt_set(AK_OPT_PLY_EXPORT_NORMALS, (uintptr_t)(ply_export_normals != 0));
    ak_opt_set(AK_OPT_PLY_EXPORT_UV, (uintptr_t)(ply_export_uv != 0));
    ak_opt_set(AK_OPT_PLY_EXPORT_COLOR_MODE, (uintptr_t)ply_export_color_mode);
    ak_opt_set(AK_OPT_PLY_EXPORT_TRIANGULATED,
               (uintptr_t)(ply_export_triangulated != 0));
  }
  saved_authoring_tool = ak_opt_get(AK_OPT_EXPORT_AUTHORING_TOOL);
  set_authoring_tool = 0;
  if (authoring_tool_fragment && authoring_tool_fragment[0]) {
    snprintf(authoring_tool,
             sizeof(authoring_tool),
             "%s by %s",
             AK_AUTHORING_TOOL,
             authoring_tool_fragment);
    ak_opt_set(AK_OPT_EXPORT_AUTHORING_TOOL, (uintptr_t)authoring_tool);
    set_authoring_tool = 1;
  }
  result = ak_export(doc, out_dir, (AkFileType)file_type_int);
  if (set_authoring_tool)
    ak_opt_set(AK_OPT_EXPORT_AUTHORING_TOOL, saved_authoring_tool);
  if (set_dae_options) {
    ak_opt_set(AK_OPT_DAE_EXPORT_VERSION, saved_dae_version);
    ak_opt_set(AK_OPT_DAE_EXPORT_INDEX_MODE, saved_dae_index_mode);
  }
  if (set_stl_options)
    ak_opt_set(AK_OPT_STL_EXPORT_FORMAT, saved_stl_export_format);
  if (set_ply_options) {
    ak_opt_set(AK_OPT_PLY_EXPORT_FORMAT, saved_ply_export_format);
    ak_opt_set(AK_OPT_PLY_EXPORT_NORMALS, saved_ply_export_normals);
    ak_opt_set(AK_OPT_PLY_EXPORT_UV, saved_ply_export_uv);
    ak_opt_set(AK_OPT_PLY_EXPORT_COLOR_MODE, saved_ply_export_color_mode);
    ak_opt_set(AK_OPT_PLY_EXPORT_TRIANGULATED, saved_ply_export_triangulated);
  }
  if (profile)
    core_export_ms = akb_now_ms() - phase_started_at;
  Py_END_ALLOW_THREADS

  if (profile) {
    akb_profile_log("export_scene name=\"%s\" result=%d items=%zd item_parse=%.3fms payload=%.3fms coord=%.3fms core_export=%.3fms total=%.3fms",
                    name ? name : "",
                    result,
                    item_count,
                    item_ms,
                    payload_ms,
                    coord_ms,
                    core_export_ms,
                    akb_now_ms() - total_started_at);
  }

  ak_free(doc);
  return PyLong_FromLong((long)result);
}

#define AKB_EXPORT_FAST_UV_MAX 8u
#define AKB_EXPORT_FAST_COLOR_MAX 8u

typedef enum AkbExportFastAttrDomain {
  AKB_EXPORT_FAST_ATTR_CORNER = 0,
  AKB_EXPORT_FAST_ATTR_POINT = 1
} AkbExportFastAttrDomain;

typedef struct AkbExportFastVertex {
  uint8_t  used;
  uint32_t vertexIndex;
  uint32_t outIndex;
  float    position[3];
  float    normal[3];
  float    tangent[4];
  uint16_t joints[4];
  float    weights[4];
  float    uv[AKB_EXPORT_FAST_UV_MAX * 2u];
  float    color[AKB_EXPORT_FAST_COLOR_MAX * 4u];
} AkbExportFastVertex;

typedef struct AkbExportSkinVertexCache {
  uint8_t  filled;
  uint16_t joints[4];
  float    weights[4];
} AkbExportSkinVertexCache;

typedef struct AkbExportFastGroup {
  int                  materialIndex;
  float               *positions;
  float               *normals;
  float               *tangents;
  uint16_t            *joints;
  float               *weights;
  float              **morphs;
  float               *uvs[AKB_EXPORT_FAST_UV_MAX];
  float               *colors[AKB_EXPORT_FAST_COLOR_MAX];
  uint32_t            *indices;
  size_t               vertexCount;
  size_t               vertexCap;
  size_t               indexCount;
  size_t               indexCap;
  AkbExportFastVertex *table;
  size_t               tableCap;
  size_t               tableCount;
} AkbExportFastGroup;
