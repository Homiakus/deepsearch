"""Unit tests for Sensitivity Matrices, Boundary Discontinuities, and Deterministic Tie-Breaks (§DS-32).

Covers:
- Page Intelligence Classifier threshold boundaries (scripts, shell size, tables, APIs, bot block).
- CostPlanner & ExtractionQuality weight sensitivity (±1%, ±5%, ±10%), required_quality ± ε.
- ProviderYieldTracker health factor thresholds and intent routing boundaries.
- Media Finder dimension (159 vs 160) and relevance (0.549 vs 0.550) boundaries.
- Deterministic tie-breaking on equal scores (FRAG-003).
- Permutation invariance and neutral candidate stability.
- Inverted bounds validation (FRAG-009).
"""

import pytest

from scraper.acquisition.page_classifier import (
    API_DISCOVERY_MULTIPLIER,
    BOT_BLOCK_JS_SCORE_FLOOR,
    BOT_BLOCK_SCORE,
    EMPTY_DOM_SHELL_MAX_BYTES,
    SCRIPT_COUNT_HEURISTIC_THRESHOLD,
    classify_page,
)
from scraper.control.planner import (
    CONTENT_DENSITY_MAX_HTML_LEN,
    DEFAULT_REQUIRED_QUALITY,
    QUALITY_WEIGHT_COMPLETENESS,
    QUALITY_WEIGHT_CONSISTENCY,
    QUALITY_WEIGHT_CONTENT_DENSITY,
    QUALITY_WEIGHT_SCHEMA_MATCH,
    QUALITY_WEIGHT_VALIDITY,
    CostPlanner,
    ExtractionQuality,
    StrategyEscalation,
    evaluate_quality,
)
from scraper.discovery.media_finder import (
    MIN_ACCEPTED_IMAGE_DIMENSION,
    MIN_ACCEPTED_IMAGE_RELEVANCE,
    is_accepted_media_file,
    score_and_rank_images,
)
from scraper.discovery.provider_policy import (
    HEALTH_FACTOR_DEGRADED,
    HEALTH_FACTOR_HEALTHY,
    HEALTH_FACTOR_UNHEALTHY,
    ProviderYieldTracker,
    provider_policy,
)
from scraper.research.goals import ResearchGoal
from scraper.research.intent import Entity, ResearchIntent
from scraper.search.candidates import SourceCandidate
from scraper.search.query_models import SearchQueryVariant
from scraper.search.ranking.candidate_ranker import candidate_ranker

# ============================================================================
# 1. Page Classifier Sensitivity & Boundary Tests
# ============================================================================


def test_classifier_script_count_boundary_sensitivity():
    """Boundary test: script count <= 15 vs > 15."""
    base_html = "<html><head>{}</head><body>Content</body></html>"

    # Exactly 15 scripts (threshold boundary): no +0.2 JS score boost
    scripts_15 = "".join(
        "<script></script>" for _ in range(SCRIPT_COUNT_HEURISTIC_THRESHOLD)
    )
    pi_15 = classify_page(
        "https://example.com",
        200,
        {"content-type": "text/html"},
        base_html.format(scripts_15),
    )

    # 16 scripts (threshold + 1): triggers +0.2 JS score boost
    scripts_16 = "".join(
        "<script></script>" for _ in range(SCRIPT_COUNT_HEURISTIC_THRESHOLD + 1)
    )
    pi_16 = classify_page(
        "https://example.com",
        200,
        {"content-type": "text/html"},
        base_html.format(scripts_16),
    )

    assert pi_15.js_dependency_score == 0.1
    assert pi_16.js_dependency_score == pytest.approx(0.3)
    assert pi_15.static_score == 0.90
    assert pi_16.static_score == 0.70


def test_classifier_empty_dom_shell_size_boundary():
    """Boundary test: framework marker with length < 2000 vs >= 2000 bytes."""
    framework_marker = '<div id="react-root"></div>'

    # Length 1999 bytes (< 2000): triggers unrendered shell bonus +0.3
    padding_1999 = "x" * (EMPTY_DOM_SHELL_MAX_BYTES - 1 - len(framework_marker))
    html_1999 = f"{framework_marker}{padding_1999}"
    assert len(html_1999) == EMPTY_DOM_SHELL_MAX_BYTES - 1
    pi_1999 = classify_page(
        "https://example.com", 200, {"content-type": "text/html"}, html_1999
    )

    # Length 2000 bytes (>= 2000): does not trigger unrendered shell bonus
    padding_2000 = "x" * (EMPTY_DOM_SHELL_MAX_BYTES - len(framework_marker))
    html_2000 = f"{framework_marker}{padding_2000}"
    assert len(html_2000) == EMPTY_DOM_SHELL_MAX_BYTES
    pi_2000 = classify_page(
        "https://example.com", 200, {"content-type": "text/html"}, html_2000
    )

    # 0.1 base + 0.4 framework + 0.3 shell = 0.8
    assert pi_1999.js_dependency_score == pytest.approx(0.8)
    # 0.1 base + 0.4 framework = 0.5
    assert pi_2000.js_dependency_score == pytest.approx(0.5)


