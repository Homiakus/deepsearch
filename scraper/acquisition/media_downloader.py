"""Media Acquisition Downloader Engine (§6, §74 Download Safety, §DS-07, §DS-14).

Asynchronously downloads binary files (PDFs, Word documents, images) with:
- Strict SSRF check before request and on redirect.
- Content-Length pre-check.
- Stream-based downloading without loading unbounded bytes into memory.
- Decompression bomb / oversized stream limit protection.
- MIME sniffing and magic byte validation to reject HTML error pages masquerading as binary.
- Atomic file write via temporary file replacement.
- Image dimension extraction and SHA-256 content addressable hash computation.
- License, author, and source attribution tracking with explicit UNKNOWN_LICENSE fallback.
"""

import hashlib
import os
import re
import tempfile
import urllib.parse
from typing import Any

import httpx

from scraper.config import settings
from scraper.extraction.pdf_extractor import validate_pdf_stream
from scraper.security.url_policy import url_security_policy

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
UNKNOWN_LICENSE = "UNKNOWN_LICENSE"
UNKNOWN_AUTHOR = "UNKNOWN_AUTHOR"


def sanitize_media_filename(url: str, prefix: str = "doc") -> str:
    """Generates a clean unique filename preserving original file extension and IDs."""
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)

    # If accid query parameter present (e.g. PMC13299106)
    accid = query_params.get("accid", [None])[0]
    if accid:
        return f"{prefix}_{accid}.pdf"

    # Check PMC ID in path
    pmc_match = re.search(r"PMC\d+", url, re.IGNORECASE)
    if pmc_match:
        return f"{prefix}_{pmc_match.group(0).upper()}.pdf"

    basename = os.path.basename(parsed.path)
    ext_match = re.search(r"(\.[a-zA-Z0-9]{2,5})$", basename)

    if ext_match:
        ext = ext_match.group(1).lower()
    else:
        # Default extension based on prefix hint
        ext = ".jpg" if "img" in prefix or "media" in prefix else ".pdf"

    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", basename.replace(ext, ""))
    clean_name = clean_name.strip("_")[:30] or "file"
    url_digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]

    return f"{prefix}_{clean_name}_{url_digest}{ext}"


def _is_valid_binary_header(
    header_chunk: bytes, filename: str, content_type: str
) -> bool:
    """Sniffs magic bytes to ensure file is not HTML/error page disguised as binary."""
    if not header_chunk:
        return False

    # Check for HTML signatures
    lower_hdr = header_chunk.lower()
    if b"<!doctype html" in lower_hdr or b"<html" in lower_hdr or b"<head" in lower_hdr:
        return False

    is_pdf = (
        filename.lower().endswith(".pdf") or "application/pdf" in content_type.lower()
    )
    if is_pdf:
        is_valid_pdf, _ = validate_pdf_stream(header_chunk)
        return is_valid_pdf

    return True


async def download_media_file(
    url: str,
    output_dir: str,
    filename_prefix: str = "doc",
    max_bytes: int = 50 * 1024 * 1024,
    timeout_sec: float = 20.0,
    caption: str = "",
    license: str | None = None,
    author: str | None = None,
    source_domain: str | None = None,
) -> dict[str, Any] | None:
    """Downloads binary file asynchronously using streaming, SSRF checks, atomic writes, and metadata tracking (§DS-14)."""
    try:
        await url_security_policy.async_validate_url(url)
    except Exception:
        return None

    os.makedirs(output_dir, exist_ok=True)
    filename = sanitize_media_filename(url, prefix=filename_prefix)
    target_path = os.path.join(output_dir, filename)

    user_agent = getattr(settings.robots, "user_agent", "")
    if not user_agent or user_agent == "DeepSearch/1.0":
        user_agent = (
            "DeepSearchBot/1.0 (https://deepsearch.org; contact@deepsearch.org)"
        )

    headers = {"User-Agent": user_agent}

    async def _validate_redirect_hook(response: httpx.Response):
        if response.is_redirect and "location" in response.headers:
            redirect_url = str(response.url.join(response.headers["location"]))
            url_security_policy.validate_url(redirect_url)

    temp_file_path = None
    try:
        transport = httpx.AsyncHTTPTransport(retries=1)
        async with (
            httpx.AsyncClient(
                transport=transport,
                timeout=timeout_sec,
                follow_redirects=True,
                trust_env=False,
                event_hooks={"response": [_validate_redirect_hook]},
            ) as client,
            client.stream("GET", url, headers=headers) as res,
        ):
            if res.status_code != 200:
                return None

            # Content-Length pre-check
            content_length_hdr = res.headers.get("content-length")
            if content_length_hdr:
                try:
                    content_len = int(content_length_hdr)
                    if content_len > max_bytes or content_len <= 0:
                        return None
                except ValueError:
                    pass

            content_type = res.headers.get("content-type", "")

            # Atomic write to temporary file in the target directory
            with tempfile.NamedTemporaryFile(
                dir=output_dir, delete=False, prefix=".ds_dl_"
            ) as tmp_f:
                temp_file_path = tmp_f.name
                hasher = hashlib.sha256()
                bytes_read = 0
                header_bytes = bytearray()

                async for chunk in res.aiter_bytes(chunk_size=65536):
                    if not chunk:
                        continue
                    bytes_read += len(chunk)
                    if bytes_read > max_bytes:
                        # Exceeded allowed decompressed bytes / bomb protection
                        return None

                    if len(header_bytes) < 1024:
                        needed = 1024 - len(header_bytes)
                        header_bytes.extend(chunk[:needed])

                    hasher.update(chunk)
                    tmp_f.write(chunk)

            if bytes_read == 0:
                return None

            # Verify magic bytes / reject fake MIME
            if not _is_valid_binary_header(bytes(header_bytes), filename, content_type):
                return None

            # Atomically replace target path
            os.replace(temp_file_path, target_path)
            temp_file_path = None

            sha256 = hasher.hexdigest()

            # Extract dimensions if image
            width, height = None, None
            if content_type.startswith("image/") or any(
                target_path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS
            ):
                try:
                    from PIL import Image

                    with Image.open(target_path) as img:
                        width, height = img.size
                except Exception:
                    pass

            resolved_domain = source_domain or urllib.parse.urlparse(url).netloc or ""

            return {
                "url": url,
                "filename": filename,
                "file_path": target_path,
                "size_bytes": bytes_read,
                "sha256": sha256,
                "content_type": content_type,
                "width": width,
                "height": height,
                "caption": caption,
                "license": license or UNKNOWN_LICENSE,
                "author": author or UNKNOWN_AUTHOR,
                "source_domain": resolved_domain,
            }

    except Exception:
        return None
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass
