"""Groq backend - free-tier, OpenAI-compatible chat completions API.

Groq's open models (Llama, Gemma, etc.) don't have Anthropic-style guaranteed
JSON-schema-validated output, so structured extraction here is done the
portable way: ask for `response_format={"type": "json_object"}` (valid JSON,
not schema-validated) and put the schema description in the prompt itself.
app/llm/client.py is responsible for validating/coercing the result
afterwards - this backend only guarantees "valid JSON", not "matches schema".
"""

from __future__ import annotations

import json
import os

from app.llm.backends.base import LLMBackend, LLMBackendNotConfiguredError


class GroqBackend(LLMBackend):
    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not os.environ.get("GROQ_API_KEY"):
                raise LLMBackendNotConfiguredError(
                    "No GROQ_API_KEY found. Get a free key at https://console.groq.com/keys "
                    "and set it in the environment before using the conversational features."
                )
            try:
                import groq
            except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
                raise LLMBackendNotConfiguredError("The 'groq' package is not installed.") from exc
            self._client = groq.Groq()
        return self._client

    def generate_json(self, system: str, user_message: str, json_schema: dict, model: str) -> dict:
        schema_instruction = (
            "Respond with ONLY a single JSON object - no markdown fences, no "
            "explanation before or after it. It must be valid JSON matching "
            f"this shape (omit any key you're not confident about): {json.dumps(json_schema)}"
        )
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"{system}\n\n{schema_instruction}"},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_tokens=1024,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def generate_text(
        self, system: str, user_message: str, model: str, cache_system: bool = False
    ) -> str:
        # No prompt-caching concept on Groq's API - cache_system is accepted
        # for interface compatibility with other backends and ignored here.
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""
