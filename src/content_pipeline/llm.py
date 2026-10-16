"""LLM providers. Every provider returns a validated pydantic object (structured output).

- `claude`: Anthropic, with native JSON-schema output and a cached system prompt.
- `groq`:   Llama on Groq, JSON mode plus schema validation with up to 3 repair turns.
- `mock`:   deterministic, offline drafts so the whole pipeline runs without a key.

Each call reports token usage and latency through an optional `on_usage` callback,
which the CLI forwards to the event bus (and so to the dashboard).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from content_pipeline.config import env
from content_pipeline.writer.models import IdeaList, IdeaSuggestion, ScriptDraft, json_schema

T = TypeVar("T", bound=BaseModel)
UsageCallback = Callable[[dict[str, Any]], None]


class LLMError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, schema: type[T]) -> T: ...


class _Reporting:
    name = "base"
    model = ""

    def __init__(self, on_usage: UsageCallback | None = None):
        self.on_usage = on_usage

    def _report(self, started: float, schema: type[BaseModel], input_tokens: int, output_tokens: int,
                cache_read_tokens: int = 0, attempts: int = 1) -> None:
        if self.on_usage is None:
            return
        self.on_usage({
            "provider": self.name,
            "model": self.model,
            "schema": schema.__name__,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "attempts": attempts,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        })


class ClaudeProvider(_Reporting):
    name = "claude"

    def __init__(self, model: str | None = None, effort: str | None = None, on_usage: UsageCallback | None = None):
        super().__init__(on_usage)
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or env("ACP_CLAUDE_MODEL", "claude-opus-5-5")
        self.effort = effort or env("ACP_CLAUDE_EFFORT", "high")

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        started = time.perf_counter()
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                # The system prompt is identical for every script in a run, so cache it.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": json_schema(schema)},
                },
                # On a safety-classifier decline, the API retries on Anthropic's recommended fallback model.
                fallbacks="default",
            )
        except self._anthropic.AuthenticationError as e:
            raise LLMError("Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.") from e
        except self._anthropic.BadRequestError as e:
            raise LLMError(f"Claude rejected the request: {e.message}") from e
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError("Couldn't reach the Claude API. Check the internet connection.") from e

        usage = getattr(response, "usage", None)
        self._report(
            started, schema,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )
        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise LLMError(f"Claude declined this request (category: {category}). Try --provider groq.")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude's response was cut off at max_tokens.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMError("Claude returned no text.")
        try:
            return schema.model_validate_json(text)
        except ValidationError as e:
            raise LLMError(f"Claude's output didn't match the schema: {e}") from e


class GroqProvider(_Reporting):
    name = "groq"

    def __init__(self, model: str | None = None, on_usage: UsageCallback | None = None):
        super().__init__(on_usage)
        import groq

        self._groq = groq
        self.client = groq.Groq()
        self.model = model or env("ACP_GROQ_MODEL", "llama-3.3-70b-versatile")

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        started = time.perf_counter()
        schema_text = json.dumps(json_schema(schema), ensure_ascii=False)
        messages = [
            {"role": "system", "content": f"{system}\n\nRespond with one JSON object matching this JSON schema:\n{schema_text}"},
            {"role": "user", "content": user},
        ]
        tokens_in = tokens_out = 0
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=4096,
                )
            except self._groq.AuthenticationError as e:
                raise LLMError("Groq rejected the API key. Check GROQ_API_KEY in .env (it starts with gsk_).") from e
            except self._groq.APIStatusError as e:
                raise LLMError(f"Groq API error {e.status_code}: {e.message}") from e
            except self._groq.APIConnectionError as e:
                raise LLMError("Couldn't reach the Groq API. Check the internet connection.") from e
            usage = getattr(response, "usage", None)
            tokens_in += getattr(usage, "prompt_tokens", 0) or 0
            tokens_out += getattr(usage, "completion_tokens", 0) or 0
            text = response.choices[0].message.content or ""
            try:
                result = schema.model_validate_json(text)
            except ValidationError as e:
                last_error = e
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That JSON doesn't match the schema:\n{e}\nReturn the corrected JSON object only."},
                ]
                continue
            self._report(started, schema, tokens_in, tokens_out, attempts=attempt)
            return result
        self._report(started, schema, tokens_in, tokens_out, attempts=3)
        raise LLMError(f"Groq's output didn't match the schema after 3 tries: {last_error}")


class MockProvider(_Reporting):
    """Offline, deterministic drafts for demos, CI and dry runs of the whole pipeline.

    The text is clearly a placeholder; it exists so planning, rendering, the bridge to
    the studio and the dashboard can all run without an API key.
    """

    name = "mock"
    model = "mock-writer"

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        started = time.perf_counter()
        if schema is IdeaList:
            result: BaseModel = IdeaList(ideas=[IdeaSuggestion(idea=f"Mock idea {i + 1}", source="") for i in range(5)])
        elif schema is ScriptDraft:
            result = _mock_draft(_field(user, "Idea") or "Slow down")
        else:
            raise LLMError(f"The mock provider has no fixture for {schema.__name__}.")
        words = len(user.split()) + len(system.split())
        self._report(started, schema, input_tokens=words, output_tokens=len(result.model_dump_json().split()))
        return result  # type: ignore[return-value]


def _field(text: str, name: str) -> str:
    m = re.search(rf"^{name}: (.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _mock_draft(idea: str) -> ScriptDraft:
    topic = idea.split(":")[0].strip()
    filler = ("Socho zara. Hum sab ek race mein hain jiska finish line kisi ne dekhi hi nahi. "
              "Har din lagta hai ki koi aage nikal gaya, aur hum peeche reh gaye. ")
    return ScriptDraft(
        working_title=f"[mock] {topic}"[:60],
        hooks=[f"{topic}? Ruko zara.", "Tum late nahi ho."],
        relate=f"Main bhi aisa sochta tha. {topic} ke baare mein soch soch ke raat nikal jaati thi. " + filler,
        reframe=(filler * 2) + "Par zindagi koi train nahi jo ek fixed station pe rukti ho. "
                "Apni speed se chalna bhi progress hai. Thahrav matlab rukna nahi, direction ke saath chalna hai.",
        takeaway="Aaj sirf ek kaam karo: apne aap se poocho, ye deadline kisne di?",
        soft_close="Aaram se. Zindagi race nahi hai.",
        on_screen_hook_text=topic[:40],
        cover_text="Ruko zara",
        youtube_titles=[f"{topic}?"[:58], "Tum late nahi ho"],
        instagram_caption="Ye timeline kisne di?\nTumhari list mein kya hai?",
        hashtags=["#thahrav", "#slowliving", "#hinglish"],
        quotes_to_verify=[],
        sensitive_topic=False,
    )


PROVIDERS = ("claude", "groq", "mock")


def available_providers() -> list[str]:
    names = []
    if env("ANTHROPIC_API_KEY"):
        names.append("claude")
    if env("GROQ_API_KEY"):
        names.append("groq")
    return names


def get_provider(name: str | None = None, on_usage: UsageCallback | None = None) -> Provider:
    name = (name or env("ACP_PROVIDER", "auto")).lower()
    if name == "auto":
        available = available_providers()
        if not available:
            raise LLMError("No LLM key found. Set ANTHROPIC_API_KEY or GROQ_API_KEY in .env, "
                           "or pass --provider mock to run offline.")
        name = available[0]
    if name == "claude":
        return ClaudeProvider(on_usage=on_usage)
    if name == "groq":
        return GroqProvider(on_usage=on_usage)
    if name == "mock":
        return MockProvider(on_usage=on_usage)
    raise LLMError(f"Unknown provider '{name}'. Use claude, groq, mock or auto.")
