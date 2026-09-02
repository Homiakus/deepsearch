"""Maximal Marginal Relevance (MMR) & Domain Diversity Selector (DS-SI45, DS-SI46)."""

import re

from scraper.search.rerank.base import RerankedPassage


class DiversitySelector:
    """Selects top passages balancing high relevance and source domain / content diversity."""

    def __init__(self, lambda_param: float = 0.7, max_per_domain: int = 2):
        self.lambda_param = lambda_param  # 0 = max diversity, 1 = max relevance
        self.max_per_domain = max_per_domain

    def select_diverse(
        self, candidates: list[RerankedPassage], top_k: int = 10
    ) -> list[RerankedPassage]:
        if len(candidates) <= top_k:
            return candidates

        selected: list[RerankedPassage] = []
        domain_counts: dict[str, int] = {}
        remaining = list(candidates)

        while remaining and len(selected) < top_k:
            best_idx = -1
            best_mmr_score = -999.0

            for idx, cand in enumerate(remaining):
                dom = (
                    cand.fused_result.hit.url.split("/")[2]
                    if "//" in cand.fused_result.hit.url
                    else "unknown"
                )
                if domain_counts.get(dom, 0) >= self.max_per_domain:
                    # Domain cap penalty
                    dom_penalty = 0.3
                else:
                    dom_penalty = 0.0

                # Max similarity to already selected
                max_sim_to_selected = 0.0
                cand_tokens = set(
                    re.findall(r"\w+", cand.fused_result.hit.text.lower())
                )
                for s in selected:
                    s_tokens = set(re.findall(r"\w+", s.fused_result.hit.text.lower()))
                    jaccard = len(cand_tokens.intersection(s_tokens)) / max(
                        len(cand_tokens.union(s_tokens)), 1
                    )
                    max_sim_to_selected = max(max_sim_to_selected, jaccard)

                # MMR score = lambda * Relevance - (1 - lambda) * MaxSim - DomainPenalty
                mmr_score = (
                    (self.lambda_param * cand.rerank_score)
                    - ((1.0 - self.lambda_param) * max_sim_to_selected)
                    - dom_penalty
                )

                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx

            if best_idx >= 0:
                chosen = remaining.pop(best_idx)
                selected.append(chosen)
                dom = (
                    chosen.fused_result.hit.url.split("/")[2]
                    if "//" in chosen.fused_result.hit.url
                    else "unknown"
                )
                domain_counts[dom] = domain_counts.get(dom, 0) + 1
            else:
                break

        return selected


diversity_selector = DiversitySelector()
