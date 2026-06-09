static int
akb_export_foreach_get_buffer(PyObject *owner,
                              const char *prop,
                              PyObject *buffer,
                              const char *format) {
  PyObject *method;
  PyObject *prop_obj;
  PyObject *res;

  (void)format;

  method = PyObject_GetAttrString(owner, "foreach_get");
  if (!method)
    return 0;
  prop_obj = PyUnicode_FromString(prop);
  if (!prop_obj) {
    Py_XDECREF(prop_obj);
    Py_DECREF(method);
    return 0;
  }

  res = PyObject_CallFunctionObjArgs(method, prop_obj, buffer, NULL);
  Py_DECREF(prop_obj);
  Py_DECREF(method);
  if (!res)
    return 0;
  Py_DECREF(res);
  return 1;
}

static PyObject *
akb_export_array_type(void) {
  static PyObject *array_type = NULL;
  PyObject *array_mod;

  if (array_type)
    return Py_NewRef(array_type);

  array_mod = PyImport_ImportModule("array");
  if (!array_mod)
    return NULL;
  array_type = PyObject_GetAttrString(array_mod, "array");
  Py_DECREF(array_mod);
  return array_type ? Py_NewRef(array_type) : NULL;
}

static PyObject *
akb_export_array_new(const char *typecode, Py_ssize_t count) {
  PyObject *array_type;
  PyObject *type_obj;
  PyObject *init;
  PyObject *zero;
  PyObject *one;
  PyObject *count_obj;
  PyObject *out;

  array_type = akb_export_array_type();
  if (!array_type)
    return NULL;
  type_obj = PyUnicode_FromString(typecode);
  init = PyList_New(1);
  if (!array_type || !type_obj || !init) {
    Py_XDECREF(init);
    Py_XDECREF(type_obj);
    Py_XDECREF(array_type);
    return NULL;
  }
  zero = typecode[0] == 'f' ? PyFloat_FromDouble(0.0) : PyLong_FromLong(0);
  if (!zero) {
    Py_DECREF(init);
    Py_DECREF(type_obj);
    Py_DECREF(array_type);
    return NULL;
  }
  PyList_SET_ITEM(init, 0, zero);
  one = PyObject_CallFunctionObjArgs(array_type, type_obj, init, NULL);
  Py_DECREF(init);
  Py_DECREF(type_obj);
  Py_DECREF(array_type);
  if (!one)
    return NULL;
  count_obj = PyLong_FromSsize_t(count);
  out = count_obj ? PyNumber_Multiply(one, count_obj) : NULL;
  Py_XDECREF(count_obj);
  Py_DECREF(one);
  return out;
}

typedef struct AkbExportImagePixels {
  Py_buffer view;
  const float *pixels;
  Py_ssize_t width;
  Py_ssize_t height;
  int has;
} AkbExportImagePixels;

static float
akb_export_clamp01(float value) {
  if (value < 0.0f)
    return 0.0f;
  if (value > 1.0f)
    return 1.0f;
  return value;
}

static int
akb_export_image_pixels_init(AkbExportImagePixels *image, PyObject *obj) {
  PyObject *pixels_obj;

  memset(image, 0, sizeof(*image));
  if (!obj || obj == Py_None)
    return 1;

  if (!PyTuple_Check(obj) || PyTuple_GET_SIZE(obj) < 3) {
    PyErr_SetString(PyExc_TypeError, "image pixels must be a tuple(width, height, pixels)");
    return 0;
  }

  image->width = PyLong_AsSsize_t(PyTuple_GET_ITEM(obj, 0));
  if (PyErr_Occurred())
    return 0;
  image->height = PyLong_AsSsize_t(PyTuple_GET_ITEM(obj, 1));
  if (PyErr_Occurred())
    return 0;
  if (image->width <= 0 || image->height <= 0) {
    PyErr_SetString(PyExc_ValueError, "image dimensions must be positive");
    return 0;
  }
  if (image->width > PY_SSIZE_T_MAX / image->height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "image is too large");
    return 0;
  }

  pixels_obj = PyTuple_GET_ITEM(obj, 2);
  if (PyObject_GetBuffer(pixels_obj, &image->view, PyBUF_SIMPLE) < 0)
    return 0;
  if (image->view.len < image->width * image->height * 4 * (Py_ssize_t)sizeof(float)) {
    PyBuffer_Release(&image->view);
    memset(&image->view, 0, sizeof(image->view));
    PyErr_SetString(PyExc_ValueError, "image pixel buffer is shorter than dimensions");
    return 0;
  }

  image->pixels = (const float *)image->view.buf;
  image->has = image->pixels != NULL;
  return 1;
}

