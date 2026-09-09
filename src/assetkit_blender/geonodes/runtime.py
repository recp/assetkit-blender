"""Source updates run outside node evaluation; Geometry Nodes reads cached IDs."""

import os

import bpy
from bpy.app.handlers import persistent

from .cache import CACHE, PATH, fingerprint, sequence_path

NODES = {}
DIRTY = set()
LAST = {}
ERRORS = {}
BUSY = False
RENDER_LOCKS = {}
LOCK_PROPERTY = "assetkit_source_previous_render_lock"


def track(node):
    NODES[node.as_pointer()] = node
    sync_sequences()


def sync_sequences():
    scenes = {}
    for pointer, node in tuple(NODES.items()):
        try:
            if node.enabled and node.sequence and node.owner_scene:
                scenes[node.owner_scene.as_pointer()] = node.owner_scene
        except ReferenceError:
            NODES.pop(pointer, None)
    handlers = bpy.app.handlers.frame_change_pre
    if scenes and frame_changed not in handlers:
        handlers.append(frame_changed)
    elif not scenes and frame_changed in handlers:
        handlers.remove(frame_changed)
    # Lock before a render job starts, not from its worker-thread callback.
    for pointer, scene in scenes.items():
        if pointer not in RENDER_LOCKS:
            previous = bool(scene.get(LOCK_PROPERTY, scene.render.use_lock_interface))
            RENDER_LOCKS[pointer] = (scene, previous)
            scene[LOCK_PROPERTY] = previous
        scene.render.use_lock_interface = True
    for pointer in tuple(RENDER_LOCKS):
        if pointer not in scenes:
            scene, previous = RENDER_LOCKS.pop(pointer)
            try:
                scene.render.use_lock_interface = previous
                if LOCK_PROPERTY in scene:
                    del scene[LOCK_PROPERTY]
            except ReferenceError:
                pass


def changed(node, _context=None):
    track(node)
    DIRTY.add(node.as_pointer())
    if not BUSY and not bpy.app.timers.is_registered(flush):
        bpy.app.timers.register(flush, first_interval=0.05)


def budget():
    addon = bpy.context.preferences.addons.get(__package__.split(".geonodes")[0])
    mib = getattr(addon.preferences, "source_cache_mib", 512) if addon else 512
    return mib * 1024 * 1024


def _source_collection(node, entry):
    tree = node.node_tree
    selection = node.node_path.strip()
    if not selection:
        tree["assetkit_source_all"] = entry.collection
        collection = tree.get("assetkit_source_selection")
        if collection is not None:
            for obj in tuple(collection.objects):
                collection.objects.unlink(obj)
        return entry.collection
    selected = [obj for obj in entry.collection.objects
                if obj.get(PATH) == selection or str(obj.get(PATH, "")).startswith(selection + "/")]
    if not selected:
        raise ValueError("Selected node is absent from this file: " + selection)
    tree["assetkit_source_all"] = entry.collection
    collection = tree.get("assetkit_source_selection")
    if collection is None:
        collection = bpy.data.collections.new("AssetKit Source Selection")
        tree["assetkit_source_selection"] = collection
    for obj in tuple(collection.objects):
        collection.objects.unlink(obj)
    for obj in selected:
        collection.objects.link(obj)
    return collection


def _detach(node):
    tree = node.node_tree
    tree.nodes["Source"].inputs["Collection"].default_value = None
    if "assetkit_source_all" in tree:
        del tree["assetkit_source_all"]
    collection = tree.get("assetkit_source_selection")
    if collection is not None:
        for obj in tuple(collection.objects):
            collection.objects.unlink(obj)


