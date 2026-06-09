static int
akb_export_anim_curve_co(PyObject   *curve,
                         PyObject  **points_out,
                         PyObject  **co_obj_out,
                         Py_buffer  *co_view_out,
                         Py_ssize_t *count_out) {
  PyObject   *points;
  PyObject   *co_obj;
  Py_ssize_t  count;

  points = PyObject_GetAttrString(curve, "keyframe_points");
  if (!points)
    return 0;

  count = PyObject_Length(points);
  if (count < 0) {
    Py_DECREF(points);
    return 0;
  }

  if (count < 2) {
    Py_DECREF(points);
    *count_out = count;
    return 1;
  }

  co_obj = akb_export_array_new("f", count * 2);
  if (!co_obj) {
    Py_DECREF(points);
    return -1;
  }

  if (PyObject_GetBuffer(co_obj, co_view_out, PyBUF_SIMPLE) < 0) {
    Py_DECREF(co_obj);
    Py_DECREF(points);
    return -1;
  }

  if (!akb_export_foreach_get_buffer(points, "co", co_obj, "f")) {
    PyBuffer_Release(co_view_out);
    memset(co_view_out, 0, sizeof(*co_view_out));
    Py_DECREF(co_obj);
    Py_DECREF(points);
    return 0;
  }

  *points_out = points;
  *co_obj_out = co_obj;
  *count_out = count;
  return 1;
}

static int
akb_export_anim_curves_interpolation(PyObject **points,
                                     int        width,
                                     int       *interpolation_out) {
  int found;

  found = 0;
  *interpolation_out = AK_INTERPOLATION_LINEAR;

  for (int component = 0; component < width; component++) {
    PyObject   *points_obj;
    Py_ssize_t  count;

    points_obj = points[component];
    if (!points_obj)
      continue;

    count = PyObject_Length(points_obj);
    if (count < 0)
      return 0;

    for (Py_ssize_t i = 0; i < count; i++) {
      PyObject   *key;
      PyObject   *interp_obj;
      const char *interp;

      key = PySequence_GetItem(points_obj, i);
      if (!key)
        return 0;

      interp_obj = PyObject_GetAttrString(key, "interpolation");
      Py_DECREF(key);
      if (!interp_obj)
        return 0;

      interp = PyUnicode_AsUTF8(interp_obj);
      if (!interp) {
        Py_DECREF(interp_obj);
        return 0;
      }

      found = 1;
      if (strcmp(interp, "CONSTANT") != 0) {
        Py_DECREF(interp_obj);
        *interpolation_out = AK_INTERPOLATION_LINEAR;
        return 1;
      }
      Py_DECREF(interp_obj);
    }
  }

  *interpolation_out = found ? AK_INTERPOLATION_STEP : AK_INTERPOLATION_LINEAR;
  return 1;
}

