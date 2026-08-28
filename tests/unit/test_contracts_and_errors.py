"""Unit and Contract tests for Protocols and Error Taxonomy (§DS-05)."""

import pytest
from typing import Dict, Any, Optional, List

from scraper.contracts import (
    FetcherProtocol,
    BrowserPoolProtocol,
    StorageProtocol,
    OCREngineProtocol,
    AcquisitionBackend,
    DiscoveryProviderProtocol,
)
from scraper.acquisition.http_fetcher import HTTPFetcher, HTTPResponse
from scraper.acquisition.browser_pool import BrowserPoolManager, BrowserResponse
from scraper.acquisition.models import AcquisitionRequest, AcquisitionResult
from scraper.application.models import (
    RunResult,
    ResearchResult,
    ProviderStatus,
    RunLifecycleState,
)
from scraper.exceptions import (
    ErrorCode,
    DeepSearchError,
    InvalidInputError,
    BlockedTargetError,
    SSRFError,
    DeepSearchTimeoutError,
    DependencyUnavailableError,
    BudgetExceededError,
    PartialResultError,
    InternalError,
    ERROR_CODE_HTTP_STATUS,
    ERROR_CODE_CLI_EXIT,
)


# --- 1. Fake implementations testing Protocol compliance ---


class FakeFetcher:
    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
    ) -> HTTPResponse:
        return HTTPResponse(
            url=url,
            status_code=200,
            headers={},
            content=b"ok",
            text="ok",
            content_type="text/plain",
            elapsed_sec=0.01,
        )

    async def close(self) -> None:
        pass


class FakeBrowserPool:
    async def fetch_page(
        self,
        url: str,
        visual_mode: bool = False,
        wait_for_selector: Optional[str] = None,
        take_screenshot: bool = False,
    ) -> BrowserResponse:
        return BrowserResponse(
            url=url,
            status_code=200,
            content="<html>fake</html>",
            screenshot_bytes=None,
            network_requests=[],
            headers={},
        )

    async def close(self) -> None:
        pass


