import unittest

from skills.swarm.runtime.agent_colors import (
    AGENT_COLOR_REGISTRY,
    AGENT_COLOR_REGISTRY_DIGEST,
    CTRL_RESERVED_COLOR_NAMES,
    DISPLAY_NAME,
    ELIGIBLE_AGENT_COLOR_NAMES,
    FRIENDLY_NAME,
    assign_agent_color,
    project_agent_color_registry,
    valid_display_name,
)


class AgentColorContractTests(unittest.TestCase):
    def test_registry_is_large_single_word_unique_and_provenanced(self) -> None:
        self.assertGreaterEqual(len(AGENT_COLOR_REGISTRY), 100)
        self.assertEqual(len({item.name.casefold() for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertEqual(len({item.hex for item in AGENT_COLOR_REGISTRY}), len(AGENT_COLOR_REGISTRY))
        self.assertTrue(all(item.source and item.hex.startswith("#") and len(item.hex) == 7 for item in AGENT_COLOR_REGISTRY))
        by_name = {item.name: item.hex for item in AGENT_COLOR_REGISTRY}
        self.assertEqual({name: by_name[name] for name in ("Mint", "Rose", "Amber")}, {
            "Mint": "#5EEAD4", "Rose": "#F43F5E", "Amber": "#FBBF24",
        })
        self.assertTrue(all(FRIENDLY_NAME.fullmatch(item.name) for item in AGENT_COLOR_REGISTRY))
        self.assertTrue(all(not any(character.isspace() for character in item.name) and "_" not in item.name for item in AGENT_COLOR_REGISTRY))
        self.assertIn("Coral", CTRL_RESERVED_COLOR_NAMES)
        self.assertNotIn("Coral", ELIGIBLE_AGENT_COLOR_NAMES)

    def test_assignment_is_lookup_only_stable_and_case_insensitive(self) -> None:
        first = assign_agent_color("agent-a", structural_role="DOER", requested_name="Blue")
        replay = assign_agent_color("agent-a", "#0000FF", (("agent-a", first.name),))
        second = assign_agent_color("agent-b", assignments=(("agent-a", first.name),), structural_role="DOER", requested_name="blue")
        self.assertEqual((first.name, first.hex), ("Blue", "#1D4ED8"))
        self.assertEqual(replay, first)
        self.assertEqual(second.name, "Blue II")

    def test_palette_exhaustion_uses_stable_roman_suffix(self) -> None:
        first = assign_agent_color("overflow-a", assignments=(("agent-a", "Blue"),), structural_role="DOER", requested_name="Blue")
        second = assign_agent_color("overflow-b", assignments=(("agent-a", "Blue"), ("agent-b", "Blue II")), structural_role="DOER", requested_name="Blue")
        self.assertEqual(first.name, "Blue II")
        self.assertEqual(second.name, "Blue III")
        self.assertEqual(first.hex, "#1D4ED8")

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
        with self.assertRaisesRegex(ValueError, "reserved for CTRL"):
            assign_agent_color("agent", structural_role="LEAD", requested_name="Coral")
        with self.assertRaisesRegex(ValueError, "structural-role"):
            assign_agent_color("task", structural_role="TASK")

    def test_projection_is_canonical_data_not_a_second_assignment_store(self) -> None:
        projection = project_agent_color_registry()
        self.assertEqual(projection["registry_digest"], AGENT_COLOR_REGISTRY_DIGEST)
        self.assertEqual(projection["duplicate_suffix"]["first_duplicate"], "II")
        self.assertEqual(len(projection["colors"]), len(AGENT_COLOR_REGISTRY))
        self.assertEqual(projection["assignment"], "deterministic_sha256_lookup")


if __name__ == "__main__":
    unittest.main()
