"""Structured outputs the LLM must return (decision D8: never parse free text)."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QuoteToVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(description="The exact words used in the script")
    claimed_source: str = Field(description="Book and chapter.verse, or poet/author")


class ScriptDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_title: str = Field(description="Short internal title")
    hooks: list[str] = Field(description="Exactly two alternative opening lines")
    relate: str = Field(description="3-15s: show you understand the feeling")
    reframe: str = Field(description="15-45s: the core idea")
    takeaway: str = Field(description="45-55s: exactly one thing to remember or do")
    soft_close: str = Field(description="55-60s: one calm closing line")
    on_screen_hook_text: str = Field(description="At most 6 words shown during the hook")
    cover_text: str = Field(description="2-4 words for the thumbnail")
    youtube_titles: list[str] = Field(description="Two options, each under 60 characters")
    instagram_caption: str = Field(description="2-4 lines ending with one question")
    hashtags: list[str] = Field(description="3-5 hashtags")
    quotes_to_verify: list[QuoteToVerify] = Field(
        description="Every quote, verse or attributed saying in the script; empty if none")
    sensitive_topic: bool = Field(
        description="True if the script touches anxiety, depression, loneliness, grief or similar distress")

    def spoken_text(self) -> str:
        hook = self.hooks[0] if self.hooks else ""
        return "\n".join([hook, self.relate, self.reframe, self.takeaway, self.soft_close])

    def word_count(self) -> int:
        return len(self.spoken_text().split())


class IdeaSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idea: str = Field(description="One line, in the style of the existing theme bank")
    source: str = Field(description="Source to verify for wisdom ideas, otherwise an empty string")


class IdeaList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ideas: list[IdeaSuggestion]


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON schema with $refs inlined, for structured-output APIs."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
