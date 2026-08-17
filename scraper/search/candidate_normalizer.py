"""Candidate Normalizer and Multi-Provider Provenance Merger (DS-SI14, DS-SI15)."""

import urllib.parse
from typing import Dict, List
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.search.candidates import SourceCandidate


class CandidateNormalizer:
    """Normalizes candidate URLs, titles, and dates while preserving provider agreement signals."""

    @staticmethod
    def normalize_candidates(candidates: List[SourceCandidate]) -> List[SourceCandidate]:
        merged: Dict[str, SourceCandidate] = {}

        for c in candidates:
            c_url = canonicalize_url(c.url)
            if not c_url:
                continue

            parsed = urllib.parse.urlparse(c_url)
            domain = parsed.netloc.lower()

            if c_url not in merged:
                c.canonical_url = c_url
                c.domain = domain
                c.title = c.title.strip()
                c.snippet = c.snippet.strip()
                if c.provider and c.provider not in c.found_by_providers:
                    c.found_by_providers.append(c.provider)
                merged[c_url] = c
            else:
                # Merge provenance signals
                existing = merged[c_url]
                if c.provider and c.provider not in existing.found_by_providers:
                    existing.found_by_providers.append(c.provider)
                for gid in c.goal_ids:
                    if gid not in existing.goal_ids:
                        existing.goal_ids.append(gid)
                for qv in c.query_variants:
                    if qv not in existing.query_variants:
                        existing.query_variants.append(qv)
                # Keep higher quality title and snippet if available
                if len(c.title) > len(existing.title):
                    existing.title = c.title
                if len(c.snippet) > len(existing.snippet):
                    existing.snippet = c.snippet
                # Best provider rank
                existing.provider_rank = min(existing.provider_rank, c.provider_rank)
                existing.authority_prior = max(existing.authority_prior, c.authority_prior)
                existing.provider_metadata.update(c.provider_metadata)

        return list(merged.values())


candidate_normalizer = CandidateNormalizer()
