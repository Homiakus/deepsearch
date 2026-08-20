"""Source Policy & Contextual Authority Prior (DS-SI18, DS-SI48)."""

from enum import Enum
from scraper.search.source_types import SourceType


class SourceClass(str, Enum):
    PEER_REVIEWED = "peer_reviewed"
    PREPRINT = "preprint"
    OFFICIAL = "official"
    DATASET = "dataset"
    SECONDARY = "secondary"
    NAVIGATION = "navigation"
    UNKNOWN = "unknown"


# High authority scientific, medical, and multi-regional repositories
ACADEMIC_DOMAINS = {
    "europepmc.org": 0.95,
    "ncbi.nlm.nih.gov": 0.95,
    "pubmed.ncbi.nlm.nih.gov": 0.96,
    "semanticscholar.org": 0.96,
    "api.semanticscholar.org": 0.96,
    "openalex.org": 0.95,
    "crossref.org": 0.96,
    "api.crossref.org": 0.96,
    "arxiv.org": 0.90,
    "export.arxiv.org": 0.90,
    "biorxiv.org": 0.88,
    "medrxiv.org": 0.88,
    "nature.com": 0.98,
    "science.org": 0.98,
    "cell.com": 0.98,
    "thelancet.com": 0.98,
    "nejm.org": 0.98,
    "bmj.com": 0.97,
    "jamanetwork.com": 0.97,
    "pnas.org": 0.96,
    "hal.science": 0.93,
    "cyberleninka.ru": 0.92,
    "scielo.org": 0.92,
    "jstage.jst.go.jp": 0.92,
    "doi.org": 0.92,
}

TECH_DOMAINS = {
    "github.com": 0.90,
    "qdrant.tech": 0.92,
    "servo.org": 0.92,
    "mozilla.org": 0.92,
    "developer.mozilla.org": 0.95,
    "docs.python.org": 0.95,
    "rust-lang.org": 0.95,
}

GOVERNMENT_DOMAINS = {
    "fda.gov": 0.95,
    "nih.gov": 0.95,
    "who.int": 0.95,
    "cdc.gov": 0.92,
    "gost.ru": 0.95,
    "docs.cntd.ru": 0.90,
}


def calculate_authority_prior(
    domain: str,
    source_type: str = "UNKNOWN",
    task_type: str = "general_research",
) -> float:
    """Calculates prior authority score based on domain, source type, and research context."""
    d_lower = domain.lower()

    # 1. Exact domain prior match
    if d_lower in ACADEMIC_DOMAINS:
        return ACADEMIC_DOMAINS[d_lower]
    if d_lower in TECH_DOMAINS:
        return TECH_DOMAINS[d_lower]
    if d_lower in GOVERNMENT_DOMAINS:
        return GOVERNMENT_DOMAINS[d_lower]

    for dom, score in {
        **ACADEMIC_DOMAINS,
        **TECH_DOMAINS,
        **GOVERNMENT_DOMAINS,
    }.items():
        if d_lower.endswith(f".{dom}"):
            return score

    # 2. Source-type contextual prior
    if source_type in (
        SourceType.GUIDELINE.value,
        SourceType.REGULATOR.value,
        SourceType.STANDARD.value,
    ):
        return 0.94
    if source_type in (
        SourceType.META_ANALYSIS.value,
        SourceType.SYSTEMATIC_REVIEW.value,
    ):
        return 0.96
    if source_type == SourceType.PRIMARY_RESEARCH.value:
        return 0.92
    if source_type == SourceType.OFFICIAL_DOC.value:
        return 0.90
    if source_type == SourceType.GOVERNMENT.value:
        return 0.92
    if source_type == SourceType.SOURCE_CODE.value:
        return 0.85
    if source_type == SourceType.WIKI.value:
        return 0.75
    if source_type == SourceType.NEWS_MEDIA.value:
        return 0.70
    if source_type in (SourceType.FORUM.value, SourceType.ISSUE_TRACKER.value):
        return 0.70 if task_type in ("technical", "bug", "user_experience") else 0.50
    if source_type == SourceType.MARKETING.value:
        return 0.40

    return 0.50


PEER_REVIEWED_DOMAINS = (
    "nature.com",
    "science.org",
    "cell.com",
    "thelancet.com",
    "nejm.org",
    "bmj.com",
    "springer.com",
    "sciencedirect.com",
    "mdpi.com",
    "frontiersin.org",
    "plos.org",
    "acm.org",
    "ieeexplore.ieee.org",
    "wiley.com",
    "tandfonline.com",
    "pubmed.ncbi.nlm.nih.gov",
    "semanticscholar.org",
    "openalex.org",
    "hal.science",
    "cyberleninka.ru",
    "scielo.org",
    "jstage.jst.go.jp",
)


def classify_source_class(
    url: str, source_type: str = "UNKNOWN", title: str = ""
) -> SourceClass:
    """Classifies epistemic role independently of topical relevance."""
    from urllib.parse import urlparse

    parsed = urlparse(url or "")
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    title_lower = (title or "").lower()

    if any(
        marker in path
        for marker in ("/search", "/results", "/browse", "/login", "/accounts/login")
    ):
        return SourceClass.NAVIGATION
    if source_type in (SourceType.WIKI.value, SourceType.AGGREGATOR.value):
        return SourceClass.SECONDARY
    if source_type in (
        SourceType.BLOG.value,
        SourceType.NEWS_MEDIA.value,
        SourceType.NEWS_WIRE.value,
    ):
        return SourceClass.SECONDARY
    if domain in ("arxiv.org", "export.arxiv.org", "biorxiv.org", "medrxiv.org"):
        return SourceClass.PREPRINT
    if domain == "europepmc.org" and "/article/" in path:
        return SourceClass.PEER_REVIEWED
    if any(domain == d or domain.endswith("." + d) for d in PEER_REVIEWED_DOMAINS):
        return SourceClass.PEER_REVIEWED
    if source_type in (
        SourceType.REGULATOR.value,
        SourceType.GUIDELINE.value,
        SourceType.STANDARD.value,
        SourceType.GOVERNMENT.value,
        SourceType.OFFICIAL_DOC.value,
    ):
        return SourceClass.OFFICIAL
    if source_type == SourceType.SOURCE_CODE.value:
        return SourceClass.DATASET
    if any(
        term in title_lower
        for term in ("survey", "systematic review", "meta-analysis", "benchmark")
    ):
        return SourceClass.SECONDARY
    return SourceClass.UNKNOWN
