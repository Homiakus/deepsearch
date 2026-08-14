"""Unit tests for Media Finder and Downloader Modules."""

import pytest
from scraper.discovery.media_finder import extract_document_links, extract_relevant_images
from scraper.acquisition.media_downloader import sanitize_media_filename


def test_extract_document_links():
    html = """
    <html>
        <body>
            <a href="/papers/study_2024.pdf">Download PDF</a>
            <a href="https://arxiv.org/pdf/2401.12345">ArXiv PDF</a>
            <a href="/data/dataset.csv">CSV Data</a>
            <a href="https://example.com/about">About Page</a>
        </body>
    </html>
    """
    base_url = "https://example.com"
    docs = extract_document_links(html, base_url)
    
    assert len(docs) == 3
    assert any(d.endswith(".pdf") for d in docs)
    assert any("arxiv.org/pdf" in d for d in docs)
    assert any(d.endswith(".csv") for d in docs)


def test_extract_relevant_images():
    html = """
    <html>
        <body>
            <img src="/img/logo.png" alt="Company Logo" class="site-logo" width="50" height="50">
            <img src="https://example.com/figures/hair_follicle_diagram.jpg" alt="Hair Follicle Anagen Phase Diagram" width="800" height="600">
            <img src="/charts/clinical_trial_results.png" title="JAK Inhibitor Response Chart" width="600" height="400">
        </body>
    </html>
    """
    base_url = "https://example.com"
    images = extract_relevant_images(html, base_url)
    
    assert len(images) == 2
    assert images[0]["url"] == "https://example.com/figures/hair_follicle_diagram.jpg"
    assert "Diagram" in images[0]["caption"]
    assert images[1]["url"] == "https://example.com/charts/clinical_trial_results.png"


def test_sanitize_media_filename():
    fn1 = sanitize_media_filename("https://arxiv.org/pdf/2401.12345.pdf", prefix="doc_001")
    assert fn1.startswith("doc_001")
    assert fn1.endswith(".pdf")

    fn2 = sanitize_media_filename("https://example.com/images/figure1.jpg?token=123", prefix="img")
    assert fn2.startswith("img")
    assert fn2.endswith(".jpg")
