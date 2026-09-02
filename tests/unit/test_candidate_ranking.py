"""Unit tests for Pre-ranking and Candidate Ranking (DS-SI14 - DS-SI22)."""

from scraper.research.intent import Entity, ResearchIntent
from scraper.search.candidate_normalizer import candidate_normalizer
from scraper.search.candidates import SourceCandidate
from scraper.search.ranking.candidate_ranker import candidate_ranker


def test_candidate_normalizer_and_provenance_merge():
    c1 = SourceCandidate(
        url="https://example.com/doc?utm_source=test",
        canonical_url="https://example.com/doc",
        title="Title 1",
        provider="arxiv",
        goal_ids=["g1"],
    )
    c2 = SourceCandidate(
        url="https://example.com/doc",
        canonical_url="https://example.com/doc",
        title="Longer Detailed Title 1",
        provider="wikipedia",
        goal_ids=["g2"],
    )

    merged = candidate_normalizer.normalize_candidates([c1, c2])
    assert len(merged) == 1
    assert "arxiv" in merged[0].found_by_providers
    assert "wikipedia" in merged[0].found_by_providers
    assert "g1" in merged[0].goal_ids
    assert "g2" in merged[0].goal_ids
    assert merged[0].title == "Longer Detailed Title 1"


def test_candidate_ranker_scoring_and_explanation():
    intent = ResearchIntent(
        original_query="baricitinib alopecia clinical trials",
        normalized_query="baricitinib alopecia clinical trials",
        entities=[Entity(name="baricitinib", entity_type="CHEMICAL")],
    )

    high_cand = SourceCandidate(
        url="https://europepmc.org/article/PMC9346513",
        canonical_url="https://europepmc.org/article/PMC9346513",
        title="Efficacy of Baricitinib in Patients with Severe Alopecia Areata",
        snippet="Randomized double-blind clinical trials phase 3 trial results",
        provider="europe_pmc",
        source_type="PRIMARY_RESEARCH",
    )

    low_cand = SourceCandidate(
        url="https://random-blog.com/post",
        canonical_url="https://random-blog.com/post",
        title="My daily routine and thoughts",
        snippet="Unrelated discussion about life",
        provider="web_search",
        source_type="BLOG",
    )

    ranked = candidate_ranker.rank_pool([low_cand, high_cand], intent)
    assert len(ranked) == 2
    assert ranked[0].candidate.url == high_cand.url
    assert ranked[0].final_score > ranked[1].final_score
    assert "authority" in ranked[0].score_breakdown
    assert "lexical" in ranked[0].score_breakdown
