from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = REPOSITORY_ROOT / "scripts" / "build_package.py"
VERIFIER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_plugin_install.py"

sys.path.insert(0, str(BUILDER_PATH.parent))
import build_package as package_builder
from build_package import (
    PACKAGE_METADATA_PATH,
    build_package_bytes,
    installed_file_hashes,
    normalise_relative_path,
    source_file_hashes,
    write_package,
)

SPEC = importlib.util.spec_from_file_location("verify_plugin_install_tested", VERIFIER_PATH)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class ReleasePackageTests(unittest.TestCase):
    @staticmethod
    def write_sidecar(package: Path) -> None:
        package.with_name(package.name + ".sha256").write_bytes(
            f"{hashlib.sha256(package.read_bytes()).hexdigest()}  {package.name}\n".encode("ascii")
        )

    def write_archive(self, package: Path, metadata: dict[str, object], entries: list[object]) -> None:
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(PACKAGE_METADATA_PATH, json.dumps(metadata, sort_keys=True))
            for entry in entries:
                if isinstance(entry, zipfile.ZipInfo):
                    archive.writestr(entry, "entry\n")
                else:
                    archive.writestr(entry, "entry\n")
        self.write_sidecar(package)

    @staticmethod
    def archive_identity(files: dict[str, str] | None = None) -> dict[str, object]:
        return {
            "schema": "swarm-package-v1",
            "version": "1.2.3",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "files": files or {},
        }

    def make_plugin(self, parent: Path) -> Path:
        root = parent / "plugin"
        files = {
            ".codex-plugin/plugin.json": '{"version":"1.2.3","skills":"./skills/"}\n',
            "skills/swarm/SKILL.md": "# SWARM\n",
            "skills/swarm/scripts/swarm_console.py": "print('console')\n",
            "console/Dockerfile": "FROM python:3.11-slim\n",
            "console/docker-compose.yml": "services: {}\n",
            "console/static/index.html": "<title>SWARM</title>\n",
            "docs/console.md": "# Console\n",
            "README.md": "# SWARM\n",
            "SECURITY.md": "# Security\n",
            "CONTRIBUTING.md": "# Contributing\n",
            "LICENSE": "MIT\n",
        }
        for relative, contents in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SWARM tests"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return root

    def test_repeated_clean_builds_are_byte_identical_and_record_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            first, first_metadata = build_package_bytes(root)
            second, second_metadata = build_package_bytes(root)
            self.assertEqual(first, second)
            self.assertEqual(first_metadata, second_metadata)
            self.assertEqual(first_metadata["version"], "1.2.3")
            self.assertRegex(first_metadata["commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(first_metadata["tree"], r"^[0-9a-f]{40}$")

            output = Path(temporary) / "swarm.zip"
            checksum, count = write_package(root, output, verify_repeat=True)
            self.assertEqual(checksum, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(count, len(first_metadata["files"]))
            self.assertEqual(
                output.with_name("swarm.zip.sha256").read_text(encoding="ascii"),
                f"{checksum}  swarm.zip\n",
            )

    def test_release_excludes_development_only_material_from_the_declared_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            development_files = {
                "skills/swarm/tests/test_contract.py": "test\n",
                "skills/swarm/evals/evals.json": "{}\n",
                "skills/swarm/evals/fixtures/case.json": "{}\n",
                ".github/workflows/validate.yml": "name: validate\n",
                "docs/friction-audit.md": "internal\n",
            }
            for relative, contents in development_files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "development material"], check=True)

            payload, metadata = build_package_bytes(root)
            self.assertTrue(set(development_files).isdisjoint(metadata["files"]))
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertTrue(set(development_files).isdisjoint(archive.namelist()))

    def test_source_verifier_rejects_development_material_in_an_installed_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_plugin(Path(temporary) / "source")
            installed = Path(temporary) / "installed"
            shutil.copytree(source, installed, ignore=shutil.ignore_patterns(".git"))
            for root in (source, installed):
                path = root / "skills" / "swarm" / "tests" / "test_contract.py"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "development test"], check=True)

            with self.assertRaisesRegex(ValueError, "skills/swarm/tests/test_contract.py"):
                verifier.verify(source, installed)

    def test_path_safety_rejects_absolute_and_traversal_names(self) -> None:
        for path in (
            Path("../escape"),
            Path("nested/../escape"),
            Path("C:/escape"),
            Path("folder/CON.txt"),
            Path("name. "),
            "bad?.txt",
            "bad*.txt",
            "bad|.txt",
            'bad".txt',
            "bad<.txt",
            "bad\x1f.txt",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    normalise_relative_path(path)

    def test_package_verifier_rejects_unsafe_or_windows_ambiguous_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, name in enumerate((
                "../escape.txt", "/absolute.txt", "C:/drive.txt", "CON", "name. ",
                "bad?.txt", "bad*.txt", "bad|.txt", 'bad".txt', "bad<.txt", "bad\x1f.txt",
            )):
                package = root / f"unsafe-{index}.zip"
                self.write_archive(package, self.archive_identity(), [name])
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unsafe"):
                    verifier.verify_package(package, root / "installed")

            backslash = zipfile.ZipInfo("placeholder")
            backslash.filename = "folder\\backslash.txt"
            package = root / "backslash.zip"
            self.write_archive(package, self.archive_identity(), [backslash])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verifier.verify_package(package, root / "installed")

            collision = root / "collision.zip"
            self.write_archive(collision, self.archive_identity(), ["README.md", "readme.md"])
            with self.assertRaisesRegex(ValueError, "collision"):
                verifier.verify_package(collision, root / "installed")

            link = zipfile.ZipInfo("link")
            link.external_attr = 0o120777 << 16
            package = root / "link.zip"
            self.write_archive(package, self.archive_identity(), [link])
            with self.assertRaisesRegex(ValueError, "link or reparse"):
                verifier.verify_package(package, root / "installed")

            reparse = zipfile.ZipInfo("reparse")
            reparse.external_attr = 0x0400
            package = root / "reparse.zip"
            self.write_archive(package, self.archive_identity(), [reparse])
            with self.assertRaisesRegex(ValueError, "link or reparse"):
                verifier.verify_package(package, root / "installed")

            for mode in (0o010644, 0o020644):
                non_regular = zipfile.ZipInfo(f"mode-{mode:o}")
                non_regular.external_attr = mode << 16
                package = root / f"mode-{mode:o}.zip"
                self.write_archive(package, self.archive_identity(), [non_regular])
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "link or reparse"):
                    verifier.verify_package(package, root / "installed")

    def test_dirty_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            (root / "README.md").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source bytes differ from HEAD"):
                build_package_bytes(root)

    def test_assume_unchanged_cannot_hide_changed_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            subprocess.run(
                ["git", "-C", str(root), "update-index", "--assume-unchanged", "README.md"],
                check=True,
            )
            (root / "README.md").write_text("hidden working-tree edit\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source bytes differ from HEAD.*README.md"):
                build_package_bytes(root)

    def test_archive_uses_captured_blobs_when_working_tree_changes_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            expected = subprocess.run(
                ["git", "-C", str(root), "show", "HEAD:README.md"],
                capture_output=True,
                check=True,
            ).stdout
            original_hashes = package_builder.source_file_hashes

            def validate_then_mutate(target: Path) -> dict[str, str]:
                hashes = original_hashes(target)
                (root / "README.md").write_text("changed after validation\n", encoding="utf-8")
                return hashes

            with mock.patch.object(package_builder, "source_file_hashes", side_effect=validate_then_mutate):
                payload, metadata = build_package_bytes(root)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                self.assertEqual(archive.read("README.md"), expected)
            self.assertEqual(metadata["files"]["README.md"], hashlib.sha256(expected).hexdigest())

    def test_captured_snapshot_rejects_nfc_nfd_path_aliases_before_build(self) -> None:
        blob_contents = {
            "1" * 40: b'{"version":"1.2.3","skills":"./skills/"}\n',
            "2" * 40: b"# SWARM\n",
            "3" * 40: b"composed\n",
            "4" * 40: b"decomposed\n",
        }
        entries = (
            (".codex-plugin/plugin.json", "1" * 40),
            ("skills/swarm/SKILL.md", "2" * 40),
            ("docs/caf\u00e9.md", "3" * 40),
            ("docs/cafe\u0301.md", "4" * 40),
        )
        tree = b"".join(
            f"100644 blob {object_id}\t{name}".encode("utf-8") + b"\0"
            for name, object_id in entries
        )

        def git_snapshot(_root: Path, *arguments: str) -> bytes:
            if arguments[0] == "ls-tree":
                return tree
            return blob_contents[arguments[-1]]

        with mock.patch.object(package_builder, "_git_bytes", side_effect=git_snapshot), self.assertRaisesRegex(
            ValueError, "Windows-normalized collision"
        ):
            package_builder._capture_snapshot(Path("."), "a" * 40, "b" * 40)

    def test_tracked_case_alias_of_generated_metadata_is_rejected_before_emission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            (root / "SWARM-PACKAGE.JSON").write_text("tracked alias\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "SWARM-PACKAGE.JSON"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "metadata alias"], check=True)
            with mock.patch.object(package_builder, "_build_snapshot_bytes") as emit, self.assertRaisesRegex(
                ValueError, "Windows-normalized collision"
            ):
                build_package_bytes(root)
            emit.assert_not_called()

    def test_source_parity_rejects_tamper_missing_and_extra_product_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            installed = Path(temporary) / "installed"
            shutil.copytree(root, installed, ignore=shutil.ignore_patterns(".git"))
            self.assertEqual(verifier.verify(root, installed), len(verifier.declared_files(root)))
            (installed / "README.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed=.*README.md"):
                verifier.verify(root, installed)
            shutil.copy2(root / "README.md", installed / "README.md")
            (installed / "SECURITY.md").unlink()
            with self.assertRaisesRegex(ValueError, "missing=.*SECURITY.md"):
                verifier.verify(root, installed)
            shutil.copy2(root / "SECURITY.md", installed / "SECURITY.md")
            (installed / "unexpected.txt").write_text("extra\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "extra=.*unexpected.txt"):
                verifier.verify(root, installed)

    def test_cli_reports_expected_parity_failure_without_traceback_or_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            installed = Path(temporary) / "installed"
            shutil.copytree(root, installed, ignore=shutil.ignore_patterns(".git"))
            (installed / "README.md").unlink()
            completed = subprocess.run(
                [sys.executable, str(VERIFIER_PATH), str(installed), "--source", str(root)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue(completed.stderr.startswith("error: plugin tree mismatch:"))
            self.assertNotIn("Traceback", completed.stderr)
            self.assertNotIn(str(root), completed.stderr)
            self.assertNotIn(str(installed), completed.stderr)

    def test_installed_parity_ignores_only_host_metadata_and_rejects_loose_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            installed = Path(temporary) / "installed"
            shutil.copytree(root, installed, ignore=shutil.ignore_patterns(".git"))
            (installed / ".git").mkdir()
            (installed / ".git" / "config").write_text("host metadata\n", encoding="utf-8")
            (installed / "__pycache__").mkdir()
            (installed / "__pycache__" / "generated.pyc").write_bytes(b"cache")
            (installed / PACKAGE_METADATA_PATH).write_text("generated metadata\n", encoding="utf-8")
            self.assertEqual(verifier.verify(root, installed), len(verifier.declared_files(root)))
            for relative in ("error.log", "loose.pyc", "state.sqlite", "dist/output.txt", "node_modules/pkg.js"):
                candidate = installed / relative
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text("unexpected\n", encoding="utf-8")
                with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "extra"):
                    verifier.verify(root, installed)
                candidate.unlink()

    def test_source_and_installed_policies_reject_junctions_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            (root / "linked").mkdir()
            with mock.patch.object(
                Path, "is_junction", lambda path: path.name == "linked", create=True
            ):
                with self.assertRaisesRegex(ValueError, "link or junction"):
                    source_file_hashes(root)
                with self.assertRaisesRegex(ValueError, "link or junction"):
                    installed_file_hashes(root)

    def test_python_311_reparse_attribute_fallback_and_ignored_cache_redirect_are_rejected(self) -> None:
        with mock.patch.object(Path, "is_junction", None, create=True), mock.patch.object(
            package_builder.os,
            "lstat",
            return_value=SimpleNamespace(st_file_attributes=0x0400),
        ):
            self.assertTrue(package_builder._is_reparse_path(Path("junction")))

        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            (root / "__pycache__").mkdir()
            with mock.patch.object(
                package_builder,
                "_is_reparse_path",
                side_effect=lambda path: path.name == "__pycache__",
            ), self.assertRaisesRegex(ValueError, "link or junction"):
                installed_file_hashes(root)

    def test_package_metadata_identity_and_checksum_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            installed = Path(temporary) / "installed"
            package = Path(temporary) / "swarm.zip"
            write_package(root, package)
            with zipfile.ZipFile(package) as archive:
                archive.extractall(installed)

            invalid = (
                ("schema", "other-schema", "schema"),
                ("version", "", "version"),
                ("version", "9.9.9", "version does not match"),
                ("commit", "A" * 40, "commit"),
                ("tree", "b" * 39, "tree"),
                ("digest", "c" * 63, "file manifest"),
            )
            for index, (field, value, error) in enumerate(invalid):
                mutated = Path(temporary) / f"identity-{index}.zip"
                with zipfile.ZipFile(package) as source, zipfile.ZipFile(mutated, "w") as target:
                    metadata = json.loads(source.read(PACKAGE_METADATA_PATH))
                    if field == "digest":
                        first = next(iter(metadata["files"]))
                        metadata["files"][first] = value
                    else:
                        metadata[field] = value
                    for entry in source.infolist():
                        contents = source.read(entry)
                        if entry.filename == PACKAGE_METADATA_PATH:
                            contents = json.dumps(metadata, sort_keys=True).encode("utf-8")
                        target.writestr(entry.filename, contents)
                self.write_sidecar(mutated)
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, error):
                    verifier.verify_package(mutated, installed)

            sidecar = package.with_name(package.name + ".sha256")
            for contents in (b"not-a-checksum\n", f"{'0' * 64}  other.zip\n".encode("ascii"), f"{'0' * 64}  swarm.zip\n".encode("ascii")):
                sidecar.write_bytes(contents)
                with self.subTest(sidecar=contents), self.assertRaisesRegex(ValueError, "checksum sidecar"):
                    verifier.verify_package(package, installed)

    def test_package_parity_covers_full_shipped_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_plugin(Path(temporary))
            package = Path(temporary) / "swarm.zip"
            write_package(root, package, verify_repeat=True)
            installed = Path(temporary) / "installed"
            with zipfile.ZipFile(package) as archive:
                archive.extractall(installed)
            self.assertEqual(
                verifier.verify_package(package, installed), len(verifier.declared_files(root))
            )
            self.assertTrue((installed / PACKAGE_METADATA_PATH).is_file())
            self.assertTrue((installed / "console" / "Dockerfile").is_file())
            self.assertTrue((installed / "docs" / "console.md").is_file())
            self.assertTrue((installed / "SECURITY.md").is_file())
            metadata = json.loads((installed / PACKAGE_METADATA_PATH).read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema"], "swarm-package-v1")

    def test_package_path_swap_after_checksum_cannot_change_verified_zip_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary)
            original_root = self.make_plugin(temp_root / "original")
            replacement_root = self.make_plugin(temp_root / "replacement")
            (replacement_root / "README.md").write_text("replacement release\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(replacement_root), "add", "README.md"], check=True)
            subprocess.run(["git", "-C", str(replacement_root), "commit", "-qm", "replacement"], check=True)

            package = temp_root / "original.zip"
            replacement = temp_root / "replacement.zip"
            write_package(original_root, package)
            write_package(replacement_root, replacement)
            installed = temp_root / "installed"
            with zipfile.ZipFile(replacement) as archive:
                archive.extractall(installed)

            replacement_bytes = replacement.read_bytes()
            normal_read_bytes = Path.read_bytes
            package_reads = 0

            def swap_after_snapshot(path: Path) -> bytes:
                nonlocal package_reads
                contents = normal_read_bytes(path)
                if path == package:
                    package_reads += 1
                    package.write_bytes(replacement_bytes)
                return contents

            with mock.patch.object(Path, "read_bytes", swap_after_snapshot), self.assertRaisesRegex(
                ValueError, "plugin tree mismatch"
            ):
                verifier.verify_package(package, installed)
            self.assertEqual(package_reads, 1)


if __name__ == "__main__":
    unittest.main()
