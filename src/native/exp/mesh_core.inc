static AkBuffer *
akb_export_buffer(AkHeap *heap, AkDoc *doc, void *parent, const void *data, size_t length) {
  AkBuffer *buff;

  if (!heap || !doc || !data || length == 0)
    return NULL;

  buff = (AkBuffer *)ak_heap_calloc(heap, doc, sizeof(*buff));
  if (!buff)
    return NULL;
  buff->data = ak_heap_alloc(heap, buff, length);
  if (!buff->data)
    return NULL;
  memcpy(buff->data, data, length);
  buff->length = length;
  ak_setypeid(buff, AKT_BUFFER);
  AKB_LIB_APPEND(doc->lib.buffers, buff, next);
  (void)parent;

  return buff;
}

static AkAccessor *
akb_export_accessor(AkHeap         *heap,
                    AkDoc          *doc,
                    AkBuffer       *buff,
                    AkComponentSize component_size,
                    AkTypeId        component_type,
                    uint32_t        component_count,
                    uint32_t        count) {
  AkAccessor *acc;
  AkTypeDesc *type_desc;
  size_t      component_bytes;

  if (!heap || !doc || !buff || count == 0 || component_count == 0)
    return NULL;

  type_desc = ak_typeDesc(component_type);
  if (!type_desc || type_desc->size <= 0)
    return NULL;
  component_bytes = (size_t)type_desc->size;

  acc = (AkAccessor *)ak_heap_calloc(heap, doc, sizeof(*acc));
  if (!acc)
    return NULL;

  acc->buffer                = buff;
  acc->byteLength            = buff->length;
  acc->byteStride            = component_bytes * component_count;
  acc->componentSize         = component_size;
  acc->componentType         = component_type;
  acc->originalComponentType = component_type;
  acc->bytesPerComponent     = (uint32_t)component_bytes;
  acc->componentCount        = component_count;
  acc->fillByteSize          = component_bytes * component_count;
  acc->count                 = count;

  ak_setypeid(acc, AKT_ACCESSOR);
  AKB_LIB_APPEND(doc->lib.accessors, acc, next);

  return acc;
}

static AkInput *
akb_export_input(AkHeap          *heap,
                 AkMeshPrimitive *prim,
                 AkAccessor      *acc,
                 AkInputSemantic  semantic,
                 const char      *semantic_raw,
                 uint32_t         set) {
  AkInput *input;

  if (!heap || !prim || !acc)
    return NULL;

  input = (AkInput *)ak_heap_calloc(heap, prim, sizeof(*input));
  if (!input)
    return NULL;

  input->accessor    = acc;
  input->semantic    = semantic;
  input->semanticRaw = semantic_raw;
  input->set         = set;
  input->next        = prim->input;
  prim->input        = input;
  prim->inputCount++;

  if (semantic == AK_INPUT_POSITION)
    prim->pos = input;

  return input;
}

static int
akb_export_add_input_buffer_with_offset(AkHeap          *heap,
                                        AkDoc           *doc,
                                        AkMeshPrimitive *prim,
                                        const void      *data,
                                        size_t           length,
                                        uint32_t         vertex_count,
                                        AkComponentSize  component_size,
                                        AkTypeId         component_type,
                                        uint32_t         component_count,
                                        AkInputSemantic  semantic,
                                        const char      *semantic_raw,
                                        uint32_t         set,
                                        uint32_t         index_offset) {
  AkTypeDesc *type_desc;
  AkBuffer   *buff;
  AkAccessor *acc;
  AkInput    *input;
  size_t      required;

  if (!heap || !doc || !prim || !data || vertex_count == 0 || component_count == 0)
    return 0;

  type_desc = ak_typeDesc(component_type);
  if (!type_desc || type_desc->size <= 0)
    return 0;

  required = (size_t)vertex_count * component_count * (size_t)type_desc->size;
  if (length < required) {
    PyErr_SetString(PyExc_ValueError, "mesh attribute buffer is smaller than declared vertex count");
    return 0;
  }

  buff = akb_export_buffer(heap, doc, prim, data, required);
  acc  = akb_export_accessor(heap,
                             doc,
                             buff,
                             component_size,
                             component_type,
                             component_count,
                             vertex_count);
  input = akb_export_input(heap, prim, acc, semantic, semantic_raw, set);
  if (!input)
    return 0;
  input->indexOffset = index_offset;

  return 1;
}

