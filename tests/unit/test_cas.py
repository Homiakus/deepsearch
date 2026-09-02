"""Unit tests for Content-Addressable Storage (§44) and Zstandard Compression (§45)."""

import shutil
import tempfile

from scraper.storage.cas import ContentAddressableStore


def test_cas_store_and_retrieve():
    temp_dir = tempfile.mkdtemp()
    try:
        cas = ContentAddressableStore(base_dir=temp_dir)
        content = b"Content-Addressable Storage test string with Zstandard compression."

        content_hash, byte_size = cas.store(content)
        assert len(content_hash) == 64
        assert byte_size == len(content)

        retrieved = cas.retrieve(content_hash)
        assert retrieved == content
    finally:
        shutil.rmtree(temp_dir)
