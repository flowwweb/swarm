#!/usr/bin/env python3
"""Run the smallest declared SWARM test tier without duplicate discovery."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "skills" / "swarm" / "tests"
sys.path.insert(0, str(ROOT))
PLATFORM_MODULES = (
    "test_console_entrypoint",
    "test_host_contracts",
    "test_swarm_config",
    "test_ctrl_authority_guard",
)


def suite_for(tier: str) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    names = PLATFORM_MODULES if tier == "platform" else tuple(
        path.stem for path in sorted(TESTS.glob("test_*.py"))
        if path.stem != "test_release_package"
    )
    return loader.loadTestsFromNames(
        tuple(f"skills.swarm.tests.{name}" for name in names)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tier", choices=("fast", "platform"))
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=1).run(suite_for(args.tier))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
