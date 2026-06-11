static int
akb_export_payload_is_native_curve(PyObject *payload_obj) {
  PyObject *tag_obj;
  unsigned long tag;

  if (!PyTuple_Check(payload_obj) || PyTuple_Size(payload_obj) != 4)
    return 0;

  tag_obj = PyTuple_GET_ITEM(payload_obj, 0);
  tag = PyLong_AsUnsignedLong(tag_obj);
  if (PyErr_Occurred()) {
    PyErr_Clear();
    return 0;
  }
  return tag == AKB_EXPORT_NATIVE_CURVE_PAYLOAD;
}

static int
akb_export_curve_bool_attr(PyObject *obj, const char *name, int default_value) {
  PyObject *value_obj;
  int       value;

  value_obj = PyObject_GetAttrString(obj, name);
  if (!value_obj) {
    PyErr_Clear();
    return default_value;
  }
  value = PyObject_IsTrue(value_obj);
  Py_DECREF(value_obj);
  if (value < 0) {
    PyErr_Clear();
    return default_value;
  }
  return value != 0;
}

static long
akb_export_curve_long_attr(PyObject *obj, const char *name, long default_value) {
  PyObject *value_obj;
  long      value;

  value_obj = PyObject_GetAttrString(obj, name);
  if (!value_obj) {
    PyErr_Clear();
    return default_value;
  }
  value = PyLong_AsLong(value_obj);
  Py_DECREF(value_obj);
  if (PyErr_Occurred()) {
    PyErr_Clear();
    return default_value;
  }
  return value;
}

static AkVertices *
akb_export_curve_vertices(AkDoc          *doc,
                          void           *parent,
                          PyObject       *points_obj,
                          uint32_t        component_count,
                          uint32_t       *point_count_out) {
  AkHeap    *heap;
  PyObject  *co_obj;
  Py_buffer  co_view;
  AkVertices *vertices;
  AkBuffer   *buff;
  AkAccessor *acc;
  AkInput    *input;
  const float *co;
  float      *packed;
  Py_ssize_t  point_count_py;
  uint32_t    point_count;
  size_t      required4;
  size_t      length;

  if (!doc || !points_obj || !point_count_out)
    return NULL;

  point_count_py = PySequence_Size(points_obj);
  if (point_count_py <= 1 || point_count_py > UINT32_MAX) {
    PyErr_SetString(PyExc_ValueError, "curve payload must contain 2..UINT32_MAX points");
    return NULL;
  }
  point_count = (uint32_t)point_count_py;
  required4 = (size_t)point_count * 4u * sizeof(float);

  co_obj = akb_export_array_new("f", (Py_ssize_t)point_count * 4);
  if (!co_obj)
    return NULL;
  memset(&co_view, 0, sizeof(co_view));
  if (!akb_export_foreach_get_buffer(points_obj, "co", co_obj, "f")
      || PyObject_GetBuffer(co_obj, &co_view, PyBUF_SIMPLE) < 0) {
    Py_DECREF(co_obj);
    return NULL;
  }
  if ((size_t)co_view.len < required4) {
    PyBuffer_Release(&co_view);
    Py_DECREF(co_obj);
    PyErr_SetString(PyExc_ValueError, "curve point co buffer is shorter than expected");
    return NULL;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyBuffer_Release(&co_view);
    Py_DECREF(co_obj);
    return NULL;
  }

  vertices = (AkVertices *)ak_heap_calloc(heap, parent ? parent : doc, sizeof(*vertices));
  if (!vertices) {
    PyBuffer_Release(&co_view);
    Py_DECREF(co_obj);
    PyErr_NoMemory();
    return NULL;
  }

  co = (const float *)co_view.buf;
  packed = NULL;
  if (component_count == 3u) {
    length = (size_t)point_count * 3u * sizeof(float);
    packed = (float *)malloc(length);
    if (!packed) {
      PyBuffer_Release(&co_view);
      Py_DECREF(co_obj);
      PyErr_NoMemory();
      return NULL;
    }
    for (uint32_t i = 0; i < point_count; i++) {
      packed[(size_t)i * 3u]      = co[(size_t)i * 4u];
      packed[(size_t)i * 3u + 1u] = co[(size_t)i * 4u + 1u];
      packed[(size_t)i * 3u + 2u] = co[(size_t)i * 4u + 2u];
    }
    buff = akb_export_buffer(heap, doc, vertices, packed, length);
    free(packed);
  } else {
    component_count = 4u;
    length = required4;
    buff = akb_export_buffer(heap, doc, vertices, co, length);
  }

  PyBuffer_Release(&co_view);
  Py_DECREF(co_obj);
  if (!buff)
    return NULL;

  acc = akb_export_accessor(heap,
                            doc,
                            buff,
                            component_count == 4u
                              ? AK_COMPONENT_SIZE_VEC4
                              : AK_COMPONENT_SIZE_VEC3,
                            AKT_FLOAT,
                            component_count,
                            point_count);
  if (!acc)
    return NULL;

  input = (AkInput *)ak_heap_calloc(heap, vertices, sizeof(*input));
  if (!input) {
    PyErr_NoMemory();
    return NULL;
  }
  input->accessor = acc;
  input->semantic = AK_INPUT_POSITION;
  input->next = vertices->input;
  vertices->input = input;
  vertices->inputCount++;

  *point_count_out = point_count;
  return vertices;
}

