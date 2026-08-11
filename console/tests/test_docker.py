from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


DOCKER = Path(__file__).resolve().parents[1] / "docker.py"
COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
TEST_HOME = Path("C:/Users/swarm-test")
SPEC = importlib.util.spec_from_file_location("swarm_docker_tested", DOCKER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class SwarmDockerTests(unittest.TestCase):
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
        expected_environment.setdefault("SWARM_CODEX_HOME",str(TEST_HOME / ".codex"))
        selected=Path(environment.get("SWARM_CONFIG_PATH",TEST_HOME / ".agents" / "swarm" / "config.toml"))
        expected_environment["SWARM_CONFIG_HOME"]=str(selected.parent)
        expected_environment["SWARM_CONTAINER_CONFIG_PATH"]=f"/data/swarm/{selected.name}"
        invoked_environment = run.call_args.kwargs["env"]
        run.assert_called_once_with(
            ["docker", "compose", "-f", str(COMPOSE), "config", "--quiet"],
            cwd=DOCKER.parent.parent,
            env=invoked_environment,
            check=False,
        )
        self.assertEqual(
            {key: value for key, value in invoked_environment.items() if key != "SWARM_CONTAINER_USER"},
            {key: value for key, value in expected_environment.items() if key != "SWARM_CONTAINER_USER"},
        )
        return invoked_environment

    def test_posix_host_identity_is_forwarded_through_main(self) -> None:
        environment = self._run_main(
            {},
            getuid=mock.Mock(return_value=501),
            getgid=mock.Mock(return_value=20),
        )
        self.assertEqual(environment["SWARM_CONTAINER_USER"], "501:20")

    def test_windows_unavailable_identity_uses_compose_fallback_through_main(self) -> None:
        environment = self._run_main({}, getuid=None, getgid=None)
        self.assertNotIn("SWARM_CONTAINER_USER", environment)

    def test_explicit_container_identity_is_preserved_through_main(self) -> None:
        environment = self._run_main(
            {"SWARM_CONTAINER_USER": "123:456"},
            getuid=mock.Mock(return_value=501),
            getgid=mock.Mock(return_value=20),
        )
        self.assertEqual(environment["SWARM_CONTAINER_USER"], "123:456")

    def test_zero_host_identity_uses_compose_fallback_through_main(self) -> None:
        for uid, gid in ((0, 20), (501, 0), (0, 0)):
            with self.subTest(uid=uid, gid=gid):
                environment = self._run_main(
                    {},
                    getuid=mock.Mock(return_value=uid),
                    getgid=mock.Mock(return_value=gid),
                )
                self.assertNotIn("SWARM_CONTAINER_USER", environment)

    def test_compose_preserves_container_security_and_safe_fallback(self) -> None:
        compose = COMPOSE.read_text(encoding="utf-8")
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("\nUSER swarm\n", dockerfile)
        self.assertIn('user: "${SWARM_CONTAINER_USER:-swarm}"', compose)
        self.assertIn('"127.0.0.1:4788:4788"', compose)
        self.assertIn(':/data/codex:ro"', compose)
        self.assertIn(':/data/swarm"', compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)

    def test_explicit_swarm_config_path_drives_safe_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selected=Path(directory) / "selected.toml"; selected.write_text("",encoding="utf-8")
            environment=self._run_main({"SWARM_CONFIG_PATH":str(selected)},getuid=None,getgid=None)
            self.assertEqual(environment["SWARM_CONFIG_HOME"],str(selected.parent))
            self.assertEqual(environment["SWARM_CONTAINER_CONFIG_PATH"],"/data/swarm/selected.toml")

    def test_explicit_environment_config_is_mounted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            custom=Path(directory) / "custom.toml"; custom.write_text("",encoding="utf-8")
            environment=self._run_main({"SWARM_CONFIG_PATH":str(custom)},getuid=None,getgid=None)
            self.assertEqual(environment["SWARM_CONFIG_HOME"],str(custom.parent))
            self.assertEqual(environment["SWARM_CONTAINER_CONFIG_PATH"],"/data/swarm/custom.toml")


if __name__ == "__main__":
    unittest.main()
