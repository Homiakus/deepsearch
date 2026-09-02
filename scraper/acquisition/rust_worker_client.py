"""Client for Rust Browser Acquisition Worker Local REST API (§4, DS-RB38)."""

import logging
from typing import Any

import httpx

from scraper.acquisition.capabilities import BackendDescriptor
from scraper.acquisition.models import AcquisitionRequest, AcquisitionResult

logger = logging.getLogger(__name__)


class RustWorkerClient:
    """Async client communicating with Rust Acquisition Worker over local REST API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8081", timeout: float = 35.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout
            )
        return self._client

    async def health(self) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.get("/v1/health")
        resp.raise_for_status()
        return resp.json()

    async def list_backends(self) -> list[BackendDescriptor]:
        client = await self._get_client()
        resp = await client.get("/v1/backends")
        resp.raise_for_status()
        return [BackendDescriptor.model_validate(b) for b in resp.json()]

    async def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        client = await self._get_client()
        payload = request.model_dump()
        resp = await client.post("/v1/acquire", json=payload)
        resp.raise_for_status()
        return AcquisitionResult.model_validate(resp.json())

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
