# AssetIO Blender

Blender add-on for importing 3D assets through AssetKit.

## Formats

- glTF / GLB
- COLLADA DAE
- OBJ
- STL
- PLY

## AssetKit

AssetKit can be provided as a submodule or an external checkout. The build looks for it in this order:

1. `-DASSETKIT_ROOT=/path/to/assetkit`
2. `ASSETKIT_ROOT` environment variable
3. `../assetio`
4. `deps/assetkit`
5. system install paths

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

The bridge is written to `assetio_blender/` as `_assetkit_blender.*`. If it is not present, the add-on can still use the configured AssetKit shared library through `ctypes`.

## Install

Install or symlink the `assetio_blender` package into Blender's add-ons directory, then enable `AssetIO Blender` in Preferences.

If needed, set the AssetKit shared library path in:

```text
Edit > Preferences > Add-ons > AssetIO Blender
```

## Import

```text
File > Import > AssetKit
```