static int
akb_export_add_input_buffer(AkHeap          *heap,
                            AkDoc           *doc,
                            AkMeshPrimitive *prim,
                            const void      *data,
                            size_t           length,
                            uint32_t         vertex_count,
                            AkComponentSize  component_size,
                            AkTypeId         component_type,
                            uint32_t         component_count,
                            AkInputSemantic  semantic,
                            const char      *semantic_raw,
                            uint32_t         set) {
  return akb_export_add_input_buffer_with_offset(heap,
                                                 doc,
                                                 prim,
                                                 data,
                                                 length,
                                                 vertex_count,
                                                 component_size,
                                                 component_type,
                                                 component_count,
                                                 semantic,
                                                 semantic_raw,
                                                 set,
                                                 0);
}

static int
akb_export_add_float_input_sequence(AkHeap          *heap,
                                    AkDoc           *doc,
                                    AkMeshPrimitive *prim,
                                    PyObject        *seq_obj,
                                    uint32_t         vertex_count,
                                    uint32_t         component_count,
                                    AkComponentSize  component_size,
                                    AkInputSemantic  semantic,
                                    const char      *semantic_raw) {
  PyObject   *seq;
  Py_ssize_t  count;
  Py_ssize_t  i;

  if (!seq_obj || seq_obj == Py_None)
    return 1;

  seq = PySequence_Fast(seq_obj, "mesh attribute sets must be a sequence");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count > UINT32_MAX) {
    Py_DECREF(seq);
    PyErr_SetString(PyExc_OverflowError, "too many mesh attribute sets");
    return 0;
  }

  for (i = 0; i < count; i++) {
    PyObject  *item;
    Py_buffer  view;
    int        ok;

    item = PySequence_Fast_GET_ITEM(seq, i);
    if (!item || item == Py_None)
      continue;

    memset(&view, 0, sizeof(view));
    if (PyObject_GetBuffer(item, &view, PyBUF_SIMPLE) < 0) {
      Py_DECREF(seq);
      return 0;
    }

    ok = akb_export_add_input_buffer(heap,
                                     doc,
                                     prim,
                                     view.buf,
                                     (size_t)view.len,
                                     vertex_count,
                                     component_size,
                                     AKT_FLOAT,
                                     component_count,
                                     semantic,
                                     semantic_raw,
                                     (uint32_t)i);
    PyBuffer_Release(&view);
    if (!ok) {
      Py_DECREF(seq);
      return 0;
    }
  }

  Py_DECREF(seq);
  return 1;
}

static AkInput *
akb_export_morphable_input(AkHeap       *heap,
                           void         *parent,
                           AkMorphable  *morphable,
                           AkAccessor   *acc,
                           AkInputSemantic semantic,
                           const char   *semantic_raw,
                           uint32_t      set) {
  AkInput *input;

  if (!heap || !morphable || !acc)
    return NULL;

  input = (AkInput *)ak_heap_calloc(heap, parent ? parent : morphable, sizeof(*input));
  if (!input)
    return NULL;

  input->accessor    = acc;
  input->semantic    = semantic;
  input->semanticRaw = semantic_raw;
  input->set         = set;
  input->next        = morphable->input;
  morphable->input   = input;
  morphable->inputCount++;

  return input;
}

static int
akb_export_add_morphable_input_buffer(AkHeap       *heap,
                                      AkDoc        *doc,
                                      void         *parent,
                                      AkMorphable  *morphable,
                                      const void   *data,
                                      size_t        length,
                                      uint32_t      vertex_count,
                                      AkComponentSize component_size,
                                      AkTypeId      component_type,
                                      uint32_t      component_count,
                                      AkInputSemantic semantic,
                                      const char   *semantic_raw,
                                      uint32_t      set) {
  AkTypeDesc *type_desc;
  AkBuffer   *buff;
  AkAccessor *acc;
  size_t      required;

  if (!heap || !doc || !morphable || !data || vertex_count == 0 || component_count == 0)
    return 0;

  type_desc = ak_typeDesc(component_type);
  if (!type_desc || type_desc->size <= 0)
    return 0;

  required = (size_t)vertex_count * component_count * (size_t)type_desc->size;
  if (length < required) {
    PyErr_SetString(PyExc_ValueError, "morph target buffer is smaller than declared vertex count");
    return 0;
  }

  buff = akb_export_buffer(heap, doc, morphable, data, required);
  acc  = akb_export_accessor(heap,
                             doc,
                             buff,
                             component_size,
                             component_type,
                             component_count,
                             vertex_count);
  if (!akb_export_morphable_input(heap, parent, morphable, acc, semantic, semantic_raw, set))
    return 0;

  return 1;
}

