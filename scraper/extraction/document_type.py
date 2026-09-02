"""Document-type classification for acquisition quality gates.

The extractor must distinguish an evidence-bearing document from a page that was
technically fetched successfully but cannot be used as research evidence.
"""

import re
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    DOCUMENT = "DOCUMENT"
    SEARCH_LISTING = "SEARCH_LISTING"
    NAVIGATION = "NAVIGATION"
    LOGIN = "LOGIN"
    BLOCK_PAGE = "BLOCK_PAGE"
    JS_SHELL = "JS_SHELL"
    ERROR_PAGE = "ERROR_PAGE"


class DocumentClassification(BaseModel):
    document_type: DocumentType
    accepted: bool
    reason_code: str
    signals: list[str] = Field(default_factory=list)
    useful_text_chars: int = 0
    link_density: float = 0.0


class DocumentTypeClassifier:
    """Conservative classifier used before a page enters the research corpus."""

    BLOCK_MARKERS = (
        "access denied",
        "attention required",
        "cloudflare",
        "captcha",
        "datadome",
        "perimeterx",
        "security check",
        "please verify you are a human",
        "checking your browser",
        "reference #",
    )
    ERROR_MARKERS = (
        "internal server error",
        "service unavailable",
        "bad gateway",
        "page not found",
        "404 not found",
    )
    LOGIN_MARKERS = (
        "sign in",
        "log in",
        "login",
        "forgotten your password",
        "keep me signed in",
        "create an account",
    )
    JS_MARKERS = (
        "please enable javascript",
        "enable javascript to proceed",
        "requires javascript to function",
        "you need to enable javascript",
    )
    LISTING_PATH_MARKERS = (
        "/search",
        "/results",
        "/browse",
        "/authors",
        "/author/",
        "/category/",
        "/tag/",
    )
    LOGIN_PATH_MARKERS = (
        "/login",
        "/signin",
        "/sign-in",
        "/account/login",
        "/accounts/login",
    )

    @staticmethod
    def _useful_text(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()

    @classmethod
    def classify(
        cls,
        url: str,
        text: str,
        status_code: int = 200,
        content_type: str = "text/html",
        title: str = "",
        link_density: float = 0.0,
    ) -> DocumentClassification:
        lower_text = (text or "").lower()
        parsed = urlparse(url or "")
        path = parsed.path.lower()
        useful_text = cls._useful_text(text)
        signals: list[str] = []

        if status_code >= 500:
            return DocumentClassification(
                document_type=DocumentType.ERROR_PAGE,
                accepted=False,
                reason_code="HTTP_SERVER_ERROR",
                signals=[f"status:{status_code}"],
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        if status_code in (401, 403, 429) or any(
            marker in lower_text for marker in cls.BLOCK_MARKERS
        ):
            if status_code in (401, 403, 429):
                signals.append(f"status:{status_code}")
            signals.extend(
                marker for marker in cls.BLOCK_MARKERS if marker in lower_text
            )
            return DocumentClassification(
                document_type=DocumentType.BLOCK_PAGE,
                accepted=False,
                reason_code="BLOCK_OR_ACCESS_DENIED",
                signals=signals,
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        if status_code >= 400 or any(
            marker in lower_text for marker in cls.ERROR_MARKERS
        ):
            if status_code >= 400:
                signals.append(f"status:{status_code}")
            signals.extend(
                marker for marker in cls.ERROR_MARKERS if marker in lower_text
            )
            return DocumentClassification(
                document_type=DocumentType.ERROR_PAGE,
                accepted=False,
                reason_code="HTTP_OR_ERROR_PAGE",
                signals=signals,
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        login_signal_count = sum(marker in lower_text for marker in cls.LOGIN_MARKERS)
        has_login_form = "password" in lower_text and (
            "email" in lower_text or "username" in lower_text
        )
        if any(marker in path for marker in cls.LOGIN_PATH_MARKERS) or (
            login_signal_count >= 3 and (len(useful_text) < 1200 or has_login_form)
        ):
            signals.extend(
                marker for marker in cls.LOGIN_MARKERS if marker in lower_text
            )
            return DocumentClassification(
                document_type=DocumentType.LOGIN,
                accepted=False,
                reason_code="AUTHENTICATION_PAGE",
                signals=signals,
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        if any(marker in lower_text for marker in cls.JS_MARKERS) or (
            len(useful_text) < 300
            and re.search(
                r"<(?:div|main)[^>]+(?:id|class)=[\"'](?:root|app|__next)", lower_text
            )
        ):
            signals.extend(marker for marker in cls.JS_MARKERS if marker in lower_text)
            if len(useful_text) < 300:
                signals.append("thin_spa_shell")
            return DocumentClassification(
                document_type=DocumentType.JS_SHELL,
                accepted=False,
                reason_code="UNRENDERED_JAVASCRIPT_SHELL",
                signals=signals,
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        path_is_listing = any(marker in path for marker in cls.LISTING_PATH_MARKERS)
        query_is_listing = any(
            key in parsed.query.lower()
            for key in ("searchtype=", "query=", "page=", "offset=")
        )
        if path_is_listing or query_is_listing or link_density >= 0.65:
            if path_is_listing:
                signals.append("listing_path")
            if query_is_listing:
                signals.append("listing_query")
            if link_density >= 0.65:
                signals.append("high_link_density")
            return DocumentClassification(
                document_type=DocumentType.SEARCH_LISTING,
                accepted=False,
                reason_code="SEARCH_OR_DIRECTORY_PAGE",
                signals=signals,
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        if path in ("", "/") and not title.strip() and len(useful_text) < 1200:
            return DocumentClassification(
                document_type=DocumentType.NAVIGATION,
                accepted=False,
                reason_code="DOMAIN_HOME_PAGE",
                signals=["root_path", "missing_title"],
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        if (
            "html" not in (content_type or "").lower()
            and "text" not in (content_type or "").lower()
        ):
            signals.append(f"content_type:{content_type}")

        if len(useful_text) < 120:
            return DocumentClassification(
                document_type=DocumentType.NAVIGATION,
                accepted=False,
                reason_code="INSUFFICIENT_USEFUL_TEXT",
                signals=signals + ["text_too_short"],
                useful_text_chars=len(useful_text),
                link_density=link_density,
            )

        return DocumentClassification(
            document_type=DocumentType.DOCUMENT,
            accepted=True,
            reason_code="DOCUMENT_EVIDENCE_CANDIDATE",
            signals=signals,
            useful_text_chars=len(useful_text),
            link_density=link_density,
        )


document_type_classifier = DocumentTypeClassifier()
