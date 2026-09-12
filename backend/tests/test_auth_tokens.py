"""Unit tests for app/auth/tokens.py's hand-rolled signed session tokens -
see that module's docstring for why this isn't a JWT library.
"""

import time

from app.auth import tokens


def test_create_and_verify_round_trip():
    token = tokens.create_token("user-123")
    assert tokens.verify_token(token) == "user-123"


def test_verify_rejects_a_tampered_signature():
    token = tokens.create_token("user-123")
    payload_b64, signature = token.split(".", 1)
    flipped = "0" if signature[-1] != "0" else "1"
    tampered = f"{payload_b64}.{signature[:-1]}{flipped}"
    assert tokens.verify_token(tampered) is None


def test_verify_rejects_a_tampered_payload():
    token = tokens.create_token("user-123")
    payload_b64, signature = token.split(".", 1)
    tampered = f"{payload_b64}x.{signature}"
    assert tokens.verify_token(tampered) is None


def test_verify_rejects_malformed_tokens():
    assert tokens.verify_token("not-a-token-at-all") is None
    assert tokens.verify_token("") is None


def test_verify_rejects_an_expired_token(monkeypatch):
    monkeypatch.setattr(tokens, "_TOKEN_TTL_SECONDS", 1)
    token = tokens.create_token("user-123")
    time.sleep(1.5)
    assert tokens.verify_token(token) is None


def test_tokens_signed_with_a_different_secret_never_verify(monkeypatch):
    token = tokens.create_token("user-123")
    monkeypatch.setattr(tokens, "_SECRET", "a-completely-different-secret")
    assert tokens.verify_token(token) is None
