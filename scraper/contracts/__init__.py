"""Core Protocols and Data Contracts for DeepSearch Platform (§DS-05)."""

from __future__ import annotations

from typing import Protocol, Optional, Dict, Any, List, runtime_checkable
from scraper.acquisition.http_fetcher import HTTPResponse
from scraper.acquisition.browser_pool import BrowserResponse
from scraper.acquisition.models import AcquisitionRequest, AcquisitionResult


@runtime_checkable
class FetcherProtocol(Protocol):
    """Abstract protocol for HTTP page fetchers."""

    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
    ) -> HTTPResponse: ...

    async def close(self) -> None: ...


@runtime_checkable
class BrowserPoolProtocol(Protocol):
    """Abstract protocol for Playwright browser pool managers."""

    async def fetch_page(
        self,
        url: str,
        visual_mode: bool = False,
        wait_for_selector: Optional[str] = None,
        take_screenshot: bool = False,
    ) -> BrowserResponse: ...

    async def close(self) -> None: ...


@runtime_checkable
class StorageProtocol(Protocol):
    """Abstract protocol for Content Addressable and Persistent Storage engines."""

    async def put(
        self, data: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> str: ...

    async def get(self, key: str) -> Optional[bytes]: ...

    async def exists(self, key: str) -> bool: ...


@runtime_checkable
class OCREngineProtocol(Protocol):
    """Abstract protocol for visual OCR engines."""

    async def extract_text_from_image(self, image_bytes: bytes) -> str: ...


@runtime_checkable
class AcquisitionBackend(Protocol):
    """Capability-oriented acquisition backend protocol (§4, DS-RB02)."""

    @property
    def descriptor(self) -> Any: ...

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult: ...


@runtime_checkable
class DiscoveryProviderProtocol(Protocol):
    """Protocol for academic and open access discovery providers (§DS-13)."""

    @property
    def name(self) -> str: ...

    async def search(
        self,
        query: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> List[str]: ...
