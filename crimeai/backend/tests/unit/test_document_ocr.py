"""Scanned PDFs and multi-page TIFFs are rendered page by page and OCR'd with one detected script."""
import io
import shutil
import sys
import types

import pytest

from app.nlp import documents
from app.nlp.documents import extract_text

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
ImageFont = pytest.importorskip("PIL.ImageFont")


def _page(text: str):
    image = Image.new("L", (1600, 600), 255)
    ImageDraw.Draw(image).text((60, 220), text, fill=0, font=ImageFont.load_default(size=64))
    return image


def _scanned_pdf(*texts: str) -> bytes:
    """Image-only PDF, like the output of a photocopier: no text layer at all."""
    buf = io.BytesIO()
    pages = [_page(t).convert("RGB") for t in texts]
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


def _multipage_tiff(*texts: str) -> bytes:
    buf = io.BytesIO()
    pages = [_page(t) for t in texts]
    pages[0].save(buf, format="TIFF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


@pytest.fixture
def fake_tesseract(monkeypatch):
    """Records each OCR call; returns the page number so joins and page order can be checked."""
    calls = {"osd": 0, "pages": []}

    def image_to_string(image, lang, config):
        calls["pages"].append(lang)
        return f"page {len(calls['pages'])} text of a complaint"

    def image_to_osd(image, output_type):
        calls["osd"] += 1
        return {"script": "Telugu"}

    module = types.SimpleNamespace(
        get_languages=lambda config: ["eng", "tel", "hin"],
        image_to_string=image_to_string,
        image_to_osd=image_to_osd,
        Output=types.SimpleNamespace(DICT="dict"),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", module)
    return calls


def test_scanned_pdf_is_ocrd_page_by_page(fake_tesseract):
    pytest.importorskip("pypdfium2")
    result = extract_text(_scanned_pdf("one", "two", "three"), "application/pdf")

    assert not result.needs_ocr
    assert result.method == "tesseract:tel+eng"
    assert result.text.split("\n\n") == [f"page {n} text of a complaint" for n in (1, 2, 3)]
    assert fake_tesseract["osd"] == 1, "script is detected once and reused for every page"


def test_scanned_pdf_page_cap(fake_tesseract, monkeypatch):
    pytest.importorskip("pypdfium2")
    monkeypatch.setattr(documents, "_MAX_OCR_PAGES", 2)
    extract_text(_scanned_pdf("a", "b", "c", "d"), "application/pdf")
    assert len(fake_tesseract["pages"]) == 2


def test_multipage_tiff_reads_every_frame(fake_tesseract):
    result = extract_text(_multipage_tiff("one", "two"), "image/tiff")
    assert len(fake_tesseract["pages"]) == 2 and "page 2" in result.text


def test_scanned_pdf_waits_for_ocr_without_tesseract(monkeypatch):
    pytest.importorskip("pypdfium2")
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    result = extract_text(_scanned_pdf("one"), "application/pdf")
    assert result.needs_ocr and result.text == ""


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is installed only in the worker image")
def test_real_ocr_of_scanned_pdf():
    pytest.importorskip("pypdfium2")
    pytest.importorskip("pytesseract")
    result = extract_text(_scanned_pdf("Mobile phone stolen near Karol Bagh"), "application/pdf")
    assert "phone" in result.text.lower() and "stolen" in result.text.lower()
