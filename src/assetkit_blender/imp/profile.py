from __future__ import annotations

from ..assetkit import _profile_enabled, _profile_log

stats: dict[str, float | int] | None = None


def _reset_material_profile() -> None:
    global stats
    if not _profile_enabled():
        stats = None
        return
    stats = {
        "calls": 0,
        "cache_hits": 0,
        "created": 0,
        "cache_key_ms": 0.0,
        "new_ms": 0.0,
        "simple_ms": 0.0,
        "nodes_ms": 0.0,
        "props_ms": 0.0,
        "settings_ms": 0.0,
        "textures_ms": 0.0,
        "texture_node_calls": 0,
        "texture_node_cache_hits": 0,
        "texture_node_create_ms": 0.0,
        "texture_image_cache_hits": 0,
        "texture_image_refs": 0,
        "texture_image_loads": 0,
        "texture_image_find_ms": 0.0,
        "texture_image_ref_ms": 0.0,
        "texture_image_load_ms": 0.0,
        "texture_image_register_ms": 0.0,
        "animation_ms": 0.0,
        "total_ms": 0.0,
        "mesh_calls": 0,
        "mesh_alloc_ms": 0.0,
        "mesh_views_ms": 0.0,
        "mesh_topology_ms": 0.0,
        "mesh_uv_ms": 0.0,
        "mesh_color_ms": 0.0,
        "mesh_tangent_ms": 0.0,
        "mesh_update_ms": 0.0,
        "mesh_shading_ms": 0.0,
        "mesh_finish_ms": 0.0,
        "mesh_total_ms": 0.0,
        "finish_calls": 0,
        "finish_bind_shape_ms": 0.0,
        "finish_object_ms": 0.0,
        "finish_material_ms": 0.0,
        "finish_props_ms": 0.0,
        "finish_morph_ms": 0.0,
        "finish_skin_ms": 0.0,
        "finish_animation_ms": 0.0,
        "finish_instancing_ms": 0.0,
        "finish_total_ms": 0.0,
    }


def _record_material_profile(
    *,
    cache_hit: bool,
    cache_key_ms: float,
    new_ms: float,
    simple_ms: float,
    nodes_ms: float,
    props_ms: float,
    settings_ms: float,
    textures_ms: float,
    animation_ms: float,
    total_ms: float,
) -> None:
    current = stats
    if current is None:
        return

    current["calls"] = int(current["calls"]) + 1
    if cache_hit:
        current["cache_hits"] = int(current["cache_hits"]) + 1
    else:
        current["created"] = int(current["created"]) + 1

    current["cache_key_ms"] = float(current["cache_key_ms"]) + cache_key_ms
    current["new_ms"]       = float(current["new_ms"]) + new_ms
    current["simple_ms"]    = float(current["simple_ms"]) + simple_ms
    current["nodes_ms"]     = float(current["nodes_ms"]) + nodes_ms
    current["props_ms"]     = float(current["props_ms"]) + props_ms
    current["settings_ms"]  = float(current["settings_ms"]) + settings_ms
    current["textures_ms"]  = float(current["textures_ms"]) + textures_ms
    current["animation_ms"] = float(current["animation_ms"]) + animation_ms
    current["total_ms"]     = float(current["total_ms"]) + total_ms


