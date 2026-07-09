"""Recipe image pipeline (PRD §5): download, re-encode, store locally.

Images are downloaded once at save time (never hotlinked), re-encoded to a
web-friendly JPEG (max 1024px, quality 80) with Pillow, and written to
``<recipe_images_dir>/{recipe_id}.jpg``. A missing/failed image is non-fatal:
the functions return ``None`` and the recipe simply has no image.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

from remy_api.config import get_settings

logger = logging.getLogger("remy.recipes.images")

_MAX_DIMENSION = 1024
_JPEG_QUALITY = 80
_DOWNLOAD_TIMEOUT = 10.0
_MAX_IMAGE_BYTES = 15_000_000  # 15 MB cap on a source image download
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) RemyRecipeBot/1.0"


def images_dir() -> Path:
    """Return the configured image directory, creating it if needed."""
    path = Path(get_settings().recipe_images_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_path_for(recipe_id: str) -> Path:
    """Absolute-ish path where ``recipe_id``'s image lives (may not exist)."""
    return images_dir() / f"{recipe_id}.jpg"


def _encode_jpeg(raw: bytes, dest: Path) -> str | None:
    """Re-encode ``raw`` image bytes to a capped JPEG at ``dest``.

    Returns the stored path as a string, or ``None`` if the bytes are not a
    decodable image.
    """
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert("RGB")
            img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.info("Could not decode/encode image for %s: %s", dest.name, exc)
        return None
    return str(dest)


def store_image_bytes(recipe_id: str, raw: bytes) -> str | None:
    """Re-encode already-downloaded bytes and store them. ``None`` on failure."""
    return _encode_jpeg(raw, image_path_for(recipe_id))


async def download_recipe_image(
    recipe_id: str,
    image_url: str | None,
    *,
    client: httpx.AsyncClient | None = None,
    headers: dict[str, str] | None = None,
) -> str | None:
    """Download ``image_url``, re-encode, and store as the recipe's image.

    Returns the stored path (str) or ``None`` — a missing image is fine (§5). A
    caller-supplied ``client``/``headers`` lets the Mealie importer pass auth.
    """
    if not image_url:
        return None
    req_headers = {"User-Agent": _USER_AGENT, **(headers or {})}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
    try:
        resp = await client.get(image_url, headers=req_headers)
        resp.raise_for_status()
        raw = resp.content[: _MAX_IMAGE_BYTES + 1]
        if len(raw) > _MAX_IMAGE_BYTES:
            logger.info("Image for %s exceeds size cap; skipping.", recipe_id)
            return None
    except httpx.HTTPError as exc:
        logger.info("Failed to download image for %s from %s: %s", recipe_id, image_url, exc)
        return None
    finally:
        if owns_client:
            await client.aclose()
    return store_image_bytes(recipe_id, raw)


def delete_recipe_image(recipe_id: str) -> None:
    """Remove a recipe's stored image if present (best-effort)."""
    try:
        image_path_for(recipe_id).unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - unlikely fs error
        logger.info("Could not delete image for %s: %s", recipe_id, exc)
