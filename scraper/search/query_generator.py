"""Search Query Variant Generator (DS-SI07).

Generates bounded, goal-directed query formulations without exponential query explosion.
"""

from scraper.research.goals import ResearchGoal, ResearchGoalGraph
from scraper.research.intent import ResearchIntent
from scraper.search.query_models import QueryType, SearchQueryVariant


class QueryGenerator:
    """Generates typed query variants per goal with budget caps."""

    def __init__(
        self, max_queries_per_goal: int = 4, max_total_query_variants: int = 16
    ):
        self.max_queries_per_goal = max_queries_per_goal
        self.max_total_query_variants = max_total_query_variants

    def generate_variants(
        self, intent: ResearchIntent, goal_graph: ResearchGoalGraph
    ) -> list[SearchQueryVariant]:
        variants: list[SearchQueryVariant] = []
        seen_queries = set()

        for goal in goal_graph.goals.values():
            goal_variants = self._generate_for_goal(goal, intent)
            for v in goal_variants:
                q_key = (v.query.lower().strip(), v.language)
                if q_key not in seen_queries:
                    seen_queries.add(q_key)
                    variants.append(v)
                    if len(variants) >= self.max_total_query_variants:
                        return variants

        return variants

    def _generate_for_goal(
        self, goal: ResearchGoal, intent: ResearchIntent
    ) -> list[SearchQueryVariant]:
        results: list[SearchQueryVariant] = []
        clean_q = intent.normalized_query

        # 1. Canonical / Semantic Query
        results.append(
            SearchQueryVariant(
                query=clean_q,
                language="ru"
                if intent.normalized_query
                and any(ord(c) > 127 for c in intent.normalized_query[:10])
                else "en",
                goal_id=goal.id,
                query_type=QueryType.SEMANTIC,
                priority=1.0,
            )
        )

        # 2. Entity Exact Query if entities present
        if intent.entities:
            exact_tokens = [e.canonical_form or e.name for e in intent.entities[:3]]
            results.append(
                SearchQueryVariant(
                    query=" ".join(exact_tokens),
                    language="en",
                    goal_id=goal.id,
                    query_type=QueryType.ENTITY,
                    priority=0.9,
                )
            )

        # 3. Scientific Cross-Lingual Mapping (RU/ZH/ES/DE -> EN)
        if any(ord(c) > 127 for c in clean_q):
            en_query = clean_q.lower()
            translations = [
                # Biomedical & Clinical
                ("жидкостная биопсия", "liquid biopsy ctDNA circulating tumor DNA"),
                ("колоректальный рак", "colorectal cancer"),
                ("онкологи", "oncology cancer neoplasms"),
                ("иммунотерапи", "immunotherapy checkpoint inhibitors PD-1 CTLA-4"),
                ("биомаркер", "biomarker diagnostic prognostic clinical validation"),
                ("мутаци", "gene mutation variant pathogenicity CRISPR Cas9"),
                ("фармако", "pharmacokinetics pharmacodynamics drug bioavailability"),
                ("сердечн", "cardiovascular atherosclerosis myocardial infarction"),
                ("нейродеген", "neurodegenerative Alzheimer Parkinson neuroprotection"),
                ("микробиом", "microbiome gut microbiota 16S rRNA sequencing"),
                ("вакцин", "vaccine mRNA adjuvant immunogenicity efficacy"),
                # Materials, Physics & Engineering
                ("квантов", "quantum computing algorithm entanglement"),
                ("лазерн", "laser cutting assist gas nozzle parameters"),
                ("резани", "machining parameters cutting speed feed rate"),
                ("титан", "titanium alloy Ti6Al4V microstructure"),
                ("печать", "3D printing additive manufacturing SLM"),
                ("аддитивн", "additive manufacturing selective laser melting"),
                ("твердотельн", "solid state battery solid electrolyte conductivity"),
                ("аккумулятор", "lithium ion battery cathode anode degradation"),
                ("графен", "graphene 2D materials synthesis characterization"),
                (
                    "перовскит",
                    "perovskite solar cells photovoltaic efficiency stability",
                ),
                (
                    "сверхпровод",
                    "superconductivity high temperature superconductor critical current",
                ),
                ("спектроскоп", "spectroscopy FTIR Raman XRD characterization"),
                ("полупроводник", "semiconductor bandgap heterojunction transistor"),
                ("композит", "composite materials carbon fiber reinforced matrix"),
                (
                    "микроконтроллер",
                    "microcontroller embedded systems firmware ARM RISC-V",
                ),
                # Computer Science, AI & Systems
                ("нейросеть", "neural networks deep learning RAG LLM"),
                ("трансформер", "transformer attention mechanism LLM"),
                ("векторн", "vector database embeddings similarity search HNSW"),
                (
                    "обучение с подкреплением",
                    "reinforcement learning policy gradient PPO RLHF",
                ),
                (
                    "компьютерное зрение",
                    "computer vision object detection segmentation",
                ),
                ("генеративн", "generative AI diffusion models LLM"),
                ("распределенн", "distributed consensus Raft Paxos replication"),
                ("безопасност", "cybersecurity vulnerability exploit mitigation"),
                # Scholarly metadata & Standards
                (
                    "первичное исследование",
                    "randomized clinical trial systematic review meta-analysis",
                ),
                ("научная статья", "journal article peer reviewed DOI"),
                ("гост", "standard specification technical requirements"),
                ("патент", "patent claims prior art intellectual property"),
                ("сравнение", "comparative analysis benchmark performance evaluation"),
                ("мета-анализ", "meta-analysis systematic review PRISMA forest plot"),
            ]
            for ru_term, en_replacement in translations:
                if ru_term in en_query:
                    en_query = en_query.replace(ru_term, en_replacement)

            if en_query != clean_q.lower():
                results.append(
                    SearchQueryVariant(
                        query=en_query,
                        language="en",
                        goal_id=goal.id,
                        query_type=QueryType.DOMAIN_SPECIFIC,
                        priority=0.92,
                    )
                )

        # 4. Primary Scientific Source Formulation (PubMed / Semantic Scholar / OpenAlex)
        if (
            "GUIDELINE" in goal.required_evidence_types
            or "PRIMARY_RESEARCH" in goal.required_evidence_types
            or "SYSTEMATIC_REVIEW" in goal.required_evidence_types
        ):
            results.append(
                SearchQueryVariant(
                    query=f"{clean_q} (systematic review OR meta-analysis OR clinical trial OR randomized controlled)",
                    language="en",
                    goal_id=goal.id,
                    query_type=QueryType.PRIMARY_SOURCE,
                    provider_hint="semantic_scholar",
                    priority=0.88,
                )
            )

        # 5. Multi-Regional Academic Formulation (HAL / CyberLeninka / CrossRef)
        results.append(
            SearchQueryVariant(
                query=clean_q,
                language="ru" if any(ord(c) > 127 for c in clean_q) else "en",
                goal_id=goal.id,
                query_type=QueryType.DOMAIN_SPECIFIC,
                provider_hint="regional_academic",
                priority=0.80,
            )
        )

        return results[: self.max_queries_per_goal]

    def generate_followup_variants(
        self,
        seed_terms: list[str],
        original_query: str,
        goal_id: str = "goal_followup",
    ) -> list[SearchQueryVariant]:
        """Generates targeted query variants from newly discovered high-relevance terms during deep crawling."""
        if not seed_terms:
            return []
        variants = []
        for term in seed_terms[:3]:
            term_clean = term.strip()
            if len(term_clean) > 3:
                variants.append(
                    SearchQueryVariant(
                        query=f"{original_query} {term_clean}",
                        language="en" if term_clean.isascii() else "ru",
                        goal_id=goal_id,
                        query_type=QueryType.DOMAIN_SPECIFIC,
                        priority=0.85,
                    )
                )
        return variants
