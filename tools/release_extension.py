#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform as host_platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "assetkit_blender"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build native binaries and produce a validated Blender extension zip."
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get("BLENDER_BIN") or shutil.which("blender"),
        help="Path to Blender executable; defaults to BLENDER_BIN or blender on PATH",
    )
    parser.add_argument(
        "--platform",
        default="auto",
        help="Extension platform tag passed to tools/package_extension.py",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=None,
        help="Primary Python executable used to build the native bridge; defaults to Blender's bundled Python",
    )
    parser.add_argument(
        "--extra-python",
        type=Path,
        action="append",
        default=[],
        help="Additional Python executable used to build another native ABI; can be repeated",
    )
    parser.add_argument(
        "--python-include",
        type=Path,
        default=None,
        help="Python include directory containing Python.h",
    )
    parser.add_argument(
        "--assetkit-root",
        type=Path,
        default=None,
        help="AssetKit source or install root; defaults to env, sibling checkout, then deps/assetkit",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=ROOT / "build" / "release-extension",
        help="Native bridge CMake build directory",
    )
    parser.add_argument(
        "--assetkit-build-dir",
        type=Path,
        default=None,
        help="AssetKit CMake build directory; defaults to ASSETKIT_ROOT/build-static for wheel packages",
    )
    parser.add_argument(
        "--skip-assetkit",
        action="store_true",
        help="Do not build AssetKit before building the Blender bridge",
    )
    parser.add_argument(
        "--no-decoders",
        action="store_true",
        help="Build without optional AssetKit decoder shim libraries",
    )
    parser.add_argument(
        "--static-assetkit",
        action="store_true",
        help="Link AssetKit core statically into the native Blender bridge",
    )
    parser.add_argument(
        "--native-wheels",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Package native bridge binaries as wheels instead of loose extension files",
    )
    parser.add_argument(
        "--skip-native",
        action="store_true",
        help="Do not build the native Blender bridge before packaging",
    )
    parser.add_argument(
        "--clean-artifacts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove old package native binaries before building",
    )
    return parser.parse_args()


def default_blender_path() -> str | None:
    candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    return next((path for path in candidates if Path(path).exists()), None)


