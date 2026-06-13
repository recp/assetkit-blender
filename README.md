# AssetKit Blender

Blender add-on for importing and exporting 3D assets through AssetKit.

## Formats

- glTF / GLB
- 3MF
- COLLADA DAE
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

## Install

Install or symlink the `assetkit_blender` package into Blender's add-ons directory, then enable `AssetKit Blender` in Preferences.

If needed, set the AssetKit shared library path in:

```text
Edit > Preferences > Add-ons > AssetKit Blender
```

## Import

```text
File > Import > AssetKit
```
