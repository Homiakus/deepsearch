"""Unit tests for Topic Media Discovery, Candidate Extraction, and Relevance Scoring."""

from scraper.discovery.media_finder import (
    extract_image_candidates,
    score_and_rank_images,
    is_accepted_media_file,
)


def test_extract_image_candidates():
    html = """
    <html>
        <body>
            <img src="/img/logo.png" alt="Company Logo" class="site-logo" width="50" height="50">
            <figure>
                <img src="https://example.com/figures/laser_cutting_beam.jpg" alt="Fiber Laser Cutting Beam Setup" width="800" height="600">
                <figcaption>Laser Cutting Beam Profile Diagram</figcaption>
            </figure>
            <img src="/charts/cutting_speed_chart.png" title="Laser Cutting Speed vs Thickness Chart" width="600" height="400">
            <img src="/icons/tracking.pixel" width="1" height="1">
        </body>
    </html>
    """
    base_url = "https://example.com/laser_machining"
    candidates = extract_image_candidates(html, base_url)

    assert len(candidates) == 2
    urls = [c["url"] for c in candidates]
    assert "https://example.com/figures/laser_cutting_beam.jpg" in urls
    assert "https://example.com/charts/cutting_speed_chart.png" in urls
    assert candidates[0]["figcaption"] == "Laser Cutting Beam Profile Diagram"


def test_score_and_rank_images_topic_relevance():
    query = "laser cutting speed"
    candidates = [
        {
            "url": "https://example.com/img1.jpg",
            "caption": "Irrelevant random scenery",
            "alt": "Landscape view",
            "source_domain": "scenery.com",
            "width": 800,
            "height": 600,
        },
        {
            "url": "https://commons.wikimedia.org/wiki/File:Laser_cutting_head.jpg",
            "caption": "High power fiber laser cutting head operation with speed controls",
            "alt": "Laser cutting speed experiment",
            "source_domain": "commons.wikimedia.org",
            "width": 1024,
            "height": 768,
        },
        {
            "url": "https://example.com/logo.png",
            "caption": "Site logo icon",
            "alt": "banner logo",
            "source_domain": "example.com",
            "width": 50,
            "height": 50,
        },
    ]

    ranked = score_and_rank_images(candidates, query=query, min_count=1, max_count=5)

    assert len(ranked) >= 1
    # Top ranked image should be the wikimedia laser cutting image
    top_item = ranked[0]
    assert "laser" in top_item["caption"].lower()
    assert top_item["relevance_score"] > 0.6
    assert top_item["source_domain"] == "commons.wikimedia.org"


def test_score_and_rank_images_min_max_bounds():
    query = "quantum algorithms"
    candidates = [
        {
            "url": f"https://example.com/quantum_img_{i}.png",
            "caption": f"Quantum algorithm diagram {i}",
            "alt": f"Quantum circuit {i}",
            "source_domain": "arxiv.org",
            "width": 800,
            "height": 600,
        }
        for i in range(30)
    ]

    # Target 5 to 25 range
    ranked_25 = score_and_rank_images(
        candidates, query=query, min_count=5, max_count=25
    )
    assert len(ranked_25) == 25

    # Target 5 to 10 range
    ranked_10 = score_and_rank_images(
        candidates, query=query, min_count=5, max_count=10
    )
    assert len(ranked_10) == 10


def test_media_quality_gate_rejects_small_and_technical_assets():
    assert not is_accepted_media_file(
        {"width": 10, "height": 10, "relevance_score": 0.9},
        {"caption": "Topic image"},
    )
    assert not is_accepted_media_file(
        {"width": 800, "height": 600, "relevance_score": 0.9},
        {"caption": "Creative Commons licence badge"},
    )
    assert is_accepted_media_file(
        {"width": 800, "height": 600, "relevance_score": 0.8},
        {"caption": "Quantum algorithm diagram"},
    )
