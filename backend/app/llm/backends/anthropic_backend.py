"""Anthropic backend - kept as the alternative provider behind the same
LLMBackend interface as Groq, proving the abstraction in app/llm/client.py
is genuinely provider-agnostic rather than Groq-shaped.

Unlike Groq, Claude models support schema-validated JSON output directly
(output_config.format), so this backend gets a stronger guarantee: the
returned text is guaranteed valid JSON matching json_schema, not just "valid
JSON" - see the "Raw Schema" pattern in Anthropic's structured outputs docs.
"""

from __future__ import annotations

import json
import os

from app.llm.backends.base import LLMBackend, LLMBackendNotConfiguredError


class AnthropicBackend(LLMBackend):
    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise LLMBackendNotConfiguredError(
                    "No Anthropic credentials found. Set ANTHROPIC_API_KEY in the "
                    "environment before using the conversational features."
                )
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
                raise LLMBackendNotConfiguredError("The 'anthropic' package is not installed.") from exc
            self._client = anthropic.Anthropic()
        return self._client

    def generate_json(self, system: str, user_message: str, json_schema: dict, model: str) -> dict:
        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            output_config={"format": {"type": "json_schema", "schema": json_schema}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    def generate_text(
        self, system: str, user_message: str, model: str, cache_system: bool = False
    ) -> str:
        system_param = [
            {
                "type": "text",
                "text": system,
                **({"cache_control": {"type": "ephemeral"}} if cache_system else {}),
            }
        ]
        response = self.client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_param,
            messages=[{"role": "user", "content": user_message}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")
