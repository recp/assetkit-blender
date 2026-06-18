# AssetKit

Blender add-on for importing and exporting 3D assets through AssetKit.

## Formats

- glTF / GLB (2.0+)
- COLLADA DAE (1.4+, 1.5.0+)
- 3MF
- OBJ
- STL
- PLY

## AssetKit

AssetKit can be provided as a submodule or an external checkout. The build looks for it in this order:

1. `-DASSETKIT_ROOT=/path/to/assetkit`
2. `ASSETKIT_ROOT` environment variable
3. sibling local checkout `../assetio`
4. sibling local checkout `../assetkit`
5. `deps/assetkit`
6. system install paths

For local development next to the AssetKit repository, build `../assetio` once and the Blender bridge will use that checkout by default for both Python 3.13 and 3.14 build directories.

For a fresh clone:

```sh
git submodule update --init --recursive
```

## Build

Build AssetKit, then build the native Blender bridge with Blender's Python:

```sh
cmake -S deps/assetkit -B deps/assetkit/build -DAK_SHARED=ON
cmake --build deps/assetkit/build
cmake -S . -B build -DASSETKIT_ROOT=deps/assetkit -DPython3_EXECUTABLE=/path/to/blender/python
cmake --build build
```

The bridge is written to `assetkit_blender/` as `_assetkit_blender.*`. If it is not present, the add-on can still use the configured AssetKit shared library through `ctypes`.

## Benchmarks

Run repeatable importer benchmarks from Blender. `--download-suite` fetches the
review suite into the ignored `benchmark-assets/` cache, including Khronos glTF
sample assets and OBJ, PLY, and STL comparison files:

```sh
/path/to/blender --background --factory-startup \
  --python tools/blender_import_benchmark.py -- \
  --download-suite --runs 3 --warmup 1 --markdown
```

The node stress test is much slower with Blender's built-in importer, so it can
be run separately:

```sh
/path/to/blender --background --factory-startup \
  --python tools/blender_import_benchmark.py -- \
  --download-suite --suite-assets gltf-node-performance \
  --runs 1 --warmup 0 --markdown
```

## Production package

Build and validate a Blender Extensions package zip with one command:

```sh
python3 tools/release_extension.py --blender /path/to/blender
```

To include Blender 4.5/5.0 support in the same platform package, add Python
3.11:

```sh
python3 tools/release_extension.py --blender /path/to/blender --extra-python python3.11
```

The zip is written to `dist/`.

For repeat packaging after the native bridge is already built:

```sh
python3 tools/package_extension.py --blender /path/to/blender --platform auto
```

The release script stages the extension so `blender_manifest.toml` and
`__init__.py` are at the zip root and native AssetKit runtime libraries are
included.

## Release assets

Pushing a tag such as `v0.1.0` runs the package matrix and attaches the five
platform zip files to the GitHub Release for that tag.

## Install

Install or symlink the `assetkit_blender` package into Blender's add-ons directory, then enable `AssetKit` in Preferences.

If needed, set the AssetKit shared library path in:

```text
Edit > Preferences > Add-ons > AssetKit
```

## Import

```text
File > Import > AssetKit
```
