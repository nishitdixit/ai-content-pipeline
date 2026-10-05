"""Prompts. The voice & style guide doc is embedded verbatim, so editing the doc tunes the scripts."""

from __future__ import annotations

import re
from datetime import date

from thahrav.config import Paths
from thahrav.pillars import PILLARS, SERIES

VERB_EXAMPLES = {
    "masculine": "main bhi aisa sochta tha, main bhaagta raha",
    "feminine": "main bhi aisa sochti thi, main bhaagti rahi",
}

SYSTEM_PROMPT = """\
You write scripts for Thahrav (ठहराव), a daily 60-second face-to-camera video on YouTube Shorts and \
Instagram Reels. The creator is a software engineer in India. They read your script once, then record \
it on their phone in their own words, in natural Hinglish. The audience is mostly 22-32 year olds in \
Indian cities who feel rushed and behind: comparing themselves to peers, anxious about career, money \
and "settle ho jao" timelines. The channel's message is that life should be lived well, not rushed \
through. Slow down with direction; don't stop.

Because the creator speaks from your script rather than reading it, write the way they would talk: \
short sentences, natural pauses, Roman-script Hinglish. In first-person Hindi, use {verb_form} verb \
forms (for example: "{verb_example}").

Each script is about 60 seconds, which is 130-160 spoken words across the first hook, relate, reframe, \
takeaway and soft close:
- hooks: two alternative opening lines, each under about 10 words, that stop the scroll. Never open \
with a greeting.
- relate (3-15s): show you understand the feeling.
- reframe (15-45s): the core idea, whether that's wisdom, a perspective shift or a story.
- takeaway (45-55s): exactly one thing to remember or do today.
- soft_close (55-60s): one calm line. Never ask for likes, follows or subscribes.

Credibility is the channel's whole asset, so these rules matter:
- Never invent facts about the creator's life. When a line needs a real personal detail (a specific \
event, number, person or place), write a bracketed prompt for the creator instead, such as \
"[apna real example: jab tumne pehli baar ...]". General feelings ("main bhi aisa sochta tha") are fine.
- Quote scripture or poets only when you are confident of the text and source, and never present a \
paraphrase as a direct quote. List every quote, verse and attributed saying in quotes_to_verify with \
its claimed source (book with chapter.verse, or poet), even when you're confident; the creator checks \
each one before recording.
- Don't cite statistics or studies.
- Offer perspective, not prescription: no medical, psychological or financial advice, and never tell \
people to quit their job. Set sensitive_topic to true when the script touches anxiety, depression, \
loneliness, grief or similar distress. A helpline line is appended automatically in that case, so \
don't write one yourself.

Metadata:
- on_screen_hook_text: at most 6 words, shown on screen during the hook.
- cover_text: 2-4 words for the thumbnail.
- youtube_titles: two options, each under 60 characters, in Hinglish, phrased as a question or a \
direct statement.
- instagram_caption: 2-4 lines that extend the idea, ending with one question that invites comments.
- hashtags: 3-5, mixing broad and niche tags.

The creator's voice & style guide follows. It is the authority on tone, word choice and what to avoid.

<voice_and_style_guide>
{voice_guide}
</voice_and_style_guide>

Here is a finished script in the house format. It is rendered as text; your output is JSON with the \
same fields.

<example_script>
{example}
</example_script>
"""


def _worked_example(template_md: str) -> str:
    _, _, after = template_md.partition("## Worked example")
    m = re.search(r"```\n(.*?)```", after, re.S)
    return m.group(1).strip() if m else ""


def build_system_prompt(paths: Paths, verb_form: str) -> str:
    return SYSTEM_PROMPT.format(
        verb_form=verb_form,
        verb_example=VERB_EXAMPLES[verb_form],
        voice_guide=paths.voice_guide.read_text(encoding="utf-8").strip(),
        example=_worked_example(paths.script_template.read_text(encoding="utf-8")),
    )


def build_script_request(
    *, day: date, pillar: str, idea: str, source: str | None, series: str | None
) -> str:
    p = PILLARS[pillar]
    lines = [
        f"Write the script for {day.isoformat()} ({day.strftime('%A')}).",
        f"Pillar: {p.code} {p.name}: {p.description}",
    ]
    if series:
        lines.append(f"Series: {series}: {SERIES[series]}")
    lines.append(f"Idea: {idea}")
    if source:
        lines.append(f"Source to verify: {source}")
    if pillar == "P5":
        lines.append(
            "This is a personal-story video, and the story has to be the creator's real one. Build the "
            "script around bracketed prompts for the real details; keep the structure, feelings and "
            "lesson around them."
        )
    return "\n".join(lines)


def build_ideas_request(*, pillar: str, count: int, existing: list[str]) -> str:
    p = PILLARS[pillar]
    existing_list = "\n".join(f"- {idea}" for idea in existing)
    source_rule = (
        "Each idea draws on a specific text or teacher; give its source (book chapter.verse, or poet) "
        "so the creator can verify it."
        if pillar == "P1"
        else "Leave source as an empty string."
    )
    story_rule = (
        "\nThese are prompts for the creator's own stories, so phrase them as questions or situations "
        "the creator fills in from real life; never invent events."
        if pillar == "P5"
        else ""
    )
    return (
        f"Suggest {count} new video ideas for pillar {p.code} {p.name}: {p.description}.\n"
        f"Write each as a one-line hook in Hinglish, in the same style as the existing ideas. "
        f"{source_rule}{story_rule}\n"
        f"Every idea must be clearly different from these existing ones:\n{existing_list}"
    )