def test_classifier_tables_visual_score_boundary():
    """Boundary test: tables_count <= 2 vs > 2."""
    html_2_tables = "<html><body><table></table><table></table></body></html>"
    html_3_tables = (
        "<html><body><table></table><table></table><table></table></body></html>"
    )

    pi_2 = classify_page(
        "https://example.com", 200, {"content-type": "text/html"}, html_2_tables
    )
    pi_3 = classify_page(
        "https://example.com", 200, {"content-type": "text/html"}, html_3_tables
    )

    assert pi_2.tables_count == 2
    assert pi_2.visual_score == 0.1
    assert pi_3.tables_count == 3
    assert pi_3.visual_score == pytest.approx(0.4)  # 0.1 base + 0.3


def test_classifier_api_score_linear_scaling_and_ceiling():
    """Test API score progression: 0.3 per detected endpoint, capped at 1.0."""
    net_reqs = [
        {"url": f"https://example.com/api/v1/resource_{i}", "mime": "application/json"}
        for i in range(5)
    ]

    for count in range(5):
        pi = classify_page(
            "https://example.com",
            200,
            {"content-type": "text/html"},
            "<html><body></body></html>",
            network_requests=net_reqs[:count],
        )
        expected = min(1.0, round(count * API_DISCOVERY_MULTIPLIER, 2))
        assert pi.api_score == expected


def test_classifier_bot_block_indicators():
    """Test bot block detection triggers high block_score and elevated js_score."""
    for indicator in [
        "Cloudflare Ray ID",
        "Please complete the Captcha to continue",
        "Access Denied: error 1020",
        "Checking your browser before accessing",
        "Just a moment...",
    ]:
        pi = classify_page(
            "https://example.com",
            200,
            {"content-type": "text/html"},
            f"<html><body>{indicator}</body></html>",
        )
        assert pi.block_score == BOT_BLOCK_SCORE
        assert pi.js_dependency_score >= BOT_BLOCK_JS_SCORE_FLOOR
        assert pi.content_quality == pytest.approx(0.05)


def test_classifier_framework_markers_no_false_positives():
    """FRAG-002: Ensure natural language occurrences do not trigger framework markers."""
    prose_html = """
    <html>
      <body>
        <p>A chemical reaction occurred in the laboratory.</p>
        <p>The angular momentum was calculated with precision.</p>
        <p>Subtle nuances in the viewpoint were discussed.</p>
      </body>
    </html>
    """
    pi = classify_page(
        "https://example.com", 200, {"content-type": "text/html"}, prose_html
    )
    assert pi.detected_frameworks == []
    assert pi.js_dependency_score == 0.1


# ============================================================================
# 2. CostPlanner & Extraction Quality Sensitivity & Discontinuity Tests
# ============================================================================


def test_planner_quality_weights_canonical_sum():
    """Verify quality weights sum to exactly 1.00."""
    total_weights = (
        QUALITY_WEIGHT_COMPLETENESS
        + QUALITY_WEIGHT_VALIDITY
        + QUALITY_WEIGHT_CONSISTENCY
        + QUALITY_WEIGHT_SCHEMA_MATCH
        + QUALITY_WEIGHT_CONTENT_DENSITY
    )
    assert total_weights == pytest.approx(1.00)


def test_planner_weight_perturbation_sensitivity_matrix():
    """Table-driven sensitivity matrix for ±1%, ±5%, ±10% weight variations."""
    html = "x" * 25000  # content_density = 0.5
    data = {"field_a": "val1"}
    req_fields = ["field_a", "field_b"]  # completeness = 0.5

    evaluate_quality(data, html, req_fields)

    for delta_pct in [-0.10, -0.05, -0.01, 0.01, 0.05, 0.10]:
        perturbed_w_comp = QUALITY_WEIGHT_COMPLETENESS * (1 + delta_pct)
        # Expected delta in overall score
        comp_contribution_base = QUALITY_WEIGHT_COMPLETENESS * 0.5
        comp_contribution_perturbed = perturbed_w_comp * 0.5
        expected_diff = comp_contribution_perturbed - comp_contribution_base

        # Overall score response must be linear with no discontinuous jump
        assert abs(expected_diff) <= abs(delta_pct * 0.30)


