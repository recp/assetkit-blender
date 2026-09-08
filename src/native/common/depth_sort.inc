/* Stable, exact float32 depth ordering for the Gaussian viewport. */
static PyObject *
akb_sort_depth(PyObject *self, PyObject *arg) {
  const unsigned char *data;
  const char          *format;
  PyObject            *result;
  uint32_t            *keys, *scratch, *src, *dst, *swap;
  Py_buffer            buffer;
  size_t               count, i;
  uint32_t             histogram[4][256], bits, key, sum, n, index;
  unsigned int         pass, bin, shift;
  uint16_t             byte_order;

  (void)self;

  if (PyObject_GetBuffer(arg, &buffer, PyBUF_FORMAT | PyBUF_C_CONTIGUOUS) < 0)
    return NULL;

  byte_order = 1;
  format     = buffer.format;

  if (format && (*format == '@' || *format == '='
                 || (*format == '<' && *(unsigned char *)&byte_order)
                 || (*format == '>' && !*(unsigned char *)&byte_order)))
    format++;

  if (buffer.itemsize != 4 || !format || strcmp(format, "f")
      || buffer.len % 4 || (uint64_t)buffer.len / 4 > UINT32_MAX) {
    PyBuffer_Release(&buffer);
    PyErr_SetString(PyExc_ValueError, "Expected a contiguous native float32 depth buffer");
    return NULL;
  }

  count  = (size_t)buffer.len / 4;
  result = PyBytes_FromStringAndSize(NULL, buffer.len);

  if (!result || !count) {
    PyBuffer_Release(&buffer);
    return result;
  }

  keys    = malloc(count * sizeof(*keys));
  scratch = malloc(count * sizeof(*scratch));

  if (!keys || !scratch) {
    free(keys);
    free(scratch);
    Py_DECREF(result);
    PyBuffer_Release(&buffer);
    return PyErr_NoMemory();
  }

  data = buffer.buf;
  src  = (uint32_t *)PyBytes_AS_STRING(result);
  dst  = scratch;
  memset(histogram, 0, sizeof(histogram));

  /* Snapshot the keys before releasing the GIL: the caller may own mutable data. */
  for (i = 0; i < count; i++) {
    memcpy(&bits, data + i * 4, sizeof(bits));

    if ((bits & UINT32_C(0x7fffffff)) >= UINT32_C(0x7f800000)) {
      free(keys);
      free(scratch);
      Py_DECREF(result);
      PyBuffer_Release(&buffer);
      PyErr_SetString(PyExc_ValueError, "Depth values must be finite");
      return NULL;
    }

    if (!(bits & UINT32_C(0x7fffffff)))
      bits = 0;

    key     = bits ^ ((bits >> 31) ? UINT32_MAX : UINT32_C(0x80000000));
    keys[i] = key;
    src[i]  = (uint32_t)i;

    histogram[0][ key        & 255]++;
    histogram[1][(key >>  8) & 255]++;
    histogram[2][(key >> 16) & 255]++;
    histogram[3][ key >> 24       ]++;
  }

  PyBuffer_Release(&buffer);
  Py_BEGIN_ALLOW_THREADS

  for (pass = 0; pass < 4; pass++) {
    sum   = 0;
    shift = pass * 8;

    for (bin = 0; bin < 256; bin++) {
      n                   = histogram[pass][bin];
      histogram[pass][bin] = sum;
      sum                 += n;
    }

    for (i = 0; i < count; i++) {
      index = src[i];
      bin   = (keys[index] >> shift) & 255;
      dst[histogram[pass][bin]++] = index;
    }

    swap = src;
    src  = dst;
    dst  = swap;
  }

  Py_END_ALLOW_THREADS
  free(keys);
  free(scratch);
  return result;
}
