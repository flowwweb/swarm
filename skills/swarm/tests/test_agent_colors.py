import unittest

from skills.swarm.runtime.agent_colors import (
    AGENT_COLOR_REGISTRY,
    CSS_COLOR_4_SOURCE,
    DISPLAY_NAME,
    FRIENDLY_NAME,
    assign_agent_color,
    valid_display_name,
)


class AgentColorContractTests(unittest.TestCase):
    def test_registry_is_single_word_unique_and_provenanced(self) -> None:
        self.assertEqual(len(AGENT_COLOR_REGISTRY), 83)
        self.assertEqual(len({item.name.casefold() for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertEqual(len({item.hex for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertTrue(all(item.source and item.hex.startswith("#") and len(item.hex) == 7 for item in AGENT_COLOR_REGISTRY))
        self.assertGreater(sum(item.source == CSS_COLOR_4_SOURCE for item in AGENT_COLOR_REGISTRY), 50)
        by_name = {item.name: item.hex for item in AGENT_COLOR_REGISTRY}
        self.assertEqual({name: by_name[name] for name in ("Mint", "Rose", "Amber")}, {
            "Mint": "#3EB489", "Rose": "#E63E62", "Amber": "#FFBF00",
        })
        self.assertTrue(all(FRIENDLY_NAME.fullmatch(item.name) for item in AGENT_COLOR_REGISTRY))
        self.assertTrue(all(not any(character.isspace() for character in item.name) and "_" not in item.name for item in AGENT_COLOR_REGISTRY))

    def test_assignment_is_nearest_free_stable_and_case_insensitive(self) -> None:
        first = assign_agent_color("agent-a", "#FF0000", ())
        replay = assign_agent_color("agent-a", "#0000FF", (("agent-a", first.name),))
        second = assign_agent_color("agent-b", "#FF0000", (("agent-a", first.name.upper()),))
        self.assertEqual((first.name, first.hex), ("Red", "#FF0000"))
        self.assertEqual(replay, first)
        self.assertNotEqual(second.name.casefold(), first.name.casefold())

    def test_palette_exhaustion_uses_stable_roman_suffix(self) -> None:
        occupied = tuple((f"agent-{index}", item.name) for index, item in enumerate(AGENT_COLOR_REGISTRY))
        first = assign_agent_color("overflow-a", "#FF0000", occupied)
        occupied_ii = tuple((f"roman-{index}", f"{item.name} II") for index, item in enumerate(AGENT_COLOR_REGISTRY))
        second = assign_agent_color("overflow-b", "#FF0000", (*occupied, *occupied_ii))
        self.assertEqual(first.name, "Red II")
        self.assertEqual(second.name, "Red III")
        self.assertEqual(first.hex, "#FF0000")

    def test_display_grammar_allows_only_bounded_roman_whitespace(self) -> None:
        examples = ("Violet", "Violet II", "Violet III", "Violet MMMCMXCIX")
        self.assertTrue(all(valid_display_name(name) for name in examples))
        self.assertFalse(valid_display_name("Orange Red"))
        self.assertFalse(valid_display_name("Orange-Red"))
        self.assertFalse(valid_display_name("Violet I"))
        self.assertFalse(valid_display_name("Violet  II"))
        self.assertFalse(valid_display_name("Violet_II"))

    def test_invalid_or_conflicting_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "#RRGGBB"):
            assign_agent_color("agent", "red", ())
        with self.assertRaisesRegex(ValueError, "conflicting"):
            assign_agent_color("agent", "#123456", (("agent", "Red"), ("agent", "Blue")))
        with self.assertRaisesRegex(ValueError, "not in the registry"):
            assign_agent_color("agent", "#123456", (("agent", "Invented"),))


if __name__ == "__main__":
    unittest.main()
