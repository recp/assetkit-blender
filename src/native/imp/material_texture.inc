static size_t
akb_doc_image_index(AkDoc *doc, AkImage *image) {
  AkImage *item;
  size_t index;

  if (!doc || !image)
    return 0;

  index = 0;
  for (item = doc->lib.images.first; item; item = item->next, index++)
    if (item == image)
      return index;

  return 0;
}

static uint64_t
akb_embedded_image_cache_hash(AkDoc *doc, AkImage *image, size_t length) {
  const char *path;
  uint64_t hash;
  size_t image_index;
#if defined(_WIN32)
  struct _stat st;
#else
  struct stat st;
#endif

  path = (doc && doc->inf && doc->inf->name) ? doc->inf->name : "";
  hash = akb_fnv1a64((const unsigned char *)path, strlen(path));
  image_index = akb_doc_image_index(doc, image);
  hash = akb_fnv1a64_mix_u64(hash, (uint64_t)image_index);
  hash = akb_fnv1a64_mix_u64(hash, (uint64_t)length);

  if (path[0]
#if defined(_WIN32)
      && _stat(path, &st) == 0
#else
      && stat(path, &st) == 0
#endif
  ) {
    hash = akb_fnv1a64_mix_u64(hash, (uint64_t)st.st_size);
    hash = akb_fnv1a64_mix_u64(hash, (uint64_t)st.st_mtime);
  }

  return hash;
}

