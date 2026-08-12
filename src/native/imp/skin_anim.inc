static AkMorphInspectMorphable *
akb_morphable_at(AkMorphInspectTargetView *view, uint32_t index) {
  AkMorphInspectMorphable *morphable;
  uint32_t i;

  morphable = view ? view->morphable : NULL;
  for (i = 0; morphable && i < index; i++)
    morphable = morphable->next;
  return morphable;
}

static AkInput *
akb_morph_position_input(AkMorphInspectMorphable *morphable) {
  AkMorphInspectInput *input;

  for (input = morphable ? morphable->input : NULL; input; input = input->next) {
    if (input->input && input->input->semantic == AK_INPUT_POSITION)
      return input->input;
  }

  return NULL;
}

static int
akb_float3_bytes(uint32_t count, size_t *bytes) {
  if (!bytes || (size_t)count > SIZE_MAX / (3u * sizeof(float)))
    return 0;
  *bytes = (size_t)count * 3u * sizeof(float);
  return 1;
}

static float
akb_morph_initial_weight(AkInstanceMorph *morpher, AkMesh *mesh, uint32_t index) {
  AkMorph *morph;

  if (!morpher || !(morph = morpher->morph))
    return 0.0f;
  if (morpher->overrideWeights && index < morpher->overrideWeights->count)
    return morpher->overrideWeights->items[index];
  if (morph->defaultWeights && index < morph->defaultWeights->count)
    return morph->defaultWeights->items[index];
  if (mesh && mesh->weights && index < mesh->weights->count)
    return mesh->weights->items[index];
  return 0.0f;
}

static int
akb_morph_is_relative(AkMorph *morph) {
  return morph && morph->method == AK_MORPH_METHOD_RELATIVE;
}

static int
akb_morph_copy_positions(AkbMorphTarget *target,
                         const float *base_positions,
                         uint32_t base_count,
                         AkInput *position,
                         int relative) {
  float *source;
  float *dest;
  uint32_t source_count = 0;
  size_t element_count;
  size_t bytes;
  size_t i;
  uint8_t source_borrowed;

  if (!target || !base_positions || !position || !position->accessor)
    return 0;

  source = akb_accessor_float_borrow(position->accessor, 3, &source_count);
  if (source) {
    source_borrowed = 1;
  } else {
    source = akb_accessor_float_copy(position->accessor, 3, &source_count);
    source_borrowed = 0;
  }

  if (!source || source_count != base_count) {
    if (!source_borrowed)
      free(source);
    return 0;
  }

  if (!akb_float3_bytes(base_count, &bytes)) {
    if (!source_borrowed)
      free(source);
    return 0;
  }
  element_count = (size_t)base_count * 3u;
  dest = (float *)malloc(bytes);
  if (!dest) {
    if (!source_borrowed)
      free(source);
    return 0;
  }

  if (relative) {
    for (i = 0; i < element_count; i++)
      dest[i] = base_positions[i] + source[i];
  } else {
    memcpy(dest, source, bytes);
  }

  if (!source_borrowed)
    free(source);

  target->positions = dest;
  target->vertex_count = base_count;
  return 1;
}

static int
akb_extract_morph_targets(AkbPrimitive *out,
                          AkGeometry *geom,
                          AkMesh *mesh,
                          AkMeshPrimitive *prim,
                          uint32_t prim_index,
                          AkInstanceMorph *morpher) {
  AkInputSemantic desired[1] = {AK_INPUT_POSITION};
  AkMorph *morph;
  AkMorphInspectView *view;
  AkMorphInspectTargetView *target_view;
  AkMorphInspectMorphable *morphable;
  AkInput *position;
  AkbMorphTarget *targets;
  uint32_t target_index;
  uint32_t cleanup_index;
  size_t position_bytes;
  const char *target_name;

  (void)prim;

  if (!out || !geom || !mesh || !morpher || !(morph = morpher->morph)
      || !morph->targetCount || !out->vertices || !out->vertex_count)
    return 1;
  if (!akb_float3_bytes(out->vertex_count, &position_bytes))
    return 0;

  out->morph_presets = morph->presets;
  out->morph_preset_count = morph->presetCount;

  view = morph->inspectResult;
  if (!view) {
    if (ak_morphInspect(geom, morph, desired, 1, false, true) != AK_OK)
      return 1;
    view = morph->inspectResult;
  }
  if (!view || !view->targets)
    return 1;

  targets = (AkbMorphTarget *)calloc(morph->targetCount, sizeof(*targets));
  if (!targets)
    return 0;

  target_index = 0;
  for (target_view = view->targets;
       target_view && target_index < morph->targetCount;
       target_view = target_view->next, target_index++) {
    morphable = akb_morphable_at(target_view, prim_index);
    position = akb_morph_position_input(morphable);
    if (!position
        || !akb_morph_copy_positions(&targets[target_index],
                                     out->vertices,
                                     out->vertex_count,
                                     position,
                                     akb_morph_is_relative(morph))) {
      /* Keep morph slot indices stable even when one target has no POSITION
       * input for this primitive. Blender needs one shape key per authored
       * weight slot, so materialize a zero-delta placeholder from the basis. */
      targets[target_index].positions = (float *)malloc(
        position_bytes);
      if (!targets[target_index].positions) {
        for (cleanup_index = 0; cleanup_index < morph->targetCount; cleanup_index++)
          free(targets[cleanup_index].positions);
        free(targets);
        return 0;
      }
      memcpy(targets[target_index].positions,
             out->vertices,
             position_bytes);
      targets[target_index].vertex_count = out->vertex_count;
    }

    target_name = morph->targetNames && target_index < morph->targetCount
                  ? morph->targetNames[target_index]
                  : NULL;
    if (target_name && target_name[0])
      snprintf(targets[target_index].name, sizeof(targets[target_index].name), "%s", target_name);
    else
      snprintf(targets[target_index].name, sizeof(targets[target_index].name), "AssetKitMorph_%u", target_index);

    targets[target_index].weight = akb_morph_initial_weight(morpher, mesh, target_index);
  }

  if (target_index != morph->targetCount) {
    for (cleanup_index = 0; cleanup_index < morph->targetCount; cleanup_index++)
      free(targets[cleanup_index].positions);
    free(targets);
    return 1;
  }

  out->morph_targets = targets;
  out->morph_target_count = morph->targetCount;
  return 1;
}

static size_t
akb_scene_node_hash(const AkNode *source) {
  uintptr_t value = (uintptr_t)source;

  value ^= value >> 33;
  value *= (uintptr_t)UINT64_C(0xff51afd7ed558ccd);
  value ^= value >> 33;
  return (size_t)value;
}

static void
akb_scene_node_index_insert(AkbSceneNodeIndexEntry *entries,
                            size_t capacity,
                            AkNode *source,
                            int32_t node_index) {
  size_t index;
  size_t mask;

  if (!entries || !capacity || !source)
    return;

  mask = capacity - 1;
  index = akb_scene_node_hash(source) & mask;
  while (entries[index].source) {
    /* Preserve the first occurrence, matching the former linear lookup. */
    if (entries[index].source == source)
      return;
    index = (index + 1) & mask;
  }
  entries[index].source = source;
  entries[index].index = node_index;
}

static int
akb_scene_node_index_update(AkbSceneNodeList *nodes) {
  AkbSceneNodeIndexEntry *entries;
  size_t capacity;
  size_t i;

  if (!nodes || nodes->indexed_count == nodes->count)
    return nodes && nodes->index_entries;
  if (nodes->count > (size_t)INT32_MAX)
    return 0;

  capacity = nodes->index_capacity;
  if (!capacity || nodes->count > capacity / 2) {
    capacity = 64;
    if (nodes->count > SIZE_MAX / 2)
      return 0;
    while (capacity < nodes->count * 2) {
      if (capacity > SIZE_MAX / 2)
        return 0;
      capacity *= 2;
    }

    entries = (AkbSceneNodeIndexEntry *)calloc(capacity, sizeof(*entries));
    if (!entries)
      return 0;
    for (i = 0; i < nodes->count; i++)
      akb_scene_node_index_insert(entries,
                                  capacity,
                                  nodes->items[i].source,
                                  (int32_t)i);
    free(nodes->index_entries);
    nodes->index_entries = entries;
    nodes->index_capacity = capacity;
    nodes->indexed_count = nodes->count;
    return 1;
  }

  for (i = nodes->indexed_count; i < nodes->count; i++)
    akb_scene_node_index_insert(nodes->index_entries,
                                capacity,
                                nodes->items[i].source,
                                (int32_t)i);
  nodes->indexed_count = nodes->count;
  return 1;
}

static int32_t
akb_scene_node_pointer_index_for(AkbSceneNodeList *nodes, AkNode *node) {
  size_t index;
  size_t mask;

  if (!nodes || !node || !akb_scene_node_index_update(nodes))
    return -1;

  mask = nodes->index_capacity - 1;
  index = akb_scene_node_hash(node) & mask;
  while (nodes->index_entries[index].source) {
    if (nodes->index_entries[index].source == node)
      return nodes->index_entries[index].index;
    index = (index + 1) & mask;
  }
  return -1;
}

static int32_t
akb_scene_node_index_for(AkbSceneNodeList *nodes, AkNode *node) {
  const char *target_id;
  const char *source_id;
  int32_t pointer_index;
  size_t i;

  if (!nodes || !node)
    return -1;

  pointer_index = akb_scene_node_pointer_index_for(nodes, node);
  if (pointer_index >= 0)
    return pointer_index;

  /* Retain the ID fallback for loaders that reconstruct equivalent nodes. */
  target_id = (const char *)ak_mem_getId(node);
  for (i = 0; i < nodes->count; i++) {
    if (!nodes->items[i].source)
      continue;
    source_id = (const char *)ak_mem_getId(nodes->items[i].source);
    if (source_id && target_id && strcmp(source_id, target_id) == 0)
      return (int32_t)i;
  }

  return -1;
}

static uint32_t
akb_skin_joint_width(AkSkin *skin) {
  uint32_t width;

  width = skin && skin->nMaxJoints
          ? skin->nMaxJoints
          : AKB_SKIN_DEFAULT_JOINTS_PER_VERTEX;
  if (width > AKB_SKIN_MAX_JOINTS_PER_VERTEX)
    return AKB_SKIN_MAX_JOINTS_PER_VERTEX;
  return width;
}

static int
akb_node_is_skin_joint(AkNode *node, AkNode **joints, size_t count) {
  size_t i;

  if (!node || !joints)
    return 0;

  for (i = 0; i < count; i++) {
    if (joints[i] == node)
      return 1;
  }

  return 0;
}

static AkNode *
akb_skin_armature_root(AkNode *root, AkNode **joints, size_t count) {
  if (root) {
    if (akb_node_is_skin_joint(root, joints, count) && root->parent)
      return root->parent;
    return root;
  }

  if (joints && count && joints[0]) {
    if (joints[0]->parent)
      return joints[0]->parent;
    return joints[0];
  }

  return NULL;
}

static int
akb_extract_skin(AkbArena *arena,
                 AkbPrimitive *out,
                 AkbSceneNodeList *nodes,
                 AkMeshPrimitive *prim,
                 uint32_t prim_index,
                 AkInstanceSkin *skinner) {
  AkSkin *skin;
  AkNode *root;
  AkNode **joints;
  AkNode **joint_sources;
  uint16_t *joint_indices;
  int32_t *joint_nodes;
  float *weights;
  float *inverse_bind_matrices;
  size_t filled_count;
  uint32_t joint_width;
  size_t i;
  uint8_t arena_joint_nodes = 0;
  uint8_t arena_inverse_bind_matrices = 0;
  uint8_t arena_joint_sources = 0;

  if (!out || !prim || !skinner || !(skin = skinner->skin)
      || !skin->nJoints || !out->vertex_count)
    return 1;

  joint_width = akb_skin_joint_width(skin);
  joint_indices = (uint16_t *)calloc((size_t)out->vertex_count
                                     * joint_width,
                                     sizeof(*joint_indices));
  weights = (float *)calloc((size_t)out->vertex_count
                            * joint_width,
                            sizeof(*weights));
  if (!joint_indices || !weights) {
    free(joint_indices);
    free(weights);
    return 0;
  }

  filled_count = ak_skinFillWeights(skin,
                                    prim,
                                    prim_index,
                                    joint_width,
                                    joint_indices,
                                    weights);
  if (!filled_count) {
    free(joint_indices);
    free(weights);
    return 1;
  }

  joint_nodes = (int32_t *)akb_owned_alloc(arena,
                                           (size_t)skin->nJoints * sizeof(*joint_nodes),
                                           sizeof(*joint_nodes),
                                           &arena_joint_nodes);
  joint_sources = (AkNode **)akb_owned_alloc(arena,
                                             (size_t)skin->nJoints * sizeof(*joint_sources),
                                             sizeof(void *),
                                             &arena_joint_sources);
  if (!joint_nodes || !joint_sources) {
    if (!arena_joint_sources)
      free(joint_sources);
    if (!arena_joint_nodes)
      free(joint_nodes);
    free(joint_indices);
    free(weights);
    return 0;
  }

  joints = skinner->overrideJoints ? skinner->overrideJoints : skin->joints;
  for (i = 0; i < skin->nJoints; i++) {
    joint_sources[i] = joints ? joints[i] : NULL;
    joint_nodes[i] = joint_sources[i]
                     ? akb_scene_node_index_for(nodes, joint_sources[i])
                     : -1;
  }

  inverse_bind_matrices = NULL;
  if (skin->invBindPoses) {
    inverse_bind_matrices = (float *)akb_owned_alloc(arena,
                                                     (size_t)skin->nJoints
                                                     * 16
                                                     * sizeof(*inverse_bind_matrices),
                                                     sizeof(*inverse_bind_matrices),
                                                     &arena_inverse_bind_matrices);
    if (!inverse_bind_matrices) {
      if (!arena_joint_nodes)
        free(joint_nodes);
      if (!arena_joint_sources)
        free(joint_sources);
      free(joint_indices);
      free(weights);
      return 0;
    }
    memcpy(inverse_bind_matrices,
           skin->invBindPoses,
           (size_t)skin->nJoints * 16 * sizeof(*inverse_bind_matrices));
  }

  out->skin_joints = joint_indices;
  out->skin_weights = weights;
  out->skin_joint_nodes = joint_nodes;
  out->skin_joint_sources = joint_sources;
  out->skin_inverse_bind_matrices = inverse_bind_matrices;
  out->arena_skin_joint_nodes = arena_joint_nodes;
  out->arena_skin_joint_sources = arena_joint_sources;
  out->arena_skin_inverse_bind_matrices = arena_inverse_bind_matrices;
  memcpy(out->skin_bind_shape_matrix,
         skin->bindShapeMatrix,
         sizeof(out->skin_bind_shape_matrix));
  root = akb_skin_armature_root(
    skinner->overrideSkeleton ? skinner->overrideSkeleton : skin->skeleton,
    joint_sources,
    skin->nJoints);
  out->skin_root_source = root;
  out->skin_root_node_index = akb_scene_node_index_for(nodes, root);
  out->skin_vertex_count = (uint32_t)filled_count;
  out->skin_joint_count = (uint32_t)skin->nJoints;
  out->skin_joint_width = joint_width;
  out->has_skin = 1;
  return 1;
}