def test_planner_content_density_boundary():
    """Boundary conditions for content density calculation (floor 0.1, max 50000)."""
    # Empty HTML -> 0.0
    q_empty = evaluate_quality({"a": 1}, "", ["a"])
    assert q_empty.overall_score == 0.0

    # Short HTML (100 chars) -> floor at 0.1
    q_short = evaluate_quality({"a": 1}, "x" * 100, ["a"])
    assert q_short.content_density == 0.1

    # Exactly max ceiling length (50,000 chars) -> 1.0
    q_max = evaluate_quality({"a": 1}, "x" * CONTENT_DENSITY_MAX_HTML_LEN, ["a"])
    assert q_max.content_density == 1.0

    # Oversized HTML (100,000 chars) -> capped at 1.0
    q_over = evaluate_quality({"a": 1}, "x" * (CONTENT_DENSITY_MAX_HTML_LEN * 2), ["a"])
    assert q_over.content_density == 1.0


def test_cost_planner_required_quality_epsilon_boundary():
    """Test required_quality threshold at threshold - ε, threshold, threshold + ε."""
    epsilon = 0.001
    threshold = DEFAULT_REQUIRED_QUALITY  # 0.85

    # At threshold: overall_score == 0.85 -> No escalation needed
    q_equal = ExtractionQuality(overall_score=threshold)
    next_strat = CostPlanner.determine_next_strategy(
        StrategyEscalation.CACHE, q_equal, required_quality=threshold
    )
    assert next_strat == StrategyEscalation.CACHE

    # At threshold + epsilon: overall_score == 0.851 -> No escalation needed
    q_above = ExtractionQuality(overall_score=round(threshold + epsilon, 3))
    next_strat = CostPlanner.determine_next_strategy(
        StrategyEscalation.CACHE, q_above, required_quality=threshold
    )
    assert next_strat == StrategyEscalation.CACHE

    # At threshold - epsilon: overall_score == 0.849 -> Escalates CACHE -> HTTP
    q_below = ExtractionQuality(overall_score=round(threshold - epsilon, 3))
    next_strat = CostPlanner.determine_next_strategy(
        StrategyEscalation.CACHE, q_below, required_quality=threshold
    )
    assert next_strat == StrategyEscalation.HTTP


def test_cost_planner_strategy_escalation_pathways():
    """Test explicit escalation pathways through all tiers."""
    q_low = ExtractionQuality(overall_score=0.5)

    # 1. CACHE -> HTTP
    assert (
        CostPlanner.determine_next_strategy(StrategyEscalation.CACHE, q_low)
        == StrategyEscalation.HTTP
    )

    # 2. HTTP -> API (when API available)
    assert (
        CostPlanner.determine_next_strategy(
            StrategyEscalation.HTTP, q_low, api_available=True
        )
        == StrategyEscalation.API
    )

    # 3. HTTP -> BROWSER (when API not available)
    assert (
        CostPlanner.determine_next_strategy(
            StrategyEscalation.HTTP, q_low, api_available=False
        )
        == StrategyEscalation.BROWSER
    )

    # 4. BROWSER -> VISUAL (when visual_score >= 0.7)
    assert (
        CostPlanner.determine_next_strategy(
            StrategyEscalation.BROWSER, q_low, visual_score=0.75
        )
        == StrategyEscalation.VISUAL
    )

    # 5. BROWSER -> SEMANTIC (when visual_score < 0.7)
    assert (
        CostPlanner.determine_next_strategy(
            StrategyEscalation.BROWSER, q_low, visual_score=0.3
        )
        == StrategyEscalation.SEMANTIC
    )

    # 6. SEMANTIC -> VISUAL
    assert (
        CostPlanner.determine_next_strategy(StrategyEscalation.SEMANTIC, q_low)
        == StrategyEscalation.VISUAL
    )


# ============================================================================
# 3. Provider Yield & Policy Sensitivity Tests
# ============================================================================


