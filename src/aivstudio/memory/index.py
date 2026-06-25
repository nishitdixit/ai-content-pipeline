"""The memory index — what makes retrieval instant and re-analysis unnecessary.

Three views over the same Segment records:
  - vector  : semantic similarity on embeddings
  - metadata: numeric/categorical filters (scores, duration, roles, tags)
  - fulltext: keyword search over transcript + ocr + tags

A request like "motivational short, 10 shots in 30s" becomes a search +
filter over this index. No clip is ever re-opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .records import Segment
from ..text import cosine, embed_text, tokenize


@dataclass
class Candidate:
    segment: Segment
    score: float
    semantic: float
    breakdown: dict[str, float]


class MemoryIndex:
    def __init__(self, segments: list[Segment]) -> None:
        self.segments = segments

    # --- vector search ---
    def semantic_search(self, query: str, k: int | None = None) -> list[tuple[Segment, float]]:
        qv = embed_text(query)
        scored = [(s, cosine(qv, s.embedding)) for s in self.segments if s.embedding]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k] if k else scored

    # --- fulltext ---
    def keyword_search(self, query: str) -> list[Segment]:
        q = set(tokenize(query))
        hits = []
        for s in self.segments:
            bag = set(tokenize(s.transcript + " " + s.ocr_text + " " + " ".join(s.tags)))
            if q & bag:
                hits.append(s)
        return hits

    # --- metadata filter ---
    def filter(self, predicate: Callable[[Segment], bool]) -> list[Segment]:
        return [s for s in self.segments if predicate(s)]
