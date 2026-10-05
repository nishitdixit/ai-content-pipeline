"""Generate one script, check it, and apply the deterministic house rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from thahrav.llm import Provider
from thahrav.models import ScriptDraft
from thahrav.prompts import build_script_request

# From docs/03-voice-and-style-guide.md, "Sensitive topics".
HELPLINE_LINE = (
    "Agar ye feeling bahut heavy hai, kisi se baat karo — dost, family, ya professional. "
    "Tele-MANAS helpline 14416 pe free baat kar sakte ho."
)
MIN_WORDS, MAX_WORDS = 110, 190
PLACEHOLDER = re.compile(r"\[[^\]]+\]")


@dataclass
class ScriptResult:
    day: date
    pillar: str
    series: str | None
    idea: str
    source: str | None
    theme_id: int | None
    draft: ScriptDraft
    provider: str
    warnings: list[str] = field(default_factory=list)


def finalize(draft: ScriptDraft) -> ScriptDraft:
    tags = []
    for tag in draft.hashtags:
        tag = "#" + tag.strip().lstrip("#").replace(" ", "")
        if tag != "#" and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    soft_close = draft.soft_close
    if draft.sensitive_topic and "14416" not in soft_close:
        soft_close = f"{soft_close}\n{HELPLINE_LINE}"
    return draft.model_copy(update={"hashtags": tags, "soft_close": soft_close})


def check(draft: ScriptDraft) -> list[str]:
    warnings = []
    words = draft.word_count()
    if not MIN_WORDS <= words <= MAX_WORDS:
        warnings.append(f"Spoken length is {words} words (target 130-160)")
    if len(draft.hooks) != 2:
        warnings.append(f"Expected 2 hooks, got {len(draft.hooks)}")
    for title in draft.youtube_titles:
        if len(title) >= 60:
            warnings.append(f"YouTube title is {len(title)} characters: {title!r}")
    if not 3 <= len(draft.hashtags) <= 5:
        warnings.append(f"{len(draft.hashtags)} hashtags (target 3-5)")
    placeholders = PLACEHOLDER.findall(draft.spoken_text() + "\n" + "\n".join(draft.hooks[1:]))
    if placeholders:
        warnings.append(f"Fill in {len(placeholders)} [placeholder(s)] with your real details before recording")
    if draft.quotes_to_verify:
        warnings.append(f"Verify {len(draft.quotes_to_verify)} quote(s) before recording")
    return warnings


def generate_script(
    provider: Provider,
    system_prompt: str,
    *,
    day: date,
    pillar: str,
    idea: str,
    source: str | None = None,
    series: str | None = None,
    theme_id: int | None = None,
) -> ScriptResult:
    request = build_script_request(day=day, pillar=pillar, idea=idea, source=source, series=series)
    draft = provider.generate(system_prompt, request, ScriptDraft)
    words = draft.word_count()
    if not MIN_WORDS <= words <= MAX_WORDS:
        # One rewrite. If it's still off, the warning tells the creator to trim while reviewing.
        draft = provider.generate(
            system_prompt,
            f"{request}\n\nA previous draft had {words} spoken words; the target is 130-160. "
            "Write it again at that length.",
            ScriptDraft,
        )
    draft = finalize(draft)
    return ScriptResult(day, pillar, series, idea, source, theme_id, draft, provider.name, check(draft))