static int
akb_export_add_poly_curve_to_node(AkDoc      *doc,
                                  AkNode     *node,
                                  const char *name,
                                  PyObject   *spline_obj,
                                  PyObject   *geometry_extra_obj,
                                  PyObject   *curve_extra_obj) {
  AkHeap     *heap;
  PyObject   *points_obj;
  AkGeometry *geom;
  AkObject   *spline_data_obj;
  AkSpline   *spline;
  uint32_t    point_count;
  int         ok;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  points_obj = PyObject_GetAttrString(spline_obj, "points");
  if (!points_obj)
    return 0;

  geom = (AkGeometry *)ak_heap_calloc(heap, doc, sizeof(*geom));
  if (!geom) {
    Py_DECREF(points_obj);
    PyErr_NoMemory();
    return 0;
  }
  geom->name = name && name[0] ? name : NULL;
  ak_setypeid(geom, AKT_GEOMETRY);

  spline_data_obj = ak_objAlloc(heap, geom, sizeof(*spline), AK_GEOMETRY_SPLINE, true);
  if (!spline_data_obj) {
    Py_DECREF(points_obj);
    PyErr_NoMemory();
    return 0;
  }
  geom->gdata = spline_data_obj;
  spline = (AkSpline *)ak_objGet(spline_data_obj);
  spline->geom = geom;
  spline->closed = akb_export_curve_bool_attr(spline_obj, "use_cyclic_u", 0) ? 1 : 0;
  spline->cverts = akb_export_curve_vertices(doc,
                                             spline_data_obj,
                                             points_obj,
                                             3u,
                                             &point_count);
  Py_DECREF(points_obj);
  if (!spline->cverts)
    return 0;
  (void)point_count;

  ok = akb_export_apply_direct_extra(doc, geom, &geom->extra, geometry_extra_obj)
       && akb_export_apply_direct_extra(doc, spline, &spline->extra, curve_extra_obj);
  if (!ok)
    return 0;

  AKB_LIB_APPEND(doc->lib.geometries, geom, next);
  return ak_nodeAttachGeometry(node, geom) != NULL;
}

