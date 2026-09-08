#!/usr/bin/env python3
"""Exercise the real GPU preview in a separate, factory-startup Blender process.

blender --factory-startup --python tools/blender_gsplat_preview_check.py -- --spz capture.spz
"""

import argparse
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

import bpy
import gpu
from mathutils import Matrix, Quaternion, Vector
import numpy as np


def cloud(name, positions, coefficients, scales=None, rotations=None, opacity=None):
    count = len(positions)
    points = bpy.data.pointclouds.new(name)
    points.resize(count)

    def store(name, kind, field, values):
        attr = points.attributes.get(name) or points.attributes.new(name, kind, 'POINT')
        attr.data.foreach_set(field, np.asarray(values, np.float32).ravel())

    store('position', 'FLOAT_VECTOR', 'vector', positions)
    store('scale', 'FLOAT_VECTOR', 'vector', scales if scales is not None else [[.1, .1, .1]] * count)
    store('rotation', 'QUATERNION', 'value', rotations if rotations is not None else [[1, 0, 0, 0]] * count)
    store('radius', 'FLOAT', 'value', [.1] * count)
    alpha = np.asarray(opacity if opacity is not None else [.5] * count).reshape(count, 1)
    store('radiance:base', 'FLOAT_COLOR', 'color', np.concatenate((coefficients[:, 0], alpha), axis=1))
    for i in range(1, coefficients.shape[1]):
        store(f'radiance:sh_{i - 1}', 'FLOAT_VECTOR', 'vector', coefficients[:, i])
    return points


def projection(orthographic=False):
    if orthographic:
        return Matrix(((.5,0,0,.1),(0,.75,0,-.15),(0,0,-.02,-1.002),(0,0,0,1)))
    return Matrix(((1.5,0,.1,0),(0,2,-.15,0),(0,0,-1.002,-.2002),(0,0,-1,0)))


def sh_basis(degree, ray):
    # Independent associated-Legendre recurrence, not the shader polynomials.
    ray = np.asarray(ray, np.float64)
    ray /= np.linalg.norm(ray)
    z = ray[2]
    phi = math.atan2(ray[1], ray[0])
    result = []
    for ell in range(degree + 1):
        for signed_m in range(-ell, ell + 1):
            m = abs(signed_m)
            pmm = 1.0
            for k in range(1, m + 1):
                pmm *= -(2*k - 1)*math.sqrt(max(0, 1-z*z))
            previous, current = pmm, z*(2*m + 1)*pmm
            value = pmm if ell == m else current
            for k in range(m + 2, ell + 1):
                value = ((2*k - 1)*z*current - (k + m - 1)*previous)/(k - m)
                previous, current = current, value
            norm = math.sqrt((2*ell+1)/(4*math.pi)*math.factorial(ell-m)/math.factorial(ell+m))
            value *= norm
            if signed_m < 0:
                value *= math.sqrt(2)*math.sin(m*phi)
            elif signed_m > 0:
                value *= math.sqrt(2)*math.cos(m*phi)
            result.append(value)
    return np.array(result)


def read_projected(renderer, view, proj, size=(640, 480), key=0):
    result = renderer.prepare(view, proj, size, key)['result']
    return np.array(result.read()).reshape(-1, 4)[:renderer.count*3].reshape(-1, 3, 4)


def draw(renderer, view, proj, size=(63, 63), depth=1):
    off = gpu.types.GPUOffScreen(*size, format='RGBA32F')
    try:
        with off.bind():
            gpu.state.viewport_set(0, 0, *size)
            frame = gpu.state.active_framebuffer_get()
            frame.clear(color=(0, 0, 0, 0), depth=depth)
            old = (gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get())
            renderer.draw(view, proj, size)
            assert old == (gpu.state.blend_get(), gpu.state.depth_test_get(), gpu.state.depth_mask_get())
            return np.array(frame.read_color(0, 0, *size, 4, 0, 'FLOAT'))
    finally:
        off.free()


