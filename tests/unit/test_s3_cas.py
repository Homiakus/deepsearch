"""Unit tests for S3 / MinIO CAS Adapter."""

import os
from unittest.mock import MagicMock
from scraper.storage.s3_cas import S3ContentAddressableStore
from scraper.storage.cas import get_cas_store, ContentAddressableStore


def test_s3_cas_store_and_retrieve_with_mock_client(tmp_path):
    mock_s3 = MagicMock()
    stored_s3_objects = {}

    def put_object(Bucket, Key, Body, Metadata=None):
        stored_s3_objects[Key] = Body
        return {"ETag": "12345"}

    def get_object(Bucket, Key):
        if Key not in stored_s3_objects:
            raise Exception("NoSuchKey")
        mock_body = MagicMock()
        mock_body.read.return_value = stored_s3_objects[Key]
        return {"Body": mock_body}

    mock_s3.put_object.side_effect = put_object
    mock_s3.get_object.side_effect = get_object
    mock_s3.head_bucket.return_value = {}

    cache_dir = str(tmp_path / "cache")
    cas = S3ContentAddressableStore(
        bucket_name="test-bucket",
        local_cache_dir=cache_dir,
        s3_client=mock_s3,
    )

    test_data = b"Hello, S3 Content Addressable Storage with Zstd compression!"
    content_hash, size = cas.store(test_data)
    assert len(content_hash) == 64
    assert size == len(test_data)

    # Check retrieve from local cache
    retrieved = cas.retrieve(content_hash)
    assert retrieved == test_data

    # Clear local cache to force S3 download
    for f in os.listdir(os.path.join(cache_dir, content_hash[:2])):
        os.remove(os.path.join(cache_dir, content_hash[:2], f))

    retrieved_from_s3 = cas.retrieve(content_hash)
    assert retrieved_from_s3 == test_data


def test_get_cas_store_factory():
    local_store = get_cas_store("local")
    assert isinstance(local_store, ContentAddressableStore)
