"""Expected Acquisition Cost Estimation (DS-SI20)."""

from typing import Optional


def estimate_acquisition_cost(url: str, domain: str, provider: Optional[str] = None) -> float:
    """Estimates expected network & rendering cost (normalized 0.1 to 2.0)."""
    cost = 1.0

    # Fast academic/API direct endpoints
    if any(k in domain for k in ["arxiv.org", "europepmc.org", "wikipedia.org", "github.com"]):
        cost = 0.5

    # Heavy PDF links
    if url.lower().endswith(".pdf") or "/pdf" in url.lower():
        cost = 1.2

    # Known dynamic SPA sites requiring browser escalation
    if any(k in domain for k in ["twitter.com", "x.com", "linkedin.com", "medium.com"]):
        cost = 1.8

    return cost
