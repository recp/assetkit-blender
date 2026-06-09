static void
akb_extract_node_camera(AkbSceneNode *out, AkNode *node) {
  AkCamera *camera;
  AkProjection *projection;

  if (!out || !node || !node->camera)
    return;

  camera = (AkCamera *)ak_instanceObject(node->camera);
  if (!camera || !camera->optics || !camera->optics->proj)
    return;

  projection = camera->optics->proj;
  out->camera_extra = ak_extra(camera);
  out->camera_imager_extra = camera->imager ? ak_extra(camera->imager) : NULL;
  out->camera_type = (uint8_t)projection->type + 1;
  out->camera_name = akb_name(camera->name, out->name);

  if (projection->type == AK_PROJECTION_PERSPECTIVE) {
    AkPerspective *persp;

    persp = (AkPerspective *)projection;
    out->camera_values[0] = persp->xfov;
    out->camera_values[1] = persp->yfov;
    out->camera_values[2] = persp->aspectRatio;
    out->camera_values[3] = persp->znear;
    out->camera_values[4] = persp->zfar;
  } else if (projection->type == AK_PROJECTION_ORTHOGRAPHIC) {
    AkOrthographic *ortho;

    ortho = (AkOrthographic *)projection;
    out->camera_values[0] = ortho->xmag;
    out->camera_values[1] = ortho->ymag;
    out->camera_values[2] = ortho->aspectRatio;
    out->camera_values[3] = ortho->znear;
    out->camera_values[4] = ortho->zfar;
  }
}

static void
akb_extract_node_light(AkbSceneNode *out, AkNode *node) {
  AkLight *light;
  AkLightBase *base;

  if (!out || !node || !node->light)
    return;

  light = (AkLight *)ak_instanceObject(node->light);
  if (!light || !light->data)
    return;

  base = light->data;
  out->light_extra = ak_extra(light);
  out->light_type = (uint8_t)base->type;
  out->light_name = akb_name(light->name, out->name);
  out->light_color[0] = base->color.rgba.R;
  out->light_color[1] = base->color.rgba.G;
  out->light_color[2] = base->color.rgba.B;
  out->light_values[0] = base->intensity;
  out->light_values[1] = base->range;

  if (base->type == AK_LIGHT_TYPE_SPOT) {
    AkSpotLight *spot;

    spot = (AkSpotLight *)base;
    out->light_values[2] = spot->innerConeAngle;
    out->light_values[3] = spot->outerConeAngle;
    out->light_values[4] = spot->coneFalloffExponent;
  }
}

static int
akb_extract_scene_node(AkbSceneNodeList *nodes,
                       AkDoc *doc,
                       AkbSharedDoc *doc_owner,
                       AkNode *node,
                       const AkbAnimationIndex *anim_index,
                       const AkbCoordContext *coord,
                       int32_t parent_index,
                       int32_t *node_index) {
  AkbSceneNode out = {0};
  int ok;

  if (!nodes || !node || !node_index)
    return 0;

  *node_index = (int32_t)nodes->count;
  out.source = node;
  out.name = node->name;
  out.parent_index = parent_index;
  out.visible = node->visible ? 1 : 0;
  out.layers = node->layer;
  ak_transformCombine(node->transform, out.matrix);
  out.has_transform = 1;
  akb_extract_node_camera(&out, node);
  akb_extract_node_light(&out, node);
  if ((anim_index && anim_index->count)
      || (!anim_index && doc && doc->lib.animations.first)) {
    out.animation = akb_animation_new(doc, doc_owner, node, anim_index, coord, &ok);
    if (!ok) {
      akb_scene_node_free(&out);
      return 0;
    }
  }

  if (!akb_node_list_push(nodes, &out)) {
    akb_scene_node_free(&out);
    return 0;
  }

  return 1;
}

static int
akb_primitive_supported(AkMeshPrimitive *prim, const AkbLoadOptions *options) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
    case AKB_PRIMITIVE_POLYGONS:
    case AKB_PRIMITIVE_POINTS:
      return 1;
    case AKB_PRIMITIVE_LINES:
      return options ? options->import_lines : 1;
    default:
      return 0;
  }
}

static uint32_t
akb_primitive_mode(AkMeshPrimitive *prim) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
      return (uint32_t)((AkTriangles *)prim)->mode;
    case AKB_PRIMITIVE_LINES:
      return (uint32_t)((AkLines *)prim)->mode;
    default:
      return 0;
  }
}

static uint32_t
akb_primitive_index_width(AkMeshPrimitive *prim) {
  if (!prim)
    return 0;

  switch (prim->type) {
    case AKB_PRIMITIVE_TRIANGLES:
      return ((AkTriangles *)prim)->mode == 0
             || ((AkTriangles *)prim)->mode == AK_TRIANGLES
             ? 3
             : 0;
    case AKB_PRIMITIVE_POLYGONS:
      return ((AkPolygon *)prim)->vcount ? 1 : 0;
    case AKB_PRIMITIVE_LINES:
      return ((AkLines *)prim)->mode == 0
             || ((AkLines *)prim)->mode == AK_LINES
             ? 2
             : 0;
    case AKB_PRIMITIVE_POINTS:
      return 1;
    default:
      return 0;
  }
}

static AkInput *
akb_primitive_position_input(AkMeshPrimitive *prim) {
  return prim && prim->pos && prim->pos->accessor && prim->pos->accessor->count > 0
         ? prim->pos
         : akb_find_input_with_accessor(prim,
                                        AK_INPUT_POSITION,
                                        AK_INPUT_POSITION,
                                        "POSITION",
                                        NULL);
}

static int
akb_doc_is_wavefront(const AkDoc *doc) {
  return doc && doc->inf && doc->inf->ftype == AK_FILE_TYPE_WAVEFRONT;
}

static int
akb_wavefront_primitive_smooth(const AkDoc *doc, const AkMeshPrimitive *prim) {
  return akb_doc_is_wavefront(doc)
         && prim
         && ak_meshPrimitiveSmoothShading(prim);
}

static int
akb_primitive_can_use_fast_extract(AkMeshPrimitive *prim,
                                   AkGeometry *geom,
                                   AkMesh *mesh,
                                   AkNode *node,
                                   AkInput *pos_input,
                                   AkbAnimation *animation,
                                   AkbAnimation *morph_animation) {
  AkInput *input;

  if (!prim || !mesh || !geom)
    return 0;

  if ((prim->inputCount && prim->inputCount > 1)
      || prim->material
      || prim->materialBindings
      || prim->materialBindingCount
      || prim->variantMappings
      || prim->variantMappingCount
      || prim->gsplat
      || ak_extra(prim)
      || ak_extra(mesh)
      || ak_extra(geom)
      || (animation && animation->count)
      || (morph_animation && morph_animation->count))
    return 0;

  if (node) {
    if (node->gpuInstancing
        || (node->geometry
            && (node->geometry->morpher
                || node->geometry->skinner
                || akb_instance_affects_material(prim, node->geometry))))
      return 0;
  }

  for (input = prim->input; input; input = input->next) {
    if (!input->accessor || input->accessor->count == 0)
      continue;
    if (input == pos_input
        || input->semantic == AK_INPUT_POSITION
        || akb_raw_semantic_is(input, "POSITION"))
      continue;
    return 0;
  }

  return 1;
}

