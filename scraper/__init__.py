"""Adaptive Web Scraping & Retrieval Platform."""

import os

# Sanitize NO_PROXY environment variable for httpx compatibility on Windows
for _k in ("NO_PROXY", "no_proxy"):
    if _k in os.environ and ":" in os.environ[_k]:
        _parts = [
            p.strip()
            for p in os.environ[_k].split(",")
            if p.strip() and not p.strip().startswith(":")
        ]
        os.environ[_k] = ",".join(_parts)

__version__ = "1.0.0"
