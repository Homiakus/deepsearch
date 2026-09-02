"""Global pytest fixtures and test isolation boundaries (§DS-03)."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def hermetic_dns_mock(monkeypatch: pytest.MonkeyPatch):
    """Fast hermetic DNS resolution: prevents slow network DNS timeouts for test domains."""
    orig_getaddrinfo = socket.getaddrinfo

    def mock_getaddrinfo(host, port, *args, **kwargs):
        if not host:
            return orig_getaddrinfo(host, port, *args, **kwargs)
        # Let private / loopback IP literals pass to standard resolver
        h_str = str(host).lower().strip("[]")
        if (
            h_str
            in (
                "127.0.0.1",
                "localhost",
                "localhost.localdomain",
                "0.0.0.0",
                "::1",
                "::",
            )
            or h_str.startswith("10.")
            or h_str.startswith("192.168.")
            or h_str.startswith("172.16.")
            or h_str.startswith("169.254.")
        ):
            return orig_getaddrinfo(host, port, *args, **kwargs)
        # Fast deterministic resolution for standard test hostnames (example.com, arxiv.org, etc.)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)


@pytest.fixture(autouse=True)
def clean_test_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hermetic filesystem isolation: redirect default exports and clean temporary artifacts."""
    test_data_dir = tmp_path / "deepsearch_data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DEEPSEARCH_DATA_DIR", str(test_data_dir))
    monkeypatch.setenv("CAS_STORAGE_PATH", str(test_data_dir / "cas"))

    yield

    # Clean any accidental zip files or exports created in workspace root
    for zip_file in WORKSPACE_ROOT.glob("*.zip"):
        try:
            zip_file.unlink()
        except OSError:
            pass

    for export_dir in WORKSPACE_ROOT.glob("zotero_*"):
        if export_dir.is_dir():
            shutil.rmtree(export_dir, ignore_errors=True)
