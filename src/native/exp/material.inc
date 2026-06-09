static AkMaterialInput *
akb_export_material_color(AkHeap            *heap,
                          AkMaterialSurface *surface,
                          AkMaterialSemantic semantic,
                          AkTextureChannels  channels,
                          AkTextureColorSpace color_space,
                          const float        color[4]) {
  AkMaterialInput *input;

  input = (AkMaterialInput *)ak_heap_calloc(heap, surface, sizeof(*input));
  if (!input) {
    PyErr_NoMemory();
    return NULL;
  }

  input->semantic     = ak_materialSemanticName(semantic);
  input->source       = AK_MATERIAL_INPUT_CONSTANT;
  input->valueType    = AK_MATERIAL_VALUE_COLOR;
  input->channels     = channels;
  input->colorSpace   = color_space;
  input->color.rgba.R = color[0];
  input->color.rgba.G = color[1];
  input->color.rgba.B = color[2];
  input->color.rgba.A = color[3];

  return input;
}

static AkMaterialInput *
akb_export_material_scalar(AkHeap              *heap,
                           AkMaterialSurface   *surface,
                           AkMaterialSemantic   semantic,
                           float                value,
                           AkTextureChannels    channels) {
  AkMaterialInput *input;

  input = (AkMaterialInput *)ak_heap_calloc(heap, surface, sizeof(*input));
  if (!input) {
    PyErr_NoMemory();
    return NULL;
  }

  input->semantic   = ak_materialSemanticName(semantic);
  input->source     = AK_MATERIAL_INPUT_CONSTANT;
  input->valueType  = AK_MATERIAL_VALUE_FLOAT;
  input->channels   = channels;
  input->colorSpace = AK_TEXTURE_COLORSPACE_LINEAR;
  input->value[0]   = value;

  return input;
}

static AkTexture *
akb_export_find_texture_uri(AkDoc       *doc,
                            const char  *uri,
                            AkWrapMode   wrapS,
                            AkWrapMode   wrapT,
                            AkWrapMode   wrapP,
                            AkMinFilter  minfilter,
                            AkMagFilter  magfilter,
                            AkMipFilter  mipfilter) {
  AkTexture *texture;

  if (!doc || !uri || !uri[0])
    return NULL;

  for (texture = doc->lib.textures.first; texture; texture = texture->next) {
    AkImageSource *source;

    if (!texture->image)
      continue;
    source = texture->image->source;
    if (!source || source->type != AK_IMAGE_SOURCE_URI || !source->uri)
      continue;
    if (strcmp(source->uri, uri) == 0) {
      if (texture->sampler
          && texture->sampler->wrapS == wrapS
          && texture->sampler->wrapT == wrapT
          && texture->sampler->wrapP == wrapP
          && texture->sampler->minfilter == minfilter
          && texture->sampler->magfilter == magfilter
          && texture->sampler->mipfilter == mipfilter)
        return texture;
    }
  }

  return NULL;
}

static int
akb_export_apply_object_extra(AkDoc *doc, void *obj, PyObject *extra_obj);

static int
akb_export_texinfo(PyObject     *info_obj,
                   AkWrapMode   *wrapS,
                   AkWrapMode   *wrapT,
                   AkWrapMode   *wrapP,
                   AkMinFilter  *minfilter,
                   AkMagFilter  *magfilter,
                   AkMipFilter  *mipfilter,
                   PyObject    **transform_out,
                   PyObject    **texture_extra_out,
                   PyObject    **texref_extra_out,
                   PyObject    **image_extra_out,
                   PyObject    **sampler_extra_out) {
  int wrap_s;
  int wrap_t;
  int wrap_p;
  int min_filter;
  int mag_filter;
  int mip_filter;
  PyObject *transform_obj;
  PyObject *texture_extra_obj;
  PyObject *texref_extra_obj;
  PyObject *image_extra_obj;
  PyObject *sampler_extra_obj;
  Py_ssize_t info_size;

  if (transform_out)
    *transform_out = Py_None;
  if (texture_extra_out)
    *texture_extra_out = Py_None;
  if (texref_extra_out)
    *texref_extra_out = Py_None;
  if (image_extra_out)
    *image_extra_out = Py_None;
  if (sampler_extra_out)
    *sampler_extra_out = Py_None;
  if (!info_obj || info_obj == Py_None)
    return 1;

  transform_obj = Py_None;
  texture_extra_obj = Py_None;
  texref_extra_obj = Py_None;
  image_extra_obj = Py_None;
  sampler_extra_obj = Py_None;
  info_size = PyTuple_Check(info_obj) ? PyTuple_Size(info_obj) : -1;
  if (info_size == 11) {
    if (!PyArg_ParseTuple(info_obj,
                          "iiiiiiOOOOO",
                          &wrap_s,
                          &wrap_t,
                          &wrap_p,
                          &min_filter,
                          &mag_filter,
                          &mip_filter,
                          &transform_obj,
                          &texture_extra_obj,
                          &texref_extra_obj,
                          &image_extra_obj,
                          &sampler_extra_obj))
      return 0;
  } else if (info_size == 7) {
    if (!PyArg_ParseTuple(info_obj,
                          "iiiiiiO",
                          &wrap_s,
                          &wrap_t,
                          &wrap_p,
                          &min_filter,
                          &mag_filter,
                          &mip_filter,
                          &transform_obj))
      return 0;
  } else {
    if (!PyArg_ParseTuple(info_obj,
                          "iiiiO",
                          &wrap_s,
                          &wrap_t,
                          &min_filter,
                          &mag_filter,
                          &transform_obj))
      return 0;
    wrap_p = wrap_t;
    mip_filter = AK_MIPFILTER_LINEAR;
  }

  *wrapS = (AkWrapMode)wrap_s;
  *wrapT = (AkWrapMode)wrap_t;
  if (wrapP)
    *wrapP = (AkWrapMode)wrap_p;
  *minfilter = (AkMinFilter)min_filter;
  *magfilter = (AkMagFilter)mag_filter;
  if (mipfilter)
    *mipfilter = (AkMipFilter)mip_filter;
  if (transform_out)
    *transform_out = transform_obj ? transform_obj : Py_None;
  if (texture_extra_out)
    *texture_extra_out = texture_extra_obj ? texture_extra_obj : Py_None;
  if (texref_extra_out)
    *texref_extra_out = texref_extra_obj ? texref_extra_obj : Py_None;
  if (image_extra_out)
    *image_extra_out = image_extra_obj ? image_extra_obj : Py_None;
  if (sampler_extra_out)
    *sampler_extra_out = sampler_extra_obj ? sampler_extra_obj : Py_None;
  return 1;
}

