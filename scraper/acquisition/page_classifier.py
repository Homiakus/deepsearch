"""Page Intelligence Engine (§7)."""

import re
from typing import List, Dict, Any
from pydantic import BaseModel


class PageIntelligence(BaseModel):
    content_type: str = "html"
    static_score: float = 0.90
    js_dependency_score: float = 0.10
    api_score: float = 0.0
    visual_score: float = 0.10
    content_quality: float = 0.90
    block_score: float = 0.0
    detected_frameworks: List[str] = []
    detected_apis: List[str] = []
    has_canvas: bool = False
    has_svg: bool = False
    tables_count: int = 0


def classify_page(
    url: str,
    status_code: int,
    headers: Dict[str, str],
    content_text: str,
    network_requests: List[Dict[str, Any]] = None,
) -> PageIntelligence:
    """Calculates metrics for Page Intelligence Engine (§7)."""
    mime = headers.get("content-type", "").lower()

    if "json" in mime:
        return PageIntelligence(
            content_type="json",
            static_score=1.0,
            js_dependency_score=0.0,
            api_score=1.0,
            visual_score=0.0,
            content_quality=1.0,
        )

    if "pdf" in mime:
        return PageIntelligence(
            content_type="pdf",
            static_score=1.0,
            js_dependency_score=0.0,
            api_score=0.0,
            visual_score=0.8,
            content_quality=0.9,
        )

    # Analyze HTML content
    html_lower = content_text.lower()

    # Detect frameworks & SPA hydration markers (§7)
    frameworks = []
    if (
        "__next_data__" in html_lower
        or "next/static" in html_lower
        or "__next" in html_lower
    ):
        frameworks.append("Next.js")
    if "__nuxt__" in html_lower or "nuxt.js" in html_lower:
        frameworks.append("Nuxt")
    if (
        "data-reactroot" in html_lower
        or 'id="react-root"' in html_lower
        or "react-dom" in html_lower
        or "/react." in html_lower
    ):
        frameworks.append("React")
    if (
        "v-app" in html_lower
        or "data-v-" in html_lower
        or "vue.js" in html_lower
        or "vue.runtime" in html_lower
    ):
        frameworks.append("Vue")
    if (
        "ng-version" in html_lower
        or "ng-app" in html_lower
        or "ng-controller" in html_lower
    ):
        frameworks.append("Angular")

    # Detect visual elements
    has_canvas = "<canvas" in html_lower
    has_svg = "<svg" in html_lower
    tables_count = len(re.findall(r"<table", html_lower))

    # Detect internal JSON / GraphQL API requests (§30 API Discovery)
    detected_apis = []
    if network_requests:
        for req in network_requests:
            req_mime = req.get("mime", "").lower()
            req_url = req.get("url", "")
            if "json" in req_mime or "/api/" in req_url or "graphql" in req_url:
                detected_apis.append(req_url)

    api_score = min(1.0, len(detected_apis) * 0.3)

    # Compute JS dependency score
    js_score = 0.1
    if frameworks:
        js_score += 0.4
    if len(re.findall(r"<script", html_lower)) > 15:
        js_score += 0.2
    if len(html_lower) < 2000 and frameworks:
        # Empty DOM shell requiring JS render
        js_score += 0.3

    js_score = min(1.0, js_score)
    static_score = round(1.0 - js_score, 2)

    # Compute Visual score
    visual_score = 0.1
    if has_canvas:
        visual_score += 0.5
    if tables_count > 2:
        visual_score += 0.3
    if has_svg:
        visual_score += 0.2

    visual_score = min(1.0, visual_score)

    # Compute Block score (detect bot block pages, Cloudflare, 403)
    block_score = 0.0
    if (
        status_code in (403, 429)
        or "captcha" in html_lower
        or "cloudflare" in html_lower
        or "access denied" in html_lower
        or "checking your browser" in html_lower
        or "just a moment..." in html_lower
    ):
        block_score = 0.95
        js_score = max(
            js_score, 0.85
        )  # Force JS dependency escalation for challenge pages

    static_score = round(1.0 - js_score, 2)

    return PageIntelligence(
        static_score=static_score,
        js_dependency_score=js_score,
        api_score=round(api_score, 2),
        visual_score=round(visual_score, 2),
        content_quality=round(1.0 - block_score, 2),
        block_score=block_score,
        detected_frameworks=frameworks,
        detected_apis=detected_apis,
        has_canvas=has_canvas,
        has_svg=has_svg,
        tables_count=tables_count,
    )