static void
akb_node_world_matrix(AkNode *node, float out[16]) {
  if (!node) {
    glm_mat4_identity(AKB_MAT4(out));
    return;
  }

  ak_transformCombineWorld(node, out);
}

static int
akb_ensure_owned_vertices(AkbPrimitive *out) {
  float *copy;
  size_t bytes;

  if (!out || !out->vertices || !out->vertex_count || !out->borrowed_vertices)
    return 1;

  if (!akb_float3_bytes(out->vertex_count, &bytes))
    return 0;
  copy = (float *)malloc(bytes);
  if (!copy)
    return 0;

  memcpy(copy, out->vertices, bytes);
  out->vertices = copy;
  out->borrowed_vertices = 0;
  out->zero_copy_flags &= (uint8_t)~1u;
  return 1;
}

static int
akb_skin_vertex_rigid_joint(const AkbPrimitive *out,
                            uint32_t vertex_index,
                            uint16_t *joint_out) {
  size_t base;
  uint16_t joint;
  uint32_t slot;
  int found;

  if (!out || !joint_out || !out->skin_joints || !out->skin_weights
      || vertex_index >= out->vertex_count || !out->skin_joint_width)
    return 0;

  base = (size_t)vertex_index * out->skin_joint_width;
  joint = 0;
  found = 0;
  for (slot = 0; slot < out->skin_joint_width; slot++) {
    if (out->skin_weights[base + slot] <= 0.0f)
      continue;
    if (found)
      return 0;
    joint = out->skin_joints[base + slot];
    if ((uint32_t)joint >= out->skin_joint_count)
      return 0;
    found = 1;
  }

  if (!found)
    return 0;

  *joint_out = joint;
  return 1;
}

static uint16_t *
akb_skin_rigid_vertex_joints(const AkbPrimitive *out) {
  uint16_t *vertex_joints;
  uint32_t vertex_index;

  if (!out || !out->vertex_count || !out->skin_joint_count)
    return NULL;

  vertex_joints = (uint16_t *)malloc((size_t)out->vertex_count * sizeof(*vertex_joints));
  if (!vertex_joints)
    return NULL;

  for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
    if (!akb_skin_vertex_rigid_joint(out, vertex_index, &vertex_joints[vertex_index])) {
      free(vertex_joints);
      return NULL;
    }
  }

  return vertex_joints;
}

static void
akb_skin_vertex_matrix(const AkbPrimitive *out,
                       const float *joint_mats,
                       uint32_t vertex_index,
                       float matrix[16]) {
  const float *joint_matrix;
  uint32_t slot, index;
  float weight, weight_sum;
  int has_matrix;

  weight_sum = 0.0f;
  has_matrix = 0;

  for (slot = 0; slot < out->skin_joint_width; slot++) {
    index = out->skin_joints[(size_t)vertex_index * out->skin_joint_width + slot];
    weight = out->skin_weights[(size_t)vertex_index * out->skin_joint_width + slot];
    if (weight <= 0.0f || index >= out->skin_joint_count)
      continue;

    joint_matrix = joint_mats + (size_t)index * 16;
    if (!has_matrix) {
      glm_vec4_scale(AKB_VEC4(joint_matrix),      weight, AKB_VEC4(matrix));
      glm_vec4_scale(AKB_VEC4(joint_matrix + 4),  weight, AKB_VEC4(matrix + 4));
      glm_vec4_scale(AKB_VEC4(joint_matrix + 8),  weight, AKB_VEC4(matrix + 8));
      glm_vec4_scale(AKB_VEC4(joint_matrix + 12), weight, AKB_VEC4(matrix + 12));
      has_matrix = 1;
    } else {
      glm_vec4_muladds(AKB_VEC4(joint_matrix),      weight, AKB_VEC4(matrix));
      glm_vec4_muladds(AKB_VEC4(joint_matrix + 4),  weight, AKB_VEC4(matrix + 4));
      glm_vec4_muladds(AKB_VEC4(joint_matrix + 8),  weight, AKB_VEC4(matrix + 8));
      glm_vec4_muladds(AKB_VEC4(joint_matrix + 12), weight, AKB_VEC4(matrix + 12));
    }
    weight_sum += weight;
  }

  if (weight_sum > 1.0e-8f) {
    weight = 1.0f / weight_sum;
    glm_vec4_scale(AKB_VEC4(matrix),      weight, AKB_VEC4(matrix));
    glm_vec4_scale(AKB_VEC4(matrix + 4),  weight, AKB_VEC4(matrix + 4));
    glm_vec4_scale(AKB_VEC4(matrix + 8),  weight, AKB_VEC4(matrix + 8));
    glm_vec4_scale(AKB_VEC4(matrix + 12), weight, AKB_VEC4(matrix + 12));
  } else {
    /* Blender leaves vertices without a valid group assignment unchanged. */
    glm_mat4_identity(AKB_MAT4(matrix));
  }
}

typedef enum AkbSkinBindPoseMatrixResult {
  AKB_SKIN_BIND_POSE_MATRIX_ERROR = 0,
  AKB_SKIN_BIND_POSE_MATRIX_OK,
  AKB_SKIN_BIND_POSE_MATRIX_SKIP
} AkbSkinBindPoseMatrixResult;

static int
akb_mat4_is_finite(const float matrix[16]) {
  uint32_t i;

  if (!matrix)
    return 0;

  for (i = 0; i < 16; i++)
    if (!isfinite(matrix[i]))
      return 0;

  return 1;
}

static int
akb_mat4_inverse_checked(const float matrix[16], float inverse[16]) {
  float determinant;

  if (!matrix || !inverse || !akb_mat4_is_finite(matrix))
    return 0;

  determinant = glm_mat4_det(AKB_MAT4(matrix));
  if (!isfinite(determinant) || determinant == 0.0f)
    return 0;

  glm_mat4_inv(AKB_MAT4(matrix), AKB_MAT4(inverse));
  return akb_mat4_is_finite(inverse);
}

static float
akb_mat4_linear_determinant(const float matrix[16]) {
  return matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
         + matrix[1] * (matrix[6] * matrix[8] - matrix[4] * matrix[10])
         + matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8]);
}

static void
akb_skin_transform_normal(const float matrix[16], float normal[3]) {
  float cofactor0[3], cofactor1[3], cofactor2[3];
  float transformed[3];
  float determinant;
  float length_squared;
  float x, y, z;

  if (!matrix || !normal)
    return;

  x = normal[0];
  y = normal[1];
  z = normal[2];

  /* The inverse-transpose is the cofactor matrix divided by det.  The
   * division can be omitted before normalization, except that a reflected
   * transform must retain the determinant's sign. */
  cofactor0[0] = matrix[5] * matrix[10] - matrix[6] * matrix[9];
  cofactor0[1] = matrix[6] * matrix[8]  - matrix[4] * matrix[10];
  cofactor0[2] = matrix[4] * matrix[9]  - matrix[5] * matrix[8];
  cofactor1[0] = matrix[9] * matrix[2]  - matrix[10] * matrix[1];
  cofactor1[1] = matrix[10] * matrix[0] - matrix[8] * matrix[2];
  cofactor1[2] = matrix[8] * matrix[1]  - matrix[9] * matrix[0];
  cofactor2[0] = matrix[1] * matrix[6]  - matrix[2] * matrix[5];
  cofactor2[1] = matrix[2] * matrix[4]  - matrix[0] * matrix[6];
  cofactor2[2] = matrix[0] * matrix[5]  - matrix[1] * matrix[4];
  determinant = akb_mat4_linear_determinant(matrix);

  if (isfinite(determinant) && determinant != 0.0f) {
    transformed[0] = cofactor0[0] * x + cofactor1[0] * y + cofactor2[0] * z;
    transformed[1] = cofactor0[1] * x + cofactor1[1] * y + cofactor2[1] * z;
    transformed[2] = cofactor0[2] * x + cofactor1[2] * y + cofactor2[2] * z;
    if (determinant < 0.0f)
      glm_vec3_negate(AKB_VEC3(transformed));
  } else {
    /* There is no defined normal transform for a singular matrix.  Keep the
     * previous tolerant linear behavior if it still produces a direction. */
    transformed[0] = matrix[0] * x + matrix[4] * y + matrix[8]  * z;
    transformed[1] = matrix[1] * x + matrix[5] * y + matrix[9]  * z;
    transformed[2] = matrix[2] * x + matrix[6] * y + matrix[10] * z;
  }

  length_squared = glm_vec3_norm2(AKB_VEC3(transformed));
  if (isfinite(length_squared) && length_squared > 0.0f)
    glm_vec3_copy(AKB_VEC3(transformed), AKB_VEC3(normal));
  glm_vec3_normalize(AKB_VEC3(normal));
}

static void
akb_skin_transform_tangent(const float matrix[16], float tangent[4]) {
  float determinant;

  if (!matrix || !tangent)
    return;

  glm_mat4_mulv3(AKB_MAT4(matrix), AKB_VEC3(tangent), 0.0f, AKB_VEC3(tangent));
  glm_vec3_normalize(AKB_VEC3(tangent));

  /* A reflected linear transform reverses the tangent frame's handedness. */
  determinant = akb_mat4_linear_determinant(matrix);
  if (isfinite(determinant) && determinant < 0.0f)
    tangent[3] = -tangent[3];
}

static AkbSkinBindPoseMatrixResult
akb_skin_bind_pose_joint_matrices(AkbPrimitive *out, float **joint_mats_out) {
  float *joint_mats;
  const float *inverse_bind;
  float root_world[16];
  float root_inv[16];
  float bind_world[16];
  float bind_arma[16];
  float bind_with_shape[16];
  float inverse_bind_check[16];
  float fallback_inverse_bind[16];
  uint32_t i;

  if (!out || !out->skin_joint_count || !joint_mats_out)
    return AKB_SKIN_BIND_POSE_MATRIX_ERROR;

  *joint_mats_out = NULL;

  akb_node_world_matrix(out->skin_root_source, root_world);
  if (!akb_mat4_inverse_checked(root_world, root_inv))
    return AKB_SKIN_BIND_POSE_MATRIX_SKIP;

  joint_mats = (float *)malloc((size_t)out->skin_joint_count * 16 * sizeof(*joint_mats));
  if (!joint_mats)
    return AKB_SKIN_BIND_POSE_MATRIX_ERROR;

  for (i = 0; i < out->skin_joint_count; i++) {
    if (out->skin_inverse_bind_matrices) {
      inverse_bind = out->skin_inverse_bind_matrices + (size_t)i * 16;
      if (!akb_mat4_inverse_checked(inverse_bind, inverse_bind_check)) {
        if (!out->skin_joint_sources || !out->skin_joint_sources[i]) {
          free(joint_mats);
          return AKB_SKIN_BIND_POSE_MATRIX_SKIP;
        }

        akb_node_world_matrix(out->skin_joint_sources[i], bind_world);
        if (!akb_mat4_inverse_checked(bind_world, fallback_inverse_bind)) {
          free(joint_mats);
          return AKB_SKIN_BIND_POSE_MATRIX_SKIP;
        }
        inverse_bind = fallback_inverse_bind;
      }

      if (out->skin_joint_sources && out->skin_joint_sources[i]) {
        akb_node_world_matrix(out->skin_joint_sources[i], bind_world);
        if (!akb_mat4_is_finite(bind_world)) {
          free(joint_mats);
          return AKB_SKIN_BIND_POSE_MATRIX_SKIP;
        }
      } else {
        glm_mat4_copy(AKB_MAT4(inverse_bind_check), AKB_MAT4(bind_world));
      }
      glm_mul(AKB_MAT4(root_inv), AKB_MAT4(bind_world), AKB_MAT4(bind_arma));
      glm_mul(AKB_MAT4(bind_arma),
              AKB_MAT4(inverse_bind),
              AKB_MAT4(joint_mats + (size_t)i * 16));
    } else {
      akb_node_world_matrix(out->skin_joint_sources ? out->skin_joint_sources[i] : NULL,
                            bind_world);
      glm_mul(AKB_MAT4(root_inv),
              AKB_MAT4(bind_world),
              AKB_MAT4(joint_mats + (size_t)i * 16));
    }

    /* COLLADA skins vertices as joint * inverse_bind * bind_shape * position. */
    glm_mul(AKB_MAT4(joint_mats + (size_t)i * 16),
            AKB_MAT4(out->skin_bind_shape_matrix),
            AKB_MAT4(bind_with_shape));
    glm_mat4_copy(AKB_MAT4(bind_with_shape),
                  AKB_MAT4(joint_mats + (size_t)i * 16));
    if (!akb_mat4_is_finite(joint_mats + (size_t)i * 16)) {
      free(joint_mats);
      return AKB_SKIN_BIND_POSE_MATRIX_SKIP;
    }
  }

  *joint_mats_out = joint_mats;
  return AKB_SKIN_BIND_POSE_MATRIX_OK;
}

static void
akb_skin_bind_pose_apply_loop_vectors(AkbPrimitive *out, const float *vertex_mats) {
  const float *matrix;
  float *vector;
  uint32_t loop_index;
  uint32_t vertex_index;

  if (!out || !vertex_mats || !out->indices)
    return;

  if (out->normals) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      matrix = vertex_mats + (size_t)vertex_index * 16;
      vector = out->normals + (size_t)loop_index * 3;
      akb_skin_transform_normal(matrix, vector);
    }
  }

  if (out->tangents) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      matrix = vertex_mats + (size_t)vertex_index * 16;
      vector = out->tangents + (size_t)loop_index * 4;
      akb_skin_transform_tangent(matrix, vector);
    }
  }
}