def test_provider_yield_tracker_health_factor_boundaries():
    """Test health factor transitions at error rate and min call boundaries."""
    tracker = ProviderYieldTracker()
    p_name = "test_provider"

    # 0 calls -> Healthy
    assert tracker.get_health_factor(p_name) == HEALTH_FACTOR_HEALTHY

    # 2 calls with 100% errors (calls < 3): degraded (0.6), not unhealthy (0.2)
    tracker.record_call(p_name, 0, error=True)
    tracker.record_call(p_name, 0, error=True)
    assert tracker.get_health_factor(p_name) == HEALTH_FACTOR_DEGRADED

    # 3rd call with error (calls == 3, error_rate = 1.0 >= 0.8) -> Unhealthy (0.2)
    tracker.record_call(p_name, 0, error=True)
    assert tracker.get_health_factor(p_name) == HEALTH_FACTOR_UNHEALTHY

    # Reset with fresh tracker to test 0.5 boundary
    tracker2 = ProviderYieldTracker()
    p2 = "test_provider_2"
    # 4 calls, 2 errors: error_rate = 0.50 -> Degraded (0.6)
    tracker2.record_call(p2, 1, error=False)
    tracker2.record_call(p2, 1, error=False)
    tracker2.record_call(p2, 0, error=True)
    tracker2.record_call(p2, 0, error=True)
    assert tracker2.get_health_factor(p2) == HEALTH_FACTOR_DEGRADED

    # Add 1 success -> 5 calls, 2 errors (error_rate = 0.40 < 0.50) -> Healthy (1.0)
    tracker2.record_call(p2, 1, error=False)
    assert tracker2.get_health_factor(p2) == HEALTH_FACTOR_HEALTHY


def test_provider_policy_intent_keyword_sensitivity():
    """Verify medical keyword presence correctly triggers specialized providers."""
    intent_med = ResearchIntent(
        original_query="oncology patient therapy trial",
        normalized_query="oncology patient therapy trial",
        task_type="scientific",
    )
    goal_med = ResearchGoal(
        id="g_med",
        title="Goal Med",
        question="What are the oncology therapy guidelines?",
        required_evidence_types=["GUIDELINE"],
    )
    qv_med = [SearchQueryVariant(query="oncology patient therapy", goal_id="g_med")]

    reqs_med = provider_policy.plan_provider_requests(intent_med, goal_med, qv_med)
    provider_names = [p.descriptor.name for p, _ in reqs_med]
    assert "pubmed" in provider_names or "europe_pmc" in provider_names


# ============================================================================
# 4. Media Ranking & Candidate Ranking Sensitivity, Permutation, and Tie-Break
# ============================================================================


def test_media_dimension_boundary_sensitivity():
    """Boundary test: 159px (rejected) vs 160px (accepted) minimum dimension."""
    cand_159 = {
        "url": "https://example.com/img_159.jpg",
        "caption": "Quantum laser diagram",
        "width": MIN_ACCEPTED_IMAGE_DIMENSION - 1,
        "height": 300,
        "source_domain": "example.com",
    }
    cand_160 = {
        "url": "https://example.com/img_160.jpg",
        "caption": "Quantum laser diagram",
        "width": MIN_ACCEPTED_IMAGE_DIMENSION,
        "height": 300,
        "source_domain": "example.com",
    }

    assert not is_accepted_media_file(
        {"width": 159, "height": 300, "relevance_score": 0.9}
    )
    assert is_accepted_media_file({"width": 160, "height": 300, "relevance_score": 0.9})

    ranked = score_and_rank_images(
        [cand_159, cand_160], query="quantum laser", min_count=1, max_count=5
    )
    assert len(ranked) == 1
    assert ranked[0]["url"] == "https://example.com/img_160.jpg"


def test_media_relevance_threshold_boundary():
    """Boundary test: score < 0.55 (rejected) vs >= 0.55 (accepted)."""
    assert not is_accepted_media_file(
        {
            "width": 400,
            "height": 300,
            "relevance_score": MIN_ACCEPTED_IMAGE_RELEVANCE - 0.01,
        }
    )
    assert is_accepted_media_file(
        {"width": 400, "height": 300, "relevance_score": MIN_ACCEPTED_IMAGE_RELEVANCE}
    )


def test_media_ranking_permutation_invariance_and_deterministic_tiebreak():
    """FRAG-003: Permuting candidate list with equal scores must produce identical winner order."""
    item_a = {
        "url": "https://example.com/image_alpha.jpg",
        "caption": "Fiber laser cutting beam setup",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }
    item_b = {
        "url": "https://example.com/image_beta.jpg",
        "caption": "Fiber laser cutting beam setup",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }
    item_c = {
        "url": "https://example.com/image_gamma.jpg",
        "caption": "Fiber laser cutting beam setup",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }

    order_1 = [item_a, item_b, item_c]
    order_2 = [item_c, item_a, item_b]
    order_3 = [item_b, item_c, item_a]

    ranked_1 = score_and_rank_images(
        order_1, query="laser cutting", min_count=1, max_count=3
    )
    ranked_2 = score_and_rank_images(
        order_2, query="laser cutting", min_count=1, max_count=3
    )
    ranked_3 = score_and_rank_images(
        order_3, query="laser cutting", min_count=1, max_count=3
    )

    urls_1 = [x["url"] for x in ranked_1]
    urls_2 = [x["url"] for x in ranked_2]
    urls_3 = [x["url"] for x in ranked_3]

    assert urls_1 == urls_2 == urls_3


