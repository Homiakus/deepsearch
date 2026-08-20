"""Terminal URL policy for research candidates.

Discovery pages may be useful to a provider internally, but they are not valid
terminal evidence sources for the acquisition pipeline.
"""

from enum import Enum
from urllib.parse import parse_qs, urlparse


class URLRejectionReason(str, Enum):
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
    AUTHENTICATION_URL = "AUTHENTICATION_URL"
    SEARCH_LISTING_URL = "SEARCH_LISTING_URL"
    DOMAIN_HOME_URL = "DOMAIN_HOME_URL"
    BINARY_DOCUMENT_URL = "BINARY_DOCUMENT_URL"


class CandidateURLPolicy:
    AUTH_PATHS = ("/login", "/signin", "/sign-in", "/account/login", "/accounts/login")
    LISTING_PATHS = (
        "/search",
        "/results",
        "/browse",
        "/authors",
        "/author/",
        "/category/",
        "/tag/",
    )
    LISTING_QUERY_KEYS = {"searchtype", "query", "q", "page", "offset", "start"}
    BINARY_PATH_MARKERS = (
        "/pdf/",
        "/pdf",
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        "ptpmcrender.fcgi",
    )

    @classmethod
    def rejection_reason(cls, url: str) -> URLRejectionReason | None:
        parsed = urlparse(url or "")
        scheme = parsed.scheme.lower()
        path = parsed.path.lower().rstrip("/") or "/"
        if scheme not in {"http", "https"}:
            return URLRejectionReason.UNSUPPORTED_SCHEME
        if any(
            path == marker or path.startswith(marker + "/") for marker in cls.AUTH_PATHS
        ):
            return URLRejectionReason.AUTHENTICATION_URL
        if any(
            marker in path or marker in parsed.query.lower()
            for marker in cls.BINARY_PATH_MARKERS
        ):
            return URLRejectionReason.BINARY_DOCUMENT_URL
        if any(
            path == marker or path.startswith(marker + "/")
            for marker in cls.LISTING_PATHS
        ):
            return URLRejectionReason.SEARCH_LISTING_URL
        if parse_qs(parsed.query) and any(
            key.lower() in cls.LISTING_QUERY_KEYS for key in parse_qs(parsed.query)
        ):
            return URLRejectionReason.SEARCH_LISTING_URL
        if path == "/":
            return URLRejectionReason.DOMAIN_HOME_URL
        return None

    @classmethod
    def is_terminal_source_allowed(cls, url: str) -> bool:
        return cls.rejection_reason(url) is None


candidate_url_policy = CandidateURLPolicy()