static void
akb_skin_bind_pose_apply_loop_vectors_rigid(AkbPrimitive *out,
                                            const float *joint_mats,
                                            const uint16_t *vertex_joints) {
  const float *matrix;
  float *vector;
  uint32_t loop_index;
  uint32_t vertex_index;

  if (!out || !joint_mats || !vertex_joints || !out->indices)
    return;

  if (out->normals) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      matrix = joint_mats + (size_t)vertex_joints[vertex_index] * 16;
      vector = out->normals + (size_t)loop_index * 3;
      akb_skin_transform_normal(matrix, vector);
    }
  }

  if (out->tangents) {
    for (loop_index = 0; loop_index < out->loop_count; loop_index++) {
      vertex_index = out->indices[loop_index];
      if (vertex_index >= out->vertex_count)
        continue;
      matrix = joint_mats + (size_t)vertex_joints[vertex_index] * 16;
      vector = out->tangents + (size_t)loop_index * 4;
      akb_skin_transform_tangent(matrix, vector);
    }
  }
}

static void
akb_skin_into_bind_pose_rigid(AkbPrimitive *out,
                              const float *joint_mats,
                              const uint16_t *vertex_joints) {
  AkbMorphTarget *target;
  const float *matrix;
  float *position;
  uint32_t vertex_index;
  uint32_t target_index;

  for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
    matrix = joint_mats + (size_t)vertex_joints[vertex_index] * 16;
    position = out->vertices + (size_t)vertex_index * 3;
    glm_mat4_mulv3(AKB_MAT4(matrix), AKB_VEC3(position), 1.0f, AKB_VEC3(position));
  }

  for (target_index = 0; target_index < out->morph_target_count; target_index++) {
    target = &out->morph_targets[target_index];
    if (!target->positions || target->vertex_count != out->vertex_count)
      continue;
    for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
      matrix = joint_mats + (size_t)vertex_joints[vertex_index] * 16;
      position = target->positions + (size_t)vertex_index * 3;
      glm_mat4_mulv3(AKB_MAT4(matrix), AKB_VEC3(position), 1.0f, AKB_VEC3(position));
    }
  }

  akb_skin_bind_pose_apply_loop_vectors_rigid(out, joint_mats, vertex_joints);
  out->skin_mesh_in_bind_pose = 1;
}

static int
akb_skin_into_bind_pose(AkbPrimitive *out) {
  float *joint_mats;
  float *vertex_mats;
  const float *matrix;
  float *position;
  uint16_t *rigid_vertex_joints;
  AkbMorphTarget *target;
  AkbSkinBindPoseMatrixResult joint_matrix_result;
  uint32_t vertex_index;
  uint32_t target_index;

  if (!out || !out->has_skin)
    return 1;
  if (!out->skin_joints || !out->skin_weights || !out->skin_joint_count
      || !out->skin_joint_width || out->skin_vertex_count != out->vertex_count
      || !out->skin_inverse_bind_matrices || !out->skin_joint_sources
      || !out->skin_root_source)
    return 1;

  if (!akb_ensure_owned_vertices(out))
    return 0;
  joint_matrix_result = akb_skin_bind_pose_joint_matrices(out, &joint_mats);
  if (joint_matrix_result == AKB_SKIN_BIND_POSE_MATRIX_SKIP)
    return 1;
  if (joint_matrix_result != AKB_SKIN_BIND_POSE_MATRIX_OK)
    return 0;

  rigid_vertex_joints = akb_skin_rigid_vertex_joints(out);
  if (rigid_vertex_joints) {
    akb_skin_into_bind_pose_rigid(out, joint_mats, rigid_vertex_joints);
    free(rigid_vertex_joints);
    free(joint_mats);
    return 1;
  }

  vertex_mats = (float *)malloc((size_t)out->vertex_count * 16 * sizeof(*vertex_mats));
  if (!vertex_mats) {
    free(joint_mats);
    return 0;
  }

  for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
    akb_skin_vertex_matrix(out,
                           joint_mats,
                           vertex_index,
                           vertex_mats + (size_t)vertex_index * 16);
    matrix = vertex_mats + (size_t)vertex_index * 16;
    position = out->vertices + (size_t)vertex_index * 3;
    glm_mat4_mulv3(AKB_MAT4(matrix), AKB_VEC3(position), 1.0f, AKB_VEC3(position));
  }

  for (target_index = 0; target_index < out->morph_target_count; target_index++) {
    target = &out->morph_targets[target_index];
    if (!target->positions || target->vertex_count != out->vertex_count)
      continue;
    for (vertex_index = 0; vertex_index < out->vertex_count; vertex_index++) {
      matrix = vertex_mats + (size_t)vertex_index * 16;
      position = target->positions + (size_t)vertex_index * 3;
      glm_mat4_mulv3(AKB_MAT4(matrix), AKB_VEC3(position), 1.0f, AKB_VEC3(position));
    }
  }

  akb_skin_bind_pose_apply_loop_vectors(out, vertex_mats);

  out->skin_mesh_in_bind_pose = 1;
  free(vertex_mats);
  free(joint_mats);
  return 1;
}

static void
akb_resolve_skin_joint_nodes(AkbPrimitiveList *list, AkbSceneNodeList *nodes) {
  AkbPrimitive *prim;
  uint32_t i;
  size_t j;

  if (!list || !nodes)
    return;

  for (j = 0; j < list->count; j++) {
    prim = &list->items[j];
    if (!prim->has_skin || !prim->skin_joint_sources || !prim->skin_joint_nodes)
      continue;

    for (i = 0; i < prim->skin_joint_count; i++) {
      if (prim->skin_joint_nodes[i] >= 0)
        continue;
      prim->skin_joint_nodes[i] = akb_scene_node_index_for(nodes,
                                                           prim->skin_joint_sources[i]);
    }
    if (prim->skin_root_node_index < 0)
      prim->skin_root_node_index = akb_scene_node_index_for(nodes,
                                                            prim->skin_root_source);
  }
}

static size_t
akb_list_count_skin_primitives(const AkbPrimitiveList *list) {
  return list ? list->skin_count : 0;
}

static AkInput *
akb_anim_sampler_input(AkAnimSampler *sampler, AkInputSemantic semantic) {
  AkInput *input;

  if (!sampler)
    return NULL;

  if (semantic == AK_INPUT_INPUT && sampler->inputInput)
    return sampler->inputInput;
  if (semantic == AK_INPUT_OUTPUT && sampler->outputInput)
    return sampler->outputInput;

  for (input = sampler->input; input; input = input->next) {
    if (input->semantic == semantic)
      return input;
  }

  return NULL;
}

static int
akb_anim_target_kind(AkObject *target, uint32_t *width) {
  if (!target)
    return 0;

  switch ((AkTypeId)target->type) {
    case AKT_TRANSLATE:
      *width = 3;
      return AKB_ANIM_TRANSLATION;
    case AKT_QUATERNION:
      *width = 4;
      return AKB_ANIM_ROTATION_QUAT;
    case AKT_SCALE:
      *width = 3;
      return AKB_ANIM_SCALE;
    default:
      break;
  }

  return 0;
}

static int
akb_anim_binding_push(AkbAnimBinding *bindings,
                      int capacity,
                      int count,
                      void *target,
                      uint32_t kind,
                      uint32_t width) {
  if (!target || !kind || !width || count >= capacity)
    return count;
  bindings[count].target = target;
  bindings[count].kind = kind;
  bindings[count].width = width;
  return count + 1;
}

static int
akb_animation_push(AkbAnimation *animation, AkbAnimChannel *channel) {
  AkbAnimChannel *channels;
  size_t capacity;

  if (animation->count == animation->capacity) {
    capacity = animation->capacity ? animation->capacity * 2 : 8;
    channels = (AkbAnimChannel *)realloc(animation->channels,
                                         capacity * sizeof(*channels));
    if (!channels)
      return 0;
    animation->channels = channels;
    animation->capacity = capacity;
  }

  animation->channels[animation->count++] = *channel;
  memset(channel, 0, sizeof(*channel));
  return 1;
}

static void
akb_pose_basis_from_rest(const float rest[16],
                         float edit_translation[3],
                         versor edit_rotation_inv) {
  mat4 rotation_matrix = GLM_MAT4_IDENTITY_INIT;
  versor edit_rotation;
  float len;
  int col;
  int row;

  edit_translation[0] = rest[12];
  edit_translation[1] = rest[13];
  edit_translation[2] = rest[14];

  for (col = 0; col < 3; col++) {
    len = sqrtf(rest[col * 4] * rest[col * 4]
                + rest[col * 4 + 1] * rest[col * 4 + 1]
                + rest[col * 4 + 2] * rest[col * 4 + 2]);
    if (len <= 1.0e-8f)
      len = 1.0f;
    for (row = 0; row < 3; row++)
      rotation_matrix[col][row] = rest[col * 4 + row] / len;
  }

  glm_mat4_quat(rotation_matrix, edit_rotation);
  glm_quat_normalize(edit_rotation);
  glm_quat_inv(edit_rotation, edit_rotation_inv);
  glm_quat_normalize(edit_rotation_inv);
}

static void
akb_mat4_to_trs(const float m[16],
                float translation[3],
                versor rotation_xyzw,
                float scale[3]) {
  mat4 rotation_matrix;
  vec4 translation4;

  glm_decompose(AKB_MAT4(m), translation4, rotation_matrix, scale);
  translation[0] = translation4[0];
  translation[1] = translation4[1];
  translation[2] = translation4[2];

  glm_mat4_quat(rotation_matrix, rotation_xyzw);
}

static void
akb_pose_transform_translation(float *dst,
                               const float *src,
                               const float edit_translation[3],
                               const versor edit_rotation_inv) {
  vec3 relative;

  glm_vec3_sub(AKB_VEC3(src), AKB_VEC3(edit_translation), relative);
  glm_quat_rotatev(AKB_VERSOR(edit_rotation_inv), relative, AKB_VEC3(dst));
}

static void
akb_pose_transform_rotation(float *dst,
                            const float *src,
                            const versor edit_rotation_inv) {
  versor rotation;
  versor corrected;

  rotation[0] = src[1];
  rotation[1] = src[2];
  rotation[2] = src[3];
  rotation[3] = src[0];
  glm_quat_normalize(rotation);
  glm_quat_mul(AKB_VERSOR(edit_rotation_inv), rotation, corrected);

  dst[0] = corrected[3];
  dst[1] = corrected[0];
  dst[2] = corrected[1];
  dst[3] = corrected[2];
}

static int
akb_pose_channel_is_default(const AkbAnimChannel *channel) {
  const float *values;
  uint32_t i;

  if (!channel || channel->is_partial || !channel->values || !channel->count)
    return 0;

  values = channel->values;
  if (channel->target == AKB_ANIM_TRANSLATION && channel->value_width >= 3) {
    for (i = 0; i < channel->count; i++) {
      const float *sample = values + (size_t)i * channel->value_width;
      if (fabsf(sample[0]) > 1.0e-6f
          || fabsf(sample[1]) > 1.0e-6f
          || fabsf(sample[2]) > 1.0e-6f)
        return 0;
    }
    return 1;
  }

  if (channel->target == AKB_ANIM_ROTATION_QUAT && channel->value_width >= 4) {
    for (i = 0; i < channel->count; i++) {
      const float *sample = values + (size_t)i * channel->value_width;
      if (fabsf(sample[0] - 1.0f) > 1.0e-6f
          || fabsf(sample[1]) > 1.0e-6f
          || fabsf(sample[2]) > 1.0e-6f
          || fabsf(sample[3]) > 1.0e-6f)
        return 0;
    }
    return 1;
  }

  if (channel->target == AKB_ANIM_SCALE && channel->value_width >= 3) {
    for (i = 0; i < channel->count; i++) {
      const float *sample = values + (size_t)i * channel->value_width;
      if (fabsf(sample[0] - 1.0f) > 1.0e-6f
          || fabsf(sample[1] - 1.0f) > 1.0e-6f
          || fabsf(sample[2] - 1.0f) > 1.0e-6f)
        return 0;
    }
    return 1;
  }

  return 0;
}

static int
akb_pose_channel_clone(AkbAnimChannel *dst,
                       const AkbAnimChannel *src,
                       const float edit_translation[3],
                       const versor edit_rotation_inv) {
  size_t value_count;
  size_t value_bytes;
  uint32_t i;
  int pose_ready;
  int transform_values;

  if (!dst || !src)
    return 0;

  memset(dst, 0, sizeof(*dst));
  dst->times = src->times;
  dst->clip_name = src->clip_name;
  dst->count = src->count;
  dst->value_width = src->value_width;
  dst->target = src->target;
  dst->target_offset = src->target_offset;
  dst->clip_index = src->clip_index;
  dst->interpolation = src->interpolation;
  dst->is_partial = src->is_partial;
  dst->borrowed_times = 1;

  pose_ready = !src->is_partial
               && src->values
               && src->count
               && ((src->target == AKB_ANIM_TRANSLATION && src->value_width >= 3)
                   || (src->target == AKB_ANIM_ROTATION_QUAT && src->value_width >= 4)
                   || (src->target == AKB_ANIM_SCALE && src->value_width >= 3));
  transform_values = pose_ready
                     && (src->target == AKB_ANIM_TRANSLATION
                         || src->target == AKB_ANIM_ROTATION_QUAT);

  value_count = (size_t)src->count * src->value_width;
  value_bytes = value_count * sizeof(float);
  if (value_bytes && src->values) {
    if (transform_values) {
      dst->values = (float *)malloc(value_bytes);
      if (!dst->values)
        return 0;
      if ((src->target == AKB_ANIM_TRANSLATION && src->value_width != 3)
          || (src->target == AKB_ANIM_ROTATION_QUAT && src->value_width != 4))
        memcpy(dst->values, src->values, value_bytes);
    } else {
      dst->values = src->values;
      dst->borrowed_values = 1;
    }
  }

  if (value_bytes && src->in_tangents) {
    dst->in_tangents = src->in_tangents;
    dst->borrowed_in_tangents = 1;
  }
  if (value_bytes && src->out_tangents) {
    dst->out_tangents = src->out_tangents;
    dst->borrowed_out_tangents = 1;
  }

  if (!transform_values) {
    dst->pose_ready = pose_ready ? 1 : 0;
    return 1;
  }

  for (i = 0; i < src->count; i++) {
    float *sample = dst->values + (size_t)i * dst->value_width;
    const float *source = src->values + (size_t)i * src->value_width;

    if (src->target == AKB_ANIM_TRANSLATION)
      akb_pose_transform_translation(sample,
                                     source,
                                     edit_translation,
                                     edit_rotation_inv);
    else if (src->target == AKB_ANIM_ROTATION_QUAT)
      akb_pose_transform_rotation(sample,
                                  source,
                                  edit_rotation_inv);
  }

  dst->pose_ready = 1;
  return 1;
}

