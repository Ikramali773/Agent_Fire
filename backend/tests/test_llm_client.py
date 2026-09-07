"""Tests the LLMClient wrapper against a fake Anthropic client - verifies our
dynamic schema construction and call wiring without any network access or
API key, per app/llm/client.py's testability design.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.llm.client import LLMClient, LLMNotConfiguredError


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeMessage:
    content: list[Any]


@dataclass
class FakeParsedResponse:
    parsed_output: Any


class FakeMessagesAPI:
    def __init__(self, parse_return=None, create_return=None):
        self._parse_return = parse_return
        self._create_return = create_return
        self.parse_calls: list[dict] = []
        self.create_calls: list[dict] = []

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self._parse_return

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self._create_return


@dataclass
class FakeAnthropicClient:
    messages: FakeMessagesAPI


def test_extract_fields_builds_dynamic_schema_and_returns_only_non_null():
    class Parsed:
        def model_dump(self):
            return {"height_m": 12.5, "floors_above_ground": None}

    fake_client = FakeAnthropicClient(
        messages=FakeMessagesAPI(parse_return=FakeParsedResponse(parsed_output=Parsed()))
    )
    llm = LLMClient(anthropic_client=fake_client)

    result = llm.extract_fields("about 12.5 meters tall", {"height_m": float, "floors_above_ground": int})

    assert result == {"height_m": 12.5}
    call = fake_client.messages.parse_calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["output_format"].__name__ == "ExtractedFields"


def test_classify_intent_returns_parsed_literal():
    class Parsed:
        intent = "question"

    fake_client = FakeAnthropicClient(
        messages=FakeMessagesAPI(parse_return=FakeParsedResponse(parsed_output=Parsed()))
    )
    llm = LLMClient(anthropic_client=fake_client)

    intent = llm.classify_intent("what's a refuge area?", "What's the building height?")
    assert intent == "question"


def test_answer_question_extracts_text_block_and_caches_system_prompt():
    fake_client = FakeAnthropicClient(
        messages=FakeMessagesAPI(create_return=FakeMessage(content=[FakeTextBlock(text="A refuge area is...")]))
    )
    llm = LLMClient(anthropic_client=fake_client)

    answer = llm.answer_question("what's a refuge area?", "some knowledge context")

    assert answer == "A refuge area is..."
    call = fake_client.messages.create_calls[0]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "some knowledge context" in call["system"][0]["text"]


def test_llm_client_without_credentials_raises_clear_error():
    llm = LLMClient()  # no injected client, no ANTHROPIC_API_KEY in test env
    with pytest.raises(LLMNotConfiguredError):
        llm.classify_intent("hello", "pending question")
