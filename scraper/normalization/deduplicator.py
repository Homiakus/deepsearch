"""Three-Level Deduplication Engine (§17)."""

import hashlib
import re


class Deduplicator:
    """Manages 3 levels of deduplication: URL hash, BLAKE3/SHA256 content hash, SimHash near-duplicate."""

    def __init__(self, simhash_distance_threshold: int = 3):
        self.url_hashes: set[str] = set()
        self.content_hashes: set[str] = set()
        self.simhashes: dict[int, str] = {}  # simhash_int -> canonical_url
        self.threshold = simhash_distance_threshold

    @staticmethod
    def hash_url(canonical_url: str) -> str:
        """Level 1: Canonical URL hash."""
        return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_content(content_bytes: bytes) -> str:
        """Level 2: Content-level hash (BLAKE3 fallback to SHA256)."""
        try:
            import blake3

            return blake3.blake3(content_bytes).hexdigest()
        except ImportError:
            return hashlib.sha256(content_bytes).hexdigest()

    @staticmethod
    def compute_simhash(text: str) -> int:
        """Level 3: SimHash algorithm for near-duplicate text detection."""
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return 0

        v = [0] * 64
        for token in tokens:
            # 64-bit hash of token
            t_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(64):
                bitmask = 1 << i
                if t_hash & bitmask:
                    v[i] += 1
                else:
                    v[i] -= 1

        fingerprint = 0
        for i in range(64):
            if v[i] >= 0:
                fingerprint |= 1 << i

        return fingerprint

    @staticmethod
    def hamming_distance(h1: int, h2: int) -> int:
        """Calculate Hamming distance between two 64-bit integers."""
        x = h1 ^ h2
        set_bits = 0
        while x > 0:
            set_bits += x & 1
            x >>= 1
        return set_bits

    def is_url_duplicate(self, canonical_url: str) -> bool:
        u_hash = self.hash_url(canonical_url)
        if u_hash in self.url_hashes:
            return True
        self.url_hashes.add(u_hash)
        return False

    def is_content_duplicate(self, content_bytes: bytes) -> bool:
        c_hash = self.hash_content(content_bytes)
        if c_hash in self.content_hashes:
            return True
        self.content_hashes.add(c_hash)
        return False

    def is_near_duplicate(self, text: str) -> bool:
        s_hash = self.compute_simhash(text)
        if s_hash == 0:
            return False

        for existing_hash in self.simhashes.keys():
            if self.hamming_distance(s_hash, existing_hash) <= self.threshold:
                return True

        self.simhashes[s_hash] = text[:100]
        return False

    def compute_hashes(self, text: str):
        """Computes content hash and SimHash for a given text."""
        from collections import namedtuple

        HashResult = namedtuple("HashResult", ["blake3_hash", "simhash_64"])
        content_bytes = text.encode("utf-8")
        b3 = self.hash_content(content_bytes)
        sh = self.compute_simhash(text)
        return HashResult(blake3_hash=b3, simhash_64=sh)
