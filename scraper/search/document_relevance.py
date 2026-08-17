"""Document Relevance Evaluator (DS-SI29).

Evaluates acquired markdown document relevance against query, subgoals,
and required entities to reject off-topic/spam content before RAG indexing.
"""

import re
from enum import Enum
from typing import List, Tuple
from scraper.research.intent import ResearchIntent
from scraper.search.document_quality import DocumentQuality


class RelevanceTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    OFF_TOPIC = "OFF_TOPIC"


class DocumentRelevanceEvaluator:
    """Evaluates document relevance using term coverage, entity occurrence, and heading match."""

    @staticmethod
    def evaluate(
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
        q_tokens = [t for t in re.findall(r'\w+', q_lower) if len(t) > 2]
        doc_lower = text_content.lower()
        title_lower = title.lower()

        # 1. Term occurrences
        matched_tokens = sum(1 for t in q_tokens if t in doc_lower)
        token_coverage = matched_tokens / max(len(q_tokens), 1)

        # 2. Entity matches
        entity_matches = 0
        for e in intent.entities:
            ename = (e.canonical_form or e.name).lower()
            if ename in doc_lower or ename in title_lower:
                entity_matches += 1
        entity_score = entity_matches / max(len(intent.entities), 1) if intent.entities else 1.0

        # 3. Evidence density (rough heuristic: presence of quantitative/verifiable tokens)
        has_numbers = len(re.findall(r'\b\d+(?:\.\d+)?\b', doc_lower)) > 3
        has_citations = any(k in doc_lower for k in ["doi:", "pmid", "reference", "источник", "таблица", "табл."])
        density = 0.5 + (0.25 if has_numbers else 0.0) + (0.25 if has_citations else 0.0)

        # Composite score
        raw_relevance = (0.50 * token_coverage) + (0.35 * entity_score) + (0.15 * density)
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