static const char *
akb_embedded_image_extension(const unsigned char *data, size_t length, const char *mime) {
  if (mime) {
    if (strstr(mime, "png"))
      return "png";
    if (strstr(mime, "jpeg") || strstr(mime, "jpg"))
      return "jpg";
    if (strstr(mime, "webp"))
      return "webp";
    if (strstr(mime, "ktx2"))
      return "ktx2";
  }

  if (data && length >= 8
      && data[0] == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G')
    return "png";
  if (data && length >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF)
    return "jpg";
  if (data && length >= 12
      && memcmp(data, "RIFF", 4) == 0
      && memcmp(data + 8, "WEBP", 4) == 0)
    return "webp";
  if (data && length >= 12
      && data[0] == 0xAB && data[1] == 'K' && data[2] == 'T' && data[3] == 'X'
      && data[4] == ' ' && data[5] == '2')
    return "ktx2";

  return "bin";
}

static int
akb_file_has_size(const char *path, size_t length) {
#if defined(_WIN32)
  struct _stat st;
  if (_stat(path, &st) != 0)
    return 0;
#else
  struct stat st;
  if (stat(path, &st) != 0)
    return 0;
#endif

  return (size_t)st.st_size == length;
}

static int
akb_write_file_once(const char *path, const unsigned char *data, size_t length) {
  FILE *file;
  size_t written;

  if (akb_file_has_size(path, length))
    return 1;

  file = fopen(path, "wb");
  if (!file)
    return 0;

  written = fwrite(data, 1, length, file);
  if (fclose(file) != 0 || written != length) {
    remove(path);
    return 0;
  }

  return 1;
}

static int
akb_copy_embedded_texture_path(AkDoc *doc, AkImage *image, char *dest, size_t capacity) {
  AkImageSource *source;
  AkBuffer *buff;
  const unsigned char *data;
  const char *tmpdir;
  const char *ext;
  char dir[PATH_MAX];
  char filename[128];
  uint64_t hash;
  size_t length;
  int borrowed_slice;

  if (!image || !dest || capacity == 0)
    return 0;

  source = image->source;
  if (source && source->resolvedPath) {
    snprintf(dest, capacity, "%s", source->resolvedPath);
    return dest[0] != '\0';
  }

  buff = source ? source->buffer : NULL;
  data = buff ? (const unsigned char *)buff->data : NULL;
  length = buff ? buff->length : 0;
  if (!data || length == 0)
    return 0;
  borrowed_slice = buff->name
                   && strcmp(buff->name, "assetkit:gltf-buffer-view-slice") == 0;

  tmpdir = getenv("TMPDIR");
  if (!tmpdir || !tmpdir[0])
    tmpdir = "/tmp";

  akb_path_join(dir, sizeof(dir), tmpdir, "assetkit_blender");
  if (!akb_mkdir_if_needed(dir))
    return 0;

  hash = borrowed_slice
           ? akb_embedded_image_cache_hash(doc, image, length)
           : akb_fnv1a64(data, length);
  ext = akb_embedded_image_extension(data, length, source->mimeType);
  snprintf(filename,
           sizeof(filename),
           "texture_%016llx.%s",
           (unsigned long long)hash,
           ext);
  akb_path_join(dest, capacity, dir, filename);

  if (!akb_write_file_once(dest, data, length)) {
    dest[0] = '\0';
    return 0;
  }

  if (!source->resolvedPath)
    source->resolvedPath = ak_strdup(source, dest);

  return 1;
}

static void
akb_copy_image_path(AkDoc *doc, AkImage *image, char *dest, size_t capacity) {
  AkImageSource *source;
  const char *path;
  char resolved[PATH_MAX];

  if (!dest || capacity == 0)
    return;
  dest[0] = '\0';

  if (!image)
    return;

  source = image->source;
  if (!source)
    return;

  path = source->resolvedPath ? source->resolvedPath : source->uri;
  if (!path || !path[0]) {
    akb_copy_embedded_texture_path(doc, image, dest, capacity);
    return;
  }

  if (path[0] == '/' || !doc || !doc->inf || !doc->inf->dir) {
    snprintf(dest, capacity, "%s", path);
  } else {
    snprintf(dest, capacity, "%s", ak_fullpath(doc, path, resolved));
  }

}

static void
akb_copy_texture_path(AkDoc *doc, AkTextureRef *texref, char *dest, size_t capacity) {
  AkImage *image;

  if (!dest || capacity == 0)
    return;
  dest[0] = '\0';

  if (!texref || !texref->texture || !(image = texref->texture->image))
    return;

  akb_copy_image_path(doc, image, dest, capacity);
}

static int
akb_strdup_to(char **dest, const char *src) {
  char *copy;
  size_t len;

  if (!dest)
    return 0;

  free(*dest);
  *dest = NULL;

  if (!src || !src[0])
    return 1;

  len = strlen(src);
  copy = (char *)malloc(len + 1u);
  if (!copy)
    return 0;
  memcpy(copy, src, len + 1u);
  *dest = copy;
  return 1;
}

static int
akb_cstr_has(const char *value) {
  return value && value[0];
}

static int
akb_copy_texture_path_alloc(AkDoc *doc, AkTextureRef *texref, char **dest) {
  char path[1024];

  akb_copy_texture_path(doc, texref, path, sizeof(path));
  return akb_strdup_to(dest, path);
}

static int
akb_primitive_clone_texture_paths(AkbPrimitive *dst, const AkbPrimitive *src) {
#define AKB_CLONE_TEX_PATH(FIELD)                                            \
  do {                                                                       \
    if (!akb_strdup_to(&dst->FIELD, src->FIELD))                             \
      return 0;                                                              \
  } while (0)

  AKB_CLONE_TEX_PATH(base_color_texture);
  AKB_CLONE_TEX_PATH(metallic_roughness_texture);
  AKB_CLONE_TEX_PATH(occlusion_texture);
  AKB_CLONE_TEX_PATH(normal_texture);
  AKB_CLONE_TEX_PATH(emissive_texture);
  AKB_CLONE_TEX_PATH(transparent_texture);
  AKB_CLONE_TEX_PATH(specular_texture);
  AKB_CLONE_TEX_PATH(specular_color_texture);
  AKB_CLONE_TEX_PATH(clearcoat_texture);
  AKB_CLONE_TEX_PATH(clearcoat_roughness_texture);
  AKB_CLONE_TEX_PATH(clearcoat_normal_texture);
  AKB_CLONE_TEX_PATH(transmission_texture);
  AKB_CLONE_TEX_PATH(sheen_color_texture);
  AKB_CLONE_TEX_PATH(sheen_roughness_texture);
  AKB_CLONE_TEX_PATH(iridescence_texture);
  AKB_CLONE_TEX_PATH(iridescence_thickness_texture);
  AKB_CLONE_TEX_PATH(volume_thickness_texture);
  AKB_CLONE_TEX_PATH(anisotropy_texture);
  AKB_CLONE_TEX_PATH(diffuse_transmission_texture);
  AKB_CLONE_TEX_PATH(diffuse_transmission_color_texture);

#undef AKB_CLONE_TEX_PATH
  return 1;
}

static AkbTextureInfo *
akb_texture_info_for_role(AkbPrimitive *out, const char *role) {
  AkbTextureInfo *new_infos;
  uint32_t new_capacity;
  uint32_t i;

  if (!out || !role || !role[0])
    return NULL;

  for (i = 0; i < out->texture_info_count; i++) {
    if (strcmp(out->texture_infos[i].role, role) == 0)
      return &out->texture_infos[i];
  }

  if (out->texture_info_count >= AKB_TEXTURE_INFO_MAX)
    return NULL;

  if (out->texture_info_count == out->texture_info_capacity) {
    new_capacity = out->texture_info_capacity ? out->texture_info_capacity * 2u : 2u;
    if (new_capacity > AKB_TEXTURE_INFO_MAX)
      new_capacity = AKB_TEXTURE_INFO_MAX;
    if (new_capacity <= out->texture_info_capacity)
      return NULL;

    new_infos = (AkbTextureInfo *)realloc(out->texture_infos,
                                          (size_t)new_capacity * sizeof(*new_infos));
    if (!new_infos)
      return NULL;
    out->texture_infos = new_infos;
    out->texture_info_capacity = new_capacity;
  }

  i = out->texture_info_count++;
  memset(&out->texture_infos[i], 0, sizeof(out->texture_infos[i]));
  snprintf(out->texture_infos[i].role, sizeof(out->texture_infos[i].role), "%s", role);
  return &out->texture_infos[i];
}

static const char *
akb_texture_role_color_space(const char *role) {
  if (!role)
    return "Non-Color";

  if (strcmp(role, "base_color") == 0
      || strcmp(role, "emissive") == 0
      || strcmp(role, "specular_color") == 0
      || strcmp(role, "sheen_color") == 0
      || strcmp(role, "diffuse_transmission_color") == 0)
    return "sRGB";

  return "Non-Color";
}

static const char *
akb_texture_role_channels(const char *role) {
  if (!role)
    return "";

  if (strcmp(role, "occlusion") == 0
      || strcmp(role, "clearcoat") == 0
      || strcmp(role, "transmission") == 0
      || strcmp(role, "iridescence") == 0)
    return "R";
  if (strcmp(role, "metallic_roughness") == 0)
    return "GB";
  if (strcmp(role, "clearcoat_roughness") == 0
      || strcmp(role, "iridescence_thickness") == 0
      || strcmp(role, "volume_thickness") == 0)
    return "G";
  if (strcmp(role, "specular") == 0
      || strcmp(role, "diffuse_transmission") == 0)
    return "A";
  if (strcmp(role, "base_color") == 0
      || strcmp(role, "emissive") == 0
      || strcmp(role, "normal") == 0
      || strcmp(role, "clearcoat_normal") == 0
      || strcmp(role, "specular_color") == 0
      || strcmp(role, "sheen_color") == 0
      || strcmp(role, "diffuse_transmission_color") == 0)
    return "RGB";
  if (strcmp(role, "anisotropy") == 0)
    return "RGB";

  return "";
}

static void
akb_material_input_color_space(AkMaterialInput *input,
                               const char *role,
                               char *dest,
                               size_t capacity) {
  AkTextureColorSpace color_space;
  const char *name;

  if (!dest || capacity == 0)
    return;

  color_space = input ? input->colorSpace : AK_TEXTURE_COLORSPACE_UNSPECIFIED;
  if (color_space == AK_TEXTURE_COLORSPACE_SRGB)
    name = "sRGB";
  else if (color_space == AK_TEXTURE_COLORSPACE_LINEAR)
    name = "Non-Color";
  else
    name = akb_texture_role_color_space(role);

  snprintf(dest, capacity, "%s", name);
}

static void
akb_material_input_channels(AkMaterialInput *input,
                            const char *role,
                            char *dest,
                            size_t capacity) {
  AkTextureChannels channels;
  size_t i;

  if (!dest || capacity == 0)
    return;

  channels = input ? input->channels : AK_TEXTURE_CHANNEL_NONE;
  if (channels == AK_TEXTURE_CHANNEL_NONE) {
    snprintf(dest, capacity, "%s", akb_texture_role_channels(role));
    return;
  }

  i = 0;
#define AKB_APPEND_INPUT_CHANNEL(CHANNEL, LETTER) do { \
    if ((channels & (CHANNEL)) && i + 1 < capacity) {  \
      dest[i++] = (LETTER);                            \
    }                                                  \
  } while (0)

  AKB_APPEND_INPUT_CHANNEL(AK_TEXTURE_CHANNEL_R, 'R');
  AKB_APPEND_INPUT_CHANNEL(AK_TEXTURE_CHANNEL_G, 'G');
  AKB_APPEND_INPUT_CHANNEL(AK_TEXTURE_CHANNEL_B, 'B');
  AKB_APPEND_INPUT_CHANNEL(AK_TEXTURE_CHANNEL_A, 'A');

#undef AKB_APPEND_INPUT_CHANNEL

  dest[i] = '\0';
}

