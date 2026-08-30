import unittest

from skills.swarm.runtime.agent_colors import (
    AGENT_COLOR_REGISTRY,
    CSS_COLOR_4_SOURCE,
    FRIENDLY_NAME,
    assign_agent_color,
)


class AgentColorContractTests(unittest.TestCase):
    def test_registry_is_large_unique_and_provenanced(self) -> None:
        self.assertGreater(len(AGENT_COLOR_REGISTRY), 120)
        self.assertEqual(len({item.name.casefold() for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertEqual(len({item.hex for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertTrue(all(item.source and item.hex.startswith("#") and len(item.hex) == 7 for item in AGENT_COLOR_REGISTRY))
        self.assertGreater(sum(item.source == CSS_COLOR_4_SOURCE for item in AGENT_COLOR_REGISTRY), 100)
        self.assertTrue(all(FRIENDLY_NAME.fullmatch(item.name) for item in AGENT_COLOR_REGISTRY))
        self.assertTrue(all(not any(character.isspace() for character in item.name) and "_" not in item.name for item in AGENT_COLOR_REGISTRY))

    def test_assignment_is_nearest_free_stable_and_case_insensitive(self) -> None:
        first = assign_agent_color("agent-a", "#FF0000", ())
        replay = assign_agent_color("agent-a", "#0000FF", (("agent-a", first.name),))
        second = assign_agent_color("agent-b", "#FF0000", (("agent-a", first.name.upper()),))
        self.assertEqual((first.name, first.hex), ("Red", "#FF0000"))
        self.assertEqual(replay, first)
        self.assertNotEqual(second.name.casefold(), first.name.casefold())

    def test_palette_exhaustion_uses_stable_numeric_suffix(self) -> None:
        occupied = tuple((f"agent-{index}", item.name) for index, item in enumerate(AGENT_COLOR_REGISTRY))
        first = assign_agent_color("overflow-a", "#FF0000", occupied)
        second = assign_agent_color("overflow-b", "#FF0000", (*occupied, ("overflow-a", first.name)))
        self.assertEqual(first.name, "Red-2")
        self.assertEqual(second.name, "Red-3")
        self.assertEqual(first.hex, "#FF0000")

    def test_single_word_pool_precedes_nearer_compound_then_suffixes(self) -> None:
        singles = tuple(item for item in AGENT_COLOR_REGISTRY if "-" not in item.name)
        compounds = tuple(item for item in AGENT_COLOR_REGISTRY if "-" in item.name)
        self.assertTrue(singles)
        self.assertTrue(compounds)
        nearest_red_single = assign_agent_color("single", "#F0F8FF", ())
        self.assertNotIn("-", nearest_red_single.name)
        occupied_singles = tuple((f"single-{index}", item.name) for index, item in enumerate(singles))
        reserve = assign_agent_color("reserve", "#F0F8FF", occupied_singles)
        self.assertIn("-", reserve.name)
        self.assertFalse(reserve.name.rsplit("-", 1)[-1].isdigit())
        occupied_all = tuple((f"all-{index}", item.name) for index, item in enumerate(AGENT_COLOR_REGISTRY))
        exhausted = assign_agent_color("exhausted", "#F0F8FF", occupied_all)
        self.assertTrue(exhausted.name.rsplit("-", 1)[-1].isdigit())

    def test_invalid_or_conflicting_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "#RRGGBB"):
            assign_agent_color("agent", "red", ())
        with self.assertRaisesRegex(ValueError, "conflicting"):
            assign_agent_color("agent", "#123456", (("agent", "Red"), ("agent", "Blue")))
        with self.assertRaisesRegex(ValueError, "not in the registry"):
            assign_agent_color("agent", "#123456", (("agent", "Invented"),))


if __name__ == "__main__":
    unittest.main()
