"""Unified URL Security Policy and SSRF Defense (§25, §26, DS-A20)."""

import ipaddress
import socket
import urllib.parse
from typing import List, Optional
from scraper.config import settings
from scraper.exceptions import SSRFBlockedError


class URLSecurityPolicy:
    """Validates URLs, resolves DNS, and blocks private/loopback/link-local destinations."""

    # RFC 1918, RFC 3927, RFC 4193, loopback, link-local
    BLOCKED_CIDRS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    def __init__(
        self,
        block_private_ips: Optional[bool] = None,
        allowed_protocols: Optional[List[str]] = None,
        max_response_size: Optional[int] = None,
    ):
        self.block_private_ips = block_private_ips if block_private_ips is not None else settings.security.block_private_ips
        self.allowed_protocols = allowed_protocols or settings.security.allowed_protocols
        self.max_response_size = max_response_size or settings.security.max_response_size_bytes

    def is_ip_blocked(self, ip_str: str) -> bool:
        """Checks if an IP string belongs to private, loopback, or reserved subnets."""
        try:
            ip = ipaddress.ip_address(ip_str)
            if not self.block_private_ips:
                return False
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
            for cidr in self.BLOCKED_CIDRS:
                if ip in cidr:
                    return True
            return False
        except ValueError:
            return False

    def validate_url(self, url: str) -> str:
        """Validates protocol, host, and resolves DNS to prevent SSRF."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in self.allowed_protocols:
            raise SSRFBlockedError(f"Protocol '{parsed.scheme}' not allowed")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFBlockedError("Missing hostname in URL")

        # Direct IP check
        try:
            if self.is_ip_blocked(hostname):
                raise SSRFBlockedError(f"Target host {hostname} is in a blocked private/loopback network")
        except ValueError:
            pass

        # DNS resolution pre-flight check
        if self.block_private_ips:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for res in addr_info:
                    ip_candidate = res[4][0]
                    if self.is_ip_blocked(ip_candidate):
                        raise SSRFBlockedError(f"Host {hostname} resolved to blocked IP {ip_candidate}")
            except socket.gaierror:
                # DNS failure can be handled downstream by fetcher
                pass

        return url


url_security_policy = URLSecurityPolicy()