static AkbAnimation *
akb_animation_new_pose_for_joint(AkbAnimation *source,
                                 const float rest[16]) {
  AkbAnimation *animation;
  AkbAnimChannel channel;
  float edit_translation[3];
  versor edit_rotation_inv;
  size_t i;

  if (!source || !source->count)
    return NULL;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation)
    return NULL;

  animation->refcount = 1;
  animation->doc_owner = source->doc_owner;
  akb_shared_doc_retain(animation->doc_owner);
  akb_pose_basis_from_rest(rest, edit_translation, edit_rotation_inv);

  for (i = 0; i < source->count; i++) {
    if (!akb_pose_channel_clone(&channel,
                                &source->channels[i],
                                edit_translation,
                                edit_rotation_inv)) {
      akb_animation_release(animation);
      return NULL;
    }
    if (akb_pose_channel_is_default(&channel)) {
      akb_anim_channel_free(&channel);
      continue;
    }
    if (!akb_animation_push(animation, &channel)) {
      akb_anim_channel_free(&channel);
      akb_animation_release(animation);
      return NULL;
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static int
akb_skin_pose_is_same_skin(const AkbPrimitive *a, const AkbPrimitive *b) {
  uint32_t i;

  if (!a || !b)
    return 0;
  if (!a->skin_mesh_in_bind_pose || !b->skin_mesh_in_bind_pose)
    return 0;
  if (a->skin_root_source != b->skin_root_source)
    return 0;
  if (a->skin_joint_count != b->skin_joint_count)
    return 0;
  if (!a->skin_joint_sources || !b->skin_joint_sources)
    return 0;

  for (i = 0; i < a->skin_joint_count; i++)
    if (a->skin_joint_sources[i] != b->skin_joint_sources[i])
      return 0;

  return 1;
}

static int
akb_skin_pose_retain_from(AkbPrimitive *dst, AkbPrimitive *src) {
  uint32_t i;

  if (!dst || !src || !src->skin_pose_animation_count)
    return 0;

  dst->skin_pose_animations = (AkbAnimation **)calloc((size_t)src->skin_pose_animation_count,
                                                      sizeof(*dst->skin_pose_animations));
  if (!dst->skin_pose_animations)
    return 0;

  dst->skin_pose_animation_count = src->skin_pose_animation_count;
  for (i = 0; i < dst->skin_pose_animation_count; i++)
    dst->skin_pose_animations[i] = akb_animation_retain(src->skin_pose_animations[i]);

  return 1;
}

static int
akb_skin_pose_reuse(AkbPrimitiveList *list, AkbPrimitive *prim, size_t current_index) {
  size_t i;

  if (!list || !prim)
    return 0;

  for (i = 0; i < current_index; i++) {
    AkbPrimitive *candidate = &list->items[i];
    if (!candidate->skin_pose_animation_count || !candidate->skin_pose_animations)
      continue;
    if (akb_skin_pose_is_same_skin(prim, candidate))
      return akb_skin_pose_retain_from(prim, candidate);
  }

  return 0;
}

static int32_t
akb_skin_pose_parent_joint_index(const AkbPrimitive *prim,
                                 const AkbSceneNodeList *nodes,
                                 const int32_t *node_to_joint,
                                 uint32_t joint_index) {
  int32_t parent_index;

  if (!prim || !nodes || !node_to_joint || !prim->skin_joint_nodes
      || joint_index >= prim->skin_joint_count)
    return -1;

  parent_index = prim->skin_joint_nodes[joint_index];
  if (parent_index < 0 || (size_t)parent_index >= nodes->count)
    return -1;

  parent_index = nodes->items[parent_index].parent_index;
  while (parent_index >= 0) {
    if ((size_t)parent_index >= nodes->count)
      break;
    if (node_to_joint[parent_index] >= 0)
      return node_to_joint[parent_index];
    parent_index = nodes->items[parent_index].parent_index;
  }

  return -1;
}

static void
akb_build_skin_pose_animations(AkbPrimitiveList *list, AkbSceneNodeList *nodes) {
  AkbPrimitive *prim;
  AkbSceneNode *node;
  float *rest_mats;
  float root_world[16];
  float root_inv[16];
  float joint_world[16];
  float rest[16];
  float parent_inv[16];
  int32_t *node_to_joint;
  uint32_t i;
  size_t j;
  size_t node_table_index;
  int32_t node_index;
  int32_t parent_joint_index;

  if (!list || !nodes)
    return;

  for (j = 0; j < list->count; j++) {
    prim = &list->items[j];
    if (!prim->has_skin || !prim->skin_mesh_in_bind_pose
        || !prim->skin_joint_count || !prim->skin_joint_nodes
        || !prim->skin_root_source)
      continue;

    if (akb_skin_pose_reuse(list, prim, j))
      continue;

    prim->skin_pose_animations = (AkbAnimation **)calloc((size_t)prim->skin_joint_count,
                                                         sizeof(*prim->skin_pose_animations));
    if (!prim->skin_pose_animations)
      continue;
    prim->skin_pose_animation_count = prim->skin_joint_count;

    akb_node_world_matrix(prim->skin_root_source, root_world);
    glm_mat4_inv(AKB_MAT4(root_world), AKB_MAT4(root_inv));

    rest_mats = (float *)malloc((size_t)prim->skin_joint_count * 16 * sizeof(*rest_mats));
    if (!rest_mats)
      continue;

    node_to_joint = (int32_t *)malloc(nodes->count * sizeof(*node_to_joint));
    if (!node_to_joint) {
      free(rest_mats);
      continue;
    }
    for (node_table_index = 0; node_table_index < nodes->count; node_table_index++)
      node_to_joint[node_table_index] = -1;

    for (i = 0; i < prim->skin_joint_count; i++) {
      node_index = prim->skin_joint_nodes[i];
      if (node_index < 0 || (size_t)node_index >= nodes->count)
        continue;
      node_to_joint[node_index] = (int32_t)i;
      node = &nodes->items[node_index];
      if (!node->source)
        continue;

      akb_node_world_matrix(node->source, joint_world);
      glm_mul(AKB_MAT4(root_inv),
              AKB_MAT4(joint_world),
              AKB_MAT4(rest_mats + (size_t)i * 16));
    }

    for (i = 0; i < prim->skin_joint_count; i++) {
      node_index = prim->skin_joint_nodes[i];
      if (node_index < 0 || (size_t)node_index >= nodes->count)
        continue;
      node = &nodes->items[node_index];
      if (!node->animation || !node->animation->count || !node->source)
        continue;

      memcpy(rest, rest_mats + (size_t)i * 16, 16 * sizeof(float));
      parent_joint_index = akb_skin_pose_parent_joint_index(prim, nodes, node_to_joint, i);
      if (parent_joint_index >= 0) {
        glm_mat4_inv(AKB_MAT4(rest_mats + (size_t)parent_joint_index * 16),
                     AKB_MAT4(parent_inv));
        glm_mul(AKB_MAT4(parent_inv),
                AKB_MAT4(rest_mats + (size_t)i * 16),
                AKB_MAT4(rest));
      }

      prim->skin_pose_animations[i] = akb_animation_new_pose_for_joint(node->animation,
                                                                       rest);
    }

    free(node_to_joint);
    free(rest_mats);
  }
}

static int
akb_animation_extract_cubic_values(float **values_io,
                                   float **in_tangents_out,
                                   float **out_tangents_out,
                                   uint32_t *value_count_io,
                                   uint8_t *borrowed_io,
                                   uint32_t time_count,
                                   uint32_t read_width,
                                   uint32_t value_width) {
  float *src;
  float *values;
  float *in_tangents;
  float *out_tangents;
  uint32_t sample_width;
  uint32_t expected_count;
  uint32_t compact_count;
  uint32_t i;

  if (!values_io || !*values_io || !in_tangents_out || !out_tangents_out
      || !value_count_io || !borrowed_io
      || !time_count || !read_width || !value_width)
    return 1;

  sample_width = (read_width == 1 && value_width > 1) ? value_width : read_width;
  expected_count = time_count * 3;
  if (read_width == 1 && value_width > 1)
    expected_count *= value_width;

  if (*value_count_io != expected_count)
    return 1;

  compact_count = time_count * sample_width;
  src = *values_io;
  values = (float *)malloc((size_t)compact_count * sizeof(float));
  in_tangents = (float *)malloc((size_t)compact_count * sizeof(float));
  out_tangents = (float *)malloc((size_t)compact_count * sizeof(float));
  if (!values || !in_tangents || !out_tangents) {
    free(values);
    free(in_tangents);
    free(out_tangents);
    return 0;
  }

  for (i = 0; i < time_count; i++) {
    memcpy(&in_tangents[(size_t)i * sample_width],
           &src[((size_t)i * 3) * sample_width],
           (size_t)sample_width * sizeof(float));
    memcpy(&values[(size_t)i * sample_width],
           &src[((size_t)i * 3 + 1) * sample_width],
           (size_t)sample_width * sizeof(float));
    memcpy(&out_tangents[(size_t)i * sample_width],
           &src[((size_t)i * 3 + 2) * sample_width],
           (size_t)sample_width * sizeof(float));
  }

  if (!*borrowed_io)
    free(src);

  *values_io = values;
  *in_tangents_out = in_tangents;
  *out_tangents_out = out_tangents;
  *borrowed_io = 0;
  *value_count_io = (read_width == 1 && value_width > 1)
                    ? compact_count
                    : time_count;
  return 1;
}

static void
akb_animation_copy_quat_sample(float *dst,
                               const float *src,
                               float sign) {
  dst[0] = sign * src[3];
  dst[1] = sign * src[0];
  dst[2] = sign * src[1];
  dst[3] = sign * src[2];
}

static int
akb_animation_convert_values(AkbAnimChannel *out,
                             float *raw_values,
                             uint32_t raw_count,
                             uint8_t raw_borrowed,
                             const AkbCoordContext *coord) {
  float *values;
  float *in_tangents;
  float *out_tangents;
  float *raw_in_tangents;
  float *raw_out_tangents;
  float dot;
  float sign;
  uint32_t i;

  (void)coord;

  if (out->target != AKB_ANIM_ROTATION_QUAT || out->is_partial) {
    if (out->target == AKB_ANIM_ROTATION_QUAT && out->is_partial) {
      switch (out->target_offset) {
        case 0: out->target_offset = 1; break;
        case 1: out->target_offset = 2; break;
        case 2: out->target_offset = 3; break;
        case 3: out->target_offset = 0; break;
        default: break;
      }
    }
    out->values = raw_values;
    out->borrowed_values = raw_borrowed;
    return 1;
  }

  values = (float *)malloc((size_t)raw_count * 4 * sizeof(float));
  in_tangents = out->in_tangents
                ? (float *)malloc((size_t)raw_count * 4 * sizeof(float))
                : NULL;
  out_tangents = out->out_tangents
                 ? (float *)malloc((size_t)raw_count * 4 * sizeof(float))
                 : NULL;
  if (!values) {
    if (!raw_borrowed)
      free(raw_values);
    if (!out->borrowed_in_tangents)
      free(out->in_tangents);
    if (!out->borrowed_out_tangents)
      free(out->out_tangents);
    out->in_tangents = NULL;
    out->out_tangents = NULL;
    return 0;
  }
  if ((out->in_tangents && !in_tangents)
      || (out->out_tangents && !out_tangents)) {
    free(values);
    free(in_tangents);
    free(out_tangents);
    if (!raw_borrowed)
      free(raw_values);
    if (!out->borrowed_in_tangents)
      free(out->in_tangents);
    if (!out->borrowed_out_tangents)
      free(out->out_tangents);
    out->in_tangents = NULL;
    out->out_tangents = NULL;
    return 0;
  }

  raw_in_tangents = out->in_tangents;
  raw_out_tangents = out->out_tangents;
  for (i = 0; i < raw_count; i++) {
    akb_animation_copy_quat_sample(&values[(size_t)i * 4],
                                   &raw_values[(size_t)i * out->value_width],
                                   1.0f);

    sign = 1.0f;
    if (i > 0) {
      dot = values[(size_t)i * 4] * values[(size_t)(i - 1) * 4]
            + values[(size_t)i * 4 + 1] * values[(size_t)(i - 1) * 4 + 1]
            + values[(size_t)i * 4 + 2] * values[(size_t)(i - 1) * 4 + 2]
            + values[(size_t)i * 4 + 3] * values[(size_t)(i - 1) * 4 + 3];
      if (dot < 0.0f) {
        sign = -1.0f;
        values[(size_t)i * 4]     = -values[(size_t)i * 4];
        values[(size_t)i * 4 + 1] = -values[(size_t)i * 4 + 1];
        values[(size_t)i * 4 + 2] = -values[(size_t)i * 4 + 2];
        values[(size_t)i * 4 + 3] = -values[(size_t)i * 4 + 3];
      }
    }

    if (raw_in_tangents) {
      akb_animation_copy_quat_sample(&in_tangents[(size_t)i * 4],
                                     &raw_in_tangents[(size_t)i * out->value_width],
                                     sign);
    }
    if (raw_out_tangents) {
      akb_animation_copy_quat_sample(&out_tangents[(size_t)i * 4],
                                     &raw_out_tangents[(size_t)i * out->value_width],
                                     sign);
    }
  }
  out->value_width = 4;

  if (!raw_borrowed)
    free(raw_values);
  if (!out->borrowed_in_tangents)
    free(raw_in_tangents);
  if (!out->borrowed_out_tangents)
    free(raw_out_tangents);
  out->values = values;
  out->borrowed_values = 0;
  out->in_tangents = in_tangents;
  out->out_tangents = out_tangents;
  out->borrowed_in_tangents = 0;
  out->borrowed_out_tangents = 0;
  return 1;
}

static int
akb_animation_sample_clip_channel(AkAnimSampler *sampler,
                                  AkAccessor *time_accessor,
                                  uint32_t value_width,
                                  AkAnimationClip *clip,
                                  float **times_out,
                                  uint32_t *count_out,
                                  float **values_out,
                                  uint32_t *value_count_out,
                                  uint8_t *interpolation_out) {
  float *source_times;
  float *base_times;
  float *times;
  float *values;
  float start;
  float end;
  float previous_time;
  float local_time;
  float sample_time;
  float gap;
  float subdivision_count_float;
  size_t required_width;
  size_t base_count;
  size_t base_index;
  size_t sample_capacity;
  size_t sample_index;
  size_t subdivision_count;
  size_t subdivision;
  size_t value_total;
  uint32_t source_count;
  uint32_t i;

  if (!sampler || !time_accessor || !value_width || !clip || !times_out
      || !count_out || !values_out || !value_count_out || !interpolation_out)
    return 0;

  *times_out = NULL;
  *count_out = 0;
  *values_out = NULL;
  *value_count_out = 0;

  if (!ak_animationClipTimeRange(clip, &start, &end)
      || !isfinite(start) || !isfinite(end) || end < start)
    return 0;

  required_width = ak_animationSamplerSample(sampler, start, NULL, 0);
  if (required_width != value_width)
    return 0;

  source_times = akb_accessor_float_copy(time_accessor, 1, &source_count);
  if (!source_times || !source_count) {
    free(source_times);
    return 0;
  }

  if ((size_t)source_count > SIZE_MAX - 2u
      || (size_t)source_count + 2u > SIZE_MAX / sizeof(float)) {
    free(source_times);
    return 0;
  }
  base_times = (float *)malloc(((size_t)source_count + 2u) * sizeof(float));
  if (!base_times) {
    free(source_times);
    return 0;
  }

  base_count = 0u;
  base_times[base_count++] = start;
  for (i = 0; i < source_count; i++) {
    if (!isfinite(source_times[i])
        || (i && !(source_times[i] > source_times[i - 1]))) {
      free(source_times);
      free(base_times);
      return 0;
    }
    if (source_times[i] > start && source_times[i] < end)
      base_times[base_count++] = source_times[i];
  }
  if (end > start)
    base_times[base_count++] = end;
  free(source_times);
  source_times = NULL;

  /* Blender channels carry one interpolation mode, while COLLADA samplers
   * may mix per-key STEP/LINEAR/BEZIER/HERMITE modes.  Sample every segment
   * on the same 30 Hz upper-bound used by the matrix baker, then emit LINEAR
   * curves.  A left-limit sample immediately before every authored key keeps
   * STEP discontinuities sharp while the exact key stores the right value. */
  sample_capacity = 1u;
  previous_time = base_times[0];
  for (base_index = 1u; base_index < base_count; base_index++) {
    gap = base_times[base_index] - previous_time;
    subdivision_count_float = ceilf(gap / (1.0f / 30.0f));
    if (!isfinite(subdivision_count_float)
        || subdivision_count_float < 1.0f
        || subdivision_count_float >= (float)SIZE_MAX) {
      free(base_times);
      return 0;
    }
    subdivision_count = (size_t)subdivision_count_float;
    if (sample_capacity > SIZE_MAX - subdivision_count) {
      free(base_times);
      return 0;
    }
    sample_capacity += subdivision_count;
    if (sample_capacity == SIZE_MAX) {
      free(base_times);
      return 0;
    }
    sample_capacity++;
    previous_time = base_times[base_index];
  }
  if (sample_capacity > UINT32_MAX
      || sample_capacity > SIZE_MAX / sizeof(float)
      || sample_capacity > SIZE_MAX / value_width) {
    free(base_times);
    return 0;
  }
  value_total = sample_capacity * value_width;
  if (value_total > SIZE_MAX / sizeof(float)) {
    free(base_times);
    return 0;
  }

  times = (float *)malloc(sample_capacity * sizeof(float));
  values = (float *)malloc(value_total * sizeof(float));
  if (!times || !values) {
    free(base_times);
    free(times);
    free(values);
    return 0;
  }

  sample_index = 0u;
  times[sample_index] = 0.0f;
  if (ak_animationSamplerSample(sampler,
                                start,
                                values + sample_index * value_width,
                                value_width) != value_width)
    goto fail;
  sample_index++;

  previous_time = base_times[0];
  for (base_index = 1u; base_index < base_count; base_index++) {
    sample_time = base_times[base_index];
    gap = sample_time - previous_time;
    subdivision_count = (size_t)ceilf(gap / (1.0f / 30.0f));
    for (subdivision = 1u; subdivision <= subdivision_count; subdivision++) {
      if (subdivision == subdivision_count) {
        float left_time = nextafterf(sample_time, previous_time);
        local_time = left_time - start;
        if (isfinite(local_time) && local_time > times[sample_index - 1u]) {
          times[sample_index] = local_time;
          if (ak_animationSamplerSample(sampler,
                                        left_time,
                                        values + sample_index * value_width,
                                        value_width) != value_width)
            goto fail;
          sample_index++;
        }
      }

      local_time = subdivision == subdivision_count
                   ? sample_time - start
                   : previous_time - start
                     + gap * (float)subdivision / (float)subdivision_count;
      if (!isfinite(local_time) || local_time <= times[sample_index - 1u])
        goto fail;
      times[sample_index] = local_time;
      if (ak_animationSamplerSample(sampler,
                                    subdivision == subdivision_count
                                      ? sample_time
                                      : start + local_time,
                                    values + sample_index * value_width,
                                    value_width) != value_width)
        goto fail;
      sample_index++;
    }
    previous_time = sample_time;
  }

  free(base_times);
  *times_out = times;
  *count_out = (uint32_t)sample_index;
  *values_out = values;
  *value_count_out = (uint32_t)sample_index;
  *interpolation_out = AK_INTERPOLATION_LINEAR;
  return 1;

fail:
  free(source_times);
  free(base_times);
  free(times);
  free(values);
  return 0;
}

static int
akb_animation_add_channel(AkbAnimation *animation,
                          AkChannel *channel,
                          AkResolvedTarget *target,
                          const AkbAnimBinding *binding,
                          const AkbCoordContext *coord,
                          AkAnimationClip *clip,
                          uint32_t clip_index,
                          const char *clip_name) {
  AkbAnimChannel out = {0};
  AkAnimSampler *sampler;
  AkInput *time_input;
  AkInput *value_input;
  float *raw_values;
  uint32_t time_count;
  uint32_t value_count;
  uint32_t read_width;
  uint32_t logical_value_count;
  uint8_t raw_borrowed;
  uint8_t clipped_interpolation;

  sampler = ak_getObjectByUrl(&channel->source);
  if (!sampler)
    return 1;

  time_input = akb_anim_sampler_input(sampler, AK_INPUT_INPUT);
  value_input = akb_anim_sampler_input(sampler, AK_INPUT_OUTPUT);
  if (!time_input || !time_input->accessor || !value_input || !value_input->accessor)
    return 1;

  out.target = binding->kind;
  if (!out.target)
    return 1;
  out.clip_index = clip_index;
  out.clip_name = clip_name;

  out.value_width = value_input->accessor->componentCount
                    ? value_input->accessor->componentCount
                    : binding->width;
  if (target->isPartial && out.value_width > 1)
    out.value_width = 1;
  read_width = out.value_width;

  if (binding->kind == AKB_ANIM_MORPH_WEIGHTS && !target->isPartial) {
    out.value_width = binding->width;
    read_width = value_input->accessor->componentCount
                 ? value_input->accessor->componentCount
                 : 1;
    if (read_width != out.value_width)
      read_width = 1;
  }

  if (clip) {
    if (!akb_animation_sample_clip_channel(sampler,
                                           time_input->accessor,
                                           out.value_width,
                                           clip,
                                           &out.times,
                                           &time_count,
                                           &raw_values,
                                           &value_count,
                                           &clipped_interpolation))
      return 0;
    raw_borrowed = 0;
  } else {
    out.times = akb_accessor_float_borrow(time_input->accessor, 1, &time_count);
    if (out.times) {
      out.borrowed_times = 1;
    } else {
      out.times = akb_accessor_float_copy(time_input->accessor, 1, &time_count);
      if (!out.times)
        return 0;
    }

    raw_values = akb_accessor_float_borrow(value_input->accessor,
                                           read_width,
                                           &value_count);
    if (raw_values) {
      raw_borrowed = 1;
    } else {
      raw_values = akb_accessor_float_copy(value_input->accessor,
                                           read_width,
                                           &value_count);
      raw_borrowed = 0;
      if (!raw_values) {
        if (!out.borrowed_times)
          free(out.times);
        return 0;
      }
    }
  }

  if (!clip
      && sampler->uniInterpolation == AK_INTERPOLATION_HERMITE
      && !akb_animation_extract_cubic_values(&raw_values,
                                             &out.in_tangents,
                                             &out.out_tangents,
                                             &value_count,
                                             &raw_borrowed,
                                             time_count,
                                             read_width,
                                             out.value_width)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!raw_borrowed)
      free(raw_values);
    return 0;
  }

  logical_value_count = value_count;
  if (binding->kind == AKB_ANIM_MORPH_WEIGHTS
      && !clip
      && !target->isPartial
      && read_width == 1
      && out.value_width > 1)
    logical_value_count = value_count / out.value_width;

  if (logical_value_count < time_count)
    time_count = logical_value_count;

  out.count = time_count;
  out.target_offset = target->isPartial ? target->off : 0;
  out.is_partial = target->isPartial ? 1 : 0;
  out.interpolation = clip
                      ? clipped_interpolation
                      : (uint8_t)sampler->uniInterpolation;

  if (!akb_animation_convert_values(&out,
                                    raw_values,
                                    value_count,
                                    raw_borrowed,
                                    coord)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 0;
  }

  if (!out.count) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 1;
  }

  if (!akb_animation_push(animation, &out)) {
    if (!out.borrowed_times)
      free(out.times);
    if (!out.borrowed_values)
      free(out.values);
    if (!out.borrowed_in_tangents)
      free(out.in_tangents);
    if (!out.borrowed_out_tangents)
      free(out.out_tangents);
    return 0;
  }

  return 1;
}

