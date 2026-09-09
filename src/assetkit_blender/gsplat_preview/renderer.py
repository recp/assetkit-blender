"""Cached point attributes, instanced GPU quads and global back-to-front sorting."""

from collections import OrderedDict
import math

import gpu
import numpy as np

from . import shaders
from ..bridge.runtime import native_module


def attribute(cloud, name, width, field, dtype=np.float32):
    attr = cloud.attributes.get(name)
    count = len(cloud.points)
    if attr is None or len(attr.data) != count:
        raise ValueError(f'Missing Gaussian attribute: {name}')
    values = np.empty(count * width, dtype=dtype)
    attr.data.foreach_get(field, values)
    values = values.reshape(count, width)
    if not np.isfinite(values).all():
        raise ValueError(f'Non-finite Gaussian attribute: {name}')
    return values


def sh_degree(cloud):
    degree = 0
    for band in range(1, 5):
        if not all(f'radiance:sh_{i - 1}' in cloud.attributes
                   for i in range(band * band, (band + 1) ** 2)):
            break
        degree = band
    return degree


def pack(cloud, data=None):
    degree = sh_degree(cloud)
    count = len(cloud.points)
    stride = 3 + (degree + 1) ** 2
    if data is None:
        data = np.zeros((count, stride, 4), dtype=np.float32)
    data[:, 0, :3] = attribute(cloud, 'position', 3, 'vector')
    data[:, 1, :3] = attribute(cloud, 'scale', 3, 'vector')
    data[:, 2] = attribute(cloud, 'rotation', 4, 'value')[:, [1, 2, 3, 0]]
    data[:, 3] = attribute(cloud, 'radiance:base', 4, 'color')
    data[:, 0, 3] = np.clip(data[:, 3, 3], 0.0, 1.0)
    # Zero inherits the cloud's color space. Node-created radiance can opt into
    # linear RGB per point, including when geometry joins different sources.
    data[:, 3, 3] = (attribute(cloud, 'assetkit:color_space', 1, 'value', np.int32)[:, 0]
                     if 'assetkit:color_space' in cloud.attributes else 0)
    data[:, 1, 3] = (1 + attribute(cloud, 'assetkit:antialiased', 1, 'value', np.bool_)[:, 0].astype(np.float32)
                     if 'assetkit:antialiased' in cloud.attributes else 0)
    if np.any(data[:, 1, :3] < 0):
        raise ValueError('Negative Gaussian scale')
    for i in range((degree + 1) ** 2 - 1):
        data[:, i + 4, :3] = attribute(cloud, f'radiance:sh_{i}', 3, 'vector')
    return data, degree


