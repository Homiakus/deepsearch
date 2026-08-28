"""Document Relevance Evaluator (DS-SI29).

Evaluates acquired markdown document relevance against query, subgoals,
and required entities to reject off-topic/spam content before RAG indexing.
"""

import re
from enum import Enum
from typing import Tuple
from scraper.research.intent import ResearchIntent
from scraper.search.document_quality import DocumentQuality


class RelevanceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF_TOPIC = "OFF_TOPIC"


class DocumentRelevanceEvaluator:
    """Evaluates document relevance using term coverage, entity occurrence, and heading match."""

    RESEARCH_EVIDENCE_MARKERS = (
        "doi:",
        "pmid",
        "reference",
        "references",
        "источник",
        "литература",
        "таблица",
        "табл.",
        "рис.",
        "figure",
        "table",
        "исследование",
        "результаты",
        "вывод",
        "method",
        "experiment",
        "conclusion",
        "p-value",
        "p <",
    )

    @classmethod
    def _term_matches(cls, token: str, text: str) -> bool:
        """Checks exact or morphological prefix match for inflected terms."""
        if token in text:
            return True
        if len(token) >= 4:
            # Check root prefix (e.g. фотополимер -> фотополимеризация / curing -> cured)
            stem = token[:-2] if len(token) >= 6 else token[:-1]
            if len(stem) >= 3 and stem in text:
                return True
        return False

    @classmethod
    def evaluate(
        cls,
        text_content: str,
        title: str,
        intent: ResearchIntent,
        min_relevance_threshold: float = 0.15,
    ) -> Tuple[RelevanceTier, DocumentQuality]:
        if not text_content or len(text_content.strip()) < 50:
            quality = DocumentQuality(
                topical_relevance=0.0,
                is_accepted=False,
                reject_reason="EMPTY_OR_TRIVIAL_CONTENT",
                composite_quality_score=0.0,
            )
            return RelevanceTier.OFF_TOPIC, quality

        q_lower = intent.normalized_query.lower()
        q_tokens = [t for t in re.findall(r"\w+", q_lower) if len(t) > 2]
        doc_lower = text_content.lower()
        title_lower = title.lower()

        # 1. Term occurrences with morphological prefix support
        matched_tokens = 0
        title_matches = 0
        for t in q_tokens:
            if cls._term_matches(t, doc_lower):
                matched_tokens += 1
            if cls._term_matches(t, title_lower):
                title_matches += 1

        token_coverage = matched_tokens / max(len(q_tokens), 1)
        title_bonus = min(0.15, 0.05 * title_matches)

        # 2. Entity matches
        entity_matches = 0
        for e in intent.entities:
            ename = (e.canonical_form or e.name).lower()
            if cls._term_matches(ename, doc_lower) or cls._term_matches(
                ename, title_lower
            ):
                entity_matches += 1
        entity_score = (
            entity_matches / max(len(intent.entities), 1) if intent.entities else 1.0
        )

        # 3. Evidence density (quantitative tokens, metrics, citations)
        has_numbers = len(re.findall(r"\b\d+(?:\.\d+)?\b", doc_lower)) > 3
        has_citations = any(k in doc_lower for k in cls.RESEARCH_EVIDENCE_MARKERS)
        density = (
            0.5 + (0.25 if has_numbers else 0.0) + (0.25 if has_citations else 0.0)
        )

        # Composite score
        raw_relevance = (
            (0.45 * token_coverage)
            + (0.35 * entity_score)
            + (0.15 * density)
            + (0.05 * (title_bonus / 0.15 if title_bonus else 0.0))
        )
        raw_relevance = min(1.0, round(raw_relevance, 4))

        if raw_relevance >= 0.65:
            tier = RelevanceTier.HIGH
        elif raw_relevance >= 0.35:
            tier = RelevanceTier.MEDIUM
        elif raw_relevance >= min_relevance_threshold:
            tier = RelevanceTier.LOW
        else:
            tier = RelevanceTier.OFF_TOPIC

        accepted = tier != RelevanceTier.OFF_TOPIC
        quality = DocumentQuality(
            topical_relevance=raw_relevance,
            evidence_density=density,
            is_accepted=accepted,
            reject_reason=None if accepted else "OFF_TOPIC_RELEVANCE_TOO_LOW",
            composite_quality_score=raw_relevance,
        )

        return tier, quality


document_relevance_evaluator = DocumentRelevanceEvaluator()
