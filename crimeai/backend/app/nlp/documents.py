"""Identify uploaded documents by content (not by client-declared type) and extract their text."""
from __future__ import annotations

import io
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)
SUPPORTED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/tiff", "text/plain"}

# Tesseract script names (from orientation-and-script detection) -> installed language packs.
_SCRIPT_TO_TESSERACT = {
    "Devanagari": "hin+mar",
    "Bengali": "ben+asm",
    "Gurmukhi": "pan",
    "Gujarati": "guj",
    "Oriya": "ori",
    "Tamil": "tam",
    "Telugu": "tel",
    "Kannada": "kan",
    "Malayalam": "mal",
    "Arabic": "urd",
    "Latin": "eng",
}
_MIN_TEXT = 20
# Scanned FIRs run to a few pages; the cap bounds worker time and memory for oversized uploads.
_MAX_OCR_PAGES = 15
_PDF_RENDER_DPI = 250


@dataclass(frozen=True, slots=True)
class ExtractedText:
    text: str
    method: str
    needs_ocr: bool = False


def sniff_content_type(data: bytes) -> str | None:
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    try:
        data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain" if b"\x00" not in data[:4096] else None


def extract_text(data: bytes, content_type: str) -> ExtractedText:
    if content_type == "text/plain":
        return ExtractedText(data.decode("utf-8", errors="replace"), "plain_text")
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:50]).strip()
        if len(text) >= _MIN_TEXT:
            return ExtractedText(text, "pdf_text_layer")
        return _ocr_scanned_pdf(data)
    return _ocr_image(data)


def _ocr_scanned_pdf(data: bytes) -> ExtractedText:
    """A PDF without a text layer is a scan: render each page and OCR it like a photo."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ExtractedText("", "none", needs_ocr=True)
    pdf = pdfium.PdfDocument(data)
    try:
        pages = [
            pdf[i].render(scale=_PDF_RENDER_DPI / 72, grayscale=True).to_pil()
            for i in range(min(len(pdf), _MAX_OCR_PAGES))
        ]
    finally:
        pdf.close()
    return _ocr_pages(pages, source="pdf")


def _prepare(image):
    """Scans and phone photos OCR far better as upscaled, contrast-stretched greyscale."""
    from PIL import ImageOps

    image = ImageOps.exif_transpose(image).convert("L")
    if image.width < 1800:
        factor = 1800 / image.width
        image = image.resize((round(image.width * factor), round(image.height * factor)))
    return ImageOps.autocontrast(image, cutoff=1)


def _detect_languages(pytesseract, image, installed: set[str]) -> str:
    """Pick Tesseract language packs from the detected script, always keeping English for mixed text."""
    script = None
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        script = osd.get("script")
    except Exception as exc:
        logger.info("ocr_script_detection_failed", error=str(exc)[:120])
    packs = [p for p in _SCRIPT_TO_TESSERACT.get(script or "", "").split("+") if p in installed]
    if not packs:
        # Unknown script: try every installed Indic pack; Tesseract scores the best fit per line.
        packs = [p for p in ("hin", "tel", "tam", "ben", "kan", "mal", "guj", "pan", "ori", "urd") if p in installed]
    if "eng" in installed and "eng" not in packs:
        packs.append("eng")
    return "+".join(packs) or "eng"


def _ocr_image(data: bytes) -> ExtractedText:
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return ExtractedText("", "none", needs_ocr=True)
    image = Image.open(io.BytesIO(data))
    # Multi-page TIFF is the usual output of office scanners.
    pages = [frame.copy() for _, frame in zip(range(_MAX_OCR_PAGES), ImageSequence.Iterator(image), strict=False)]
    return _ocr_pages(pages, source="image")


def _ocr_pages(pages: list, source: str) -> ExtractedText:
    """OCR runs where Tesseract is installed (the worker image); elsewhere the FIR waits in awaiting_ocr."""
    try:
        import pytesseract
    except ImportError:
        return ExtractedText("", "none", needs_ocr=True)
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return ExtractedText("", "none", needs_ocr=True)
    if not pages:
        return ExtractedText("", "none", needs_ocr=True)

    # One complaint is written in one script; detect it on the first page and reuse it for the rest.
    languages = _detect_languages(pytesseract, _prepare(pages[0]), installed)
    text = "\n\n".join(
        pytesseract.image_to_string(_prepare(page), lang=languages, config="--oem 1 --psm 4").strip() for page in pages
    ).strip()
    logger.info("ocr_complete", source=source, pages=len(pages), languages=languages, characters=len(text))
    return ExtractedText(text, f"tesseract:{languages}", needs_ocr=len(text) < _MIN_TEXT)
