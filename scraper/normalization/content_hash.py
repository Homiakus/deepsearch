"""Exact Content Hash Engine (DS-SI33)."""

import hashlib
import re
import unicodedata


def compute_content_hash(text: str) -> str:
    """Computes deterministic SHA-256 hash over normalized text content."""
    if not text:
        return hashlib.sha256(b"").hexdigest()

    # 1. Unicode NFKC normalization
    norm_text = unicodedata.normalize("NFKC", text)

    # 2. Whitespace normalization (collapse multi-spaces and blank lines)
    norm_text = re.sub(r"[ \t]+", " ", norm_text)
    norm_text = re.sub(r"\n+", "\n", norm_text).strip().lower()

    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
