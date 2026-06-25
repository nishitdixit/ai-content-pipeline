"""The blackboard — shared state for one generation run.

Loaded from memory (no re-analysis). Perception already happened at
ingest; during a run the director annotates roles and pairings here, and
the EDL history accumulates. Agents are loosely coupled: they read and
write named fields, so adding an agent is purely additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .memory.records import Segment


@dataclass
class Blackboard:
    profile: str
    request: dict[str, Any]
    segments: list[Segment] = field(default_factory=list)
    roles: dict[str, list[str]] = field(default_factory=dict)        # seg_id -> roles
    pairings: list[dict[str, str]] = field(default_factory=list)     # audio_from/visuals_from
    edl_history: list[dict[str, Any]] = field(default_factory=list)
    flags: list[dict[str, Any]] = field(default_factory=list)

    def by_id(self, seg_id: str) -> Segment | None:
        return next((s for s in self.segments if s.seg_id == seg_id), None)