static int
akb_extract_simple_mesh_group(AkbArena *arena,
                              AkbPrimitiveList *list,
                              AkDoc *doc,
                              AkNode *node,
                              int32_t node_index,
                              AkGeometry *geom,
                              AkMesh *mesh,
                              const AkbLoadOptions *options,
                              AkbAnimation *animation,
                              AkbAnimation *morph_animation,
                              int *handled) {
  AkbPrimitive out = {0};
  AkMeshPrimitive *prim;
  AkInput *pos_input;
  const float *positions;
  AkbIndexView index_view;
  size_t total_vertex_count = 0;
  size_t total_loop_count = 0;
  size_t total_face_count = 0;
  size_t vertex_offset = 0;
  size_t loop_offset = 0;
  size_t raw_loop_count;
  uint32_t pos_count;
  uint32_t loop_count;
  uint32_t stride;
  uint32_t pos_offset;
  uint32_t prim_count = 0;
  uint32_t i;
  const char *base_name;
  int wavefront;
  int smooth_shading;
  int smooth_shading_set;

  if (handled)
    *handled = 0;
  if (!handled || !list || !mesh || !geom)
    return 0;

  wavefront = akb_doc_is_wavefront(doc);
  smooth_shading = 0;
  smooth_shading_set = 0;

  for (prim = mesh->primitive; prim; prim = prim->next) {
    int prim_smooth;

    if (!akb_primitive_supported(prim, options))
      return 1;
    if (prim->type != AKB_PRIMITIVE_TRIANGLES
        || akb_primitive_index_width(prim) != 3)
      return 1;

    pos_input = akb_primitive_position_input(prim);
    if (!pos_input || !pos_input->accessor || pos_input->accessor->count == 0)
      return 1;

    if (!akb_primitive_can_use_fast_extract(prim,
                                            geom,
                                            mesh,
                                            node,
                                            pos_input,
                                            animation,
                                            morph_animation))
      return 1;

    positions = akb_accessor_float_borrow(pos_input->accessor, 3, &pos_count);
    if (!positions || pos_count == 0)
      return 1;

    if (wavefront) {
      prim_smooth = akb_wavefront_primitive_smooth(doc, prim);
      if (!smooth_shading_set) {
        smooth_shading = prim_smooth;
        smooth_shading_set = 1;
      } else if (smooth_shading != prim_smooth) {
        return 1;
      }
    }

    stride = prim->indexStride ? prim->indexStride : 1;
    if (akb_index_view_init(prim, &index_view)) {
      raw_loop_count = index_view.count / stride;
      if (raw_loop_count > UINT32_MAX)
        return 1;
      loop_count = (uint32_t)raw_loop_count;
    } else {
      loop_count = pos_count;
    }
    loop_count = (loop_count / 3) * 3;
    if (!loop_count)
      continue;

    if (total_vertex_count > (SIZE_MAX / (3 * sizeof(float))) - pos_count
        || total_loop_count > (SIZE_MAX / sizeof(uint32_t)) - loop_count
        || total_face_count > SIZE_MAX - (loop_count / 3))
      return 0;

    total_vertex_count += pos_count;
    total_loop_count += loop_count;
    total_face_count += loop_count / 3;
    prim_count++;
  }

  if (prim_count < 2 || !total_vertex_count || !total_loop_count || !total_face_count)
    return 1;
  if (total_vertex_count > UINT32_MAX
      || total_loop_count > UINT32_MAX
      || total_face_count > UINT32_MAX)
    return 1;

  *handled = 1;
  out.node_index = node_index;
  out.mesh_key = (uintptr_t)mesh;
  out.primitive_index = 0;
  out.file_type = doc && doc->inf ? (uint32_t)doc->inf->ftype : 0;
  out.primitive_type = AKB_PRIMITIVE_TRIANGLES;
  out.primitive_mode = AK_TRIANGLES;
  out.smooth_shading = (uint8_t)(wavefront && smooth_shading);
  out.vertex_count = (uint32_t)total_vertex_count;
  out.loop_count = (uint32_t)total_loop_count;
  out.face_count = (uint32_t)total_face_count;

  if (node) {
    out.object_name = akb_name(node->name, "AssetKitObject");
    ak_transformCombine(node->transform, out.matrix);
    out.has_node = 1;
  }

  base_name = akb_name(mesh->name, akb_name(geom->name, "AssetKitMesh"));
  out.name = base_name;

  out.vertices = (float *)akb_owned_alloc(arena,
                                          total_vertex_count * 3 * sizeof(float),
                                          sizeof(float),
                                          &out.arena_vertices);
  out.indices = (uint32_t *)akb_owned_alloc(arena,
                                            total_loop_count * sizeof(uint32_t),
                                            sizeof(uint32_t),
                                            &out.arena_indices);
  if (!out.vertices || !out.indices) {
    akb_primitive_free(&out);
    return 0;
  }

  for (prim = mesh->primitive; prim; prim = prim->next) {
    pos_input = akb_primitive_position_input(prim);
    positions = akb_accessor_float_borrow(pos_input->accessor, 3, &pos_count);
    stride = prim->indexStride ? prim->indexStride : 1;
    pos_offset = pos_input->indexOffset;
    if (akb_index_view_init(prim, &index_view)) {
      raw_loop_count = index_view.count / stride;
      if (raw_loop_count > UINT32_MAX) {
        akb_primitive_free(&out);
        return 0;
      }
      loop_count = (uint32_t)raw_loop_count;
    } else {
      loop_count = pos_count;
    }
    loop_count = (loop_count / 3) * 3;
    if (!loop_count)
      continue;

    memcpy(out.vertices + vertex_offset * 3,
           positions,
           (size_t)pos_count * 3 * sizeof(float));

    if (akb_index_view_init(prim, &index_view)) {
      if (!akb_index_view_copy_u32(&index_view,
                                   out.indices + loop_offset,
                                   loop_count,
                                   stride,
                                   pos_offset,
                                   (uint32_t)vertex_offset)) {
        akb_primitive_free(&out);
        return 0;
      }
    } else {
      for (i = 0; i < loop_count; i++)
        out.indices[loop_offset + i] = (uint32_t)(vertex_offset + i);
    }

    vertex_offset += pos_count;
    loop_offset += loop_count;
  }

  akb_finalize_primitive_buffers(arena, &out, options);

  if (!akb_list_push(list, &out)) {
    akb_primitive_free(&out);
    return 0;
  }

  return 1;
}

