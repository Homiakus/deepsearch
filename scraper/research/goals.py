"""Research Goal Graph and Subgoal Models (DS-SI05, DS-SI06)."""

import uuid
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GoalStatus(str, Enum):
    UNEXPLORED = "UNEXPLORED"
    IN_PROGRESS = "IN_PROGRESS"
    COVERED = "COVERED"
    CONFLICT = "CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ResearchGoal(BaseModel):
    id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:8]}")
    question: str
    importance: float = 1.0  # 0.0 to 1.0
    dependencies: List[str] = Field(default_factory=list)
    required_evidence_types: List[str] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.UNEXPLORED
    coverage: float = 0.0  # 0.0 to 1.0
    unresolved_conflicts: List[str] = Field(default_factory=list)
    independent_sources_count: int = 0
    assigned_queries: List[str] = Field(default_factory=list)


class ResearchGoalGraph(BaseModel):
    root_goal_id: Optional[str] = None
    goals: Dict[str, ResearchGoal] = Field(default_factory=dict)

    def add_goal(self, goal: ResearchGoal, is_root: bool = False) -> ResearchGoal:
        self.goals[goal.id] = goal
        if is_root or self.root_goal_id is None:
            self.root_goal_id = goal.id
        return goal

    def get_uncovered_goals(self, coverage_threshold: float = 0.8) -> List[ResearchGoal]:
        """Returns goals that are below the target coverage threshold."""
        return [g for g in self.goals.values() if g.coverage < coverage_threshold]

    def update_coverage(self, goal_id: str, coverage: float, source_count: int = 0):
        if goal_id in self.goals:
            g = self.goals[goal_id]
            g.coverage = min(1.0, max(0.0, coverage))
            g.independent_sources_count = max(g.independent_sources_count, source_count)
            if g.coverage >= 0.8:
                g.status = GoalStatus.COVERED
            elif g.coverage > 0.0:
                g.status = GoalStatus.IN_PROGRESS

    def total_progress(self) -> float:
        if not self.goals:
            return 0.0
        return sum(g.coverage * g.importance for g in self.goals.values()) / sum(g.importance for g in self.goals.values())
