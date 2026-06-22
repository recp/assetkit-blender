# AssetKit ⇢ Blender

Blender add-on for importing and exporting 3D assets through [AssetKit](https://github.com/recp/assetkit)

## Formats

- glTF / GLB (2.0+)
- COLLADA DAE (1.4+, 1.5.0+)
- 3MF
- OBJ
- STL
- PLY

## Benchmarks

Here are local benchmark results from an M1 Max MacBook Pro, using Blender 4.5.10 LTS to include COLLADA:

| File | AssetKit median | Blender median | Blender / AssetKit |
| --- | ---: | ---: | ---: |
| BrainStem.dae | 61.1 ms | 6106.5 ms | 99.89x |
| Duck.dae | 1.7 ms | 5.8 ms | 3.44x |
| GearboxAssy.dae | 50.2 ms | 211.7 ms | 4.21x |
| NodePerformanceTest.glb | 16827.8 ms | 254056.5 ms | 15.10x |
| BoomBox.glb | 8.2 ms | 9.2 ms | 1.11x |
| DamagedHelmet.glb | 2.2 ms | 15.4 ms | 7.01x |
| WaterBottle.glb | 6.7 ms | 7.3 ms | 1.09x |
| ABeautifulGame.glb | 67.8 ms | 453.1 ms | 6.68x |
| AntiqueCamera.glb | 2.8 ms | 25.3 ms | 9.15x |
| MosquitoInAmber.glb | 18.5 ms | 26.9 ms | 1.45x |
| xyzrgb_dragon.obj | 24.4 ms | 82.8 ms | 3.39x |
| dragon_vrip.ply | 51.2 ms | 227.6 ms | 4.45x |
| 3DBenchy.stl | 8.4 ms | 38.4 ms | 4.59x |
...

---


Run repeatable importer benchmarks from Blender. `--download-suite` fetches the
review suite into the ignored `benchmark-assets/` cache, including Khronos glTF
sample assets, Khronos `glTF-Sample-Models/sourceModels` DAE files, and OBJ,
PLY, and STL comparison files:

Use Blender 4.5 LTS for DAE comparison runs.

The default suite only includes files where both importers complete. Some extra
DAE candidates are useful robustness cases but are kept out of the performance
table if Blender's legacy Collada importer exits during import.
The suite also includes coverage cases where AssetKit is not faster, so results
should be read per file rather than as a blanket speed claim.

```sh
/path/to/blender --background --factory-startup \
  --python tools/blender_import_benchmark.py -- \
  --download-suite --runs 3 --warmup 1 --markdown
```

The node stress test is much slower with Blender's built-in importer, so it can
be run separately by selecting the optional suite asset:

```sh
/path/to/blender --background --factory-startup \
  --python tools/blender_import_benchmark.py -- \
  --download-suite --suite-assets gltf-node-performance \
  --runs 1 --warmup 0 --markdown
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
`__init__.py` are at the zip root. Native bridge binaries and optional AssetKit
decoder libraries are packaged as platform wheels under `wheels/`.

## Release assets

Pushing a tag such as `v0.1.0` runs the package matrix on GitHub Actions and attaches
the platform zip files to the GitHub Release for that tag automatically.

## Install

Download the addon in releases page and use "Install from Disk" select the downloaded addon zip.