static int
akb_extract_primitive(AkbArena *arena,
                      AkbPrimitiveList *list,
                      AkbSceneNodeList *nodes,
                      AkDoc *doc,
                      AkbSharedDoc *doc_owner,
                      const AkbAnimationIndex *anim_index,
                      AkbAnimation *animation,
                      AkbAnimation *morph_animation,
                      AkNode *node,
                      int32_t node_index,
                      AkGeometry *geom,
                      AkMesh *mesh,
                      AkMeshPrimitive *prim,
                      uint32_t prim_index,
                      const AkbLoadOptions *options) {
  AkbPrimitive out = {0};
  AkInput *pos_input, *normal_input, *tangent_input;
  AkbInputScan input_scan;
  AkbIndexView index_view = {0};
  const AkbIndexView *attr_index_view;
  const uint32_t *borrowed_indices;
  size_t raw_loop_count;
  uint32_t pos_count = 0;
  uint32_t stride, pos_offset;
  uint32_t i;
  uint32_t index_width;
  int ok;
  int fast_extract;
  int has_index_view;
  const char *base_name;
  uint8_t arena_normals;
  uint8_t arena_tangents;
  int flip_uv_v;

  index_width = akb_primitive_index_width(prim);
  if (!index_width)
    return 1;

  pos_input = akb_primitive_position_input(prim);
  if (!pos_input || !pos_input->accessor || pos_input->accessor->count == 0)
    return 1;

  fast_extract = akb_primitive_can_use_fast_extract(prim,
                                                    geom,
                                                    mesh,
                                                    node,
                                                    pos_input,
                                                    animation,
                                                    morph_animation);

  out.node_index = node_index;
  out.mesh_key = (uintptr_t)mesh;
  out.primitive_index = prim_index;
  out.file_type = doc && doc->inf ? (uint32_t)doc->inf->ftype : 0;
  out.primitive_type = (uint32_t)prim->type;
  out.primitive_mode = akb_primitive_mode(prim);
  out.smooth_shading = (uint8_t)akb_wavefront_primitive_smooth(doc, prim);
  flip_uv_v = akb_blender_flip_uv_v(doc);
  if (!fast_extract) {
    out.primitive_extra = ak_extra(prim);
    out.mesh_extra = ak_extra(mesh);
    out.geometry_extra = ak_extra(geom);
    if (prim->gsplat) {
      out.has_gsplat = 1;
      out.gsplat.kernel = (uint32_t)prim->gsplat->kernel;
      out.gsplat.color_space = (uint32_t)prim->gsplat->colorSpace;
      out.gsplat.projection = (uint32_t)prim->gsplat->projection;
      out.gsplat.sorting_method = (uint32_t)prim->gsplat->sortingMethod;
      out.gsplat.decoded_count = prim->gsplat->decodedCount;
    }
    akb_extract_material(doc, akb_node_geometry_instance(node), prim, &out);
    if (anim_index && anim_index->count) {
      out.material_animation = akb_material_animation_new(doc,
                                                          doc_owner,
                                                          anim_index,
                                                          prim,
                                                          akb_node_geometry_instance(node),
                                                          NULL,
                                                          &ok);
      if (!ok) {
        akb_primitive_free(&out);
        return 0;
      }
    }
    if ((prim->materialBindings
         || prim->materialBindingCount
         || prim->variantMappings
         || prim->variantMappingCount)
        && !akb_extract_material_variants(doc,
                                          akb_node_geometry_instance(node),
                                          prim,
                                          &out)) {
      akb_primitive_free(&out);
      return 0;
    }
    out.animation = akb_animation_retain(animation);
    out.morph_animation = akb_animation_retain(morph_animation);
    if (node && node->gpuInstancing && !akb_extract_instancing(arena, &out, node)) {
      akb_primitive_free(&out);
      return 0;
    }
  }

  if (node) {
    out.object_name = akb_name(node->name, "AssetKitObject");
    ak_transformCombine(node->transform, out.matrix);
    out.has_node = 1;
  }

  out.vertices = akb_accessor_float_borrow(pos_input->accessor, 3, &pos_count);
  if (out.vertices) {
    out.borrowed_vertices = 1;
    out.zero_copy_flags |= 1;
    akb_primitive_retain_doc(&out, doc_owner);
  } else {
    out.vertices = akb_accessor_float_copy(pos_input->accessor, 3, &pos_count);
    if (!out.vertices) {
      akb_primitive_free(&out);
      return 0;
    }
  }
  out.vertex_count = pos_count;

  has_index_view = akb_index_view_init(prim, &index_view);
  if (has_index_view) {
    stride = prim->indexStride ? prim->indexStride : 1;
    pos_offset = pos_input->indexOffset;
    raw_loop_count = index_view.count / stride;
    if (raw_loop_count > UINT32_MAX) {
      akb_primitive_free(&out);
      return 0;
    }
    out.loop_count = (uint32_t)raw_loop_count;
    borrowed_indices = akb_index_view_u32_ptr(&index_view);
    if (borrowed_indices && stride == 1 && pos_offset == 0) {
      out.indices = (uint32_t *)borrowed_indices;
      out.borrowed_indices = 1;
      out.zero_copy_flags |= 2;
      akb_primitive_retain_doc(&out, doc_owner);
    } else {
      out.indices = (uint32_t *)akb_owned_alloc(arena,
                                                 (size_t)out.loop_count * sizeof(uint32_t),
                                                 sizeof(uint32_t),
                                                 &out.arena_indices);
      if (!out.indices) {
        akb_primitive_free(&out);
        return 0;
      }

      if (!akb_index_view_copy_u32(&index_view,
                                   out.indices,
                                   out.loop_count,
                                   stride,
                                   pos_offset,
                                   0)) {
        akb_primitive_free(&out);
        return 0;
      }
    }
  } else {
    out.loop_count = out.vertex_count;
    out.indices = (uint32_t *)akb_owned_alloc(arena,
                                               (size_t)out.loop_count * sizeof(uint32_t),
                                               sizeof(uint32_t),
                                               &out.arena_indices);
    if (!out.indices) {
      akb_primitive_free(&out);
      return 0;
    }

    for (i = 0; i < out.loop_count; i++)
      out.indices[i] = i;
  }

  out.loop_count = (out.loop_count / index_width) * index_width;
  if (out.primitive_type == AKB_PRIMITIVE_TRIANGLES) {
    out.face_count = out.loop_count / index_width;
  } else if (out.primitive_type == AKB_PRIMITIVE_POLYGONS
             && ((AkPolygon *)prim)->vcount) {
    out.face_count = (uint32_t)((AkPolygon *)prim)->vcount->count;
  } else {
    out.face_count = 0;
  }
  attr_index_view = has_index_view
                    && (prim->indexStride ? prim->indexStride : 1) > 1
                    ? &index_view
                    : NULL;
  if (out.face_count) {
    size_t loop_meta_count;

    loop_meta_count = out.primitive_type == AKB_PRIMITIVE_TRIANGLES && index_width == 3
                        ? (size_t)out.face_count
                        : (size_t)out.face_count * 2u;
    out.loop_meta = (int32_t *)akb_owned_alloc(arena,
                                                loop_meta_count * sizeof(int32_t),
                                                sizeof(int32_t),
                                                &out.arena_loop_meta);
    if (!out.loop_meta) {
      akb_primitive_free(&out);
      return 0;
    }
    out.loop_starts = out.loop_meta;
    if (loop_meta_count > out.face_count)
      out.loop_totals = out.loop_meta + out.face_count;
  }

  if (out.loop_starts) {
    if (out.primitive_type == AKB_PRIMITIVE_POLYGONS
        && ((AkPolygon *)prim)->vcount
        && out.loop_totals) {
      AkUInt *vcount_items;
      uint32_t loop_start;

      vcount_items = ((AkPolygon *)prim)->vcount->items;
      loop_start = 0;
      for (i = 0; i < out.face_count; i++) {
        AkUInt face_loop_count;

        face_loop_count = vcount_items[i];
        if (loop_start >= out.loop_count)
          face_loop_count = 0;
        else if ((uint64_t)loop_start + face_loop_count > out.loop_count)
          face_loop_count = out.loop_count - loop_start;
        out.loop_starts[i] = (int32_t)loop_start;
        out.loop_totals[i] = (int32_t)face_loop_count;
        loop_start += (uint32_t)face_loop_count;
      }
    } else {
      for (i = 0; i < out.face_count; i++) {
        out.loop_starts[i] = (int32_t)(i * index_width);
        if (out.loop_totals)
          out.loop_totals[i] = (int32_t)index_width;
      }
    }
  }

  if (!fast_extract
      && out.primitive_type != AKB_PRIMITIVE_TRIANGLES
      && !akb_extract_point_float_attrs(&out, prim, doc_owner)) {
    akb_primitive_free(&out);
    return 0;
  }

  if (!fast_extract
      && (out.primitive_type == AKB_PRIMITIVE_TRIANGLES
          || out.primitive_type == AKB_PRIMITIVE_POLYGONS)) {
    akb_scan_inputs(prim, out.primitive_type, &input_scan);
    if (input_scan.point_attr_count
        && !akb_extract_point_float_attrs(&out, prim, doc_owner)) {
      akb_primitive_free(&out);
      return 0;
    }

    normal_input = input_scan.normal;
    akb_try_extract_vertex_normals(&out,
                                   normal_input,
                                   pos_input,
                                   doc_owner,
                                   node);
    if (!out.has_vertex_normals) {
      arena_normals = 0;
      out.normals = akb_loop_attribute_copy(arena,
                                            prim,
                                            normal_input,
                                            attr_index_view,
                                            out.indices,
                                            out.loop_count,
                                            3,
                                            0,
                                            &out.has_normals,
                                            &arena_normals);
      if (arena_normals)
        out.borrowed_normals = 1;
    }

    if (input_scan.uv_count == 1) {
      if (!akb_extract_one_loop_float_attr(arena,
                                           prim,
                                           input_scan.uv,
                                           attr_index_view,
                                           out.indices,
                                           out.loop_count,
                                           2,
                                           flip_uv_v,
                                           0.0f,
                                           "UVMap",
                                           &out.uv_sets,
                                           &out.uv_set_count,
                                           &out.arena_uv_sets)) {
        akb_primitive_free(&out);
        return 0;
      }
    } else if (input_scan.uv_count > 1) {
      if (!akb_extract_loop_float_attrs(arena,
                                        &out,
                                        prim,
                                        attr_index_view,
                                        out.indices,
                                        out.loop_count,
                                        AK_INPUT_TEXCOORD,
                                        AK_INPUT_UV,
                                        "TEXCOORD",
                                        "UV",
                                        2,
                                        flip_uv_v,
                                        0.0f,
                                        "UVMap",
                                        &out.uv_sets,
                                        &out.uv_set_count,
                                        &out.arena_uv_sets)) {
        akb_primitive_free(&out);
        return 0;
      }
    }
    if (out.uv_set_count) {
      out.uvs = out.uv_sets[0].values;
      out.has_uvs = 1;
    }

    if (input_scan.color_count == 1) {
      if (!akb_extract_one_loop_float_attr(arena,
                                           prim,
                                           input_scan.color,
                                           attr_index_view,
                                           out.indices,
                                           out.loop_count,
                                           4,
                                           0,
                                           1.0f,
                                           "Color",
                                           &out.color_sets,
                                           &out.color_set_count,
                                           &out.arena_color_sets)) {
        akb_primitive_free(&out);
        return 0;
      }
    } else if (input_scan.color_count > 1) {
      if (!akb_extract_loop_float_attrs(arena,
                                        &out,
                                        prim,
                                        attr_index_view,
                                        out.indices,
                                        out.loop_count,
                                        AK_INPUT_COLOR,
                                        AK_INPUT_COLOR,
                                        "COLOR",
                                        NULL,
                                        4,
                                        0,
                                        1.0f,
                                        "Color",
                                        &out.color_sets,
                                        &out.color_set_count,
                                        &out.arena_color_sets)) {
        akb_primitive_free(&out);
        return 0;
      }
    }
    if (out.color_set_count) {
      out.colors = out.color_sets[0].values;
      out.has_colors = 1;
    }

    tangent_input = input_scan.tangent;
    if (tangent_input) {
      arena_tangents = 0;
      out.tangents = akb_loop_attribute_copy(arena,
                                             prim,
                                             tangent_input,
                                             attr_index_view,
                                             out.indices,
                                             out.loop_count,
                                             4,
                                             0,
                                             &out.has_tangents,
                                             &arena_tangents);
      if (arena_tangents)
        out.borrowed_tangents = 1;
      if (out.tangents && tangent_input->accessor)
        akb_fill_missing_components(out.tangents,
                                    out.loop_count,
                                    4,
                                    tangent_input->accessor->componentCount,
                                    1.0f);
    }

    if (node && node->geometry && node->geometry->morpher) {
      if (!akb_extract_morph_targets(&out,
                                     geom,
                                     mesh,
                                     prim,
                                     prim_index,
                                     node->geometry->morpher)) {
        akb_primitive_free(&out);
        return 0;
      }
    }

    if (node && node->geometry && node->geometry->skinner) {
      if (!akb_extract_skin(arena,
                            &out,
                            nodes,
                            prim,
                            prim_index,
                            node->geometry->skinner)) {
        akb_primitive_free(&out);
        return 0;
      }
      if (node->geometry->skinner->skin
          && node->geometry->skinner->skin->joints
          && !node->geometry->skinner->overrideJoints
          && !akb_skin_into_bind_pose(&out)) {
        akb_primitive_free(&out);
        return 0;
      }
    }
  }

  base_name = akb_name(mesh->name, akb_name(geom->name, "AssetKitMesh"));
  if (mesh->primitiveCount > 1) {
    out.name = akb_arena_format_name_u32(arena, base_name, prim_index);
    if (!out.name) {
      akb_primitive_free(&out);
      return 0;
    }
  } else {
    out.name = base_name;
  }

  akb_finalize_primitive_buffers(arena, &out, options);

  if (!akb_list_push(list, &out)) {
    akb_primitive_free(&out);
    return 0;
  }

  return 1;
}

