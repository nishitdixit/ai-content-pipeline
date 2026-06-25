from .base import Agent, AgentRegistry
from .director import NarrativeDirectorAgent, classify_roles
from .critics import PlatformCritic, CutQualityCritic


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
