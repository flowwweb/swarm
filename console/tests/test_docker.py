from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


DOCKER = Path(__file__).resolve().parents[1] / "docker.py"
COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
SPEC = importlib.util.spec_from_file_location("rush_docker_tested", DOCKER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class RushDockerTests(unittest.TestCase):
    def test_posix_host_identity_is_forwarded(self) -> None:
        environment: dict[str, str] = {}
        with (
            mock.patch.object(launcher.os, "getuid", return_value=501, create=True),
            mock.patch.object(launcher.os, "getgid", return_value=20, create=True),
        ):
            launcher._set_container_user(environment)
        self.assertEqual(environment["RUSH_CONTAINER_USER"], "501:20")

    def test_explicit_container_identity_is_preserved(self) -> None:
        environment = {"RUSH_CONTAINER_USER": "123:456"}
        launcher._set_container_user(environment)
        self.assertEqual(environment["RUSH_CONTAINER_USER"], "123:456")

    def test_compose_uses_host_identity_with_safe_fallback(self) -> None:
        compose = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('user: "${RUSH_CONTAINER_USER:-rush}"', compose)
        self.assertIn(':/data/rush"', compose)
        self.assertIn("no-new-privileges:true", compose)


if __name__ == "__main__":
    unittest.main()
