"""Production skills.

These decide *how* a timeline entry is treated; the render skill executes
the decisions. Kept directive-level so the heavy lifting (ffmpeg filtergraph)
lives in one place.
"""
from __future__ import annotations

from typing import Any

from .base import Skill


class ReframeSkill(Skill):
    capability = "reframe"
    name = "mock-track"
    version = "1.0.0"

    def run(self, *, shot_type: str, has_face: bool = False, **_: Any) -> dict[str, Any]:
        # A real impl runs subject tracking; here we pick a crop strategy.
        strategy = "track_subject" if has_face or shot_type in ("closeup", "medium") else "center_safe"
        return {"reframe": strategy, "aspect": "9:16"}


class CaptionSkill(Skill):
    capability = "captions"
    name = "mock-burn"
    version = "1.0.0"

    def run(self, *, transcript: str, **_: Any) -> dict[str, Any]:
        text = (transcript or "").strip()
        return {"captions": bool(text), "caption_text": text[:60]}


class MusicSkill(Skill):
    capability = "music"
    name = "mock-select"
    version = "1.0.0"

    def run(self, *, mood: str = "rising_cinematic", **_: Any) -> dict[str, Any]:
        # A real impl queries a licensed library; here we just name a bed.
        return {"music_bed": mood, "duck_db": -12, "licensed": True}