static int
akb_animation_collect_list(AkbAnimation *animation,
                           AkAnimation *source,
                           AkContext *context,
                           const AkbAnimBinding *bindings,
                           int binding_count,
                           const AkbCoordContext *coord,
                           uint32_t clip_index,
                           const char *clip_name);

static int
akb_animation_collect_tree(AkbAnimation *animation,
                           AkAnimation *source,
                           AkContext *context,
                           const AkbAnimBinding *bindings,
                           int binding_count,
                           const AkbCoordContext *coord,
                           uint32_t clip_index,
                           const char *clip_name) {
  AkChannel *channel;
  AkResolvedTarget resolved;
  int i;

  if (!source)
    return 1;

  for (channel = source->channel; channel; channel = channel->next) {
    resolved = ak_channelTarget(context, channel);
    if (!resolved.target)
      continue;

    for (i = 0; i < binding_count; i++) {
      if (resolved.target == bindings[i].target) {
        if (!akb_animation_add_channel(animation,
                                       channel,
                                       &resolved,
                                       &bindings[i],
                                       coord,
                                       NULL,
                                       clip_index,
                                       clip_name))
          return 0;
        break;
      }
    }
  }

  if (source->animation
      && !akb_animation_collect_list(animation,
                                     source->animation,
                                     context,
                                     bindings,
                                     binding_count,
                                     coord,
                                     clip_index,
                                     clip_name))
    return 0;

  return 1;
}

static int
akb_animation_collect_list(AkbAnimation *animation,
                           AkAnimation *source,
                           AkContext *context,
                           const AkbAnimBinding *bindings,
                           int binding_count,
                           const AkbCoordContext *coord,
                           uint32_t clip_index,
                           const char *clip_name) {
  while (source) {
    if (!akb_animation_collect_tree(animation,
                                    source,
                                    context,
                                    bindings,
                                    binding_count,
                                    coord,
                                    clip_index,
                                    clip_name))
      return 0;
    source = source->next;
  }

  return 1;
}

static void
akb_animation_index_free(AkbAnimationIndex *index) {
  if (!index)
    return;
  free(index->items);
  free(index->target_buckets);
  memset(index, 0, sizeof(*index));
}

static int
akb_animation_index_push(AkbAnimationIndex *index,
                         AkChannel *channel,
                         const AkResolvedTarget *resolved,
                         AkAnimationClip *clip,
                         uint32_t clip_index,
                         const char *clip_name) {
  AkbResolvedAnimChannel *items;
  size_t i;
  size_t capacity;

  if (!index || !channel || !resolved || !resolved->target)
    return 1;

  /* An explicit COLLADA clip may reference the same animation twice, or both
   * an animation and one of its descendants.  The clip owns one logical copy
   * of each authored channel; do not emit duplicate Blender curves. */
  for (i = 0; i < index->count; i++) {
    if (index->items[i].channel == channel
        && index->items[i].clip_index == clip_index
        && index->items[i].resolved.target == resolved->target
        && index->items[i].resolved.off == resolved->off
        && index->items[i].resolved.isPartial == resolved->isPartial)
      return 1;
  }

  if (index->count == index->capacity) {
    capacity = index->capacity ? index->capacity * 2 : 64;
    if (capacity < index->capacity
        || capacity > SIZE_MAX / sizeof(*items))
      return 0;
    items = (AkbResolvedAnimChannel *)realloc(index->items,
                                              capacity * sizeof(*items));
    if (!items)
      return 0;
    index->items = items;
    index->capacity = capacity;
  }

  index->items[index->count].channel = channel;
  index->items[index->count].clip = clip;
  index->items[index->count].resolved = *resolved;
  index->items[index->count].clip_name = clip_name;
  index->items[index->count].next_target = SIZE_MAX;
  index->items[index->count].clip_index = clip_index;
  index->count++;
  return 1;
}