static int
akb_sampler_is_default(AkSampler *sampler) {
  if (!sampler)
    return 1;
  if (sampler->extra)
    return 0;
  return sampler->wrapS == AK_WRAP_MODE_WRAP
         && sampler->wrapT == AK_WRAP_MODE_WRAP
         && sampler->wrapP == AK_WRAP_MODE_WRAP
         && sampler->minfilter == AK_MINFILTER_LINEAR
         && sampler->magfilter == AK_MAGFILTER_LINEAR
         && sampler->mipfilter == AK_MIPFILTER_LINEAR
         && sampler->maxAnisotropy == 0
         && sampler->mipMaxLevel == 0
         && sampler->mipMinLevel == 0
         && sampler->mipBias == 0.0f;
}

static float
akb_material_input_scalar(AkMaterialInput *input, float fallback) {
  if (!input)
    return fallback;
  if (input->valueType == AK_MATERIAL_VALUE_COLOR)
    return input->color.vec[0];
  return input->value[0];
}

static void
akb_material_input_color4(AkMaterialInput *input,
                          float fallback_r,
                          float fallback_g,
                          float fallback_b,
                          float fallback_a,
                          float out[4]) {
  out[0] = fallback_r;
  out[1] = fallback_g;
  out[2] = fallback_b;
  out[3] = fallback_a;
  if (!input)
    return;

  if (input->valueType == AK_MATERIAL_VALUE_FLOAT4
      || input->valueType == AK_MATERIAL_VALUE_FLOAT3) {
    out[0] = input->value[0];
    out[1] = input->value[1];
    out[2] = input->value[2];
    if (input->valueType == AK_MATERIAL_VALUE_FLOAT4)
      out[3] = input->value[3];
    return;
  }

  out[0] = input->color.vec[0];
  out[1] = input->color.vec[1];
  out[2] = input->color.vec[2];
  out[3] = input->color.vec[3];
  if (input->source == AK_MATERIAL_INPUT_TEXTURE
      && input->valueType == AK_MATERIAL_VALUE_COLOR
      && out[0] == 0.0f
      && out[1] == 0.0f
      && out[2] == 0.0f
      && out[3] == 1.0f
      && (fallback_r != 0.0f || fallback_g != 0.0f || fallback_b != 0.0f)) {
    out[0] = fallback_r;
    out[1] = fallback_g;
    out[2] = fallback_b;
    out[3] = fallback_a;
  }
}

