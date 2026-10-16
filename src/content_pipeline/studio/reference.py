"""Reference extraction — "make something like this, from my clips".

Runs the same analyze-once pipeline, then derives a style spec (shot
count, pacing, arc, shot grammar, dominant theme) the director can target.
"""
from __future__ import annotations

from typing import Any

from .memory.records import Asset, Segment


def extract_style_spec(asset: Asset, segments: list[Segment]) -> dict[str, Any]:
    segs = [s for s in segments if s.asset_id == asset.asset_id]
    n = max(1, len(segs))
    dur = asset.duration_s or sum(s.duration_s for s in segs)
    avg_shot = round(dur / n, 2) if n else dur
    has_speech = any(s.scores.get("speech_value", 0) > 0.6 for s in segs)
    tags: list[str] = []
    for s in segs:
        tags += s.tags
    theme = max(set(tags), key=tags.count) if tags else "general"
    grammar = [s.shot_type for s in segs] or ["wide"]
    arc = "slow_build_to_peak" if (segs and segs[-1].scores.get("emotion", 0) >=
                                   max((s.scores.get("emotion", 0) for s in segs), default=0)) \
        else "even"
    return {
        "style_spec_id": f"ref_{asset.asset_id}",
        "duration_s": round(dur, 2),
        "shots": n,
        "avg_shot_s": avg_shot,
        "arc": arc,
        "shot_grammar": grammar[:8],
        "theme": theme,
        "speech_ratio": round(sum(1 for s in segs if s.scores.get("speech_value", 0) > 0.6) / n, 2),
        "music_led": not has_speech,
    }
