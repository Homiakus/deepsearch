"""Three-Level Deduplication Engine (§17)."""

import hashlib
import re


class Deduplicator:
    """Manages 3 levels of deduplication: URL hash, BLAKE3/SHA256 content hash, SimHash near-duplicate."""

    def __init__(self, simhash_distance_threshold: int = 3, max_simhashes: int = 50000):
        self.url_hashes: set[str] = set()
        self.content_hashes: set[str] = set()
        self.simhashes: dict[int, str] = {}  # simhash_int -> canonical_url
        self.threshold = simhash_distance_threshold
        self.max_simhashes = max_simhashes

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
    def compute_simhash(text: str, max_tokens: int = 10000) -> int:
        """Level 3: SimHash algorithm for near-duplicate text detection."""
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return 0

        if len(tokens) > max_tokens:
            tokens = tokens[:max_tokens]

        from collections import Counter

        token_counts = Counter(tokens)

        v = [0] * 64
        for token, weight in token_counts.items():
            t_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(64):
                if (t_hash >> i) & 1:
                    v[i] += weight
                else:
                    v[i] -= weight

        fingerprint = 0
        for i in range(64):
            if v[i] >= 0:
                fingerprint |= 1 << i

        return fingerprint

    @staticmethod
    def hamming_distance(h1: int, h2: int) -> int:
        """Calculate Hamming distance between two 64-bit integers."""
        return (h1 ^ h2).bit_count()

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

        # Fast exact match check
        if s_hash in self.simhashes:
            return True

        threshold = self.threshold
        for existing_hash in self.simhashes:
            if (s_hash ^ existing_hash).bit_count() <= threshold:
                return True

        if len(self.simhashes) < self.max_simhashes:
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
