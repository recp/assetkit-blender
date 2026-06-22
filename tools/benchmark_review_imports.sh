#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender5.app/Contents/MacOS/Blender}"
BLENDER_DAE="${BLENDER_DAE:-/Applications/Blender-45-LTS.app/Contents/MacOS/Blender}"
RUNS="${RUNS:-5}"
WARMUP="${WARMUP:-1}"
NODE_RUNS="${NODE_RUNS:-2}"
NODE_WARMUP="${NODE_WARMUP:-0}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/benchmark-results}"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [[ ! -x "$BLENDER" ]]; then
  echo "BLENDER is not executable: $BLENDER" >&2
  exit 1
fi

if [[ ! -x "$BLENDER_DAE" ]]; then
  echo "BLENDER_DAE is not executable: $BLENDER_DAE" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

NONDAE_JSON="$OUT_DIR/import-as-is-nondae-$STAMP.jsonl"
NODE_JSON="$OUT_DIR/import-as-is-node-performance-$STAMP.jsonl"
DAE_ASSETKIT_JSON="$OUT_DIR/import-as-is-dae-assetkit-$STAMP.jsonl"
DAE_BUILTIN_JSON="$OUT_DIR/import-as-is-dae-blender45-$STAMP.jsonl"
TABLE_MD="$OUT_DIR/import-as-is-table-$STAMP.md"

COMMON_ARGS=(
  --assetkit-textures IMMEDIATE
  --assetkit-shading AS_IS
)

echo "Benchmarking non-DAE assets with $BLENDER"
"$BLENDER" --background --factory-startup \
  --python "$ROOT_DIR/tools/blender_import_benchmark.py" -- \
  --download-suite \
  --suite-assets \
    gltf-damaged-helmet \
    gltf-boombox \
    gltf-water-bottle \
    gltf-a-beautiful-game \
    gltf-antique-camera \
    gltf-mosquito-in-amber \
    obj-xyzrgb-dragon \
    ply-stanford-dragon \
    stl-3dbenchy \
  --engines native assetkit builtin \
  --runs "$RUNS" \
  --warmup "$WARMUP" \
  "${COMMON_ARGS[@]}" \
  --jsonl "$NONDAE_JSON" \
  --markdown

echo "Benchmarking NodePerformanceTest with $BLENDER"
"$BLENDER" --background --factory-startup \
  --python "$ROOT_DIR/tools/blender_import_benchmark.py" -- \
  --download-suite \
  --suite-assets gltf-node-performance \
  --engines native assetkit builtin \
  --runs "$NODE_RUNS" \
  --warmup "$NODE_WARMUP" \
  "${COMMON_ARGS[@]}" \
  --jsonl "$NODE_JSON" \
  --markdown

echo "Benchmarking DAE AssetKit/native with $BLENDER"
"$BLENDER" --background --factory-startup \
  --python "$ROOT_DIR/tools/blender_import_benchmark.py" -- \
  --download-suite \
  --suite-assets dae-brainstem dae-duck dae-gearbox-assy \
  --engines native assetkit \
  --runs "$RUNS" \
  --warmup "$WARMUP" \
  "${COMMON_ARGS[@]}" \
  --jsonl "$DAE_ASSETKIT_JSON"

echo "Benchmarking DAE Blender builtin with $BLENDER_DAE"
"$BLENDER_DAE" --background --factory-startup \
  --python "$ROOT_DIR/tools/blender_import_benchmark.py" -- \
  --download-suite \
  --suite-assets dae-brainstem dae-duck dae-gearbox-assy \
  --engines builtin \
  --runs "$RUNS" \
  --warmup "$WARMUP" \
  "${COMMON_ARGS[@]}" \
  --jsonl "$DAE_BUILTIN_JSON"

python3 - "$TABLE_MD" "$NONDAE_JSON" "$NODE_JSON" "$DAE_ASSETKIT_JSON" "$DAE_BUILTIN_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

table_path = Path(sys.argv[1])
jsonl_paths = [Path(arg) for arg in sys.argv[2:]]

rows: dict[str, dict[str, dict]] = {}
for path in jsonl_paths:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            summary = payload.get("summary")
            if not summary or summary.get("error"):
                continue
            rows.setdefault(Path(summary["file"]).name, {})[summary["engine"]] = summary

order = (
    "BrainStem.dae",
    "Duck.dae",
    "GearboxAssy.dae",
    "NodePerformanceTest.glb",
    "BoomBox.glb",
    "DamagedHelmet.glb",
    "WaterBottle.glb",
    "ABeautifulGame.glb",
    "AntiqueCamera.glb",
    "MosquitoInAmber.glb",
    "xyzrgb_dragon.obj",
    "dragon_vrip.ply",
    "3DBenchy.stl",
)

def median_ms(name: str, engine: str) -> float | None:
    summary = rows.get(name, {}).get(engine)
    if not summary:
        return None
    return float(summary["median_ms"])

def fmt_ms(value: float | None) -> str:
    return "" if value is None else f"{value:.1f} ms"

lines = [
    "| File | AssetKit native | AssetKit Blender | Blender | Blender / AssetKit Blender |",
    "| --- | ---: | ---: | ---: | ---: |",
]
for name in order:
    native = median_ms(name, "native")
    assetkit = median_ms(name, "assetkit")
    blender = median_ms(name, "builtin")
    ratio = "" if not assetkit or not blender else f"{blender / assetkit:.2f}x"
    lines.append(f"| {name} | {fmt_ms(native)} | {fmt_ms(assetkit)} | {fmt_ms(blender)} | {ratio} |")

notes = [
    "Benchmarked locally on macOS with AssetKit shading mode set to AS_IS and texture loading set to IMMEDIATE.",
    "AssetKit native measures backend loading/parsing only; AssetKit Blender measures blocking end-to-end import into Blender objects/materials.",
    "DAE Blender builtin results are measured with Blender 4.5 LTS because Blender 5.x no longer includes the COLLADA importer.",
    "",
]

table_path.write_text("\n".join(notes + lines) + "\n", encoding="utf-8")
print(table_path.read_text(encoding="utf-8"))
PY

echo "Wrote:"
echo "  $NONDAE_JSON"
echo "  $NODE_JSON"
echo "  $DAE_ASSETKIT_JSON"
echo "  $DAE_BUILTIN_JSON"
echo "  $TABLE_MD"
