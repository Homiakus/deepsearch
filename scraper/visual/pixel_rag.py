"""PixelRAG and Hybrid Retrieval Pipeline (§39, §41)."""

from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel
from scraper.visual.tiling import VisualTile, generate_screenshot_tiles
from scraper.visual.ocr_engine import PaddleOCREngine, OCRResult
from scraper.visual.vlm_embeddings import VLMEmbeddingEngine, VisualEmbedding


class PixelRAGResult(BaseModel):
    page_id: str
    tile_id: int
    score: float
    x: int
    y: int
    image_hash: str
    ocr_text: Optional[str] = None


class PixelRAGPipeline:
    """Manages visual tile processing, PaddleOCR-VL text extraction, and multivector indexing for PixelRAG (§39)."""

    def __init__(
        self,
        ocr_engine: Optional[PaddleOCREngine] = None,
        vlm_engine: Optional[VLMEmbeddingEngine] = None,
    ):
        self.ocr_engine = ocr_engine or PaddleOCREngine()
        self.vlm_engine = vlm_engine or VLMEmbeddingEngine()
        self._indexed_tiles: Dict[str, Tuple[VisualTile, VisualEmbedding]] = {}

    def process_page_screenshot(self, page_id: str, screenshot_bytes: bytes) -> List[VisualTile]:
        """Generate screenshot tiles and index them with VLM embeddings (§40)."""
        tiles = generate_screenshot_tiles(page_id, screenshot_bytes)
        for tile in tiles:
            emb = self.vlm_engine.embed_tile(tile)
            key = f"{tile.page_id}_{tile.tile_id}"
            self._indexed_tiles[key] = (tile, emb)
        return tiles

    async def process_page_ocr(self, screenshot_bytes: bytes) -> OCRResult:
        """Run PaddleOCR visual text & bounding box extraction (§37, §39)."""
        return await self.ocr_engine.extract_text_from_image(screenshot_bytes)

    def search_visual(self, query: str, top_k: int = 5) -> List[PixelRAGResult]:
        """Execute visual multivector vector search against indexed tiles using VLM embeddings (§42)."""
        if not self._indexed_tiles:
            return []

        q_vec = self.vlm_engine.embed_query(query)
        scored: List[PixelRAGResult] = []

        for (tile, emb) in self._indexed_tiles.values():
            sim = self.vlm_engine.compute_similarity(q_vec, emb.vector)
            scored.append(
                PixelRAGResult(
                    page_id=tile.page_id,
                    tile_id=tile.tile_id,
                    score=round(float(sim), 4),
                    x=tile.x,
                    y=tile.y,
                    image_hash=tile.image_hash,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

