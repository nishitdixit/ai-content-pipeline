"""LLM providers. Both return validated pydantic objects (structured output)."""

from __future__ import annotations

import json
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from thahrav.config import env
from thahrav.models import json_schema

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def generate(self, system: str, user: str, schema: type[T]) -> T: ...


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str | None = None, effort: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or env("THAHRAV_CLAUDE_MODEL", "claude-opus-5-5")
        self.effort = effort or env("THAHRAV_CLAUDE_EFFORT", "high")

    def generate(self, system: str, user: str, schema: type[T]) -> T:
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
            raise LLMError("Claude rejected the API key. Check ANTHROPIC_API_KEY in engine/.env.") from e
        except self._anthropic.BadRequestError as e:
            raise LLMError(f"Claude rejected the request: {e.message}") from e
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError("Couldn't reach the Claude API. Check the internet connection.") from e

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


class GroqProvider:
    name = "groq"

    def __init__(self, model: str | None = None):
        import groq

        self._groq = groq
        self.client = groq.Groq()
        self.model = model or env("THAHRAV_GROQ_MODEL", "llama-3.3-70b-versatile")

    def generate(self, system: str, user: str, schema: type[T]) -> T:
        schema_text = json.dumps(json_schema(schema), ensure_ascii=False)
        messages = [
            {"role": "system", "content": f"{system}\n\nRespond with one JSON object matching this JSON schema:\n{schema_text}"},
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for _ in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=4096,
                )
            except self._groq.AuthenticationError as e:
                raise LLMError("Groq rejected the API key. Check GROQ_API_KEY in engine/.env (it starts with gsk_).") from e
            except self._groq.APIStatusError as e:
                raise LLMError(f"Groq API error {e.status_code}: {e.message}") from e
            except self._groq.APIConnectionError as e:
                raise LLMError("Couldn't reach the Groq API. Check the internet connection.") from e
            text = response.choices[0].message.content or ""
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:
                last_error = e
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That JSON doesn't match the schema:\n{e}\nReturn the corrected JSON object only."},
                ]
        raise LLMError(f"Groq's output didn't match the schema after 3 tries: {last_error}")


def available_providers() -> list[str]:
    names = []
    if env("ANTHROPIC_API_KEY"):
        names.append("claude")
    if env("GROQ_API_KEY"):
        names.append("groq")
    return names


def get_provider(name: str | None = None) -> Provider:
    name = (name or env("THAHRAV_PROVIDER", "auto")).lower()
    if name == "auto":
        available = available_providers()
        if not available:
            raise LLMError("No LLM key found. Set ANTHROPIC_API_KEY or GROQ_API_KEY in engine/.env.")
        name = available[0]
    if name == "claude":
        return ClaudeProvider()
    if name == "groq":
        return GroqProvider()
    raise LLMError(f"Unknown provider '{name}'. Use claude, groq or auto.")