static void
akb_export_image_pixels_release(AkbExportImagePixels *image) {
  if (image && image->view.buf)
    PyBuffer_Release(&image->view);
}

static float
akb_export_image_sample_channel(const AkbExportImagePixels *image,
                                Py_ssize_t                 x,
                                Py_ssize_t                 y,
                                Py_ssize_t                 width,
                                Py_ssize_t                 height,
                                float                      fallback,
                                int                        channel) {
  Py_ssize_t src_x;
  Py_ssize_t src_y;

  if (!image || !image->has)
    return akb_export_clamp01(fallback);

  if (channel < 0 || channel > 3)
    channel = 0;

  src_x = (x * image->width) / width;
  src_y = (y * image->height) / height;
  if (src_x < 0)
    src_x = 0;
  else if (src_x >= image->width)
    src_x = image->width - 1;
  if (src_y < 0)
    src_y = 0;
  else if (src_y >= image->height)
    src_y = image->height - 1;

  return akb_export_clamp01(image->pixels[(src_y * image->width + src_x) * 4 + channel]);
}

static PyObject *
akb_export_pack_metallic_roughness(PyObject *self, PyObject *args) {
  PyObject *occ_obj;
  PyObject *metal_obj;
  PyObject *rough_obj;
  PyObject *out_obj;
  Py_buffer out_view;
  AkbExportImagePixels occ;
  AkbExportImagePixels metal;
  AkbExportImagePixels rough;
  Py_ssize_t width;
  Py_ssize_t height;
  float *out;
  double metallic_factor;
  double roughness_factor;
  int occlusion_channel;
  int metallic_channel;
  int roughness_channel;
  int ok;

  (void)self;

  memset(&out_view, 0, sizeof(out_view));
  memset(&occ, 0, sizeof(occ));
  memset(&metal, 0, sizeof(metal));
  memset(&rough, 0, sizeof(rough));
  out_obj = NULL;
  ok = 0;

  if (!PyArg_ParseTuple(args,
                        "nnOiOiOidd",
                        &width,
                        &height,
                        &occ_obj,
                        &occlusion_channel,
                        &metal_obj,
                        &metallic_channel,
                        &rough_obj,
                        &roughness_channel,
                        &metallic_factor,
                        &roughness_factor))
    return NULL;
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "output dimensions must be positive");
    return NULL;
  }
  if (width > PY_SSIZE_T_MAX / height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "output image is too large");
    return NULL;
  }

  if (!akb_export_image_pixels_init(&occ, occ_obj)
      || !akb_export_image_pixels_init(&metal, metal_obj)
      || !akb_export_image_pixels_init(&rough, rough_obj))
    goto done_pack_mr;

  out_obj = akb_export_array_new("f", width * height * 4);
  if (!out_obj || PyObject_GetBuffer(out_obj, &out_view, PyBUF_SIMPLE) < 0)
    goto done_pack_mr;
  if (out_view.len < width * height * 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "output image buffer is too small");
    goto done_pack_mr;
  }
  out = (float *)out_view.buf;
  if (!out) {
    PyErr_NoMemory();
    goto done_pack_mr;
  }

  for (Py_ssize_t y = 0; y < height; y++) {
    for (Py_ssize_t x = 0; x < width; x++) {
      size_t offset = (size_t)(y * width + x) * 4u;

      out[offset] = akb_export_image_sample_channel(&occ,
                                                    x,
                                                    y,
                                                    width,
                                                    height,
                                                    1.0f,
                                                    occlusion_channel);
      out[offset + 1u] = akb_export_image_sample_channel(&rough,
                                                         x,
                                                         y,
                                                         width,
                                                         height,
                                                         (float)roughness_factor,
                                                         roughness_channel);
      out[offset + 2u] = akb_export_image_sample_channel(&metal,
                                                         x,
                                                         y,
                                                         width,
                                                         height,
                                                         (float)metallic_factor,
                                                         metallic_channel);
      out[offset + 3u] = 1.0f;
    }
  }
  ok = 1;