static void
akb_material_input_color3(AkMaterialInput *input,
                          float fallback_r,
                          float fallback_g,
                          float fallback_b,
                          float out[3]) {
  float color[4];

  akb_material_input_color4(input,
                            fallback_r,
                            fallback_g,
                            fallback_b,
                            1.0f,
                            color);
  out[0] = color[0];
  out[1] = color[1];
  out[2] = color[2];
}

static int
akb_material_input_is_fast_base_color(AkMeshPrimitive *prim,
                                      AkInstanceGeometry *instance,
                                      AkMaterialInput *input) {
  AkTextureRef *texref;
  AkTexture *texture;
  AkImage *image;

  if (!input || !(texref = input->texture))
    return 1;
  if (!texref->texture
      || texref->transform
      || ak_materialTextureSlot(prim, instance, texref) > 0)
    return 0;
  if (input->colorSpace == AK_TEXTURE_COLORSPACE_LINEAR)
    return 0;
  if (input->channels != AK_TEXTURE_CHANNEL_NONE
      && input->channels != AK_TEXTURE_CHANNEL_RGB
      && input->channels != AK_TEXTURE_CHANNEL_RGBA)
    return 0;

  texture = texref->texture;
  image = texture->image;
  if (!image)
    return 0;
  if (ak_extra(texref)
      || ak_extra(texture)
      || ak_extra(image)
      || !akb_sampler_is_default(texture->sampler))
    return 0;

  return 1;
}

static int
akb_extract_material_fast_surface(AkDoc *doc,
                                  AkInstanceGeometry *instance,
                                  AkMeshPrimitive *prim,
                                  AkMaterialSurface *surface,
                                  AkbPrimitive *out) {
  if (!surface || !out)
    return 0;
  if (out->material_extra)
    return 0;
  if (surface->type != AK_MATERIAL_TYPE_PBR
      && surface->type != AK_MATERIAL_TYPE_PBR_METALLIC_ROUGHNESS)
    return 0;
  if (surface->features
      || surface->extras
      || surface->normal
      || surface->occlusion
      || surface->emissive
      || surface->opacity)
    return 0;
  if ((surface->flags & ~(uint32_t)AK_MATERIAL_FLAG_DOUBLE_SIDED) != 0)
    return 0;
  if (surface->metallic && surface->metallic->texture)
    return 0;
  if (surface->roughness && surface->roughness->texture)
    return 0;
  if (!akb_material_input_is_fast_base_color(prim, instance, surface->baseColor))
    return 0;

  out->material_type = (uint32_t)surface->type;
  out->double_sided = (surface->flags & AK_MATERIAL_FLAG_DOUBLE_SIDED) ? 1 : 0;
  akb_material_input_color4(surface->baseColor, 1.0f, 1.0f, 1.0f, 1.0f, out->base_color);
  if (!akb_copy_texture_path_alloc(doc,
                                   surface->baseColor ? surface->baseColor->texture : NULL,
                                   &out->base_color_texture))
    return 0;
  out->metallic = akb_material_input_scalar(surface->metallic, 1.0f);
  out->roughness = akb_material_input_scalar(surface->roughness, 1.0f);
  out->alpha_mode = 0;
  out->opacity = 1.0f;
  out->base_color[3] = 1.0f;
  return 1;
}