def _log_material_profile(label: str) -> None:
    current = stats
    if current is None:
        return

    if int(current["calls"]):
        _profile_log(
            "material_profile "
            f"{label} calls={int(current['calls'])} "
            f"created={int(current['created'])} "
            f"cache_hits={int(current['cache_hits'])} "
            f"cache_key={float(current['cache_key_ms']):.3f}ms "
            f"new={float(current['new_ms']):.3f}ms "
            f"simple={float(current['simple_ms']):.3f}ms "
            f"nodes={float(current['nodes_ms']):.3f}ms "
            f"props={float(current['props_ms']):.3f}ms "
            f"settings={float(current['settings_ms']):.3f}ms "
            f"textures={float(current['textures_ms']):.3f}ms "
            f"tex_nodes={int(current.get('texture_node_calls', 0) or 0)} "
            f"tex_node_hits={int(current.get('texture_node_cache_hits', 0) or 0)} "
            f"tex_node_create={float(current.get('texture_node_create_ms', 0.0) or 0.0):.3f}ms "
            f"image_hits={int(current.get('texture_image_cache_hits', 0) or 0)} "
            f"image_refs={int(current.get('texture_image_refs', 0) or 0)} "
            f"image_loads={int(current.get('texture_image_loads', 0) or 0)} "
            f"image_find={float(current.get('texture_image_find_ms', 0.0) or 0.0):.3f}ms "
            f"image_ref={float(current.get('texture_image_ref_ms', 0.0) or 0.0):.3f}ms "
            f"image_load={float(current.get('texture_image_load_ms', 0.0) or 0.0):.3f}ms "
            f"image_register={float(current.get('texture_image_register_ms', 0.0) or 0.0):.3f}ms "
            f"animation={float(current['animation_ms']):.3f}ms "
            f"total={float(current['total_ms']):.3f}ms"
        )

    mesh_calls = int(current.get("mesh_calls", 0) or 0)
    if mesh_calls:
        _profile_log(
            "mesh_profile "
            f"{label} calls={mesh_calls} "
            f"alloc={float(current['mesh_alloc_ms']):.3f}ms "
            f"views={float(current['mesh_views_ms']):.3f}ms "
            f"topology={float(current['mesh_topology_ms']):.3f}ms "
            f"uv={float(current['mesh_uv_ms']):.3f}ms "
            f"color={float(current['mesh_color_ms']):.3f}ms "
            f"tangent={float(current['mesh_tangent_ms']):.3f}ms "
            f"update={float(current['mesh_update_ms']):.3f}ms "
            f"shading={float(current['mesh_shading_ms']):.3f}ms "
            f"finish={float(current['mesh_finish_ms']):.3f}ms "
            f"total={float(current['mesh_total_ms']):.3f}ms"
        )

    finish_calls = int(current.get("finish_calls", 0) or 0)
    if finish_calls:
        _profile_log(
            "finish_profile "
            f"{label} calls={finish_calls} "
            f"bind_shape={float(current['finish_bind_shape_ms']):.3f}ms "
            f"object={float(current['finish_object_ms']):.3f}ms "
            f"material={float(current['finish_material_ms']):.3f}ms "
            f"props={float(current['finish_props_ms']):.3f}ms "
            f"morph={float(current['finish_morph_ms']):.3f}ms "
            f"skin={float(current['finish_skin_ms']):.3f}ms "
            f"animation={float(current['finish_animation_ms']):.3f}ms "
            f"instancing={float(current['finish_instancing_ms']):.3f}ms "
            f"total={float(current['finish_total_ms']):.3f}ms"
        )


def _record_mesh_profile(phases: dict[str, float], total_ms: float) -> None:
    current = stats
    if current is None:
        return

    current["mesh_calls"] = int(current.get("mesh_calls", 0) or 0) + 1
    for name in (
        "alloc",
        "views",
        "topology",
        "uv",
        "color",
        "tangent",
        "update",
        "shading",
        "finish",
    ):
        key = f"mesh_{name}_ms"
        current[key] = float(current.get(key, 0.0) or 0.0) + float(phases.get(name, 0.0))

    current["mesh_total_ms"] = float(current.get("mesh_total_ms", 0.0) or 0.0) + total_ms


def _record_finish_profile(
    *,
    bind_shape_ms: float,
    object_ms: float,
    material_ms: float,
    props_ms: float,
    morph_ms: float,
    skin_ms: float,
    animation_ms: float,
    instancing_ms: float,
    total_ms: float,
) -> None:
    current = stats
    if current is None:
        return

    current["finish_calls"]          = int(current.get("finish_calls", 0) or 0) + 1
    current["finish_bind_shape_ms"]  = float(current.get("finish_bind_shape_ms", 0.0) or 0.0) + bind_shape_ms
    current["finish_object_ms"]      = float(current.get("finish_object_ms", 0.0) or 0.0) + object_ms
    current["finish_material_ms"]    = float(current.get("finish_material_ms", 0.0) or 0.0) + material_ms
    current["finish_props_ms"]       = float(current.get("finish_props_ms", 0.0) or 0.0) + props_ms
    current["finish_morph_ms"]       = float(current.get("finish_morph_ms", 0.0) or 0.0) + morph_ms
    current["finish_skin_ms"]        = float(current.get("finish_skin_ms", 0.0) or 0.0) + skin_ms
    current["finish_animation_ms"]   = float(current.get("finish_animation_ms", 0.0) or 0.0) + animation_ms
    current["finish_instancing_ms"]  = float(current.get("finish_instancing_ms", 0.0) or 0.0) + instancing_ms
    current["finish_total_ms"]       = float(current.get("finish_total_ms", 0.0) or 0.0) + total_ms
