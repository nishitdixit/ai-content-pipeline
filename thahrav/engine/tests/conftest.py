import shutil
from pathlib import Path

import pytest

from thahrav.config import Paths
from thahrav.models import IdeaList, IdeaSuggestion, QuoteToVerify, ScriptDraft

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def paths(tmp_path) -> Paths:
    """A copy of the real docs/ and content/ so tests exercise the real files without changing them."""
    for folder in ("docs", "content"):
        shutil.copytree(PROJECT_ROOT / folder, tmp_path / folder, ignore=shutil.ignore_patterns("scripts", "compare"))
    return Paths(tmp_path)


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
