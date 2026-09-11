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


class LLMUnavailableError(LLMNotConfiguredError):
    """The backend IS configured, but the provider's own API call failed -
    a rate limit, a 5xx, a timeout. Subclasses LLMNotConfiguredError
    deliberately: every existing `except LLMNotConfiguredError` call site
    (dialogue manager, ingest pipeline) already fails open for this without
    needing its own except clause, since Python catches subclasses too -
    only the message differs, so a user sees "temporarily rate-limited, try
    again shortly" instead of "no API key configured" for what is a very
    different, transient situation. Real-world trigger this guards against:
    Groq's free/on-demand tier enforces a tiny per-minute OUTPUT token quota
    per model (seen live: 1000 tokens/minute) - a handful of document
    uploads in quick succession can exhaust it, and the groq/anthropic SDKs
    raise their own exception types for that, which nothing here was
    catching before this - it reached the API layer as an uncaught 500.
    """


def _is_transient_provider_error(exc: Exception) -> bool:
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is in requirements.txt
        anthropic = None  # type: ignore[assignment]
    try:
        import groq
    except ImportError:  # pragma: no cover - dependency is in requirements.txt
        groq = None  # type: ignore[assignment]

    provider_bases = tuple(
        error_type
        for error_type in (
            getattr(anthropic, "AnthropicError", None),
            getattr(groq, "GroqError", None),
        )
        if error_type is not None
    )
    return bool(provider_bases) and isinstance(exc, provider_bases)


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


def _coerce_extracted_fields(raw: dict, field_types: dict[str, type]) -> dict:
    result = {}
    for name, typ in field_types.items():
        if name in raw and raw[name] is not None:
            coerced = _coerce_field(name, raw[name], typ)
            if coerced is not None:
                result[name] = coerced
    return result


class LLMClient:
    def __init__(self, backend: LLMBackend | None = None, config: LLMConfig = DEFAULT_CONFIG) -> None:
        self._backend = backend
        self.config = config

    @property
    def backend(self) -> LLMBackend:
        # Constructing a backend object never fails - it's a plain object
        # with a lazily-checked `.client` property (see GroqBackend/
        # AnthropicBackend). So this is safe to cache unconditionally: it's
        # NOT "did credentials check out", only "which backend to use".
        # Credentials are (re-)checked on every call via _call(), below -
        # caching the *result* of that check here was the original bug:
        # the first failure got wrapped into LLMNotConfiguredError, but the
        # object stayed cached, so every later call skipped this property
        # entirely and let the raw, un-wrapped LLMBackendNotConfiguredError
        # escape uncaught (seen live as a 500 on the second /message turn).
        if self._backend is None:
            self._backend = _build_real_backend(self.config.provider)
        return self._backend

    def _call(self, method_name: str, model_tier: Literal["routine", "reasoning", "vision"], *args, **kwargs):
        """Invoke a backend method, translating every "this deployment isn't
        set up right" failure into the one public, provider-independent
        error - at every call, not just the first, so a still-unconfigured
        backend (missing credentials, or FIRE_AGENT_LLM_PROVIDER typo'd to a
        provider with no registered default models) fails the same clear
        way on turn 1 and turn 100, rather than reaching the API layer as an
        uncaught exception. Also translates a transient provider-side
        failure (rate limit, 5xx, timeout) into LLMUnavailableError, same
        reasoning - a live user hit an uncaught groq.RateLimitError from
        this exact path (Groq's free tier enforces a small per-minute
        output-token quota, easily exhausted by a few uploads in a row).
        """
        try:
            model = self.config.model_for(model_tier)
            return getattr(self.backend, method_name)(*args, model, **kwargs)
        except (LLMBackendNotConfiguredError, ValueError) as exc:
            raise LLMNotConfiguredError(str(exc)) from exc
        except Exception as exc:
            if _is_transient_provider_error(exc):
                raise LLMUnavailableError(
                    f"The AI provider is temporarily unavailable or rate-limited: {exc}"
                ) from exc
            raise

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
        raw = self._call("generate_json", model_tier, system, user_text, schema)
        return _coerce_extracted_fields(raw, field_types)

    def extract_fields_from_image(
        self,
        image_bytes: bytes,
        media_type: str,
        field_types: dict[str, type],
        context: str = "",
    ) -> dict:
        """Tier 4 of the OCR pipeline (§B.7.1): read fields directly off a
        page image via a vision-capable model, for when Tiers 1-3 (text
        layer, standard OCR, preprocessed OCR retry - app/ingest/tiers.py)
        all produced low-confidence or empty results. Same
        validate-and-drop-per-field behavior as extract_fields - never
        trusts the model followed the schema exactly.
        """
        import base64

        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        schema = build_json_schema(field_types)
        system = (
            "You extract structured facts about a building from a page image "
            "(a scanned architectural plan, NOC letter, or certificate) in a "
            "fire-safety compliance intake. Only fill in a field if the image "
            "actually shows or clearly implies it - omit anything not legible "
            "or not present. Never invent a value, and if handwriting or a "
            "stamp makes a field ambiguous, omit it rather than guess. "
            f"{context}"
        )
        raw = self._call(
            "generate_json_from_image",
            "vision",
            system,
            "Extract the requested fields from this document image.",
            image_b64,
            media_type,
            schema,
        )
        return _coerce_extracted_fields(raw, field_types)

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
        raw = self._call("generate_json", "routine", system, user_message, schema)
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
        return self._call("generate_text", model_tier, system, question, cache_system=True)