def require_blender(path: str | None) -> str:
    blender = path or default_blender_path()
    if not blender:
        raise SystemExit("Blender executable not found. Set BLENDER_BIN or pass --blender.")
    return blender


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def blender_python(blender: str) -> str:
    code = "import sys; print(sys.executable)"
    result = subprocess.run(
        [blender, "--background", "--python-expr", code],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line and ("/python" in line or "\\python" in line):
            return line
    raise SystemExit("Could not detect Blender's bundled Python executable.")


def python_config(python: str) -> tuple[str, str, Path | None]:
    code = (
        "import sys, sysconfig; "
        "print(f'{sys.version_info[0]}.{sys.version_info[1]}'); "
        "print(sysconfig.get_config_var('SOABI') or ''); "
        "print(sysconfig.get_config_var('INCLUDEPY') or '')"
    )
    result = subprocess.run(
        [python, "-c", code],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    lines = [line.strip() for line in result.stdout.splitlines()]
    version = lines[0]
    soabi = lines[1] if len(lines) > 1 else ""
    include = Path(lines[2]) if len(lines) > 2 and lines[2] else None
    if include and not (include / "Python.h").exists():
        include = None
    return version, soabi, include


def python_soabi(python: str) -> str:
    version, soabi, _include = python_config(python)
    if soabi:
        return soabi
    major, minor = version.split(".", 1)
    return f"cpython-{major}{minor}"


def python_include_for_bridge(python: str, explicit_include: Path | None) -> Path | None:
    if explicit_include:
        if not (explicit_include / "Python.h").exists():
            raise SystemExit(f"Python.h not found in {explicit_include}")
        return explicit_include

    version, _soabi, include = python_config(python)
    if include:
        return include

    fallback = shutil.which(f"python{version}")
    if fallback:
        fallback_version, _fallback_soabi, fallback_include = python_config(fallback)
        if fallback_version == version and fallback_include:
            return fallback_include

    return None


def clean_native_artifacts() -> None:
    patterns = [
        "_assetkit_blender*.so",
        "_assetkit_blender*.pyd",
        "_assetkit_blender*.dll",
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
        "wheels/*.whl",
    ]
    for pattern in patterns:
        for path in PACKAGE_DIR.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()


def resolve_assetkit_root(explicit_root: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit_root:
        candidates.append(explicit_root)
    env_root = os.environ.get("ASSETKIT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(
        [
            ROOT.parent / "assetio",
            ROOT.parent / "assetkit",
            ROOT / "deps" / "assetkit",
        ]
    )

    for candidate in candidates:
        root = candidate.resolve()
        if (root / "include" / "ak" / "assetkit.h").exists():
            return root
    checked = ", ".join(os.fspath(path) for path in candidates)
    raise SystemExit(f"AssetKit root not found. Checked: {checked}")


def cmake_configure(source: Path, build: Path, extra: list[str]) -> None:
    command = [
        "cmake",
        "-S",
        os.fspath(source),
        "-B",
        os.fspath(build),
        "-DCMAKE_BUILD_TYPE=Release",
        *extra,
    ]
    if host_platform.system().lower() != "windows" and shutil.which("ninja"):
        command.extend(["-G", "Ninja"])
    run(command)


def platform_tag(value: str) -> str:
    if value != "auto":
        return value
    system = host_platform.system().lower()
    machine = host_platform.machine().lower()
    if system == "darwin":
        return "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-x64"
    if system == "linux":
        return "linux-x64"
    if system == "windows":
        return "windows-arm64" if machine in {"arm64", "aarch64"} else "windows-x64"
    raise SystemExit(f"Unsupported host platform: {system} {machine}")


def main() -> int:
    args = parse_args()
    blender = require_blender(args.blender)
    primary_python = os.fspath(args.python) if args.python else blender_python(blender)
    pythons = list(dict.fromkeys([primary_python, *(os.fspath(path) for path in args.extra_python)]))
    python_builds: list[tuple[str, str]] = []
    seen_soabis: set[str] = set()
    for python in pythons:
        soabi = python_soabi(python)
        if soabi in seen_soabis:
            continue
        seen_soabis.add(soabi)
        python_builds.append((python, soabi))
    if args.python_include and len(pythons) != 1:
        raise SystemExit("--python-include can only be used when building one Python ABI")
    assetkit_root = resolve_assetkit_root(args.assetkit_root)
    static_assetkit = args.static_assetkit or args.native_wheels
    assetkit_build_dir = args.assetkit_build_dir or (
        assetkit_root / ("build-static" if static_assetkit else "build")
    )
    tag = platform_tag(args.platform)

    if args.clean_artifacts:
        clean_native_artifacts()

    if not args.skip_assetkit:
        if static_assetkit:
            assetkit_options = [
                "-DAK_SHARED=OFF",
                "-DAK_STATIC=ON",
                "-DAK_STATIC_INTERNAL_DEPS=ON",
                "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
            ]
        else:
            assetkit_options = [
                "-DAK_SHARED=ON",
            ]
        if args.no_decoders:
            assetkit_options.append("-DAK_BUILD_DECODER_SHIMS=OFF")
        cmake_configure(
            assetkit_root,
            assetkit_build_dir,
            assetkit_options,
        )
        run(["cmake", "--build", os.fspath(assetkit_build_dir), "--config", "Release"])

    if not args.skip_native:
        multi_abi = len(python_builds) > 1
        for python, soabi in python_builds:
            python_include = python_include_for_bridge(python, args.python_include)
            build_dir = args.build_dir / soabi if multi_abi else args.build_dir
            print(f"Building native bridge for {python} ({soabi})")
            cmake_configure(
                ROOT,
                build_dir,
                [
                    f"-DASSETKIT_ROOT={assetkit_root}",
                    f"-DASSETKIT_BLENDER_STATIC_ASSETKIT={'ON' if static_assetkit else 'OFF'}",
                    f"-DPython3_EXECUTABLE={python}",
                    *([f"-DPython3_INCLUDE_DIR={python_include}"] if python_include else []),
                ],
            )
            run(["cmake", "--build", os.fspath(build_dir), "--config", "Release"])

    run(
        [
            sys.executable,
            os.fspath(ROOT / "tools" / "package_extension.py"),
            "--blender",
            blender,
            "--platform",
            tag,
            *(["--native-wheels"] if args.native_wheels else []),
        ]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