static int
akb_animation_index_push_channel(AkbAnimationIndex *index,
                                 AkChannel *channel,
                                 AkContext *context,
                                 AkAnimationClip *clip,
                                 uint32_t clip_index,
                                 const char *clip_name) {
  AkResolvedTarget  local[1];
  AkResolvedTarget *targets;
  size_t            count, confirmed, i;
  int               ok;

  count = ak_channelResolvedTargets(context, channel, NULL, 0);
  if (count == SIZE_MAX)
    return 0;
  if (!count)
    return 1;

  if (count == 1) {
    targets = local;
  } else {
    if (count > SIZE_MAX / sizeof(*targets))
      return 0;
    targets = (AkResolvedTarget *)malloc(count * sizeof(*targets));
    if (!targets)
      return 0;
  }

  confirmed = ak_channelResolvedTargets(context, channel, targets, count);
  if (confirmed != count) {
    if (targets != local)
      free(targets);
    return 0;
  }

  ok = 1;
  for (i = 0; i < count; i++) {
    if (!akb_animation_index_push(index,
                                  channel,
                                  &targets[i],
                                  clip,
                                  clip_index,
                                  clip_name)) {
      ok = 0;
      break;
    }
  }
  if (targets != local)
    free(targets);
  return ok;
}

static size_t
akb_animation_target_hash(const void *target) {
  uintptr_t value = (uintptr_t)target;

  value ^= value >> 33;
  value *= (uintptr_t)UINT64_C(0xff51afd7ed558ccd);
  value ^= value >> 33;
  return (size_t)value;
}

static void
akb_animation_index_build_target_table(AkbAnimationIndex *index) {
  size_t bucket_count;
  size_t bucket_index;
  size_t i;

  if (!index || !index->count)
    return;
  if (index->count > SIZE_MAX / 2)
    return;

  bucket_count = 64;
  while (bucket_count < index->count * 2) {
    if (bucket_count > SIZE_MAX / 2)
      return;
    bucket_count *= 2;
  }

  index->target_buckets = (size_t *)malloc(bucket_count * sizeof(*index->target_buckets));
  if (!index->target_buckets)
    return;
  index->target_bucket_count = bucket_count;
  for (i = 0; i < bucket_count; i++)
    index->target_buckets[i] = SIZE_MAX;

  /* Reverse insertion keeps each target chain in original channel order. */
  for (i = index->count; i > 0; i--) {
    AkbResolvedAnimChannel *item = &index->items[i - 1];
    bucket_index = akb_animation_target_hash(item->resolved.target) & (bucket_count - 1);
    item->next_target = index->target_buckets[bucket_index];
    index->target_buckets[bucket_index] = i - 1;
  }
}

static size_t
akb_animation_index_target_item(const AkbAnimationIndex *index,
                                const void *target,
                                size_t item_index) {
  if (!index || !target || !index->target_buckets || !index->target_bucket_count)
    return SIZE_MAX;

  if (item_index == SIZE_MAX) {
    size_t bucket_index = akb_animation_target_hash(target)
                          & (index->target_bucket_count - 1);
    item_index = index->target_buckets[bucket_index];
  } else if (item_index < index->count) {
    item_index = index->items[item_index].next_target;
  }

  while (item_index < index->count) {
    if (index->items[item_index].resolved.target == target)
      return item_index;
    item_index = index->items[item_index].next_target;
  }
  return SIZE_MAX;
}

static int
akb_animation_index_collect_list(AkbAnimationIndex *index,
                                 AkAnimation *source,
                                 AkContext *context,
                                 AkAnimationClip *clip,
                                 uint32_t clip_index,
                                 const char *clip_name);

static int
akb_animation_index_collect_tree(AkbAnimationIndex *index,
                                 AkAnimation *source,
                                 AkContext *context,
                                 AkAnimationClip *clip,
                                 uint32_t clip_index,
                                 const char *clip_name) {
  AkChannel *channel;

  if (!source)
    return 1;

  for (channel = source->channel; channel; channel = channel->next) {
    if (!akb_animation_index_push_channel(index,
                                          channel,
                                          context,
                                          clip,
                                          clip_index,
                                          clip_name))
      return 0;
  }

  if (source->animation
      && !akb_animation_index_collect_list(index,
                                           source->animation,
                                           context,
                                           clip,
                                           clip_index,
                                           clip_name))
    return 0;

  return 1;
}

static int
akb_animation_index_collect_list(AkbAnimationIndex *index,
                                 AkAnimation *source,
                                 AkContext *context,
                                 AkAnimationClip *clip,
                                 uint32_t clip_index,
                                 const char *clip_name) {
  while (source) {
    if (!akb_animation_index_collect_tree(index,
                                          source,
                                          context,
                                          clip,
                                          clip_index,
                                          clip_name))
      return 0;
    source = source->next;
  }

  return 1;
}

static int
akb_animation_index_build_collada(AkbAnimationIndex *index,
                                  AkDoc *doc,
                                  AkContext *context) {
  AkAnimationClip       *clip;
  AkAnimationClipMember *member;
  AkAnimation           *animation;
  uint32_t               clip_index;

  clip_index = 0;
  for (clip = doc->animationClips.first;
       clip;
       clip = clip->next, clip_index++) {
    for (member = clip->members; member; member = member->next) {
      if (!akb_animation_index_collect_tree(index,
                                            member->animation,
                                            context,
                                            clip,
                                            clip_index,
                                            clip->name))
        return 0;
    }
  }

  /* COLLADA files without <animation_clip> traditionally treat all sibling
   * animations as one implicit clip.  When explicit clips exist, retain the
   * same grouping for every channel not owned by one of them. */
  {
    AkAnimation **pending = NULL;
    AkAnimation **seen = NULL;
    size_t pending_count = 0, pending_capacity = 0;
    size_t seen_count = 0, seen_capacity = 0;

#define AKB_PUSH_ANIMATION(ARRAY, COUNT, CAPACITY, VALUE)                     \
    do {                                                                      \
      if ((COUNT) == (CAPACITY)) {                                            \
        size_t new_capacity = (CAPACITY) ? (CAPACITY) * 2u : 64u;             \
        AkAnimation **grown;                                                  \
        if (new_capacity < (CAPACITY)                                         \
            || new_capacity > SIZE_MAX / sizeof(*(ARRAY))) {                  \
          free(pending);                                                      \
          free(seen);                                                         \
          return 0;                                                           \
        }                                                                     \
        grown = (AkAnimation **)realloc((ARRAY),                              \
                                        new_capacity * sizeof(*(ARRAY)));     \
        if (!grown) {                                                         \
          free(pending);                                                      \
          free(seen);                                                         \
          return 0;                                                           \
        }                                                                     \
        (ARRAY) = grown;                                                      \
        (CAPACITY) = new_capacity;                                            \
      }                                                                       \
      (ARRAY)[(COUNT)++] = (VALUE);                                           \
    } while (0)

    for (animation = doc->lib.animations.first;
         animation;
         animation = animation->next)
      AKB_PUSH_ANIMATION(pending, pending_count, pending_capacity, animation);
    {
      size_t i;
      for (i = 0; i < pending_count / 2u; i++) {
        AkAnimation *swap = pending[i];
        pending[i] = pending[pending_count - 1u - i];
        pending[pending_count - 1u - i] = swap;
      }
    }

    while (pending_count) {
      AkAnimation *item = pending[--pending_count];
      AkAnimation *child;
      AkChannel *channel;
      AkAnimationClip *owner;
      AkAnimationClipMember *owner_member;
      size_t i, child_start;
      int exact_member = 0;

      for (i = 0; i < seen_count; i++)
        if (seen[i] == item)
          break;
      if (i < seen_count)
        continue;
      AKB_PUSH_ANIMATION(seen, seen_count, seen_capacity, item);

      for (owner = doc->animationClips.first;
           owner && !exact_member;
           owner = owner->next) {
        for (owner_member = owner->members;
             owner_member;
             owner_member = owner_member->next) {
          if (owner_member->animation == item) {
            exact_member = 1;
            break;
          }
        }
      }
      if (exact_member)
        continue;

      for (channel = item->channel; channel; channel = channel->next) {
        if (!akb_animation_index_push_channel(index,
                                              channel,
                                              context,
                                              NULL,
                                              clip_index,
                                              NULL)) {
          free(pending);
          free(seen);
          return 0;
        }
      }

      child_start = pending_count;
      for (child = item->animation; child; child = child->next)
        AKB_PUSH_ANIMATION(pending, pending_count, pending_capacity, child);
      for (i = 0; i < (pending_count - child_start) / 2u; i++) {
        AkAnimation *swap = pending[child_start + i];
        pending[child_start + i] = pending[pending_count - 1u - i];
        pending[pending_count - 1u - i] = swap;
      }
    }

#undef AKB_PUSH_ANIMATION
    free(pending);
    free(seen);
  }

  return 1;
}

static int
akb_animation_index_build(AkbAnimationIndex *index, AkDoc *doc) {
  AkAnimation *animation;
  AkContext context;
  uint32_t clip_index;

  if (!index || !doc)
    return 1;

  memset(index, 0, sizeof(*index));
  memset(&context, 0, sizeof(context));
  context.doc = doc;

  if (doc->inf && doc->inf->ftype == AK_FILE_TYPE_COLLADA) {
    if (!akb_animation_index_build_collada(index, doc, &context)) {
      akb_animation_index_free(index);
      return 0;
    }
    akb_animation_index_build_target_table(index);
    return 1;
  }

  clip_index = 0;
  for (animation = doc->lib.animations.first; animation; animation = animation->next, clip_index++) {
    if (!akb_animation_index_collect_tree(index,
                                          animation,
                                          &context,
                                          NULL,
                                          clip_index,
                                          animation->name)) {
      akb_animation_index_free(index);
      return 0;
    }
  }

  akb_animation_index_build_target_table(index);
  return 1;
}

static int
akb_animation_collect_index(AkbAnimation *animation,
                            const AkbAnimationIndex *index,
                            const AkbAnimBinding *bindings,
                            int binding_count,
                            const AkbCoordContext *coord) {
  size_t heads[64];
  size_t selected;
  size_t j;
  int i;
  int selected_binding;

  if (!animation || !index || !bindings || binding_count <= 0)
    return 1;

  if (index->target_buckets && binding_count <= 64) {
    for (i = 0; i < binding_count; i++) {
      int duplicate = 0;
      int previous;

      for (previous = 0; previous < i; previous++) {
        if (bindings[previous].target == bindings[i].target) {
          duplicate = 1;
          break;
        }
      }
      heads[i] = duplicate
                   ? SIZE_MAX
                   : akb_animation_index_target_item(index,
                                                     bindings[i].target,
                                                     SIZE_MAX);
    }

    for (;;) {
      selected = SIZE_MAX;
      selected_binding = -1;
      for (i = 0; i < binding_count; i++) {
        if (heads[i] < selected) {
          selected = heads[i];
          selected_binding = i;
        }
      }
      if (selected_binding < 0)
        return 1;

      {
        const AkbResolvedAnimChannel *item = &index->items[selected];
        AkResolvedTarget resolved = item->resolved;
        if (!akb_animation_add_channel(animation,
                                       item->channel,
                                       &resolved,
                                       &bindings[selected_binding],
                                       coord,
                                       item->clip,
                                       item->clip_index,
                                       item->clip_name))
          return 0;
      }
      heads[selected_binding] = akb_animation_index_target_item(index,
                                                                bindings[selected_binding].target,
                                                                selected);
    }
  }

  for (j = 0; j < index->count; j++) {
    const AkbResolvedAnimChannel *item = &index->items[j];
    for (i = 0; i < binding_count; i++) {
      if (item->resolved.target == bindings[i].target) {
        AkResolvedTarget resolved = item->resolved;
        if (!akb_animation_add_channel(animation,
                                       item->channel,
                                       &resolved,
                                       &bindings[i],
                                       coord,
                                       item->clip,
                                       item->clip_index,
                                       item->clip_name))
          return 0;
        break;
      }
    }
  }

  return 1;
}

static int
akb_animation_list_has_channel(AkAnimation *source, AkChannel *channel);

static int
akb_animation_subtree_has_channel(AkAnimation *source, AkChannel *channel) {
  AkChannel *item;

  if (!source || !channel)
    return 0;

  for (item = source->channel; item; item = item->next) {
    if (item == channel)
      return 1;
  }

  if (source->animation
      && akb_animation_list_has_channel(source->animation, channel))
    return 1;

  return 0;
}

static int
akb_animation_list_has_channel(AkAnimation *source, AkChannel *channel) {
  while (source) {
    if (akb_animation_subtree_has_channel(source, channel))
      return 1;
    source = source->next;
  }

  return 0;
}

static int
akb_animation_index_clip_for_source(const AkbAnimationIndex *index,
                                    AkAnimation *source,
                                    uint32_t *clip_index,
                                    const char **clip_name) {
  size_t i;

  if (!index || !source || !clip_index || !clip_name)
    return 0;

  for (i = 0; i < index->count; i++) {
    if (akb_animation_subtree_has_channel(source, index->items[i].channel)) {
      *clip_index = index->items[i].clip_index;
      *clip_name = index->items[i].clip_name;
      return 1;
    }
  }

  return 0;
}

