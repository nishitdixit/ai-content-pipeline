"""Agents — reasoning units with a role that select skills and annotate
the blackboard. Add/remove by (un)registering; the orchestrator runs
whatever is registered for each phase.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..blackboard import Blackboard


class Agent(ABC):
    name: str = "agent"
    phase: str = "plan"   # perceive | classify | plan | produce | critique

    @abstractmethod
    def run(self, bb: Blackboard, ctx: dict[str, Any]) -> None:
        ...


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: list[Agent] = []

    def register(self, agent: Agent) -> None:
        self._agents.append(agent)

    def unregister(self, name: str) -> None:
        self._agents = [a for a in self._agents if a.name != name]

    def for_phase(self, phase: str) -> list[Agent]:
        return [a for a in self._agents if a.phase == phase]

    def all(self) -> list[Agent]:
        return list(self._agents)
