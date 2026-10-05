"""Mirror scripts into the Notion Content database (docs/06-system-architecture.md, data model)."""

from __future__ import annotations

from typing import Any

from thahrav.config import env
from thahrav.pillars import PILLARS, SERIES
from thahrav.scriptgen import ScriptResult

# Pinned so the database/page endpoints below keep their current shape.
NOTION_VERSION = "2022-06-28"
TEXT_LIMIT = 2000  # Notion's per-text-object character limit

STATUSES = ["Idea", "Drafted", "Approved", "Recorded", "Edited", "Scheduled", "Posted", "Reviewed"]


def client():
    from notion_client import Client

    token = env("NOTION_API_KEY")
    if not token:
        raise RuntimeError("NOTION_API_KEY is not set in engine/.env")
    return Client(auth=token, notion_version=NOTION_VERSION)


def is_configured() -> bool:
    return bool(env("NOTION_API_KEY") and env("NOTION_CONTENT_DB_ID"))


def _select(names: list[str]) -> dict[str, Any]:
    return {"select": {"options": [{"name": n} for n in names]}}


def create_content_database(notion, parent_page_id: str) -> str:
    db = notion.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "Thahrav — Content"}}],
        properties={
            "Title": {"title": {}},
            "Date": {"date": {}},
            "Status": _select(STATUSES),
            "Pillar": _select([f"{p.code} {p.name}" for p in PILLARS.values()]),
            "Series": _select([*SERIES, "Comment ka Jawab"]),
            "Hook": {"rich_text": {}},
            "Takeaway": {"rich_text": {}},
            "YT Title": {"rich_text": {}},
            "IG Caption": {"rich_text": {}},
            "Hashtags": {"multi_select": {}},
            "Quotes to verify": {"rich_text": {}},
            "Verified": {"checkbox": {}},
            "Word count": {"number": {}},
            "Theme ID": {"number": {}},
            "Local file": {"rich_text": {}},
            "Raw file": {"rich_text": {}},
            "Final file": {"rich_text": {}},
            "YT URL": {"url": {}},
            "IG URL": {"url": {}},
        },
    )
    return db["id"]


def _rich(text: str) -> list[dict[str, Any]]:
    text = text or ""
    return [{"type": "text", "text": {"content": text[i:i + TEXT_LIMIT]}} for i in range(0, len(text), TEXT_LIMIT)] or []


def _heading(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rich(text)}}


def _paragraphs(text: str) -> list[dict[str, Any]]:
    return [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(chunk.strip())}}
        for chunk in text.split("\n\n")
        if chunk.strip()
    ]


def _todo(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "to_do", "to_do": {"rich_text": _rich(text), "checked": False}}


def page_blocks(result: ScriptResult) -> list[dict[str, Any]]:
    d = result.draft
    blocks: list[dict[str, Any]] = []
    if result.warnings:
        blocks.append(_heading("Before recording"))
        blocks += [_todo(w) for w in result.warnings]
    blocks.append(_heading("Hook (pick one)"))
    blocks += _paragraphs("\n\n".join(f"{chr(65 + i)}: {h}" for i, h in enumerate(d.hooks)))
    for title, body in [
        ("Relate", d.relate),
        ("Reframe", d.reframe),
        ("Takeaway", d.takeaway),
        ("Soft close", d.soft_close),
        ("Instagram caption", d.instagram_caption),
    ]:
        blocks.append(_heading(title))
        blocks += _paragraphs(body)
    if d.quotes_to_verify:
        blocks.append(_heading("Quotes to verify"))
        blocks += [_todo(f"\"{q.quote}\" — {q.claimed_source}") for q in d.quotes_to_verify]
    return blocks


def push_script(notion, database_id: str, result: ScriptResult, local_file: str, replace_page_id: str | None = None) -> str:
    d = result.draft
    pillar = PILLARS[result.pillar]
    properties: dict[str, Any] = {
        "Title": {"title": _rich(d.working_title)},
        "Date": {"date": {"start": result.day.isoformat()}},
        "Status": {"select": {"name": "Drafted"}},
        "Pillar": {"select": {"name": f"{pillar.code} {pillar.name}"}},
        "Hook": {"rich_text": _rich(d.hooks[0] if d.hooks else "")},
        "Takeaway": {"rich_text": _rich(d.takeaway)},
        "YT Title": {"rich_text": _rich(d.youtube_titles[0] if d.youtube_titles else "")},
        "IG Caption": {"rich_text": _rich(d.instagram_caption)},
        "Hashtags": {"multi_select": [{"name": t.replace(",", "")} for t in d.hashtags]},
        "Quotes to verify": {"rich_text": _rich("\n".join(f"{q.quote} — {q.claimed_source}" for q in d.quotes_to_verify))},
        "Verified": {"checkbox": False},
        "Word count": {"number": d.word_count()},
        "Local file": {"rich_text": _rich(local_file)},
    }
    if result.series:
        properties["Series"] = {"select": {"name": result.series}}
    if result.theme_id is not None:
        properties["Theme ID"] = {"number": result.theme_id}

    if replace_page_id:
        notion.pages.update(page_id=replace_page_id, archived=True)
    page = notion.pages.create(
        parent={"database_id": database_id}, properties=properties, children=page_blocks(result)
    )
    return page["id"]


class NotionMirror:
    """What the planner talks to: push one script, optionally replacing an earlier page."""

    def __init__(self, database_id: str | None = None):
        self.client = client()
        self.database_id = database_id or env("NOTION_CONTENT_DB_ID")

    def push(self, result: ScriptResult, local_file: str, replace_page_id: str | None = None) -> str:
        return push_script(self.client, self.database_id, result, local_file, replace_page_id)