done_pack_mr:
  if (out_view.buf)
    PyBuffer_Release(&out_view);
  akb_export_image_pixels_release(&rough);
  akb_export_image_pixels_release(&metal);
  akb_export_image_pixels_release(&occ);
  if (!ok) {
    Py_XDECREF(out_obj);
    return NULL;
  }
  return out_obj;
}

static PyObject *
akb_export_pack_base_color_alpha(PyObject *self, PyObject *args) {
  PyObject *base_obj;
  PyObject *alpha_obj;
  PyObject *out_obj;
  Py_buffer out_view;
  AkbExportImagePixels base;
  AkbExportImagePixels alpha;
  Py_ssize_t width;
  Py_ssize_t height;
  float *out;
  int base_channel;
  int alpha_channel;
  int invert_alpha;
  int ok;

  (void)self;

  memset(&out_view, 0, sizeof(out_view));
  memset(&base, 0, sizeof(base));
  memset(&alpha, 0, sizeof(alpha));
  out_obj = NULL;
  invert_alpha = 0;
  ok = 0;

  if (!PyArg_ParseTuple(args,
                        "nnOiOi|p",
                        &width,
                        &height,
                        &base_obj,
                        &base_channel,
                        &alpha_obj,
                        &alpha_channel,
                        &invert_alpha))
    return NULL;
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "output dimensions must be positive");
    return NULL;
  }
  if (width > PY_SSIZE_T_MAX / height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "output image is too large");
    return NULL;
  }

  if (!akb_export_image_pixels_init(&base, base_obj)
      || !akb_export_image_pixels_init(&alpha, alpha_obj))
    goto done_pack_alpha;
  if (!alpha.has) {
    PyErr_SetString(PyExc_ValueError, "alpha image pixels are required");
    goto done_pack_alpha;
  }

  out_obj = akb_export_array_new("f", width * height * 4);
  if (!out_obj || PyObject_GetBuffer(out_obj, &out_view, PyBUF_SIMPLE) < 0)
    goto done_pack_alpha;
  if (out_view.len < width * height * 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "output image buffer is too small");
    goto done_pack_alpha;
  }
  out = (float *)out_view.buf;
  if (!out) {
    PyErr_NoMemory();
    goto done_pack_alpha;
  }

  for (Py_ssize_t y = 0; y < height; y++) {
    for (Py_ssize_t x = 0; x < width; x++) {
      size_t offset = (size_t)(y * width + x) * 4u;

      if (base_channel == 0) {
        out[offset] = akb_export_image_sample_channel(&base, x, y, width, height, 1.0f, 0);
        out[offset + 1u] = akb_export_image_sample_channel(&base, x, y, width, height, 1.0f, 1);
        out[offset + 2u] = akb_export_image_sample_channel(&base, x, y, width, height, 1.0f, 2);
      } else {
        float value = akb_export_image_sample_channel(&base,
                                                     x,
                                                     y,
                                                     width,
                                                     height,
                                                     1.0f,
                                                     base_channel);

        out[offset] = value;
        out[offset + 1u] = value;
        out[offset + 2u] = value;
      }
      out[offset + 3u] = akb_export_image_sample_channel(&alpha,
                                                         x,
                                                         y,
                                                         width,
                                                         height,
                                                         1.0f,
                                                         alpha_channel);
      if (invert_alpha)
        out[offset + 3u] = 1.0f - out[offset + 3u];
    }
  }
  ok = 1;

done_pack_alpha:
  if (out_view.buf)
    PyBuffer_Release(&out_view);
  akb_export_image_pixels_release(&alpha);
  akb_export_image_pixels_release(&base);
  if (!ok) {
    Py_XDECREF(out_obj);
    return NULL;
  }
  return out_obj;
}

