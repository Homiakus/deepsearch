"""Proxy Manager (§28)."""

from enum import Enum
from typing import List, Optional
import itertools


class ProxyMode(str, Enum):
    DIRECT = "DIRECT"
    ROUND_ROBIN = "ROUND_ROBIN"
    SESSION_STICKY = "SESSION_STICKY"
    DOMAIN_POOL = "DOMAIN_POOL"


class ProxyManager:
    """Manages proxy rotation and proxy session mapping (§28)."""

    def __init__(
        self, proxies: Optional[List[str]] = None, mode: ProxyMode = ProxyMode.DIRECT
    ):
        self.proxies = proxies or []
        self.mode = mode
        self._iterator = itertools.cycle(self.proxies) if self.proxies else None

    def get_proxy(self, session_id: Optional[str] = None) -> Optional[str]:
        if not self.proxies or self.mode == ProxyMode.DIRECT:
            return None

        if self.mode == ProxyMode.ROUND_ROBIN and self._iterator:
            return next(self._iterator)

        if self.mode == ProxyMode.SESSION_STICKY and session_id:
            # Deterministic hash to sticky proxy mapping
            idx = abs(hash(session_id)) % len(self.proxies)
            return self.proxies[idx]

        return self.proxies[0]
