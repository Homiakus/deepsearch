"""Named Entity Extraction for Search Intelligence (DS-SI04)."""

import re
from enum import Enum

from scraper.research.intent import Entity


class EntityClass(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PRODUCT = "PRODUCT"
    MODEL = "MODEL"
    VERSION = "VERSION"
    STANDARD = "STANDARD"
    PAPER = "PAPER"
    DOI = "DOI"
    PMID = "PMID"
    CHEMICAL = "CHEMICAL"
    DISEASE = "DISEASE"
    LOCATION = "LOCATION"
    DATE = "DATE"
    SOFTWARE_API = "SOFTWARE_API"
    OTHER_IDENTIFIER = "OTHER_IDENTIFIER"


# Domain dictionaries and regex recognizers
MEDICAL_TERMS = {
    "diabetes": EntityClass.DISEASE,
    "диабет": EntityClass.DISEASE,
    "oncology": EntityClass.DISEASE,
    "онкология": EntityClass.DISEASE,
    "hypertension": EntityClass.DISEASE,
    "гипертония": EntityClass.DISEASE,
    "carcinoma": EntityClass.DISEASE,
    "melanoma": EntityClass.DISEASE,
    "aspirin": EntityClass.CHEMICAL,
    "аспирин": EntityClass.CHEMICAL,
    "insulin": EntityClass.CHEMICAL,
    "инсулин": EntityClass.CHEMICAL,
    "metformin": EntityClass.CHEMICAL,
    "метформин": EntityClass.CHEMICAL,
    "crispr": EntityClass.CHEMICAL,
}


TECH_TERMS = {
    "qdrant": EntityClass.PRODUCT,
    "fastembed": EntityClass.PRODUCT,
    "servo": EntityClass.PRODUCT,
    "webrender": EntityClass.PRODUCT,
    "chromium": EntityClass.PRODUCT,
    "sqlite": EntityClass.PRODUCT,
    "simhash": EntityClass.SOFTWARE_API,
    "minhash": EntityClass.SOFTWARE_API,
    "nxopen": EntityClass.SOFTWARE_API,
    "crawlee": EntityClass.PRODUCT,
    "playwright": EntityClass.PRODUCT,
}


def extract_entities_from_query(query: str) -> list[Entity]:
    """Extracts typed entities from query string."""
    entities: list[Entity] = []
    q_lower = query.lower()

    # 1. Regex-based pattern extractors
    # DOI
    for m in re.finditer(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", query):
        entities.append(
            Entity(
                name=m.group(0),
                entity_type=EntityClass.DOI.value,
                canonical_form=m.group(0),
            )
        )

    # PMID / PMC
    for m in re.finditer(r"\b(?:PMID:?\s*|PMC)(\d+)\b", query, re.IGNORECASE):
        entities.append(
            Entity(
                name=m.group(0),
                entity_type=EntityClass.PMID.value,
                canonical_form=m.group(0).upper(),
            )
        )

    # Standards (GOST, ISO, RFC, IEEE)
    for m in re.finditer(
        r"\b(ГОСТ|ISO|RFC|IEEE)\s*[\d.-]+(?::\d+)?\b", query, re.IGNORECASE
    ):
        entities.append(
            Entity(
                name=m.group(0),
                entity_type=EntityClass.STANDARD.value,
                canonical_form=m.group(0).upper(),
            )
        )

    # Software API symbols (UF_DRAW_*, function::symbol)
    for m in re.finditer(
        r"\b[A-Z][a-zA-Z0-9_]+::[A-Za-z0-9_]+\b|\b[A-Z]{2,}_[A-Z0-9_]{3,}\b", query
    ):
        entities.append(
            Entity(
                name=m.group(0),
                entity_type=EntityClass.SOFTWARE_API.value,
                canonical_form=m.group(0),
            )
        )

    # Versions
    for m in re.finditer(r"\bv?\d+\.\d+(?:\.\d+)?\b", query):
        entities.append(
            Entity(
                name=m.group(0),
                entity_type=EntityClass.VERSION.value,
                canonical_form=m.group(0),
            )
        )

    # 2. Dictionary-based recognizers
    for term, eclass in MEDICAL_TERMS.items():
        if term in q_lower:
            entities.append(
                Entity(name=term, entity_type=eclass.value, canonical_form=term)
            )

    for term, eclass in TECH_TERMS.items():
        if term in q_lower:
            entities.append(
                Entity(name=term, entity_type=eclass.value, canonical_form=term)
            )

    # Deduplicate entities by name
    seen = set()
    unique_entities = []
    for e in entities:
        if e.name.lower() not in seen:
            seen.add(e.name.lower())
            unique_entities.append(e)

    return unique_entities
