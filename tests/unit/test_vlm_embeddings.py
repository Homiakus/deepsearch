"""Unit tests for Multimodal VLM Embeddings and PixelRAG Pipeline."""

from scraper.visual.tiling import VisualTile
from scraper.visual.vlm_embeddings import VLMEmbeddingEngine
from scraper.visual.pixel_rag import PixelRAGPipeline


def test_vlm_embedding_engine_deterministic():
    engine = VLMEmbeddingEngine(embedding_dim=128)

    tile1 = VisualTile(
        page_id="p1",
        tile_id=1,
        x=0,
        y=0,
        width=500,
        height=500,
        tile_bytes=b"tile1",
        image_hash="hash1",
    )
    tile2 = VisualTile(
        page_id="p1",
        tile_id=2,
        x=500,
        y=0,
        width=500,
        height=500,
        tile_bytes=b"tile2",
        image_hash="hash2",
    )

    emb1 = engine.embed_tile(tile1)
    emb1_repeat = engine.embed_tile(tile1)
    emb2 = engine.embed_tile(tile2)

    assert len(emb1.vector) == 128
    assert emb1.vector == emb1_repeat.vector  # deterministic
    assert emb1.vector != emb2.vector

    # Query embedding and cosine similarity
    q_vec = engine.embed_query("chart showing revenue")
    sim1 = engine.compute_similarity(q_vec, emb1.vector)
    assert -1.0 <= sim1 <= 1.0


def test_pixel_rag_pipeline_search():
    engine = VLMEmbeddingEngine(embedding_dim=64)
    pipeline = PixelRAGPipeline(vlm_engine=engine)

    # Fake 1000x1000 PNG image bytes
    from PIL import Image
    import io

    img = Image.new("RGB", (1000, 1000), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    screenshot_bytes = buf.getvalue()

    tiles = pipeline.process_page_screenshot("page_test_1", screenshot_bytes)
    assert len(tiles) > 0

    results = pipeline.search_visual("blue background diagram", top_k=3)
    assert len(results) <= 3
    for r in results:
        assert r.page_id == "page_test_1"
        assert 0 <= r.score <= 1.0 or -1.0 <= r.score <= 1.0
