"""Cost-Aware Planner and Extraction Quality Evaluator (§51, §52)."""

from typing import Any

from pydantic import BaseModel

from scraper.config import settings

# Extraction Quality Calibration Weights (§52, DS-32)
# Sum of canonical weights = 1.00
QUALITY_WEIGHT_COMPLETENESS = 0.30  # Primary factor: ratio of required schema fields
QUALITY_WEIGHT_VALIDITY = 0.20  # Data types and schema validity
QUALITY_WEIGHT_CONSISTENCY = 0.20  # Cross-field logical consistency
QUALITY_WEIGHT_SCHEMA_MATCH = 0.15  # Structural schema conformance
QUALITY_WEIGHT_CONTENT_DENSITY = 0.15  # Text vs DOM size ratio
CONTENT_DENSITY_MAX_HTML_LEN = 50000  # Normalization ceiling for DOM size
DEFAULT_REQUIRED_QUALITY = 0.85  # Default threshold for triggering escalation


class ExtractionQuality(BaseModel):
    completeness: float = 1.0  # Ratio of required schema fields populated
    validity: float = 1.0  # Data type / format validity score
    consistency: float = 1.0  # Cross-field logical consistency
    schema_match: float = 1.0  # Schema validation match score
    content_density: float = 1.0  # Useful text / total DOM size ratio
    overall_score: float = 1.0  # Weighted overall quality score


class StrategyEscalation(str):
    CACHE = "L0_CACHE"
    HTTP = "L1_HTTP"
    API = "L2_API"
    BROWSER = "L3_BROWSER"
    SEMANTIC = "L4_SEMANTIC"
    VISUAL = "L5_VISUAL"


class CostPlanner:
    """Calculates acquisition cost weights and determines escalation strategy."""

    COST_MAP = {
        StrategyEscalation.CACHE: settings.cost.cache,
        StrategyEscalation.HTTP: settings.cost.http,
        StrategyEscalation.API: settings.cost.api,
        StrategyEscalation.BROWSER: settings.cost.browser,
        StrategyEscalation.SEMANTIC: settings.cost.llm,
        StrategyEscalation.VISUAL: settings.cost.visual_vlm,
    }

    @classmethod
    def get_cost(cls, strategy: str) -> float:
        return cls.COST_MAP.get(strategy, 1.0)

    @classmethod
    def determine_next_strategy(
        self,
        current_strategy: str,
        quality: ExtractionQuality,
        required_quality: float = 0.85,
        js_score: float = 0.0,
        api_available: bool = False,
        visual_score: float = 0.0,
    ) -> str:
        """Determines next acquisition strategy according to escalation rules (§52)."""
        if quality.overall_score >= required_quality:
            return current_strategy

        # Escalation sequence: CACHE -> HTTP -> API -> BROWSER -> SEMANTIC -> VISUAL
        if current_strategy == StrategyEscalation.CACHE:
            return StrategyEscalation.HTTP

        if current_strategy == StrategyEscalation.HTTP:
            if api_available and settings.adaptive.api_preference:
                return StrategyEscalation.API
            if js_score >= settings.adaptive.browser_threshold:
                return StrategyEscalation.BROWSER
            return StrategyEscalation.BROWSER

        if current_strategy in (StrategyEscalation.API, StrategyEscalation.BROWSER):
            if visual_score >= settings.adaptive.visual_threshold:
                return StrategyEscalation.VISUAL
            return StrategyEscalation.SEMANTIC

        if current_strategy == StrategyEscalation.SEMANTIC:
            return StrategyEscalation.VISUAL

        return current_strategy


def evaluate_quality(
    extracted_data: dict[str, Any] | None,
    raw_html: str,
    required_fields: list | None = None,
) -> ExtractionQuality:
    """Evaluates quality metrics for extracted page content (§52)."""
    if not raw_html:
        return ExtractionQuality(
            completeness=0.0,
            validity=0.0,
            consistency=0.0,
            schema_match=0.0,
            content_density=0.0,
            overall_score=0.0,
        )

    # 1. Content density (text length / HTML length)
    text_len = len(raw_html)
    content_density = (
        min(1.0, max(0.1, text_len / CONTENT_DENSITY_MAX_HTML_LEN))
        if text_len > 0
        else 0.0
    )

    # 2. Completeness
    completeness = 1.0
    if extracted_data and required_fields:
        found = sum(1 for f in required_fields if extracted_data.get(f) is not None)
        completeness = found / len(required_fields)

    validity = 1.0 if extracted_data else 0.5
    schema_match = completeness
    consistency = 1.0

    overall = (
        QUALITY_WEIGHT_COMPLETENESS * completeness
        + QUALITY_WEIGHT_VALIDITY * validity
        + QUALITY_WEIGHT_CONSISTENCY * consistency
        + QUALITY_WEIGHT_SCHEMA_MATCH * schema_match
        + QUALITY_WEIGHT_CONTENT_DENSITY * content_density
    )

    return ExtractionQuality(
        completeness=round(completeness, 3),
        validity=round(validity, 3),
        consistency=round(consistency, 3),
        schema_match=round(schema_match, 3),
        content_density=round(content_density, 3),
        overall_score=round(overall, 3),
    )
