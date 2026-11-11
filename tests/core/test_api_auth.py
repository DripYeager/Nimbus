from __future__ import annotations

import pytest

import core.api_auth as auth_module
from core.api_auth import TOKEN_HEADER, auth_headers, is_allowed_host, is_valid_token, session_token


@pytest.fixture
def fresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_token", None)


def test_session_token_is_random_and_stable_for_the_run(fresh_token: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(auth_module.TOKEN_ENV_VAR, raising=False)
    first = session_token()

    assert (len(first) >= 40, session_token()) == (True, first)


def test_session_token_comes_from_the_environment_when_set(fresh_token: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(auth_module.TOKEN_ENV_VAR, "my-secret")

    assert session_token() == "my-secret"


def test_auth_headers_carry_the_token() -> None:
    assert auth_headers() == {TOKEN_HEADER: session_token()}


@pytest.mark.parametrize(("presented", "expected"), [(None, False), ("wrong", False)])
def test_is_valid_token_rejects_missing_or_wrong(presented: str | None, expected: bool) -> None:
    assert is_valid_token(presented) is expected


def test_is_valid_token_accepts_this_runs_token() -> None:
    assert is_valid_token(session_token())


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1:8765", True),
        ("localhost:8765", True),
        ("LOCALHOST", True),
        ("evil.example:8765", False),
        ("", False),
        (None, False),
    ],
)
def test_is_allowed_host_only_accepts_this_machine_by_name(host: str | None, expected: bool) -> None:
    assert is_allowed_host(host) is expected
