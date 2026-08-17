"""S3 / MinIO Content Addressable Storage (CAS) Adapter with Zstandard Compression.

Enables distributed, durable object storage for compressed crawl artifacts and media.
"""

import io
import os
import hashlib
import logging
from typing import Optional, Tuple, Any
from scraper.config import settings

logger = logging.getLogger(__name__)

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


class S3ContentAddressableStore:
    """Remote S3 / MinIO Content-Addressable Object Store with local read-through caching."""

    def __init__(
        self,
        bucket_name: str = settings.s3_bucket_name,
        endpoint_url: str = settings.s3_endpoint_url,
        access_key: str = settings.s3_access_key_id,
        secret_key: str = settings.s3_secret_access_key,
        region: str = settings.s3_region,
        local_cache_dir: Optional[str] = None,
        s3_client: Optional[Any] = None,
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.local_cache_dir = local_cache_dir or os.path.join(settings.storage_path, "s3_cache")
        os.makedirs(self.local_cache_dir, exist_ok=True)

        if ZSTD_AVAILABLE:
            self.cctx = zstd.ZstdCompressor(level=3)
            self.dctx = zstd.ZstdDecompressor()

        self._s3_client = s3_client
        self._bucket_verified = False

    def _get_client(self):
        if self._s3_client is not None:
            return self._s3_client
        import boto3
        from botocore.client import Config

        session = boto3.session.Session()
        self._s3_client = session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._ensure_bucket()
        return self._s3_client

    def _ensure_bucket(self):
        if self._bucket_verified:
            return
        try:
            client = self._s3_client
            client.head_bucket(Bucket=self.bucket_name)
            self._bucket_verified = True
        except Exception:
            try:
                client = self._s3_client
                client.create_bucket(Bucket=self.bucket_name)
                self._bucket_verified = True
            except Exception as create_err:
                logger.warning(f"Could not head/create S3 bucket '{self.bucket_name}': {create_err}")

    def _get_s3_key(self, content_hash: str) -> str:
        prefix = content_hash[:2]
        return f"cas/{prefix}/{content_hash}.zst"

    def _get_cache_path(self, content_hash: str) -> str:
        prefix = content_hash[:2]
        dir_path = os.path.join(self.local_cache_dir, prefix)
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{content_hash}.zst")

    def store(self, content: bytes) -> Tuple[str, int]:
        """Compress content and store to S3/MinIO CAS with local cache."""
        content_hash = hashlib.sha256(content).hexdigest()
        cache_path = self._get_cache_path(content_hash)
        s3_key = self._get_s3_key(content_hash)

        compressed = self.cctx.compress(content) if ZSTD_AVAILABLE else content

        # Save to local cache
        if not os.path.exists(cache_path):
            with open(cache_path, "wb") as f:
                f.write(compressed)

        # Upload to S3 if not already present
        try:
            client = self._get_client()
            client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=compressed,
                Metadata={"uncompressed-length": str(len(content)), "sha256": content_hash},
            )
        except Exception as e:
            logger.warning(f"Failed to upload {content_hash} to S3 CAS ({e}), saved to local cache")

        return content_hash, len(content)

    def retrieve(self, content_hash: str) -> Optional[bytes]:
        """Retrieve and decompress content from local cache or S3/MinIO CAS."""
        cache_path = self._get_cache_path(content_hash)
        s3_key = self._get_s3_key(content_hash)

        # 1. Try local cache
        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                compressed = f.read()
            if ZSTD_AVAILABLE:
                try:
                    return self.dctx.decompress(compressed)
                except Exception:
                    return compressed
            return compressed

        # 2. Try remote S3
        try:
            client = self._get_client()
            resp = client.get_object(Bucket=self.bucket_name, Key=s3_key)
            compressed = resp["Body"].read()

            # Cache locally
            with open(cache_path, "wb") as f:
                f.write(compressed)

            if ZSTD_AVAILABLE:
                return self.dctx.decompress(compressed)
            return compressed
        except Exception as e:
            logger.error(f"Failed to retrieve {content_hash} from S3 CAS: {e}")
            return None
