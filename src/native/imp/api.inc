static PyObject *
akb_load_meshes(PyObject *self, PyObject *args) {
  const char *filepath;
  AkDoc *doc = NULL;
  AkbLoadOptions options;
  AkbSavedOptions saved_options;
  AkbSharedDoc *doc_owner;
  AkResult result;
  AkbImport import = {0};
  AkbImport *owner_import;
  PyObject *options_obj = NULL;
  PyObject *out;
  PyObject *mesh_list;
  PyObject *curve_list;
  PyObject *node_list;
  PyObject *owner;
  PyObject *item;
  double total_started_at;
  double load_started_at;
  double load_ms;
  double extract_started_at;
  double extract_ms;
  double py_started_at;
  double py_ms;
  size_t i;
  int ok;
  int profile;

  (void)self;

  if (!PyArg_ParseTuple(args, "s|O", &filepath, &options_obj))
    return NULL;

  if (!akb_load_options_from_object(&options, options_obj))
    return NULL;
  if (!akb_load_lock_ensure())
    return NULL;

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  profile = akb_profile_enabled();
  total_started_at = profile ? akb_now_ms() : 0.0;
  load_ms = 0.0;
  extract_ms = 0.0;

  Py_BEGIN_ALLOW_THREADS
  PyThread_acquire_lock(akb_load_lock, WAIT_LOCK);
  akb_options_apply(&options, &saved_options);
  load_started_at = profile ? akb_now_ms() : 0.0;
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  if (profile)
    load_ms = akb_now_ms() - load_started_at;
  doc_owner->doc = doc;
  if (result == AK_OK && doc) {
    extract_started_at = profile ? akb_now_ms() : 0.0;
    ok = akb_extract_doc(doc, doc_owner, &import, &options);
    if (profile)
      extract_ms = akb_now_ms() - extract_started_at;
  } else {
    ok = 0;
  }
  akb_options_restore(&saved_options);
  PyThread_release_lock(akb_load_lock);
  Py_END_ALLOW_THREADS

  if (result != AK_OK || !doc) {
    PyErr_Format(PyExc_RuntimeError, "AssetKit failed to load file: result=%d", result);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (!ok) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    PyErr_SetString(PyExc_MemoryError, "AssetKit bridge could not prepare mesh buffers");
    return NULL;
  }

  py_started_at = profile ? akb_now_ms() : 0.0;

  out = PyDict_New();
  if (!out) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  mesh_list = PyList_New((Py_ssize_t)import.primitives.count);
  node_list = PyList_New((Py_ssize_t)import.nodes.count);
  if (!mesh_list || !node_list) {
    Py_XDECREF(mesh_list);
    Py_XDECREF(node_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  owner_import = (AkbImport *)malloc(sizeof(*owner_import));
  if (!owner_import) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return PyErr_NoMemory();
  }

  *owner_import = import;
  memset(&import, 0, sizeof(import));

  owner = PyCapsule_New(owner_import,
                        "assetkit_blender.AkbImport",
                        akb_import_capsule_destructor);
  if (!owner) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    akb_import_free(owner_import);
    free(owner_import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  for (i = 0; i < owner_import->primitives.count; i++) {
    item = akb_primitive_to_py(&owner_import->primitives.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(mesh_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(mesh_list, (Py_ssize_t)i, item);
  }

  for (i = 0; i < owner_import->nodes.count; i++) {
    item = akb_scene_node_to_py(&owner_import->nodes.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(mesh_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(node_list, (Py_ssize_t)i, item);
  }

  if (PyDict_SetItemString(out, "meshes", mesh_list) < 0
      || PyDict_SetItemString(out, "nodes", node_list) < 0) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  curve_list = akb_curve_list_to_py(owner_import, owner);
  if (!curve_list || PyDict_SetItemString(out, "curves", curve_list) < 0) {
    Py_XDECREF(curve_list);
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(curve_list);

  item = akb_tree_to_py(ak_extra(doc));
  if (!item || PyDict_SetItemString(out, "doc_extra", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  item = akb_doc_images_to_py(doc);
  if (!item || PyDict_SetItemString(out, "images", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  if (!akb_set_scene_info(out, doc, &options)) {
    Py_DECREF(node_list);
    Py_DECREF(mesh_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  Py_DECREF(node_list);
  Py_DECREF(mesh_list);
  if (profile) {
    py_ms = akb_now_ms() - py_started_at;
    akb_profile_log("load_meshes file=\"%s\" result=%d nodes=%zu primitives=%zu curves=%zu ak_load=%.3fms extract=%.3fms py_pack=%.3fms total=%.3fms",
                    filepath,
                    result,
                    owner_import->nodes.count,
                    owner_import->primitives.count,
                    owner_import->curves.count,
                    load_ms,
                    extract_ms,
                    py_ms,
                    akb_now_ms() - total_started_at);
  }
  Py_DECREF(owner);
  akb_shared_doc_release(doc_owner);
  return out;
}

static PyObject *
akb_open_scene(PyObject *self, PyObject *args) {
  const char *filepath;
  AkDoc *doc = NULL;
  AkbLoadOptions options;
  AkbSavedOptions saved_options;
  AkbSharedDoc *doc_owner;
  AkResult result;
  AkbImport import = {0};
  AkbImport *owner_import;
  PyObject *options_obj = NULL;
  PyObject *out;
  PyObject *curve_list;
  PyObject *node_list;
  PyObject *owner;
  PyObject *item;
  double total_started_at;
  double load_started_at;
  double load_ms;
  double extract_started_at;
  double extract_ms;
  double py_started_at;
  double py_ms;
  size_t i;
  int ok;
  int profile;

  (void)self;

  if (!PyArg_ParseTuple(args, "s|O", &filepath, &options_obj))
    return NULL;

  if (!akb_load_options_from_object(&options, options_obj))
    return NULL;
  if (!akb_load_lock_ensure())
    return NULL;

  doc_owner = (AkbSharedDoc *)calloc(1, sizeof(*doc_owner));
  if (!doc_owner)
    return PyErr_NoMemory();
  doc_owner->refcount = 1;

  profile = akb_profile_enabled();
  total_started_at = profile ? akb_now_ms() : 0.0;
  load_ms = 0.0;
  extract_ms = 0.0;

  Py_BEGIN_ALLOW_THREADS
  PyThread_acquire_lock(akb_load_lock, WAIT_LOCK);
  akb_options_apply(&options, &saved_options);
  load_started_at = profile ? akb_now_ms() : 0.0;
  result = ak_load(&doc, filepath, AK_FILE_TYPE_AUTO);
  if (profile)
    load_ms = akb_now_ms() - load_started_at;
  doc_owner->doc = doc;
  if (result == AK_OK && doc) {
    extract_started_at = profile ? akb_now_ms() : 0.0;
    ok = akb_extract_doc(doc, doc_owner, &import, &options);
    if (profile)
      extract_ms = akb_now_ms() - extract_started_at;
  } else {
    ok = 0;
  }
  akb_options_restore(&saved_options);
  PyThread_release_lock(akb_load_lock);
  Py_END_ALLOW_THREADS

  if (result != AK_OK || !doc) {
    PyErr_Format(PyExc_RuntimeError, "AssetKit failed to load file: result=%d", result);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (!ok) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    PyErr_SetString(PyExc_MemoryError, "AssetKit bridge could not prepare mesh buffers");
    return NULL;
  }

  py_started_at = profile ? akb_now_ms() : 0.0;

  out = PyDict_New();
  if (!out) {
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  node_list = PyList_New((Py_ssize_t)import.nodes.count);
  if (!node_list) {
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  owner_import = (AkbImport *)malloc(sizeof(*owner_import));
  if (!owner_import) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    akb_import_free(&import);
    akb_shared_doc_release(doc_owner);
    return PyErr_NoMemory();
  }

  *owner_import = import;
  memset(&import, 0, sizeof(import));

  owner = PyCapsule_New(owner_import,
                        "assetkit_blender.AkbImport",
                        akb_import_capsule_destructor);
  if (!owner) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    akb_import_free(owner_import);
    free(owner_import);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  for (i = 0; i < owner_import->nodes.count; i++) {
    item = akb_scene_node_to_py(&owner_import->nodes.items[i], owner);
    if (!item) {
      Py_DECREF(node_list);
      Py_DECREF(out);
      Py_DECREF(owner);
      akb_shared_doc_release(doc_owner);
      return NULL;
    }
    PyList_SET_ITEM(node_list, (Py_ssize_t)i, item);
  }

  item = PyLong_FromSize_t(owner_import->primitives.count);
  if (!item) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  if (PyDict_SetItemString(out, "_owner", owner) < 0
      || PyDict_SetItemString(out, "nodes", node_list) < 0
      || PyDict_SetItemString(out, "mesh_count", item) < 0) {
    Py_DECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  curve_list = akb_curve_list_to_py(owner_import, owner);
  if (!curve_list || PyDict_SetItemString(out, "curves", curve_list) < 0) {
    Py_XDECREF(curve_list);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(curve_list);

  item = akb_tree_to_py(ak_extra(doc));
  if (!item || PyDict_SetItemString(out, "doc_extra", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  item = akb_doc_images_to_py(doc);
  if (!item || PyDict_SetItemString(out, "images", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  if (!akb_set_scene_info(out, doc, &options)) {
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }

  item = akb_required_node_indices_to_py(owner_import);
  if (!item || PyDict_SetItemString(out, "required_node_indices", item) < 0) {
    Py_XDECREF(item);
    Py_DECREF(node_list);
    Py_DECREF(out);
    Py_DECREF(owner);
    akb_shared_doc_release(doc_owner);
    return NULL;
  }
  Py_DECREF(item);

  Py_DECREF(node_list);
  if (profile) {
    py_ms = akb_now_ms() - py_started_at;
    akb_profile_log("open_scene file=\"%s\" result=%d nodes=%zu primitives=%zu curves=%zu ak_load=%.3fms extract=%.3fms py_pack=%.3fms total=%.3fms",
                    filepath,
                    result,
                    owner_import->nodes.count,
                    owner_import->primitives.count,
                    owner_import->curves.count,
                    load_ms,
                    extract_ms,
                    py_ms,
                    akb_now_ms() - total_started_at);
  }
  Py_DECREF(owner);
  akb_shared_doc_release(doc_owner);
  return out;
}

static PyObject *
akb_read_mesh_batch(PyObject *self, PyObject *args) {
  AkbImport *import;
  PyObject *owner;
  PyObject *item;
  PyObject *list;
  Py_ssize_t start;
  Py_ssize_t count;
  Py_ssize_t available;
  Py_ssize_t i;
  double started_at;
  double py_ms;
  int profile;

  (void)self;

  if (!PyArg_ParseTuple(args, "Onn", &owner, &start, &count))
    return NULL;

  if (start < 0 || count < 0) {
    PyErr_SetString(PyExc_ValueError, "AssetKit mesh batch range must be non-negative");
    return NULL;
  }

  import = (AkbImport *)PyCapsule_GetPointer(owner, "assetkit_blender.AkbImport");
  if (!import)
    return NULL;

  if ((size_t)start >= import->primitives.count || count == 0)
    return PyList_New(0);

  profile = akb_profile_enabled();
  started_at = profile ? akb_now_ms() : 0.0;

  available = (Py_ssize_t)(import->primitives.count - (size_t)start);
  if (count > available)
    count = available;

  list = PyList_New(count);
  if (!list)
    return NULL;

  for (i = 0; i < count; i++) {
    item = akb_primitive_to_py(&import->primitives.items[start + i], owner);
    if (!item) {
      Py_DECREF(list);
      return NULL;
    }
    PyList_SET_ITEM(list, i, item);
  }

  if (profile) {
    py_ms = akb_now_ms() - started_at;
    akb_profile_log("read_mesh_batch start=%zd count=%zd returned=%zd py_pack=%.3fms",
                    start,
                    count,
                    count,
                    py_ms);
  }
  return list;
}

static int
akb_read_file_bytes(const char *path, uint8_t **bytes, size_t *size) {
  FILE *file;
  long length;
  size_t read_size;
  uint8_t *data;

  *bytes = NULL;
  *size = 0;

  file = fopen(path, "rb");
  if (!file)
    return 0;
  if (fseek(file, 0, SEEK_END) != 0) {
    fclose(file);
    return 0;
  }
  length = ftell(file);
  if (length <= 0) {
    fclose(file);
    return 0;
  }
  if (fseek(file, 0, SEEK_SET) != 0) {
    fclose(file);
    return 0;
  }

  data = (uint8_t *)malloc((size_t)length);
  if (!data) {
    fclose(file);
    return 0;
  }

  read_size = fread(data, 1, (size_t)length, file);
  fclose(file);
  if (read_size != (size_t)length) {
    free(data);
    return 0;
  }

  *bytes = data;
  *size = read_size;
  return 1;
}

static void *
akb_ktx2_dlopen(const char *path) {
#if defined(_WIN32)
  return (void *)LoadLibraryA(path);
#else
  return dlopen(path, RTLD_NOW);
#endif
}

static void *
akb_ktx2_symbol(void *library, const char *name) {
#if defined(_WIN32)
  return library ? (void *)GetProcAddress((HMODULE)library, name) : NULL;
#else
  return library ? dlsym(library, name) : NULL;
#endif
}

static AkbKtx2DecodeFn
akb_ktx2_decoder(void) {
  static void *library = NULL;
  static AkbKtx2DecodeFn decode = NULL;
  static int tried = 0;
  const char *env_path;

  if (tried)
    return decode;
  tried = 1;

  env_path = getenv("ASSETKIT_KTX2_DECODER_PATH");
  if (env_path && env_path[0])
    library = akb_ktx2_dlopen(env_path);

#if defined(__APPLE__)
  if (!library)
    library = akb_ktx2_dlopen("@loader_path/libassetkit_ktx2.dylib");
  if (!library)
    library = akb_ktx2_dlopen("@rpath/libassetkit_ktx2.dylib");
  if (!library)
    library = akb_ktx2_dlopen("libassetkit_ktx2.dylib");
#elif defined(_WIN32)
  if (!library)
    library = akb_ktx2_dlopen("assetkit_ktx2.dll");
#else
  if (!library)
    library = akb_ktx2_dlopen("$ORIGIN/libassetkit_ktx2.so");
  if (!library)
    library = akb_ktx2_dlopen("libassetkit_ktx2.so");
#endif

  decode = (AkbKtx2DecodeFn)akb_ktx2_symbol(library, "assetkit_ktx2_decode");
  return decode;
}

static PyObject *
akb_decode_ktx2(PyObject *self, PyObject *args) {
  AkbKtx2DecodeFn decode;
  AkbKtx2DecodedImage image;
  PyObject *out;
  PyObject *pixels;
  PyObject *width_obj;
  PyObject *height_obj;
  uint8_t *file_bytes;
  size_t file_size;
  size_t pixel_count;
  size_t i;
  float *pixel_floats;
  const char *path;
  int result;

  (void)self;

  if (!PyArg_ParseTuple(args, "s", &path))
    return NULL;

  decode = akb_ktx2_decoder();
  if (!decode) {
    PyErr_SetString(PyExc_RuntimeError, "AssetKit KTX2 decoder library was not found");
    return NULL;
  }

  if (!akb_read_file_bytes(path, &file_bytes, &file_size)) {
    PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    return NULL;
  }

  memset(&image, 0, sizeof(image));
  result = decode(file_bytes, file_size, &image);
  free(file_bytes);
  if (result != 0 || !image.data || !image.width || !image.height || image.channels != 4) {
    free(image.data);
    free(image.mips);
    PyErr_Format(PyExc_RuntimeError, "AssetKit KTX2 decode failed: result=%d", result);
    return NULL;
  }

  if ((size_t)image.width > SIZE_MAX / (size_t)image.height / 4 / sizeof(float)) {
    free(image.data);
    free(image.mips);
    PyErr_SetString(PyExc_OverflowError, "KTX2 image is too large");
    return NULL;
  }

  pixel_count = (size_t)image.width * (size_t)image.height * 4;
  pixels = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(pixel_count * sizeof(float)));
  if (!pixels) {
    free(image.data);
    free(image.mips);
    return NULL;
  }

  pixel_floats = (float *)PyBytes_AS_STRING(pixels);
  for (i = 0; i < pixel_count; i++)
    pixel_floats[i] = (float)image.data[i] * (1.0f / 255.0f);

  free(image.data);
  free(image.mips);

  out = PyDict_New();
  if (!out) {
    Py_DECREF(pixels);
    return NULL;
  }

  width_obj = PyLong_FromUnsignedLong(image.width);
  height_obj = PyLong_FromUnsignedLong(image.height);
  if (!width_obj || !height_obj
      || PyDict_SetItemString(out, "width", width_obj) < 0
      || PyDict_SetItemString(out, "height", height_obj) < 0
      || PyDict_SetItemString(out, "pixels_f32", pixels) < 0) {
    Py_XDECREF(width_obj);
    Py_XDECREF(height_obj);
    Py_DECREF(pixels);
    Py_DECREF(out);
    return NULL;
  }

  Py_DECREF(width_obj);
  Py_DECREF(height_obj);
  Py_DECREF(pixels);
  return out;
}

static PyObject *
akb_anim_coords(PyObject *self, PyObject *args) {
  PyObject *channel;
  PyObject *times_obj;
  PyObject *values_obj;
  PyObject *coords;
  Py_buffer times_view;
  Py_buffer values_view;
  const float *times;
  const float *values;
  float *out;
  double fps;
  unsigned long count_ul;
  unsigned long value_width_ul;
  uint32_t count;
  uint32_t value_width;
  int component;
  uint32_t i;

  (void)self;

  memset(&times_view, 0, sizeof(times_view));
  memset(&values_view, 0, sizeof(values_view));

  if (!PyArg_ParseTuple(args, "Oid", &channel, &component, &fps))
    return NULL;

  if (!PyTuple_Check(channel)
      || PyTuple_GET_SIZE(channel) < AKB_PY_ANIM_FIELD_COUNT
      || component < 0) {
    Py_RETURN_NONE;
  }

  count_ul = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(channel, AKB_PY_ANIM_COUNT));
  if (PyErr_Occurred())
    return NULL;
  value_width_ul = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(channel, AKB_PY_ANIM_VALUE_WIDTH));
  if (PyErr_Occurred())
    return NULL;
  if (count_ul == 0
      || count_ul > UINT32_MAX
      || value_width_ul == 0
      || value_width_ul > UINT32_MAX
      || (unsigned long)component >= value_width_ul) {
    Py_RETURN_NONE;
  }

  count       = (uint32_t)count_ul;
  value_width = (uint32_t)value_width_ul;
  if ((size_t)count > (SIZE_MAX / (2 * sizeof(float)))) {
    PyErr_SetString(PyExc_OverflowError, "animation coordinate buffer is too large");
    return NULL;
  }

  times_obj  = PyTuple_GET_ITEM(channel, AKB_PY_ANIM_TIMES_F32);
  values_obj = PyTuple_GET_ITEM(channel, AKB_PY_ANIM_VALUES_F32);
  if (PyObject_GetBuffer(times_obj, &times_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if (PyObject_GetBuffer(values_obj, &values_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&times_view);
    return NULL;
  }

  if ((size_t)times_view.len < (size_t)count * sizeof(float)
      || (size_t)values_view.len < (size_t)count * value_width * sizeof(float)) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    Py_RETURN_NONE;
  }

  coords = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)((size_t)count * 2 * sizeof(float)));
  if (!coords) {
    PyBuffer_Release(&values_view);
    PyBuffer_Release(&times_view);
    return NULL;
  }

  times  = (const float *)times_view.buf;
  values = (const float *)values_view.buf;
  out    = (float *)PyBytes_AS_STRING(coords);
  for (i = 0; i < count; i++) {
    out[i * 2]     = times[i] * (float)fps;
    out[i * 2 + 1] = values[(size_t)i * value_width + (uint32_t)component];
  }

  PyBuffer_Release(&values_view);
  PyBuffer_Release(&times_view);
  return coords;
}

static PyObject *
akb_anim_component_constant(PyObject *self, PyObject *args) {
  PyObject *channel;
  PyObject *values_obj;
  Py_buffer values_view;
  const float *values;
  double expected;
  double epsilon;
  unsigned long count_ul;
  unsigned long value_width_ul;
  uint32_t count;
  uint32_t value_width;
  int component;
  uint32_t i;

  (void)self;

  memset(&values_view, 0, sizeof(values_view));
  if (!PyArg_ParseTuple(args, "Oidd", &channel, &component, &expected, &epsilon))
    return NULL;

  if (!PyTuple_Check(channel)
      || PyTuple_GET_SIZE(channel) < AKB_PY_ANIM_FIELD_COUNT
      || component < 0) {
    Py_RETURN_FALSE;
  }

  count_ul = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(channel, AKB_PY_ANIM_COUNT));
  if (PyErr_Occurred())
    return NULL;
  value_width_ul = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(channel, AKB_PY_ANIM_VALUE_WIDTH));
  if (PyErr_Occurred())
    return NULL;
  if (count_ul == 0
      || count_ul > UINT32_MAX
      || value_width_ul == 0
      || value_width_ul > UINT32_MAX
      || (unsigned long)component >= value_width_ul) {
    Py_RETURN_FALSE;
  }

  count       = (uint32_t)count_ul;
  value_width = (uint32_t)value_width_ul;
  values_obj = PyTuple_GET_ITEM(channel, AKB_PY_ANIM_VALUES_F32);
  if (PyObject_GetBuffer(values_obj, &values_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if ((size_t)values_view.len < (size_t)count * value_width * sizeof(float)) {
    PyBuffer_Release(&values_view);
    Py_RETURN_FALSE;
  }

  if (epsilon < 0.0)
    epsilon = -epsilon;

  values = (const float *)values_view.buf;
  for (i = 0; i < count; i++) {
    if (fabs((double)values[(size_t)i * value_width + (uint32_t)component] - expected) > epsilon) {
      PyBuffer_Release(&values_view);
      Py_RETURN_FALSE;
    }
  }

  PyBuffer_Release(&values_view);
  Py_RETURN_TRUE;
}

static PyObject *
akb_offset_i32(PyObject *self, PyObject *args) {
  PyObject *buffer_obj;
  PyObject *out_obj;
  Py_buffer buffer_view;
  const int32_t *in;
  int32_t *out;
  long offset;
  size_t count;
  size_t i;

  (void)self;

  memset(&buffer_view, 0, sizeof(buffer_view));
  if (!PyArg_ParseTuple(args, "Ol", &buffer_obj, &offset))
    return NULL;
  if (PyObject_GetBuffer(buffer_obj, &buffer_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if ((size_t)buffer_view.len % sizeof(int32_t) != 0) {
    PyBuffer_Release(&buffer_view);
    PyErr_SetString(PyExc_ValueError, "buffer size is not int32-aligned");
    return NULL;
  }

  count = (size_t)buffer_view.len / sizeof(int32_t);
  out_obj = PyBytes_FromStringAndSize(NULL, (Py_ssize_t)(count * sizeof(int32_t)));
  if (!out_obj) {
    PyBuffer_Release(&buffer_view);
    return NULL;
  }

  in  = (const int32_t *)buffer_view.buf;
  out = (int32_t *)PyBytes_AS_STRING(out_obj);
  for (i = 0; i < count; i++)
    out[i] = (int32_t)((int64_t)in[i] + (int64_t)offset);

  PyBuffer_Release(&buffer_view);
  return out_obj;
}

static PyObject *
akb_write_offset_i32(PyObject *self, PyObject *args) {
  PyObject *dst_obj;
  PyObject *src_obj;
  Py_buffer dst_view;
  Py_buffer src_view;
  Py_ssize_t dst_offset_py;
  const int32_t *in;
  int32_t *out;
  long offset;
  size_t dst_offset;
  size_t count;
  size_t nbytes;
  size_t i;

  (void)self;

  memset(&dst_view, 0, sizeof(dst_view));
  memset(&src_view, 0, sizeof(src_view));
  if (!PyArg_ParseTuple(args, "OnOl", &dst_obj, &dst_offset_py, &src_obj, &offset))
    return NULL;
  if (dst_offset_py < 0) {
    PyErr_SetString(PyExc_ValueError, "destination offset must be non-negative");
    return NULL;
  }
  if (PyObject_GetBuffer(dst_obj, &dst_view, PyBUF_WRITABLE) < 0)
    return NULL;
  if (PyObject_GetBuffer(src_obj, &src_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&dst_view);
    return NULL;
  }
  if ((size_t)src_view.len % sizeof(int32_t) != 0) {
    PyBuffer_Release(&src_view);
    PyBuffer_Release(&dst_view);
    PyErr_SetString(PyExc_ValueError, "source buffer size is not int32-aligned");
    return NULL;
  }

  dst_offset = (size_t)dst_offset_py;
  count      = (size_t)src_view.len / sizeof(int32_t);
  nbytes     = count * sizeof(int32_t);
  if (dst_offset > (size_t)dst_view.len
      || nbytes > (size_t)dst_view.len - dst_offset) {
    PyBuffer_Release(&src_view);
    PyBuffer_Release(&dst_view);
    PyErr_SetString(PyExc_ValueError, "destination buffer is too small");
    return NULL;
  }

  in  = (const int32_t *)src_view.buf;
  out = (int32_t *)((char *)dst_view.buf + dst_offset);
  Py_BEGIN_ALLOW_THREADS
  if (offset == 0) {
    memcpy(out, in, nbytes);
  } else {
    for (i = 0; i < count; i++)
      out[i] = (int32_t)((int64_t)in[i] + (int64_t)offset);
  }
  Py_END_ALLOW_THREADS

  PyBuffer_Release(&src_view);
  PyBuffer_Release(&dst_view);
  return PyLong_FromSize_t(nbytes);
}

static PyObject *
akb_fill_i32(PyObject *self, PyObject *args) {
  PyObject *dst_obj;
  Py_buffer dst_view;
  Py_ssize_t dst_offset_py;
  Py_ssize_t count_py;
  int32_t *out;
  long value;
  size_t dst_offset;
  size_t count;
  size_t nbytes;
  size_t i;

  (void)self;

  memset(&dst_view, 0, sizeof(dst_view));
  if (!PyArg_ParseTuple(args, "Onln", &dst_obj, &dst_offset_py, &value, &count_py))
    return NULL;
  if (dst_offset_py < 0 || count_py < 0) {
    PyErr_SetString(PyExc_ValueError, "destination offset and count must be non-negative");
    return NULL;
  }
  if (PyObject_GetBuffer(dst_obj, &dst_view, PyBUF_WRITABLE) < 0)
    return NULL;

  dst_offset = (size_t)dst_offset_py;
  count      = (size_t)count_py;
  if (count > SIZE_MAX / sizeof(int32_t)) {
    PyBuffer_Release(&dst_view);
    PyErr_SetString(PyExc_OverflowError, "fill size is too large");
    return NULL;
  }
  nbytes = count * sizeof(int32_t);
  if (dst_offset > (size_t)dst_view.len
      || nbytes > (size_t)dst_view.len - dst_offset) {
    PyBuffer_Release(&dst_view);
    PyErr_SetString(PyExc_ValueError, "destination buffer is too small");
    return NULL;
  }

  out = (int32_t *)((char *)dst_view.buf + dst_offset);
  Py_BEGIN_ALLOW_THREADS
  for (i = 0; i < count; i++)
    out[i] = (int32_t)value;
  Py_END_ALLOW_THREADS

  PyBuffer_Release(&dst_view);
  return PyLong_FromSize_t(nbytes);
}

static PyObject *
akb_fill_triangle_loop_offsets_ptr(PyObject *self, PyObject *args) {
  unsigned long long address;
  Py_ssize_t face_count_py;
  int32_t *out;
  size_t face_count;
  size_t i;

  (void)self;

  if (!PyArg_ParseTuple(args, "Kn", &address, &face_count_py))
    return NULL;
  if (address == 0 || face_count_py < 0) {
    PyErr_SetString(PyExc_ValueError, "address and face count must be non-negative");
    return NULL;
  }

  face_count = (size_t)face_count_py;
  if (face_count > (size_t)INT32_MAX / 3u) {
    PyErr_SetString(PyExc_OverflowError, "triangle loop offsets exceed int32 range");
    return NULL;
  }

  out = (int32_t *)(uintptr_t)address;
  Py_BEGIN_ALLOW_THREADS
  for (i = 0; i <= face_count; i++)
    out[i] = (int32_t)(i * 3u);
  Py_END_ALLOW_THREADS

  return PyLong_FromSize_t((face_count + 1u) * sizeof(int32_t));
}

static PyObject *
akb_fill_u8_ptr(PyObject *self, PyObject *args) {
  unsigned long long address;
  Py_ssize_t count_py;
  size_t count;
  int value;

  (void)self;

  if (!PyArg_ParseTuple(args, "Kin", &address, &value, &count_py))
    return NULL;
  if (address == 0 || count_py < 0) {
    PyErr_SetString(PyExc_ValueError, "address and count must be non-negative");
    return NULL;
  }
  if (value < 0 || value > 255) {
    PyErr_SetString(PyExc_ValueError, "fill value must fit in uint8");
    return NULL;
  }

  count = (size_t)count_py;
  Py_BEGIN_ALLOW_THREADS
  memset((void *)(uintptr_t)address, value, count);
  Py_END_ALLOW_THREADS

  return PyLong_FromSize_t(count);
}

static PyObject *
akb_skin_group_assignments(PyObject *self, PyObject *args) {
  PyObject *joints_obj;
  PyObject *weights_obj;
  PyObject *out;
  PyObject **buffers;
  Py_buffer joints_view;
  Py_buffer weights_view;
  const uint16_t *joints;
  const float *weights;
  int32_t **writes;
  uint32_t *counts;
  uint32_t *filled;
  Py_ssize_t vertex_count_py;
  Py_ssize_t width_py;
  Py_ssize_t joint_count_py;
  size_t vertex_count;
  size_t width;
  size_t joint_count;
  size_t vertex_index;
  size_t joint_index;
  size_t out_index;
  size_t buffer_count;
  int ok;

  (void)self;

  memset(&joints_view, 0, sizeof(joints_view));
  memset(&weights_view, 0, sizeof(weights_view));

  if (!PyArg_ParseTuple(args,
                        "OOnnn",
                        &joints_obj,
                        &weights_obj,
                        &vertex_count_py,
                        &width_py,
                        &joint_count_py))
    return NULL;

  if (vertex_count_py <= 0 || width_py <= 0 || joint_count_py <= 0)
    Py_RETURN_NONE;

  vertex_count = (size_t)vertex_count_py;
  width        = (size_t)width_py;
  joint_count  = (size_t)joint_count_py;
  if (width > AKB_SKIN_MAX_JOINTS_PER_VERTEX
      || joint_count > UINT32_MAX
      || vertex_count > INT32_MAX)
    Py_RETURN_NONE;
  if (vertex_count > SIZE_MAX / width) {
    PyErr_SetString(PyExc_OverflowError, "skin assignment dimensions are too large");
    return NULL;
  }

  if (PyObject_GetBuffer(joints_obj, &joints_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if (PyObject_GetBuffer(weights_obj, &weights_view, PyBUF_SIMPLE) < 0) {
    PyBuffer_Release(&joints_view);
    return NULL;
  }

  if ((size_t)joints_view.len < vertex_count * width * sizeof(uint16_t)
      || (size_t)weights_view.len < vertex_count * width * sizeof(float)) {
    PyBuffer_Release(&weights_view);
    PyBuffer_Release(&joints_view);
    Py_RETURN_NONE;
  }

  joints = (const uint16_t *)joints_view.buf;
  weights = (const float *)weights_view.buf;

  counts = (uint32_t *)calloc(joint_count, sizeof(*counts));
  if (!counts) {
    PyBuffer_Release(&weights_view);
    PyBuffer_Release(&joints_view);
    return PyErr_NoMemory();
  }

  ok = 1;
  for (vertex_index = 0; vertex_index < vertex_count && ok; vertex_index++) {
    size_t base;
    int found_joint;
    int found_count;
    float found_weight;
    size_t slot;

    base = vertex_index * width;
    found_joint = -1;
    found_count = 0;
    found_weight = 0.0f;
    for (slot = 0; slot < width; slot++) {
      float weight;

      weight = weights[base + slot];
      if (weight <= 0.0f)
        continue;
      found_joint = (int)joints[base + slot];
      found_weight = weight;
      found_count++;
      if (found_count > 1)
        break;
    }

    if (found_count != 1
        || found_joint < 0
        || (size_t)found_joint >= joint_count
        || fabsf(found_weight - 1.0f) > 1.0e-6f) {
      ok = 0;
      break;
    }
    counts[found_joint]++;
  }

  if (!ok) {
    free(counts);
    PyBuffer_Release(&weights_view);
    PyBuffer_Release(&joints_view);
    Py_RETURN_NONE;
  }

  buffer_count = 0;
  for (joint_index = 0; joint_index < joint_count; joint_index++)
    if (counts[joint_index])
      buffer_count++;

  buffers = (PyObject **)calloc(joint_count, sizeof(*buffers));
  writes = (int32_t **)calloc(joint_count, sizeof(*writes));
  filled = (uint32_t *)calloc(joint_count, sizeof(*filled));
  if (!buffers || !writes || !filled) {
    free(filled);
    free(writes);
    free(buffers);
    free(counts);
    PyBuffer_Release(&weights_view);
    PyBuffer_Release(&joints_view);
    return PyErr_NoMemory();
  }

  for (joint_index = 0; joint_index < joint_count; joint_index++) {
    if (!counts[joint_index])
      continue;
    buffers[joint_index] = PyBytes_FromStringAndSize(NULL,
                                                     (Py_ssize_t)((size_t)counts[joint_index]
                                                                  * sizeof(int32_t)));
    if (!buffers[joint_index]) {
      ok = 0;
      break;
    }
    writes[joint_index] = (int32_t *)PyBytes_AS_STRING(buffers[joint_index]);
  }

  if (ok) {
    for (vertex_index = 0; vertex_index < vertex_count; vertex_index++) {
      size_t base;
      size_t slot;

      base = vertex_index * width;
      for (slot = 0; slot < width; slot++) {
        if (weights[base + slot] > 0.0f) {
          joint_index = (size_t)joints[base + slot];
          writes[joint_index][filled[joint_index]++] = (int32_t)vertex_index;
          break;
        }
      }
    }
  }

  out = ok ? PyList_New((Py_ssize_t)buffer_count) : NULL;
  out_index = 0;
  if (out) {
    for (joint_index = 0; joint_index < joint_count; joint_index++) {
      PyObject *tuple;
      PyObject *joint_obj;
      PyObject *weight_obj;

      if (!buffers[joint_index])
        continue;

      tuple = PyTuple_New(3);
      joint_obj = PyLong_FromSize_t(joint_index);
      weight_obj = PyFloat_FromDouble(1.0);
      if (!tuple || !joint_obj || !weight_obj) {
        Py_XDECREF(tuple);
        Py_XDECREF(joint_obj);
        Py_XDECREF(weight_obj);
        Py_DECREF(out);
        out = NULL;
        break;
      }

      PyTuple_SET_ITEM(tuple, 0, joint_obj);
      PyTuple_SET_ITEM(tuple, 1, weight_obj);
      PyTuple_SET_ITEM(tuple, 2, buffers[joint_index]);
      buffers[joint_index] = NULL;
      PyList_SET_ITEM(out, (Py_ssize_t)out_index++, tuple);
    }
  }

  for (joint_index = 0; joint_index < joint_count; joint_index++)
    Py_XDECREF(buffers[joint_index]);
  free(filled);
  free(writes);
  free(buffers);
  free(counts);
  PyBuffer_Release(&weights_view);
  PyBuffer_Release(&joints_view);
  if (!out)
    return NULL;
  return out;
}
