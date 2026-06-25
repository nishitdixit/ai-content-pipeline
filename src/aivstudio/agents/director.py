"""The director — role classification + pairing + EDL assembly.

This is the moat. It never collapses modalities into one score: it reads
the independent per-modality scores, assigns each segment a *role*, then
combines roles — pairing a soundbite's audio with a B-roll's visuals into
one segment strong on both axes (the bike-clip case). It places heroes as
a staircase that builds to the final peak.
"""
from __future__ import annotations

from typing import Any

from .base import Agent
from ..blackboard import Blackboard
from ..memory.records import Segment
from ..edl import Edl, EdlClip
from ..text import cosine

DEFAULT_THRESHOLDS = {"high": 0.7, "mid": 0.45}


def classify_roles(seg: Segment, th: dict[str, float]) -> list[str]:
    v = seg.scores.get("visual_quality", 0)
    sp = seg.scores.get("speech_value", 0)
    a = max(seg.scores.get("audio_quality", 0), sp)
    roles: list[str] = []
    if v >= th["high"] and a >= th["high"]:
        roles.append("hero")
    if v >= th["high"] and a < th["mid"]:
        roles.append("b_roll")
    if sp >= th["high"] and v < th["mid"]:
        roles.append("soundbite")
    if v < th["mid"] and a < th["mid"]:
        roles.append("discard")
    if not roles:                      # usable-but-middling -> b_roll filler
        roles.append("b_roll")
    return roles


def _window(seg: Segment, want: float) -> tuple[float, float]:
    """Pick a sub-window of `want` seconds inside the segment."""
    if seg.duration_s <= want:
        return seg.in_s, seg.out_s
    start = seg.in_s + (seg.duration_s - want) / 2.0   # center of the segment
    return round(start, 3), round(start + want, 3)


