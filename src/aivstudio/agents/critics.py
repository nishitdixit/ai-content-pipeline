"""Critic agents — gate quality before the user sees a render.

Flags feed the director's revise pass. Kept as data-driven rules so a new
platform or check is a config row, not a rewrite.
"""
from __future__ import annotations

from typing import Any

from .base import Agent
from ..blackboard import Blackboard
from ..edl import Edl


class PlatformCritic(Agent):
    name = "PlatformCritic"
    phase = "critique"

    def run(self, bb: Blackboard, ctx: dict[str, Any]) -> None:
        emit = ctx["emit"]
        edl: Edl = ctx["edl"]
        rules = ctx.get("platform_rules", {})
        target = edl.target.get("duration_s", 30)
        dur = edl.total_duration_s
        if abs(dur - target) > max(2.0, 0.15 * target):
            f = {"agent": self.name, "issue": f"duration {dur}s vs target {target}s"}
            bb.flags.append(f); emit("critic.flag", **f)
        n = len(edl.timeline)
        want = edl.target.get("shots")
        if want and n != want:
            f = {"agent": self.name, "issue": f"{n} shots vs target {want}"}
            bb.flags.append(f); emit("critic.flag", **f)
        if not edl.timeline or edl.timeline[0].duration_s > rules.get("hook_window_s", 2.0) + 1.5:
            f = {"agent": self.name, "issue": "opening hook too slow"}
            bb.flags.append(f); emit("critic.flag", **f)
        if not bb.flags:
            emit("agent.done", agent=self.name, result="platform checks passed")


class CutQualityCritic(Agent):
    name = "CutQualityCritic"
    phase = "critique"

    def run(self, bb: Blackboard, ctx: dict[str, Any]) -> None:
        emit = ctx["emit"]
        edl: Edl = ctx["edl"]
        prev = None
        for i, c in enumerate(edl.timeline):
            if c.duration_s < 0.6:
                f = {"agent": self.name, "issue": f"shot {i+1} too short ({c.duration_s}s)"}
                bb.flags.append(f); emit("critic.flag", **f)
            if prev is not None and c.source == prev and c.role == "b_roll":
                f = {"agent": self.name, "issue": f"shots {i},{i+1} same source — jump-cut risk"}
                bb.flags.append(f); emit("critic.flag", **f)
            prev = c.source
        if not any(fl["agent"] == self.name for fl in bb.flags):
            emit("agent.done", agent=self.name, result="cut quality ok")
