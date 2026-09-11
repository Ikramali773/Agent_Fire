"""Proves generate_json[_from_image] request a smaller max_tokens than
generate_text on both backends - see JSON_MAX_TOKENS/TEXT_MAX_TOKENS in
groq_backend.py/anthropic_backend.py for why: Groq's free/on-demand tier
enforces a tiny per-minute output-token quota per model (seen live: 1000
tokens/minute), and the old flat max_tokens=1024 for every call could
exceed that on a single request, let alone several uploads in a row.
Uses a fake client injected via each backend's constructor - no network,
no real API key needed.
"""

from app.llm.backends.anthropic_backend import AnthropicBackend
from app.llm.backends.anthropic_backend import JSON_MAX_TOKENS as ANTHROPIC_JSON_MAX_TOKENS
from app.llm.backends.anthropic_backend import TEXT_MAX_TOKENS as ANTHROPIC_TEXT_MAX_TOKENS
from app.llm.backends.groq_backend import GroqBackend
from app.llm.backends.groq_backend import JSON_MAX_TOKENS as GROQ_JSON_MAX_TOKENS
from app.llm.backends.groq_backend import TEXT_MAX_TOKENS as GROQ_TEXT_MAX_TOKENS


class FakeGroqMessage:
    content = "{}"


class FakeGroqChoice:
    message = FakeGroqMessage()


class FakeGroqResponse:
    choices = [FakeGroqChoice()]


class FakeGroqCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeGroqResponse()


class FakeGroqChat:
    def __init__(self):
        self.completions = FakeGroqCompletions()


class FakeGroqClient:
    def __init__(self):
        self.chat = FakeGroqChat()


class FakeAnthropicContentBlock:
    type = "text"
    text = "{}"


class FakeAnthropicResponse:
    content = [FakeAnthropicContentBlock()]


class FakeAnthropicMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeAnthropicResponse()


class FakeAnthropicClient:
    def __init__(self):
        self.messages = FakeAnthropicMessages()


class TestGroqMaxTokens:
    def test_json_extraction_uses_smaller_budget(self):
        client = FakeGroqClient()
        backend = GroqBackend(client=client)

        backend.generate_json("system", "user", {"type": "object"}, "some-model")

        assert client.chat.completions.calls[-1]["max_tokens"] == GROQ_JSON_MAX_TOKENS
        assert GROQ_JSON_MAX_TOKENS < GROQ_TEXT_MAX_TOKENS

    def test_text_generation_uses_larger_budget(self):
        client = FakeGroqClient()
        backend = GroqBackend(client=client)

        backend.generate_text("system", "user", "some-model")

        assert client.chat.completions.calls[-1]["max_tokens"] == GROQ_TEXT_MAX_TOKENS

    def test_vision_json_uses_smaller_budget(self):
        client = FakeGroqClient()
        backend = GroqBackend(client=client)

        backend.generate_json_from_image(
            "system", "user", "base64data", "image/png", {"type": "object"}, "some-model"
        )

        assert client.chat.completions.calls[-1]["max_tokens"] == GROQ_JSON_MAX_TOKENS


class TestAnthropicMaxTokens:
    def test_json_extraction_uses_smaller_budget(self):
        client = FakeAnthropicClient()
        backend = AnthropicBackend(client=client)

        backend.generate_json("system", "user", {"type": "object"}, "some-model")

        assert client.messages.calls[-1]["max_tokens"] == ANTHROPIC_JSON_MAX_TOKENS
        assert ANTHROPIC_JSON_MAX_TOKENS < ANTHROPIC_TEXT_MAX_TOKENS

    def test_text_generation_uses_larger_budget(self):
        client = FakeAnthropicClient()
        backend = AnthropicBackend(client=client)

        backend.generate_text("system", "user", "some-model")

        assert client.messages.calls[-1]["max_tokens"] == ANTHROPIC_TEXT_MAX_TOKENS