def check_math():
    from assetkit_blender.gsplat_preview.renderer import Renderer, depth_order, pack
    rng = np.random.default_rng(27)
    coefficients = rng.uniform(-.1, .1, (25, 25, 3))
    positions = rng.uniform(-.3, .3, (25, 3)) + [0, 0, -3]
    scales = rng.uniform(.01, .15, (25, 3))
    rotations = [tuple(Quaternion(Vector(v).normalized(), .7)) for v in rng.normal(size=(25, 3))]
    points = cloud('math', positions, coefficients, scales, rotations)
    model = Matrix(((1.5,.1,0,.1),(0,.7,.2,0),(0,0,1.1,0),(0,0,0,1)))
    renderer = Renderer([(points, model)])
    view = Matrix.Identity(4)
    for orthographic in (False, True):
        proj = projection(orthographic)
        output = read_projected(renderer, view, proj)
        order = depth_order(renderer.centers, np.asarray(view, np.float32)[2, :3])
        for slot, index in enumerate(order):
            world = np.asarray(model) @ np.append(positions[index], 1)
            clip = np.asarray(proj) @ world
            expected_center = clip[:3]/clip[3]
            np.testing.assert_allclose(output[slot, 0, :3], expected_center, atol=2e-6)
            ray = (model.inverted().to_3x3() @ Vector((0,0,-1)) if orthographic
                   else positions[index] - np.asarray(model.inverted().translation))
            expected_color = np.maximum(.5 + sh_basis(4, ray) @ coefficients[index], 0)
            expected_color = np.where(expected_color <= .04045, expected_color/12.92,
                                      ((expected_color+.055)/1.055)**2.4)
            np.testing.assert_allclose(output[slot, 2, :3], expected_color, atol=2e-6)
            basis = np.asarray(model)[:3, :3] @ np.asarray(Quaternion(rotations[index]).to_matrix()) @ np.diag(scales[index])
            jacobian = (np.asarray(proj)[:2, :3] - expected_center[:2, None]*np.asarray(proj)[3, :3])/clip[3]
            jacobian *= np.array([320,240])[:, None]
            covariance = jacobian @ basis @ basis.T @ jacobian.T + np.eye(2)*.3
            extent = output[slot, 2, 3]
            axes = output[slot, 1].reshape(2, 2).T*np.array([320,240])[:, None]/extent
            np.testing.assert_allclose(axes @ axes.T, covariance, rtol=1e-4, atol=.005)
        old = (renderer.uploads, renderer.sorts, renderer.projections)
        renderer.prepare(view, proj, (640,480))
        assert old == (renderer.uploads, renderer.sorts, renderer.projections)

    moved_view = Matrix.Translation((.2,.1,0))
    renderer.prepare(moved_view, projection(), (640,480))
    assert renderer.sorts == 1, 'Camera translation must not repeat depth sorting'
    renderer.update_transforms([(points, Matrix.Translation((0,0,-1)) @ model)])
    renderer.prepare(moved_view, projection(), (640,480))
    assert renderer.uploads == 1 and renderer.sorts == 2
    for key in range(6):
        renderer.prepare(view, projection(), (640,480), key)
    assert len(renderer.views) == 4
    packed, degree = pack(points)
    assert degree == 4
    np.testing.assert_allclose(packed[:, 3:, :3], coefficients, atol=1e-7)
    points.attributes.remove(points.attributes['radiance:sh_12'])
    assert pack(points)[1] == 2, 'An incomplete SH band must not be read'
    try:
        Renderer([(points, model)], budget=1)
    except ValueError:
        pass
    else:
        raise AssertionError('Preview memory budget not enforced')
    depths = np.array([-1e20, 4, -0., 0., -1e-20, 4, -2, 1e-20], np.float32)
    centers = np.zeros((len(depths),3), np.float32)
    centers[:,2] = depths
    np.testing.assert_array_equal(depth_order(centers, np.array([0,0,1], np.float32)),
                                  np.argsort(depths, kind='stable'))
    from assetkit_blender.bridge.runtime import native_module
    native = native_module()
    if hasattr(native, 'sort_depth'):
        depths = rng.normal(size=100000).astype(np.float32)
        depths[::13] = -0.
        depths[::17] = 0.
        np.testing.assert_array_equal(np.frombuffer(native.sort_depth(depths), np.uint32),
                                      np.argsort(depths, kind='stable'))
        assert not native.sort_depth(np.empty(0, np.float32))
        unaligned = np.ndarray(4, np.float32, buffer=bytearray(17), offset=1)
        unaligned[:] = [3, -2, 1, -2]
        np.testing.assert_array_equal(np.frombuffer(native.sort_depth(unaligned), np.uint32), [1,3,2,0])
        for invalid in (np.array([np.nan],np.float32), np.array([np.inf],np.float32),
                        np.zeros(4,np.float64), np.zeros(8,np.float32)[::2]):
            try:
                native.sort_depth(invalid)
            except (ValueError, BufferError):
                pass
            else:
                raise AssertionError('Invalid sort input accepted')
    print('Projection, affine covariance, SH 0..4, cache and exact-depth sorting OK', flush=True)