static int
akb_export_texref_transform(AkHeap       *heap,
                            AkTextureRef *texref,
                            PyObject     *transform_obj) {
  AkTextureTransform *transform;
  double offset_x;
  double offset_y;
  double rotation;
  double scale_x;
  double scale_y;
  int slot;

  if (!heap || !texref || !transform_obj || transform_obj == Py_None)
    return 1;

  if (!PyArg_ParseTuple(transform_obj,
                        "dddddi",
                        &offset_x,
                        &offset_y,
                        &rotation,
                        &scale_x,
                        &scale_y,
                        &slot))
    return 0;

  transform = (AkTextureTransform *)ak_heap_calloc(heap, texref, sizeof(*transform));
  if (!transform) {
    PyErr_NoMemory();
    return 0;
  }
  transform->offset[0] = (float)offset_x;
  transform->offset[1] = (float)offset_y;
  transform->rotation = (float)rotation;
  transform->scale[0] = (float)scale_x;
  transform->scale[1] = (float)scale_y;
  transform->slot = slot;
  transform->coordInputName = "TEXCOORD";
  texref->transform = transform;
  return 1;
}

static AkTextureRef *
akb_export_texref(AkDoc               *doc,
                  void                *parent,
                  const char          *uri,
                  AkTextureColorSpace  color_space,
                  AkTextureChannels    channels,
                  int32_t              slot,
                  PyObject            *info_obj) {
  AkHeap        *heap;
  AkImage       *image;
  AkImageSource *source;
  AkSampler     *sampler;
  AkTexture     *texture;
  AkTextureRef  *texref;
  PyObject      *transform_obj;
  PyObject      *texture_extra_obj;
  PyObject      *texref_extra_obj;
  PyObject      *image_extra_obj;
  PyObject      *sampler_extra_obj;
  AkWrapMode     wrapS;
  AkWrapMode     wrapT;
  AkWrapMode     wrapP;
  AkMinFilter    minfilter;
  AkMagFilter    magfilter;
  AkMipFilter    mipfilter;

  if (!doc || !uri || !uri[0])
    return NULL;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyErr_NoMemory();
    return NULL;
  }

  wrapS = AK_WRAP_MODE_WRAP;
  wrapT = AK_WRAP_MODE_WRAP;
  wrapP = AK_WRAP_MODE_WRAP;
  minfilter = AK_MINFILTER_LINEAR;
  magfilter = AK_MAGFILTER_LINEAR;
  mipfilter = AK_MIPFILTER_LINEAR;
  transform_obj = Py_None;
  texture_extra_obj = Py_None;
  texref_extra_obj = Py_None;
  image_extra_obj = Py_None;
  sampler_extra_obj = Py_None;
  if (!akb_export_texinfo(info_obj,
                          &wrapS,
                          &wrapT,
                          &wrapP,
                          &minfilter,
                          &magfilter,
                          &mipfilter,
                          &transform_obj,
                          &texture_extra_obj,
                          &texref_extra_obj,
                          &image_extra_obj,
                          &sampler_extra_obj))
    return NULL;

  texture = NULL;
  if ((!texture_extra_obj || texture_extra_obj == Py_None)
      && (!image_extra_obj || image_extra_obj == Py_None)
      && (!sampler_extra_obj || sampler_extra_obj == Py_None)) {
    texture = akb_export_find_texture_uri(doc,
                                          uri,
                                          wrapS,
                                          wrapT,
                                          wrapP,
                                          minfilter,
                                          magfilter,
                                          mipfilter);
  }
  if (texture) {
    texref = (AkTextureRef *)ak_heap_calloc(heap, parent, sizeof(*texref));
    if (!texref) {
      PyErr_NoMemory();
      return NULL;
    }
    ak_setypeid(texref, AKT_TEXTURE_REF);
    texref->texture        = texture;
    texref->coordInputName = "TEXCOORD";
    texref->slot           = slot;
    ak_texref_usage(texref, color_space, channels);
    if (!akb_export_texref_transform(heap, texref, transform_obj))
      return NULL;
    if (!akb_export_apply_object_extra(doc, texref, texref_extra_obj))
      return NULL;
    return texref;
  }

  image = (AkImage *)ak_heap_calloc(heap, doc, sizeof(*image));
  source = (AkImageSource *)ak_heap_calloc(heap, image, sizeof(*source));
  sampler = (AkSampler *)ak_heap_calloc(heap, doc, sizeof(*sampler));
  texture = (AkTexture *)ak_heap_calloc(heap, doc, sizeof(*texture));
  texref = (AkTextureRef *)ak_heap_calloc(heap, parent, sizeof(*texref));
  if (!image || !source || !sampler || !texture || !texref) {
    PyErr_NoMemory();
    return NULL;
  }

  source->type = AK_IMAGE_SOURCE_URI;
  source->uri  = uri;
  image->source = source;
  AKB_LIB_APPEND(doc->lib.images, image, next);

  sampler->wrapS = wrapS;
  sampler->wrapT = wrapT;
  sampler->wrapP = wrapP;
  sampler->minfilter = minfilter;
  sampler->magfilter = magfilter;
  sampler->mipfilter = mipfilter;
  ak_setypeid(sampler, AKT_SAMPLER2D);
  AKB_LIB_APPEND(doc->lib.samplers, sampler, next);

  texture->type    = AKT_SAMPLER2D;
  texture->image   = image;
  texture->sampler = sampler;
  AKB_LIB_APPEND(doc->lib.textures, texture, next);

  ak_setypeid(texref, AKT_TEXTURE_REF);
  texref->texture        = texture;
  texref->coordInputName = "TEXCOORD";
  texref->slot           = slot;
  ak_texref_usage(texref, color_space, channels);
  if (!akb_export_texref_transform(heap, texref, transform_obj))
    return NULL;
  if (!akb_export_apply_object_extra(doc, texture, texture_extra_obj)
      || !akb_export_apply_object_extra(doc, texref, texref_extra_obj)
      || !akb_export_apply_object_extra(doc, image, image_extra_obj)
      || !akb_export_apply_object_extra(doc, sampler, sampler_extra_obj))
    return NULL;

  return texref;
}

