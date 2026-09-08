"""Shared, byte-budgeted source geometry, loaded outside node evaluation."""

import json
import os
import re
import stat
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import quote

import bpy

from ..importer import import_assetkit_file
from ..load_options import make_load_options

OWNER = "assetkit_source_owner"
KEY = "assetkit_source_key"
PATH = "assetkit_source_node_path"
ID_COLLECTIONS = ("collections", "objects", "meshes", "pointclouds", "curves",
                  "armatures", "cameras", "lights", "materials", "node_groups",
                  "actions", "images", "textures")
GEOMETRY = {"MESH", "POINTCLOUD", "CURVE", "CURVES", "VOLUME", "FONT", "SURFACE"}


def sequence_path(path, frame, start, first, last, step, loop):
    """One contiguous run of # marks the frame number; no expressions are evaluated."""
    matches = list(re.finditer(r"#+", path))
    if len(matches) != 1:
        raise ValueError("Sequence path requires one frame placeholder, e.g. capture_####.spz")
    if last < first:
        raise ValueError("Last file frame must not precede first file frame")
    index = (int(frame) - start) // max(step, 1)
    count = last - first + 1
    number = first + (index % count if loop else max(0, min(index, count - 1)))
    match = matches[0]
    return path[:match.start()] + str(number).zfill(len(match[0])) + path[match.end():]


def fingerprint(path, scene_index):
    path = os.path.realpath(os.path.abspath(path))
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Source path is not a file")
    return (path, int(scene_index), info.st_mtime_ns, info.st_size)


def _snapshot():
    return {name: {item.as_pointer() for item in getattr(bpy.data, name, ())}
            for name in ID_COLLECTIONS}


def _created(before, owner):
    result = []
    for name in ID_COLLECTIONS:
        for item in getattr(bpy.data, name, ()):
            if item.as_pointer() not in before[name]:
                item[OWNER] = owner
                result.append((name, item))
    return result


def _dispose(ids):
    # Only remove this load's unreferenced IDs. Never purge the user's orphans.
    owned = set()
    for _name, item in ids:
        try:
            if item.as_pointer():
                owned.add(item)
        except ReferenceError:
            pass
    if not owned:
        return
    users = bpy.data.user_map(subset=owned)
    dependencies, protected = {}, set()
    for item, references in users.items():
        if item.use_fake_user or any(user not in owned for user in references):
            protected.add(item)
        for user in references & owned:
            dependencies.setdefault(user, []).append(item)
    pending = list(protected)
    while pending:
        for item in dependencies.get(pending.pop(), ()):
            if item not in protected:
                protected.add(item)
                pending.append(item)
    bpy.data.batch_remove(ids=owned - protected)


def _geometry_bytes(ids):
    sizes = {"FLOAT": 4, "INT": 4, "FLOAT_VECTOR": 12, "FLOAT_COLOR": 16,
             "BYTE_COLOR": 4, "BOOLEAN": 1, "FLOAT2": 8, "INT8": 1,
             "INT32_2D": 8, "QUATERNION": 16, "FLOAT4X4": 64}
    total = 0
    for name, item in ids:
        total += 1024
        if name in {"meshes", "pointclouds", "curves"}:
            for attr in getattr(item, "attributes", ()):
                total += len(attr.data) * sizes.get(attr.data_type, 16)
            if name == "meshes":
                total += len(item.polygons) * 4
        elif name == "images":
            total += item.size[0] * item.size[1] * max(item.channels, 4) * 4
    return total


def node_paths(nodes):
    paths, counts, components = {}, {}, {}
    for index, node in enumerate(nodes):
        name = quote(node.name or "(unnamed)", safe=" -_.")
        key = (node.parent_index, name)
        ordinal = counts.get(key, 0)
        counts[key] = ordinal + 1
        components[index] = f"{name}[{ordinal}]"
    for index in range(len(nodes)):
        chain, seen, current = [], set(), index
        while current >= 0 and current not in paths:
            if current in seen or current >= len(nodes):
                raise ValueError("Invalid source node hierarchy")
            seen.add(current)
            chain.append(current)
            current = nodes[current].parent_index
        prefix = paths.get(current, "")
        for child in reversed(chain):
            prefix += "/" + components[child]
            paths[child] = prefix
    return paths