def check_pixels():
    from assetkit_blender.gsplat_preview.renderer import Renderer
    c0 = .28209479177387814
    red = np.array([[[(1-.5)/c0, -.5/c0, -.5/c0]]])
    green = np.array([[[-.5/c0, (1-.5)/c0, -.5/c0]]])
    front = cloud('front', [[0,0,-2]], red)
    back = cloud('back', [[0,0,-3]], green)
    view = Matrix.Identity(4)
    proj = projection()
    proj[0][2] = proj[1][2] = 0
    a = Renderer([(front, view), (back, view)])
    b = Renderer([(back, view), (front, view)])
    first = draw(a, view, proj)
    second = draw(b, view, proj)
    np.testing.assert_allclose(first, second, atol=2e-6)
    np.testing.assert_allclose(first[31,31], [.5,.25,0,.75], atol=2e-5)
    assert 0 < first[31,34,3] < first[31,31,3]
    assert first[0,0,3] == 0, 'A splat must not have visible rectangular corners'
    assert not draw(a, view, proj, depth=0).any(), 'Opaque foreground depth must occlude splats'
    linear = cloud('linear', [[0,0,-2]], np.full((1,1,3), (.25-.5)/c0), opacity=[.8])
    linear['assetkit_gaussian_splat_color_space'] = 2
    expected = .25
    np.testing.assert_allclose(draw(Renderer([(linear,view)]),view,proj)[31,31,:3],
                               np.full(3, expected*.8), atol=2e-5)
    front['assetkit_gaussian_splat_antialiased'] = True
    corrected = read_projected(Renderer([(front,view)]), view, proj, (63,63))[0,0,3]
    a0, c = (.1*1.5*31.5/2)**2, (.1*2*31.5/2)**2
    np.testing.assert_allclose(corrected, .5*math.sqrt(a0*c/((a0+.3)*(c+.3))), atol=2e-6)
    edge = cloud('near-offscreen', [[240,240,-.101], [0,0,.1], [0,0,-200]], np.zeros((3,1,3)),
                 scales=[[7,7,7]]*3)
    assert not draw(Renderer([(edge,view)]), view, proj).any(), 'Near/far/frustum rejection failed'
    empty = cloud('empty', [], np.empty((0,1,3)))
    assert not draw(Renderer([(empty, view)]), view, proj).any()
    print('Alpha falloff, multi-object compositing, depth, color space, mip filtering and clipping OK', flush=True)


