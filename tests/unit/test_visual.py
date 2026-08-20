"""Unit tests for Visual Intelligence Engine (§38), Screenshot Tiling (§40), and PixelRAG (§41)."""

import io
from PIL import Image
from scraper.visual.tiling import generate_screenshot_tiles
from scraper.visual.pixel_rag import PixelRAGPipeline


def test_screenshot_tiling():
    # Create synthetic test image (2000x2000 px)
    img = Image.new("RGB", (2000, 2000), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    screenshot_bytes = buf.getvalue()

    tiles = generate_screenshot_tiles(
        "page_123", screenshot_bytes, tile_width=1000, tile_height=1000
    )
    # 2000x2000 sliced into 1000x1000 -> 4 tiles
    assert len(tiles) == 4
    assert tiles[0].page_id == "page_123"
    assert tiles[0].width == 1000
    assert tiles[0].height == 1000
    assert len(tiles[0].image_hash) == 64


def test_pixel_rag_pipeline():
    pipeline = PixelRAGPipeline()
    results = pipeline.search_visual("diagram match")
    assert isinstance(results, list)
