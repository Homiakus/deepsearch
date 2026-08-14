"""Core Protocols and Data Contracts for DeepSearch Platform."""

from typing import Protocol, Optional, Dict, Any, runtime_checkable


@runtime_checkable
class FetcherProtocol(Protocol):
    """Abstract protocol for HTTP page fetchers."""
    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> Any:
        ...


@runtime_checkable
class BrowserPoolProtocol(Protocol):
    """Abstract protocol for Playwright browser pool managers."""
    async def fetch_page(
        self,
        url: str,
        visual_mode: bool = False,
        wait_for_selector: Optional[str] = None,
        take_screenshot: bool = False,
        timeout: float = 30.0
    ) -> Any:
        ...


@runtime_checkable
class StorageProtocol(Protocol):
    """Abstract protocol for Content Addressable and Persistent Storage engines."""
    async def put(self, data: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        ...

    async def get(self, key: str) -> Optional[bytes]:
        ...

    async def exists(self, key: str) -> bool:
        ...


@runtime_checkable
class OCREngineProtocol(Protocol):
    """Abstract protocol for visual OCR engines (PaddleOCR-VL-1.6)."""
    async def extract_text_from_image(self, image_bytes: bytes) -> Any:
        ...
