"""Tests for the auth hardening flagged in the Phase 1-3 audit.

Three separate holes, all of them the kind that only matter once somebody
other than the developer uses the thing: a logout that did not log you out,
a login endpoint with no limit, and a signing key published in this
repository.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.auth import rate_limit, revoked_tokens
from app.auth.tokens import create_token, decode_token, using_default_secret
from app.auth.user_store import delete_all as delete_all_users
from app.main import _check_auth_secret, app
from app.store import delete_all as delete_all_case_files

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    delete_all_case_files()
    delete_all_users()
    revoked_tokens.delete_all()
    rate_limit.reset()


def _signup(email: str = "a@example.com", password: str = "correct-horse") -> dict:
    return client.post("/auth/signup", json={"email": email, "password": password}).json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestLogoutRevokesTheToken:
    def test_a_token_stops_working_after_logout(self):
        # Before this, logout only made the frontend forget the token while
        # it stayed valid for the rest of its seven-day life.
        account = _signup()
        token = account["access_token"]
        assert client.get("/auth/me", headers=_headers(token)).status_code == 200

        assert client.post("/auth/logout", headers=_headers(token)).status_code == 204

        assert client.get("/auth/me", headers=_headers(token)).status_code == 401

    def test_a_revoked_token_cannot_reach_case_files_either(self):
        # /auth/me is not the only door.
        account = _signup()
        token = account["access_token"]
        session_id = client.post("/case-files", json=None, headers=_headers(token)).json()["session_id"]
        client.post("/auth/logout", headers=_headers(token))

        assert client.get(f"/case-files/{session_id}", headers=_headers(token)).status_code == 403
        assert client.get("/users/me/case-files", headers=_headers(token)).status_code == 401

    def test_signing_out_on_one_device_leaves_other_sessions_alone(self):
        # Each token carries its own id, so revocation is per session.
        _signup()
        first = client.post("/auth/login", json={"email": "a@example.com", "password": "correct-horse"}).json()
        rate_limit.reset()
        second = client.post("/auth/login", json={"email": "a@example.com", "password": "correct-horse"}).json()

        client.post("/auth/logout", headers=_headers(first["access_token"]))

        assert client.get("/auth/me", headers=_headers(first["access_token"])).status_code == 401
        assert client.get("/auth/me", headers=_headers(second["access_token"])).status_code == 200

    def test_logging_out_twice_is_not_an_error(self):
        token = _signup()["access_token"]

        assert client.post("/auth/logout", headers=_headers(token)).status_code == 204
        assert client.post("/auth/logout", headers=_headers(token)).status_code == 204

    def test_logging_out_without_a_token_is_still_204(self):
        # "Am I logged out?" should have exactly one answer, and an error
        # would confirm to an attacker which tokens are live.
        assert client.post("/auth/logout").status_code == 204
        assert client.post("/auth/logout", headers={"Authorization": "Bearer nonsense"}).status_code == 204

    def test_expired_revocations_are_pruned_rather_than_kept_forever(self):
        from datetime import datetime, timedelta, timezone

        revoked_tokens.revoke("old", "u1", datetime.now(timezone.utc) - timedelta(days=1))
        assert revoked_tokens.is_revoked("old") is True

        # Any later revocation prunes what has already expired.
        revoked_tokens.revoke("new", "u1", datetime.now(timezone.utc) + timedelta(days=1))

        assert revoked_tokens.is_revoked("old") is False
        assert revoked_tokens.is_revoked("new") is True

    def test_every_issued_token_has_its_own_id(self):
        first = decode_token(create_token("u1"))
        second = decode_token(create_token("u1"))

        assert first.token_id and second.token_id
        assert first.token_id != second.token_id


class TestLoginRateLimit:
    def test_repeated_wrong_passwords_are_eventually_refused(self):
        _signup()

        statuses = [
            client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"}).status_code
            for _ in range(rate_limit.MAX_ATTEMPTS + 2)
        ]

        assert statuses[0] == 401
        assert 429 in statuses

    def test_the_refusal_says_how_long_to_wait(self):
        _signup()
        for _ in range(rate_limit.MAX_ATTEMPTS + 1):
            client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})

        resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})

        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) >= 1

    def test_a_correct_password_clears_the_counter(self):
        # Someone who mistypes a few times and then gets it right must not
        # be left throttled.
        _signup()
        for _ in range(rate_limit.MAX_ATTEMPTS - 1):
            client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})

        assert client.post(
            "/auth/login", json={"email": "a@example.com", "password": "correct-horse"}
        ).status_code == 200
        assert client.post(
            "/auth/login", json={"email": "a@example.com", "password": "correct-horse"}
        ).status_code == 200

    def test_one_account_being_attacked_does_not_lock_out_another(self):
        _signup("victim@example.com")
        _signup("other@example.com")
        for _ in range(rate_limit.MAX_ATTEMPTS + 2):
            client.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})

        assert client.post(
            "/auth/login", json={"email": "other@example.com", "password": "correct-horse"}
        ).status_code == 200

    def test_the_limiter_forgets_attempts_once_the_window_passes(self, monkeypatch):
        monkeypatch.setattr(rate_limit, "WINDOW_SECONDS", 0.2)
        for _ in range(rate_limit.MAX_ATTEMPTS + 1):
            rate_limit.check("k")
        assert rate_limit.check("k") is not None

        time.sleep(0.25)

        assert rate_limit.check("k") is None

    def test_signup_is_not_rate_limited_by_the_login_counter(self):
        # Different endpoint, different failure mode - a shared counter
        # would let login attempts block account creation.
        for _ in range(rate_limit.MAX_ATTEMPTS + 2):
            client.post("/auth/login", json={"email": "new@example.com", "password": "wrong"})

        assert client.post(
            "/auth/signup", json={"email": "new@example.com", "password": "correct-horse"}
        ).status_code == 201


class TestDefaultSecretGuard:
    def test_the_tests_themselves_run_on_the_development_key(self):
        # If this ever stops being true the guard below is not being
        # exercised at all.
        assert using_default_secret() is True

    @pytest.mark.parametrize("environment", ["production", "prod", "staging", "PRODUCTION"])
    def test_a_production_start_is_refused(self, monkeypatch, environment: str):
        # The difference between "every account is protected by a password"
        # and "every account is open to anyone who has read the source".
        monkeypatch.setenv("FIRE_AGENT_ENV", environment)

        with pytest.raises(RuntimeError, match="Refusing to start"):
            _check_auth_secret()

    def test_development_only_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("FIRE_AGENT_ENV", "development")

        _check_auth_secret()

        assert any("SECURITY" in record.message for record in caplog.records)

    def test_no_environment_set_is_treated_as_development(self, monkeypatch):
        monkeypatch.delenv("FIRE_AGENT_ENV", raising=False)

        _check_auth_secret()  # must not raise
