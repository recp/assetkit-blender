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

typedef struct AkbAnimCurveView {
  PyObject   *points;
  PyObject   *co_obj;
  Py_buffer   co_view;
  const float *co;
  Py_ssize_t  count;
  Py_ssize_t  cursor;
} AkbAnimCurveView;

static void
akb_anim_curve_view_init(AkbAnimCurveView *view) {
  memset(view, 0, sizeof(*view));
}

static void
akb_anim_curve_view_release(AkbAnimCurveView *view) {
  if (view->co_view.buf)
    PyBuffer_Release(&view->co_view);
  Py_XDECREF(view->co_obj);
  Py_XDECREF(view->points);
  akb_anim_curve_view_init(view);
}

static int
akb_anim_curve_view_load(PyObject *curve, AkbAnimCurveView *view) {
  int rc;

  akb_anim_curve_view_init(view);
  if (!curve || curve == Py_None)
    return 1;

  rc = akb_export_anim_curve_co(curve, &view->points, &view->co_obj, &view->co_view, &view->count);
  if (rc < 0)
    return -1;
  if (rc == 0)
    return 0;
  if (view->count < 2)
    return 0;
  if ((size_t)view->co_view.len < (size_t)view->count * 2u * sizeof(float))
    return 0;

  view->co = (const float *)view->co_view.buf;
  return view->co != NULL;
}

static float
akb_anim_curve_eval(AkbAnimCurveView *view,
                    float             frame,
                    float             fallback,
                    int               interpolation) {
  const float eps = 1.0e-6f;
  Py_ssize_t  cursor;
  float       f0;
  float       f1;
  float       v0;
  float       v1;
  float       t;

  if (!view || !view->co || view->count <= 0)
    return fallback;

  if (frame <= view->co[0] + eps)
    return view->co[1];

  cursor = view->cursor;
  if (cursor < 0)
    cursor = 0;
  while (cursor + 1 < view->count
         && view->co[((size_t)cursor + 1u) * 2u] <= frame + eps)
    cursor++;
  view->cursor = cursor;

  if (cursor + 1 >= view->count)
    return view->co[(size_t)cursor * 2u + 1u];

  f0 = view->co[(size_t)cursor * 2u];
  v0 = view->co[(size_t)cursor * 2u + 1u];
  if (interpolation == AK_INTERPOLATION_STEP)
    return v0;

  f1 = view->co[((size_t)cursor + 1u) * 2u];
  v1 = view->co[((size_t)cursor + 1u) * 2u + 1u];
  if (fabsf(f1 - f0) <= eps)
    return v0;

  t = (frame - f0) / (f1 - f0);
  if (t <= 0.0f)
    return v0;
  if (t >= 1.0f)
    return v1;
  return v0 + (v1 - v0) * t;
}

static int
akb_anim_parse_defaults(PyObject *obj, float *dst, int width) {
  PyObject *seq;

  seq = PySequence_Fast(obj, "animation defaults must be a sequence");
  if (!seq)
    return 0;
  if (PySequence_Fast_GET_SIZE(seq) < width) {
    Py_DECREF(seq);
    return 0;
  }

  for (int i = 0; i < width; i++) {
    double value = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, i));
    if (PyErr_Occurred()) {
      Py_DECREF(seq);
      return 0;
    }
    dst[i] = (float)value;
  }

  Py_DECREF(seq);
  return 1;
}

static int
akb_anim_load_curve_set(PyObject          *curves_obj,
                        AkbAnimCurveView *curves,
                        int               width) {
  PyObject   *seq;
  Py_ssize_t  count;

  seq = PySequence_Fast(curves_obj, "animation curves must be a sequence");
  if (!seq)
    return -1;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count < width) {
    Py_DECREF(seq);
    return 0;
  }

  for (int i = 0; i < width; i++) {
    int rc = akb_anim_curve_view_load(PySequence_Fast_GET_ITEM(seq, i), &curves[i]);
    if (rc <= 0) {
      Py_DECREF(seq);
      return rc;
    }
  }

  Py_DECREF(seq);
  return 1;
}

static void
akb_pose_basis_matrix(const float loc[3],
                      versor      rotation,
                      const float scale[3],
                      mat4        out) {
  glm_quat_mat4(rotation, out);
  for (int col = 0; col < 3; col++) {
    out[col][0] *= scale[col];
    out[col][1] *= scale[col];
    out[col][2] *= scale[col];
  }
  out[3][0] = loc[0];
  out[3][1] = loc[1];
  out[3][2] = loc[2];
  out[3][3] = 1.0f;
}

