"""The provider-agnostic seam (product scope §B.10: "LLM: provider-agnostic
abstraction layer"). Every backend implements exactly two operations - get
JSON back, get prose back - in whatever way that provider actually supports
structured output. Nothing above this layer (app/llm/client.py and
everything that calls it) knows or cares which provider is behind it.

Adding a third provider means writing one new file that implements this
Protocol - no changes anywhere else in the codebase.
"""

from __future__ import annotations

from typing import Protocol


class LLMBackendNotConfiguredError(RuntimeError):
    """Raised by a backend when it can't find its provider's credentials."""


class LLMBackend(Protocol):
    def generate_json(self, system: str, user_message: str, json_schema: dict, model: str) -> dict:
        """Return a dict parsed from the model's JSON response. Raise
        json.JSONDecodeError (or let it propagate) on unparseable output -
        callers treat that as "nothing extracted", never as a crash.
        """
        ...

    def generate_text(
        self, system: str, user_message: str, model: str, cache_system: bool = False
    ) -> str:
        """Return prose. cache_system is a hint, not a guarantee - a backend
        with no prompt-caching concept (e.g. Groq's OpenAI-compatible API)
        is free to ignore it.
        """
        ...
