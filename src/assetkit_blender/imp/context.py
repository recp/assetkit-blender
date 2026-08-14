from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ImportState:
    coord_root:                     object | None
    root_objects:                   list
    node_objects:                   dict
    node_data:                      dict
    node_visibility:                dict | None
    node_animation_skip_indices:    set
    material_cache:                 dict
    mesh_cache:                     dict
    skin_cache:                     dict
    node_animation_deferred:        bool
    skin_animation_deferred:        bool
    deferred_skin_animations:       list
    mesh_cache_hits:                int
    defer_custom_normals:           bool
    has_node_visibility_animation:  bool
    has_node_animation:             bool
    dynamic_skin_animation_skip:    bool
    node_parent_cache:              dict
    preserve_tangents:              bool
    prototype_collections:          dict
    deferred_collection_instances: list
    preserve_hierarchy:             bool
    realized_instance_objects:      list
    deferred_scene_node_build:      dict | None
    compact_instance_plan:          dict | None
    compact_instance_objects:       list
    scene_bounds:                   tuple | None
