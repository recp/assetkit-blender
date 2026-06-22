#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
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
WHEEL_DISTRIBUTION = "assetkit_blender_native"
NATIVE_ARTIFACT_PATTERNS = (
    "wheels/*.whl",
    "_assetkit_blender*.so",
    "_assetkit_blender*.pyd",
    "libassetkit*.dylib",
    "libassetkit*.so",
    "libassetkit*.so.*",
    "assetkit*.dll",
    "libassetkit*.dll",
    "libds*.dylib",
    "libds*.so",
    "libds*.so.*",
    "ds*.dll",
    "libds*.dll",
)

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
    parser.add_argument(
        "--native-wheels",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Package native bridge binaries as platform wheels instead of loose files",
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


def path_matches_any(path: Path, patterns: tuple[str, ...]) -> bool:
    return any(path.match(pattern) for pattern in patterns)


def should_copy(path: Path, *, include_native: bool = True) -> bool:
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    if not include_native and path_matches_any(path, NATIVE_ARTIFACT_PATTERNS):
        return False
    return True


def copy_tree_contents(src: Path, dst: Path, *, include_native: bool = True) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if not should_copy(rel, include_native=include_native):
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

    assetkit_build = ROOT / "deps" / "assetkit" / "build"
    if assetkit_build.exists():
        for pattern in core_library_patterns(platform_tag):
            candidates.extend(assetkit_build.rglob(pattern))

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


def wheel_platform_tag(platform_tag: str) -> str:
    return {
        "linux-x64": "manylinux_2_17_x86_64",
        "macos-arm64": "macosx_11_0_arm64",
        "macos-x64": "macosx_10_15_x86_64",
        "windows-arm64": "win_arm64",
        "windows-x64": "win_amd64",
    }[platform_tag]


def python_tag_for_native_module(path: Path) -> str:
    match = re.search(r"(?:cpython-|cp)(\d)(\d+)", path.name)
    if not match:
        raise SystemExit(f"Could not determine Python ABI tag from {path.name}")
    return f"cp{match.group(1)}{match.group(2)}"


def wheel_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def zip_writestr_recorded(
    zf: zipfile.ZipFile,
    records: list[tuple[str, str, int]],
    name: str,
    data: bytes,
) -> None:
    zf.writestr(name, data)
    records.append((name, wheel_hash(data), len(data)))


def zip_write_file_recorded(
    zf: zipfile.ZipFile,
    records: list[tuple[str, str, int]],
    source: Path,
    name: str | None = None,
) -> None:
    data = source.read_bytes()
    arcname = name or source.name
    zf.writestr(arcname, data)
    records.append((arcname, wheel_hash(data), len(data)))


def native_support_files() -> list[Path]:
    files: list[Path] = []
    for pattern in NATIVE_ARTIFACT_PATTERNS:
        files.extend(
            path
            for path in PACKAGE_DIR.glob(pattern)
            if path.is_file() and not path.name.startswith("_assetkit_blender")
        )
    return sorted(set(files))


def build_native_wheel(
    module_path: Path,
    wheel_dir: Path,
    *,
    version: str,
    platform_tag: str,
) -> Path:
    python_tag = python_tag_for_native_module(module_path)
    abi_tag = python_tag
    platform = wheel_platform_tag(platform_tag)
    dist_info = f"{WHEEL_DISTRIBUTION}-{version}.dist-info"
    wheel_name = f"{WHEEL_DISTRIBUTION}-{version}-{python_tag}-{abi_tag}-{platform}.whl"
    wheel_path = wheel_dir / wheel_name
    wheel_dir.mkdir(parents=True, exist_ok=True)

    records: list[tuple[str, str, int]] = []
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zip_write_file_recorded(zf, records, module_path)
        for support_file in native_support_files():
            zip_write_file_recorded(zf, records, support_file)

        metadata = (
            "Metadata-Version: 2.1\n"
            f"Name: {WHEEL_DISTRIBUTION.replace('_', '-')}\n"
            f"Version: {version}\n"
            "Summary: Native AssetKit bridge for Blender\n"
        ).encode("utf-8")
        wheel = (
            "Wheel-Version: 1.0\n"
            "Generator: assetkit-blender package_extension.py\n"
            "Root-Is-Purelib: false\n"
            f"Tag: {python_tag}-{abi_tag}-{platform}\n"
        ).encode("utf-8")
        zip_writestr_recorded(zf, records, f"{dist_info}/METADATA", metadata)
        zip_writestr_recorded(zf, records, f"{dist_info}/WHEEL", wheel)

        record_name = f"{dist_info}/RECORD"
        record_lines = [
            f"{name},{digest},{size}" for name, digest, size in records
        ]
        record_lines.append(f"{record_name},,")
        zf.writestr(record_name, "\n".join(record_lines).encode("utf-8"))

    return wheel_path


def build_native_wheels(stage_dir: Path, manifest: dict, platform_tag: str) -> list[Path]:
    modules: list[Path] = []
    for pattern in native_module_patterns(platform_tag):
        modules.extend(path for path in PACKAGE_DIR.glob(pattern) if path.is_file())
    if not modules:
        patterns = ", ".join(native_module_patterns(platform_tag))
        raise SystemExit(f"Missing native Python module for wheel build: {patterns}")

    wheel_dir = stage_dir / "wheels"
    version = str(manifest["version"])
    return [
        build_native_wheel(module, wheel_dir, version=version, platform_tag=platform_tag)
        for module in sorted(set(modules))
    ]


def remove_manifest_array(text: str, key: str) -> str:
    return re.sub(
        rf"(?ms)^{key}\s*=\s*\[[^\]]*\]\n*",
        "",
        text,
    )


def patch_manifest(text: str, platform_tag: str | None, wheel_paths: list[Path] | None = None) -> str:
    wheel_paths = wheel_paths or []
    text = remove_manifest_array(text, "wheels")
    if platform_tag is None:
        text = re.sub(r"(?m)^platforms\s*=\s*\[[^\n]*\]\n?", "", text)
    else:
        platforms_line = f'platforms = ["{platform_tag}"]'
        if re.search(r"(?m)^platforms\s*=", text):
            text = re.sub(r"(?m)^platforms\s*=\s*\[[^\n]*\]", platforms_line, text)
        else:
            permissions_match = re.search(r"(?m)^\[permissions\]\s*$", text)
            insert_at = permissions_match.start() if permissions_match else len(text)
            prefix = text[:insert_at].rstrip() + "\n"
            suffix = text[insert_at:].lstrip("\n")
            text = f"{prefix}{platforms_line}\n\n{suffix}"

    if not wheel_paths:
        return text

    permissions_match = re.search(r"(?m)^\[permissions\]\s*$", text)
    insert_at = permissions_match.start() if permissions_match else len(text)
    prefix = text[:insert_at].rstrip() + "\n"
    suffix = text[insert_at:].lstrip("\n")
    wheel_lines = ["wheels = ["]
    for path in wheel_paths:
        wheel_lines.append(f'  "./wheels/{path.name}",')
    wheel_lines.append("]")
    return f"{prefix}{chr(10).join(wheel_lines)}\n\n{suffix}"


def write_staged_manifest(
    stage_dir: Path,
    platform_tag: str | None,
    wheel_paths: list[Path] | None = None,
) -> dict:
    text = MANIFEST.read_text(encoding="utf-8")
    staged_text = patch_manifest(text, platform_tag, wheel_paths)
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


def prepare_stage(stage_dir: Path, platform_tag: str | None, *, native_wheels: bool = False) -> dict:
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    copy_tree_contents(PACKAGE_DIR, stage_dir, include_native=not native_wheels)
    copy_metadata(stage_dir)
    manifest = tomllib.loads(patch_manifest(MANIFEST.read_text(encoding="utf-8"), platform_tag))
    wheel_paths: list[Path] = []
    if native_wheels:
        if platform_tag is None:
            raise SystemExit("--native-wheels requires a concrete platform tag")
        wheel_paths = build_native_wheels(stage_dir, manifest, platform_tag)
    return write_staged_manifest(stage_dir, platform_tag, wheel_paths)


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

    manifest = prepare_stage(args.stage_dir, platform_tag, native_wheels=args.native_wheels)
    if platform_tag is not None and not args.native_wheels:
        ensure_core_runtime(args.stage_dir, platform_tag)
    if not args.allow_source_only:
        if args.native_wheels:
            if not any((args.stage_dir / "wheels").glob("*.whl")):
                raise SystemExit("Missing native wheels")
        else:
            require_native_artifacts(args.stage_dir, platform_tag)

    output = build_zip(args, manifest, platform_tag)
    print(f"Staged extension source: {args.stage_dir}")
    if not args.no_build:
        print(f"Built extension package: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