static void
akb_primitive_reuse_cache_free(AkbPrimitiveReuseCache *cache) {
  if (!cache)
    return;

  free(cache->items);
  memset(cache, 0, sizeof(*cache));
}

static uint64_t
akb_primitive_reuse_hash(AkGeometry *geom,
                         AkMesh *mesh,
                         AkMeshPrimitive *prim,
                         AkInstanceGeometry *instance,
                         uint32_t prim_index) {
  uint64_t hash = UINT64_C(1469598103934665603);

  hash = akb_fnv1a64_mix_u64(hash, (uintptr_t)geom);
  hash = akb_fnv1a64_mix_u64(hash, (uintptr_t)mesh);
  hash = akb_fnv1a64_mix_u64(hash, (uintptr_t)prim);
  hash = akb_fnv1a64_mix_u64(hash, (uintptr_t)instance);
  hash = akb_fnv1a64_mix_u64(hash, prim_index);
  return hash;
}

static int
akb_primitive_reuse_entry_matches(const AkbPrimitiveReuseEntry *entry,
                                  AkGeometry *geom,
                                  AkMesh *mesh,
                                  AkMeshPrimitive *prim,
                                  AkInstanceGeometry *instance,
                                  uint32_t prim_index) {
  return entry
         && entry->occupied
         && entry->geom == geom
         && entry->mesh == mesh
         && entry->prim == prim
         && entry->instance == instance
         && entry->prim_index == prim_index;
}