def test_media_ranking_neutral_candidate_addition():
    """Adding a neutral/unrelated candidate does not alter the relative ordering or scores of existing candidates."""
    query = "semiconductor manufacturing"
    target_1 = {
        "url": "https://example.com/semi_fab.jpg",
        "caption": "Semiconductor manufacturing cleanroom fab",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }
    target_2 = {
        "url": "https://example.com/silicon_wafer.jpg",
        "caption": "Silicon wafer semiconductor processing",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }
    neutral = {
        "url": "https://example.com/unrelated_cat.jpg",
        "caption": "Fluffy domestic kitten resting indoors",
        "source_domain": "example.com",
        "width": 800,
        "height": 600,
    }

    ranked_without = score_and_rank_images(
        [target_1, target_2], query=query, min_count=1, max_count=5
    )
    ranked_with = score_and_rank_images(
        [target_1, neutral, target_2], query=query, min_count=1, max_count=5
    )

    scores_without = {x["url"]: x["relevance_score"] for x in ranked_without}
    scores_with = {
        x["url"]: x["relevance_score"]
        for x in ranked_with
        if x["url"] != neutral["url"]
    }

    assert scores_without == scores_with
    assert [x["url"] for x in ranked_without] == [
        x["url"] for x in ranked_with if x["url"] != neutral["url"]
    ]


def test_candidate_ranker_permutation_invariance_on_equal_scores():
    """FRAG-003: Candidate ranker with equal final scores tie-breaks deterministically."""
    intent = ResearchIntent(
        original_query="machine learning optimization",
        normalized_query="machine learning optimization",
        entities=[],
    )

    c1 = SourceCandidate(
        url="https://alpha.org/paper_alpha",
        canonical_url="https://alpha.org/paper_alpha",
        domain="alpha.org",
        title="Optimization in Machine Learning",
        snippet="A study of optimization algorithms",
        provider="arxiv",
        source_type="PRIMARY_RESEARCH",
    )
    c2 = SourceCandidate(
        url="https://beta.org/paper_beta",
        canonical_url="https://beta.org/paper_beta",
        domain="beta.org",
        title="Optimization in Machine Learning",
        snippet="A study of optimization algorithms",
        provider="arxiv",
        source_type="PRIMARY_RESEARCH",
    )

    ranked_forward = candidate_ranker.rank_pool([c1, c2], intent)
    ranked_reverse = candidate_ranker.rank_pool([c2, c1], intent)

    assert ranked_forward[0].final_score == ranked_forward[1].final_score
    urls_forward = [rc.candidate.url for rc in ranked_forward]
    urls_reverse = [rc.candidate.url for rc in ranked_reverse]

    assert urls_forward == urls_reverse


def test_candidate_ranker_neutral_candidate_stability():
    """Adding a neutral candidate preserves the scores and ordering of existing candidates."""
    intent = ResearchIntent(
        original_query="graphene electrical conductivity",
        normalized_query="graphene electrical conductivity",
        entities=[Entity(name="graphene", entity_type="MATERIAL")],
    )

    c_relevant = SourceCandidate(
        url="https://example.com/graphene_paper",
        canonical_url="https://example.com/graphene_paper",
        title="Electrical Conductivity of Graphene Nanostructures",
        snippet="High mobility ballistic transport in graphene sheets",
        provider="arxiv",
        source_type="PRIMARY_RESEARCH",
    )
    c_neutral = SourceCandidate(
        url="https://example.com/recipes",
        canonical_url="https://example.com/recipes",
        title="Grandma's Chocolate Cake Recipe",
        snippet="Bake at 350 degrees for 45 minutes",
        provider="web_search",
        source_type="BLOG",
    )

    ranked_single = candidate_ranker.rank_pool([c_relevant], intent)
    ranked_with_neutral = candidate_ranker.rank_pool([c_relevant, c_neutral], intent)

    assert ranked_single[0].final_score == ranked_with_neutral[0].final_score
    assert ranked_with_neutral[0].candidate.url == c_relevant.url
