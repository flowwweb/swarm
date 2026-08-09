from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rush_config.py"
SPEC = importlib.util.spec_from_file_location("rush_config_tested", SCRIPT)
assert SPEC and SPEC.loader
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class RushConfigTests(unittest.TestCase):
    def test_usage_saver_is_off_in_defaults_and_template(self) -> None:
        self.assertFalse(config.DEFAULTS["execution"]["usage_saver"])
        effective, exists = config.load(config.TEMPLATE_PATH)
        self.assertTrue(exists)
        self.assertFalse(effective["execution"]["usage_saver"])

    def test_existing_config_without_usage_saver_merges_off(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[execution]\nusage_profile = "low"\n', encoding="utf-8")
            effective, exists = config.load(path)
        self.assertTrue(exists)
        self.assertEqual(effective["execution"]["usage_profile"], "low")
        self.assertFalse(effective["execution"]["usage_saver"])

    def test_usage_saver_accepts_only_a_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = root / "enabled.toml"
            enabled.write_text("[execution]\nusage_saver = true\n", encoding="utf-8")
            effective, _ = config.load(enabled)
            self.assertTrue(effective["execution"]["usage_saver"])

            invalid = root / "invalid.toml"
            invalid.write_text('[execution]\nusage_saver = "sometimes"\n', encoding="utf-8")
            with self.assertRaisesRegex(
                config.ConfigError,
                "execution.usage_saver must be true or false",
            ):
                config.load(invalid)

    def test_archive_completed_tasks_defaults_on_and_can_opt_out(self) -> None:
        self.assertTrue(config.DEFAULTS["lifecycle"]["archive_completed_tasks"])
        effective, _ = config.load(config.TEMPLATE_PATH)
        self.assertTrue(effective["lifecycle"]["archive_completed_tasks"])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[lifecycle]\narchive_completed_tasks = false\n",
                encoding="utf-8",
            )
            effective, _ = config.load(path)
        self.assertFalse(effective["lifecycle"]["archive_completed_tasks"])


if __name__ == "__main__":
    unittest.main()