static void
akb_export_material_feature_append(AkMaterialSurface *surface,
                                   AkMaterialFeature *feature) {
  if (!surface || !feature)
    return;
  feature->next = surface->features;
  surface->features = feature;
}

static AkMaterialInput *
akb_export_feature_scalar_input(AkDoc               *doc,
                                void                *parent,
                                float                value,
                                AkTextureChannels    channels,
                                AkTextureColorSpace  color_space,
                                const char          *uri,
                                int32_t              slot,
                                PyObject            *info_obj) {
  AkHeap          *heap;
  AkMaterialInput *input;
  AkTextureRef    *texref;

  if (!doc || !parent)
    return NULL;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyErr_NoMemory();
    return NULL;
  }

  input = (AkMaterialInput *)ak_heap_calloc(heap, parent, sizeof(*input));
  if (!input) {
    PyErr_NoMemory();
    return NULL;
  }

  input->source     = AK_MATERIAL_INPUT_CONSTANT;
  input->valueType  = AK_MATERIAL_VALUE_FLOAT;
  input->channels   = channels;
  input->colorSpace = color_space;
  input->value[0]   = value;

  texref = akb_export_texref(doc,
                             input,
                             uri,
                             color_space,
                             channels,
                             slot,
                             info_obj);
  if (PyErr_Occurred())
    return NULL;
  if (texref) {
    input->texture = texref;
    input->source  = AK_MATERIAL_INPUT_TEXTURE;
  }

  return input;
}

static AkMaterialInput *
akb_export_feature_color_input(AkDoc               *doc,
                               void                *parent,
                               PyObject            *color_obj,
                               float                fallback,
                               AkTextureChannels    channels,
                               AkTextureColorSpace  color_space,
                               const char          *uri,
                               int32_t              slot,
                               PyObject            *info_obj) {
  AkHeap          *heap;
  AkMaterialInput *input;
  AkTextureRef    *texref;
  Py_buffer        view;
  const float     *color;

  if (!doc || !parent || !color_obj)
    return NULL;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyErr_NoMemory();
    return NULL;
  }

  memset(&view, 0, sizeof(view));
  if (PyObject_GetBuffer(color_obj, &view, PyBUF_SIMPLE) < 0)
    return NULL;
  if (view.len < (Py_ssize_t)(4u * sizeof(float))) {
    PyBuffer_Release(&view);
    PyErr_SetString(PyExc_ValueError, "material feature color buffer must hold four float values");
    return NULL;
  }

  input = (AkMaterialInput *)ak_heap_calloc(heap, parent, sizeof(*input));
  if (!input) {
    PyBuffer_Release(&view);
    PyErr_NoMemory();
    return NULL;
  }

  color = (const float *)view.buf;
  input->source       = AK_MATERIAL_INPUT_CONSTANT;
  input->valueType    = AK_MATERIAL_VALUE_COLOR;
  input->channels     = channels;
  input->colorSpace   = color_space;
  input->color.rgba.R = color[0];
  input->color.rgba.G = color[1];
  input->color.rgba.B = color[2];
  input->color.rgba.A = color[3];
  PyBuffer_Release(&view);

  texref = akb_export_texref(doc,
                             input,
                             uri,
                             color_space,
                             channels,
                             slot,
                             info_obj);
  if (PyErr_Occurred())
    return NULL;
  if (texref) {
    input->texture = texref;
    input->source  = AK_MATERIAL_INPUT_TEXTURE;
  }

  (void)fallback;
  return input;
}

