"""Durable memory records.

These are what "analyze once" writes and what every later query reads.
A run never re-opens media — it loads Segment records from the index.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Asset:
    """One per source file."""
    asset_id: str
    content_hash: str
    phash: str
    source_name: str
    original_path: str
    proxy_path: str
    duration_s: float
    status: str = "queued"            # queued | analyzing | analyzed | failed
    analyzed_at: str | None = None
    skill_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Asset:
        return Asset(**d)


@dataclass
class Segment:
    """The queryable unit. Many per asset."""
    seg_id: str
    asset_id: str
    source_name: str
    proxy_path: str
    in_s: float
    out_s: float
    scores: dict[str, float] = field(default_factory=dict)
    shot_type: str = "unknown"
    tags: list[str] = field(default_factory=list)
    transcript: str = ""
    ocr_text: str = ""
    roles: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return round(self.out_s - self.in_s, 3)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Segment:
        return Segment(**d)
