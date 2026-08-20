"""URL Canonicalization, 3-Level Deduplication Engine, and Text Sanitization."""

from scraper.normalization.text import recursive_sanitize, sanitize_unicode_string

__all__ = ["sanitize_unicode_string", "recursive_sanitize"]
