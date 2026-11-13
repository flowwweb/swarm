import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "swarm_mcp.py"
spec = importlib.util.spec_from_file_location("supporter_mcp", SCRIPT)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class SupporterConfigTest(unittest.TestCase):
    def render(self, rows):
        return mcp._supporters_markup(json.dumps(rows).encode())

    def test_safe_links_and_labels(self):
        markup = self.render([{"name": "A & B", "href": "https://example.test/?a=1&b=2", "logo": None}])
        self.assertIn('A &amp; B', markup)
        self.assertIn('href="https://example.test/?a=1&amp;b=2"', markup)
        self.assertIn('data-external', markup)

    def test_rejects_unsafe_or_unknown_fields(self):
        for change in ({"href": "javascript:alert(1)"}, {"href": "https://user:pass@example.test"},
                       {"href": "https://example.test/\nheader"}, {"logo": "../outside.svg"}, {"extra": 1}):
            with self.subTest(change=change), self.assertRaises(mcp.MCPError):
                self.render([{**{"name": "Sponsor", "href": None, "logo": None}, **change}])

    def test_known_logo_embeds_and_unknown_is_rejected(self):
        markup = self.render([{"name": "Boatpedia", "href": None, "logo": "boatpedia-logo-dark.svg"}])
        self.assertIn('alt="Boatpedia"', markup)
        self.assertIn('src="data:image/svg+xml;base64,', markup)
        png = self.render([{"name": "Bluprint", "href": None, "logo": "bluprint-wordmark-alpha-990.png"}])
        self.assertIn('alt="Bluprint"', png)
        self.assertIn('src="data:image/png;base64,', png)
        with self.assertRaises(mcp.MCPError):
            self.render([{"name": "Helm", "href": None, "logo": "unreviewed.svg"}])

    def test_held_logos_render_as_accessible_names_and_are_not_packaged(self):
        import hashlib
        from scripts.build_package import _source_included
        rows = json.loads((mcp.REPO_ROOT / "skills/swarm/assets/ui/supporters.json").read_bytes())
        self.assertEqual([row["name"] for row in rows], ["Nemo", "Boatpedia", "Bluprint", "Helm", "RightWork", "Whxtever", "Unbake", "FontGoblin"])
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Nemo"], {"name": "Nemo", "href": "https://nemoboat.app", "logo": None})
        self.assertEqual(by_name["Helm"], {"name": "Helm", "href": None, "logo": None})
        markup = self.render(rows)
        self.assertIn('<li><a data-external href="https://nemoboat.app">Nemo</a></li>', markup)
        self.assertIn('<li>Helm</li>', markup)
        held = {
            "nemo-horizontal-canonical-on-dark.svg": "0a5823943d93fb8df3ef3283f7249d2015148a9e3cde345fde3f8dfae37a2fb2",
            "helm-lockup-white.svg": "0016c40141d10081755ab2d5752816e84cc9ed8c160379a51848b7e7ba6cfb4a",
        }
        for name, digest in held.items():
            path = Path("skills/swarm/assets/ui/brand/supporters") / name
            self.assertFalse(_source_included(path))
            self.assertNotIn(name, mcp.SUPPORTER_LOGOS)
            self.assertEqual(hashlib.sha256((mcp.REPO_ROOT / path).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