static int
akb_export_add_nurbs_curve_to_node(AkDoc      *doc,
                                   AkNode     *node,
                                   const char *name,
                                   PyObject   *spline_obj,
                                   PyObject   *geometry_extra_obj,
                                   PyObject   *curve_extra_obj) {
  AkHeap      *heap;
  PyObject    *points_obj;
  AkGeometry  *geom;
  AkObject    *brep_data_obj;
  AkBoundryRep *brep;
  AkCurves    *curves;
  AkCurve     *curve;
  AkObject    *nurbs_obj;
  AkNurbs     *nurbs;
  uint32_t     point_count;
  long         order;
  int          ok;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  points_obj = PyObject_GetAttrString(spline_obj, "points");
  if (!points_obj)
    return 0;

  geom = (AkGeometry *)ak_heap_calloc(heap, doc, sizeof(*geom));
  if (!geom) {
    Py_DECREF(points_obj);
    PyErr_NoMemory();
    return 0;
  }
  geom->name = name && name[0] ? name : NULL;
  ak_setypeid(geom, AKT_GEOMETRY);

  brep_data_obj = ak_objAlloc(heap, geom, sizeof(*brep), AK_GEOMETRY_BREP, true);
  if (!brep_data_obj) {
    Py_DECREF(points_obj);
    PyErr_NoMemory();
    return 0;
  }
  geom->gdata = brep_data_obj;
  brep = (AkBoundryRep *)ak_objGet(brep_data_obj);
  brep->geom = geom;

  curves = (AkCurves *)ak_heap_calloc(heap, brep_data_obj, sizeof(*curves));
  curve = (AkCurve *)ak_heap_calloc(heap, curves, sizeof(*curve));
  nurbs_obj = ak_objAlloc(heap, curve, sizeof(*nurbs), AK_CURVE_NURBS, true);
  if (!curves || !curve || !nurbs_obj) {
    Py_DECREF(points_obj);
    PyErr_NoMemory();
    return 0;
  }

  nurbs = (AkNurbs *)ak_objGet(nurbs_obj);
  order = akb_export_curve_long_attr(spline_obj, "order_u", 2);
  nurbs->degree = order > 1 ? (AkUInt)(order - 1) : 1u;
  nurbs->closed = akb_export_curve_bool_attr(spline_obj, "use_cyclic_u", 0) ? 1 : 0;
  nurbs->cverts = akb_export_curve_vertices(doc,
                                            nurbs_obj,
                                            points_obj,
                                            4u,
                                            &point_count);
  Py_DECREF(points_obj);
  if (!nurbs->cverts)
    return 0;
  if (nurbs->degree >= point_count)
    nurbs->degree = point_count > 1u ? point_count - 1u : 1u;

  curve->curve = nurbs_obj;
  curves->curve = curve;
  brep->curves = curves;

  ok = akb_export_apply_direct_extra(doc, geom, &geom->extra, geometry_extra_obj)
       && akb_export_apply_direct_extra(doc, nurbs, &nurbs->extra, curve_extra_obj);
  if (!ok)
    return 0;

  AKB_LIB_APPEND(doc->lib.geometries, geom, next);
  return ak_nodeAttachGeometry(node, geom) != NULL;
}

static int
akb_export_add_curve_object_to_node(AkDoc      *doc,
                                    AkNode     *node,
                                    const char *name,
                                    PyObject   *payload_obj) {
  PyObject *curve_data_obj;
  PyObject *geometry_extra_obj;
  PyObject *curve_extra_obj;
  PyObject *splines_obj;
  PyObject *spline_obj;
  PyObject *type_obj;
  Py_ssize_t spline_count;
  int is_poly;
  int is_nurbs;
  int ok;

  if (!doc || !node || !payload_obj)
    return 0;
  if (!akb_export_payload_is_native_curve(payload_obj)) {
    PyErr_SetString(PyExc_TypeError, "curve payload must be a native curve tuple");
    return 0;
  }

  curve_data_obj = PyTuple_GET_ITEM(payload_obj, 1);
  geometry_extra_obj = PyTuple_GET_ITEM(payload_obj, 2);
  curve_extra_obj = PyTuple_GET_ITEM(payload_obj, 3);
  splines_obj = PyObject_GetAttrString(curve_data_obj, "splines");
  if (!splines_obj)
    return 0;

  spline_count = PySequence_Size(splines_obj);
  if (spline_count != 1) {
    Py_DECREF(splines_obj);
    PyErr_SetString(PyExc_ValueError, "native curve export expects exactly one spline");
    return 0;
  }

  spline_obj = PySequence_GetItem(splines_obj, 0);
  Py_DECREF(splines_obj);
  if (!spline_obj)
    return 0;

  type_obj = PyObject_GetAttrString(spline_obj, "type");
  if (!type_obj) {
    Py_DECREF(spline_obj);
    return 0;
  }
  ok = PyUnicode_Check(type_obj);
  is_poly = ok && PyUnicode_CompareWithASCIIString(type_obj, "POLY") == 0;
  if (PyErr_Occurred()) {
    Py_DECREF(type_obj);
    Py_DECREF(spline_obj);
    return 0;
  }
  is_nurbs = ok && PyUnicode_CompareWithASCIIString(type_obj, "NURBS") == 0;
  if (PyErr_Occurred()) {
    Py_DECREF(type_obj);
    Py_DECREF(spline_obj);
    return 0;
  }
  Py_DECREF(type_obj);

  if (is_poly)
    ok = akb_export_add_poly_curve_to_node(doc,
                                           node,
                                           name,
                                           spline_obj,
                                           geometry_extra_obj,
                                           curve_extra_obj);
  else if (is_nurbs)
    ok = akb_export_add_nurbs_curve_to_node(doc,
                                            node,
                                            name,
                                            spline_obj,
                                            geometry_extra_obj,
                                            curve_extra_obj);
  else {
    PyErr_SetString(PyExc_ValueError, "native curve export supports POLY and NURBS splines");
    ok = 0;
  }

  Py_DECREF(spline_obj);
  return ok;
}
