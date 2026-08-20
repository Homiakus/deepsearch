"""Unit tests for OpenAccessResolver and DOI bypass engine (DS-OA01)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from scraper.acquisition.open_access_resolver import (
    OpenAccessResolver,
    open_access_resolver,
)


def test_extract_doi_from_urls():
    # Nature DOI pattern
    assert (
        open_access_resolver.extract_doi_from_url_or_text(
            "https://www.nature.com/articles/s41416-023-02337-4?fromPaywallRec=false"
        )
        == "10.1038/s41416-023-02337-4"
    )

    # Springer DOI pattern
    assert (
        open_access_resolver.extract_doi_from_url_or_text(
            "https://link.springer.com/article/10.1186/s12943-024-02063-2"
        )
        == "10.1186/s12943-024-02063-2"
    )

    # ASCO DOI pattern
    assert (
        open_access_resolver.extract_doi_from_url_or_text(
            "https://ascopubs.org/doi/10.1200/JCO.21.02615"
        )
        == "10.1200/JCO.21.02615"
    )

    # Text containing DOI
    assert (
        open_access_resolver.extract_doi_from_url_or_text(
            "Found paper with doi: 10.1073/pnas.1704961114 in oncology."
        )
        == "10.1073/pnas.1704961114"
    )


@pytest.mark.asyncio
async def test_resolve_doi_unpaywall_mock():
    mock_payload = {
        "doi": "10.1038/s41416-023-02337-4",
        "title": "Colorectal cancer detected by liquid biopsy 2 years prior to clinical diagnosis",
        "is_oa": True,
        "oa_status": "gold",
        "best_oa_location": {
            "url_for_pdf": "https://www.nature.com/articles/s41416-023-02337-4.pdf",
            "url_for_landing_page": "https://www.nature.com/articles/s41416-023-02337-4",
            "repository_institution": "Nature Publishing Group",
        },
        "year": 2023,
    }

    resolver = OpenAccessResolver()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        res = await resolver.resolve_doi_unpaywall("10.1038/s41416-023-02337-4")
        assert res is not None
        assert res.is_open_access is True
        assert res.oa_status == "gold"
        assert res.pdf_url == "https://www.nature.com/articles/s41416-023-02337-4.pdf"
