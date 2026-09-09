# Geometry Nodes

AssetKit's nodes work in standard Blender. Open a Geometry Nodes tree on a host
object, then choose **Add > AssetKit**. Connect the source's Geometry output to
Group Output, or process it with other nodes first.
The file source is also available under **Add > Input > Import > AssetKit File / Sequence**.

## Sources

**File / Sequence Source** loads through AssetKit. It outputs all geometry in the
file's active/default scene as instances, preserving the source transforms and
materials. It does not merge every mesh into one or choose an arbitrary mesh.
Cameras and lights are not part of the geometry output. Loading a source does not
replace the Blender scene's world, timeline range or import metadata.

- **Scene Index:** `-1` selects the active/default source scene. Other values are
  zero-based indices; the node lists the scene names after loading.
- **Node:** leave empty for all geometry, or choose a source node and its
  descendants. Paths use source names, not Blender's renamed objects. Sibling
  ordinals distinguish duplicate names. Changing this selection reuses the
  loaded scene.
- **Enabled:** disabling a source disconnects its geometry.
- **Coordinate Mode / Target Coordinates:** the same options as normal import.
  Sources loaded with different coordinate settings have separate cache entries.
- **Reload Sources:** reloads shared sources and their external geometry buffers.

The source is an add-on-managed node group backed by Collection Info, not a
native file-reading evaluator. File and sequence settings are node properties,
not field-driven input sockets. Ordinary Geometry Nodes evaluation reads the
loaded Blender data without calling AssetKit again.

**Translation**, **Rotation**, **Scale** and **Global Scale** inputs place the source as a whole,
after its imported transforms. They operate on instances, leaving shared mesh
and Gaussian attributes unchanged, and do not reload the file. Rotation can
adjust the up axis; Global Scale uniformly adjusts units. Normal blocking and
progressive imports expose the same Global Scale option and apply it through
an import root, preserving animation channels. Existing source nodes saved
before these inputs were added keep working; add a new source node to use them.

**Object Source** references an existing Blender object through Object Info.
Use this when the asset is already imported. It adds no file loading or source
cache. Choose an object other than the host to avoid a dependency cycle.

## File sequences

Enable **Sequence** and replace the numbered part of the path with `#` characters,
for example `capture_####.spz`. The pattern has exactly one number placeholder;
four hashes produce names such as `capture_0001.spz`.

- **Timeline:** the Blender scene whose current frame selects the file.
- **First File / Last File:** inclusive file-number range.
- **Start:** timeline frame at which the first file is shown.
- **Hold Frames:** how many timeline frames each file lasts.
- **Loop:** repeat the range. Otherwise, frames outside the range use the first
  or last file.
- **Missing / Invalid:** output Empty or Hold Previous geometry and display the
  error on the node. Hold Previous depends on the last successfully loaded file,
  so use Empty when frame order must not affect the result.

For example, first file `10`, last file `12`, start `1` and hold `2` display files
10, 10, 11, 11, 12, 12 on timeline frames 1–6. There is no interpolation between
files or subframes.

Sequences update during playback, scrubbing and animation rendering. A cache
miss loads synchronously, so a new large frame can pause playback. Cached frames
reuse their Blender data. An enabled sequence temporarily enables the timeline
scene's **Render > Lock Interface**, keeping viewport access out of render-time
data updates. Its previous setting is restored when that scene no longer has an
enabled sequence, or when the add-on is disabled.

## Point operations

**Crop Points** keeps points or mesh vertices inside an axis-aligned Min/Max box
in the input geometry's space. It deletes outside points; it is not a mesh-plane
clipping operation.

**Splat Opacity** multiplies the alpha component of `radiance:base`, leaving its
RGB coefficients unchanged. Use it on imported Gaussian point clouds.

Both helpers use built-in nodes, with no per-point Python work. They realize
incoming instances to edit the geometry. Add them only when needed; the source
itself keeps instances intact. These helpers do not add a Gaussian renderer or
convert an ordinary mesh into trained splats. Blender builds without a native
Gaussian splat type retain the imported attributes on ordinary point clouds.
On those builds, realizing a rotated or scaled Gaussian instance does not bake
its custom scale, quaternion or SH attributes. For splats, apply these helpers
before instance transforms and keep the final placement at the instance level.

**Points to Gaussians** initializes missing radiance, scale and rotation
attributes on a point cloud. Color is scene-linear; Opacity, per-axis Scale and
Rotation set the new splats' appearance. Existing attributes take precedence,
including authored SH coefficients. This does not reconstruct or train a capture.
Use Blender's Mesh to Points first if the input is a mesh.

**Gaussians to Points** uses ordinary point display with the chosen Radius.
It saves `radiance:base` as `assetkit:radiance_base`, keeping scale, rotation
and higher SH attributes. Points to Gaussians restores the saved radiance.
These groups operate on direct geometry, not inside instances, and do not
realize them automatically. Work on the source cloud before instancing it.

In standard Blender these are attribute groups for AssetKit's viewport preview,
not native EEVEE/Cycles Gaussian types. A Geometry Nodes host with a point-cloud
output can use **N > AssetKit > Gaussian Preview**, including a mesh host.

## Memory and updates

File sources share a cache keyed by resolved path, source scene, file size and
modification time. Reusing a file or returning to a cached frame does not decode
it again. File timestamps are checked when a source is updated, not by an idle
filesystem watcher. Use Reload Sources after changing a static source or its
external geometry buffers. Image datablocks use Blender's image cache; reload
changed textures in the Image Editor.

**Preferences > Add-ons > AssetKit > Geometry Source Cache (MiB)** controls the
estimated source-data budget, initially 512 MiB. Unused entries are evicted
oldest-first. Current sources remain resident even when larger than the budget.
This is not a cap on total Blender memory: evaluated geometry, GPU data and
temporary import buffers can use additional memory.

Saving a `.blend` retains referenced source data and drops unused cache entries.
Keep the source files available for reloads and later sequence frames. Cache
cleanup only removes data created by these loads; it does not purge unrelated
Blender data or data that your scene still references.

Normal import creates no source helpers and installs no sequence frame handler.
The frame handler is active only while an enabled sequence exists.
