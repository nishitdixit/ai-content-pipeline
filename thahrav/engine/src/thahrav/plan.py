"""Weekly planning: pick a theme per day, write the scripts, mark themes used."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from thahrav.config import Paths
from thahrav.llm import Provider
from thahrav.models import IdeaList
from thahrav.pillars import pillar_for, series_for
from thahrav.prompts import build_ideas_request
from thahrav.render import existing_script, read_front_matter, render_markdown, script_path
from thahrav.scriptgen import ScriptResult, generate_script
from thahrav.themes import Theme, ThemeBank

Log = Callable[[str], None]


@dataclass
class DayOutcome:
    day: date
    status: str  # "written", "skipped", "planned", "failed"
    path: Path | None = None
    theme: Theme | None = None
    result: ScriptResult | None = None
    note: str = ""


def next_monday(today: date) -> date:
    return today + timedelta(days=7 - today.weekday())


def suggest_ideas(provider: Provider, system_prompt: str, bank: ThemeBank, pillar: str, count: int) -> list[Theme]:
    """Ask the LLM for new ideas and append them to the theme bank (not saved until bank.save())."""
    request = build_ideas_request(pillar=pillar, count=count, existing=[t.idea for t in bank.themes])
    suggestions = provider.generate(system_prompt, request, IdeaList)
    return [bank.add(pillar, s.idea, s.source or None) for s in suggestions.ideas[:count]]


def write_script(paths: Paths, result: ScriptResult, *, replace: Path | None = None, notion=None, log: Log = print) -> Path:
    paths.scripts_dir.mkdir(parents=True, exist_ok=True)
    path = script_path(paths.scripts_dir, result.day, result.draft.working_title)
    old_page = read_front_matter(replace).get("notion_page_id") if replace else None
    page_id = None
    if notion is not None:
        try:
            page_id = notion.push(result, str(path.relative_to(paths.root)), old_page or None)
        except Exception as e:  # Notion is a mirror (D12); a failure must not lose the script.
            log(f"  ! Notion sync failed, the local file is still written: {e}")
    if replace and replace != path:
        replace.unlink()
    path.write_text(render_markdown(result, page_id), encoding="utf-8")
    return path


def plan_week(
    paths: Paths,
    provider: Provider | None,
    system_prompt: str,
    start: date,
    *,
    days: int = 7,
    force: bool = False,
    dry_run: bool = False,
    notion=None,
    log: Log = print,
) -> list[DayOutcome]:
    bank = ThemeBank(paths.theme_bank)
    picked: set[int] = set()
    outcomes: list[DayOutcome] = []

    for offset in range(days):
        day = start + timedelta(days=offset)
        pillar = pillar_for(day)
        existing = existing_script(paths.scripts_dir, day)

        if existing and not force:
            outcomes.append(DayOutcome(day, "skipped", existing, note="script already exists"))
            log(f"{day} {pillar}: already has {existing.name}, skipping")
            continue

        theme = None
        if existing:  # --force: rewrite the same theme
            theme_id = read_front_matter(existing).get("theme_id")
            theme = bank.by_id(int(theme_id)) if theme_id and theme_id.isdigit() else None
        if theme is None:
            theme = next((t for t in bank.unused(pillar) if t.id not in picked), None)
        if theme is None:
            if dry_run or provider is None:
                outcomes.append(DayOutcome(day, "planned", note=f"no unused {pillar} ideas; new ones would be suggested"))
                log(f"{day} {pillar}: theme bank is out of {pillar} ideas (new ones get suggested on a real run)")
                continue
            log(f"{day} {pillar}: out of {pillar} ideas, asking for 5 new ones")
            suggest_ideas(provider, system_prompt, bank, pillar, 5)
            bank.save()
            theme = next((t for t in bank.unused(pillar) if t.id not in picked), None)
            if theme is None:
                outcomes.append(DayOutcome(day, "failed", note="no ideas available"))
                continue
        picked.add(theme.id)

        if dry_run or provider is None:
            outcomes.append(DayOutcome(day, "planned", theme=theme))
            log(f"{day} {pillar}: #{theme.id} {theme.idea}")
            continue

        log(f"{day} {pillar}: writing #{theme.id} {theme.idea}")
        try:
            result = generate_script(
                provider, system_prompt, day=day, pillar=pillar, idea=theme.idea, source=theme.source,
                series=series_for(pillar, theme.source), theme_id=theme.id,
            )
        except Exception as e:
            outcomes.append(DayOutcome(day, "failed", theme=theme, note=str(e)))
            log(f"  ! failed: {e}")
            continue
        path = write_script(paths, result, replace=existing, notion=notion, log=log)
        bank.mark_used(theme, day.isoformat())
        bank.save()  # after every day, so a crash mid-week keeps finished work
        outcomes.append(DayOutcome(day, "written", path, theme, result))
        for w in result.warnings:
            log(f"  - {w}")

    return outcomes
