"""Durable record store (JSON files under the project dir).

Real deployments swap this for Postgres + object storage; the interface
is intentionally tiny so that swap is mechanical.
"""
from __future__ import annotations

import json
from pathlib import Path

from .records import Asset, Segment


class RecordStore:
    def __init__(self, project_dir: str | Path) -> None:
        self.dir = Path(project_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.assets_path = self.dir / "assets.json"
        self.segments_path = self.dir / "segments.json"
        self._assets: dict[str, Asset] = {}
        self._segments: dict[str, Segment] = {}
        self._load()

    def _load(self) -> None:
        if self.assets_path.exists():
            for d in json.loads(self.assets_path.read_text()):
                a = Asset.from_dict(d)
                self._assets[a.asset_id] = a
        if self.segments_path.exists():
            for d in json.loads(self.segments_path.read_text()):
                s = Segment.from_dict(d)
                self._segments[s.seg_id] = s

    def save(self) -> None:
        self.assets_path.write_text(
            json.dumps([a.to_dict() for a in self._assets.values()], indent=2)
        )
        self.segments_path.write_text(
            json.dumps([s.to_dict() for s in self._segments.values()], indent=2)
        )

    # --- queries used by the incremental diff ---
    def known_content_hashes(self) -> set[str]:
        return {a.content_hash for a in self._assets.values()}

    def asset_by_hash(self, content_hash: str) -> Asset | None:
        for a in self._assets.values():
            if a.content_hash == content_hash:
                return a
        return None

    # --- mutations ---
    def upsert_asset(self, asset: Asset) -> None:
        self._assets[asset.asset_id] = asset

    def replace_segments(self, asset_id: str, segments: list[Segment]) -> None:
        self._segments = {
            sid: s for sid, s in self._segments.items() if s.asset_id != asset_id
        }
        for s in segments:
            self._segments[s.seg_id] = s

    # --- accessors ---
    @property
    def assets(self) -> list[Asset]:
        return list(self._assets.values())

    @property
    def segments(self) -> list[Segment]:
        return list(self._segments.values())

    def counts(self) -> dict[str, int]:
        st = [a.status for a in self._assets.values()]
        return {
            "assets": len(st),
            "analyzed": sum(1 for s in st if s == "analyzed"),
            "queued": sum(1 for s in st if s in ("queued", "analyzing")),
            "segments": len(self._segments),
        }
