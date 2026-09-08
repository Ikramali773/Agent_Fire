"""Tests LLMClient against a fake LLMBackend - verifies schema building, field
coercion, and call wiring without any network access, API key, or real
provider SDK, per app/llm/client.py's testability design. Because LLMClient
only ever talks to the LLMBackend Protocol, these tests double as proof the
abstraction is genuinely provider-agnostic (a Groq-shaped fake and an
Anthropic-shaped fake would look identical from LLMClient's side).
"""

import pytest

from app.llm.backends.base import LLMBackendNotConfiguredError
from app.llm.client import LLMClient, LLMNotConfiguredError
from app.llm.config import LLMConfig


class FakeBackend:
    def __init__(self, json_return=None, text_return=""):
        self.json_return = json_return or {}
        self.text_return = text_return
        self.json_calls: list[dict] = []
        self.text_calls: list[dict] = []

    def generate_json(self, system, user_message, json_schema, model):
        self.json_calls.append(
            {"system": system, "user_message": user_message, "json_schema": json_schema, "model": model}
        )
        return self.json_return

    def generate_text(self, system, user_message, model, cache_system=False):
        self.text_calls.append(
            {"system": system, "user_message": user_message, "model": model, "cache_system": cache_system}
        )
        return self.text_return


def test_extract_fields_builds_json_schema_and_returns_only_valid_non_null():
    backend = FakeBackend(json_return={"height_m": 12.5, "floors_above_ground": None})
    llm = LLMClient(backend=backend)

    result = llm.extract_fields(
        "about 12.5 meters tall", {"height_m": float, "floors_above_ground": int}
    )

    assert result == {"height_m": 12.5}
    call = backend.json_calls[0]
    assert call["json_schema"]["properties"]["height_m"] == {"type": "number"}
    assert call["model"] == "llama-3.1-8b-instant"  # groq is the default provider


def test_extract_fields_drops_a_field_that_fails_type_coercion():
    # Open models sometimes return a string where a number was expected -
    # that single bad field must not discard an otherwise-good extraction.
    backend = FakeBackend(json_return={"height_m": "quite tall", "built_up_area_sqm": 600})
    llm = LLMClient(backend=backend)

    result = llm.extract_fields("quite tall, 600 sqm", {"height_m": float, "built_up_area_sqm": float})

    assert result == {"built_up_area_sqm": 600.0}


def test_extract_fields_handles_literal_enum_field():
    from typing import Literal

    backend = FakeBackend(json_return={"occupancy_type": "Storage"})
    llm = LLMClient(backend=backend)

    result = llm.extract_fields(
        "it's a warehouse", {"occupancy_type": Literal["Residential", "Storage", "Hazardous"]}
    )
    assert result == {"occupancy_type": "Storage"}

    # A value outside the enum must be dropped, not passed through.
    backend2 = FakeBackend(json_return={"occupancy_type": "NotARealOccupancy"})
    llm2 = LLMClient(backend=backend2)
    result2 = llm2.extract_fields(
        "hmm", {"occupancy_type": Literal["Residential", "Storage", "Hazardous"]}
    )
    assert result2 == {}


def test_classify_intent_returns_parsed_value():
    backend = FakeBackend(json_return={"intent": "question"})
    llm = LLMClient(backend=backend)

    intent = llm.classify_intent("what's a refuge area?", "What's the building height?")
    assert intent == "question"


def test_classify_intent_falls_back_to_other_on_bad_output():
    backend = FakeBackend(json_return={"intent": "something-unexpected"})
    llm = LLMClient(backend=backend)
    assert llm.classify_intent("hmm", "pending question") == "other"


def test_answer_question_passes_context_and_requests_caching():
    backend = FakeBackend(text_return="A refuge area is...")
    llm = LLMClient(backend=backend)

    answer = llm.answer_question("what's a refuge area?", "some knowledge context")

    assert answer == "A refuge area is..."
    call = backend.text_calls[0]
    assert call["cache_system"] is True
    assert "some knowledge context" in call["system"]
    assert call["model"] == "llama-3.3-70b-versatile"  # reasoning tier, groq default


def test_llm_client_without_credentials_raises_clear_error():
    llm = LLMClient()  # no injected backend, no GROQ_API_KEY in test env
    with pytest.raises(LLMNotConfiguredError):
        llm.classify_intent("hello", "pending question")


def test_llm_client_without_credentials_fails_the_same_way_on_every_call():
    # Regression test: caught live via the frontend browser test - the first
    # call correctly wrapped the missing-credentials error, but the backend
    # object stayed cached, so the SECOND call on the same LLMClient instance
    # skipped the wrapping and let the raw, provider-specific
    # LLMBackendNotConfiguredError escape uncaught (a 500 in the API, not the
    # graceful "didn't catch that" fallback dialogue/manager.py depends on).
    llm = LLMClient()
    for _ in range(3):
        with pytest.raises(LLMNotConfiguredError):
            llm.classify_intent("hello", "pending question")


def test_config_switches_provider_and_models_via_env(monkeypatch):
    monkeypatch.setenv("FIRE_AGENT_LLM_PROVIDER", "anthropic")
    config = LLMConfig()
    assert config.model_for("routine") == "claude-haiku-4-5"
    assert config.model_for("reasoning") == "claude-sonnet-5"


def test_config_model_override_wins_over_provider_default(monkeypatch):
    monkeypatch.setenv("FIRE_AGENT_ROUTINE_MODEL", "custom-model-id")
    config = LLMConfig()
    assert config.model_for("routine") == "custom-model-id"


def test_unknown_provider_raises_not_configured_error():
    llm = LLMClient(config=LLMConfig(provider="not-a-real-provider"))
    with pytest.raises(LLMNotConfiguredError):
        llm.classify_intent("hello", "pending question")
