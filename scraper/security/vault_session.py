"""Dynamic Cookie and Authentication Session Persistence Engine with AES-GCM Encryption.

Enables secure storage, retrieval, and automated injection of authenticated sessions,
bearer tokens, and cookies across crawl executions.
"""

import base64
import hashlib
import json
import os
import time
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from scraper.config import settings

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class AuthSession(BaseModel):
    """Encapsulates authenticated domain session data."""

    domain: str
    cookies: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    bearer_token: str | None = None
    created_at: float = Field(default_factory=time.time)
    expires_at: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at


class SessionVault:
    """Encrypted persistent session and cookie vault."""

    def __init__(
        self,
        vault_path: str = settings.session_vault_path,
        secret_key: str = settings.session_vault_key,
    ):
        self.vault_path = vault_path
        self._key = hashlib.sha256(secret_key.encode("utf-8")).digest()
        os.makedirs(os.path.dirname(os.path.abspath(self.vault_path)), exist_ok=True)
        self._sessions: dict[str, AuthSession] = {}
        self._load_vault()

    def _encrypt(self, plaintext: bytes) -> bytes:
        if not CRYPTO_AVAILABLE:
            # Fallback XOR cipher for environments without cryptography lib
            return base64.b64encode(
                bytes(
                    [b ^ self._key[i % len(self._key)] for i, b in enumerate(plaintext)]
                )
            )
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def _decrypt(self, payload: bytes) -> bytes:
        if not CRYPTO_AVAILABLE:
            raw = base64.b64decode(payload)
            return bytes([b ^ self._key[i % len(self._key)] for i, b in enumerate(raw)])
        nonce = payload[:12]
        ciphertext = payload[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def _load_vault(self) -> None:
        if not os.path.exists(self.vault_path):
            return
        try:
            with open(self.vault_path, "rb") as f:
                encrypted_data = f.read()
            if not encrypted_data:
                return
            decrypted = self._decrypt(encrypted_data)
            data = json.loads(decrypted.decode("utf-8"))
            for domain, s_dict in data.items():
                self._sessions[domain] = AuthSession(**s_dict)
        except Exception:
            self._sessions = {}

    def _save_vault(self) -> None:
        raw_dict = {domain: s.model_dump() for domain, s in self._sessions.items()}
        plaintext = json.dumps(raw_dict).encode("utf-8")
        encrypted = self._encrypt(plaintext)
        with open(self.vault_path, "wb") as f:
            f.write(encrypted)

    def save_session(self, session: AuthSession) -> None:
        """Store or update session for a domain."""
        self._sessions[session.domain.lower()] = session
        self._save_vault()

    def get_session(self, domain: str) -> AuthSession | None:
        """Retrieve valid session for domain or parent domain."""
        domain = domain.lower()
        if domain in self._sessions:
            s = self._sessions[domain]
            if not s.is_expired():
                return s
            del self._sessions[domain]
            self._save_vault()

        # Check wildcard / parent domain
        for d, s in list(self._sessions.items()):
            if domain.endswith(f".{d}"):
                if not s.is_expired():
                    return s
                del self._sessions[d]
                self._save_vault()
        return None

    def remove_session(self, domain: str) -> bool:
        """Remove a domain session from vault."""
        domain = domain.lower()
        if domain in self._sessions:
            del self._sessions[domain]
            self._save_vault()
            return True
        return False

    def list_domains(self) -> list[str]:
        """List active unexpired domains."""
        active = []
        for domain, s in list(self._sessions.items()):
            if not s.is_expired():
                active.append(domain)
        return active

    def inject_for_url(
        self, url: str, headers: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Inject cookies and auth headers into outgoing request headers for a given URL."""
        res_headers = dict(headers or {})
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        session = self.get_session(domain)
        if not session:
            return res_headers

        # Inject session custom headers
        for k, v in session.headers.items():
            res_headers[k] = v

        # Inject bearer token
        if session.bearer_token and "Authorization" not in res_headers:
            res_headers["Authorization"] = f"Bearer {session.bearer_token}"

        # Inject cookies as Cookie header
        if session.cookies:
            cookie_strs = [f"{k}={v}" for k, v in session.cookies.items()]
            existing = res_headers.get("Cookie", "")
            if existing:
                cookie_strs.insert(0, existing)
            res_headers["Cookie"] = "; ".join(cookie_strs)

        return res_headers
