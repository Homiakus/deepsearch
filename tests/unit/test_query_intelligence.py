"""Unit tests for Query Intelligence & Research Goals (DS-SI02 - DS-SI07)."""

import pytest
from scraper.research.intent import ResearchIntent, FreshnessRequirement
from scraper.research.query_normalizer import normalize_query
from scraper.research.entities import extract_entities_from_query
from scraper.research.goals import ResearchGoal, ResearchGoalGraph, GoalStatus
from scraper.research.decomposer import decompose_intent
from scraper.search.query_generator import QueryGenerator


def test_query_normalizer_preserves_identifiers():
    q = 'NXOpen UF_DRAW_2512 "special parameter" 10.1016/j.addma.2020.101345 ГОСТ 25346-2013'
    norm = normalize_query(q)

    assert "special parameter" in norm.quoted_phrases
    assert any("UF_DRAW_2512" in i for i in norm.identifiers)
    assert any("10.1016" in i for i in norm.identifiers)
    assert any("ГОСТ" in i for i in norm.identifiers)
    assert norm.has_cyrillic is True
    assert norm.has_latin is True


def test_entity_extraction_types():
    q = "baricitinib clinical trials for androgenetic alopecia compared with minoxidil in ISO 9001"
    entities = extract_entities_from_query(q)

    e_names = [e.name.lower() for e in entities]
    assert "baricitinib" in e_names
    assert "alopecia" in e_names or "androgenetic alopecia" in e_names
    assert "minoxidil" in e_names
    assert any(e.entity_type == "STANDARD" for e in entities)


def test_goal_decomposition_comparative_and_medical():
    q = "SLA vs DLP 3D printing resolution and curing wavelength"
    norm = normalize_query(q)
    intent = ResearchIntent(
        original_query=q,
        normalized_query=norm.normalized_text,
        task_type="engineering",
    )
    goal_graph = decompose_intent(intent)

    assert len(goal_graph.goals) >= 3  # Root + 2 comparative goals
    assert goal_graph.root_goal_id is not None
    uncovered = goal_graph.get_uncovered_goals()
    assert len(uncovered) >= 3


def test_query_generator_variants_budget():
    q = "Qdrant HNSW vector search payload filtering"
    norm = normalize_query(q)
    intent = ResearchIntent(
        original_query=q,
        normalized_query=norm.normalized_text,
        task_type="technical",
    )
    goal_graph = decompose_intent(intent)
    q_gen = QueryGenerator(max_queries_per_goal=3, max_total_query_variants=10)
    variants = q_gen.generate_variants(intent, goal_graph)

    assert len(variants) > 0
    assert len(variants) <= 10
    assert all(v.query and v.goal_id for v in variants)
