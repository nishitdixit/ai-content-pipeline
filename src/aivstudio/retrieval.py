"""Retrieval — the seam where memory meets the engine.

Turns "motivational short, 10 shots in 30s, build to a peak" into a
ranked candidate set, entirely from the index. Combines semantic
similarity with quality/emotion scores and role suitability. No clip is
re-opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .memory.index import MemoryIndex
from .memory.records import Segment
from .text import embed_text, cosine


@dataclass
class Candidate:
    segment: Segment
    total: float
    semantic: float
    breakdown: dict[str, float]


def retrieve(
    index: MemoryIndex,
    request: dict[str, Any],
    weights: dict[str, float],
    pool: int = 60,
) -> list[Candidate]:
    qtext = " ".join(filter(None, [request.get("theme", ""), request.get("raw", "")]))
    qv = embed_text(qtext) if qtext else []

    out: list[Candidate] = []
    for s in index.segments:
        sem = cosine(qv, s.embedding) if qv and s.embedding else 0.0
        # usable if it can play *some* role (asymmetric clips still count)
        v = s.scores.get("visual_quality", 0)
        a = max(s.scores.get("audio_quality", 0), s.scores.get("speech_value", 0))
        emo = s.scores.get("emotion", 0)
        usable = max(v, a)
        bd = {
            "semantic": round(weights.get("semantic", 0.4) * sem, 4),
            "emotion": round(weights.get("emotion", 0.25) * emo, 4),
            "usable": round(weights.get("usable", 0.2) * usable, 4),
            "visual": round(weights.get("visual", 0.15) * v, 4),
        }
        total = round(sum(bd.values()), 4)
        out.append(Candidate(segment=s, total=total, semantic=round(sem, 4), breakdown=bd))

    out.sort(key=lambda c: c.total, reverse=True)
    return out[:pool]
