import shutil
from pathlib import Path

import pytest

from content_pipeline.config import Paths
from content_pipeline.writer.channel import load_channel
from content_pipeline.writer.models import IdeaList, IdeaSuggestion, QuoteToVerify, ScriptDraft
from content_pipeline.writer.themes import ThemeBank

PROFILE = Path(__file__).resolve().parents[2] / "profiles" / "thahrav"


@pytest.fixture
def paths(tmp_path) -> Paths:
    """A copy of the real Thahrav profile, with every idea unused, so tests exercise the real
    files without changing them and don't depend on which ideas have been used so far."""
    root = tmp_path / "thahrav"
    shutil.copytree(PROFILE, root, ignore=shutil.ignore_patterns("scripts", "compare"))
    bank = ThemeBank(root / "theme-bank.md")
    for t in bank.themes:
        bank.mark_used(t, "")
    bank.save()
    return Paths(root)


@pytest.fixture
def channel(paths):
    return load_channel(paths)


def make_draft(words: int = 140, **overrides) -> ScriptDraft:
    body = " ".join(["shabd"] * (words - 8))
    fields = dict(
        working_title="25 tak settle",
        hooks=["25 tak settle — kisne kaha?", "Tum late nahi ho."],
        relate="Main bhi aisa sochta tha.",
        reframe=body,
        takeaway="Aaj ek sawaal poocho.",
        soft_close="Aaram se.",
        on_screen_hook_text="25 tak settle?",
        cover_text="Tum late nahi ho",
        youtube_titles=["25 tak settle hona zaroori hai?", "Tum late nahi ho"],
        instagram_caption="Ye timeline kisne di?\nTumhari list mein kya hai? 👇",
        hashtags=["hinglish", "#slowliving", "#Hinglish", "life lessons"],
        quotes_to_verify=[],
        sensitive_topic=False,
    )
    fields.update(overrides)
    return ScriptDraft(**fields)


class FakeProvider:
    name = "fake"
    model = "fake"

    def __init__(self, drafts=None):
        self.drafts = list(drafts or [])
        self.calls = []

    def generate(self, system, user, schema):
        self.calls.append((schema, user))
        if schema is IdeaList:
            return IdeaList(ideas=[IdeaSuggestion(idea=f"New idea {i}", source="") for i in range(5)])
        return self.drafts.pop(0) if self.drafts else make_draft()


@pytest.fixture
def fake_provider():
    return FakeProvider()


__all__ = ["make_draft", "FakeProvider", "QuoteToVerify"]
