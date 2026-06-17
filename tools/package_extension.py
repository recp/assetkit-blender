#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "assetkit_blender"
MANIFEST = ROOT / "blender_manifest.toml"
DEFAULT_STAGE_DIR = ROOT / "build" / "extension-stage"
DEFAULT_OUTPUT_DIR = ROOT / "dist"

PLATFORMS = {
    "linux-x64",
    "macos-arm64",
    "macos-x64",
    "windows-arm64",
    "windows-x64",
}

EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_FILES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage, validate and build the AssetKit extension zip."
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get("BLENDER_BIN") or shutil.which("blender"),
        help="Path to Blender executable; defaults to BLENDER_BIN or blender on PATH",
    )
    parser.add_argument(
        "--platform",
        default="auto",
        help="Blender extension platform tag, or auto",
    )
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=DEFAULT_STAGE_DIR,
        help="Temporary source directory used for the extension build",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the final zip",
    )
    parser.add_argument(
        "--allow-source-only",
        action="store_true",
        help="Allow a package without native AssetKit binaries",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Only create and validate the staged source tree",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip Blender extension validate",
    )
    return parser.parse_args()


def detected_platform() -> str:
    system = host_platform.system().lower()
    machine = host_platform.machine().lower()
    if system == "darwin":
        return "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-x64"
    if system == "linux":
        return "linux-x64"
    if system == "windows":
        return "windows-arm64" if machine in {"arm64", "aarch64"} else "windows-x64"
    raise SystemExit(f"Unsupported host platform: {system} {machine}")


