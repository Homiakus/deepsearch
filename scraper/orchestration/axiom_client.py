"""HTTP Client for Axiom ADGO Remote Worker Protocol (DS-A06)."""

import logging
from typing import Optional
import httpx

from scraper.orchestration.protocol import (
    WorkerSpec,
    RemoteWorkItem,
    WorkToken,
    ActivityResult,
    RemoteFailure,
    CompleteHTTPRequest,
    FailHTTPRequest,
    HeartbeatHTTPRequest,
)

logger = logging.getLogger(__name__)


class AxiomClient:
    """Async HTTP client communicating with Axiom ADGO coordinator."""

    PROTOCOL_VERSION = "adgo-worker-v1"

    def __init__(self, base_url: str = "http://localhost:8081", token: Optional[str] = "adgo-dev-token", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        headers = {
            "Content-Type": "application/json",
            "X-ADGO-Worker-Protocol": self.PROTOCOL_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )

    async def close(self):
        await self._client.aclose()

    async def poll(self, spec: WorkerSpec) -> Optional[RemoteWorkItem]:
        """Poll coordinator for available work item."""
        try:
            resp = await self._client.post("/v1/poll", json=spec.model_dump())
            if resp.status_code == 204:
                return None
            if resp.status_code == 200:
                data = resp.json()
                return RemoteWorkItem.model_validate(data)
            logger.warning("Poll returned unexpected status: %s %s", resp.status_code, resp.text)
            return None
        except httpx.RequestError as exc:
            logger.debug("Coordinator poll network exception: %s", exc)
            return None

    async def heartbeat(self, token: WorkToken, details: Optional[dict] = None) -> bool:
        """Send heartbeat to extend task lease."""
        req = HeartbeatHTTPRequest(token=token, details=details or {})
        try:
            resp = await self._client.post("/v1/heartbeat", json=req.model_dump())
            return resp.status_code == 200
        except httpx.RequestError as exc:
            logger.warning("Failed to send heartbeat: %s", exc)
            return False

    async def complete(self, token: WorkToken, result: ActivityResult, duration_nanos: int) -> bool:
        """Commit successful activity completion."""
        req = CompleteHTTPRequest(token=token, result=result, durationNanos=duration_nanos)
        try:
            resp = await self._client.post("/v1/complete", json=req.model_dump())
            if resp.status_code == 200:
                return True
            logger.warning("Complete rejected by coordinator: %s %s", resp.status_code, resp.text)
            return False
        except httpx.RequestError as exc:
            logger.error("Failed to post completion: %s", exc)
            return False

    async def fail(self, token: WorkToken, failure: RemoteFailure, duration_nanos: int) -> bool:
        """Report activity failure with classification."""
        req = FailHTTPRequest(token=token, failure=failure, durationNanos=duration_nanos)
        try:
            resp = await self._client.post("/v1/fail", json=req.model_dump(by_alias=True))
            return resp.status_code == 200
        except httpx.RequestError as exc:
            logger.error("Failed to post failure: %s", exc)
            return False