static AkFloatArray *
akb_export_float_array_from_sequence(AkHeap    *heap,
                                     void      *parent,
                                     PyObject  *seq_obj,
                                     uint32_t   expected_count) {
  AkFloatArray *out;
  PyObject     *seq;
  Py_ssize_t    count;
  Py_ssize_t    i;

  if (!seq_obj || seq_obj == Py_None || expected_count == 0)
    return NULL;

  seq = PySequence_Fast(seq_obj, "morph weights must be a sequence");
  if (!seq)
    return NULL;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count != (Py_ssize_t)expected_count) {
    Py_DECREF(seq);
    PyErr_SetString(PyExc_ValueError, "morph weight count must match target count");
    return NULL;
  }

  out = (AkFloatArray *)ak_heap_alloc(heap,
                                      parent,
                                      sizeof(*out) + sizeof(float) * expected_count);
  if (!out) {
    Py_DECREF(seq);
    PyErr_NoMemory();
    return NULL;
  }

  out->count = expected_count;
  for (i = 0; i < count; i++) {
    double value;

    value = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, i));
    if (PyErr_Occurred()) {
      Py_DECREF(seq);
      return NULL;
    }
    out->items[i] = (float)value;
  }

  Py_DECREF(seq);
  return out;
}

static int
akb_export_morph_begin(AkDoc               *doc,
                       AkbExportMorphBuild *build,
                       PyObject            *names_obj,
                       PyObject            *weights_obj,
                       uint32_t             target_count) {
  AkHeap        *heap;
  PyObject      *names_seq;
  AkMorphTarget *last_target;
  uint32_t       i;

  if (!doc || !build || target_count == 0)
    return 0;

  if (build->morph)
    return build->targetCount == target_count;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  names_seq = PySequence_Fast(names_obj, "morph target names must be a sequence");
  if (!names_seq)
    return 0;
  if (PySequence_Fast_GET_SIZE(names_seq) != (Py_ssize_t)target_count) {
    Py_DECREF(names_seq);
    PyErr_SetString(PyExc_ValueError, "morph target name count must match target count");
    return 0;
  }

  build->morph = (AkMorph *)ak_heap_calloc(heap, doc, sizeof(*build->morph));
  build->targets = (AkMorphTarget **)ak_heap_calloc(heap,
                                                    build->morph,
                                                    sizeof(*build->targets) * target_count);
  build->lastMorphables = (AkMorphable **)ak_heap_calloc(heap,
                                                         build->morph,
                                                         sizeof(*build->lastMorphables) * target_count);
  if (!build->morph || !build->targets || !build->lastMorphables) {
    Py_DECREF(names_seq);
    PyErr_NoMemory();
    return 0;
  }

  build->morph->method = AK_MORPH_METHOD_RELATIVE;
  build->morph->targetCount = target_count;
  build->morph->targetNames = (const char **)ak_heap_calloc(heap,
                                                            build->morph,
                                                            sizeof(*build->morph->targetNames)
                                                            * target_count);
  if (!build->morph->targetNames) {
    Py_DECREF(names_seq);
    PyErr_NoMemory();
    return 0;
  }

  build->morph->defaultWeights = akb_export_float_array_from_sequence(heap,
                                                                      build->morph,
                                                                      weights_obj,
                                                                      target_count);
  if (PyErr_Occurred()) {
    Py_DECREF(names_seq);
    return 0;
  }

  ak_setypeid(build->morph, AKT_MORPH);
  last_target = NULL;
  for (i = 0; i < target_count; i++) {
    AkMorphTarget *target;
    AkObject      *target_obj;
    PyObject      *name_obj;
    const char    *name;

    target = (AkMorphTarget *)ak_heap_calloc(heap, build->morph, sizeof(*target));
    target_obj = ak_objAlloc(heap,
                             target,
                             sizeof(AkMorphable),
                             AK_MORPHABLE_MORPHABLE,
                             true);
    if (!target || !target_obj) {
      Py_DECREF(names_seq);
      PyErr_NoMemory();
      return 0;
    }

    name_obj = PySequence_Fast_GET_ITEM(names_seq, (Py_ssize_t)i);
    name = PyUnicode_AsUTF8(name_obj);
    if (!name) {
      Py_DECREF(names_seq);
      return 0;
    }
    build->morph->targetNames[i] = ak_heap_strdup(heap, build->morph, name);

    target->target = target_obj;
    if (last_target)
      last_target->next = target;
    else
      build->morph->target = target;
    last_target = target;
    build->targets[i] = target;
  }

  Py_DECREF(names_seq);
  build->targetCount = target_count;
  AKB_LIB_APPEND(doc->lib.morphs, build->morph, next);

  return 1;
}

