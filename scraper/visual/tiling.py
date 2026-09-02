"""Screenshot Tiling Generator (§40)."""

import hashlib
import io

from pydantic import BaseModel

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class VisualTile(BaseModel):
    page_id: str
    tile_id: int
    x: int
    y: int
    width: int
    height: int
    image_hash: str
    tile_bytes: bytes


def generate_screenshot_tiles(
    page_id: str,
    screenshot_bytes: bytes,
    tile_width: int = 1280,
    tile_height: int = 1024,
) -> list[VisualTile]:
    """Slices a full page screenshot into visual tiles (§40)."""
    if not PIL_AVAILABLE or not screenshot_bytes:
        return []

    image = Image.open(io.BytesIO(screenshot_bytes))
    img_w, img_h = image.size

    tiles: list[VisualTile] = []
    tile_id = 0

    for y in range(0, img_h, tile_height):
        for x in range(0, img_w, tile_width):
            crop_w = min(tile_width, img_w - x)
            crop_h = min(tile_height, img_h - y)
            box = (x, y, x + crop_w, y + crop_h)

            tile_img = image.crop(box)
            buf = io.BytesIO()
            tile_img.save(buf, format="PNG")
            t_bytes = buf.getvalue()

            img_hash = hashlib.sha256(t_bytes).hexdigest()

            tiles.append(
                VisualTile(
                    page_id=page_id,
                    tile_id=tile_id,
                    x=x,
                    y=y,
                    width=crop_w,
                    height=crop_h,
                    image_hash=img_hash,
                    tile_bytes=t_bytes,
                )
            )
            tile_id += 1

    return tiles
