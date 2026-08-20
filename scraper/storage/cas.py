"""Content-Addressable Storage (CAS) Engine with Zstandard Compression (§44, §45)."""

import os
import hashlib
from typing import Tuple, Optional
from scraper.config import settings

try:
    import zstandard as zstd

    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


class ContentAddressableStore:
    """Content-addressable object store maintaining reference counts and Zstandard compression (§44, §45)."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or settings.storage_path
        os.makedirs(self.base_dir, exist_ok=True)
        if ZSTD_AVAILABLE:
            self.cctx = zstd.ZstdCompressor(level=3)
            self.dctx = zstd.ZstdDecompressor()

    def _get_path(self, content_hash: str) -> str:
        # Shard path by first 2 characters
        prefix = content_hash[:2]
        dir_path = os.path.join(self.base_dir, prefix)
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{content_hash}.zst")

    def store(self, content: bytes) -> Tuple[str, int]:
        """Store content by hash. Returns (content_hash, byte_size)."""
        content_hash = hashlib.sha256(content).hexdigest()
        file_path = self._get_path(content_hash)

        if not os.path.exists(file_path):
            compressed = self.cctx.compress(content) if ZSTD_AVAILABLE else content
            with open(file_path, "wb") as f:
                f.write(compressed)

        return content_hash, len(content)

    def retrieve(self, content_hash: str) -> Optional[bytes]:
        """Retrieve decompressed content by hash."""
        file_path = self._get_path(content_hash)
        if not os.path.exists(file_path):
            return None

        with open(file_path, "rb") as f:
            compressed = f.read()

        if ZSTD_AVAILABLE:
            return self.dctx.decompress(compressed)
        return compressed


def get_cas_store(backend: Optional[str] = None) -> ContentAddressableStore:
    """Factory to retrieve configured CAS store (local or S3)."""
    selected = backend or settings.cas_backend
    if selected.lower() == "s3":
        from scraper.storage.s3_cas import S3ContentAddressableStore

        return S3ContentAddressableStore()
    return ContentAddressableStore()