static AkbAnimation *
akb_animation_new_for_bindings(AkDoc *doc,
                               AkbSharedDoc *doc_owner,
                               const AkbAnimationIndex *index,
                               const AkbAnimBinding *bindings,
                               int binding_count,
                               const AkbCoordContext *coord,
                               int *ok) {
  AkbAnimation *animation;
  AkAnimation *source;
  AkContext context;
  uint32_t clip_index;

  *ok = 1;
  if (!doc || !bindings || binding_count <= 0)
    return NULL;
  if ((index && !index->count) || (!index && !doc->lib.animations.first))
    return NULL;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  if (index) {
    if (!akb_animation_collect_index(animation,
                                     index,
                                     bindings,
                                     binding_count,
                                     coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  } else {
    memset(&context, 0, sizeof(context));
    context.doc = doc;

    clip_index = 0;
    for (source = doc->lib.animations.first; source; source = source->next, clip_index++) {
      if (!akb_animation_collect_tree(animation,
                                      source,
                                      &context,
                                      bindings,
                                      binding_count,
                                      coord,
                                      clip_index,
                                      source->name)) {
        akb_animation_release(animation);
        *ok = 0;
        return NULL;
      }
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static int
akb_node_visibility_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  if (!node)
    return 0;

  return akb_anim_binding_push(bindings,
                               capacity,
                               0,
                               &node->visible,
                               AKB_ANIM_VISIBILITY,
                               1);
}

static int
akb_node_transform_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  AkObject *object;
  uint32_t kind;
  uint32_t width;
  int count;

  count = akb_node_visibility_bindings(node, bindings, capacity);
  if (!node)
    return 0;
  if (!node->transform)
    return count;

  for (object = node->transform->base; object; object = object->next) {
    kind = (uint32_t)akb_anim_target_kind(object, &width);
    count = akb_anim_binding_push(bindings, capacity, count, object, kind, width);
  }

  for (object = node->transform->item; object; object = object->next) {
    kind = (uint32_t)akb_anim_target_kind(object, &width);
    count = akb_anim_binding_push(bindings, capacity, count, object, kind, width);
  }

  return count;
}

static int
akb_node_camera_bindings(AkNode *node,
                         AkbAnimBinding *bindings,
                         int capacity,
                         int count) {
  AkCamera *camera;
  AkProjection *projection;

  if (!node || !node->camera)
    return count;

  camera = (AkCamera *)ak_instanceObject(node->camera);
  if (!camera || !camera->optics || !(projection = camera->optics->proj))
    return count;

  if (projection->type == AK_PROJECTION_PERSPECTIVE) {
    AkPerspective *persp;

    persp = (AkPerspective *)projection;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->xfov,
                                  AKB_ANIM_CAMERA_XFOV,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->yfov,
                                  AKB_ANIM_CAMERA_YFOV,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->znear,
                                  AKB_ANIM_CAMERA_ZNEAR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &persp->zfar,
                                  AKB_ANIM_CAMERA_ZFAR,
                                  1);
  } else if (projection->type == AK_PROJECTION_ORTHOGRAPHIC) {
    AkOrthographic *ortho;

    ortho = (AkOrthographic *)projection;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->xmag,
                                  AKB_ANIM_CAMERA_ORTHO_XMAG,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->ymag,
                                  AKB_ANIM_CAMERA_ORTHO_YMAG,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->znear,
                                  AKB_ANIM_CAMERA_ZNEAR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &ortho->zfar,
                                  AKB_ANIM_CAMERA_ZFAR,
                                  1);
  }

  return count;
}

static int
akb_node_light_bindings(AkNode *node,
                        AkbAnimBinding *bindings,
                        int capacity,
                        int count) {
  AkLight *light;
  AkLightBase *base;

  if (!node || !node->light)
    return count;

  light = (AkLight *)ak_instanceObject(node->light);
  if (!light || !(base = light->data))
    return count;

  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                base->color.vec,
                                AKB_ANIM_LIGHT_COLOR,
                                3);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &base->intensity,
                                AKB_ANIM_LIGHT_INTENSITY,
                                1);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &base->range,
                                AKB_ANIM_LIGHT_RANGE,
                                1);

  if (base->type == AK_LIGHT_TYPE_SPOT) {
    AkSpotLight *spot;

    spot = (AkSpotLight *)base;
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &spot->innerConeAngle,
                                  AKB_ANIM_LIGHT_SPOT_INNER,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &spot->outerConeAngle,
                                  AKB_ANIM_LIGHT_SPOT_OUTER,
                                  1);
  }

  return count;
}

static int
akb_node_scene_bindings(AkNode *node, AkbAnimBinding *bindings, int capacity) {
  int count;

  count = akb_node_transform_bindings(node, bindings, capacity);
  count = akb_node_camera_bindings(node, bindings, capacity, count);
  count = akb_node_light_bindings(node, bindings, capacity, count);

  return count;
}

static int
akb_texture_transform_binding_push(AkbAnimBinding *bindings,
                                   int capacity,
                                   int count,
                                   AkTextureRef *texref,
                                   uint32_t role_id) {
  AkTextureTransform *transform;
  uint32_t base;

  if (!texref || !(transform = texref->transform))
    return count;

  base = AKB_ANIM_TEXTURE_TRANSFORM_BASE
         + role_id * AKB_ANIM_TEXTURE_TRANSFORM_STRIDE;
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                transform->offset,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_OFFSET,
                                2);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                transform->scale,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_SCALE,
                                2);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &transform->rotation,
                                base + AKB_ANIM_TEXTURE_TRANSFORM_ROTATION,
                                1);

  return count;
}

static void *
akb_material_input_anim_vector(AkMaterialInput *input) {
  if (!input)
    return NULL;
  if (input->valueType == AK_MATERIAL_VALUE_COLOR)
    return input->color.vec;
  return input->value;
}

static int
akb_material_color_binding(AkbAnimBinding *bindings,
                           int capacity,
                           int count,
                           AkMaterialInput *input,
                           uint32_t target,
                           uint32_t width,
                           uint32_t tex_role) {
  if (!input)
    return count;
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                akb_material_input_anim_vector(input),
                                target,
                                width);
  return akb_texture_transform_binding_push(bindings,
                                            capacity,
                                            count,
                                            input->texture,
                                            tex_role);
}

static int
akb_material_scalar_binding(AkbAnimBinding *bindings,
                            int capacity,
                            int count,
                            AkMaterialInput *input,
                            uint32_t target,
                            uint32_t tex_role) {
  if (!input)
    return count;
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &input->value[0],
                                target,
                                1);
  return akb_texture_transform_binding_push(bindings,
                                            capacity,
                                            count,
                                            input->texture,
                                            tex_role);
}

static int
akb_material_bindings(AkMaterialSurface *surface, AkbAnimBinding *bindings, int capacity) {
  AkMaterialSpecularGlossinessFeature *sg;
  AkMaterialSpecularFeature *specular;
  AkMaterialClassicFeature *classic;
  AkMaterialClearcoatFeature *clearcoat;
  AkMaterialTransmissionFeature *transmission;
  AkMaterialSheenFeature *sheen;
  AkMaterialIridescenceFeature *iridescence;
  AkMaterialVolumeFeature *volume;
  AkMaterialAnisotropyFeature *anisotropy;
  AkMaterialDispersionFeature *dispersion;
  AkMaterialDiffuseTransmissionFeature *diffuse_transmission;
  int count;

  count = 0;
  if (!surface)
    return 0;

  count = akb_material_color_binding(bindings,
                                     capacity,
                                     count,
                                     surface->baseColor,
                                     AKB_ANIM_MATERIAL_BASE_COLOR,
                                     4,
                                     AKB_TEX_ROLE_BASE_COLOR);
  count = akb_material_scalar_binding(bindings,
                                      capacity,
                                      count,
                                      surface->metallic,
                                      AKB_ANIM_MATERIAL_METALLIC,
                                      AKB_TEX_ROLE_METALLIC_ROUGHNESS);
  count = akb_material_scalar_binding(bindings,
                                      capacity,
                                      count,
                                      surface->roughness,
                                      AKB_ANIM_MATERIAL_ROUGHNESS,
                                      AKB_TEX_ROLE_METALLIC_ROUGHNESS);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &surface->alphaCutoff,
                                AKB_ANIM_MATERIAL_ALPHA_CUTOFF,
                                1);
  count = akb_material_color_binding(bindings,
                                     capacity,
                                     count,
                                     surface->emissive,
                                     AKB_ANIM_MATERIAL_EMISSIVE_COLOR,
                                     3,
                                     AKB_TEX_ROLE_EMISSIVE);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &surface->emissiveStrength,
                                AKB_ANIM_MATERIAL_EMISSIVE_STRENGTH,
                                1);
  count = akb_material_scalar_binding(bindings,
                                      capacity,
                                      count,
                                      surface->normal,
                                      AKB_ANIM_MATERIAL_NORMAL_SCALE,
                                      AKB_TEX_ROLE_NORMAL);
  count = akb_material_scalar_binding(bindings,
                                      capacity,
                                      count,
                                      surface->occlusion,
                                      AKB_ANIM_MATERIAL_OCCLUSION_STRENGTH,
                                      AKB_TEX_ROLE_OCCLUSION);
  count = akb_anim_binding_push(bindings,
                                capacity,
                                count,
                                &surface->ior,
                                AKB_ANIM_MATERIAL_IOR,
                                1);
  count = akb_texture_transform_binding_push(bindings,
                                             capacity,
                                             count,
                                             surface->opacity ? surface->opacity->texture : NULL,
                                             AKB_TEX_ROLE_TRANSPARENT);

  sg = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR_GLOSSINESS);
  if (sg) {
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       sg->diffuse,
                                       AKB_ANIM_MATERIAL_BASE_COLOR,
                                       4,
                                       AKB_TEX_ROLE_BASE_COLOR);
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       sg->specular,
                                       AKB_ANIM_MATERIAL_SPECULAR_COLOR,
                                       3,
                                       AKB_TEX_ROLE_SPECULAR_COLOR);
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        sg->glossiness,
                                        AKB_ANIM_MATERIAL_SPECULAR,
                                        AKB_TEX_ROLE_SPECULAR);
  }

  specular = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SPECULAR);
  if (specular) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        specular->factor,
                                        AKB_ANIM_MATERIAL_SPECULAR,
                                        AKB_TEX_ROLE_SPECULAR);
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       specular->color,
                                       AKB_ANIM_MATERIAL_SPECULAR_COLOR,
                                       3,
                                       AKB_TEX_ROLE_SPECULAR_COLOR);
  }

  classic = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLASSIC);
  if (classic) {
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       classic->diffuse,
                                       AKB_ANIM_MATERIAL_BASE_COLOR,
                                       4,
                                       AKB_TEX_ROLE_BASE_COLOR);
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       classic->specular,
                                       AKB_ANIM_MATERIAL_SPECULAR_COLOR,
                                       3,
                                       AKB_TEX_ROLE_SPECULAR_COLOR);
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       classic->emission,
                                       AKB_ANIM_MATERIAL_EMISSIVE_COLOR,
                                       3,
                                       AKB_TEX_ROLE_EMISSIVE);
  }

  clearcoat = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_CLEARCOAT);
  if (clearcoat) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        clearcoat->factor,
                                        AKB_ANIM_MATERIAL_CLEARCOAT,
                                        AKB_TEX_ROLE_CLEARCOAT);
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        clearcoat->roughness,
                                        AKB_ANIM_MATERIAL_CLEARCOAT_ROUGHNESS,
                                        AKB_TEX_ROLE_CLEARCOAT_ROUGHNESS);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &clearcoat->normalScale,
                                  AKB_ANIM_MATERIAL_CLEARCOAT_NORMAL_SCALE,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               clearcoat->normal ? clearcoat->normal->texture : NULL,
                                               AKB_TEX_ROLE_CLEARCOAT_NORMAL);
  }

  transmission = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_TRANSMISSION);
  if (transmission)
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        transmission->factor,
                                        AKB_ANIM_MATERIAL_TRANSMISSION,
                                        AKB_TEX_ROLE_TRANSMISSION);

  sheen = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_SHEEN);
  if (sheen) {
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       sheen->color,
                                       AKB_ANIM_MATERIAL_SHEEN_COLOR,
                                       3,
                                       AKB_TEX_ROLE_SHEEN_COLOR);
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        sheen->roughness,
                                        AKB_ANIM_MATERIAL_SHEEN_ROUGHNESS,
                                        AKB_TEX_ROLE_SHEEN_ROUGHNESS);
  }

  iridescence = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_IRIDESCENCE);
  if (iridescence) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        iridescence->factor,
                                        AKB_ANIM_MATERIAL_IRIDESCENCE,
                                        AKB_TEX_ROLE_IRIDESCENCE);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &iridescence->ior,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_IOR,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &iridescence->thicknessMinimum,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MINIMUM,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &iridescence->thicknessMaximum,
                                  AKB_ANIM_MATERIAL_IRIDESCENCE_THICKNESS_MAXIMUM,
                                  1);
    count = akb_texture_transform_binding_push(bindings,
                                               capacity,
                                               count,
                                               iridescence->thickness ? iridescence->thickness->texture : NULL,
                                               AKB_TEX_ROLE_IRIDESCENCE_THICKNESS);
  }

  volume = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_VOLUME);
  if (volume) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        volume->thickness,
                                        AKB_ANIM_MATERIAL_VOLUME_THICKNESS,
                                        AKB_TEX_ROLE_VOLUME_THICKNESS);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &volume->attenuationDistance,
                                  AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_DISTANCE,
                                  1);
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  volume->attenuationColor.vec,
                                  AKB_ANIM_MATERIAL_VOLUME_ATTENUATION_COLOR,
                                  3);
  }

  anisotropy = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_ANISOTROPY);
  if (anisotropy) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        anisotropy->strength,
                                        AKB_ANIM_MATERIAL_ANISOTROPY,
                                        AKB_TEX_ROLE_ANISOTROPY);
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        anisotropy->rotation,
                                        AKB_ANIM_MATERIAL_ANISOTROPY_ROTATION,
                                        AKB_TEX_ROLE_ANISOTROPY);
  }

  dispersion = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DISPERSION);
  if (dispersion)
    count = akb_anim_binding_push(bindings,
                                  capacity,
                                  count,
                                  &dispersion->dispersion,
                                  AKB_ANIM_MATERIAL_DISPERSION,
                                  1);

  diffuse_transmission = (void*)ak_materialFeature(surface, AK_MATERIAL_FEATURE_DIFFUSE_TRANSMISSION);
  if (diffuse_transmission) {
    count = akb_material_scalar_binding(bindings,
                                        capacity,
                                        count,
                                        diffuse_transmission->factor,
                                        AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION,
                                        AKB_TEX_ROLE_DIFFUSE_TRANSMISSION);
    count = akb_material_color_binding(bindings,
                                       capacity,
                                       count,
                                       diffuse_transmission->color,
                                       AKB_ANIM_MATERIAL_DIFFUSE_TRANSMISSION_COLOR,
                                       3,
                                       AKB_TEX_ROLE_DIFFUSE_TRANSMISSION_COLOR);
  }

  return count;
}