def should_copy(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    return True


def copy_tree_contents(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if not should_copy(rel):
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def native_module_patterns(platform_tag: str) -> tuple[str, ...]:
    if platform_tag.startswith("windows"):
        return ("_assetkit_blender*.pyd",)
    return ("_assetkit_blender*.so",)


def core_library_patterns(platform_tag: str) -> tuple[str, ...]:
    if platform_tag.startswith("macos"):
        return ("libassetkit.dylib", "libassetkit.*.dylib")
    if platform_tag.startswith("linux"):
        return ("libassetkit.so", "libassetkit.so.*")
    return ("assetkit*.dll", "libassetkit*.dll")


def has_any(root: Path, patterns: tuple[str, ...]) -> bool:
    return any(any(root.glob(pattern)) for pattern in patterns)


def is_core_runtime(path: Path, platform_tag: str) -> bool:
    name = path.name
    if platform_tag.startswith("macos"):
        return bool(re.fullmatch(r"libassetkit(?:\.\d+(?:\.\d+)*)?\.dylib", name))
    if platform_tag.startswith("linux"):
        return name == "libassetkit.so" or bool(re.fullmatch(r"libassetkit\.so(?:\.\d+)*", name))
    return name in {"assetkit.dll", "libassetkit.dll"}


def core_runtime_files(root: Path, platform_tag: str) -> list[Path]:
    patterns = core_library_patterns(platform_tag)
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(path for path in root.glob(pattern) if is_core_runtime(path, platform_tag))
    return sorted(set(matches))


def require_native_artifacts(stage_dir: Path, platform_tag: str) -> None:
    missing: list[str] = []
    if not has_any(stage_dir, native_module_patterns(platform_tag)):
        missing.append("native Python module _assetkit_blender")
    if not core_runtime_files(stage_dir, platform_tag):
        missing.append("AssetKit runtime library")
    if missing:
        details = ", ".join(missing)
        raise SystemExit(
            f"Missing {details}. Build the native bridge first, or pass "
            "--allow-source-only for a non-production source package."
        )


def cmake_cache_value(cache_path: Path, key: str) -> Path | None:
    if not cache_path.exists():
        return None
    prefix = f"{key}:"
    for line in cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(prefix):
            continue
        _, value = line.split("=", 1)
        path = Path(value)
        if path.exists():
            return path
    return None


def runtime_alias_names(real_name: str, platform_tag: str) -> list[str]:
    names = [real_name]
    if platform_tag.startswith("macos"):
        match = re.fullmatch(r"(.+?)\.(\d+)(?:\.\d+)*\.dylib", real_name)
        if match:
            names.append(f"{match.group(1)}.{match.group(2)}.dylib")
            names.append(f"{match.group(1)}.dylib")
    elif platform_tag.startswith("linux"):
        match = re.fullmatch(r"(.+?\.so)\.(\d+)(?:\.\d+)*", real_name)
        if match:
            names.append(f"{match.group(1)}.{match.group(2)}")
            names.append(match.group(1))
    return sorted(set(names))


def runtime_candidates(platform_tag: str) -> list[Path]:
    env_library = os.environ.get("ASSETKIT_LIBRARY")
    candidates: list[Path] = []
    if env_library:
        candidates.append(Path(env_library))

    for build_dir in sorted(ROOT.glob("build*")):
        candidate = cmake_cache_value(build_dir / "CMakeCache.txt", "ASSETKIT_LIBRARY")
        if candidate:
            candidates.append(candidate)

    for path in ROOT.glob("deps/assetkit/build/libassetkit*"):
        candidates.append(path)

    candidates = [path.resolve() for path in candidates if path.exists()]
    return [path for path in sorted(set(candidates), reverse=True) if is_core_runtime(path, platform_tag)]


def best_core_runtime(stage_dir: Path, platform_tag: str) -> Path | None:
    staged = core_runtime_files(stage_dir, platform_tag)
    def version_key(path: Path) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", path.name))

    versioned = [path for path in staged if version_key(path)]
    if versioned:
        return sorted(versioned, key=version_key, reverse=True)[0]
    candidates = runtime_candidates(platform_tag)
    if candidates:
        return candidates[0]
    return staged[0] if staged else None


def ensure_core_runtime(stage_dir: Path, platform_tag: str) -> None:
    source = best_core_runtime(stage_dir, platform_tag)
    if not source:
        return

    if source.is_symlink():
        source = source.resolve()
    real_name = source.name
    for alias in runtime_alias_names(real_name, platform_tag):
        target = stage_dir / alias
        if source.resolve() == target.resolve():
            continue
        shutil.copy2(source, target)


def patch_manifest(text: str, platform_tag: str | None) -> str:
    if platform_tag is None:
        text = re.sub(r"(?m)^platforms\s*=\s*\[[^\n]*\]\n?", "", text)
        return text

    platforms_line = f'platforms = ["{platform_tag}"]'
    if re.search(r"(?m)^platforms\s*=", text):
        return re.sub(r"(?m)^platforms\s*=\s*\[[^\n]*\]", platforms_line, text)

    permissions_match = re.search(r"(?m)^\[permissions\]\s*$", text)
    insert_at = permissions_match.start() if permissions_match else len(text)
    prefix = text[:insert_at].rstrip() + "\n"
    suffix = text[insert_at:].lstrip("\n")
    return f"{prefix}{platforms_line}\n\n{suffix}"


def write_staged_manifest(stage_dir: Path, platform_tag: str | None) -> dict:
    text = MANIFEST.read_text(encoding="utf-8")
    staged_text = patch_manifest(text, platform_tag)
    (stage_dir / "blender_manifest.toml").write_text(staged_text, encoding="utf-8")
    return tomllib.loads(staged_text)


def copy_metadata(stage_dir: Path) -> None:
    for name in ("LICENSE", "NOTICE.md", "README.md"):
        path = ROOT / name
        if path.exists():
            shutil.copy2(path, stage_dir / name)
    licenses = ROOT / "LICENSES"
    if licenses.exists():
        shutil.copytree(licenses, stage_dir / "LICENSES", dirs_exist_ok=True)


def prepare_stage(stage_dir: Path, platform_tag: str | None) -> dict:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    copy_tree_contents(PACKAGE_DIR, stage_dir)
    copy_metadata(stage_dir)
    return write_staged_manifest(stage_dir, platform_tag)


def blender_command(args: argparse.Namespace) -> str:
    blender = args.blender
    if not blender:
        candidates = [
            "/Applications/Blender.app/Contents/MacOS/Blender",
        ]
        blender = next((candidate for candidate in candidates if Path(candidate).exists()), None)
    if not blender:
        raise SystemExit("Blender executable not found. Set BLENDER_BIN or pass --blender.")
    return blender


def run_blender(blender: str, command: list[str]) -> None:
    subprocess.run([blender, "--background", "--command", "extension", *command], check=True)


def build_zip(args: argparse.Namespace, manifest: dict, platform_tag: str | None) -> Path:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{platform_tag}" if platform_tag else ""
    output = args.output_dir / f"{manifest['id']}-{manifest['version']}{suffix}.zip"
    blender = blender_command(args)
    if not args.no_validate:
        run_blender(blender, ["validate", os.fspath(args.stage_dir)])
    if not args.no_build:
        run_blender(
            blender,
            [
                "build",
                "--source-dir",
                os.fspath(args.stage_dir),
                "--output-filepath",
                os.fspath(output),
            ],
        )
        if not args.no_validate:
            run_blender(blender, ["validate", os.fspath(output)])
    return output


def main() -> int:
    args = parse_args()
    platform_tag = detected_platform() if args.platform == "auto" else args.platform
    if platform_tag not in PLATFORMS:
        valid = ", ".join(sorted(PLATFORMS))
        raise SystemExit(f"Unknown platform '{platform_tag}'. Expected one of: {valid}")

    manifest = prepare_stage(args.stage_dir, platform_tag)
    if platform_tag is not None:
        ensure_core_runtime(args.stage_dir, platform_tag)
    if not args.allow_source_only:
        require_native_artifacts(args.stage_dir, platform_tag)

    output = build_zip(args, manifest, platform_tag)
    print(f"Staged extension source: {args.stage_dir}")
    if not args.no_build:
        print(f"Built extension package: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
