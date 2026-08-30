"""Deterministic, dependency-free display identities for agent instances."""
from __future__ import annotations

from dataclasses import dataclass
from math import cbrt
import re
from typing import Iterable


CSS_COLOR_4_SOURCE = "W3C CSS Color Module Level 4 named colors"
CURATED_EXTENSION_SOURCE = "SWARM curated friendly display colors v1"
HEX_COLOR = re.compile(r"#[0-9A-F]{6}\Z")
FRIENDLY_NAME = re.compile(r"[A-Z][A-Za-z0-9]*(?:-[A-Z0-9][A-Za-z0-9]*)*\Z")


@dataclass(frozen=True, slots=True)
class AgentColor:
    name: str
    hex: str
    source: str


_CSS_SEED = (
    ("Alice Blue", "#F0F8FF"), ("Antique White", "#FAEBD7"), ("Aqua", "#00FFFF"),
    ("Aquamarine", "#7FFFD4"), ("Azure", "#F0FFFF"), ("Beige", "#F5F5DC"),
    ("Bisque", "#FFE4C4"), ("Blue", "#0000FF"), ("Blue Violet", "#8A2BE2"),
    ("Brown", "#A52A2A"), ("Burlywood", "#DEB887"), ("Cadet Blue", "#5F9EA0"),
    ("Chartreuse", "#7FFF00"), ("Chocolate", "#D2691E"), ("Coral", "#FF7F50"),
    ("Cornflower Blue", "#6495ED"), ("Cornsilk", "#FFF8DC"), ("Crimson", "#DC143C"),
    ("Cyan", "#00FFFF"), ("Dark Blue", "#00008B"), ("Dark Cyan", "#008B8B"),
    ("Dark Goldenrod", "#B8860B"), ("Dark Gray", "#A9A9A9"), ("Dark Green", "#006400"),
    ("Dark Khaki", "#BDB76B"), ("Dark Magenta", "#8B008B"), ("Dark Olive Green", "#556B2F"),
    ("Dark Orange", "#FF8C00"), ("Dark Orchid", "#9932CC"), ("Dark Red", "#8B0000"),
    ("Dark Salmon", "#E9967A"), ("Dark Sea Green", "#8FBC8F"), ("Dark Slate Blue", "#483D8B"),
    ("Dark Slate Gray", "#2F4F4F"), ("Dark Turquoise", "#00CED1"), ("Dark Violet", "#9400D3"),
    ("Deep Pink", "#FF1493"), ("Deep Sky Blue", "#00BFFF"), ("Dim Gray", "#696969"),
    ("Dodger Blue", "#1E90FF"), ("Firebrick", "#B22222"), ("Floral White", "#FFFAF0"),
    ("Forest Green", "#228B22"), ("Fuchsia", "#FF00FF"), ("Gainsboro", "#DCDCDC"),
    ("Ghost White", "#F8F8FF"), ("Gold", "#FFD700"), ("Goldenrod", "#DAA520"),
    ("Gray", "#808080"), ("Green", "#008000"), ("Green Yellow", "#ADFF2F"),
    ("Honeydew", "#F0FFF0"), ("Hot Pink", "#FF69B4"), ("Indian Red", "#CD5C5C"),
    ("Indigo", "#4B0082"), ("Ivory", "#FFFFF0"), ("Khaki", "#F0E68C"),
    ("Lavender", "#E6E6FA"), ("Lavender Blush", "#FFF0F5"), ("Lawn Green", "#7CFC00"),
    ("Lemon Chiffon", "#FFFACD"), ("Light Blue", "#ADD8E6"), ("Light Coral", "#F08080"),
    ("Light Cyan", "#E0FFFF"), ("Light Goldenrod Yellow", "#FAFAD2"), ("Light Gray", "#D3D3D3"),
    ("Light Green", "#90EE90"), ("Light Pink", "#FFB6C1"), ("Light Salmon", "#FFA07A"),
    ("Light Sea Green", "#20B2AA"), ("Light Sky Blue", "#87CEFA"), ("Light Slate Gray", "#778899"),
    ("Light Steel Blue", "#B0C4DE"), ("Light Yellow", "#FFFFE0"), ("Lime", "#00FF00"),
    ("Lime Green", "#32CD32"), ("Linen", "#FAF0E6"), ("Magenta", "#FF00FF"),
    ("Maroon", "#800000"), ("Medium Aquamarine", "#66CDAA"), ("Medium Blue", "#0000CD"),
    ("Medium Orchid", "#BA55D3"), ("Medium Purple", "#9370DB"), ("Medium Sea Green", "#3CB371"),
    ("Medium Slate Blue", "#7B68EE"), ("Medium Spring Green", "#00FA9A"),
    ("Medium Turquoise", "#48D1CC"), ("Medium Violet Red", "#C71585"), ("Midnight Blue", "#191970"),
    ("Mint Cream", "#F5FFFA"), ("Misty Rose", "#FFE4E1"), ("Moccasin", "#FFE4B5"),
    ("Navajo White", "#FFDEAD"), ("Navy", "#000080"), ("Old Lace", "#FDF5E6"),
    ("Olive", "#808000"), ("Olive Drab", "#6B8E23"), ("Orange", "#FFA500"),
    ("Orange Red", "#FF4500"), ("Orchid", "#DA70D6"), ("Pale Goldenrod", "#EEE8AA"),
    ("Pale Green", "#98FB98"), ("Pale Turquoise", "#AFEEEE"), ("Pale Violet Red", "#DB7093"),
    ("Papaya Whip", "#FFEFD5"), ("Peach Puff", "#FFDAB9"), ("Peru", "#CD853F"),
    ("Pink", "#FFC0CB"), ("Plum", "#DDA0DD"), ("Powder Blue", "#B0E0E6"),
    ("Purple", "#800080"), ("Rebecca Purple", "#663399"), ("Red", "#FF0000"),
    ("Rosy Brown", "#BC8F8F"), ("Royal Blue", "#4169E1"), ("Saddle Brown", "#8B4513"),
    ("Salmon", "#FA8072"), ("Sandy Brown", "#F4A460"), ("Sea Green", "#2E8B57"),
    ("Seashell", "#FFF5EE"), ("Sienna", "#A0522D"), ("Silver", "#C0C0C0"),
    ("Sky Blue", "#87CEEB"), ("Slate Blue", "#6A5ACD"), ("Slate Gray", "#708090"),
    ("Snow", "#FFFAFA"), ("Spring Green", "#00FF7F"), ("Steel Blue", "#4682B4"),
    ("Tan", "#D2B48C"), ("Teal", "#008080"), ("Thistle", "#D8BFD8"),
    ("Tomato", "#FF6347"), ("Turquoise", "#40E0D0"), ("Violet", "#EE82EE"),
    ("Wheat", "#F5DEB3"), ("White", "#FFFFFF"), ("White Smoke", "#F5F5F5"),
    ("Yellow", "#FFFF00"), ("Yellow Green", "#9ACD32"),
)

