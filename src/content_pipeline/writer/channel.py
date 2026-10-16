"""A channel's pillars, series and weekly rotation, loaded from `channel.json`.

Everything that differs between channels lives in the profile, so the planner and
the script writer never hard-code a channel.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from content_pipeline.config import Paths, env


@dataclass(frozen=True)
class Pillar:
    code: str
    name: str
    description: str

    @property
    def label(self) -> str:
        return f"{self.code} {self.name}"


@dataclass(frozen=True)
class Series:
    name: str
    description: str
    pillar: str | None = None
    source_contains: str | None = None
    manual: bool = False


@dataclass(frozen=True)
class Channel:
    name: str
    pillars: dict[str, Pillar]
    series: list[Series]
    weekly_rotation: list[str]
    words_min: int
    words_max: int
    words_target: str
    duration_s: int = 60
    wisdom_pillar: str | None = None
    personal_pillar: str | None = None
    verb_form: str = "masculine"
    verb_examples: dict[str, str] = field(default_factory=dict)
    footer_marker: str = ""
    footer_line: str = ""
    edit: dict[str, Any] = field(default_factory=dict)

    def pillar_for(self, day: date) -> str:
        return self.weekly_rotation[day.weekday()]

    def series_for(self, pillar: str, source: str | None) -> str | None:
        for s in self.series:
            if s.manual or s.pillar != pillar:
                continue
            if s.source_contains and not (source and s.source_contains in source.lower()):
                continue
            return s.name
        return None

    def series_description(self, name: str) -> str:
        return next((s.description for s in self.series if s.name == name), "")


def load_channel(paths: Paths) -> Channel:
    if not paths.channel_file.exists():
        raise ValueError(f"No channel.json in {paths.root}. Is the profile name right?")
    d = json.loads(paths.channel_file.read_text(encoding="utf-8"))
    pillars = {p["code"]: Pillar(p["code"], p["name"], p["description"]) for p in d["pillars"]}
    rotation = d["weekly_rotation"]
    if len(rotation) != 7 or any(code not in pillars for code in rotation):
        raise ValueError("weekly_rotation needs 7 pillar codes, Monday to Sunday")

    verb_form = env("ACP_VERB_FORM", d.get("verb_form", "masculine")).lower()
    verb_examples = d.get("verb_examples", {})
    if verb_examples and verb_form not in verb_examples:
        raise ValueError(f"verb form must be one of {sorted(verb_examples)}, got '{verb_form}'")

    footer = d.get("sensitive_topic_footer", {})
    words = d.get("words", {})
    return Channel(
        name=d["name"],
        pillars=pillars,
        series=[Series(**s) for s in d.get("series", [])],
        weekly_rotation=rotation,
        words_min=words.get("min", 110),
        words_max=words.get("max", 190),
        words_target=words.get("target", "130-160"),
        duration_s=d.get("duration_s", 60),
        wisdom_pillar=d.get("wisdom_pillar"),
        personal_pillar=d.get("personal_pillar"),
        verb_form=verb_form,
        verb_examples=verb_examples,
        footer_marker=footer.get("marker", ""),
        footer_line=footer.get("line", ""),
        edit=d.get("edit", {}),
    )
