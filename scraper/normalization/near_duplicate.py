import hashlib
import re
import threading
from collections import namedtuple

NearDupCheckResult = namedtuple(
    "NearDupCheckResult", ["is_near_duplicate", "duplicate_of_id", "cluster_id"]
)


class NearDuplicateDetector:
    """Manages 64-bit SimHash index with Multi-Index Hash tables and Hamming distance clustering."""

    def __init__(self, hamming_threshold: int = 12):
        self.hamming_threshold = hamming_threshold
        self._fingerprints: dict[str, int] = {}  # doc_id -> simhash_int
        self._clusters: dict[int, list[str]] = {}  # cluster_id -> [doc_ids]
        self._tables: list[dict[int, set[str]]] = [{}, {}, {}, {}]  # 4 x 16-bit buckets
        self._next_cluster_id = 1
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Clear all registered fingerprints and clusters."""
        with self._lock:
            self._fingerprints.clear()
            self._clusters.clear()
            self._tables = [{}, {}, {}, {}]
            self._next_cluster_id = 1

    @staticmethod
    def _get_blocks(fp: int) -> tuple[int, int, int, int]:
        return (
            fp & 0xFFFF,
            (fp >> 16) & 0xFFFF,
            (fp >> 32) & 0xFFFF,
            (fp >> 48) & 0xFFFF,
        )

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
        """Registers a document using Multi-Index lookup and returns NearDupCheckResult."""
        fp = self.compute_simhash(text)
        if fp == 0:
            return NearDupCheckResult(False, None, 0)

        with self._lock:
            # Candidate pre-filtering: check for direct candidates via 4-block index
            blocks = self._get_blocks(fp)
            candidates: set[str] = set()
            for i, b in enumerate(blocks):
                if b in self._tables[i]:
                    candidates.update(self._tables[i][b])

            # If candidates found via block matches, check them first
            for existing_id in candidates:
                existing_fp = self._fingerprints.get(existing_id)
                if existing_fp is not None:
                    dist = self.hamming_distance(fp, existing_fp)
                    if dist <= self.hamming_threshold:
                        cluster_id = 0
                        for cid, members in self._clusters.items():
                            if existing_id in members:
                                cluster_id = cid
                                members.append(doc_id)
                                break
                        self._fingerprints[doc_id] = fp
                        for idx, blk in enumerate(blocks):
                            self._tables[idx].setdefault(blk, set()).add(doc_id)
                        return NearDupCheckResult(True, existing_id, cluster_id)

            # Fallback scan over non-candidate fingerprints only if candidates didn't match
            # (guarantees completeness for hamming_threshold > 15)
            if len(self._fingerprints) < 1000 or self.hamming_threshold > 15:
                for existing_id, existing_fp in list(self._fingerprints.items()):
                    if existing_id in candidates:
                        continue
                    dist = self.hamming_distance(fp, existing_fp)
                    if dist <= self.hamming_threshold:
                        cluster_id = 0
                        for cid, members in self._clusters.items():
                            if existing_id in members:
                                cluster_id = cid
                                members.append(doc_id)
                                break
                        self._fingerprints[doc_id] = fp
                        for idx, blk in enumerate(blocks):
                            self._tables[idx].setdefault(blk, set()).add(doc_id)
                        return NearDupCheckResult(True, existing_id, cluster_id)

            # New unique cluster
            cid = self._next_cluster_id
            self._next_cluster_id += 1
            self._clusters[cid] = [doc_id]
            self._fingerprints[doc_id] = fp
            for idx, blk in enumerate(blocks):
                self._tables[idx].setdefault(blk, set()).add(doc_id)
            return NearDupCheckResult(False, None, cid)


near_duplicate_detector = NearDuplicateDetector(hamming_threshold=12)
