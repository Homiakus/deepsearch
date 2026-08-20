"""Unit tests for Dynamic Cookie & Auth Session Persistence Vault."""

import time
from scraper.security.vault_session import SessionVault, AuthSession


def test_session_vault_encryption_and_crud(tmp_path):
    vault_file = str(tmp_path / "sessions.vault")
    secret = "test-secret-key-32-chars-long!!"
    vault = SessionVault(vault_path=vault_file, secret_key=secret)

    session = AuthSession(
        domain="api.github.com",
        cookies={"user_session": "abc123token"},
        headers={"X-Custom-Auth": "SecretHeader"},
        bearer_token="ghp_exampleToken12345",
        expires_at=time.time() + 3600,
    )

    vault.save_session(session)

    # Verify encrypted on disk
    with open(vault_file, "rb") as f:
        data = f.read()
        assert b"ghp_exampleToken12345" not in data  # must be encrypted

    # Verify retrieval
    loaded = vault.get_session("api.github.com")
    assert loaded is not None
    assert loaded.bearer_token == "ghp_exampleToken12345"
    assert loaded.cookies["user_session"] == "abc123token"
    assert loaded.headers["X-Custom-Auth"] == "SecretHeader"

    # Verify header injection
    injected = vault.inject_for_url("https://api.github.com/user")
    assert injected["Authorization"] == "Bearer ghp_exampleToken12345"
    assert injected["X-Custom-Auth"] == "SecretHeader"
    assert "user_session=abc123token" in injected["Cookie"]

    # Verify removal
    assert vault.remove_session("api.github.com") is True
    assert vault.get_session("api.github.com") is None


def test_session_vault_expiration(tmp_path):
    vault_file = str(tmp_path / "expired.vault")
    vault = SessionVault(vault_path=vault_file, secret_key="test-secret")

    expired_session = AuthSession(
        domain="expired.example.com",
        cookies={"session": "old"},
        expires_at=time.time() - 10,
    )
    vault.save_session(expired_session)

    # get_session should clean up expired session
    assert vault.get_session("expired.example.com") is None