class FakeStorage:
    def __init__(self):
        self.store = {}

    async def put(self, data: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        key = str(len(self.store))
        self.store[key] = data
        return key

    async def get(self, key: str) -> Optional[bytes]:
        return self.store.get(key)

    async def exists(self, key: str) -> bool:
        return key in self.store


class FakeOCR:
    async def extract_text_from_image(self, image_bytes: bytes) -> str:
        return "extracted text"


class FakeAcquisitionBackend:
    @property
    def descriptor(self) -> Dict[str, Any]:
        return {"name": "fake_backend", "version": "1.0.0"}

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        return AcquisitionResult(
            requested_url=request.url,
            final_url=request.url,
            backend="fake_backend",
        )


class FakeDiscoveryProvider:
    @property
    def name(self) -> str:
        return "fake_provider"

    async def search(
        self,
        query: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> List[str]:
        return [f"https://example.com/item/{i}" for i in range(limit)]


def test_protocol_conformance_with_fakes():
    """Verify fake implementations satisfy the runtime-checkable Protocol definitions (§DS-05)."""
    assert isinstance(FakeFetcher(), FetcherProtocol)
    assert isinstance(FakeBrowserPool(), BrowserPoolProtocol)
    assert isinstance(FakeStorage(), StorageProtocol)
    assert isinstance(FakeOCR(), OCREngineProtocol)
    assert isinstance(FakeAcquisitionBackend(), AcquisitionBackend)
    assert isinstance(FakeDiscoveryProvider(), DiscoveryProviderProtocol)


def test_production_adapters_satisfy_protocols():
    """Verify real production adapters satisfy the runtime-checkable Protocol definitions (§DS-05)."""
    fetcher = HTTPFetcher()
    assert isinstance(fetcher, FetcherProtocol)

    pool = BrowserPoolManager()
    assert isinstance(pool, BrowserPoolProtocol)


# --- 2. Error Taxonomy & Scenario Matrix Tests ---


@pytest.mark.parametrize(
    "error_cls, expected_code, expected_http, expected_cli",
    [
        (InvalidInputError, ErrorCode.INVALID_INPUT, 400, 2),
        (BlockedTargetError, ErrorCode.BLOCKED_TARGET, 403, 3),
        (SSRFError, ErrorCode.BLOCKED_TARGET, 403, 3),
        (DeepSearchTimeoutError, ErrorCode.TIMEOUT, 504, 4),
        (DependencyUnavailableError, ErrorCode.DEPENDENCY_UNAVAILABLE, 503, 5),
        (BudgetExceededError, ErrorCode.BUDGET_EXCEEDED, 429, 6),
        (PartialResultError, ErrorCode.PARTIAL_RESULT, 206, 7),
        (InternalError, ErrorCode.INTERNAL_ERROR, 500, 1),
    ],
)
def test_error_taxonomy_mappings(error_cls, expected_code, expected_http, expected_cli):
    """Verify closed error taxonomy mapping across REST HTTP status and CLI exit code (§DS-05)."""
    exc = error_cls("Test error message", details={"field": "test_field"})
    assert isinstance(exc, DeepSearchError)
    assert exc.code == expected_code
    assert exc.http_status == expected_http
    assert exc.cli_exit_code == expected_cli

    payload = exc.to_dict()
    assert payload["error"] == expected_code.value
    assert payload["message"] == "Test error message"
    assert payload["details"] == {"field": "test_field"}


def test_all_error_codes_covered():
    """Ensure every enum value in ErrorCode has corresponding HTTP and CLI mappings."""
    for code in ErrorCode:
        assert code in ERROR_CODE_HTTP_STATUS
        assert code in ERROR_CODE_CLI_EXIT


# --- 3. Structured RunResult & Distinguishability Tests ---


def test_structured_run_result_and_provider_statuses():
    """Verify RunResult holds structured warnings, errors, and provider statuses (§DS-05)."""
    p_status = ProviderStatus(
        provider="arxiv",
        status="ok",
        items_count=12,
        duration_sec=0.45,
    )
    result = RunResult(
        run_id="run_test_123",
        query="quantum computing",
        status=RunLifecycleState.COMPLETED,
        total_pages_processed=10,
        total_rag_chunks=45,
        warnings=["Non-fatal encoding issue on page 3"],
        errors=[],
        provider_statuses={"arxiv": p_status},
    )

    assert result.run_id == "run_test_123"
    assert result.status == RunLifecycleState.COMPLETED
    assert len(result.warnings) == 1
    assert result.provider_statuses["arxiv"].items_count == 12

    # ResearchResult compatibility
    assert isinstance(result, RunResult)
    res_result = ResearchResult(**result.model_dump())
    assert res_result.query == "quantum computing"


def test_empty_result_distinguishable_from_failure():
    """Verify an empty result with insufficient evidence is clearly distinguished from dependency failure (§DS-05)."""
    empty_result = RunResult(
        run_id="run_empty_1",
        query="nonexistent topic xyz123",
        status=RunLifecycleState.INSUFFICIENT_EVIDENCE,
        total_pages_processed=0,
        warnings=["No matching documents found across 3 providers"],
        errors=[],
    )

    failed_result = RunResult(
        run_id="run_failed_1",
        query="network down topic",
        status=RunLifecycleState.FAILED,
        total_pages_processed=0,
        errors=["DNS resolution timeout for all seed targets"],
    )

    # Invariant: Insufficient evidence != Failed
    assert empty_result.status != failed_result.status
    assert empty_result.status == RunLifecycleState.INSUFFICIENT_EVIDENCE
    assert failed_result.status == RunLifecycleState.FAILED
    assert len(empty_result.errors) == 0
    assert len(failed_result.errors) > 0
