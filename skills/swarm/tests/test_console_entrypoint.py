from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


ENTRYPOINT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_console.py"
SPEC = importlib.util.spec_from_file_location("swarm_console_entrypoint_tested", ENTRYPOINT)
assert SPEC and SPEC.loader
entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entrypoint)


class ConsoleEntrypointTests(unittest.TestCase):
    def test_start_routes_to_setting_aware_launcher(self) -> None:
        with (
            mock.patch.object(sys, "argv", ["swarm_console.py", "--start", "--port", "4888"]),
            mock.patch.object(entrypoint.os, "execv") as execv,
        ):
            self.assertEqual(entrypoint.main(), 0)
        target = ENTRYPOINT.parents[3] / "console" / "launcher.py"
        execv.assert_called_once_with(sys.executable, [sys.executable, str(target), "--port", "4888"])

    def test_manual_options_still_route_to_server(self) -> None:
        with (
            mock.patch.object(sys, "argv", ["swarm_console.py", "--open"]),
            mock.patch.object(entrypoint.os, "execv") as execv,
        ):
            self.assertEqual(entrypoint.main(), 0)
        target = ENTRYPOINT.parents[3] / "console" / "server.py"
        execv.assert_called_once_with(sys.executable, [sys.executable, str(target), "--open"])


if __name__ == "__main__":
    unittest.main()
