"""Unit tests for Evidence Layer, Coverage, Information Gain & Gaps (DS-SI51 - DS-SI64)."""

from scraper.evidence.models import EvidenceRelation
from scraper.evidence.store import EvidenceStore
from scraper.research.coverage import goal_coverage_analyzer
from scraper.research.gaps import gap_analyzer
from scraper.research.goals import ResearchGoal, ResearchGoalGraph
from scraper.search.followup import followup_query_generator


def test_evidence_matching_and_store():
    store = EvidenceStore()
    claim = store.add_claim(
        "c1", "Baricitinib is effective for severe alopecia areata.", goal_id="g1"
    )

    # Add supporting evidence
    store.add_evidence(
        evidence_id="e1",
        claim_id="c1",
        source_url="https://europepmc.org/article/PMC9346513",
        chunk_id="chk1",
        quote="Baricitinib was superior to placebo with respect to hair regrowth.",
        relation=EvidenceRelation.SUPPORTS,
        domain="europepmc.org",
        source_type="PRIMARY_RESEARCH",
    )

    assert claim.status == "SUPPORTED"
    assert claim.independent_sources_count == 1

    # Add second independent supporting evidence
    store.add_evidence(
        evidence_id="e2",
        claim_id="c1",
        source_url="https://nejm.org/doi/full/10.1056/NEJMoa2119588",
        chunk_id="chk2",
        quote="Two phase 3 trials showed baricitinib efficacy.",
        relation=EvidenceRelation.SUPPORTS,
        domain="nejm.org",
        source_type="PRIMARY_RESEARCH",
    )

    assert claim.status == "VERIFIED"
    assert claim.independent_sources_count == 2


def test_goal_coverage_and_gap_analysis():
    graph = ResearchGoalGraph()
    g1 = ResearchGoal(
        id="g1",
        question="What are effective alopecia treatments?",
        required_evidence_types=["PRIMARY_RESEARCH"],
    )
    g2 = ResearchGoal(
        id="g2",
        question="What are common side effects?",
        required_evidence_types=["PRIMARY_RESEARCH"],
    )
    graph.add_goal(g1)
    graph.add_goal(g2)

    store = EvidenceStore()
    store.add_claim("c1", "Baricitinib promotes hair growth", goal_id="g1")
    store.add_evidence(
        "e1",
        "c1",
        "https://europepmc.org/1",
        "chk1",
        "Promotes hair growth",
        domain="europepmc.org",
        source_type="PRIMARY_RESEARCH",
    )

    assessment = goal_coverage_analyzer.analyze(graph, store)
    assert assessment.overall_progress > 0.0
    assert assessment.is_sufficient is False  # g2 is still uncovered

    gaps = gap_analyzer.identify_gaps(graph, store)
    assert any(g.goal_id == "g2" for g in gaps)

    followups = followup_query_generator.generate_followup_queries(gaps)
    assert len(followups) > 0
    assert any("side effects" in f.query.lower() for f in followups)