class NarrativeDirectorAgent(Agent):
    name = "Director"
    phase = "plan"

    def __init__(self, thresholds: dict[str, float] | None = None) -> None:
        self.th = thresholds or DEFAULT_THRESHOLDS

    # phase 1: classify (called explicitly by orchestrator before plan)
    def classify(self, bb: Blackboard, emit) -> None:
        for s in bb.segments:
            roles = classify_roles(s, self.th)
            s.roles = roles
            bb.roles[s.seg_id] = roles
        n = {r: sum(1 for s in bb.segments if r in s.roles)
             for r in ("hero", "b_roll", "soundbite", "discard")}
        emit("agent.done", agent="Casting", result=f"roles: {n}")

    # phase 2: plan
    def run(self, bb: Blackboard, ctx: dict[str, Any]) -> None:
        emit = ctx["emit"]
        req = bb.request
        total = float(req.get("duration_s", 30))
        n_shots = int(req.get("shots", max(6, round(total / 3))))

        segs = bb.segments
        distinct = len(segs)
        if n_shots > distinct:
            emit("warning", agent="Director",
                 msg=f"requested {n_shots} shots but only {distinct} distinct segments in the candidate pool — some clips will repeat")
        heroes = sorted((s for s in segs if "hero" in s.roles),
                        key=lambda s: s.scores.get("visual_quality", 0)
                        + s.scores.get("audio_quality", 0)
                        + s.scores.get("emotion", 0), reverse=True)
        soundbites = sorted((s for s in segs if "soundbite" in s.roles),
                            key=lambda s: s.scores.get("speech_value", 0)
                            + s.scores.get("emotion", 0), reverse=True)
        broll = sorted((s for s in segs if "b_roll" in s.roles),
                       key=lambda s: s.scores.get("visual_quality", 0)
                       + s.scores.get("emotion", 0), reverse=True)

        # --- decide the role pattern across n_shots, heroes as a staircase ---
        hero_slots = self._staircase_positions(n_shots, len(heroes))
        sb_budget = min(len(soundbites), max(1, n_shots // 4))
        sb_slots = self._spread(n_shots, hero_slots, sb_budget)

        used_broll: set[str] = set()
        used_sources: dict[str, int] = {}
        timeline: list[EdlClip] = []
        per_dur = total / n_shots

        def _mark(seg):
            used_broll.add(seg.seg_id)
            used_sources[seg.proxy_path] = used_sources.get(seg.proxy_path, 0) + 1

        hi = si = 0
        prev_source: str | None = None
        for pos in range(n_shots):
            is_finale = pos == n_shots - 1
            want = per_dur * (1.6 if is_finale else 1.0)

            if pos in hero_slots and hi < len(heroes):
                h = heroes[hi]; hi += 1
                _mark(h)
                a, b = _window(h, want)
                timeline.append(EdlClip(
                    source=h.proxy_path, in_s=a, out_s=b, role="hero",
                    reason=("closing summit — strongest hero, full frame, longest hold"
                            if is_finale else "hero beat — re-lifts momentum on the staircase"),
                    captions=False, reframe="center_safe",
                ))
            elif pos in sb_slots and si < len(soundbites):
                sb = soundbites[si]; si += 1
                cover = self._best_cover(sb, broll, used_broll, used_sources)
                if cover:
                    _mark(cover)
                vis = cover or sb
                a, b = _window(vis, want)
                sa, sb_e = _window(sb, want)
                bb.pairings.append({"audio_from": sb.seg_id,
                                    "visuals_from": (cover.seg_id if cover else sb.seg_id)})
                emit("director.pairing", audio_from=sb.seg_id,
                     visuals_from=(cover.seg_id if cover else sb.seg_id))
                timeline.append(EdlClip(
                    source=vis.proxy_path, in_s=a, out_s=b, role="soundbite",
                    reason="soundbite — strong spoken line over covering B-roll",
                    captions=True, caption_text=sb.transcript,
                    reframe="track_subject",
                    audio_from=sb.proxy_path, audio_in_s=sa, audio_out_s=sb_e,
                ))
            else:
                pick = self._pick_broll(broll, used_broll, used_sources, prev_source)
                if pick is None:
                    continue
                _mark(pick)
                a, b = _window(pick, want)
                hook = pos == 0
                timeline.append(EdlClip(
                    source=pick.proxy_path, in_s=a, out_s=b, role="b_roll",
                    reason=("opening hook — strongest visual to stop the scroll"
                            if hook else "B-roll — muted, music bed carries it"),
                    mute=True, reframe="center_safe",
                ))
            prev_source = timeline[-1].source if timeline else prev_source

        edl = Edl(
            variant_label=req.get("variant", "build-to-peak"),
            rationale=("Staircase of heroes building to the summit; soundbites "
                       "ride over covering B-roll; muted B-roll under a music bed."),
            target={"platform": req.get("platform", "reels"), "aspect": "9:16",
                    "duration_s": total, "shots": n_shots},
            music_bed=req.get("music", "rising_cinematic"),
        )
        edl.timeline = timeline
        ctx["edl"] = edl
        bb.edl_history.append(edl.to_dict())
        emit("agent.done", agent="Director",
             result=f"{len(timeline)} shots, {edl.total_duration_s}s")

    # --- helpers ---
    @staticmethod
    def _staircase_positions(n: int, available: int) -> set[int]:
        want = min(available, max(1, n // 3))
        if want == 0:
            return set()
        # spread heroes toward the back, finale always a hero if possible
        positions = set()
        for k in range(want):
            frac = (k + 1) / want
            positions.add(min(n - 1, round(frac * (n - 1))))
        positions.add(n - 1)
        return positions

    @staticmethod
    def _spread(n: int, taken: set[int], count: int) -> set[int]:
        slots: set[int] = set()
        i = 1
        while len(slots) < count and i < n - 1:
            if i not in taken:
                slots.add(i)
            i += 2
        return slots

    @staticmethod
    def _best_cover(sb: Segment, broll: list[Segment], used: set[str],
                    used_sources: dict[str, int]) -> Segment | None:
        # cover with semantically matching B-roll, preferring less-used clips
        best, best_key = None, None
        for b in broll:
            if b.seg_id in used:
                continue
            sim = cosine(sb.embedding, b.embedding) + b.scores.get("visual_quality", 0)
            key = (-used_sources.get(b.proxy_path, 0), sim)   # fewer-used source first, then best match
            if best_key is None or key > best_key:
                best, best_key = b, key
        return best

    @staticmethod
    def _pick_broll(broll: list[Segment], used: set[str], used_sources: dict[str, int],
                    prev_source: str | None) -> Segment | None:
        # candidates: prefer unused segments; spread across source clips;
        # never repeat the previous shot's source back-to-back
        pool = [b for b in broll if b.seg_id not in used] or list(broll)
        if not pool:
            return None
        ranked = sorted(
            range(len(pool)),
            key=lambda i: (used_sources.get(pool[i].proxy_path, 0),     # least-used clip first
                           1 if pool[i].proxy_path == prev_source else 0,  # avoid adjacency
                           i),                                          # then keep score order
        )
        return pool[ranked[0]]
