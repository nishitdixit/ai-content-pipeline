"""Orchestrator — the runtime that registers agents/skills and runs the
generation loop. Perception already happened at ingest; a run only:

  retrieve -> classify -> plan -> produce -> critique -> revise -> render

It emits stage/agent events throughout, which is exactly what the live
dashboard renders. Nothing here re-opens or re-analyzes media.
"""
from __future__ import annotations

from typing import Any

from ..events import EventBus
from .agents import AgentRegistry, NarrativeDirectorAgent
from .blackboard import Blackboard
from .edl import Edl
from .memory.index import MemoryIndex
from .memory.records import Segment
from .retrieval import retrieve
from .skills import SkillRegistry


class Orchestrator:
    def __init__(self, skills: SkillRegistry, agents: AgentRegistry, bus: EventBus,
                 style: dict[str, Any]) -> None:
        self.skills = skills
        self.agents = agents
        self.bus = bus
        self.style = style

    def generate(self, segments: list[Segment], request: dict[str, Any], out_dir: str,
                 execute: bool = True) -> dict[str, Any]:
        emit = lambda t, **p: self.bus.emit(t, **p)
        index = MemoryIndex(segments)
        request = {**request, "music": request.get("music") or self.style.get("music", "rising_cinematic")}

        # 1) retrieve from memory (no re-analysis)
        emit("stage.enter", stage="retrieve")
        candidates = retrieve(index, request, self.style["weights"])
        cand_segs = [c.segment for c in candidates]
        emit("agent.done", agent="Retriever",
             result=f"{len(cand_segs)} candidates from {len(segments)} in memory")

        bb = Blackboard(style=self.style["style"], request=request, segments=cand_segs)
        director: NarrativeDirectorAgent = next(
            a for a in self.agents.all() if isinstance(a, NarrativeDirectorAgent))

        # 2) classify roles
        emit("stage.enter", stage="classify")
        director.classify(bb, emit)

        # 3) plan
        emit("stage.enter", stage="plan")
        ctx: dict[str, Any] = {"emit": emit,
                               "platform_rules": self.style["platform_rules"].get(
                                   request.get("platform", "reels"), {})}
        director.run(bb, ctx)
        edl: Edl = ctx["edl"]

        # 4) produce (run production skills to fill treatments)
        emit("stage.enter", stage="produce")
        self._produce(edl, request, emit)

        # 5) critique
        emit("stage.enter", stage="critique")
        for critic in self.agents.for_phase("critique"):
            critic.run(bb, ctx)

        # 6) revise once if flags
        if bb.flags:
            emit("agent.running", agent="Director", doing=f"revising ({len(bb.flags)} flags)")
            self._revise(edl, bb)
            bb.flags.clear()
            for critic in self.agents.for_phase("critique"):
                critic.run(bb, ctx)

        # 7) render
        emit("stage.enter", stage="render")
        render = self.skills.get("render").run(edl=edl, out_dir=out_dir, execute=execute)
        emit("render.done", output=render.get("output_path"), rendered=render.get("rendered"),
             shots=len(edl.timeline), duration_s=edl.total_duration_s)

        return {"edl": edl.to_dict(), "render": render,
                "candidates": [{"seg_id": c.segment.seg_id, "total": c.total,
                                "breakdown": c.breakdown} for c in candidates[:15]],
                "pairings": bb.pairings, "flags": bb.flags}

    def _produce(self, edl: Edl, request: dict[str, Any], emit) -> None:
        reframe = self.skills.get("reframe")
        captions = self.skills.get("captions")
        music = self.skills.get("music")
        for c in edl.timeline:
            r = reframe.run(shot_type="closeup" if c.role == "soundbite" else "wide",
                            has_face=(c.role == "soundbite"))
            c.reframe = r["reframe"]
            if c.role == "soundbite":
                cap = captions.run(transcript=c.caption_text)
                c.captions = cap["captions"]; c.caption_text = cap["caption_text"]
        hook = request.get("hook_text")
        if hook and edl.timeline:          # the script's on-screen hook goes over the opening shot
            first = edl.timeline[0]
            first.captions, first.caption_text = True, hook
            emit("agent.done", agent="CaptionAgent", result=f"hook text on shot 1: '{hook}'")
        m = music.run(mood=edl.music_bed)
        edl.duck_db = m["duck_db"]
        emit("agent.done", agent="Reframer", result=f"reframed {len(edl.timeline)} shots")
        emit("agent.done", agent="CaptionAgent",
             result=f"captioned {sum(1 for c in edl.timeline if c.captions)} soundbites")
        emit("agent.done", agent="AudioMix", result=f"music bed '{edl.music_bed}', duck {m['duck_db']}dB")

    def _revise(self, edl: Edl, bb: Blackboard) -> None:
        """Rescale shot lengths to hit the target. The opening shot keeps its length:
        it was sized to the platform's hook window, and stretching it re-breaks the hook."""
        if not edl.timeline:
            return
        target = edl.target.get("duration_s", 30)
        opening, rest = edl.timeline[0], edl.timeline[1:]
        cur = sum(c.duration_s for c in rest)
        if cur <= 0:
            return
        k = max(0.0, target - opening.duration_s) / cur
        for c in rest:
            new = max(0.6, c.duration_s * k)
            if c.src_in_s is not None and c.src_out_s is not None:
                new = min(new, c.src_out_s - c.src_in_s)        # never past the source segment
            if c.audio_from and c.audio_src_in_s is not None and c.audio_src_out_s is not None:
                new = min(new, c.audio_src_out_s - c.audio_src_in_s)
            c.in_s, c.out_s = _fit(c.in_s, new, c.src_in_s, c.src_out_s)
            if c.audio_from and c.audio_in_s is not None:
                c.audio_in_s, c.audio_out_s = _fit(c.audio_in_s, new, c.audio_src_in_s, c.audio_src_out_s)


def _fit(start: float, length: float, lo: float | None, hi: float | None) -> tuple[float, float]:
    """A `length`-second window starting near `start`, shifted back if needed to stay inside [lo, hi]."""
    if hi is not None and start + length > hi:
        start = hi - length
    if lo is not None:
        start = max(lo, start)
    return round(start, 3), round(start + length, 3)
