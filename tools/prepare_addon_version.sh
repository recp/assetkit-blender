#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_REPO="recp/assetkit-blender"
DEFAULT_WORKFLOW="Extension package"
DEFAULT_OUT_DIR="addon_upload_ready"

repo="${GITHUB_REPOSITORY:-$DEFAULT_REPO}"
workflow="$DEFAULT_WORKFLOW"
out_dir="$DEFAULT_OUT_DIR"
run_id=""
tag=""
branch=""
version=""

usage() {
  cat <<'EOF'
Usage:
  tools/prepare_addon_version.sh [options]

Downloads the five platform package zips into addon_upload_ready/.

Options:
  --run-id ID        Download artifacts from a specific Actions run.
  --tag TAG          Download assets from a GitHub Release tag, for example v0.1.0.
  --repo OWNER/REPO  GitHub repository. Defaults to recp/assetkit-blender.
  --branch NAME      Branch used when finding the latest successful Actions run.
  --workflow NAME    Workflow name. Defaults to "Extension package".
  --version VERSION  Package version. Defaults to blender_manifest.toml.
  --out DIR          Output directory. Defaults to addon_upload_ready.
  -h, --help         Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)
      run_id="${2:?missing value for --run-id}"
      shift 2
      ;;
    --tag)
      tag="${2:?missing value for --tag}"
      shift 2
      ;;
    --repo)
      repo="${2:?missing value for --repo}"
      shift 2
      ;;
    --branch)
      branch="${2:?missing value for --branch}"
      shift 2
      ;;
    --workflow)
      workflow="${2:?missing value for --workflow}"
      shift 2
      ;;
    --version)
      version="${2:?missing value for --version}"
      shift 2
      ;;
    --out)
      out_dir="${2:?missing value for --out}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "$run_id" && -n "$tag" ]]; then
  echo "--run-id and --tag cannot be used together." >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required: https://cli.github.com/" >&2
  exit 1
fi

if [[ -z "$version" ]]; then
  version="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "$ROOT_DIR/blender_manifest.toml" | head -n 1)"
fi
if [[ -z "$version" ]]; then
  echo "Could not determine version from blender_manifest.toml." >&2
  exit 1
fi

if [[ -z "$branch" ]]; then
  branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ -z "$branch" || "$branch" == "HEAD" ]]; then
    branch="main"
  fi
fi

platforms=(
  linux-x64
  windows-x64
  windows-arm64
  macos-arm64
  macos-x64
)

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

if [[ -n "$tag" ]]; then
  echo "Downloading release assets for $tag from $repo..."
  gh release download "$tag" \
    --repo "$repo" \
    --pattern "assetkit_blender-${version}-*.zip" \
    --dir "$tmp_dir"
else
  if [[ -z "$run_id" ]]; then
    echo "Finding latest successful \"$workflow\" run on $branch..."
    run_id="$(gh run list \
      --repo "$repo" \
      --workflow "$workflow" \
      --branch "$branch" \
      --status success \
      --limit 1 \
      --json databaseId \
      --jq '.[0].databaseId')"
  fi
  if [[ -z "$run_id" || "$run_id" == "null" ]]; then
    echo "Could not find a successful workflow run." >&2
    exit 1
  fi

  echo "Downloading artifacts from run $run_id..."
  gh run download "$run_id" --repo "$repo" --dir "$tmp_dir"
fi

mkdir -p "$ROOT_DIR/$out_dir"
rm -f "$ROOT_DIR/$out_dir"/assetkit_blender-*.zip
rm -f "$ROOT_DIR/$out_dir"/SHA256SUMS

expected=()
missing=0
for platform in "${platforms[@]}"; do
  name="assetkit_blender-${version}-${platform}.zip"
  found="$(find "$tmp_dir" -type f -name "$name" -print -quit)"
  if [[ -z "$found" ]]; then
    echo "Missing expected package: $name" >&2
    missing=1
    continue
  fi

  cp "$found" "$ROOT_DIR/$out_dir/$name"
  expected+=("$name")
done

if [[ "$missing" -ne 0 ]]; then
  echo "Downloaded files:" >&2
  find "$tmp_dir" -type f -print >&2
  exit 1
fi

(
  cd "$ROOT_DIR/$out_dir"
  shasum -a 256 "${expected[@]}" > SHA256SUMS
)

echo "Prepared $out_dir:"
printf '  %s\n' "${expected[@]}"
echo "  SHA256SUMS"
