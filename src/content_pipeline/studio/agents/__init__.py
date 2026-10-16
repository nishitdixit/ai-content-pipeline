from .base import Agent, AgentRegistry
from .critics import CutQualityCritic, PlatformCritic
from .director import NarrativeDirectorAgent, classify_roles


def default_agents(thresholds: dict | None = None) -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(NarrativeDirectorAgent(thresholds))
    reg.register(PlatformCritic())
    reg.register(CutQualityCritic())
    return reg


__all__ = [
    "Agent", "AgentRegistry", "NarrativeDirectorAgent", "classify_roles",
    "PlatformCritic", "CutQualityCritic", "default_agents",
]
