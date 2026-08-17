"""Unit tests for Document Assessment, Content Filter, and Deduplication (DS-SI28 - DS-SI36)."""

import pytest
from scraper.research.intent import ResearchIntent, Entity
from scraper.search.document_relevance import document_relevance_evaluator, RelevanceTier
from scraper.extraction.content_filter import content_filter
from scraper.normalization.content_hash import compute_content_hash
from scraper.normalization.near_duplicate import NearDuplicateDetector
from scraper.search.source_lineage import SourceLineage, LineageRelation


def test_content_filter_and_relevance_evaluation():
    intent = ResearchIntent(
        original_query="photopolymer SLA curing 405nm",
        normalized_query="photopolymer SLA curing 405nm",
        entities=[Entity(name="405nm", entity_type="OTHER_IDENTIFIER")],
    )

    relevant_text = "# SLA Photopolymers\n\nStandard desktop stereolithography resin photoinitiators peak at 405nm ultraviolet-visible curing wavelength with high resolution."
    tier, quality = document_relevance_evaluator.evaluate(relevant_text, "SLA Resins Guide", intent)

    assert tier in (RelevanceTier.HIGH, RelevanceTier.MEDIUM)
    assert quality.is_accepted is True

    # Off-topic content
    offtopic_text = "# Cooking Recipes\n\nHow to bake fresh apple pies with cinnamon and vanilla sugar in oven at 180 degrees."
    off_tier, off_quality = document_relevance_evaluator.evaluate(offtopic_text, "Apple Pie Recipe", intent)

    assert off_tier == RelevanceTier.OFF_TOPIC
    assert off_quality.is_accepted is False


def test_near_duplicate_detection_and_lineage():
    detector = NearDuplicateDetector(hamming_threshold=5)
    t1 = """Stereolithography (SLA) 3D printing uses a liquid photopolymer resin that is selectively cured layer by layer using an ultraviolet laser beam with 405nm wavelength to produce accurate physical prototypes and functional parts."""
    t2 = """Stereolithography (SLA) 3D printing uses a liquid photopolymer resin that is selectively cured layer by layer using an ultraviolet laser beam with 405nm wavelength to produce accurate physical prototypes and functional parts in engineering laboratories."""

    is_dup1, _, c1 = detector.register_document("doc1", t1)
    is_dup2, dup_of, c2 = detector.register_document("doc2", t2)

    assert is_dup1 is False
    assert is_dup2 is True
    assert dup_of == "doc1"
    assert c1 == c2

    lineage = SourceLineage()
    s1 = lineage.register_source("doc1", "https://primary.com/doc", "primary.com", content_hash="hash1", near_dup_cluster=c1, is_primary=True)
    s2 = lineage.register_source("doc2", "https://mirror.com/doc", "mirror.com", content_hash="hash2", near_dup_cluster=c2)

    assert s1.relation_to_root == LineageRelation.PRIMARY_SOURCE
    assert s2.relation_to_root == LineageRelation.SYNDICATED_COPY
