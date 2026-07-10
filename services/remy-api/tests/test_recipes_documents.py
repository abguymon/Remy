"""Unit tests for upload ingestion (recipes/documents.py).

Fixtures are generated in-process (Pillow for images, reportlab for a text-native
PDF, Pillow-into-PDF for a scanned/image PDF) so no binary blobs live in the
repo. No LLM is involved — these test classification, routing, and limits only.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from remy_api.recipes.documents import (
    MAX_FILE_BYTES,
    MAX_FILES,
    Extraction,
    RawUpload,
    UploadRejectedError,
    build_extraction,
)


def _image_bytes(fmt: str = "PNG", size=(320, 240), color=(200, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def _text_pdf_bytes() -> bytes:
    """A real text-native PDF (embedded selectable text) via reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    text = c.beginText(72, 720)
    for line in [
        "Grandma's Lemon Bars",
        "Yield: 16 bars",
        "Ingredients:",
        "2 cups flour",
        "1 cup butter",
        "4 eggs",
        "2 cups sugar",
        "Instructions:",
        "Press the crust into a pan and bake.",
        "Whisk the filling, pour over crust, and bake again.",
    ]:
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()
    return buf.getvalue()


def _scanned_pdf_bytes() -> bytes:
    """An image-only PDF (a photo saved as a PDF page — no extractable text)."""
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), (180, 180, 180)).save(buf, format="PDF")
    return buf.getvalue()


# --- classification / routing -------------------------------------------------


def test_single_image_routes_to_vision():
    ext = build_extraction([RawUpload("photo.png", "image/png", _image_bytes())])
    assert isinstance(ext, Extraction)
    assert ext.mode == "vision"
    assert len(ext.images) == 1
    assert ext.images[0].media_type == "image/jpeg"  # normalized to jpeg
    assert ext.cover_jpeg is not None and ext.cover_jpeg[:3] == b"\xff\xd8\xff"  # JPEG SOI


def test_multiple_images_route_to_vision_in_order():
    ext = build_extraction(
        [
            RawUpload("a.jpg", "image/jpeg", _image_bytes("JPEG", color=(10, 10, 10))),
            RawUpload("b.jpg", "image/jpeg", _image_bytes("JPEG", color=(250, 250, 250))),
        ]
    )
    assert ext.mode == "vision"
    assert len(ext.images) == 2


def test_text_native_pdf_routes_to_text():
    ext = build_extraction([RawUpload("recipe.pdf", "application/pdf", _text_pdf_bytes())])
    assert ext.mode == "text"
    assert ext.text is not None
    assert "Lemon Bars" in ext.text and "flour" in ext.text
    assert ext.images == []
    assert ext.cover_jpeg is not None  # first page rendered as the cover image


def test_scanned_pdf_routes_to_vision():
    ext = build_extraction([RawUpload("scan.pdf", "application/pdf", _scanned_pdf_bytes())])
    assert ext.mode == "vision"
    assert len(ext.images) >= 1
    assert ext.cover_jpeg is not None


def test_pdf_detected_by_magic_bytes_without_content_type():
    ext = build_extraction([RawUpload("mystery", None, _text_pdf_bytes())])
    assert ext.mode == "text"


# --- limits / rejections ------------------------------------------------------


def test_rejects_empty_batch():
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction([])
    assert "no_files" in exc.value.reasons


def test_rejects_too_many_files():
    files = [RawUpload(f"{i}.png", "image/png", _image_bytes()) for i in range(MAX_FILES + 1)]
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction(files)
    assert "too_many_files" in exc.value.reasons


def test_rejects_oversize_file():
    big = RawUpload("big.png", "image/png", b"\x89PNG" + b"0" * (MAX_FILE_BYTES + 1))
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction([big])
    assert "file_too_large" in exc.value.reasons


def test_rejects_empty_file():
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction([RawUpload("empty.png", "image/png", b"")])
    assert "empty_file" in exc.value.reasons


def test_rejects_unsupported_type():
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction([RawUpload("notes.txt", "text/plain", b"hello there")])
    assert "unsupported_type" in exc.value.reasons


def test_rejects_undecodable_image():
    with pytest.raises(UploadRejectedError) as exc:
        build_extraction([RawUpload("broken.png", "image/png", b"not really a png")])
    assert "undecodable_image" in exc.value.reasons
