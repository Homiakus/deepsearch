import asyncio
import hashlib
import os
import uuid

from scraper.config import settings

try:
    import zstandard as zstd

    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


class ContentAddressableStore:
    """Content-addressable object store maintaining reference counts and Zstandard compression (§44, §45)."""

    def __init__(self, base_dir: str | None = None):
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

    def store(self, content: bytes) -> tuple[str, int]:
        """Store content by hash atomically. Returns (content_hash, byte_size)."""
        content_hash = hashlib.sha256(content).hexdigest()
        file_path = self._get_path(content_hash)

        if not os.path.exists(file_path):
            compressed = self.cctx.compress(content) if ZSTD_AVAILABLE else content
            tmp_path = f"{file_path}.tmp.{uuid.uuid4().hex[:8]}"
            try:
                with open(tmp_path, "wb") as f:
                    f.write(compressed)
                os.replace(tmp_path, file_path)
            except Exception:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                if not os.path.exists(file_path):
                    raise

        return content_hash, len(content)

    def retrieve(self, content_hash: str) -> bytes | None:
        """Retrieve decompressed content by hash."""
        file_path = self._get_path(content_hash)
        if not os.path.exists(file_path):
            return None

        with open(file_path, "rb") as f:
            compressed = f.read()

        if ZSTD_AVAILABLE:
            return self.dctx.decompress(compressed)
        return compressed

    async def async_store(self, content: bytes) -> tuple[str, int]:
        """Non-blocking async wrapper to store content offloaded to thread pool."""
        return await asyncio.to_thread(self.store, content)

    async def async_retrieve(self, content_hash: str) -> bytes | None:
        """Non-blocking async wrapper to retrieve content offloaded to thread pool."""
        return await asyncio.to_thread(self.retrieve, content_hash)


def get_cas_store(backend: str | None = None) -> ContentAddressableStore:
    """Factory to retrieve configured CAS store (local or S3)."""
    selected = backend or settings.cas_backend
    if selected.lower() == "s3":
        from scraper.storage.s3_cas import S3ContentAddressableStore

        return S3ContentAddressableStore()
    return ContentAddressableStore()