static PyObject *
akb_pose_channel_tuple(int          target,
                       PyObject    *times_obj,
                       PyObject    *values_obj,
                       Py_ssize_t   count,
                       int          interpolation) {
  PyObject *target_obj;
  PyObject *count_obj;
  PyObject *interp_obj;
  PyObject *out;

  target_obj = PyLong_FromLong(target);
  count_obj = PyLong_FromSsize_t(count);
  interp_obj = PyLong_FromLong(interpolation);
  out = PyTuple_New(5);
  if (!target_obj || !times_obj || !values_obj || !count_obj || !interp_obj || !out) {
    Py_XDECREF(out);
    Py_XDECREF(interp_obj);
    Py_XDECREF(count_obj);
    Py_XDECREF(target_obj);
    return NULL;
  }

  Py_INCREF(times_obj);
  Py_INCREF(values_obj);
  PyTuple_SET_ITEM(out, 0, target_obj);
  PyTuple_SET_ITEM(out, 1, times_obj);
  PyTuple_SET_ITEM(out, 2, values_obj);
  PyTuple_SET_ITEM(out, 3, count_obj);
  PyTuple_SET_ITEM(out, 4, interp_obj);
  return out;
}

static PyObject *
akb_export_pose_bone_anim_channels(PyObject *self, PyObject *args) {
  PyObject          *rest_obj;
  PyObject          *frames_obj;
  PyObject          *loc_curves_obj;
  PyObject          *quat_curves_obj;
  PyObject          *scale_curves_obj;
  PyObject          *loc_defaults_obj;
  PyObject          *quat_defaults_obj;
  PyObject          *scale_defaults_obj;
  Py_buffer          rest_view;
  Py_buffer          frames_view;
  AkbAnimCurveView   loc_curves[3];
  AkbAnimCurveView   quat_curves[4];
  AkbAnimCurveView   scale_curves[3];
  const float       *rest;
  const float       *frames;
  PyObject          *times_obj;
  PyObject          *translations_obj;
  PyObject          *rotations_obj;
  PyObject          *scales_obj;
  float             *times;
  float             *translations;
  float             *rotations;
  float             *scales;
  float              loc_defaults[3];
  float              quat_defaults[4];
  float              scale_defaults[3];
  double             fps;
  Py_ssize_t         sample_count;
  int                loc_interp;
  int                rot_interp;
  int                scale_interp;
  int                rc;
  int                loc_changed;
  int                rot_changed;
  int                scale_changed;
  PyObject          *out;
  Py_ssize_t         out_index;

  (void)self;

  memset(&rest_view, 0, sizeof(rest_view));
  memset(&frames_view, 0, sizeof(frames_view));
  for (int i = 0; i < 3; i++) {
    akb_anim_curve_view_init(&loc_curves[i]);
    akb_anim_curve_view_init(&scale_curves[i]);
  }
  for (int i = 0; i < 4; i++)
    akb_anim_curve_view_init(&quat_curves[i]);

  times_obj = NULL;
  translations_obj = NULL;
  rotations_obj = NULL;
  scales_obj = NULL;
  times = NULL;
  translations = NULL;
  rotations = NULL;
  scales = NULL;
  out = NULL;

  if (!PyArg_ParseTuple(args,
                        "OOOOOOOOdiii",
                        &rest_obj,
                        &frames_obj,
                        &loc_curves_obj,
                        &quat_curves_obj,
                        &scale_curves_obj,
                        &loc_defaults_obj,
                        &quat_defaults_obj,
                        &scale_defaults_obj,
                        &fps,
                        &loc_interp,
                        &rot_interp,
                        &scale_interp))
    return NULL;

  if (fps <= 0.0)
    fps = 24.0;

  if (!akb_anim_parse_defaults(loc_defaults_obj, loc_defaults, 3)
      || !akb_anim_parse_defaults(quat_defaults_obj, quat_defaults, 4)
      || !akb_anim_parse_defaults(scale_defaults_obj, scale_defaults, 3))
    goto unsupported;

  if (PyObject_GetBuffer(rest_obj, &rest_view, PyBUF_SIMPLE) < 0)
    goto error;
  if ((size_t)rest_view.len < 16u * sizeof(float))
    goto unsupported;
  rest = (const float *)rest_view.buf;

  if (PyObject_GetBuffer(frames_obj, &frames_view, PyBUF_SIMPLE) < 0)
    goto error;
  if (frames_view.len <= 0 || frames_view.len % (Py_ssize_t)sizeof(float) != 0)
    goto unsupported;
  sample_count = frames_view.len / (Py_ssize_t)sizeof(float);
  if (sample_count < 2)
    goto no_channel;
  frames = (const float *)frames_view.buf;

  rc = akb_anim_load_curve_set(loc_curves_obj, loc_curves, 3);
  if (rc < 0)
    goto error;
  if (rc == 0)
    goto unsupported;
  rc = akb_anim_load_curve_set(quat_curves_obj, quat_curves, 4);
  if (rc < 0)
    goto error;
  if (rc == 0)
    goto unsupported;
  rc = akb_anim_load_curve_set(scale_curves_obj, scale_curves, 3);
  if (rc < 0)
    goto error;
  if (rc == 0)
    goto unsupported;

  if (sample_count > PY_SSIZE_T_MAX / (Py_ssize_t)(4 * (int)sizeof(float))) {
    PyErr_SetString(PyExc_OverflowError, "pose bone animation is too large");
    goto error;
  }

  times_obj = PyBytes_FromStringAndSize(NULL, sample_count * (Py_ssize_t)sizeof(float));
  translations_obj = PyBytes_FromStringAndSize(NULL,
                                               sample_count * 3u * (Py_ssize_t)sizeof(float));
  rotations_obj = PyBytes_FromStringAndSize(NULL,
                                            sample_count * 4u * (Py_ssize_t)sizeof(float));
  scales_obj = PyBytes_FromStringAndSize(NULL,
                                         sample_count * 3u * (Py_ssize_t)sizeof(float));
  if (!times_obj || !translations_obj || !rotations_obj || !scales_obj)
    goto error;

  times = (float *)PyBytes_AS_STRING(times_obj);
  translations = (float *)PyBytes_AS_STRING(translations_obj);
  rotations = (float *)PyBytes_AS_STRING(rotations_obj);
  scales = (float *)PyBytes_AS_STRING(scales_obj);

  loc_changed = 0;
  rot_changed = 0;
  scale_changed = 0;

  for (Py_ssize_t i = 0; i < sample_count; i++) {
    float frame;
    float basis_loc[3];
    float basis_scale[3];
    float raw_quat[4];
    versor basis_rot;
    mat4 basis;
    mat4 local;
    float translation[3];
    float scale[3];
    versor rotation;
    float *out_loc;
    float *out_rot;
    float *out_scale;

    frame = frames[i];
    times[i] = frame / (float)fps;

    for (int component = 0; component < 3; component++) {
      basis_loc[component] = akb_anim_curve_eval(&loc_curves[component],
                                                 frame,
                                                 loc_defaults[component],
                                                 loc_interp);
      basis_scale[component] = akb_anim_curve_eval(&scale_curves[component],
                                                   frame,
                                                   scale_defaults[component],
                                                   scale_interp);
    }
    for (int component = 0; component < 4; component++) {
      raw_quat[component] = akb_anim_curve_eval(&quat_curves[component],
                                                frame,
                                                quat_defaults[component],
                                                rot_interp);
    }

    basis_rot[0] = raw_quat[1];
    basis_rot[1] = raw_quat[2];
    basis_rot[2] = raw_quat[3];
    basis_rot[3] = raw_quat[0];
    glm_quat_normalize(basis_rot);
    akb_pose_basis_matrix(basis_loc, basis_rot, basis_scale, basis);
    glm_mat4_mul(AKB_MAT4(rest), basis, local);

    akb_mat4_to_trs((const float *)local, translation, rotation, scale);
    glm_quat_normalize(rotation);

    out_loc = translations + (size_t)i * 3u;
    out_rot = rotations + (size_t)i * 4u;
    out_scale = scales + (size_t)i * 3u;

    out_loc[0] = translation[0];
    out_loc[1] = translation[1];
    out_loc[2] = translation[2];

    out_rot[0] = rotation[0];
    out_rot[1] = rotation[1];
    out_rot[2] = rotation[2];
    out_rot[3] = rotation[3];
    if (i > 0) {
      float *prev = rotations + ((size_t)i - 1u) * 4u;
      float dot = prev[0] * out_rot[0]
                + prev[1] * out_rot[1]
                + prev[2] * out_rot[2]
                + prev[3] * out_rot[3];
      if (dot < 0.0f) {
        out_rot[0] = -out_rot[0];
        out_rot[1] = -out_rot[1];
        out_rot[2] = -out_rot[2];
        out_rot[3] = -out_rot[3];
      }
    }

    out_scale[0] = scale[0];
    out_scale[1] = scale[1];
    out_scale[2] = scale[2];

    if (i > 0) {
      float *first_loc = translations;
      float *first_rot = rotations;
      float *first_scale = scales;
      for (int component = 0; component < 3; component++) {
        if (fabsf(out_loc[component] - first_loc[component]) > 1.0e-6f)
          loc_changed = 1;
        if (fabsf(out_scale[component] - first_scale[component]) > 1.0e-6f)
          scale_changed = 1;
      }
      for (int component = 0; component < 4; component++) {
        if (fabsf(out_rot[component] - first_rot[component]) > 1.0e-6f)
          rot_changed = 1;
      }
    }
  }

  out = PyTuple_New((loc_changed ? 1 : 0) + (rot_changed ? 1 : 0) + (scale_changed ? 1 : 0));
  if (!out)
    goto error;

  out_index = 0;
  if (loc_changed) {
    PyObject *channel = akb_pose_channel_tuple(AK_TARGET_POSITION,
                                               times_obj,
                                               translations_obj,
                                               sample_count,
                                               loc_interp);
    if (!channel)
      goto error;
    PyTuple_SET_ITEM(out, out_index++, channel);
  }
  if (rot_changed) {
    PyObject *channel = akb_pose_channel_tuple(AK_TARGET_QUAT,
                                               times_obj,
                                               rotations_obj,
                                               sample_count,
                                               rot_interp);
    if (!channel)
      goto error;
    PyTuple_SET_ITEM(out, out_index++, channel);
  }
  if (scale_changed) {
    PyObject *channel = akb_pose_channel_tuple(AK_TARGET_SCALE,
                                               times_obj,
                                               scales_obj,
                                               sample_count,
                                               scale_interp);
    if (!channel)
      goto error;
    PyTuple_SET_ITEM(out, out_index++, channel);
  }

  Py_DECREF(scales_obj);
  Py_DECREF(rotations_obj);
  Py_DECREF(translations_obj);
  Py_DECREF(times_obj);
  PyBuffer_Release(&frames_view);
  PyBuffer_Release(&rest_view);
  for (int i = 0; i < 3; i++) {
    akb_anim_curve_view_release(&loc_curves[i]);
    akb_anim_curve_view_release(&scale_curves[i]);
  }
  for (int i = 0; i < 4; i++)
    akb_anim_curve_view_release(&quat_curves[i]);
  return out;

no_channel:
  Py_XDECREF(out);
  Py_XDECREF(scales_obj);
  Py_XDECREF(rotations_obj);
  Py_XDECREF(translations_obj);
  Py_XDECREF(times_obj);
  if (frames_view.buf)
    PyBuffer_Release(&frames_view);
  if (rest_view.buf)
    PyBuffer_Release(&rest_view);
  for (int i = 0; i < 3; i++) {
    akb_anim_curve_view_release(&loc_curves[i]);
    akb_anim_curve_view_release(&scale_curves[i]);
  }
  for (int i = 0; i < 4; i++)
    akb_anim_curve_view_release(&quat_curves[i]);
  Py_RETURN_NONE;

unsupported:
  PyErr_Clear();
  Py_XDECREF(out);
  Py_XDECREF(scales_obj);
  Py_XDECREF(rotations_obj);
  Py_XDECREF(translations_obj);
  Py_XDECREF(times_obj);
  if (frames_view.buf)
    PyBuffer_Release(&frames_view);
  if (rest_view.buf)
    PyBuffer_Release(&rest_view);
  for (int i = 0; i < 3; i++) {
    akb_anim_curve_view_release(&loc_curves[i]);
    akb_anim_curve_view_release(&scale_curves[i]);
  }
  for (int i = 0; i < 4; i++)
    akb_anim_curve_view_release(&quat_curves[i]);
  Py_RETURN_FALSE;

error:
  Py_XDECREF(out);
  Py_XDECREF(scales_obj);
  Py_XDECREF(rotations_obj);
  Py_XDECREF(translations_obj);
  Py_XDECREF(times_obj);
  if (frames_view.buf)
    PyBuffer_Release(&frames_view);
  if (rest_view.buf)
    PyBuffer_Release(&rest_view);
  for (int i = 0; i < 3; i++) {
    akb_anim_curve_view_release(&loc_curves[i]);
    akb_anim_curve_view_release(&scale_curves[i]);
  }
  for (int i = 0; i < 4; i++)
    akb_anim_curve_view_release(&quat_curves[i]);
  return NULL;
}