static PyObject *
akb_export_aligned_anim_channel(PyObject *self, PyObject *args) {
  PyObject   *curves_obj;
  PyObject   *defaults_obj;
  PyObject   *curves_seq;
  PyObject   *defaults_seq;
  PyObject   *points[4];
  PyObject   *co_objs[4];
  Py_buffer   co_views[4];
  const float *co[4];
  float       defaults[4];
  float       first[4];
  PyObject   *times_obj;
  PyObject   *values_obj;
  PyObject   *out;
  float      *times;
  float      *values;
  double      fps;
  Py_ssize_t  curve_count;
  Py_ssize_t  default_count;
  Py_ssize_t  sample_count;
  Py_ssize_t  present_count;
  int         target_type;
  int         mode;
  int         width;
  int         changed;
  int         interpolation;

  (void)self;

  if (!PyArg_ParseTuple(args, "iOOdi", &target_type, &curves_obj, &defaults_obj, &fps, &mode))
    return NULL;

  width = mode == 1 ? 4 : (int)akb_export_anim_target_width((AkTargetPropertyType)target_type);
  if (width <= 0 || width > 4)
    Py_RETURN_FALSE;
  if (mode == 1 && target_type != AK_TARGET_QUAT)
    Py_RETURN_FALSE;
  if (fps <= 0.0)
    fps = 24.0;

  curves_seq = PySequence_Fast(curves_obj, "animation curves must be a sequence");
  if (!curves_seq)
    return NULL;
  defaults_seq = PySequence_Fast(defaults_obj, "animation defaults must be a sequence");
  if (!defaults_seq) {
    Py_DECREF(curves_seq);
    return NULL;
  }

  curve_count = PySequence_Fast_GET_SIZE(curves_seq);
  default_count = PySequence_Fast_GET_SIZE(defaults_seq);
  if (curve_count < width || default_count < width) {
    Py_DECREF(defaults_seq);
    Py_DECREF(curves_seq);
    Py_RETURN_FALSE;
  }

  for (int component = 0; component < 4; component++) {
    points[component] = NULL;
    co_objs[component] = NULL;
    co[component] = NULL;
    memset(&co_views[component], 0, sizeof(co_views[component]));
    defaults[component] = 0.0f;
    first[component] = 0.0f;
  }

  for (int component = 0; component < width; component++) {
    PyObject *default_obj;
    double    default_value;

    default_obj = PySequence_Fast_GET_ITEM(defaults_seq, component);
    default_value = PyFloat_AsDouble(default_obj);
    if (PyErr_Occurred()) {
      Py_DECREF(defaults_seq);
      Py_DECREF(curves_seq);
      return NULL;
    }
    defaults[component] = (float)default_value;
  }

  sample_count = 0;
  present_count = 0;
  for (int component = 0; component < width; component++) {
    PyObject   *curve;
    Py_ssize_t  count;
    int         rc;

    curve = PySequence_Fast_GET_ITEM(curves_seq, component);
    if (!curve || curve == Py_None)
      continue;

    count = 0;
    rc = akb_export_anim_curve_co(curve,
                                  &points[component],
                                  &co_objs[component],
                                  &co_views[component],
                                  &count);
    if (rc < 0)
      goto error;
    if (rc == 0)
      goto unsupported;
    if (count < 2)
      goto no_channel;

    if ((size_t)co_views[component].len < (size_t)count * 2u * sizeof(float))
      goto unsupported;

    co[component] = (const float *)co_views[component].buf;
    if (!co[component])
      goto unsupported;

    if (present_count == 0)
      sample_count = count;
    else if (count != sample_count)
      goto unsupported;
    present_count++;
  }

  if (present_count == 0 || sample_count < 2)
    goto no_channel;

  for (int component = 0; component < width; component++) {
    if (!co[component])
      continue;
    for (Py_ssize_t i = 0; i < sample_count; i++) {
      float expected = co[component][(size_t)i * 2u];
      float actual = co[0] ? co[0][(size_t)i * 2u] : expected;

      if (!co[0]) {
        for (int find = 1; find < width; find++) {
          if (co[find]) {
            actual = co[find][(size_t)i * 2u];
            break;
          }
        }
      }

      if (fabsf(expected - actual) > 1.0e-6f)
        goto unsupported;
    }
  }

  if (sample_count > PY_SSIZE_T_MAX / (Py_ssize_t)sizeof(float)
      || sample_count > PY_SSIZE_T_MAX / (Py_ssize_t)(width * (int)sizeof(float))) {
    PyErr_SetString(PyExc_OverflowError, "animation channel is too large");
    goto error;
  }

  times_obj = PyBytes_FromStringAndSize(NULL, sample_count * (Py_ssize_t)sizeof(float));
  values_obj = PyBytes_FromStringAndSize(NULL,
                                         sample_count * (Py_ssize_t)width * (Py_ssize_t)sizeof(float));
  if (!times_obj || !values_obj) {
    Py_XDECREF(values_obj);
    Py_XDECREF(times_obj);
    goto error;
  }

  times = (float *)PyBytes_AS_STRING(times_obj);
  values = (float *)PyBytes_AS_STRING(values_obj);
  changed = 0;

  for (Py_ssize_t i = 0; i < sample_count; i++) {
    float raw[4];
    float out_values[4];
    float frame;

    frame = 0.0f;
    for (int component = 0; component < width; component++) {
      if (co[component]) {
        frame = co[component][(size_t)i * 2u];
        break;
      }
    }
    times[i] = frame / (float)fps;

    for (int component = 0; component < width; component++)
      raw[component] = co[component] ? co[component][(size_t)i * 2u + 1u] : defaults[component];

    if (mode == 1) {
      out_values[0] = raw[1];
      out_values[1] = raw[2];
      out_values[2] = raw[3];
      out_values[3] = raw[0];
      if (i > 0) {
        float *prev = values + ((size_t)i - 1u) * 4u;
        float dot = prev[0] * out_values[0]
                  + prev[1] * out_values[1]
                  + prev[2] * out_values[2]
                  + prev[3] * out_values[3];
        if (dot < 0.0f) {
          out_values[0] = -out_values[0];
          out_values[1] = -out_values[1];
          out_values[2] = -out_values[2];
          out_values[3] = -out_values[3];
        }
      }
    } else {
      for (int component = 0; component < width; component++)
        out_values[component] = raw[component];
    }

    for (int component = 0; component < width; component++) {
      values[(size_t)i * (size_t)width + (size_t)component] = out_values[component];
      if (i == 0)
        first[component] = out_values[component];
      else if (fabsf(out_values[component] - first[component]) > 1.0e-6f)
        changed = 1;
    }
  }

  if (!changed) {
    Py_DECREF(values_obj);
    Py_DECREF(times_obj);
    goto no_channel;
  }

  if (!akb_export_anim_curves_interpolation(points, width, &interpolation)) {
    Py_DECREF(values_obj);
    Py_DECREF(times_obj);
    goto unsupported;
  }

  {
    PyObject *target_obj;
    PyObject *count_obj;
    PyObject *interpolation_obj;

    target_obj = PyLong_FromLong(target_type);
    count_obj = PyLong_FromSsize_t(sample_count);
    interpolation_obj = PyLong_FromLong(interpolation);
    out = PyTuple_New(5);
    if (!target_obj || !count_obj || !interpolation_obj || !out) {
      Py_XDECREF(out);
      Py_XDECREF(interpolation_obj);
      Py_XDECREF(count_obj);
      Py_XDECREF(target_obj);
      Py_DECREF(values_obj);
      Py_DECREF(times_obj);
      goto error;
    }

    PyTuple_SET_ITEM(out, 0, target_obj);
    PyTuple_SET_ITEM(out, 1, times_obj);
    PyTuple_SET_ITEM(out, 2, values_obj);
    PyTuple_SET_ITEM(out, 3, count_obj);
    PyTuple_SET_ITEM(out, 4, interpolation_obj);
  }

  for (int component = 0; component < width; component++) {
    if (co_views[component].buf)
      PyBuffer_Release(&co_views[component]);
    Py_XDECREF(co_objs[component]);
    Py_XDECREF(points[component]);
  }
  Py_DECREF(defaults_seq);
  Py_DECREF(curves_seq);
  return out;

no_channel:
  for (int component = 0; component < width; component++) {
    if (co_views[component].buf)
      PyBuffer_Release(&co_views[component]);
    Py_XDECREF(co_objs[component]);
    Py_XDECREF(points[component]);
  }
  Py_DECREF(defaults_seq);
  Py_DECREF(curves_seq);
  Py_RETURN_NONE;

unsupported:
  PyErr_Clear();
  for (int component = 0; component < width; component++) {
    if (co_views[component].buf)
      PyBuffer_Release(&co_views[component]);
    Py_XDECREF(co_objs[component]);
    Py_XDECREF(points[component]);
  }
  Py_DECREF(defaults_seq);
  Py_DECREF(curves_seq);
  Py_RETURN_FALSE;

error:
  for (int component = 0; component < width; component++) {
    if (co_views[component].buf)
      PyBuffer_Release(&co_views[component]);
    Py_XDECREF(co_objs[component]);
    Py_XDECREF(points[component]);
  }
  Py_DECREF(defaults_seq);
  Py_DECREF(curves_seq);
  return NULL;
}

