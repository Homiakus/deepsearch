"""Near-Duplicate Fingerprint Engine (DS-SI34).

Uses 64-bit SimHash over tokens/shingles to detect syndicated and mirror copies.
"""

import hashlib
import re
from collections import namedtuple

NearDupCheckResult = namedtuple(
    "NearDupCheckResult", ["is_near_duplicate", "duplicate_of_id", "cluster_id"]
)


class NearDuplicateDetector:
    """Manages 64-bit SimHash index with Hamming distance clustering."""

    def __init__(self, hamming_threshold: int = 12):
        self.hamming_threshold = hamming_threshold
        self._fingerprints: dict[str, int] = {}  # doc_id -> simhash_int
        self._clusters: dict[int, list[str]] = {}  # cluster_id -> [doc_ids]
        self._next_cluster_id = 1

    @staticmethod
    def compute_simhash(
        text: str, shingle_size: int = 2, max_shingles: int = 10000
    ) -> int:
        """Computes 64-bit SimHash over word tokens/shingles."""
        tokens = [t for t in re.findall(r"\w+", text.lower()) if len(t) > 1]
        if not tokens:
            return 0

        # Generate shingles
        if len(tokens) < shingle_size:
            shingles = tokens[:max_shingles]
        else:
            limit = min(len(tokens) - shingle_size + 1, max_shingles)
            if shingle_size == 2:
                shingles = [f"{tokens[i]} {tokens[i + 1]}" for i in range(limit)]
            else:
                shingles = [
                    " ".join(tokens[i : i + shingle_size]) for i in range(limit)
                ]

        from collections import Counter

        shingle_counts = Counter(shingles)

        v = [0] * 64
        for sh, weight in shingle_counts.items():
            sh_hash = int(hashlib.md5(sh.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(64):
                if (sh_hash >> i) & 1:
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
        return (h1 ^ h2).bit_count()

    def register_document(self, doc_id: str, text: str) -> NearDupCheckResult:
        """Registers a document and returns NearDupCheckResult(is_near_dup, existing_doc_id, cluster_id)."""
        fp = self.compute_simhash(text)
        if fp == 0:
            return NearDupCheckResult(False, None, 0)

        for existing_id, existing_fp in self._fingerprints.items():
            dist = self.hamming_distance(fp, existing_fp)
            if dist <= self.hamming_threshold:
                # Find cluster
                cluster_id = 0
                for cid, members in self._clusters.items():
                    if existing_id in members:
                        cluster_id = cid
                        members.append(doc_id)
                        break
                self._fingerprints[doc_id] = fp
                return NearDupCheckResult(True, existing_id, cluster_id)

        # New unique cluster
        cid = self._next_cluster_id
        self._next_cluster_id += 1
        self._clusters[cid] = [doc_id]
        self._fingerprints[doc_id] = fp
        return NearDupCheckResult(False, None, cid)


near_duplicate_detector = NearDuplicateDetector(hamming_threshold=12)
