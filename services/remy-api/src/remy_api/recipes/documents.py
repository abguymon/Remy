"""Upload ingestion for photo / PDF recipe import (PRD FR-6).

Turns a batch of user-uploaded files (phone photos or a PDF) into an
:class:`Extraction` the router routes to one of two LLM paths:

* **text** — a text-native PDF: its embedded text is extracted with
  ``pdfplumber`` and sent through the EXISTING ``recipe_parse_fallback`` text
  prompt (the same path a scraped web page uses).
* **vision** — image files and scanned/image PDFs: images are normalized (and
  PDF pages rendered to images via ``pypdfium2``) and sent through the
  multimodal ``recipe_from_images`` prompt.

This module is framework-free (no FastAPI types) so it unit-tests with plain
bytes. Size/count/type limits raise :class:`UploadRejectedError` (HTTP 422) —
never a silent drop (PRD §9.1).
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from remy_api.errors import APIError
from remy_api.llm.prompt import ImagePart

logger = logging.getLogger("remy.recipes.documents")

# Caps (PRD FR-6 upload limits).
MAX_FILES = 6
MAX_FILE_BYTES = 15_000_000  # 15 MB per file
MAX_PDF_PAGES = 10  # render at most this many pages of a scanned PDF
_MAX_DIMENSION = 1600  # long-edge px for normalized/rendered images
_JPEG_QUALITY = 85
_PDF_RENDER_SCALE = 2.0  # 72dpi * 2 = 144dpi base before downscale
# A text-native PDF has real extractable text; a scanned one has ~none. This is
# the average characters-per-page threshold below which we treat it as scanned.
_TEXT_NATIVE_MIN_CHARS_PER_PAGE = 40

# Content types / extensions we accept. HEIF/HEIC is only supported if the
# optional ``pillow-heif`` plugin is installed (registered below); otherwise it
# is reported as an unsupported type rather than silently mangled.
_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_PDF_TYPES = {"application/pdf"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

try:  # optional; keeps HEIF working where the wheel is available without a hard dep
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _IMAGE_TYPES |= {"image/heic", "image/heif"}
    _IMAGE_EXTS |= {".heic", ".heif"}
except Exception:  # noqa: BLE001 - optional plugin; absence is fine
    pass


class UploadRejectedError(APIError):
    """A file batch violates the upload limits (count, size, or type).

    Carries ``reasons`` (machine codes) so the API surfaces *why* the upload was
    rejected, matching the ``recipe_parse_failed`` convention.
    """

    status_code = 422
    code = "upload_rejected"

    def __init__(self, message: str, *, reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.reasons = reasons or []


@dataclass(frozen=True)
class RawUpload:
    """One uploaded file as read by the router (framework-agnostic)."""

    filename: str
    content_type: str | None
    data: bytes


@dataclass
class Extraction:
    """The routed result of preparing an upload batch.

    ``mode`` is ``"text"`` (route ``text`` through the text prompt) or
    ``"vision"`` (route ``images`` through the multimodal prompt). ``cover_jpeg``
    is the first page/photo re-encoded as JPEG, used as the recipe image.
    """

    mode: str
    text: str | None = None
    images: list[ImagePart] = field(default_factory=list)
    cover_jpeg: bytes | None = None


def _kind(upload: RawUpload) -> str:
    """Classify an upload as ``"image"`` or ``"pdf"``; raise if unsupported."""
    ctype = (upload.content_type or "").split(";", 1)[0].strip().lower()
    name = upload.filename.lower()
    if ctype in _PDF_TYPES or name.endswith(".pdf") or upload.data[:5] == b"%PDF-":
        return "pdf"
    if ctype in _IMAGE_TYPES or any(name.endswith(ext) for ext in _IMAGE_EXTS):
        return "image"
    raise UploadRejectedError(
        f"Unsupported file type for {upload.filename!r}. Upload JPEG, PNG, WEBP, or PDF.",
        reasons=["unsupported_type"],
    )


def _normalize_image(raw: bytes, *, label: str) -> bytes:
    """Decode arbitrary image bytes, downscale, and re-encode as JPEG."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert("RGB")
            img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadRejectedError(
            f"Could not read {label} as an image.",
            reasons=["undecodable_image"],
        ) from exc


