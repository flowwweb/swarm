"""Canonical deterministic agent-color registry.

Color distance is evaluated once while this module is authored/imported. Runtime
assignment is then a bounded dictionary/tuple lookup; it never searches colors,
calls a model, or creates a second assignment authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import MappingProxyType


CTRL_ACCENT_NAME = "Coral"
CTRL_ACCENT_HEXES = ("#FF6B4A", "#FF7A18", "#FF3D32")
MIN_CTRL_OKLAB_DISTANCE = 0.12
_COLOR_NAME = re.compile(r"[A-Z][A-Za-z]*\Z")
_COLOR_HEX = re.compile(r"#[0-9A-F]{6}\Z")
ROMAN_SUFFIX = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})\Z")
DISPLAY_NAME = re.compile(r"[A-Z][A-Za-z]*(?: [IVXLCDM]+)?\Z")
FRIENDLY_NAME = _COLOR_NAME
HEX_COLOR = _COLOR_HEX
CSS_COLOR_4_SOURCE = "W3C CSS Color Module Level 4 named colors"
CURATED_EXTENSION_SOURCE = "SWARM canonical agent colors v2"


@dataclass(frozen=True, slots=True)
class AgentColor:
    name: str
    hex: str
    source: str = CURATED_EXTENSION_SOURCE


_PALETTE = (
    ("Coral", "#FF6B4A"), ("Tangerine", "#F97316"), ("Cyan", "#22D3EE"),
    ("Sky", "#38BDF8"), ("Indigo", "#6366F1"), ("Magenta", "#D946EF"),
    ("Amber", "#FBBF24"), ("Pink", "#F72585"), ("Violet", "#8B5CF6"),
    ("Lavender", "#C084FC"), ("Cobalt", "#2563EB"), ("Rose", "#F43F5E"),
    ("Teal", "#14B8A6"), ("Periwinkle", "#818CF8"), ("Vermilion", "#FF4D2E"),
    ("Silver", "#CBD5E1"), ("Crimson", "#E11D48"), ("Lime", "#A3E635"),
    ("Emerald", "#10B981"), ("Salmon", "#FB7185"), ("Mint", "#5EEAD4"),
    ("Jade", "#2DD4BF"), ("Purple", "#A855F7"), ("Yellow", "#FDE047"),
    ("Aqua", "#06B6D4"), ("Azure", "#0284C7"), ("Blue", "#1D4ED8"),
    ("Denim", "#1E40AF"), ("Iris", "#7C3AED"), ("Lilac", "#D8B4FE"),
    ("Navy", "#1E3A8A"), ("Sapphire", "#0F52BA"), ("Turquoise", "#0D9488"),
    ("Wisteria", "#A78BFA"), ("Plum", "#9333EA"), ("Orchid", "#E879F9"),
    ("Fuchsia", "#C026D3"), ("Ruby", "#BE123C"), ("Scarlet", "#DC2626"),
    ("Cherry", "#B91C1C"), ("Berry", "#9F1239"), ("Wine", "#881337"),
    ("Maroon", "#7F1D1D"), ("Garnet", "#991B1B"), ("Peach", "#FDBA74"),
    ("Apricot", "#FB923C"), ("Orange", "#EA580C"), ("Gold", "#EAB308"),
    ("Lemon", "#FEF08A"), ("Canary", "#FACC15"), ("Butter", "#FDE68A"),
    ("Sand", "#D6D3A3"), ("Beige", "#D4C2A8"), ("Khaki", "#B5A642"),
    ("Tan", "#D2B48C"), ("Bronze", "#CD7F32"), ("Copper", "#B87333"),
    ("Umber", "#635147"), ("Brown", "#7C2D12"), ("Cocoa", "#6F4E37"),
    ("Coffee", "#4B3621"), ("Mocha", "#967969"), ("Chestnut", "#954535"),
    ("Sienna", "#A0522D"), ("Rust", "#B7410E"), ("Clay", "#B66A50"),
    ("Terracotta", "#C96442"), ("Brick", "#A14A3A"), ("Red", "#EF4444"),
    ("Persimmon", "#EC5800"), ("Papaya", "#FFB347"), ("Melon", "#FDBCB4"),
    ("Honey", "#E3A008"), ("Mustard", "#CA8A04"), ("Olive", "#808000"),
    ("Chartreuse", "#84CC16"), ("Green", "#16A34A"), ("Sage", "#84A98C"),
    ("Moss", "#4D7C0F"), ("Fern", "#4F7942"), ("Forest", "#166534"),
    ("Pine", "#14532D"), ("Spruce", "#0F766E"), ("Seafoam", "#99F6E4"),
    ("Celadon", "#ACE1AF"), ("Viridian", "#40826D"), ("Malachite", "#0BDA51"),
    ("Shamrock", "#00A86B"), ("Basil", "#5F8A4C"), ("Avocado", "#568203"),
    ("Pear", "#D1E231"), ("Pistachio", "#93C572"), ("Kiwi", "#8EE53F"),
    ("Meadow", "#65A30D"), ("Lagoon", "#0891B2"), ("Ocean", "#0369A1"),
    ("Glacier", "#7DD3FC"), ("Ice", "#BAE6FD"), ("Gray", "#6B7280"),
    ("Slate", "#475569"), ("Graphite", "#374151"), ("Charcoal", "#36454F"),
    ("Onyx", "#353839"), ("Black", "#111827"), ("White", "#F8FAFC"),
    ("Pearl", "#E2E8F0"), ("Ivory", "#FFFFF0"), ("Cream", "#FFFDD0"),
    ("Snow", "#FFFAFA"), ("Smoke", "#94A3B8"), ("Ash", "#B2BEB5"),
    ("Stone", "#78716C"), ("Flint", "#6F6F6F"), ("Steel", "#64748B"),
    ("Quartz", "#D1D5DB"), ("Opal", "#A8C3BC"), ("Aquamarine", "#7FFFD4"),
    ("Cerulean", "#007BA7"), ("Cornflower", "#6495ED"), ("Ultramarine", "#3F00FF"),
    ("Amethyst", "#9966CC"), ("Mauve", "#E0B0FF"), ("Heliotrope", "#DF73FF"),
    ("Raspberry", "#E30B5C"), ("Blush", "#DE5D83"), ("Flamingo", "#FC8EAC"),
    ("Burgundy", "#800020"), ("Mahogany", "#C04000"), ("Sepia", "#704214"),
    ("Caramel", "#C68E17"), ("Ocher", "#CC7722"), ("Sunflower", "#FFC512"),
    ("Dandelion", "#F0E130"), ("Citron", "#9FA91F"), ("Kelly", "#4CBB17"),
    ("Hunter", "#355E3B"), ("Myrtle", "#317873"), ("Juniper", "#3A5F5F"),
    ("Pebble", "#9CA3AF"), ("Nickel", "#727472"), ("Cloud", "#E5E7EB"),
)


def _oklab(hex_value: str) -> tuple[float, float, float]:
    channels = [int(hex_value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    red, green, blue = linear
    light = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    light_root, medium_root, short_root = (value ** (1 / 3) for value in (light, medium, short))
    return (
        0.2104542553 * light_root + 0.7936177850 * medium_root - 0.0040720468 * short_root,
        1.9779984951 * light_root - 2.4285922050 * medium_root + 0.4505937099 * short_root,
        0.0259040371 * light_root + 0.7827717662 * medium_root - 0.8086757660 * short_root,
    )


def oklab_distance(first: str, second: str) -> float:
    """Return the Euclidean OKLab distance between two exact registry colors."""
    return math.dist(_oklab(first.upper()), _oklab(second.upper()))


AGENT_COLORS = tuple(AgentColor(name, value) for name, value in _PALETTE)
AGENT_COLOR_REGISTRY = AGENT_COLORS
AGENT_COLOR_BY_NAME = MappingProxyType({color.name.casefold(): color for color in AGENT_COLORS})
BUILT_IN_ROLE_ACCENT_NAMES = MappingProxyType({
    "manager": "Coral", "strategist": "Tangerine", "researcher": "Cyan", "analyst": "Sky",
    "specialist": "Indigo", "inventor": "Magenta", "architect": "Amber", "designer": "Pink",
    "artist": "Violet", "writer": "Lavender", "developer": "Cobalt", "producer": "Rose",
    "tester": "Teal", "assistant": "Periwinkle", "security": "Vermilion", "auditor": "Silver",
    "legal": "Crimson", "reviewer": "Lime", "operator": "Emerald", "marketer": "Salmon",
    "support": "Mint", "accountant": "Jade", "recruiter": "Purple", "educator": "Yellow",
})
BUILT_IN_ROLE_ACCENTS = MappingProxyType({
    role_id: AGENT_COLOR_BY_NAME[color_name.casefold()].hex
    for role_id, color_name in BUILT_IN_ROLE_ACCENT_NAMES.items()
})
ELIGIBLE_AGENT_COLORS = tuple(
    color for color in AGENT_COLORS
    if min(oklab_distance(color.hex, accent) for accent in CTRL_ACCENT_HEXES) >= MIN_CTRL_OKLAB_DISTANCE
)
ELIGIBLE_AGENT_COLOR_NAMES = frozenset(color.name for color in ELIGIBLE_AGENT_COLORS)
CTRL_RESERVED_COLOR_NAMES = frozenset(color.name for color in AGENT_COLORS if color.name not in ELIGIBLE_AGENT_COLOR_NAMES)
AGENT_COLOR_REGISTRY_DIGEST = hashlib.sha256(
    json.dumps(_PALETTE, separators=(",", ":")).encode("utf-8")
).hexdigest()


def validate_agent_color_registry() -> None:
    """Fail closed if the authored registry or frozen eligibility set drifts."""
    names = [color.name for color in AGENT_COLORS]
    hexes = [color.hex for color in AGENT_COLORS]
    if len(AGENT_COLORS) < 100 or len(names) != len(set(names)) or len(hexes) != len(set(hexes)):
        raise ValueError("agent color registry requires at least 100 unique names and hex values")
    if any(not _COLOR_NAME.fullmatch(name) for name in names) or any(not _COLOR_HEX.fullmatch(value) for value in hexes):
        raise ValueError("agent colors require single-word names and exact six-digit hex values")
    if not {"Mint", "Rose", "Amber"}.issubset(names) or CTRL_ACCENT_NAME not in CTRL_RESERVED_COLOR_NAMES:
        raise ValueError("agent color registry is missing required or CTRL-reserved colors")
    if len(BUILT_IN_ROLE_ACCENTS) != 24 or len(set(BUILT_IN_ROLE_ACCENTS.values())) != 24:
        raise ValueError("built-in role accents must be 24 unique registry colors")
    recomputed = frozenset(
        color.name for color in AGENT_COLORS
        if min(oklab_distance(color.hex, accent) for accent in CTRL_ACCENT_HEXES) >= MIN_CTRL_OKLAB_DISTANCE
    )
    if recomputed != ELIGIBLE_AGENT_COLOR_NAMES:
        raise ValueError("agent color eligibility drifted from the authored OKLab boundary")


def _roman(number: int) -> str:
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 3999:
        raise ValueError("color occurrence must be between 1 and 3999")
    pieces: list[str] = []
    for value, token in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
        (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
        (5, "V"), (4, "IV"), (1, "I"),
    ):
        count, number = divmod(number, value)
        pieces.append(token * count)
    return "".join(pieces)


def valid_display_name(value: str) -> bool:
    if not isinstance(value, str) or not DISPLAY_NAME.fullmatch(value):
        return False
    parts = value.split(" ", 1)
    return len(parts) == 1 or (parts[1] != "I" and bool(ROMAN_SUFFIX.fullmatch(parts[1])))


def _retained_occurrence(display_name: str, base_name: str) -> int | None:
    if display_name.casefold() == base_name.casefold():
        return 1
    prefix = f"{base_name} "
    if not display_name.casefold().startswith(prefix.casefold()):
        return None
    suffix = display_name[len(prefix):]
    if suffix == "I" or not ROMAN_SUFFIX.fullmatch(suffix):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for token in reversed(suffix):
        value = values[token]
        total += -value if value < previous else value
        previous = max(previous, value)
    return total if 2 <= total <= 3999 and _roman(total) == suffix else None


def assign_agent_color(
    agent_id: str,
    requested_accent: str | None = None,
    assignments: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
    *,
    structural_role: str = "DOER",
    requested_name: str | None = None,
    occurrence: int | None = None,
) -> AgentColor:
    """Resolve one stable color using lookup plus one retained-identity pass."""
    identity = str(agent_id).strip()
    role = str(structural_role).strip().upper()
    if not identity or len(identity) > 256 or role not in {"CTRL", "LEAD", "DOER"}:
        raise ValueError("agent color assignment requires bounded agent and structural-role identities")
    retained: dict[str, str] = {}
    occupied: list[str] = []
    for assigned_agent, display_name in assignments:
        if assigned_agent in retained and retained[assigned_agent] != display_name:
            raise ValueError("an agent cannot have conflicting retained identities")
        retained[assigned_agent] = display_name
        occupied.append(display_name)
    existing = retained.get(identity)
    if existing is not None:
        if not valid_display_name(existing):
            raise ValueError("retained agent identity has invalid display grammar")
        base_name = existing.split(" ", 1)[0]
        color = AGENT_COLOR_BY_NAME.get(base_name.casefold())
        if color is None:
            raise ValueError("retained agent identity is not in the registry")
        if role != "CTRL" and color.name not in ELIGIBLE_AGENT_COLOR_NAMES:
            raise ValueError("retained agent identity uses a CTRL-reserved color")
        return AgentColor(existing, color.hex, color.source)
    if requested_name is None:
        requested_hex = None if requested_accent is None else str(requested_accent).strip().upper()
        if requested_hex is not None and not _COLOR_HEX.fullmatch(requested_hex):
            raise ValueError("accent must be an exact #RRGGBB color")
        exact_color = next((item for item in AGENT_COLORS if item.hex == requested_hex), None)
        if exact_color is not None:
            color = exact_color
        elif role == "CTRL":
            color = AGENT_COLOR_BY_NAME[CTRL_ACCENT_NAME.casefold()]
        else:
            seed = f"{identity}|{requested_hex or ''}".encode("utf-8")
            index = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") % len(ELIGIBLE_AGENT_COLORS)
            color = ELIGIBLE_AGENT_COLORS[index]
    else:
        color = AGENT_COLOR_BY_NAME.get(str(requested_name).strip().casefold())
        if color is None:
            raise ValueError("requested agent color is not in the canonical registry")
        if role != "CTRL" and color.name not in ELIGIBLE_AGENT_COLOR_NAMES:
            raise ValueError("requested agent color is reserved for CTRL")
    if role != "CTRL" and color.name not in ELIGIBLE_AGENT_COLOR_NAMES:
        raise ValueError("requested agent color is reserved for CTRL")
    if occurrence is None:
        used = [value for name in occupied if (value := _retained_occurrence(name, color.name)) is not None]
        occurrence = max(used, default=0) + 1
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        raise ValueError("color occurrence must be a positive integer")
    display_name = color.name if occurrence == 1 else f"{color.name} {_roman(occurrence)}"
    return AgentColor(display_name, color.hex, color.source)


def project_agent_color_registry() -> dict[str, object]:
    """Return the sole data-only projection intended for later UI consumption."""
    return {
        "schema_version": 1,
        "registry_digest": AGENT_COLOR_REGISTRY_DIGEST,
        "ctrl_accent": {"name": CTRL_ACCENT_NAME, "hexes": list(CTRL_ACCENT_HEXES)},
        "minimum_ctrl_oklab_distance": MIN_CTRL_OKLAB_DISTANCE,
        "colors": [
            {"name": color.name, "hex": color.hex, "eligible_for_non_ctrl": color.name in ELIGIBLE_AGENT_COLOR_NAMES}
            for color in AGENT_COLORS
        ],
        "built_in_role_accents": dict(BUILT_IN_ROLE_ACCENT_NAMES),
        "duplicate_suffix": {"style": "roman", "first_duplicate": "II"},
        "assignment": "deterministic_sha256_lookup",
    }


validate_agent_color_registry()
