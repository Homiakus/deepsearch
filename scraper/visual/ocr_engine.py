"""PP-OCRv5 & PaddleOCR-VL-1.6 Visual OCR Engine (§37, §38, §39)."""

import io
import time
import logging
from typing import List, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False


class OCRBoundingBox(BaseModel):
    """Bounding box coordinates and recognized text block from PP-OCRv5 / PaddleOCR-VL-1.6."""
    text: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    box: List[List[float]] = Field(
        default_factory=list,
        description="4 points defining polygon bounding box [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"
    )


class OCRResult(BaseModel):
    """Complete OCR extraction result containing full text and structured bounding boxes."""
    full_text: str
    blocks: List[OCRBoundingBox] = Field(default_factory=list)
    mean_confidence: float = 1.0
    model_name: str = "PP-OCRv5"
    elapsed_sec: float = 0.0


class PaddleOCREngine:
    """Engine supporting PP-OCRv5, PP-OCRv4, and PaddleOCR-VL-1.6 for document & visual retrieval (§37, §38)."""

    def __init__(
        self,
        lang: str = "en",
        ocr_version: str = "PP-OCRv5",
        use_angle_cls: bool = True,
        show_log: bool = False
    ):
        self.lang = lang
        self.ocr_version = ocr_version
        self.use_angle_cls = use_angle_cls
        self.show_log = show_log
        self._ocr_instance: Optional[Any] = None

    def _get_ocr_instance(self):
        if not PADDLE_AVAILABLE:
            return None
        if self._ocr_instance is None:
            try:
                self._ocr_instance = PaddleOCR(
                    use_angle_cls=self.use_angle_cls,
                    lang=self.lang,
                    show_log=self.show_log,
                    ocr_version=self.ocr_version
                )
            except Exception as e:
                logger.warning("Failed to initialize native PaddleOCR (%s) instance: %s", self.ocr_version, e)
                return None
        return self._ocr_instance

    async def extract_text_from_image(self, image_bytes: bytes) -> OCRResult:
        """Extract text and bounding boxes from image bytes using PP-OCRv5 / PaddleOCR-VL-1.6 (§37, §39)."""
        start_t = time.time()

        if not image_bytes:
            return OCRResult(full_text="", blocks=[], mean_confidence=1.0, model_name=self.ocr_version, elapsed_sec=0.0)

        ocr_instance = self._get_ocr_instance()

        if ocr_instance:
            try:
                # Open image from bytes
                image = Image.open(io.BytesIO(image_bytes)) if PIL_AVAILABLE else None
                import numpy as np
                img_np = np.array(image) if image else image_bytes

                results = ocr_instance.ocr(img_np, cls=self.use_angle_cls)
                blocks: List[OCRBoundingBox] = []
                extracted_texts: List[str] = []
                total_conf = 0.0

                if results and results[0]:
                    for line in results[0]:
                        box_coords = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        text, conf = line[1]
                        blocks.append(OCRBoundingBox(
                            text=text,
                            confidence=float(conf),
                            box=[[float(pt[0]), float(pt[1])] for pt in box_coords]
                        ))
                        extracted_texts.append(text)
                        total_conf += float(conf)

                full_text = "\n".join(extracted_texts)
                mean_conf = (total_conf / len(blocks)) if blocks else 1.0

                return OCRResult(
                    full_text=full_text,
                    blocks=blocks,
                    mean_confidence=round(mean_conf, 4),
                    model_name=self.ocr_version,
                    elapsed_sec=round(time.time() - start_t, 4)
                )
            except Exception as e:
                logger.warning("Error running %s inference: %s", self.ocr_version, e)

        # Fallback mode when paddleocr is not installed or inference fails
        full_text = ""
        blocks: List[OCRBoundingBox] = []

        if PIL_AVAILABLE and image_bytes:
            try:
                img = Image.open(io.BytesIO(image_bytes))
                w, h = img.size
                blocks.append(OCRBoundingBox(
                    text=f"[{self.ocr_version} Fallback Container {w}x{h}]",
                    confidence=1.0,
                    box=[[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]]
                ))
                full_text = f"[{self.ocr_version} Fallback Container {w}x{h}]"
            except Exception:
                pass

        return OCRResult(
            full_text=full_text,
            blocks=blocks,
            mean_confidence=1.0,
            model_name=f"{self.ocr_version} (Fallback)",
            elapsed_sec=round(time.time() - start_t, 4)
        )