static int
akb_export_morph_add_primitive(AkDoc               *doc,
                               AkbExportMorphBuild *build,
                               PyObject            *positions_obj,
                               uint32_t             vertex_count) {
  AkHeap     *heap;
  PyObject   *seq;
  Py_ssize_t  count;
  Py_ssize_t  i;

  if (!doc || !build || !build->morph || !positions_obj || positions_obj == Py_None)
    return 1;

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  seq = PySequence_Fast(positions_obj, "morph target positions must be a sequence");
  if (!seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(seq);
  if (count != (Py_ssize_t)build->targetCount) {
    Py_DECREF(seq);
    PyErr_SetString(PyExc_ValueError, "morph target position count must match target count");
    return 0;
  }

  for (i = 0; i < count; i++) {
    AkMorphTarget *target;
    AkMorphable   *morphable;
    void          *input_parent;
    PyObject      *item;
    Py_buffer      view;
    int            ok;

    target = build->targets[i];
    if (!target || !target->target)
      continue;

    if (build->primitiveCount == 0) {
      morphable = (AkMorphable *)ak_objGet(target->target);
      input_parent = target->target;
    } else {
      morphable = (AkMorphable *)ak_heap_calloc(heap, target, sizeof(*morphable));
      if (!morphable) {
        Py_DECREF(seq);
        PyErr_NoMemory();
        return 0;
      }
      build->lastMorphables[i]->next = morphable;
      input_parent = morphable;
    }
    build->lastMorphables[i] = morphable;

    item = PySequence_Fast_GET_ITEM(seq, i);
    memset(&view, 0, sizeof(view));
    if (PyObject_GetBuffer(item, &view, PyBUF_SIMPLE) < 0) {
      Py_DECREF(seq);
      return 0;
    }

    ok = akb_export_add_morphable_input_buffer(heap,
                                               doc,
                                               input_parent,
                                               morphable,
                                               view.buf,
                                               (size_t)view.len,
                                               vertex_count,
                                               AK_COMPONENT_SIZE_VEC3,
                                               AKT_FLOAT,
                                               3,
                                               AK_INPUT_POSITION,
                                               "POSITION",
                                               0);
    PyBuffer_Release(&view);
    if (!ok) {
      Py_DECREF(seq);
      return 0;
    }

    target->primitiveCount++;
  }

  Py_DECREF(seq);
  build->primitiveCount++;
  return 1;
}

static int
akb_export_morph_add_primitive_buffers(AkDoc               *doc,
                                       AkbExportMorphBuild *build,
                                       float              **positions,
                                       uint32_t             target_count,
                                       uint32_t             vertex_count) {
  AkHeap   *heap;
  uint32_t  i;

  if (!doc || !build || !build->morph || !positions || target_count == 0)
    return 1;

  if (target_count != build->targetCount) {
    PyErr_SetString(PyExc_ValueError, "morph target position count must match target count");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap)
    return 0;

  for (i = 0; i < target_count; i++) {
    AkMorphTarget *target;
    AkMorphable   *morphable;
    void          *input_parent;

    target = build->targets[i];
    if (!target || !target->target || !positions[i])
      continue;

    if (build->primitiveCount == 0) {
      morphable = (AkMorphable *)ak_objGet(target->target);
      input_parent = target->target;
    } else {
      morphable = (AkMorphable *)ak_heap_calloc(heap, target, sizeof(*morphable));
      if (!morphable) {
        PyErr_NoMemory();
        return 0;
      }
      build->lastMorphables[i]->next = morphable;
      input_parent = morphable;
    }
    build->lastMorphables[i] = morphable;

    if (!akb_export_add_morphable_input_buffer(heap,
                                               doc,
                                               input_parent,
                                               morphable,
                                               positions[i],
                                               (size_t)vertex_count * 3u * sizeof(float),
                                               vertex_count,
                                               AK_COMPONENT_SIZE_VEC3,
                                               AKT_FLOAT,
                                               3,
                                               AK_INPUT_POSITION,
                                               "POSITION",
                                               0))
      return 0;

    target->primitiveCount++;
  }

  build->primitiveCount++;
  return 1;
}

static AkIndexArray *
akb_export_index_array_from_u32_max(AkHeap          *heap,
                                    AkMeshPrimitive *prim,
                                    const uint32_t  *src,
                                    size_t           count,
                                    uint32_t         max_index) {
  AkIndexArray *indices;
  AkTypeId      component_type;
  size_t        i;

  if (!heap || !prim || !src || count == 0)
    return NULL;
  if (count > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "mesh index count is too large");
    return NULL;
  }

  component_type = ak_indexComponentTypeForMax(max_index);
  indices = ak_indexArrayAlloc(heap, prim, count, component_type);
  if (!indices) {
    PyErr_NoMemory();
    return NULL;
  }
  indices->max = max_index;

  switch (component_type) {
    case AKT_UBYTE: {
      uint8_t *dst;

      dst = (uint8_t *)indices->items;
      for (i = 0; i < count; i++)
        dst[i] = (uint8_t)src[i];
      break;
    }
    case AKT_USHORT: {
      uint16_t *dst;

      dst = (uint16_t *)(void *)indices->items;
      for (i = 0; i < count; i++)
        dst[i] = (uint16_t)src[i];
      break;
    }
    case AKT_UINT: {
      uint32_t *dst;

      dst = (uint32_t *)(void *)indices->items;
      memcpy(dst, src, count * sizeof(*dst));
      break;
    }
    default:
      PyErr_SetString(PyExc_ValueError, "unsupported mesh index component type");
      return NULL;
  }

  return indices;
}

