"""Content pillars, series, and the weekly rotation (docs/02-content-strategy.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Pillar:
    code: str
    name: str
    description: str


PILLARS: dict[str, Pillar] = {
    p.code: p
    for p in [
        Pillar("P1", "Purani Wisdom",
               "One idea from the Gita, Upanishads, Kabir, Chanakya or folk wisdom, applied to a modern problem"),
        Pillar("P2", "Rush Reframes",
               "Taking apart the myths that make people rush: timelines, comparison, FOMO, 'settle ho jao'"),
        Pillar("P3", "Gentle Productivity",
               "Doing fewer things better, rest without guilt, focus, saying no"),
        Pillar("P4", "Chhoti Practices",
               "One tiny practice to try today: breathing, a phone-free morning, a walk, a gratitude line"),
        Pillar("P5", "Meri Kahani",
               "The creator's own experience as an engineer who used to rush, and what they're learning"),
    ]
}

SERIES: dict[str, str] = {
    "Ruko Zara": "Start with a common rushing behaviour, then pause and reframe it",
    "Gita ki Ek Line": "One verse with chapter.verse cited, a plain meaning, and a modern application",
    "Aaj ka Ek Kaam": "One small action for today",
}

# Monday..Sunday, from the sample week in the content strategy.
WEEKLY_ROTATION = ["P2", "P1", "P3", "P4", "P2", "P1", "P5"]


def pillar_for(day: date) -> str:
    return WEEKLY_ROTATION[day.weekday()]


def series_for(pillar: str, source: str | None) -> str | None:
    if pillar == "P2":
        return "Ruko Zara"
    if pillar == "P1" and source and "gita" in source.lower():
        return "Gita ki Ek Line"
    if pillar == "P4":
        return "Aaj ka Ek Kaam"
    return None
