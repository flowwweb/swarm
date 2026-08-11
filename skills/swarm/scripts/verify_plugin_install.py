#!/usr/bin/env python3
"""Verify that an installed plugin contains the complete declared skill trees."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def declared_files(plugin_root: Path) -> dict[str, str]:
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    skills_root = plugin_root / payload["skills"]
    files = [manifest, *(path for path in skills_root.rglob("*") if path.is_file())]
    return {
        path.relative_to(plugin_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
        if "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def verify(source: Path, installed: Path) -> int:
    expected = declared_files(source)
    actual = declared_files(installed)
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(path for path in expected.keys() & actual.keys() if expected[path] != actual[path])
    if missing or extra or changed:
        raise ValueError(f"plugin tree mismatch: missing={missing}, extra={extra}, changed={changed}")
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("installed", type=Path)
    args = parser.parse_args()
    print(f"verified {verify(args.source.resolve(), args.installed.resolve())} declared plugin files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
