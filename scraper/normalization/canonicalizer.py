"""URL Canonicalization Engine (§16)."""

import urllib.parse

TRACKING_PARAMS: set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
    "mc_eid",
    "_ga",
    "ref",
    "source",
}

HTTPS_UPGRADE_DOMAINS: set[str] = {
    "arxiv.org",
    "export.arxiv.org",
    "europepmc.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
}


def canonicalize_url(raw_url: str, canonical_link_tag: str = None) -> str:
    """Normalizes and canonicalizes a URL (§16)."""
    if canonical_link_tag and canonical_link_tag.startswith("http"):
        target_url = canonical_link_tag.strip()
    else:
        target_url = raw_url.strip()

    parsed = urllib.parse.urlparse(target_url)

    # 1. Lowercase scheme and hostname
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    if scheme == "http" and netloc in HTTPS_UPGRADE_DOMAINS:
        scheme = "https"

    # 2. Normalize default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # 3. Path normalization (unquote and collapse slashes while preserving %2F)
    path = parsed.path
    if not path:
        path = "/"
    else:
        # Preserve %2F (%2f) to avoid merging distinct path resources (§FRAG-001)
        path = path.replace("%2f", "%2F")
        segments = path.split("/")
        norm_segments = []
        for i, seg in enumerate(segments):
            if not seg and i > 0 and i < len(segments) - 1:
                # Collapse empty intermediate segments (e.g., //)
                continue
            seg_token = seg.replace("%2F", "__ENC_SLASH__")
            seg_unquoted = urllib.parse.unquote(seg_token)
            seg_restored = seg_unquoted.replace("__ENC_SLASH__", "%2F")
            norm_segments.append(seg_restored)
        path = "/".join(norm_segments)
        if not path.startswith("/"):
            path = "/" + path

    # 4. Filter and sort query parameters
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_params = [
        (k, v) for k, v in query_params if k.lower() not in TRACKING_PARAMS
    ]
    filtered_params.sort(key=lambda x: (x[0], x[1]))

    clean_query = urllib.parse.urlencode(filtered_params)

    # 5. Remove fragment
    canonical = urllib.parse.urlunparse((scheme, netloc, path, "", clean_query, ""))
    return canonical