static void
akb_primitive_reuse_cache_insert_entry(AkbPrimitiveReuseEntry *items,
                                       size_t capacity,
                                       AkbPrimitiveReuseEntry entry) {
  size_t mask;
  size_t index;

  mask = capacity - 1;
  index = (size_t)akb_primitive_reuse_hash(entry.geom,
                                           entry.mesh,
                                           entry.prim,
                                           entry.instance,
                                           entry.prim_index) & mask;
  while (items[index].occupied)
    index = (index + 1) & mask;
  items[index] = entry;
}

static int
akb_primitive_reuse_cache_resize(AkbPrimitiveReuseCache *cache, size_t capacity) {
  AkbPrimitiveReuseEntry *items;
  AkbPrimitiveReuseEntry *old_items;
  size_t old_capacity;
  size_t i;

  if (!cache)
    return 1;

  if (capacity < 64)
    capacity = 64;
  if (capacity & (capacity - 1)) {
    size_t pow2 = 64;
    while (pow2 < capacity)
      pow2 <<= 1;
    capacity = pow2;
  }

  items = (AkbPrimitiveReuseEntry *)calloc(capacity, sizeof(*items));
  if (!items)
    return 0;

  old_items = cache->items;
  old_capacity = cache->capacity;
  for (i = 0; i < old_capacity; i++) {
    if (old_items[i].occupied)
      akb_primitive_reuse_cache_insert_entry(items, capacity, old_items[i]);
  }

  free(old_items);
  cache->items = items;
  cache->capacity = capacity;
  return 1;
}

static int
akb_primitive_reuse_cache_find(const AkbPrimitiveReuseCache *cache,
                               AkGeometry *geom,
                               AkMesh *mesh,
                               AkMeshPrimitive *prim,
                               AkInstanceGeometry *instance,
                               uint32_t prim_index,
                               size_t *source_index) {
  size_t mask;
  size_t index;

  if (!cache || !source_index || !cache->items || !cache->capacity)
    return 0;

  mask = cache->capacity - 1;
  index = (size_t)akb_primitive_reuse_hash(geom,
                                           mesh,
                                           prim,
                                           instance,
                                           prim_index) & mask;
  for (;;) {
    if (!cache->items[index].occupied)
      return 0;
    if (akb_primitive_reuse_entry_matches(&cache->items[index],
                                          geom,
                                          mesh,
                                          prim,
                                          instance,
                                          prim_index)) {
      *source_index = cache->items[index].source_index;
      return 1;
    }
    index = (index + 1) & mask;
  }
}

static int
akb_primitive_reuse_cache_add(AkbPrimitiveReuseCache *cache,
                              AkGeometry *geom,
                              AkMesh *mesh,
                              AkMeshPrimitive *prim,
                              AkInstanceGeometry *instance,
                              uint32_t prim_index,
                              size_t source_index) {
  AkbPrimitiveReuseEntry entry = {0};

  if (!cache)
    return 1;

  if (!cache->capacity
      || (cache->count + 1) * 10 >= cache->capacity * 7) {
    if (!akb_primitive_reuse_cache_resize(cache,
                                          cache->capacity
                                          ? cache->capacity * 2
                                          : 64))
      return 0;
  }

  entry.geom = geom;
  entry.mesh = mesh;
  entry.prim = prim;
  entry.instance = instance;
  entry.prim_index = prim_index;
  entry.source_index = source_index;
  entry.occupied = 1;
  akb_primitive_reuse_cache_insert_entry(cache->items, cache->capacity, entry);
  cache->count++;
  return 1;
}

static int
akb_primitive_can_reuse_mesh_data(const AkbAnimationIndex *anim_index,
                                  AkbAnimation *animation,
                                  AkbAnimation *morph_animation,
                                  AkNode *node,
                                  AkMeshPrimitive *prim) {
  if (!node || !node->geometry || !prim)
    return 0;
  if (anim_index && anim_index->count)
    return 0;
  if ((animation && animation->count)
      || (morph_animation && morph_animation->count))
    return 0;
  if (node->gpuInstancing
      || node->geometry->morpher
      || node->geometry->skinner
      || akb_instance_affects_material(prim, node->geometry))
    return 0;
  if (prim->type != AKB_PRIMITIVE_TRIANGLES
      || akb_primitive_index_width(prim) != 3
      || prim->gsplat
      || prim->materialBindings
      || prim->materialBindingCount
      || prim->variantMappings
      || prim->variantMappingCount)
    return 0;

  return 1;
}

static int
akb_loop_attrs_share(AkbLoopFloatAttribute **dst,
                     AkbLoopFloatAttribute *src,
                     uint32_t count) {
  uint32_t i;

  *dst = NULL;
  if (!src || !count)
    return 1;

  *dst = (AkbLoopFloatAttribute *)calloc(count, sizeof(**dst));
  if (!*dst)
    return 0;

  memcpy(*dst, src, (size_t)count * sizeof(**dst));
  for (i = 0; i < count; i++)
    (*dst)[i].borrowed = 1;

  return 1;
}

static int
akb_primitive_clone_shared(AkbPrimitive *dst,
                           const AkbPrimitive *src,
                           AkNode *node,
                           int32_t node_index) {
  AkbTextureInfo *texture_infos = NULL;

  if (!dst || !src)
    return 0;

  if (src->texture_info_count) {
    if (!src->texture_infos)
      return 0;
    texture_infos = (AkbTextureInfo *)malloc((size_t)src->texture_info_count * sizeof(*texture_infos));
    if (!texture_infos)
      return 0;
    memcpy(texture_infos,
           src->texture_infos,
           (size_t)src->texture_info_count * sizeof(*texture_infos));
  }

  *dst = *src;

  dst->texture_infos = texture_infos;
  dst->texture_info_capacity = src->texture_info_count;

  dst->doc_owner = src->doc_owner;
  akb_shared_doc_retain(dst->doc_owner);
  dst->animation = akb_animation_retain(src->animation);
  dst->morph_animation = akb_animation_retain(src->morph_animation);
  dst->material_animation = akb_animation_retain(src->material_animation);

  dst->borrowed_vertices = src->vertices != NULL;
  dst->borrowed_indices = src->indices != NULL;
  dst->borrowed_edges = src->edges != NULL;
  dst->borrowed_normals = src->normals != NULL;
  dst->borrowed_vertex_normals = src->vertex_normals != NULL;
  dst->borrowed_tangents = src->tangents != NULL;
  dst->arena_vertices = 0;
  dst->arena_indices = 0;
  dst->arena_edges = 0;
  dst->arena_loop_meta = src->loop_meta != NULL;
  dst->arena_instance_matrices = src->instance_matrices != NULL;
  dst->arena_skin_joint_nodes = src->skin_joint_nodes != NULL;
  dst->arena_skin_inverse_bind_matrices = src->skin_inverse_bind_matrices != NULL;
  dst->arena_skin_joint_sources = src->skin_joint_sources != NULL;

  dst->uv_sets = NULL;
  dst->color_sets = NULL;
  dst->point_attrs = NULL;
  dst->material_variants = NULL;
  dst->morph_targets = NULL;
  dst->skin_pose_animations = NULL;
  dst->base_color_texture = NULL;
  dst->metallic_roughness_texture = NULL;
  dst->occlusion_texture = NULL;
  dst->normal_texture = NULL;
  dst->emissive_texture = NULL;
  dst->transparent_texture = NULL;
  dst->specular_texture = NULL;
  dst->specular_color_texture = NULL;
  dst->clearcoat_texture = NULL;
  dst->clearcoat_roughness_texture = NULL;
  dst->clearcoat_normal_texture = NULL;
  dst->transmission_texture = NULL;
  dst->sheen_color_texture = NULL;
  dst->sheen_roughness_texture = NULL;
  dst->iridescence_texture = NULL;
  dst->iridescence_thickness_texture = NULL;
  dst->volume_thickness_texture = NULL;
  dst->anisotropy_texture = NULL;
  dst->diffuse_transmission_texture = NULL;
  dst->diffuse_transmission_color_texture = NULL;
  dst->material_variant_count = 0;
  dst->morph_target_count = 0;
  dst->skin_pose_animation_count = 0;

  if (!akb_primitive_clone_texture_paths(dst, src)) {
    akb_primitive_free(dst);
    return 0;
  }

  if (!akb_loop_attrs_share(&dst->uv_sets, src->uv_sets, src->uv_set_count)
      || !akb_loop_attrs_share(&dst->color_sets, src->color_sets, src->color_set_count)
      || !akb_loop_attrs_share(&dst->point_attrs, src->point_attrs, src->point_attr_count)) {
    akb_primitive_free(dst);
    return 0;
  }

  if (dst->uv_set_count)
    dst->uvs = dst->uv_sets[0].values;
  if (dst->color_set_count)
    dst->colors = dst->color_sets[0].values;

  dst->node_index = node_index;
  dst->has_node = 0;
  dst->object_name = NULL;
  if (node) {
    dst->object_name = akb_name(node->name, "AssetKitObject");
    ak_transformCombine(node->transform, dst->matrix);
    dst->has_node = 1;
  }

  return 1;
}

static int
akb_extract_primitive_cached(AkbArena *arena,
                             AkbPrimitiveList *list,
                             AkbSceneNodeList *nodes,
                             AkDoc *doc,
                             AkbSharedDoc *doc_owner,
                             const AkbAnimationIndex *anim_index,
                             AkbPrimitiveReuseCache *reuse_cache,
                             AkbAnimation *animation,
                             AkbAnimation *morph_animation,
                             AkNode *node,
                             int32_t node_index,
                             AkGeometry *geom,
                             AkMesh *mesh,
                             AkMeshPrimitive *prim,
                             uint32_t prim_index,
                             const AkbLoadOptions *options) {
  AkbPrimitive out = {0};
  AkInstanceGeometry *instance;
  size_t source_index;
  size_t before_count;
  int can_reuse;

  instance = akb_node_geometry_instance(node);
  can_reuse = reuse_cache
              && akb_primitive_can_reuse_mesh_data(anim_index,
                                                   animation,
                                                   morph_animation,
                                                   node,
                                                   prim);
  if (can_reuse
      && akb_primitive_reuse_cache_find(reuse_cache,
                                        geom,
                                        mesh,
                                        prim,
                                        instance,
                                        prim_index,
                                        &source_index)
      && source_index < list->count) {
    if (!akb_primitive_clone_shared(&out, &list->items[source_index], node, node_index))
      return 0;
    if (!akb_list_push(list, &out)) {
      akb_primitive_free(&out);
      return 0;
    }
    reuse_cache->hits++;
    return 1;
  }

  before_count = list->count;
  if (!akb_extract_primitive(arena,
                             list,
                             nodes,
                             doc,
                             doc_owner,
                             anim_index,
                             animation,
                             morph_animation,
                             node,
                             node_index,
                             geom,
                             mesh,
                             prim,
                             prim_index,
                             options))
    return 0;

  if (can_reuse && list->count > before_count) {
    return akb_primitive_reuse_cache_add(reuse_cache,
                                         geom,
                                         mesh,
                                         prim,
                                         instance,
                                         prim_index,
                                         before_count);
  }

  return 1;
}

