"""Media Acquisition Downloader Engine (§6, §74 Download Safety).

Asynchronously downloads binary files (PDFs, Word documents, images) with size limits,
path sanitization, image metadata extraction (dimensions, format), and SHA-256 content addressable tracking.
"""

import os
import re
import io
import hashlib
import urllib.parse
import httpx
from typing import Optional, Dict, Any
from scraper.config import settings

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


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
    clean_name = clean_name.strip("_")[:40] or "file"

    return f"{prefix}_{clean_name}{ext}"


async def download_media_file(
    url: str,
    output_dir: str,
    filename_prefix: str = "doc",
    max_bytes: int = 50 * 1024 * 1024,
    timeout_sec: float = 20.0,
    caption: str = "",
) -> Optional[Dict[str, Any]]:
    """Downloads binary file asynchronously with size limits, SHA-256, and image dimension extraction."""
    os.makedirs(output_dir, exist_ok=True)
    filename = sanitize_media_filename(url, prefix=filename_prefix)
    target_path = os.path.join(output_dir, filename)

    user_agent = getattr(settings.robots, "user_agent", "")
    if not user_agent or user_agent == "DeepSearch/1.0":
        user_agent = (
            "DeepSearchBot/1.0 (https://deepsearch.org; contact@deepsearch.org)"
        )

    headers = {"User-Agent": user_agent}

    try:
        transport = httpx.AsyncHTTPTransport(retries=1)
        async with httpx.AsyncClient(
            transport=transport,
            timeout=timeout_sec,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                return None

            content = res.content
            if len(content) > max_bytes or len(content) == 0:
                return None

            # Calculate SHA-256
            sha256 = hashlib.sha256(content).hexdigest()

            # Save file to disk
            with open(target_path, "wb") as f:
                f.write(content)

            content_type = res.headers.get("content-type", "")
            width, height = None, None

            # Extract image dimensions if content is an image
            if content_type.startswith("image/") or any(
                target_path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS
            ):
                try:
                    from PIL import Image

                    with Image.open(io.BytesIO(content)) as img:
                        width, height = img.size
                except Exception:
                    pass

            return {
                "url": url,
                "filename": filename,
                "file_path": target_path,
                "size_bytes": len(content),
                "sha256": sha256,
                "content_type": content_type,
                "width": width,
                "height": height,
                "caption": caption,
            }

    except Exception:
        return None
