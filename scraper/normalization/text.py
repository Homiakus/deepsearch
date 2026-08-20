"""Text and Unicode Sanitization Utilities.

Protects JSON serialization and Markdown generation from unpaired surrogates,
null bytes, and unprintable control characters extracted from malformed PDFs and web pages.
"""

import re
from typing import Any

RE_SURROGATES = re.compile(r"[\ud800-\udfff]")
RE_NULL_BYTES = re.compile(r"\x00")
RE_CONTROL_CHARS = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_unicode_string(text: str) -> str:
    """Sanitizes string from unpaired Unicode surrogates, null bytes, and control characters."""
    if not text:
        return ""
    # 1. Replace unpaired surrogates using utf-8 replace encoder-decoder roundtrip
    clean = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    # 2. Remove null bytes
    clean = RE_NULL_BYTES.sub("", clean)
    # 3. Remove control characters except standard newlines (\n, \r) and tab (\t)
    clean = RE_CONTROL_CHARS.sub("", clean)
    return clean.strip()


def recursive_sanitize(obj: Any) -> Any:
    """Recursively sanitizes all string fields in dicts, lists, tuples, and primitives."""
    if isinstance(obj, str):
        return sanitize_unicode_string(obj)
    elif isinstance(obj, dict):
        return {
            sanitize_unicode_string(str(k)): recursive_sanitize(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [recursive_sanitize(elem) for elem in obj]
    elif isinstance(obj, tuple):
        return tuple(recursive_sanitize(elem) for elem in obj)
    elif isinstance(obj, set):
        return {recursive_sanitize(elem) for elem in obj}
    return obj
