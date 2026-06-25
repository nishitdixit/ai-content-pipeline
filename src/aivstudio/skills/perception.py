"""Perception skills (mock/heuristic adapters).

These produce per-modality scores from a mix of *real* cheap ffmpeg
signals (duration, loudness, scene cuts) and deterministic, content-hash
seeded values, plus filename hint tokens standing in for what a real
ASR + vision model would detect. Every score here is a number a real
model would output; the interfaces are exactly what you keep when you
swap the model in.

Hint tokens (encode a clip's character in its filename for the demo):
  visual-strong : sunrise wide drone coast landscape ridge vista summit
  audio-strong  : speech talk vlog interview line quote voiceover
  hero (both)   : hero summit triumph finish win peak
  weak          : filler shaky boring dead
  emotion/theme : motivational triumph struggle climb grind dream rise
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

from .base import Skill
from . import media
from ..text import embed_tags

VISUAL_HINTS = {"sunrise", "wide", "drone", "coast", "landscape", "ridge", "vista", "scenery"}
AUDIO_HINTS = {"speech", "talk", "vlog", "interview", "line", "quote", "voiceover", "voice"}
HERO_HINTS = {"hero", "summit", "triumph", "finish", "win", "peak"}
WEAK_HINTS = {"filler", "shaky", "boring", "dead", "blurry"}
THEME_HINTS = {"motivational", "triumph", "struggle", "climb", "grind", "dream", "rise", "push", "ride"}
SHOT_HINTS = {
    "wide": "wide", "drone": "aerial", "closeup": "closeup", "close": "closeup",
    "ridge": "wide", "coast": "wide", "summit": "wide", "talk": "medium",
}


def _seed(content_hash: str) -> random.Random:
    return random.Random(int(hashlib.md5(content_hash.encode()).hexdigest(), 16))


def _tokens(name: str) -> set[str]:
    return set(name.lower().replace("-", "_").replace(".", "_").split("_"))


class SceneDetectSkill(Skill):
    """Boundaries from scene cuts, then long spans sliced into windows.

    Continuous single-take footage has no hard cuts, so cut-detection alone
    collapses a clip to one segment. We therefore subdivide any span longer
    than MAX_WINDOW into ~WINDOW_S windows, so the whole clip is captured at
    moment-level granularity (fun start, motivating middle, sad end each get
    their own segment).
    """
    capability = "scene_detect"
    name = "ffmpeg-heuristic"
    version = "2.0.0"

    WINDOW_S = 4.0       # target window length for long spans
    MAX_WINDOW = 6.0     # spans longer than this get subdivided
    MIN_SEG = 1.2        # don't emit windows shorter than this (except tiny clips)

    def run(self, *, proxy_path: str, duration_s: float,
            window_s: float | None = None, **_: Any) -> dict[str, Any]:
        win = window_s or self.WINDOW_S
        cuts = media.scene_cut_times(proxy_path)
        bounds = sorted(set(round(b, 3) for b in
                            [0.0] + [c for c in cuts if 0 < c < duration_s] + [duration_s]))

        spans = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)
                 if bounds[i + 1] - bounds[i] >= 0.4]
        if not spans:
            spans = [(0.0, max(duration_s, 0.5))]

        segs: list[tuple[float, float]] = []
        for a, b in spans:
            span = b - a
            if span <= self.MAX_WINDOW:
                segs.append((round(a, 3), round(b, 3)))
            else:
                import math
                n = max(1, math.ceil(span / win))
                step = span / n
                for k in range(n):
                    s = a + k * step
                    e = b if k == n - 1 else a + (k + 1) * step
                    if e - s >= self.MIN_SEG:
                        segs.append((round(s, 3), round(e, 3)))
        return {"segments": segs}


class VisualQualitySkill(Skill):
    capability = "visual_quality"
    name = "mock-heuristic"
    version = "1.0.0"

    def run(self, *, content_hash: str, source_name: str, window_idx: int = 0, **_: Any) -> dict[str, Any]:
        rng = _seed(f"{content_hash}v{window_idx}")
        toks = _tokens(source_name)
        base = 0.45 + rng.uniform(-0.12, 0.12)
        if toks & AUDIO_HINTS and not (toks & VISUAL_HINTS) and not (toks & HERO_HINTS):
            base = 0.3 + rng.uniform(-0.06, 0.06)   # talking clip, weak visual
        if toks & VISUAL_HINTS:
            base = 0.85 + rng.uniform(-0.05, 0.1)
        if toks & HERO_HINTS:
            base = max(base, 0.82 + rng.uniform(-0.03, 0.1))
        if toks & WEAK_HINTS:
            base = 0.2 + rng.uniform(-0.05, 0.08)
        shot = next((SHOT_HINTS[t] for t in toks if t in SHOT_HINTS), "medium")
        return {
            "visual_quality": round(min(1.0, max(0.0, base)), 3),
            "aesthetic": round(min(1.0, max(0.0, base + rng.uniform(-0.08, 0.08))), 3),
            "motion": round(rng.uniform(0.2, 0.95), 3),
            "shot_type": shot,
        }


class AudioQualitySkill(Skill):
    capability = "audio_quality"
    name = "mock-heuristic"
    version = "1.0.0"

    def run(self, *, content_hash: str, source_name: str, proxy_path: str,
            window_idx: int = 0, **_: Any) -> dict[str, Any]:
        rng = _seed(f"{content_hash}a{window_idx}")
        toks = _tokens(source_name)
        # real loudness signal nudges the base if available
        mv = media.mean_volume_db(proxy_path)
        loud = 0.5 if mv is None else max(0.0, min(1.0, (mv + 40) / 35))
        base = 0.35 + 0.3 * loud + rng.uniform(-0.08, 0.08)
        noise = "clean"
        if toks & HERO_HINTS:
            base = max(base, 0.78 + rng.uniform(-0.03, 0.08))   # hero: strong on both axes
        if toks & VISUAL_HINTS and not (toks & AUDIO_HINTS):
            base = min(base, 0.3 + rng.uniform(-0.05, 0.08))
            noise = "ambient" if not (toks & {"shaky"}) else "wind"
        return {
            "audio_quality": round(min(1.0, max(0.0, base)), 3),
            "noise_type": noise,
            "loudness_db": None if mv is None else round(mv, 1),
        }


class SpeechValueSkill(Skill):
    capability = "speech_value"
    name = "mock-asr"
    version = "1.0.0"

    _LINES = {
        "speech": "the only way out is through, keep pushing",
        "talk": "every morning you choose to show up",
        "vlog": "i almost quit but i kept going",
        "interview": "discipline beats motivation every single day",
        "line": "one more mile, one more rep",
        "quote": "you become what you repeat",
        "voiceover": "the summit is earned not given",
    }

    def run(self, *, content_hash: str, source_name: str,
            window_idx: int = 0, n_windows: int = 1, **_: Any) -> dict[str, Any]:
        rng = _seed(f"{content_hash}s{window_idx}")
        toks = _tokens(source_name)
        transcript = ""
        val = 0.05 + rng.uniform(0, 0.1)
        # a clip with a speech hint has its line in ONE window (not every window),
        # so different windows of the same clip differ
        speech_window = int(_seed(content_hash + "sw").random() * max(1, n_windows))
        if window_idx == speech_window:
            for t in toks:
                if t in self._LINES:
                    transcript = self._LINES[t]
                    val = 0.85 + rng.uniform(-0.05, 0.1)
                    break
        return {
            "speech_value": round(min(1.0, max(0.0, val)), 3),
            "transcript": transcript,
        }


class EmotionThemeSkill(Skill):
    capability = "emotion"
    name = "mock-heuristic"
    version = "1.0.0"

    def run(self, *, content_hash: str, source_name: str, transcript: str = "",
            window_idx: int = 0, n_windows: int = 1, **_: Any) -> dict[str, Any]:
        import math
        rng = _seed(f"{content_hash}e{window_idx}")
        toks = _tokens(source_name) | set(transcript.lower().split())
        base = 0.4 + rng.uniform(-0.1, 0.1)
        if toks & THEME_HINTS:
            base = 0.78 + rng.uniform(-0.05, 0.12)
        # simulate an emotional arc across the clip so start/mid/end differ:
        # a clip-specific phase shapes where the peak falls
        phase = _seed(content_hash + "ph").uniform(0, math.pi)
        pos = window_idx / max(1, n_windows - 1) if n_windows > 1 else 0.5
        arc = 0.7 + 0.3 * math.sin(math.pi * pos + phase)   # 0.4..1.0 over the clip
        emo = base * arc
        tags = sorted((toks & (THEME_HINTS | VISUAL_HINTS | HERO_HINTS)) | {t for t in toks if len(t) > 3})
        return {"emotion": round(min(1.0, max(0.0, emo)), 3), "tags": tags[:8]}


class EmbedSkill(Skill):
    capability = "embed"
    name = "hashed-bow"
    version = "1.0.0"

    def run(self, *, tags: list[str], transcript: str = "", **_: Any) -> dict[str, Any]:
        return {"embedding": embed_tags(tags, transcript)}


class MockTranscribeSkill(Skill):
    """Placeholder clip-level transcription. Returns no words, so ingest
    falls back to the per-window mock speech skill. Swapped for Deepgram
    (or any ASR) when its key is set.
    """
    capability = "transcribe"
    name = "mock-asr"
    version = "1.0.0"

    def run(self, *, proxy_path: str = "", **_: Any) -> dict[str, Any]:
        return {"words": [], "transcript": ""}
