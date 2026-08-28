"""Global pytest fixtures and test isolation boundaries (§DS-03)."""

from __future__ import annotations

import shutil
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


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
