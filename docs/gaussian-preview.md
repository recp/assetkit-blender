# Gaussian preview

Gaussian SPZ, L-GSC, PLY and glTF imports keep their positions, per-axis scales,
quaternions, opacity and spherical harmonics in a Blender PointCloud. The
preview reads those attributes without replacing the cloud with a mesh.
It also reads evaluated point-cloud outputs from Geometry Nodes. The conversion
groups are available under **Add > AssetKit** in the node editor.

## Viewing a capture

Ordinary import enables the GPU preview and switches to Solid shading. To turn
this off for future imports, disable **Gaussian Preview on Import** in the
AssetKit add-on preferences. **Select Imported Objects** does not affect the
preview. Turning off **Set Viewport Shading** in the import options leaves the
viewport unchanged and does not enable the preview automatically.

For a previously imported cloud, select it, move the pointer over the 3D
Viewport and press **N** to open the right sidebar. Open its **AssetKit** tab,
then **Gaussian Preview > Enable Preview**. The same button disables
the preview and restores the object's previous viewport display setting.
While enabled, the ordinary point display uses Bounds, so Blender's point
overlays do not draw a second layer of square markers over the splats.

The preview draws oriented Gaussian ellipses with smooth opacity and
view-dependent SH color, including SH degrees 0–4. sRGB radiance is decoded
after SH evaluation, before blending. For sRGB captures this is an approximation:
the glTF Gaussian specification requires blending in the capture's color space.
Linear-RGB captures do not need this conversion. Captures marked antialiased use the
projected-area opacity correction. The original coefficients are unchanged.
Ellipses are clipped at three standard deviations from their centers.

This is a **Solid/Wireframe viewport preview**, not an EEVEE or Cycles F12
renderer. Material Preview and Rendered shading still show the ordinary point
cloud on Blender versions without native Gaussian support. Studio lights and
material assignments do not relight the GPU preview. A Blender build with the
native Gaussian point-cloud type uses that type instead.

## Selecting and separating points

Select one cloud. In the same panel, **Edit Points** disables the custom preview and enters
Blender's point-cloud Edit Mode. Use Blender's selection tools, then
**Separate Selected** to move selected points into another cloud. Attributes
stay with their points; the panel's operation also preserves Gaussian color
space and antialiasing metadata, which Blender's separate operation alone does
not copy. This does not generate a mesh or retrain the capture.
**Finish Editing** returns to Object Mode. Select the clouds you want to view
and use **Enable Preview** again. Hide an object to isolate the others.

## Data and performance

Point attributes are uploaded on first use and refreshed after geometry changes.
Instances of the same cloud share the GPU attribute data. Object transforms
update placement without uploading the attributes again. Perspective views sort
splats globally by distance from the camera across visible clouds. Camera movement
updates that order; rotation in place only updates projection and shading.
Orthographic views use depth along the viewing direction. Unchanged views reuse
both results.

Projection and SH run once per splat in a compute pass. Drawing uses instances of one
shared quad; it does not create Blender mesh vertices or faces. Up to four
viewport results are cached. **Gaussian Preview Budget (MiB)** limits the
estimated preview data and working-buffer footprint. If a cloud exceeds the
budget or GPU texture limits, the preview reports it and restores ordinary
point display. Disabling the preview releases its cache.

Opaque scene geometry can occlude splats. Depth ordering uses splat centers,
as in a raster splat renderer; it is not ray-traced transparency through
intersecting surfaces. Captured background shells, outliers and incomplete
regions remain part of the source. The preview does not crop or repair them.

Saving a `.blend` restores ordinary point display in the saved copy, so it can
be opened without the add-on. With AssetKit enabled, the preview resumes on
load. It adds no material, Geometry Nodes modifier or helper object.