def update(node, frame, stats):
    pointer = node.as_pointer()
    tree = node.node_tree
    if not node.enabled or not node.filepath:
        _detach(node)
        LAST.pop(pointer, None)
        node.status = "Disabled" if not node.enabled else "Choose a source file"
        return
    path = bpy.path.abspath(node.filepath, library=node.id_data.library)
    try:
        if node.sequence:
            path = sequence_path(path, frame, node.start_frame, node.first_frame,
                                 node.last_frame, node.frame_step, node.loop)
        request = (path, node.scene_index, node.coordinate_conversion, node.coordinate_system)
        if request not in stats:
            try:
                stats[request] = fingerprint(*request)
            except (OSError, ValueError) as exc:
                stats[request] = exc
        key = stats[request]
        if isinstance(key, Exception):
            raise key
        state = (key, node.node_path)
        if LAST.get(pointer) == state:
            return
        if key in ERRORS:
            raise ValueError(ERRORS[key])
        try:
            entry = CACHE.get(key)
        except Exception as exc:
            if len(ERRORS) >= 64:
                ERRORS.pop(next(iter(ERRORS)))
            ERRORS[key] = str(exc)
            raise
        collection = _source_collection(node, entry)
        tree.nodes["Source"].inputs["Collection"].default_value = collection
        if tuple(item.name for item in node.source_nodes) != entry.selections:
            node.source_nodes.clear()
            for path in entry.selections:
                node.source_nodes.add().name = path
        node.scene_names = " | ".join(f"{i}: {name}" for i, name in enumerate(entry.scenes))
        node.status = os.path.basename(key[0]) + f" · {len(collection.objects)} geometry objects"
        LAST[pointer] = state
        tree.update_tag()
    except Exception as exc:
        if node.missing == "EMPTY":
            _detach(node)
        LAST.pop(pointer, None)
        message = str(exc)
        holding = node.missing == "HOLD" and tree.nodes["Source"].inputs["Collection"].default_value is not None
        node.status = ("Holding previous geometry: " if holding else "No geometry: ") + message


def run(scene=None, dirty_only=False):
    global BUSY
    if BUSY or not NODES:
        return
    BUSY = True
    stats = {}
    try:
        for pointer, node in tuple(NODES.items()):
            try:
                owner = node.owner_scene
                if scene is not None and owner != scene:
                    continue
                if dirty_only and pointer not in DIRTY:
                    continue
                if not dirty_only and pointer not in DIRTY and not node.sequence:
                    continue
                update(node, owner.frame_current if owner else 1, stats)
                DIRTY.discard(pointer)
            except ReferenceError:
                NODES.pop(pointer, None)
                LAST.pop(pointer, None)
                DIRTY.discard(pointer)
        CACHE.trim(budget())
    finally:
        BUSY = False


def flush():
    if bpy.app.is_job_running("RENDER"):
        return 0.1
    run(dirty_only=True)
    return None


def forget(node):
    pointer = node.as_pointer()
    NODES.pop(pointer, None)
    LAST.pop(pointer, None)
    DIRTY.discard(pointer)
    sync_sequences()


def reload_sources():
    # Keep old, still-referenced entries until every consumer has switched.
    for key in tuple(CACHE.entries):
        if len(key) == 4:
            entry = CACHE.entries.pop(key)
            CACHE.entries[key + ("reload", entry.collection.as_pointer())] = entry
    ERRORS.clear()
    LAST.clear()
    DIRTY.update(NODES)
    run(dirty_only=True)
    CACHE.trim(0)


@persistent
def frame_changed(scene, _depsgraph=None):
    run(scene)


@persistent
def rebuild(_dummy=None):
    NODES.clear()
    LAST.clear()
    DIRTY.clear()
    ERRORS.clear()
    RENDER_LOCKS.clear()
    CACHE.restore()
    for tree in bpy.data.node_groups:
        if tree.bl_idname == "GeometryNodeTree":
            for node in tree.nodes:
                if node.bl_idname == "AssetKitGeometrySource":
                    changed(node)
    sync_sequences()
    for scene in bpy.data.scenes:
        if LOCK_PROPERTY in scene and scene.as_pointer() not in RENDER_LOCKS:
            scene.render.use_lock_interface = bool(scene[LOCK_PROPERTY])
            del scene[LOCK_PROPERTY]


@persistent
def before_save(_dummy=None):
    CACHE.trim(0)


@persistent
def render_start(scene):
    DIRTY.update(NODES)
    run(scene)


@persistent
def render_end(_scene):
    if DIRTY and not bpy.app.timers.is_registered(flush):
        bpy.app.timers.register(flush, first_interval=0.05)


HANDLERS = (("load_post", rebuild),
            ("undo_post", rebuild), ("redo_post", rebuild), ("save_pre", before_save),
            ("render_init", render_start), ("render_complete", render_end),
            ("render_cancel", render_end))


def register():
    for name, callback in HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback not in handlers:
            handlers.append(callback)
    # Blender restricts bpy.data while enabling add-ons.
    bpy.app.timers.register(rebuild, first_interval=0.0)


def unregister():
    for callback in (flush, rebuild):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)
    for name, callback in HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback in handlers:
            handlers.remove(callback)
    NODES.clear()
    sync_sequences()
    DIRTY.clear()
    LAST.clear()
    ERRORS.clear()
    CACHE.trim(0)
    CACHE.entries.clear()
