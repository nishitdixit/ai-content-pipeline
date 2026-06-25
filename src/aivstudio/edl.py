"""The EDL — the contract between the reasoning layer and the dumb renderer.

The director emits this; the render skill executes it mechanically. Every
clip carries a `reason` (the audit trail that powers click-to-ask), and an
optional `audio_from` so a soundbite's audio can ride over a different
clip's visuals (the core asymmetric-signal move).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class EdlClip:
    source: str               # visuals come from here
    in_s: float
    out_s: float
    role: str                 # hero | b_roll | soundbite
    reason: str
    captions: bool = False
    caption_text: str = ""
    reframe: str = "center_safe"
    audio_from: str | None = None   # if set, take audio from this source instead
    audio_in_s: float | None = None
    audio_out_s: float | None = None
    mute: bool = False

    @property
    def duration_s(self) -> float:
        return round(self.out_s - self.in_s, 3)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_s"] = self.duration_s
        return d


@dataclass
class Edl:
    variant_label: str
    rationale: str
    target: dict[str, Any]
    timeline: list[EdlClip] = field(default_factory=list)
    music_bed: str = "rising_cinematic"
    duck_db: int = -12

    @property
    def total_duration_s(self) -> float:
        return round(sum(c.duration_s for c in self.timeline), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_label": self.variant_label,
            "rationale": self.rationale,
            "target": self.target,
            "total_duration_s": self.total_duration_s,
            "shot_count": len(self.timeline),
            "music_bed": self.music_bed,
            "duck_db": self.duck_db,
            "timeline": [c.to_dict() for c in self.timeline],
        }