static int
akb_extract_mesh(AkbArena *arena,
                 AkbPrimitiveList *list,
                 AkbSceneNodeList *nodes,
                 AkDoc *doc,
                 AkbSharedDoc *doc_owner,
                 const AkbAnimationIndex *anim_index,
                 AkbPrimitiveReuseCache *reuse_cache,
                 AkbAnimation *animation,
                 AkbAnimation *morph_animation,
                 AkNode *node,
                 int32_t node_index,
                 AkGeometry *geom,
                 const AkbLoadOptions *options) {
  AkObject *gdata;
  AkMesh *mesh;
  AkMeshPrimitive *prim;
  uint32_t prim_index = 0;
  int handled_group = 0;

  if (!geom || !(gdata = geom->gdata) || gdata->type != AKB_GEOMETRY_MESH)
    return 1;

  mesh = (AkMesh *)ak_objGet(gdata);
  if (!mesh)
    return 1;

  if (!akb_extract_simple_mesh_group(arena,
                                     list,
                                     doc,
                                     node,
                                     node_index,
                                     geom,
                                     mesh,
                                     options,
                                     animation,
                                     morph_animation,
                                     &handled_group))
    return 0;
  if (handled_group)
    return 1;

  for (prim = mesh->primitive; prim; prim = prim->next, prim_index++) {
    if (!akb_primitive_supported(prim, options))
      continue;
    if (!akb_extract_primitive_cached(arena,
                                      list,
                                      nodes,
                                      doc,
                                      doc_owner,
                                      anim_index,
                                      reuse_cache,
                                      animation,
                                      morph_animation,
                                      node,
                                      node_index,
                                      geom,
                                      mesh,
                                      prim,
                                      prim_index,
                                      options))
      return 0;
  }

  return 1;
}

static int
akb_extract_node(AkbArena *arena,
                 AkbPrimitiveList *list,
                 AkbSceneNodeList *nodes,
                 AkDoc *doc,
                 AkbSharedDoc *doc_owner,
                 AkNode *node,
                 const AkbAnimationIndex *anim_index,
                 AkbPrimitiveReuseCache *reuse_cache,
                 const AkbCoordContext *coord,
                 const AkbLoadOptions *options,
                 int32_t parent_index) {
  AkNode *child;
  AkNode *inst_node;
  AkGeometry *geom;
  AkInstanceGeometry *geometry_inst;
  AkInstanceGeometry *next_geometry;
  AkInstanceGeometry *saved_geometry;
  AkInstanceNode *node_ref;
  AkbAnimation *animation;
  AkbAnimation *morph_animation;
  int32_t node_index;
  int ok;

  if (!node)
    return 1;

  if (!akb_extract_scene_node(nodes,
                              doc,
                              doc_owner,
                              node,
                              anim_index,
                              coord,
                              parent_index,
                              &node_index))
    return 0;

  if (node->geometry) {
    saved_geometry = node->geometry;
    for (geometry_inst = saved_geometry; geometry_inst; geometry_inst = next_geometry) {
      next_geometry = (AkInstanceGeometry *)geometry_inst->base.next;
      node->geometry = geometry_inst;

      animation = akb_animation_retain(nodes->items[node_index].animation);
      morph_animation = NULL;
      ok = 1;
      if (geometry_inst->morpher
          && ((anim_index && anim_index->count)
              || (!anim_index && doc && doc->lib.animations.first))) {
        morph_animation = akb_morph_animation_new(doc,
                                                  doc_owner,
                                                  anim_index,
                                                  geometry_inst->morpher,
                                                  coord,
                                                  &ok);
      }
      if (!ok) {
        node->geometry = saved_geometry;
        akb_animation_release(animation);
        akb_animation_release(morph_animation);
        return 0;
      }

      geom = (AkGeometry *)ak_instanceObject(&geometry_inst->base);
      if (!akb_extract_mesh(arena,
                            list,
                            nodes,
                            doc,
                            doc_owner,
                            anim_index,
                            reuse_cache,
                            animation,
                            morph_animation,
                            node,
                            node_index,
                            geom,
                            options)) {
        node->geometry = saved_geometry;
        akb_animation_release(animation);
        akb_animation_release(morph_animation);
        return 0;
      }
      akb_animation_release(animation);
      akb_animation_release(morph_animation);
    }
    node->geometry = saved_geometry;
  }

  for (child = node->chld; child; child = child->next) {
    if (!akb_extract_node(arena, list, nodes, doc, doc_owner, child, anim_index, reuse_cache, coord, options, node_index))
      return 0;
  }

  for (node_ref = node->node; node_ref; node_ref = node_ref->next) {
    inst_node = ak_instanceNodeTarget(node_ref);
    if (!inst_node || inst_node == node)
      continue;
    if (!akb_extract_node(arena, list, nodes, doc, doc_owner, inst_node, anim_index, reuse_cache, coord, options, node_index))
      return 0;
  }

  return 1;
}

static AkScene *
akb_default_scene(AkDoc *doc) {
  if (!doc || !doc->scene)
    return NULL;
  return doc->scene;
}

static AkScene *
akb_scene_by_index(AkDoc *doc, int32_t scene_index) {
  AkScene *scene;
  int32_t index;

  if (!doc || scene_index < 0 || !doc->lib.scenes.first)
    return NULL;

  for (scene = doc->lib.scenes.first, index = 0;
       scene;
       scene = scene->next, index++) {
    if (index == scene_index)
      return scene;
  }

  return NULL;
}

static AkScene *
akb_selected_scene(AkDoc *doc, const AkbLoadOptions *options) {
  AkScene *scene;

  scene = options ? akb_scene_by_index(doc, options->scene_index) : NULL;
  return scene ? scene : akb_default_scene(doc);
}

typedef struct AkbSceneEstimate {
  size_t nodes;
  size_t primitives;
} AkbSceneEstimate;

static size_t
akb_count_geometry_primitives(AkGeometry *geom, const AkbLoadOptions *options) {
  AkObject *gdata;
  AkMesh *mesh;
  AkMeshPrimitive *prim;
  size_t count = 0;

  if (!geom || !(gdata = geom->gdata) || gdata->type != AKB_GEOMETRY_MESH)
    return 0;

  mesh = (AkMesh *)ak_objGet(gdata);
  if (!mesh)
    return 0;

  for (prim = mesh->primitive; prim; prim = prim->next) {
    if (akb_primitive_supported(prim, options))
      count++;
  }

  return count;
}

static void
akb_estimate_node(AkNode *node, const AkbLoadOptions *options, AkbSceneEstimate *estimate) {
  AkNode *child;
  AkNode *inst_node;
  AkInstanceNode *node_ref;
  AkInstanceGeometry *geometry_inst;
  AkGeometry *geom;

  if (!node || !estimate)
    return;

  estimate->nodes++;
  if (node->geometry) {
    for (geometry_inst = node->geometry;
         geometry_inst;
         geometry_inst = (AkInstanceGeometry *)geometry_inst->base.next) {
      geom = (AkGeometry *)ak_instanceObject(&geometry_inst->base);
      estimate->primitives += akb_count_geometry_primitives(geom, options);
    }
  }

  for (child = node->chld; child; child = child->next)
    akb_estimate_node(child, options, estimate);

  for (node_ref = node->node; node_ref; node_ref = node_ref->next) {
    inst_node = ak_instanceNodeTarget(node_ref);
    if (!inst_node || inst_node == node)
      continue;
    akb_estimate_node(inst_node, options, estimate);
  }
}