def check_sample(path, output_dir):
    from assetkit_blender.importer import import_assetkit_file
    from assetkit_blender.gsplat_preview.renderer import Renderer
    objects = import_assetkit_file(str(path), set_viewport_shading=False)
    bpy.context.view_layer.update()
    obj = next(o for o in objects if o.type == 'POINTCLOUD')
    start = time.perf_counter()
    renderer = Renderer([(obj.data, obj.matrix_world)])
    upload_ms = (time.perf_counter()-start)*1000
    eye = Vector((0,-2,.7))
    view = (Matrix.Translation(eye) @ (-eye).to_track_quat('-Z','Y').to_matrix().to_4x4()).inverted()
    proj = Matrix(((1.125,0,0,0),(0,1.5,0,0),(0,0,-1.00002,-.0200002),(0,0,-1,0)))
    pixels = draw(renderer,view,proj,(1024,768))
    assert np.isfinite(pixels).all() and np.std(pixels[:,:,:3]) > .05
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        image = bpy.data.images.new('Gaussian Preview', width=1024, height=768, alpha=True, float_buffer=True)
        image.colorspace_settings.name = 'sRGB'
        display = pixels.copy()
        display[:,:,:3] = np.where(display[:,:,:3] <= .0031308, 12.92*display[:,:,:3],
                                   1.055*display[:,:,:3]**(1/2.4)-.055)
        image.pixels.foreach_set(display.ravel())
        image.filepath_raw = str(output_dir / 'gaussian-preview.png')
        image.file_format = 'PNG'
        image.save()
        bpy.data.images.remove(image)
    off = gpu.types.GPUOffScreen(1024,768,format='RGBA32F')
    samples, moving = [], []
    with off.bind():
        gpu.state.viewport_set(0,0,1024,768)
        frame = gpu.state.active_framebuffer_get()
        for i in range(20):
            frame.clear(color=(0,0,0,0),depth=1)
            start = time.perf_counter()
            renderer.draw(view,proj,(1024,768))
            frame.read_color(0,0,1,1,4,0,'FLOAT')  # Include GPU completion, not just submission.
            samples.append((time.perf_counter()-start)*1000)
        for i in range(20):
            moved = Matrix.Rotation(i*.002,4,'Y') @ view
            frame.clear(color=(0,0,0,0),depth=1)
            start = time.perf_counter()
            renderer.draw(moved,proj,(1024,768))
            frame.read_color(0,0,1,1,4,0,'FLOAT')
            moving.append((time.perf_counter()-start)*1000)
    off.free()
    assert renderer.uploads == 1
    print(f'{path.name}: {renderer.count} splats, upload {upload_ms:.1f} ms, '
          f'cached draw median {np.median(samples):.1f} ms, moving view {np.median(moving):.1f} ms', flush=True)