@dataclass
class Entry:
    key: tuple
    collection: object
    ids: list
    size: int
    selections: tuple
    scenes: tuple


def load(key):
    before = _snapshot()
    owner = uuid.uuid4().hex
    try:
        storage = bpy.data.collections.new("AssetKit Source Data")
        context = {}
        objects = import_assetkit_file(
            key[0], collection=storage, preserve_hierarchy=True,
            load_options=make_load_options(scene_index=key[1], triangulate=False,
                                           texture_loading="IMMEDIATE", scene_bounds=False),
            set_viewport_shading=False, clean_viewport_overlays=False,
            _source_context=context,
        )
        output = bpy.data.collections.new("AssetKit Source " + os.path.basename(key[0]))
        paths = node_paths(context["nodes"])
        selections = set()
        for index, obj in enumerate(objects):
            if obj.type not in GEOMETRY and not (obj.type == "EMPTY" and obj.instance_collection):
                continue
            if obj.hide_render:
                continue
            parent = obj
            node_index = -1
            while parent is not None and node_index < 0:
                node_index = context["objects"].get(parent.as_pointer(), -1)
                parent = parent.parent
            path = paths.get(node_index, f"/Geometry[{index}]")
            obj[PATH] = path
            prefix = ""
            for component in path.split("/")[1:]:
                prefix += "/" + component
                selections.add(prefix)
            output.objects.link(obj)
        if not output.objects:
            raise ValueError("Selected source scene contains no geometry")
        output[KEY] = json.dumps(key)
        output["assetkit_source_selections"] = json.dumps(sorted(selections))
        scenes = tuple(context["scene_info"].get("names") or ())
        output["assetkit_source_scenes"] = json.dumps(scenes)
        # Keep parents and prototype collections alive with the cached source.
        output["assetkit_source_storage"] = storage
        ids = _created(before, owner)
        size = _geometry_bytes(ids)
        output["assetkit_source_bytes"] = size
        return Entry(key, output, ids, size, tuple(sorted(selections)), scenes)
    except Exception:
        ids = _created(before, owner)
        # Drop only the internal storage pointer before disposing its owner.
        for name, item in ids:
            if name == "collections" and "assetkit_source_storage" in item:
                del item["assetkit_source_storage"]
        _dispose(ids)
        raise


class SourceCache:
    def __init__(self):
        self.entries = OrderedDict()
        self.loads = 0
        self.hits = 0

    def get(self, key):
        entry = self.entries.get(key)
        if entry is None:
            entry = load(key)
            self.entries[key] = entry
            self.loads += 1
        else:
            self.hits += 1
        self.entries.move_to_end(key)
        return entry

    def trim(self, limit, keep=()):
        total = sum(entry.size for entry in self.entries.values())
        for key, entry in list(self.entries.items()):
            if total <= limit:
                break
            if key in keep or entry.collection.users:
                continue
            total -= entry.size
            del self.entries[key]
            if "assetkit_source_storage" in entry.collection:
                del entry.collection["assetkit_source_storage"]
            _dispose(entry.ids)
        return total

    def restore(self):
        self.entries.clear()
        owned = {}
        for name in ID_COLLECTIONS:
            for item in getattr(bpy.data, name, ()):
                if owner := item.get(OWNER):
                    owned.setdefault(owner, []).append((name, item))
        for collection in bpy.data.collections:
            if not collection.get(KEY):
                continue
            key = tuple(json.loads(collection[KEY]))
            if key in self.entries:
                key += ("restored", collection.as_pointer())
            self.entries[key] = Entry(
                key, collection, owned.get(collection.get(OWNER), []),
                int(collection.get("assetkit_source_bytes", 0)),
                tuple(json.loads(collection.get("assetkit_source_selections", "[]"))),
                tuple(json.loads(collection.get("assetkit_source_scenes", "[]"))),
            )


CACHE = SourceCache()