def _to_part(jpeg: bytes) -> ImagePart:
    return ImagePart(media_type="image/jpeg", data=base64.b64encode(jpeg).decode("ascii"))


def _extract_pdf_text(raw: bytes) -> tuple[str, int]:
    """Return (concatenated page text, page_count) via pdfplumber."""
    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
    return "\n\n".join(chunks), page_count


def _render_pdf_pages(raw: bytes, *, max_pages: int = MAX_PDF_PAGES) -> list[bytes]:
    """Render up to ``max_pages`` PDF pages to downscaled JPEG bytes."""
    jpegs: list[bytes] = []
    pdf = pdfium.PdfDocument(raw)
    try:
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            bitmap = page.render(scale=_PDF_RENDER_SCALE)
            pil = bitmap.to_pil().convert("RGB")
            pil.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))
            out = io.BytesIO()
            pil.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            jpegs.append(out.getvalue())
    finally:
        pdf.close()
    if not jpegs:
        raise UploadRejectedError("The PDF has no renderable pages.", reasons=["empty_pdf"])
    return jpegs


def _validate_batch(uploads: list[RawUpload]) -> None:
    if not uploads:
        raise UploadRejectedError("No files were uploaded.", reasons=["no_files"])
    if len(uploads) > MAX_FILES:
        raise UploadRejectedError(
            f"Too many files — upload at most {MAX_FILES}.",
            reasons=["too_many_files"],
        )
    for upload in uploads:
        if len(upload.data) == 0:
            raise UploadRejectedError(f"{upload.filename!r} is empty.", reasons=["empty_file"])
        if len(upload.data) > MAX_FILE_BYTES:
            raise UploadRejectedError(
                f"{upload.filename!r} exceeds the {MAX_FILE_BYTES // 1_000_000} MB per-file limit.",
                reasons=["file_too_large"],
            )


def build_extraction(uploads: list[RawUpload]) -> Extraction:
    """Validate and prepare a batch into a routed :class:`Extraction`.

    Routing:
    * a single text-native PDF -> ``text`` mode (embedded text + first page as
      the cover image);
    * anything else (images, a scanned PDF, or a multi-file mix) -> ``vision``
      mode, concatenating every file's images in upload order (a text-native PDF
      inside a multi-file batch is rendered to images so nothing is lost).
    """
    _validate_batch(uploads)
    kinds = [_kind(u) for u in uploads]  # raises on unsupported type before any heavy work

    # Single-PDF fast path: prefer cheap, exact text extraction when the PDF is
    # text-native; fall back to rendering pages for scanned PDFs.
    if len(uploads) == 1 and kinds[0] == "pdf":
        raw = uploads[0].data
        text, page_count = _extract_pdf_text(raw)
        pages = max(page_count, 1)
        if len(text.strip()) >= _TEXT_NATIVE_MIN_CHARS_PER_PAGE * pages:
            cover = _first_pdf_cover(raw)
            return Extraction(mode="text", text=text, cover_jpeg=cover)
        jpegs = _render_pdf_pages(raw)
        parts = [_to_part(j) for j in jpegs]
        return Extraction(mode="vision", images=parts, cover_jpeg=jpegs[0])

    # Vision path over the whole batch, in order.
    images: list[ImagePart] = []
    cover: bytes | None = None
    for upload, kind in zip(uploads, kinds, strict=True):
        if kind == "image":
            jpeg = _normalize_image(upload.data, label=upload.filename)
            images.append(_to_part(jpeg))
            cover = cover or jpeg
        else:  # pdf inside a multi-file batch -> render pages to images
            jpegs = _render_pdf_pages(upload.data)
            images.extend(_to_part(j) for j in jpegs)
            cover = cover or jpegs[0]
    if not images:  # unreachable given validation, but never return an empty vision batch
        raise UploadRejectedError("No usable images were found in the upload.", reasons=["no_images"])
    return Extraction(mode="vision", images=images, cover_jpeg=cover)


def _first_pdf_cover(raw: bytes) -> bytes | None:
    """Render just the first PDF page as a JPEG cover; None on failure (non-fatal)."""
    try:
        return _render_pdf_pages(raw, max_pages=1)[0]
    except Exception as exc:  # noqa: BLE001 - cover image is best-effort (PRD §5)
        logger.info("Could not render PDF cover page: %s", exc)
        return None
