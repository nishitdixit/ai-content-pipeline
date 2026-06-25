"""Conversational session — the non-coder entry point.

Parses a natural-language brief into a structured request, runs the
orchestrator, and supports re-edits ("punchier opening", "add captions")
by adjusting the request and re-planning. No JSON required from the user.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import load_profile, load_providers
from .memory.store import RecordStore
from .skills import default_registry
from .agents import default_agents
from .orchestrator import Orchestrator
from .events import EventBus, console_printer, JsonlRecorder

_GENRES = {
    "motivational": "motivational", "bike": "bike_vlog", "ride": "bike_vlog",
    "podcast": "podcast", "talk": "podcast",
}


def parse_request(raw: str) -> dict[str, Any]:
    text = raw.lower()
    req: dict[str, Any] = {"raw": raw}
    m = re.search(r"(\d+)\s*shots?", text)
    if m:
        req["shots"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:secs?|seconds?|s\b)", text)
    if m:
        req["duration_s"] = int(m.group(1))
    for kw, prof in _GENRES.items():
        if kw in text:
            req["profile"] = prof
            req["theme"] = kw
            break
    for plat in ("reels", "shorts", "tiktok"):
        if plat in text:
            req["platform"] = plat
    req.setdefault("duration_s", 30)
    req.setdefault("platform", "reels")
    req.setdefault("theme", "")
    return req


class Session:
    def __init__(self, project_dir: str, profile_name: str | None = None,
                 quiet: bool = False) -> None:
        self.store = RecordStore(project_dir)
        self.project_dir = Path(project_dir)
        self.quiet = quiet
        self._profile_name = profile_name
        self.last_request: dict[str, Any] | None = None

    def _build(self, profile_name: str) -> tuple[Orchestrator, EventBus, JsonlRecorder]:
        bus = EventBus()
        bus.subscribe(console_printer(self.quiet))
        rec = JsonlRecorder(str(self.project_dir / "events.jsonl"))
        bus.subscribe(rec)
        profile = load_profile(profile_name)
        skills = default_registry(load_providers())
        agents = default_agents(profile["thresholds"])
        return Orchestrator(skills, agents, bus, profile), bus, rec

    def generate(self, brief: str, execute: bool = True) -> dict[str, Any]:
        req = parse_request(brief)
        profile_name = self._profile_name or req.get("profile", "general")
        req["profile"] = profile_name
        self.last_request = req
        orch, bus, rec = self._build(profile_name)
        out_dir = str(self.project_dir / "renders" / "latest")
        try:
            result = orch.generate(self.store.segments, req, out_dir, execute=execute)
        finally:
            rec.close()
        result["request"] = req
        return result

    def re_edit(self, instruction: str, execute: bool = True) -> dict[str, Any]:
        if not self.last_request:
            raise RuntimeError("nothing to re-edit yet; call generate() first")
        req = dict(self.last_request)
        ins = instruction.lower()
        if "punch" in ins or "faster" in ins or "tighter" in ins:
            req["shots"] = int(req.get("shots", 8)) + 2          # more cuts
            req["variant"] = "punchier"
        if "longer" in ins:
            req["duration_s"] = int(req.get("duration_s", 30)) + 10
        if "shorter" in ins:
            req["duration_s"] = max(10, int(req.get("duration_s", 30)) - 10)
        m = re.search(r"(\d+)\s*shots?", ins)
        if m:
            req["shots"] = int(m.group(1))
        self.last_request = req
        orch, bus, rec = self._build(req["profile"])
        out_dir = str(self.project_dir / "renders" / "reedit")
        try:
            result = orch.generate(self.store.segments, req, out_dir, execute=execute)
        finally:
            rec.close()
        result["request"] = req
        return result