def dimensions(count, width=2048):
    limit = gpu.capabilities.max_texture_size_get()
    width = min(width, limit, max(1, count))
    if count > width * limit:
        needed = (count + limit - 1) // limit
        width = min(limit, 1 << (needed - 1).bit_length())
    height = max(1, (count + width - 1) // width)
    if height > limit:
        raise ValueError('Gaussian preview exceeds the GPU texture limit')
    return width, height


def texture(data, width=2048):
    data = data.reshape(-1, data.shape[-1])
    channels = data.shape[-1]
    size = dimensions(len(data), width)
    if len(data) == size[0] * size[1]:
        padded = data
    else:
        padded = np.zeros((size[0] * size[1], channels), dtype=data.dtype)
        padded[:len(data)] = data
    format = ('RG' if channels == 2 else 'RGBA') + '32F'
    result = gpu.types.GPUTexture(size, format=format,
                                  data=gpu.types.Buffer('FLOAT', padded.size, padded.ravel()))
    result.filter_mode(False)
    return result


def depth_order(centers, direction):
    depth = centers @ direction
    native = native_module()
    if native is not None and hasattr(native, 'sort_depth'):
        return np.frombuffer(native.sort_depth(depth), dtype=np.uint32)
    return np.argsort(depth, kind='stable')


class Renderer:
    def __init__(self, entries, budget=1024 * 1024 * 1024):
        self.views = OrderedDict()
        self.uploads = 0
        self.sorts = 0
        self.projections = 0
        self.count = sum(len(cloud.points) for cloud, _matrix in entries)
        unique = {cloud.as_pointer(): cloud for cloud, _ in entries}
        texels = sum(len(cloud.points) * (3 + (sh_degree(cloud) + 1) ** 2)
                     for cloud in unique.values())
        size = dimensions(texels)
        # CPU atlas + upload staging + GPU atlas, source positions, transient
        # sorting buffers and up to four per-viewport projected/order caches.
        estimate = size[0] * size[1] * 16 * 3 + self.count * (12 + 8 + 96 + 64 * 4)
        if estimate > budget:
            raise ValueError('Gaussian preview exceeds its memory budget; increase it in AssetKit preferences')

        atlas = np.zeros((size[0] * size[1], 4), np.float32)
        self.centers = np.empty((self.count, 3), np.float32)
        self.indices = np.empty((self.count, 2), np.uint32)
        self.metadata = []
        sources = {}
        address = 0
        for pointer, cloud in unique.items():
            count = len(cloud.points)
            stride = 3 + (sh_degree(cloud) + 1) ** 2
            data, degree = pack(cloud, atlas[address:address + count * stride].reshape(count, stride, 4))
            sources[pointer] = (address, stride, degree, np.ascontiguousarray(data[:, 0, :3]))
            address += count * stride
        start = 0
        for cloud, matrix in entries:
            address, stride, degree, local = sources[cloud.as_pointer()]
            count = len(local)
            if not count:
                continue
            transform = np.asarray(matrix, dtype=np.float32)
            if not np.isfinite(transform).all():
                raise ValueError('Non-finite Gaussian object transform')
            self.centers[start:start + count] = local @ transform[:3, :3].T + transform[:3, 3]
            index = self.indices[start:start + count]
            index[:, 0] = address + np.arange(count, dtype=np.uint32) * stride
            index[:, 1] = len(self.metadata)
            self.metadata.append((matrix.copy(), degree,
                                  int(cloud.get('assetkit_gaussian_splat_color_space', 1)),
                                  bool(cloud.get('assetkit_gaussian_splat_antialiased', False)), local, start))
            start += count
        self.data = texture(atlas)
        self.uploads += 1
        self.compute, self.shader, self.batch = shaders.create()

    def update_transforms(self, entries):
        changed = False
        nonempty = [(cloud, matrix) for cloud, matrix in entries if len(cloud.points)]
        for i, ((_cloud, matrix), meta) in enumerate(zip(nonempty, self.metadata)):
            old, degree, colorspace, antialiased, local, start = meta
            if old == matrix:
                continue
            transform = np.asarray(matrix, np.float32)
            if not np.isfinite(transform).all():
                raise ValueError('Non-finite Gaussian object transform')
            self.centers[start:start + len(local)] = local @ transform[:3, :3].T + transform[:3, 3]
            self.metadata[i] = (matrix.copy(), degree, colorspace, antialiased, local, start)
            changed = True
        if changed:
            for cached in self.views.values():
                cached['signature'] = cached['sort_key'] = None

    def prepare(self, view, projection, size, key=0):
        signature = (tuple(map(tuple, view)), tuple(map(tuple, projection)), tuple(size))
        cached = self.views.pop(key, None)
        if cached is None:
            cached = {'signature': None, 'sort_key': None}
        self.views[key] = cached
        while len(self.views) > 4:
            self.views.popitem(last=False)
        if cached['signature'] == signature or not self.count:
            return cached

        direction = np.asarray(view, dtype=np.float32)[2, :3]
        sort_key = tuple(direction)
        if cached['sort_key'] != sort_key:
            order = depth_order(self.centers, direction)
            indices = self.indices[order]
            # Blender's public texture upload API accepts float buffers only.
            # Split addresses instead of rounding indices above 2**24 to float.
            packed = np.zeros((self.count, 4), dtype=np.float32)
            packed[:, 0] = indices[:, 0] & 65535
            packed[:, 1] = indices[:, 0] >> 16
            packed[:, 2] = indices[:, 1]
            cached['order'] = texture(packed)
            cached['sort_key'] = sort_key
            self.sorts += 1

        inverse_view = view.inverted()
        orthographic = abs(projection[3][3]) > 0.5
        objects = np.zeros((len(self.metadata), 8, 4), np.float32)
        for i, (matrix, degree, colorspace, antialiased, _local, _start) in enumerate(self.metadata):
            inverse_model = matrix.inverted_safe()
            camera = inverse_model @ inverse_view.translation
            parallel = inverse_model.to_3x3() @ (-inverse_view.col[2].to_3d())
            objects[i, :4] = np.asarray(view @ matrix, np.float32).T
            objects[i, 4] = (*camera, degree)
            objects[i, 5] = (*parallel, colorspace)
            objects[i, 6, :2] = (antialiased, orthographic)
        object_texture = texture(objects, width=8)
        if 'result' not in cached:
            cached['result'] = gpu.types.GPUTexture(dimensions(self.count * 3), format='RGBA32F')
        self.compute.uniform_sampler('splats', self.data)
        self.compute.uniform_sampler('order', cached['order'])
        self.compute.uniform_sampler('objects', object_texture)
        self.compute.image('projected', cached['result'])
        self.compute.uniform_float('projection', projection)
        self.compute.uniform_float('viewport', size)
        self.compute.uniform_int('pointCount', self.count)
        groups = math.ceil(self.count / 128)
        gpu.compute.dispatch(self.compute, min(groups, 65535), math.ceil(groups / 65535), 1)
        cached['signature'] = signature
        self.projections += 1
        return cached

    def draw(self, view, projection, size, key=0):
        if not self.count:
            return
        cached = self.prepare(view, projection, size, key)
        blend = gpu.state.blend_get()
        depth = gpu.state.depth_test_get()
        mask = gpu.state.depth_mask_get()
        try:
            gpu.state.blend_set('ALPHA_PREMULT')
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.depth_mask_set(False)
            self.shader.uniform_sampler('projected', cached['result'])
            self.batch.draw_instanced(self.shader, instance_count=self.count)
        finally:
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)
