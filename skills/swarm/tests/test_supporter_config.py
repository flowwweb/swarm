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
        markup = self.render([{"name": "Helm", "href": None, "logo": "helm-lockup-white.svg"}])
        self.assertIn('alt="Helm"', markup)
        self.assertIn('src="data:image/svg+xml;base64,', markup)
        png = self.render([{"name": "Bluprint", "href": None, "logo": "bluprint-wordmark-alpha-990.png"}])
        self.assertIn('alt="Bluprint"', png)
        self.assertIn('src="data:image/png;base64,', png)
        with self.assertRaises(mcp.MCPError):
            self.render([{"name": "Helm", "href": None, "logo": "unreviewed.svg"}])


if __name__ == "__main__":
    unittest.main()
