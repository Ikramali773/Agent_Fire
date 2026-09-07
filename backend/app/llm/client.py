"""Thin LLM wrapper - the ONLY place in this codebase allowed to call an LLM.

Per Part G, Principle 1 of the product scope ("LLM reasons and explains;
deterministic engines decide"), nothing here ever produces a compliance
result. It only: (a) extracts structured fields from a user's free-text
reply so the deterministic Case File can be filled in, (b) classifies
whether a message is answering the current question or asking something
else, and (c) answers general knowledge questions in prose.

This class itself is provider-agnostic - it talks only to the LLMBackend
Protocol (app/llm/backends/base.py), never to a specific SDK. Swapping
providers (Groq <-> Anthropic <-> anything else) means writing one new
backend file; nothing here or in app/dialogue/ changes.

Testability: every instance takes the backend as a constructor argument
(defaulting to a lazily-built real one, chosen by LLMConfig.provider) so
tests can inject a fake and never need network access or an API key.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationError, create_model

from app.llm.backends.base import LLMBackend, LLMBackendNotConfiguredError
from app.llm.config import DEFAULT_CONFIG, LLMConfig
from app.llm.schema import build_json_schema


class LLMNotConfiguredError(RuntimeError):
    """Public, backend-independent version of LLMBackendNotConfiguredError -
    callers (the dialogue manager, the API layer) only need to catch this
    one type regardless of which provider is configured.
    """


def _build_real_backend(provider: str) -> LLMBackend:
    if provider == "groq":
        from app.llm.backends.groq_backend import GroqBackend

        return GroqBackend()
    if provider == "anthropic":
        from app.llm.backends.anthropic_backend import AnthropicBackend

        return AnthropicBackend()
    raise LLMNotConfiguredError(
        f"Unknown LLM provider '{provider}' (FIRE_AGENT_LLM_PROVIDER). "
        "Known providers: groq, anthropic."
    )


def _coerce_field(name: str, raw_value, expected_type: type):
    """Validate/coerce one extracted value against its expected type,
    dropping it (returning None) rather than raising if it doesn't fit -
    open models are less reliable than Claude at strictly following a
    schema, so a single malformed field must not throw away the rest of an
    otherwise-good extraction.
    """
    SingleFieldModel = create_model("SingleField", value=(expected_type, ...))  # noqa: N806
    try:
        return SingleFieldModel(value=raw_value).value
    except ValidationError:
        return None


class LLMClient:
    def __init__(self, backend: LLMBackend | None = None, config: LLMConfig = DEFAULT_CONFIG) -> None:
        self._backend = backend
        self.config = config

    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            try:
                self._backend = _build_real_backend(self.config.provider)
                # Touch .client now so a missing key surfaces here, at the
                # single call site every method already wraps, rather than
                # differently in each of the three methods below.
                self._backend.client  # type: ignore[attr-defined]
            except LLMBackendNotConfiguredError as exc:
                raise LLMNotConfiguredError(str(exc)) from exc
        return self._backend

    def extract_fields(
        self,
        user_text: str,
        field_types: dict[str, type],
        context: str = "",
        model_tier: Literal["routine", "reasoning"] = "routine",
    ) -> dict:
        """Pull structured field values out of a free-text reply.

        field_types maps a Case File field name to a plain Python type
        (str/float/int/bool/list[str]/Literal[...]). Any field the model
        can't confidently find, or that fails validation against its
        expected type, is absent from the returned dict - callers must
        treat a missing key as "not provided", never guess a default.
        """
        schema = build_json_schema(field_types)
        system = (
            "You extract structured facts about a building from a short reply "
            "in a fire-safety compliance intake conversation. Only fill in a "
            "field if the user's message actually states or clearly implies "
            "it - omit anything not mentioned. Never invent a value. "
            f"{context}"
        )
        raw = self.backend.generate_json(system, user_text, schema, self.config.model_for(model_tier))

        result = {}
        for name, typ in field_types.items():
            if name in raw and raw[name] is not None:
                coerced = _coerce_field(name, raw[name], typ)
                if coerced is not None:
                    result[name] = coerced
        return result

    def classify_intent(
        self, user_text: str, pending_question: str
    ) -> Literal["answer", "question", "other"]:
        """Is this message answering the currently pending question, asking
        a different (general knowledge) question, or something else (e.g.
        wanting to correct an earlier answer)?
        """
        schema = {
            "type": "object",
            "properties": {"intent": {"type": "string", "enum": ["answer", "question", "other"]}},
            "additionalProperties": False,
        }
        system = (
            "Classify the user's message relative to the question the agent "
            "just asked them. 'answer' = they are responding to that "
            "question (even partially/vaguely). 'question' = they are "
            "instead asking their own question (general knowledge, "
            "unrelated to answering). 'other' = anything else (e.g. asking "
            "to correct a previous answer, small talk)."
        )
        user_message = f"Agent asked: {pending_question}\nUser said: {user_text}"
        raw = self.backend.generate_json(
            system, user_message, schema, self.config.model_for("routine")
        )
        intent = raw.get("intent")
        return intent if intent in ("answer", "question", "other") else "other"

    def answer_question(
        self,
        question: str,
        knowledge_context: str,
        model_tier: Literal["routine", "reasoning"] = "reasoning",
    ) -> str:
        """General Knowledge Q&A (product scope B.3's Code/Knowledge Agent).

        knowledge_context is whatever grounding text the caller has available
        (today: a summary drawn from the digitized rule data, NOT full RAG
        retrieval - see app/knowledge/context.py). This method never invents a
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
        return self.backend.generate_text(
            system, question, self.config.model_for(model_tier), cache_system=True
        )
