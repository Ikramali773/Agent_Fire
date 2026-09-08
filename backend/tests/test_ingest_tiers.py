"""Tests app/ingest/tiers.py against REAL PDFs and REAL Tesseract OCR calls -
no mocks. Fixture PDFs/images are generated on the fly with pymupdf/PIL
rather than checked in as binary files.
"""

import io

import pymupdf
from PIL import Image

from app.ingest.tiers import (
    TIER1_MIN_TEXT_LENGTH,
    extract_text_layer,
    ocr_standard,
    ocr_with_preprocessing,
    render_pdf_pages,
)


def make_text_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=14)
        y += 24
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def make_blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestTier1TextLayer:
    def test_extracts_native_text_with_high_confidence(self):
        pdf_bytes = make_text_pdf(
            ["Fire Safety Plan - Residential Apartment Building", "Height: 32 meters, State: Gujarat"]
        )
        result = extract_text_layer(pdf_bytes)
        assert result.tier == 1
        assert "Residential Apartment Building" in result.text
        assert result.confidence > 0

    def test_blank_pdf_gets_zero_confidence(self):
        result = extract_text_layer(make_blank_pdf())
        assert result.confidence == 0.0

    def test_short_text_below_threshold_gets_zero_confidence(self):
        pdf_bytes = make_text_pdf(["hi"])
        assert len("hi") < TIER1_MIN_TEXT_LENGTH
        result = extract_text_layer(pdf_bytes)
        assert result.confidence == 0.0


class TestTier2And3Ocr:
    def test_ocr_standard_reads_rendered_text_correctly(self):
        pdf_bytes = make_text_pdf(["Built-up area: 4500 sqm", "Floors above ground: 10"])
        images = render_pdf_pages(pdf_bytes)
        result = ocr_standard(images)
        assert result.tier == 2
        assert "4500" in result.text
        assert result.confidence > 60

    def test_ocr_corrects_180_degree_rotation(self):
        # Tesseract's orientation detection (OSD) needs a reasonable amount
        # of text to work reliably - a single short line isn't enough
        # signal, confirmed while writing this test, so this uses a
        # multi-line page like a real document would have.
        pdf_bytes = make_text_pdf(
            ["Occupancy: Storage building", "Height: 12 meters", "State: Maharashtra"]
        )
        images = render_pdf_pages(pdf_bytes)
        rotated = [images[0].rotate(180)]
        result = ocr_standard(rotated)
        assert "Storage" in result.text
        assert result.confidence > 60

    def test_preprocessing_tier_also_reads_correctly(self):
        pdf_bytes = make_text_pdf(["Number of staircases: 2", "Number of exits: 3"])
        images = render_pdf_pages(pdf_bytes)
        result = ocr_with_preprocessing(images)
        assert result.tier == 3
        assert "staircases" in result.text.lower()

    def test_blank_page_ocr_gets_low_confidence(self):
        images = render_pdf_pages(make_blank_pdf())
        result = ocr_standard(images)
        assert result.confidence == 0.0
        assert result.text.strip() == ""


class TestRenderPdfPages:
    def test_renders_one_image_per_page(self):
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        images = render_pdf_pages(pdf_bytes)
        assert len(images) == 2
        assert all(isinstance(img, Image.Image) for img in images)