static PyObject *
akb_export_pack_channel(PyObject *self, PyObject *args) {
  PyObject *image_obj;
  PyObject *out_obj;
  Py_buffer out_view;
  AkbExportImagePixels image;
  Py_ssize_t width;
  Py_ssize_t height;
  float *out;
  double fallback;
  int source_channel;
  int target_channel;
  int ok;

  (void)self;

  memset(&out_view, 0, sizeof(out_view));
  memset(&image, 0, sizeof(image));
  out_obj = NULL;
  ok = 0;

  if (!PyArg_ParseTuple(args,
                        "nnOiid",
                        &width,
                        &height,
                        &image_obj,
                        &source_channel,
                        &target_channel,
                        &fallback))
    return NULL;
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "output dimensions must be positive");
    return NULL;
  }
  if (width > PY_SSIZE_T_MAX / height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "output image is too large");
    return NULL;
  }
  if (target_channel < 0 || target_channel > 3)
    target_channel = 0;

  if (!akb_export_image_pixels_init(&image, image_obj))
    goto done_pack_channel;
  if (!image.has) {
    PyErr_SetString(PyExc_ValueError, "image pixels are required");
    goto done_pack_channel;
  }

  out_obj = akb_export_array_new("f", width * height * 4);
  if (!out_obj || PyObject_GetBuffer(out_obj, &out_view, PyBUF_SIMPLE) < 0)
    goto done_pack_channel;
  if (out_view.len < width * height * 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "output image buffer is too small");
    goto done_pack_channel;
  }
  out = (float *)out_view.buf;
  if (!out) {
    PyErr_NoMemory();
    goto done_pack_channel;
  }

  for (Py_ssize_t y = 0; y < height; y++) {
    for (Py_ssize_t x = 0; x < width; x++) {
      size_t offset = (size_t)(y * width + x) * 4u;

      out[offset] = 1.0f;
      out[offset + 1u] = 1.0f;
      out[offset + 2u] = 1.0f;
      out[offset + 3u] = 1.0f;
      out[offset + (size_t)target_channel] =
        akb_export_image_sample_channel(&image,
                                        x,
                                        y,
                                        width,
                                        height,
                                        (float)fallback,
                                        source_channel);
    }
  }
  ok = 1;

done_pack_channel:
  if (out_view.buf)
    PyBuffer_Release(&out_view);
  akb_export_image_pixels_release(&image);
  if (!ok) {
    Py_XDECREF(out_obj);
    return NULL;
  }
  return out_obj;
}

static PyObject *
akb_export_pack_rgb_channel(PyObject *self, PyObject *args) {
  PyObject *image_obj;
  PyObject *out_obj;
  Py_buffer out_view;
  AkbExportImagePixels image;
  Py_ssize_t width;
  Py_ssize_t height;
  float *out;
  double fallback;
  int source_channel;
  int ok;

  (void)self;

  memset(&out_view, 0, sizeof(out_view));
  memset(&image, 0, sizeof(image));
  out_obj = NULL;
  ok = 0;

  if (!PyArg_ParseTuple(args,
                        "nnOid",
                        &width,
                        &height,
                        &image_obj,
                        &source_channel,
                        &fallback))
    return NULL;
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "output dimensions must be positive");
    return NULL;
  }
  if (width > PY_SSIZE_T_MAX / height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "output image is too large");
    return NULL;
  }

  if (!akb_export_image_pixels_init(&image, image_obj))
    goto done_pack_rgb_channel;
  if (!image.has) {
    PyErr_SetString(PyExc_ValueError, "image pixels are required");
    goto done_pack_rgb_channel;
  }

  out_obj = akb_export_array_new("f", width * height * 4);
  if (!out_obj || PyObject_GetBuffer(out_obj, &out_view, PyBUF_SIMPLE) < 0)
    goto done_pack_rgb_channel;
  if (out_view.len < width * height * 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "output image buffer is too small");
    goto done_pack_rgb_channel;
  }
  out = (float *)out_view.buf;
  if (!out) {
    PyErr_NoMemory();
    goto done_pack_rgb_channel;
  }

  for (Py_ssize_t y = 0; y < height; y++) {
    for (Py_ssize_t x = 0; x < width; x++) {
      size_t offset = (size_t)(y * width + x) * 4u;
      float value;

      value = akb_export_image_sample_channel(&image,
                                              x,
                                              y,
                                              width,
                                              height,
                                              (float)fallback,
                                              source_channel);
      out[offset] = value;
      out[offset + 1u] = value;
      out[offset + 2u] = value;
      out[offset + 3u] = 1.0f;
    }
  }
  ok = 1;

done_pack_rgb_channel:
  if (out_view.buf)
    PyBuffer_Release(&out_view);
  akb_export_image_pixels_release(&image);
  if (!ok) {
    Py_XDECREF(out_obj);
    return NULL;
  }
  return out_obj;
}

