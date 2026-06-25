"""Skills — single capabilities behind a typed contract.

A skill does one thing, is stateless, versioned, swappable (mock ->
hosted -> self-hosted), and individually retrainable. Agents *select*
skills; they do not hardcode vendors. Register an impl in the registry
keyed by capability + name; config picks which name is active.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    capability: str = "abstract"
    name: str = "base"
    version: str = "0.0.0"
    remote: bool = False           # True for adapters that call an external API

    @abstractmethod
    def run(self, **inputs: Any) -> dict[str, Any]:
        ...

    def available(self) -> bool:
        """Whether this skill is usable right now (e.g. API key present)."""
        return True

    def info(self) -> str:
        return f"{self.capability}:{self.name}@{self.version}"


class SkillRegistry:
    def __init__(self) -> None:
        self._by_cap: dict[str, dict[str, Skill]] = {}
        self._pref: dict[str, str] = {}      # capability -> preferred impl name

    def register(self, skill: Skill) -> None:
        self._by_cap.setdefault(skill.capability, {})[skill.name] = skill

    def set_preference(self, capability: str, name: str) -> None:
        self._pref[capability] = name

    def get(self, capability: str, name: str | None = None) -> Skill:
        impls = self._by_cap.get(capability, {})
        if not impls:
            raise KeyError(f"no skill registered for capability '{capability}'")
        if name is not None:
            return impls[name]
        pref = self._pref.get(capability)
        if pref and pref in impls:
            return impls[pref]
        return next(iter(impls.values()))

    def active(self) -> list[str]:
        out = []
        for cap, impls in self._by_cap.items():
            chosen = self.get(cap)
            out.append(chosen.info())
        return out

    def list(self) -> list[str]:
        return [s.info() for impls in self._by_cap.values() for s in impls.values()]
