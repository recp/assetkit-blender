# AssetKit-Blender

Blender add-on for importing and exporting 3D assets through [AssetKit](https://github.com/recp/assetkit)

👉  **Blender 5 removed the built-in COLLADA/DAE importer and exporter. AssetKit-Blender brings DAE support back to current Blender releases**, while also adding
a **fast**, native path for **other formats** like glTF/GLB, OBJ, STL, PLY, and 3MF import/export. 

## Formats

- glTF / GLB (2.0+)
- COLLADA DAE (1.4+, 1.5.0+)
- 3MF
- OBJ
- STL
- PLY


## Install to Blender

After a release a tag e.g. *v0.1.0*, [GitHub Actions](https://github.com/recp/assetkit-blender/actions/) builds package for multiple platforms then attaches
the generated platform zip files to the *GitHub Release* for that tag automatically. 

1. Download the zip for your platform from:
   https://github.com/recp/assetkit-blender/releases/latest

2. In Blender, install it with:
   Edit > Preferences > Add-ons > Install from Disk

3. Enable the add-on.

4. Follow repo to get/report bugfixes and get new features asap

## Benchmarks

Here are local benchmark results from an M1 Max MacBook Pro, measured with `tools/benchmark_review_imports.sh`.

DAE Blender builtin results are measured with Blender 4.5.10 LTS because Blender 5.x no longer includes the COLLADA importer. Other Blender builtin results are measured with Blender 5.1.2.


| File | AssetKit | AssetKit Blender Addon (+AssetKit) | Blender | Blender / AssetKit Blender |
| --- | ---: | ---: | ---: | ---: |
| BrainStem.dae | 33.0 ms | 60.7 ms | 6309.8 ms | 104.01x |
| Duck.dae | 0.8 ms | 1.7 ms | 5.5 ms | 3.25x |
| GearboxAssy.dae | 30.0 ms | 53.9 ms | 216.0 ms | 4.01x |
| NodePerformanceTest.glb | 103.6 ms | 8912.2 ms | 185195.6 ms | 20.78x |
| BoomBox.glb | 0.3 ms | 1.8 ms | 12.5 ms | 6.94x |
| DamagedHelmet.glb | 0.3 ms | 2.5 ms | 29.6 ms | 11.79x |
| WaterBottle.glb | 0.3 ms | 1.7 ms | 10.1 ms | 6.09x |
| ABeautifulGame.glb | 11.4 ms | 63.8 ms | 773.9 ms | 12.12x |
| AntiqueCamera.glb | 0.4 ms | 2.6 ms | 42.0 ms | 16.26x |
| MosquitoInAmber.glb | 0.4 ms | 2.9 ms | 40.6 ms | 13.92x |
| xyzrgb_dragon.obj | 17.3 ms | 22.6 ms | 55.6 ms | 2.46x |
| dragon_vrip.ply | 26.1 ms | 46.9 ms | 166.9 ms | 3.56x |
| 3DBenchy.stl | 3.5 ms | 7.4 ms | 28.7 ms | 3.86x |
...

The script uses AssetKit shading mode `AS_IS` and texture loading `IMMEDIATE`.
### Reproducing the Benchmarks

Run the review benchmark script:

```sh
tools/benchmark_review_imports.sh
```

The script downloads the benchmark assets into the ignored `benchmark-assets/` cache and writes JSONL results plus a Markdown table to `benchmark-results/`.

By default it uses:

- Blender 5.1.2 for glTF, OBJ, PLY, and STL comparisons
- Blender 4.5.10 LTS for DAE builtin COLLADA comparisons
- AssetKit shading mode `AS_IS`
- AssetKit texture loading `IMMEDIATE`

---

## Build

Build AssetKit, then build the native Blender bridge with Blender's Python:

```sh
cmake -S deps/assetkit -B deps/assetkit/build -DAK_SHARED=ON
cmake --build deps/assetkit/build
cmake -S . -B build -DASSETKIT_ROOT=deps/assetkit -DPython3_EXECUTABLE=/path/to/blender/python
cmake --build build
```

The bridge is written to `assetkit_blender/` as `_assetkit_blender.*`. If it is not present, the add-on can still use the configured AssetKit shared library through `ctypes`.

### Production package

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

### Release assets

Pushing a tag such as `v0.1.0` runs the package matrix on GitHub Actions and attaches
the platform zip files to the GitHub Release for that tag automatically.
