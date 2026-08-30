#!/usr/bin/env python3
"""Create reproducible WebP and AVIF derivatives from transparent PNG assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from PIL import Image, features


SCHEMA_VERSION = 1
DEFAULT_SIZES = (64, 128, 256, 512)
DEFAULT_FORMATS = ("webp", "avif")
FORMAT_OPTIONS = {
    "webp": {"format": "WEBP", "quality": 82, "method": 6, "exact": True},
    "avif": {"format": "AVIF", "quality": 58, "speed": 6},
}


class OptimizationError(RuntimeError):
    """A source or derivative violates the optimization contract."""


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_csv(value: str, *, allowed: Iterable[str] | None = None) -> tuple[str, ...]:
    items = tuple(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))
    if not items:
        raise argparse.ArgumentTypeError("at least one value is required")
    if allowed is not None:
        unexpected = sorted(set(items) - set(allowed))
        if unexpected:
            raise argparse.ArgumentTypeError(f"unsupported values: {', '.join(unexpected)}")
    return items


def _parse_sizes(value: str) -> tuple[int, ...]:
    try:
        sizes = tuple(sorted({int(item.strip()) for item in value.split(",") if item.strip()}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from error
    if not sizes or any(size < 16 or size > 4096 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must be integers from 16 to 4096")
    return sizes


def _safe_root(path: Path, label: str) -> Path:
    root = path.resolve()
    if not root.is_dir() or root.is_symlink():
        raise OptimizationError(f"{label} must be a real directory: {root}")
    return root


def _source_files(source_root: Path) -> tuple[Path, ...]:
    files = tuple(sorted(path for path in source_root.glob("*.png") if path.is_file() and not path.is_symlink()))
    if not files:
        raise OptimizationError("source directory contains no direct PNG files")
    stems = [path.stem.lower() for path in files]
    if len(stems) != len(set(stems)):
        raise OptimizationError("source PNG names collide case-insensitively")
    return files


def _encode(image: Image.Image, image_format: str) -> bytes:
    if image_format == "webp" and not features.check("webp"):
        raise OptimizationError("Pillow WebP support is unavailable")
    if image_format == "avif" and not features.check("avif"):
        raise OptimizationError("Pillow AVIF support is unavailable")
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as output:
        image.save(output, **FORMAT_OPTIONS[image_format])
        output.seek(0)
        return output.read()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def optimize_directory(
    source: Path,
    output: Path,
    *,
    sizes: tuple[int, ...] = DEFAULT_SIZES,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
    require_alpha: bool = False,
    check: bool = False,
    reuse_existing: bool = False,
) -> dict[str, object]:
    source_root = _safe_root(source, "source")
    output_root = output.resolve()
    if output_root == source_root or source_root in output_root.parents:
        raise OptimizationError("output must not be the source directory or one of its descendants")
    if output_root.exists() and (not output_root.is_dir() or output_root.is_symlink()):
        raise OptimizationError(f"output must be a real directory: {output_root}")

    records: list[dict[str, object]] = []
    expected_paths: set[Path] = set()
    for source_path in _source_files(source_root):
        payload = source_path.read_bytes()
        with Image.open(source_path) as opened:
            image = opened.convert("RGBA")
            if opened.format != "PNG":
                raise OptimizationError(f"source is not a PNG: {source_path.name}")
            alpha_extrema = image.getchannel("A").getextrema()
            if require_alpha and alpha_extrema[0] != 0:
                raise OptimizationError(f"source has no transparent pixels: {source_path.name}")
            derivatives: list[dict[str, object]] = []
            for size in sizes:
                if size > max(image.size):
                    continue
                resized = image.copy()
                resized.thumbnail((size, size), Image.Resampling.LANCZOS)
                for image_format in formats:
                    relative = Path(f"{source_path.stem}-{size}.{image_format}")
                    destination = output_root / relative
                    expected_paths.add(relative)
                    if reuse_existing and destination.is_file() and not destination.is_symlink():
                        encoded = destination.read_bytes()
                        try:
                            with Image.open(destination) as retained:
                                if retained.size != resized.size or "A" not in retained.getbands() or retained.format.lower() != image_format:
                                    raise OptimizationError(f"retained derivative is invalid: {relative.as_posix()}")
                        except OSError as error:
                            raise OptimizationError(f"retained derivative is invalid: {relative.as_posix()}") from error
                    else:
                        encoded = _encode(resized, image_format)
                    if check:
                        if not destination.is_file() or destination.read_bytes() != encoded:
                            raise OptimizationError(f"derivative is missing or stale: {relative.as_posix()}")
                    else:
                        _atomic_write(destination, encoded)
                    derivatives.append({
                        "path": relative.as_posix(),
                        "format": image_format,
                        "width": resized.width,
                        "height": resized.height,
                        "bytes": len(encoded),
                        "sha256": _digest(encoded),
                        "saved_bytes_vs_source": len(payload) - len(encoded),
                    })
            records.append({
                "id": source_path.stem,
                "source": {
                    "file": source_path.name,
                    "width": image.width,
                    "height": image.height,
                    "mode": "RGBA",
                    "alpha_min": alpha_extrema[0],
                    "alpha_max": alpha_extrema[1],
                    "bytes": len(payload),
                    "sha256": _digest(payload),
                },
                "derivatives": derivatives,
            })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "settings": {"sizes": list(sizes), "formats": list(formats)},
        "assets": records,
    }
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = output_root / "manifest.json"
    expected_paths.add(Path("manifest.json"))
    if check:
        if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_payload:
            raise OptimizationError("derivative manifest is missing or stale")
        actual_paths = {path.relative_to(output_root) for path in output_root.iterdir() if path.is_file() and not path.is_symlink()}
        if actual_paths != expected_paths:
            raise OptimizationError("derivative directory contains missing or unexpected files")
    else:
        output_root.mkdir(parents=True, exist_ok=True)
        _atomic_write(manifest_path, manifest_payload)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Directory containing direct PNG sources")
    parser.add_argument("--output", type=Path, required=True, help="Separate derivative directory")
    parser.add_argument("--sizes", type=_parse_sizes, default=DEFAULT_SIZES)
    parser.add_argument("--formats", type=lambda value: _parse_csv(value, allowed=FORMAT_OPTIONS), default=DEFAULT_FORMATS)
    parser.add_argument("--require-alpha", action="store_true")
    parser.add_argument("--check", action="store_true", help="Fail unless every derivative and manifest byte is current")
    parser.add_argument("--reuse-existing", action="store_true", help="Resume generation from validated existing derivatives")
    arguments = parser.parse_args()
    try:
        manifest = optimize_directory(
            arguments.source,
            arguments.output,
            sizes=arguments.sizes,
            formats=arguments.formats,
            require_alpha=arguments.require_alpha,
            check=arguments.check,
            reuse_existing=arguments.reuse_existing,
        )
    except OptimizationError as error:
        parser.error(str(error))
    derivative_count = sum(len(asset["derivatives"]) for asset in manifest["assets"])
    print(f"optimized {len(manifest['assets'])} source images into {derivative_count} derivatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
