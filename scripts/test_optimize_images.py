from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.optimize_images import OptimizationError, optimize_directory


class OptimizeImagesTests(unittest.TestCase):
    def test_generates_and_rechecks_transparent_webp_and_avif(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            image = Image.new("RGBA", (32, 32), (255, 106, 61, 255))
            image.putpixel((0, 0), (0, 0, 0, 0))
            image.save(source / "sample.png")

            manifest = optimize_directory(source, output, sizes=(16, 32), formats=("webp", "avif"), require_alpha=True)
            self.assertEqual([asset["id"] for asset in manifest["assets"]], ["sample"])
            self.assertEqual(len(manifest["assets"][0]["derivatives"]), 4)
            for derivative in manifest["assets"][0]["derivatives"]:
                path = output / derivative["path"]
                self.assertTrue(path.is_file())
                with Image.open(path) as optimized:
                    self.assertEqual(optimized.size, (derivative["width"], derivative["height"]))
                    self.assertIn("A", optimized.getbands())
            optimize_directory(source, output, sizes=(16, 32), formats=("webp", "avif"), require_alpha=True, check=True)
            optimize_directory(source, output, sizes=(16, 32), formats=("webp", "avif"), require_alpha=True, reuse_existing=True)

            (output / "sample-16.webp").write_bytes(b"stale")
            with self.assertRaisesRegex(OptimizationError, "missing or stale"):
                optimize_directory(source, output, sizes=(16, 32), formats=("webp", "avif"), require_alpha=True, check=True)

    def test_rejects_opaque_source_when_alpha_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            Image.new("RGB", (32, 32), (255, 106, 61)).save(source / "opaque.png")
            with self.assertRaisesRegex(OptimizationError, "no transparent pixels"):
                optimize_directory(source, output, sizes=(16,), formats=("webp",), require_alpha=True)


if __name__ == "__main__":
    unittest.main()
