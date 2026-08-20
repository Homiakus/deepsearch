"""Deterministic Query Normalizer (DS-SI03).

Preserves exact identifiers, version tokens, acronyms, and quoted phrases
without destructive stemming.
"""

import re
import unicodedata
from typing import List, Set
from pydantic import BaseModel, Field


class NormalizedQuery(BaseModel):
    raw_query: str
    normalized_text: str
    quoted_phrases: List[str] = Field(default_factory=list)
    identifiers: List[str] = Field(default_factory=list)
    detected_languages: List[str] = Field(default_factory=list)
    has_cyrillic: bool = False
    has_latin: bool = False


# Regex patterns for non-destructive entity and identifier preservation
RE_QUOTED = re.compile(r'["«]([^"»]+)["»]')
RE_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
RE_PMID = re.compile(r"\b(?:PMID:?\s*|PMC)(\d+)\b", re.IGNORECASE)
RE_GOST = re.compile(r"\bГОСТ\s*[\d.-]+(?::\d+)?\b", re.IGNORECASE)
RE_API_SYMBOL = re.compile(
    r"\b[A-Z][a-zA-Z0-9_]+::[A-Za-z0-9_]+\b|\b[A-Z]{2,}_[A-Z0-9_]+\b"
)
RE_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?\b")
RE_UNITS = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:nm|mm|cm|m|kg|g|mg|hz|khz|mhz|ghz|rpm|v|w|a|%)\b",
    re.IGNORECASE,
)


def normalize_query(query: str) -> NormalizedQuery:
    """Performs deterministic Unicode normalization and entity extraction without destruction."""
    if not query:
        return NormalizedQuery(raw_query="", normalized_text="")

    # 1. Unicode NFKC normalization
    nfkc = unicodedata.normalize("NFKC", query.strip())

    # 2. Extract quoted phrases
    quoted = [m.strip() for m in RE_QUOTED.findall(nfkc) if m.strip()]

    # 3. Extract technical identifiers
    identifiers: Set[str] = set()
    for match in RE_DOI.finditer(nfkc):
        identifiers.add(match.group(0))
    for match in RE_PMID.finditer(nfkc):
        identifiers.add(match.group(0))
    for match in RE_GOST.finditer(nfkc):
        identifiers.add(match.group(0))
    for match in RE_API_SYMBOL.finditer(nfkc):
        identifiers.add(match.group(0))
    for match in RE_VERSION.finditer(nfkc):
        identifiers.add(match.group(0))
    for match in RE_UNITS.finditer(nfkc):
        identifiers.add(match.group(0))

    # 4. Whitespace cleanup
    clean_text = re.sub(r"\s+", " ", nfkc).strip()

    # 5. Language detection markers
    has_cyrillic = bool(re.search(r"[\u0400-\u04FF]", clean_text))
    has_latin = bool(re.search(r"[a-zA-Z]", clean_text))

    languages = []
    if has_latin:
        languages.append("en")
    if has_cyrillic:
        languages.append("ru")
    if not languages:
        languages.append("en")

    return NormalizedQuery(
        raw_query=query,
        normalized_text=clean_text,
        quoted_phrases=quoted,
        identifiers=sorted(list(identifiers)),
        detected_languages=languages,
        has_cyrillic=has_cyrillic,
        has_latin=has_latin,
    )