static void
akb_copy_texture_info(AkDoc *doc,
                      AkInstanceGeometry *instance,
                      AkMeshPrimitive *prim,
                      AkMaterialInput *input,
                      const char *role,
                      char **dest,
                      AkbPrimitive *out) {
  AkbTextureInfo *info;
  AkTextureRef *texref;
  AkImage *image;
  AkSampler *sampler;
  AkTextureTransform *transform;

  texref = input ? input->texture : NULL;
  if (!akb_copy_texture_path_alloc(doc, texref, dest))
    return;
  if (!dest || !*dest || !(*dest)[0])
    return;

  info = akb_texture_info_for_role(out, role);
  if (!info)
    return;

  memset(info->path, 0, sizeof(info->path));
  snprintf(info->path, sizeof(info->path), "%s", *dest);
  akb_material_input_color_space(input,
                                 role,
                                 info->color_space,
                                 sizeof(info->color_space));
  akb_material_input_channels(input,
                              role,
                              info->channels,
                              sizeof(info->channels));
  info->slot = ak_materialTextureSlot(prim, instance, texref);

  if (texref->texcoord)
    snprintf(info->texcoord, sizeof(info->texcoord), "%s", texref->texcoord);
  if (texref->coordInputName)
    snprintf(info->coord_input_name, sizeof(info->coord_input_name), "%s", texref->coordInputName);

  image = texref->texture ? texref->texture->image : NULL;
  sampler = texref->texture ? texref->texture->sampler : NULL;
  info->texture_extra = texref->texture ? ak_extra(texref->texture) : NULL;
  info->texref_extra = ak_extra(texref);
  info->image_extra = image ? ak_extra(image) : NULL;
  info->sampler_extra = sampler ? ak_extra(sampler) : NULL;
  if (image && image->name)
    snprintf(info->image_name, sizeof(info->image_name), "%s", image->name);
  if (sampler && sampler->name)
    snprintf(info->sampler_name, sizeof(info->sampler_name), "%s", sampler->name);
  info->wrap_s = sampler ? sampler->wrapS : AK_WRAP_MODE_WRAP;
  info->wrap_t = sampler ? sampler->wrapT : AK_WRAP_MODE_WRAP;
  info->wrap_p = sampler ? sampler->wrapP : AK_WRAP_MODE_WRAP;
  info->min_filter = sampler ? sampler->minfilter : AK_MINFILTER_LINEAR;
  info->mag_filter = sampler ? sampler->magfilter : AK_MAGFILTER_LINEAR;
  info->mip_filter = sampler ? sampler->mipfilter : AK_MIPFILTER_LINEAR;

  transform = texref->transform;
  info->transform_offset[0] = 0.0f;
  info->transform_offset[1] = 0.0f;
  info->transform_scale[0] = 1.0f;
  info->transform_scale[1] = 1.0f;
  info->transform_rotation = 0.0f;
  info->transform_slot = -1;
  info->has_transform = 0;
  if (transform) {
    info->transform_offset[0] = transform->offset[0];
    info->transform_offset[1] = transform->offset[1];
    info->transform_scale[0] = transform->scale[0];
    info->transform_scale[1] = transform->scale[1];
    info->transform_rotation = transform->rotation;
    info->transform_slot = transform->slot;
    info->has_transform = 1;
  }
}

static float
akb_clampf(float value, float min_value, float max_value) {
  if (value < min_value)
    return min_value;
  if (value > max_value)
    return max_value;
  return value;
}

static AkInstanceGeometry *
akb_node_geometry_instance(AkNode *node) {
  return node ? node->geometry : NULL;
}

static int
akb_instance_affects_material(AkMeshPrimitive *prim, AkInstanceGeometry *instance) {
  AkResolvedMaterial with_instance;
  AkResolvedMaterial without_instance;

  if (!prim || !instance)
    return 0;

  memset(&with_instance, 0, sizeof(with_instance));
  memset(&without_instance, 0, sizeof(without_instance));

  if (!ak_materialResolve(prim, instance, UINT32_MAX, &with_instance))
    return 0;
  if (!ak_materialResolve(prim, NULL, UINT32_MAX, &without_instance))
    return with_instance.material || with_instance.surface || with_instance.binding;

  return with_instance.material != without_instance.material
         || with_instance.surface != without_instance.surface
         || with_instance.binding != without_instance.binding
         || with_instance.propertyIndex != without_instance.propertyIndex
         || with_instance.variantIndex != without_instance.variantIndex;
}

