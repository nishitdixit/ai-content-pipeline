"""Bridge: a written script becomes an edit request for the studio.

The writer's output (a markdown script with front matter) already says what the
video is about, how long it runs and what the opening hook says. This module reads
those fields so `acp edit --script` needs no hand-written brief:

  idea + title + takeaway -> retrieval query (what B-roll fits the message)
  channel duration         -> target length
  on-screen hook text      -> caption over the opening shot
  channel edit settings    -> edit style, platform, pacing
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_pipeline.writer.channel import Channel
from content_pipeline.writer.render import read_front_matter

SECTION = re.compile(r"^## (.+?)\n(.*?)(?=^## |^---$|\Z)", re.M | re.S)


@dataclass
class ScriptDoc:
    path: Path
    meta: dict[str, str]
    title: str
    idea: str
    hooks: list[str]
    takeaway: str
    on_screen_hook: str


def read_script(path: str | Path) -> ScriptDoc:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    sections = {name.split(" (")[0].split(":")[0].strip().lower(): body.strip()
                for name, body in SECTION.findall(text)}

    def field(label: str) -> str:
        m = re.search(rf"^\*\*{re.escape(label)}:\*\* ?(.*)$", text, re.M)
        return m.group(1).strip() if m else ""

    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
    hooks = [re.sub(r"^[A-Z]: ", "", line).strip() for line in sections.get("hook", "").splitlines() if line.strip()]
    idea = re.sub(r"\s*\(source to verify:.*\)$", "", field("Idea"))
    return ScriptDoc(path, read_front_matter(path), title, idea, hooks,
                     sections.get("takeaway", ""), field("On-screen hook text"))


def edit_request(doc: ScriptDoc, channel: Channel) -> tuple[str, dict[str, Any], str]:
    """Returns (brief, request overrides, style name) for `Session.generate`."""
    edit = channel.edit
    duration = int(edit.get("duration_s", channel.duration_s))
    shots = max(4, round(duration / float(edit.get("avg_shot_s", 4))))
    platform = edit.get("platform", "shorts")
    brief = f"{doc.title}. {doc.idea}. {doc.takeaway}"
    overrides: dict[str, Any] = {
        "raw": brief,
        "theme": doc.idea or doc.title,
        "duration_s": duration,
        "shots": shots,
        "platform": platform,
        "hook_text": doc.on_screen_hook or (doc.hooks[0] if doc.hooks else ""),
        "variant": "from-script",
        "script": str(doc.path),
    }
    return brief, overrides, edit.get("style", "general")