static int
akb_export_material_features(AkDoc             *doc,
                             AkMaterialSurface *surface,
                             PyObject          *features_obj) {
  PyObject   *features_seq;
  Py_ssize_t  count;

  if (!features_obj || features_obj == Py_None)
    return 1;

  features_seq = PySequence_Fast(features_obj, "material features must be a sequence");
  if (!features_seq)
    return 0;

  count = PySequence_Fast_GET_SIZE(features_seq);
  for (Py_ssize_t i = 0; i < count; i++) {
    PyObject   *item;
    Py_ssize_t  item_size;
    long        feature_type;

    item = PySequence_Fast_GET_ITEM(features_seq, i);
    if (!PyTuple_Check(item) || PyTuple_Size(item) < 1) {
      Py_DECREF(features_seq);
      PyErr_SetString(PyExc_ValueError, "material feature item must be a tuple");
      return 0;
    }

    item_size = PyTuple_Size(item);
    feature_type = PyLong_AsLong(PyTuple_GET_ITEM(item, 0));
    if (PyErr_Occurred()) {
      Py_DECREF(features_seq);
      return 0;
    }

    switch (feature_type) {
      case AKB_EXPORT_MATERIAL_FEATURE_IOR: {
        double ior;

        if (item_size != 2
            || !PyArg_ParseTuple(item, "ld", &feature_type, &ior)) {
          Py_DECREF(features_seq);
          return 0;
        }
        surface->ior = (float)ior;
        surface->flags |= AK_MATERIAL_FLAG_HAS_IOR;
        break;
      }
      case AK_MATERIAL_FEATURE_CLEARCOAT: {
        AkHeap *heap;
        AkMaterialClearcoatFeature *feature;
        const char *factor_uri;
        const char *roughness_uri;
        const char *normal_uri;
        PyObject *factor_info;
        PyObject *roughness_info;
        PyObject *normal_info;
        double factor;
        double roughness;
        double normal_scale;
        int factor_slot;
        int roughness_slot;
        int normal_slot;

        if (item_size != 13
            || !PyArg_ParseTuple(item,
                                 "ldziOdziOzidO",
                                 &feature_type,
                                 &factor,
                                 &factor_uri,
                                 &factor_slot,
                                 &factor_info,
                                 &roughness,
                                 &roughness_uri,
                                 &roughness_slot,
                                 &roughness_info,
                                 &normal_uri,
                                 &normal_slot,
                                 &normal_scale,
                                 &normal_info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_CLEARCOAT;
        feature->factor = akb_export_feature_scalar_input(doc,
                                                          feature,
                                                          (float)factor,
                                                          AK_TEXTURE_CHANNEL_R,
                                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                                          factor_uri,
                                                          factor_slot,
                                                          factor_info);
        feature->roughness = akb_export_feature_scalar_input(doc,
                                                             feature,
                                                             (float)roughness,
                                                             AK_TEXTURE_CHANNEL_G,
                                                             AK_TEXTURE_COLORSPACE_LINEAR,
                                                             roughness_uri,
                                                             roughness_slot,
                                                             roughness_info);
        feature->normalScale = (float)normal_scale;
        if (normal_uri && normal_uri[0]) {
          feature->normal = akb_export_feature_scalar_input(doc,
                                                            feature,
                                                            (float)normal_scale,
                                                            AK_TEXTURE_CHANNEL_RGB,
                                                            AK_TEXTURE_COLORSPACE_LINEAR,
                                                            normal_uri,
                                                            normal_slot,
                                                            normal_info);
        }
        if (!feature->factor || !feature->roughness || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_SPECULAR: {
        AkHeap *heap;
        AkMaterialSpecularFeature *feature;
        const char *factor_uri;
        const char *color_uri;
        PyObject *factor_info;
        PyObject *color_obj;
        PyObject *color_info;
        double factor;
        int factor_slot;
        int color_slot;

        if (item_size != 9
            || !PyArg_ParseTuple(item,
                                 "ldziOOziO",
                                 &feature_type,
                                 &factor,
                                 &factor_uri,
                                 &factor_slot,
                                 &factor_info,
                                 &color_obj,
                                 &color_uri,
                                 &color_slot,
                                 &color_info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_SPECULAR;
        feature->factor = akb_export_feature_scalar_input(doc,
                                                          feature,
                                                          (float)factor,
                                                          AK_TEXTURE_CHANNEL_A,
                                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                                          factor_uri,
                                                          factor_slot,
                                                          factor_info);
        feature->color = akb_export_feature_color_input(doc,
                                                        feature,
                                                        color_obj,
                                                        1.0f,
                                                        AK_TEXTURE_CHANNEL_RGB,
                                                        AK_TEXTURE_COLORSPACE_SRGB,
                                                        color_uri,
                                                        color_slot,
                                                        color_info);
        if (!feature->factor || !feature->color || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_SPECULAR_GLOSSINESS: {
        AkHeap *heap;
        AkMaterialSpecularGlossinessFeature *feature;
        const char *diffuse_uri;
        const char *specular_uri;
        const char *glossiness_uri;
        PyObject *diffuse_obj;
        PyObject *diffuse_info;
        PyObject *specular_obj;
        PyObject *specular_info;
        PyObject *glossiness_info;
        double glossiness;
        int diffuse_slot;
        int specular_slot;
        int glossiness_slot;

        if (item_size != 13
            || !PyArg_ParseTuple(item,
                                 "lOziOOziOdziO",
                                 &feature_type,
                                 &diffuse_obj,
                                 &diffuse_uri,
                                 &diffuse_slot,
                                 &diffuse_info,
                                 &specular_obj,
                                 &specular_uri,
                                 &specular_slot,
                                 &specular_info,
                                 &glossiness,
                                 &glossiness_uri,
                                 &glossiness_slot,
                                 &glossiness_info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_SPECULAR_GLOSSINESS;
        feature->diffuse = akb_export_feature_color_input(doc,
                                                          feature,
                                                          diffuse_obj,
                                                          1.0f,
                                                          AK_TEXTURE_CHANNEL_RGBA,
                                                          AK_TEXTURE_COLORSPACE_SRGB,
                                                          diffuse_uri,
                                                          diffuse_slot,
                                                          diffuse_info);
        feature->specular = akb_export_feature_color_input(doc,
                                                           feature,
                                                           specular_obj,
                                                           1.0f,
                                                           AK_TEXTURE_CHANNEL_RGB,
                                                           AK_TEXTURE_COLORSPACE_SRGB,
                                                           specular_uri,
                                                           specular_slot,
                                                           specular_info);
        feature->glossiness = akb_export_feature_scalar_input(doc,
                                                              feature,
                                                              (float)glossiness,
                                                              AK_TEXTURE_CHANNEL_A,
                                                              AK_TEXTURE_COLORSPACE_LINEAR,
                                                              glossiness_uri,
                                                              glossiness_slot,
                                                              glossiness_info);
        if (!feature->diffuse || !feature->specular || !feature->glossiness || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_TRANSMISSION: {
        AkHeap *heap;
        AkMaterialTransmissionFeature *feature;
        const char *uri;
        PyObject *info;
        double factor;
        int slot;

        if (item_size != 5
            || !PyArg_ParseTuple(item,
                                 "ldziO",
                                 &feature_type,
                                 &factor,
                                 &uri,
                                 &slot,
                                 &info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_TRANSMISSION;
        feature->factor = akb_export_feature_scalar_input(doc,
                                                          feature,
                                                          (float)factor,
                                                          AK_TEXTURE_CHANNEL_R,
                                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                                          uri,
                                                          slot,
                                                          info);
        if (!feature->factor || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_SHEEN: {
        AkHeap *heap;
        AkMaterialSheenFeature *feature;
        const char *color_uri;
        const char *roughness_uri;
        PyObject *color_obj;
        PyObject *color_info;
        PyObject *roughness_info;
        double roughness;
        int color_slot;
        int roughness_slot;

        if (item_size != 9
            || !PyArg_ParseTuple(item,
                                 "lOziOdziO",
                                 &feature_type,
                                 &color_obj,
                                 &color_uri,
                                 &color_slot,
                                 &color_info,
                                 &roughness,
                                 &roughness_uri,
                                 &roughness_slot,
                                 &roughness_info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_SHEEN;
        feature->color = akb_export_feature_color_input(doc,
                                                        feature,
                                                        color_obj,
                                                        0.0f,
                                                        AK_TEXTURE_CHANNEL_RGB,
                                                        AK_TEXTURE_COLORSPACE_SRGB,
                                                        color_uri,
                                                        color_slot,
                                                        color_info);
        feature->roughness = akb_export_feature_scalar_input(doc,
                                                             feature,
                                                             (float)roughness,
                                                             AK_TEXTURE_CHANNEL_A,
                                                             AK_TEXTURE_COLORSPACE_LINEAR,
                                                             roughness_uri,
                                                             roughness_slot,
                                                             roughness_info);
        if (!feature->color || !feature->roughness || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_IRIDESCENCE: {
        AkHeap *heap;
        AkMaterialIridescenceFeature *feature;
        const char *factor_uri;
        const char *thickness_uri;
        PyObject *factor_info;
        PyObject *thickness_info;
        double factor;
        double thickness;
        double ior;
        double thickness_min;
        double thickness_max;
        int factor_slot;
        int thickness_slot;

        factor_uri = NULL;
        thickness_uri = NULL;
        factor_info = Py_None;
        thickness_info = Py_None;
        factor_slot = 0;
        thickness_slot = 0;

        if (item_size == 6) {
          if (!PyArg_ParseTuple(item,
                                "lddddd",
                                &feature_type,
                                &factor,
                                &thickness,
                                &ior,
                                &thickness_min,
                                &thickness_max)) {
            Py_DECREF(features_seq);
            return 0;
          }
        } else if (item_size == 12) {
          if (!PyArg_ParseTuple(item,
                                "ldziOdziOddd",
                                &feature_type,
                                &factor,
                                &factor_uri,
                                &factor_slot,
                                &factor_info,
                                &thickness,
                                &thickness_uri,
                                &thickness_slot,
                                &thickness_info,
                                &ior,
                                &thickness_min,
                                &thickness_max)) {
            Py_DECREF(features_seq);
            return 0;
          }
        } else {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_IRIDESCENCE;
        feature->factor = akb_export_feature_scalar_input(doc,
                                                          feature,
                                                          (float)factor,
                                                          AK_TEXTURE_CHANNEL_R,
                                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                                          factor_uri,
                                                          factor_slot,
                                                          factor_info);
        feature->thickness = akb_export_feature_scalar_input(doc,
                                                             feature,
                                                             (float)thickness,
                                                             AK_TEXTURE_CHANNEL_G,
                                                             AK_TEXTURE_COLORSPACE_LINEAR,
                                                             thickness_uri,
                                                             thickness_slot,
                                                             thickness_info);
        feature->ior = (float)ior;
        feature->thicknessMinimum = (float)thickness_min;
        feature->thicknessMaximum = (float)thickness_max;
        if (!feature->factor || !feature->thickness || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_VOLUME: {
        AkHeap *heap;
        AkMaterialVolumeFeature *feature;
        const char *uri;
        PyObject *info;
        PyObject *color_obj;
        Py_buffer color_view;
        double thickness;
        double attenuation_distance;
        int slot;

        if (item_size != 7
            || !PyArg_ParseTuple(item,
                                 "ldziOOd",
                                 &feature_type,
                                 &thickness,
                                 &uri,
                                 &slot,
                                 &info,
                                 &color_obj,
                                 &attenuation_distance)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        memset(&color_view, 0, sizeof(color_view));
        if (PyObject_GetBuffer(color_obj, &color_view, PyBUF_SIMPLE) < 0) {
          Py_DECREF(features_seq);
          return 0;
        }
        if (color_view.len >= (Py_ssize_t)(3u * sizeof(float))) {
          const float *color = (const float *)color_view.buf;
          feature->attenuationColor.vec[0] = color[0];
          feature->attenuationColor.vec[1] = color[1];
          feature->attenuationColor.vec[2] = color[2];
          feature->attenuationColor.vec[3] = color_view.len >= (Py_ssize_t)(4u * sizeof(float))
                                             ? color[3]
                                             : 1.0f;
        }
        PyBuffer_Release(&color_view);
        feature->base.type = AK_MATERIAL_FEATURE_VOLUME;
        feature->attenuationDistance = (float)attenuation_distance;
        feature->thickness = akb_export_feature_scalar_input(doc,
                                                             feature,
                                                             (float)thickness,
                                                             AK_TEXTURE_CHANNEL_G,
                                                             AK_TEXTURE_COLORSPACE_LINEAR,
                                                             uri,
                                                             slot,
                                                             info);
        if (!feature->thickness || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_ANISOTROPY: {
        AkHeap *heap;
        AkMaterialAnisotropyFeature *feature;
        const char *uri;
        PyObject *info;
        double strength;
        double rotation;
        int slot;

        if (item_size != 6
            || !PyArg_ParseTuple(item,
                                 "ldziOd",
                                 &feature_type,
                                 &strength,
                                 &uri,
                                 &slot,
                                 &info,
                                 &rotation)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_ANISOTROPY;
        feature->strength = akb_export_feature_scalar_input(doc,
                                                            feature,
                                                            (float)strength,
                                                            AK_TEXTURE_CHANNEL_B,
                                                            AK_TEXTURE_COLORSPACE_LINEAR,
                                                            uri,
                                                            slot,
                                                            info);
        feature->rotation = akb_export_feature_scalar_input(doc,
                                                            feature,
                                                            (float)rotation,
                                                            AK_TEXTURE_CHANNEL_NONE,
                                                            AK_TEXTURE_COLORSPACE_LINEAR,
                                                            NULL,
                                                            0,
                                                            Py_None);
        if (!feature->strength || !feature->rotation || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_DISPERSION: {
        AkHeap *heap;
        AkMaterialDispersionFeature *feature;
        double dispersion;

        if (item_size != 2
            || !PyArg_ParseTuple(item, "ld", &feature_type, &dispersion)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_DISPERSION;
        feature->dispersion = (float)dispersion;
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION: {
        AkHeap *heap;
        AkMaterialDiffuseTransmissionFeature *feature;
        const char *factor_uri;
        const char *color_uri;
        PyObject *factor_info;
        PyObject *color_obj;
        PyObject *color_info;
        double factor;
        int factor_slot;
        int color_slot;

        if (item_size != 9
            || !PyArg_ParseTuple(item,
                                 "ldziOOziO",
                                 &feature_type,
                                 &factor,
                                 &factor_uri,
                                 &factor_slot,
                                 &factor_info,
                                 &color_obj,
                                 &color_uri,
                                 &color_slot,
                                 &color_info)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION;
        feature->factor = akb_export_feature_scalar_input(doc,
                                                          feature,
                                                          (float)factor,
                                                          AK_TEXTURE_CHANNEL_A,
                                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                                          factor_uri,
                                                          factor_slot,
                                                          factor_info);
        feature->color = akb_export_feature_color_input(doc,
                                                        feature,
                                                        color_obj,
                                                        1.0f,
                                                        AK_TEXTURE_CHANNEL_RGB,
                                                        AK_TEXTURE_COLORSPACE_SRGB,
                                                        color_uri,
                                                        color_slot,
                                                        color_info);
        if (!feature->factor || !feature->color || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      case AK_MATERIAL_FEATURE_SUBSURFACE: {
        AkHeap *heap;
        AkMaterialSubsurfaceFeature *feature;
        PyObject *color_obj;
        PyObject *radius_obj;
        double weight;
        double anisotropy;

        if (item_size != 5
            || !PyArg_ParseTuple(item,
                                 "ldOOd",
                                 &feature_type,
                                 &weight,
                                 &color_obj,
                                 &radius_obj,
                                 &anisotropy)) {
          Py_DECREF(features_seq);
          return 0;
        }

        heap = ak_heap_getheap(doc);
        feature = heap ? ak_heap_calloc(heap, surface, sizeof(*feature)) : NULL;
        if (!feature) {
          Py_DECREF(features_seq);
          PyErr_NoMemory();
          return 0;
        }
        feature->base.type = AK_MATERIAL_FEATURE_SUBSURFACE;
        /* glTF export maps this AssetKit feature to
         * KHR_materials_volume_scatter, which only carries scatter color and
         * anisotropy.  The core exporter rejects non-empty weight/radius
         * inputs for this extension, so keep those fields empty here.
         */
        feature->color = akb_export_feature_color_input(doc,
                                                        feature,
                                                        color_obj,
                                                        0.0f,
                                                        AK_TEXTURE_CHANNEL_RGB,
                                                        AK_TEXTURE_COLORSPACE_SRGB,
                                                        NULL,
                                                        0,
                                                        Py_None);
        feature->anisotropy = (float)anisotropy;
        if (!feature->color || PyErr_Occurred()) {
          Py_DECREF(features_seq);
          return 0;
        }
        (void)weight;
        (void)radius_obj;
        akb_export_material_feature_append(surface, &feature->base);
        break;
      }
      default:
        break;
    }
  }

  Py_DECREF(features_seq);
  return 1;
}

static int
akb_export_add_material_animations(AkDoc      *doc,
                                   AkMaterial *mat,
                                   PyObject   *animation_obj);

static AkMaterial *
akb_export_material(AkDoc *doc, PyObject *obj) {
  AkHeap            *heap;
  AkMaterial        *mat;
  AkMaterialSurface *surface;
  AkTextureRef      *base_color_texture;
  PyObject          *color_obj;
  PyObject          *emissive_color_obj;
  PyObject          *base_color_info_obj;
  PyObject          *opacity_info_obj;
  PyObject          *metallic_roughness_info_obj;
  PyObject          *normal_info_obj;
  PyObject          *occlusion_info_obj;
  PyObject          *emissive_info_obj;
  PyObject          *features_obj;
  PyObject          *animations_obj;
  PyObject          *extra_obj;
  Py_buffer          color_view;
  Py_buffer          emissive_color_view;
  const char        *name;
  const char        *base_color_uri;
  const char        *opacity_uri;
  const char        *metallic_roughness_uri;
  const char        *normal_uri;
  const char        *occlusion_uri;
  const char        *emissive_uri;
  const float       *color;
  const float       *emissive_color;
  const float        default_emissive[4] = {0.0f, 0.0f, 0.0f, 1.0f};
  double             metallic;
  double             roughness;
  double             alpha_cutoff;
  double             normal_scale;
  double             occlusion_strength;
  double             emissive_strength;
  int                base_color_slot;
  int                opacity_slot;
  int                metallic_roughness_slot;
  int                normal_slot;
  int                occlusion_slot;
  int                emissive_slot;
  int                material_type;
  int                opacity_inverted;
  int                alpha_mode;
  int                double_sided;
  Py_ssize_t         obj_size;

#define AKB_EXPORT_MAT_RELEASE_BUFFERS()                                      \
  do {                                                                        \
    if (emissive_color_view.buf)                                              \
      PyBuffer_Release(&emissive_color_view);                                 \
    if (color_view.buf)                                                       \
      PyBuffer_Release(&color_view);                                          \
  } while (0)

  if (!obj || obj == Py_None)
    return NULL;

  base_color_uri = NULL;
  opacity_uri = NULL;
  metallic_roughness_uri = NULL;
  normal_uri = NULL;
  occlusion_uri = NULL;
  emissive_uri = NULL;
  base_color_info_obj = Py_None;
  opacity_info_obj = Py_None;
  metallic_roughness_info_obj = Py_None;
  normal_info_obj = Py_None;
  occlusion_info_obj = Py_None;
  emissive_info_obj = Py_None;
  features_obj = Py_None;
  animations_obj = Py_None;
  extra_obj = Py_None;
  normal_scale = 1.0;
  occlusion_strength = 1.0;
  emissive_strength = 1.0;
  base_color_slot = 0;
  opacity_slot = 0;
  metallic_roughness_slot = 0;
  normal_slot = 0;
  occlusion_slot = 0;
  emissive_slot = 0;
  material_type = 0;
  opacity_inverted = 0;
  emissive_color_obj = Py_None;
  memset(&color_view, 0, sizeof(color_view));
  memset(&emissive_color_view, 0, sizeof(emissive_color_view));
  obj_size = PyTuple_Check(obj) ? PyTuple_Size(obj) : -1;
  if (obj_size == 34) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOOiiOOO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj,
                          &material_type,
                          &opacity_inverted,
                          &features_obj,
                          &animations_obj,
                          &extra_obj))
      return NULL;
  } else if (obj_size == 33) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOOiiOO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj,
                          &material_type,
                          &opacity_inverted,
                          &features_obj,
                          &animations_obj))
      return NULL;
  } else if (obj_size == 32) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOOiiO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj,
                          &material_type,
                          &opacity_inverted,
                          &features_obj))
      return NULL;
  } else if (obj_size == 31) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOOiO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj,
                          &opacity_inverted,
                          &features_obj))
      return NULL;
  } else if (obj_size == 30) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOOO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj,
                          &features_obj))
      return NULL;
  } else if (obj_size == 29) {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzidOOOOOO",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength,
                          &base_color_info_obj,
                          &opacity_info_obj,
                          &metallic_roughness_info_obj,
                          &normal_info_obj,
                          &occlusion_info_obj,
                          &emissive_info_obj))
      return NULL;
  } else {
    if (!PyArg_ParseTuple(obj,
                          "sOddidpzizizizidzidOzid",
                          &name,
                          &color_obj,
                          &metallic,
                          &roughness,
                          &alpha_mode,
                          &alpha_cutoff,
                          &double_sided,
                          &base_color_uri,
                          &base_color_slot,
                          &opacity_uri,
                          &opacity_slot,
                          &metallic_roughness_uri,
                          &metallic_roughness_slot,
                          &normal_uri,
                          &normal_slot,
                          &normal_scale,
                          &occlusion_uri,
                          &occlusion_slot,
                          &occlusion_strength,
                          &emissive_color_obj,
                          &emissive_uri,
                          &emissive_slot,
                          &emissive_strength))
      return NULL;
  }

  if (PyObject_GetBuffer(color_obj, &color_view, PyBUF_SIMPLE) < 0)
    return NULL;
  if (color_view.len < (Py_ssize_t)(4u * sizeof(float))) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    PyErr_SetString(PyExc_ValueError, "material baseColor buffer must hold four float values");
    return NULL;
  }

  emissive_color = default_emissive;
  if (emissive_color_obj && emissive_color_obj != Py_None) {
    if (PyObject_GetBuffer(emissive_color_obj, &emissive_color_view, PyBUF_SIMPLE) < 0) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (emissive_color_view.len < (Py_ssize_t)(4u * sizeof(float))) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      PyErr_SetString(PyExc_ValueError, "material emissive color buffer must hold four float values");
      return NULL;
    }
    emissive_color = (const float *)emissive_color_view.buf;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    PyErr_NoMemory();
    return NULL;
  }

  mat = (AkMaterial *)ak_heap_calloc(heap, doc, sizeof(*mat));
  if (!mat) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    PyErr_NoMemory();
    return NULL;
  }
  ak_setypeid(mat, AKT_MATERIAL);

  surface = (AkMaterialSurface *)ak_heap_calloc(heap, mat, sizeof(*surface));
  if (!surface) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    PyErr_NoMemory();
    return NULL;
  }

  color = (const float *)color_view.buf;
  surface->type             = AK_MATERIAL_TYPE_PBR_METALLIC_ROUGHNESS;
  surface->alphaCutoff      = (float)alpha_cutoff;
  surface->ior              = 1.5f;
  surface->emissiveStrength = (float)emissive_strength;
  if (material_type == AK_MATERIAL_TYPE_UNLIT) {
    surface->type = AK_MATERIAL_TYPE_UNLIT;
    surface->flags |= AK_MATERIAL_FLAG_UNLIT;
  } else if (material_type == AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS) {
    surface->type = AK_MATERIAL_TYPE_PBR_SPECULAR_GLOSSINESS;
  }
  surface->baseColor        = akb_export_material_color(heap,
                                                        surface,
                                                        AK_MATERIAL_SEMANTIC_BASE_COLOR,
                                                        AK_TEXTURE_CHANNEL_RGBA,
                                                        AK_TEXTURE_COLORSPACE_SRGB,
                                                        color);
  surface->metallic         = akb_export_material_scalar(heap,
                                                         surface,
                                                         AK_MATERIAL_SEMANTIC_METALLIC,
                                                         (float)metallic,
                                                         AK_TEXTURE_CHANNEL_B);
  surface->roughness        = akb_export_material_scalar(heap,
                                                         surface,
                                                         AK_MATERIAL_SEMANTIC_ROUGHNESS,
                                                         (float)roughness,
                                                         AK_TEXTURE_CHANNEL_G);
  if (!surface->baseColor || !surface->metallic || !surface->roughness) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    return NULL;
  }

  base_color_texture = akb_export_texref(doc,
                                         surface->baseColor,
                                         base_color_uri,
                                         AK_TEXTURE_COLORSPACE_SRGB,
                                         AK_TEXTURE_CHANNEL_RGBA,
                                         (int32_t)base_color_slot,
                                         base_color_info_obj);
  if (PyErr_Occurred()) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    return NULL;
  }
  if (base_color_texture) {
    surface->baseColor->texture = base_color_texture;
    surface->baseColor->source  = AK_MATERIAL_INPUT_TEXTURE;
  }

  if (opacity_uri && opacity_uri[0]) {
    AkTextureRef *opacity_texture;

    surface->opacity = akb_export_material_scalar(heap,
                                                  surface,
                                                  AK_MATERIAL_SEMANTIC_OPACITY,
                                                  1.0f,
                                                  AK_TEXTURE_CHANNEL_A);
    if (!surface->opacity) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }

    opacity_texture = akb_export_texref(doc,
                                        surface->opacity,
                                        opacity_uri,
                                        AK_TEXTURE_COLORSPACE_SRGB,
                                        AK_TEXTURE_CHANNEL_A,
                                        (int32_t)opacity_slot,
                                        opacity_info_obj);
    if (PyErr_Occurred()) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (opacity_texture) {
      surface->opacity->texture = opacity_texture;
      surface->opacity->source  = AK_MATERIAL_INPUT_TEXTURE;
      if (opacity_inverted)
        surface->opacity->flags |= AK_MATERIAL_INPUT_FLAG_INVERTED;
    }
  }

  if (metallic_roughness_uri && metallic_roughness_uri[0]) {
    AkTextureRef *mr_texture;

    mr_texture = akb_export_texref(doc,
                                   surface,
                                   metallic_roughness_uri,
                                   AK_TEXTURE_COLORSPACE_LINEAR,
                                   AK_TEXTURE_CHANNEL_GB,
                                   (int32_t)metallic_roughness_slot,
                                   metallic_roughness_info_obj);
    if (PyErr_Occurred()) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (mr_texture) {
      surface->metallic->texture  = mr_texture;
      surface->metallic->source   = AK_MATERIAL_INPUT_TEXTURE;
      surface->metallic->channels = AK_TEXTURE_CHANNEL_B;
      surface->roughness->texture = mr_texture;
      surface->roughness->source  = AK_MATERIAL_INPUT_TEXTURE;
      surface->roughness->channels = AK_TEXTURE_CHANNEL_G;
    }
  }

  if (normal_uri && normal_uri[0]) {
    AkTextureRef *normal_texture;

    surface->normal = akb_export_material_scalar(heap,
                                                 surface,
                                                 AK_MATERIAL_SEMANTIC_NORMAL,
                                                 (float)normal_scale,
                                                 AK_TEXTURE_CHANNEL_RGB);
    if (!surface->normal) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }

    normal_texture = akb_export_texref(doc,
                                       surface->normal,
                                       normal_uri,
                                       AK_TEXTURE_COLORSPACE_LINEAR,
                                       AK_TEXTURE_CHANNEL_RGB,
                                       (int32_t)normal_slot,
                                       normal_info_obj);
    if (PyErr_Occurred()) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (normal_texture) {
      surface->normal->texture = normal_texture;
      surface->normal->source  = AK_MATERIAL_INPUT_TEXTURE;
    }
  }

  if (occlusion_uri && occlusion_uri[0]) {
    AkTextureRef *occlusion_texture;

    surface->occlusion = akb_export_material_scalar(heap,
                                                    surface,
                                                    AK_MATERIAL_SEMANTIC_OCCLUSION,
                                                    (float)occlusion_strength,
                                                    AK_TEXTURE_CHANNEL_R);
    if (!surface->occlusion) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }

    occlusion_texture = akb_export_texref(doc,
                                          surface->occlusion,
                                          occlusion_uri,
                                          AK_TEXTURE_COLORSPACE_LINEAR,
                                          AK_TEXTURE_CHANNEL_R,
                                          (int32_t)occlusion_slot,
                                          occlusion_info_obj);
    if (PyErr_Occurred()) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (occlusion_texture) {
      surface->occlusion->texture = occlusion_texture;
      surface->occlusion->source  = AK_MATERIAL_INPUT_TEXTURE;
    }
  }

  if ((emissive_uri && emissive_uri[0])
      || emissive_color[0] != 0.0f
      || emissive_color[1] != 0.0f
      || emissive_color[2] != 0.0f) {
    AkTextureRef *emissive_texture;

    surface->emissive = akb_export_material_color(heap,
                                                  surface,
                                                  AK_MATERIAL_SEMANTIC_EMISSIVE,
                                                  AK_TEXTURE_CHANNEL_RGB,
                                                  AK_TEXTURE_COLORSPACE_SRGB,
                                                  emissive_color);
    if (!surface->emissive) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }

    emissive_texture = akb_export_texref(doc,
                                         surface->emissive,
                                         emissive_uri,
                                         AK_TEXTURE_COLORSPACE_SRGB,
                                         AK_TEXTURE_CHANNEL_RGB,
                                         (int32_t)emissive_slot,
                                         emissive_info_obj);
    if (PyErr_Occurred()) {
      AKB_EXPORT_MAT_RELEASE_BUFFERS();
      return NULL;
    }
    if (emissive_texture) {
      surface->emissive->texture = emissive_texture;
      surface->emissive->source  = AK_MATERIAL_INPUT_TEXTURE;
    }
  }

  if (double_sided)
    surface->flags |= AK_MATERIAL_FLAG_DOUBLE_SIDED;
  if (alpha_mode == 1)
    surface->flags |= AK_MATERIAL_FLAG_ALPHA_BLEND;
  else if (alpha_mode == 2)
    surface->flags |= AK_MATERIAL_FLAG_ALPHA_MASK;

  if (!akb_export_material_features(doc, surface, features_obj)) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    return NULL;
  }

  mat->name    = name && name[0] ? name : NULL;
  mat->surface = surface;
  if (!akb_export_apply_object_extra(doc, mat, extra_obj)) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    return NULL;
  }
  AKB_LIB_APPEND(doc->lib.materials, mat, next);

  if (!akb_export_add_material_animations(doc, mat, animations_obj)) {
    AKB_EXPORT_MAT_RELEASE_BUFFERS();
    return NULL;
  }

  AKB_EXPORT_MAT_RELEASE_BUFFERS();
#undef AKB_EXPORT_MAT_RELEASE_BUFFERS
  return mat;
}

static int
akb_export_ensure_material_variant(AkDoc *doc, uint32_t variant_index, const char *name) {
  AkHeap             *heap;
  AkMaterialVariant **link;
  AkMaterialVariant  *variant;
  uint32_t            index;

  if (!doc)
    return 0;
  if (variant_index > 65535u) {
    PyErr_SetString(PyExc_ValueError, "material variant index is too large");
    return 0;
  }

  heap = ak_heap_getheap(doc);
  if (!heap) {
    PyErr_NoMemory();
    return 0;
  }

  link = &doc->materialVariants;
  for (index = 0; index <= variant_index; index++) {
    if (!*link) {
      variant = (AkMaterialVariant *)ak_heap_calloc(heap, doc, sizeof(*variant));
      if (!variant) {
        PyErr_NoMemory();
        return 0;
      }
      *link = variant;
    }

    variant = *link;
    if (index == variant_index && name && name[0] && !variant->name)
      variant->name = name;
    link = &variant->next;
  }

  return 1;
}

static int
akb_export_apply_material_variants(AkDoc           *doc,
                                   AkMeshPrimitive *prim,
                                   PyObject        *variants_obj,
                                   int              material_index,
                                   PyObject        *materials_seq) {
  AkHeap                    *heap;
  AkMaterialVariantMapping **tail;
  PyObject                  *variants_seq;
  Py_ssize_t                 count;

  if (!doc || !prim || !variants_obj || variants_obj == Py_None)
    return 1;
  if (material_index != 0)
    return 1;

  variants_seq = PySequence_Fast(variants_obj, "material variants must be a sequence");
  if (!variants_seq)
    return 0;

  heap = ak_heap_getheap(doc);
  if (!heap) {
    Py_DECREF(variants_seq);
    PyErr_NoMemory();
    return 0;
  }

  tail = &prim->variantMappings;
  while (*tail)
    tail = &(*tail)->next;

  count = PySequence_Fast_GET_SIZE(variants_seq);
  for (Py_ssize_t i = 0; i < count; i++) {
    PyObject *item;
    const char *variant_name;
    unsigned int variant_index;
    unsigned int slot;
    AkMaterial *material;
    AkMaterialVariantMapping *mapping;

    item = PySequence_Fast_GET_ITEM(variants_seq, i);
    if (!PyTuple_Check(item)
        || !PyArg_ParseTuple(item, "IsI", &variant_index, &variant_name, &slot)) {
      Py_DECREF(variants_seq);
      return 0;
    }
    if ((Py_ssize_t)slot >= PySequence_Fast_GET_SIZE(materials_seq))
      continue;
    if (!akb_export_ensure_material_variant(doc, variant_index, variant_name)) {
      Py_DECREF(variants_seq);
      return 0;
    }

    material = akb_export_material(doc, PySequence_Fast_GET_ITEM(materials_seq, (Py_ssize_t)slot));
    if (PyErr_Occurred()) {
      Py_DECREF(variants_seq);
      return 0;
    }
    if (!material)
      continue;

    mapping = (AkMaterialVariantMapping *)ak_heap_calloc(heap, prim, sizeof(*mapping));
    if (!mapping) {
      Py_DECREF(variants_seq);
      PyErr_NoMemory();
      return 0;
    }
    mapping->material = material;
    mapping->variantIndex = variant_index;
    *tail = mapping;
    tail = &mapping->next;
    prim->variantMappingCount++;
  }

  Py_DECREF(variants_seq);
  return 1;
}

