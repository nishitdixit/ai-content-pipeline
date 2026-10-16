"""Prompts. The profile's prompt, voice guide and worked example are embedded verbatim,
so editing those files tunes the scripts without touching code."""

from __future__ import annotations

import re
from datetime import date

from content_pipeline.config import Paths
from content_pipeline.writer.channel import Channel


def _worked_example(template_md: str) -> str:
    _, _, after = template_md.partition("## Worked example")
    m = re.search(r"```\n(.*?)```", after, re.S)
    return m.group(1).strip() if m else ""


def build_system_prompt(paths: Paths, channel: Channel, verb_form: str | None = None) -> str:
    verb_form = verb_form or channel.verb_form
    return paths.prompt.read_text(encoding="utf-8").format(
        verb_form=verb_form,
        verb_example=channel.verb_examples.get(verb_form, ""),
        words_target=channel.words_target,
        voice_guide=paths.voice_guide.read_text(encoding="utf-8").strip(),
        example=_worked_example(paths.script_template.read_text(encoding="utf-8")),
    ).strip()


def build_script_request(
    channel: Channel, *, day: date, pillar: str, idea: str, source: str | None, series: str | None
) -> str:
    p = channel.pillars[pillar]
    lines = [
        f"Write the script for {day.isoformat()} ({day.strftime('%A')}).",
        f"Pillar: {p.code} {p.name}: {p.description}",
    ]
    if series:
        lines.append(f"Series: {series}: {channel.series_description(series)}")
    lines.append(f"Idea: {idea}")
    if source:
        lines.append(f"Source to verify: {source}")
    if pillar == channel.personal_pillar:
        lines.append(
            "This is a personal-story video, and the story has to be the creator's real one. Build the "
            "script around bracketed prompts for the real details; keep the structure, feelings and "
            "lesson around them."
        )
    return "\n".join(lines)


def build_ideas_request(channel: Channel, *, pillar: str, count: int, existing: list[str]) -> str:
    p = channel.pillars[pillar]
    existing_list = "\n".join(f"- {idea}" for idea in existing)
    source_rule = (
        "Each idea draws on a specific text or teacher; give its source (book chapter.verse, or poet) "
        "so the creator can verify it."
        if pillar == channel.wisdom_pillar
        else "Leave source as an empty string."
    )
    story_rule = (
        "\nThese are prompts for the creator's own stories, so phrase them as questions or situations "
        "the creator fills in from real life; never invent events."
        if pillar == channel.personal_pillar
        else ""
    )
    return (
        f"Suggest {count} new video ideas for pillar {p.code} {p.name}: {p.description}.\n"
        f"Write each as a one-line hook, in the same style and language as the existing ideas. "
        f"{source_rule}{story_rule}\n"
        f"Every idea must be clearly different from these existing ones:\n{existing_list}"
    )
