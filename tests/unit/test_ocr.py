"""Unit tests for PP-OCRv5 / PaddleOCR-VL-1.6 engine and PixelRAG integration (§37, §38, §39)."""

import io

import pytest

from scraper.contracts import OCREngineProtocol
from scraper.visual.ocr_engine import OCRBoundingBox, OCRResult, PaddleOCREngine
from scraper.visual.pixel_rag import PixelRAGPipeline

try:
    from PIL import Image, ImageDraw

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def create_dummy_image_bytes() -> bytes:
    if not PIL_AVAILABLE:
        return b"fake_image_bytes"
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((10, 10), "DeepSearch OCR", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_engine_protocol_compliance():
    """Verify PaddleOCREngine implements OCREngineProtocol."""
    engine = PaddleOCREngine(ocr_version="PP-OCRv5")
    assert isinstance(engine, OCREngineProtocol)


@pytest.mark.asyncio
async def test_pp_ocrv5_extraction():
    """Verify PP-OCRv5 model extraction and fallback container structure."""
    engine = PaddleOCREngine(ocr_version="PP-OCRv5")
    img_bytes = create_dummy_image_bytes()
    result = await engine.extract_text_from_image(img_bytes)

    assert isinstance(result, OCRResult)
    assert result.model_name.startswith("PP-OCRv5")
    assert result.elapsed_sec >= 0.0
    if result.blocks:
        assert isinstance(result.blocks[0], OCRBoundingBox)


@pytest.mark.asyncio
async def test_pixel_rag_ocr_integration():
    """Verify PixelRAGPipeline processes OCR using PP-OCRv5 engine."""
    pipeline = PixelRAGPipeline(ocr_engine=PaddleOCREngine(ocr_version="PP-OCRv5"))
    img_bytes = create_dummy_image_bytes()
    ocr_result = await pipeline.process_page_ocr(img_bytes)

    assert isinstance(ocr_result, OCRResult)
    assert ocr_result.model_name.startswith("PP-OCRv5")
