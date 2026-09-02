"""Unit tests for dependencies reduction and module structure (§DS-18)."""

import ast
import importlib
from pathlib import Path
import pytest


def test_removed_stub_modules_are_absent():
    """Verify that empty stub modules proxy_manager and session_manager have been removed."""
    acquisition_dir = (
        Path(__file__).resolve().parent.parent.parent / "scraper" / "acquisition"
    )
    assert not (acquisition_dir / "proxy_manager.py").exists()
    assert not (acquisition_dir / "session_manager.py").exists()


def test_no_unused_third_party_imports_in_scraper():
    """Verify that unused heavy dependencies (crawlee, jinja2, bs4, opentelemetry, lxml) are not imported in scraper."""
    scraper_dir = Path(__file__).resolve().parent.parent.parent / "scraper"
    forbidden_prefixes = (
        "crawlee",
        "jinja2",
        "bs4",
        "beautifulsoup4",
        "opentelemetry",
        "lxml",
    )

    found_violations = []

    for py_file in scraper_dir.rglob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(code, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == f or alias.name.startswith(f + ".")
                        for f in forbidden_prefixes
                    ):
                        found_violations.append((str(py_file), alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(
                    node.module == f or node.module.startswith(f + ".")
                    for f in forbidden_prefixes
                ):
                    found_violations.append((str(py_file), node.module))

    assert not found_violations, (
        f"Found forbidden imports in scraper source: {found_violations}"
    )


@pytest.mark.parametrize(
    "module_path",
    [
        "scraper.config",
        "scraper.exceptions",
        "scraper.application.service",
        "scraper.application.job_service",
        "scraper.pipeline.search_pipeline",
        "scraper.discovery.seed_finder",
        "scraper.extraction.engine",
        "scraper.storage.cas",
        "scraper.storage.db",
        "scraper.storage.models",
        "scraper.api.routes",
        "scraper.mcp.server",
        "scraper.cli.main",
    ],
)
def test_core_and_extra_modules_import_cleanly(module_path):
    """Smoke test ensuring all key core and adapter modules import without side-effects."""
    mod = importlib.import_module(module_path)
    assert mod is not None
