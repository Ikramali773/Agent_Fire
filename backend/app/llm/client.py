"""Thin LLM wrapper - the ONLY place in this codebase allowed to call an LLM.

Per Part G, Principle 1 of the product scope ("LLM reasons and explains;
deterministic engines decide"), nothing here ever produces a compliance
result. It only: (a) extracts structured fields from a user's free-text
reply so the deterministic Case File can be filled in, (b) classifies
whether a message is answering the current question or asking something
else, and (c) answers general knowledge questions in prose.

Testability: every method takes the Anthropic client as a constructor
argument (defaulting to a lazy real client) so tests can inject a fake and
never need network access or an API key.
"""

from __future__ import annotations

import os
from typing import Any, Literal, Protocol

from pydantic import BaseModel, create_model

from app.llm.config import DEFAULT_CONFIG, LLMConfig


class LLMNotConfiguredError(RuntimeError):
    """Raised when a real LLM call is attempted without credentials.

    Deliberately distinct from anthropic's own AuthenticationError so callers
    (the dialogue manager, API layer) can catch this specific case and return
    a clear, actionable message instead of a raw SDK stack trace.
    """


class AnthropicClientLike(Protocol):
    """Structural type for the subset of the Anthropic client we use - lets
    tests supply a fake without importing/instantiating the real SDK client.
    """

    messages: Any


def _build_real_client() -> AnthropicClientLike:
    # The anthropic SDK constructor succeeds even with no credentials at all -
    # it only fails lazily, deep in header-building, on the first actual
    # request (a bare TypeError with no distinct exception type to catch).
    # Checking the standard env vars up front lets us fail with one clear,
    # catchable error instead of letting that SDK internal leak out of every
    # call site. A deployer using an `ant auth login` profile instead of an
    # env var will need to also export ANTHROPIC_API_KEY - a reasonable
    # requirement for a server deployment (no interactive CLI session).
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LLMNotConfiguredError(
            "No Anthropic credentials found. Set ANTHROPIC_API_KEY in the "
            "environment before using the conversational features."
        )

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
        raise LLMNotConfiguredError("The 'anthropic' package is not installed.") from exc

    return anthropic.Anthropic()


_PY_TYPE_TO_JSON_SCHEMA_TYPE = {
    str: "string",
    float: "number",
    int: "integer",
    bool: "boolean",
}


class LLMClient:
    def __init__(
        self,
        anthropic_client: AnthropicClientLike | None = None,
        config: LLMConfig = DEFAULT_CONFIG,
    ) -> None:
        self._anthropic_client = anthropic_client
        self.config = config

    @property
    def client(self) -> AnthropicClientLike:
        if self._anthropic_client is None:
            self._anthropic_client = _build_real_client()
        return self._anthropic_client

    def _model_for_tier(self, tier: Literal["routine", "reasoning"]) -> str:
        return self.config.routine_model if tier == "routine" else self.config.reasoning_model

    def extract_fields(
        self,
        user_text: str,
        field_types: dict[str, type],
        context: str = "",
        model_tier: Literal["routine", "reasoning"] = "routine",
    ) -> dict:
        """Pull structured field values out of a free-text reply.

        field_types maps a Case File field name to a plain Python type
        (str/float/int/bool/list[str]). Any field the model can't confidently
        find is left absent from the returned dict - callers must treat a
        missing key as "not provided", never guess a default.
        """
        schema_fields = {name: (typ, None) for name, typ in field_types.items()}
        DynamicModel = create_model("ExtractedFields", **schema_fields)  # noqa: N806

        system = (
            "You extract structured facts about a building from a short reply "
            "in a fire-safety compliance intake conversation. Only fill in a "
            "field if the user's message actually states or clearly implies "
            "it - leave anything not mentioned as null. Never invent a value. "
            f"{context}"
        )

        response = self.client.messages.parse(
            model=self._model_for_tier(model_tier),
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_format=DynamicModel,
        )
        parsed: BaseModel = response.parsed_output
        return {k: v for k, v in parsed.model_dump().items() if v is not None}

    def classify_intent(
        self, user_text: str, pending_question: str
    ) -> Literal["answer", "question", "other"]:
        """Is this message answering the currently pending question, asking
        a different (general knowledge) question, or something else (e.g.
        wanting to correct an earlier answer)?
        """

        class Intent(BaseModel):
            intent: Literal["answer", "question", "other"]

        response = self.client.messages.parse(
            model=self._model_for_tier("routine"),
            max_tokens=256,
            system=(
                "Classify the user's message relative to the question the "
                "agent just asked them. 'answer' = they are responding to "
                "that question (even partially/vaguely). 'question' = they "
                "are instead asking their own question (general knowledge, "
                "unrelated to answering). 'other' = anything else (e.g. "
                "asking to correct a previous answer, small talk)."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Agent asked: {pending_question}\nUser said: {user_text}",
                }
            ],
            output_format=Intent,
        )
        return response.parsed_output.intent

    def answer_question(
        self,
        question: str,
        knowledge_context: str,
        model_tier: Literal["routine", "reasoning"] = "reasoning",
    ) -> str:
        """General Knowledge Q&A (product scope B.3's Code/Knowledge Agent).

        knowledge_context is whatever grounding text the caller has available
        (today: a summary drawn from the digitized rule data, NOT full RAG
        retrieval - see app/knowledge/README.md). This method never invents a
        clause citation beyond what's in knowledge_context; the system prompt
        instructs it to say so explicitly when the context doesn't cover the
        question, per the product scope's guardrail against fabricated
        citations (B.12).
        """
        system = (
            "You are a fire-safety compliance assistant for Indian buildings, "
            "answering under NBCS 2026 Part F. Use ONLY the reference material "
            "below - if it doesn't cover the question, say so plainly and "
            "recommend the user confirm with a licensed fire consultant, "
            "rather than guessing a clause number or threshold. Never state a "
            "numeric threshold or clause citation that isn't in the reference "
            "material. This is advisory only, never a statutory approval.\n\n"
            f"REFERENCE MATERIAL:\n{knowledge_context}"
        )
        response = self.client.messages.create(
            model=self._model_for_tier(model_tier),
            max_tokens=1024,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": question}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")
