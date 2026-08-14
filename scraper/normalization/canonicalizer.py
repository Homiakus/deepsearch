"""URL Canonicalization Engine (§16)."""

import urllib.parse
import re
from typing import Set

TRACKING_PARAMS: Set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_eid", "_ga", "ref", "source"
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

    # 2. Normalize default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # 3. Path normalization (unquote and collapse slashes)
    path = parsed.path
    if not path:
        path = "/"
    else:
        path = urllib.parse.unquote(path)
        path = re.sub(r"/+", "/", path)

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