_EXTENSIONS = (
    ("Aurora Teal", "#008F8C"), ("Berry Punch", "#B23A8A"), ("Bluebell", "#5B6EE1"),
    ("Canyon Clay", "#C65D3B"), ("Cedar Green", "#3F7D5B"), ("Citrine", "#D9A600"),
    ("Cloudberry", "#E06C9F"), ("Cobalt Bloom", "#2855D9"), ("Copper Glow", "#C77832"),
    ("Dragonfruit", "#D92F87"), ("Evergreen Mist", "#2F806A"), ("Fig", "#74405E"),
    ("Glacier", "#4AA8C7"), ("Grape Soda", "#7650B3"), ("Harbor Blue", "#24749A"),
    ("Juniper", "#4C8062"), ("Lagoon", "#0798A5"), ("Lilac Dream", "#A977D4"),
    ("Mango Tango", "#E88619"), ("Meadow", "#57A33E"), ("Moonstone", "#6998A8"),
    ("Mulberry", "#9B356D"), ("Ocean Ink", "#315A9E"), ("Orchid Pop", "#C449C2"),
    ("Paprika", "#C9472F"), ("Peacock", "#007F78"), ("Persimmon", "#E05B2D"),
    ("Pineapple", "#E8C62A"), ("Pistachio", "#78A94A"), ("Plum Jam", "#763B78"),
    ("Poppy", "#E13B45"), ("Rainforest", "#167B57"), ("Raspberry", "#C72C68"),
    ("Riverstone", "#5D7E8A"), ("Rosewood", "#8E3E47"), ("Saffron", "#DDA512"),
    ("Sea Glass", "#44AFA1"), ("Solar Flare", "#EE721C"), ("Spruce", "#286B55"),
    ("Starfruit", "#C9B52D"), ("Storm Blue", "#4C6595"), ("Tangerine", "#E66A24"),
    ("Twilight", "#5E4A9D"), ("Watermelon", "#E04F65"), ("Wildflower", "#9D57B5"),
)


