"""Goal Coverage & Evidence Sufficiency Analyzer (DS-SI55, DS-SI56)."""

from typing import Dict, List
from pydantic import BaseModel, Field
from scraper.research.goals import ResearchGoal, ResearchGoalGraph, GoalStatus
from scraper.evidence.store import EvidenceStore


class GoalCoverageReport(BaseModel):
    goal_id: str
    question: str
    coverage_score: float
    status: GoalStatus
    claims_count: int
    independent_sources_count: int
    missing_evidence_types: List[str] = Field(default_factory=list)
    is_sufficient: bool = False


class OverallCoverageAssessment(BaseModel):
    overall_progress: float
    is_sufficient: bool
    goal_reports: List[GoalCoverageReport] = Field(default_factory=list)
    unresolved_contradictions_count: int = 0


class GoalCoverageAnalyzer:
    """Analyzes goal coverage and assesses whether evidence sufficiency criteria are met."""

    @staticmethod
    def analyze(goal_graph: ResearchGoalGraph, store: EvidenceStore) -> OverallCoverageAssessment:
        reports: List[GoalCoverageReport] = []
        contradictions = store.get_contradictions()

        for goal in goal_graph.goals.values():
            claims = store.get_claims_for_goal(goal.id)
            total_claims = len(claims)

            # Count unique source domains supporting these claims
            unique_domains = set()
            found_source_types = set()
            for c in claims:
                for eid in c.supporting_evidence_ids:
                    if eid in store.graph.evidence:
                        ev = store.graph.evidence[eid]
                        unique_domains.add(ev.domain)
                        found_source_types.add(ev.source_type)

            # Coverage calculation
            indep_count = len(unique_domains)
            req_types = set(goal.required_evidence_types)
            missing = list(req_types - found_source_types)

            # Score formula: 50% claims presence, 30% independent sources, 20% type coverage
            c_claims = min(1.0, total_claims / 3.0) if total_claims > 0 else 0.0
            c_sources = min(1.0, indep_count / 2.0) if indep_count > 0 else 0.0
            c_types = 1.0 - (len(missing) / max(len(req_types), 1)) if req_types else 1.0

            coverage = round(0.50 * c_claims + 0.30 * c_sources + 0.20 * c_types, 3)
            goal_graph.update_coverage(goal.id, coverage, source_count=indep_count)

            is_suff = coverage >= 0.70 and indep_count >= 1

            reports.append(
                GoalCoverageReport(
                    goal_id=goal.id,
                    question=goal.question,
                    coverage_score=coverage,
                    status=goal.status,
                    claims_count=total_claims,
                    independent_sources_count=indep_count,
                    missing_evidence_types=missing,
                    is_sufficient=is_suff,
                )
            )

        overall_prog = goal_graph.total_progress()
        all_sufficient = all(r.is_sufficient for r in reports) if reports else False

        return OverallCoverageAssessment(
            overall_progress=round(overall_prog, 3),
            is_sufficient=all_sufficient,
            goal_reports=reports,
            unresolved_contradictions_count=len(contradictions),
        )


goal_coverage_analyzer = GoalCoverageAnalyzer()
