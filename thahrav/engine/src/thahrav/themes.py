"""Read and update content/theme-bank.md, which stays the human-editable source of truth.

Rows look like `| 21 | idea | used |` (or `| 1 | idea | source | used |` in the P1
table), under `## P1: ...` .. `## P5: ...` headings. Other tables are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PILLAR_HEADING = re.compile(r"^##\s+(P[1-5])\b")
NUMBERED_ROW = re.compile(r"^\|\s*(\d+)\s*\|")
# Editorial notes like "*(post on Nov 10)*" stay in the file but aren't part of the idea.
NOTE = re.compile(r"\s*\*\([^)]*\)\*")


@dataclass
class Theme:
    id: int
    pillar: str
    idea: str
    source: str | None
    used: str
    line_no: int

    @property
    def is_used(self) -> bool:
        return bool(self.used.strip())


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row(cells: list[str]) -> str:
    return ("| " + " | ".join(cells) + " |").replace("|  |", "| |")


class ThemeBank:
    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.themes = self._parse()

    def _parse(self) -> list[Theme]:
        themes: list[Theme] = []
        pillar = None
        for i, line in enumerate(self.lines):
            if line.startswith("## "):
                m = PILLAR_HEADING.match(line)
                pillar = m.group(1) if m else None
                continue
            if pillar and NUMBERED_ROW.match(line):
                cells = _cells(line)
                if len(cells) not in (3, 4):
                    continue
                source = cells[2] if len(cells) == 4 else None
                themes.append(Theme(int(cells[0]), pillar, NOTE.sub("", cells[1]).strip(), source, cells[-1], i))
        return themes

    def by_id(self, theme_id: int) -> Theme | None:
        return next((t for t in self.themes if t.id == theme_id), None)

    def unused(self, pillar: str | None = None) -> list[Theme]:
        return [t for t in self.themes if not t.is_used and (pillar is None or t.pillar == pillar)]

    def mark_used(self, theme: Theme, used_on: str) -> None:
        cells = _cells(self.lines[theme.line_no])
        cells[-1] = used_on
        self.lines[theme.line_no] = _row(cells)
        theme.used = used_on

    def add(self, pillar: str, idea: str, source: str | None = None) -> Theme:
        """Append a new idea to the end of the pillar's table."""
        rows = [t for t in self.themes if t.pillar == pillar]
        if not rows:
            raise ValueError(f"No table for {pillar} found in {self.path.name}")
        last = max(rows, key=lambda t: t.line_no)
        idea = idea.replace("|", "/").strip()
        cells = [str(max(t.id for t in self.themes) + 1), idea]
        if last.source is not None:
            source = (source or "").replace("|", "/").strip() or "—"
            cells.append(source)
        cells.append("")
        at = last.line_no + 1
        self.lines.insert(at, _row(cells))
        for t in self.themes:
            if t.line_no >= at:
                t.line_no += 1
        theme = Theme(int(cells[0]), pillar, idea, source if last.source is not None else None, "", at)
        self.themes.append(theme)
        return theme

    def save(self) -> None:
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