static AkbSceneEstimate
akb_estimate_scene(AkDoc *doc, const AkbLoadOptions *options) {
  AkbSceneEstimate estimate = {0};
  AkScene *scene;

  scene = akb_selected_scene(doc, options);
  if (!scene || !scene->node)
    return estimate;

  akb_estimate_node(scene->node, options, &estimate);

  return estimate;
}

static size_t
akb_estimate_library_primitives(AkDoc *doc, const AkbLoadOptions *options) {
  AkGeometry *geom;
  size_t count = 0;

  if (!doc)
    return 0;

  for (geom = doc->lib.geometries.first; geom; geom = geom->next)
    count += akb_count_geometry_primitives(geom, options);

  return count;
}

static int
akb_extract_scene(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  const AkbAnimationIndex *anim_index,
                  AkbArena *arena,
                  AkbPrimitiveList *list,
                  AkbSceneNodeList *nodes,
                  const AkbCoordContext *coord,
                  const AkbLoadOptions *options,
                  size_t *reuse_hits) {
  AkbPrimitiveReuseCache reuse_cache = {0};
  AkScene *scene;
  int ok = 1;

  if (!doc)
    return 1;

  scene = akb_selected_scene(doc, options);
  if (!scene || !scene->node)
    return 1;

  if (!akb_extract_node(arena, list, nodes, doc, doc_owner, scene->node, anim_index, &reuse_cache, coord, options, -1))
    ok = 0;

  if (reuse_hits)
    *reuse_hits = reuse_cache.hits;
  akb_primitive_reuse_cache_free(&reuse_cache);
  return ok;
}

static int
akb_extract_doc(AkDoc *doc,
                AkbSharedDoc *doc_owner,
                AkbImport *import,
                const AkbLoadOptions *options) {
  AkbCoordContext coord;
  AkbAnimationIndex anim_index;
  AkbSceneEstimate estimate;
  AkbLoadOptions runtime_options;
  AkGeometry *geom;
  size_t fallback_estimate;
  size_t skin_count;
  size_t reuse_hits = 0;
  double total_started_at = 0.0;
  double phase_started_at = 0.0;
  double coord_ms = 0.0;
  double anim_index_ms = 0.0;
  double scene_ms = 0.0;
  double resolve_skin_ms = 0.0;
  double pose_anim_ms = 0.0;
  double fallback_mesh_ms = 0.0;
  double set_coord_ms = 0.0;
  int profile;

  runtime_options = *options;
  profile = akb_profile_enabled();
  if (profile)
    total_started_at = phase_started_at = akb_now_ms();

  akb_prepare_blender_coords(doc, &coord, &runtime_options);
  if (profile) {
    coord_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  if (!akb_animation_index_build(&anim_index, doc))
    return 0;
  if (profile) {
    anim_index_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  estimate = akb_estimate_scene(doc, &runtime_options);
  if (estimate.primitives >= AKB_LARGE_SCENE_PRIMITIVE_THRESHOLD) {
    runtime_options.build_triangle_edges = 0;
  }
  if ((estimate.primitives && !akb_list_reserve(&import->primitives, estimate.primitives))
      || (estimate.nodes && !akb_node_list_reserve(&import->nodes, estimate.nodes))) {
    akb_animation_index_free(&anim_index);
    return 0;
  }

  if (!akb_extract_scene(doc,
                         doc_owner,
                         &anim_index,
                         &import->arena,
                         &import->primitives,
                         &import->nodes,
                         &coord,
                         &runtime_options,
                         &reuse_hits)) {
    akb_animation_index_free(&anim_index);
    return 0;
  }
  if (profile) {
    scene_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  skin_count = akb_list_count_skin_primitives(&import->primitives);
  if (skin_count) {
    akb_resolve_skin_joint_nodes(&import->primitives, &import->nodes);
    if (profile) {
      resolve_skin_ms = akb_now_ms() - phase_started_at;
      phase_started_at = akb_now_ms();
    }
    akb_build_skin_pose_animations(&import->primitives, &import->nodes);
    if (profile) {
      pose_anim_ms = akb_now_ms() - phase_started_at;
      phase_started_at = akb_now_ms();
    }
  }

  if (import->primitives.count > 0) {
    akb_list_set_coord_matrix(&import->primitives, &coord, skin_count > 0);
    if (profile) {
      set_coord_ms = akb_now_ms() - phase_started_at;
      akb_profile_log("extract_doc nodes=%zu primitives=%zu anim_channels=%zu reuse_hits=%zu coord=%.3fms anim_index=%.3fms scene=%.3fms resolve_skin=%.3fms pose_anim=%.3fms fallback_mesh=%.3fms set_coord=%.3fms total=%.3fms",
                      import->nodes.count,
                      import->primitives.count,
                      anim_index.count,
                      reuse_hits,
                      coord_ms,
                      anim_index_ms,
                      scene_ms,
                      resolve_skin_ms,
                      pose_anim_ms,
                      fallback_mesh_ms,
                      set_coord_ms,
                      akb_now_ms() - total_started_at);
    }
    akb_animation_index_free(&anim_index);
    return 1;
  }

  if (profile)
    phase_started_at = akb_now_ms();
  fallback_estimate = akb_estimate_library_primitives(doc, &runtime_options);
  if (fallback_estimate >= AKB_LARGE_SCENE_PRIMITIVE_THRESHOLD) {
    runtime_options.build_triangle_edges = 0;
  }
  if (fallback_estimate && !akb_list_reserve(&import->primitives, fallback_estimate)) {
    akb_animation_index_free(&anim_index);
    return 0;
  }
  for (geom = doc->lib.geometries.first; geom; geom = geom->next) {
    if (!akb_extract_mesh(&import->arena,
                          &import->primitives,
                          &import->nodes,
                          doc,
                          doc_owner,
                          &anim_index,
                          NULL,
                          NULL,
                          NULL,
                          NULL,
                          -1,
                          geom,
                          &runtime_options)) {
      akb_animation_index_free(&anim_index);
      return 0;
    }
  }
  if (profile) {
    fallback_mesh_ms = akb_now_ms() - phase_started_at;
    phase_started_at = akb_now_ms();
  }

  akb_list_set_coord_matrix(&import->primitives, &coord, 1);
  if (profile) {
    set_coord_ms = akb_now_ms() - phase_started_at;
    akb_profile_log("extract_doc nodes=%zu primitives=%zu anim_channels=%zu reuse_hits=%zu coord=%.3fms anim_index=%.3fms scene=%.3fms resolve_skin=%.3fms pose_anim=%.3fms fallback_mesh=%.3fms set_coord=%.3fms total=%.3fms",
                    import->nodes.count,
                    import->primitives.count,
                    anim_index.count,
                    reuse_hits,
                    coord_ms,
                    anim_index_ms,
                    scene_ms,
                    resolve_skin_ms,
                    pose_anim_ms,
                    fallback_mesh_ms,
                    set_coord_ms,
                    akb_now_ms() - total_started_at);
  }
  akb_animation_index_free(&anim_index);
  return 1;
}
