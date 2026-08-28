"""API Security, Authentication, and Workspace Isolation (§DS-08)."""

from pathlib import Path
from typing import Optional
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from scraper.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


async def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(http_bearer),
) -> str:
    """Verifies that protected endpoints require a valid API key via X-API-Key or Bearer token (§DS-08)."""
    expected_key = settings.api_key

    provided_key = None
    if header_key:
        provided_key = header_key
    elif bearer_creds and bearer_creds.credentials:
        provided_key = bearer_creds.credentials

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API authentication token. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or unauthorized API key provided.",
        )

    return provided_key


def resolve_safe_workspace_dir(
    base_dir: Path, target_subpath: Optional[str], default_name: str
) -> Path:
    """Resolves and validates an output export path strictly inside the allowed workspace directory (§DS-08)."""
    base = base_dir.resolve()
    base.mkdir(parents=True, exist_ok=True)

    if not target_subpath:
        target = (base / default_name).resolve()
    else:
        # Sanitize any directory traversal attempts (../, /, \, absolute paths)
        raw_name = Path(target_subpath).name
        if not raw_name or raw_name in (".", ".."):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workspace directory name.",
            )
        target = (base / raw_name).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal forbidden: export target must reside strictly within workspace base directory.",
        )

    return target