static AkbAnimation *
akb_material_animation_new(AkDoc *doc,
                           AkbSharedDoc *doc_owner,
                           const AkbAnimationIndex *index,
                           AkMeshPrimitive *prim,
                           AkInstanceGeometry *instance,
                           const AkbCoordContext *coord,
                           int *ok) {
  AkResolvedMaterial resolved;
  AkbAnimBinding bindings[64];
  int binding_count;

  *ok = 1;
  if ((index && !index->count) || (!index && (!doc || !doc->lib.animations.first)))
    return NULL;

  memset(&resolved, 0, sizeof(resolved));
  if (!ak_materialResolve(prim, instance, UINT32_MAX, &resolved))
    return NULL;

  binding_count = akb_material_bindings(resolved.surface, bindings, 64);

  return akb_animation_new_for_bindings(doc,
                                        doc_owner,
                                        index,
                                        bindings,
                                        binding_count,
                                        coord,
                                        ok);
}

static int
akb_node_has_rotate(AkNode *node) {
  AkObject *object;

  if (!node || !node->transform)
    return 0;

  for (object = node->transform->base; object; object = object->next) {
    if ((AkTypeId)object->type == AKT_ROTATE)
      return 1;
  }

  for (object = node->transform->item; object; object = object->next) {
    if ((AkTypeId)object->type == AKT_ROTATE)
      return 1;
  }

  return 0;
}

static void
akb_baked_matrix_to_trs(const float m[16],
                        float *translation,
                        float *rotation,
                        float *scale,
                        const float *previous_rotation) {
  versor rotation_xyzw;

  akb_mat4_to_trs(m, translation, rotation_xyzw, scale);

  rotation[0] = rotation_xyzw[3];
  rotation[1] = rotation_xyzw[0];
  rotation[2] = rotation_xyzw[1];
  rotation[3] = rotation_xyzw[2];

  if (previous_rotation) {
    if (glm_vec4_dot(AKB_VEC4(rotation), AKB_VEC4(previous_rotation)) < 0.0f)
      glm_vec4_negate(AKB_VEC4(rotation));
  }
}

static AkbAnimation *
akb_animation_new_baked(AkDoc *doc,
                        AkbSharedDoc *doc_owner,
                        AkNode *node,
                        int *ok) {
  AkbAnimation *animation;
  AkBakedAnimation *baked;
  AkbAnimChannel channel;
  float *translations;
  float *rotations;
  float *scales;
  uint32_t i;

  baked = ak_nodeBakeAnimation(doc, node);
  if (!baked || !baked->count || !baked->times || !baked->matrices) {
    if (baked)
      ak_free(baked);
    return NULL;
  }

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    ak_free(baked);
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  animation->baked = baked;
  akb_shared_doc_retain(doc_owner);

  animation->baked_values = (float *)malloc((size_t)baked->count * 10 * sizeof(float));
  if (!animation->baked_values) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  translations = animation->baked_values;
  rotations = translations + (size_t)baked->count * 3;
  scales = rotations + (size_t)baked->count * 4;

  for (i = 0; i < baked->count; i++) {
    akb_baked_matrix_to_trs(baked->matrices + (size_t)i * 16,
                            translations + (size_t)i * 3,
                            rotations + (size_t)i * 4,
                            scales + (size_t)i * 3,
                            i > 0 ? rotations + (size_t)(i - 1) * 4 : NULL);
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_TRANSLATION;
  channel.value_width = 3;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = translations;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;

  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_ROTATION_QUAT;
  channel.value_width = 4;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = rotations;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;
  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  memset(&channel, 0, sizeof(channel));
  channel.target = AKB_ANIM_SCALE;
  channel.value_width = 3;
  channel.count = baked->count;
  channel.times = baked->times;
  channel.values = scales;
  channel.borrowed_times = 1;
  channel.borrowed_values = 1;
  channel.interpolation = AK_INTERPOLATION_LINEAR;
  if (!akb_animation_push(animation, &channel)) {
    akb_animation_release(animation);
    *ok = 0;
    return NULL;
  }

  return animation;
}

static int
akb_animation_prepare_baked_channel(AkbAnimChannel *channel,
                                    const float *times,
                                    uint32_t count,
                                    uint32_t target,
                                    uint32_t width,
                                    float time_offset,
                                    uint32_t clip_index,
                                    const char *clip_name) {
  size_t time_bytes;
  size_t value_bytes;
  uint32_t i;

  if (!channel || !times || !count || !target || !width
      || !isfinite(time_offset)
      || (size_t)count > SIZE_MAX / sizeof(float)
      || (size_t)count > SIZE_MAX / width
      || (size_t)count * width > SIZE_MAX / sizeof(float))
    return 0;

  memset(channel, 0, sizeof(*channel));

  time_bytes = (size_t)count * sizeof(float);
  value_bytes = (size_t)count * width * sizeof(float);

  channel->times = (float *)malloc(time_bytes);
  channel->values = (float *)malloc(value_bytes);
  if (!channel->times || !channel->values) {
    free(channel->times);
    free(channel->values);
    memset(channel, 0, sizeof(*channel));
    return 0;
  }

  for (i = 0; i < count; i++) {
    channel->times[i] = times[i] - time_offset;
    if (!isfinite(channel->times[i])) {
      free(channel->times);
      free(channel->values);
      memset(channel, 0, sizeof(*channel));
      return 0;
    }
  }

  channel->target = target;
  channel->value_width = width;
  channel->count = count;
  channel->interpolation = AK_INTERPOLATION_LINEAR;
  channel->clip_index = clip_index;
  channel->clip_name = clip_name;
  return 1;
}

static int
akb_animation_append_baked_clip(AkbAnimation *animation,
                               AkBakedAnimation *baked,
                               float time_offset,
                               uint32_t clip_index,
                               const char *clip_name) {
  AkbAnimChannel channels[3];
  uint32_t i;
  int pushed;

  if (!animation || !baked || !baked->count || !baked->times || !baked->matrices)
    return 1;

  memset(channels, 0, sizeof(channels));

  if (!akb_animation_prepare_baked_channel(&channels[0],
                                           baked->times,
                                           baked->count,
                                           AKB_ANIM_TRANSLATION,
                                           3,
                                           time_offset,
                                           clip_index,
                                           clip_name)
      || !akb_animation_prepare_baked_channel(&channels[1],
                                             baked->times,
                                             baked->count,
                                             AKB_ANIM_ROTATION_QUAT,
                                             4,
                                             time_offset,
                                             clip_index,
                                             clip_name)
      || !akb_animation_prepare_baked_channel(&channels[2],
                                             baked->times,
                                             baked->count,
                                             AKB_ANIM_SCALE,
                                             3,
                                             time_offset,
                                             clip_index,
                                             clip_name)) {
    for (i = 0; i < 3; i++) {
      free(channels[i].times);
      free(channels[i].values);
    }
    return 0;
  }

  for (i = 0; i < baked->count; i++) {
    akb_baked_matrix_to_trs(baked->matrices + (size_t)i * 16,
                            channels[0].values + (size_t)i * 3,
                            channels[1].values + (size_t)i * 4,
                            channels[2].values + (size_t)i * 3,
                            i > 0 ? channels[1].values + (size_t)(i - 1) * 4 : NULL);
  }

  for (pushed = 0; pushed < 3; pushed++) {
    if (!akb_animation_push(animation, &channels[pushed])) {
      for (i = (uint32_t)pushed; i < 3; i++) {
        free(channels[i].times);
        free(channels[i].values);
      }
      return 0;
    }
  }

  return 1;
}

static AkbAnimation *
akb_animation_new_baked_indexed(AkDoc *doc,
                                AkbSharedDoc *doc_owner,
                                const AkbAnimationIndex *index,
                                AkNode *node,
                                int *ok) {
  AkbAnimation *animation;
  AkAnimation *source;
  AkBakedAnimation *baked;
  const char *clip_name;
  uint32_t clip_index;
  uint32_t source_index;

  if (!doc || !doc->lib.animations.first || !node)
    return NULL;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  source_index = 0;
  for (source = doc->lib.animations.first; source; source = source->next, source_index++) {
    baked = ak_nodeBakeAnimationForAnimation(doc, node, source);
    if (!baked)
      continue;

    clip_index = source_index;
    clip_name = source->name;
    (void)akb_animation_index_clip_for_source(index,
                                              source,
                                              &clip_index,
                                              &clip_name);
    if (!akb_animation_append_baked_clip(animation,
                                        baked,
                                        0.0f,
                                        clip_index,
                                        clip_name)) {
      ak_free(baked);
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }

    ak_free(baked);
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static AkbAnimation *
akb_animation_new_baked_collada(AkDoc *doc,
                                AkbSharedDoc *doc_owner,
                                AkNode *node,
                                int *ok) {
  AkbAnimation *animation;
  AkAnimationClip *clip;
  AkBakedAnimation *baked;
  float clip_start;
  float clip_end;
  uint32_t clip_index;

  if (!doc || !doc->lib.animations.first || !node)
    return NULL;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  clip_index = 0;
  for (clip = doc->animationClips.first;
       clip;
       clip = clip->next, clip_index++) {
    baked = ak_nodeBakeAnimationForClip(doc, node, clip);
    if (!baked)
      continue;
    if (!ak_animationClipTimeRange(clip, &clip_start, &clip_end)
        || !isfinite(clip_start) || !isfinite(clip_end)
        || clip_end < clip_start) {
      ak_free(baked);
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
    if (!akb_animation_append_baked_clip(animation,
                                         baked,
                                         clip_start,
                                         clip_index,
                                         clip->name)) {
      ak_free(baked);
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
    ak_free(baked);
  }

  baked = ak_nodeBakeUnclippedAnimation(doc, node);
  if (baked) {
    if (!akb_animation_append_baked_clip(animation,
                                         baked,
                                         0.0f,
                                         clip_index,
                                         NULL)) {
      ak_free(baked);
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
    ak_free(baked);
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static AkbAnimation *
akb_animation_new(AkDoc *doc,
                  AkbSharedDoc *doc_owner,
                  AkNode *node,
                  const AkbAnimationIndex *index,
                  const AkbCoordContext *coord,
                  int *ok) {
  AkbAnimation *animation;
  AkAnimation *source;
  AkbAnimBinding bindings[64];
  AkContext context;
  uint32_t clip_index;
  int binding_count;
  int is_collada;
  int needs_bake;
  int is_gltf;

  *ok = 1;
  if ((index && !index->count) || (!index && (!doc || !doc->lib.animations.first)))
    return NULL;

  is_gltf = doc
            && doc->inf
            && (doc->inf->ftype == AK_FILE_TYPE_GLTF
                || doc->inf->ftype == AK_FILE_TYPE_GLB);
  is_collada = doc
               && doc->inf
               && doc->inf->ftype == AK_FILE_TYPE_COLLADA;
  needs_bake = ak_nodeNeedsBaking(node) || (!is_gltf && akb_node_has_rotate(node));

  if (needs_bake) {
    if (is_collada)
      animation = akb_animation_new_baked_collada(doc, doc_owner, node, ok);
    else if (index)
      animation = akb_animation_new_baked_indexed(doc, doc_owner, index, node, ok);
    else
      animation = akb_animation_new_baked(doc, doc_owner, node, ok);
    if (!animation || !*ok)
      return animation;
    binding_count = akb_node_visibility_bindings(node, bindings, 64);
    binding_count = akb_node_camera_bindings(node, bindings, 64, binding_count);
    binding_count = akb_node_light_bindings(node, bindings, 64, binding_count);
  } else {
    binding_count = akb_node_scene_bindings(node, bindings, 64);
  }

  if (!binding_count) {
    if (needs_bake)
      return animation;
    animation = akb_animation_new_baked(doc, doc_owner, node, ok);
    return animation;
  }

  if (!needs_bake) {
    animation = (AkbAnimation *)calloc(1, sizeof(*animation));
    if (!animation) {
      *ok = 0;
      return NULL;
    }

    animation->refcount = 1;
    animation->doc_owner = doc_owner;
    akb_shared_doc_retain(doc_owner);
  }

  if (index) {
    if (!akb_animation_collect_index(animation,
                                     index,
                                     bindings,
                                     binding_count,
                                     coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  } else {
    memset(&context, 0, sizeof(context));
    context.doc = doc;

    clip_index = 0;
    for (source = doc->lib.animations.first; source; source = source->next, clip_index++) {
      if (!akb_animation_collect_tree(animation,
                                      source,
                                      &context,
                                      bindings,
                                      binding_count,
                                      coord,
                                      clip_index,
                                      source->name)) {
        akb_animation_release(animation);
        *ok = 0;
        return NULL;
      }
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}

static AkbAnimation *
akb_morph_animation_new(AkDoc *doc,
                        AkbSharedDoc *doc_owner,
                        const AkbAnimationIndex *index,
                        AkInstanceMorph *morpher,
                        const AkbCoordContext *coord,
                        int *ok) {
  AkbAnimation *animation;
  AkbAnimBinding binding = {0};
  AkAnimation *source;
  AkContext context;
  uint32_t clip_index;

  *ok = 1;
  if (!morpher || !morpher->morph || !morpher->morph->targetCount)
    return NULL;
  if ((index && !index->count) || (!index && (!doc || !doc->lib.animations.first)))
    return NULL;

  binding.target = morpher;
  binding.kind = AKB_ANIM_MORPH_WEIGHTS;
  binding.width = morpher->morph->targetCount;

  animation = (AkbAnimation *)calloc(1, sizeof(*animation));
  if (!animation) {
    *ok = 0;
    return NULL;
  }

  animation->refcount = 1;
  animation->doc_owner = doc_owner;
  akb_shared_doc_retain(doc_owner);

  if (index) {
    if (!akb_animation_collect_index(animation,
                                     index,
                                     &binding,
                                     1,
                                     coord)) {
      akb_animation_release(animation);
      *ok = 0;
      return NULL;
    }
  } else {
    memset(&context, 0, sizeof(context));
    context.doc = doc;

    clip_index = 0;
    for (source = doc->lib.animations.first; source; source = source->next, clip_index++) {
      if (!akb_animation_collect_tree(animation,
                                      source,
                                      &context,
                                      &binding,
                                      1,
                                      coord,
                                      clip_index,
                                      source->name)) {
        akb_animation_release(animation);
        *ok = 0;
        return NULL;
      }
    }
  }

  if (!animation->count) {
    akb_animation_release(animation);
    return NULL;
  }

  return animation;
}