static void
akb_extract_material(AkDoc *doc,
                     AkInstanceGeometry *instance,
                     AkMeshPrimitive *prim,
                     AkbPrimitive *out) {
  AkResolvedMaterial resolved;
  AkMaterial *mat;
  AkMaterialSurface *surface;
  AkMaterialSpecularGlossinessFeature *sg;
  AkMaterialSpecularFeature *specular;
  AkMaterialClassicFeature *classic;
  AkMaterialClearcoatFeature *clearcoat;
  AkMaterialTransmissionFeature *transmission;
  AkMaterialSheenFeature *sheen;
  AkMaterialIridescenceFeature *iridescence;
  AkMaterialVolumeFeature *volume;
  AkMaterialSubsurfaceFeature *subsurface;
  AkMaterialAnisotropyFeature *anisotropy;
  AkMaterialDispersionFeature *dispersion;
  AkMaterialDiffuseTransmissionFeature *diffuse_transmission;
  float opacity;

  out->base_color[0] = 1.0f;
  out->base_color[1] = 1.0f;
  out->base_color[2] = 1.0f;
  out->base_color[3] = 1.0f;
  out->transparent_color[0] = 1.0f;
  out->transparent_color[1] = 1.0f;
  out->transparent_color[2] = 1.0f;
  out->transparent_color[3] = 1.0f;
  out->emissive_color[0] = 0.0f;
  out->emissive_color[1] = 0.0f;
  out->emissive_color[2] = 0.0f;
  out->specular_color[0] = 1.0f;
  out->specular_color[1] = 1.0f;
  out->specular_color[2] = 1.0f;
  out->sheen_color[0] = 0.0f;
  out->sheen_color[1] = 0.0f;
  out->sheen_color[2] = 0.0f;
  out->volume_attenuation_color[0] = 1.0f;
  out->volume_attenuation_color[1] = 1.0f;
  out->volume_attenuation_color[2] = 1.0f;
  out->volume_scatter_color[0] = 0.0f;
  out->volume_scatter_color[1] = 0.0f;
  out->volume_scatter_color[2] = 0.0f;
  out->diffuse_transmission_color[0] = 1.0f;
  out->diffuse_transmission_color[1] = 1.0f;
  out->diffuse_transmission_color[2] = 1.0f;
  out->metallic = 1.0f;
  out->roughness = 1.0f;
  out->alpha_cutoff = 0.5f;
  out->transparent_amount = 1.0f;
  out->opacity = 1.0f;
  out->normal_scale = 1.0f;
  out->occlusion_strength = 1.0f;
  out->emissive_strength = 1.0f;
  out->specular_strength = 1.0f;
  out->ior = 1.5f;
  out->clearcoat_normal_scale = 1.0f;
  out->iridescence_ior = 1.3f;
  out->iridescence_thickness_minimum = 100.0f;
  out->iridescence_thickness_maximum = 400.0f;
  out->volume_attenuation_distance = INFINITY;

  memset(&resolved, 0, sizeof(resolved));
  if (!prim || !ak_materialResolve(prim, instance, UINT32_MAX, &resolved))
    return;
  mat = resolved.material;
  surface = resolved.surface;
  if (!surface)
    return;

  if (mat)
    out->material_key = (uintptr_t)mat;
  else
    out->material_key = (uintptr_t)surface;

  if (mat && mat->name)
    out->material_name = akb_name(mat->name, "AssetKitMaterial");

  if (mat)
    out->material_extra = ak_extra(mat);
  if (akb_extract_material_fast_surface(doc, instance, prim, surface, out))
    return;

  out->material_type = (uint32_t)surface->type;

#define AKB_COPY_TEX(ROLE, TEXREF, DEST) \
  akb_copy_texture_info(doc, instance, prim, (TEXREF), (ROLE), &(DEST), out)

  out->double_sided = (surface->flags & AK_MATERIAL_FLAG_DOUBLE_SIDED) ? 1 : 0;
  out->alpha_cutoff = surface->alphaCutoff;
  out->ior = surface->ior > 0.0f ? surface->ior : out->ior;
  out->emissive_strength = surface->emissiveStrength;

  if (surface->baseColor) {
    akb_material_input_color4(surface->baseColor, 1.0f, 1.0f, 1.0f, 1.0f, out->base_color);
    AKB_COPY_TEX("base_color", surface->baseColor, out->base_color_texture);
  }

  if (surface->metallic)
    out->metallic = akb_material_input_scalar(surface->metallic, out->metallic);
  if (surface->roughness)
    out->roughness = akb_material_input_scalar(surface->roughness, out->roughness);
  AKB_COPY_TEX("metallic_roughness", surface->metallic, out->metallic_roughness_texture);
  if (!akb_cstr_has(out->metallic_roughness_texture))
    AKB_COPY_TEX("metallic_roughness", surface->roughness, out->metallic_roughness_texture);

  if (surface->normal) {
    out->normal_scale = akb_material_input_scalar(surface->normal, 1.0f);
    AKB_COPY_TEX("normal", surface->normal, out->normal_texture);
  }

  if (surface->occlusion) {
    out->occlusion_strength = akb_material_input_scalar(surface->occlusion, 1.0f);
    AKB_COPY_TEX("occlusion", surface->occlusion, out->occlusion_texture);
  }

  if (surface->emissive) {
    akb_material_input_color3(surface->emissive, 0.0f, 0.0f, 0.0f, out->emissive_color);
    AKB_COPY_TEX("emissive", surface->emissive, out->emissive_texture);
  }

  sg = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR_GLOSSINESS);
  if (sg) {
    out->material_type = AKB_MATERIAL_SPECULAR_GLOSSINESS;
    if (sg->diffuse) {
      akb_material_input_color4(sg->diffuse, 1.0f, 1.0f, 1.0f, 1.0f, out->base_color);
      AKB_COPY_TEX("base_color", sg->diffuse, out->base_color_texture);
    }
    if (sg->specular) {
      akb_material_input_color3(sg->specular, 1.0f, 1.0f, 1.0f, out->specular_color);
      AKB_COPY_TEX("specular_color", sg->specular, out->specular_color_texture);
    }
    if (sg->glossiness) {
      out->specular_strength = akb_material_input_scalar(sg->glossiness, out->specular_strength);
      AKB_COPY_TEX("specular", sg->glossiness, out->specular_texture);
    }
    out->metallic = 0.0f;
    out->roughness = 1.0f - akb_clampf(out->specular_strength, 0.0f, 1.0f);
  }

  specular = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR);
  if (specular) {
    if (specular->factor) {
      out->specular_strength = akb_material_input_scalar(specular->factor, out->specular_strength);
      AKB_COPY_TEX("specular", specular->factor, out->specular_texture);
    }
    if (specular->color) {
      akb_material_input_color3(specular->color, 1.0f, 1.0f, 1.0f, out->specular_color);
      AKB_COPY_TEX("specular_color", specular->color, out->specular_color_texture);
    }
  }

  classic = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLASSIC);
  if (classic) {
    if (classic->diffuse) {
      akb_material_input_color4(classic->diffuse, 1.0f, 1.0f, 1.0f, 1.0f, out->base_color);
      AKB_COPY_TEX("base_color", classic->diffuse, out->base_color_texture);
    }
    if (classic->specular) {
      akb_material_input_color3(classic->specular, 1.0f, 1.0f, 1.0f, out->specular_color);
      AKB_COPY_TEX("specular_color", classic->specular, out->specular_color_texture);
    }
    if (classic->emission) {
      akb_material_input_color3(classic->emission, 0.0f, 0.0f, 0.0f, out->emissive_color);
      AKB_COPY_TEX("emissive", classic->emission, out->emissive_texture);
    }
    out->specular_strength = classic->shininess;
    if (classic->ior > 0.0f)
      out->ior = classic->ior;
  }

  clearcoat = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLEARCOAT);
  if (clearcoat) {
    out->clearcoat = akb_material_input_scalar(clearcoat->factor, 0.0f);
    out->clearcoat_roughness = akb_material_input_scalar(clearcoat->roughness, 0.0f);
    out->clearcoat_normal_scale = clearcoat->normalScale == 0.0f
                                  ? akb_material_input_scalar(clearcoat->normal, 1.0f)
                                  : clearcoat->normalScale;
    AKB_COPY_TEX("clearcoat", clearcoat->factor, out->clearcoat_texture);
    AKB_COPY_TEX("clearcoat_roughness", clearcoat->roughness, out->clearcoat_roughness_texture);
    AKB_COPY_TEX("clearcoat_normal", clearcoat->normal, out->clearcoat_normal_texture);
  }

  transmission = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_TRANSMISSION);
  if (transmission) {
    out->transmission = akb_material_input_scalar(transmission->factor, 0.0f);
    AKB_COPY_TEX("transmission", transmission->factor, out->transmission_texture);
  }

  sheen = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SHEEN);
  if (sheen) {
    out->has_sheen = 1;
    out->sheen_roughness = akb_material_input_scalar(sheen->roughness, 0.0f);
    if (sheen->color)
      akb_material_input_color3(sheen->color, 0.0f, 0.0f, 0.0f, out->sheen_color);
    AKB_COPY_TEX("sheen_color", sheen->color, out->sheen_color_texture);
    AKB_COPY_TEX("sheen_roughness", sheen->roughness, out->sheen_roughness_texture);
  }

  iridescence = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
  if (iridescence) {
    out->iridescence = akb_material_input_scalar(iridescence->factor, 0.0f);
    out->iridescence_ior = iridescence->ior > 0.0f
                           ? iridescence->ior
                           : out->iridescence_ior;
    out->iridescence_thickness_minimum = iridescence->thicknessMinimum;
    out->iridescence_thickness_maximum = iridescence->thicknessMaximum;
    AKB_COPY_TEX("iridescence", iridescence->factor, out->iridescence_texture);
    AKB_COPY_TEX("iridescence_thickness", iridescence->thickness, out->iridescence_thickness_texture);
  }

  volume = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_VOLUME);
  if (volume) {
    out->volume_thickness = akb_material_input_scalar(volume->thickness, 0.0f);
    out->volume_attenuation_distance = volume->attenuationDistance > 0.0f
                                       ? volume->attenuationDistance
                                       : out->volume_attenuation_distance;
    out->volume_attenuation_color[0] = volume->attenuationColor.vec[0];
    out->volume_attenuation_color[1] = volume->attenuationColor.vec[1];
    out->volume_attenuation_color[2] = volume->attenuationColor.vec[2];
    AKB_COPY_TEX("volume_thickness", volume->thickness, out->volume_thickness_texture);
  }

  subsurface = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SUBSURFACE);
  if (subsurface) {
    if (subsurface->color)
      akb_material_input_color3(subsurface->color, 0.0f, 0.0f, 0.0f, out->volume_scatter_color);
    out->volume_scatter_anisotropy = subsurface->anisotropy;
  }

  anisotropy = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_ANISOTROPY);
  if (anisotropy) {
    out->anisotropy = akb_material_input_scalar(anisotropy->strength, 0.0f);
    out->anisotropy_rotation = akb_material_input_scalar(anisotropy->rotation, 0.0f);
    AKB_COPY_TEX("anisotropy", anisotropy->strength, out->anisotropy_texture);
  }

  diffuse_transmission = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION);
  if (diffuse_transmission) {
    out->diffuse_transmission = akb_material_input_scalar(diffuse_transmission->factor, 0.0f);
    if (diffuse_transmission->color)
      akb_material_input_color3(diffuse_transmission->color,
                                1.0f,
                                1.0f,
                                1.0f,
                                out->diffuse_transmission_color);
    AKB_COPY_TEX("diffuse_transmission_color",
                 diffuse_transmission->color,
                 out->diffuse_transmission_color_texture);
    AKB_COPY_TEX("diffuse_transmission",
                 diffuse_transmission->factor,
                 out->diffuse_transmission_texture);
  }

  dispersion = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DISPERSION);
  if (dispersion)
    out->dispersion = dispersion->dispersion;

  if ((surface->flags & (AK_MATERIAL_FLAG_ALPHA_BLEND | AK_MATERIAL_FLAG_ALPHA_MASK))
      || surface->opacity)
    opacity = out->base_color[3];
  else
    opacity = 1.0f;

  if (surface->opacity) {
    out->transparent_amount = akb_material_input_scalar(surface->opacity, 1.0f);
    opacity *= out->transparent_amount;
    out->transparent_color[0] = 1.0f;
    out->transparent_color[1] = 1.0f;
    out->transparent_color[2] = 1.0f;
    out->transparent_color[3] = out->transparent_amount;
    out->transparent_inverted = ak_materialInputFlag(surface->opacity, AK_MATERIAL_INPUT_FLAG_INVERTED) ? 1 : 0;
    AKB_COPY_TEX("transparent", surface->opacity, out->transparent_texture);
  }

  if (surface->flags & AK_MATERIAL_FLAG_ALPHA_MASK)
    out->alpha_mode = 2;
  else if ((surface->flags & AK_MATERIAL_FLAG_ALPHA_BLEND)
           || opacity < 0.999f
           || akb_cstr_has(out->transparent_texture))
    out->alpha_mode = 1;
  else
    out->alpha_mode = 0;
  out->opacity = akb_clampf(opacity, 0.0f, 1.0f);
  out->base_color[3] = out->opacity;

