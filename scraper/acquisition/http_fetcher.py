"""Async HTTP Fetcher (§6 L1, §72 SSRF, §73 Protocols, §74 Download Safety)."""

import ipaddress
import socket
import urllib.parse
import httpx
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from scraper.config import settings
from scraper.exceptions import SSRFError


class SSRFValidationError(SSRFError, ValueError):
    """Raised when target URL resolves to a restricted private IP address."""
    pass


class HTTPResponse(BaseModel):
    url: str
    status_code: int
    headers: Dict[str, str]
    content: bytes
    text: str
    content_type: str
    elapsed_sec: float
    redirect_chain: List[str] = Field(default_factory=list)


class HTTPFetcher:
    """Async HTTP Client with SSRF protection and download safety checks."""

    PRIVATE_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]

    def __init__(self, timeout_sec: float = 30.0):
        self.timeout_sec = timeout_sec

    @classmethod
    def validate_url_security(cls, url: str):
        """Validate protocol and check for SSRF (§72, §73)."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in settings.security.allowed_protocols:
            raise SSRFValidationError(f"Protocol '{parsed.scheme}' is not allowed.")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFValidationError("Invalid URL hostname.")

        if settings.security.block_private_ips:
            try:
                ip_addrs = socket.getaddrinfo(hostname, None)
                for family, _, _, _, sockaddr in ip_addrs:
                    ip = ipaddress.ip_address(sockaddr[0])
                    for net in cls.PRIVATE_NETWORKS:
                        if ip in net:
                            raise SSRFValidationError(f"Access to private IP {ip} is blocked.")
            except socket.gaierror:
                pass  # DNS resolution error handled downstream

    async def fetch(self, url: str, headers: Optional[Dict[str, str]] = None, proxy: Optional[str] = None) -> HTTPResponse:
        """Fetch URL content via direct HTTP request with streaming size checks (§74)."""
        self.validate_url_security(url)

        default_headers = {"User-Agent": settings.robots.user_agent}
        if headers:
            default_headers.update(headers)

        transport = httpx.AsyncHTTPTransport(retries=0, verify=False)
        async with httpx.AsyncClient(
            transport=transport,
            timeout=self.timeout_sec,
            follow_redirects=True,
            max_redirects=settings.security.max_redirects,
            proxy=proxy,
            trust_env=False
        ) as client:
            req = client.build_request("GET", url, headers=default_headers)
            res = await client.send(req, stream=True)

            # Stream response to enforce max response size limit (§74)
            chunks = []
            total_size = 0
            async for chunk in res.aiter_bytes():
                total_size += len(chunk)
                if total_size > settings.security.max_response_size_bytes:
                    await res.aclose()
                    raise ValueError(f"Response size exceeded max limit of {settings.security.max_response_size_bytes} bytes")
                chunks.append(chunk)

            await res.aclose()
            content = b"".join(chunks)

            content_type = res.headers.get("content-type", "").split(";")[0].strip().lower()

            return HTTPResponse(
                url=str(res.url),
                status_code=res.status_code,
                headers=dict(res.headers),
                content=content,
                text=content.decode("utf-8", errors="ignore") if (content_type.startswith("text/") or "json" in content_type or "xml" in content_type or not content_type) else "",
                content_type=content_type,
                elapsed_sec=res.elapsed.total_seconds(),
                redirect_chain=[str(r.url) for r in res.history]
            )