static AkIndexArray *
akb_export_index_array_from_u32(AkHeap          *heap,
                                AkMeshPrimitive *prim,
                                const uint32_t  *src,
                                size_t           count,
                                uint32_t         vertex_count) {
  uint32_t max_index;
  size_t   i;

  if (!heap || !prim || !src || count == 0)
    return NULL;
  if (count > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "mesh index count is too large");
    return NULL;
  }

  max_index = 0;
  for (i = 0; i < count; i++) {
    uint32_t value;

    value = src[i];
    if (value >= vertex_count) {
      PyErr_SetString(PyExc_ValueError, "mesh index references a missing vertex");
      return NULL;
    }
    if (value > max_index)
      max_index = value;
  }

  return akb_export_index_array_from_u32_max(heap, prim, src, count, max_index);
}

static AkIndexArray *
akb_export_index_array_from_i32(AkHeap          *heap,
                                AkMeshPrimitive *prim,
                                const int32_t   *src,
                                size_t           count,
                                uint32_t         vertex_count) {
  uint32_t *tmp;
  size_t    i;
  AkIndexArray *indices;

  if (!heap || !prim || !src || count == 0)
    return NULL;
  if (count > UINT32_MAX) {
    PyErr_SetString(PyExc_OverflowError, "mesh index count is too large");
    return NULL;
  }

  tmp = (uint32_t *)malloc(count * sizeof(*tmp));
  if (!tmp) {
    PyErr_NoMemory();
    return NULL;
  }

  for (i = 0; i < count; i++) {
    if (src[i] < 0 || (uint32_t)src[i] >= vertex_count) {
      free(tmp);
      PyErr_SetString(PyExc_ValueError, "mesh index references a missing vertex");
      return NULL;
    }
    tmp[i] = (uint32_t)src[i];
  }

  indices = akb_export_index_array_from_u32(heap, prim, tmp, count, vertex_count);
  free(tmp);
  return indices;
}

static AkIndexArray *
akb_export_indices_from_u32(AkHeap          *heap,
                            AkMeshPrimitive *prim,
                            const uint32_t  *src,
                            size_t           count,
                            uint32_t         vertex_count) {
  if (count % 3u != 0) {
    PyErr_SetString(PyExc_ValueError, "mesh index count must be divisible by three");
    return NULL;
  }
  return akb_export_index_array_from_u32(heap, prim, src, count, vertex_count);
}
