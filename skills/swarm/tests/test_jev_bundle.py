"""Exercise the actual vendored Jev/Zod bundle offline, including code literals."""
from pathlib import Path
import shutil
import subprocess
import unittest


class JevBundleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for the Jev bundle contract")
    def test_vendored_bundle_security_and_compatibility(self):
        script = Path(__file__).with_name("jev_bundle_contract.mjs")
        result = subprocess.run([shutil.which("node"), "--test", str(script)],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
