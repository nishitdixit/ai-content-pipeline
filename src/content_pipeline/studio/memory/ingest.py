"""Ingest — the analyze-once pipeline with incremental diff.

Re-running ingest on a media folder only analyzes files whose content
hash is not already in the registry. Everything known is untouched. This
is what lets you keep dumping media and only pay for the new clips.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ...events import EventBus
from ..skills import SkillRegistry
from ..skills import media as _media
from .fingerprint import content_hash, perceptual_hash
from .records import Asset, Segment
from .store import RecordStore

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

_MOTIV = {"keep", "push", "never", "quit", "discipline", "earn", "rise",
          "grind", "stronger", "win", "summit", "dream", "through", "going"}


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def _transcribe_clip(skills: SkillRegistry, proxy_path: str) -> tuple[list[dict], str]:
    """One transcription call for the whole clip; returns word timestamps."""
    try:
        out = skills.get("transcribe").run(proxy_path=proxy_path)
        return out.get("words", []), out.get("transcript", "")
    except Exception:
        return [], ""


def _slice_words(words: list[dict], a: float, b: float) -> str:
    return " ".join(w["word"] for w in words
                    if w.get("start", 0) >= a - 0.2 and w.get("end", w.get("start", 0)) <= b + 0.2).strip()


def _speech_value_from_text(text: str) -> float:
    toks = text.lower().split()
    if not toks:
        return 0.05
    length = min(1.0, len(toks) / 25)
    punch = min(1.0, sum(1 for w in toks if w.strip(".,!?") in _MOTIV) / 3)
    return round(min(1.0, 0.5 * length + 0.5 * punch), 3)


def ingest_dir(
    media_dir: str | Path,
    store: RecordStore,
    skills: SkillRegistry,
    bus: EventBus,
    proxy_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, int]:
    media_dir = Path(media_dir)
    proxy_dir = Path(proxy_dir or store.dir / "proxies")
    proxy_dir.mkdir(parents=True, exist_ok=True)

    known = set() if force else store.known_content_hashes()
    files = sorted(p for p in media_dir.rglob("*") if p.suffix.lower() in VIDEO_EXTS)
    new, skipped = 0, 0

    bus.emit("stage.enter", stage="ingest")
    bus.emit("ingest.scan", found=len(files), known=len(known))

    for path in files:
        ch = content_hash(path)
        if ch in known:
            skipped += 1
            bus.emit("ingest.skip", file=path.name, reason="already-analyzed")
            continue

        new += 1
        asset_id = "a_" + ch.split(":")[1][:8]
        bus.emit("ingest.analyzing", file=path.name, i=new, asset=asset_id)

        # normalize to a working proxy (fall back to original if no ffmpeg)
        proxy = proxy_dir / f"{asset_id}.mp4"
        if not _media.make_proxy(path, proxy):
            proxy = path
        duration = _media.probe_duration(proxy) or 0.0

        asset = Asset(
            asset_id=asset_id, content_hash=ch, phash=perceptual_hash(path),
            source_name=path.name, original_path=str(path), proxy_path=str(proxy),
            duration_s=round(duration, 3), status="analyzing",
        )
        store.upsert_asset(asset)

        # --- analyze once, per window ---
        scene = skills.get("scene_detect").run(proxy_path=str(proxy), duration_s=duration or 1.0)
        windows = scene["segments"]
        n_win = len(windows)

        # transcribe the whole clip ONCE (real ASR returns word timestamps);
        # fall back to per-window mock speech when no transcribe service is active
        words, _full = _transcribe_clip(skills, str(proxy))

        segments: list[Segment] = []
        for j, (a, b) in enumerate(windows):
            if words:                                  # real transcript, sliced to this window
                transcript = _slice_words(words, a, b)
                speech_value = _speech_value_from_text(transcript)
            else:                                      # mock per-window speech
                spe = skills.get("speech_value").run(
                    content_hash=ch, source_name=path.name, window_idx=j, n_windows=n_win)
                transcript, speech_value = spe["transcript"], spe["speech_value"]

            vis = skills.get("visual_quality").run(
                content_hash=ch, source_name=path.name, window_idx=j)
            aud = skills.get("audio_quality").run(
                content_hash=ch, source_name=path.name, proxy_path=str(proxy), window_idx=j)
            emo = skills.get("emotion").run(
                content_hash=ch, source_name=path.name, transcript=transcript,
                window_idx=j, n_windows=n_win)

            scores = {
                "visual_quality": vis["visual_quality"], "aesthetic": vis["aesthetic"],
                "motion": vis["motion"], "audio_quality": aud["audio_quality"],
                "speech_value": speech_value, "emotion": emo["emotion"],
            }
            tags = emo["tags"]
            emb = skills.get("embed").run(tags=tags, transcript=transcript)
            segments.append(Segment(
                seg_id=f"{asset_id}:s_{j:02d}", asset_id=asset_id,
                source_name=path.name, proxy_path=str(proxy),
                in_s=a, out_s=b, scores=scores, shot_type=vis["shot_type"],
                tags=tags, transcript=transcript, roles=[],
                embedding=emb["embedding"],
            ))

        store.replace_segments(asset_id, segments)
        asset.status = "analyzed"
        asset.analyzed_at = _now()
        asset.skill_versions = {
            "scene_detect": skills.get("scene_detect").version,
            "visual": skills.get("visual_quality").version,
            "audio": skills.get("audio_quality").version,
            "transcribe": skills.get("transcribe").version,
            "embed": skills.get("embed").version,
        }
        store.upsert_asset(asset)
        bus.emit("ingest.analyzed", file=path.name, asset=asset_id, segments=len(segments))

    store.save()
    result = {"found": len(files), "new": new, "skipped": skipped}
    bus.emit("ingest.done", **result)
    return result
