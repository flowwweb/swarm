from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


DOCKER = Path(__file__).resolve().parents[1] / "docker.py"
COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
TEST_HOME = Path("C:/Users/rush-test")
SPEC = importlib.util.spec_from_file_location("rush_docker_tested", DOCKER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class RushDockerTests(unittest.TestCase):
    def _run_main(
        self,
        environment: dict[str, str],
        *,
        getuid: object,
        getgid: object,
    ) -> dict[str, str]:
        completed = mock.Mock(returncode=0)
        with (
            mock.patch.object(launcher.sys, "argv", ["docker.py", "config"]),
            mock.patch.object(launcher.shutil, "which", return_value="docker"),
            mock.patch.object(launcher.os, "environ", environment),
            mock.patch.object(launcher.os, "getuid", getuid, create=True),
            mock.patch.object(launcher.os, "getgid", getgid, create=True),
            mock.patch.object(launcher.Path, "home", return_value=TEST_HOME),
            mock.patch.object(launcher.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(launcher.main(), 0)

        expected_environment = environment.copy()
        expected_environment.setdefault("RUSH_CODEX_HOME", str(TEST_HOME / ".codex"))
        expected_environment.setdefault("RUSH_CONFIG_HOME", str(TEST_HOME / ".agents" / "rush"))
        invoked_environment = run.call_args.kwargs["env"]
        run.assert_called_once_with(
            ["docker", "compose", "-f", str(COMPOSE), "config", "--quiet"],
            cwd=DOCKER.parent.parent,
            env=invoked_environment,
            check=False,
        )
        self.assertEqual(
            {key: value for key, value in invoked_environment.items() if key != "RUSH_CONTAINER_USER"},
            {key: value for key, value in expected_environment.items() if key != "RUSH_CONTAINER_USER"},
        )
        return invoked_environment

    def test_posix_host_identity_is_forwarded_through_main(self) -> None:
        environment = self._run_main(
            {},
            getuid=mock.Mock(return_value=501),
            getgid=mock.Mock(return_value=20),
        )
        self.assertEqual(environment["RUSH_CONTAINER_USER"], "501:20")

    def test_windows_unavailable_identity_uses_compose_fallback_through_main(self) -> None:
        environment = self._run_main({}, getuid=None, getgid=None)
        self.assertNotIn("RUSH_CONTAINER_USER", environment)

    def test_explicit_container_identity_is_preserved_through_main(self) -> None:
        environment = self._run_main(
            {"RUSH_CONTAINER_USER": "123:456"},
            getuid=mock.Mock(return_value=501),
            getgid=mock.Mock(return_value=20),
        )
        self.assertEqual(environment["RUSH_CONTAINER_USER"], "123:456")

    def test_zero_host_identity_uses_compose_fallback_through_main(self) -> None:
        for uid, gid in ((0, 20), (501, 0), (0, 0)):
            with self.subTest(uid=uid, gid=gid):
                environment = self._run_main(
                    {},
                    getuid=mock.Mock(return_value=uid),
                    getgid=mock.Mock(return_value=gid),
                )
                self.assertNotIn("RUSH_CONTAINER_USER", environment)

    def test_compose_preserves_container_security_and_safe_fallback(self) -> None:
        compose = COMPOSE.read_text(encoding="utf-8")
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("\nUSER rush\n", dockerfile)
        self.assertIn('user: "${RUSH_CONTAINER_USER:-rush}"', compose)
        self.assertIn('"127.0.0.1:4788:4788"', compose)
        self.assertIn(':/data/codex:ro"', compose)
        self.assertIn(':/data/rush"', compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)


if __name__ == "__main__":
    unittest.main()