def _registry() -> tuple[AgentColor, ...]:
    seen: set[str] = set()
    result: list[AgentColor] = []
    for source, values in ((CSS_COLOR_4_SOURCE, _CSS_SEED), (CURATED_EXTENSION_SOURCE, _EXTENSIONS)):
        for raw_name, color in values:
            name = "-".join(raw_name.split())
            if color in seen:
                continue
            seen.add(color)
            result.append(AgentColor(name, color, source))
    return tuple(result)


AGENT_COLOR_REGISTRY = _registry()


def _oklab(color: str) -> tuple[float, float, float]:
    if not isinstance(color, str) or not HEX_COLOR.fullmatch(color.upper()):
        raise ValueError("accent must be an exact #RRGGBB color")
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
    red, green, blue = linear
    l = .4122214708 * red + .5363325363 * green + .0514459929 * blue
    m = .2119034982 * red + .6806995451 * green + .1073969566 * blue
    s = .0883024619 * red + .2817188376 * green + .6299787005 * blue
    l_, m_, s_ = cbrt(l), cbrt(m), cbrt(s)
    return (
        .2104542553 * l_ + .7936177850 * m_ - .0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + .4505937099 * s_,
        .0259040371 * l_ + .7827717662 * m_ - .8086757660 * s_,
    )


def assign_agent_color(
    agent_id: str,
    requested_accent: str,
    assignments: Iterable[tuple[str, str]],
) -> AgentColor:
    """Return an existing identity or the nearest currently-free registry color."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id must be non-empty")
    retained: dict[str, str] = {}
    occupied: set[str] = set()
    for assigned_agent, name in assignments:
        if assigned_agent in retained and retained[assigned_agent] != name:
            raise ValueError("an agent cannot have conflicting retained identities")
        retained[assigned_agent] = name
        occupied.add(name.casefold())
    existing = retained.get(agent_id)
    if existing is not None:
        base = existing.rsplit("-", 1)[0] if existing.rsplit("-", 1)[-1].isdigit() else existing
        match = next((item for item in AGENT_COLOR_REGISTRY if item.name.casefold() == base.casefold()), None)
        if match is None:
            raise ValueError("retained agent identity is not in the registry")
        return AgentColor(existing, match.hex, match.source)
    target = _oklab(requested_accent.upper())
    ranked = sorted(
        AGENT_COLOR_REGISTRY,
        key=lambda item: (sum((left - right) ** 2 for left, right in zip(_oklab(item.hex), target)), item.name.casefold()),
    )
    available = next((item for item in ranked if item.name.casefold() not in occupied), None)
    if available is not None:
        return available
    base = ranked[0]
    suffix = 2
    while f"{base.name}-{suffix}".casefold() in occupied:
        suffix += 1
    return AgentColor(f"{base.name}-{suffix}", base.hex, base.source)


if len(AGENT_COLOR_REGISTRY) <= 120:
    raise RuntimeError("agent color registry must contain more than 120 colors")
if len({item.name.casefold() for item in AGENT_COLOR_REGISTRY}) != len(AGENT_COLOR_REGISTRY):
    raise RuntimeError("agent color names must be unique case-insensitively")
if not all(FRIENDLY_NAME.fullmatch(item.name) for item in AGENT_COLOR_REGISTRY):
    raise RuntimeError("agent color names must be whitespace-free friendly identifiers")
if len({item.hex for item in AGENT_COLOR_REGISTRY}) != len(AGENT_COLOR_REGISTRY):
    raise RuntimeError("agent color values must be unique")
