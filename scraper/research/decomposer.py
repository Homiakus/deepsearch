"""Research Goal Decomposer (DS-SI05, DS-SI06).

Breaks down complex queries into cohesive research goals with targeted evidence requirements.
"""

import re
from scraper.research.intent import ResearchIntent
from scraper.research.goals import ResearchGoal, ResearchGoalGraph


def decompose_intent(intent: ResearchIntent) -> ResearchGoalGraph:
    """Decomposes ResearchIntent into a ResearchGoalGraph."""
    graph = ResearchGoalGraph()
    q = intent.normalized_query
    q_lower = q.lower()

    # Determine domain evidence requirements
    is_medical = (
        intent.task_type == "medical"
        or any(e.entity_type in ("DISEASE", "CHEMICAL") for e in intent.entities)
        or any(
            k in q_lower
            for k in [
                "клиническ",
                "лечени",
                "medicin",
                "drug",
                "trial",
                "efficacy",
                "therapy",
            ]
        )
    )
    is_software = (
        intent.task_type in ("technical", "code")
        or any(e.entity_type in ("SOFTWARE_API", "PRODUCT") for e in intent.entities)
        or any(
            k in q_lower
            for k in ["api", "function", "library", "sdk", "qdrant", "rust", "python"]
        )
    )
    is_comparative = (
        " vs " in q_lower
        or " versus " in q_lower
        or "сравнение" in q_lower
        or "против" in q_lower
    )
    is_contradiction = any(
        k in q_lower
        for k in [
            "controversy",
            "dispute",
            "противореч",
            "побочные эффекты",
            "side effect",
            "risk",
            "criticism",
        ]
    )

    # Base evidence preference
    if is_medical:
        base_reqs = [
            "GUIDELINE",
            "REGULATOR",
            "SYSTEMATIC_REVIEW",
            "META_ANALYSIS",
            "PRIMARY_RESEARCH",
        ]
    elif is_software:
        base_reqs = ["OFFICIAL_DOC", "SOURCE_CODE", "STANDARD", "ISSUE_TRACKER"]
    else:
        base_reqs = ["OFFICIAL_DOC", "PRIMARY_RESEARCH", "WIKI"]

    # 1. Root / Primary Goal
    root_goal = ResearchGoal(
        question=f"Answer primary research question: {q}",
        importance=1.0,
        required_evidence_types=base_reqs,
    )
    graph.add_goal(root_goal, is_root=True)

    # 2. Comparative Query Decomposition
    if is_comparative:
        parts = re.split(r"\b(?:vs|versus|против|и)\b", q, flags=re.IGNORECASE)
        if len(parts) >= 2:
            item_a = parts[0].strip()
            item_b = parts[1].strip()
            goal_a = ResearchGoal(
                question=f"Investigate characteristics and properties of {item_a}",
                importance=0.8,
                dependencies=[root_goal.id],
                required_evidence_types=base_reqs,
            )
            goal_b = ResearchGoal(
                question=f"Investigate characteristics and properties of {item_b}",
                importance=0.8,
                dependencies=[root_goal.id],
                required_evidence_types=base_reqs,
            )
            graph.add_goal(goal_a)
            graph.add_goal(goal_b)

    # 3. Contradiction / Dispute Decomposition
    if is_contradiction:
        crit_goal = ResearchGoal(
            question=f"Investigate criticisms, adverse effects, and counter-evidence for: {q}",
            importance=0.9,
            dependencies=[root_goal.id],
            required_evidence_types=[
                "PRIMARY_RESEARCH",
                "SYSTEMATIC_REVIEW",
                "ISSUE_TRACKER",
                "FORUM",
            ],
        )
        graph.add_goal(crit_goal)

    # 4. Standards / Technical Identification Subgoal
    standards = [e for e in intent.entities if e.entity_type == "STANDARD"]
    if standards:
        for s in standards:
            std_goal = ResearchGoal(
                question=f"Retrieve official normative standard specifications for {s.name}",
                importance=0.9,
                dependencies=[root_goal.id],
                required_evidence_types=["STANDARD", "OFFICIAL_DOC"],
            )
            graph.add_goal(std_goal)

    return graph
