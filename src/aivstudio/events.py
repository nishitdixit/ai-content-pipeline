"""Event bus.

Every agent and skill emits events here. Subscribers include a console
printer and a JSONL recorder; the dashboard replays the recorded stream.
Because state lives on the blackboard and tasks are explicit, the
dashboard is a *view* of real work, not a decorative progress bar.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ts": round(self.ts, 3), **self.payload}


class EventBus:
    def __init__(self) -> None:
        self._subs: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._subs.append(fn)

    def emit(self, type: str, **payload: Any) -> None:
        ev = Event(type=type, payload=payload)
        for fn in self._subs:
            fn(ev)


def console_printer(quiet: bool = False) -> Callable[[Event], None]:
    def _print(ev: Event) -> None:
        if quiet:
            return
        p = ev.payload
        if ev.type == "stage.enter":
            print(f"\n=== stage: {p.get('stage')} ===")
        elif ev.type.startswith("agent."):
            detail = p.get("doing") or p.get("result") or ""
            print(f"  [{p.get('agent','?'):<16}] {ev.type.split('.')[-1]:<8} {detail}")
        else:
            kv = " ".join(f"{k}={v}" for k, v in p.items())
            print(f"  - {ev.type}: {kv}")
    return _print


class JsonlRecorder:
    """Records events to a .jsonl file the dashboard can fetch and replay."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._fh = open(path, "w", encoding="utf-8")

    def __call__(self, ev: Event) -> None:
        self._fh.write(json.dumps(ev.to_dict()) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
