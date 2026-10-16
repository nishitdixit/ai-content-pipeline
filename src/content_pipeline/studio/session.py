"""Conversational session — the non-coder entry point.

Parses a natural-language brief into a structured request, runs the
orchestrator, and supports re-edits ("punchier opening", "add captions")
by adjusting the request and re-planning. No JSON required from the user.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..events import EventBus, JsonlRecorder, console_printer
from .agents import default_agents
from .config import load_providers, load_style
from .memory.store import RecordStore
from .orchestrator import Orchestrator
from .skills import default_registry

_GENRES = {
    "motivational": "motivational", "bike": "bike_vlog", "ride": "bike_vlog",
    "podcast": "podcast", "talk": "podcast", "calm": "calm_talking_head",
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
            req["style"] = prof
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
    def __init__(self, project_dir: str, style: str | None = None,
                 quiet: bool = False, bus: EventBus | None = None) -> None:
        self.store = RecordStore(project_dir)
        self.project_dir = Path(project_dir)
        self.quiet = quiet
        self._bus = bus          # an outer bus (e.g. the full pipeline run) records events itself
        self._style = style
        self.last_request: dict[str, Any] | None = None

    def _build(self, style_name: str) -> tuple[Orchestrator, EventBus, JsonlRecorder | None]:
        rec = None
        bus = self._bus
        if bus is None:
            bus = EventBus()
            bus.subscribe(console_printer(self.quiet))
            rec = JsonlRecorder(str(self.project_dir / "events.jsonl"))
            bus.subscribe(rec)
        style = load_style(style_name)
        skills = default_registry(load_providers())
        agents = default_agents(style["thresholds"])
        return Orchestrator(skills, agents, bus, style), bus, rec

    def generate(self, brief: str, execute: bool = True,
                 overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        req = parse_request(brief)
        req.update(overrides or {})
        style_name = self._style or req.get("style", "general")
        req["style"] = style_name
        self.last_request = req
        orch, bus, rec = self._build(style_name)
        out_dir = str(self.project_dir / "renders" / "latest")
        try:
            result = orch.generate(self.store.segments, req, out_dir, execute=execute)
        finally:
            if rec:
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
        orch, bus, rec = self._build(req["style"])
        out_dir = str(self.project_dir / "renders" / "reedit")
        try:
            result = orch.generate(self.store.segments, req, out_dir, execute=execute)
        finally:
            if rec:
                rec.close()
        result["request"] = req
        return result
