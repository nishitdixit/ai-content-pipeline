"""Orchestrator — the runtime that registers agents/skills and runs the
generation loop. Perception already happened at ingest; a run only:

  retrieve -> classify -> plan -> produce -> critique -> revise -> render

It emits stage/agent events throughout, which is exactly what the live
dashboard renders. Nothing here re-opens or re-analyzes media.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .blackboard import Blackboard
from .memory.index import MemoryIndex
from .memory.records import Segment
from .retrieval import retrieve
from .agents import AgentRegistry, NarrativeDirectorAgent
from .skills import SkillRegistry
from .edl import Edl
from .events import EventBus


class Orchestrator:
    def __init__(self, skills: SkillRegistry, agents: AgentRegistry, bus: EventBus,
                 profile: dict[str, Any]) -> None:
        self.skills = skills
        self.agents = agents
        self.bus = bus
        self.profile = profile

    def generate(self, segments: list[Segment], request: dict[str, Any], out_dir: str,
                 execute: bool = True) -> dict[str, Any]:
        emit = lambda t, **p: self.bus.emit(t, **p)
        index = MemoryIndex(segments)

        # 1) retrieve from memory (no re-analysis)
        emit("stage.enter", stage="retrieve")
        candidates = retrieve(index, request, self.profile["weights"])
        cand_segs = [c.segment for c in candidates]
        emit("agent.done", agent="Retriever",
             result=f"{len(cand_segs)} candidates from {len(segments)} in memory")

        bb = Blackboard(profile=self.profile["profile"], request=request, segments=cand_segs)
        director: NarrativeDirectorAgent = next(
            a for a in self.agents.all() if isinstance(a, NarrativeDirectorAgent))

        # 2) classify roles
        emit("stage.enter", stage="classify")
        director.classify(bb, emit)

        # 3) plan
        emit("stage.enter", stage="plan")
        ctx: dict[str, Any] = {"emit": emit,
                               "platform_rules": self.profile["platform_rules"].get(
                                   request.get("platform", "reels"), {})}
        director.run(bb, ctx)
        edl: Edl = ctx["edl"]

        # 4) produce (run production skills to fill treatments)
        emit("stage.enter", stage="produce")
        self._produce(edl, emit)

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
        emit("render.done", output=render.get("output_path"), rendered=render.get("rendered"))

        return {"edl": edl.to_dict(), "render": render,
                "candidates": [{"seg_id": c.segment.seg_id, "total": c.total,
                                "breakdown": c.breakdown} for c in candidates[:15]],
                "pairings": bb.pairings, "flags": bb.flags}

    def _produce(self, edl: Edl, emit) -> None:
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
        m = music.run(mood=edl.music_bed)
        edl.duck_db = m["duck_db"]
        emit("agent.done", agent="Reframer", result=f"reframed {len(edl.timeline)} shots")
        emit("agent.done", agent="CaptionAgent",
             result=f"captioned {sum(1 for c in edl.timeline if c.captions)} soundbites")
        emit("agent.done", agent="AudioMix", result=f"music bed '{edl.music_bed}', duck {m['duck_db']}dB")

    def _revise(self, edl: Edl, bb: Blackboard) -> None:
        """Proportional rescale of shot lengths to better hit the target."""
        target = edl.target.get("duration_s", 30)
        cur = edl.total_duration_s
        if cur <= 0:
            return
        k = target / cur
        for c in edl.timeline:
            new = max(0.6, c.duration_s * k)
            c.out_s = round(c.in_s + new, 3)
            if c.audio_from and c.audio_out_s is not None and c.audio_in_s is not None:
                c.audio_out_s = round(c.audio_in_s + new, 3)
