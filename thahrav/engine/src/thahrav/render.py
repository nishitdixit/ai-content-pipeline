"""Render scripts as markdown files in the house template (content/script-template.md)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

from thahrav.pillars import PILLARS
from thahrav.scriptgen import ScriptResult

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", text.lower())
    slug = ""
    for w in words:
        if len(slug) + len(w) + 1 > max_len:
            break
        slug = f"{slug}-{w}" if slug else w
    return slug or "script"


def script_path(scripts_dir: Path, day: date, title: str) -> Path:
    return scripts_dir / f"{day.isoformat()}_{slugify(title)}.md"


def existing_script(scripts_dir: Path, day: date) -> Path | None:
    return next(iter(sorted(scripts_dir.glob(f"{day.isoformat()}_*.md"))), None)


def read_front_matter(path: Path) -> dict[str, str]:
    m = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not m:
        return {}
    pairs = (line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def render_markdown(result: ScriptResult, notion_page_id: str | None = None) -> str:
    d = result.draft
    pillar = PILLARS[result.pillar]
    meta = {
        "date": result.day.isoformat(),
        "status": "Drafted",
        "pillar": result.pillar,
        "series": result.series or "",
        "theme_id": result.theme_id if result.theme_id is not None else "",
        "provider": result.provider,
        "word_count": d.word_count(),
        "verified": "false",
        "notion_page_id": notion_page_id or "",
    }
    quotes = "\n".join(f"- [ ] \"{q.quote}\" — claimed source: {q.claimed_source}" for q in d.quotes_to_verify) or "none"
    warnings = "\n".join(f"- {w}" for w in result.warnings) or "- none"
    hooks = "\n".join(f"{chr(65 + i)}: {h}" for i, h in enumerate(d.hooks))
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(d.youtube_titles, 1))

    return f"""---
{chr(10).join(f"{k}: {v}" for k, v in meta.items())}
---

# {d.working_title}

**{result.day.strftime('%a %d %b %Y')}** · {pillar.code} {pillar.name}{f" · {result.series}" if result.series else ""}
**Idea:** {result.idea}{f" (source to verify: {result.source})" if result.source else ""}

> **Before recording**
{chr(10).join("> " + line for line in warnings.splitlines())}

## Hook (0-3s): pick one
{hooks}

## Relate (3-15s)
{d.relate}

## Reframe (15-45s)
{d.reframe}

## Takeaway (45-55s)
{d.takeaway}

## Soft close (55-60s)
{d.soft_close}

---

**On-screen hook text:** {d.on_screen_hook_text}
**Cover text:** {d.cover_text}

## YouTube title
{titles}

## Instagram caption
{d.instagram_caption}

## Hashtags
{" ".join(d.hashtags)}

## Quotes to verify
{quotes}

**Sensitive topic:** {"yes (helpline line added to the close)" if d.sensitive_topic else "no"}
"""