static PyObject *
akb_export_pack_specular_glossiness(PyObject *self, PyObject *args) {
  PyObject *spec_obj;
  PyObject *gloss_obj;
  PyObject *spec_color_obj;
  PyObject *out_obj;
  Py_buffer spec_color_view;
  Py_buffer out_view;
  AkbExportImagePixels spec;
  AkbExportImagePixels gloss;
  Py_ssize_t width;
  Py_ssize_t height;
  const float *spec_color;
  float *out;
  double glossiness_factor;
  int specular_channel;
  int glossiness_channel;
  int ok;

  (void)self;

  memset(&spec_color_view, 0, sizeof(spec_color_view));
  memset(&out_view, 0, sizeof(out_view));
  memset(&spec, 0, sizeof(spec));
  memset(&gloss, 0, sizeof(gloss));
  out_obj = NULL;
  ok = 0;

  if (!PyArg_ParseTuple(args,
                        "nnOiOiOd",
                        &width,
                        &height,
                        &spec_obj,
                        &specular_channel,
                        &gloss_obj,
                        &glossiness_channel,
                        &spec_color_obj,
                        &glossiness_factor))
    return NULL;
  if (width <= 0 || height <= 0) {
    PyErr_SetString(PyExc_ValueError, "output dimensions must be positive");
    return NULL;
  }
  if (width > PY_SSIZE_T_MAX / height / 4 / (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_OverflowError, "output image is too large");
    return NULL;
  }
  if (PyObject_GetBuffer(spec_color_obj, &spec_color_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if (spec_color_view.len < 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "specular color buffer must hold four float values");
    goto done_pack_spec_gloss;
  }

  if (!akb_export_image_pixels_init(&spec, spec_obj)
      || !akb_export_image_pixels_init(&gloss, gloss_obj))
    goto done_pack_spec_gloss;

  out_obj = akb_export_array_new("f", width * height * 4);
  if (!out_obj || PyObject_GetBuffer(out_obj, &out_view, PyBUF_SIMPLE) < 0)
    goto done_pack_spec_gloss;
  if (out_view.len < width * height * 4 * (Py_ssize_t)sizeof(float)) {
    PyErr_SetString(PyExc_ValueError, "output image buffer is too small");
    goto done_pack_spec_gloss;
  }
  out = (float *)out_view.buf;
  if (!out) {
    PyErr_NoMemory();
    goto done_pack_spec_gloss;
  }

  spec_color = (const float *)spec_color_view.buf;
  for (Py_ssize_t y = 0; y < height; y++) {
    for (Py_ssize_t x = 0; x < width; x++) {
      size_t offset = (size_t)(y * width + x) * 4u;

      if (!spec.has) {
        out[offset]      = akb_export_clamp01(spec_color[0]);
        out[offset + 1u] = akb_export_clamp01(spec_color[1]);
        out[offset + 2u] = akb_export_clamp01(spec_color[2]);
      } else if (specular_channel == 0) {
        out[offset] = akb_export_image_sample_channel(&spec,
                                                      x,
                                                      y,
                                                      width,
                                                      height,
                                                      spec_color[0],
                                                      0);
        out[offset + 1u] = akb_export_image_sample_channel(&spec,
                                                           x,
                                                           y,
                                                           width,
                                                           height,
                                                           spec_color[1],
                                                           1);
        out[offset + 2u] = akb_export_image_sample_channel(&spec,
                                                           x,
                                                           y,
                                                           width,
                                                           height,
                                                           spec_color[2],
                                                           2);
      } else {
        float value = akb_export_image_sample_channel(&spec,
                                                     x,
                                                     y,
                                                     width,
                                                     height,
                                                     1.0f,
                                                     specular_channel);

        out[offset]      = value;
        out[offset + 1u] = value;
        out[offset + 2u] = value;
      }

      out[offset + 3u] = akb_export_image_sample_channel(&gloss,
                                                         x,
                                                         y,
                                                         width,
                                                         height,
                                                         (float)glossiness_factor,
                                                         glossiness_channel);
    }
  }
  ok = 1;

done_pack_spec_gloss:
  if (out_view.buf)
    PyBuffer_Release(&out_view);
  akb_export_image_pixels_release(&gloss);
  akb_export_image_pixels_release(&spec);
  if (spec_color_view.buf)
    PyBuffer_Release(&spec_color_view);
  if (!ok) {
    Py_XDECREF(out_obj);
    return NULL;
  }
  return out_obj;
}