#undef AKB_COPY_TEX
}

static const char *
akb_material_variant_name(AkDoc *doc, uint32_t index) {
  AkMaterialVariant *variant;
  uint32_t i;

  variant = doc ? doc->materialVariants : NULL;
  for (i = 0; variant && i < index; i++)
    variant = variant->next;

  return variant ? variant->name : NULL;
}

static int
akb_extract_material_variants(AkDoc *doc,
                              AkInstanceGeometry *instance,
                              AkMeshPrimitive *prim,
                              AkbPrimitive *out) {
  AkResolvedMaterial resolved;
  AkbMaterialVariantMap *items;
  const char *variant_name;
  const char *material_name;
  uint32_t i, count;

  if (!doc || !prim || !out || doc->materialVariantCount == 0)
    return 1;

  items = (AkbMaterialVariantMap *)calloc(doc->materialVariantCount, sizeof(*items));
  if (!items)
    return 0;

  count = 0;
  for (i = 0; i < doc->materialVariantCount; i++) {
    memset(&resolved, 0, sizeof(resolved));
    if (!ak_materialResolve(prim, instance, i, &resolved)
        || resolved.variantIndex != i
        || !resolved.material)
      continue;

    items[count].variant_index = i;
    items[count].material = resolved.material;
    variant_name = akb_material_variant_name(doc, i);
    material_name = resolved.material->name;

    if (variant_name && variant_name[0])
      snprintf(items[count].variant_name, sizeof(items[count].variant_name), "%s", variant_name);
    if (material_name && material_name[0])
      snprintf(items[count].material_name, sizeof(items[count].material_name), "%s", material_name);
    count++;
  }

  if (!count) {
    free(items);
    return 1;
  }

  out->material_variants = items;
  out->material_variant_count = count;
  return 1;
}