def start_ui_check(args):
    import addon_utils
    from assetkit_blender import gsplat_preview as preview
    from assetkit_blender.importer import import_assetkit_file
    if not args.spz:
        raise ValueError('--ui requires --spz')
    if bpy.data.filepath or {obj.name for obj in bpy.context.scene.objects} != {'Camera','Cube','Light'}:
        raise ValueError('UI check must run in a disposable --factory-startup Blender')
    assert addon_utils.enable('assetkit_blender', default_set=True) is not None
    for name in ('Camera','Cube','Light'):
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    # The import operator defaults to no selection; preview must not depend on it.
    properties = bpy.ops.assetkit.import_assetkit.get_rna_type().properties
    assert not properties['select_imported_objects'].default
    assert properties['set_viewport_shading'].default
    assert bpy.context.preferences.addons['assetkit_blender'].preferences.gaussian_preview
    imported = import_assetkit_file(str(args.spz), scene_was_empty=True)
    obj = next(o for o in imported if o.type == 'POINTCLOUD')
    assert obj.get(preview.ENABLED) and obj.display_type == 'BOUNDS'
    assert not obj.select_get()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    previous = obj[preview.DISPLAY]
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    space = area.spaces.active
    eye = Vector((0,-2,.7))
    space.clip_start, space.clip_end = .01, 1000
    space.overlay.show_overlays = True
    space.region_3d.view_location = (0,0,0)
    space.region_3d.view_distance = eye.length
    space.region_3d.view_rotation = (-eye).to_track_quat('-Z','Y')
    space.region_3d.view_perspective = 'PERSP'
    state = {'frames': 0, 'started': time.monotonic()}

    def capture():
        if not preview._renderer or state.get('pixels') is not None:
            return
        state['frames'] += 1
        if state['frames'] < 3:
            area.tag_redraw()
            return
        region = bpy.context.region
        state['size'] = (region.width, region.height)
        state['view'] = bpy.context.region_data.view_matrix.copy()
        state['projection'] = bpy.context.region_data.window_matrix.copy()
        state['pixels'] = np.array(gpu.state.active_framebuffer_get().read_color(
            0,0,region.width,region.height,4,0,'FLOAT'))

    handle = bpy.types.SpaceView3D.draw_handler_add(capture, (), 'WINDOW', 'POST_PIXEL')

    def finish():
        try:
            if state.get('pixels') is None:
                if preview._error or time.monotonic() - state['started'] > 20:
                    raise AssertionError(preview._error or 'Viewport preview did not draw')
                return .2
            bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
            renderer = preview._renderer
            assert (renderer.uploads, renderer.sorts, renderer.projections) == (1,1,1)
            raw = draw(renderer, state['view'], state['projection'], state['size'])
            display = np.where(raw[:,:,:3] <= .0031308, raw[:,:,:3]*12.92,
                                1.055*raw[:,:,:3]**(1/2.4)-.055)
            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                image = bpy.data.images.new('Viewport Preview', width=state['size'][0],
                                             height=state['size'][1], alpha=True, float_buffer=True)
                image.colorspace_settings.name = 'sRGB'
                image.pixels.foreach_set(state['pixels'].ravel())
                image.filepath_raw = str(args.output_dir / 'viewport-preview.png')
                image.file_format = 'PNG'
                image.save()
                bpy.data.images.remove(image)
            mask = raw[:,:,3] > .999
            assert mask.any()
            difference = np.median(np.abs(display[mask] - state['pixels'][mask,:3]))
            assert difference < .01, f'Viewport display transform mismatch: {difference}'
            revision = preview._revision
            value = tuple(obj.data.attributes['radiance:base'].data[0].color)
            obj.data.attributes['radiance:base'].data[0].color = (0,0,0,.01)
            obj.data.update_tag()
            bpy.context.view_layer.update()
            assert preview._revision > revision, 'Geometry edits must invalidate the GPU data'
            obj.data.attributes['radiance:base'].data[0].color = value
            obj.data.update_tag()
            with tempfile.TemporaryDirectory(prefix='assetkit-preview-ui-') as directory:
                path = str(Path(directory) / 'preview.blend')
                bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
                assert obj.display_type == 'BOUNDS'
                with bpy.data.libraries.load(path) as (_source, target):
                    target.objects = [obj.name]
                saved = target.objects[0]
                assert saved.display_type == previous and saved.get(preview.ENABLED)
                bpy.data.objects.remove(saved)
            preview.enable(obj, False)
            assert obj.display_type == previous and not preview._enabled and preview._renderer is None
            preview.enable(obj, True)
            addon_utils.disable('assetkit_blender', default_set=True)
            assert obj.display_type == previous and preview._handler is None
            print('Real viewport color, unchanged-frame cache, save and disable lifecycle OK', flush=True)
        except Exception:
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)
        sys.stdout.flush()
        os._exit(0)

    area.tag_redraw()
    bpy.app.timers.register(finish, first_interval=.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--spz', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--native-dir', type=Path)
    parser.add_argument('--ui', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    try:
        if args.native_dir:
            sys.path.insert(0, str(args.native_dir))
            import _assetkit_blender
            from assetkit_blender.bridge import runtime
            runtime._NATIVE_MODULE = _assetkit_blender
        if args.ui:
            start_ui_check(args)
            return
        check_math()
        check_pixels()
        if args.spz:
            check_sample(args.spz, args.output_dir)
        print('Gaussian preview checks passed', flush=True)
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    # This is a disposable factory-startup process, not the user's Blender.
    # Avoid overwriting their quit.blend recovery file on test completion.
    sys.stdout.flush()
    os._exit(0)


bpy.app.timers.register(main, first_interval=1)
