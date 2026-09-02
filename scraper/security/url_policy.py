"""Unified URL Security Policy and SSRF Defense (§25, §26, DS-A20, §DS-07)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import urllib.parse

from scraper.config import settings
from scraper.exceptions import SSRFBlockedError


class URLSecurityPolicy:
    """Validates URLs, resolves DNS asynchronously, and blocks private/loopback/link-local destinations (§DS-07)."""

    BLOCKED_CIDRS = [
        # IPv4 Private / Loopback / Link-Local / Reserved
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("224.0.0.0/4"),
        ipaddress.ip_network("240.0.0.0/4"),
        ipaddress.ip_network("255.255.255.255/32"),
        # IPv6 Loopback / Unspecified / Unique Local / Link-Local / Multicast
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("ff00::/8"),
        ipaddress.ip_network("64:ff9b::/96"),
    ]

    def __init__(
        self,
        block_private_ips: bool | None = None,
        allowed_protocols: list[str] | None = None,
        max_response_size: int | None = None,
    ):
        self.block_private_ips = (
            block_private_ips
            if block_private_ips is not None
            else settings.security.block_private_ips
        )
        self.allowed_protocols = [
            p.lower()
            for p in (allowed_protocols or settings.security.allowed_protocols)
        ]
        self.max_response_size = (
            max_response_size or settings.security.max_response_size_bytes
        )

    def is_ip_blocked(self, ip_str: str) -> bool:
        """Checks if an IP string belongs to private, loopback, or reserved subnets, including IPv4-mapped IPv6."""
        try:
            ip = ipaddress.ip_address(ip_str)
            if not self.block_private_ips:
                return False

            # Check IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                return self.is_ip_blocked(str(ip.ipv4_mapped))

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return True

            for cidr in self.BLOCKED_CIDRS:
                if ip in cidr:
                    return True

            return False
        except ValueError:
            return False

    def validate_url(self, url: str) -> str:
        """Synchronously validates protocol, host, and resolves DNS to prevent SSRF."""
        if not url or not isinstance(url, str):
            raise SSRFBlockedError("Invalid empty URL target")

        parsed = urllib.parse.urlparse(url.strip())
        if not parsed.scheme or parsed.scheme.lower() not in self.allowed_protocols:
            raise SSRFBlockedError(
                f"Protocol '{parsed.scheme}' not allowed; must be one of {self.allowed_protocols}"
            )

        hostname = parsed.hostname
        if not hostname:
            raise SSRFBlockedError("Missing or invalid hostname in URL")

        # Normalize localhost aliases
        clean_host = hostname.strip().lower().strip("[]")
        if clean_host in ("localhost", "localhost.localdomain", "0.0.0.0"):
            raise SSRFBlockedError(
                f"Target host '{hostname}' is a forbidden local destination"
            )

        # Direct IP check
        try:
            if self.is_ip_blocked(clean_host):
                raise SSRFBlockedError(
                    f"Target host '{hostname}' is in a blocked private/loopback network"
                )
        except ValueError:
            pass

        # DNS resolution pre-flight check
        if self.block_private_ips:
            try:
                addr_info = socket.getaddrinfo(clean_host, None)
                for res in addr_info:
                    ip_candidate = res[4][0]
                    if self.is_ip_blocked(ip_candidate):
                        raise SSRFBlockedError(
                            f"Host '{hostname}' resolved to blocked private IP '{ip_candidate}'"
                        )
            except socket.gaierror:
                # DNS failures handled downstream by transport
                pass

        return url

    async def async_validate_url(self, url: str) -> str:
        """Asynchronously validates URL offloading synchronous DNS lookups to worker thread pool."""
        return await asyncio.to_thread(self.validate_url, url)


url_security_policy = URLSecurityPolicy()
